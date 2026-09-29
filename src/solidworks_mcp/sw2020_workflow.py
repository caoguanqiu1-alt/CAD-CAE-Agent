"""SW2020 grouped COM workflow. All dimensions mm; no UI automation.

Original upstream tools remain available. Prefer these bounded tools for common
boss/cut workflows. Durable request IDs block uncertain/partial replays; they do
not claim transaction rollback. Logs never go to the JSON-RPC stdout channel.
"""
import asyncio
import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastmcp.server.middleware import Middleware
from .adapters.base import ExtrusionParameters

STATE = Path(__file__).resolve().parents[2] / 'local_state' / 'sw2020'

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.pending')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)

def event(value):
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'timings.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps({'time':time.time(), 'pid':os.getpid(), **value}, ensure_ascii=False)+'\n')

class SerialTimingMiddleware(Middleware):
    """Serialize all tools in this server; cooperating stable servers fail busy.

    The file lock does not control legacy launchers or manual SolidWorks edits.
    Keep COM on the server's existing thread (no unsafe worker-thread offload).
    """
    def __init__(self, ensure_connected=None):
        self.lock = asyncio.Lock()
        self.ensure_connected = ensure_connected

    async def on_call_tool(self, context, call_next):
        # These closed, numeric operations have no COM or filesystem side effects.
        if context.message.name in {'sw2020_validate_plan', 'sw2020_compare_results'}:
            return await call_next(context)
        import msvcrt
        async with self.lock:
            STATE.mkdir(parents=True, exist_ok=True)
            with (STATE / 'com.lock').open('a+b') as gate:
                if gate.tell() == 0:
                    gate.write(b'0'); gate.flush()
                gate.seek(0)
                try:
                    msvcrt.locking(gate.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    raise RuntimeError('SW2020_BUSY: another stable MCP session is executing; inspect before retrying')
                start = time.perf_counter()
                status = 'returned'
                event({'tool':context.message.name, 'phase':'started'})
                try:
                    # Connect only for tools/call, inside the existing COM lock.
                    # initialize and tools/list never enter this callback.
                    # Simulation owns an attach-only bridge, including diagnostics
                    # for SW not running. Keep the same lock but never auto-launch SW.
                    if self.ensure_connected is not None and not context.message.name.startswith('sw_simulation_'):
                        await self.ensure_connected()
                    return await call_next(context)
                except BaseException:
                    status = 'exception'
                    raise
                finally:
                    event({'tool':context.message.name, 'phase':status, 'seconds':time.perf_counter()-start})
                    gate.seek(0)
                    msvcrt.locking(gate.fileno(), msvcrt.LK_UNLCK, 1)

class Shape(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    kind: Literal['rectangle', 'circle', 'polygon']
    x: float = 0
    y: float = 0
    width: float = Field(default=0, ge=0)
    height: float = Field(default=0, ge=0)
    radius: float = Field(default=0, ge=0)
    points: list[tuple[float, float]] = Field(default_factory=list, max_length=500)

    @model_validator(mode='after')
    def valid_geometry(self):
        if self.kind == 'rectangle' and (self.width <= 0 or self.height <= 0):
            raise ValueError('Rectangle width and height must be positive')
        if self.kind == 'circle' and self.radius <= 0:
            raise ValueError('Circle radius must be positive')
        if self.kind == 'polygon':
            if len(self.points) < 3 or len(set(self.points)) != len(self.points):
                raise ValueError('Polygon needs at least 3 distinct vertices, without repeated closing point')
            area = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(self.points,self.points[1:]+self.points[:1]))
            if abs(area) < 1e-9:
                raise ValueError('Polygon has zero signed area')
        return self

class Group(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z_\u3400-\u9fff][A-Za-z0-9_\u3400-\u9fff-]*$')
    sketch_name: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z_\u3400-\u9fff][A-Za-z0-9_\u3400-\u9fff-]*$')
    plane: str = Field(min_length=1)
    kind: Literal['boss', 'cut']
    depth: float = Field(gt=0)
    reverse: bool = False
    through_all: bool = False
    shapes: list[Shape] = Field(min_length=1, max_length=100)

