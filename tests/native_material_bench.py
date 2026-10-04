"""Optional isolated native coupon qualification. Run only on an approved G: lab.

Usage: blender --background --factory-startup --offline-mode --python-exit-code 1
       --python tests/native_material_bench.py -- --output G:/.../NEW-DIRECTORY
Every coupon uses the production evaluated-frame observer. PASS remains
COUPON_ONLY; time/frame exhaustion is deliberately retained as INCOMPLETE.
"""
import argparse
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',required=True)
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--experiment',choices=('legacy-bending','supported-damping'),default='legacy-bending')
    parser.add_argument('--validate-only', action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:])
    output=Path(args.output).resolve()
    if output.drive.upper()!='G:' or output.exists():
        raise ValueError('Native material lab must use a fresh approved G: directory')
    from a3d.core import read_json, contract
    from a3d.material_bench import laboratory_conditions, coupon, SUPPORTED_SEEDS, LEGACY_SEEDS
    seed = SUPPORTED_SEEDS if args.experiment=='supported-damping' else LEGACY_SEEDS
    conditions=laboratory_conditions(seed)
    recipe=contract('sewing-recipe',read_json(ROOT/'templates/sewing-recipe.json'))
    programs=['cantilever','sewing','contact'] if args.full else ['cantilever']
    for program in programs:
        payload=coupon(program,recipe['mesh']['spacing_cm'],seed)
        assert len(payload['rest_cm'])<=recipe['mesh']['max_vertices']
    if args.validate_only:
        print('Arguments valid; experiment='+args.experiment+'; source conditions='+str(conditions)+'; no execution')
        return
    output.mkdir(parents=True)
    import bpy
    from a3d.core import atomic_json,read_json,sha
    from a3d.material_bench import compile_material_bench,run_material_bench
    from a3d.store import Project
    from tests.support import asset
    from tests.test_material_bench import bench_fixture
    bpy.context.preferences.filepaths.temporary_directory=str(output/'tmp')
    bpy.context.preferences.filepaths.save_version=0
    project=Project.create(output/'project',asset(True)); spec=bench_fixture(project)
    spec['laboratory']={'seed_set':seed}
    if args.experiment=='supported-damping':
        spec['id']='material-supported-damping'
        spec['factor']={'parameter':'structural_damping','values':[1.,20.]}
    if args.full:
        spec['programs']=['cantilever', 'sewing', 'contact']
        spec['execution'].update(max_frames=240,min_frames=24,window_frames=8,max_seconds=45.)
    else:
        spec['programs']=['cantilever']; spec['execution'].update(max_frames=8,min_frames=4,window_frames=3,max_seconds=3.)
    atomic_json(project.root/'spec.json',spec)
    prepared=compile_material_bench(project,'spec.json','compiled')
    before={obj.name:sha(project.root/'candidate.json') for obj in bpy.context.scene.objects}
    from a3d.runs import create_run, next_run_step, run_status
    created=create_run(project,'material_bench',prepared['run_specification']['path'])
    step=next_run_step(project,created['run_id'])
    scope={}; exec(step['code'],scope); result=scope['result']
    journal=run_status(project,created['run_id'])
    report=read_json(project.root/result['report']['path'])
    assert report['original_scene_unchanged'] and not report['accepted']
    assert report['fitting']==report['garment_simulation']=='NOT_EXECUTED'
    assert len(report['rows'])==(6 if args.full else 2)
    assert all(row['status'] in ('PASS','FAIL','INCOMPLETE') for row in report['rows'])
    assert report['laboratory_conditions']==conditions
    for row in report['rows']:
        observation=row.get('observations')
        if observation:
            assert observation['evaluated_frame_count']==len(observation['samples'])
            assert [sample['frame'] for sample in observation['samples']]==list(range(1,len(observation['samples'])+1))
    for program in spec['programs']:
        rows=[row for row in report['rows'] if row['program']==program]
        assert len({row['coupon_sha256'] for row in rows})==1
        assert len({row['source_conditions_sha256'] for row in rows})==1
    assert {obj.name:sha(project.root/'candidate.json') for obj in bpy.context.scene.objects}==before
    assert all(row['execution_control']['stop_reason'] in ('MEASURED_CONVERGENCE','TIME_BUDGET','FRAME_BUDGET')
               or row['status']=='FAIL' and row['execution_control']['stop_reason'] is None
               for row in report['rows'] if row['execution_control'])
    atomic_json(output/'receipt.json',{'result':result,'qualification':'COUPON_ONLY',
        'fitting':'NOT_EXECUTED','original_scene_unchanged':True,'report_sha256':sha(project.root/result['report']['path']),
        'run_id':created['run_id'],'run_status':journal['status'],
        'pipeline_checks':'PASS','coupon_result':report['status'],
        'experiment':args.experiment,'laboratory_conditions':conditions,
        'source_recipe':spec['bindings']['recipe'],'factor':spec['factor'],'execution':spec['execution'],
        'coupon_statuses':{row['case_id']:row['status'] for row in report['rows']}})
    print('Native material benchmark retained '+report['status']+'; no fitting acceptance')


if __name__=='__main__': main()
