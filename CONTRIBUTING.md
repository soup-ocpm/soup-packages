# Contributing a SOUP package

## Package source

Create `packages/<package_id>/` and include the following files.

| Path | Purpose |
| --- | --- |
| `soup-package.json` | SOUP manifest. Set `name` to the directory name, include a description, and use a version such as `1.0.0` and the compatible `api_version`. |
| `server/` | Python backend. Declare its module and plugin entry in the manifest. |
| `requirements.txt` | Optional named PEP 508 Python dependencies. The manifest's `python_dependencies` field is also supported. Declare SOUP package and tool dependencies in `requires` and `requires_tools`. |
| `app/` | For packages with a frontend, include `package.json`, `tsconfig.json`, and `src/index.ts`. Declare frontend dependencies in `app/package.json` and set the manifest's `app.entry` to `dist/index.js`. |
| `tests/` and `app/test/` | Optional backend `unittest` files named `test_*.py` and frontend Vitest files named `*.test.ts`. |
| `README.md` | Explain the package, its dependencies, and how to use or test it. |

Package IDs start with a lowercase letter and use lowercase letters, digits,
and underscores. Use normalized release versions such as `1.0.0` or `1.1.0rc1`.
SOUP's [package development guide](https://github.com/soup-ocpm/soup/blob/694f2083c311a12c1e4a32a8ff1212b9f72e7b1a/soup-packages/docs/package-development.md)
describes the manifest and runtime contracts.

## Local development and pull requests

Use Python 3.12, Node.js 24.22.0, and npm 11. Run these commands from the
community repository with the SOUP checkout beside it.

```sh
git clone --branch plugin-based https://github.com/soup-ocpm/soup.git ../soup-plugin-based
python3.12 -m venv .venv
. .venv/bin/activate
git -C ../soup-plugin-based show "$(cat scripts/soup-ref.txt):soup-server/requirements.txt" > .venv/soup-requirements.txt
python -m pip install -r .venv/soup-requirements.txt
python scripts/build_packages.py --soup ../soup-plugin-based
```

The script stages community sources with the SOUP revision in
`scripts/soup-ref.txt`. It checks manifests and dependencies, runs SOUP's
`build:packages` and `pack` commands, and checks the result with SOUP's ZIP
extractor and backend plugin loader. Package tests are optional. CI runs backend
and frontend tests when present. Backend unit tests
can import the installed package as `soup_pkg_<package_id>`. Test ZIPs are
written to `dist/` for a local installer check.

Open a pull request against `main` with package source. Leave ZIPs, compiled
bundles, dependency directories, and catalog entries out of the submission.
The PR workflow has read-only repository permissions. A push to `main`
builds the packages and lists each installer ZIP separately under **Artifacts**
on the Actions run. Use `all-package-zips` to download the full set. Publishing a GitHub Release requires the maintainer
workflow below.

## Maintainer releases

To publish multiple packages automatically, add their IDs and exact manifest
versions to [`.github/release-approvals.json`](.github/release-approvals.json)
in a maintainer-reviewed PR. The following example approves two versions.

```json
{
  "graph_explorer": "1.0.0",
  "oced_importer": "1.2.0"
}
```

After the PR lands on `main` and the build passes, the publish job creates
any missing package tags, attaches each approved installer ZIP to its own
GitHub Release, and updates the catalog. A version bump requires a matching
approval. Already published versions are skipped. Configure repository rules
to allow the workflow to create package tags and push its catalog commit.
Restrict approval-list changes to maintainer review.

### Manual release

1. Update the package's manifest version in a PR and merge it. Packages have
   independent versions. When overriding a package bundled with SOUP, choose
   a version higher than the bundled one. Release any required community
   packages first.
2. Tag the reviewed commit and push the tag. The name and version must match
   the manifest at the tagged commit.

   ```sh
   git switch main
   git pull --ff-only
   git tag -a graph_explorer/v1.0.1 -m 'Graph Explorer 1.0.1'
   git push origin refs/tags/graph_explorer/v1.0.1
   ```

3. From `main`, run the **Community packages** workflow in GitHub Actions
   with that tag. The workflow checks that the tag points to a commit on
   `main`, builds and validates the package with read-only permissions, then
   publishes the ZIP in a separate job using the `package-release` environment.
4. The publishing job rebuilds `catalog.json` from the published Release ZIPs
   and commits it to `main`. The catalog includes only published versions.
   Rerun the workflow to retry a catalog update after publication.

Configure required reviewers on the `package-release` environment if a second
maintainer must approve publishing. Restrict creation and updates of release
tags to maintainers, and configure `main` so the workflow can push its catalog
commit. Keep published tags and assets fixed and use a new version for updates.
To preview the release catalog locally, authenticate GitHub CLI and run
`python scripts/generate_catalog.py`.
