import copy,unittest
from a3d.sewing import permanent_support_groups,weld_permanent
from a3d.core import StudioError

class SeamSupportTests(unittest.TestCase):
    def test_transitive_shared_corner_is_deterministic_and_source_unchanged(self):
        payload={'seams':{'a':{'kind':'permanent','pairs':[[4,1],[8,4],[3,2],[1,4]]},
                         'b':{'kind':'permanent','pairs':[[8,9]]}}}
        before=copy.deepcopy(payload)
        self.assertEqual(permanent_support_groups(payload),[[1,4,8,9],[2,3]])
        self.assertEqual(payload,before)
        payload['seams']['a']['pairs'].reverse()
        self.assertEqual(permanent_support_groups(payload),[[1,4,8,9],[2,3]])

    def test_openings_detachables_and_temporary_closures_do_not_share_support(self):
        payload={'seams':{'p':{'kind':'permanent','pairs':[[0,1]]},
                         'c':{'kind':'closure','pairs':[[1,2]]},
                         'd':{'kind':'detachable','pairs':[[2,3]]}},
                 'fitting_tacks':[{'pairs':[[1,2]]}]}
        self.assertEqual(permanent_support_groups(payload),[[0,1]])
        self.assertEqual(permanent_support_groups({'seams':{}}),[])

    def test_historical_residual_is_never_admitted_as_a_consolidated_seam(self):
        # Historical 01f reported 65.9 mm residual; normal consolidation is 1.5 mm.
        with self.assertRaisesRegex(StudioError,'refusing forced weld'):
            weld_permanent([[0,0,0],[.0659,0,0]],[],{'s':{'kind':'permanent','pairs':[[0,1]]}},.0015)
