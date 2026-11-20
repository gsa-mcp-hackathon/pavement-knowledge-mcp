"""Offline foundation checks in fresh processes, with synthetic settings only."""

import asyncio
import importlib.abc
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "mcp_server" / "launch.py"
sys.dont_write_bytecode = True


def guard_side_effects(*, allow_event_loop=False):
    """Deny credential/data reads and application side effects in child checks."""
    blocked = []

    def guard(event, args):
        reason = None
        # Windows asyncio wakes its loop through stdlib socketpair's temporary
        # loopback connection. Permit only that exact caller, not arbitrary local
        # listeners or outbound connections. Import-only probes need no exception.
        if (allow_event_loop and event in {"socket.connect", "socket.bind"}
                and sys._getframe(1).f_code is socket.socketpair.__code__
                and args[1][0] in {"127.0.0.1", "::1"}):
            return
        if event in {"socket.connect", "socket.bind", "sqlite3.connect", "subprocess.Popen", "os.system"}:
            reason = event
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.name == ".env" or path.name.startswith(".env."):
                reason = "dotenv read"
            if path.is_relative_to(ROOT / "data") or path.suffix.lower() in {".doc", ".docx"}:
                reason = "application data/document read"
            flags = args[2]
            if path.is_relative_to(ROOT) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
                reason = "workspace write"
        if reason:
            blocked.append(reason)
            raise RuntimeError("Foundation check blocked: " + reason)

    sys.addaudithook(guard)
    return blocked


def forbid_generation_imports():
    """Fail if an active MCP path tries to import shared application code or a generation service."""
    attempted = []

    class Guard(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if (fullname.split(".")[0] in {"app", "rag", "services", "openai", "anthropic"}
                    or fullname in {"rag.agent", "rag.v3"}):
                attempted.append(fullname)
                raise ImportError("Generation import prohibited by test")
            return None

    sys.meta_path.insert(0, Guard())
    return attempted


def child_check(mode):
    blocked = guard_side_effects(allow_event_loop=mode == "serve")
    sys.path.insert(0, str(ROOT))
    if mode == "serve":
        sys.argv = [str(LAUNCHER)]
        try:
            runpy.run_path(str(LAUNCHER), run_name="__main__")
        except SystemExit as exc:
            assert exc.code == 0
        assert not any(n.split(".")[0] in {"app", "rag", "services"} for n in sys.modules)
    else:
        from mcp_server.runtime import isolated_runtime

        previous_directory = Path.cwd()
        with isolated_runtime():
            runtime_directory = Path.cwd()
            assert runtime_directory != previous_directory
            assert not list(runtime_directory.iterdir())
            assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"
            assert not any(n.startswith(("FHWA_", "OPENAI_", "PAVEMENT_MCP_OPENAI_")) for n in os.environ)

            # Real local imports must work even when generation dependencies are forbidden.
            forbidden = forbid_generation_imports()
            from mcp_server.catalog import PublicationCatalog
            from mcp_server.services import CorpusServices, RetrievalSettings
            from mcp_server.retrieval.cache import _cached_engine

            assert RetrievalSettings().corpus_version == "v1"
            assert _cached_engine.cache_info().currsize == 0
            assert not forbidden
            assert not any(n.split(".")[0] in {"app", "rag", "services", "openai", "anthropic"}
                           or n in {"rag.agent", "rag.v3"} for n in sys.modules)
        assert Path.cwd() == previous_directory
        assert not runtime_directory.exists()
        # Starting after retrieval imports must fail rather than silently reuse config.
        try:
            with isolated_runtime():
                raise AssertionError("Reused application configuration")
        except RuntimeError as exc:
            assert str(exc) == "MCP must start before retrieval or application imports."
    assert not blocked, "A dependency attempted and caught a forbidden side effect"


if __name__ == "__main__" and len(sys.argv) == 2 and sys.argv[1] in {"probe", "provider", "serve"}:
    child_check(sys.argv[1])
    raise SystemExit(0)


from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, get_default_environment


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="mcp-foundation-test-")
        self.addCleanup(self.directory.cleanup)
        # This is a fake fixture outside the repository, never a real env file.
        Path(self.directory.name, ".env").write_text(
            "FHWA_LOCAL_ANSWER_PIPELINE=v2\nOPENAI_API_KEY=synthetic-file-key\n",
            encoding="utf-8",
        )
        self.env = get_default_environment() | {
            "FHWA_LOCAL_ANSWER_PIPELINE": "v2",
            "FHWA_CORPUS_VERSION": "invalid-inherited-version",
            "OPENAI_API_KEY": "synthetic-inherited-key",
            "OPENAI_BASE_URL": "https://invalid.example",
            "PYTHON_DOTENV_DISABLED": "0",
        }

    def test_local_imports_ignore_application_environment_and_dotenv(self):
        self.run_probe("probe")

    def test_obsolete_mcp_provider_settings_are_discarded(self):
        self.env["PAVEMENT_MCP_OPENAI_API_KEY"] = "synthetic-mcp-key"
        self.env["PAVEMENT_MCP_OPENAI_BASE_URL"] = "https://invalid.example"
        self.run_probe("provider")

    def run_probe(self, mode):
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(Path(__file__).resolve()), mode],
            cwd=self.directory.name, env=self.env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_real_stdio_modern_and_legacy_connections(self):
        async def exercise():
            for mode in ("auto", "legacy"):
                with self.subTest(mode=mode):
                    params = StdioServerParameters(
                        command=sys.executable,
                        args=["-I", "-B", str(Path(__file__).resolve()), "serve"],
                        cwd=self.directory.name, env=self.env,
                    )
                    async with Client(params, mode=mode, read_timeout_seconds=10) as client:
                        self.assertEqual(client.server_info.name, "Pavement Knowledge MCP")
                        definitions = (await client.list_tools()).tools
                        self.assertEqual({t.name for t in definitions}, {
                            "search_publications", "get_publication", "retrieve_evidence",
                        })
                        self.assertTrue(all(t.input_schema["additionalProperties"] is False for t in definitions))
                        invalid = await client.call_tool("retrieve_evidence", {"query": " "})
                        self.assertTrue(invalid.is_error)
                        self.assertEqual(invalid.structured_content["error"]["code"], "INVALID_ARGUMENT")

        asyncio.run(asyncio.wait_for(exercise(), timeout=30))


if __name__ == "__main__":
    unittest.main(verbosity=2)
