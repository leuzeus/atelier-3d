"""Whole material-row guide evaluation; no native fitting or homology approval."""
import copy
import unittest

from a3d.core import digest
from a3d.garment_measurements import propose_measurement_paths
from tests.test_garment_measurements import fixture


def collar_fixture():
    compiled,body,guides,requests,world=fixture()
    for pid,role,layer,geometry,semantics in (
        ('collar','collar','outer',{'vertices':[[0.,0.],[12.,0.],[12.,7.],[0.,7.]],
            'edges':{'left':[3,0],'right':[1,2],'neck-base':[0,1]}},
            {'longitudinal_uv_axis':'u'}),
        ('neck-part','front','attachment',{'vertices':[[0.,0.],[12.,0.],[12.,2.],[0.,2.]],
            'edges':{'actual-neck':[0,1]}},{'guide_edges':{'neck':'actual-neck'}})):
        compiled['textiles'][pid]={'component_id':'garment.coat','source_geometry':geometry,
            'semantics':{'role':role,'side':'center','layer':layer,**semantics},
            'package_source_ref':compiled['source_ref']}
        guides['garment.coat']['panels'][pid]={'arc_sections':[{'v_cm':v,'arc_offset_cm':0.,
            'curve_cm':[world([0.,0.,9.+v]),world([12.,0.,9.+v])]}for v in (0.,7.)]}
    compiled['links'] += [
        {'id':'collar-closure','piece_a':'collar','edge_a':'left','piece_b':'collar','edge_b':'right',
            'kind':'closure','orientation':'reverse'},
        {'id':'neck-attachment','piece_a':'collar','edge_a':'neck-base','piece_b':'neck-part',
            'edge_b':'actual-neck','kind':'permanent','orientation':'forward'}]
    uv=[[0.,0.],[6.,0.],[12.,0.],[0.,7.],[6.,7.],[12.,7.]]
    cage={'uv_cm':uv,'triangles':[[0,1,4],[0,4,3],[1,2,5],[1,5,4]],
        'target_cm':[world([u,0.,9.+v])for u,v in uv]}
    guides['garment.coat']['panels']['collar']=cage
    guides['garment.coat']['semantics_sha256']=digest({pid:row['semantics']for pid,row in compiled['textiles'].items()})
    requests.append({'id':'coat.neck','component_id':'garment.coat','layer':'outer','body_landmark':'neck'})
    return compiled,body,guides,requests,world


class CollarMeasurementGuideDispatch(unittest.TestCase):
    def propose(self,items):
        return propose_measurement_paths(*items[:4],configuration={'wearing_configuration':'open_front'})

    def test_planar_cage_covers_complete_row_and_retains_unqualified_proposal(self):
        items=collar_fixture();before=digest(items[:4]);result=self.propose(items)
        self.assertEqual(result['diagnostics'],[])
        row=next(row for row in result['proposals']if row['id']=='coat.neck')
        self.assertEqual(row['body_girth_cm'],14.);self.assertEqual(row['source_material_length_cm'],12.)
        proof=row['source_spans'][0]['guide_source_row']
        self.assertEqual(proof['representation'],'EXPLICIT_UV_CAGE')
        self.assertGreater(len(proof['source_uv_polyline_cm']),2)
        self.assertIn([6.,0.],proof['source_uv_polyline_cm'])
        self.assertTrue(all(abs(height-9.)<1e-12 for height in row['homology'][0]['guide_body_frame_height_cm']))
        self.assertFalse(row['admissible_for_fit']);self.assertEqual(row['qualification'],'NONE')
        self.assertNotIn('arc_sections',items[2]['garment.coat']['panels']['collar'])
        self.assertEqual(digest(items[:4]),before)

    def test_planar_endpoints_do_not_hide_nonplanar_cage_interior(self):
        items=collar_fixture();items[2]['garment.coat']['panels']['collar']['target_cm'][1][2]+=1.
        before=digest(items[:4]);result=self.propose(items)
        self.assertEqual([row['id']for row in result['proposals']],['coat.chest'])
        diagnostic=result['diagnostics'][0]
        options=diagnostic['source_open_collar_options']
        self.assertTrue(all(row['body_girth_cm']is None for row in options))
        self.assertEqual(options[0]['guide_body_frame_height_cm'][0],9.)
        self.assertEqual(options[0]['guide_body_frame_height_cm'][-1],9.)
        self.assertGreater(max(options[0]['guide_body_frame_height_cm']),9.)
        self.assertEqual(digest(items[:4]),before)

    def test_missing_malformed_mixed_or_uncovered_cage_is_localized(self):
        for mutation in ('unsupported','malformed','mixed','uncovered','duplicate','overlap'):
            items=collar_fixture();frame=items[2]['garment.coat']['panels']['collar']
            if mutation=='unsupported':frame.clear();frame['origin_cm']=[0.,0.,0.]
            elif mutation=='malformed':frame['target_cm'].pop()
            elif mutation=='mixed':frame['arc_sections']=[]
            elif mutation=='uncovered':frame['triangles']=frame['triangles'][:2]
            elif mutation=='duplicate':frame['triangles'].append(copy.deepcopy(frame['triangles'][0]))
            else:
                frame['uv_cm']+=copy.deepcopy(frame['uv_cm'])
                frame['target_cm']+=copy.deepcopy(frame['target_cm'])
                frame['target_cm'][7][2]+=1.
                frame['triangles'] += [[index+6 for index in triangle]for triangle in frame['triangles'][:]]
            before=digest(items[:4]);result=self.propose(items)
            with self.subTest(mutation=mutation):
                self.assertEqual([row['id']for row in result['proposals']],['coat.chest'])
                self.assertEqual(result['diagnostics'][0]['code'],'HOMOLOGOUS_SOURCE_PATH_NEEDS_DATA')
                self.assertIn('source_open_collar_options_missing',result['diagnostics'][0])
                self.assertEqual(digest(items[:4]),before)

    def test_arc_guide_retains_full_row_breaks_and_refuses_malformed_data(self):
        items=collar_fixture();world=items[4]
        frame={'arc_sections':[{'v_cm':v,'arc_offset_cm':0.,'curve_cm':[
            world([0.,0.,9.+v]),world([6.,0.,9.+v]),world([12.,0.,9.+v])]}for v in (0.,7.)]}
        items[2]['garment.coat']['panels']['collar']=frame
        result=self.propose(items);row=next(row for row in result['proposals']if row['id']=='coat.neck')
        self.assertEqual(row['source_spans'][0]['guide_source_row']['representation'],'ARC_SECTIONS')
        self.assertIn([6.,0.],row['source_spans'][0]['guide_source_row']['source_uv_polyline_cm'])
        del frame['arc_sections'][0]['curve_cm']
        result=self.propose(items)
        self.assertEqual([row['id']for row in result['proposals']],['coat.chest'])
        self.assertIn('malformed',result['diagnostics'][0]['source_open_collar_options_missing'])
