from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knowledge_service.config import get_settings
from knowledge_service.evaluation import evaluate_retrieval
from knowledge_service.models import IngestRequest
from knowledge_service.store import KnowledgeStore


if __name__ == "__main__":
    store = KnowledgeStore(get_settings())
    ingest = store.ingest(IngestRequest(reset=True))
    print(ingest.model_dump())
    print(evaluate_retrieval(store, Path("data/evaluation/ground_truth.json")))

