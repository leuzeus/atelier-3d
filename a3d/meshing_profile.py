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
