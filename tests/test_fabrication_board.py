import copy
import xml.etree.ElementTree as ET
from a3d.core import StudioError, atomic_json, read_json
from a3d.planning import build_board, admission
from a3d.board_contract import prepare_exploded, register_exploded, validate_patterns
from tests.support import ready_project, construction_dossier, prepare_synthetic_exploded
from tests.test_core import Case


class FabricationBoardTests(Case):
    def setUp(self):
        super().setUp()
        self.p=ready_project(self.root,garment=True,approve_board=False)
        self.d=read_json(self.p.data/'evidence/construction.json')

    def build(self):
        atomic_json(self.p.data/'evidence/construction.json',self.d)
        return build_board(self.p,'.a3d/evidence/construction.json')

    def test_manufacturing_lines_labels_and_common_scale_are_rendered(self):
        result=self.build()
        manifest=read_json(self.p.root/self.p.state()['evidence']['construction-board']['path'])
        svg=(self.p.root/manifest['image']).read_text(encoding='utf-8')
        for value in ('Couture / piqûre','Pli / milieu','Droit-fil','crans appariés','NOMENCLATURE','Synthetic front','test cotton'):
            self.assertIn(value,svg)
        dom=ET.fromstring(svg)
        for cls in ('fold-line','grain-direction','assembly-notch','stitch-line'):
            self.assertTrue(any(n.get('class')==cls for n in dom.iter()),cls)
        scales={n.get('data-scale') for n in dom.iter() if n.get('data-piece')}
        self.assertEqual(len(scales),1)
        self.assertNotIn('indépendantes',svg)

    def test_missing_fabrication_metadata_blocks_board(self):
        self.d['components']['garment.coat']['pieces'][0].pop('pattern')
        with self.assertRaisesRegex(StudioError,'Manufacturing patterns'):
            self.build()

    def test_declared_margin_must_exist_in_drawing(self):
        self.d['components']['garment.coat']['pieces'][0]['seam_allowance_cm']=2
        with self.assertRaisesRegex(StudioError,'cut margin'):
            self.build()

    def test_self_intersecting_cut_contour_is_rejected(self):
        self.d['components']['garment.coat']['pieces'][0]['pattern']['cut_outline_cm']=[[-1,-1],[21,41],[21,-1],[-1,41]]
        with self.assertRaisesRegex(StudioError,'simple nondegenerate'):
            self.build()

    def test_out_of_piece_fold_is_rejected(self):
        self.d['components']['garment.coat']['pieces'][0]['pattern']['folds'][0]['line_cm'][1]=[100,100]
        with self.assertRaisesRegex(StudioError,'Fold line'):
            self.build()

    def test_missing_paired_notch_is_rejected(self):
        self.d['components']['garment.coat']['pieces'][0]['pattern']['assembly_marks'].pop()
        with self.assertRaisesRegex(StudioError,'matching assembly marks'):
            self.build()

    def test_notches_follow_reverse_sewing_orientation(self):
        self.d['components']['garment.coat']['pieces'][1]['pattern']['assembly_marks'][0]['position']=0.3
        with self.assertRaisesRegex(StudioError,'seam orientation'):
            self.build()

    def test_fold_absence_must_be_explicit_not_invented(self):
        pattern=self.d['components']['garment.coat']['pieces'][0]['pattern']
        pattern['folds']=[]; pattern['fold_notes']='No fold required for this synthetic cutting choice'
        prepare_synthetic_exploded(self.p,self.d)
        self.build()
        pattern.pop('fold_notes')
        with self.assertRaises(StudioError): self.build()

    def test_proportion_drift_blocks_board(self):
        self.d['proportion_checks'][0]['view_spans_px'][0][1]=[55,0]
        with self.assertRaisesRegex(StudioError,'proportion mismatch'):
            self.build()

    def test_equal_image_ratio_is_not_a_meaningful_measurement(self):
        check=self.d['proportion_checks'][0]
        check['reference_spans_px'][0]=copy.deepcopy(check['reference_spans_px'][1])
        with self.assertRaisesRegex(StudioError,'distinct spans'):
            self.build()

    def test_every_view_needs_measured_proportions(self):
        self.d['proportion_checks'][-1]['view']='front'
        with self.assertRaisesRegex(StudioError,'front, side, back and exploded'):
            self.build()

    def test_orthographic_subject_height_cannot_change_between_views(self):
        self.d['orthographic']['front']['subject_height_cm']=170
        with self.assertRaisesRegex(StudioError,'same subject height'):
            self.build()

    def test_every_exploded_piece_needs_a_label(self):
        self.d['exploded']['annotations'].pop()
        with self.assertRaisesRegex(StudioError,'every piece exactly once'):
            self.build()

    def test_exploded_image_requires_codex_image_receipt(self):
        self.d['exploded'].pop('generation_evidence_key')
        with self.assertRaisesRegex(StudioError,'registered Codex Image'):
            self.build()

    def test_changed_cutting_requires_new_image_request(self):
        self.d['components']['garment.coat']['pieces'][0]['characteristics']=['Changed cutting characteristic']
        with self.assertRaisesRegex(StudioError,'Cutting design changed'):
            self.build()

    def test_request_includes_original_images_and_exact_inventory(self):
        request=prepare_exploded(self.p,'.a3d/evidence/construction.json')['request']
        self.assertEqual(request['provider'],'Codex Image')
        self.assertEqual(request['referenced_image_paths'],[str(self.p.data/'source/original.png')])
        for piece in self.d['components']['garment.coat']['pieces']:
            self.assertIn(piece['label'],request['prompt'])
            self.assertIn(piece['id'],request['prompt'])

    def test_comfy_provenance_is_not_accepted_for_exploded(self):
        key=self.d['exploded']['generation_evidence_key']
        path=self.p.root/self.p.state()['evidence'][key]['path']
        receipt=read_json(path); receipt['provider']='ComfyUI'; atomic_json(path,receipt)
        self.p.evidence(key,path.relative_to(self.p.root).as_posix())
        with self.assertRaisesRegex(StudioError,'Codex Image provenance'):
            self.build()

    def test_legacy_approved_board_does_not_bypass_new_contract(self):
        rec=self.p.state()['evidence']['construction-board']
        manifest=read_json(self.p.root/rec['path'])
        manifest.pop('board_contract_version')
        atomic_json(self.p.root/rec['path'],manifest)
        self.p.evidence('construction-board',rec['path'])
        self.p.gate('construction',True,'Synthetic legacy approval',['construction-board'],'test:legacy')
        result=admission(self.p)
        self.assertFalse(result['admitted'])
        self.assertIn('Legacy board',str(result['issues']))

    def test_unequal_pattern_sizes_keep_their_relative_scale(self):
        from a3d.board_render import render
        garment=read_json(self.p.data/'source/package/garment.json')
        garment['pieces']['sleeve-left']['vertices']=[[x/2,y/2] for x,y in garment['pieces']['sleeve-left']['vertices']]
        p=self.d['components']['garment.coat']['pieces'][2]
        p['dimensions_cm']=[10,20]
        p['pattern']['cut_outline_cm']=[[x/2,y/2] for x,y in p['pattern']['cut_outline_cm']]
        manifest=read_json(self.p.root/self.p.state()['evidence']['construction-board']['path'])
        svg=render(self.p,self.d,{'garment.coat':garment},manifest['source_references'])
        polygons={n.get('data-piece'):n for n in ET.fromstring(svg).iter() if n.get('data-piece')}
        def width(key):
            xs=[float(v.split(',')[0]) for v in polygons[key].get('points').split()]
            return max(xs)-min(xs)
        self.assertAlmostEqual(width('garment.coat/front')/width('garment.coat/sleeve-left'),2,places=4)

    def test_invalid_cutting_is_rejected_before_image_request(self):
        self.d['components']['garment.coat']['pieces'][0]['dimensions_cm']=[200,400]
        atomic_json(self.p.data/'evidence/construction.json',self.d)
        with self.assertRaisesRegex(StudioError,'dimensions must match'):
            prepare_exploded(self.p,'.a3d/evidence/construction.json')
