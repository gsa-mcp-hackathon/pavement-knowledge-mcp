"""Print a local STDIO configuration; do not modify client settings."""
import json
from pathlib import Path
import sys

server = Path(__file__).resolve().parent
runtime = server.parent / 'runtime'
if not (runtime / 'data/index_registry.json').is_file():
    raise SystemExit('Keep server/ and runtime/ together inside the evaluation bundle.')
print(json.dumps({'mcpServers': {'pavement_knowledge': {
    'command': str(Path(sys.executable).resolve()),
    'args': ['-I', '-B', str(server / 'mcp_server/launch.py')],
    'env': {
        'PAVEMENT_MCP_CORPUS_ROOT': str(runtime),
        'HF_HOME': str(runtime / 'model-cache'),
        'HF_HUB_CACHE': str(runtime / 'model-cache/hub'),
        'HF_HUB_DISABLE_TELEMETRY': '1',
        'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1',
        'ANONYMIZED_TELEMETRY': 'False',
    },
}}}, indent=2))
