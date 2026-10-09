"""Reconstruct guide hypotheses from declared inputs, never qualify a fit.

Only the existing garment_volume_frames dispatcher generates coordinates.
Source packages, the measured native body and optional skin sections retain
their own exact identities. A reproducible hypothesis still needs metric,
contact, donning, physical and human checks on its actual candidate.
"""
import copy
import hashlib
import json
import zipfile

from .core import ROOT,StudioError,contract,digest,inside,read_json,sha
from .garment_guides import (garment_volume_frames,measured_native_skin_sections,
                            validate_section_parameterization,validate_limb_parameterization)
from .anatomical_guide_inputs import check_anatomical_inputs, project_anatomical_references


CODE_SOURCES=('garment_guide_policy','anatomical_guide_inputs','anatomical_placement','attachment_clearance','attachment_guide_guard','regional_surface_guides','assembly_relaxation','active_metric_constraints',
    'dressing_derivation','body_region_sections','garment_guides','limb_surface_sampling','limb_axis_binding','semantic_placement','torso_sections','guide_cage_sampling','material_section_sampling',
    'source_seam_coupling','source_boundary_bindings','surface_path_continuation','guide_stage_metrics','cloth_metrics','rigid_guide_alignment','shoulder_guides','preform_volume','pattern_assembly','anatomy_profile','shoulder_surface','head_surface','contact_geometry','sewing','core')


def guide_generator_identity():
    return {name:sha(ROOT/('a3d/'+name+'.py'))for name in CODE_SOURCES}


def _owners(compiled):
    return {row['id']:row for row in compiled['components']if row['pipeline']=='PATTERN_SEWN'}


def _recipe_components(rows):
    selected = set()
    for cid, row in rows.items():
        if 'attachment_clearance' in row:
            from .attachment_guide_guard import validate_attachment_guard_policy
            clearance = row['attachment_clearance']
            if not isinstance(clearance, dict) or not isinstance(clearance.get('recipe_ref'), dict):
                raise StudioError('Attachment guard requires an exact source recipe reference')
            validate_attachment_guard_policy({key: value for key, value in clearance.items() if key != 'recipe_ref'})
            if 'anatomical_references_ref' not in row:
                raise StudioError('Attachment guard requires declared anatomical reference files')
        if 'source_boundary_bindings' in row:
            from .source_boundary_bindings import validate_current_boundary_policy
            boundary = row['source_boundary_bindings']
            if not isinstance(boundary, dict) or not isinstance(boundary.get('recipe_ref'), dict):
                raise StudioError('Source boundary inspection requires an exact source recipe reference')
            validate_current_boundary_policy({key: value for key, value in boundary.items() if key != 'recipe_ref'})
        references = [row[key]['recipe_ref'] for key in ('source_seam_coupling', 'source_boundary_bindings', 'attachment_clearance') if key in row]
        if references:
            if any(ref != references[0] for ref in references[1:]):
                raise StudioError('Guide coupling and boundary inspection must share one exact source recipe reference')
            selected.add(cid)
        if 'source_boundary_bindings' in row and 'anatomical_references_ref' not in row:
            raise StudioError('Source boundary inspection requires declared anatomical reference files')
    return selected


