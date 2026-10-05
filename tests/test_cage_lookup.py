"""Behavioral comparison with the unchanged linear cage evaluator."""
import copy
from dataclasses import FrozenInstanceError
import math
import random
import unittest

from a3d.cage_lookup import CageLookup
from a3d.core import StudioError
from a3d.pattern_assembly import _cage_point, _compile_cage


def lattice(size=12):
    uv=[[float(x),float(y)]for y in range(size+1)for x in range(size+1)]
    triangles=[]
    for y in range(size):
        for x in range(size):
            a=y*(size+1)+x;b=a+1;c=a+size+1;d=c+1
            triangles.extend(([a,b,d],[a,d,c]))
    return {'uv_cm':uv,'target_cm':[[x*.71+y*.07,y*.93-x*.04,x*y*.013]for x,y in uv],
        'triangles':triangles}


def outcome(frame, compiled, uv):
    try:return ('OK',_cage_point(frame,compiled,uv,'fixture'))
    except StudioError as error:return ('REFUSED',str(error))


def accepted_ids(compiled, uv):
    """Independent explicit reference predicate, including all matching cells."""
    ids=[]
    for triangle_id,_,a,b,c,denominator in compiled:
        beta=((uv[0]-a[0])*(c[1]-a[1])-(uv[1]-a[1])*(c[0]-a[0]))/denominator
        gamma=((b[0]-a[0])*(uv[1]-a[1])-(b[1]-a[1])*(uv[0]-a[0]))/denominator
        weights=[1-beta-gamma,beta,gamma]
        if min(weights)>=-1e-8 and max(weights)<=1+1e-8:ids.append(triangle_id)
    return ids


