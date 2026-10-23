import math
import unittest
from a3d.catalog_anatomy import region_guides
from a3d.core import StudioError, digest


def tube(offset=0., count=8):
    vertices = [[offset+10*math.cos(i*math.tau/count), 10*math.sin(i*math.tau/count), z]
                for z in (0., 80., 160.) for i in range(count)]
    faces = [[level*count+i, level*count+(i+1)%count, (level+1)*count+(i+1)%count, (level+1)*count+i]
             for level in (0, 1) for i in range(count)]
    return vertices, faces, [1]*count+[2]*count


def fixture():
    v, f, labels = tube()
    geometry = {'vertices_cm': v, 'faces': f, 'face_sets': labels}
    adapter = {'source_geometry_sha256': digest([v, f, labels]), 'source_ref': 'fixture source',
               'joints': {'joint': [1, 2]}, 'centers': {'upper.center': [2]}, 'torso_regions': [1, 2]}
    return geometry, adapter


class CatalogAnatomy(unittest.TestCase):
    def test_guides_use_source_ring_without_mutating_geometry(self):
        geometry, adapter = fixture(); before = digest([geometry, adapter])
        report = region_guides(geometry, adapter)
        self.assertEqual(report['joint_evidence']['joint']['boundary_vertices'], list(range(8, 16)))
        for actual, expected in zip(report['rig_landmarks']['joint']['point_cm'], [0., 0., 80.]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(report['qualification'], 'SOURCE_TOPOLOGY_GUIDES_ONLY')
        self.assertEqual(digest([geometry, adapter]), before)

    def test_stale_metric_topology_and_regions_are_refused(self):
        for field in ('vertices_cm', 'faces', 'face_sets'):
            geometry, adapter = fixture()
            if field == 'vertices_cm': geometry[field][0][0] += .01
            if field == 'faces': geometry[field][0].reverse()
            if field == 'face_sets': geometry[field][0] = 2
            with self.subTest(field=field), self.assertRaises(StudioError): region_guides(geometry, adapter)

    def test_multiple_rings_require_unambiguous_declared_selector(self):
        geometry, adapter = fixture(); v, f, labels = tube(40., count=6)
        offset = len(geometry['vertices_cm']); geometry['vertices_cm'] += v
        geometry['faces'] += [[i+offset for i in face] for face in f]; geometry['face_sets'] += labels
        adapter['source_geometry_sha256'] = digest([geometry['vertices_cm'], geometry['faces'], geometry['face_sets']])
        with self.assertRaises(StudioError): region_guides(geometry, adapter)
        adapter['joint_ring_vertex_counts'] = {'joint': 8}
        result = region_guides(geometry, adapter)
        self.assertEqual(result['joint_evidence']['joint']['excluded_source_rings'], 1)
        adapter['joint_ring_vertex_counts']['joint'] = 100
        with self.assertRaises(StudioError): region_guides(geometry, adapter)

    def test_missing_provenance_or_regions_are_refused(self):
        for failure in ('source', 'joint', 'torso', 'center'):
            geometry, adapter = fixture()
            if failure == 'source': adapter['source_ref'] = ''
            if failure == 'joint': adapter['joints']['joint'] = [1, 1]
            if failure == 'torso': adapter['torso_regions'] = [999]
            if failure == 'center': adapter['centers']['upper.center'] = [999]
            with self.subTest(failure=failure), self.assertRaises(StudioError): region_guides(geometry, adapter)
