"""Immutable PNG intake with dimensions, provenance and a deterministic contact sheet."""
import base64
import html
import shutil
from pathlib import Path
from .core import StudioError, atomic_json, digest, ident, inside, sha
from .packages import png_dimensions


def import_references(project, source_root, references):
    source_root = Path(source_root).resolve(strict=True)
    if not isinstance(references, list) or not references:
        raise StudioError('Declare reference identities, paths, hashes and provenance')
    entries = []
    names = set()
    for row in sorted(references, key=lambda value: value['id']):
        if set(row) != {'id', 'path', 'sha256', 'provenance'} or not isinstance(row['provenance'], str) or not row['provenance'].strip():
            raise StudioError('Reference provenance must be explicit')
        name = ident(row['id'])
        if name in names: raise StudioError('Duplicate reference identity')
        names.add(name)
        source = inside(source_root, row['path'])
        if source.suffix.lower() != '.png' or source.stat().st_size > 32*1024*1024:
            raise StudioError('Reference intake supports PNG up to 32 MiB')
        checksum = sha(source)
        if checksum != row['sha256']: raise StudioError('Declared reference source changed')
        dimensions = png_dimensions(source.read_bytes())
        output = inside(project.root, 'references/imported/'+checksum+'.png', False)
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists():
            with source.open('rb') as src, output.open('xb') as dst: shutil.copyfileobj(src, dst)
        if sha(output) != checksum or sha(source) != checksum:
            raise StudioError('Reference identity changed during intake')
        entries.append({'id': name, 'path': output.relative_to(project.root).as_posix(),
                        'sha256': checksum, 'dimensions_px': dimensions, 'provenance': row['provenance'],
                        'original_root': str(source_root), 'original_path': row['path']})
    identity = digest(entries)
    folder = project.root/'references/imported'
    sheet = folder/(identity+'.svg')
    width = 1200; card_w = 400; card_h = 420; rows = (len(entries)+2)//3
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{rows*card_h}">',
                '<rect width="100%" height="100%" fill="#f3f4f6"/>']
    for index, row in enumerate(entries):
        x, y = index%3*card_w, index//3*card_h
        data = base64.b64encode(inside(project.root, row['path']).read_bytes()).decode()
        label = html.escape(f"{row['id']} · {row['dimensions_px'][0]} × {row['dimensions_px'][1]} px")
        elements.extend([f'<image x="{x+12}" y="{y+12}" width="376" height="360" preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{data}"/>',
                         f'<text x="{x+12}" y="{y+399}" font-family="Segoe UI, sans-serif" font-size="16">{label}</text>'])
    elements.append('</svg>')
    content = '\n'.join(elements)
    if sheet.exists() and sheet.read_text(encoding='utf-8') != content:
        raise StudioError('Immutable reference contact sheet changed')
    if not sheet.exists(): sheet.write_text(content, encoding='utf-8')
    report = {'version': 1, 'status': 'REFERENCES_IMPORTED', 'identity': identity, 'references': entries,
              'contact_sheet': {'path': sheet.relative_to(project.root).as_posix(), 'sha256': sha(sheet)},
              'visual_review': 'NOT_EXECUTED', 'orthographic_qualification': 'NOT_INFERRED'}
    atomic_json(folder/(identity+'.json'), report)
    return report
