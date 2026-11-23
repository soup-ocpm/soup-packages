#!/usr/bin/env python3
"""Generate the catalog from published GitHub Release ZIP assets."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
TAG = re.compile(r"(?P<name>[a-z][a-z0-9_]*)/v(?P<version>[0-9][a-z0-9.]*)")
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024


class ReleaseManifestMismatch(ValueError):
    """The manifest identifies a different package or version than the tag."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def parse_metadata(text):
    metadata = json.loads(text, object_pairs_hook=unique_object)
    if not isinstance(metadata, dict):
        raise ValueError("manifest must be a JSON object")
    json.dumps(metadata, allow_nan=False)
    return metadata


def parse_tag(tag):
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError(f"expected a package release tag such as graph_explorer/v1.0.0, got {tag!r}")
    return match["name"], match["version"]


def asset_name(tag):
    name, version = parse_tag(tag)
    return f"{name}-{version}.zip"


def read_text(archive, name):
    with archive.open(name) as file:
        data = file.read(MAX_METADATA_BYTES + 1)
    if len(data) > MAX_METADATA_BYTES:
        raise ValueError(f"{name} exceeds the metadata size limit")
    return data.decode("utf-8")


def read_asset(path, tag):
    name, version = parse_tag(tag)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{tag}: expected ZIP file {path.name}")
    if path.stat().st_size > MAX_ZIP_BYTES:
        raise ValueError(f"{tag}: ZIP exceeds the SOUP installer size limit")
    with path.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
        source.seek(0)
        with ZipFile(source) as archive:
            metadata = parse_metadata(read_text(archive, f"{name}/soup-package.json"))
            if (metadata.get("name"), metadata.get("version")) != (name, version):
                raise ReleaseManifestMismatch(
                    f"{tag}: ZIP manifest declares {metadata.get('name')!r} "
                    f"version {metadata.get('version')!r}"
                )
            requirements = f"{name}/requirements.txt"
            if requirements in archive.namelist():
                specs = list(metadata.get("python_dependencies", []))
                for line in read_text(archive, requirements).splitlines():
                    spec = line.split(" #", 1)[0].strip()
                    if spec and not spec.startswith("#") and spec not in specs:
                        specs.append(spec)
                metadata["python_dependencies"] = specs
    return {**metadata, "sha256": checksum}


def github(*args, **kwargs):
    return subprocess.run(["gh", *args], check=True, **kwargs)


def list_releases(repo):
    pages = json.loads(github(
        "api", "--paginate", "--slurp", f"repos/{repo}/releases?per_page=100",
        stdout=subprocess.PIPE,
    ).stdout)
    return [release for page in pages for release in page]


def catalog_from_releases(repo):
    entries = {}
    with tempfile.TemporaryDirectory() as directory:
        for release in list_releases(repo):
            tag = release["tag_name"]
            if release["draft"] or not TAG.fullmatch(tag):
                continue
            filename = asset_name(tag)
            assets = [asset for asset in release["assets"] if asset["name"] == filename]
            if len(assets) != 1 or assets[0]["state"] != "uploaded":
                raise ValueError(f"{tag}: expected one uploaded release asset named {filename}")
            asset = assets[0]
            if asset["size"] > MAX_ZIP_BYTES:
                raise ValueError(f"{tag}: released ZIP exceeds the SOUP installer size limit")
            path = Path(directory) / filename
            with path.open("wb") as file:
                github(
                    "api", "-H", "Accept: application/octet-stream",
                    f"repos/{repo}/releases/assets/{asset['id']}", stdout=file,
                )
            try:
                metadata = read_asset(path, tag)
            except ReleaseManifestMismatch as error:
                print(f"Skipping release: {error}. The manifest must match the tag.", file=sys.stderr)
                continue
            finally:
                path.unlink()
            if digest := asset.get("digest"):
                if digest != f"sha256:{metadata['sha256']}":
                    raise ValueError(f"{tag}: downloaded ZIP does not match GitHub's digest")
            identity = parse_tag(tag)
            if identity in entries:
                raise ValueError(f"{tag}: duplicate release")
            entries[identity] = {**metadata, "download_url": asset["browser_download_url"]}
    return {"packages": [entries[key] for key in sorted(entries)]}


def publish_release(repo, tag, directory):
    path = directory / asset_name(tag)
    read_asset(path, tag)
    existing = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repo, "--json", "isDraft"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if existing.returncode == 0:
        release = json.loads(existing.stdout)
        if not release["isDraft"]:
            return
        github("release", "upload", tag, str(path), "--clobber", "--repo", repo)
        github("release", "edit", tag, "--draft=false", "--latest=false", "--repo", repo)
    else:
        github(
            "release", "create", tag, str(path), "--repo", repo,
            "--verify-tag", "--latest=false", "--title", tag,
            "--notes", f"Installable SOUP package for {tag}.",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "soup-ocpm/soup-packages"))
    parser.add_argument("--output", type=Path, default=ROOT / "catalog.json")
    parser.add_argument("--publish", nargs=2, metavar=("TAG", "ASSET_DIRECTORY"))
    args = parser.parse_args()
    try:
        if args.publish:
            tag, directory = args.publish
            publish_release(args.repo, tag, Path(directory))
        else:
            catalog = catalog_from_releases(args.repo)
            output = json.dumps(catalog, indent=2, sort_keys=True, allow_nan=False) + "\n"
            args.output.write_text(output, encoding="utf-8")
            print(f"Catalog contains {len(catalog['packages'])} released version(s)")
    except (OSError, ValueError, KeyError, BadZipFile, subprocess.CalledProcessError) as error:
        print(f"Release catalog failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
