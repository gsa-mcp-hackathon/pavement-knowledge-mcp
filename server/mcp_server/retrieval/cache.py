"""Process-level RetrievalEngine cache."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Optional

from mcp_server.retrieval.engine import RetrievalEngine

_ENGINE_BUILD_LOCK = Lock()


@lru_cache(maxsize=8)
def _cached_engine(
    project_root: str,
    corpus_version: str,
    embedding_model: str,
) -> RetrievalEngine:
    return RetrievalEngine(
        project_root=Path(project_root),
        corpus_version=corpus_version,
        embedding_model=(embedding_model or None),
    )


def get_retrieval_engine(
    *,
    project_root: Path,
    corpus_version: str,
    embedding_model: Optional[str],
) -> RetrievalEngine:
    root = str(Path(project_root).resolve())
    version = str(corpus_version or "").strip()
    model = str(embedding_model or "").strip()
    if not version:
        raise ValueError("corpus_version is required")
    with _ENGINE_BUILD_LOCK:
        return _cached_engine(root, version, model)
