# MediTrust AI - Member 1 Knowledge Service Integration Guide

This document is for Members 2, 3, and 4 to integrate with Member 1's Knowledge Service.

Member 1 owns:

- Healthcare document ingestion
- Data preparation
- ChromaDB/vector-backed RAG retrieval
- Metadata-aware retrieval
- Role-aware retrieval
- Semantic response cache
- Cache validation and invalidation
- Retrieval evaluation
- Knowledge Service FastAPI endpoints

The Knowledge Service does not diagnose, prescribe, calculate dosage, select treatment, or generate patient-specific clinical recommendations. It only returns evidence chunks and validated cached answers.

---

## 1. Service Base URL

Run locally at:

```text
http://127.0.0.1:8001
```

FastAPI Swagger UI:

```text
http://127.0.0.1:8001/docs
```

Health check:

```text
http://127.0.0.1:8001/health
```

Note: Opening `http://127.0.0.1:8001/` returns `{"detail":"Not Found"}` because no root route is defined. This is expected.

---

## 2. Start Knowledge Service

From the project root:

```powershell
python -m uvicorn knowledge_service.app:app --host 127.0.0.1 --port 8001
```

The service must remain running while other members test integration.

---

## 3. Health Endpoint

### Endpoint

```http
GET /health
```

### Example

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
```

### Example Response

```json
{
  "schema_version": "1.0",
  "service": "knowledge_service",
  "status": "ok",
  "chroma_available": true,
  "knowledge_collection": "meditrust_knowledge",
  "cache_collection": "meditrust_response_cache",
  "persist_directory": "storage\\chroma"
}
```

If `status` is `degraded` and `chroma_available` is `false`, the service is using the local JSON vector fallback instead of real ChromaDB. Retrieval can still work, but for final integration ChromaDB should be installed and available.

---

## 4. Ingest Documents

Call this once before retrieval, or whenever source documents are changed.

### Endpoint

```http
POST /ingest
```

### Request Body

```json
{
  "reset": true
}
```

### PowerShell Example

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/ingest" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"reset":true}'
```

### Example Response

```json
{
  "schema_version": "1.0",
  "documents_loaded": 20,
  "chunks_loaded": 62,
  "duplicates_skipped": 8,
  "collection": "meditrust_knowledge"
}
```

### Integration Notes

- Member 4 can call this during local demo setup.
- Member 2 and Member 3 usually do not need to call `/ingest` during normal workflow execution.
- Re-ingesting with `reset: true` rebuilds the retrieval collection.

---

## 5. Retrieve Evidence

This is the main RAG endpoint.

Members 2 and 4 will call this endpoint to retrieve evidence chunks.

Important: retrieval must happen only after Member 3 input governance or Member 2 risk routing has screened the user input. Unsafe, high-risk, emergency, patient-specific diagnosis/treatment, dosage, restricted-data, or prompt-injection requests must be blocked or escalated before calling `/retrieve`.

### Endpoint

```http
POST /retrieve
```

### Request Body

```json
{
  "query": "When should healthcare workers perform hand hygiene?",
  "role": "nurse",
  "top_k": 5,
  "status": "active",
  "source_type": "public_guideline"
}
```

### Required Fields

```text
query: string
role: user role
top_k: number of results to return
```

### Optional Fields

```text
status: active | superseded | expired | draft
source_type: public_guideline | synthetic_sop
document_ids: list of document IDs to restrict retrieval
tags: list of tags to restrict retrieval
```

### Allowed Roles

```text
doctor
nurse
pharmacist
compliance_officer
administrator
public
```

