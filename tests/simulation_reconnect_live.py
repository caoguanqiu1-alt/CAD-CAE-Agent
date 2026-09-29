"""Opt-in readback of an existing saved study through two new MCP connections.

Does not create geometry/studies, mesh, solve, or save. Study activation can
change the selected Simulation tab. Keep raw output local: it contains paths.
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
EXPECTED = {
    'sw_simulation_check', 'sw_simulation_create_static_study',
    'sw_simulation_inspect_geometry', 'sw_simulation_resolve_geometry',
    'sw_simulation_static_step', 'sw_simulation_general_step',
    'sw_simulation_make_pin', 'sw_simulation_run_plan',
}


def pids():
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq SLDWORKS.exe',
                             '/FO', 'CSV', '/NH'], capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, check=True)
    return sorted(row[1] for row in csv.reader(io.StringIO(result.stdout))
                  if len(row) > 1 and row[0].lower() == 'sldworks.exe')


async def verify(args):
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {'scope': 'two new stdio MCP connections; not desktop tool-cache reload',
                'sessions': []}
    for index in range(2):
        before = pids()
        transport = StdioTransport(str(ROOT / '.venv/Scripts/python.exe'),
            [str(ROOT / 'src/utils/start_sw2020_stable.py'), '--real', '--year', '2020'],
            cwd=str(ROOT), log_file=output.with_suffix(f'.{index}.server.log'))
        async with Client(transport, timeout=180) as client:
            names = {tool.name for tool in await client.list_tools()}
            assert EXPECTED <= names, sorted(EXPECTED - names)
            assert before == pids(), 'Discovery changed SolidWorks processes'
            async def call(name, **arguments):
                data = (await client.call_tool(name, arguments)).data
                assert isinstance(data, dict), data
                return data
            check = await call('sw_simulation_check', load_addin=False)
            assert check['status'] == 'success' and check['simulation_api_available'], check
            assert check['document_path'].lower() == args.document.lower(), check
            assert not check['document_dirty'], 'Keep unsaved changes intact'
            common = dict(expected_document=args.document, study=args.study)
            state = await call('sw_simulation_general_step', **common, operation='state')
            assert state['status'] == 'success', state
            results = await call('sw_simulation_general_step', **common, operation='results')
            assert results['status'] == 'success', results
            assert abs(results['max_displacement_mm'] - args.expected_ures) <= 1e-7, results
            invalid = await call('sw_simulation_run_plan', plan={})
            assert invalid['status'] == 'error', invalid
            after = await call('sw_simulation_check', load_addin=False)
            assert after['document_path'] == check['document_path']
            assert after['document_dirty'] == check['document_dirty']
            assert before == pids()
            evidence['sessions'].append(dict(tool_count=len(names),
                simulation_tools=sorted(EXPECTED), discovery_preserved_processes=True,
                check=check, state=state, results=results, invalid_plan=invalid,
                saved_document_preserved=True))
            output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'success', 'connections': len(evidence['sessions']),
                      'tool_count': len(names), 'simulation_tool_count': len(EXPECTED),
                      'max_displacement_mm': results['max_displacement_mm'],
                      'output': str(output)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--document', required=True)
    parser.add_argument('--study', required=True)
    parser.add_argument('--expected-ures', required=True, type=float)
    parser.add_argument('--output', required=True)
    asyncio.run(verify(parser.parse_args()))
