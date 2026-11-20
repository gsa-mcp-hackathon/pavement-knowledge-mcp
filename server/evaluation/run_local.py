"""Exercise all three tools over STDIO without an AI client or generation key."""
import argparse
import asyncio
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def preflight(runtime):
    if runtime.is_relative_to(PACKAGE_ROOT) or PACKAGE_ROOT.is_relative_to(runtime):
        raise ValueError('The runtime assets must be outside the code directory.')
    for relative in ('data/index_registry.json', 'data/corpus/releases/v1/corpus_v1_chunks.csv',
                     'data/vector_db/v1/chroma.sqlite3', 'model-cache/hub'):
        path = runtime / relative
        if not path.exists() or not path.resolve().is_relative_to(runtime):
            raise ValueError('Required runtime assets are missing or outside the runtime root.')
    registry = json.loads((runtime / 'data/index_registry.json').read_text(encoding='utf-8'))
    index = registry['indexes']['v1']
    if index.get('embedding_model') != 'intfloat/e5-large-v2':
        raise ValueError('The evaluation expects the documented E5 corpus release.')


async def exercise(runtime, timeout):
    env = {
        'PAVEMENT_MCP_CORPUS_ROOT': str(runtime),
        'HF_HOME': str(runtime / 'model-cache'),
        'HF_HUB_CACHE': str(runtime / 'model-cache/hub'),
        'HF_HUB_DISABLE_TELEMETRY': '1',
        'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1',
        'ANONYMIZED_TELEMETRY': 'False',
    }
    params = StdioServerParameters(command=sys.executable,
        args=['-I', '-B', str(PACKAGE_ROOT / 'mcp_server/launch.py')], env=env)
    cases = json.loads((Path(__file__).with_name('cases.json')).read_text(encoding='utf-8'))
    results = []
    start = perf_counter()
    async with Client(params, read_timeout_seconds=timeout) as client:
        tools = (await client.list_tools()).tools
        if {t.name for t in tools} != {'search_publications', 'get_publication', 'retrieve_evidence'}:
            raise ValueError('Unexpected tool catalog.')
        discovery = perf_counter() - start
        for case in cases:
            before = perf_counter()
            response = await client.call_tool(case['tool'], case['arguments'])
            elapsed = perf_counter() - before
            data = response.structured_content
            if not isinstance(data, dict) or json.loads(response.content[0].text) != data:
                raise ValueError('Structured and text tool payloads differ.')
            error = case.get('expected_error')
            if error:
                passed = response.is_error and data.get('error', {}).get('code') == error
            else:
                passed = not response.is_error
                if case['tool'] == 'search_publications':
                    passed = passed and bool(data.get('items')) and len(data['items']) <= case['arguments']['limit']
                elif case['tool'] == 'get_publication':
                    passed = passed and data.get('doc_id') == case['arguments']['doc_id'] and bool(data.get('pdf_url'))
                else:
                    passages = data.get('passages', [])
                    passed = (passed and bool(passages) and len(passages) <= case['arguments'].get('limit', 8)
                        and sum(len(p['text']) for p in passages) <= 16000
                        and data.get('coverage', {}).get('complete_report') is False)
                    if case['arguments'].get('doc_id'):
                        passed = passed and all(p['doc_id'] == case['arguments']['doc_id'] for p in passages)
            results.append(dict(case_id=case['id'], tool=case['tool'], arguments=case['arguments'],
                seconds=round(elapsed, 4), passed=bool(passed), payload=data))
            print(f"{case['id']}: {'PASS' if passed else 'FAIL'} ({elapsed:.2f}s)", flush=True)
        return dict(server_version=client.server_info.version, python=platform.python_version(),
            platform=platform.system(), architecture=platform.machine(),
            discovery_seconds=round(discovery, 4), all_passed=all(r['passed'] for r in results),
            results=results, limitations=[
                'First call includes any remaining local warm-up time; later calls use the warm server.',
                'Checks transport, scope, bounds and errors; does not score answer accuracy or automatic discovery.',
                'No generation tools are called; the client model is not involved.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True, help='Prepared writable runtime asset directory')
    parser.add_argument('--timeout', type=float, default=240, help='Per-call timeout in seconds')
    parser.add_argument('--output', type=Path, help='Save results to a new JSON file; existing files are not overwritten')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    if args.output and args.output.exists():
        parser.error('--output already exists; choose a new filename')
    try:
        runtime = args.runtime.resolve(strict=True)
        preflight(runtime)
        result = asyncio.run(exercise(runtime, args.timeout))
        if args.output:
            with args.output.open('x', encoding='utf-8') as handle:
                json.dump(result, handle, indent=2)
                handle.write('\n')
        return 0 if result['all_passed'] else 1
    except Exception as exc:
        print(f'Local verification failed ({type(exc).__name__}). Check runtime assets, dependencies and server stderr.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
