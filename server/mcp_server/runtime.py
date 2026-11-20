"""Process-local configuration boundary for the standalone MCP launcher."""

from contextlib import contextmanager
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


@contextmanager
def isolated_runtime():
    """Enter once in a fresh MCP process, before importing the SDK or retrieval engine.

    Environment changes deliberately last for this process. This is not a
    sandbox for file access or third-party dependency operations.
    """
    if ("mcp_server.retrieval.engine" in sys.modules
            or any(name.split(".")[0] in {"app", "rag", "services"} for name in sys.modules)):
        raise RuntimeError("MCP must start before retrieval or application imports.")

    sys.dont_write_bytecode = True
    # No generation settings are consumed. Discard obsolete MCP provider inputs
    # as well as inherited application/provider values in this child process only.
    for name in list(os.environ):
        if name.startswith(("FHWA_", "OPENAI_", "PAVEMENT_MCP_OPENAI_")):
            os.environ.pop(name, None)

    # Disable dotenv loading by dependencies. Chroma's separate dotenv_values
    # lookup also needs a clean cwd below.
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    previous_directory = Path.cwd()
    with TemporaryDirectory(prefix="pavement-mcp-") as directory:
        os.chdir(directory)
        try:
            yield
        finally:
            os.chdir(previous_directory)
