from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .manifest import load_manifest, role_allowed
from .models import (
    CacheLookupRequest,
    CacheLookupResponse,
    CacheWriteRequest,
    CacheWriteResponse,
    Citation,
    IngestRequest,
    IngestResponse,
    RetrieveRequest,
    RetrieveResponse,
    RetrievedChunk,
)
from .text_processing import chunk_section, content_hash, detect_sections, normalize_query, read_document
from .vector_store import VectorStore


class KnowledgeStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.vector = VectorStore(
            settings.chroma_persist_directory,
            settings.chroma_knowledge_collection,
            settings.chroma_cache_collection,
        )

    def ingest(self, request: IngestRequest) -> IngestResponse:
        if request.reset:
            self.vector.reset()
            self.vector = VectorStore(
                self.settings.chroma_persist_directory,
                self.settings.chroma_knowledge_collection,
                self.settings.chroma_cache_collection,
            )
        manifest_path = Path(request.manifest_path) if request.manifest_path else self.settings.source_manifest_path
        docs = load_manifest(manifest_path)
        ids, texts, metas = [], [], []
        seen_hashes: set[str] = set()
        duplicates = 0
        for doc in docs:
            path = Path(doc.file_path)
            if not path.is_absolute():
                path = manifest_path.parent.parent / path
            raw = read_document(path)
            for section, body in detect_sections(raw):
                for idx, (_, chunk_text) in enumerate(chunk_section(section, body)):
                    h = content_hash(chunk_text)
                    if h in seen_hashes:
                        duplicates += 1
                        continue
                    seen_hashes.add(h)
                    chunk_id = f"{doc.document_id}::ch{idx:03d}::{h[:10]}"
                    ids.append(chunk_id)
                    texts.append(chunk_text)
                    metas.append(
                        {
                            "document_id": doc.document_id,
                            "title": doc.title,
                            "publisher": doc.publisher,
                            "url": doc.url or "",
                            "source_type": doc.source_type,
                            "license_terms": doc.license_terms,
                            "version_date": doc.version_date,
                            "status": doc.status,
                            "access_roles": ",".join(doc.access_roles),
                            "synthetic": str(doc.synthetic).lower(),
                            "tags": ",".join(doc.tags),
                            "section": section,
                            "content_hash": h,
                        }
                    )
        if ids:
            self.vector.knowledge.add(
                ids=ids,
                documents=texts,
                metadatas=metas,
                embeddings=self.vector.embedder(texts),
            )
        return IngestResponse(
            documents_loaded=len(docs),
            chunks_loaded=len(ids),
            duplicates_skipped=duplicates,
            collection=self.settings.chroma_knowledge_collection,
        )

    def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        where = {"status": request.status}
        if request.source_type:
            where["source_type"] = request.source_type
        query_embedding = self.vector.embedder([request.query])[0]
        raw = self.vector.knowledge.query(
            query_embeddings=[query_embedding],
            n_results=max(request.top_k * 4, request.top_k),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        rows = []
        for chunk_id, text, meta, distance in zip(
            raw.get("ids", [[]])[0],
            raw.get("documents", [[]])[0],
            raw.get("metadatas", [[]])[0],
            raw.get("distances", [[]])[0],
        ):
            if request.document_ids and meta["document_id"] not in request.document_ids:
                continue
            if request.tags and not set(request.tags).intersection(set(str(meta.get("tags", "")).split(","))):
                continue
            allowed_roles = str(meta.get("access_roles", "")).split(",")
            if request.role not in allowed_roles and "public" not in allowed_roles:
                continue
            score = max(0.0, 1.0 - float(distance))
            score += self._keyword_boost(request.query, meta, text)
            rows.append((score, chunk_id, text, meta))
        rows.sort(key=lambda row: row[0], reverse=True)
        results = [self._to_result(*row) for row in rows[: request.top_k]]
        return RetrieveResponse(
            request_id=f"REQ-{uuid.uuid4()}",
            query=request.query,
            role=request.role,
            results=results,
            evidence_status="sufficient" if len(results) >= min(3, request.top_k) else "insufficient",
            leakage_detected=any((request.role not in r.metadata["access_roles"].split(",") and "public" not in r.metadata["access_roles"].split(",")) for r in results),
        )

    def cache_lookup(self, request: CacheLookupRequest) -> CacheLookupResponse:
        key = cache_key(request.query, request.role, request.filters)
        raw = self.vector.cache.query(
            query_embeddings=[self.vector.embedder([key])[0]],
            n_results=3,
            include=["documents", "metadatas", "distances"],
        )
        now = datetime.now(timezone.utc)
        for cid, answer, meta, distance in zip(
            raw.get("ids", [[]])[0],
            raw.get("documents", [[]])[0],
            raw.get("metadatas", [[]])[0],
            raw.get("distances", [[]])[0],
        ):
            similarity = max(0.0, 1.0 - float(distance))
            if similarity < self.settings.cache_similarity_threshold:
                continue
            if meta.get("role") != request.role:
                continue
            expires_at = datetime.fromisoformat(meta["expires_at"])
            if expires_at < now:
                self.vector.cache.delete(ids=[cid])
                return CacheLookupResponse(request_id=f"REQ-{uuid.uuid4()}", cache_hit=False, reason="expired")
            if not self._source_versions_valid(json.loads(meta.get("source_versions", "{}"))):
                self.vector.cache.delete(ids=[cid])
                return CacheLookupResponse(request_id=f"REQ-{uuid.uuid4()}", cache_hit=False, reason="source_version_changed")
            return CacheLookupResponse(
                request_id=f"REQ-{uuid.uuid4()}",
                cache_hit=True,
                answer=answer,
                citations=[Citation.model_validate(c) for c in json.loads(meta.get("citations", "[]"))],
                validation_status=meta.get("validation_status"),
                expires_at=expires_at,
                similarity=similarity,
            )
        return CacheLookupResponse(request_id=f"REQ-{uuid.uuid4()}", cache_hit=False, reason="miss")

    def cache_write(self, request: CacheWriteRequest) -> CacheWriteResponse:
        key = cache_key(request.query, request.role, request.filters)
        ttl = request.ttl_seconds or self.settings.cache_ttl_seconds
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        cid = hashlib.sha256(key.encode("utf-8")).hexdigest()
        self.vector.cache.add(
            ids=[cid],
            documents=[request.answer],
            metadatas=[
                {
                    "cache_key": key,
                    "role": request.role,
                    "filters": json.dumps(request.filters, sort_keys=True),
                    "validation_status": request.validation_status,
                    "citations": json.dumps([c.model_dump() for c in request.citations]),
                    "source_versions": json.dumps(request.source_versions, sort_keys=True),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "expires_at": expires_at.isoformat(),
                }
            ],
            embeddings=[self.vector.embedder.embed(key)],
        )
        return CacheWriteResponse(request_id=f"REQ-{uuid.uuid4()}", cache_key=key, stored=True, expires_at=expires_at)

    def invalidate_cache(self, document_id: str | None = None) -> dict[str, Any]:
        if document_id:
            raw = self.vector.cache.get(include=["metadatas"])
            doomed = []
            for cid, meta in zip(raw.get("ids", []), raw.get("metadatas", [])):
                versions = json.loads(meta.get("source_versions", "{}"))
                if document_id in versions:
                    doomed.append(cid)
            if doomed:
                self.vector.cache.delete(ids=doomed)
            return {"invalidated": len(doomed), "document_id": document_id}
        count = self.vector.cache.count()
        self.vector.cache.delete()
        return {"invalidated": count}

    def _to_result(self, score: float, chunk_id: str, text: str, meta: dict[str, Any]) -> RetrievedChunk:
        citation = Citation(
            document_id=meta["document_id"],
            title=meta["title"],
            section=meta["section"],
            publisher=meta["publisher"],
            url=meta.get("url") or None,
            version_date=meta["version_date"],
            source_type=meta["source_type"],
            synthetic=meta.get("synthetic") == "true",
            chunk_id=chunk_id,
            score=round(score, 4),
        )
        return RetrievedChunk(
            chunk_id=chunk_id,
            document_id=meta["document_id"],
            title=meta["title"],
            section=meta["section"],
            text=text,
            score=round(score, 4),
            metadata=meta,
            citation=citation,
        )

    def _keyword_boost(self, query: str, meta: dict[str, Any], text: str) -> float:
        q_terms = set(normalize_query(query).split())
        hay = normalize_query(" ".join([meta.get("title", ""), meta.get("section", ""), text]))
        hits = sum(1 for term in q_terms if len(term) > 3 and term in hay)
        title_hits = sum(1 for term in q_terms if len(term) > 3 and term in normalize_query(meta.get("title", "")))
        return min(0.25, hits * 0.025 + title_hits * 0.05)

    def _source_versions_valid(self, versions: dict[str, str]) -> bool:
        manifest = {doc.document_id: doc for doc in load_manifest(self.settings.source_manifest_path)}
        for doc_id, version in versions.items():
            doc = manifest.get(doc_id)
            if not doc or doc.status != "active" or doc.version_date != version:
                return False
        return True


def cache_key(query: str, role: str, filters: dict[str, Any]) -> str:
    payload = {
        "query": normalize_query(query),
        "role": role,
        "filters": filters,
    }
    return json.dumps(payload, sort_keys=True)

