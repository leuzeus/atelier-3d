from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import tempfile
import uuid
import zipfile
from pathlib import Path

from .core import StudioError, atomic_json, canonical, contract, inside, now, read_json, relative, sha

MAX_TOTAL = 512 * 1024 * 1024
MAX_FILE = 128 * 1024 * 1024
SUFFIX = {"PATTERN_SEWN": ".garmentpkg", "MULTIVIEW_PART": ".partpkg"}


def png_dimensions(data):
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise StudioError("Clean reference must be a PNG with valid IHDR")
    w, h = struct.unpack(">II", data[16:24])
    if not (1 <= w <= 16384 and 1 <= h <= 16384):
        raise StudioError("Invalid PNG dimensions")
    return [w, h]


def check_manifest(manifest, get):
    contract("package", manifest)
    if manifest["pipeline"] == "MULTIVIEW_PART":
        part = contract("part-package", json.loads(get("part.json")))
        if part["component_id"] != manifest["component_id"]:
            raise StudioError("Part identity mismatch")
        for view in part["required_views"]:
            if view not in part["views"]:
                raise StudioError(f"Required view missing: {view}")
        for view, rec in part["views"].items():
            if rec["role"] != "clean" or any(x in rec["path"].lower() for x in ("overlay", "annotation", ".mask.")):
                raise StudioError("Reconstruction view must be clean")
            if png_dimensions(get(rec["path"])) != rec["dimensions"]:
                raise StudioError("Reference dimensions mismatch")
            if rec["camera"]["projection"] != "orthographic":
                raise StudioError("Part reconstruction requires declared orthographic cameras")
        if not part["anchors"]:
            raise StudioError("Part needs an assembly anchor")
    else:
        garment = contract("garment", json.loads(get("garment.json")))
        if garment["component_id"] != manifest["component_id"]:
            raise StudioError("Garment identity mismatch")
        import xml.etree.ElementTree as ET
        svg = get("pattern.svg")
        if b"<!DOCTYPE" in svg.upper() or b"<!ENTITY" in svg.upper():
            raise StudioError("SVG entities are forbidden")
        svgroot = ET.fromstring(svg)
        if svgroot.tag.rsplit("}", 1)[-1] != "svg":
            raise StudioError("Expected SVG")
        polygons = {}
        for element in svgroot.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag not in ("svg", "g", "polygon", "line", "text", "title", "desc"):
                raise StudioError("V1 patterns support explicit polygon panels only")
            if any(k.lower().startswith("on") or "href" in k for k in element.attrib):
                raise StudioError("Active SVG content is forbidden")
            if tag == "polygon":
                if "transform" in element.attrib or element.get("id") in polygons:
                    raise StudioError("Panel transforms or duplicate IDs are not supported")
                try:
                    polygons[element.get("id")] = [[float(v) for v in pair.split(",")] for pair in element.get("points", "").split()]
                except ValueError as exc:
                    raise StudioError("Invalid polygon points") from exc
        pieces = garment["pieces"]
        if set(polygons) != set(pieces):
            raise StudioError("Pattern polygons must match all garment pieces")
        for pid, piece in pieces.items():
            if polygons[pid] != piece["vertices"]:
                raise StudioError("SVG and garment geometry differ")
            n = len(piece["vertices"])
            for face in piece["faces"]:
                if len(set(face)) != len(face) or any(i < 0 or i >= n for i in face):
                    raise StudioError("Invalid panel face indices")
            for edge in piece["edges"].values():
                if len(set(edge)) != len(edge) or any(i < 0 or i >= n for i in edge):
                    raise StudioError("Invalid seam edge indices")
        for seam in garment["seams"]:
            try:
                a = pieces[seam["piece_a"]]["edges"][seam["edge_a"]]
                b = pieces[seam["piece_b"]]["edges"][seam["edge_b"]]
            except KeyError as exc:
                raise StudioError("Dangling seam reference") from exc
            if seam["piece_a"] == seam["piece_b"] or len(a) != len(b):
                raise StudioError("Seam needs distinct panels with equal vertex counts")
    for name in manifest["entrypoints"].values():
        get(name)
    return manifest