### PowerShell Example

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/retrieve" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"query":"When should healthcare workers perform hand hygiene?","role":"nurse","top_k":5,"status":"active","source_type":"public_guideline"}'
```

### Example Response Shape

```json
{
  "schema_version": "1.0",
  "request_id": "REQ-UUID",
  "query": "When should healthcare workers perform hand hygiene?",
  "role": "nurse",
  "results": [
    {
      "chunk_id": "CDC-HAND-003::ch000::abc123",
      "document_id": "CDC-HAND-003",
      "title": "CDC Clinical Safety: Hand Hygiene for Healthcare Workers",
      "section": "When to Clean Hands",
      "text": "Evidence chunk text...",
      "score": 0.91,
      "metadata": {
        "document_id": "CDC-HAND-003",
        "title": "CDC Clinical Safety: Hand Hygiene for Healthcare Workers",
        "publisher": "CDC",
        "url": "https://www.cdc.gov/clean-hands/hcp/clinical-safety/index.html",
        "source_type": "public_guideline",
        "version_date": "2024-02-27",
        "status": "active",
        "access_roles": "doctor,nurse,pharmacist,compliance_officer,administrator,public",
        "synthetic": "false",
        "tags": "hand-hygiene,clinical-safety",
        "section": "When to Clean Hands"
      },
      "citation": {
        "document_id": "CDC-HAND-003",
        "title": "CDC Clinical Safety: Hand Hygiene for Healthcare Workers",
        "section": "When to Clean Hands",
        "publisher": "CDC",
        "url": "https://www.cdc.gov/clean-hands/hcp/clinical-safety/index.html",
        "version_date": "2024-02-27",
        "source_type": "public_guideline",
        "synthetic": false,
        "chunk_id": "CDC-HAND-003::ch000::abc123",
        "score": 0.91
      }
    }
  ],
  "evidence_status": "sufficient",
  "leakage_detected": false
}
```

### Important Response Fields

```text
results: retrieved evidence chunks
evidence_status: sufficient | insufficient
leakage_detected: true | false
citation: citation-ready source metadata for downstream answer validation
metadata.access_roles: role authorization details
metadata.status: active/superseded/expired/draft
metadata.synthetic: true/false
```

### Safety Rules for Members 2, 3, and 4

- If `evidence_status` is `insufficient`, Member 2 should not perform unrestricted Gemini generation.
- If `leakage_detected` is `true`, Member 3 should treat it as a governance failure.
- Synthetic SOPs have `synthetic: true` and must be displayed as demonstration-only.
- Returned evidence should be used as context only; the Knowledge Service does not produce clinical advice.

---

## 6. Semantic Cache Lookup

Member 2 should call cache lookup after input guard/risk screening and before normal RAG generation.

### Endpoint

```http
POST /cache/lookup
```

### Request Body

```json
{
  "query": "When should nurses clean their hands?",
  "role": "nurse",
  "filters": {
    "status": "active"
  }
}
```

### PowerShell Example

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/cache/lookup" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"query":"When should nurses clean their hands?","role":"nurse","filters":{"status":"active"}}'
```

### Cache Hit Response

```json
{
  "schema_version": "1.0",
  "request_id": "REQ-UUID",
  "cache_hit": true,
  "answer": "Validated cached answer...",
  "citations": [],
  "validation_status": "pass",
  "reason": null,
  "expires_at": "2026-07-29T10:00:00Z",
  "similarity": 0.92
}
```

### Cache Miss Response

```json
{
  "schema_version": "1.0",
  "request_id": "REQ-UUID",
  "cache_hit": false,
  "answer": null,
  "citations": [],
  "validation_status": null,
  "reason": "miss",
  "expires_at": null,
  "similarity": null
}
```

### Integration Notes

- Cache lookup must happen only after unsafe/high-risk input is blocked or escalated. This same rule also applies to `/retrieve`.
- Do not use cached answers for a different role.
- The service validates TTL and source-version compatibility before returning a hit.
- If cache lookup fails or returns miss, Member 2 should continue to normal retrieval.

---

## 7. Semantic Cache Write

Member 2 or Member 4 should write to cache only after Member 3 validates the answer.

Do not cache unsafe, escalated, blocked, evidence-only failure, or unvalidated generated responses.

### Endpoint

```http
POST /cache/write
```

### Request Body

```json
{
  "query": "What are safe injection practices?",
  "role": "pharmacist",
  "filters": {
    "status": "active"
  },
  "answer": "Use aseptic technique and safe sharps handling. This is not dosage or prescribing guidance.",
  "citations": [
    {
      "document_id": "CDC-INJECTION-006",
      "title": "CDC Safe Injection Practices",
      "section": "Safe Injection",
      "publisher": "CDC",
      "url": "https://www.cdc.gov/infection-control/hcp/basics/standard-precautions.html",
      "version_date": "2024-04-03",
      "source_type": "public_guideline",
      "synthetic": false,
      "chunk_id": "CDC-INJECTION-006::example",
      "score": 0.91
    }
  ],
  "validation_status": "pass",
  "source_versions": {
    "CDC-INJECTION-006": "2024-04-03"
  }
}
```

