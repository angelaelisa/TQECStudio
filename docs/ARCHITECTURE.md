# Architecture

Studio is a single-user application bound to the loopback interface. Flask serves static browser code and a token-protected JSON API; TQEC supplies graph semantics, correlation discovery and compilation. Stim/Sinter and PyMatching perform circuit validation, sampling and decoding.

- `studio/cli.py`: launcher, data location and loopback server. No debug server or reloader.
- `studio/app.py`: HTTP routes, compilation jobs and artifact allowlists.
- `studio/graph.py`: graph parsing, validation, pipe inference and port replacement, independent of HTTP.
- `studio/compilation.py`: validated adapters for the installed compiler and noise model.
- `studio/simulation.py`: task generation, statistics and plotting.
- `studio/security.py`: request boundaries, response headers and safe DAE preflight.
- `studio/static/`: plain JavaScript, SVG rendering and styles. No production Node dependency.
- `tests/`: real engine regression tests and security boundary tests.

The browser owns the editable graph. Server operations receive explicit snapshots rather than reading a shared working file. Revisions are hashes of normalized graphs and guard against stale surface selections. Generated artifacts have per-job UUID directories. One background executor serializes compilation and simulation; edits remain available while jobs run. Job state is currently in memory, while artifact files are persistent.

The dependency snapshot targets Python 3.13 and TQEC 0.1.0. The adapter accounts for two installed-engine limitations: positioned-ZX conversion detects three-axis corners that basic graph validation can miss, and database-only mode must reject an empty database before the engine's parallel detector path. Both are regression tested.

The legacy app and its generated files are excluded from the candidate. The existing Git history is not rewritten. The source exporter uses an explicit allowlist, so the review archive has no legacy Git history, private data, caches or local environments.

Future work includes cancellable process-isolated jobs with resource budgets, persistent job browsing, signed/notarized macOS packaging, and an explicit extension system for custom Python builders. These are not claimed as implemented security boundaries.