class CageLookupTests(unittest.TestCase):
    def assert_reference(self,frame,compiled,lookup,uv):
        result=lookup.query(uv)
        ids=[entry[0]for entry in result.entries]
        self.assertEqual(ids,[entry[0]for entry in compiled if entry[0]in ids])
        self.assertTrue(set(accepted_ids(compiled,uv))<=set(ids))
        self.assertEqual(outcome(frame,compiled,uv),outcome(lookup.frame,result.entries,uv))
        return result

    def test_lattice_all_controls_edges_nextafter_and_random_queries_are_exact(self):
        frame=lattice();compiled=_compile_cage(frame,'fixture');lookup=CageLookup(frame,compiled)
        before=copy.deepcopy([frame,compiled]);queries=copy.deepcopy(frame['uv_cm'])
        for coordinate in (0.,.5,1.,3.5,8.,12.):
            for axis in (0,1):
                for direction in (-math.inf,math.inf):
                    point=[coordinate,coordinate];point[axis]=math.nextafter(coordinate,direction);queries.append(point)
        generator=random.Random(7911)
        queries.extend([generator.uniform(-1.,13.),generator.uniform(-1.,13.)]for _ in range(150))
        counts=[self.assert_reference(frame,compiled,lookup,uv).retained_cells for uv in queries]
        self.assertLess(sum(counts),len(queries)*len(compiled)//3)
        self.assertEqual([frame,compiled],before)
        # A tolerance-accepted point just outside the exact triangle box survives.
        single={'uv_cm':[[0.,0.],[1.,0.],[0.,1.]],'target_cm':[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],'triangles':[[0,1,2]]}
        rows=_compile_cage(single,'fixture');index=CageLookup(single,rows,leaf_size=1)
        for u in (-1e-8,math.nextafter(-1e-8,0.),math.nextafter(-1e-8,-math.inf),0.):
            self.assert_reference(single,rows,index,[u,.25])

    def test_overlapping_conflicting_targets_keep_all_candidates_and_refusal(self):
        frame=lattice(4);offset=len(frame['uv_cm'])
        frame['uv_cm'].extend([[0.,0.],[8.,0.],[0.,8.]])
        frame['target_cm'].extend([[0.,0.,10.],[8.,0.,10.],[0.,8.,10.]])
        frame['triangles'].append([offset,offset+1,offset+2])
        compiled=_compile_cage(frame,'fixture');lookup=CageLookup(frame,compiled,leaf_size=1)
        result=self.assert_reference(frame,compiled,lookup,[.25,.25])
        self.assertIn(len(compiled)-1,[entry[0]for entry in result.entries])
        self.assertEqual(outcome(lookup.frame,result.entries,[.25,.25])[0],'REFUSED')

    def test_rotated_sheared_scaled_translated_and_mixed_orientation_cells(self):
        generator=random.Random(317)
        for scale,offset in ((.001,0.),(1.,1e12),(1e6,-1e7)):
            frame=lattice(5)
            frame['uv_cm']=[[offset+scale*(.93*x-.37*y),offset+scale*(.41*x+1.12*y)]for x,y in frame['uv_cm']]
            frame['triangles']=[row[::-1]if i%3==0 else row for i,row in enumerate(frame['triangles'])]
            compiled=_compile_cage(frame,'fixture');lookup=CageLookup(frame,compiled,leaf_size=2)
            queries=copy.deepcopy(frame['uv_cm'])
            for point in frame['uv_cm'][::4]:
                queries.append([math.nextafter(point[0],math.inf),point[1]])
                queries.append([point[0],math.nextafter(point[1],-math.inf)])
            for _ in range(70):
                x,y=generator.uniform(-.5,5.5),generator.uniform(-.5,5.5)
                queries.append([offset+scale*(.93*x-.37*y),offset+scale*(.41*x+1.12*y)])
            for uv in queries:
                with self.subTest(scale=scale,offset=offset,uv=uv):self.assert_reference(frame,compiled,lookup,uv)

    def test_nonmonotone_compiled_order_preserves_first_overlap_binding(self):
        points=[[0.,0.],[1.,0.],[0.,1.],[0.,0.],[1.,0.],[0.,1.],[5.,5.],[6.,5.],[5.,6.]]
        frame={'uv_cm':points,'target_cm':[[x,y,0.]for x,y in points],
            'triangles':[[0,1,2],[3,4,5],[6,7,8]]}
        original=_compile_cage(frame,'fixture')
        compiled=[original[1],original[2],original[0]]
        lookup=CageLookup(frame,compiled,leaf_size=1)
        query=self.assert_reference(frame,compiled,lookup,[.2,.3])
        self.assertEqual([entry[0]for entry in query.entries],[1,0])
        self.assertEqual(_cage_point(lookup.frame,query.entries,[.2,.3],'fixture')[1]['cage_triangle'],1)

    def test_concave_domain_mixed_winding_preserves_missing_regions_and_cell_order(self):
        frame={'uv_cm':[[0.,0.],[2.,0.],[2.,1.],[1.,1.],[1.,2.],[0.,2.]],
            'target_cm':[[0.,0.,0.],[2.,0.,0.],[2.,1.,0.],[1.,1.,0.],[1.,2.,0.],[0.,2.,0.]],
            'triangles':[[0,1,3],[1,3,2],[0,3,5],[3,5,4]]}
        compiled=_compile_cage(frame,'fixture');lookup=CageLookup(frame,compiled,leaf_size=1)
        for uv in ([.5,.5],[1.5,.5],[.5,1.5],[1.5,1.5],[1.,1.],[3.,3.]):
            self.assert_reference(frame,compiled,lookup,uv)
        self.assertEqual(outcome(frame,compiled,[1.5,1.5])[0],'REFUSED')

    def test_query_unproved_types_nonfinite_and_extreme_arithmetic_fall_back(self):
        frame=lattice(2);compiled=_compile_cage(frame,'fixture');lookup=CageLookup(frame,compiled)
        for uv in ([0,0],[False,.5],[float('nan'),.5],[float('inf'),.5],[1e308,-1e308],['x',.5],[]):
            with self.subTest(uv=uv):
                result=lookup.query(uv)
                self.assertTrue(result.full_scan_fallback)
                self.assertEqual([r[0]for r in result.entries],[r[0]for r in compiled])
        for edit in ('integer','nonfinite','zero','extreme'):
            changed=copy.deepcopy(compiled)
            triangle_id,ids,a,b,c,denominator=changed[0]
            if edit=='integer':a[0]=2**53+1
            elif edit=='nonfinite':a[0]=float('inf')
            elif edit=='zero':denominator=0.
            else:a[0]=-1e308;b[0]=1e308
            changed[0]=(triangle_id,ids,a,b,c,denominator)
            result=CageLookup(frame,changed).query([.5,.5])
            self.assertTrue(result.full_scan_fallback)
            self.assertEqual([r[0]for r in result.entries],[r[0]for r in changed])
        for bounds in ((0,1),(float('nan'),1.),(1.,0.),(0.,1.)):
            result=CageLookup(frame,compiled,bary_min=bounds[0],bary_max=bounds[1]).query([.5,.5])
            self.assertTrue(result.full_scan_fallback)

    def test_snapshot_is_immutable_and_explicit_reuse_binding_detects_changes(self):
        frame=lattice(2);compiled=_compile_cage(frame,'fixture');lookup=CageLookup(frame,compiled)
        expected=outcome(lookup.frame,lookup.candidates([.3,.2]),[.3,.2])
        self.assertTrue(lookup.matches(frame,compiled))
        frame['target_cm'][0][2]=50.;compiled[0][2][0]=-.1
        self.assertFalse(lookup.matches(frame,compiled))
        self.assertEqual(outcome(lookup.frame,lookup.candidates([.3,.2]),[.3,.2]),expected)
        with self.assertRaises(FrozenInstanceError):lookup.bary_min=-1.
        with self.assertRaises(TypeError):lookup.frame['target_cm'][0][0]=50.

    def test_exact_integer_and_mixed_coefficients_match_original_arithmetic(self):
        frames=[]
        integer=lattice(4)
        integer['uv_cm']=[[int(x),int(y)]for x,y in integer['uv_cm']]
        frames.append(integer)
        mixed=copy.deepcopy(integer)
        mixed['uv_cm']=[[(float(value)if (i+axis)%3==0 else value)for axis,value in enumerate(point)]
            for i,point in enumerate(mixed['uv_cm'])]
        frames.append(mixed)
        for frame in frames:
            compiled=_compile_cage(frame,'fixture');lookup=CageLookup(frame,compiled,leaf_size=2)
            for uv in ([.2,.3],[1.,1.],[math.nextafter(1.,math.inf),2.5],[-1e-8,.25],[3.5,3.5]):
                result=self.assert_reference(frame,compiled,lookup,uv)
                self.assertFalse(result.full_scan_fallback)
        # b itself is not representable, but ORIGINAL b-a=1 is exact.
        origin=2**53
        frame={'uv_cm':[[origin,0],[origin+1,0],[origin,1]],
            'target_cm':[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],'triangles':[[0,1,2]]}
        compiled=_compile_cage(frame,'fixture');lookup=CageLookup(frame,compiled,leaf_size=1)
        result=self.assert_reference(frame,compiled,lookup,[float(origin),.25])
        self.assertFalse(result.full_scan_fallback)
        self.assertEqual(_cage_point(lookup.frame,result.entries,[float(origin),.25],'fixture')[0],[0.,.25,0.])
        # Exact large powers and an integer denominator require no magnitude cap.
        power=2**80
        frame={'uv_cm':[[power,0],[2*power,0],[power,power]],
            'target_cm':[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],'triangles':[[0,1,2]]}
        compiled=_compile_cage(frame,'fixture');lookup=CageLookup(frame,compiled,leaf_size=1)
        self.assertFalse(self.assert_reference(frame,compiled,lookup,[1.5*power,.25*power]).full_scan_fallback)

    def test_unrepresentable_integer_origin_coefficients_denominator_and_huge_fall_back(self):
        frame=lattice(2);compiled=_compile_cage(frame,'fixture')
        for changed_field in ('origin','coefficient','denominator','huge'):
            rows=copy.deepcopy(compiled)
            tid,ids,a,b,c,denominator=rows[0]
            if changed_field=='origin':a[0]=2**53+1
            elif changed_field=='coefficient':a[0]=0;b[0]=2**53+1
            elif changed_field=='denominator':denominator=2**53+1
            else:a[0]=10**1000
            rows[0]=(tid,ids,a,b,c,denominator)
            with self.subTest(field=changed_field):
                result=CageLookup(frame,rows).query([.2,.3])
                self.assertTrue(result.full_scan_fallback)
                self.assertEqual([row[0]for row in result.entries],[row[0]for row in rows])

    def test_time_checks_propagate_in_build_query_and_fallback(self):
        frame=lattice(4);compiled=_compile_cage(frame,'fixture')
        def stop():raise StudioError('diagnostic time budget exhausted')
        with self.assertRaisesRegex(StudioError,'time budget'):CageLookup(frame,compiled,stop)
        lookup=CageLookup(frame,compiled,leaf_size=1)
        for uv in ([.2,.3],[0,0]):
            with self.assertRaisesRegex(StudioError,'time budget'):lookup.query(uv,stop)
        calls=[]
        def delayed():
            calls.append(1)
            if len(calls)>3:stop()
        with self.assertRaisesRegex(StudioError,'time budget'):lookup.query([.2,.3],delayed)
        self.assertEqual(len(calls),4)


if __name__=='__main__':unittest.main()
