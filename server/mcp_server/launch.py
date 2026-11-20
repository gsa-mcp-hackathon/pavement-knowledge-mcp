"""Launch with the dedicated Python: python -I -B /absolute/path/launch.py."""

import argparse
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Pavement Knowledge MCP over local STDIO."
    )
    parser.parse_args()
    sys.dont_write_bytecode = True
    # An absolute script path plus -I works from any client working directory,
    # without trusting PYTHONPATH or loading the user's Python site packages.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from mcp_server.runtime import isolated_runtime

    try:
        with isolated_runtime():
            import anyio
            from mcp_server.server import run_stdio

            anyio.run(run_stdio)
    except KeyboardInterrupt:
        return 0
    except Exception:
        # No raw exception text: configuration failures may contain local paths
        # or credentials. stdout is exclusively the MCP protocol stream.
        print("Pavement Knowledge MCP could not run. Check its setup guide.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
