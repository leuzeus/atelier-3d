"""Admission for known Blender entrypoints, not a sandbox for arbitrary Python."""
import ast
from pathlib import Path
from .core import ROOT, StudioError, inside, read_json, sha
from .planning import require_board


def code_for(project_root, operation, arguments):
    payload = dict(project_root=project_root, operation=operation, arguments=arguments)
    return ("# Atelier 3D controlled operation v2\nimport runpy\n"
        f"dispatch = runpy.run_path({str(ROOT / 'blender/bootstrap.py')!r})['dispatch_current']\n"
        f"result = dispatch(**{payload!r})\n")


def parse_code(code):
    try:
        tree = ast.parse(code)
        payload = ast.literal_eval(tree.body[-1].value.keywords[0].value)
        if code != code_for(**payload):
            raise ValueError()
        return payload
    except (SyntaxError, ValueError, AttributeError, KeyError, TypeError, IndexError):
        raise StudioError("Raw Blender code is not admitted in this managed project. Use studio_blender_operation; never substitute procedural geometry for a reviewed route.")


def admit_operation(project, operation, arguments):
    state = project.state()
    if operation == 'bind_component_preparations':
        from .lifecycle import no_pending_operation
        from .core import digest
        from .dressing import _reference
        from .production_dossier import compile_project_dossier
        from .garment_guide_policy import _project_inputs
        no_pending_operation(state)
        expected = {'templates_path', 'body_object', 'body_geometry_ref', 'output_directory', 'policy_path'}
        if set(arguments) not in (expected, expected | {'envelope_review'}):
            raise StudioError('Unexpected/missing source preparation binding arguments')
        if state['stage'] != 'RECONSTRUCTING':
            raise StudioError('Source preparation binding requires active reconstruction')
        require_board(project, state)
        if not isinstance(arguments['body_object'], str) or not arguments['body_object']:
            raise StudioError('Source preparation binding requires the explicit measured body object')
        output = inside(project.root, arguments['output_directory'], False)
        if output.exists() and not (output.is_dir() and (output/'binding.json').is_file()):
            raise StudioError('Native preparation binding stopped before its boundary; preserve it and choose a fresh output directory')
        templates = read_json(inside(project.root, arguments['templates_path']))
        if (templates.get('status') != 'SOURCE_PREPARATION_TEMPLATES_READY'
                or templates.get('prepared_sha256') != digest({k:v for k,v in templates.items() if k!='prepared_sha256'})):
            raise StudioError('Source preparation binding requires exact complete proposal templates')
        inputs = templates.get('compiler_inputs', {})
        if set(inputs) != {'assembly_plan_ref', 'guides_ref', 'production_spec_ref', 'standard_recipe_ref', 'dossier_ref'}:
            raise StudioError('Source preparation binding requires all compiler input references')
        for ref in [*inputs.values(), arguments['body_geometry_ref']]:
            _reference(ref)
            if sha(inside(project.root, ref['path'])) != ref['sha256']:
                raise StudioError('Source preparation binding input changed: '+ref['path'])
        policy = read_json(inside(project.root, arguments['policy_path']))
        compiled = compile_project_dossier(project, inputs['dossier_ref']['path'], inputs['production_spec_ref']['path'])
        _, _, geometry_ref, _, _ = _project_inputs(project, compiled)
        if (templates['body_ref'] != compiled['assembly_spec']['body_ref']
                or arguments['body_geometry_ref'] != geometry_ref
                or policy.get('compiled_sha256') != digest(compiled)
                or policy.get('body_ref') != templates['body_ref'] or policy.get('geometry_ref') != geometry_ref):
            raise StudioError('Source preparation binding belongs to another current source or native body')
        owners = {row['id'] for row in compiled['components'] if row['pipeline']=='PATTERN_SEWN'}
        if set(templates.get('components', {})) != owners:
            raise StudioError('Source preparation binding must cover all exact textile components')
        declared = {name for node in compiled['assembly_spec']['layers']['nodes']
                    if node['kind'] == 'body' for name in node['colliders']}
        if declared != {arguments['body_object']}:
            raise StudioError('Native collider identity differs from the explicit source layer graph')
        if output.exists():
            previous = read_json(output/'binding.json')
            if (previous.get('status') != 'NATIVE_PREPARATION_INPUTS_BOUND'
                    or previous.get('templates') != {'path': arguments['templates_path'],
                                                     'sha256': sha(inside(project.root, arguments['templates_path']))}
                    or previous.get('body_ref') != templates['body_ref']
                    or previous.get('body_geometry_ref') != geometry_ref
                    or previous.get('collider', {}).get('object') != arguments['body_object']
                    or previous.get('guide_reconstruction', {}).get('policy_ref') != {
                        'path': arguments['policy_path'], 'sha256': sha(inside(project.root, arguments['policy_path']))}):
                raise StudioError('Persisted native preparation binding differs from its exact source or body')
            ref = previous.get('run_specification'); _reference(ref)
            if sha(inside(project.root, ref['path'])) != ref['sha256']:
                raise StudioError('Persisted native preparation run specification changed')
        for cid in sorted(owners):
            _, component = project.ready(cid)
            package = {key: component['package'][key] for key in ('path', 'sha256')}
            source = next(row for row in compiled['components'] if row['id'] == cid)['package_source_ref']
            if source != package or templates['components'][cid].get('source_ref') != package:
                raise StudioError('Preparation source package differs from canonical approved component')
        if 'envelope_review' in arguments:
            ref = arguments['envelope_review']; _reference(ref)
            if sha(inside(project.root, ref['path'])) != ref['sha256']:
                raise StudioError('Source preparation binding envelope review changed')
        return
    if operation == 'introduce_body_target':
        from .lifecycle import no_pending_operation
        from .body_context import body_context_descriptor
        no_pending_operation(state)
        if set(arguments) != {'context_path'}:
            raise StudioError('Unexpected/missing measured body context arguments')
        if state['stage'] != 'RECONSTRUCTING':
            raise StudioError('Measured body introduction requires active garment reconstruction')
        require_board(project, state)
        body_context_descriptor(project, arguments['context_path'])
        return
    if operation in ('inspect_reconstructed_part', 'prepare_reconstructed_part', 'run_garment_motion', 'attach_reconstructed_part', 'run_dressing_program'):
        from .lifecycle import no_pending_operation
        no_pending_operation(state)
        if state['stage'] == 'COMPLETE': raise StudioError('Completed project is immutable')
        if set(arguments) != {'profile_path'}:
            raise StudioError('Unexpected/missing native candidate profile arguments')
        if operation in ('inspect_reconstructed_part', 'prepare_reconstructed_part'):
            from .part_preparation import part_descriptor
            part_descriptor(project, arguments['profile_path'], normalize=operation == 'prepare_reconstructed_part')
        elif operation == 'attach_reconstructed_part':
            from .rigid_attachment import rigid_attachment_descriptor
            rigid_attachment_descriptor(project, arguments['profile_path'])
        elif operation == 'run_dressing_program':
            from .dressing_paths import dressing_execution_descriptor
            dressing_execution_descriptor(project, arguments['profile_path'])
        else:
            from .garment_motion import motion_inputs
            motion_inputs(project, arguments['profile_path'])
        return
    if operation in ('export_blender_animation', 'prepare_asset_finishing', 'compose_animated_delivery', 'render_motion_review'):
        from .lifecycle import no_pending_operation
        no_pending_operation(state)
        if set(arguments) != {'profile_path'}:
            raise StudioError('Unexpected/missing asset delivery profile arguments')
        if operation == 'export_blender_animation':
            from .export_profiles import export_descriptor
            export_descriptor(project, arguments['profile_path'])
        elif operation == 'prepare_asset_finishing':
            from .asset_finishing import finishing_descriptor
            finishing_descriptor(project, arguments['profile_path'])
        elif operation == 'render_motion_review':
            from .review_motion import review_motion_descriptor
            review_motion_descriptor(project, arguments['profile_path'])
        else:
            from .animated_delivery import animated_delivery_descriptor
            animated_delivery_descriptor(project, arguments['profile_path'])
        return
    if operation in ('run_material_bench', 'inspect_dressing_plan'):
        from .lifecycle import no_pending_operation
        no_pending_operation(state)
        if state['stage'] == 'COMPLETE': raise StudioError('Completed project is immutable')
        if operation == 'run_material_bench':
            from .material_bench import _load_compiled
            if set(arguments) != {'bench_path', 'output_dir'}:
                raise StudioError('Unexpected/missing material benchmark arguments')
            _load_compiled(project, arguments['bench_path'])
            if inside(project.root, arguments['output_dir'], False).exists():
                raise StudioError('Material benchmark output must be a new directory')
        else:
            from .dressing import _compiled_dressing
            if set(arguments) != {'component_id', 'recipe_path', 'dressing_path'}:
                raise StudioError('Unexpected/missing dressing inspection arguments')
            if state['stage'] != 'RECONSTRUCTING': raise StudioError('Dressing inspection requires active reconstruction')
            require_board(project, state)
            _, component = project.ready(arguments['component_id'])
            if component['route']['selected'] != 'PATTERN_SEWN' or component['stage'] == 'RECONSTRUCTED':
                raise StudioError('Dressing inspection requires an unaccepted sewn component')
            document = _compiled_dressing(project, arguments['dressing_path'])
            if (document['component_id'] != arguments['component_id']
                    or document['bindings']['recipe']['path'] != arguments['recipe_path']):
                raise StudioError('Dressing operation differs from its exact compiled target')
        return
    if operation in ('advance_textile_program', 'transition_textile_group'):
        from .lifecycle import no_pending_operation
        from .textile_executor import load_textile_program, require_textile_program_admission, STAGES
        from blender.textile_executor import _source_relations
        expected = {'program_path'} if operation == 'advance_textile_program' else {'program_path','group_id','stage'}
        if set(arguments) != expected: raise StudioError('Unexpected/missing textile program arguments')
        no_pending_operation(state)
        if state['stage'] != 'RECONSTRUCTING': raise StudioError('Textile execution requires active reconstruction')
        require_board(project, state)
        specification, compiled = load_textile_program(project, arguments['program_path'])
        assembly = read_json(inside(project.root, specification['assembly_plan_ref']['path']))
        require_textile_program_admission(project, specification, assembly)
        _source_relations(state, assembly)
        for component in specification['components']:
            project.ready(component['component_id'])
        if operation == 'transition_textile_group':
            if arguments['stage'] not in STAGES: raise StudioError('Unknown textile group stage')
            if arguments['group_id'] not in {row['group']['id'] for row in compiled['groups']}:
                raise StudioError('Unknown source-bound textile group')
        return
    if operation in ('prepare_body_motion', 'render_asset_review'):
        from .lifecycle import no_pending_operation
        no_pending_operation(state)
        if operation == 'prepare_body_motion':
            from blender.body_motion import prepare_motion_inputs
            if set(arguments) != {'body_target_receipt_path', 'motion_profile_path'}:
                raise StudioError('Unexpected/missing body motion arguments')
            if state['stage'] == 'COMPLETE': raise StudioError('Completed project is immutable')
            prepare_motion_inputs(project, **arguments)
        else:
            from .delivery import delivery_profile
            if set(arguments) != {'profile_path'}: raise StudioError('Unexpected/missing review arguments')
            delivery_profile(project, arguments['profile_path'])
        return
    if operation == 'prepare_body_target':
        from .body_target import target_descriptor
        from .lifecycle import no_pending_operation
        if set(arguments) != {'selection_path', 'target_path'}:
            raise StudioError('Unexpected/missing body target operation arguments')
        if state['stage'] == 'COMPLETE':
            raise StudioError('Completed project is immutable')
        no_pending_operation(state)
        target_descriptor(project, **arguments)
        return
    if operation not in ("prepare", "start_clean_construction", "recover_clean_construction", "inspect_body_source", "prepare_body_reference", "prepare_fitting_envelope", "prepare_fitting_pose", "introduce_fitting_context", "resume", "inspect", "frame_view", "inspect_sewing_failure", "inspect_garment_failure", "inspect_sewing_placement", "inspect_garment_fit", "propose_pattern_adjustment", "verify_legacy_import", "garment", "assemble", "run_script", "restore_checkpoint", "simulate_sewn", "freeze_sewn", "apply_sewn_result", "prepare_sewn_stage", "transition_pattern_assembly", "prepare_pattern_assembly"):
        raise StudioError("Unknown guarded Blender operation")
    required = {"prepare": set(), "resume": set(), "inspect": set(),
        "start_clean_construction":{"working_sha256"},
        "recover_clean_construction":{"recovery_path"},
        "inspect_body_source":{"selection_path"},"prepare_body_reference":{"selection_path"},
        "prepare_fitting_envelope":{"envelope_path"},"prepare_fitting_pose":{"component_id","recipe_path","pose_path"},
        "introduce_fitting_context":{"component_id","recipe_path","fit_path","source_blend","source_sha256"},
        "frame_view": {"component_id", "object_name"},
        "inspect_sewing_failure": {"component_id", "attempt_dir"},
        "inspect_garment_failure": {"component_id", "attempt_dir"},
        "inspect_sewing_placement": {"component_id", "recipe_path"},
        "inspect_garment_fit": {"component_id", "recipe_path", "fit_path"},
        "propose_pattern_adjustment": {"component_id", "recipe_path", "fit_path"},
        "verify_legacy_import": {"package_dir", "checkpoint_receipt"}, "garment": {"package_dir"}, "assemble": {"plan_path"},
        "run_script": {"purpose", "path", "sha256", "component_ids"}, "restore_checkpoint": set(),
        "simulate_sewn": {"component_id", "recipe_path", "phase", "scope"},
        "apply_sewn_result": {"component_id", "recipe_path", "result_path", "result_sha256"},
        "prepare_sewn_stage": {"component_id", "recipe_path", "stage"},
        "transition_pattern_assembly": {"component_id", "recipe_path", "plan_path", "stage"},
        "prepare_pattern_assembly": {"component_id", "recipe_path", "preparation_path"},
        "freeze_sewn": {"component_id", "recipe_path"}}[operation]
    if operation=='simulate_sewn' and 'purpose' in arguments:
        required|={'purpose'}
        if arguments['purpose'] not in ('assembly','fitting'):raise StudioError('Unknown sewing purpose')
    if operation=='prepare_sewn_stage' and arguments.get('stage') not in ('assembly','fitting'):
        raise StudioError('Unknown sewing construction stage')
    if operation=='transition_pattern_assembly' and arguments.get('stage') not in ('migrate','preposition','mount','close','consolidate','relax','drape'):
        raise StudioError('Unknown pattern assembly stage')
    if operation == "garment" and "recipe_path" in arguments:
        required = required | {"recipe_path"}
    if operation == "garment" and "rebuild" in arguments:
        required = required | {"rebuild"}
        if not isinstance(arguments['rebuild'], bool):raise StudioError('rebuild must be a boolean')
    if operation == "garment" and "migrate_legacy" in arguments:
        required = required | {"migrate_legacy"}
        if not isinstance(arguments['migrate_legacy'], bool):
            raise StudioError('migrate_legacy must be a boolean')
        if arguments['migrate_legacy'] and arguments.get('rebuild') is not True:
            raise StudioError('Legacy migration requires explicit rebuild=true')
    if operation == 'garment' and {'legacy_snapshot_sha256', 'legacy_script_receipts'} & set(arguments):
        required |= {'legacy_snapshot_sha256', 'legacy_script_receipts'}
        fingerprint = arguments.get('legacy_snapshot_sha256')
        receipts = arguments.get('legacy_script_receipts')
        if arguments.get('migrate_legacy') is not True:
            raise StudioError('Legacy snapshot archival requires migrate_legacy=true')
        if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(c not in '0123456789abcdef' for c in fingerprint):
            raise StudioError('Legacy snapshot must be the SHA-256 returned by inspect')
        if not isinstance(receipts, list) or not receipts or any(not isinstance(p, str) or not p for p in receipts):
            raise StudioError('Legacy modified mesh requires explicit script receipts')
        if len(set(receipts)) != len(receipts):
            raise StudioError('Legacy script receipts must be unique')
    if operation == 'garment' and 'legacy_checkpoint_receipt' in arguments:
        required |= {'legacy_checkpoint_receipt'}
        if arguments.get('migrate_legacy') is not True:
            raise StudioError('Legacy checkpoint recovery requires migrate_legacy=true')
        if not isinstance(arguments['legacy_checkpoint_receipt'], str) or not arguments['legacy_checkpoint_receipt']:
            raise StudioError('Legacy checkpoint recovery requires an existing receipt path')
    if operation == "run_script" and arguments.get("purpose") == "simulate":
        required = required | {"simulation_plan"}
    if set(arguments) != required:
        raise StudioError("Unexpected/missing operation arguments")
    from .lifecycle import no_pending_operation
    if operation in ('inspect_sewing_failure', 'inspect_garment_failure'):
        from .sewing_diagnostics import inspect_failure
        from .garment_rejections import inspect_rejection
        if arguments['component_id'] not in state['components']:
            raise StudioError('Unknown diagnostic component')
        (inspect_rejection if operation == 'inspect_garment_failure' else inspect_failure)(project, **arguments)
        return
    if operation == "restore_checkpoint":
        pending = state.get("pending_blender_operation")
        if not pending:
            raise StudioError("No interrupted operation to recover")
        from .lifecycle import verify_files
        verify_files(project, [pending["checkpoint"]])
        return
    if operation == "frame_view":
        if state['stage'] not in ('RECONSTRUCTING', 'RECONSTRUCTED', 'ASSEMBLING', 'REFINING', 'BEHAVIOR_AUTHORING', 'VALIDATING', 'COMPLETE', 'BLOCKED', 'FAILED'):
            raise StudioError('Viewport framing requires an existing production candidate')
        cid, name = arguments['component_id'], arguments['object_name']
        if not isinstance(cid, str) or cid not in state['components'] or not state['components'][cid].get('package'):
            raise StudioError('Viewport framing requires an existing packaged component')
        if not isinstance(name, str) or not name.strip() or len(name) > 255 or any(ord(c) < 32 for c in name):
            raise StudioError('Viewport framing requires an exact object name')
        # Inspection must remain possible after a failure or invalidated board.
        # Live scene, object and provenance checks occur inside Blender.
        return
    if operation not in ("inspect", "inspect_body_source", "inspect_sewing_placement", "inspect_garment_fit", "propose_pattern_adjustment"):
        no_pending_operation(state)
    if operation=='recover_clean_construction':
        path=inside(project.root,arguments['recovery_path'])
        if path.parent!=project.data/'blender' or not path.name.startswith('clean-recovery-'):
            raise StudioError('Expected a native clean construction recovery receipt')
        record=read_json(path)
        if record.get('status')!='ROLLBACK_REQUIRED':raise StudioError('Clean construction does not require recovery')
        previous=inside(project.root,record['previous_session'])
        if sha(previous)!=record['previous_session_sha256']:raise StudioError('Clean recovery session archive changed')
        old=read_json(previous)
        source=Path(old['working']).resolve(strict=True)
        if not source.is_relative_to(project.data/'blender') or str(source)!=record['source'] or sha(source)!=record['source_sha256']:
            raise StudioError('Clean recovery source identity changed')
        if sha(inside(project.root,record['witness']))!=record['source_sha256']:
            raise StudioError('Clean recovery witness identity changed')
        current=read_json(project.data/'blender/session.json')
        candidate=inside(project.root,record['candidate'],False)
        if current!=old and Path(current['working']).resolve()!=candidate:
            raise StudioError('Another construction session supersedes this recovery')
        return
    if operation=='prepare_fitting_envelope':
        from .fitting_preparation import envelope_spec
        if state['stage'] not in ('RECONSTRUCTING','ASSEMBLING'):raise StudioError('Envelope preparation requires an active construction')
        require_board(project,state)
        envelope_spec(project,arguments['envelope_path'])
        return
    if operation=='prepare_fitting_pose':
        from .fitting_preparation import pose_spec
        from .sewing import validate_recipe
        if state['stage']!='RECONSTRUCTING':raise StudioError('Common pose preparation requires active reconstruction')
        require_board(project,state)
        spec,_=pose_spec(project,arguments['pose_path'])
        if spec['component_id']!=arguments['component_id'] or arguments['component_id'] not in state['components']:
            raise StudioError('Common pose component mismatch')
        component=state['components'][arguments['component_id']]
        if component['stage']=='RECONSTRUCTED' or component['route']['selected']!='PATTERN_SEWN':raise StudioError('Common pose requires an unaccepted sewn component')
        recipe=read_json(inside(project.root,arguments['recipe_path']))
        if recipe['component_id']!=arguments['component_id']:raise StudioError('Common pose recipe component mismatch')
        return
    if operation in ('inspect_body_source','prepare_body_reference'):
        from .body_source import selection
        selection(project,arguments['selection_path'])
        if operation=='prepare_body_reference':
            if state['stage']=='COMPLETE':raise StudioError('Completed project is immutable')
            require_board(project,state)
        return
    if operation in ("prepare", "resume", "inspect"):
        if state["stage"] == "COMPLETE" and operation != "inspect":
            raise StudioError("Completed project is immutable")
        return
    require_board(project, state)
    if operation=='start_clean_construction':
        if state['stage']!='RECONSTRUCTING' or any(c['stage']=='RECONSTRUCTED' for c in state['components'].values()):
            raise StudioError('Clean construction requires unaccepted reconstruction candidates')
        value=arguments['working_sha256']
        if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
            raise StudioError('Clean construction requires the exact saved working SHA-256')
        return
    if operation in ("simulate_sewn", "freeze_sewn", "inspect_sewing_placement", "inspect_garment_fit", "propose_pattern_adjustment", "apply_sewn_result", "prepare_sewn_stage", "introduce_fitting_context", "transition_pattern_assembly", "prepare_pattern_assembly"):
        if state["stage"] != "RECONSTRUCTING":
            raise StudioError("Native sewing requires RECONSTRUCTING")
        if arguments['component_id'] not in state['components']:
            raise StudioError('Unknown sewing component')
        _, component = project.ready(arguments["component_id"])
        if component["route"]["selected"] != "PATTERN_SEWN" or component["stage"] == "RECONSTRUCTED":
            raise StudioError("Native sewing requires an unaccepted sewn component")
        from .core import contract
        recipe = contract("sewing-recipe", read_json(inside(project.root, arguments["recipe_path"])))
        if recipe["component_id"] != arguments["component_id"]:
            raise StudioError("Sewing recipe identity mismatch")
        if operation=='prepare_pattern_assembly':
            spec=contract('pattern-preparation',read_json(inside(project.root,arguments['preparation_path'])))
            if spec['component_id']!=arguments['component_id']:raise StudioError('Pattern preparation component mismatch')
            for key in ('assembly_plan','construction_dossier'):
                if spec.get(key) and sha(inside(project.root,spec[key]['path']))!=spec[key]['sha256']:
                    raise StudioError('Pattern preparation source reference changed: '+key)
            if spec.get('assembly_plan'):
                plan=contract('pattern-assembly',read_json(inside(project.root,spec['assembly_plan']['path'])))
                if plan['component_id']!=arguments['component_id']:raise StudioError('Pattern preparation assembly plan mismatch')
        if operation=='transition_pattern_assembly':
            plan=contract('pattern-assembly',read_json(inside(project.root,arguments['plan_path'])))
            if plan['component_id']!=arguments['component_id']:
                raise StudioError('Pattern assembly plan component mismatch')
        if operation in ('transition_pattern_assembly','prepare_pattern_assembly'):
            redundant={'experimental_prefit','interface_preparation','panel_mount','fitting_placement',
                       'contact_recovery','fitting_pose','fitting_tacks'}
            migrating=operation=='prepare_pattern_assembly' and spec.get('migration',{}).get('retire_legacy_preparations') is True
            if migrating and not spec.get('assembly_plan'):
                raise StudioError('Legacy preparation migration requires a sourced assembly plan reference')
            if any(key in recipe for key in redundant) and not migrating:
                raise StudioError('Nominal pattern assembly requires one preform and one bounded closure; migrate legacy preparations separately')
            if migrating:recipe={key:value for key,value in recipe.items() if key not in redundant}
        if operation=='apply_sewn_result':
            fingerprint=arguments['result_sha256']
            if not isinstance(fingerprint,str) or len(fingerprint)!=64 or sha(inside(project.root,arguments['result_path']))!=fingerprint:
                raise StudioError('Sewing result identity changed')
        if (operation=='apply_sewn_result' or operation=='prepare_sewn_stage' and arguments['stage']=='assembly'
            or operation=='simulate_sewn' and arguments.get('purpose')=='assembly'):
            if recipe['colliders'] or recipe.get('fitting_plan') or recipe.get('fitting_tacks') or not recipe['no_collision_reason'].strip():
                raise StudioError('Free assembly requires an explicit collider-free recipe without fitting/tacks')
        if 'fit_path' in arguments:
            plan=contract('fitting-plan',read_json(inside(project.root,arguments['fit_path'])))
            if plan['component_id']!=arguments['component_id']:raise StudioError('Fitting plan component mismatch')
        if operation=='introduce_fitting_context':
            path=inside(project.root,arguments['source_blend'])
            if path.suffix.lower()!='.blend' or sha(path)!=arguments['source_sha256']:
                raise StudioError('Fitting context source identity changed')
        if recipe.get('fitting_plan'):
            if recipe.get('fitting_pose'):
                ref=recipe['fitting_pose']
                if sha(inside(project.root,ref['path']))!=ref['sha256']:
                    raise StudioError('Prepared common pose field changed; prepare and requalify')
            ref=recipe['fitting_plan']
            if sha(inside(project.root,ref['path']))!=ref['sha256']:raise StudioError('Referenced fitting plan changed; update the recipe and requalify')
        if operation in ('simulate_sewn','freeze_sewn') and recipe.get('fitting_tacks') and (operation=='freeze_sewn' or arguments['scope']=='full'):
            raise StudioError('Temporary fitting tacks qualify a construction trial only; remove them and pass a new local before full/freeze')
        if operation == "simulate_sewn" and (arguments["phase"] not in ("mount", "drape") or arguments["scope"] not in ("local", "full")):
            raise StudioError("Unknown sewing phase or scope")
        if operation == 'freeze_sewn' and recipe.get('physics_purpose') == 'TEST_ONLY':
            raise StudioError('TEST_ONLY body physics cannot become a production frozen fitting result')
        if operation in ('simulate_sewn', 'freeze_sewn') or (operation == 'transition_pattern_assembly' and
                arguments['stage'] in ('mount', 'relax', 'drape')):
            from .physics_admission import require_recipe_fit_intent
            require_recipe_fit_intent(project, recipe)
        return
    if operation in ("garment", "verify_legacy_import"):
        if state["stage"] != "RECONSTRUCTING":
            raise StudioError("Sewn panel construction requires RECONSTRUCTING")
        data_dir = inside(project.root, arguments["package_dir"])
        data = read_json(data_dir / "garment.json")
        _, component = project.ready(data["component_id"])
        if component['stage']=='RECONSTRUCTED':
            raise StudioError('Accepted sewing reconstruction is immutable; create a new revision')
        if component["route"]["selected"] != "PATTERN_SEWN":
            raise StudioError("Sewn operation cannot change the selected pipeline")
        manifest = read_json(data_dir / "manifest.json")
        if manifest != component["package"]["manifest"]:
            raise StudioError("Extracted package mismatch")
        for path, checksum in manifest["checksums"].items():
            if sha(inside(data_dir, path)) != checksum:
                raise StudioError("Extracted pattern input changed")
        if operation == 'verify_legacy_import':
            checkpoint_receipt = arguments['checkpoint_receipt']
            if not isinstance(checkpoint_receipt, str) or not checkpoint_receipt:
                raise StudioError('Legacy checkpoint recovery requires an existing receipt path')
            inside(project.root, checkpoint_receipt)
            return
        if "recipe_path" not in arguments:
            raise StudioError("garment requires recipe_path for its derived simulation mesh; keep approved packages unchanged")
        from .sewing import validate_recipe
        garment_recipe=read_json(inside(project.root, arguments["recipe_path"]))
        if garment_recipe.get('interface_preparation') or garment_recipe.get('panel_mount') or garment_recipe.get('fitting_placement'):
            raise StudioError('Use prepare_sewn_stage on existing sewn geometry for local interfaces/panel mount/fitting placement')
        validate_recipe(data, garment_recipe)
    elif operation == "assemble":
        if state["stage"] != "ASSEMBLING":
            raise StudioError("Assembly requires ASSEMBLING")
        from .lifecycle import assembly_plan
        assembly_plan(project, state, arguments["plan_path"])
    else:
        stages = {"simulate": "RECONSTRUCTING", "refine": "REFINING", "behavior": "BEHAVIOR_AUTHORING", "validate": "VALIDATING", "export": "VALIDATING"}
        if stages.get(arguments["purpose"]) != state["stage"]:
            raise StudioError("Script purpose/stage mismatch; arbitrary reconstruction scripts are unsupported")
        if not arguments["component_ids"] or set(arguments["component_ids"]) - state["components"].keys():
            raise StudioError("Declare existing components for the script")
        if arguments["purpose"] == "simulate" and any(state["components"][cid]["route"]["selected"] != "PATTERN_SEWN" for cid in arguments["component_ids"]):
            raise StudioError("Simulation requires already sewn pattern components")
        if arguments["purpose"] == "simulate":
            from .lifecycle import simulation_plan
            if any(state["components"][cid]["stage"] == "RECONSTRUCTED" for cid in arguments["component_ids"]):
                raise StudioError("Accepted sewing reconstruction is immutable; create a new revision for another simulation")
            simulation_plan(project, state, arguments["simulation_plan"], arguments["component_ids"])
        if arguments["purpose"] in ("behavior", "export"):
            from .lifecycle import silhouette
            silhouette(project, state)
        if arguments["purpose"] in ("behavior", "validate", "export") and any(c['route']['selected'] == 'PATTERN_SEWN' for c in state['components'].values()):
            from .piece_inventory import current_proof
            current_proof(project, state, require_global=True)
        path = inside(project.root, arguments["path"])
        if path.suffix != ".py" or sha(path) != arguments["sha256"]:
            raise StudioError("Script changed or is not a project Python file")
