# Real SW2020 stable MCP workflow

Local integration on branch `sw2020-compat`. The original host launcher and upstream tools are retained.

## Launch

Use `.venv\Scripts\python.exe src\utils\start_sw2020_stable.py --real --year 2020` with repository cwd. Stdio is JSON-RPC only; logging is stderr or local JSONL. The launcher refuses missing real mode and non-2020 years.

The user's Codex `[mcp_servers.solidworks]` entry now selects this launcher. `codex mcp get solidworks` and `codex mcp list` confirm the saved registration. Existing host processes must reconnect to load changed code; changing TOML alone does not hot-reload a running server.

## Stable workflow tools

- `sw2020_preflight`: live COM revision 28.x, document identity, sketch mode, graphics/AddToDB state; optional up to 30 exact feature lookups. No full topology traversal.
- `sw2020_build_batch`: 1–30 groups of rectangle/circle/closed polygon sketches plus boss/cut. Multi-hole profiles are supported. Exact plane resolution, whole-recipe validation, named document guard, temporary graphics suppression with restoration, durable request IDs and per-group timing.
- `sw2020_verify_save`: rebuild, required features, body count, optional analytic volume expectation; then save a `.SLDPRT` without deleting/closing another document. Solid-body boxes are approximate; vertex-only extents are not used.

The stable launcher disables the problematic upstream pool and intelligent VBA routing for this workflow, rather than claiming to repair their general upstream implementations. Each tool is serialized; a cooperating-process file lock rejects concurrent stable-server access. Old launchers/manual edits do not honor that lock. Complex features still use upstream tools and may retain their original latency.

## Failure semantics

- `success`: this batch completed; final drawing compliance still requires verification.
- `partial`: stop and inspect the named in-progress feature/sketch. Later groups were not run. No transaction rollback is claimed.
- `started` after process loss/timeout: outcome uncertain; inspect before any modification.
- A repeated request ID with identical arguments returns historical status without re-execution; it is not a fresh model verification. Different arguments with the same ID are rejected. Never change ID merely to retry an uncertain mutation.
- Restore graphics/AddToDB/display state in `finally`; cleanup failures are returned as partial status. Hung native COM cannot safely be force-cancelled, so the system does not launch another mutating session to work around it.

Logs: `local_state/sw2020/timings.jsonl` (tool start/return/exception and elapsed wall time), `local_state/sw2020/requests/*.json` (durable batch results). `returned` means returned, not necessarily success. These runtime records are ignored by git. Preserve request journals for replay protection.

## Actual acceptance, 2026-09-09

Real SW revision 28.5.0, MCP SDK stdio client, no GUI input automation and no mock adapter:

- New 100×60×10 mm boss plus four Ø6 through holes at X±35/Y±20.
- Batch client round trip 5.077 s; batch internal 4.259 s. Startup observed 5.35–6.36 s; lightweight preflight about 0.17–0.29 s before optional feature checks. These are observations, not speed guarantees or an old/new benchmark.
- Expected volume `60000 - 4*pi*3^2*10` = 58869.0266447 mm³, matched COM result; one solid; body box [-50,-30,0] to [50,30,10] mm. Saved with dirty=false.
- Repeated success ID performed no additional modeling. Wrong plane rejected all groups before modification. Wrong document rejected. Actual non-intersecting cut returned partial and did not run the following boss; replay did not repeat the failed cut. Graphics and sketch mode restored. Only that test's leftover sketch was deleted, then volume verified and test file saved again.
- A second process holding the shared lock caused an explicit SW2020_BUSY result.

Acceptance scripts/evidence are in the user's project `work/verify_stable_mcp.py`, `work/verify_stable_failure.py`, `outputs/stable-mcp-acceptance.json`, `outputs/stable-failure-acceptance.json`. Workflow instructions for the coding agent are in that project's `AGENTS.md`.

This is executable MCP functionality plus project instructions, not an installed Skill. Adding a cross-project Skill later would only route usage; it would not replace this implementation.

## Structured plans and metric comparison (2026-09-14)

Four additional tools are registered by the same stable launcher:

- `sw2020_validate_plan`: pure, COM-free validation and stable topological compilation of `sw2020-plan/1`. Explicit SW2020/mm contract, Chinese feature names, unique node/name guards and dependency checking. Unsupported operations/fields are rejected.
- `sw2020_execute_plan`: uses the existing batch and verify/save handlers on an explicitly named new unsaved empty Part. Compares independent expected volume (required), optional area/centroid/counts, then saves to a fresh absolute SLDPRT path. Never closes a document. Uses separate durable `local_state/sw2020/plan_requests` journals; repeated IDs return history without writing again. No auto rollback.
- `sw2020_capture_result`: read-only volume, area, center of mass, solid/face/edge/vertex counts, and optional named feature types; records path/revision/dirty state. Does not rebuild/save.
- `sw2020_compare_results`: pure comparison of supplied snapshots with explicit absolute tolerances and per-metric differences. Count/metric agreement is not exact BREP equivalence; snapshots are not automatically current.

The original implementation borrows the architectural idea, not SolidPilot code. It adds no new dependencies. Numerical recipe values do not create linked dimensions or equations in SolidWorks. Existing-model edits, other features and linked design parameters retain their existing API workflows. See `examples/sw2020/four_hole_plan.json` and the actual MCP schemas.

Plan execution marks `disk_reopen_verified=false`: a caller must capture a snapshot, close only its own clean saved output, reopen, capture again and compare for disk verification. A failed expectation leaves partial geometry unsaved for inspection. Do not infer rollback or issue a new request ID to retry.

The installed `solidworks-2020-modeling` Skill now routes these tools through `references/structured-plan.md`. Restart/reconnect existing MCP processes to load code changes; initialization/listing and the two pure tools do not activate COM.

Offline regression command (repository cwd):

```powershell
& .\.venv\Scripts\python.exe -c "import sys,runpy; sys.path.insert(0,'src'); runpy.run_path('tests/test_sw2020_plan_contract.py',run_name='__main__')"
```

The earlier modeling acceptance client was a local-only `verify_plan_mcp.py` with `--phase discovery` or `--phase live`; it is not shipped in this repository. That live run created independent test parts and included an intentional 9 mm / 10 mm expectation mismatch. Current portable offline checks are in `tests/test_sw2020_plan_contract.py`; the Simulation reconnection/readback check is in `tests/simulation_reconnect_live.py`. These scopes are different and must not be presented as a fresh modeling acceptance run.
