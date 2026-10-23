"""Synthetic geometry probes; none of these qualifies an anatomical body."""
import copy
import math
import unittest

from a3d.anatomy_profile import profile_mesh
from a3d.body_region_sections import (_section, measure_body_regions, measure_project_body_regions,
                                      verified_region)
from a3d.core import StudioError, digest
from a3d.shoulder_surface import measured_surface_shoulders


def box(x_offset=0.):
    vertices=[[x+x_offset,y,z] for z in (0.,180.) for y in (-10.,10.) for x in (-20.,20.)]
    faces=[[0,2,3,1],[4,5,7,6],[0,1,5,4],[2,6,7,3],[0,4,6,2],[1,3,7,5]]
    triangles=[t for a,b,c,d in faces for t in ([a,b,c],[a,c,d])]
    return vertices,faces,triangles


def fixture(rotated=False):
    vertices,faces,triangles=box()
    names={'shoulder.left':[-10.,0.,170.],'elbow.left':[-10.,0.,140.],'wrist.left':[-10.,0.,110.],
           'shoulder.right':[10.,0.,170.],'elbow.right':[10.,0.,140.],'wrist.right':[10.,0.,110.],
           'head.center':[0.,0.,175.],'hand.left':[0.,0.,90.],'hand.right':[0.,0.,90.]}
    options={'up_axis':[0.,0.,1.],'forward_axis':[0.,-1.,0.],'origin_cm':[0.,0.,0.],
             'torso_faces':list(range(len(faces))),'segmentation_source_ref':'synthetic:closed-box',
             'section_count':24}
    if rotated:
        # Rotate around two independent axes, then translate. A horizontal-only
        # section or treating local landmarks as world coordinates fails here.
        a,b=.37,.61
        def rotate(p):
            q=[math.cos(a)*p[0]-math.sin(a)*p[1],math.sin(a)*p[0]+math.cos(a)*p[1],p[2]]
            return [q[0],math.cos(b)*q[1]-math.sin(b)*q[2],math.sin(b)*q[1]+math.cos(b)*q[2]]
        translation=[17.,-23.,8.]
        def transform(p):return [v+t for v,t in zip(rotate(p),translation)]
        vertices=list(map(transform,vertices));names={key:transform(point) for key,point in names.items()}
        options['up_axis']=rotate(options['up_axis']);options['forward_axis']=rotate(options['forward_axis']);options['origin_cm']=translation
    geometry={'vertices_cm':vertices,'faces':faces,'face_sets':[1]*len(faces),
              'source_sha256':'a'*64,'pose_sha256':digest(vertices),
              'rig_landmarks':{name:{'point_cm':point,'source_ref':'synthetic:source-rings'} for name,point in names.items()}}
    profile=measured_surface_shoulders(profile_mesh(geometry,options),geometry,triangles)
    identity={'profile_sha256':digest(profile),'profile_cache_key':profile['cache_key'],
              'geometry_sha256':profile['geometry_sha256'],'source_sha256':profile['source_sha256'],
              'pose_sha256':profile['pose_sha256'],'face_sets_sha256':digest(geometry['face_sets']),
              'triangles_sha256':digest(triangles)}
    ref={'path':'synthetic-source.json','sha256':'b'*64}
    row={'id':'arm.left','side':'left','domain':'SHOULDER_TO_ELBOW_ONLY',
         'axis_start_landmark':'shoulder.left','axis_end_landmark':'elbow.left',
         'plane_reference_axis':'forward','fraction_domain':[0.,1.],'fractions':[0.,.5,1.],
         'face_ids':list(range(len(faces))),'source_ref':ref}
    specification={'version':1,'purpose':'TEST_ONLY','identity':identity,
        'bindings':{'profile_ref':dict(ref,path='profile.json'),'geometry_ref':dict(ref,path='geometry.json'),
                    'triangles_ref':dict(ref,path='triangles.json')},
        'numerical_tolerance_cm':.000001,'regions':[row],
        'budgets':{'max_sections':3,'max_triangle_evaluations':36,'max_projection_vertices':100}}
    return profile,geometry,triangles,specification


