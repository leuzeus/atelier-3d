"""Read-only recompilation diagnostic; no native scene or provider operation."""
import json
import os
from pathlib import Path
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from a3d.core import atomic_json,digest,inside,read_json,sha
from a3d.garment_planner import plan_assembly
from a3d.production_dossier import compile_project_dossier
from a3d.store import Project
from a3d.textile_executor import prepare_component_templates


def differences(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        for key in sorted(set(a)|set(b)):
            if key not in a or key not in b:
                yield {'path':path+'/'+key,'kind':'MISSING_KEY'}
            else:yield from differences(a[key],b[key],path+'/'+key)
    elif isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b):yield {'path':path,'kind':'LENGTH','stored':len(a),'reconstructed':len(b)}
        for index,(x,y) in enumerate(zip(a,b)):yield from differences(x,y,path+'/'+str(index))
    elif a!=b:yield {'path':path,'kind':'VALUE','stored':a,'reconstructed':b}


project=Project(Path(os.environ['A3D_PRODUCTION_PROJECT']))
request=read_json(inside(project.root,os.environ['A3D_PRODUCTION_REQUEST']))
templates=read_json(inside(project.root,request['templates_ref']['path']));inputs=templates['compiler_inputs']
def verified(ref):
    path=inside(project.root,ref['path']);assert sha(path)==ref['sha256'],ref
    return read_json(path)
compiled=compile_project_dossier(project,inputs['dossier_ref']['path'],inputs['production_spec_ref']['path'])
assembly=verified(inputs['assembly_plan_ref']);sources={}
for item in verified(inputs['production_spec_ref'])['packages']:
    with zipfile.ZipFile(inside(project.root,item['source_ref']['path'])) as archive:
        sources[item['component_id']]={'source_ref':item['source_ref'],'data':json.loads(archive.read('garment.json'))}
reconstructed=prepare_component_templates(assembly,sources,verified(inputs['guides_ref']),verified(inputs['standard_recipe_ref']),
    verified(inputs['dossier_ref']),inputs['dossier_ref'],inputs)
output=Path(os.environ['A3D_VALIDATION_OUTPUT']);output.mkdir(parents=True,exist_ok=True)
atomic_json(output/'reconstructed.json',reconstructed)
report={'status':'IDENTICAL' if reconstructed==templates else 'DIFFERS','stored_sha256':digest(templates),
    'reconstructed_sha256':digest(reconstructed),'differences':list(differences(templates,reconstructed)),
    'assembly_recompiled_equal':assembly==plan_assembly(compiled['assembly_spec'],capabilities=['coupled_multilayer']),
    'python_version':sys.version,'scene_mutated':False,'simulation':'NOT_EXECUTED','qualification':'NONE'}
atomic_json(output/'result.json',report)
print(json.dumps(report,ensure_ascii=False),flush=True)
