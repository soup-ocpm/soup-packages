#!/usr/bin/env python3
"""Find and publish the current package versions approved on main."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from zipfile import BadZipFile

from generate_catalog import (
    ROOT, asset_name, list_releases, parse_metadata, parse_tag, publish_release, read_asset,
)


def approved_tags(root):
    approvals = parse_metadata((root / ".github/release-approvals.json").read_text(encoding="utf-8"))
    for package, version in sorted(approvals.items()):
        if not isinstance(version, str):
            raise ValueError(f"{package}: approved version must be a string")
        tag = f"{package}/v{version}"
        if parse_tag(tag) != (package, version):
            raise ValueError(f"{tag}: invalid approval")
        path = root / "packages" / package / "soup-package.json"
        manifest = parse_metadata(path.read_text(encoding="utf-8"))
        if manifest["name"] != package:
            raise ValueError(f"{package}: approval does not match the manifest name")
        if manifest["version"] == version:
            yield tag
        else:
            print(f"Skipping {tag}: current manifest version is {manifest['version']}", file=sys.stderr)


def pending_tags(root):
    catalog = parse_metadata((root / "catalog.json").read_text(encoding="utf-8"))
    published = {f"{entry['name']}/v{entry['version']}" for entry in catalog["packages"]}
    return [tag for tag in approved_tags(root) if tag not in published]


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def publish(root, repo, directory):
    approved = list(approved_tags(root))
    if not approved:
        return
    published = {release["tag_name"] for release in list_releases(repo) if not release["draft"]}
    pending = [tag for tag in approved if tag not in published]
    if not pending:
        return

    commit = git(root, "rev-parse", "HEAD")
    refs = {}
    for line in git(root, "ls-remote", "--tags", "origin").splitlines():
        sha, ref = line.split("\t")
        refs[ref] = sha

    missing = []
    for tag in pending:
        read_asset(directory / asset_name(tag), tag)
        ref = f"refs/tags/{tag}"
        existing = refs.get(ref + "^{}", refs.get(ref))
        if existing is None:
            missing.append(f"{commit}:{ref}")
        elif existing != commit:
            raise ValueError(f"{tag} already points to another commit; release that tag with the manual workflow")

    if missing:
        git(root, "push", "--atomic", "origin", *missing)
    for tag in pending:
        publish_release(repo, tag, directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", type=Path, metavar="ASSET_DIRECTORY")
    parser.add_argument("--repo", help="GitHub repository for publishing")
    args = parser.parse_args()
    if args.publish and not args.repo:
        parser.error("--publish requires --repo")
    try:
        if args.publish:
            publish(ROOT, args.repo, args.publish)
        else:
            print(json.dumps(pending_tags(ROOT)))
    except (OSError, ValueError, KeyError, BadZipFile, subprocess.CalledProcessError) as error:
        print(f"Approved releases failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
