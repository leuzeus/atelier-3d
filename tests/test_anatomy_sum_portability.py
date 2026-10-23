"""Section identity must not inherit builtin floating-sum version changes."""
import copy
import math
import unittest
from unittest.mock import patch

from a3d import anatomy_profile
from a3d.core import digest


def legacy_sum(values, start=0):
    """Model the Python 3.11 float left fold, retaining exact integer sums."""
    result = start
    for value in values:
        result += value
    return result


def compensated_sum(values, start=0):
    """Model newer compensated float semantics; integer counts stay integer.

    This deliberately uses fsum for the comparison, not a claim to reproduce
    every detail of the Python 3.13 builtin implementation on this host.
    """
    values = list(values)
    if type(start) is float or any(type(value) is float for value in values):
        return math.fsum([start, *values])
    return legacy_sum(values, start)


def irregular_closed_surface():
    count = 47
    contour = [[(19.+(i % 7)*.37+(i % 11)*.019)*math.cos(math.tau*i/count),
                (19.+(i % 7)*.37+(i % 11)*.019)*math.sin(math.tau*i/count)]
               for i in range(count)]
    vertices = [[x, y, z] for z in (0., 180.) for x, y in contour]
    faces = [[i, (i+1) % count, (i+1) % count+count, i+count] for i in range(count)]
    faces += [list(reversed(range(count))), list(range(count, 2*count))]
    return vertices, faces


def measured_with_sum(vertices, faces, builtin_sum):
    with patch.object(anatomy_profile, 'sum', side_effect=builtin_sum, create=True) as observed:
        result = anatomy_profile.surface_section(vertices, faces, 90., [0., 0.])
        observed.assert_called()  # The remaining integer loop count uses it.
    return result


class AnatomySumPortability(unittest.TestCase):
    def test_irregular_closed_section_has_identical_complete_identity_across_float_sum_semantics(self):
        vertices, faces = irregular_closed_surface(); before = digest([vertices, faces])
        legacy = measured_with_sum(vertices, faces, legacy_sum)
        compensated = measured_with_sum(vertices, faces, compensated_sum)
        self.assertEqual(legacy['status'], 'MEASURED')
        lengths = [math.dist(a, b) for a, b in
                   zip(legacy['curve_cm'], legacy['curve_cm'][1:]+legacy['curve_cm'][:1])]
        # Keep a regression-sensitive fixture: the old source with builtin
        # float sum would change its perimeter, and hence its full digest.
        self.assertNotEqual(legacy_sum(lengths), compensated_sum(lengths))
        self.assertEqual(legacy['girth_cm'], math.fsum(lengths))
        self.assertEqual(legacy, compensated)
        self.assertEqual(digest(legacy), digest(compensated))
        for key in ('loop_count', 'open_loop_count', 'excluded_loops'):
            self.assertIs(type(legacy[key]), int)
            self.assertIs(type(compensated[key]), int)
        self.assertEqual(before, digest([vertices, faces]))

    def test_measurable_source_geometry_change_still_changes_section_evidence_without_tolerance(self):
        vertices, faces = irregular_closed_surface()
        original = measured_with_sum(vertices, faces, legacy_sum)
        changed_vertices = copy.deepcopy(vertices); count = len(vertices)//2
        changed_vertices[0][0] += .125
        changed_vertices[count][0] += .125
        changed = measured_with_sum(changed_vertices, faces, compensated_sum)
        self.assertEqual(changed['status'], 'MEASURED')
        self.assertNotEqual(original['curve_cm'], changed['curve_cm'])
        self.assertNotEqual(original['girth_cm'], changed['girth_cm'])
        self.assertNotEqual(digest(original), digest(changed))
        self.assertEqual(changed, measured_with_sum(changed_vertices, faces, legacy_sum))

    def test_open_surface_remains_refused_and_integer_counts_exact_under_both_semantics(self):
        vertices, faces = irregular_closed_surface(); open_faces = faces[1:]
        before = digest([vertices, open_faces])
        legacy = measured_with_sum(vertices, open_faces, legacy_sum)
        compensated = measured_with_sum(vertices, open_faces, compensated_sum)
        self.assertEqual(legacy, compensated)
        self.assertEqual(legacy['status'], 'NOT_QUALIFIED')
        self.assertEqual(legacy['reason'], 'SECTION_OPEN_AMBIGUOUS_OR_COPLANAR')
        self.assertEqual(legacy['open_loop_count'], 1)
        self.assertIs(type(legacy['open_loop_count']), int)
        self.assertNotIn('girth_cm', legacy)
        self.assertNotIn('curve_cm', legacy)
        self.assertEqual(before, digest([vertices, open_faces]))


if __name__ == '__main__':
    unittest.main()
