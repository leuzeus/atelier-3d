import copy,unittest
from a3d.core import StudioError,contract,digest
from a3d.regional_cloth import regional_weights
from a3d.sewing import validate_recipe
from tests.test_sewing import sources

def configuration():
    return {'profiles':[{'id':name,'source_ref':'synthetic coupon hypothesis','status':'hypothesis',
        'structural_weight':weight,'shear_weight':weight,'bending_weight':weight} for name,weight in (('cloth',0.),('reinforced',1.))],
        'default_profile':'cloth','assignments':[{'piece':'back','profile':'reinforced'}],
        'reinforcements':[{'piece':'front','edge':'right','profile':'reinforced','width_cm':2}],
        'ceilings':{k+'_stiffness_max':100 for k in ('tension','compression','shear','bending')}}

class RegionalTests(unittest.TestCase):
    def test_shared_profiles_and_local_edge_falloff(self):
        payload={'rest_cm':[[0,0,0],[10,0,0],[9,1,0],[0,0,1000]],'panels':{
            'front':{'indices':[0,1,2],'edges':{'right':[1,2]}},'back':{'indices':[3],'edges':{}}}}
        weights,receipt=regional_weights(payload,configuration())
        self.assertEqual(weights['bending'],[0,1,1,1])
        self.assertEqual(receipt['anisotropic_warp_weft'],'NOT_IMPLEMENTED')
        config=configuration();config['profiles'][1]['bending_weight']=.5
        self.assertNotEqual(receipt['configuration_sha256'],regional_weights(payload,config)[1]['configuration_sha256'])

    def test_recipe_rejects_unknown_sources_duplicate_profiles_and_low_ceilings(self):
        data,recipe=sources();recipe['phases']['mount']['regional_stiffness']=configuration()
        validate_recipe(data,recipe)
        for mode in ('profile','piece','edge','ceiling','range'):
            r=copy.deepcopy(recipe);c=r['phases']['mount']['regional_stiffness']
            if mode=='profile':c['profiles'].append(c['profiles'][0])
            if mode=='piece':c['assignments'][0]['piece']='invented'
            if mode=='edge':c['reinforcements'][0]['edge']='invented'
            if mode=='ceiling':c['ceilings']['tension_stiffness_max']=.001
            if mode=='range':c['profiles'][0]['bending_weight']=1.1
            with self.assertRaises(StudioError):validate_recipe(data,r)

    def test_uniform_recipe_and_cut_identity_survive_profile_change(self):
        data,recipe=sources();before=digest({k:recipe[k] for k in ('mesh','placements','seams','pins')})
        validate_recipe(data,recipe)
        recipe['phases']['mount']['regional_stiffness']=configuration();validate_recipe(data,recipe)
        self.assertEqual(before,digest({k:recipe[k] for k in ('mesh','placements','seams','pins')}))

    def test_ambiguous_vertex_mapping_refused(self):
        payload={'rest_cm':[[0,0,0]],'panels':{'front':{'indices':[0],'edges':{}},'back':{'indices':[0],'edges':{}}}}
        c=configuration();c['reinforcements']=[]
        with self.assertRaises(StudioError):regional_weights(payload,c)
