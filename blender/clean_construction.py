"""Versioned empty construction and later exact fitting-context introduction."""
import shutil
import uuid
from pathlib import Path
from a3d.core import StudioError,atomic_json,inside,read_json,sha,now


def start_clean_construction(project_root,working_sha256):
    import bpy
    from blender.operations import working
    project,session=working(project_root)
    source=Path(session['working'])
    if bpy.data.is_dirty:raise StudioError('Save the current working scene before starting a clean construction witness')
    if sha(source)!=working_sha256:raise StudioError('Clean construction working identity changed')
    token=uuid.uuid4().hex
    witness=project.data/('blender/witness-'+token+'.blend')
    shutil.copyfile(source,witness)
    if sha(witness)!=working_sha256:raise StudioError('Clean construction witness copy differs')
    previous=project.data/('blender/session-'+token+'.json')
    atomic_json(previous,session)
    path=project.data/('blender/working-clean-'+token+'.blend')
    record={'original':str(witness),'original_sha256':working_sha256,'working':str(path),
        'created_at':now(),'construction_id':token,'empty_start':True,
        'previous_session':previous.relative_to(project.root).as_posix()}
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
        if len(bpy.data.objects):raise StudioError('Clean construction requires no Blender objects')
        bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=False)
        atomic_json(project.data/'blender/session.json',record)
    except BaseException:
        bpy.ops.wm.open_mainfile(filepath=str(source))
        atomic_json(project.data/'blender/session.json',session)
        raise
    if sha(source)!=working_sha256 or sha(witness)!=working_sha256:
        raise StudioError('Clean construction changed its witness source')
    return {**record,'witness':witness.relative_to(project.root).as_posix(),
        'objects':[],'colliders':[],'simulation':'NOT_EXECUTED','accepted':False,
        'historical_physics_imported':False,'visual_validation':'NOT_EXECUTED'}


def introduce_fitting_context(project_root,component_id,recipe_path,fit_path,source_blend,source_sha256):
    import bpy
    from blender.operations import working
    from blender.sewing import managed_inputs,structural_inputs,mesh_digest,context_colliders
    from blender.sewn_stages import stage_receipt
    project,session=working(project_root)
    obj,payload,recipe=managed_inputs(project,component_id,recipe_path,check_placement=False)
    previous,_=stage_receipt(project,obj,payload,allow_completed=True)
    structural_inputs(obj,payload,previous['recipe'])
    full_path=inside(project.root,obj.get('a3d_sewn_stage_result',''))
    if not full_path.is_file() or sha(full_path)!=obj.get('a3d_sewn_stage_result_sha256'):
        raise StudioError('Introduce fitting context only after immutable full assembly')
    full=read_json(full_path)
    if full.get('purpose')!='assembly' or full.get('scope')!='full' or full.get('simulation')!='PASS' or full.get('result_mesh_sha256')!=mesh_digest(obj) or full.get('boundary_map_sha256')!=obj['a3d_sewing_mesh_sha256']:
        raise StudioError('Fitting context requires the current full free assembly')
    path=inside(project.root,source_blend)
    if sha(path)!=source_sha256:raise StudioError('Fitting context source identity changed')
    plan=read_json(inside(project.root,fit_path))
    if recipe.get('fitting_plan') and recipe['fitting_plan']['path']!=fit_path:
        raise StudioError('Fitting context must use the recipe measurement plan')
    names={c['object'] for c in recipe['colliders']}|{plan[r]['object'] for r in ('body','envelope') if plan.get(r)}
    if not names:raise StudioError('Declare the body and collision context explicitly')
    if any(bpy.data.objects.get(n) is not None for n in names):raise StudioError('Fitting context name already exists; inspect it instead of duplicating it')
    before=mesh_digest(obj);existing=set(bpy.data.objects)
    with bpy.data.libraries.load(str(path),link=False) as (available,loaded):
        if not names<=set(available.objects):raise StudioError('Declared fitting objects are missing from the witness')
        loaded.objects=sorted(names)
    added=set(bpy.data.objects)-existing
    if {o.name for o in added}!=names or any(o.type!='MESH' or o.get('a3d_component_id') for o in added):
        raise StudioError('Fitting import brought undeclared dependencies or construction geometry')
    for target in loaded.objects:
        bpy.context.scene.collection.objects.link(target)
        target.hide_set(False);target.hide_viewport=False;target.hide_render=False
    # Fitting landmarks/sections and collider identity remain exact, independent
    # of whether the current garment contacts pass. No pose or scale is guessed.
    context_colliders(recipe)
    from blender.fitting import measured_report
    report=measured_report(project,obj,payload,recipe,fit_path,measurement_only=True)[0]
    if mesh_digest(obj)!=before or sha(path)!=source_sha256:raise StudioError('Fitting import changed the construction or witness')
    bpy.ops.wm.save_as_mainfile(filepath=session['working'],check_existing=False)
    return {'objects':sorted(names),'source_blend':source_blend,'source_sha256':source_sha256,
        'garment_unchanged':True,'measurements':report,'placement':'NOT_APPLIED',
        'simulation':'NOT_EXECUTED','accepted':False,'visual_validation':'NOT_EXECUTED'}