### Example Response

```json
{
  "schema_version": "1.0",
  "request_id": "REQ-UUID",
  "cache_key": "{\"filters\":{\"status\":\"active\"},\"query\":\"what are safe injection practices?\",\"role\":\"pharmacist\"}",
  "stored": true,
  "expires_at": "2026-07-29T10:00:00Z"
}
```

### Required Cache Write Conditions

Only write to cache when:

```text
validation_status is pass or pass_with_warning
requires_human_review is false
evidence_status is sufficient
citations are valid
answer is not high-risk clinical advice
answer is not dosage/prescribing/diagnosis content
```

---

## 8. Cache Invalidation

Use this if documents are updated, superseded, expired, or source versions change.

### Endpoint

```http
POST /cache/invalidate
```

### Invalidate All Cache Entries

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/cache/invalidate" `
  -Method Post
```

### Invalidate Cache Entries for One Document

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/cache/invalidate?document_id=CDC-HAND-003" `
  -Method Post
```

### Example Response

```json
{
  "invalidated": 2,
  "document_id": "CDC-HAND-003"
}
```

---

## 9. Recommended Integration Flow

### Member 2 - Orchestration Service

Member 2 should use the Knowledge Service in this order:

1. Receive already-screened or risk-classified query.
2. Call `POST /cache/lookup`.
3. If `cache_hit` is `true`, send cached answer to Member 3 for validation or revalidation if needed.
4. If cache miss, call `POST /retrieve`.
5. If `evidence_status` is `insufficient`, use safe fallback or escalation.
6. If evidence is sufficient, pass retrieved `results[].text` as context to optimization/generation.
7. After Member 3 validates the final answer, call `POST /cache/write`.

### Member 3 - Governance Service

Member 3 should validate:

1. `document_id` exists in returned citations.
2. `section` exists in returned citation metadata.
3. `version_date` matches source metadata.
4. `status` is `active`.
5. The requesting `role` is allowed by `metadata.access_roles`.
6. `synthetic: true` sources are not presented as approved clinical policy.
7. Final generated answer is grounded in returned evidence.
8. `leakage_detected` is `false`.

### Member 4 - Integration Gateway and Frontend

Member 4 should:

1. Keep browser calls routed through the BFF/gateway, not directly to `8001`.
2. Call `GET /health` for system-health display.
3. Call `POST /ingest` during local setup or demo reset.
4. Call `POST /retrieve` for evidence explorer or backend workflow integration.
5. Display citations using `citation.title`, `citation.section`, `citation.publisher`, `citation.url`, and `citation.version_date`.
6. Display synthetic SOP badges when `citation.synthetic` is `true`.
7. Display an insufficient evidence state when `evidence_status` is `insufficient`.

---

## 10. Contract Summary

### Main Endpoints

```text
GET  /health
POST /ingest
POST /retrieve
POST /cache/lookup
POST /cache/write
POST /cache/invalidate
```

### Primary Contract for RAG

```text
POST /retrieve
```

Input:

```text
query
role
top_k
status
source_type
document_ids
tags
```

Output:

```text
request_id
results[]
evidence_status
leakage_detected
results[].text
results[].citation
results[].metadata
```

### Primary Contract for Semantic Cache

```text
POST /cache/lookup
POST /cache/write
```

Cache hit means Gemini/model generation can be avoided, but only after safety and role checks have passed.

---

## 11. Validation Evidence

Member 1 has tested:

```text
/health returned HTTP 200
/ingest completed successfully
/retrieve returned role-aware evidence results
retrieval evaluation script printed Precision@3, Recall@5, MRR, and leakage rate
```

The evaluation script is:

```powershell
python scripts\evaluate_member1.py
```

---

## 12. Important Files

```text
knowledge_service/app.py
knowledge_service/models.py
knowledge_service/store.py
knowledge_service/README.md
knowledge_service/samples/retrieve_request.json
knowledge_service/samples/cache_write_request.json
data/source_manifest.json
data/evaluation/ground_truth.json
```