def inspect_package(path):
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        if not names or "manifest.json" not in names or len(names) > 4096:
            raise StudioError("Invalid package inventory")
        if len({n.casefold() for n in names}) != len(names):
            raise StudioError("Duplicate/case-colliding ZIP member")
        if sum(i.file_size for i in infos) > MAX_TOTAL:
            raise StudioError("Package too large")
        for info in infos:
            relative(info.filename)
            if info.is_dir() or info.file_size > MAX_FILE or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise StudioError("Unsupported ZIP entry")
            if info.file_size > 1024 * 1024 and info.file_size > max(1, info.compress_size) * 1000:
                raise StudioError("Unsafe compression ratio")
        if archive.getinfo("manifest.json").file_size > 2 * 1024 * 1024:
            raise StudioError("Manifest too large")
        manifest = json.loads(archive.read("manifest.json"))
        contract("package", manifest)
        if Path(path).suffix not in (SUFFIX[manifest["pipeline"]], ".3dpkg"):
            raise StudioError("Package extension and pipeline mismatch")
        if set(manifest["checksums"]) != set(names) - {"manifest.json"}:
            raise StudioError("Checksum inventory must cover every payload file")
        for name, expected in manifest["checksums"].items():
            with archive.open(name) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if expected != actual:
                raise StudioError(f"Checksum mismatch: {name}")

        def get(name):
            relative(name)
            if name not in manifest["checksums"]:
                raise StudioError(f"Missing package member: {name}")
            return archive.read(name)
        return check_manifest(manifest, get)


def build_package(source_dir, destination, asset_id, component_id, pipeline, provenance):
    from .core import ident
    ident(asset_id)
    ident(component_id)
    if pipeline not in SUFFIX:
        raise StudioError("Unsupported pipeline")
    source = Path(source_dir).resolve(strict=True)
    dest = Path(destination).absolute()
    if dest.exists() or dest.is_relative_to(source):
        raise StudioError("Archive must be new and outside package source")
    if dest.suffix != SUFFIX[pipeline]:
        raise StudioError("Wrong archive extension")
    members = {}
    for file in source.rglob("*"):
        if file.is_symlink() or (hasattr(file, "is_junction") and file.is_junction()):
            raise StudioError("Package cannot contain links")
        if file.is_file():
            name = relative(file.relative_to(source).as_posix())
            if name == "manifest.json":
                raise StudioError("Manifest is generated, not supplied")
            if file.suffix.lower() not in (".json", ".png", ".svg") or any(p.startswith(".") for p in file.relative_to(source).parts):
                raise StudioError("Package payload is limited to JSON, PNG and SVG")
            members[name] = sha(file)
    manifest = {"format": "codex-3d-package", "schema_version": "1.0", "package_id": str(uuid.uuid4()),
                "asset_id": asset_id, "component_id": component_id, "pipeline": pipeline, "created_at": now(), "units": "cm",
                "coordinate_system": {"up": "Z", "front": "-Y", "handedness": "right"},
                "entrypoints": {"component": "garment.json" if pipeline == "PATTERN_SEWN" else "part.json"},
                "dependencies": [], "provenance": provenance, "checksums": members}
    check_manifest(manifest, lambda name: inside(source, name).read_bytes())
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with dest.open("xb") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", canonical(manifest))
                for name in sorted(members):
                    archive.write(inside(source, name), name)
        inspect_package(dest)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return {"path": str(dest), "sha256": sha(dest), "manifest": manifest}


def extract_package(archive_path, destination):
    manifest = inspect_package(archive_path)
    destination = Path(destination).absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise StudioError("Extract destination must not exist")
    temp = Path(tempfile.mkdtemp(prefix=".extract-", dir=destination.parent))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                target = inside(temp, info.filename, must_exist=False)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as out:
                    shutil.copyfileobj(source, out)
        os.rename(temp, destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return manifest
