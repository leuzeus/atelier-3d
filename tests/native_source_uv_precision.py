"""Native CDT precision on source UV anchors; no Cloth or garment acceptance."""
import copy
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from a3d.core import StudioError,atomic_json,digest,read_json
from a3d.sewing import mesh_quality,signed_area
from blender.sewing import triangulate
from mathutils.geometry import delaunay_2d_cdt as native_cdt
from unittest.mock import patch

output=Path(os.environ['A3D_VALIDATION_OUTPUT'])
assert output.is_absolute() and output.drive.lower()=='g:'
recipe=read_json(ROOT/'templates/sewing-recipe.json')
recipe['mesh'].update(spacing_cm=2.,min_angle_degrees=1.,min_edge_cm=.01)
recipe['mesh'].pop('quality_refinement',None)
cases=[]
for clockwise in (False,True):
    polygon=[[.123456789012,0.234567890123],[8.123456789012,.234567890123],
             [8.123456789012,10.234567890123],[.123456789012,10.234567890123]]
    if clockwise:polygon.reverse()
    boundary={'polygon':polygon,'source':copy.deepcopy(polygon),'flip':False}
    source_identity=digest(boundary)
    native_calls=[]
    def observed_cdt(*args,**kwargs):
        result=native_cdt(*args,**kwargs)
        native_calls.append(copy.deepcopy(result))
        return result
    with patch('mathutils.geometry.delaunay_2d_cdt',observed_cdt):
        coords,faces,mapping=triangulate(boundary,recipe)
    assert len({mapping[i] for i in range(len(polygon))})==len(polygon)
    assert all(coords[mapping[i]]==point for i,point in enumerate(polygon))
    assert digest(boundary)==source_identity
    native_coords,_,native_faces,_,_,_=native_calls[-1]
    expected_faces=[list(reversed(face)) for face in native_faces] if clockwise else native_faces
    assert faces==expected_faces
    anchors={mapping[i] for i in range(len(polygon))}
    assert all(coords[i]==list(native_coords[i]) for i in range(len(coords)) if i not in anchors)
    assert all(signed_area([coords[i] for i in face])*(-1 if clockwise else 1)>0 for face in faces)
    rest=[[x,y,0.] for x,y in coords]
    quality=mesh_quality(rest,rest,faces,recipe['mesh'])
    assert quality['rest_area_cm2']>0
    cases.append({'source_orientation':'CW' if clockwise else 'CCW',
                  'source_anchor_error_cm':0.,'exact_source_anchors':True,
                  'source_preserved':True,'topology_preserved':True,'interiors_preserved':True,
                  'winding_preserved':True,'vertices':len(coords),'faces':len(faces),
                  'quality':quality})
close=[[8.123456789012,.234567890123],[8.123456799012,.234567890123],
       [16.123456789012,.234567890123],[16.123456789012,10.234567890123],
       [8.123456789012,10.234567890123]]
try:triangulate({'polygon':close,'source':copy.deepcopy(close),'flip':False},recipe)
except StudioError as error:
    assert 'boundary anchor' in str(error)
    close_refusal={'status':'REFUSED','reason':str(error)}
else:raise AssertionError('CDT collapsed close source anchors without refusal')
receipt={'version':1,'status':'PASS_NATIVE_SOURCE_UV_PRECISION_ONLY',
         'cases':cases,'close_source_anchors':close_refusal,
         'cloth':'NOT_EXECUTED','fitting':'NOT_QUALIFIED',
         'qualification':'SOURCE_UV_ANCHORS_ONLY','product_acceptance':'NOT_GRANTED'}
atomic_json(output/'receipt.json',receipt)
print(receipt['status'],flush=True)
