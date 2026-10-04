"""Exercise real frozen assets, compiler, diagramming and spawned decoder workers."""

import json
import os
import re
import tempfile
import time
import traceback
from pathlib import Path


def run(output):
    result = {"ok": False}
    try:
        import tkinter as tk

        from studio import create_studio_app

        window = tk.Tk()
        try:
            window.withdraw()
            window.update()
            result["tk_version"] = str(window.tk.call("info", "patchlevel"))
        finally:
            window.destroy()

        with tempfile.TemporaryDirectory() as directory:
            os.environ["MPLCONFIGDIR"] = str(Path(directory) / "matplotlib")
            app = create_studio_app(directory)
            try:
                client = app.test_client()
                page = client.get("/").text
                token = re.search(r'name="studio-token" content="([^"]+)"', page)[1]
                headers = {"X-Studio-Token": token}
                for asset in ("studio.js", "studio.css", "physical_layers.js", "favicon.svg"):
                    assert client.get("/static/" + asset).status_code == 200
                graph = client.get("/api/example/memory").json["graph"]
                found = client.post("/api/surfaces", json=graph, headers=headers).json
                response = client.post(
                    "/api/compile",
                    json={
                        "graph": graph,
                        "revision": found["revision"],
                        "k": 1,
                        "observable_mode": "auto",
                        "noise_model": "none",
                    },
                    headers=headers,
                )
                assert response.status_code == 202, response.text
                job = response.json["id"]
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    status = client.get(f"/api/jobs/{job}").json
                    if status["status"] in ("complete", "failed"):
                        break
                    time.sleep(0.2)
                assert status["status"] == "complete", status
                for path in ("crumble", "physical-layers", "physical-slice.svg?tick=0"):
                    response = client.get(f"/api/jobs/{job}/{path}")
                    assert response.status_code == 200, response.text
                response = client.post(
                    "/api/simulate",
                    json={
                        "graph": graph,
                        "revision": found["revision"],
                        "ks": [1],
                        "ps": [0.01, 0.03],
                        "max_shots": 16,
                        "max_errors": 16,
                        "num_workers": 1,
                        "observable_inset": True,
                        "zoom_bounds": [0.005, 0.001, 0.05, 0.8],
                        "compilation": {"observable_mode": "auto"},
                    },
                    headers=headers,
                )
                assert response.status_code == 202, response.text
                simulation = response.json["id"]
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    simulated = client.get(f"/api/jobs/{simulation}").json
                    if simulated["status"] in ("complete", "failed"):
                        break
                    time.sleep(0.2)
                assert simulated["status"] == "complete", simulated
                assert len(simulated["plots"]) == 1, simulated
                assert len(simulated["rows"]) == 2, simulated
                assert all(row["shots"] == 16 for row in simulated["rows"]), simulated
                exports = ["observable-1.png", "observable-1.svg", "samples.csv", "simulation.json"]
                for filename in exports:
                    response = client.get(f"/api/simulations/{simulation}/{filename}")
                    assert response.status_code == 200, response.text
                    assert len(response.data) > 100, filename
                    if filename.endswith(".png"):
                        assert response.data.startswith(b"\x89PNG\r\n\x1a\n"), filename
                    if filename.endswith(".svg"):
                        assert b"<svg" in response.data, filename
                result.update(
                    ok=True,
                    compile=status["statistics"],
                    sampled_shots=sum(row["shots"] for row in simulated["rows"]),
                    plot_exports=exports,
                )
            finally:
                app.extensions["studio_executor"].shutdown(wait=True)
    except BaseException:
        result["error"] = traceback.format_exc()
    Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