def prepare_guide_policy(compiled,profile,geometry,geometry_ref,component_parameters,*,source_seam_recipes=None,
                         anatomical_references=None):
    """Prepare a policy from explicit parameters; pure callers supply trusted inputs."""
    owners=_owners(compiled)
    if set(component_parameters)!=set(owners):
        raise StudioError('Guide policy must declare parameters for every actual textile component exactly once')
    if (geometry.get('source_sha256')!=profile.get('source_sha256')or geometry.get('pose_sha256')!=profile.get('pose_sha256')
            or digest([geometry['vertices_cm'],geometry['faces']])!=profile.get('geometry_sha256')):
        raise StudioError('Guide policy needs its exact measured body geometry, source and pose')
    source_seam_recipes={} if source_seam_recipes is None else source_seam_recipes
    selected=_recipe_components(component_parameters)
    if set(source_seam_recipes)!=selected:
        raise StudioError('Guide source-seam coupling needs exactly its declared complete sewing recipes')
    anatomical_references={} if anatomical_references is None else anatomical_references
    reference_components=check_anatomical_inputs(component_parameters,anatomical_references)
    components={}
    for cid,parameters in sorted(component_parameters.items()):
        if set(parameters)-{'source_seam_coupling','source_boundary_bindings','attachment_clearance','anatomical_references_ref','section_parameterization','limb_parameterization'}!={'upper_blend','surface_sections','skin_section_heights_cm'}:
            raise StudioError('Guide parameters must explicitly declare blend, measured surfaces and skin heights without overrides')
        validate_section_parameterization(parameters.get('section_parameterization','POLYLINE_ARCLENGTH_V1'),
            parameters['upper_blend'],parameters['surface_sections'])
        validate_limb_parameterization(parameters.get('limb_parameterization','SOURCE_ROW_CIRCUMFERENCE_V1'))
        row={**copy.deepcopy(parameters),'package_source_ref':copy.deepcopy(owners[cid]['package_source_ref'])}
        if cid in selected:
            row['source_seam_recipe_sha256']=digest(source_seam_recipes[cid])
        if cid in reference_components:
            from .anatomical_placement import validate_anatomical_references
            validate_anatomical_references(profile,anatomical_references[cid],geometry=geometry)
            row['anatomical_references_sha256']=digest(anatomical_references[cid])
        if parameters['skin_section_heights_cm']:
            if not parameters['surface_sections']:
                raise StudioError('Guide policy skin heights need explicitly enabled surfaces')
            skin=measured_native_skin_sections(profile,geometry,parameters['skin_section_heights_cm'])
            row['skin_sections_sha256']=digest(skin)
        components[cid]=row
    modern=bool(reference_components) or any(row.get('source_seam_coupling',{}).get('strategy')=='COUPLED_REST_METRIC_V2'
        or row.get('section_parameterization')=='SOURCE_MATERIAL_U_V1'
        or row.get('limb_parameterization')=='SOURCE_SEWN_DOMAIN_V1'
        for row in component_parameters.values())
    policy={'version':2 if modern else 1,'generator':'GARMENT_VOLUME_FRAMES_V2' if modern else 'GARMENT_VOLUME_FRAMES_V1','compiled_sha256':digest(compiled),
        'dossier_ref':copy.deepcopy(compiled['source_ref']),
        'specification_ref':copy.deepcopy(compiled['specification_source_ref']),
        'body_ref':copy.deepcopy(compiled['assembly_spec']['body_ref']),'geometry_ref':copy.deepcopy(geometry_ref),
        'generator_code_sha256':guide_generator_identity(),'components':components}
    return contract('garment-guide-policy',policy)


