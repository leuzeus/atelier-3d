"""Archive known mutable display projections without weakening artifact checks."""
import copy
import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from .core import StudioError,ident,inside,sha


ROLE='MUTABLE_PROJECT_PROJECTION_NOT_ARTIFACT'
RECOVERY_ROLE='RESTORATION_ONLY'


def _is_working_projection(path):
    return isinstance(path,str) and re.fullmatch(r'\.a3d/blender/working-(?:recovered-)?[0-9a-f]+\.blend',path) is not None


def is_project_projection(path):
    return (path in ('.a3d/blender/piece-candidates.json','.a3d/blender/session.json') or
            _is_working_projection(path))


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


def _exact_bytes(project,reference):
    path=inside(project.root,reference['path'],False)
    if not path.is_file():return None
    data=path.read_bytes()
    return data if hashlib.sha256(data).hexdigest()==reference['sha256'] else None


def _session_reconstruction(project,reference,working_refs):
    if len(working_refs)!=1:
        raise StudioError('Historical session reconstruction requires one exact working reference')
    source=inside(project.root,reference['path'],False)
    if not source.is_file():raise StudioError('Current managed session is missing')
    def unique_object(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise StudioError('Managed session has duplicate JSON fields')
            result[key]=value
        return result
    def reject_constant(value):raise StudioError('Managed session has nonfinite JSON values')
    try:
        session=json.loads(source.read_bytes().decode('utf-8'),object_pairs_hook=unique_object,
                           parse_constant=reject_constant)
        if not isinstance(session,dict) or not isinstance(session.get('working'),str):
            raise StudioError('Managed session requires its existing working field')
        current=Path(session['working'])
        root=Path(project.root).resolve(strict=True)
        if not current.is_absolute():raise StudioError('Managed session working must be absolute')
        relative=current.relative_to(root).as_posix()
        if not _is_working_projection(relative) or inside(root,relative)!=current:
            raise StudioError('Current session working is not an exact managed working path')
        session['working']=str(inside(root,working_refs[0]['path'],False))
        data=json.dumps(session,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')+b'\n'
    except (ValueError,UnicodeError,OSError,TypeError) as error:
        raise StudioError('Historical session cannot be reconstructed from strict managed JSON') from error
    if hashlib.sha256(data).hexdigest()!=reference['sha256']:
        raise StudioError('Historical session reconstruction differs from its exact SHA-256')
    return data


def _recovery_projection_bytes(project,receipt):
    """Canonical receipt authentication belongs to the caller; no state is written."""
    ident(receipt['attempt_id'])
    references=receipt.get('files')
    if not isinstance(references,list):raise StudioError('Recovery files must be a list')
    verify_projection_archives(project,receipt)
    paths=set();validated=[]
    for reference in references:
        if (not isinstance(reference,dict) or set(reference)!={'path','sha256'} or
                not isinstance(reference['path'],str) or reference['path'] in paths or
                not isinstance(reference['sha256'],str) or re.fullmatch(r'[0-9a-f]{64}',reference['sha256']) is None):
            raise StudioError('Recovery requires unique exact file references')
        inside(project.root,reference['path'],False)
        paths.add(reference['path']);validated.append(reference)
    working_refs=[ref for ref in validated if _is_working_projection(ref['path'])]
    results=[];deferred=[]
    for reference in validated:
        if not is_project_projection(reference['path']):
            if _exact_bytes(project,reference) is None:
                raise StudioError('Immutable recovery artifact is absent or changed: '+reference['path'])
            continue
        target_path=_archive_path(receipt['attempt_id'],reference)
        target=inside(project.root,target_path,False)
        archive_ref={'path':target_path,'sha256':reference['sha256']}
        row={'observed_ref':copy.deepcopy(reference),'archive_ref':archive_ref,'role':RECOVERY_ROLE}
        if target.exists():
            data=_exact_bytes(project,archive_ref)
            if data is None:raise StudioError('Historical projection archive differs; preserve the orphan')
            row['evidence_source']='EXACT_ARCHIVE'
        else:
            data=_exact_bytes(project,reference)
            if data is not None:row['evidence_source']='EXACT_LIVE'
            elif reference['path']=='.a3d/blender/session.json':
                deferred.append((reference,row));continue
            else:raise StudioError('Historical projection is absent or changed without an exact archive')
        results.append((row,data))
    for reference,row in deferred:
        data=_session_reconstruction(project,reference,working_refs)
        row['evidence_source']='EXACT_SESSION_RECONSTRUCTION'
        results.append((row,data))
    return sorted(results,key=lambda item:item[0]['observed_ref']['path'])


def verify_recovery_projections(project,receipt):
    """Read-only historical identity proof for restoration; never authorizes replay."""
    return [row for row,_ in _recovery_projection_bytes(project,receipt)]


def archive_recovery_projections(project,receipt):
    """Freeze exact legacy projections before an authorized restoration mutates them.

    Does not rewrite receipts, SQLite, or live files. Existing differing archives
    remain untouched. All inputs are authenticated before the first archive write.
    """
    rows=_recovery_projection_bytes(project,receipt)
    for row,data in rows:
        reference=row['archive_ref'];target=inside(project.root,reference['path'],False)
        target.parent.mkdir(parents=True,exist_ok=True)
        try:
            with target.open('xb') as writer:
                writer.write(data);writer.flush();os.fsync(writer.fileno())
        except FileExistsError:
            pass
        if _exact_bytes(project,reference) is None:
            raise StudioError('Historical projection archive differs; preserve the orphan')
    return verify_recovery_projections(project,receipt)
