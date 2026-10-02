# Release review

This review candidate is licensed under Apache-2.0. The checks below describe the initial local preparation; platform release checks remain necessary. Use the source archive when sharing code without local user data.

## Completed preparation

- Legacy application, generated legacy outputs and the previous guide were preserved in a separately verified local backup and removed from the candidate source tree.
- Active graph logic is separated from HTTP setup; Python, JavaScript, CSS and templates are formatted for review. Obsolete hidden cube-building controls/routes are removed.
- Loopback request protection, browser security headers, safe XML preflight, generic internal errors and import/artifact checks have regression tests.
- Runtime dependencies are pinned for Python 3.13 with PyPI SHA-256 distribution hashes. The old environment audit reported 59 advisories across eight packages; the newly resolved candidate audit reported no known vulnerabilities and no skipped packages. This describes the audit result at preparation time, not a permanent security guarantee.
- Tests exercise real memory/CNOT/Hadamard compilation, custom noise, detector databases, real sampling, multi-observable statistics, figure exports and security boundaries.
- The source exporter uses an allowlist and scans common credential formats and personal absolute paths. It includes a per-file checksum manifest and excludes user data and Git history.
- CI is configured for Python 3.13 on macOS/Linux with read-only repository permissions and pinned action commits. It does not publish. Local checks are not evidence of a GitHub CI run.

## Local validation results

- 23 tests passed on macOS/Python 3.13, including real engine compilation and sampling.
- Ruff lint and formatting checks, JavaScript syntax checks and `pip check` passed.
- All 76 pinned runtime distributions were audited: zero known vulnerabilities, zero skipped packages.
- The source distribution and wheel built successfully. Package contents were checked for required assets and exclusion of legacy/user files.
- The wheel was installed in a separate virtual environment and launched from outside the source checkout on a separate loopback port. Browser checks covered editor selection, layer view, compilation and interactive Crumble under its script-hash policy, with no browser errors reported.
- Local data and the prior graph draft were preserved; the review export excludes them.

## Required before publication

1. Obtain project-owner and TQEC-maintainer approval of destination, name and scope.
2. Include LICENSE, NOTICE and THIRD_PARTY_NOTICES.md in every distribution. Collect the original dependency and runtime licence texts for bundled binaries.
3. Configure a verified private security-reporting contact in the receiving repository.
4. Run the receiving repository's CI and clean-machine installation tests on every claimed platform. Local validation uses macOS/Python 3.13; Linux is not claimed as manually verified.
5. Review the source archive and scan the receiving repository history for secrets before publishing. Never upload the local backup, `.git`, environments or data directories.
6. For an end-user macOS release, add an installer and complete clean-machine, signing and notarization checks. A source archive and wheel are not a signed desktop application.

## Known gaps

Long-running work is not yet isolated in cancellable/resource-limited processes. Job status is in memory and prior-run browsing is not implemented. Exported geometric viewers depend on a CDN. Upstream compiler limitations remain, including Y-cube compilation and convention-dependent geometry support. The current TQEC inset helper emits a Matplotlib deprecation warning; the scientific stack is pinned and tested.
