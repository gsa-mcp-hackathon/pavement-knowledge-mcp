"""Offline service-mapping and MCP payload checks. No real corpus or API calls."""

import asyncio
import csv
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from mcp_server.runtime import isolated_runtime

# This entire test suite uses the actual standalone configuration boundary.
for name in list(os.environ):
    if name.startswith("PAVEMENT_MCP_"):
        os.environ.pop(name)

from tests.test_mcp_foundation import guard_side_effects


class ToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mcp_server.tools import PavementTools

        cls.adapter_type = PavementTools

    def setUp(self):
        self.record = dict(doc_id="REPORT-A", title="Pavement testing", report_no="FHWA-A",
                           year=None, topic="Testing", primary_topic="Testing", pdf_url="https://example.test/a.pdf",
                           trust_badge="", abstract="", page_count=None)
        self.backend = Mock()
        self.backend.publication.return_value = self.record
        self.backend.search.return_value = dict(items=[], count=0, topics=[], years=[])
        self.tools = self.adapter_type(self.backend)

    def call(self, name, args):
        response = self.tools.call(name, args)
        self.assertEqual(json.loads(response.content[0].text), response.structured_content)
        return response

    def assert_error(self, result, code):
        self.assertTrue(result.is_error)
        self.assertEqual(result.structured_content["error"]["code"], code)
        self.assertNotIn("PRIVATE-SENTINEL", result.model_dump_json())

    def test_search_preserves_count_facets_order_and_match_labels(self):
        payload = dict(items=[dict(self.record, match_status="content_mention", match_reason="Text match")],
                       count=24, topics=["Testing", "Materials"], years=[2024, 2018])
        self.backend.search.return_value = payload
        response = self.call("search_publications", {"search": "  FWD  ", "topic": " ", "limit": 1, "offset": 3})
        self.assertFalse(response.is_error)
        self.assertEqual(response.structured_content, payload)
        self.backend.search.assert_called_once_with(search="FWD", topic=None, year=None, limit=1, offset=3)

    def test_exact_identity_unknown_and_malformed_catalog(self):
        response = self.call("get_publication", {"doc_id": " REPORT-A "})
        self.assertEqual(response.structured_content, self.record)
        self.backend.publication.assert_called_once_with("REPORT-A")
        self.backend.publication.return_value = None
        self.assert_error(self.call("get_publication", {"doc_id": "unknown"}), "PUBLICATION_NOT_FOUND")
        self.backend.evidence_candidates.assert_not_called()
        self.backend.publication.return_value = dict(self.record, doc_id="other")
        self.assert_error(self.call("get_publication", {"doc_id": "REPORT-A"}), "INVALID_SERVICE_RESPONSE")
        self.backend.search.return_value = dict(items=[], count="0", topics=[], years=[])
        self.assert_error(self.call("search_publications", {}), "INVALID_SERVICE_RESPONSE")

    def test_warmup_waits_once_and_keeps_discovery_available(self):
        from threading import Event
        import concurrent.futures
        entered, release = Event(), Event()
        def warming():
            entered.set()
            if not release.wait(10):
                raise RuntimeError("test coordination timeout")
        self.backend.warmup.side_effect = warming
        self.tools.start_warmup()
        try:
            self.assertTrue(entered.wait(5))
            self.assertEqual(len(self.tools.definitions()), 3)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(self.tools.call, "search_publications", {"search": "q"})
                try:
                    with self.assertRaises(concurrent.futures.TimeoutError):
                        pending.result(timeout=0.1)
                    self.backend.evidence_candidates.assert_not_called()
                finally:
                    release.set()
                self.assertFalse(pending.result(timeout=5).is_error)
        finally:
            release.set()
            self.assertTrue(self.tools._warmup_done.wait(5))
        self.tools.start_warmup()
        self.backend.warmup.assert_called_once()

    def test_warmup_failure_is_private_and_blocks_retrieval(self):
        self.backend.warmup.side_effect = RuntimeError("PRIVATE-SENTINEL")
        with self.assertLogs("pavement_mcp.warmup", level="WARNING") as logs:
            self.tools.start_warmup()
            self.assertTrue(self.tools._warmup_done.wait(5))
        self.assertNotIn("PRIVATE-SENTINEL", str(logs.output))
        self.assert_error(self.call("retrieve_evidence", {"query": "q"}), "SERVICE_UNAVAILABLE")
        self.assert_error(self.call("retrieve_evidence", {"mode": "report_overview", "doc_id": "REPORT-A"}), "SERVICE_UNAVAILABLE")
        self.backend.evidence_candidates.assert_not_called()
        # Catalog operations remain usable after local retrieval warm-up failure.
        self.backend.search.return_value = {"items": [], "count": 0, "topics": [], "years": []}
        self.assertFalse(self.call("search_publications", {}).is_error)

    def test_index_preflight_refuses_active_or_outside_paths(self):
        from mcp_server.services import CorpusServices
        from mcp_server.errors import ToolFailure

        backend = CorpusServices()
        backend._loaded = True
        backend.isolated = False
        with self.assertRaises(ToolFailure):
            backend.require_retrieval()
        with TemporaryDirectory() as directory:
            backend.root, backend.isolated = Path(directory), True
            backend.config = SimpleNamespace(corpus_version="v1")
            (backend.root / "data").mkdir()
            registry = backend.root / "data/index_registry.json"
            registry.write_text(json.dumps({"indexes": {"v1": {"persist_dir": str(ROOT / "data/vector_db/v1")}}}))
            with self.assertRaises(ToolFailure):
                backend.require_retrieval()
            registry.write_text(json.dumps({"indexes": {"v1": {"persist_dir": "relative/path"}}}))
            with self.assertRaises(ToolFailure):
                backend.require_retrieval()
            vector = backend.root / "data/vector_db/v1"
            vector.mkdir(parents=True)
            (vector / "chroma.sqlite3").touch()  # Empty test marker, never connected.
            registry.write_text(json.dumps({"indexes": {"v1": {}}}))
            backend.require_retrieval()

    def test_removed_tools_and_invalid_inputs_never_reach_services(self):
        for name in ("answer_pavement_question", "summarize_publication", "retrieve_publication_evidence"):
            self.assert_error(self.call(name, {"query": "q", "doc_id": "REPORT-A"}), "INVALID_ARGUMENT")
        for name, args in [
            ("get_publication", {}), ("get_publication", {"doc_id": " "}),
            ("get_publication", {"doc_id": "a" * 201}),
            ("search_publications", {"year": True}), ("search_publications", {"limit": "2"}),
            ("search_publications", {"limit": 26}), ("search_publications", {"offset": -1}),
            ("search_publications", {"search": "a" * 501}),
            ("retrieve_evidence", {"query": "q", "source_only": True}),
            ("retrieve_evidence", {"query": "q", "model": "PRIVATE-SENTINEL"}),
        ]:
            self.assert_error(self.call(name, args), "INVALID_ARGUMENT")
        self.assertEqual(self.backend.mock_calls, [])

    def test_safe_errors_and_rejected_service_fields(self):
        from mcp_server.errors import ToolFailure
        for error, code in [(RuntimeError("PRIVATE-SENTINEL"), "INTERNAL_ERROR"),
                            (ValueError("PRIVATE-SENTINEL"), "INVALID_SERVICE_RESPONSE"),
                            (TimeoutError("PRIVATE-SENTINEL"), "SERVICE_UNAVAILABLE"),
                            (FileNotFoundError("PRIVATE-SENTINEL"), "CORPUS_UNAVAILABLE"),
                            (ImportError("PRIVATE-SENTINEL"), "SERVICE_UNAVAILABLE"),
                            (ToolFailure("SERVICE_UNAVAILABLE"), "SERVICE_UNAVAILABLE")]:
            self.backend.search.side_effect = error
            self.assert_error(self.call("search_publications", {}), code)
        self.backend.search.side_effect = None
        self.backend.search.return_value["private_config"] = "PRIVATE-SENTINEL"
        self.assert_error(self.call("search_publications", {}), "INVALID_SERVICE_RESPONSE")

    def test_local_catalog_and_independent_root_binding(self):
        from mcp_server.services import CorpusServices
        from mcp_server.errors import ToolFailure
        with patch.dict(os.environ, {"PAVEMENT_MCP_CORPUS_ROOT": str(ROOT)}):
            with self.assertRaises(ToolFailure):
                CorpusServices().require_catalog()
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            release = root / "data/corpus/releases/v1"
            release.mkdir(parents=True)
            chunks = release / "corpus_v1_chunks.csv"
            with chunks.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["doc_id", "doc_title", "topic", "chunk_text_readable"])
                writer.writeheader()
                writer.writerows([
                    dict(doc_id="REPORT-A", doc_title="Materials", topic="Testing", chunk_text_readable="FWD response"),
                    dict(doc_id="REPORT-B", doc_title="FWD methods", topic="Testing", chunk_text_readable="Other text"),
                    dict(doc_id="REPORT-B", doc_title="FWD methods", topic="Testing", chunk_text_readable="Repeat document"),
                ])
            with patch.dict(os.environ, {"PAVEMENT_MCP_CORPUS_ROOT": str(root)}):
                backend = CorpusServices()
                self.tools = self.adapter_type(backend)
                data = self.call("search_publications", {"search": "FWD"}).structured_content
                self.assertEqual(data["count"], 1)
                self.assertEqual(data["items"][0]["doc_id"], "REPORT-B")
                self.assertEqual(data["items"][0]["match_status"], "metadata_match")
                data = self.call("search_publications", {"search": "FWD response"}).structured_content
                self.assertEqual(data["items"][0]["doc_id"], "REPORT-A")
                self.assertEqual(data["items"][0]["match_status"], "content_mention")
                self.assertEqual(self.call("search_publications", {"limit": 1, "offset": 1}).structured_content["count"], 2)
                self.assertEqual(self.call("get_publication", {"doc_id": "REPORT-A"}).structured_content["title"], "Materials")
                self.assertEqual(backend.root, root)
                self.assertEqual(backend.publications.CHUNKS_PATH, chunks)
                self.assertFalse(any(n.split(".")[0] == "app" for n in sys.modules))
                chunks.unlink()
                self.assert_error(self.call("search_publications", {}), "CORPUS_UNAVAILABLE")

    def test_strict_warmup_uses_local_engine_and_propagates_failure(self):
        from mcp_server.services import CorpusServices, RetrievalSettings
        from mcp_server.errors import ToolFailure
        backend = CorpusServices()
        backend.require_catalog = Mock()
        backend.require_retrieval = Mock()
        backend.root = ROOT
        backend.config = RetrievalSettings()
        backend.publications = Mock()
        backend.publications.all_publications.return_value = [self.record]
        with patch("mcp_server.retrieval.cache.get_retrieval_engine") as factory:
            engine = factory.return_value
            engine.retrieve.return_value = [{"chunk_id": "synthetic"}]
            engine._ensure_bm25_index.return_value.N = 1
            backend.warmup()
            self.assertEqual(engine.retrieve.call_args.kwargs["retrieval_mode"], "hybrid")
            engine.retrieve.side_effect = RuntimeError("PRIVATE-SENTINEL")
            with self.assertRaises(RuntimeError):
                backend.warmup()
            factory.reset_mock()
            backend.require_retrieval.side_effect = ToolFailure("SERVICE_UNAVAILABLE")
            with self.assertRaises(ToolFailure):
                backend.warmup()
            factory.assert_not_called()

    def test_sdk_three_tools_and_structured_payload(self):
        from mcp.client import Client
        from mcp_server.server import create_server

        async def exercise():
            async with Client(create_server(self.backend)) as client:
                definitions = (await client.list_tools()).tools
                self.assertEqual({d.name for d in definitions}, {
                    "search_publications", "get_publication", "retrieve_evidence"})
                self.assertTrue(all(d.input_schema["additionalProperties"] is False for d in definitions))
                self.assertTrue(all(d.annotations.read_only_hint and d.annotations.idempotent_hint
                                    and not d.annotations.open_world_hint for d in definitions))
                response = await client.call_tool("get_publication", {"doc_id": "REPORT-A"})
                self.assertFalse(response.is_error, response.structured_content)
                self.assertEqual(response.structured_content, self.record)
                self.assertEqual(json.loads(response.content[0].text), self.record)
        asyncio.run(exercise())


if __name__ == "__main__":
    from tests.test_mcp_foundation import forbid_generation_imports
    with isolated_runtime():
        forbidden = forbid_generation_imports()
        blocked = guard_side_effects(allow_event_loop=True)
        program = unittest.main(verbosity=2, exit=False)
        if blocked or forbidden or not program.result.wasSuccessful():
            raise SystemExit(1)
