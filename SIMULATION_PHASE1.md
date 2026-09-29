# SOLIDWORKS Simulation 2020 — Phase 1

Extends the existing Python/FastMCP stable entrypoint. No separate MCP server,
mock Simulation implementation, solver, or geometry changes are introduced.

## Architecture

`start_sw2020_stable.py` → `register_simulation` → existing
`SerialTimingMiddleware` / `local_state/sw2020/com.lock` → short-lived x64 STA
`SimulationBridge.exe` → running `SldWorks.Application.28` →
`GetAddInObject("SldWorks.Simulation")` → `ICwAddincallback.CosmosWorks` →
`ICosmosWorks.ActiveDoc` → `ICWModelDoc.StudyManager`.

The old modeling adapter remains Python/pywin32. Simulation uses strongly typed
C# .NET Framework Interop. Its three assembly references come from the local
SW2020 installation (28.5.0.78). No NuGet packages or newer API assemblies.
Initialization and tools/list do not attach to COM. Simulation calls bypass only
the middleware's automatic modeling-adapter connection, retaining its serial lock.
The bridge never creates or quits SOLIDWORKS. It checks revision 28 and, when the
existing adapter is connected, verifies the process ID matches that adapter.

## Build and use

```powershell
& .\simulation\build.ps1
# Alternate installation: set SW2020_INSTALL_DIR for the server AND pass
# -InstallDir to build.ps1, using a SOLIDWORKS 2020 installation only.
& .\.venv\Scripts\python.exe .\src\utils\start_sw2020_stable.py --real --year 2020
```

The active Codex configuration already uses this entrypoint. Existing running
server processes do not hot-reload Python; reconnect the SolidWorks MCP (or restart
the Codex app normally) to expose the new tool schemas in that client. Validation
used a fresh stdio client against this SAME entrypoint, not a new server project.

| Tool | Operation |
| --- | --- |
| `sw_simulation_check(load_addin=True)` | Attach-only environment check; attempts to load installed cosworks.dll if needed |
| `sw_simulation_inspect_geometry(expected_document)` | All solid-body faces/edges/vertices, engineering units, serialized persistent references with resolution check |
| `sw_simulation_resolve_geometry(expected_document, ids, highlight=False)` | Resolve saved IDs; optionally replace the selection with those entities and check selected count |
| `sw_simulation_create_static_study(expected_document, name="Static_API_Test")` | Create static study using CreateNewStudy3; reuse matching existing study; activate and read back |

`expected_document` is the exact absolute active Part path. Create study on a clean,
saved test copy. No implicit save; the user controls saving. Phase 1 only supports
linear static study creation, not materials, loads, meshing or results.

## Identity and units

Persistent IDs are `<kind>_<base64 GetPersistReference3 bytes>`. They are scoped to
the inspected document/configuration. F001/E001/V001 labels are convenient local
aliases; never use enumeration order as persistent identity. Save the full JSON.
Topology edits, replacing bodies, Save As and other file transformations can
invalidate references; rerun inspection if GetObjectByPersistReference3 fails.
No coordinate-based SelectByID2 is used.

Units: lengths/radii m→mm, areas m²→mm²; directions are unitless.
`center_mm` is the approximate face bounding-box midpoint, explicitly NOT its
area centroid and potentially outside a trimmed face. Cylindrical radius/axis are
analytic surface properties. Surface type alone does not classify a hole versus
an exterior fillet. Plane normals use FaceInSurfaceSense to orient outward.

## Diagnostics and recovery

Missing interop/build, SW not running, wrong version/instance, no active document,
non-part, wrong document, sketch editing, dirty document, unavailable add-in/API,
invalid persistent reference, and typed study error values are distinct.
COM exceptions retain stage, HRESULT and message. Add-in load/API availability
does not prove a solver license: `simulation_license_status` remains
`not_independently_verified`. No invented license diagnosis is returned.
Phase 2 must add a license-specific diagnosis where the actual API supplies evidence.

Bridge requests and outcomes are in `local_state/sw2020/timings.jsonl`; detailed
API traces are in `local_state/simulation/api.jsonl`. Protocol stdout is JSON only.
Mutation exceptions return `status=unknown` and require inspection. A bridge
protocol error also returns unknown. Never kill/retry a hung COM mutation: wait,
then inspect actual document/study state before deciding on a subsequent write.
The synchronous subprocess wait retains the existing lock until the child exits.
COM RCWs are released in reverse order, without calling ExitApp or UnloadAddIn.

## Real integration test

Use an already-open test copy, never an unsaved original:

```powershell
& .\.venv\Scripts\python.exe tests\simulation_phase1_live.py `
  --document 'C:\absolute\test-copy.SLDPRT' `
  --output 'C:\absolute\evidence.json'
```

This opt-in test checks tool discovery without business calls/new SW processes,
live Simulation diagnostics, inspection/resolution, study reuse, wrong-document
write rejection, malformed references, selection count, and the existing modeling
preflight. No mocked stress/displacement values or solver results.

2026-09-28 local validation also saved and closed ONLY the test copy, reopened it,
then resolved all 40 saved entity IDs and read back the sole Static_API_Test study.
Original source SHA-256 was unchanged. Study existence/activation was verified
through Simulation API, not by a screenshot of the Simulation tree. SaveBMP
captures the model viewport and does not establish UI-tree visibility/highlight.

Only normal loaded-environment behavior and documented guard cases were executed.
Missing installation/license/COM-fault branches were not reproduced by disrupting
the user's installation. No solve, mesh convergence, or engineering validity claim.
