"""Prepare existing source-bound textile inputs through the public compiler.

This writes a fresh proposal directory only. The existing guide generator,
planner and template producer retain their contracts and budgets. Collider
snapshots and mesh mapping remain real native dispatcher responsibilities.
"""
import copy

from .core import StudioError, atomic_json, contract, digest, inside, read_json, sha
from .garment_guide_policy import (
    _project_inputs, _project_seam_recipes, guide_generator_identity,
    prepare_project_guide_policy, reconstruct_guide_policy,
)
from .garment_planner import plan_assembly
from .textile_executor import prepare_component_templates


def prepare_project_component_preparation(project, compilation, parameters_path,
                                          standard_recipe_path, output_dir):
    """Produce reconstructable proposals, never native placement admission.

    Parameters use the existing component-parameter mapping without coordinate
    overrides. The private project readers are reused narrowly to authenticate
    the completed native body and declared seam recipes, not to create origins.
    Refused producers retain their real exception message and the known phase.
    Partial output directories are preserved and must not be silently reused.
    """
    phase = 'INPUTS'
    artifacts = {}
    guides = {}
    try:
        for name, value in (('parameters_path', parameters_path),
                            ('standard_recipe_path', standard_recipe_path),
                            ('output_dir', output_dir)):
            if not isinstance(value, str) or not value:
                raise StudioError('Component preparation requires explicit '+name)
        output = inside(project.root, output_dir, False)
        if output.exists():
            raise StudioError('Component preparation output already exists; preserve it and choose a fresh directory')
        if not isinstance(compilation, dict) or compilation.get('status') != 'READY_TO_PLAN':
            raise StudioError('Component preparation requires a complete current source compilation')
        parameters_file = inside(project.root, parameters_path)
        standard_file = inside(project.root, standard_recipe_path)
        for file in (parameters_file, standard_file):
            if file.is_relative_to(output):
                raise StudioError('Component preparation inputs cannot be inside its fresh output directory')
        parameters_ref = {'path': parameters_path, 'sha256': sha(parameters_file)}
        standard_ref = {'path': standard_recipe_path, 'sha256': sha(standard_file)}
        parameters = read_json(parameters_file)
        if not isinstance(parameters, dict):
            raise StudioError('Component preparation parameters must be the explicit component mapping')
        standard = contract('sewing-recipe', read_json(standard_file))
        immutable = digest([compilation, parameters, standard])

        phase = 'GUIDE_POLICY'
        policy, policy_evidence = prepare_project_guide_policy(project, compilation, parameters)
        # These existing readers recheck the source compilation, packages and
        # canonical native receipt rather than trusting a profile file alone.
        profile, geometry, geometry_ref, source_data, origin = _project_inputs(project, compilation)
        if origin != policy_evidence['native_body_origin']:
            raise StudioError('Native body origin changed during component preparation')
        recipes = _project_seam_recipes(project, policy['components'])
        source_identity = digest([profile, geometry, geometry_ref, source_data, recipes, origin])

        phase = 'GUIDE_RECONSTRUCTION'
        guides, guide_report = reconstruct_guide_policy(compilation, profile, geometry,
            geometry_ref, source_data, policy, source_seam_recipes=recipes)
        phase = 'ASSEMBLY_PLAN'
        assembly = plan_assembly(compilation['assembly_spec'], capabilities=['coupled_multilayer'])

        def recheck():
            if (sha(parameters_file) != parameters_ref['sha256'] or
                    sha(standard_file) != standard_ref['sha256']):
                raise StudioError('Component preparation parameters or standard recipe artifact changed')
            if digest([compilation, parameters, standard]) != immutable:
                raise StudioError('Component preparation mutated its immutable source inputs')
            current = _project_inputs(project, compilation)
            current_recipes = _project_seam_recipes(project, policy['components'])
            if digest([*current[:4], current_recipes, current[4]]) != source_identity:
                raise StudioError('Component preparation source, native body or seam recipe changed')
            if guide_generator_identity() != policy['generator_code_sha256']:
                raise StudioError('Component preparation guide generator code changed')

        phase = 'SOURCE_RECHECK'
        recheck()
        dossier_ref = copy.deepcopy(compilation['source_ref'])
        dossier_file = inside(project.root, dossier_ref['path'])
        dossier = read_json(dossier_file)
        sources = {row['id']: {'source_ref': copy.deepcopy(row['package_source_ref']),
                             'data': source_data[row['id']]}
                   for row in compilation['components'] if row['pipeline'] == 'PATTERN_SEWN'}
        phase = 'TEMPLATE_OUTPUT'
        try:
            output.mkdir(parents=True, exist_ok=False)
        except FileExistsError as error:
            raise StudioError('Component preparation output already exists; preserve it and choose a fresh directory') from error

        def save(name, value):
            file = output/name
            atomic_json(file, value)
            return {'path': file.relative_to(project.root).as_posix(), 'sha256': sha(file)}

        artifacts = {'guide_policy': save('guide-policy.json', policy),
                     'guides': save('guides.json', guides),
                     'assembly_plan': save('assembly-plan.json', assembly)}
        compiler_inputs = {'assembly_plan_ref': artifacts['assembly_plan'],
                          'guides_ref': artifacts['guides'],
                          'production_spec_ref': copy.deepcopy(compilation['specification_source_ref']),
                          'standard_recipe_ref': standard_ref, 'dossier_ref': dossier_ref}
        phase = 'COMPONENT_TEMPLATES'
        templates = prepare_component_templates(assembly, sources, guides, standard,
                                                dossier, dossier_ref, compiler_inputs)
        phase = 'FINAL_RECHECK'
        recheck()
        for ref in [*artifacts.values(), *compiler_inputs.values()]:
            if sha(inside(project.root, ref['path'])) != ref['sha256']:
                raise StudioError('Component preparation compiler artifact changed: '+ref['path'])
        artifacts['templates'] = save('component-templates.json', templates)
        guide_report = {**guide_report, 'native_body_origin': copy.deepcopy(origin),
                        'policy_ref': artifacts['guide_policy'], 'parameters_ref': parameters_ref}
        artifacts['guide_report'] = save('guide-report.json', guide_report)
        return {'version': 1, 'status': templates['status'], 'artifacts': artifacts,
                'diagnostics': copy.deepcopy(templates['diagnostics']),
                'parameters_ref': parameters_ref, 'compiler_inputs': compiler_inputs,
                'native_body_origin': copy.deepcopy(origin), 'body_ref': copy.deepcopy(policy['body_ref']),
                'geometry_ref': copy.deepcopy(geometry_ref), 'qualification': 'NONE',
                'planning_capability': {'coupled_multilayer': 'PROPOSAL_ONLY',
                                        'native_path': 'NOT_QUALIFIED'},
                'placement': 'NOT_QUALIFIED', 'simulation': 'NOT_EXECUTED', 'fitting': 'NOT_EXECUTED',
                'acceptance': 'NOT_GRANTED', 'source_mutated': False,
                'native_bindings_required': ['BODY_COLLIDER_SNAPSHOT', 'NATIVE_REGULAR_MESH_MAP',
                                             'COLLISION_ENVELOPE_REVIEW']}
    except StudioError as error:
        error.preparation_phase = phase
        error.diagnostic = {**getattr(error, 'diagnostic', {}), 'phase': phase,
                            'qualification': 'NONE', 'simulation': 'NOT_EXECUTED',
                            'fitting': 'NOT_EXECUTED', 'acceptance': 'NOT_GRANTED'}
        if artifacts:
            error.diagnostic['partial_artifacts'] = copy.deepcopy(artifacts)
        incomplete = {cid: {key: copy.deepcopy(row[key])
                           for key in ('status', 'pending_pieces', 'diagnostics') if key in row}
                      for cid, row in guides.items() if row.get('status') != 'GARMENT_GUIDES_PREPARED'}
        if incomplete:
            error.diagnostic['guide_diagnostics'] = incomplete
        raise