def methods(obj, *names):
    # Flag only methods actually needed, avoiding hundreds of COM name lookups
    # per face/edge as in the earlier full-interface traversal.
    for name in names:
        obj._FlagAsMethod(name)
    return obj

def real_adapter(server):
    adapter = server.adapter
    while hasattr(adapter, 'adapter'):
        adapter = adapter.adapter
    return adapter

def model_state(adapter, expected_document=None):
    app = adapter.swApp
    if app is None:
        raise RuntimeError('SolidWorks COM is disconnected')
    methods(app, 'RevisionNumber')
    rev = app.RevisionNumber()
    if str(rev).split('.')[0] != '28':
        raise RuntimeError('Expected SW2020 revision 28, got '+str(rev))
    model = app.ActiveDoc
    result = {'revision':rev, 'year':2020, 'active_document':None}
    if model is None:
        if expected_document:
            raise RuntimeError('No active document')
        return None, result
    methods(model, 'GetTitle', 'GetPathName', 'GetType', 'GetActiveSketch2', 'GetSaveFlag',
            'FeatureByName', 'ClearSelection2', 'GetBodies2')
    title, path = model.GetTitle(), model.GetPathName()
    result.update(active_document=title, path=path, type=model.GetType(),
                  sketch_editing=model.GetActiveSketch2() is not None, dirty=model.GetSaveFlag())
    if expected_document and expected_document.casefold() not in (title.casefold(), path.casefold()):
        raise RuntimeError(f'Active document mismatch: expected {expected_document}, got {title}')
    adapter.currentModel = model
    return model, result

def check(result):
    if not result.is_success:
        raise RuntimeError(str(result.error))
    return result.data

def plane_feature(model, name):
    aliases = {'Front':['Front Plane','前视基准面','前視基準面'],
               'Top':['Top Plane','上视基准面','上視基準面'],
               'Right':['Right Plane','右视基准面','右視基準面']}
    for candidate in aliases.get(name, [name]):
        feat = model.FeatureByName(candidate)
        if feat is not None:
            methods(feat, 'GetTypeName2', 'Select2')
            if feat.GetTypeName2() != 'RefPlane':
                raise ValueError('Sketch support must be a reference plane')
            return feat
    # Never fall back to a different principal plane when the name is wrong.
    raise ValueError('Plane not found: '+name)

def geometry(model):
    bodies = list(model.GetBodies2(0, False) or [])
    boxes = []
    for body in bodies:
        methods(body, 'GetBodyBox')
        boxes.append([v*1000 for v in body.GetBodyBox()])
    ext = methods(model.Extension, 'CreateMassProperty')
    mass = ext.CreateMassProperty()
    return {'solid_bodies':len(bodies), 'body_boxes_mm_approx':boxes,
            'volume_mm3':mass.Volume*1e9 if mass is not None else 0}

