"""Opt-in real MCP integration checks; run against an already-open TEST COPY.

python tests/simulation_phase1_live.py --document C:/.../test.SLDPRT --output C:/.../evidence.json
Does not mesh or solve. Creates/reuses Static_API_Test and changes face selection.
"""
import argparse
import asyncio
import csv
import io
import json
import subprocess
from pathlib import Path
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).resolve().parents[1]


def pids():
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq SLDWORKS.exe', '/FO', 'CSV', '/NH'],
                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return sorted(row[1] for row in csv.reader(io.StringIO(result.stdout))
                  if len(row) > 1 and row[0].casefold() == 'sldworks.exe')


async def main(args):
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    timings = ROOT / 'local_state/sw2020/timings.jsonl'
    before_size = timings.stat().st_size if timings.exists() else 0
    before_pids = pids()
    transport = StdioTransport(str(ROOT / '.venv/Scripts/python.exe'),
        [str(ROOT / 'src/utils/start_sw2020_stable.py'), '--real', '--year', '2020'],
        cwd=str(ROOT), log_file=output.with_suffix('.server.log'))
    results = {}
    async with Client(transport, timeout=180) as client:
        names = [tool.name for tool in await client.list_tools()]
        results['discovery'] = {'tool_count': len(names), 'simulation_tools': [n for n in names if n.startswith('sw_simulation_')],
            'pids_before': before_pids, 'pids_after': pids(),
            'no_business_calls_during_discovery': (timings.stat().st_size if timings.exists() else 0) == before_size}
        assert results['discovery']['pids_before'] == results['discovery']['pids_after']
        assert results['discovery']['no_business_calls_during_discovery']
        async def call(name, arguments, key, status='success'):
            data = (await client.call_tool(name, arguments)).data
            results[key] = data
            output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            assert data['status'] == status, data
            return data
        await call('sw_simulation_check', {'load_addin': True}, 'environment')
        geometry = await call('sw_simulation_inspect_geometry', {'expected_document': args.document}, 'geometry')
        ids = [item['id'] for category in ('faces', 'edges', 'vertices') for item in geometry[category]]
        resolved = await call('sw_simulation_resolve_geometry', {'expected_document': args.document, 'ids': ids}, 'references')
        assert resolved['count'] == len(ids)
        first = await call('sw_simulation_create_static_study', {'expected_document': args.document}, 'study')
        repeat = await call('sw_simulation_create_static_study', {'expected_document': args.document}, 'study_repeat')
        assert not repeat['created'] and first['study_count'] == repeat['study_count']
        guard = await call('sw_simulation_create_static_study', {'expected_document': 'C:/wrong-document.SLDPRT', 'name': 'MUST_NOT_BE_CREATED'}, 'wrong_document', 'error')
        assert guard['error_code'] == 'DOCUMENT_MISMATCH'
        invalid = await call('sw_simulation_resolve_geometry', {'expected_document': args.document, 'ids': ['face_NOT_BASE64']}, 'invalid_reference', 'error')
        assert invalid['error_code'] == 'INVALID_PERSIST_REFERENCE'
        await call('sw_simulation_resolve_geometry', {'expected_document': args.document, 'ids': [geometry['faces'][0]['id']], 'highlight': True}, 'highlight')
        preflight = await call('sw2020_preflight', {'expected_document': args.document}, 'existing_modeling_tool')
        assert not preflight['sketch_editing']
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: discovery, environment, geometry, references, study reuse, document guard, invalid ID, selection, existing preflight')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--document', required=True)
    parser.add_argument('--output', required=True)
    asyncio.run(main(parser.parse_args()))
