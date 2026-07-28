from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .embeddings import DeterministicEmbeddingFunction, cosine


class JsonVectorCollection:
    def __init__(self, path: Path, embedder: DeterministicEmbeddingFunction):
        self.path = path
        self.embedder = embedder
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            self.records = json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.records, indent=2), encoding="utf-8")

    def add(self, ids, documents, metadatas, embeddings=None):
        embeddings = embeddings or self.embedder(documents)
        for rid, doc, meta, emb in zip(ids, documents, metadatas, embeddings):
            self.records[rid] = {"document": doc, "metadata": meta, "embedding": emb}
        self._save()

    def delete(self, ids=None, where=None):
        if ids:
            for rid in ids:
                self.records.pop(rid, None)
        elif where:
            doomed = [rid for rid, rec in self.records.items() if _match_where(rec["metadata"], where)]
            for rid in doomed:
                self.records.pop(rid, None)
        else:
            self.records.clear()
        self._save()

    def get(self, ids=None, where=None, include=None):
        items = self.records.items()
        if ids:
            idset = set(ids)
            items = [(rid, rec) for rid, rec in items if rid in idset]
        if where:
            items = [(rid, rec) for rid, rec in items if _match_where(rec["metadata"], where)]
        ids_out, docs, metas = [], [], []
        for rid, rec in items:
            ids_out.append(rid)
            docs.append(rec["document"])
            metas.append(rec["metadata"])
        return {"ids": ids_out, "documents": docs, "metadatas": metas}

    def query(self, query_embeddings, n_results=5, where=None, include=None):
        q = query_embeddings[0]
        scored = []
        for rid, rec in self.records.items():
            if where and not _match_where(rec["metadata"], where):
                continue
            distance = 1.0 - cosine(q, rec["embedding"])
            scored.append((distance, rid, rec))
        scored.sort(key=lambda x: x[0])
        top = scored[:n_results]
        return {
            "ids": [[rid for _, rid, _ in top]],
            "documents": [[rec["document"] for _, _, rec in top]],
            "metadatas": [[rec["metadata"] for _, _, rec in top]],
            "distances": [[dist for dist, _, _ in top]],
        }

    def count(self) -> int:
        return len(self.records)


def _match_where(metadata: dict[str, Any], where: dict[str, Any]) -> bool:
    for key, expected in where.items():
        actual = metadata.get(key)
        if isinstance(expected, dict):
            if "$eq" in expected and actual != expected["$eq"]:
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$contains" in expected and str(expected["$contains"]) not in str(actual):
                return False
        elif actual != expected:
            return False
    return True


class VectorStore:
    def __init__(self, persist_dir: Path, knowledge_name: str, cache_name: str):
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.embedder = DeterministicEmbeddingFunction()
        self.chroma_available = False
        try:
            import chromadb

            self.client = chromadb.PersistentClient(path=str(persist_dir))
            self.knowledge = self.client.get_or_create_collection(
                name=knowledge_name, embedding_function=self.embedder
            )
            self.cache = self.client.get_or_create_collection(
                name=cache_name, embedding_function=self.embedder
            )
            self.chroma_available = True
        except Exception:
            self.client = None
            self.knowledge = JsonVectorCollection(persist_dir / f"{knowledge_name}.json", self.embedder)
            self.cache = JsonVectorCollection(persist_dir / f"{cache_name}.json", self.embedder)

    def reset(self) -> None:
        if self.chroma_available and self.client:
            for name in [self.knowledge.name, self.cache.name]:
                try:
                    self.client.delete_collection(name)
                except Exception:
                    pass
            self.knowledge = self.client.get_or_create_collection(
                name=self.knowledge.name, embedding_function=self.embedder
            )
            self.cache = self.client.get_or_create_collection(name=self.cache.name, embedding_function=self.embedder)
        else:
            shutil.rmtree(self.persist_dir, ignore_errors=True)
            self.persist_dir.mkdir(parents=True, exist_ok=True)
