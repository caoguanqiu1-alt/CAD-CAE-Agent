"""Phase 1 Simulation tools; existing MCP server and serial COM gate only.

Build simulation/build.ps1 once. No COM, compilation, or process launch at import.
"""
import json
import os
import subprocess
from pathlib import Path
from .sw2020_workflow import event, real_adapter, methods

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / 'local_state' / 'simulation' / 'bin' / 'SimulationBridge.exe'
INSTALL = Path(os.environ.get('SW2020_INSTALL_DIR', r'D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS'))


def invoke(operation: str, **parameters) -> dict:
    """Caller MUST hold SerialTimingMiddleware's existing COM lock.

    No timeout/kill/retry: a COM mutation may still execute after client timeout.
    Synchronous wait keeps the lock held until the child actually exits.
    """
    missing = [str(BRIDGE.parent / ('SolidWorks.Interop.' + name + '.dll'))
               for name in ('sldworks', 'swconst', 'cosworks')
               if not (BRIDGE.parent / ('SolidWorks.Interop.' + name + '.dll')).is_file()]
    if missing or not BRIDGE.is_file():
        return {'status': 'error', 'error_code': 'INTEROP_MISSING' if missing else 'BRIDGE_NOT_BUILT',
                'missing': missing, 'message': 'Run simulation/build.ps1 against the SW2020 installation.'}
    payload = {'operation': operation, 'install_dir': str(INSTALL), **parameters}
    event({'component': 'simulation', 'phase': 'bridge_start', 'request': payload})
    result = subprocess.run([str(BRIDGE)], input=json.dumps(payload), capture_output=True,
                            encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
    log = ROOT / 'local_state' / 'simulation' / 'api.jsonl'
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'operation': operation, 'request': payload,
                                'returncode': result.returncode, 'api_trace': result.stderr},
                               ensure_ascii=False) + '\n')
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError):
        data = {'status': 'unknown', 'error_code': 'BRIDGE_PROTOCOL_ERROR',
                'message': result.stderr, 'requires_inspection': True}
    event({'component': 'simulation', 'phase': 'bridge_end', 'result': data})
    return data


