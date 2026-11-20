"""Run checks inside the temporary workspace prepared by build_packages.py."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

workspace, output, names, tag, soup_server = sys.argv[1:]
sys.path.insert(0, soup_server)
sys.path.insert(1, str(Path(__file__).resolve().parent))

from generate_catalog import parse_metadata, parse_tag
from soup.core.contracts import ValidationError, is_api_compatible
from soup.core.ordering import topological_order
from soup.core.packages import discover_packages, load_manifest
from soup.core.packages.archive import extract_package_zip
from soup.core.packages.dependencies import python_dependency_problems

workspace = Path(workspace)
output = Path(output)
names = json.loads(names)

discovery = discover_packages([workspace], workspace / "dist")
if discovery.failures:
    raise SystemExit("\n".join(f"{name}: {error}" for name, error in discovery.failures))
sources = discovery.sources
providers = {}
for name, source in sources.items():
    for tool in source.manifest.provides_tools:
        providers.setdefault(tool, []).append(name)


def dependencies(name):
    manifest = sources[name].manifest
    if not is_api_compatible(manifest.api_version):
        raise ValueError(f"{name}: incompatible SOUP API {manifest.api_version}")
    result = set(manifest.requires)
    for tool in set(manifest.requires_tools) - set(manifest.provides_tools):
        owners = providers.get(tool, [])
        if len(owners) != 1:
            raise ValueError(f"{name}: expected one provider of tool {tool!r}, found {owners}")
        result.update(owners)
    if missing := result - sources.keys():
        raise ValueError(f"{name}: unknown package dependencies: {', '.join(sorted(missing))}")
    return sorted(result)


def dependency_order(name):
    graph = {}
    pending = [name]
    while pending:
        current = pending.pop()
        if current not in graph:
            graph[current] = dependencies(current)
            pending.extend(graph[current])
    order, cyclic = topological_order(list(graph), graph)
    if cyclic:
        raise ValueError(f"{name}: dependency cycle involving {', '.join(cyclic)}")
    return order


def run(*command, **kwargs):
    subprocess.run(command, cwd=workspace, check=True, **kwargs)


def validate_backend(order, extracted, test_directory):
    requirements = set()
    for name in order:
        manifest = sources[name].manifest
        requirements.update(manifest.python_dependencies)
    libraries = extracted.parent / "dependencies"
    env = os.environ.copy()
    if requirements:
        from packaging.requirements import Requirement

        if any(Requirement(spec).url for spec in requirements):
            raise ValueError("direct URLs are unsupported for Python dependencies")
        if any(python_dependency_problems(sources[name].manifest) for name in order):
            run(
                sys.executable, "-I", "-m", "pip", "install", "--only-binary=:all:",
                "--constraint", Path(soup_server) / "requirements.txt", "--target", libraries,
                *sorted(requirements),
            )
            env["PYTHONPATH"] += os.pathsep + str(libraries)
    package_dirs = [str(sources[name].path) for name in order[:-1]]
    run(
        sys.executable, "-P", "-c", """
import sys
import unittest
from pathlib import Path
from soup.core.packages import ORIGIN_INSTALLED, PackageSource, load_manifest, plugin_factory
from soup.core.packages.dependencies import python_dependency_problems

tests, *packages = map(Path, sys.argv[1:])
for path in packages:
    manifest = load_manifest(path)
    problems = python_dependency_problems(manifest)
    if problems:
        raise SystemExit(f"{manifest.name}: {', '.join(problems)}")
    plugin_factory(PackageSource(manifest, path, ORIGIN_INSTALLED))()
if any(tests.rglob("test_*.py")):
    suite = unittest.defaultTestLoader.discover(str(tests))
    if not suite.countTestCases():
        raise SystemExit(f"{tests}: no unittest cases found")
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        sys.exit(1)
""",
        test_directory, *package_dirs, extracted, env=env,
    )


def main():
    for name in names:
        if name not in sources:
            raise ValueError(f"{name}: missing soup-package.json")
        manifest = sources[name].manifest
        if not manifest.description.strip():
            raise ValueError(f"{name}: add a description to soup-package.json")
        if not (sources[name].path / "README.md").is_file():
            raise ValueError(f"{name}: add a package README.md")
        parse_tag(f"{name}/v{manifest.version}")
        if str(manifest.parsed_version) != manifest.version:
            raise ValueError(f"{name}: use a normalized version such as {manifest.parsed_version}")
        raw = parse_metadata((sources[name].path / "soup-package.json").read_text(encoding="utf-8"))
        if "id" in raw and raw["id"] != name:
            raise ValueError(f"{name}: manifest id must match name")
        if {"sha256", "download_url"} & raw.keys():
            raise ValueError(f"{name}: sha256 and download_url are generated fields")

        path = sources[name].path
        if manifest.app_entry:
            for file in ("package.json", "tsconfig.json", "src/index.ts"):
                if not (path / "app" / file).is_file():
                    raise ValueError(f"{name}: missing app/{file}")
        elif (path / "app").exists():
            raise ValueError(f"{name}: app/ requires an app.entry in the manifest")

    selected = {f"{name}/v{sources[name].manifest.version}": name for name in names}
    if tag and tag not in selected:
        raise ValueError(f"{tag}: tag must match a package's name and manifest version")
    targets = [selected[tag]] if tag else names
    orders = {name: dependency_order(name) for name in targets}
    apps = [name for name in targets if sources[name].manifest.app_entry]
    if targets:
        # npm retains the pinned SOUP tooling while resolving dependencies for new workspaces.
        run("npm", "install", "--ignore-scripts", "--no-audit", "--no-fund")
    if apps:
        run("npm", "run", "build:packages", "--", *apps)
        for name in apps:
            if any((workspace / name / "app/test").rglob("*.test.ts")):
                run("npm", "test", "--", f"{name}/app/test/")

    for name in targets:
        manifest = sources[name].manifest
        run("npm", "run", "pack", "--", name)
        archive = workspace / "dist" / f"{name}-{manifest.version}.zip"
        with archive.open("rb") as stream:
            extracted = extract_package_zip(stream, workspace / "installed" / name)
        installed = load_manifest(extracted)
        if installed != manifest or (installed.app_entry and not (extracted / "app" / installed.app_entry).is_file()):
            raise ValueError(f"{name}: packaged manifest or frontend entry does not match the source")
        validate_backend(orders[name], extracted, sources[name].path / "tests")
        output.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive, output)


try:
    main()
except (ValidationError, ValueError, subprocess.CalledProcessError) as error:
    raise SystemExit(str(error)) from error
