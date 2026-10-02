import io
import json
import re
import tempfile
import time
import unittest
from pathlib import Path

from studio import create_studio_app


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_studio_app(self.temp.name)
        self.client = self.app.test_client()
        page = self.client.get("/").text
        self.headers = {
            "X-Studio-Token": re.search(r'name="studio-token" content="([^"]+)"', page)[1]
        }

    def test_minimal_caps_all_axes_and_hadamard_endpoints(self):
        from tqec import Basis, BlockGraph
        from tqec.utils.position import Direction3D, Position3D

        from studio.graph import PIPE_KINDS, cap_ports_minimally

        for base in PIPE_KINDS:
            axis = base.index("O")
            for suffix in ("", "H"):
                for basis in ("X", "Z"):
                    with self.subTest(pipe=base + suffix, basis=basis):
                        g = BlockGraph("Open pipe")
                        a = Position3D(0, 0, 0)
                        target = [0, 0, 0]
                        target[axis] = 1
                        b = Position3D(*target)
                        g.add_cube(a, "P", "Input")
                        g.add_cube(b, "P", "Output")
                        g.add_pipe(a, b, base + suffix)
                        original = g.to_dict()
                        result, caps = cap_ports_minimally(g, basis)
                        self.assertEqual(g.to_dict(), original)
                        self.assertEqual(result.num_ports, 0)
                        self.assertEqual(len(caps), 2)
                        self.assertEqual(len(result.pipes), 1)
                        for pos, at_head in ((a, True), (b, False)):
                            for direction in Direction3D.all_directions():
                                expected = g.pipes[0].kind.get_basis_along(
                                    direction, at_head
                                ) or Basis(basis)
                                self.assertEqual(
                                    result[pos].kind.get_basis_along(direction), expected
                                )
                        response = self.client.post(
                            "/api/cap-minimal",
                            json={"graph": original, "basis": basis},
                            headers=self.headers,
                        )
                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertEqual(
                            response.json["graph"], json.loads(json.dumps(result.to_dict()))
                        )

    def test_minimal_caps_reject_invalid_basis_and_no_ports(self):
        graph = self.client.get("/api/example/memory").json["graph"]
        for basis in ("X", "Z", "Y", None):
            response = self.client.post(
                "/api/cap-minimal", json={"graph": graph, "basis": basis}, headers=self.headers
            )
            self.assertEqual(response.status_code, 400)

    def tearDown(self):
        self.app.extensions["studio_executor"].shutdown(wait=True)
        self.temp.cleanup()

    def post(self, url, data):
        return self.client.post(url, json=data, headers=self.headers)

    def example(self, name="memory"):
        return self.client.get("/api/example/" + name).json["graph"]

    def test_graph_roundtrip_and_invalid_edges(self):
        graph = self.example("cnot")
        response = self.post("/api/graph", graph)
        self.assertEqual(response.status_code, 200)
        project = {"schema": "tqec-studio/1", "graph": response.json["graph"]}
        imported = self.client.post(
            "/api/import",
            data={"file": (io.BytesIO(json.dumps(project).encode()), "project.json")},
            headers=self.headers,
        )
        self.assertEqual(imported.json["graph"], response.json["graph"])
        graph["pipes"].append(graph["pipes"][0])
        self.assertEqual(self.post("/api/graph", graph).status_code, 400)
        graph = self.example()
        graph["cubes"][0]["position"][0] = 0.5
        self.assertEqual(self.post("/api/graph", graph).status_code, 400)

    def test_removed_legacy_cube_building_routes(self):
        self.assertEqual(self.post("/api/place", {}).status_code, 404)
        self.assertEqual(self.post("/api/placements", {}).status_code, 404)

    def test_pipe_first_inference_and_ambiguity(self):
        empty = self.example("empty")
        first = self.post(
            "/api/place-pipe", dict(graph=empty, u=[0, 0, 0], v=[0, 0, 1], kind="ZXO")
        )
        self.assertEqual(first.status_code, 200, first.json)
        graph = first.json["graph"]
        self.assertEqual(len(graph["ports"]), 2)
        turn = self.post("/api/place-pipe", dict(graph=graph, u=[0, 0, 1], v=[0, 1, 1], kind="ZOX"))
        self.assertEqual(turn.status_code, 200, turn.json)
        junction = next(c for c in turn.json["graph"]["cubes"] if c["position"] == [0, 0, 1])
        self.assertEqual(junction["kind"], "ZXX")
        self.assertEqual(len(turn.json["graph"]["ports"]), 2)
        straight = dict(graph=graph, u=[0, 0, 1], v=[0, 0, 2], kind="ZXO")
        ambiguous = self.post("/api/place-pipe", straight)
        self.assertEqual(set(ambiguous.json["ambiguities"][0]["kinds"]), {"ZXZ", "ZXX"})
        self.assertNotIn("graph", ambiguous.json)
        resolved = self.post("/api/place-pipe", {**straight, "choices": {"0,0,1": "ZXZ"}})
        self.assertEqual(resolved.status_code, 200, resolved.json)
        self.assertEqual(len(resolved.json["graph"]["pipes"]), 2)
        self.assertEqual(
            self.post("/api/place-pipe", {**straight, "choices": {"0,0,1": "XZZ"}}).status_code, 400
        )
        self.assertEqual(
            self.post(
                "/api/place-pipe", dict(graph=graph, u=[0, 0, 1], v=[0, 1, 1], kind="XOZ")
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                "/api/place-pipe", dict(graph=graph, u=[0, 0, 1], v=[0, 1, 1], kind="XOZH")
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                "/api/place-pipe", dict(graph=graph, u=[0, 0, 0], v=[0, 0, 1], kind="ZXO")
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                "/api/place-pipe", dict(graph=graph, u=[5, 0, 0], v=[5, 0, 1], kind="ZXO")
            ).status_code,
            400,
        )
        # At the tail of a Hadamard pipe the walls swap X/Z.
        hadamard = self.post(
            "/api/place-pipe", dict(graph=empty, u=[0, 0, 0], v=[0, 0, 1], kind="ZXOH")
        ).json["graph"]
        turn = self.post(
            "/api/place-pipe", dict(graph=hadamard, u=[0, 0, 1], v=[0, 1, 1], kind="XOZ")
        )
        self.assertEqual(turn.status_code, 200, turn.json)
        self.assertEqual(
            next(c["kind"] for c in turn.json["graph"]["cubes"] if c["position"] == [0, 0, 1]),
            "XZZ",
        )

    def test_hadamard_edit_and_conflict(self):
        graph = self.post(
            "/api/place-pipe",
            dict(graph=self.example("empty"), u=[0, 0, 0], v=[0, 0, 1], kind="ZXO"),
        ).json["graph"]
        payload = dict(graph=graph, u=[0, 0, 0], v=[0, 0, 1], enabled=True)
        changed = self.post("/api/pipe-hadamard", payload)
        self.assertEqual(changed.status_code, 200, changed.json)
        self.assertEqual(changed.json["graph"]["pipes"][0]["kind"], "ZXOH")
        restored = self.post(
            "/api/pipe-hadamard", {**payload, "graph": changed.json["graph"], "enabled": False}
        )
        self.assertEqual(restored.json["graph"], graph)
        fixed = self.example("hadamard")
        rejected = self.post("/api/pipe-hadamard", {**payload, "graph": fixed, "enabled": False})
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("conflicts", rejected.json["error"])
        self.assertEqual(fixed, self.example("hadamard"))
        self.assertEqual(
            self.post("/api/pipe-hadamard", {**payload, "enabled": "yes"}).status_code, 400
        )

    def test_three_axis_hadamard_junction_is_rejected(self):
        from tqec import BlockGraph
        from tqec.utils.position import Position3D as P

        from studio.graph import graph_from_data

        g = BlockGraph("Hadamard junction regression")
        g.add_cube(P(0, 0, 0), "ZXZ")
        g.add_cube(P(0, -1, 0), "XZZ")
        for i, p in enumerate([P(0, 0, -1), P(0, 0, 1)]):
            g.add_cube(p, "P", f"time{i}")
            g.add_pipe(P(0, 0, 0), p, "ZXO")
        g.add_pipe(P(0, -1, 0), P(0, 0, 0), "XOZH")
        g.validate()
        original = g.to_dict()
        # Reproduce the engine gap: its shadowed-face check accepts this 3D corner.
        bad = graph_from_data(original)
        bad.add_cube(P(1, 0, 0), "P", "third_axis")
        bad.add_pipe(P(0, 0, 0), P(1, 0, 0), "OXZ")
        bad.validate()
        with self.assertRaisesRegex(Exception, "3D corner"):
            bad.to_zx_graph()
        proposal = dict(graph=original, u=[0, 0, 0], v=[1, 0, 0], kind="OXZ")
        rejected = self.post("/api/place-pipe", proposal)
        self.assertEqual(rejected.status_code, 400, rejected.json)
        self.assertIn("at most two axes", rejected.json["error"])
        options = self.post("/api/pipe-placements", dict(graph=original, kind="OXZ")).json[
            "placements"
        ]
        self.assertFalse(any(p["u"] == [0, 0, 0] and p["v"] == [1, 0, 0] for p in options))
        self.assertEqual(g.to_dict(), original)
        self.assertEqual(self.post("/api/surfaces", bad.to_dict()).status_code, 400)
        restored = self.post("/api/graph", bad.to_dict())
        self.assertEqual(restored.status_code, 200)
        self.assertIn("at most two axes", restored.json["warning"])
        self.assertEqual(
            self.post("/api/graph", {**bad.to_dict(), "validate_edit": True}).status_code, 400
        )

    def test_hadamard_endpoint_basis_in_both_directions(self):
        from tqec import BlockGraph
        from tqec.utils.position import Position3D as P

        from studio.graph import pipe_proposal

        # These boundary cubes match the head and swapped tail of a temporal H pipe.
        for source, target, kind in [
            (P(0, 0, 0), P(0, 0, 1), "ZXZ"),
            (P(0, 0, 1), P(0, 0, 0), "XZX"),
        ]:
            g = BlockGraph("H endpoints")
            g.add_cube(source, kind)
            result, ambiguities, _ = pipe_proposal(g, source.as_tuple(), target.as_tuple(), "ZXOH")
            self.assertFalse(ambiguities)
            result.validate()
            with self.assertRaises(Exception):
                pipe_proposal(g, source.as_tuple(), target.as_tuple(), "XZOH")

    def test_cap_ports_respects_hadamard_walls(self):
        g = self.post(
            "/api/place-pipe",
            dict(graph=self.example("empty"), u=[0, 0, 0], v=[0, 0, 1], kind="ZXOH"),
        ).json["graph"]
        head = self.post("/api/cap-options", dict(graph=g, kind="ZXZ")).json["placements"]
        tail = self.post("/api/cap-options", dict(graph=g, kind="XZX")).json["placements"]
        self.assertEqual([p["position"] for p in head], [[0, 0, 0]])
        self.assertEqual([p["position"] for p in tail], [[0, 0, 1]])
        self.assertEqual(
            self.post("/api/fill", dict(graph=g, label=tail[0]["label"], kind="ZXZ")).status_code,
            400,
        )
        capped = self.post("/api/fill", dict(graph=g, label=head[0]["label"], kind="ZXZ"))
        self.assertEqual(capped.status_code, 200, capped.json)
        self.assertEqual(capped.json["graph"]["pipes"], g["pipes"])
        self.assertEqual(len(capped.json["graph"]["cubes"]), 2)
        self.assertEqual(len(capped.json["graph"]["ports"]), 1)
        self.assertEqual(
            self.post(
                "/api/fill", dict(graph=capped.json["graph"], label=head[0]["label"], kind="ZXZ")
            ).status_code,
            400,
        )

    def test_replace_cube_preserves_pipes_and_reopens_end(self):
        g = self.example("hadamard")
        payload = dict(graph=g, position=[0, 0, 1])
        options = self.post("/api/cube-options", payload)
        self.assertEqual(options.json["kinds"], ["XZZ", "Y"])
        self.assertTrue(options.json["can_reopen"])
        changed = self.post("/api/replace-cube", {**payload, "kind": "XZZ"})
        self.assertEqual(changed.status_code, 200, changed.json)
        self.assertEqual(changed.json["graph"]["pipes"], g["pipes"])
        self.assertEqual(
            self.post("/api/replace-cube", {**payload, "kind": "ZXZ"}).status_code, 400
        )
        reopened = self.post("/api/replace-cube", {**payload, "kind": "P"})
        self.assertEqual(reopened.status_code, 200, reopened.json)
        self.assertEqual(reopened.json["graph"]["pipes"], g["pipes"])
        self.assertEqual(len(reopened.json["graph"]["ports"]), 1)
        extended = self.post(
            "/api/place-pipe",
            dict(graph=reopened.json["graph"], u=[0, 0, 1], v=[0, 1, 1], kind="XOZ"),
        )
        self.assertEqual(extended.status_code, 200, extended.json)
        self.assertEqual(len(extended.json["graph"]["pipes"]), 2)
        junction = dict(graph=extended.json["graph"], position=[0, 0, 1])
        self.assertFalse(self.post("/api/cube-options", junction).json["can_reopen"])
        self.assertEqual(self.post("/api/replace-cube", {**junction, "kind": "P"}).status_code, 400)

    def test_surface_html_exports(self):
        import base64
        import xml.etree.ElementTree as ET

        graph = self.example("hadamard")
        found = self.post("/api/surfaces", graph).json
        payload = dict(graph=graph, revision=found["revision"], surface=0)
        for axis in "XYZ":
            result = self.post("/api/surface-viewer/" + axis, payload)
            self.assertEqual(result.status_code, 200, result.text[:200])
            self.assertIn("attachment;", result.headers["Content-Disposition"])
            self.assertIn("Observable 1", result.text)
            encoded = re.search(r'data:text/plain;base64,([^"\s]+)', result.text)[1]
            dae = base64.b64decode(encoded).decode()
            ET.fromstring(dae)
            self.assertIn("correlation_surface", dae)
            self.assertIn("+" + axis, dae)
            self.assertIn("Only the +" + axis + " face is removed.", result.text)
        self.assertEqual(
            self.post("/api/surface-viewer/X", {**payload, "revision": "old"}).status_code, 400
        )
        self.assertEqual(
            self.post("/api/surface-viewer/X", {**payload, "surface": -1}).status_code, 400
        )
        self.assertEqual(self.post("/api/surface-viewer/Q", payload).status_code, 400)

    def test_y_caps_only_on_temporal_ports(self):
        for kind in ["OXZ", "OZX", "XOZ", "ZOX", "XZO", "ZXO"]:
            for suffix in ["", "H"]:
                axis = kind.index("O")
                end = [0, 0, 0]
                end[axis] = 1
                g = self.post(
                    "/api/place-pipe",
                    dict(graph=self.example("empty"), u=[0, 0, 0], v=end, kind=kind + suffix),
                ).json["graph"]
                options = self.post("/api/cap-options", dict(graph=g, kind="Y")).json["placements"]
                self.assertEqual(len(options), 2 if axis == 2 else 0)
                for cube in g["cubes"]:
                    result = self.post("/api/fill", dict(graph=g, label=cube["label"], kind="Y"))
                    self.assertEqual(result.status_code, 200 if axis == 2 else 400, result.json)
                if axis == 2:
                    for option in options:
                        g = self.post(
                            "/api/fill", dict(graph=g, label=option["label"], kind="Y")
                        ).json["graph"]
                    found = self.post("/api/surfaces", g)
                    self.assertEqual(found.status_code, 200, found.json)
                    response = self.post(
                        "/api/compile",
                        dict(
                            graph=g, revision=found.json["revision"], surfaces=[0], k=1, noise_p=0
                        ),
                    )
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("does not implement Y", response.json["error"])

    def test_local_write_guard_and_invalid_import(self):
        self.assertEqual(self.client.post("/api/graph", json=self.example()).status_code, 403)
        response = self.client.post(
            "/api/import",
            data={"file": (io.BytesIO(b"{}"), "unknown.bgraph")},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_revision_and_parameter_validation(self):
        graph = self.example()
        found = self.post("/api/surfaces", graph).json
        payload = dict(graph=graph, revision=found["revision"], surfaces=[0], k=1, noise_p=0)
        for field, value in [
            ("k", 0),
            ("noise_p", -0.1),
            ("noise_p", float("nan")),
            ("surfaces", [-1]),
            ("revision", "old"),
            ("convention", "fixed_parity"),
        ]:
            with self.subTest(field=field, value=value):
                self.assertEqual(
                    self.post("/api/compile", {**payload, field: value}).status_code, 400
                )
        graph["name"] = "Changed"
        self.assertEqual(self.post("/api/compile", payload).status_code, 400)

    def test_real_memory_and_cnot_compile(self):
        import stim

        for name in ["memory", "cnot", "hadamard"]:
            with self.subTest(name=name):
                graph = self.example(name)
                found = self.post("/api/surfaces", graph)
                self.assertEqual(found.status_code, 200, found.json)
                self.assertGreater(len(found.json["surfaces"]), 0)
                payload = dict(
                    graph=graph,
                    revision=found.json["revision"],
                    surfaces=[s["index"] for s in found.json["surfaces"]],
                    k=1,
                    noise_p=0.001,
                )
                response = self.post("/api/compile", payload)
                self.assertEqual(response.status_code, 202, response.json)
                job_id = response.json["id"]
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    job = self.client.get("/api/jobs/" + job_id).json
                    if job["status"] in ["complete", "failed"]:
                        break
                    time.sleep(0.05)
                self.assertEqual(job["status"], "complete", job)
                with self.client.get(f"/api/jobs/{job_id}/circuit.stim") as result:
                    circuit = stim.Circuit(result.text)
                self.assertGreater(circuit.num_detectors, 0)
                self.assertEqual(circuit.num_observables, len(payload["surfaces"]))
                circuit.detector_error_model()
                viewer = self.client.get(f"/api/jobs/{job_id}/crumble")
                self.assertEqual(viewer.status_code, 200)
                self.assertEqual(viewer.mimetype, "text/html")
                self.assertIn("script-src 'sha256-", viewer.headers["Content-Security-Policy"])
                self.assertEqual(viewer.text, str(circuit.diagram("interactive")))
                self.assertEqual(
                    self.client.get("/api/jobs/" + "0" * 32 + "/crumble").status_code, 404
                )
                with self.client.get(f"/api/jobs/{job_id}/run.json") as result:
                    manifest = json.loads(result.text)
                self.assertEqual(manifest["revision"], payload["revision"])
                self.assertEqual(manifest["settings"]["noise_p"], 0.001)
                self.assertTrue((Path(self.temp.name) / job_id / "circuit.stim").exists())

    def test_extended_compilation_settings_validation(self):
        from studio.compilation import compilation_settings, noise_model

        self.assertEqual(compilation_settings({"k": 6})["k"], 6)
        bad = [
            {"k": True},
            {"manhattan_radius": 1.5},
            {"database_name": "../escape"},
            {"observable_mode": "invalid"},
            {"noise_model": "si1000", "noise_p": 0.3},
            {"block_temporal_height": {"slope": 0, "offset": 0.5}},
            {"noise_model": "custom", "custom_noise": {"idle_depolarization": -1}},
            {
                "noise_model": "custom",
                "custom_noise": {"any_clifford_1q_rule": {"flip_result": 0.1}},
            },
        ]
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                compilation_settings(payload)
        settings = compilation_settings(
            {
                "noise_model": "custom",
                "custom_noise": {
                    "idle_depolarization": 0.002,
                    "additional_depolarization_waiting_for_m_or_r": 0.003,
                    "any_clifford_1q_rule": {"after": {"DEPOLARIZE1": 0.004}},
                    "any_clifford_2q_rule": {"after": {"DEPOLARIZE2": 0.005}},
                    "gate_rules": {"RX": {"after": {"Z_ERROR": 0.006}}},
                    "measure_rules": {"X": {"after": {}, "flip_result": 0.007}},
                },
            }
        )
        model = noise_model(settings)
        self.assertEqual(model.idle_depolarization, 0.002)
        self.assertEqual(model.additional_depolarization_waiting_for_m_or_r, 0.003)
        self.assertEqual(model.any_clifford_1q_rule.after, {"DEPOLARIZE1": 0.004})
        self.assertEqual(model.any_clifford_2q_rule.after, {"DEPOLARIZE2": 0.005})
        self.assertEqual(model.gate_rules["RX"].after, {"Z_ERROR": 0.006})
        self.assertEqual(model.measure_rules["X"].flip_result, 0.007)

    def test_extended_real_compilation_and_database_roundtrip(self):
        import stim

        graph = self.example()
        revision = self.post("/api/graph", graph).json["revision"]
        base = dict(graph=graph, revision=revision, k=1, noise_model="none", observable_mode="auto")

        def compile_run(options, success=True):
            response = self.post("/api/compile", {**base, **options})
            self.assertEqual(response.status_code, 202, response.json)
            job_id = response.json["id"]
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                job = self.client.get("/api/jobs/" + job_id).json
                if job["status"] not in ("queued", "running"):
                    break
                time.sleep(0.05)
            self.assertEqual(job["status"], "complete" if success else "failed", job)
            if success:
                with self.client.get(f"/api/jobs/{job_id}/circuit.stim") as result:
                    circuit = stim.Circuit(result.text)
                return job_id, circuit
            return job

        _, original = compile_run({})
        _, taller = compile_run(
            {
                "convention": "fixed_boundary",
                "block_temporal_height": {"slope": 2, "offset": 1},
                "observable_mode": "none",
                "manhattan_radius": 0,
            }
        )
        self.assertEqual(taller.num_observables, 0)
        self.assertEqual(taller.num_detectors, 0)
        self.assertGreater(taller.num_measurements, original.num_measurements)
        # Exercise real custom rules with a memory circuit, including explicit noiseless rules.
        _, noisy = compile_run(
            {
                "noise_model": "custom",
                "custom_noise": {
                    "idle_depolarization": 0.001,
                    "any_clifford_1q_rule": {"after": {"DEPOLARIZE1": 0.001}},
                    "any_clifford_2q_rule": {"after": {"DEPOLARIZE2": 0.002}},
                    "gate_rules": {name: {"after": {}} for name in ("R", "RX", "RY")},
                    "measure_rules": {name: {"flip_result": 0.003} for name in ("X", "Y", "Z")},
                },
            }
        )
        self.assertIn("DEPOLARIZE2(0.002)", str(noisy))
        job_id, cached = compile_run({"detector_cache": "reuse", "database_name": "roundtrip"})
        database_response = self.client.get(f"/api/jobs/{job_id}/detectors.json")
        self.assertEqual(database_response.status_code, 200)
        database_data = json.loads(database_response.text)
        database_response.close()
        imported = self.post(
            "/api/detector-database", {"name": "imported", "database": database_data}
        )
        self.assertEqual(imported.status_code, 200, imported.json)
        self.assertGreater(imported.json["entries"], 0)
        _, reused = compile_run({"detector_cache": "only", "database_name": "imported"})
        self.assertEqual(cached, reused)
        compile_run({"detector_cache": "only", "database_name": "missing"}, success=False)
        self.assertEqual(
            self.post("/api/detector-database", {"name": "../escape", "database": {}}).status_code,
            400,
        )

    def test_simulation_parameters(self):
        from studio.compilation import compilation_settings
        from studio.simulation import simulation_settings, sweep_noise

        base = {"ks": [1, 2], "ps": [0.001, 0.01], "compilation": {"observable_mode": "auto"}}
        self.assertEqual(simulation_settings(base)["max_shots"], 10000)
        for changed in [
            {"ks": [True]},
            {"ps": [0]},
            {"ps": [0.1, 0.1]},
            {"max_shots": 0},
            {"num_workers": 0},
            {"decoder": "missing"},
            {"zoom_bounds": [0.1, 0.1, 0.01, 0.5]},
            {"compilation": {"noise_model": "none"}},
            {"compilation": {"observable_mode": "none"}},
            {"compilation": {"manhattan_radius": 0}},
        ]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                simulation_settings({**base, **changed})
        settings = compilation_settings(
            {
                "noise_model": "custom",
                "noise_p": 0.01,
                "custom_noise": {
                    "idle_depolarization": 0.02,
                    "measure_rules": {"Z": {"flip_result": 0.03}},
                },
            }
        )
        model = sweep_noise(0.02, settings)
        self.assertEqual(model.idle_depolarization, 0.04)
        self.assertEqual(model.measure_rules["Z"].flip_result, 0.06)
        self.assertEqual(settings["custom_noise"]["idle_depolarization"], 0.02)
        with self.assertRaises(ValueError):
            sweep_noise(0.9, settings)

    def test_real_simulation_and_plot_exports(self):
        graph = self.example()
        revision = self.post("/api/graph", graph).json["revision"]
        payload = dict(
            graph=graph,
            revision=revision,
            ks=[1],
            ps=[0.01, 0.03],
            max_shots=200,
            max_errors=100,
            num_workers=1,
            observable_inset=True,
            zoom_bounds=[0.005, 0.001, 0.05, 0.8],
            compilation={
                "observable_mode": "auto",
                "convention": "fixed_boundary",
                "block_temporal_height": {"slope": 2, "offset": 1},
            },
        )
        self.assertEqual(
            self.post("/api/simulate", {**payload, "revision": "old"}).status_code, 400
        )
        started = self.post("/api/simulate", payload)
        self.assertEqual(started.status_code, 202, started.json)
        job_id = started.json["id"]
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            job = self.client.get("/api/jobs/" + job_id).json
            if job["status"] not in ("queued", "running"):
                break
            time.sleep(0.1)
        self.assertEqual(job["status"], "complete", job)
        self.assertEqual(len(job["plots"]), 1)
        self.assertEqual(len(job["rows"]), 2)
        self.assertEqual({row["p"] for row in job["rows"]}, {0.01, 0.03})
        for row in job["rows"]:
            self.assertEqual(row["shots"], 200)
            self.assertLessEqual(row["likelihood_low"], row["rate"])
            self.assertGreaterEqual(row["likelihood_high"], row["rate"])
        for filename in ["observable-1.png", "observable-1.svg", "samples.csv", "simulation.json"]:
            with self.client.get(f"/api/simulations/{job_id}/{filename}") as response:
                self.assertEqual(response.status_code, 200)
                self.assertGreater(len(response.data), 100)
                if filename == "samples.csv":
                    self.assertIn("block_stabilizer_rounds", response.text)
                if filename == "simulation.json":
                    record = json.loads(response.text)
                    self.assertEqual(
                        record["settings"]["compilation"]["convention"], "fixed_boundary"
                    )
                    self.assertEqual(record["revision"], revision)
        self.assertEqual(
            self.client.get(f"/api/simulations/{job_id}/unapproved.txt").status_code, 404
        )

    def test_plot_observables_keep_selected_order_and_zero_error_bounds(self):
        from collections import Counter

        import sinter

        from studio.graph import checked_surfaces, graph_from_data
        from studio.simulation import render_plots

        graph = graph_from_data(self.example("cnot"))
        found = checked_surfaces(graph)
        selected = [1, 0]
        stats = [
            sinter.TaskStats(
                strong_id="test",
                decoder="pymatching",
                json_metadata={"p": 0.01, "d": 3},
                shots=100,
                errors=4,
                custom_counts=Counter({"obs_mistake_mask=E_": 3, "obs_mistake_mask=_E": 1}),
            ),
            sinter.TaskStats(
                strong_id="zero",
                decoder="pymatching",
                json_metadata={"p": 0.001, "d": 3},
                shots=100,
                errors=0,
            ),
        ]
        plots, rows = render_plots(
            Path(self.temp.name),
            graph,
            [found[i] for i in selected],
            selected,
            stats,
            {"decoder": "pymatching", "observable_inset": True, "zoom_bounds": None},
        )
        self.assertEqual([plot["observable"] for plot in plots], [2, 1])
        self.assertEqual(
            [(r["observable"], r["errors"]) for r in rows if r["p"] == 0.01], [(2, 3), (1, 1)]
        )
        for row in rows:
            if row["p"] == 0.001:
                self.assertEqual(row["rate"], 0)
                self.assertGreater(row["likelihood_high"], 0)


if __name__ == "__main__":
    unittest.main()
