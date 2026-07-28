from __future__ import annotations

import json
from pathlib import Path

from .models import RetrieveRequest
from .store import KnowledgeStore


def evaluate_retrieval(store: KnowledgeStore, ground_truth_path: Path) -> dict[str, float]:
    cases = json.loads(ground_truth_path.read_text(encoding="utf-8-sig"))["queries"]
    p3_total = recall5_total = mrr_total = leakage_total = 0.0
    for case in cases:
        resp = store.retrieve(RetrieveRequest(query=case["query"], role=case["role"], top_k=5))
        expected = set(case["expected_document_ids"])
        docs = [r.document_id for r in resp.results]
        p3_total += len(expected.intersection(docs[:3])) / 3
        recall5_total += len(expected.intersection(docs[:5])) / max(1, len(expected))
        rank = next((idx + 1 for idx, doc_id in enumerate(docs) if doc_id in expected), None)
        mrr_total += 0.0 if rank is None else 1.0 / rank
        leakage_total += 1.0 if resp.leakage_detected else 0.0
    n = max(1, len(cases))
    return {
        "query_count": float(n),
        "precision_at_3": round(p3_total / n, 4),
        "recall_at_5": round(recall5_total / n, 4),
        "mrr": round(mrr_total / n, 4),
        "leakage_rate": round(leakage_total / n, 4),
    }

