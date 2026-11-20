"""Path-bound publication catalog with metadata and content-mention search."""
from __future__ import annotations

import csv
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "into", "is", "it",
    "of", "on", "or", "that", "the", "this", "to", "using", "with",
}

_INTERNAL_FIELDS = {"search_blob", "search_tokens"}


def _clean_text(value: Any) -> str:
    text = str(value or "").replace("\x00", "").strip()
    if text.lower() in {"nan", "none", "null", "n/a"}:
        return ""
    return text


def _clean_report_no(value: Any) -> str:
    text = _clean_text(value)
    lowered = text.lower()
    if not text:
        return ""
    bad_prefixes = (
        "1. report",
        "2. government",
        "10. work unit",
        "shrp/",
    )
    if any(lowered.startswith(prefix) for prefix in bad_prefixes):
        return ""
    if text in {"!", "I", "1 2.", "2.0"}:
        return ""
    if len(text) > 80:
        return ""
    return text


def _extract_year(value: Any) -> Optional[int]:
    text = _clean_text(value)
    match = re.search(r"(19|20)\d{2}", text)
    if not match:
        return None
    year = int(match.group(0))
    return year if 1900 <= year <= 2100 else None


def _search_tokenize(value: Any) -> set[str]:
    text = _clean_text(value).lower()
    return {tok for tok in re.split(r"[^a-z0-9]+", text) if len(tok) >= 2 and tok not in _STOP_WORDS}


def _normalize_search_text(value: Any) -> str:
    return " ".join(re.split(r"[^a-z0-9]+", _clean_text(value).lower())).strip()


def _public_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in item.items() if key not in _INTERNAL_FIELDS}


def _best_title(chunk_row: Dict[str, Any], meta_row: Optional[Dict[str, Any]]) -> str:
    meta_row = meta_row or {}
    for value in (
        chunk_row.get("manifest_title"),
        meta_row.get("extracted_title"),
        meta_row.get("pdf_meta_title"),
        chunk_row.get("doc_title"),
    ):
        text = _clean_text(value)
        if text and text.upper() != text:
            return text
        if text and len(text.split()) > 3:
            return text.title()
    return _clean_text(chunk_row.get("doc_id"))


