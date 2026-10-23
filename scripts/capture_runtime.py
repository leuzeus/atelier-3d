"""Capture a stable source snapshot for isolated native validation on Windows."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(destination):
    destination = Path(destination).resolve()
    if destination.exists() or destination.drive.upper() != 'G:':
        raise ValueError('Use a new absolute directory on the approved G: workspace')
    # Match the complete distribution so hooks, MCP entrypoints, skills and
    # documentation contracts can also be tested on the immutable candidate.
    from package_plugin import inventory
    paths = inventory(ROOT)
    paths = sorted(set(paths), key=lambda path: path.relative_to(ROOT).as_posix())
    identities = {path.relative_to(ROOT).as_posix(): sha(path) for path in paths}
    destination.mkdir(parents=True)
    source = destination/'source'
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('Snapshot source escapes its declared checkout')
        relative = path.relative_to(ROOT)
        copied = source/relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copied)
        if sha(copied) != identities[relative.as_posix()]:
            raise ValueError('Snapshot changed while copying: '+relative.as_posix())
    for path in paths:
        if sha(path) != identities[path.relative_to(ROOT).as_posix()]:
            raise ValueError('Source changed during capture; preserve snapshot and retry')
    canonical = json.dumps(identities, sort_keys=True, separators=(',', ':')).encode()
    receipt = {'version': 1, 'status': 'IMMUTABLE_NATIVE_VALIDATION_SNAPSHOT',
               'source_checkout': str(ROOT), 'snapshot_root': str(source),
               'files': identities, 'files_count': len(identities),
               'identity_sha256': hashlib.sha256(canonical).hexdigest()}
    (destination/'capture.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    return {key: value for key, value in receipt.items() if key != 'files'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    print(json.dumps(capture(parser.parse_args().output)))
