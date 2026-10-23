from unittest.mock import patch

from a3d.board_contract import validate_patterns
from a3d.core import atomic_json,read_json
from tests.test_core import Case
from tests.textile_fixtures import source,annotate_dossier,response_control,RESPONSE_CONTROLS
from a3d.core import digest
from blender.cloth_contacts import precise_self_contacts
import tests.support as support


class TextileFixtureContracts(Case):
    def test_causal_response_controls_are_admissible_before_physics_and_preserve_the_source(self):
        rest=[[0.,0.,0.],[2.,0.,0.],[2.,8.,0.],[0.,8.,0.]]
        initial={'rest_cm':rest+[[x,y,1000.] for x,y,z in rest],
            'placed_cm':[[x,-2.,20.+y] for x,y,z in rest]+[[x+2.,-2.,20.+y] for x,y,z in rest],
            'faces':[[0,1,2],[0,2,3],[4,5,6],[4,6,7]],'pins':{},
            'panels':{'inner':{'indices':[0,1,2,3],'edges':{'top':[3,2]}},
                'outer':{'indices':[4,5,6,7],'edges':{'top':[7,6]}}},
            'seams':{'interface':{'kind':'permanent','piece_a':'inner','piece_b':'outer','pairs':[[1,4],[2,7]]}}}
        plan={'supports':{'temporary':[],'functional':[],'drape':[{'id':'top-'+pid,'piece':pid,'edge':'top',
            'weight':.7,'source_ref':'synthetic:control-support'} for pid in ('inner','outer')]}}
        before=digest([initial,plan])
        for case in RESPONSE_CONTROLS:
            with self.subTest(case=case):
                payload,supports=response_control(initial,plan,case)
                admission=precise_self_contacts(payload,payload['placed_cm'],.15,.3)
                self.assertTrue(admission['ok'],admission)
                if case=='SOURCE_COINCIDENT_NO_SUPPORT_CONTROL':self.assertEqual(payload['pins'],{})
                else:self.assertEqual(set(payload['pins']),{'2','3','6','7'})
        self.assertEqual(digest([initial,plan]),before)

    def test_ordered_belt_and_coupled_use_real_package_and_board_contracts(self):
        original=support.construction_dossier
        def dossier(project,garment=False):
            file=project.data/'source/package/garment.json';data=read_json(file)
            atomic_json(file,{'seams':[]})
            try:result=original(project,garment)
            finally:atomic_json(file,data)
            return annotate_dossier(result,data)
        for case in ('ordered','belt','coupled'):
            with self.subTest(case=case),patch('tests.support.garment_source',side_effect=lambda path:source(path,case)),\
                    patch('tests.support.construction_dossier',side_effect=dossier):
                project=support.ready_project(self.root/case,True)
                data=read_json(project.data/'source/package/garment.json')
                board=read_json(project.data/'evidence/construction.json')
                validate_patterns(board,{'garment.coat':data})
                self.assertEqual(set(data['pieces']),{row['id'] for row in board['components']['garment.coat']['pieces']})
                expected={'ordered':'detachable','belt':'closure','coupled':'permanent'}[case]
                self.assertEqual(data['seams'][0]['kind'],expected)
                if case=='belt':
                    marks=board['components']['garment.coat']['pieces'][0]['pattern']['assembly_marks']
                    self.assertEqual(len(marks),1);self.assertEqual(marks[0]['position'],.5)
