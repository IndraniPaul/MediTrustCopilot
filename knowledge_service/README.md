# MediTrust AI Knowledge Service

Member 1 owns this module: ingestion, data preparation, Chroma-backed retrieval, role-aware metadata filtering, semantic response caching, cache invalidation and retrieval evaluation.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn knowledge_service.app:app --host 127.0.0.1 --port 8001
```

Then ingest the seeded public and synthetic documents:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/ingest -Method Post -ContentType 'application/json' -Body '{"reset":true}'
```

## API

- `GET /health`
- `POST /ingest`
- `POST /retrieve`
- `POST /cache/lookup`
- `POST /cache/write`
- `POST /cache/invalidate?document_id=CDC-IPC-CORE-001`

The service uses Chroma `PersistentClient` with `meditrust_knowledge` and `meditrust_response_cache` collections when `chromadb` is installed. If Chroma cannot load in mock/offline mode, it falls back to JSON vector files under `storage/chroma` and reports `status=degraded`.

## Safety Boundaries

This service returns evidence chunks and cached validated responses only. It does not diagnose, prescribe, calculate dosage or generate clinical recommendations. Synthetic SOPs are explicitly labelled demonstration-only.
