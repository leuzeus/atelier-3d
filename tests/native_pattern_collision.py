"""Native BVH collision-sign regression; no simulation or consumer scene edits."""
import math
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from a3d.core import atomic_json
from blender.pattern_assembly import collision_check,nearest_signed_distance_cm


def box_tree(bounds):
    (x0,x1),(y0,y1),(z0,z1)=bounds
    vertices=[[x,y,z] for x,y,z in ((x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
                                   (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1))]
    faces=[[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
    mesh=bpy.data.meshes.new('CollisionSignRegression')
    try:
        mesh.from_pydata([[value/100 for value in point] for point in vertices],[],faces)
        mesh.update()
        tree=BVHTree.FromPolygons([vertex.co.copy() for vertex in mesh.vertices],
                                 [list(face.vertices) for face in mesh.polygons])
        return tree,{'object':'synthetic-box','dimensions_cm':[x1-x0,y1-y0,z1-z0]}
    finally:bpy.data.meshes.remove(mesh)


def main():
    output=Path(os.environ['A3D_VALIDATION_OUTPUT'])
    tree,snapshot=box_tree([(-9.,9.),(-1.8,1.8),(0.,32.)])
    corner=[-11.991112947,2.400147037,1.7478e-8]
    point=Vector([value/100 for value in corner])
    hit,normal,face,_=tree.find_nearest(point)
    witness={'point_cm':corner,'nearest_cm':[value*100 for value in hit],
             'normal':list(normal),'face':face,
             'former_signed_cm':nearest_signed_distance_cm(point,hit,normal)}
    results={}
    for label,coords,expected,clearance in (
        ('reported_exterior_corner',corner,True,.4),
        ('exterior_corner_below_plane',[corner[0],corner[1],-corner[2]],True,.4),
        ('inside',[0.,0.,16.],False,.4),
        ('surface',[0.,1.8,16.],False,.4),
        ('reserve_inside',[0.,2.19,16.],False,.4),
        ('reserve_outside',[0.,2.21,16.],True,.4),
        ('shallow_inside',[0.,1.8-1e-5,16.],False,0.),
    ):
        report=collision_check([coords],[tree],[snapshot],clearance)
        assert report['ok'] is expected,(label,report)
        results[label]=report
    assert results['reported_exterior_corner']['minimum_signed_offset_cm']>3.
    assert results['reported_exterior_corner']['ray_classified_samples']==1
    assert math.isclose(results['inside']['minimum_signed_offset_cm'],-1.8,abs_tol=1e-5)
    assert abs(results['surface']['minimum_signed_offset_cm'])<1e-5
    deep_tree,deep_snapshot=box_tree([(-20.,20.),(-20.,20.),(0.,32.)])
    deep=collision_check([[0.,0.,7.81148]],[deep_tree],[deep_snapshot],.4)
    assert not deep['ok'] and math.isclose(deep['minimum_signed_offset_cm'],-7.81148,abs_tol=1e-5)
    assert deep['ray_classified_samples']==0
    results['deep_7_81148_cm']=deep
    # Metre-scale translations change float precision, not physical clearance.
    shift=[101.7,-223.1,97.4]
    translated,translated_snapshot=box_tree([(a+s,b+s) for (a,b),s in zip(
        [(-9.,9.),(-1.8,1.8),(0.,32.)],shift,strict=True)])
    translated_report=collision_check([[a+b for a,b in zip(corner,shift,strict=True)]],
                                      [translated],[translated_snapshot],.4)
    assert translated_report['ok'],translated_report
    assert math.isclose(translated_report['minimum_signed_offset_cm'],
                        results['reported_exterior_corner']['minimum_signed_offset_cm'],abs_tol=3e-5)
    results['translated_corner']=translated_report
    record={'status':'PASS','blender_version':bpy.app.version_string,'former_failure_witness':witness,
            'cases':results,'simulation':'NOT_EXECUTED','qualification':'NONE'}
    atomic_json(output/'result.json',record)
    print('PASS native collision sign: exterior corner, interior, surface, reserve, deep and translation')


if __name__=='__main__':main()
