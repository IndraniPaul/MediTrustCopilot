from __future__ import annotations

import json
from pathlib import Path

from .models import SourceDocument


def load_manifest(path: Path) -> list[SourceDocument]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    docs = payload["documents"] if isinstance(payload, dict) else payload
    return [SourceDocument.model_validate(item) for item in docs]


def role_allowed(doc: SourceDocument, role: str) -> bool:
    return role in doc.access_roles or "public" in doc.access_roles

