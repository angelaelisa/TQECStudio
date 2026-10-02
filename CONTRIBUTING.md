# Contributing

Use Python 3.13 and a virtual environment. Install the hashed runtime lock, then install this package editable without resolving dependencies again. The optional `dev` extra supplies Ruff, build and pip-audit. JavaScript runs directly in the browser.

Before proposing changes, run the unit tests, Ruff lint/format checks, JavaScript syntax checks, dependency audit and package build as shown in the CI workflow. Test editor interactions and Crumble in a browser when changing UI or security policy. Tests run real small TQEC compilation and Sinter sampling jobs; do not substitute fabricated plots for numerical validation.

Keep graph validation in `studio/graph.py`, parameter adaptation in the compilation/simulation modules, and HTTP protection in `studio/security.py`. Preserve graph snapshots and accurately record every computation setting. Do not silently replace unsupported conventions, noise models or decoders.

Do not commit `.venv*`, `instance`, uploads, detector databases, private keys, generated plots or user graphs. Use `scripts/export_review.py` to generate the review source archive. Never copy the development `.git` directory into a new release repository: its history can retain removed legacy artifacts.

Dependency changes require a clean environment, regenerated `requirements.lock` hashes using `scripts/hash_lock.py`, `pip check`, a dependency audit and the real engine tests. CI uses read-only permissions and never publishes. Contributions are accepted under Apache-2.0 unless explicitly agreed otherwise. Preserve upstream copyright and attribution notices when adapting third-party code. Review the release checklist before distributing binaries.
