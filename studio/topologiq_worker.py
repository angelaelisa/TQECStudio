"""Headless Topologiq adapter, executed by its own Python environment."""

import contextlib
import json
import re
import sys


def validate_qasm_statements(qasm):
    """Explain dangling register references before the circuit parser runs."""
    # Preserve line offsets while removing comments; do not rewrite instructions.
    plain = re.sub(
        r"/\*.*?\*/|//[^\n]*",
        lambda m: "".join("\n" if char == "\n" else " " for char in m.group()),
        qasm,
        flags=re.S,
    )
    for match in re.finditer(r"[^;]+(?:;|$)", plain):
        statement = match.group().rstrip(";").strip()
        if re.fullmatch(r"[A-Za-z_]\w*\[\d+\]", statement):
            offset = match.start() + len(match.group()) - len(match.group().lstrip())
            line = plain.count("\n", 0, offset) + 1
            raise ValueError(
                f"Line {line}: '{statement};' is a register reference, not a QASM instruction. "
                "It may be a leftover measurement target. Remove the whole line only if you "
                "intend to omit that measurement."
            )


def generate(data):
    validate_qasm_statements(data["qasm"])
    import pyzx as zx
    from pyzx import Circuit
    from topologiq.core.graph_manager.graph_manager import BlockGraphManager
    from topologiq.input.zx_manager import AugmentedZXGraph
    from topologiq.utils.zx import apply_bialgebra

    circuit = Circuit.from_qasm(data["qasm"])
    if circuit.qubits < 1:
        raise ValueError("The circuit must contain at least one qubit.")
    if not 1 <= len(circuit.gates) <= 60:
        raise ValueError("Use 1–60 operations for this preview.")
    for gate in circuit.gates:
        if gate.name == "Measurement":
            raise ValueError(
                "Measurement circuits are not supported by this Studio integration yet."
            )
        if gate.name not in {"HAD", "NOT", "Z", "CNOT", "CZ", "ZPhase", "XPhase"}:
            raise ValueError("This integration supports H, X, Z, CNOT and CZ gates.")
        if getattr(gate, "phase", 0) not in (0, 1):
            raise ValueError("S, T and arbitrary rotations are not supported in this preview.")
    augmented = AugmentedZXGraph.from_qasm(qasm_str=data["qasm"], debug=0)
    if data.get("reduce", False):
        reduced = augmented.zx_graph_reduced.copy()
        if data.get("reduction_mode", "topologiq") == "topologiq":
            # Use the upstream sequence without its Steane-specific boundaries
            # or hard-coded vertex layout. Those are not generic rewrites.
            zx.to_rg(reduced)
            zx.phase_free_simp(reduced)
            apply_bialgebra(reduced)
            zx.simplify.id_simp(reduced)
        augmented = AugmentedZXGraph(zx_graph=reduced, debug=0)
        if all(augmented.zx_graph.type(v) == 0 for v in augmented.zx_graph.vertices()):
            raise ValueError(
                "Reduction leaves only identity wires, which this Topologiq adapter cannot place. "
                "Uncheck Apply reduction to generate from the original circuit."
            )
    if augmented.zx_graph.num_vertices() > 200:
        raise ValueError("The circuit exceeds this preview's ZX graph limit.")
    manager = BlockGraphManager(
        augmented,
        debug=0,
        animate=False,
        log_stats=False,
        graph_traverse_mode=data["strategy"],
        gravity=data.get("gravity", 7),
        twins=data.get("twins", False),
        seed=1,
    )
    manager.build()
    cubes, positions = [], {}
    for index, attrs in manager.bgraph.nodes(data=True):
        coords, block = attrs.get("coords"), attrs.get("zx_block")
        if coords is None or block is None or block.kind is None:
            raise ValueError("Topologiq could not complete this circuit's blockgraph.")
        kind = "P" if block.kind == "OOO" else block.kind
        if kind not in {"P", "ZXZ", "ZXX", "XZX", "XZZ", "XXZ", "ZZX"}:
            raise ValueError(f"The generated cube {block.kind} is not supported by Studio.")
        positions[index] = [int(value) for value in coords]
        if any(int(value) != value for value in coords):
            raise ValueError("Topologiq generated non-integral cube positions.")
        label = ""
        if index in manager.inputs:
            label = f"in_{manager.qubits[index]}"
        elif index in manager.outputs:
            label = f"out_{manager.qubits[index]}"
        cubes.append(dict(position=positions[index], kind=kind, label=label))
    pipes = [
        dict(u=positions[u], v=positions[v], kind=kind)
        for u, v, kind in manager.bgraph.edges(data="kind")
    ]
    return dict(name=data["name"], cubes=cubes, pipes=pipes)


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        # Topologiq prints progress; keep stdout exclusively for the JSON result.
        with contextlib.redirect_stdout(sys.stderr):
            graph = generate(data)
        print(json.dumps({"graph": graph}))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
