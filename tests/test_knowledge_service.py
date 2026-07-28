from pathlib import Path

from fastapi.testclient import TestClient

from knowledge_service.app import app, get_store
from knowledge_service.evaluation import evaluate_retrieval
from knowledge_service.models import CacheLookupRequest, CacheWriteRequest, IngestRequest, RetrieveRequest


def setup_module():
    store = get_store()
    store.ingest(IngestRequest(reset=True))


def test_ingest_loads_seed_corpus():
    store = get_store()
    resp = store.ingest(IngestRequest(reset=True))
    assert resp.documents_loaded == 20
    assert resp.chunks_loaded >= 20


def test_retrieve_returns_public_hand_hygiene_evidence():
    store = get_store()
    resp = store.retrieve(RetrieveRequest(query="when should nurses clean hands after glove removal", role="nurse", top_k=3))
    assert resp.evidence_status == "sufficient"
    assert any(r.document_id in {"CDC-HAND-003", "CDC-IPC-CORE-001"} for r in resp.results)
    assert all("nurse" in r.metadata["access_roles"].split(",") or "public" in r.metadata["access_roles"].split(",") for r in resp.results)


def test_role_filter_blocks_pharmacist_from_nurse_only_synthetic_sop():
    store = get_store()
    resp = store.retrieve(RetrieveRequest(query="PPE cart par level shortages", role="pharmacist", top_k=5, source_type="synthetic_sop"))
    assert all(r.document_id != "SYN-SOP-012" for r in resp.results)
    assert not resp.leakage_detected


def test_cache_write_and_lookup():
    store = get_store()
    retrieve = store.retrieve(RetrieveRequest(query="safe injection practices", role="pharmacist", top_k=1))
    citation = retrieve.results[0].citation
    write = store.cache_write(
        CacheWriteRequest(
            query="What are safe injection practices?",
            role="pharmacist",
            filters={"status": "active"},
            answer="Use aseptic technique and safe sharps handling; this is not dosage guidance.",
            citations=[citation],
            source_versions={citation.document_id: citation.version_date},
        )
    )
    assert write.stored
    hit = store.cache_lookup(CacheLookupRequest(query="what are safe injection practices", role="pharmacist", filters={"status": "active"}))
    assert hit.cache_hit
    assert hit.validation_status == "pass"


def test_cache_ttl_invalidation():
    store = get_store()
    retrieve = store.retrieve(RetrieveRequest(query="hand hygiene", role="nurse", top_k=1))
    citation = retrieve.results[0].citation
    store.cache_write(
        CacheWriteRequest(
            query="temporary ttl hand hygiene",
            role="nurse",
            answer="Temporary answer",
            citations=[citation],
            ttl_seconds=-1,
            source_versions={citation.document_id: citation.version_date},
        )
    )
    miss = store.cache_lookup(CacheLookupRequest(query="temporary ttl hand hygiene", role="nurse"))
    assert not miss.cache_hit
    assert miss.reason in {"expired", "miss"}


def test_fastapi_contract_health_and_retrieve():
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    payload = {"query": "environmental cleaning high touch surfaces", "role": "administrator", "top_k": 3}
    resp = client.post("/retrieve", json=payload)
    assert resp.status_code == 200
    assert resp.json()["schema_version"] == "1.0"


def test_evaluation_metrics_shape():
    metrics = evaluate_retrieval(get_store(), Path("data/evaluation/ground_truth.json"))
    assert metrics["query_count"] == 50.0
    assert 0.0 <= metrics["precision_at_3"] <= 1.0
    assert metrics["leakage_rate"] == 0.0
