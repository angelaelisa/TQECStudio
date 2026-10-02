"""Regression checks for junction changes when pipes are added or removed."""

import json
import re
import tempfile
import unittest

from tqec import BlockGraph, compile_block_graph
from tqec.utils.position import Position3D as P

from studio import create_studio_app
from studio.graph import (
    CubeKindsError,
    checked_surfaces,
    delete_cube_proposal,
    delete_pipe_proposal,
    graph_from_data,
    pipe_options,
    pipe_proposal,
    validate_graph,
)


def straight(axis=2, kind="ZXZ", pipe="ZXO", origin=(0, 0, 0)):
    graph = BlockGraph("Junction regression")
    center = P(*origin)
    graph.add_cube(center, kind, "junction")
    for sign in (-1, 1):
        coords = list(origin)
        coords[axis] += sign
        end = P(*coords)
        graph.add_cube(end, "P", f"end{sign}")
        graph.add_pipe(center, end, pipe)
    return graph


class JunctionTests(unittest.TestCase):
    def test_original_parity_error_is_prevented_before_surface_discovery(self):
        graph = BlockGraph("Third branch parity regression")
        for z, kind in ((-1, "ZXX"), (0, "ZXZ"), (1, "ZXX")):
            graph.add_cube(P(0, 0, z), kind)
        for z in (-1, 0):
            graph.add_pipe(P(0, 0, z), P(0, 0, z + 1), "ZXO")
        graph.add_cube(P(0, 1, 0), "ZXX")
        # This reproduces the old editor leaving ZXZ at the new three-way junction.
        bad = graph_from_data(graph.to_dict())
        bad.add_pipe(P(0, 0, 0), P(0, 1, 0), "ZOX")
        with self.assertRaisesRegex(Exception, "supported on all or no edges"):
            compile_block_graph(bad, observables=bad.find_correlation_surfaces())
        with self.assertRaises(CubeKindsError):
            checked_surfaces(bad)
        result, ambiguous, _ = pipe_proposal(graph, [0, 0, 0], [0, 1, 0], "ZOX")
        self.assertFalse(ambiguous)
        surfaces = checked_surfaces(result)
        self.assertTrue(surfaces)
        compile_block_graph(result, observables=surfaces)

    def test_third_branch_corrects_hidden_face_in_both_directions_with_hadamard(self):
        for sign in (-1, 1):
            for hadamard in (False, True):
                for reverse in (False, True):
                    with self.subTest(sign=sign, hadamard=hadamard, reverse=reverse):
                        graph = straight()
                        original = graph.to_dict()
                        kind = ("XOZ" if sign == -1 and hadamard else "ZOX") + (
                            "H" if hadamard else ""
                        )
                        u, v = [0, 0, 0], [0, sign, 0]
                        if reverse:
                            u, v = v, u
                        result, ambiguous, inferred = pipe_proposal(graph, u, v, kind)
                        self.assertFalse(ambiguous)
                        self.assertEqual(str(result[P(0, 0, 0)].kind), "ZXX")
                        self.assertEqual(result[P(0, 0, 0)].label, "junction")
                        self.assertEqual(inferred[0]["previous"], "ZXZ")
                        self.assertEqual(graph.to_dict(), original)
                        self.assertTrue(any(p["kind"] == kind for p in result.to_dict()["pipes"]))
                        validate_graph(result)
                        self.assertTrue(checked_surfaces(result))
                        options = pipe_options(graph, kind)
                        self.assertTrue(
                            any(
                                {tuple(p["u"]), tuple(p["v"])} == {tuple(u), tuple(v)}
                                for p in options
                            )
                        )

    def test_connecting_two_existing_junctions_rechecks_both_ends(self):
        graph = straight()
        for z in (-1, 0, 1):
            graph.add_cube(P(0, 1, z), "XZX" if z == 0 else "P", f"second{z}")
        graph.add_pipe(P(0, 1, -1), P(0, 1, 0), "XZO")
        graph.add_pipe(P(0, 1, 0), P(0, 1, 1), "XZO")
        result, ambiguous, inferred = pipe_proposal(graph, [0, 0, 0], [0, 1, 0], "ZOXH")
        self.assertFalse(ambiguous)
        self.assertEqual(str(result[P(0, 0, 0)].kind), "ZXX")
        self.assertEqual(str(result[P(0, 1, 0)].kind), "XZZ")
        self.assertEqual(len(inferred), 2)
        validate_graph(result)

    def test_delete_branch_rechecks_spatial_cube_and_keeps_other_pipes(self):
        graph = straight(axis=0, pipe="OXZ")
        joined, _, _ = pipe_proposal(graph, [0, 0, 0], [0, 1, 0], "XOZ")
        self.assertEqual(str(joined[P(0, 0, 0)].kind), "XXZ")
        original = joined.to_dict()
        removed_cube, _, cube_changes = delete_cube_proposal(joined, [0, 1, 0])
        self.assertEqual(str(removed_cube[P(0, 0, 0)].kind), "ZXZ")
        self.assertEqual(cube_changes[0]["previous"], "XXZ")
        result, ambiguous, inferred = delete_pipe_proposal(joined, [0, 1, 0], [0, 0, 0])
        self.assertFalse(ambiguous)
        self.assertEqual(str(result[P(0, 0, 0)].kind), "ZXZ")
        self.assertEqual(inferred[0]["previous"], "XXZ")
        self.assertEqual(result.to_dict(), graph_from_data(graph.to_dict()).to_dict())
        self.assertEqual(joined.to_dict(), original)
        validate_graph(result)

    def test_delete_rechecks_both_ends_preserves_valid_caps_and_removes_empty_ports(self):
        graph = straight()
        joined, _, _ = pipe_proposal(graph, [0, 0, 0], [0, 1, 0], "ZOX")
        result, _, changes = delete_pipe_proposal(joined, [0, 0, 0], [0, 1, 0])
        self.assertEqual(str(result[P(0, 0, 0)].kind), "ZXX")
        self.assertEqual(changes, [])  # Both temporal boundaries are valid; retain the chosen one.
        self.assertNotIn(P(0, 1, 0), result)
        pair = BlockGraph("caps")
        pair.add_cube(P(0, 0, 0), "ZXZ")
        pair.add_cube(P(0, 0, 1), "ZXZ")
        pair.add_pipe(P(0, 0, 0), P(0, 0, 1), "ZXO")
        isolated, _, _ = delete_pipe_proposal(pair, [0, 0, 0], [0, 0, 1])
        self.assertEqual(len(isolated.cubes), 2)
        self.assertEqual(len(isolated.pipes), 0)

    def test_repair_preview_is_validated_and_reports_exact_cube_changes(self):
        graph = straight()
        graph.add_cube(P(0, 1, 0), "P", "branch")
        graph.add_pipe(P(0, 0, 0), P(0, 1, 0), "ZOX")
        graph.validate()  # The library permits the old cube's shadowed face.
        with self.assertRaises(CubeKindsError):
            validate_graph(graph)
        original = graph.to_dict()
        with tempfile.TemporaryDirectory() as folder:
            app = create_studio_app(folder)
            try:
                client = app.test_client()
                token = re.search(r'name="studio-token" content="([^"]+)"', client.get("/").text)[1]
                headers = {"X-Studio-Token": token}
                normalized = client.post("/api/graph", json=original, headers=headers).json
                self.assertTrue(normalized["repairable"])
                failed = client.post("/api/surfaces", json=original, headers=headers)
                self.assertEqual(failed.status_code, 400)
                self.assertTrue(failed.json["repairable"])
                payload = dict(graph=original, revision=normalized["revision"])
                preview = client.post("/api/repair-cubes", json=payload, headers=headers)
                self.assertEqual(preview.status_code, 200, preview.json)
                self.assertEqual(
                    preview.json["changes"], [dict(position=[0, 0, 0], before="ZXZ", after="ZXX")]
                )
                self.assertEqual(
                    preview.json["graph"]["pipes"], json.loads(json.dumps(original["pipes"]))
                )
                validate_graph(graph_from_data(preview.json["graph"]))
                stale = client.post(
                    "/api/repair-cubes", json={**payload, "revision": "stale"}, headers=headers
                )
                self.assertEqual(stale.status_code, 400)
                self.assertEqual(graph.to_dict(), original)
                deletion = client.post(
                    "/api/delete-pipe",
                    json=dict(graph=original, u=[0, 0, 0], v=[0, 1, 0]),
                    headers=headers,
                )
                self.assertEqual(deletion.status_code, 200, deletion.json)
                validate_graph(graph_from_data(deletion.json["graph"]))
            finally:
                app.extensions["studio_executor"].shutdown(wait=True)
