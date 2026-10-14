# User guide

## Design a computation

Choose an example or start empty. Drag a pipe onto a highlighted lattice edge. Pipes join neighbouring logical positions; the drawing uses one square for each cube and two squares for each pipe. The extra visual length adds no circuit time. X faces are red, Z faces blue, and a yellow band marks a Hadamard transition.

Studio infers junction cubes from pipe walls. When several kinds fit, it uses the first compatible kind in the cube palette automatically; further pipes can update that kind as needed. In **Cubes · cap or replace**, the palette offers only valid choices for the selected endpoint. Drag a cube onto an open port, click a valid replacement for a selected cube, or choose the translucent open-port symbol to reopen a leaf. Y caps are offered only on compatible time-direction endpoints. The installed compiler cannot compile Y cubes yet.

Click a pipe to inspect it, toggle a compatible Hadamard, or delete it. Its entry scrolls into view without changing list order. Undo and redo restore graph edits. Rotate or drag empty canvas to orbit, scroll to move up/down through the workspace, hold Ctrl/Cmd while scrolling to zoom, and use Fit when needed. Label and origin checkboxes keep the drawing clean. Cube numbers follow coordinate ordering and can change when the graph changes; they are not permanent identifiers.

On desktop, the palette and inspector scroll independently so the graph stays visible while browsing their controls. Use the **Drawing area** arrows to make the canvas wider/narrower or taller/shorter. Wider has two steps: compact side panels, then the full workspace width. Narrower brings the panels back. Height changes in 100-pixel steps. **Reset size** restores the default layout. Studio remembers this preference in the current browser; it does not change your graph or camera zoom.

Use **Measurement caps → Cap all ports · X / Z** in Design to fill every open endpoint with one cube, at the port's existing position. Studio copies the pipe walls at that endpoint (including Hadamard swaps) and assigns the chosen basis to the remaining pipe-axis boundary, following TQEC's minimal port-filling convention. Inputs become preparations and outputs become measurements. No new pipes or positions are added. Existing concrete cubes remain unchanged. Undo restores the whole operation in one step. This uniform basis choice does not guarantee a particular logical observable; find correlation surfaces afterward to check the supported computation.

## Keyboard editing

Select a cube or open port, then press **X**, **Y** or **Z** to add a pipe from that position in the positive graph-axis direction. Hold **Shift** for the negative direction, or use the six **Extend from this cube** buttons in the inspector. Studio validates that specific edge and automatically uses a compatible pipe colour, preferring the palette's colour when it fits. Junction cubes are inferred automatically. The **H** checkbox controls whether the new pipe has a Hadamard transition. Selection moves to the destination cube or port, ready for the next extension; no endpoint-choice dialog is needed. Select a different cube to branch from it. If a pipe is selected instead, Studio extends from its endpoint farthest from the origin along the chosen axis. When both endpoints are equally far along that axis (for example when turning), it uses the endpoint farther from the origin overall; a remaining tie uses the requested direction, then coordinate order. The new pipe stays selected for continued building. Studio does not switch to the nearer endpoint if the chosen edge is blocked. Pipes can also be selected for Hadamard edits and deletion.

Use **Ctrl/Cmd + Z** to undo and **Ctrl/Cmd + Y** or **Ctrl/Cmd + Shift + Z** to redo. In Design, **Delete/Backspace** deletes the selected pipe, or the selected cube together with its connected pipes, **Escape** clears selection, and **F** fits the view. Typing fields, open dialogs and active edits suspend these shortcuts. Direction keys follow graph axes regardless of camera rotation. Use the palette to create the first pipe in an empty graph.

## Validate and inspect surfaces

Run **Validate and find surfaces** after graph edits. Select the observables to compile; View highlights a surface's Pauli support on the canvas. This overlay is not a filled geometric surface. The three HTML export buttons provide TQEC's geometric correlation-surface viewer with only +X, +Y or +Z opened. The downloaded HTML embeds the model but loads Three.js from a CDN when opened.

All ports must be filled before compilation or simulation. The app checks TQEC's graph and positioned-ZX constraints, including invalid three-axis junctions and Hadamard endpoint walls.

## Compile

