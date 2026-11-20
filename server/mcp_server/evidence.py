"""MCP-only bounded evidence selection and provenance; no model generation."""

from collections import Counter
import re

from mcp_server.errors import ToolFailure


MAX_TEXT_CHARS = 16000
ROLES = ("purpose", "methods", "findings", "conclusions", "limitations", "recommendations")
# Generic research-document questions, not domain keywords or generated queries.
OVERVIEW_QUERIES = {
    "purpose": "What are the purpose, objectives and scope of this study?",
    "methods": "What methods, experiments, data and analysis procedures were used?",
    "findings": "What results and main findings did this study report?",
    "conclusions": "What are the conclusions of this report?",
    "limitations": "What limitations, assumptions and uncertainties affect these results?",
    "recommendations": "What recommendations and future research does this report propose?",
}
ROLE_PATTERNS = (
    ("limitations", r"\blimitations?\b|\bcaveats?\b|\buncertaint"),
    ("recommendations", r"recommend|future (?:work|research)"),
    ("conclusions", r"conclusion|executive summary"),
    ("findings", r"result|finding|discussion|evaluation"),
    ("methods", r"method|experiment|field trial|data collection|instrumentation|analysis"),
    ("purpose", r"abstract|introduction|purpose|overview|objective|background"),
)


def section_role(hit):
    heading = str(hit["metadata"].get("section_header") or "").lower()
    return next((role for role, pattern in ROLE_PATTERNS if re.search(pattern, heading)), "other")


def _text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolFailure("INVALID_SERVICE_RESPONSE")
    value = value.strip()
    return None if value.lower() in {"", "none", "null", "nan"} else value


def _page(value):
    # Unknown or malformed pages stay unknown; never invent a location.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value)
        return number if number > 0 else None
    return None


def _eligible(hits, doc_id):
    from mcp_server.retrieval.scope import same_report

    if not isinstance(hits, list):
        raise ToolFailure("INVALID_SERVICE_RESPONSE")
    unique, seen_ids, seen_text, duplicates = [], set(), set(), 0
    for hit in hits:
        if not isinstance(hit, dict) or not isinstance(hit.get("metadata"), dict):
            raise ToolFailure("INVALID_SERVICE_RESPONSE")
        cid, did = _text(hit.get("chunk_id")), _text(hit["metadata"].get("doc_id"))
        if not cid or not did or not isinstance(hit.get("document"), str):
            raise ToolFailure("INVALID_SERVICE_RESPONSE")
        if doc_id is not None and not same_report(did, doc_id):
            raise ToolFailure("INVALID_SERVICE_RESPONSE")
        text = hit["document"].strip()
        if not text or not any(character.isalnum() for character in text):
            continue
        key = (did, re.sub(r"\s+", " ", text).casefold())
        if (did, cid) in seen_ids or key in seen_text:
            duplicates += 1
            continue
        seen_ids.add((did, cid))
        seen_text.add(key)
        unique.append(hit)
    return unique, duplicates


def _overview_order(hits, rankings):
    # Work from structural metadata, retaining unlabelled/missing-page passages.
    # Bibliography/contents are lowest priority, not silently deleted evidence.
    ordered = sorted(hits, key=lambda h: (
        bool(re.search(r"reference|bibliograph|acknowledg|table of contents",
                       str(h["metadata"].get("section_header") or ""), re.I)),
        _page(h["metadata"].get("page_start")) or 10**9, h["chunk_id"]))
    groups = {role: [] for role in (*ROLES, "other")}
    for hit in ordered:
        groups[section_role(hit)].append(hit)
    by_id = {h["chunk_id"]: h for h in hits}
    selected = set()
    # Prefer explicit headings; for missing roles use scoped local query rankings.
    # A search intent does not establish that its result actually covers the role.
    for role in ROLES:
        candidates = groups[role] or [by_id[cid] for cid in rankings.get(role, []) if cid in by_id]
        candidate = next((h for h in candidates if h["chunk_id"] not in selected), None)
        if candidate is not None:
            selected.add(candidate["chunk_id"])
            yield candidate
    while any(groups.values()):
        for role in (*ROLES, "other"):
            if groups[role]:
                candidate = groups[role].pop(0)
                if candidate["chunk_id"] not in selected:
                    selected.add(candidate["chunk_id"])
                    yield candidate


