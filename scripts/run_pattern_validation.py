"""Run a repository-owned Blender validation in an isolated G: profile.

No interaction with the connected Blender, no publication and no asset download.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('script')
    parser.add_argument('--output', required=True)
    parser.add_argument('--blender', default='C:/Program Files/Blender Foundation/Blender 5.2/blender.exe')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('arguments', nargs='*')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    script = (root / args.script).resolve(strict=True)
    output = Path(args.output).resolve()
    if not script.is_relative_to(root) or output.drive.upper() != 'G:':
        raise ValueError('Owned repository script and G: output required')
    output.mkdir(parents=True, exist_ok=False)
    profile = output / 'profile'
    profile.mkdir()
    temporary = output / 'tmp'
    temporary.mkdir()
    env = dict(os.environ, BLENDER_USER_RESOURCES=str(profile),
               PYTHONDONTWRITEBYTECODE='1', TMP=str(temporary), TEMP=str(temporary),
               A3D_VALIDATION_OUTPUT=str(output))
    def code_identity():
        paths={script,Path(__file__).resolve()}
        for folder in ('a3d','blender','tests'):
            paths.update((root/folder).rglob('*.py'))
        return {path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(paths)}
    code_before=code_identity()
    (output/'code-before.json').write_text(json.dumps(code_before,indent=2),encoding='utf-8')
    start = time.monotonic()
    with (output / 'blender.log').open('w', encoding='utf-8') as stream:
        process = subprocess.run([args.blender, '--background', '--factory-startup',
            '--disable-autoexec', '--python-exit-code', '1', '--python', str(script),
            '--', *args.arguments], env=env, stdout=stream, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=args.timeout)
    report = {'script': str(script), 'exit_code': process.returncode,
              'seconds': time.monotonic()-start, 'profile': str(profile),
              'code_before':'code-before.json','code_after':'code-after.json'}
    code_after=code_identity()
    (output/'code-after.json').write_text(json.dumps(code_after,indent=2),encoding='utf-8')
    report['code_changed_during_run']=[name for name in sorted(set(code_before)|set(code_after))
        if code_before.get(name)!=code_after.get(name)]
    report['execution_identity']='UNCHANGED_CODE_SNAPSHOT' if not report['code_changed_during_run'] else 'CODE_CHANGED_SEE_INPUT_RECEIPTS'
    (output / 'launch.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    print((output / 'blender.log').read_text(encoding='utf-8')[-5000:])
    return process.returncode


if __name__ == '__main__':
    raise SystemExit(main())
