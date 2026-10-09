"""Transported material knots retain source support without changing native gates."""
import copy
import math
import time
import unittest

from a3d.core import StudioError, digest
from a3d.material_section_sampling import (compile_material_sections, material_section_point,
                                          material_section_cage_state)
from a3d.pattern_assembly import _compile_cage, _cage_point
from a3d.source_seam_coupling import _Budget


def fixture(sign=1, rotated=False, bilinear=.2, simple=False):
    vertices = [[sign*u, v] for u, v in ((0., 0.), (4., 0.), (4., 3.), (0., 3.))]
    piece = {'vertices': vertices, 'faces': [[0, 1, 2], [0, 2, 3]],
             'edges': {'bottom': [0, 1], 'right': [1, 2], 'top': [2, 3], 'left': [3, 0]}}
    transform = (lambda p: [10+p[2], 20+p[0], -5+p[1]]) if rotated else (lambda p: p)
    sections = []
    for v in ((0., 3.) if simple else (0., 1.5, 3.)):
        us = [0., 4.] if simple else [0., 1. if v != 1.5 else 2., 4.]
        sections.append({'v_cm': v, 'material_u_cm': [sign*u for u in us],
                         'curve_cm': [transform([u, v, bilinear*u*v]) for u in us]})
    frame = {'source_ref': 'test:explicit-material-source', 'sampling_contract': 'SOURCE_MATERIAL_U_V1',
             'material_sections': sections}
    return piece, frame


def budget(**limits): return _Budget(limits or None, time.monotonic)


