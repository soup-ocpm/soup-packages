#!/usr/bin/env python3
"""Build and validate community packages with SOUP's own tooling."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOUP_REF = (ROOT / "scripts/soup-ref.txt").read_text().strip()
GENERATED = {"dist", "node_modules", "__pycache__", ".venv", ".DS_Store"}


def run(*command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def tracked_source_only(root):
    files = subprocess.check_output(["git", "-C", root, "ls-files", "-z"]).decode().split("\0")
    for name in filter(None, files):
        path = Path(name)
        if path.suffix.lower() == ".zip" or (
            path.parts[0] == "packages" and GENERATED.intersection(path.parts)
        ):
            raise ValueError(f"remove generated file from Git: {name}")


def exclude_generated(directory, names):
    ignored = shutil.ignore_patterns(*GENERATED, "*.[zZ][iI][pP]")(directory, names)
    for name in set(names) - ignored:
        path = Path(directory) / name
        if path.is_symlink():
            raise ValueError(f"symlinks are not allowed in package sources: {path}")
    return ignored


def stage_packages(source, workspace):
    packages = sorted((source / "packages").iterdir())
    for package in packages:
        if not package.is_dir() or package.is_symlink() or not re.fullmatch(r"[a-z][a-z0-9_]*", package.name):
            raise ValueError(f"invalid package directory: {package.name}")
        target = workspace / package.name
        if target.exists():
            if not (target / "soup-package.json").is_file():
                raise ValueError(f"package name conflicts with SOUP tooling: {package.name}")
            shutil.rmtree(target)
        shutil.copytree(package, target, ignore=exclude_generated)
    return [package.name for package in packages]


def build(args, temp):
    snapshot = temp / "soup.tar"
    run("git", "-C", args.soup, "archive", "--output", snapshot, SOUP_REF, "soup-packages", "soup-server")
    run("tar", "-xf", snapshot, "-C", temp)
    workspace = temp / "soup-packages"
    names = stage_packages(ROOT, workspace)
    env = {
        **os.environ,
        "PYTHONPATH": str(temp / "soup-server"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    run(
        sys.executable, "-I", "-B", ROOT / "scripts/check_packages.py", workspace, args.output,
        json.dumps(names), args.tag or "", env["PYTHONPATH"], env=env,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--soup", required=True, type=Path, help="SOUP Git checkout containing the pinned revision")
    parser.add_argument("--output", default=ROOT / "dist", type=Path, help="destination for built ZIPs")
    parser.add_argument("--tag", help="build only the package and version identified by this release tag")
    parser.add_argument("--check-tracked", action="store_true", help="reject generated files tracked by Git")
    args = parser.parse_args()
    try:
        if args.check_tracked:
            tracked_source_only(ROOT)
        with tempfile.TemporaryDirectory(prefix="soup-community-") as directory:
            build(args, Path(directory))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Package build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
