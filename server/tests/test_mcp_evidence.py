"""Offline evidence-only tool checks: no real data, provider, or network calls."""
import asyncio
from collections import Counter
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from mcp_server.runtime import isolated_runtime
from tests.test_mcp_foundation import guard_side_effects, forbid_generation_imports


def hit(cid, text=None, doc="REPORT-A", heading=None, page=None):
    return dict(chunk_id=cid, document=text or f"Evidence in {cid}", metadata=dict(
        doc_id=doc, section_header=heading, page_start=page, page_end=page))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        from mcp_server.tools import PavementTools
        self.backend = Mock()
        self.backend.publication.side_effect = lambda did: dict(doc_id=did,
            title=f"Catalog title {did}", report_no=f"FHWA-{did}", year=None,
            topic="", primary_topic="", pdf_url=f"https://example.test/{did}.pdf",
            trust_badge="", abstract="", page_count=None)
        self.backend.evidence_candidates.return_value = dict(hits=[], scan_truncated=False, corpus_version="v1")
        self.tools = PavementTools(self.backend)

    def call(self, args, hits=None, scan_truncated=False):
        if hits is not None:
            self.backend.evidence_candidates.return_value = dict(hits=hits,
                scan_truncated=scan_truncated, corpus_version="v1")
        result = self.tools.call("retrieve_evidence", args)
        self.assertEqual(json.loads(result.content[0].text), result.structured_content)
        self.backend.answer.assert_not_called()
        self.backend.require_provider.assert_not_called()
        return result

    def success(self, args, hits, **kwargs):
        result = self.call(args, hits, **kwargs)
        self.assertFalse(result.is_error, result.structured_content)
        return result.structured_content

    def test_invalid_mode_combinations_rejected_before_services(self):
        for args in ({}, {"query": " "}, {"query": "q" * 8001},
                     {"mode": "report_overview"},
                     {"mode": "report_overview", "doc_id": "REPORT-A", "query": "q"},
                     {"mode": "invalid", "query": "q"},
                     {"query": "q", "limit": True}, {"query": "q", "limit": 13},
                     {"query": "q", "doc_id": ""}, {"query": "q", "where": {}},
                     {"query": "q", "max_chars": 1000000}):
            with self.subTest(args=args):
                self.assertEqual(self.call(args).structured_content["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(self.backend.mock_calls, [])

    def test_corpus_diversity_dedup_and_catalog_provenance(self):
        rows = [hit("a1", "First passage"), hit("a1", "First passage"),
                hit("a2", "First  passage"), *[hit(f"a{i}") for i in range(3, 7)],
                hit("b1", doc="REPORT-B", page="12")]
        data = self.success({"query": "FWD compared with TSD"}, rows)
        self.assertEqual(data["scope"], "corpus")
        self.assertIsNone(data["doc_id"])
        self.assertEqual(data["duplicates_removed"], 2)
        self.assertEqual(Counter(p["doc_id"] for p in data["passages"]), {"REPORT-A": 3, "REPORT-B": 1})
        self.assertEqual(data["passages"][0]["doc_title"], "Catalog title REPORT-A")
        self.assertEqual(data["passages"][-1]["page_start"], 12)
        self.assertIsNone(data["passages"][0]["page_start"])
        self.assertTrue(data["truncated"])
        self.backend.evidence_candidates.assert_called_once_with(
            "FWD compared with TSD", doc_id=None, mode="query", limit=8)

    def test_selected_scope_has_no_diversity_cap_and_rejects_foreign_passages(self):
        args = {"query": "q", "doc_id": "REPORT-A"}
        data = self.success(args, [hit(str(i)) for i in range(7)])
        self.assertEqual(len(data["passages"]), 7)
        self.assertEqual(data["scope"], "publication")
        for mode_args in (args, {"mode": "report_overview", "doc_id": "REPORT-A"}):
            result = self.call(mode_args, [hit("foreign", doc="REPORT-B")])
            self.assertTrue(result.is_error)
            self.assertEqual(result.structured_content["error"]["code"], "INVALID_SERVICE_RESPONSE")
        self.backend.publication.side_effect = None
        self.backend.publication.return_value = None
        self.assertEqual(self.call(args).structured_content["error"]["code"], "PUBLICATION_NOT_FOUND")

    def test_overview_covers_headings_and_keeps_missing_metadata(self):
        rows = [hit("p", heading="Purpose", page=1), hit("m", heading="Test Methods", page=4),
                hit("f", heading="Results", page=30), hit("c", heading="Conclusions", page=90),
                hit("l", heading="Limitations"), hit("r", heading="Recommendations", page=91),
                hit("unlabelled")]
        data = self.success({"mode": "report_overview", "doc_id": "REPORT-A"}, rows)
        self.assertEqual(len(data["passages"]), 7)
        self.assertEqual(data["coverage"]["section_roles_not_observed"], [])
        self.assertFalse(data["coverage"]["complete_report"])
        self.assertIn("unlabelled", [p["chunk_id"] for p in data["passages"]])
        self.assertIsNone(next(p for p in data["passages"] if p["chunk_id"] == "l")["page_start"])
        data = self.success({"mode": "report_overview", "doc_id": "REPORT-A", "limit": 2}, rows)
        self.assertTrue(data["truncated"])
        self.assertIn("limitations", data["coverage"]["section_roles_not_observed"])

    def test_bounds_empty_results_and_scan_limit_are_disclosed(self):
        args = {"mode": "report_overview", "doc_id": "REPORT-A"}
        data = self.success(args, [hit("large", "x" * 17000)])
        self.assertEqual(len(data["passages"][0]["text"]), 16000)
        self.assertTrue(data["passages"][0]["text_truncated"])
        self.assertTrue(data["truncated"])
        data = self.success({"query": "q", "doc_id": "REPORT-A"},
                            [hit("a", "x" * 15000), hit("b", "y" * 2000), hit("c", "complete")])
        self.assertEqual([p["chunk_id"] for p in data["passages"]], ["a", "c"])
        self.assertTrue(data["truncated"])
        data = self.success(args, [], scan_truncated=True)
        self.assertEqual(data["passages"], [])
        self.assertTrue(data["candidate_scan_truncated"])
        self.assertTrue(any("does not prove" in w for w in data["warnings"]))

    def test_flat_headings_use_query_rankings_without_claiming_coverage(self):
        self.backend.evidence_candidates.return_value = dict(
            hits=[hit("front"), hit("methods"), hit("results"), hit("limits"), hit("noise", "•")],
            corpus_version="v1", scan_truncated=False,
            overview_rankings={"purpose": ["front"], "methods": ["methods"],
                               "findings": ["results"], "limitations": ["limits"]})
        response = self.call({"mode": "report_overview", "doc_id": "REPORT-A", "limit": 4})
        self.assertFalse(response.is_error)
        data = response.structured_content
        self.assertEqual([p["chunk_id"] for p in data["passages"]], ["front", "methods", "results", "limits"])
        self.assertEqual(data["coverage"]["section_roles_present"], ["other"])
        self.assertIn("limitations", data["coverage"]["section_roles_not_observed"])

    def test_malformed_sources_fail_closed_and_pages_are_not_invented(self):
        for row in ({}, hit(""), dict(hit("a"), document=None), hit("a", doc="")):
            result = self.call({"query": "q"}, [row])
            self.assertEqual(result.structured_content["error"]["code"], "INVALID_SERVICE_RESPONSE")
        row = hit("a", page=True)
        row["metadata"]["page_end"] = "unknown"
        data = self.success({"query": "q"}, [row])
        self.assertIsNone(data["passages"][0]["page_start"])
        self.assertIsNone(data["passages"][0]["page_end"])
        self.backend.publication.side_effect = lambda did: {"doc_id": "different"}
        self.assertTrue(self.call({"query": "q"}, [hit("a")]).is_error)

    def test_warmup_failure_blocks_new_tool(self):
        self.tools._warmup_failed = True
        result = self.call({"query": "q"})
        self.assertEqual(result.structured_content["error"]["code"], "SERVICE_UNAVAILABLE")
        self.backend.evidence_candidates.assert_not_called()

    def test_sdk_roundtrip_new_modes_and_schema(self):
        from mcp.client import Client
        from mcp_server.server import create_server
        self.backend.evidence_candidates.return_value["hits"] = [hit("a")]
        async def run():
            async with Client(create_server(self.backend)) as client:
                definition = next(d for d in (await client.list_tools()).tools if d.name == "retrieve_evidence")
                self.assertFalse(definition.input_schema["additionalProperties"])
                for args in ({"query": "q"}, {"mode": "report_overview", "doc_id": "REPORT-A"}):
                    result = await client.call_tool("retrieve_evidence", args)
                    self.assertFalse(result.is_error, result.structured_content)
                    self.assertEqual(json.loads(result.content[0].text), result.structured_content)
        asyncio.run(run())
        self.backend.require_provider.assert_not_called()
        self.backend.answer.assert_not_called()


class LocalCandidateTests(unittest.TestCase):
    def setUp(self):
        from mcp_server.services import CorpusServices
        self.backend = CorpusServices()
        self.backend.require_retrieval = Mock()
        self.backend.root = ROOT
        self.backend.config = SimpleNamespace(corpus_version="v1", embedding_model="local-test",
            dense_top_k=50, lexical_top_k=50, rrf_k=60, lexical_rrf_max_rank=20)
        self.backend.require_provider = Mock(side_effect=AssertionError("provider forbidden"))

    def test_query_uses_local_hybrid_engine_without_generation(self):
        with patch("mcp_server.retrieval.cache.get_retrieval_engine") as factory:
            factory.return_value.retrieve.return_value = [hit("a")]
            data = self.backend.evidence_candidates("q", doc_id="REPORT-A", mode="query", limit=8)
            self.assertEqual(data["corpus_version"], "v1")
            kwargs = factory.return_value.retrieve.call_args.kwargs
            self.assertEqual(kwargs["doc_id"], "REPORT-A")
            self.assertEqual(kwargs["per_doc_cap"], 0)
            self.assertNotIn("rerank", kwargs)
            self.assertEqual(kwargs["retrieval_mode"], "hybrid")
        self.backend.require_provider.assert_not_called()

    def test_overview_scan_is_scoped_paged_and_bounded(self):
        with patch("mcp_server.retrieval.cache.get_retrieval_engine") as factory:
            engine = factory.return_value
            engine.build_where.return_value = {"doc_id": "REPORT-A"}
            engine.retrieve.return_value = [hit("20")]
            def page(**kwargs):
                rows = [hit(str(i)) for i in range(kwargs["offset"], kwargs["offset"] + kwargs["limit"])]
                return dict(ids=[h["chunk_id"] for h in rows], documents=[h["document"] for h in rows],
                            metadatas=[h["metadata"] for h in rows])
            engine.collection.get.side_effect = page
            data = self.backend.evidence_candidates(None, doc_id="REPORT-A", mode="report_overview", limit=8)
            self.assertEqual(len(data["hits"]), 5000)
            self.assertTrue(data["scan_truncated"])
            self.assertEqual(engine.collection.get.call_count, 11)
            self.assertTrue(all(c.kwargs["where"] == {"doc_id": "REPORT-A"}
                                for c in engine.collection.get.call_args_list))
            self.assertEqual(engine.retrieve.call_count, 6)
            self.assertEqual(data["overview_rankings"]["limitations"], ["20"])
            self.assertTrue(all(c.kwargs["doc_id"] == "REPORT-A" and "rerank" not in c.kwargs
                                for c in engine.retrieve.call_args_list))
            engine.collection.get.side_effect = None
            engine.collection.get.return_value = dict(ids=[], documents=[], metadatas=[])
            self.assertEqual(self.backend.evidence_candidates(None, doc_id="REPORT-A",
                mode="report_overview", limit=8)["hits"], [])
        self.backend.require_provider.assert_not_called()

    def test_bad_scan_response_is_rejected(self):
        from mcp_server.errors import ToolFailure
        with patch("mcp_server.retrieval.cache.get_retrieval_engine") as factory:
            factory.return_value.collection.get.return_value = dict(ids=["a"], documents=[], metadatas=[])
            with self.assertRaises(ToolFailure):
                self.backend.evidence_candidates(None, doc_id="REPORT-A", mode="report_overview", limit=8)


if __name__ == "__main__":
    for name in list(os.environ):
        if name.startswith("PAVEMENT_MCP_"):
            os.environ.pop(name)
    with isolated_runtime():
        forbidden = forbid_generation_imports()
        blocked = guard_side_effects(allow_event_loop=True)
        program = unittest.main(verbosity=2, exit=False)
        if blocked or forbidden or not program.result.wasSuccessful():
            raise SystemExit(1)
