"""Dense and hybrid retrieval over the indexed FHWA corpus."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from heapq import nlargest
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb

from mcp_server.retrieval.embeddings import Embedder

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class _BM25Index:
    """In-memory BM25 index built from chunk_text_readable stored in Chroma."""

    def __init__(self, ids: List[str], documents: List[str], metadatas: List[Dict[str, Any]]) -> None:
        self.ids = [str(x) for x in ids]
        self.documents = [str(x or "") for x in documents]
        self.metadatas = [m or {} for m in metadatas]

        self.N = len(self.documents)
        self.k1 = 1.5
        self.b = 0.75

        self.doc_len: List[int] = []
        self.avgdl = 0.0
        self.df: Dict[str, int] = {}
        self.postings: Dict[str, List[tuple[int, int]]] = {}

        self._build()

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return _TOKEN_RE.findall((text or "").lower())

    def _build(self) -> None:
        if self.N == 0:
            return

        total_len = 0
        for idx, doc in enumerate(self.documents):
            toks = self._tokenize(doc)
            total_len += len(toks)
            self.doc_len.append(len(toks))

            tf = Counter(toks)
            for term, freq in tf.items():
                self.df[term] = self.df.get(term, 0) + 1
                self.postings.setdefault(term, []).append((idx, int(freq)))

        self.avgdl = total_len / float(self.N)

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(1.0 + ((self.N - df + 0.5) / (df + 0.5)))

    def search(
        self,
        query: str,
        *,
        top_n: int,
        metadata_filter: Optional[callable] = None,
    ) -> List[Dict[str, Any]]:
        if self.N == 0 or top_n <= 0:
            return []

        q_terms = self._tokenize(query)
        if not q_terms:
            return []

        allowed: Optional[List[bool]] = None
        if metadata_filter is not None:
            allowed = [bool(metadata_filter(md)) for md in self.metadatas]

        scores: Dict[int, float] = {}
        for term in q_terms:
            plist = self.postings.get(term)
            if not plist:
                continue

            idf = self._idf(term)
            for idx, tf in plist:
                if allowed is not None and not allowed[idx]:
                    continue

                dl = self.doc_len[idx] or 1
                denom = tf + self.k1 * (1.0 - self.b + self.b * (dl / (self.avgdl or 1.0)))
                score = idf * (tf * (self.k1 + 1.0) / (denom or 1.0))
                scores[idx] = scores.get(idx, 0.0) + score

        if not scores:
            return []

        top_idx = nlargest(top_n, scores.items(), key=lambda x: x[1])
        hits: List[Dict[str, Any]] = []
        for rank, (idx, score) in enumerate(top_idx, start=1):
            md = self.metadatas[idx] or {}
            hits.append(
                {
                    "chunk_id": self.ids[idx],
                    "doc_id": md.get("doc_id"),
                    "document": self.documents[idx],
                    "metadata": md,
                    "distance": None,
                    "lexical_score": float(score),
                    "lexical_rank": rank,
                }
            )
        return hits


class RetrievalEngine:
    def __init__(
        self,
        project_root: Path,
        corpus_version: Optional[str] = None,
        collection: str = "fhwa_chunks",
        embedding_model: Optional[str] = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.registry_path = self.project_root / "data" / "index_registry.json"
        self.registry = self._read_registry()

        self.corpus_version = corpus_version or self.registry.get("active_index")
        if not self.corpus_version:
            raise ValueError("No corpus version provided and no active_index found in index_registry.json")

        indexes = self.registry.get("indexes", {})
        if self.corpus_version not in indexes:
            raise ValueError(f"Corpus version '{self.corpus_version}' not found in index_registry.json")

        idx_cfg = indexes[self.corpus_version]
        self.registry_embedding_model = str(idx_cfg.get("embedding_model") or "").strip()
        if not self.registry_embedding_model:
            raise ValueError(f"No embedding_model recorded for corpus '{self.corpus_version}'")

        if embedding_model and embedding_model != self.registry_embedding_model:
            raise ValueError(
                "Embedding model mismatch: "
                f"query='{embedding_model}' vs registry='{self.registry_embedding_model}' "
                f"for corpus='{self.corpus_version}'"
            )

        self.embedding_model = embedding_model or self.registry_embedding_model
        self.collection_name = collection or str(idx_cfg.get("collection") or "fhwa_chunks")

        persist_dir = idx_cfg.get("persist_dir")
        self.vector_dir = Path(persist_dir) if persist_dir else (self.project_root / "data" / "vector_db" / self.corpus_version)
        if not self.vector_dir.exists():
            raise FileNotFoundError(f"Vector DB path does not exist: {self.vector_dir}")

        self.embedder = Embedder(model_name=self.embedding_model)
        self.client = chromadb.PersistentClient(path=str(self.vector_dir))
        self.collection = self.client.get_collection(self.collection_name)
        self._bm25_index: Optional[_BM25Index] = None

    def _read_registry(self) -> Dict[str, Any]:
        if not self.registry_path.exists():
            raise FileNotFoundError(f"Index registry not found: {self.registry_path}")
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    @staticmethod
    def _eq_or_in(value: Any) -> Any:
        if isinstance(value, (list, tuple, set)):
            vals = [v for v in value if v is not None and str(v).strip()]
            if not vals:
                return None
            return {"$in": list(vals)}
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    @staticmethod
    def _merge_where(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if a and b:
            return {"$and": [a, b]}
        return a or b

    def build_where(
        self,
        *,
        year: Optional[int] = None,
        topic: Optional[Any] = None,
        doc_id: Optional[Any] = None,
        severity: Optional[Any] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        terms: List[Dict[str, Any]] = []

        if year is not None:
            terms.append({"year": int(year)})

        topic_clause = self._eq_or_in(topic)
        if topic_clause is not None:
            terms.append({"topic": topic_clause})

        doc_clause = self._eq_or_in(doc_id)
        if doc_clause is not None:
            terms.append({"doc_id": doc_clause})

        sev_clause = self._eq_or_in(severity)
        if sev_clause is not None:
            terms.append({"chunk_severity": sev_clause})

        if not terms:
            base_where = None
        elif len(terms) == 1:
            base_where = terms[0]
        else:
            base_where = {"$and": terms}
        return self._merge_where(base_where, where)

    @staticmethod
    def _value_matches(actual: Any, expected: Any) -> bool:
        if isinstance(expected, dict):
            if "$in" in expected:
                vals = expected.get("$in") or []
                return any(str(actual) == str(v) for v in vals)
            return False
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return actual == expected
        return str(actual) == str(expected)

    def _metadata_matches_where(self, md: Dict[str, Any], where: Optional[Dict[str, Any]]) -> bool:
        if not where:
            return True
        if "$and" in where:
            return all(self._metadata_matches_where(md, cond) for cond in where.get("$and", []))
        if "$or" in where:
            return any(self._metadata_matches_where(md, cond) for cond in where.get("$or", []))

        for key, expected in where.items():
            if key.startswith("$"):
                continue
            if key not in md:
                return False
            if not self._value_matches(md.get(key), expected):
                return False
        return True

    def _ensure_bm25_index(self) -> _BM25Index:
        if self._bm25_index is None:
            ids: List[str] = []
            docs: List[str] = []
            metas: List[Dict[str, Any]] = []

            page_size = 5000
            offset = 0
            while True:
                data = self.collection.get(
                    limit=page_size,
                    offset=offset,
                    include=["documents", "metadatas"],
                )
                batch_ids = data.get("ids", []) or []
                if not batch_ids:
                    break

                batch_docs = data.get("documents", []) or []
                batch_metas = data.get("metadatas", []) or []

                ids.extend(str(x) for x in batch_ids)
                docs.extend(str(x or "") for x in batch_docs)
                metas.extend((m or {}) for m in batch_metas)

                if len(batch_ids) < page_size:
                    break
                offset += page_size

            self._bm25_index = _BM25Index(ids=ids, documents=docs, metadatas=metas)
        return self._bm25_index

    def _retrieve_dense(self, query: str, *, top_k: int, final_where: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        qvec = self.embedder.embed_query(query)

        query_kwargs: Dict[str, Any] = {
            "query_embeddings": [qvec],
            "n_results": int(top_k),
            "include": ["metadatas", "documents", "distances"],
        }
        if final_where:
            query_kwargs["where"] = final_where

        res = self.collection.query(**query_kwargs)

        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]

        hits: List[Dict[str, Any]] = []
        for rank, (chunk_id, doc, md, dist) in enumerate(zip(ids, docs, metas, dists), start=1):
            md = md or {}
            hits.append(
                {
                    "chunk_id": str(chunk_id),
                    "doc_id": md.get("doc_id"),
                    "document": doc or "",
                    "metadata": md,
                    "distance": float(dist),
                    "dense_rank": rank,
                }
            )
        return hits

    def _retrieve_lexical(self, query: str, *, top_k: int, final_where: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        idx = self._ensure_bm25_index()
        return idx.search(
            query,
            top_n=int(top_k),
            metadata_filter=(lambda md: self._metadata_matches_where(md, final_where)),
        )

    @staticmethod
    def _fuse_rrf(
        dense_hits: List[Dict[str, Any]],
        lexical_hits: List[Dict[str, Any]],
        *,
        rrf_k: int,
        lexical_rrf_max_rank: int,
    ) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}

        for rank, h in enumerate(dense_hits, start=1):
            cid = str(h.get("chunk_id"))
            row = dict(h)
            row["dense_rank"] = rank
            row["rrf_score"] = 1.0 / (rrf_k + rank)
            merged[cid] = row

        for rank, h in enumerate(lexical_hits, start=1):
            if rank > int(lexical_rrf_max_rank):
                break
            cid = str(h.get("chunk_id"))
            if cid in merged:
                row = merged[cid]
                row["lexical_rank"] = rank
                row["lexical_score"] = h.get("lexical_score")
                row["rrf_score"] = float(row.get("rrf_score", 0.0)) + (1.0 / (rrf_k + rank))
            else:
                row = dict(h)
                row["lexical_rank"] = rank
                row["rrf_score"] = 1.0 / (rrf_k + rank)
                merged[cid] = row

        fused = list(merged.values())
        fused.sort(
            key=lambda x: (
                -float(x.get("rrf_score", 0.0)),
                int(x.get("dense_rank", 10**9)),
                int(x.get("lexical_rank", 10**9)),
            )
        )

        for i, row in enumerate(fused, start=1):
            row["hybrid_rank"] = i
        return fused

    @staticmethod
    def _apply_doc_diversity(hits: List[Dict[str, Any]], *, top_k: int, per_doc_cap: int) -> List[Dict[str, Any]]:
        if per_doc_cap <= 0:
            return hits[:top_k]

        out: List[Dict[str, Any]] = []
        per_doc: Dict[str, int] = {}
        for h in hits:
            doc = str(h.get("doc_id") or "")
            if doc:
                cnt = per_doc.get(doc, 0)
                if cnt >= per_doc_cap:
                    continue
                per_doc[doc] = cnt + 1
            out.append(h)
            if len(out) >= top_k:
                break
        return out

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 10,
        year: Optional[int] = None,
        topic: Optional[Any] = None,
        doc_id: Optional[Any] = None,
        severity: Optional[Any] = None,
        where: Optional[Dict[str, Any]] = None,
        retrieval_mode: str = "dense",
        dense_top_k: int = 0,
        lexical_top_k: int = 0,
        rrf_k: int = 60,
        lexical_rrf_max_rank: int = 20,
        per_doc_cap: int = 2,
    ) -> List[Dict[str, Any]]:
        final_where = self.build_where(
            year=year,
            topic=topic,
            doc_id=doc_id,
            severity=severity,
            where=where,
        )

        mode = (retrieval_mode or "dense").strip().lower()
        dense_k = int(dense_top_k) if int(dense_top_k or 0) > 0 else max(50, int(top_k))
        lex_k = int(lexical_top_k) if int(lexical_top_k or 0) > 0 else max(50, int(top_k))

        if mode == "hybrid":
            dense_hits = self._retrieve_dense(query, top_k=dense_k, final_where=final_where)
            lexical_hits = self._retrieve_lexical(query, top_k=lex_k, final_where=final_where)
            fused = self._fuse_rrf(
                dense_hits,
                lexical_hits,
                rrf_k=int(rrf_k),
                lexical_rrf_max_rank=int(lexical_rrf_max_rank),
            )
            hits = self._apply_doc_diversity(fused, top_k=top_k, per_doc_cap=int(per_doc_cap))
        else:
            hits = self._retrieve_dense(query, top_k=int(top_k), final_where=final_where)

        return hits[: int(top_k)]