class MaterialSectionSampling(unittest.TestCase):
    def test_partition_is_source_conforming_deterministic_and_immutable(self):
        piece, frame = fixture(); before = digest([piece, frame])
        state = material_section_cage_state(piece, frame, 'sample', budget())
        repeated = material_section_cage_state(piece, frame, 'sample', budget())
        for key in ('uv', 'triangles', 'original', 'segments', 'triangle_source_faces', 'sampling_report'):
            self.assertEqual(state[key], repeated[key])
        self.assertEqual(set(state['triangle_source_faces']), {0, 1})
        self.assertEqual(len(state['segments']), 4)
        self.assertAlmostEqual(state['sampling_report']['material_area_cm2'], 12., places=12)
        self.assertTrue(set(map(tuple, piece['vertices'])) <= set(map(tuple, state['uv'])))
        self.assertEqual(state['sampling_report']['seed_subdivisions'], 1)
        self.assertEqual(state['sampling_report']['qualification'], 'NONE')
        self.assertEqual(digest([piece, frame]), before)
        reordered = copy.deepcopy(piece); reordered['faces'].reverse()
        other = material_section_cage_state(reordered, frame, 'sample', budget())
        for key in ('uv', 'triangles', 'original'): self.assertEqual(state[key], other[key])

    def test_bilinear_interpolation_error_is_measured_not_claimed_exact(self):
        piece, frame = fixture(); state = material_section_cage_state(piece, frame, 'sample', budget())
        cage = {'uv_cm': state['uv'], 'triangles': state['triangles'], 'target_cm': state['original']}
        compiled = _compile_cage(cage, 'sample'); observed_nonzero = False
        for triangle in state['triangles']:
            points = [state['uv'][i] for i in triangle]
            width = max(p[0] for p in points)-min(p[0] for p in points)
            height = max(p[1] for p in points)-min(p[1] for p in points)
            # For this exact fixture P=(u,v,.2*u*v), the affine interpolation
            # error is .2*Cov(u,v), bounded by .2*range(u)*range(v)/4.
            bound = .2*width*height/4
            for weights in ((.25, .25, .5), (.125, .625, .25), (1/3, 1/3, 1/3)):
                u, v = [math.fsum(w*p[k] for w, p in zip(weights, points)) for k in (0, 1)]
                actual = _cage_point(cage, compiled, [u, v], 'sample')[0]
                error = math.dist(actual, [u, v, .2*u*v])
                self.assertLessEqual(error, bound+1e-12)
                observed_nonzero |= error > 1e-5
        self.assertTrue(observed_nonzero)
        report = state['sampling_report']['interior_interpolation']
        self.assertEqual(report['sample_count'], 4*len(state['triangles']))
        self.assertGreater(report['maximum_error_over_samples_cm'], 0.)
        self.assertFalse(report['certified_continuous_bound'])
        flat_piece, flat_frame = fixture(bilinear=0.)
        flat = material_section_cage_state(flat_piece, flat_frame, 'sample', budget())
        self.assertLess(flat['sampling_report']['interior_interpolation']['maximum_error_over_samples_cm'], 1e-12)

    def test_signed_material_parameters_and_rotations_are_explicit_and_equivariant(self):
        baseline = material_section_cage_state(*fixture(), 'sample', budget())
        lookup = {tuple(uv): target for uv, target in zip(baseline['uv'], baseline['original'])}
        for sign in (-1, 1):
            for rotated in (False, True):
                piece, frame = fixture(sign=sign, rotated=rotated)
                state = material_section_cage_state(piece, frame, 'sample', budget())
                for (u, v), actual in zip(state['uv'], state['original']):
                    expected = lookup[(sign*u, v)]
                    if rotated: expected = [10+expected[2], 20+expected[0], -5+expected[1]]
                    self.assertLess(math.dist(actual, expected), 1e-12)
                compiled = compile_material_sections(frame, 'sample', budget())
                observed, binding = material_section_point(compiled, [sign*1.5, .75], 'sample', budget())
                self.assertEqual(binding['sampling_contract'], 'SOURCE_MATERIAL_U_V1')
                self.assertEqual(binding['source_uv_cm'], [sign*1.5, .75])
                self.assertTrue(all(row['original_curve_indices'][0] > row['original_curve_indices'][1]
                                    for row in binding['material_samples']) if sign < 0 else
                                all(row['original_curve_indices'][0] < row['original_curve_indices'][1]
                                    for row in binding['material_samples']))

    def test_shared_budget_is_charged_once_and_exhaustion_refuses(self):
        piece, frame = fixture(simple=True); shared = budget(max_controls=7, max_triangles=9)
        shared.reserve(3, 7)
        state = material_section_cage_state(piece, frame, 'sample', shared)
        self.assertEqual((len(state['uv']), len(state['triangles'])), (4, 2))
        self.assertEqual((shared.controls, shared.triangles), (7, 9))
        for limits in ({'max_controls': 3}, {'max_triangles': 1}, {'max_source_points': 3}):
            with self.subTest(limits=limits), self.assertRaisesRegex(StudioError, 'budget'):
                material_section_cage_state(piece, frame, 'sample', budget(**limits))
        calls = [0]
        def clock():
            calls[0] += 1
            return calls[0]*.01
        with self.assertRaisesRegex(StudioError, 'time budget'):
            material_section_cage_state(piece, frame, 'sample', _Budget({'max_seconds': .015}, clock))

    def test_invalid_parameters_refuse_instead_of_being_sorted_or_inferred(self):
        for variant in ('duplicate', 'nonmonotone', 'nan', 'boolean', 'count', 'v_duplicate', 'v_reverse', 'extra', 'missing_contract'):
            piece, frame = fixture(); bad = copy.deepcopy(frame)
            if variant == 'duplicate': bad['material_sections'][0]['material_u_cm'][1] = 0.
            elif variant == 'nonmonotone': bad['material_sections'][0]['material_u_cm'] = [0., 4., 1.]
            elif variant == 'nan': bad['material_sections'][0]['material_u_cm'][1] = math.nan
            elif variant == 'boolean': bad['material_sections'][0]['material_u_cm'][1] = True
            elif variant == 'count': bad['material_sections'][0]['curve_cm'].pop()
            elif variant == 'v_duplicate': bad['material_sections'][1]['v_cm'] = 0.
            elif variant == 'v_reverse': bad['material_sections'].reverse()
            elif variant == 'extra': bad['u_direction'] = 1
            elif variant == 'missing_contract': del bad['sampling_contract']
            with self.subTest(variant=variant), self.assertRaises(StudioError):
                material_section_cage_state(piece, bad, 'sample', budget())

    def test_queries_never_extrapolate_and_compile_snapshots_inputs(self):
        piece, frame = fixture(); compiled = compile_material_sections(frame, 'sample', budget())
        before = copy.deepcopy(compiled)
        frame['material_sections'][0]['curve_cm'][0][0] = 99.
        self.assertEqual(compiled, before)
        for uv in ((-1., 1.), (5., 1.), (1., -1.), (1., 4.), (True, 1.), (1., math.inf)):
            with self.subTest(uv=uv), self.assertRaises(StudioError):
                material_section_point(compiled, uv, 'sample', budget())
        piece, frame = fixture(simple=True)
        for section in frame['material_sections']:
            section['material_u_cm'][-1] = 3.
        with self.assertRaisesRegex(StudioError, 'outside'):
            material_section_cage_state(piece, frame, 'sample', budget())
        for section in frame['material_sections']:
            section['material_u_cm'].append(5.)
            section['curve_cm'].append([5., section['v_cm'], section['v_cm']])
        state = material_section_cage_state(piece, frame, 'sample', budget())
        self.assertEqual(state['sampling_report']['qualification'], 'NONE')

    def test_near_distinct_knots_remain_distinct_and_slivers_are_refused(self):
        piece, frame = fixture(simple=True)
        for section in frame['material_sections']:
            section['material_u_cm'].insert(1, 1e-12)
            section['curve_cm'].insert(1, [1e-12, section['v_cm'], 0.])
        before = digest([piece, frame])
        with self.assertRaisesRegex(StudioError, 'Collapsed') as refusal:
            material_section_cage_state(piece, frame, 'sample', budget())
        self.assertFalse(refusal.exception.guide_diagnostic['cuts_merged'])
        self.assertEqual(refusal.exception.guide_diagnostic['existing_minimum_abs_determinant_cm2'], 1e-10)
        self.assertEqual(digest([piece, frame]), before)


if __name__ == '__main__': unittest.main()
