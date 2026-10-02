# User guide

## Design a computation

Choose an example or start empty. Drag a pipe onto a highlighted lattice edge. Pipes join neighbouring logical positions; the drawing uses one square for each cube and two squares for each pipe. The extra visual length adds no circuit time. X faces are red, Z faces blue, and a yellow band marks a Hadamard transition.

Studio infers junction cubes from pipe walls and asks you to choose when several kinds are possible. In **Cubes · cap or replace**, the palette offers only valid choices for the selected endpoint. Drag a cube onto an open port, click a valid replacement for a selected cube, or choose the translucent open-port symbol to reopen a leaf. Y caps are offered only on compatible time-direction endpoints. The installed compiler cannot compile Y cubes yet.

Click a pipe to inspect it, toggle a compatible Hadamard, or delete it. Its entry scrolls into view without changing list order. Undo and redo restore graph edits. Rotate or drag empty canvas to orbit, scroll to move up/down through the workspace, hold Ctrl/Cmd while scrolling to zoom, and use Fit when needed. Label and origin checkboxes keep the drawing clean. Cube numbers follow coordinate ordering and can change when the graph changes; they are not permanent identifiers.

On desktop, the palette and inspector scroll independently so the graph stays visible while browsing their controls. Use the **Drawing area** arrows to make the canvas wider/narrower or taller/shorter. Wider has two steps: compact side panels, then the full workspace width. Narrower brings the panels back. Height changes in 100-pixel steps. **Reset size** restores the default layout. Studio remembers this preference in the current browser; it does not change your graph or camera zoom.

Use **Measurement caps → Cap all ports · X / Z** in Design to fill every open endpoint with one cube, at the port's existing position. Studio copies the pipe walls at that endpoint (including Hadamard swaps) and assigns the chosen basis to the remaining pipe-axis boundary, following TQEC's minimal port-filling convention. Inputs become preparations and outputs become measurements. No new pipes or positions are added. Existing concrete cubes remain unchanged. Undo restores the whole operation in one step. This uniform basis choice does not guarantee a particular logical observable; find correlation surfaces afterward to check the supported computation.

## Keyboard editing

Select an existing pipe, then press **X**, **Y** or **Z** to add a pipe in the positive graph-axis direction. Hold **Shift** for the negative direction. Studio checks both endpoints and the compatible wall colours with the same validation used for dragging. If several placements are valid, choose the kind and starting coordinates in the dialog; junction ambiguities still require a cube choice. The **H** checkbox controls whether the new pipe has a Hadamard transition. The new pipe becomes selected, ready for the next extension.

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

Save project creates a portable JSON file. The browser draft is convenient but is not a backup. Open project accepts Studio JSON, TQEC graph JSON, and self-contained DAE. DAE images, external references, entities, DTDs and compressed archives are rejected. Maximum request size is 4 MiB.

Source-checkout runs are in `instance/studio/`; installed-app runs use the platform application-data directory unless `--data-dir` is supplied. Each job has its own directory. Do not share an entire data directory unintentionally: run records contain your graph.

If the server restarts, reload the app to obtain its new write token. Save your project before reloading. If a port is already in use, stop the other Studio instance or choose `--port`. A fresh browser port has separate local-storage drafts.
