"""Exact source-index transfer of a qualified local sewing result, in cm."""
import copy
import math
from .core import StudioError
from .sewing import mesh_quality


def local_status(report,binding):
    """Only the latest projection for this exact candidate can grant/block full."""
    if not report or report.get('binding')!=binding:return None
    return report.get('simulation')


def transfer_coordinates(payload,recipe,report):
    if report.get('simulation')!='PASS' or report.get('scope')!='local' or report.get('qualification')!='PHYSICS_ONLY':
        raise StudioError('Transfer requires a completed local PHYSICS_ONLY result without temporary tacks')
    if report.get('fitting_tacks') or (report.get('context') or {}).get('colliders'):
        raise StudioError('Only a collider-free result without fitting tacks can enter assembly')
    if report.get('units','cm')!='cm':raise StudioError('Sewing transfer requires centimeter coordinates')
    if report.get('trial_pieces')!=recipe['trial_pieces']:raise StudioError('Result panel selection changed')
    expected=sorted(i for pid in recipe['trial_pieces'] for i in payload['panels'][pid]['indices'])
    # Pre-0.6.1 results imply this order through their complete trial binding.
    if report.get('source_vertex_indices',expected)!=expected:raise StudioError('Result source indices changed')
    coords=report.get('local_result_cm')
    if not isinstance(coords,list) or len(coords)!=len(expected):raise StudioError('Local result coordinate count differs from its source mapping')
    if any(not isinstance(p,list) or len(p)!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in p) for p in coords):
        raise StudioError('Malformed or non-finite sewing coordinates')
    placed=copy.deepcopy(payload['placed_cm'])
    for index,point in zip(expected,coords,strict=True):placed[index]=list(point)
    mesh_quality(payload['rest_cm'],placed,payload['faces'],recipe['mesh'])
    return placed,expected