def register_workflow(server):
    @server.mcp.tool()
    async def sw2020_preflight(expected_document: str | None = None, feature_names: list[str] = []) -> dict:
        """Read live SW2020 version/document/sketch state without traversing geometry.

        Run once before a recipe; use exact returned title/path for later guards.
        Does not create a document or modify its geometry.
        """
        if len(feature_names)>30: raise ValueError('At most 30 named feature checks')
        model, state = model_state(real_adapter(server), expected_document)
        if model is not None:
            state['features_present']={name:model.FeatureByName(name) is not None for name in feature_names}
            state['add_to_db']=model.SketchManager.AddToDB
            state['graphics_update']=model.ActiveView.EnableGraphicsUpdate
        return {'status':'success', **state, 'single_connection':True,
                'intelligent_routing':False, 'timings_path':str(STATE/'timings.jsonl')}

    @server.mcp.tool()
    async def sw2020_build_batch(request_id: str, expected_document: str, groups: list[Group]) -> dict:
        """Create groups of exact sketch profiles + boss/cut through real COM.

        mm; rectangles are centered at x,y; polygon vertices use sketch coordinates.
        Front/Top/Right or exact existing reference plane only. Validate whole
        recipe before writes, stop at first failure. No automatic mutation retry.
        Reusing request_id returns stored status; partial/uncertain runs require
        inspection, never a blind retry/new ID. Does not create/overwrite a part.
        """
        if not expected_document.strip():
            raise ValueError('An explicit expected document is required')
        if not request_id or len(request_id) > 128 or not 1 <= len(groups) <= 30:
            raise ValueError('Need a request ID <=128 chars and 1..30 groups')
        payload = {'document':expected_document, 'groups':[g.model_dump() for g in groups]}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        journal = STATE/'requests'/(hashlib.sha256(request_id.encode()).hexdigest()+'.json')
        if journal.exists():
            old = json.loads(journal.read_text(encoding='utf-8'))
            if old['digest'] != digest:
                raise ValueError('request_id already used with different arguments')
            return {**old, 'replayed':True, 'message':'No operations repeated. Inspect document if partial/started.'}
        adapter = real_adapter(server)
        model, state = model_state(adapter, expected_document)
        if model is None or state['type'] != 1 or state['sketch_editing']:
            raise ValueError('Expected an active Part outside sketch edit mode')
        names = [n for g in groups for n in (g.name, g.sketch_name)]
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError('Feature/sketch names must be unique within recipe')
        for name in names:
            if model.FeatureByName(name) is not None:
                raise ValueError('Feature already exists; inspect before retry: '+name)
        for group in groups:
            plane_feature(model, group.plane)
        record = {'status':'started','request_id':request_id,'digest':digest,'completed':[]}
        write_json(journal, record)
        manager = methods(model.SketchManager, 'InsertSketch', 'CreateCircleByRadius', 'CreateLine')
        view = model.ActiveView
        old_add, old_display = manager.AddToDB, manager.DisplayWhenAdded
        old_graphics = view.EnableGraphicsUpdate if view is not None else None
        started = time.perf_counter()
        try:
            if view is not None:
                view.EnableGraphicsUpdate = False
            for group in groups:
                stage = time.perf_counter()
                record['in_progress'] = group.name
                write_json(journal, record)
                model_state(adapter, expected_document)
                model.ClearSelection2(True)
                if not plane_feature(model, group.plane).Select2(False, 0):
                    raise RuntimeError('Plane selection failed')
                manager.InsertSketch(True)
                sketch = model.GetActiveSketch2()
                # SW2020 returns a dispatch exposing the active feature's Name;
                # GetFeature is not available on that default COM interface.
                feat = methods(model.FeatureByName(str(sketch.Name)), 'Select2')
                feat.Name = group.sketch_name
                if str(feat.Name) != group.sketch_name:
                    raise RuntimeError('Sketch rename was not accepted: '+group.sketch_name)
                adapter._last_sketch_name = group.sketch_name
                manager.AddToDB, manager.DisplayWhenAdded = True, False
                for shape in group.shapes:
                    if shape.kind == 'circle':
                        if manager.CreateCircleByRadius(shape.x/1000, shape.y/1000, 0, shape.radius/1000) is None:
                            raise RuntimeError('Circle creation failed')
                    else:
                        pts = shape.points
                        if shape.kind == 'rectangle':
                            x,y,w,h=shape.x,shape.y,shape.width/2,shape.height/2
                            pts=[(x-w,y-h),(x+w,y-h),(x+w,y+h),(x-w,y+h)]
                        for a,b in zip(pts,pts[1:]+pts[:1]):
                            if manager.CreateLine(a[0]/1000,a[1]/1000,0,b[0]/1000,b[1]/1000,0) is None:
                                raise RuntimeError('Line creation failed')
                manager.AddToDB = False
                manager.InsertSketch(True)
                model.ClearSelection2(True)
                if not feat.Select2(False,0):
                    raise RuntimeError('Whole sketch selection failed')
                params = ExtrusionParameters(depth=group.depth, reverse_direction=group.reverse,
                                             end_condition='ThroughAll' if group.through_all else 'Blind')
                result = await (adapter.create_extrusion(params) if group.kind=='boss' else adapter.create_cut_extrude(params))
                built = check(result)
                actual = model.FeatureByName(built.name)
                if actual is None:
                    raise RuntimeError('Returned feature is missing')
                actual.Name = group.name
                if str(actual.Name) != group.name:
                    raise RuntimeError('Feature rename was not accepted: '+group.name)
                record['completed'].append({'feature':group.name,'sketch':group.sketch_name,
                                            'seconds':time.perf_counter()-stage})
                write_json(journal,record)
            record['status']='success'
            record.pop('in_progress',None)
        except Exception as exc:
            record.update(status='partial', error=str(exc), recovery='Inspect existing features before any further mutation; no rollback was attempted.')
        finally:
            cleanup_errors=[]
            for label, action in [
                ('exit_sketch',lambda: manager.InsertSketch(True) if model.GetActiveSketch2() is not None else None),
                ('AddToDB',lambda:setattr(manager,'AddToDB',old_add)),
                ('DisplayWhenAdded',lambda:setattr(manager,'DisplayWhenAdded',old_display)),
                ('graphics',lambda:setattr(view,'EnableGraphicsUpdate',old_graphics) if view is not None else None),
                ('selection',lambda:model.ClearSelection2(True))]:
                try: action()
                except Exception as exc: cleanup_errors.append(label+': '+str(exc))
            if cleanup_errors:
                record.update(status='partial', cleanup_errors=cleanup_errors)
            record['seconds']=time.perf_counter()-started
            write_json(journal,record)
        return record

    @server.mcp.tool()
    async def sw2020_verify_save(expected_document: str, file_path: str,
                                 expected_features: list[str], expected_bodies: int = 1,
                                 expected_volume_mm3: float | None = None,
                                 volume_tolerance_mm3: float = 0.01) -> dict:
        """Rebuild once, verify named features/body count/optional volume, save Part.

        Reject existing target paths belonging to another document; never deletes
        or closes a user's file. Bounds are approximate body boxes, not vertex
        bounds. Does not claim drawing completeness or validate thread geometry.
        """
        if not expected_document.strip() or expected_bodies < 1:
            raise ValueError('Explicit document and positive expected body count required')
        if not math.isfinite(volume_tolerance_mm3) or volume_tolerance_mm3 < 0:
            raise ValueError('Volume tolerance must be finite and nonnegative')
        if expected_volume_mm3 is not None and (not math.isfinite(expected_volume_mm3) or expected_volume_mm3 <= 0):
            raise ValueError('Expected volume must be finite and positive')
        adapter = real_adapter(server)
        model,state = model_state(adapter,expected_document)
        if model is None or state['type']!=1 or state['sketch_editing']:
            raise ValueError('Expected active Part outside sketch edit mode')
        path=Path(file_path)
        if not path.is_absolute() or path.suffix.lower()!='.sldprt':
            raise ValueError('Use an absolute .SLDPRT path')
        same = state['path'] and Path(state['path']).resolve()==path.resolve()
        if path.exists() and not same:
            raise ValueError('Target exists; choose a new filename')
        methods(model,'ForceRebuild3','SaveAs3')
        if not model.ForceRebuild3(False):
            raise RuntimeError('ForceRebuild3 failed')
        for name in expected_features:
            feature=model.FeatureByName(name)
            if feature is None: raise ValueError('Missing feature: '+name)
        data=geometry(model)
        if data['solid_bodies']!=expected_bodies:
            raise ValueError('Solid body count mismatch')
        if expected_volume_mm3 is not None and abs(data['volume_mm3']-expected_volume_mm3)>volume_tolerance_mm3:
            raise ValueError(f'Volume mismatch: {data}')
        path.parent.mkdir(parents=True,exist_ok=True)
        # SW2020 SaveAs3 returns an integer error code; zero means success.
        code=model.SaveAs3(str(path),0,1)
        if code != 0 or not path.exists() or path.stat().st_size==0 or model.GetSaveFlag():
            raise RuntimeError(f'Save not verified, code={code}')
        return {'status':'success',**data,'features':expected_features,'path':str(path),
                'bytes':path.stat().st_size,'dirty':False}

    # Internal handlers reuse the existing execution boundary; no nested MCP call/lock.
    return {'build_batch': sw2020_build_batch, 'verify_save': sw2020_verify_save}