def register_simulation(server):
    def pid():
        adapter = real_adapter(server)
        app = getattr(adapter, 'swApp', None)
        return {} if app is None else {'expected_pid': methods(app, 'GetProcessID').GetProcessID()}

    @server.mcp.tool()
    async def sw_simulation_make_pin(expected_document: str, sketch_face: str,
                                     center_mm: list[float], radius_mm: float,
                                     length_mm: float, name: str) -> dict:
        """Add one separate coaxial pin solid to an active saved part copy.

        sketch_face is a negative-global-Y planar face persistent ID.
        The global center is in millimeters, and extrusion goes in +Y.
        The bridge verifies a new body, its radius, axis and location.
        This is a bounded helper for the demonstrated two-hole link; never
        retry an unknown mutation without inspecting actual body count.
        """
        if not isinstance(sketch_face, str) or not sketch_face.startswith('face_') or len(center_mm) != 3 or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in center_mm
        ) or not 0 < radius_mm < 100 or not 0 < length_mm < 100 or not name or len(name) > 50:
            return {'status': 'error', 'error_code': 'INVALID_PIN_PARAMETERS'}
        return invoke('phase3_make_pin', expected_document=expected_document,
                      sketch_face=sketch_face, center_mm=center_mm,
                      radius_mm=radius_mm, length_mm=length_mm, name=name,
                      **pid())

    @server.mcp.tool()
    async def sw_simulation_run_plan(plan: dict) -> dict:
        """Execute a validated static CAE plan on an already active, saved part copy.

        Required plan fields: expected_document, study, material={library,name},
        fixture_face, loads=[{face,force_N:[Fx,Fy,Fz]}], mesh_sizes_mm
        (strictly decreasing, 3-6 entries), archive_directory (new), plot_bmp
        (new). Optional: contacts=[{link_face,pin_face}], axial_roller_faces
        (exactly two), guide_face, displacement_tolerance_percent, plot_title.
        The workflow resolves persistent IDs before mutation, creates a new
        static study, assigns material, fixtures and vector loads, adds any pin
        contacts, runs every mesh, archives native CWR results, checks both
        displacement and peak-stress changes, creates URES plot and saves.
        A failed/unknown mutation stops the plan; inspect before retrying.
        """
        from .simulation_plan import run_simulation_plan
        return run_simulation_plan(plan, lambda operation, **kwargs: invoke(operation, **kwargs, **pid()))

    @server.mcp.tool()
    async def sw_simulation_general_step(expected_document: str, study: str, operation: str, parameters: dict | None = None) -> dict:
        """General static setup on an active, saved SW2020 part copy.

        Operations: state; materials (library,material); forces with loads=[{face: persistent ID,
        force_N: [global Fx,Fy,Fz]}, ...]; contacts with
        pairs=[{link_face: persistent ID,pin_face: persistent ID}, ...];
        rollers (faces=[two planar face IDs]) for axial retainers;
        guide (face=planar pin cap ID) constrains global Z while allowing X;
        mesh (element_size_mm); run (results_folder,soft_spring);
        results (optional fixed_face).
        Each load is total Newtons on one face. Contact pairs are cylindrical
        faces on separate solid bodies, with no-penetration contact.
        Forces require exactly one prior fixed fixture and no prior loads;
        contacts require no existing contact sets. Inspect state after an
        unknown result. Multibody mesh/run/results use this tool; single-body
        mesh/run/results remain sw_simulation_static_step.
        """
        if operation not in {'state', 'materials', 'forces', 'rollers', 'guide', 'contacts', 'mesh', 'run', 'results'}:
            return {'status': 'error', 'error_code': 'INVALID_OPERATION'}
        parameters = parameters or {}
        if set(parameters) & {'operation', 'expected_document', 'study', 'expected_pid', 'install_dir'}:
            return {'status': 'error', 'error_code': 'RESERVED_PARAMETER'}
        if operation == 'forces':
            loads = parameters.get('loads')
            if not isinstance(loads, list) or not 1 <= len(loads) <= 16 or any(
                not isinstance(row, dict) or not isinstance(row.get('face'), str)
                or not row['face'].startswith('face_')
                or not isinstance(row.get('force_N'), list)
                or len(row['force_N']) != 3
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in row['force_N'])
                for row in loads
            ):
                return {'status': 'error', 'error_code': 'INVALID_LOADS'}
        if operation == 'contacts':
            pairs = parameters.get('pairs')
            if not isinstance(pairs, list) or not 1 <= len(pairs) <= 8 or any(
                not isinstance(row, dict) or any(not isinstance(row.get(key), str)
                or not row[key].startswith('face_') for key in ('link_face', 'pin_face'))
                for row in pairs
            ):
                return {'status': 'error', 'error_code': 'INVALID_CONTACT_PAIRS'}
        return invoke('phase3_' + operation, expected_document=expected_document,
                      study=study, **parameters, **pid())

    @server.mcp.tool()
    async def sw_simulation_static_step(expected_document: str, study: str, operation: str, parameters: dict | None = None) -> dict:
        """Run ONE guarded Phase 2 step on a saved single-solid static-study copy.

        Operations: state, material (library,material), fixture (face persistent ID),
        force (face,magnitude_N; +global X only), mesh (element_size_mm),
        run (results_folder), results (optional fixed_face), plot (output_bmp).
        Material is explicitly linear elastic. Fixture/force reject duplicate setup.
        No retries, save, or implicit document switching. Inspect state after failure.
        Use sw_simulation_general_step for an arbitrary global 3D force vector
        and multiple simultaneous face loads. The legacy force step remains
        a one-load +X shortcut.
        """
        if operation not in {'state','material','fixture','force','mesh','run','results','plot'}:
            return {'status':'error','error_code':'INVALID_OPERATION'}
        parameters = parameters or {}
        if set(parameters) & {'operation','expected_document','study','expected_pid','install_dir'}:
            return {'status':'error','error_code':'RESERVED_PARAMETER'}
        return invoke('phase2_'+operation, expected_document=expected_document, study=study,
                      **parameters, **pid())

    @server.mcp.tool()
    async def sw_simulation_check(load_addin: bool = True) -> dict:
        """Diagnose SW2020/Simulation; optionally load the installed add-in.

        Attaches to a running instance only. License status is unknown unless
        supported by evidence; installed DLLs alone do not establish a license.
        """
        return invoke('check', load_addin=load_addin, **pid())

    @server.mcp.tool()
    async def sw_simulation_inspect_geometry(expected_document: str) -> dict:
        """Read solid-body faces, edges, vertices and round-trip persistent IDs.

        Requires exact absolute active-part path. mm/mm2. center_mm is explicitly
        an approximate bounding-box midpoint, not a surface centroid. Does not save.
        """
        return invoke('inspect_geometry', expected_document=expected_document, **pid())

    @server.mcp.tool()
    async def sw_simulation_resolve_geometry(expected_document: str, ids: list[str], highlight: bool = False) -> dict:
        """Resolve saved persistent face/edge/vertex IDs after reopening a Part.

        Optional highlight changes only current selection (clears old selection).
        IDs must come from inspection of this document. No coordinate selection.
        """
        if not ids or len(ids) > 1000:
            return {'status': 'error', 'error_code': 'INVALID_IDS'}
        return invoke('resolve_geometry', expected_document=expected_document,
                      ids=ids, highlight=highlight, **pid())

    @server.mcp.tool()
    async def sw_simulation_create_static_study(expected_document: str, name: str = 'Static_API_Test') -> dict:
        """Create/read back a SW2020 static study on an explicitly named clean Part.

        Reuses an existing static study of the same name; never duplicates it.
        Requires a saved test copy. Does not save, mesh, apply loads or solve.
        On unknown/partial result, inspect the study before another write.
        """
        if not name.strip() or len(name) > 80:
            return {'status': 'error', 'error_code': 'INVALID_STUDY_NAME'}
        return invoke('create_static_study', expected_document=expected_document,
                      name=name, load_addin=True, **pid())
