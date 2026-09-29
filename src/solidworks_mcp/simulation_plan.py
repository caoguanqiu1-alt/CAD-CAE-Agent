"""Guarded end-to-end Simulation plan runner; called under the MCP COM gate."""
import math
import shutil
from pathlib import Path


class PlanError(Exception):
    def __init__(self, code, detail=''):
        super().__init__(detail)
        self.code = code


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _face(value):
    return isinstance(value, str) and value.startswith('face_') and len(value) > 20


def _path(value, code):
    if not isinstance(value, str) or not value.strip():
        raise PlanError(code)
    return Path(value)


def relative_change_percent(previous, current):
    """A zero denominator is undefined unless both values are zero."""
    if current == 0:
        return 0.0 if previous == 0 else None
    return abs(current - previous) / abs(current) * 100


def validate_plan(plan):
    if not isinstance(plan, dict):
        raise PlanError('INVALID_PLAN')
    document = _path(plan.get('expected_document'), 'SAVED_PART_COPY_REQUIRED')
    study = plan.get('study')
    material = plan.get('material')
    loads = plan.get('loads')
    fixture = plan.get('fixture_face')
    sizes = plan.get('mesh_sizes_mm')
    archive = _path(plan.get('archive_directory'), 'NEW_ARCHIVE_DIRECTORY_REQUIRED')
    plot = _path(plan.get('plot_bmp'), 'NEW_BMP_PATH_REQUIRED')
    threshold = plan.get('displacement_tolerance_percent', 1.0)
    if not document.is_absolute() or document.suffix.lower() != '.sldprt' or not document.is_file():
        raise PlanError('SAVED_PART_COPY_REQUIRED')
    if not isinstance(study, str) or not study.strip() or len(study) > 80:
        raise PlanError('INVALID_STUDY_NAME')
    if not isinstance(material, dict) or not _path(material.get('library'), 'INVALID_MATERIAL').is_file() or not isinstance(material.get('name'), str) or not material['name'].strip():
        raise PlanError('INVALID_MATERIAL')
    if not _face(fixture):
        raise PlanError('INVALID_FIXTURE_FACE')
    if not isinstance(loads, list) or not 1 <= len(loads) <= 16:
        raise PlanError('INVALID_LOAD_COUNT')
    for load in loads:
        if not isinstance(load, dict) or not _face(load.get('face')):
            raise PlanError('INVALID_LOAD_FACE')
        force = load.get('force_N')
        if not isinstance(force, list) or len(force) != 3 or not all(_finite(v) for v in force) or math.hypot(*force) <= 0:
            raise PlanError('INVALID_FORCE_VECTOR')
    contacts = plan.get('contacts', [])
    if not isinstance(contacts, list) or len(contacts) > 8 or any(
        not isinstance(pair, dict) or not _face(pair.get('link_face')) or not _face(pair.get('pin_face')) for pair in contacts
    ):
        raise PlanError('INVALID_CONTACT_PAIRS')
    rollers = plan.get('axial_roller_faces', [])
    if not isinstance(rollers, list) or len(rollers) not in (0, 2) or any(not _face(v) for v in rollers):
        raise PlanError('INVALID_ROLLER_FACES')
    guide = plan.get('guide_face')
    if guide is not None and (not _face(guide) or len(rollers) != 2):
        raise PlanError('GUIDE_REQUIRES_TWO_ROLLERS')
    if not isinstance(sizes, list) or not 3 <= len(sizes) <= 6 or not all(_finite(v) and 1 <= v <= 20 for v in sizes):
        raise PlanError('INVALID_MESH_SEQUENCE')
    if any(sizes[i] <= sizes[i+1] for i in range(len(sizes)-1)):
        raise PlanError('MESH_SIZES_MUST_DECREASE')
    if not _finite(threshold) or not 0 < threshold <= 20:
        raise PlanError('INVALID_CONVERGENCE_TOLERANCE')
    if not archive.is_absolute() or archive.exists() or not archive.parent.is_dir():
        raise PlanError('NEW_ARCHIVE_DIRECTORY_REQUIRED')
    if not plot.is_absolute() or plot.suffix.lower() != '.bmp' or plot.exists() or not plot.parent.is_dir():
        raise PlanError('NEW_BMP_PATH_REQUIRED')
    if 'plot_title' in plan and (not isinstance(plan['plot_title'], str) or not plan['plot_title'].strip()):
        raise PlanError('INVALID_PLOT_TITLE')
    return {
        'document': str(document), 'study': study, 'material': material,
        'fixture': fixture, 'loads': loads, 'contacts': contacts, 'rollers': rollers,
        'guide': guide, 'sizes': sizes, 'archive': archive, 'plot': plot,
        'threshold': threshold,
    }


