"""Read-only measurement campaign on exact previously captured native body data.

This uses ordinary Python; no Blender process or geometry capture is performed.
An existing canonical native body introduction/preparation and an explicit
measurement policy are required. Output lives in a new directory on G:, while
the source project, approved body, targets and native receipts remain intact.
"""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def arguments(argv):
    from a3d.core import inside
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True);parser.add_argument('--spec',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--validate-only',action='store_true')
    args=parser.parse_args(argv);project=Path(args.project);output=Path(args.output)
    if (not project.is_absolute() or project.drive.lower()!='g:' or
            not (project/'.a3d/state.sqlite3').is_file() or
            not output.is_absolute() or output.drive.lower()!='g:' or output.exists() or
            output.resolve().is_relative_to(project.resolve())):
        parser.error('Require an existing G: canonical project and a new output directory outside that project')
    try:inside(project,args.spec)
    except ValueError as error:parser.error(str(error))
    args.project=project.resolve();args.output=output.resolve();return args


def run(args):
    from a3d.body_region_sections import measure_project_body_regions
    from a3d.core import atomic_json,digest,inside,read_json,sha
    from a3d.store import Project
    project=Project(args.project);specification=read_json(inside(project.root,args.spec))
    protected={args.spec:sha(inside(project.root,args.spec))}
    def collect(value):
        if isinstance(value,dict):
            if set(value)=={'path','sha256'}:
                protected[value['path']]=value['sha256']
            else:
                for child in value.values():collect(child)
        elif isinstance(value,list):
            for child in value:collect(child)
    collect(specification);database_sha=sha(project.db);state_sha=digest(project.state())
    result=measure_project_body_regions(project,args.spec)
    assert sha(project.db)==database_sha and digest(project.state())==state_sha
    assert all(sha(inside(project.root,path))==identity for path,identity in protected.items())
    args.output.mkdir(parents=True,exist_ok=False);atomic_json(args.output/'supplement.json',result)
    receipt={'version':1,'status':'BODY_REGION_SOURCE_MEASUREMENTS_RECORDED',
             'source_project':str(project.root),'result_status':result['status'],
             'specification_ref':result['specification_ref'],'supplement_sha256':sha(args.output/'supplement.json'),
             'native_body_origin':result['native_body_origin'],'body_changed':False,'profile_changed':False,
             'source_database_preserved':True,'source_files_preserved':True,
             'new_native_geometry_capture':'NOT_EXECUTED','blender':'NOT_REQUIRED',
             'dressing':'NOT_EXECUTED','physical_passage':'NOT_QUALIFIED','fitting':'NOT_EXECUTED',
             'acceptance':'NOT_GRANTED'}
    atomic_json(args.output/'receipt.json',receipt)
    print('BODY_REGION_SOURCE_MEASUREMENTS_RECORDED: '+result['status']+' '+str(args.output/'receipt.json'))


if __name__=='__main__':
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args=arguments(argv)
    if args.validate_only:print('ARGUMENTS_VALIDATED: no source measurement executed')
    else:run(args)