def _publication_from_rows(chunk_row: Dict[str, Any], meta_row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    meta_row = meta_row or {}
    title = _best_title(chunk_row, meta_row)
    report_no = _clean_report_no(meta_row.get("extracted_report_no")) or _clean_report_no(chunk_row.get("report_no"))
    year = _extract_year(meta_row.get("extracted_pub_date")) or _extract_year(meta_row.get("pdf_meta_creationDate"))
    topic = _clean_text(chunk_row.get("topic"))
    abstract = _clean_text(meta_row.get("extracted_abstract"))
    search_text = " ".join(
        part for part in [title, report_no, topic, abstract, chunk_row.get("doc_id"), meta_row.get("pdf_meta_keywords")] if _clean_text(part)
    ).lower()
    publication = {
        "doc_id": _clean_text(chunk_row.get("doc_id")),
        "title": title,
        "report_no": report_no,
        "year": year,
        "topic": topic,
        "primary_topic": topic,
        "pdf_url": _clean_text(chunk_row.get("pdf_url")),
        "trust_badge": _clean_text(meta_row.get("trust_badge")) or _clean_text(chunk_row.get("trust_badge")),
        "abstract": abstract,
        "page_count": int(meta_row.get("page_count") or 0) if _clean_text(meta_row.get("page_count")) else None,
        "search_blob": search_text,
        "search_tokens": frozenset(_search_tokenize(search_text)),
    }
    return publication


class PublicationCatalog:
    """Process-local read-only view of one release, with bounded lookup caches."""

    def __init__(self, root: Path, corpus_version: str):
        release = root / "data/corpus/releases" / corpus_version
        self.DOC_METADATA_PATH = release / "corpus_v1_doc_metadata.csv"
        self.CHUNKS_PATH = release / "corpus_v1_chunks.csv"
        self.CHUNKS_PARQUET_PATH = release / "corpus_v1_chunks.parquet"

    def _doc_metadata_rows(self) -> Dict[str, Dict[str, Any]]:
        if not self.DOC_METADATA_PATH.exists():
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        with self.DOC_METADATA_PATH.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                doc_id = _clean_text(row.get("doc_id"))
                if not doc_id:
                    continue
                out[doc_id] = dict(row)
        return out

    @lru_cache(maxsize=1)
    def all_publications(self) -> List[Dict[str, Any]]:
        meta_by_doc = self._doc_metadata_rows()
        publications: List[Dict[str, Any]] = []
        seen: set[str] = set()
        if not self.CHUNKS_PATH.exists():
            return publications
        with self.CHUNKS_PATH.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                doc_id = _clean_text(row.get("doc_id"))
                if not doc_id or doc_id in seen:
                    continue
                seen.add(doc_id)
                publications.append(_publication_from_rows(row, meta_by_doc.get(doc_id)))
        publications.sort(key=lambda item: (-(item.get("year") or 0), str(item.get("report_no") or ""), str(item.get("title") or "")))
        return publications

    @lru_cache(maxsize=128)
    def publication_content_matches(self, search: str) -> Dict[str, int]:
        """Return per-document coherent phrase-match counts from the columnar corpus."""
        normalized = _normalize_search_text(search)
        if not normalized:
            return {}
        pattern = r"(?:^|[^a-z0-9])" + r"[^a-z0-9]+".join(re.escape(term) for term in normalized.split()) + r"(?:$|[^a-z0-9])"
        if self.CHUNKS_PARQUET_PATH.exists():
            try:
                import pyarrow.compute as pc
                import pyarrow.parquet as pq

                columns = ["doc_id", "section_header", "section_header_detail", "chunk_text_readable"]
                table = pq.read_table(self.CHUNKS_PARQUET_PATH, columns=columns)
                match_mask = None
                for column_name in columns[1:]:
                    values = pc.fill_null(table[column_name], "")
                    column_mask = pc.match_substring_regex(values, pattern, ignore_case=True)
                    match_mask = column_mask if match_mask is None else pc.or_(match_mask, column_mask)
                if match_mask is None:
                    return {}
                return dict(Counter(str(doc_id) for doc_id in table.filter(match_mask)["doc_id"].to_pylist() if doc_id))
            except (ImportError, OSError, ValueError):
                pass

        matches: Counter[str] = Counter()
        if not self.CHUNKS_PATH.exists():
            return {}
        compiled = re.compile(pattern, flags=re.IGNORECASE)
        with self.CHUNKS_PATH.open(newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                doc_id = _clean_text(row.get("doc_id"))
                if not doc_id:
                    continue
                content_text = " ".join(
                    part
                    for part in (
                        _clean_text(row.get("section_header")),
                        _clean_text(row.get("section_header_detail")),
                        _clean_text(row.get("chunk_text_readable")) or _clean_text(row.get("chunk_text")),
                    )
                    if part
                )
                if compiled.search(content_text):
                    matches[doc_id] += 1
        return dict(matches)

    def publication_topics(self) -> List[str]:
        topics = {str(item.get("topic") or "").strip() for item in self.all_publications() if str(item.get("topic") or "").strip()}
        return sorted(topics)

    def list_publications(
        self,
        *,
        search: Optional[str] = None,
        topic: Optional[str] = None,
        year: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        rows = self.all_publications()
        q = _clean_text(search).lower()
        q_tokens = _search_tokenize(q)
        normalized_query = _normalize_search_text(q)
        topic_text = _clean_text(topic).lower()
        eligible: List[Dict[str, Any]] = []
        for item in rows:
            if topic_text and str(item.get("topic") or "").lower() != topic_text:
                continue
            if year and int(item.get("year") or 0) != int(year):
                continue
            eligible.append(item)

        filtered: List[tuple[int, int, Dict[str, Any]]] = []
        for item in eligible:
            search_blob = str(item.get("search_blob") or "")
            metadata_tokens = set(item.get("search_tokens") or ())
            if q and not (q in search_blob or (q_tokens and q_tokens.issubset(metadata_tokens))):
                continue
            public = _public_item(item)
            public["match_status"] = "metadata_match" if q else "catalog_record"
            public["match_reason"] = (
                "Requested terms matched the publication title or metadata" if q else "Catalog record"
            )
            filtered.append((2 if q else 0, 0, public))

        if q and not filtered and q_tokens and normalized_query:
            content_matches = self.publication_content_matches(normalized_query)
            for item in eligible:
                match_score = int(content_matches.get(str(item.get("doc_id") or "")) or 0)
                if not match_score:
                    continue
                public = _public_item(item)
                public["match_status"] = "content_mention"
                public["match_reason"] = "Requested terms were found in the publication text, not its title or metadata"
                filtered.append((1, match_score, public))
        if q:
            filtered.sort(
                key=lambda pair: (
                    -pair[0],
                    -pair[1],
                    -int(pair[2].get("year") or 0),
                    str(pair[2].get("report_no") or ""),
                    str(pair[2].get("title") or ""),
                )
            )
        total = len(filtered)
        start = max(0, int(offset))
        end = start + max(1, min(int(limit), 1000))
        page = filtered[start:end]
        return {
            "items": [item for _rank, _score, item in page],
            "count": total,
            "topics": self.publication_topics(),
            "years": sorted({int(item.get("year")) for item in rows if item.get("year")}, reverse=True),
        }

    def get_publication(self, doc_id: str) -> Optional[Dict[str, Any]]:
        target = _clean_text(doc_id)
        if not target:
            return None
        for item in self.all_publications():
            if item.get("doc_id") == target:
                return _public_item(item)
        return None
