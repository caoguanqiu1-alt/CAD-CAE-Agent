"""Offline rejection/recovery tests; these do not simulate or certify FEA."""
import copy
import math
import tempfile
import unittest
from pathlib import Path

from solidworks_mcp.simulation_plan import (
    relative_change_percent, run_simulation_plan, validate_plan, PlanError,
)


class SimulationPlanContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.doc = self.root / 'copy.SLDPRT'
        self.doc.touch()
        self.lib = self.root / 'test.sldmat'
        self.lib.touch()
        self.face = 'face_' + 'a' * 32
        self.plan = dict(expected_document=str(self.doc), study='Test',
                         material=dict(library=str(self.lib), name='Example'),
                         fixture_face=self.face,
                         loads=[dict(face=self.face, force_N=[1000, 0, 0])],
                         mesh_sizes_mm=[5, 4, 3],
                         archive_directory=str(self.root / 'archive'),
                         plot_bmp=str(self.root / 'plot.bmp'))

    def test_malformed_paths_are_structured_errors_before_any_call(self):
        for field in ['expected_document', 'archive_directory', 'plot_bmp']:
            for value in [None, 123, [], '']:
                plan = copy.deepcopy(self.plan)
                plan[field] = value
                calls = []
                result = run_simulation_plan(plan, lambda *a, **kw: calls.append(a))
                self.assertEqual(result['status'], 'error')
                self.assertEqual(calls, [])

    def test_invalid_material_path_is_structured(self):
        self.plan['material']['library'] = None
        result = run_simulation_plan(self.plan, lambda *a, **kw: self.fail('COM called'))
        self.assertEqual(result['error_code'], 'INVALID_MATERIAL')

    def test_nonfinite_zero_and_boolean_loads_rejected(self):
        for vector in [[math.nan, 0, 1], [math.inf, 0, 1], [0, 0, 0], [True, 0, 0]]:
            self.plan['loads'][0]['force_N'] = vector
            with self.assertRaises(PlanError):
                validate_plan(self.plan)

    def test_existing_outputs_are_preserved(self):
        plot = self.root / 'plot.bmp'
        plot.write_bytes(b'original')
        result = run_simulation_plan(self.plan, lambda *a, **kw: self.fail('COM called'))
        self.assertEqual(result['error_code'], 'NEW_BMP_PATH_REQUIRED')
        self.assertEqual(plot.read_bytes(), b'original')

    def test_mesh_order_and_guide_requirements(self):
        for sizes in [[3, 4, 5], [4, 4, 3], [4, 3], [4, 3, math.nan]]:
            plan = copy.deepcopy(self.plan)
            plan['mesh_sizes_mm'] = sizes
            with self.assertRaises(PlanError):
                validate_plan(plan)
        self.plan['guide_face'] = self.face
        with self.assertRaises(PlanError):
            validate_plan(self.plan)

    def test_dirty_document_stops_before_geometry_or_mutation(self):
        calls = []
        def invoke(operation, **kwargs):
            calls.append(operation)
            return dict(status='success', document_path=str(self.doc), document_dirty=True)
        result = run_simulation_plan(self.plan, invoke)
        self.assertEqual(result['error_code'], 'ACTIVE_DOCUMENT_NOT_CLEAN_COPY')
        self.assertEqual(calls, ['check'])

    def test_unknown_study_creation_is_partial_and_never_retried(self):
        calls = []
        def invoke(operation, **kwargs):
            calls.append(operation)
            return {
                'check': dict(status='success', document_path=str(self.doc), document_dirty=False),
                'inspect_geometry': dict(status='success', solid_bodies=1),
                'resolve_geometry': dict(status='success'),
                'create_static_study': dict(status='unknown', error_code='AMBIGUOUS'),
            }[operation]
        result = run_simulation_plan(self.plan, invoke)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(calls.count('create_static_study'), 1)
        self.assertEqual(calls[-1], 'create_static_study')
        self.assertFalse((self.root / 'archive').exists())

    def test_convergence_zero_and_stress_independence(self):
        self.assertEqual(relative_change_percent(0, 0), 0)
        self.assertIsNone(relative_change_percent(1, 0))
        self.assertLess(relative_change_percent(.01121472, .01123401), 1)
        self.assertGreater(relative_change_percent(11.4927, 12.4418), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
