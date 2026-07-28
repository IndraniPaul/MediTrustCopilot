from __future__ import annotations

import hashlib
import re
from pathlib import Path


SECTION_RE = re.compile(r"^(#{1,4}\s+.+|[A-Z][A-Za-z0-9 ,/()&-]{4,80})$")


def read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("PDF ingestion requires pypdf") from exc
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError(f"Unsupported document type: {suffix}")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).lower().encode("utf-8")).hexdigest()


def detect_sections(text: str) -> list[tuple[str, str]]:
    current = "Overview"
    buf: list[str] = []
    sections: list[tuple[str, str]] = []
    for raw in normalize_text(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if buf:
                sections.append((current, "\n".join(buf).strip()))
                buf = []
            current = line.lstrip("#").strip()
        elif SECTION_RE.match(line) and len(line.split()) <= 10:
            if buf:
                sections.append((current, "\n".join(buf).strip()))
                buf = []
            current = line
        else:
            buf.append(line)
    if buf:
        sections.append((current, "\n".join(buf).strip()))
    return [(name, body) for name, body in sections if body]


def approx_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\w+|[^\w\s]", text)))


def chunk_section(section: str, text: str, target_tokens: int = 520, overlap_tokens: int = 70) -> list[tuple[str, str]]:
    words = re.findall(r"\S+", text)
    if not words:
        return []
    chunks: list[tuple[str, str]] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + target_tokens)
        body = " ".join(words[start:end])
        chunks.append((section, body))
        if end == len(words):
            break
        start = max(end - overlap_tokens, start + 1)
    return chunks


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.lower()).strip()
