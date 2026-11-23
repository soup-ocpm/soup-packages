# SOUP community packages

This repository hosts package source for the plugin-based SOUP installer.
Browse [catalog.json](catalog.json) for published versions, compatibility,
dependencies, download URLs, and SHA-256 checksums. Download a package's ZIP
from its [GitHub Release](https://github.com/soup-ocpm/soup-packages/releases)
and upload it through the SOUP package manager. Required SOUP packages must be
active before installation. SOUP applies its normal version and override rules
when the package is already bundled or installed.

Each package lives in `packages/<package_id>/`. Submit source through a pull
request. GitHub Actions validates it using SOUP's own tooling and runs any
tests included with the package. Builds on `main` provide individual ZIPs
under **Artifacts** on the Actions run.

After a successful build on `main`, the workflow publishes each previously
unreleased package version approved in the release list and updates the
catalog. [Release approvals](.github/release-approvals.json)

[CONTRIBUTING.md](CONTRIBUTING.md) covers local builds, pull requests, and releases.
