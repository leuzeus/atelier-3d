"""Bounded CDT/preform regression probe; no simulation, render or scene save."""
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from a3d.core import StudioError,atomic_json,read_json,sha
from a3d.pattern_assembly import map_digest,preform_coordinates
from a3d.pattern_preparation import preparation_statistics
from blender.sewing import build_mesh


def main():
    args=sys.argv[sys.argv.index('--')+1:]
    project=Path(args[0]).resolve();previous_path=Path(args[1]).resolve()
    require_target=len(args)>2 and args[2]=='require-target'
    out=Path(os.environ['A3D_VALIDATION_OUTPUT'])
    if project.drive.upper()!='G:' or out.drive.upper()!='G:':raise ValueError('G: only')
    previous=read_json(previous_path)
    old=read_json(project/previous['derived_mesh']['path'])
    data=read_json(project/old['source_garment'])
    recipe=read_json(project/previous['recipe']['path'])
    spec=read_json(project/previous['preparation_spec']['path'])
    dossier=read_json(project/previous['construction_dossier']['path'])
    try:payload=build_mesh(data,recipe,regular_mesh=spec['regular_mesh'],dossier=dossier)
    except StudioError as exc:
        payload=getattr(exc,'garment_payload',None)
        if payload is None:raise
    plan=read_json(project/previous['assembly_plan']['path']);plan['mapping_sha256']=map_digest(payload)
    preform_error=None
    try:payload['placed_cm'],_=preform_coordinates(payload,plan)
    except StudioError as exc:
        preform_error=str(exc)
        if getattr(exc,'preform_coordinates_cm',None):payload['placed_cm']=exc.preform_coordinates_cm
    statistics=preparation_statistics(payload,payload['placed_cm'],recipe['mass'])
    minimum=statistics['extrema']['min_source_angle_degrees']['value']
    placed_minimum=statistics['extrema']['min_placed_angle_degrees']['value']
    target=spec['regular_mesh'].get('target_min_angle_degrees',15.)
    atomic_json(out/'mesh.json',payload)
    atomic_json(out/'statistics.json',statistics)
    report={'source_receipt':str(previous_path),'source_receipt_sha256':sha(previous_path),
        'source_garment_sha256':payload['source_garment_sha256'],'recipe_sha256':sha(project/previous['recipe']['path']),
        'source_min_angle_degrees':minimum,'placed_min_angle_degrees':placed_minimum,
        'source_min_edge_cm':statistics['extrema']['min_source_edge_cm']['value'],
        'placed_min_edge_cm':statistics['extrema']['min_placed_edge_cm']['value'],
        'max_principal_stretch':statistics['extrema']['max_principal_stretch']['value'],
        'target_min_angle_degrees':target,'target_reached':min(minimum,placed_minimum)>=target-1e-8,
        'refinement':payload['regular_preparation_refinement'],'vertices':len(payload['rest_cm']),
        'preform_error':preform_error,'simulation':'NOT_EXECUTED'}
    atomic_json(out/'result.json',report)
    print('NATIVE_PREPARATION_MESH_PROBE='+str(out/'result.json'),flush=True)
    print({key:value for key,value in report.items() if key!='refinement'},flush=True)
    if require_target and not report['target_reached']:raise AssertionError('Preparation mesh angle target not reached')


if __name__=='__main__':main()
