"""Run optional Topologiq without changing Studio's pinned dependencies."""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .graph import corrected_cube_kinds, graph_from_data, validate_graph


def engine_python():
    value = os.environ.get("TQEC_STUDIO_TOPOLOGIQ_PYTHON", "")
    if value:
        return Path(value).expanduser()
    environment = Path(__file__).resolve().parents[1] / ".venv-topologiq"
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def bundled_engine():
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).parent / "TopologiqEngine" / "Topologiq.exe"
        if executable.is_file():
            return executable
    return None


def generate_blockgraph(data):
    engine = bundled_engine()
    python = engine or engine_python()
    if python is None or not python.is_file():
        raise ValueError("Topologiq is not configured. See the Topologiq setup in the user guide.")
    if not isinstance(data, dict):
        raise ValueError("Provide an OpenQASM circuit.")
    qasm = data.get("qasm")
    if not isinstance(qasm, str) or not 1 <= len(qasm) <= 20000:
        raise ValueError("Provide an OpenQASM circuit of up to 20,000 characters.")
    for include in re.findall(r'\binclude\s+"([^"]+)"', qasm):
        if include != "qelib1.inc":
            raise ValueError("Only the standard qelib1.inc include is supported.")
    name = data.get("name", "Topologiq circuit")
    if not isinstance(name, str) or not 1 <= len(name) <= 120:
        raise ValueError("Use a circuit name of 1–120 characters.")
    strategy = data.get("strategy", "bfs-cross")
    if strategy not in ("bfs", "bfs-cross", "bfs-layers", "bfs-cycles"):
        raise ValueError("Choose a supported traversal strategy.")
    gravity = data.get("gravity", 7)
    if type(gravity) is not int or not 0 <= gravity <= 100:
        raise ValueError("Use an integer gravity weight from 0 to 100.")
    twins = data.get("twins", False)
    if type(twins) is not bool:
        raise ValueError("Choose whether to enable twins.")
    reduce = data.get("reduce", False)
    if type(reduce) is not bool:
        raise ValueError("Choose whether to apply reduction.")
    reduction_mode = data.get("reduction_mode", "topologiq")
    if reduction_mode not in ("topologiq", "pyzx"):
        raise ValueError("Choose a supported reduction method.")
    env = dict(os.environ, MPLBACKEND="Agg", PYINSTALLER_RESET_ENVIRONMENT="1")
    with tempfile.TemporaryDirectory() as folder:
        env["MPLCONFIGDIR"] = folder
        with tempfile.TemporaryFile() as log:
            result = subprocess.run(
                [str(python.absolute())]
                if engine
                else [str(python.absolute()), str(Path(__file__).with_name("topologiq_worker.py"))],
                input=json.dumps(
                    dict(
                        qasm=qasm,
                        name=name,
                        strategy=strategy,
                        gravity=gravity,
                        twins=twins,
                        reduce=reduce,
                        reduction_mode=reduction_mode,
                    )
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=log,
                cwd=folder,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
    try:
        output = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "Topologiq could not start. Check its separate Python environment."
        ) from exc
    if result.returncode or "error" in output:
        raise ValueError("Topologiq: " + output.get("error", "Generation failed."))
    graph = graph_from_data(output["graph"])
    graph, _ = corrected_cube_kinds(graph)
    validate_graph(graph)
    return graph
