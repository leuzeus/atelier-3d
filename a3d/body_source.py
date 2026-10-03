"""Explicit selected body source; no inference from names, height or old reports."""
from pathlib import Path
from .core import StudioError,contract,inside,read_json,sha

def selection(project,selection_path):
    descriptor=inside(project.root,selection_path)
    data=contract('body-source',read_json(descriptor))
    if set(data['meshes']) & set(data['dependencies']):
        raise StudioError('Body meshes and dependency lists must be disjoint')
    source=Path(data['source_blend'])
    if not source.is_absolute():source=inside(project.root,data['source_blend'])
    source=source.resolve(strict=True)
    if source.suffix.lower()!='.blend' or sha(source)!=data['source_sha256']:
        raise StudioError('Body source identity changed')
    return data,source,sha(descriptor)
