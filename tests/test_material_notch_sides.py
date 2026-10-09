"""Material notch positions on the two distinct sides of a unary seam."""
import copy
import math
import unittest
from a3d.core import StudioError,digest
from a3d.board_contract import assembly_mark_position,validate_patterns
from a3d.pattern_preparation import audit_source,prepare_regular_boundaries
from a3d.sewing import edge_chain,sample_chain
from tests.test_sewing import sources
from tests.test_pattern_preparation import source_dossier


def fixture():
    data,recipe=sources()
    # Opposite contour directions form a sewable reverse unary seam.
    data['pieces']['front']['edges']['right'].reverse()
    data['seams']=[{'id':'unary','piece_a':'front','edge_a':'left','piece_b':'front','edge_b':'right',
                   'orientation':'reverse','kind':'permanent'}]
    recipe['seams']={'unary':{'kind':'permanent','ease_b_over_a':0.,'tolerance_relative':.01}}
    dossier=source_dossier(data)
    mark=next(p for p in dossier['components'][data['component_id']]['pieces']if p['id']=='front')['pattern']['assembly_marks'][0]
    mark.update(position=.5,seam_side_positions={'a':.23,'b':.77})
    for p in dossier['components'][data['component_id']]['pieces']:p['pattern']['folds']=[]
    return data,recipe,dossier,mark


class MaterialNotchSides(unittest.TestCase):
    def test_unary_side_positions_keep_exact_material_points_in_source_audit_and_common_sampler(self):
        data,recipe,dossier,mark=fixture();before=digest([data,recipe,dossier])
        validate_patterns(dossier,{data['component_id']:data})
        report=audit_source(data,recipe,dossier)
        self.assertEqual(report['status'],'SOURCE_AUDITED',report['issues'])
        self.assertEqual(report['seams'][0]['notches'][0]['a'],.23)
        self.assertEqual(report['seams'][0]['notches'][0]['b'],.77)
        config={'spacing_cm':2.,'min_spacing_cm':1.,'refinement_distance_cm':3.,
                'max_vertices':10000,'target_min_angle_degrees':15.}
        boundaries,seams,sampling=prepare_regular_boundaries(data,recipe,config,dossier)
        self.assertFalse(sampling['ambiguous_source_notches'])
        self.assertEqual({row['common_parameter']for row in sampling['source_notches']},{.23,1-.77})
        for row in sampling['source_notches']:
            side=row['side'];edge=data['seams'][0]['edge_'+side]
            expected=sample_chain(edge_chain(data['pieces']['front'],edge)[1],mark['seam_side_positions'][side])
            self.assertEqual(row['source_uv_cm'],expected)
            self.assertEqual(row['binding']['kind'],'BOUNDARY_SEGMENT')
            self.assertEqual(row['binding']['index_space'],'PIECE_BOUNDARY_LOCAL')
            self.assertNotIn('common_sample',row)
            self.assertNotIn('derived_boundary_vertex',row)
            binding=row['binding']
            actual=[sum(w*boundaries['front']['polygon'][i][axis] for w,i in zip(
                binding['weights'],binding['boundary_vertices']))for axis in range(2)]
            self.assertEqual(actual,row['reconstructed_uv_cm'])
            self.assertEqual(math.dist(actual,expected),row['numeric_reconstruction_residual_cm'])
        self.assertEqual(digest([data,recipe,dossier]),before)

    def test_legacy_ambiguous_unary_mark_is_still_missing_data_and_midpoint_remains_supported(self):
        data,recipe,dossier,mark=fixture();mark.pop('seam_side_positions');mark['position']=.23
        report=audit_source(data,recipe,dossier)
        self.assertIn('SELF_SEAM_NOTCH_SIDE_UNSPECIFIED',[row['code']for row in report['issues']])
        mark['position']=.5
        self.assertEqual(audit_source(data,recipe,dossier)['status'],'SOURCE_AUDITED')

    def test_explicit_side_positions_refuse_wrong_owner_orientation_missing_side_and_nonfinite_fraction(self):
        data,_,dossier,mark=fixture();seam=data['seams'][0]
        for positions in (None,{'a':.23},{'a':.23,'b':.23},{'a':float('nan'),'b':.77},
                          {'a':True,'b':0.},{'a':.23,'b':.77,'c':.1}):
            changed={**copy.deepcopy(mark),'seam_side_positions':positions}
            with self.subTest(positions=positions),self.assertRaises(StudioError):
                assembly_mark_position(changed,seam,'a')
        with self.assertRaises(StudioError):assembly_mark_position(mark,{**seam,'piece_b':'back'},'a')
        mark['seam_side_positions']['b']=.23
        with self.assertRaises(StudioError):validate_patterns(dossier,{data['component_id']:data})


if __name__=='__main__':unittest.main()
