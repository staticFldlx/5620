"""Shared retrieval interface (spec section 7).

Only the `none` backend is implemented for now (RAG is postponed). Callers must check
`is_enabled()` first and decide themselves how to answer without citations.
`keyword` (SQLite FTS5) and `vector` can be added behind the same three functions later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    material_id: str
    title: str
    source: str
    source_type: str
    text: str
    score: float  # raw BM25 / cosine score, not a probability


@dataclass
class IngestReport:
    ingested: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # unchanged content_hash
    failed: dict[str, str] = field(default_factory=dict)


class RetrievalDisabled(RuntimeError):
    pass


FILTER_KEYS = frozenset({"stage_topics", "difficulty_level", "source_type", "material_ids"})


def backend() -> str:
    return settings.RETRIEVAL_BACKEND


def is_enabled() -> bool:
    return backend() != "none"


def search(query: str, *, filters: dict | None = None, k: int = 5) -> list[Hit]:
    unknown = set(filters or {}) - FILTER_KEYS
    if unknown:
        raise ValueError(f"unsupported retrieval filters: {sorted(unknown)}")
    if not is_enabled():
        raise RetrievalDisabled("RETRIEVAL_BACKEND=none; check is_enabled() before searching")
    raise NotImplementedError(f"retrieval backend {backend()!r} is not implemented yet")


def ingest(material_ids: list[str]) -> IngestReport:
    """Idempotent by content_hash. Only run on seed data or after a Founder-approved UpdateProposal."""
    if not is_enabled():
        return IngestReport(skipped=list(material_ids))
    raise NotImplementedError(f"retrieval backend {backend()!r} is not implemented yet")
