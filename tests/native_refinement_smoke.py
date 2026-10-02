"""Native triangulation regression: source anchors, area and bounded refusal."""
import copy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from a3d.core import ROOT,StudioError,read_json
from a3d.sewing import mesh_quality
from blender.sewing import triangulate

recipe=read_json(ROOT/'templates/sewing-recipe.json')
polygon=[[0,0],[10,0],[10,10],[0,10]]
boundary={'polygon':polygon,'source':copy.deepcopy(polygon),'flip':False}
original=copy.deepcopy(boundary)
base,faces,mapping=triangulate(boundary,recipe)
recipe['mesh']['quality_refinement']={'target_min_angle_degrees':4,'max_passes':32,'max_added_vertices':2000}
verts,refined,anchors=triangulate(boundary,recipe)
coords=[[x,y,0] for x,y in verts]
quality=mesh_quality(coords,coords,refined,recipe['mesh'])
assert quality['min_angle_degrees']>=4
assert len(verts)==len(base) and abs(quality['rest_area_cm2']-100)<1e-4
assert boundary==original
for i,p in enumerate(polygon):assert sum((verts[anchors[i]][k]-p[k])**2 for k in range(2))<1e-9
recipe['mesh']['quality_refinement']['max_added_vertices']=1
boundary['polygon']=[[0,0],[.09,0],[10,0],[10,10],[0,10]]
boundary['source']=copy.deepcopy(boundary['polygon']);original=copy.deepcopy(boundary)
try:triangulate(boundary,recipe)
except StudioError as exc:assert 'budget' in str(exc),str(exc)
else:raise AssertionError('Refinement ignored its vertex budget')
assert boundary==original
print('NATIVE_REFINEMENT_PASS',quality,flush=True)