def build_evidence(request, hits, *, corpus_version, publication, scan_truncated=False, overview_rankings=None):
    """Return excerpts plus observed coverage, never an answer/confidence label."""
    unique, duplicates = _eligible(hits, request.doc_id)
    ordered = list(_overview_order(unique, overview_rankings or {})) if request.mode == "report_overview" else unique
    passages, chosen, counts, records = [], [], Counter(), {}
    used = 0
    for hit in ordered:
        md = hit["metadata"]
        did = _text(md["doc_id"])
        if request.doc_id is None and counts[did] >= 3:
            continue
        text = hit["document"].strip()
        if len(passages) >= request.limit or used >= MAX_TEXT_CHARS:
            break
        available = MAX_TEXT_CHARS - used
        # Preserve complete passages where possible. Clip only an oversized first
        # passage; do not waste the rest of the budget on an incomplete fragment.
        if len(text) > available and passages:
            continue
        if did not in records:
            records[did] = publication(did)
        record = records[did] or {}
        if not isinstance(record, dict) or (record and record.get("doc_id") != did):
            raise ToolFailure("INVALID_SERVICE_RESPONSE")
        page_start, page_end = _page(md.get("page_start")), _page(md.get("page_end"))
        if page_start is not None and page_end is not None and page_end < page_start:
            page_start, page_end = None, None
        passages.append(dict(rank=len(passages) + 1, chunk_id=hit["chunk_id"], doc_id=did,
            doc_title=_text(record.get("title")) or _text(md.get("manifest_title"))
                      or _text(md.get("doc_title")) or "",
            report_no=_text(record.get("report_no")) or _text(md.get("report_no")),
            pdf_url=_text(record.get("pdf_url")) or _text(md.get("pdf_url")),
            section_header=_text(md.get("section_header")), page_start=page_start, page_end=page_end,
            text=text[:available], text_truncated=len(text) > available))
        chosen.append(hit)
        counts[did] += 1
        used += len(passages[-1]["text"])
    roles = list(dict.fromkeys(section_role(h) for h in chosen))
    warnings = ["Selected passages only; not a complete report or exhaustive corpus search. "
                "A retrieved match does not by itself establish support for a claim."]
    if not passages:
        warnings.append("No passages returned; this does not prove absence of relevant evidence.")
    if any(not p["doc_title"] or not p["pdf_url"] or p["page_start"] is None
           or p["page_end"] is None or not p["section_header"] for p in passages):
        warnings.append("Some source metadata is unavailable. Page ranges locate chunks, not exact quotations.")
    if request.mode == "report_overview":
        warnings.append("Section roles are inferred from headings; unobserved roles may still occur in the report. "
                        "Use scoped follow-up queries to investigate gaps.")
    if scan_truncated:
        warnings.append("Report candidate scan reached its bound; later report passages were not inspected.")
    return dict(mode=request.mode, scope="publication" if request.doc_id else "corpus",
        query=request.query, doc_id=request.doc_id, corpus_version=corpus_version, passages=passages,
        candidate_count=len(hits), duplicates_removed=duplicates, candidate_scan_truncated=scan_truncated,
        truncated=scan_truncated or len(passages) < len(unique) or any(p["text_truncated"] for p in passages),
        coverage=dict(section_roles_present=roles,
            section_roles_not_observed=[r for r in ROLES if r not in roles],
            basis="Heuristic labels from retrieved section headings; not verification of content coverage.",
            complete_report=False), warnings=warnings)
