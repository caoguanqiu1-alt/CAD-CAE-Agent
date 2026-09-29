"""Bounded SW2020 plan compiler and metric comparison, built on the local workflow.

Original implementation: no SolidPilot code or dependencies are incorporated.
Numeric recipe dimensions are millimetres, not live SolidWorks equations.
"""
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .sw2020_workflow import Group, STATE, methods, model_state, real_adapter, write_json


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class PlanNode(StrictModel):
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')
    depends_on: list[str] = Field(default_factory=list, max_length=30)
    operation: Group


class Metrics(StrictModel):
    solid_bodies: int = Field(ge=1, strict=True)
    volume_mm3: float = Field(gt=0)
    area_mm2: float = Field(gt=0)
    center_mm: tuple[float, float, float]
    faces: int = Field(ge=1, strict=True)
    edges: int = Field(ge=0, strict=True)
    vertices: int = Field(ge=0, strict=True)


class Expectations(StrictModel):
    solid_bodies: int = Field(default=1, ge=1, strict=True)
    volume_mm3: float = Field(gt=0)
    area_mm2: float | None = Field(default=None, gt=0)
    center_mm: tuple[float, float, float] | None = None
    faces: int | None = Field(default=None, ge=1, strict=True)
    edges: int | None = Field(default=None, ge=0, strict=True)
    vertices: int | None = Field(default=None, ge=0, strict=True)


class Tolerances(StrictModel):
    volume_mm3: float = Field(default=0.01, ge=0)
    area_mm2: float = Field(default=0.01, ge=0)
    center_mm: float = Field(default=0.001, ge=0)


