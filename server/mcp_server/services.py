"""Local catalog and retrieval services for the three MCP tools."""

from dataclasses import dataclass
import json
import os
from pathlib import Path

from mcp_server.errors import ToolFailure


SOURCE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class RetrievalSettings:
    """Fixed retrieval defaults for the indexed corpus."""
    corpus_version: str = "v1"
    embedding_model: str | None = None  # Use the isolated index registry's model.
    dense_top_k: int = 50
    lexical_top_k: int = 50
    rrf_k: int = 60
    lexical_rrf_max_rank: int = 20


class CorpusServices:
    """One binding per standalone process; adapter calls are serialized.

    Catalog-only calls may read source CSVs. Retrieval requires an operator-
    prepared corpus root outside the source directory.
    """

    def __init__(self):
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        if os.environ.get("PYTHON_DOTENV_DISABLED") != "1":
            raise ToolFailure("SERVICE_UNAVAILABLE")
        configured = os.environ.get("PAVEMENT_MCP_CORPUS_ROOT")
        root = Path(configured) if configured else SOURCE_ROOT
        if configured and not root.is_absolute():
            raise ToolFailure("SERVICE_UNAVAILABLE")
        root = root.resolve()
        if configured and (root.is_relative_to(SOURCE_ROOT) or SOURCE_ROOT.is_relative_to(root)):
            raise ToolFailure("SERVICE_UNAVAILABLE")

        from mcp_server.catalog import PublicationCatalog

        self.root, self.isolated = root, bool(configured)
        self.config = RetrievalSettings()
        self.publications = PublicationCatalog(root, self.config.corpus_version)
        self._loaded = True

    def require_catalog(self):
        self._load()
        # Preserve optional metadata fallback; only chunks are required by catalog.
        if not self.publications.CHUNKS_PATH.is_file():
            raise ToolFailure("CORPUS_UNAVAILABLE")
        if self.isolated:
            for path in (self.publications.CHUNKS_PATH, self.publications.DOC_METADATA_PATH,
                         self.publications.CHUNKS_PARQUET_PATH):
                if not path.resolve().is_relative_to(self.root):
                    raise ToolFailure("CORPUS_UNAVAILABLE")

    def require_retrieval(self):
        self._load()
        if not self.isolated:
            raise ToolFailure("SERVICE_UNAVAILABLE")
        registry = self.root / "data" / "index_registry.json"
        if not registry.resolve().is_relative_to(self.root):
            raise ToolFailure("CORPUS_UNAVAILABLE")
        try:
            index = json.loads(registry.read_text(encoding="utf-8"))["indexes"][self.config.corpus_version]
            vector = Path(index["persist_dir"]) if index.get("persist_dir") else (
                self.root / "data" / "vector_db" / self.config.corpus_version
            )
            if (not vector.is_absolute() or not vector.resolve().is_relative_to(self.root)
                    or not (vector / "chroma.sqlite3").is_file()
                    or not (vector / "chroma.sqlite3").resolve().is_relative_to(self.root)):
                raise ToolFailure("CORPUS_UNAVAILABLE")
        except (OSError, ValueError, KeyError, TypeError):
            raise ToolFailure("CORPUS_UNAVAILABLE") from None

    def warmup(self):
        """Strict readiness check using only the catalog and local retrieval engine."""
        self.require_catalog()
        self.require_retrieval()
        from mcp_server.retrieval.cache import get_retrieval_engine

        engine = get_retrieval_engine(project_root=self.root,
            corpus_version=self.config.corpus_version, embedding_model=self.config.embedding_model)
        hits = engine.retrieve("pavement structural evaluation", retrieval_mode="hybrid",
            top_k=1, dense_top_k=self.config.dense_top_k,
            lexical_top_k=self.config.lexical_top_k, rrf_k=self.config.rrf_k,
            lexical_rrf_max_rank=self.config.lexical_rrf_max_rank,
            per_doc_cap=2)
        if not hits or not self.publications.all_publications() or engine._ensure_bm25_index().N <= 0:
            raise ToolFailure("CORPUS_UNAVAILABLE")

    def search(self, **kwargs):
        return self.publications.list_publications(**kwargs)

    def publication(self, doc_id):
        return self.publications.get_publication(doc_id)

    def evidence_candidates(self, query, *, doc_id, mode, limit):
        """Retrieve candidates before applying evidence selection and diversity limits.

        The scoped structural scan is bounded to 5000 chunks. One extra row
        detects a larger report without claiming complete candidate coverage.
        """
        self.require_retrieval()
        from mcp_server.retrieval.cache import get_retrieval_engine

        engine = get_retrieval_engine(project_root=self.root,
            corpus_version=self.config.corpus_version, embedding_model=self.config.embedding_model)
        truncated = False
        overview_rankings = {}
        if mode == "report_overview":
            if not doc_id:
                raise ToolFailure("INVALID_ARGUMENT")
            where = engine.build_where(doc_id=doc_id)
            hits = []
            while len(hits) < 5001:
                size = min(500, 5001 - len(hits))
                page = engine.collection.get(where=where, limit=size, offset=len(hits),
                                             include=["documents", "metadatas"])
                ids, documents, metadata = (page.get(k) for k in ("ids", "documents", "metadatas"))
                if (not all(isinstance(items, list) for items in (ids, documents, metadata))
                        or len(ids) != len(documents) or len(ids) != len(metadata) or len(ids) > size):
                    raise ToolFailure("INVALID_SERVICE_RESPONSE")
                hits.extend(dict(chunk_id=cid, document=text, metadata=md)
                            for cid, text, md in zip(ids, documents, metadata))
                if len(ids) < size:
                    break
            truncated = len(hits) > 5000
            hits = hits[:5000]
            if hits:
                from mcp_server.evidence import OVERVIEW_QUERIES, section_role
                from mcp_server.retrieval.scope import same_report
                observed = {section_role(h) for h in hits}
                # Flat/missing headings cannot provide section diversity. Search
                # missing roles locally; only rank IDs present in the scoped scan.
                for role, question in OVERVIEW_QUERIES.items():
                    if role in observed:
                        continue
                    ranked = engine.retrieve(question, doc_id=doc_id, top_k=8, retrieval_mode="hybrid",
                        dense_top_k=self.config.dense_top_k, lexical_top_k=self.config.lexical_top_k,
                        rrf_k=self.config.rrf_k, lexical_rrf_max_rank=self.config.lexical_rrf_max_rank,
                        per_doc_cap=0)
                    if not isinstance(ranked, list) or any(not isinstance(h, dict)
                            or not isinstance(h.get("metadata"), dict)
                            or not isinstance(h.get("chunk_id"), str)
                            or not same_report(h["metadata"].get("doc_id"), doc_id) for h in ranked):
                        raise ToolFailure("INVALID_SERVICE_RESPONSE")
                    overview_rankings[role] = [h["chunk_id"] for h in ranked]
        else:
            pool = max(32, limit * 4)
            hits = engine.retrieve(query, doc_id=doc_id, top_k=pool, retrieval_mode="hybrid",
                dense_top_k=max(pool, self.config.dense_top_k),
                lexical_top_k=max(pool, self.config.lexical_top_k), rrf_k=self.config.rrf_k,
                lexical_rrf_max_rank=self.config.lexical_rrf_max_rank,
                per_doc_cap=0)
        return dict(hits=hits, scan_truncated=truncated, corpus_version=self.config.corpus_version,
                    overview_rankings=overview_rankings)