| Control | Meaning |
| --- | --- |
| Scale k | Positive integer. Nominal distance is 2k+1, not a measured circuit distance. |
| Convention | Fixed bulk or fixed boundary. Support depends on the installed TQEC builders and graph. |
| Observables | Checked correlation surfaces, automatic discovery, or none. |
| Temporal height | Stabilizer rounds per block, a×k+b, excluding initialization and final measurement. Default 2k−1. Must be a positive integer at the selected k. |
| Noise | No added noise, uniform depolarizing, SI1000, or custom rules. SI1000 requires Z measurements/resets and p≤0.2; incompatible circuits fail explicitly. |
| Custom rules | Idle noise, extra waiting noise, one-/two-qubit Clifford defaults, named gate rules and measurement-basis rules. Each rule has after-operation channels and an optional result flip. Gate rules take precedence. Missing operation coverage is an error; an empty rule is explicitly noiseless. |
| Detector radius | Manhattan radius; values ≤0 disable detector computation. |
| Database | Disabled, reuse/update, or database-only. Names refer to JSON files in the local data directory. Import/export TQEC JSON databases; pickle uploads are not supported. |

The custom noise editor supports scalar DEPOLARIZE1/2 and X/Y/Z_ERROR channels. The installed NoiseRule implementation does not accept vector-valued Pauli channels. Arbitrary Python subclasses and convention builders are outside the visual interface.

A completed run offers the Stim circuit, a record of the source graph/settings/engine versions, and local Crumble. Crumble edits do not change the saved graph or circuit. The detector error model check is useful validation but does not certify fault tolerance or code distance.

After compilation, **Physical qubit layers** opens the compiled circuit's 2D physical layout. Use Previous/Next, the slider or a slice number to inspect the operations at each Stim TICK boundary. These are circuit operation steps, not blockgraph z coordinates or entire stabilizer rounds. The layout depends on k, compilation convention and temporal height. The diagram covers the complete computation and does not yet isolate individual cubes. The viewer starts with **Fit** so the entire slice is visible without enlarging small diagrams. Use +/−, the Zoom slider or Ctrl/Cmd + scroll to zoom; scroll inside the diagram to explore larger layouts. **100%** restores the SVG’s natural size. Zoom carries over between slices, and SVG downloads keep their original resolution. Download a slice as SVG when needed.

## Simulate and plot

The fourth tab uses the current Compile settings and generates circuits for each combination of scale k and physical noise p. You do not need to run Compile separately first. Choose a positive detector radius and at least one observable. Enter comma-separated values, workers, maximum shots and maximum errors per sampling point. The installed decoder is PyMatching.

Sampling stops at either budget; batched errors may exceed the error limit. Errors are failures of any selected observable, not separate error budgets for each observable. Custom noise sweeps scale every probability by sweep p / reference p. Resulting probabilities must remain at most one.

Plots show per-shot logical error probabilities, optionally with correlation-surface and zoom insets. The zoom reuses existing samples; it is not a threshold search. Shading represents binomial likelihood-ratio bounds with factor 1000, not a labelled confidence interval. Gray triangles show upper bounds when no errors were observed. Zero observed errors is not proof of zero failure probability, and crossings alone do not establish a threshold.

Download PNG/SVG figures, raw Sinter CSV statistics and the simulation record. The CSV retains joint observable-error masks; tables split the counts per observable. Keep Studio and the page open while running. Job cancellation and reopening prior jobs in the UI remain future work; saved artifacts persist on disk.

## Save, import and recover

Choose **JSON (.tqec.json)** or **COLLADA (.dae)** next to **Save project**. JSON creates a portable Studio project. COLLADA exports the blockgraph through TQEC, with the two-unit pipe drawing length and all faces intact, for use in Python:

```python
from tqec import BlockGraph

graph = BlockGraph.from_dae_file("my-project.dae")
```

The browser draft is convenient but is not a backup. Open project accepts Studio JSON, TQEC graph JSON, and self-contained DAE. DAE images, external references, entities, DTDs and compressed archives are rejected. Maximum request size is 4 MiB.

Source-checkout runs are in `instance/studio/`; installed-app runs use the platform application-data directory unless `--data-dir` is supplied. Each job has its own directory. Do not share an entire data directory unintentionally: run records contain your graph.

If the server restarts, reload the app to obtain its new write token. Save your project before reloading. If a port is already in use, stop the other Studio instance or choose `--port`. A fresh browser port has separate local-storage drafts.

## Keeping junction cubes consistent

