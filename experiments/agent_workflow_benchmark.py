"""Reproducible offline controls: real MCP stdio, production plan handlers.

No LLM, COM, CAD modeling or FEA is invoked. Synthetic faults measure coverage,
not real-world failure probability or a causal effect of loading a Skill.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from solidworks_mcp.sw2020_plan import ModelingPlan, compile_plan, register_plan
from solidworks_mcp.sw2020_workflow import SerialTimingMiddleware
from solidworks_mcp.simulation_plan import run_simulation_plan


def node(index):
    return {"id": f"node_{index}", "operation": {
        "name": f"凸台{index}", "sketch_name": f"草图{index}", "plane": "Front",
        "kind": "boss", "depth": 10,
        "shapes": [{"kind": "rectangle", "x": index * 100, "width": 100, "height": 60}]}}


def plan(count=1):
    return {"schema_version": "sw2020-plan/1", "target_year": 2020,
            "units": "mm", "expected": {"volume_mm3": 60000 * count},
            "nodes": [node(i) for i in range(count)]}


def serve():
    from fastmcp import FastMCP
    server = SimpleNamespace(mcp=FastMCP("CAD-CAE offline benchmark"))

    async def forbidden_connection():
        raise AssertionError("This experiment must never connect to COM")

    server.mcp.add_middleware(SerialTimingMiddleware(forbidden_connection))
    register_plan(server, {})
    server.mcp.run(transport="stdio", show_banner=False)


def unpack(result):
    if is_error(result):
        raise AssertionError("Unexpected MCP error: " + str(result.content))
    structured = result.structured_content if hasattr(result, "structured_content") else result.structuredContent
    if structured is not None:
        return structured
    return json.loads(next(item.text for item in result.content if item.type == "text"))


def is_error(result):
    return result.is_error if hasattr(result, "is_error") else result.isError


def summary(values):
    ordered = sorted(values)
    return {"n": len(values), "median_ms": statistics.median(values),
            "p95_ms": ordered[math.ceil(len(ordered) * .95) - 1],
            "min_ms": min(values), "max_ms": max(values)}


async def timing_experiment(session, repetitions, warmups, count):
    batch = plan(count)
    singles = [{**plan(), "nodes": [copy.deepcopy(item)]} for item in batch["nodes"]]
    expected_groups = compile_plan(ModelingPlan.model_validate(batch))["groups"]

    async def individual():
        groups = []
        for source in singles:
            data = unpack(await session.call_tool("sw2020_validate_plan", {"plan": source}))
            groups.extend(data["groups"])
        return groups

    async def combined():
        data = unpack(await session.call_tool("sw2020_validate_plan", {"plan": batch}))
        return data["groups"]

    # Same independent nodes and compiled group payloads. There is no CAD execution.
    assert await individual() == await combined() == expected_groups
    for _ in range(warmups):
        await individual()
        await combined()
    rows = []
    for repetition in range(repetitions):
        row = {"repetition": repetition + 1,
               "order": "individual,batch" if repetition % 2 == 0 else "batch,individual"}
        order = [("individual_ms", individual), ("batch_ms", combined)]
        if repetition % 2:
            order.reverse()
        for key, action in order:
            start = time.perf_counter_ns()
            groups = await action()
            row[key] = (time.perf_counter_ns() - start) / 1e6
            assert groups == expected_groups
        start = time.perf_counter_ns()
        direct = compile_plan(ModelingPlan.model_validate(batch))
        row["direct_batch_ms"] = (time.perf_counter_ns() - start) / 1e6
        assert direct["groups"] == expected_groups
        rows.append(row)
    individual_stats = summary([r["individual_ms"] for r in rows])
    batch_stats = summary([r["batch_ms"] for r in rows])
    direct_stats = summary([r["direct_batch_ms"] for r in rows])
    return {"nodes": count, "warmup_pairs": warmups, "repetitions": repetitions,
            "compiled_groups_equal_every_time": True,
            "individual_calls_per_task": count, "batch_calls_per_task": 1,
            "individual": individual_stats, "batch": batch_stats, "direct_batch": direct_stats,
            "call_reduction_percent": (1 - 1 / count) * 100,
            "median_latency_reduction_percent": (1 - batch_stats["median_ms"] / individual_stats["median_ms"]) * 100,
            "median_speed_ratio": individual_stats["median_ms"] / batch_stats["median_ms"],
            "input_plan_bytes_utf8": {
                "individual_total": sum(len(json.dumps(p, ensure_ascii=False).encode()) for p in singles),
                "batch": len(json.dumps(batch, ensure_ascii=False).encode())},
            "samples": rows}


async def validation_experiment(session):
    faults = []
    for name, key, value in [
        ("wrong_schema", "schema_version", "sw2020-plan/99"),
        ("wrong_year", "target_year", 2026), ("wrong_units", "units", "m"),
        ("unknown_field", "script", "unrecognized"), ("empty_nodes", "nodes", []),
    ]:
        source = plan(); source[key] = value
        faults.append((name, source))
    source = plan(); del source["expected"]
    faults.append(("missing_expected_metrics", source))
    source = plan(2); source["nodes"][1]["id"] = source["nodes"][0]["id"]
    faults.append(("duplicate_node_id", source))
    source = plan(2); source["nodes"][1]["operation"]["name"] = "凸台0"
    faults.append(("duplicate_feature_name", source))
    source = plan(); source["nodes"][0]["depends_on"] = ["missing"]
    faults.append(("missing_dependency", source))
    source = plan(2)
    source["nodes"][0]["depends_on"] = ["node_1"]
    source["nodes"][1]["depends_on"] = ["node_0"]
    faults.append(("dependency_cycle", source))
    source = plan(); source["nodes"][0]["operation"]["depth"] = 0
    faults.append(("zero_depth", source))
    source = plan(); source["nodes"][0]["operation"]["shapes"][0]["width"] = -1
    faults.append(("negative_width", source))
    reordered = plan(2)
    reordered["nodes"][1]["depends_on"] = ["node_0"]
    reordered["nodes"].reverse()
    cases = [(name, source, True) for name, source in faults]
    cases.extend([("valid_single", plan(), False), ("valid_unsorted_dependency", reordered, False)])
    rows = []
    for name, source, invalid in cases:
        result = await session.call_tool("sw2020_validate_plan", {"plan": source})
        rejected = bool(is_error(result))
        assert rejected == invalid, name
        data = None if rejected else unpack(result)
        if name == "valid_unsorted_dependency":
            assert data["node_order"] == ["node_0", "node_1"]
        rows.append({"case": name, "input": source, "injected_fault": invalid,
                     "unchecked_forwarder_rejected": False, "schema_rejected": rejected,
                     "compiled_node_order": None if rejected else data["node_order"]})
    limitations = []
    for name in ["unavailable_plane", "inconsistent_analytic_expectation"]:
        source = plan()
        if name == "unavailable_plane":
            source["nodes"][0]["operation"]["plane"] = "NonexistentPlane"
        else:
            source["expected"]["volume_mm3"] = 123
        data = unpack(await session.call_tool("sw2020_validate_plan", {"plan": source}))
        assert data["status"] == "valid"
        limitations.append({"case": name, "input": source, "schema_accepted": True,
                            "requires": "Live plane resolution or independent geometry/expectation checking"})
    return {"invalid_cases": len(faults), "valid_controls": 2,
            "unchecked_forwarder_faults_rejected": 0,
            "schema_faults_rejected": sum(r["schema_rejected"] for r in rows if r["injected_fault"]),
            "schema_valid_controls_accepted": sum(not r["schema_rejected"] for r in rows if not r["injected_fault"]),
            "cases": rows, "known_scope_limits": limitations}


async def result_experiment(session):
    reference = {"revision": "28.5.0", "document": "synthetic-part", "path": "", "dirty": True,
                 "metrics": {"solid_bodies": 1, "volume_mm3": 60000, "area_mm2": 15200,
                             "center_mm": [0, 0, 5], "faces": 6, "edges": 12, "vertices": 8},
                 "feature_types": {"凸台0": "Extrusion"}}
    cases = []
    for key, value in [("solid_bodies", 2), ("volume_mm3", 54000), ("area_mm2", 14000),
                       ("center_mm", [0, 0, 4.5]), ("faces", 7), ("edges", 14), ("vertices", 10)]:
        candidate = copy.deepcopy(reference); candidate["metrics"][key] = value
        cases.append((key, candidate, True))
    candidate = copy.deepcopy(reference); candidate["feature_types"] = {"凸台0": "Imported"}
    cases.append(("feature_type", candidate, True))
    cases.append(("identical_control", copy.deepcopy(reference), False))
    candidate = copy.deepcopy(reference)
    candidate["metrics"].update(volume_mm3=60000.005, area_mm2=15200.005, center_mm=[.0005, 0, 5])
    cases.append(("within_tolerance_control", candidate, False))
    rows = []
    for name, candidate, faulty in cases:
        # The injected upstream envelope reports success even for incorrect metrics.
        upstream = {"status": "success", "snapshot": candidate}
        status_only_accepted = upstream["status"] == "success"
        data = unpack(await session.call_tool("sw2020_compare_results", {
            "reference": reference, "candidate": upstream["snapshot"]}))
        matched = data["status"] == "matched"
        assert matched != faulty, name
        rows.append({"case": name, "injected_fault": faulty, "upstream_status": "success",
                     "candidate": candidate, "status_only_accepted": status_only_accepted,
                     "compared_accepted": matched, "comparison": data})
    other_document = copy.deepcopy(reference)
    other_document["document"] = "another-synthetic-part"
    scope_limit = unpack(await session.call_tool("sw2020_compare_results", {
        "reference": reference, "candidate": other_document}))
    assert scope_limit["status"] == "matched" and scope_limit["live_verification"] is False
    return {"reference": reference, "fault_cases": 8, "valid_controls": 2,
            "status_only_faults_detected": sum(not r["status_only_accepted"] for r in rows if r["injected_fault"]),
            "comparison_faults_detected": sum(not r["compared_accepted"] for r in rows if r["injected_fault"]),
            "comparison_valid_controls_accepted": sum(r["compared_accepted"] for r in rows if not r["injected_fault"]),
            "cases": rows, "known_scope_limits": [{"case": "same_metrics_different_document_label",
                "status": scope_limit["status"], "live_verification": False,
                "requires": "Caller must guard document identity and obtain fresh live snapshots"}]}


def stop_experiment():
    # These files are input-validation fixtures, not actual SolidWorks documents.
    rows = []
    with tempfile.TemporaryDirectory(prefix="cad_cae_bench_") as temporary:
        root = Path(temporary)
        document = root / "fixture.SLDPRT"; document.touch()
        library = root / "fixture.sldmat"; library.touch()
        source = {"expected_document": str(document), "study": "OfflineFixture",
                  "material": {"library": str(library), "name": "fixture"},
                  "fixture_face": "face_" + "a" * 32,
                  "loads": [{"face": "face_" + "b" * 32, "force_N": [1000, 0, 0]}],
                  "mesh_sizes_mm": [5, 4, 3], "archive_directory": str(root / "archive"),
                  "plot_bmp": str(root / "plot.bmp")}
        for scenario in ["dirty_document", "unknown_creation"]:
            calls = []
            def invoke(operation, **arguments):
                calls.append(operation)
                responses = {
                    "check": {"status": "success", "document_path": str(document),
                              "document_dirty": scenario == "dirty_document"},
                    "inspect_geometry": {"status": "success", "solid_bodies": 1},
                    "resolve_geometry": {"status": "success"},
                    "create_static_study": {"status": "unknown", "error_code": "INJECTED_AMBIGUOUS"}}
                return responses[operation]
            result = run_simulation_plan(source, invoke)
            expected_calls = ["check"] if scenario == "dirty_document" else [
                "check", "inspect_geometry", "resolve_geometry", "create_static_study"]
            assert calls == expected_calls
            assert not (root / "archive").exists()
            rows.append({"scenario": scenario, "status": result["status"],
                         "error_code": result["error_code"], "bridge_calls": calls,
                         "study_creation_calls": calls.count("create_static_study"),
                         "automatic_retries": 0, "archive_created": False})
    return rows


async def run(args):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    parameters = StdioServerParameters(command=sys.executable,
        args=[str(Path(__file__).resolve()), "--serve"], env=env, cwd=str(ROOT))
    start = time.perf_counter_ns()
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            cold_start_ms = (time.perf_counter_ns() - start) / 1e6
            discovered = await session.list_tools()
            assert {t.name for t in discovered.tools} == {
                "sw2020_validate_plan", "sw2020_compare_results", "sw2020_capture_result", "sw2020_execute_plan"}
            timing = await timing_experiment(session, args.repetitions, args.warmups, args.nodes)
            validation = await validation_experiment(session)
            results = await result_experiment(session)
    source_files = ["src/solidworks_mcp/sw2020_plan.py", "src/solidworks_mcp/sw2020_workflow.py",
                    "src/solidworks_mcp/simulation_plan.py", "experiments/agent_workflow_benchmark.py"]
    record = {"experiment": "cad-cae-offline-controls/1", "run_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Real MCP stdio and production pure handlers; synthetic faults; no LLM, COM, CAD or FEA",
              "environment": {"os": platform.system(), "os_release": platform.release(),
                  "python": platform.python_version(), "packages": {
                      p: importlib.metadata.version(p) for p in ["fastmcp", "mcp", "pydantic"]}},
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "source_sha256_normalization": "UTF-8 source bytes with CRLF normalized to LF",
              "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in source_files},
              "cold_start_initialize_ms": cold_start_ms,
              "timing": timing, "input_validation": validation, "result_validation": results,
              "stop_conditions": stop_experiment()}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "timings.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(timing["samples"][0]))
        writer.writeheader(); writer.writerows(timing["samples"])
    print(json.dumps({"timing": {k: v for k, v in timing.items() if k != "samples"},
                      "input_faults_rejected": validation["schema_faults_rejected"],
                      "result_faults_detected": results["comparison_faults_detected"],
                      "stop_conditions": record["stop_conditions"]}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--repetitions", type=int, default=40)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--nodes", type=int, default=12)
    parser.add_argument("--output", default="experiments/results/2026-09-30")
    args = parser.parse_args()
    if args.serve:
        serve()
    else:
        if args.repetitions < 10 or args.warmups < 1 or not 2 <= args.nodes <= 30:
            parser.error("Use repetitions >= 10, warmups >= 1, nodes in [2, 30]")
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
