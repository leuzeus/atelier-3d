"""Real isolated preparation using Blender's Bend for simple source cylinders.

The torso retains its explicit, source-bound complex volume guide. This test
does not install an addon, modify the body or qualify Cloth/fitting.
"""
import math
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mathutils import Euler,Vector
from a3d.core import atomic_json
from tests import native_pattern_preparation_volume as volume

SOURCE_PREFORM=volume.ORIGINAL_PREFORM


def metric_bend_preform(payload,recipe,data):
    plan=SOURCE_PREFORM(payload,recipe,data)
    for pid,panel in plan['preform']['panels'].items():
        placement=recipe['placements'][pid]
        if placement['mode']!='cylinder':continue
        matrix=Euler([math.radians(v) for v in placement['rotation_degrees']],'XYZ').to_matrix()
        radius=placement['radius_cm']
        sign=-1 if placement.get('mirror_u',False) else 1
        width=max(p[0] for p in data['pieces'][pid]['vertices'])-min(p[0] for p in data['pieces'][pid]['vertices'])
        # Only convert source radius/pose into native modifier parameters.
        # Blender evaluates all curved points; no cylinder formula is used.
        plan['preform']['panels'][pid]={
            'source_ref':panel['source_ref']+'; native Blender SIMPLE_DEFORM/BEND from unchanged metric radius and frame',
            'origin_cm':list(Vector(placement['position_cm'])+matrix@Vector((0,0,radius))),
            'u_axis':list(matrix@Vector((sign,0,0))),
            'v_axis':list(matrix@Vector((0,1,0))),
            'offset_uv_cm':placement['origin_2d_cm'],
            'native_bend':{'angle_degrees':math.degrees(width/radius),'deform_axis':'Z',
                'origin_cm':[0.,0.,0.],'rotation_degrees':[-90.*sign,0.,0.]}}
    plan['source_refs'].append('Simple cylindrical pieces use evaluated Blender Bend; no Garment Tool dependency')
    return plan


if __name__=='__main__':
    volume.ORIGINAL_PREFORM=metric_bend_preform
    volume.real.metric_preform=volume.metric_preform
    original_run=volume.real.run
    def run(output,report):
        original_run(output,report)
        report['volume_guide_hypothesis']=volume.LAST_GUIDE
        report['simple_curving_backend']='BLENDER_SIMPLE_DEFORM_BEND'
        report['garment_tool_used']=False
    volume.real.run=run
    volume.real.main()
