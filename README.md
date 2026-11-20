# SOUP packages

[catalog.json](catalog.json) lists the available SOUP package versions. Each entry
contains the package manifest's metadata, a download URL, and the SHA-256
checksum of the ZIP. The manifest's `name` is the package ID.

To submit a package, add its ZIP under `packages/<name>/`, validate it locally,
and open a pull request against `main`. See [CONTRIBUTING.md](CONTRIBUTING.md)
for the ZIP layout and manifest fields.

```sh
python3 scripts/generate_catalog.py --validate
```

The generator uses Python 3.11 or newer and the standard library. Omit
`--validate` to regenerate `catalog.json` locally. For a mirror, use
`--base-url` with the URL prefix for the repository root. The default download
URLs point to this repository's `main` branch.

GitHub Actions validates packages on pull requests and commits the regenerated
catalog after changes land on `main`. The publish job uses the repository's
`GITHUB_TOKEN` with `contents: write`. Repository rules for `main` must allow
that bot push for automatic publication to succeed.