class BodyRegionSections(unittest.TestCase):
    def test_true_closed_skin_sections_are_deterministic_and_leave_every_input_unchanged(self):
        values=fixture();before=digest(values);result=measure_body_regions(*values)
        self.assertEqual(result,measure_body_regions(*values));self.assertEqual(digest(values),before)
        self.assertEqual(result['status'],'BODY_REGIONS_MEASURED')
        region=result['regions'][0];self.assertEqual(region['status'],'MEASURED_SECTIONS')
        self.assertEqual(region['spatial_coverage'],'DECLARED_SAMPLES_ONLY')
        self.assertEqual(region['full_hand_passage'],'NOT_QUALIFIED')
        for row in region['sections']:
            self.assertAlmostEqual(row['girth_cm'],120.,places=8)
            self.assertGreater(row['numerical_error_bound_cm'],0.)
            normal=row['plane']['normal_world']
            for point in row['curve_cm']:
                self.assertAlmostEqual(sum((a-b)*n for a,b,n in zip(point,row['center_cm'],normal)),0.,places=8)
        self.assertEqual(result['acceptance'],'NOT_GRANTED');self.assertEqual(result['dressing'],'NOT_EXECUTED')
        self.assertEqual(result['native_body_origin'],'NOT_CHECKED_BY_PORTABLE_KERNEL')

    def test_oblique_rotated_frame_has_same_girth_and_world_bound_joint_planes(self):
        plain=measure_body_regions(*fixture());values=fixture(True);result=measure_body_regions(*values)
        self.assertEqual(result['status'],'BODY_REGIONS_MEASURED')
        for a,b in zip(plain['regions'][0]['sections'],result['regions'][0]['sections']):
            self.assertAlmostEqual(a['girth_cm'],b['girth_cm'],places=8)
        self.assertEqual(result['regions'][0]['axis_start_cm'],values[1]['rig_landmarks']['shoulder.left']['point_cm'])
        self.assertNotEqual(values[0]['landmarks']['shoulder.left']['point_cm'],result['regions'][0]['axis_start_cm'])

    def test_profile_pose_geometry_triangles_and_region_labels_invalidate_measurements(self):
        for mutation in ('pose','vertices','triangles','labels','joint','cache','profile'):
            values=list(copy.deepcopy(fixture()));profile,geometry,triangles,spec=values
            if mutation=='pose':geometry['pose_sha256']='c'*64
            if mutation=='vertices':geometry['vertices_cm'][0][0]+=.1
            if mutation=='triangles':triangles.reverse()
            if mutation=='labels':geometry['face_sets'][0]=2
            if mutation=='joint':geometry['rig_landmarks']['elbow.left']['point_cm'][0]+=.2
            if mutation=='cache':profile['cache_key']='c'*64
            if mutation=='profile':profile['landmarks']['elbow.left']['point_cm'][0]+=.2
            with self.subTest(mutation=mutation),self.assertRaises(StudioError):measure_body_regions(*values)

    def test_changed_or_forged_contour_is_refused_even_if_resigned(self):
        values=fixture();result=measure_body_regions(*values)
        self.assertEqual(verified_region(*values,result,'arm.left'),result['regions'][0])
        result['regions'][0]['sections'][0]['girth_cm']=1.
        result['cache_key']=digest({k:v for k,v in result.items() if k!='cache_key'})
        with self.assertRaisesRegex(StudioError,'remeasured'):verified_region(*values,result,'arm.left')

    def test_measurement_code_change_invalidates_even_identical_geometry(self):
        from unittest.mock import patch
        values=fixture();result=measure_body_regions(*values)
        with patch('a3d.body_region_sections.sha',return_value='e'*64):
            with self.assertRaisesRegex(StudioError,'remeasured'):verified_region(*values,result,'arm.left')

    def test_json_file_roundtrip_preserves_skin_planes_and_hand_hull_remeasurement(self):
        import tempfile
        from pathlib import Path
        from a3d.core import ROOT,atomic_json,read_json
        values=list(fixture());profile,geometry,triangles,spec=values;original=copy.deepcopy(geometry)
        adapter={'source_ref':'synthetic:region-adapter','source_geometry_sha256':digest([geometry['vertices_cm'],geometry['faces'],geometry['face_sets']]),
                 'centers':{'hand.left':[1]},'region_to_bone':{'1':'hand.left'}}
        ref={'path':'hand-domain.json','sha256':'d'*64}
        spec['hand_envelopes']=[{'id':'hand.left','side':'left','plane_reference_axis':'forward','source_ref':ref}]
        spec['hand_source']={'adapter_ref':dict(ref,path='adapter.json'),'source_geometry_ref':dict(ref,path='original.json'),
                            'adapter_sha256':digest(adapter),'source_geometry_sha256':digest(original)}
        result=measure_body_regions(*values,adapter,original)
        (ROOT/'work/test-runs').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'work/test-runs') as directory:
            path=Path(directory)/'supplement.json';atomic_json(path,result);saved=read_json(path)
            self.assertEqual(saved,result)
            self.assertEqual(verified_region(*values,saved,'arm.left',adapter,original),result['regions'][0])
            self.assertEqual(saved['hand_envelopes'],result['hand_envelopes'])

    def test_source_face_domain_open_coplanar_and_outside_sections_are_never_admitted(self):
        values=list(fixture());values[3]['regions'][0]['face_ids']=list(range(5))
        result=measure_body_regions(*values)
        self.assertEqual(result['status'],'BODY_REGIONS_NEED_DATA')
        self.assertTrue(all(row['reason']=='SECTION_OPEN_OR_BRANCHING' for row in result['regions'][0]['sections']))
        vertices,_,triangles=box();u=[1.,0.,0.];v=[0.,1.,0.];normal=[0.,0.,1.]
        coplanar=_section(vertices,triangles,list(range(len(triangles))),[0.,0.,0.],normal,u,v,.000001)
        self.assertFalse(coplanar['ok']);self.assertIn('COPLANAR',coplanar['reason'])
        outside=_section(vertices,triangles,list(range(len(triangles))),[30.,0.,90.],normal,u,v,.000001)
        self.assertFalse(outside['ok']);self.assertEqual(outside['reason'],'SOURCED_AXIS_OUTSIDE_OR_ON_SKIN')
        empty=_section(vertices,triangles,list(range(len(triangles))),[0.,0.,200.],normal,u,v,.000001)
        self.assertFalse(empty['ok']);self.assertEqual(empty['reason'],'SECTION_EMPTY_OR_OUTSIDE_SKIN')

    def test_multiple_closed_skin_shells_cannot_be_selected_to_make_a_measurement_pass(self):
        points,_,triangles=box();other,_,other_triangles=box(80.)
        offset=len(points);points+=other;triangles += [[i+offset for i in row] for row in other_triangles]
        result=_section(points,triangles,list(range(len(triangles))),[0.,0.,90.],[0.,0.,1.],[1.,0.,0.],[0.,1.,0.],.000001)
        self.assertFalse(result['ok']);self.assertEqual(result['reason'],'MULTIPLE_SOURCE_DOMAIN_SECTION_LOOPS')
        self.assertEqual(len(result['loops']),2)

    def test_domain_fraction_reference_axis_and_budget_are_explicit(self):
        for mutation in ('hand','fractions','duplicate','missing_boundary','parallel','bool'):
            values=list(copy.deepcopy(fixture()));row=values[3]['regions'][0]
            if mutation=='hand':row['axis_end_landmark']='hand.left'
            if mutation=='fractions':row['fractions']=[0.,1.,.5]
            if mutation=='duplicate':row['face_ids'].append(0)
            if mutation=='missing_boundary':row['fractions']=[.1,.5,1.]
            if mutation=='parallel':row['plane_reference_axis']='up'
            if mutation=='bool':row['fractions'][0]=False
            with self.subTest(mutation=mutation),self.assertRaises(StudioError):measure_body_regions(*values)
        values=list(fixture());values[3]['budgets']['max_triangle_evaluations']=12
        result=measure_body_regions(*values);self.assertEqual(result['status'],'INCOMPLETE')
        self.assertEqual(result['triangle_evaluations'],12)
        self.assertEqual(sum(row['ok'] for row in result['regions'][0]['sections']),1)
        self.assertEqual(result['regions'][0]['status'],'NEEDS_DATA')

    def test_whole_hand_hull_contains_complete_source_skin_and_never_calls_it_a_girth(self):
        values=list(fixture());profile,geometry,triangles,spec=values
        original=copy.deepcopy(geometry)
        adapter={'source_ref':'synthetic:region-adapter','source_geometry_sha256':digest([geometry['vertices_cm'],geometry['faces'],geometry['face_sets']]),
                 'centers':{'hand.left':[1]},'region_to_bone':{'1':'hand.left'}}
        ref={'path':'hand-domain.json','sha256':'d'*64}
        spec['hand_envelopes']=[{'id':'hand.left','side':'left','plane_reference_axis':'forward','source_ref':ref}]
        spec['hand_source']={'adapter_ref':dict(ref,path='adapter.json'),'source_geometry_ref':dict(ref,path='original.json'),
                            'adapter_sha256':digest(adapter),'source_geometry_sha256':digest(original)}
        result=measure_body_regions(*values,adapter,original);hand=result['hand_envelopes'][0]
        self.assertEqual(hand['status'],'CONSERVATIVE_SKIN_PROJECTION_MEASURED')
        self.assertEqual(hand['source_vertex_ids'],list(range(8)))
        self.assertTrue(hand['projection_contains_all_declared_skin_vertices'])
        self.assertNotIn('girth_cm',hand);self.assertEqual(hand['anatomical_girth'],'NOT_MEASURED')
        self.assertEqual(hand['physical_hand_passage'],'NOT_QUALIFIED')
        spec['budgets']['max_projection_vertices']=3
        limited=measure_body_regions(*values,adapter,original)
        self.assertEqual(limited['status'],'INCOMPLETE')
        self.assertNotIn('hull_plane_cm',limited['hand_envelopes'][0])
        self.assertEqual(limited['hand_envelopes'][0]['physical_hand_passage'],'NOT_QUALIFIED')
        spec['budgets']['max_projection_vertices']=100
        adapter['region_to_bone']['2']='hand.left';spec['hand_source']['adapter_sha256']=digest(adapter)
        with self.assertRaisesRegex(StudioError,'absent source skin'):measure_body_regions(*values,adapter,original)

    def test_zero_domains_cannot_produce_an_empty_measured_supplement(self):
        values=list(fixture());values[3]['regions']=[]
        with self.assertRaisesRegex(StudioError,'at least one'):measure_body_regions(*values)

    def test_project_wrapper_without_native_body_origin_cannot_admit_a_supplement(self):
        import tempfile
        from pathlib import Path
        from a3d.core import ROOT,atomic_json,sha
        from tests.support import ready_project
        (ROOT/'work/test-runs').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'work/test-runs') as directory:
            project=ready_project(Path(directory),True);profile,geometry,triangles,spec=fixture()
            for name,data in [('profile',profile),('geometry',geometry),('triangles',triangles)]:
                atomic_json(project.root/(name+'.json'),data)
                spec['bindings'][name+'_ref']={'path':name+'.json','sha256':sha(project.root/(name+'.json'))}
            atomic_json(project.root/'synthetic-source.json',{'scope':'PORTABLE_NEGATIVE_ONLY'})
            spec['regions'][0]['source_ref']['sha256']=sha(project.root/'synthetic-source.json')
            atomic_json(project.root/'regions.json',spec);before=sha(project.db)
            with self.assertRaisesRegex(StudioError,'canonical native run origin'):
                measure_project_body_regions(project,'regions.json')
            self.assertEqual(sha(project.db),before)


if __name__=='__main__':unittest.main()
