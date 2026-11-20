# SOUP community packages

This repository hosts package source for the plugin-based SOUP installer.
Browse [catalog.json](catalog.json) for published versions, compatibility,
dependencies, download URLs, and SHA-256 checksums. Download a package's ZIP
from its [GitHub Release](https://github.com/soup-ocpm/soup-packages/releases)
and upload it through the SOUP package manager. Required SOUP packages must be
active before installation. SOUP applies its normal version and override rules
when the package is already bundled or installed.

Each package lives in `packages/<package_id>/`. See [Graph Explorer](packages/graph_explorer/)
for the manifest, Python backend, TypeScript frontend, tests, and package docs.
Submit source through a pull request. GitHub Actions validates it using SOUP's
own tooling. Package ZIPs are built on demand from maintainer-selected tags
such as `graph_explorer/v1.0.0` and published as GitHub Release assets.

[CONTRIBUTING.md](CONTRIBUTING.md) covers local builds, pull requests, and releases.
