"""Validated catalog and passage tools for client-written pavement research."""

from contextlib import redirect_stdout
import json
import logging
import sys
from threading import Event, Lock, Thread
from time import perf_counter

from mcp_types import CallToolResult, TextContent, Tool, ToolAnnotations
from pydantic import ValidationError

from mcp_server import models as m
from mcp_server.errors import ToolFailure, error_payload
from mcp_server.services import CorpusServices


# The schema and descriptions are the client interface, not a question router.
DESCRIPTIONS = {
    "search_publications": (
        'Find pavement research reports, reading lists, report numbers and source links in the '
        'FHWA publication corpus. Search by topic, title or report number; omit search to browse. '
        'Returns catalog doc_ids, metadata, match explanations and pagination. A content mention '
        'does not establish topic focus. No matches do not establish absence of relevant evidence. '
        'For engineering explanations or comparisons, retrieve_evidence searches passages directly.'
    ),
    "get_publication": (
        'Get the title, report number, available catalog metadata and source link for one pavement '
        'publication. Requires its exact doc_id from search_publications. Returns metadata, not '
        'the full report or findings. For report content use retrieve_evidence with that doc_id.'
    ),
    "retrieve_evidence": (
        'Retrieve source passages to explain or compare pavement engineering topics, or summarize '
        'a report using the client model. In query mode provide a question; omit doc_id to search '
        'across reports, or supply it to stay within one report. In report_overview mode supply '
        'doc_id and omit query for varied report sections. Resolve unknown IDs with '
        'search_publications. Returns bounded excerpts, source/chunk IDs, available links/pages '
        'and coverage limits. Assess support before synthesizing; matches and heading labels do '
        'not prove relevance or complete coverage. Use scoped follow-up queries for material gaps. '
        'No server-generated answer or generation API key is needed.'
    ),
}
INPUTS = {
    "search_publications": m.SearchInput,
    "get_publication": m.PublicationInput,
    "retrieve_evidence": m.RetrieveEvidenceInput,
}
OUTPUTS = {
    "search_publications": m.SearchResult,
    "get_publication": m.Publication,
    "retrieve_evidence": m.RetrievedEvidence,
}


def result(data: dict, *, failed=False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False, allow_nan=False))],
        structured_content=data, is_error=failed,
    )


class PavementTools:
    def __init__(self, services=None):
        self.services = services if services is not None else CorpusServices()
        # Corpus services use process caches; keep configuration and calls serial.
        self._lock = Lock()
        self._warmup_done = Event()
        self._warmup_done.set()
        self._warmup_started = False
        self._warmup_failed = False

    def start_warmup(self):
        """Start once before accepting calls; discovery does not wait for this."""
        with self._lock:
            if self._warmup_started:
                return
            self._warmup_started = True
            self._warmup_done.clear()
        def worker():
            start = perf_counter()
            try:
                with self._lock, redirect_stdout(sys.stderr):
                    self.services.warmup()
            except Exception as exc:
                self._warmup_failed = True
                logging.getLogger("pavement_mcp.warmup").warning(
                    "MCP local warm-up failed exception_type=%s; restart after checking setup",
                    type(exc).__name__)
            else:
                print("Pavement Knowledge MCP local retrieval ready "
                      f"(warm-up {perf_counter()-start:.1f}s).",
                      file=sys.stderr, flush=True)
            finally:
                self._warmup_done.set()
        print("Pavement Knowledge MCP local warm-up started.", file=sys.stderr, flush=True)
        try:
            Thread(target=worker, name="pavement-mcp-warmup", daemon=True).start()
        except Exception:
            self._warmup_failed = True
            self._warmup_done.set()
            raise

    def definitions(self):
        definitions = []
        for name, inputs in INPUTS.items():
            output = OUTPUTS[name].model_json_schema()
            definitions.append(Tool(
                name=name, description=DESCRIPTIONS[name], input_schema=inputs.model_json_schema(),
                output_schema=output,
                annotations=ToolAnnotations(
                    read_only_hint=True, destructive_hint=False,
                    idempotent_hint=True, open_world_hint=False,
                ),
            ))
        return definitions

    def call(self, name, arguments):
        if name not in INPUTS:
            return result(error_payload("INVALID_ARGUMENT"), failed=True)
        try:
            request = INPUTS[name].model_validate(arguments)
        except ValidationError:
            return result(error_payload("INVALID_ARGUMENT"), failed=True)
        self._warmup_done.wait()
        if self._warmup_failed and name not in {"search_publications", "get_publication"}:
            return result(error_payload("SERVICE_UNAVAILABLE"), failed=True)
        try:
            # Third-party diagnostic prints must never corrupt the STDIO stream.
            with self._lock, redirect_stdout(sys.stderr):
                data = getattr(self, name)(request)
                OUTPUTS[name].model_validate(data)
                if name == "search_publications" and (len(data["items"]) > request.limit
                                                      or data["count"] < len(data["items"])):
                    raise ToolFailure("INVALID_SERVICE_RESPONSE")
                return result(data)
        except ToolFailure as exc:
            code = exc.code
        except ImportError:
            code = "SERVICE_UNAVAILABLE"
        except (ValidationError, ValueError, TypeError, KeyError):
            code = "INVALID_SERVICE_RESPONSE"
        except TimeoutError:
            code = "SERVICE_UNAVAILABLE"
        except OSError:
            code = "CORPUS_UNAVAILABLE"
        except Exception as exc:
            code = "INTERNAL_ERROR"
            logging.getLogger("pavement_mcp.errors").warning(
                "MCP failure code=%s exception_type=%s", code, type(exc).__name__)
        return result(error_payload(code), failed=True)

    def _publication(self, doc_id):
        self.services.require_catalog()
        record = self.services.publication(doc_id)
        if record is None:
            raise ToolFailure("PUBLICATION_NOT_FOUND")
        m.Publication.model_validate(record)
        if record["doc_id"] != doc_id:
            raise ToolFailure("INVALID_SERVICE_RESPONSE")
        return record

    def search_publications(self, request):
        self.services.require_catalog()
        args = request.model_dump()
        for field in ("search", "topic"):
            args[field] = args[field].strip() or None if args[field] is not None else None
        return self.services.search(**args)

    def get_publication(self, request):
        return self._publication(request.doc_id)

    def retrieve_evidence(self, request):
        from mcp_server.evidence import build_evidence

        self.services.require_catalog()
        if request.doc_id is not None:
            self._publication(request.doc_id)
        self.services.require_retrieval()
        batch = self.services.evidence_candidates(request.query, doc_id=request.doc_id,
                                                 mode=request.mode, limit=request.limit)
        if not isinstance(batch, dict) or type(batch.get("scan_truncated")) is not bool:
            raise ToolFailure("INVALID_SERVICE_RESPONSE")
        return build_evidence(request, batch["hits"], corpus_version=batch["corpus_version"],
            publication=self.services.publication, scan_truncated=batch["scan_truncated"],
            overview_rankings=batch.get("overview_rankings"))