def reconstruct_guide_policy(compiled,profile,geometry,geometry_ref,source_data,policy,*,source_seam_recipes=None,
                             anatomical_references=None):
    """Recompute every coordinate with the sole existing generator."""
    contract('garment-guide-policy',policy);owners=_owners(compiled)
    if policy['generator_code_sha256']!=guide_generator_identity():
        raise StudioError('Guide policy generator code is stale or has unrecognized dependency bindings')
    if (policy['compiled_sha256']!=digest(compiled)or policy['dossier_ref']!=compiled['source_ref']
            or policy['specification_ref']!=compiled['specification_source_ref']):
        raise StudioError('Guide policy belongs to another exact approved source compilation')
    if policy['body_ref']!=compiled['assembly_spec']['body_ref']or policy['geometry_ref']!=geometry_ref:
        raise StudioError('Guide policy belongs to another measured native body profile or canonical geometry reference')
    if (geometry.get('source_sha256')!=profile.get('source_sha256')or geometry.get('pose_sha256')!=profile.get('pose_sha256')
            or digest([geometry['vertices_cm'],geometry['faces']])!=profile.get('geometry_sha256')):
        raise StudioError('Guide policy body, evaluated skin geometry, source or pose changed')
    if set(policy['components'])!=set(owners)or set(source_data)!=set(owners):
        raise StudioError('Guide policy must cover the exact actual textile component inventory')
    source_seam_recipes={} if source_seam_recipes is None else source_seam_recipes
    selected=_recipe_components(policy['components'])
    if set(source_seam_recipes)!=selected:
        raise StudioError('Guide source-seam coupling needs exactly its declared complete sewing recipes')
    anatomical_references={} if anatomical_references is None else anatomical_references
    reference_components=check_anatomical_inputs(policy['components'],anatomical_references)
    modern=bool(reference_components) or any(row.get('source_seam_coupling',{}).get('strategy')=='COUPLED_REST_METRIC_V2'
        or row.get('section_parameterization')=='SOURCE_MATERIAL_U_V1'
        or row.get('limb_parameterization')=='SOURCE_SEWN_DOMAIN_V1'
        for row in policy['components'].values())
    if (policy['version']!=(2 if modern else 1) or
            policy['generator']!=('GARMENT_VOLUME_FRAMES_V2' if modern else 'GARMENT_VOLUME_FRAMES_V1')):
        raise StudioError('Guide generator version does not match its declared anatomical and assembly strategy')
    before=digest([compiled,profile,geometry,geometry_ref,source_data,policy,source_seam_recipes,anatomical_references]);guides={};skins={}
    for cid,row in sorted(policy['components'].items()):
        if row['package_source_ref']!=owners[cid]['package_source_ref']:
            raise StudioError('Guide policy source package identity changed')
        data=source_data[cid]
        if data.get('component_id')!=cid:
            raise StudioError('Guide policy source package has another component owner')
        owned={pid:item for pid,item in compiled['textiles'].items()if item['component_id']==cid}
        if set(owned)!=set(data['pieces'])or any(item['source_geometry']!=data['pieces'][pid]for pid,item in owned.items()):
            raise StudioError('Guide policy immutable material geometry differs from its exact source compilation')
        semantics={pid:copy.deepcopy(item['semantics'])for pid,item in owned.items()};skin=None
        heights=row['skin_section_heights_cm']
        if heights:
            if not row['surface_sections']or 'skin_sections_sha256'not in row:
                raise StudioError('Guide policy skin heights need explicitly enabled surfaces and their exact remeasurement identity')
            skin=measured_native_skin_sections(profile,geometry,heights)
            if row['skin_sections_sha256']!=digest(skin):
                raise StudioError('Guide policy skin-section evidence differs from exact source remeasurement')
            skins[cid]={'sections_sha256':digest(skin),'geometry_sha256':skin['geometry_sha256'],
                'qualification':skin['qualification'],'anatomical_girths_replaced':False}
        elif 'skin_sections_sha256'in row:
            raise StudioError('Guide policy cannot supply unrequested skin-section evidence')
        coupling=row.get('source_seam_coupling');recipe=source_seam_recipes.get(cid)
        if cid in selected:
            if row.get('source_seam_recipe_sha256')!=digest(recipe):
                raise StudioError('Guide source-seam recipe changed from its exact declared policy')
        elif 'source_seam_recipe_sha256'in row:
            raise StudioError('Guide policy cannot supply an unrequested source-seam recipe identity')
        if cid in reference_components:
            if row.get('anatomical_references_sha256')!=digest(anatomical_references[cid]):
                raise StudioError('Anatomical guide reports or piece policies changed')
        elif 'anatomical_references_sha256' in row:
            raise StudioError('Guide policy cannot supply undeclared anatomical evidence')
        guides[cid]=garment_volume_frames(data,semantics,profile,upper_blend=row['upper_blend'],
            surface_sections=row['surface_sections'],skin_sections=skin,
            source_seam_coupling=coupling,seam_recipe=recipe,
            **({'section_parameterization':row['section_parameterization']} if 'section_parameterization'in row else {}),
            **({'limb_parameterization':row['limb_parameterization']} if 'limb_parameterization'in row else {}),
            **({'source_boundary_bindings': {key: value for key, value in row['source_boundary_bindings'].items() if key != 'recipe_ref'}}
               if 'source_boundary_bindings' in row else {}),
            **({'attachment_clearance': {key: value for key, value in row['attachment_clearance'].items() if key != 'recipe_ref'}}
               if 'attachment_clearance' in row else {}),
            **({'anatomical_references':anatomical_references[cid],
                'anatomical_geometry':{'geometry':geometry,'triangles':anatomical_references[cid].get('triangles')}}
               if cid in reference_components else {}))
    if digest([compiled,profile,geometry,geometry_ref,source_data,policy,source_seam_recipes,anatomical_references])!=before:
        raise StudioError('Guide reconstruction changed immutable source, body or declared policy inputs')
    return guides,{'status':'GUIDE_HYPOTHESES_RECONSTRUCTED','policy_sha256':digest(policy),
        'generator_code_sha256':copy.deepcopy(policy['generator_code_sha256']),
        'source_compilation_sha256':digest(compiled),'body_profile_sha256':digest(profile),
        'geometry_ref':copy.deepcopy(geometry_ref),'guides_sha256':digest(guides),'skin_sections':skins,
        'comparison':'FULL_UNROUNDED_GUIDE_REPORT','qualification':'NONE','admissible_for_fit':False,
        'placement':'NOT_QUALIFIED','simulation':'NOT_EXECUTED','acceptance':'NOT_GRANTED'}


