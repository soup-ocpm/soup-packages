# Submitting a SOUP package

1. Include one UTF-8 `soup-package.json` at the ZIP root or inside a single
   top-level package directory. Keep the package files under the same root
   as the manifest. Use relative paths with forward slashes and include
   regular files and directories only.
2. Put the archive under `packages/<name>/`. For a new release, give the
   manifest a new version and add a separate ZIP. The generator reads package
   identity and version from the manifest.
3. Run `python3 scripts/generate_catalog.py --validate` with Python 3.11 or
   newer. Fix any reported errors and rerun validation.
4. Open a pull request against `main` with the ZIP. Leave catalog generation to
   GitHub Actions after the merge.

## Manifest fields

- `name` is the package ID. Start with an ASCII letter or digit and use only
  letters, digits, dots, underscores, and hyphens. If present, `id` must
  match `name`. Each name and version pair must be unique across the catalog.
- `version` identifies the package release, such as `1.0.0`. `api_version`
  identifies the compatible SOUP API version, such as `4.0`. Both are strings.
- `description` is a non-empty string describing the package.
- `databases`, `requires`, `requires_tools`, `provides_tools`, and
  `python_dependencies`, when present, are arrays of non-empty strings
  without repeated entries. List package dependencies in `requires`, including
  dependencies supplied by the SOUP installation.
- If `app` is present, its `entry` must point to an archived file relative to
  the package's `app/` directory. If `server` is present, supply non-empty
  `module` and `plugin` strings.
- `download_url` and `sha256` are generated from the ZIP path and bytes.

Validation reads the ZIP and checks its members and manifest without extracting
the archive or loading package code. The existing Graph Explorer archive is
available under [packages/graph_explorer/](packages/graph_explorer/).
