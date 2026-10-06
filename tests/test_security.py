"""Regression tests for the local HTTP and import security boundaries."""

import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from studio import create_studio_app
from studio.graph import graph_from_data
from studio.security import validate_dae


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_studio_app(self.temp.name)
        self.client = self.app.test_client()
        self.token = re.search(r'name="studio-token" content="([^"]+)"', self.client.get("/").text)[
            1
        ]

    def tearDown(self):
        self.app.extensions["studio_executor"].shutdown(wait=True)
        self.temp.cleanup()

    def test_host_origin_and_write_token_boundaries(self):
        self.assertEqual(
            self.client.get("/", headers={"Host": "attacker.example"}).status_code, 400
        )
        for headers in (
            {"Origin": "https://attacker.example"},
            {"Origin": "null"},
            {"Origin": "http://localhost:9999"},
            {"Sec-Fetch-Site": "cross-site"},
        ):
            self.assertEqual(
                self.client.get("/api/example/memory", headers=headers).status_code, 403
            )
        graph = self.client.get("/api/example/memory").json["graph"]
        self.assertEqual(self.client.post("/api/graph", json=graph).status_code, 403)
        headers = {"X-Studio-Token": self.token, "Origin": "http://localhost"}
        self.assertEqual(
            self.client.post("/api/graph", json=graph, headers=headers).status_code, 200
        )
        headers["Origin"] = "https://attacker.example"
        self.assertEqual(
            self.client.post("/api/graph", json=graph, headers=headers).status_code, 403
        )

    def test_security_headers_and_artifact_paths(self):
        response = self.client.get("/")
        self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        for url in [
            "/api/jobs/../secret",
            "/api/jobs/" + "a" * 32 + "/secret.txt",
            "/api/simulations/" + "a" * 32 + "/secret.txt",
        ]:
            self.assertEqual(self.client.get(url).status_code, 404)
        # Labels remain data in JSON, never interpolated into application HTML.
        graph = self.client.get("/api/example/memory").json["graph"]
        graph["name"] = "<script>alert(1)</script>"
        response = self.client.post(
            "/api/graph", json=graph, headers={"X-Studio-Token": self.token}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["graph"]["name"], graph["name"])
        self.assertNotIn(graph["name"], self.client.get("/").text)

    def test_internal_errors_do_not_expose_details(self):
        from unittest.mock import patch

        with (
            self.assertLogs(self.app.logger, level="ERROR"),
            patch(
                "studio.app.graph_from_data", side_effect=RuntimeError("private filesystem detail")
            ),
        ):
            response = self.client.post(
                "/api/graph", json={}, headers={"X-Studio-Token": self.token}
            )
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private filesystem detail", response.text)

    def test_static_assets_ignore_incorrect_system_mime_types(self):
        from unittest.mock import patch

        with patch("mimetypes.guess_type", return_value=("text/plain", None)):
            for asset, expected in (
                ("studio.js", "text/javascript"),
                ("compilation.js", "text/javascript"),
                ("simulation.js", "text/javascript"),
                ("physical_layers.js", "text/javascript"),
                ("studio.css", "text/css"),
                ("favicon.svg", "image/svg+xml"),
            ):
                with self.subTest(asset=asset), self.client.get("/static/" + asset) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, expected)
                    self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
            with self.client.get("/static/missing.js") as response:
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.mimetype, "application/json")

    def test_malicious_dae_imports(self):
        malicious = [
            b'<!DOCTYPE x [<!ENTITY test SYSTEM "file:///etc/passwd">]><COLLADA>&test;</COLLADA>',
            '<!DOCTYPE x [<!ENTITY test SYSTEM "file:///etc/passwd">]><COLLADA>&test;</COLLADA>'.encode(
                "utf-16"
            ),
            b'<COLLADA><instance_node url="file:///etc/passwd"/></COLLADA>',
            b"<COLLADA><image><init_from>http://example.com/file</init_from></image></COLLADA>",
            b'<COLLADA><node id="a"><instance_node url="#b"/></node><node id="b"><instance_node url="#a"/></node></COLLADA>',
            b"PK\x03\x04compressed archive",
        ]
        for data in malicious:
            with self.subTest(data=data[:50]):
                response = self.client.post(
                    "/api/import",
                    data={"file": (io.BytesIO(data), "model.dae")},
                    headers={"X-Studio-Token": self.token},
                )
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("root:", response.text)
        with self.assertRaises(ValueError):
            validate_dae(b"<x>" * 66 + b"</x>" * 66)

    def test_safe_dae_roundtrip_and_request_limit(self):
        graph = self.client.get("/api/example/cnot").json["graph"]
        path = Path(self.temp.name) / "graph.dae"
        graph_from_data(graph).to_dae_file(path)
        with path.open("rb") as source:
            response = self.client.post(
                "/api/import",
                data={"file": (source, "graph.dae")},
                headers={"X-Studio-Token": self.token},
            )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(len(response.json["graph"]["cubes"]), len(graph["cubes"]))
        response = self.client.post(
            "/api/graph",
            data=json.dumps({"name": "x" * (4 * 1024 * 1024)}),
            content_type="application/json",
            headers={"X-Studio-Token": self.token},
        )
        self.assertEqual(response.status_code, 413)


if __name__ == "__main__":
    unittest.main()