def verify_guide_policy(compiled,profile,geometry,geometry_ref,source_data,policy,guides,*,source_seam_recipes=None,
                        anatomical_references=None):
    expected,evidence=reconstruct_guide_policy(compiled,profile,geometry,geometry_ref,source_data,policy,
        source_seam_recipes=source_seam_recipes,anatomical_references=anatomical_references)
    if expected!=guides:
        raise StudioError('Guide coordinates or reports differ from reconstruction of their exact declared source/body/skin/code policy')
    evidence['comparison']='FULL_UNROUNDED_GUIDE_REPORT_IDENTICAL'
    return evidence


def _project_inputs(project,compiled):
    from .production_dossier import compile_project_dossier
    if compile_project_dossier(project,compiled['source_ref']['path'],compiled['specification_source_ref']['path'])!=compiled:
        raise StudioError('Guide source compilation differs from current exact source reconstruction')
    def load(ref):
        path=inside(project.root,ref['path'])
        if sha(path)!=ref['sha256']:raise StudioError('Guide policy source artifact changed')
        return read_json(path)
    body_ref=compiled['assembly_spec']['body_ref'];profile=load(body_ref)
    from .native_evidence import native_origin
    native,origin=native_origin(project,lambda doc:
        (doc.get('operation')=='prepare_body_target'and doc.get('result',{}).get('artifacts',{}).get('profile')==body_ref)or
        (doc.get('operation')=='introduce_body_target'and doc.get('result',{}).get('profile_ref')==body_ref))
    geometry_ref=(native['result']['artifacts']['geometry']if native['operation']=='prepare_body_target'else native['result']['geometry_ref'])
    if body_ref not in native['files']or geometry_ref not in native['files']or native['result'].get('profile_cache_key')!=profile['cache_key']:
        raise StudioError('Guide policy needs its exact canonical completed native body profile and geometry')
    geometry=load(geometry_ref);data={}
    for cid,row in sorted(_owners(compiled).items()):
        ref=row['package_source_ref'];path=inside(project.root,ref['path'])
        if sha(path)!=ref['sha256']:raise StudioError('Guide policy source package changed')
        with zipfile.ZipFile(path)as archive:data[cid]=json.loads(archive.read('garment.json'))
    return profile,geometry,geometry_ref,data,origin


def _project_seam_recipes(project,rows):
    recipes={}
    selected=_recipe_components(rows)
    for cid,row in rows.items():
        if cid in selected:
            consumer=next(row[key] for key in ('source_seam_coupling', 'source_boundary_bindings', 'attachment_clearance') if key in row)
            ref=consumer['recipe_ref'];path=inside(project.root,ref['path'])
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=ref['sha256']:
                raise StudioError('Guide source-seam recipe artifact changed')
            recipes[cid]=json.loads(data)
    return recipes


def prepare_project_guide_policy(project,compiled,component_parameters):
    profile,geometry,ref,_,origin=_project_inputs(project,compiled)
    recipes=_project_seam_recipes(project,component_parameters)
    references=project_anatomical_references(project,component_parameters)
    policy=prepare_guide_policy(compiled,profile,geometry,ref,component_parameters,source_seam_recipes=recipes,
        anatomical_references=references)
    return policy,{'native_body_origin':origin,'qualification':'NONE','admissible_for_fit':False}


def verify_project_guides(project,compiled,guides,policy_path):
    path=inside(project.root,policy_path);policy_bytes=path.read_bytes()
    policy_sha256=hashlib.sha256(policy_bytes).hexdigest();policy=json.loads(policy_bytes)
    profile,geometry,ref,data,origin=_project_inputs(project,compiled)
    recipes=_project_seam_recipes(project,policy['components'])
    references=project_anatomical_references(project,policy['components'])
    evidence=verify_guide_policy(compiled,profile,geometry,ref,data,policy,guides,source_seam_recipes=recipes,
        anatomical_references=references)
    if _project_seam_recipes(project,policy['components'])!=recipes:
        raise StudioError('Guide source-seam recipe artifact changed during reconstruction')
    if project_anatomical_references(project,policy['components'])!=references:
        raise StudioError('Anatomical guide artifact changed during reconstruction')
    if sha(path)!=policy_sha256:raise StudioError('Guide policy artifact changed during source reconstruction')
    evidence.update(policy_ref={'path':policy_path,'sha256':policy_sha256},native_body_origin=origin)
    return evidence
