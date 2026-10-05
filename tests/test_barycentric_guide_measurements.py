import copy
import unittest
from unittest.mock import Mock, patch

from a3d.core import StudioError, digest
from a3d.pattern_assembly import _compile_cage, _cage_point
from a3d.garment_measurements import intersect_guide_material_plane


def fixture():
    polygon={'vertices':[[0.,0.],[8.,0.],[8.,10.],[0.,10.]],
             'edges':{'left':[0,3],'right':[2,1]}}
    ring=[[-1.,-1.],[0.,-1.],[1.,-1.],[1.,0.],[1.,1.],[0.,1.],[-1.,1.],[-1.,0.],[-1.,-1.]]
    uv=[];targets=[];indices=[];triangles=[]
    for u,point in enumerate(ring):
        for v in (0.,10.):uv.append([float(u),v]);targets.append(point+[v])
    for u in range(8):
        a=2*u;b=a+2
        for face in ([a,b,b+1],[a,b+1,a+1]):
            indices.append(face);triangles.append([uv[i]for i in face])
    frame={'source_ref':'synthetic:closed-square-perimeter','uv_cm':uv,'target_cm':targets,'triangles':indices}
    section={'center_cm':[0.,0.,5.],'plane':{'normal_world':[0.,.6,.8]}}
    return polygon,frame,triangles,section


class BarycentricGuideMeasurements(unittest.TestCase):
    def test_indexed_complete_material_curve_equals_full_scan_for_distinct_source_frames(self):
        class FullScan:
            def __init__(self,frame,compiled,check_time=None,**kwargs):
                self.frame=frame;self.compiled=compiled
            def candidates(self,uv,check_time=None):
                if check_time is not None:check_time()
                return self.compiled

        for rotated in (False,True):
            piece,frame,triangles,section=fixture()
            if rotated:
                transform=lambda p:[13.+.8*p[0]-.6*p[1],-7.+.6*p[0]+.8*p[1]]
                piece['vertices']=[transform(p)for p in piece['vertices']]
                frame['uv_cm']=[transform(p)for p in frame['uv_cm']]
                triangles=[[transform(p)for p in face]for face in triangles]
            before=digest([piece,frame,triangles,section])
            indexed=intersect_guide_material_plane(piece,frame,triangles,section,['left','right'])
            with patch('a3d.cage_lookup.CageLookup',FullScan):
                reference=intersect_guide_material_plane(piece,frame,triangles,section,['left','right'])
            self.assertEqual(indexed,reference)
            self.assertEqual(before,digest([piece,frame,triangles,section]))
            self.assertEqual(indexed['qualification'],'NONE')

    def test_closed_source_seam_and_oblique_material_path_use_same_cage_as_placement(self):
        piece,frame,triangles,section=fixture();before=digest([piece,frame,triangles,section])
        compiled=_compile_cage(frame,'fixture')
        for v in (0.,1.23,5.,8.9,10.):
            self.assertEqual(_cage_point(frame,compiled,[0.,v],'fixture')[0],
                             _cage_point(frame,compiled,[8.,v],'fixture')[0])
        curve=intersect_guide_material_plane(piece,frame,triangles,section,['left','right'])
        self.assertAlmostEqual(curve['source_material_length_cm'],9.)
        self.assertAlmostEqual(curve['from']['fraction'],1-curve['to']['fraction'])
        self.assertLess(curve['maximum_plane_residual_cm'],1e-12)
        self.assertEqual(curve['qualification'],'NONE');self.assertEqual(curve['homology'],'REVIEW_REQUIRED')
        self.assertEqual(digest([piece,frame,triangles,section]),before)

    def test_invalid_cage_indices_nonfinite_and_collapsed_source_are_refused(self):
        for change in ('negative-index','nonfinite','collapsed','duplicate-face','missing-target'):
            _,frame,_,_=fixture()
            if change=='negative-index':frame['triangles'][0][0]=-1
            elif change=='nonfinite':frame['target_cm'][0][0]=float('nan')
            elif change=='collapsed':frame['uv_cm'][2]=copy.deepcopy(frame['uv_cm'][0])
            elif change=='duplicate-face':frame['triangles'].append(frame['triangles'][0][:])
            else:frame['target_cm'].pop()
            with self.subTest(change=change),self.assertRaises(StudioError):_compile_cage(frame,'fixture')

    def test_ambiguous_overlap_and_uv_outside_cage_are_refused(self):
        _,frame,_,_=fixture()
        with self.assertRaises(StudioError):_cage_point(frame,_compile_cage(frame,'fixture'),[-1.,3.],'fixture')
        offset=len(frame['uv_cm']);frame['uv_cm']+=copy.deepcopy(frame['uv_cm'][:4])
        frame['target_cm']+=[[p[0]+2.,p[1],p[2]]for p in frame['target_cm'][:4]]
        frame['triangles'].append([offset,offset+2,offset+3])
        with self.assertRaisesRegex(StudioError,'Ambiguous'):
            _cage_point(frame,_compile_cage(frame,'fixture'),[.8,1.],'fixture')

    def test_cage_compilation_and_evaluation_obey_material_intersection_budget(self):
        piece,frame,triangles,section=fixture()
        with self.assertRaisesRegex(StudioError,'time budget'):
            intersect_guide_material_plane(piece,frame,triangles,section,['left','right'],
                max_seconds=.05,clock=Mock(side_effect=[0.,0.,0.,.1]))
        with self.assertRaisesRegex(StudioError,'cage computational budget'):
            intersect_guide_material_plane(piece,frame,triangles,section,['left','right'],max_points=17)
        with self.assertRaisesRegex(StudioError,'sentinel'):
            _cage_point(frame,_compile_cage(frame,'fixture'),[2.,3.],'fixture',
                        check_time=Mock(side_effect=StudioError('sentinel')))

    def test_malformed_cage_and_nonfinite_or_noninteger_budgets_are_local_refusals(self):
        piece,frame,triangles,section=fixture()
        for field in ('uv_cm','triangles'):
            malformed=copy.deepcopy(frame);malformed[field]=None
            with self.subTest(field=field),self.assertRaises(StudioError):
                intersect_guide_material_plane(piece,malformed,triangles,section,['left','right'])
        for budgets in ({'max_seconds':float('nan')},{'max_seconds':float('inf')},
                        {'max_seconds':True},{'max_faces':float('inf')},
                        {'max_faces':True},{'max_points':2.5},{'max_points':float('nan')}):
            with self.subTest(budgets=budgets),self.assertRaises(StudioError):
                intersect_guide_material_plane(piece,frame,triangles,section,['left','right'],**budgets)


if __name__=='__main__':unittest.main()
