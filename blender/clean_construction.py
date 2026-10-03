"""Versioned empty construction and later exact fitting-context introduction."""
import shutil
import uuid
from pathlib import Path
from a3d.core import StudioError,atomic_json,inside,read_json,sha,now

def _open_source(path):
    import bpy
    bpy.ops.wm.open_mainfile(filepath=str(path),load_ui=False)


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
    recovery={'source':str(source),'source_sha256':working_sha256,
        'witness':witness.relative_to(project.root).as_posix(),
        'previous_session':previous.relative_to(project.root).as_posix(),
        'previous_session_sha256':sha(previous),
        'candidate':path.relative_to(project.root).as_posix(),'status':'ROLLBACK_REQUIRED'}
    recovery_path=project.data/('blender/clean-recovery-'+token+'.json')
    atomic_json(recovery_path,recovery)
    try:
        # The official interactive MCP rejects read_factory_settings because
        # it resets preferences and unloads add-ons. Loading an empty factory
        # startup keeps user preferences and persistent MCP timers intact.
        bpy.ops.wm.read_homefile(use_empty=True,use_factory_startup=True,
            load_ui=False,use_splash=False)
        bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
        if len(bpy.data.objects):raise StudioError('Clean construction requires no Blender objects')
        bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=False)
        if sha(source)!=working_sha256 or sha(witness)!=working_sha256:
            raise StudioError('Clean construction changed its witness source')
        atomic_json(project.data/'blender/session.json',record)
        recovery['status']='COMPLETED';atomic_json(recovery_path,recovery)
    except BaseException as error:
        recovery.update(status='ROLLBACK_REQUIRED',error=str(error))
        atomic_json(recovery_path,recovery)
        try:
            if Path(bpy.data.filepath).resolve()!=source.resolve() or bpy.data.is_dirty:
                _open_source(source)
            atomic_json(project.data/'blender/session.json',session)
            if sha(source)!=working_sha256 or sha(witness)!=working_sha256:
                raise StudioError('Clean rollback source or witness identity changed')
            recovery['status']='ROLLED_BACK'
        except BaseException as rollback_error:
            recovery['rollback_error']=str(rollback_error)
            atomic_json(recovery_path,recovery)
            raise StudioError('Clean construction rollback failed; preserve source/witness/session and recover from '+
                recovery_path.relative_to(project.root).as_posix()) from error
        atomic_json(recovery_path,recovery)
        raise
    return {**record,'witness':witness.relative_to(project.root).as_posix(),
        'recovery_path':recovery_path.relative_to(project.root).as_posix(),
        'objects':[],'colliders':[],'simulation':'NOT_EXECUTED','accepted':False,
        'historical_physics_imported':False,'visual_validation':'NOT_EXECUTED'}


def recover_clean_construction(project_root,recovery_path):
    import bpy
    from a3d.store import Project
    from a3d.guard import admit_operation
    project=Project(project_root)
    admit_operation(project,'recover_clean_construction',{'recovery_path':recovery_path})
    if bpy.data.is_dirty:raise StudioError('Save or preserve the current scene before clean recovery')
    path=inside(project.root,recovery_path);record=read_json(path)
    session=read_json(inside(project.root,record['previous_session']))
    _open_source(record['source'])
    if sha(Path(record['source']))!=record['source_sha256']:
        raise StudioError('Clean recovery source changed while opening')
    atomic_json(project.data/'blender/session.json',session)
    record['status']='ROLLED_BACK';record['recovered_at']=now();atomic_json(path,record)
    return {'recovery_path':recovery_path,'status':'ROLLED_BACK','working':session['working'],
        'source_sha256':record['source_sha256'],'accepted':False,'visual_validation':'NOT_EXECUTED'}


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
    retained={n for n in names if bpy.data.objects.get(n) is not None}
    if any(bpy.data.objects[n].type!='MESH' or bpy.data.objects[n].get('a3d_component_id') for n in retained):
        raise StudioError('Existing fitting context cannot be construction geometry')
    missing=names-retained
    before=mesh_digest(obj);existing=set(bpy.data.objects)
    with bpy.data.libraries.load(str(path),link=False) as (available,loaded):
        if not missing<=set(available.objects):raise StudioError('Declared fitting objects are missing from the witness')
        loaded.objects=sorted(missing)
    added=set(bpy.data.objects)-existing
    if {o.name for o in added}!=missing or any(o.type!='MESH' or o.get('a3d_component_id') for o in added):
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
        'imported_objects':sorted(missing),'retained_objects':sorted(retained),
        'garment_unchanged':True,'measurements':report,'placement':'NOT_APPLIED',
        'simulation':'NOT_EXECUTED','accepted':False,'visual_validation':'NOT_EXECUTED'}
