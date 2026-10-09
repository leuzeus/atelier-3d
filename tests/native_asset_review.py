"""Source-bound body review using the guarded dispatcher in an isolated Blender."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(receipt_path, output):
    import bpy
    from a3d.core import atomic_json, read_json, sha
    from blender.bootstrap import dispatch_current
    from a3d.store import Project
    assert bpy.app.background and not bpy.data.filepath
    output.mkdir(parents=True, exist_ok=False)
    prior = read_json(receipt_path)
    project = Project(receipt_path.parent/'project')
    results = []
    for item in prior['reports']:
        source = project.root/item['result']['artifact']['path']
        with bpy.data.libraries.load(str(source), link=False) as (available, loaded):
            names = list(available.objects)
        profile = {'version':1,'source_ref':item['result']['artifact'],'object_names':names,
                   'frame':1,'resolution':[540,720],'views':['front','side','back','threequarter'],'max_seconds':180.}
        path = project.root/(item['catalog_id']+'.review.json'); atomic_json(path, profile)
        result = dispatch_current(str(project.root),'render_asset_review',{'profile_path':path.relative_to(project.root).as_posix()})
        assert result['status'] == 'REVIEW_RENDERED' and len(result['images']) == 4
        assert all(sha(project.root/ref['path']) == ref['sha256'] for ref in result['images'].values())
        results.append({'catalog_id':item['catalog_id'],'review':result})
    record = {'status':'NATIVE_REVIEW_RENDERED','source_receipt':{'path':str(receipt_path),'sha256':sha(receipt_path)},
              'reports':results,'artistic_review':'NOT_EXECUTED','anatomical_review':'NOT_EXECUTED'}
    atomic_json(output/'receipt.json',record)
    print(json.dumps({'status':record['status'],'receipt':str(output/'receipt.json')}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--body-target-receipt',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if not args.output.is_absolute() or args.output.exists(): parser.error('Use a new absolute output directory')
    run(args.body_target_receipt.resolve(strict=True),args.output)
