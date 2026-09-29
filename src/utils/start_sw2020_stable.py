"""Production stdio entrypoint for real SW2020. No simulation or stdout logging."""
import argparse
import asyncio
import runpy
from pathlib import Path
from solidworks_mcp.sw2020_workflow import register_workflow, SerialTimingMiddleware

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--real', action='store_true', required=True)
    parser.add_argument('--year', type=int, choices=[2020], required=True)
    args = parser.parse_args()
    args.security, args.log_level, args.port = 'minimal', 'INFO', 8000
    upstream = runpy.run_path(str(Path(__file__).with_name('start_local_server_claude.py')))
    config = upstream['_build_config'](args)
    # An interactive COM document has one mutable state. The upstream pool
    # factory returns the same adapter repeatedly; VBA routing can recurse.
    config.connection_pooling = config.enable_connection_pooling = False
    config.enable_intelligent_routing = config.enable_response_cache = False
    config.max_connections = 1
    # Upstream validation uses Dispatch as a registration probe, which can
    # launch SW. Check the requested version's registry entry without COM.
    import winreg
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, 'SldWorks.Application.28\\CLSID') as key:
        winreg.QueryValueEx(key, None)
    config.enable_windows_validation = False
    upstream['setup_logging'](config)
    server = upstream['SolidWorksMCPServer'](config)
    try:
        await server.setup()
        async def ensure_connected():
            if not server.state.is_connected:
                await server.adapter.connect()
                server.state.is_connected = True

        server.mcp.add_middleware(SerialTimingMiddleware(ensure_connected))
        workflow = register_workflow(server)
        from solidworks_mcp.sw2020_plan import register_plan
        register_plan(server, workflow)
        from solidworks_mcp.sw2020_details import register_details
        register_details(server)
        from solidworks_mcp.simulation import register_simulation
        register_simulation(server)
        # start() eagerly connects upstream. Registration is already complete;
        # serve stdio directly and defer real SW2020 connection to tools/call.
        from datetime import datetime
        server.state.startup_time = datetime.now().isoformat()
        await server._run_local_stdio()
    finally:
        if server.state.is_connected:
            await server.stop()

if __name__ == '__main__':
    asyncio.run(main())
