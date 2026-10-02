# TQEC Studio

A local visual workspace for building TQEC block graphs, inspecting correlation surfaces, compiling Stim circuits, and plotting sampled logical error rates.

**Review candidate — not an official TQEC release or a signed macOS application.** Licensed under Apache-2.0. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md).

## Install and run

Python 3.13 is required for this pinned release candidate; it is locally tested on macOS. CI defines Linux and macOS checks. Use the pinned dependencies for reproducibility:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python run_studio.py
```

On macOS, after installation, double-click **Launch Studio.command**. The source launcher keeps existing data in `instance/studio/`. The installed `tqec-studio` command uses the platform's application-data directory and accepts `--data-dir`, `--port`, and `--no-browser`.

Studio listens only on `127.0.0.1:5187`. Keep its terminal running while compiling or sampling. Do not expose this single-user application through a public server, reverse proxy or tunnel.

## Windows tester download

A no-console portable Windows application and a manual Windows build workflow are prepared. The tester downloads a ZIP, extracts it, then double-clicks **TQEC Studio.exe**. No Python installation is needed for the bundled application. The executable must first pass the Windows build and frozen checks; it has not yet been verified on Windows. See [Windows tester instructions](docs/WINDOWS_TESTERS.md).

## Workflow

1. **Design:** drag pipes onto the lattice. Matching pipe walls determine junction cubes. Use the cube palette to cap, replace or reopen compatible endpoints. Hadamards swap X/Z walls. Rotate, zoom, and toggle labels or the origin independently.
2. **Correlation surfaces:** validate the graph, discover surfaces and select observables. Download the X, Y or Z inspection viewer; each opens only the positive face. These exported viewers load Three.js from an external CDN.
3. **Compile:** choose scale, convention, observables, temporal height, noise and detector settings. Download the Stim circuit and run record, or inspect the exact circuit in local Crumble.
4. **Simulate & plot:** sweep scales/noise strengths, set budgets and workers, then inspect each observable's error-rate plot and sampled counts. Download PNG, SVG, raw Sinter CSV and the simulation record.

See [the user guide](docs/USER_GUIDE.md), [architecture](docs/ARCHITECTURE.md), and [security policy](SECURITY.md).

## Data and privacy

The graph draft is stored in this browser's local storage. **Save project** creates a portable JSON copy. Compilation/simulation outputs remain in the local data directory. The app has no accounts, telemetry or cloud compilation. Dependency installation, documentation links and the optional exported 3D viewers can use the network.

Never commit graphs, simulation results, virtual environments, credentials or detector databases. The release exporter includes only approved source paths, without `.git` history or personal files.

## Development

```sh
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m unittest discover -s tests -v
ruff check studio tests scripts run_studio.py
ruff format --check studio tests scripts run_studio.py
python -m build
```

JavaScript is plain browser code; no runtime Node dependency or frontend build is required. Maintainers can run `node --check` on each file under `studio/static/`.

## Current limits

TQEC 0.1.0 and the scientific stack are pinned intentionally. Do not upgrade the compiler without regression tests. Y caps can be edited and inspected, but the installed compiler cannot compile them. Graphs are limited to 150 cubes, 450 pipes and integer coordinates within ±100. Requests are limited to 4 MiB. DAE imports must be self-contained plain XML without images, external references, DTDs or entities.

Long-running compilation/sampling is not yet cancellable in the interface. Keep the page open to retain its job status; exported results remain on disk. Custom Python convention builders/decoders are not loaded from uploads. Curves and nominal distance labels do not certify a threshold, fault tolerance or actual circuit distance.

## AI-assisted development

TQEC Studio was created by Ángela Elisa Álvarez with substantial assistance from OpenAI's Codex. AI assisted with interface design, implementation, debugging, tests, and documentation, guided by the author's requirements and iterative feedback. Project direction, decisions, and responsibility for reviewing and validating releases remain with the human maintainer.

## Upstream and licensing

Studio uses [TQEC](https://github.com/tqec/tqec), [Stim/Sinter](https://github.com/quantumlib/Stim), PyMatching, Flask and Matplotlib; those projects retain their own licences. Copyright 2026 Ángela Elisa Álvarez. Original Studio code and documentation are licensed under [Apache-2.0](LICENSE). Dependencies retain their own licences and attributions; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
