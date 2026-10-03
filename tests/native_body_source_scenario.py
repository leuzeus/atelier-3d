"""Synthetic selected-source invariants; callable inside the actual MCP guard."""
from pathlib import Path
import bpy
from a3d.core import StudioError,atomic_json,read_json,sha
from blender.body_source import data_ids,live_geometry
from blender.operations import dispatch

def run(project,real_selection=None):
    marker_mesh=bpy.data.meshes.new('LIVE_MARKER');marker_mesh.from_pydata([(0,0,0),(.5,0,0),(0,0,.5)],[],[(0,1,2)])
    marker=bpy.data.objects.new('LIVE_MARKER',marker_mesh);bpy.context.scene.collection.objects.link(marker)
    baseline=data_ids();geometry=live_geometry();scene=bpy.context.scene;frame=scene.frame_current
    filepath=bpy.data.filepath;dirty=bpy.data.is_dirty;db=sha(project.db)
    mesh=bpy.data.meshes.new('SOURCE_BODY');mesh.from_pydata([(0,0,0),(1,0,0),(0,0,1)],[],[(0,1,2)])
    body=bpy.data.objects.new('SOURCE_BODY',mesh)
    parent=bpy.data.objects.new('SOURCE_CONTROL',None);body.parent=parent
    parent.location=(0,0,0);parent.keyframe_insert('location',frame=1)
    parent.location=(0,0,1);parent.keyframe_insert('location',frame=2)
    old=bpy.data.objects.new('OLD_GARMENT_EXCLUDED',mesh.copy());old['a3d_component_id']='old.garment'
    source=project.root/'source-body.blend'
    bpy.data.libraries.write(str(source),{body,parent,old},fake_user=True)
    bpy.data.batch_remove(ids=data_ids()-baseline)
    fingerprint=sha(source)
    selection={'version':1,'source_blend':'source-body.blend','source_sha256':fingerprint,
        'source_ref':'synthetic animated body fixture','frame':2,'unit_scale_m':1,
        'meshes':['SOURCE_BODY'],'dependencies':['SOURCE_CONTROL'],'reference_object':'FROZEN_BODY'}
    atomic_json(project.root/'body-selection.json',selection)
    args={'selection_path':'body-selection.json'}
    inspection=dispatch(str(project.root),'inspect_body_source',args)
    assert inspection['bounds_cm'][0][2]==100 and inspection['height_cm']==100
    snapshot=dispatch(str(project.root),'prepare_body_reference',args)
    path=project.root/snapshot['artifact']['path']
    with bpy.data.libraries.load(str(path),link=False) as (available,loaded):
        assert available.objects==['FROZEN_BODY'] and not available.armatures and not available.actions
        loaded.objects=['FROZEN_BODY']
    from blender.sewing import mesh_digest
    reference=loaded.objects[0]
    assert not reference.modifiers and reference.parent is None and reference.animation_data is None
    assert mesh_digest(reference)==snapshot['geometry_sha256']
    bpy.data.batch_remove(ids=data_ids()-baseline)
    # Undeclared dependencies and construction geometry are refusals, with
    # all temporary objects/actions/data removed even on the failing path.
    selection['dependencies']=[];atomic_json(project.root/'body-selection.json',selection)
    try:dispatch(str(project.root),'inspect_body_source',args)
    except StudioError as error:assert 'Undeclared body dependencies' in str(error)
    else:raise AssertionError('Implicit body dependency accepted')
    selection['meshes']=['OLD_GARMENT_EXCLUDED'];atomic_json(project.root/'body-selection.json',selection)
    try:dispatch(str(project.root),'prepare_body_reference',args)
    except StudioError as error:assert 'construction geometry' in str(error)
    else:raise AssertionError('Old garment accepted as body')
    assert data_ids()==baseline and live_geometry()==geometry and bpy.context.scene==scene and scene.frame_current==frame
    assert bpy.data.filepath==filepath and bpy.data.is_dirty==dirty and sha(project.db)==db and sha(source)==fingerprint
    result={'status':'PASS','selective_animation_frame':'PASS','snapshot_identity':'PASS',
        'undeclared_dependency_refused':'PASS','old_garment_refused':'PASS','live_scene_db_unchanged':True,
        'snapshot':snapshot}
    if real_selection:
        selection=read_json(real_selection);atomic_json(project.root/'real-body-selection.json',selection)
        real=dispatch(str(project.root),'prepare_body_reference',{'selection_path':'real-body-selection.json'})
        assert len(real['meshes'])==28 and len(real['dependencies'])==3
        assert abs(real['height_cm']-179.99318795264116)<.001
        assert live_geometry()==geometry
        result['real_body']=real
    return result