Whenever a second or later pipe joins a cube, Studio checks the junction against all its connected pipes, including the swapped walls at Hadamard endpoints. It keeps the current cube if it remains valid, otherwise replaces it with the first compatible kind in the cube palette, without interrupting pipe placement. Pipe placement and cube replacements form one Undo step.

Deleting a pipe also rechecks both surviving endpoints. Any necessary cube replacements are included in the same Undo step. Empty open ports are removed; ordinary cubes remain in place. If the remaining walls admit no compatible cube, the edit is rejected without changing the graph.

For an older graph, use **Correlation surfaces → Check cube kinds**, or **Review cube replacements** when validation offers it. Review the coordinates and old/new kinds, then choose **Apply cube replacements**. This uses TQEC’s hidden-face correction and validates the result without changing the pipes or positions. Find correlation surfaces again afterward: a changed cube kind can change the ZX vertex type and invalidate earlier surfaces. This correction addresses junction cube kinds; other geometry or compiler errors may still need a separate edit.

## Generate a blockgraph with Topologiq (experimental)

In **Design → Generate with Topologiq**, paste an OpenQASM 2 circuit, choose a traversal strategy and click **Generate blockgraph**. The provided example is a two-qubit CNOT. Successful generation replaces the current graph; Undo restores it. TQEC validates the result before Studio loads it. Generated inputs and outputs are open ports: choose compatible caps before compiling a closed computation.

**Apply reduction before generation** is enabled by default in the interface. Choose **Topologiq · enhanced bialgebra** (the default) to run `full_reduce`, `to_rg`, `phase_free_simp`, Topologiq's `apply_bialgebra`, and identity simplification before creating the blockgraph. **PyZX · full reduction** keeps the original `full_reduce` method for comparison. Studio recalculates Pauli webs on the result. Uncheck reduction to generate from the original graph.

The enhanced sequence comes from the pinned upstream Steane example. Studio does not copy its hard-coded vertex layout or silently apply its all-zero input preparations and selected-zero ancilla effects: those specify a particular computation rather than a generic simplification. Reduction does not guarantee fewer cubes and does not yet add support for measurement circuits. Source: https://github.com/tqec/topologiq/blob/d010bd3e63686c93c12c922a84a944a3386ac785/src/topologiq/assets/pyzx_graphs.py#L357

The first integration supports H, X, Z, CNOT and CZ, without a fixed qubit-count limit. There is no generation time limit. Preview limits remain at 60 operations, 150 generated cubes and 200 ZX vertices. S, T, arbitrary rotations, measurements and custom QASM includes are rejected rather than approximated. Topologiq can support more patterns upstream, but these are not yet mapped into Studio's current TQEC engine. Generation runs in a separate process; concurrent local edits are not overwritten by a late result.

For a source installation, run this once using Python 3.13 and with Git available:

```bash
python scripts/setup_topologiq.py
```

The setup installs the upstream package at commit `d010bd3e63686c93c12c922a84a944a3386ac785` in `.venv-topologiq`, without changing Studio's pinned dependencies. It downloads Topologiq's complete dependency environment, which is considerably larger than Studio's. Restart Studio afterwards. To use a different existing environment, set `TQEC_STUDIO_TOPOLOGIQ_PYTHON` to its Python executable before starting Studio. Desktop release v0.1.0rc2 does not include this new integration or its optional engine.

Upstream project and examples: https://github.com/tqec/topologiq

### Topologiq build settings

The **compact preset** uses `debug=0`, `gravity=7`, `graph_traverse_mode="bfs-cycles"`, and `twins=False`, following the upstream recommendation for compact Steane-like layouts. Cross-edge traversal remains the initial selection because cycle traversal took substantially longer on the measurement-free, open-boundary Steane variant during testing. **Use compact preset** restores gravity, traversal and twins to those values. You can also choose standard BFS, cross-edge BFS or layer BFS, adjust gravity from 0 to 100, and enable twins to try improving completion of larger graphs. These are layout heuristics; they do not guarantee globally minimal volume. Debug stays at zero because step-by-step upstream visualizations require its separate desktop interface.

Usage example: https://github.com/tqec/topologiq/blob/main/docs/examples/pyzx_panel.py

New Windows tester packages bundle `TopologiqEngine/` beside `TQEC Studio.exe`. Keep this folder with the rest of the extracted package. Studio starts its isolated executable automatically; no Python installation or environment setup is required. The current preview's circuit-format and measurement limitations still apply.