class ModelingPlan(StrictModel):
    schema_version: Literal['sw2020-plan/1']
    target_year: Literal[2020]
    units: Literal['mm']
    nodes: list[PlanNode] = Field(min_length=1, max_length=30)
    expected: Expectations
    tolerances: Tolerances = Field(default_factory=Tolerances)

    @model_validator(mode='after')
    def graph_contract(self):
        ids = [node.id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError('Duplicate node IDs')
        names = [name.casefold() for node in self.nodes
                 for name in (node.operation.name, node.operation.sketch_name)]
        if len(set(names)) != len(names):
            raise ValueError('Feature/sketch names must be unique across the plan')
        for node in self.nodes:
            if len(set(node.depends_on)) != len(node.depends_on):
                raise ValueError('Duplicate dependency: '+node.id)
            if any(dep not in ids for dep in node.depends_on):
                raise ValueError('Unknown dependency: '+node.id)
            if node.operation.kind == 'boss' and node.operation.through_all:
                raise ValueError('Through-all bosses are not supported by plan/1')
        ordered_nodes(self.nodes)  # also rejects cycles before any COM call
        return self


class Snapshot(StrictModel):
    schema_version: Literal['sw2020-result/1'] = 'sw2020-result/1'
    target_year: Literal[2020] = 2020
    units: Literal['mm'] = 'mm'
    revision: str
    document: str
    path: str
    dirty: bool
    metrics: Metrics
    feature_types: dict[str, str] = Field(default_factory=dict)


def ordered_nodes(nodes):
    """Stable topological order; unresolved geometry references are never invented."""
    pending = list(nodes)
    result, done = [], set()
    while pending:
        ready = next((node for node in pending if set(node.depends_on) <= done), None)
        if ready is None:
            raise ValueError('Dependency cycle in plan')
        result.append(ready)
        done.add(ready.id)
        pending.remove(ready)
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def compile_plan(plan):
    nodes = ordered_nodes(plan.nodes)
    return {'schema_version': plan.schema_version, 'plan_sha256': digest(plan.model_dump()),
            'node_order': [node.id for node in nodes],
            'groups': [node.operation.model_dump() for node in nodes],
            'expected_features': [name for node in nodes
                                  for name in (node.operation.sketch_name, node.operation.name)]}


def compare_metrics(actual, expected, tolerances):
    checks = []
    for key, wanted in expected.model_dump(exclude_none=True).items():
        observed = getattr(actual, key)
        tolerance = getattr(tolerances, key, 0)
        delta = ([abs(a-b) for a, b in zip(observed, wanted)]
                 if key == 'center_mm' else abs(observed-wanted))
        matched = all(d <= tolerance for d in delta) if isinstance(delta, list) else delta <= tolerance
        checks.append({'metric': key, 'expected': wanted, 'actual': observed,
                       'absolute_difference': delta, 'tolerance': tolerance, 'matched': matched})
    return {'status': 'matched' if all(c['matched'] for c in checks) else 'mismatch',
            'checks': checks,
            'scope': 'Metric agreement only; topology counts are not a BREP equivalence proof, '
                     'and this does not verify constraints, material, drawing dimensions or design intent.'}


def capture_result(adapter, expected_document, feature_names=()):
    model, state = model_state(adapter, expected_document)
    if not expected_document or model is None or state['type'] != 1 or state['sketch_editing']:
        raise ValueError('Need an explicitly named active Part outside sketch edit mode')
    bodies = list(model.GetBodies2(0, False) or [])
    if not bodies:
        raise ValueError('No solid bodies to measure')
    mass = methods(model.Extension, 'CreateMassProperty').CreateMassProperty()
    if mass is None:
        raise RuntimeError('Mass property read failed')
    mass.UseSystemUnits = True
    counts = {'faces': 0, 'edges': 0, 'vertices': 0}
    for body in bodies:
        for key, method in [('faces', 'GetFaces'), ('edges', 'GetEdges'), ('vertices', 'GetVertices')]:
            methods(body, method)
            counts[key] += len(getattr(body, method)() or [])
    types = {}
    for name in feature_names:
        feature = model.FeatureByName(name)
        if feature is None:
            raise ValueError('Missing feature: '+name)
        methods(feature, 'GetTypeName2', 'IsSuppressed')
        if feature.IsSuppressed():
            raise ValueError('Suppressed feature: '+name)
        types[name] = feature.GetTypeName2()
    return Snapshot(revision=state['revision'], document=state['active_document'],
                    path=state['path'], dirty=state['dirty'], feature_types=types,
                    metrics=Metrics(solid_bodies=len(bodies), volume_mm3=mass.Volume*1e9,
                                    area_mm2=mass.SurfaceArea*1e6,
                                    center_mm=[v*1000 for v in mass.CenterOfMass], **counts))


def register_plan(server, workflow):
    @server.mcp.tool()
    async def sw2020_validate_plan(plan: ModelingPlan) -> dict:
        """Compile sw2020-plan/1 without COM. mm, ordered dependencies, Chinese names.

        Supports rectangle/circle/polygon sketches and boss/cut on existing reference
        planes only. Numerical recipe values are not linked CAD dimensions/equations.
        Expected volume is mandatory and must come from independent design evidence.
        """
        return {'status': 'valid', **compile_plan(plan),
                'capabilities': ['rectangle', 'circle', 'polygon', 'boss', 'cut'],
                'execution_requires': 'Named empty SW2020 Part, valid planes, fresh .SLDPRT output'}

    @server.mcp.tool()
    async def sw2020_capture_result(expected_document: str, feature_names: list[str] = []) -> dict:
        """Read SW2020 solid volume/area/centroid/topology counts and named features.

        No rebuild or save. Snapshot dirty flag identifies unsaved state. Use snapshots
        before/after disk reopening with compare_results for persistence verification.
        """
        if len(feature_names) > 60:
            raise ValueError('At most 60 named feature checks')
        return {'status': 'success', 'snapshot': capture_result(
            real_adapter(server), expected_document, feature_names).model_dump()}

    @server.mcp.tool()
    async def sw2020_compare_results(reference: Snapshot, candidate: Snapshot,
                                     tolerances: Tolerances = Tolerances()) -> dict:
        """Compare two supplied SW2020 snapshots without COM. Report every difference.

        Metric agreement is NOT exact geometry equivalence. Both snapshots may be
        historical; capture_result is needed for a fresh live observation.
        """
        result = compare_metrics(candidate.metrics, reference.metrics, tolerances)
        result['feature_types_match'] = reference.feature_types == candidate.feature_types
        if not result['feature_types_match']:
            result['status'] = 'mismatch'
        result['reference_document'] = reference.document
        result['candidate_document'] = candidate.document
        result['live_verification'] = False
        return result

    @server.mcp.tool()
    async def sw2020_execute_plan(request_id: str, expected_document: str,
                                  file_path: str, plan: ModelingPlan) -> dict:
        """Compile -> build on named empty Part -> compare expectations -> verify/save.

        Fresh absolute .SLDPRT path required. Reuses serial COM and durable request IDs.
        Same ID replays history, never rebuilds/re-saves; changed arguments rejected.
        Partial/started outcomes require inspection, never blind retry with a new ID.
        Does not close any document. Disk reopen verification is a separate operation.
        """
        if not request_id.strip() or len(request_id) > 100 or not expected_document.strip():
            raise ValueError('Explicit document and request ID (1..100 chars) required')
        compiled = compile_plan(plan)
        path = Path(file_path)
        if not path.is_absolute() or path.suffix.lower() != '.sldprt':
            raise ValueError('Use an absolute .SLDPRT path')
        payload = {'expected_document': expected_document, 'file_path': str(path.resolve()),
                   'plan': plan.model_dump()}
        fingerprint = digest(payload)
        journal = STATE/'plan_requests'/(hashlib.sha256(request_id.encode()).hexdigest()+'.json')
        if journal.exists():
            old = json.loads(journal.read_text(encoding='utf-8'))
            if old['digest'] != fingerprint:
                raise ValueError('request_id already used with different plan/document/output')
            return {**old, 'replayed': True, 'live_verification': False}
        if path.exists():
            raise ValueError('Output exists; choose a new path before building')
        adapter = real_adapter(server)
        model, state = model_state(adapter, expected_document)
        if model is None or state['type'] != 1 or state['sketch_editing'] or state['path']:
            raise ValueError('Plan/1 requires a new unsaved Part outside sketch edit mode')
        if list(model.GetBodies2(-1, False) or []):
            raise ValueError('Plan/1 requires an empty Part (no solid or surface bodies)')
        groups = [Group.model_validate(group) for group in compiled['groups']]
        # Check all planes and names before recording a started request or touching CAD.
        from .sw2020_workflow import plane_feature
        for group in groups:
            plane_feature(model, group.plane)
            for name in (group.name, group.sketch_name):
                if model.FeatureByName(name) is not None:
                    raise ValueError('Feature already exists: '+name)
        record = {'status': 'started', 'stage': 'build', 'request_id': request_id,
                  'digest': fingerprint, 'plan_sha256': compiled['plan_sha256'],
                  'document': expected_document, 'output': str(path), 'node_order': compiled['node_order']}
        write_json(journal, record)
        try:
            record['build'] = await workflow['build_batch']('plan:'+request_id, expected_document, groups)
            if record['build']['status'] != 'success':
                record['status'] = 'partial'
                return record
            record['stage'] = 'compare'
            write_json(journal, record)
            methods(model, 'ForceRebuild3')
            if not model.ForceRebuild3(False):
                raise RuntimeError('Rebuild failed before metric comparison')
            snapshot = capture_result(adapter, expected_document, compiled['expected_features'])
            record['snapshot'] = snapshot.model_dump()
            record['comparison'] = compare_metrics(snapshot.metrics, plan.expected, plan.tolerances)
            if record['comparison']['status'] != 'matched':
                record.update(status='partial', error='EXPECTATION_MISMATCH: model remains unsaved')
                return record
            record['stage'] = 'save'
            write_json(journal, record)
            # A path created during modeling is never overwritten.
            if path.exists():
                raise ValueError('Output appeared during execution; refusing overwrite')
            record['saved'] = await workflow['verify_save'](
                expected_document, str(path), compiled['expected_features'],
                plan.expected.solid_bodies, plan.expected.volume_mm3, plan.tolerances.volume_mm3)
            record['snapshot'] = capture_result(adapter, str(path), compiled['expected_features']).model_dump()
            record['comparison'] = compare_metrics(
                Metrics.model_validate(record['snapshot']['metrics']), plan.expected, plan.tolerances)
            if record['comparison']['status'] != 'matched':
                raise RuntimeError('Saved model metrics differ from expectations')
            record.update(status='success', stage='saved', disk_reopen_verified=False)
        except Exception as exc:
            record.update(status='partial', error=str(exc))
        finally:
            if record['status'] != 'success':
                record['recovery'] = 'Inspect current document and journals; partial geometry may remain. No automatic rollback or retry.'
            write_json(journal, record)
        return record

    return {'validate': sw2020_validate_plan, 'execute': sw2020_execute_plan,
            'capture': sw2020_capture_result, 'compare': sw2020_compare_results}
