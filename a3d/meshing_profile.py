"""Explicit opt-in ties sourced boundary grading to permanent-birth meshing."""
import time
from .core import ROOT, StudioError, digest, read_json, validate
from .meshing_envelope import MeshingEnvelope

MODE = 'SYNCHRONIZED_GRADED_V1'


def prepare_profile(data, recipe, regular_mesh, budgets):
    """Build explicit native inputs from the full source; no admission or execution."""
    import copy
    profile={'version':1,'mode':MODE,'piece_ids':sorted(data['pieces']),
             'budgets':copy.deepcopy(budgets)}
    validate_profile(profile,data['component_id'],recipe,regular_mesh)
    return profile


def prepare_recovery_profile(data, recipe, preparation, parameters):
    """Propose fresh derived-mesh inputs; never change patterns or admit a mesh.

    Parameters are explicit resource/refinement limits. The native caller must
    derive and rebind its actual map; no old mesh or mapping proof is reusable.
    """
    import copy
    before=digest([data,recipe,preparation,parameters])
    contract_schema=read_json(ROOT/'schemas/pattern-preparation.schema.json')
    validate(preparation,contract_schema)
    if (not isinstance(parameters,dict) or set(parameters)!=
            {'max_vertices','quality_refinement','budgets'}):
        raise StudioError('Recovery meshing needs exact vertex, refinement and work budgets')
    if data['component_id']!=recipe['component_id'] or preparation['component_id']!=data['component_id']:
        raise StudioError('Recovery meshing component identities differ')
    cap=parameters['max_vertices']
    if type(cap)is not int or not 20<=cap<=min(30000,recipe['mesh']['max_vertices'],preparation['regular_mesh']['max_vertices']):
        raise StudioError('Recovery meshing cannot enlarge the existing vertex budgets')
    refinement=parameters['quality_refinement']
    if (not isinstance(refinement,dict) or set(refinement)!=
            {'target_min_angle_degrees','max_passes','max_added_vertices'}):
        raise StudioError('Recovery meshing requires complete explicit quality refinement')
    validate(refinement,read_json(ROOT/'schemas/sewing-recipe.schema.json')['properties']['mesh']['properties']['quality_refinement'])
    gate=max(recipe['mesh']['min_angle_degrees'],preparation['regular_mesh'].get('target_min_angle_degrees',15.))
    if refinement['target_min_angle_degrees']<gate:
        raise StudioError('Recovery meshing cannot lower the unchanged source angle gate')
    proposed_recipe=copy.deepcopy(recipe);proposed=copy.deepcopy(preparation)
    proposed_recipe['mesh']['max_vertices']=cap
    proposed_recipe['mesh']['quality_refinement']=copy.deepcopy(refinement)
    proposed['regular_mesh']['max_vertices']=cap
    proposed['meshing_profile']=prepare_profile(data,proposed_recipe,proposed['regular_mesh'],parameters['budgets'])
    validate(proposed,contract_schema)
    if digest([data,recipe,preparation,parameters])!=before:
        raise StudioError('Recovery meshing changed its immutable source inputs')
    return proposed_recipe,proposed,{
        'status':'MESHING_PROFILE_PROPOSAL','source_garment_sha256':digest(data),
        'source_recipe_sha256':digest(recipe),'source_preparation_sha256':digest(preparation),
        'recipe_sha256':digest(proposed_recipe),'preparation_sha256':digest(proposed),
        'profile':profile_binding(proposed['meshing_profile']),
        'native_angle_gate_degrees':gate,'patterns_changed':False,'source_mutated':False,
        'native_mapping':'REQUIRED_REBIND_BEFORE_EXECUTION',
        'qualification':'NONE','simulation':'NOT_EXECUTED','fitting':'NOT_EXECUTED'}


def validate_profile(profile, component_id, recipe, regular_mesh):
    schema=read_json(ROOT/'schemas/pattern-preparation.schema.json')['properties']['meshing_profile']
    validate(profile,schema)
    mesh=recipe['mesh'];refinement=mesh.get('quality_refinement',{})
    maximum=min(mesh['max_vertices'],regular_mesh['max_vertices'])
    if (recipe['component_id']!=component_id or not 20<=maximum<=30000
        or not .2<=regular_mesh['min_spacing_cm']<=1
        or type(refinement.get('max_passes'))is not int or not 1<=refinement['max_passes']<=8
        or type(refinement.get('max_added_vertices'))is not int or not 1<=refinement['max_added_vertices']<=4000):
        error=StudioError('Synchronized meshing requires explicit supported recipe limits')
        error.reason='MESHING_PROFILE_REFUSED';error.status='REFUSED';raise error
    return maximum,refinement['max_passes'],refinement['max_added_vertices']


def _limits(profile, component_id, recipe, regular_mesh):
    maximum,passes,insertions=validate_profile(profile,component_id,recipe,regular_mesh)
    budgets=profile['budgets'];pieces=len(profile['piece_ids'])
    limits={name:budgets['max_'+name]for name in (
        'capture_nodes','capture_bytes','output_nodes','output_bytes','work_steps',
        'sampling_calls','sampling_point_slots','fraction_requests')}
    limits.update(attempted_insertions=insertions,native_cdt_calls=pieces*(passes+1),
        native_remesh_attempts=pieces*passes,native_point_slots=pieces*(passes+1)*maximum)
    return limits,{'native_cdt_calls':passes+1,'native_remesh_attempts':passes}


def create_envelope(profile, component_id, recipe, regular_mesh, *, started_at=None,
                    clock=time.monotonic, stop_requested=None):
    limits,owners=_limits(profile,component_id,recipe,regular_mesh)
    budgets=profile['budgets']
    return MeshingEnvelope(component_id,limits,owner_limits=owners,
        max_seconds=budgets['max_seconds'],clock=clock,started_at=started_at,
        stop_requested=stop_requested)


def verify_envelope(profile, component_id, recipe, regular_mesh, envelope):
    limits,owners=_limits(profile,component_id,recipe,regular_mesh)
    if (not isinstance(envelope,MeshingEnvelope) or envelope.component_id!=component_id
        or dict(envelope.limits)!=limits or dict(envelope.owner_limits)!=owners
        or envelope.deadline>envelope.start+profile['budgets']['max_seconds']):
        error=StudioError('Meshing envelope must retain the declared profile limits and local origin')
        error.reason='MESHING_PROFILE_REFUSED';error.status='REFUSED';raise error
    envelope.check('profile_envelope_binding')


def verify_inventory(profile, data, envelope):
    envelope.check('profile_source_inventory')
    if (data['component_id']!=envelope.component_id or set(profile['piece_ids'])!=set(data['pieces'])):
        error=StudioError('Synchronized meshing profile must declare the exact full source inventory')
        error.reason='MESHING_PROFILE_REFUSED';error.status='REFUSED';raise error
    envelope.check('after_profile_source_inventory')


def profile_binding(profile):
    return {'mode':MODE,'profile_sha256':digest(profile),'qualification':'NONE',
            'clock_scope':'SOURCE_CAPTURE_AND_MESH_BUILD_ONLY_CALLER_LOCAL',
            'source_ids':sorted(profile['piece_ids'])}