def run_simulation_plan(plan, invoke):
    """Run only a clean active copy. Never retry a failed/unknown COM mutation."""
    try:
        p = validate_plan(plan)
    except PlanError as exc:
        return {'status': 'error', 'error_code': exc.code, 'message': str(exc)}
    steps = []
    created_study = False
    mutation_started = False

    def call(label, operation, **arguments):
        result = invoke(operation, **arguments)
        steps.append({'step': label, 'status': result.get('status'), 'error_code': result.get('error_code')})
        if result.get('status') != 'success':
            raise PlanError('STEP_FAILED', label)
        return result

    try:
        check = call('preflight', 'check', load_addin=True)
        if check.get('document_path', '').lower() != p['document'].lower() or check.get('document_dirty'):
            raise PlanError('ACTIVE_DOCUMENT_NOT_CLEAN_COPY')
        geometry = call('geometry', 'inspect_geometry', expected_document=p['document'])
        bodies = geometry['solid_bodies']
        if bodies != 1 and (bodies < 2 or not p['contacts']):
            raise PlanError('MULTIBODY_CONTACTS_REQUIRED')
        if bodies == 1 and p['contacts']:
            raise PlanError('CONTACTS_REQUIRE_MULTIBODY')
        ids = [p['fixture'], *(x['face'] for x in p['loads']),
               *(x for pair in p['contacts'] for x in (pair['link_face'], pair['pin_face'])),
               *p['rollers']]
        if p['guide']:
            ids.append(p['guide'])
        call('resolve_faces', 'resolve_geometry', expected_document=p['document'], ids=list(dict.fromkeys(ids)))
        mutation_started = True
        study = call('study', 'create_static_study', expected_document=p['document'],
                     name=p['study'], load_addin=True)
        created_study = study['created']
        mutation_started = created_study
        common = {'expected_document': p['document'], 'study': p['study']}
        state = call('initial_state', 'phase3_state', **common)
        if state['boundaries'] or state['contact_count']:
            raise PlanError('STUDY_NOT_EMPTY')
        mutation_started = True
        if bodies == 1:
            call('material', 'phase2_material', **common, library=p['material']['library'], material=p['material']['name'])
        else:
            call('materials', 'phase3_materials', **common, library=p['material']['library'], material=p['material']['name'])
        call('fixture', 'phase2_fixture', **common, face=p['fixture'])
        call('loads', 'phase3_forces', **common, loads=p['loads'])
        if p['rollers']:
            call('axial_rollers', 'phase3_rollers', **common, faces=p['rollers'])
        if p['guide']:
            call('lateral_guide', 'phase3_guide', **common, face=p['guide'])
        if p['contacts']:
            call('contacts', 'phase3_contacts', **common, pairs=p['contacts'])
        state = call('configured_state', 'phase3_state', **common)
        folder = state['result_folder']
        p['archive'].mkdir()
        mesh_runs = []
        for size in p['sizes']:
            tag = f'{size:g}mm'
            step_kind = 'phase3' if bodies > 1 else 'phase2'
            mesh = call('mesh_' + tag, step_kind + '_mesh', **common, element_size_mm=size)
            run = call('run_' + tag, step_kind + '_run', **common, results_folder=folder)
            results = call('results_' + tag, step_kind + '_results', **common, fixed_face=p['fixture'])
            if any(not _finite(results.get(key)) or results[key] < 0 for key in
                   ('max_displacement_mm', 'max_von_mises_MPa')):
                raise PlanError('INVALID_SOLVER_METRICS', tag)
            cwr = Path(folder) / f'{Path(p["document"]).stem}-{p["study"]}.CWR'
            if not cwr.is_file():
                raise PlanError('NATIVE_CWR_MISSING', str(cwr))
            dest = p['archive'] / tag
            dest.mkdir()
            snapshot = dest / cwr.name
            shutil.copy2(cwr, snapshot)
            mesh_runs.append({
                'element_size_mm': size, 'node_count': mesh['node_count'],
                'element_count': mesh['element_count'],
                'max_displacement_mm': results['max_displacement_mm'],
                'max_von_mises_MPa': results['max_von_mises_MPa'],
                'reaction_fx_N': (results.get('selected_reaction_N_Nm') or [None])[0],
                'solver_error_code': run['solver_error_code'],
                'cwr_snapshot': str(snapshot),
            })
        call('plot', 'phase2_plot', **common, output_bmp=str(p['plot']),
             title=plan.get('plot_title', 'URES (mm) - static analysis - true scale'))
        call('save', 'save', expected_document=p['document'])
        disp_delta = [relative_change_percent(a['max_displacement_mm'], b['max_displacement_mm'])
                      for a,b in zip(mesh_runs,mesh_runs[1:])]
        stress_delta = [relative_change_percent(a['max_von_mises_MPa'], b['max_von_mises_MPa'])
                        for a,b in zip(mesh_runs,mesh_runs[1:])]
        return {'status': 'success', 'study': p['study'], 'document': p['document'],
                'created_study': created_study, 'solid_body_count': bodies,
                'mesh_runs': mesh_runs, 'displacement_change_percent': disp_delta,
                'displacement_tolerance_percent': p['threshold'],
                'displacement_converged': all(v is not None and v <= p['threshold'] for v in disp_delta),
                'peak_stress_change_percent': stress_delta,
                'peak_stress_converged_at_same_tolerance': all(v is not None and v <= p['threshold'] for v in stress_delta),
                'plot_bmp': str(p['plot']), 'steps': steps}
    except PlanError as exc:
        return {'status': 'partial' if mutation_started else 'error', 'error_code': exc.code,
                'message': str(exc), 'steps': steps,
                'next_action': 'Inspect active study and saved results before retrying any mutation.'}
    except Exception as exc:
        return {'status': 'unknown' if mutation_started else 'error', 'error_code': 'PLAN_RUNTIME_ERROR',
                'message': str(exc), 'steps': steps,
                'next_action': 'Inspect active study and saved results before retrying any mutation.'}
