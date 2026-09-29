"""Offline contract tests. These do not claim CAD compatibility."""
import copy
import unittest
from types import SimpleNamespace
from fastmcp import FastMCP
from pydantic import ValidationError
from solidworks_mcp.sw2020_plan import (ModelingPlan, Metrics, Expectations,
    Snapshot, Tolerances, compile_plan, compare_metrics, register_plan)
from solidworks_mcp.sw2020_workflow import SerialTimingMiddleware


def example():
    return {'schema_version': 'sw2020-plan/1', 'target_year': 2020, 'units': 'mm',
            'expected': {'volume_mm3': 60000}, 'nodes': [
                {'id': 'base', 'operation': {'name': '底座拉伸', 'sketch_name': '底座草图',
                 'plane': 'Front', 'kind': 'boss', 'depth': 10,
                 'shapes': [{'kind': 'rectangle', 'width': 100, 'height': 60}]}}]}


class ContractTests(unittest.TestCase):
    def test_chinese_names_and_canonical_hash(self):
        source = example()
        result = compile_plan(ModelingPlan.model_validate(source))
        self.assertEqual(result['groups'][0]['name'], '底座拉伸')
        self.assertEqual(result['plan_sha256'], compile_plan(
            ModelingPlan.model_validate(dict(reversed(list(source.items())))))['plan_sha256'])

    def test_dependencies_sorted_without_changing_input(self):
        source = example()
        cut = copy.deepcopy(source['nodes'][0])
        cut.update(id='cut', depends_on=['base'])
        cut['operation'].update(name='切除', sketch_name='切除草图', kind='cut')
        source['nodes'].insert(0, cut)
        result = compile_plan(ModelingPlan.model_validate(source))
        self.assertEqual(result['node_order'], ['base', 'cut'])
        self.assertEqual(source['nodes'][0]['id'], 'cut')

    def test_cycles_missing_and_duplicate_dependencies_rejected(self):
        for dependencies in [['base'], ['missing'], ['base', 'base']]:
            with self.subTest(dependencies=dependencies):
                source = example()
                source['nodes'][0]['depends_on'] = dependencies
                with self.assertRaises(ValidationError): ModelingPlan.model_validate(source)

    def test_wrong_version_units_and_unknown_fields_rejected(self):
        for key, value in [('target_year', 2026), ('units', 'm'), ('script', 'anything')]:
            with self.subTest(key=key):
                source = example(); source[key] = value
                with self.assertRaises(ValidationError): ModelingPlan.model_validate(source)

    def test_nonfinite_and_nonpositive_geometry_rejected(self):
        for value in [float('nan'), float('inf'), 0, -1]:
            source = example(); source['nodes'][0]['operation']['depth'] = value
            with self.assertRaises(ValidationError): ModelingPlan.model_validate(source)

    def test_unsupported_feature_and_duplicate_names_rejected(self):
        source = example(); source['nodes'][0]['operation']['kind'] = 'loft'
        with self.assertRaises(ValidationError): ModelingPlan.model_validate(source)
        source = example(); source['nodes'][0]['operation']['sketch_name'] = '底座拉伸'
        with self.assertRaises(ValidationError): ModelingPlan.model_validate(source)

    def test_body_count_not_truncated(self):
        source = example(); source['expected']['solid_bodies'] = 1.5
        with self.assertRaises(ValidationError): ModelingPlan.model_validate(source)

    def test_mismatch_reports_volume_center_and_counts(self):
        actual = Metrics(solid_bodies=1, volume_mm3=60000, area_mm2=15200,
                         center_mm=[0, 0, 5], faces=6, edges=12, vertices=8)
        expected = Expectations(volume_mm3=59000, center_mm=[0, 0, 6], faces=7)
        result = compare_metrics(actual, expected, Tolerances())
        self.assertEqual(result['status'], 'mismatch')
        self.assertEqual({c['metric'] for c in result['checks'] if not c['matched']},
                         {'volume_mm3', 'center_mm', 'faces'})
        self.assertIn('not a BREP', result['scope'])

    def test_negative_or_nan_tolerance_rejected(self):
        for value in [-1, float('nan')]:
            with self.assertRaises(ValidationError): Tolerances(volume_mm3=value)


class PureRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_pure_tools_skip_connection(self):
        calls = []
        async def connect(): calls.append('connect')
        async def next_call(context): calls.append(context.message.name); return 'ok'
        middleware = SerialTimingMiddleware(connect)
        for name in ['sw2020_validate_plan', 'sw2020_compare_results']:
            result = await middleware.on_call_tool(SimpleNamespace(message=SimpleNamespace(name=name)), next_call)
            self.assertEqual(result, 'ok')
        self.assertNotIn('connect', calls)

    async def test_changed_feature_types_do_not_match(self):
        server = SimpleNamespace(mcp=FastMCP('offline'))
        handlers = register_plan(server, {})
        baseline = Snapshot(revision='28.5.0', document='test', path='', dirty=True,
            metrics=Metrics(solid_bodies=1, volume_mm3=60000, area_mm2=15200,
                            center_mm=[0,0,5], faces=6, edges=12, vertices=8),
            feature_types={'底座': 'Extrusion'})
        candidate = baseline.model_copy(update={'feature_types': {'底座': 'Imported'}})
        result = await handlers['compare'](baseline, candidate)
        self.assertEqual(result['status'], 'mismatch')
        self.assertFalse(result['live_verification'])


if __name__ == '__main__': unittest.main(verbosity=2)
