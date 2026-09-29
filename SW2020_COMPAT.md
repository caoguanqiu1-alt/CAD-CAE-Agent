# Local SolidWorks 2020 integration

Upstream: `https://github.com/andrewbartels1/SolidworksMCP-python`

Base: `00cf8174ae67aa4b5837749c94125255a44c85f2` (2026-09-06). The original `main` branch is preserved; local changes are on `sw2020-compat`.

## Runtime and launch

- Dedicated CPython 3.13.15 x64 from python.org. The installer SHA-256 was `edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403`; Windows Authenticode reported a valid Python Software Foundation signature.
- Interpreter installation: local Python 3.13 x64 (machine-specific path omitted).
- Repository: this checkout (machine-specific path omitted).
- Independent `.venv`, installed using `python -m venv .venv`, followed by `.venv\Scripts\python.exe -m pip install -e .`.
- Existing Python 3.12 and PATH were retained.
- Host command: `.venv\Scripts\python.exe` with absolute path to `src\utils\start_local_server_claude.py --real --year 2020`.
- Transport: standard stdio MCP. Startup/runtime logging is on stderr; initialization and `tools/list` completed successfully.
- Global Codex registration: `codex mcp add solidworks --env PYTHONUNBUFFERED=1 --env PYTHONIOENCODING=utf-8 -- <venv-python> <absolute-launcher> --real --year 2020`. The server's cwd is this repository; startup and tool timeouts are 120 seconds. Existing Codex config was backed up before the entry was added.
- Native host used for the successful modelling run: bundled Codex CLI 0.153.4. The separate PATH CLI 0.147.0 can manage the MCP registration but rejected the configured model as requiring a newer CLI.
- Installed protocol libraries: FastMCP 4.0.3, MCP SDK 2.2.0, pywin32 312. `pip check` passed.

## Changes and reasons

| File | Change | Reason |
|---|---|---|
| `adapters/sw_type_info.py` | Extend pywin32 type-library probing to major 28 | SW2020 registers TLB 28.0 (`1c.0`). Upstream only probed 30 and newer, leaving method/property resolution incomplete. |
| `adapters/solidworks/io.py` | Extend comtypes probing to major 28 | The typed COM geometry path must be able to load the installed SW2020 type library. |
| `adapters/factory.py` | Pass `solidworks_year` into the real adapter | The launcher parsed `--year`, but the adapter factory previously dropped it. |
| `adapters/pywin32_adapter.py` | Verify a running instance's revision against the requested year; launch with a versioned ProgID if needed | For `--year 2020`, require major 28 and use `SldWorks.Application.28` for activation, preventing silent attachment to another release. |
| `tools/file_management.py`, `adapters/connection_pool.py`, `adapters/circuit_breaker.py` | Expose and forward `rebuild_model` | The real backend already supported `ForceRebuild3(False)`, but the MCP surface and both wrappers did not expose/forward it. This is a missing integration operation, not a removed SW2020 API. |
| `adapters/solidworks/io.py` | Add real solid-body count and vertex bounds to `get_model_info` | Provides measurable COM readback via `GetBodies2`, `GetVertices`, and `GetPoint`, instead of trusting requested modelling dimensions. Vertex bounds are exact for polyhedra; they are not claimed as an analytic bounding box for curved geometry. |

No modelling API downgrade was required: `FeatureExtrusion3` worked in the real SW2020 test. `Select2`, `SketchManager`, `FeatureManager`, feature renaming and `ForceRebuild3` were exercised successfully. The existing `FeatureExtrusion2` fallback was not exercised or changed.

## Live verification

The server reports 133 MCP tools (132 upstream tools plus `rebuild_model`). This count is not a claim that all 133 tools were individually tested.

Native Codex MCP calls created a new Part, selected Front Plane, created a rectangle from (-50, -30) to (50, 30) mm, extruded it by 10 mm, and renamed the actual Chinese feature names to `Sketch1` and `Boss-Extrude1`. The rename implementation verifies the name after writing the COM property.

Real MCP readback confirmed one solid body, eight vertices, bounds [-50, -30, 0] to [50, 30, 10] mm, and volume approximately 60,000 mm³. Rebuild returned success. No GUI automation, mouse/keyboard simulation, pyautogui, direct modelling scripts outside MCP, mock adapter, or VBA execution was used.

The requested output target is `C:\Temp\Codex_SW2020_MCP_Test.SLDPRT`. Final save/readback evidence and native tool-call transcripts are retained in the parent Codex task's `outputs` directory.

## Validation scope

Python compilation, `git diff --check`, `pip check`, MCP initialization/tool enumeration, and the real SW2020 block workflow were used for validation. The repository's broad mock/unit test suite was not substituted for live SolidWorks verification.

An intermediate native `list_features` recheck was rejected when the automatic approval reviewer exhausted its quota. That rejection was reported and was not bypassed with GUI automation. Earlier native feature enumeration and rename readbacks were retained; subsequent attempts use the normal approval flow.
