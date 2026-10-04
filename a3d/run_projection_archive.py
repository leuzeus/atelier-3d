"""Archive known mutable display projections without weakening artifact checks."""
import copy
import re
import shutil

from .core import StudioError,ident,inside,sha


ROLE='MUTABLE_PROJECT_PROJECTION_NOT_ARTIFACT'


def is_project_projection(path):
    return (path=='.a3d/blender/piece-candidates.json' or
            isinstance(path,str) and re.fullmatch(r'\.a3d/blender/working-[0-9a-f]+\.blend',path) is not None)


def _archive_path(attempt_id,reference):
    ident(attempt_id)
    if not isinstance(reference.get('sha256'),str) or re.fullmatch(r'[0-9a-f]{64}',reference['sha256']) is None:
        raise StudioError('Native projection archive requires an exact SHA-256')
    path=reference['path'].rsplit('/',1)[-1]
    stem,extension=path.rsplit('.',1)
    return '.a3d/runs/native/projections/'+attempt_id+'/'+stem+'-'+reference['sha256']+'.'+extension


def archive_projection_references(project,attempt_id,references):
    """Only the actual native callback may persist these source-bound copies."""
    files=[];projections=[]
    for reference in references:
        if not is_project_projection(reference['path']):
            files.append(copy.deepcopy(reference));continue
        source=inside(project.root,reference['path'])
        if sha(source)!=reference['sha256']:
            raise StudioError('Project projection changed before native archival')
        target_path=_archive_path(attempt_id,reference)
        target=inside(project.root,target_path,False)
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            with source.open('rb') as reader,target.open('xb') as writer:
                shutil.copyfileobj(reader,writer)
        if sha(target)!=reference['sha256'] or sha(source)!=reference['sha256']:
            raise StudioError('Native projection archive differs; preserve the orphan and restore entry')
        archived={'path':target_path,'sha256':reference['sha256']}
        files.append(archived)
        projections.append({'observed_ref':copy.deepcopy(reference),'archive_ref':archived,'role':ROLE})
    return sorted(files,key=lambda item:item['path']),projections


def verify_projection_archives(project,receipt):
    """Verify historical copies; live projections are explicitly separate views."""
    rows=receipt.get('project_projections',[])
    if not isinstance(rows,list):raise StudioError('Native projection archives must be a list')
    paths=set();observations=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'observed_ref','archive_ref','role'} or row['role']!=ROLE:
            raise StudioError('Native projection archive has no exact declared role')
        observed=row['observed_ref'];archived=row['archive_ref']
        if (not isinstance(observed,dict) or set(observed)!={'path','sha256'} or
                not isinstance(archived,dict) or set(archived)!={'path','sha256'} or
                not is_project_projection(observed['path']) or observed['path'] in paths or
                archived['path']!=_archive_path(receipt['attempt_id'],observed) or
                archived['sha256']!=observed['sha256'] or archived not in receipt['files'] or
                observed in receipt['files']):
            raise StudioError('Native projection archive is not bound to its exact attempt and source')
        path=inside(project.root,archived['path'])
        if not path.is_file() or sha(path)!=archived['sha256']:
            raise StudioError('Immutable native projection archive changed')
        paths.add(observed['path']);live=inside(project.root,observed['path'],False)
        current={'path':observed['path'],'sha256':sha(live)} if live.is_file() else None
        observations.append({**copy.deepcopy(row),'current_ref':current,
            'current_projection_status':'UNCHANGED' if current==observed else 'CHANGED' if current else 'ABSENT',
            'archive_status':'IMMUTABLE_REFERENCE_VERIFIED'})
    return observations


def archived_result_view(project,receipt,result):
    """An exact verification view, never a replacement for the native result."""
    rows=verify_projection_archives(project,receipt)
    by_path={row['observed_ref']['path']:row for row in rows}
    def visit(value):
        if isinstance(value,dict):
            if {'path','sha256'}<=set(value) and value['path'] in by_path:
                row=by_path[value['path']]
                if value['sha256']!=row['observed_ref']['sha256']:
                    raise StudioError('Native result contradicts its archived projection identity')
                return {**copy.deepcopy(value),**row['archive_ref']}
            return {key:visit(item) for key,item in value.items()}
        if isinstance(value,list):return [visit(item) for item in value]
        return copy.deepcopy(value)
    return visit(result)
