"""Isolated native preservation of a shallow source turn; TEST_ONLY, no Cloth."""
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bpy
from a3d.core import StudioError,atomic_json,digest,sha
from a3d.pattern_preparation import prepare_regular_boundaries
from a3d.sewing import mesh_quality,segment_distance
from blender.sewing import triangulate
from tests.test_pattern_preparation_corners import shallow_source,CONFIG

OUT=Path(os.environ['A3D_VALIDATION_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.temporary_directory=str(OUT/'tmp')
bpy.context.preferences.filepaths.save_version=0
data,recipe,relation=shallow_source();before=digest([data,recipe])
boundaries,seams,sampling=prepare_regular_boundaries(data,recipe,CONFIG)
piece=data['pieces']['front'];corner=piece['vertices'][2]
boundary=boundaries['front'];source_index=boundary['polygon'].index(corner)
coordinates,faces,mapping=triangulate(boundary,recipe,CONFIG)
assert coordinates[mapping[source_index]]==corner
maximum_boundary_error=0.
for a,b in zip(boundary['polygon'],boundary['polygon'][1:]+boundary['polygon'][:1]):
    midpoint=[(x+y)/2 for x,y in zip(a,b)]
    error=min(segment_distance(midpoint,x,y)for x,y in zip(piece['vertices'],piece['vertices'][1:]+piece['vertices'][:1]))
    maximum_boundary_error=max(maximum_boundary_error,error)
assert maximum_boundary_error<1e-7
rest=[point+[0.]for point in coordinates]
try:
    quality=mesh_quality(rest,rest,faces,recipe['mesh']);quality_status='PASS'
except StudioError as error:
    quality=error.quality_violations;quality_status='REFUSED_UNCHANGED_QUALITY_GATE'
mesh=bpy.data.meshes.new('TEST_ONLY_EXACT_SOURCE_CONTOUR')
mesh.from_pydata([[u/100,v/100,0.]for u,v in coordinates],[],faces);mesh.update()
obj=bpy.data.objects.new('TEST_ONLY_EXACT_SOURCE_CONTOUR',mesh);bpy.context.collection.objects.link(obj)
vertices=[list(vertex.co)for vertex in mesh.vertices]
scene=OUT/'test-only-source-contour.blend';bpy.ops.wm.save_as_mainfile(filepath=str(scene))
bpy.ops.wm.open_mainfile(filepath=str(scene))
assert [list(vertex.co)for vertex in bpy.data.objects['TEST_ONLY_EXACT_SOURCE_CONTOUR'].data.vertices]==vertices
assert digest([data,recipe])==before
atomic_json(OUT/'result.json',{'version':1,'status':'PASS','purpose':'TEST_ONLY',
    'scope':'NATIVE_SOURCE_TURN_CDT_ANCHORS_AND_REOPEN',
    'exact_source_corner_cm':corner,'exact_rest_corner_cm':coordinates[mapping[source_index]],
    'maximum_source_boundary_chord_error_cm':maximum_boundary_error,
    'native_vertices':len(vertices),'native_faces':len(faces),'source_changed':False,
    'quality_status':quality_status,'quality':quality,'sampling':sampling['boundary_sampling_policy'],
    'scene_sha256':sha(scene),'cloth':'NOT_EXECUTED','garment':'NOT_QUALIFIED',
    'fitting':'NOT_EXECUTED','acceptance':'NOT_GRANTED'})
print('PASS TEST_ONLY_NATIVE_SOURCE_CONTOUR',flush=True)
