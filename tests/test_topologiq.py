import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from tqec import Basis
from tqec.gallery import cnot

from studio.topologiq_integration import generate_blockgraph
from studio.topologiq_worker import validate_qasm_statements

QASM = 'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[2];\ncx q[0],q[1];'


class TopologiqTests(unittest.TestCase):
    def test_dangling_measurement_target_has_line_number(self):
        with self.assertRaisesRegex(ValueError, r"Line 5: 'm_x1\[0\];'.*register reference"):
            validate_qasm_statements(QASM + "\nm_x1[0];")
        # Register declarations, comments and complete measurement statements
        # must not be mistaken for dangling references.
        validate_qasm_statements(QASM + "\ncreg m_x1[1];\n// m_x1[0];\nmeasure q[0] -> m_x1[0];")

    def test_validates_generated_graph(self):
        graph = cnot(Basis.Z).to_dict()
        result = subprocess.CompletedProcess([], 0, json.dumps({"graph": graph}))
        with (
            patch("studio.topologiq_integration.engine_python", return_value=Path(__file__)),
            patch("studio.topologiq_integration.subprocess.run", return_value=result) as run,
        ):
            generated = generate_blockgraph({"qasm": QASM})
        self.assertEqual(generated.to_dict(), graph)
        self.assertIsNone(run.call_args.kwargs.get("timeout"))
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_rejects_external_includes_and_unexpected_strategy(self):
        with (
            patch("studio.topologiq_integration.engine_python", return_value=Path(__file__)),
            patch("studio.topologiq_integration.subprocess.run") as run,
        ):
            for data in (
                {"qasm": 'include "/etc/passwd";'},
                {"qasm": QASM, "strategy": "unexpected"},
                {"qasm": QASM, "reduce": "false"},
                {"qasm": QASM, "reduction_mode": "unexpected"},
                {"qasm": QASM, "gravity": 7.5},
                {"qasm": QASM, "gravity": True},
                {"qasm": QASM, "twins": "false"},
            ):
                with self.assertRaises(ValueError):
                    generate_blockgraph(data)
            run.assert_not_called()

    def test_engine_errors(self):
        with (
            patch("studio.topologiq_integration.engine_python", return_value=Path(__file__)),
            patch("studio.topologiq_integration.subprocess.run") as run,
        ):
            run.return_value = subprocess.CompletedProcess([], 1, '{"error":"Unsupported gate"}')
            with self.assertRaisesRegex(ValueError, "Unsupported gate"):
                generate_blockgraph({"qasm": QASM})

    def test_rejects_invalid_engine_output(self):
        graph = {"name": "Bad", "cubes": [{"position": [0, 0, 0], "kind": "T"}], "pipes": []}
        result = subprocess.CompletedProcess([], 0, json.dumps({"graph": graph}))
        with (
            patch("studio.topologiq_integration.engine_python", return_value=Path(__file__)),
            patch("studio.topologiq_integration.subprocess.run", return_value=result),
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported cube"):
                generate_blockgraph({"qasm": QASM})
