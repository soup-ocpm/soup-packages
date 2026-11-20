#!/usr/bin/env python3
"""Validate package archives and generate the SOUP package catalog."""

import argparse
import hashlib
import json
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_BASE = "https://raw.githubusercontent.com/soup-ocpm/soup-packages/main/"
MANIFEST = "soup-package.json"
PACKAGE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*")
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+)*(?:[-+][a-zA-Z0-9]+(?:[.+-][a-zA-Z0-9]+)*)?")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"invalid JSON value {value}")


def path_parts(path):
    parts = path.split("/")
    if any(part in ("", ".", "..") or ":" in part for part in parts) or any(
        ord(char) < 32 or char == "\\" for char in path
    ):
        raise ValueError(f"unsafe archive path {path!r}")
    return parts


def validate_manifest(manifest, files, parent):
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    for field in ("name", "version", "api_version", "description"):
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
    if not PACKAGE_ID.fullmatch(manifest["name"]):
        raise ValueError("name must be a package ID using letters, digits, dots, underscores or hyphens")
    if "id" in manifest and manifest["id"] != manifest["name"]:
        raise ValueError("id must match name")
    for field in ("version", "api_version"):
        if not VERSION.fullmatch(manifest[field]):
            raise ValueError(f"{field} must be a numeric version with an optional suffix")
    for field in ("databases", "requires", "requires_tools", "provides_tools", "python_dependencies"):
        values = manifest.get(field, [])
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value.strip() for value in values
        ):
            raise ValueError(f"{field} must be an array of non-empty strings")
        if len(values) != len(set(values)):
            raise ValueError(f"{field} contains duplicate entries")
    if manifest["name"] in manifest.get("requires", []):
        raise ValueError("a package cannot require itself")
    if {"download_url", "sha256"} & manifest.keys():
        raise ValueError("download_url and sha256 are generated fields")

    if "app" in manifest:
        app = manifest["app"]
        if not isinstance(app, dict) or not isinstance(app.get("entry"), str):
            raise ValueError("app.entry must be a path relative to the app directory")
        entry = parent / "app" / PurePosixPath(*path_parts(app["entry"]))
        if entry not in files:
            raise ValueError(f"app.entry points to a missing file: {entry}")

    if "server" in manifest:
        server = manifest["server"]
        if not isinstance(server, dict) or any(
            not isinstance(server.get(field), str) or not server[field].strip()
            for field in ("module", "plugin")
        ):
            raise ValueError("server must contain non-empty module and plugin strings")


def read_manifest(archive):
    files = set()
    entries = set()
    for info in archive.infolist():
        name = info.orig_filename
        path = PurePosixPath(*path_parts(name.removesuffix("/") if info.is_dir() else name))
        if path in entries:
            raise ValueError(f"duplicate archive path {path}")
        entries.add(path)
        kind = stat.S_IFMT(info.external_attr >> 16) if info.create_system == 3 else 0
        expected = stat.S_IFDIR if info.is_dir() else stat.S_IFREG
        if kind not in (0, expected):
            raise ValueError(f"unsupported archive entry type: {path}")
        if info.flag_bits & 1:
            raise ValueError(f"encrypted archive entry: {path}")
        if not info.is_dir():
            files.add(path)

    for path in entries:
        if any(parent in files for parent in path.parents):
            raise ValueError(f"archive file used as a directory: {path}")
    package_files = {path for path in files if path.parts[0] != "__MACOSX"}
    manifests = [path for path in package_files if path.name == MANIFEST]
    if len(manifests) != 1 or len(manifests[0].parts) > 2:
        raise ValueError(f"expected one {MANIFEST} at the ZIP root or one directory below it")
    path = manifests[0]
    if any(not member.is_relative_to(path.parent) for member in package_files):
        raise ValueError("package files must share the manifest's root directory")

    manifest = json.loads(
        archive.read(str(path)).decode("utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    validate_manifest(manifest, package_files, path.parent)
    bad_file = archive.testzip()
    if bad_file is not None:
        raise ValueError(f"corrupt archive member: {bad_file}")
    return manifest


def build_catalog(base_url):
    packages_dir = ROOT / "packages"
    if not packages_dir.is_dir():
        raise ValueError("missing packages/ directory")
    entries = {}
    for path in sorted(packages_dir.rglob("*")):
        if path.suffix.lower() != ".zip":
            continue
        relative_path = path.relative_to(ROOT).as_posix()
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError("package ZIP must be a regular file")
            with path.open("rb") as source:
                with ZipFile(source) as archive:
                    manifest = read_manifest(archive)
                source.seek(0)
                checksum = hashlib.file_digest(source, "sha256").hexdigest()
            identity = manifest["name"], manifest["version"]
            if identity in entries:
                previous_path, _ = entries[identity]
                raise ValueError(f"duplicate package {identity[0]} {identity[1]} (also in {previous_path})")
            entry = {
                **manifest,
                "download_url": base_url + quote(relative_path, safe="/"),
                "sha256": checksum,
            }
            entries[identity] = relative_path, entry
        except (OSError, ValueError, BadZipFile, RuntimeError, EOFError, ZlibError) as error:
            raise ValueError(f"{relative_path}: {error}") from error
    return {"packages": [entries[key][1] for key in sorted(entries)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true", help="validate packages without writing the catalog")
    parser.add_argument("--base-url", default=DOWNLOAD_BASE, help="download URL prefix for the repository root")
    args = parser.parse_args()
    try:
        catalog = build_catalog(args.base_url.rstrip("/") + "/")
        output = json.dumps(catalog, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if not args.validate:
            (ROOT / "catalog.json").write_text(output, encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"Catalog generation failed: {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(catalog['packages'])} package(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
