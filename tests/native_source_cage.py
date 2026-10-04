"""Isolated cage seed/native Euler/section/reopen regression; TEST_ONLY."""
import math
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bpy
from mathutils import Euler,Vector
from a3d.core import atomic_json,digest,sha
from a3d.garment_measurements import intersect_guide_material_plane
from a3d.pattern_assembly import _compile_cage,_cage_point
from a3d.textile_executor import _guide_seed_placement,_guide_preform_bound
from blender.sewing import placed_point
from tests.test_barycentric_guide_measurements import fixture

OUT=Path(os.environ['A3D_VALIDATION_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.temporary_directory=str(OUT/'tmp')
bpy.context.preferences.filepaths.save_version=0
piece,frame,triangles,section=fixture()
rotation=Euler([.41,-.37,.63],'XYZ').to_matrix();translation=Vector([13.,-21.,35.])
frame['target_cm']=[list(rotation@Vector(point)+translation)for point in frame['target_cm']]
section['center_cm']=list(rotation@Vector(section['center_cm'])+translation)
section['plane']['normal_world']=list(rotation@Vector(section['plane']['normal_world']))
# Blender uses float32 here; normalize the observed native normal explicitly.
normal=Vector(section['plane']['normal_world']).normalized()
section['plane']['normal_world']=[value/math.sqrt(sum(v*v for v in normal))for value in normal]
before=digest([piece,frame,triangles,section])
compiled=_compile_cage(frame,'native-coupon')
placement=_guide_seed_placement(piece,frame,'native-coupon')
bound=_guide_preform_bound(piece,frame,placement)
pivot=min(piece['vertices'],key=lambda point:(point[1],point[0]))
target,_=_cage_point(frame,compiled,pivot,'native-coupon')
assert math.dist(placed_point(pivot,placement),target)<.00001
native_seed=[placed_point(uv,placement)for uv in frame['uv_cm']]
maximum_source_distance_residual=0.
for i in range(len(native_seed)):
    for j in range(i):
        maximum_source_distance_residual=max(maximum_source_distance_residual,
            abs(math.dist(native_seed[i],native_seed[j])-math.dist(frame['uv_cm'][i],frame['uv_cm'][j])))
assert maximum_source_distance_residual<.00001
assert max(math.dist(a,b)for a,b in zip(native_seed,frame['target_cm']))<=bound['bound_cm']
maximum_seam_gap=max(math.dist(_cage_point(frame,compiled,[0.,v],'native-coupon')[0],
    _cage_point(frame,compiled,[8.,v],'native-coupon')[0])for v in(0.,.35,5.,9.1,10.))
assert maximum_seam_gap<1e-7
curve=intersect_guide_material_plane(piece,frame,triangles,section,['left','right'])
assert abs(curve['source_material_length_cm']-9.)<.00001
mesh=bpy.data.meshes.new('TEST_ONLY_SOURCE_CAGE');mesh.from_pydata(
    [[value/100 for value in point]for point in frame['target_cm']],[],frame['triangles']);mesh.update()
obj=bpy.data.objects.new('TEST_ONLY_CAGE_SECTION',mesh);bpy.context.collection.objects.link(obj)
source_vertices=[list(vertex.co)for vertex in mesh.vertices]
scene=OUT/'test-only-cage.blend';bpy.ops.wm.save_as_mainfile(filepath=str(scene))
bpy.ops.wm.open_mainfile(filepath=str(scene))
assert [list(vertex.co)for vertex in bpy.data.objects['TEST_ONLY_CAGE_SECTION'].data.vertices]==source_vertices
assert digest([piece,frame,triangles,section])==before
atomic_json(OUT/'result.json',{'version':1,'status':'PASS','purpose':'TEST_ONLY',
    'scope':'NATIVE_RIGID_SOURCE_SEED_CAGE_CORRESPONDENCE_AND_SECTION_REOPEN',
    'maximum_source_distance_residual_cm':maximum_source_distance_residual,
    'maximum_guide_seam_gap_cm':maximum_seam_gap,'source_section_material_length_cm':curve['source_material_length_cm'],
    'preform_bound_cm':bound['bound_cm'],'scene_sha256':sha(scene),'source_changed':False,
    'cloth':'NOT_EXECUTED','garment':'NOT_QUALIFIED','fitting':'NOT_EXECUTED','acceptance':'NOT_GRANTED'})
print('PASS TEST_ONLY_NATIVE_SOURCE_CAGE',flush=True)
