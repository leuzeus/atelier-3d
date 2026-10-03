"""Source-indexed shared stiffness hypotheses; no material inference from pixels."""
from .core import StudioError, digest
from .sewing import segment_distance

CHANNELS=('structural','shear','bending')
MAXIMA=('tension_stiffness_max','compression_stiffness_max','shear_stiffness_max','bending_stiffness_max')

def validate_regions(data,phase):
    config=phase.get('regional_stiffness')
    if not config:return
    profiles={p['id']:p for p in config['profiles']}
    if len(profiles)!=len(config['profiles']) or config['default_profile'] not in profiles:
        raise StudioError('Regional stiffness requires unique shared profiles and an existing default')
    selected=set()
    for row in config['assignments']:
        if row['piece'] not in data['pieces'] or row['piece'] in selected or row['profile'] not in profiles:
            raise StudioError('Regional stiffness assignments must select unique existing source panels and profiles')
        selected.add(row['piece'])
    edges=set()
    for row in config['reinforcements']:
        key=(row['piece'],row['edge'])
        if (row['piece'] not in data['pieces'] or row['edge'] not in data['pieces'][row['piece']]['edges']
            or row['profile'] not in profiles or key in edges):
            raise StudioError('Regional reinforcement requires a unique source edge and shared profile')
        edges.add(key)
    for name in MAXIMA:
        if config['ceilings'][name]<phase[name.removesuffix('_max')]:
            raise StudioError('Regional stiffness ceiling cannot be lower than the phase base')

def regional_weights(payload,config):
    profiles={p['id']:p for p in config['profiles']}
    assignments={p['piece']:p['profile'] for p in config['assignments']}
    count=len(payload['rest_cm']);weights={k:[0.]*count for k in CHANNELS};owner=set()
    for pid,panel in payload['panels'].items():
        profile=profiles[assignments.get(pid,config['default_profile'])]
        for i in panel['indices']:
            if i in owner or not 0<=i<count:raise StudioError('Regional stiffness requires unambiguous source panel indices')
            owner.add(i)
            for k in CHANNELS:weights[k][i]=profile[k+'_weight']
        regions=[r for r in config['reinforcements'] if r['piece']==pid]
        for i in panel['indices']:
            # Strongest proximity wins, then edge name: independent of list order.
            candidates=[]
            for r in regions:
                ids=panel['edges'][r['edge']]
                if len(ids)<2:raise StudioError('Regional reinforcement edge has no segments')
                p=payload['rest_cm'][i][:2]
                d=min(segment_distance(p,payload['rest_cm'][a][:2],payload['rest_cm'][b][:2]) for a,b in zip(ids,ids[1:]))
                candidates.append((max(0.,1-d/r['width_cm']),r['edge'],r['profile']))
            if candidates:
                f,_,ref=max(candidates);renfort=profiles[ref]
                for k in CHANNELS:weights[k][i]=(1-f)*weights[k][i]+f*renfort[k+'_weight']
    if owner!=set(range(count)):raise StudioError('Regional stiffness requires every derived vertex to belong to a source panel')
    return weights,{'configuration_sha256':digest(config),'source_garment_sha256':payload.get('source_garment_sha256'),
        'source_vertex_indices':payload.get('source_vertex_indices',list(range(count))),
        'weights_sha256':digest(weights),'profiles':config['profiles'],'assignments':config['assignments'],
        'reinforcements':config['reinforcements'],'ceilings':config['ceilings'],
        'interpretation':'BLENDER_GROUP_WEIGHTS_NOT_MEASURED_FABRIC_CONSTANTS','anisotropic_warp_weft':'NOT_IMPLEMENTED'}
