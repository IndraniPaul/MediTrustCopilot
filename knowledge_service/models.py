from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


AccessRole = Literal["doctor", "nurse", "pharmacist", "compliance_officer", "administrator", "public"]
SourceStatus = Literal["active", "superseded", "expired", "draft"]
SourceType = Literal["public_guideline", "synthetic_sop"]


class SourceDocument(BaseModel):
    document_id: str
    title: str
    publisher: str
    url: str | None = None
    source_type: SourceType
    license_terms: str
    version_date: str
    status: SourceStatus = "active"
    access_roles: list[AccessRole]
    file_path: str
    synthetic: bool = False
    tags: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    document_id: str
    title: str
    section: str
    publisher: str
    url: str | None = None
    version_date: str
    source_type: SourceType
    synthetic: bool
    chunk_id: str
    score: float


class IngestRequest(BaseModel):
    reset: bool = False
    manifest_path: str | None = None


class IngestResponse(BaseModel):
    schema_version: str = "1.0"
    documents_loaded: int
    chunks_loaded: int
    duplicates_skipped: int
    collection: str


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    role: AccessRole = "public"
    top_k: int = Field(default=5, ge=1, le=20)
    status: SourceStatus = "active"
    source_type: SourceType | None = None
    document_ids: list[str] | None = None
    tags: list[str] | None = None


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    section: str
    text: str
    score: float
    metadata: dict[str, Any]
    citation: Citation


class RetrieveResponse(BaseModel):
    schema_version: str = "1.0"
    request_id: str
    query: str
    role: AccessRole
    results: list[RetrievedChunk]
    evidence_status: Literal["sufficient", "insufficient"]
    leakage_detected: bool = False


class CacheLookupRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    role: AccessRole
    filters: dict[str, Any] = Field(default_factory=dict)


class CacheWriteRequest(CacheLookupRequest):
    answer: str = Field(min_length=1)
    citations: list[Citation]
    validation_status: Literal["pass", "pass_with_warning"] = "pass"
    ttl_seconds: int | None = None
    source_versions: dict[str, str] = Field(default_factory=dict)


class CacheLookupResponse(BaseModel):
    schema_version: str = "1.0"
    request_id: str
    cache_hit: bool
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    validation_status: str | None = None
    reason: str | None = None
    expires_at: datetime | None = None
    similarity: float | None = None


class CacheWriteResponse(BaseModel):
    schema_version: str = "1.0"
    request_id: str
    cache_key: str
    stored: bool
    expires_at: datetime


class HealthResponse(BaseModel):
    schema_version: str = "1.0"
    service: str = "knowledge_service"
    status: Literal["ok", "degraded"]
    chroma_available: bool
    knowledge_collection: str
    cache_collection: str
    persist_directory: str
