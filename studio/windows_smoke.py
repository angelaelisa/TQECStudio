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
        import sinter
        import stim

        from studio import create_studio_app

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
                circuit = stim.Circuit.generated(
                    "surface_code:rotated_memory_z",
                    distance=3,
                    rounds=3,
                    after_clifford_depolarization=0.001,
                )
                stats = sinter.collect(
                    num_workers=1,
                    tasks=[sinter.Task(circuit=circuit)],
                    decoders=["pymatching"],
                    max_shots=16,
                    max_errors=16,
                )
                assert sum(s.shots for s in stats) == 16
                result.update(ok=True, compile=status["statistics"], sampled_shots=16)
            finally:
                app.extensions["studio_executor"].shutdown(wait=True)
    except BaseException:
        result["error"] = traceback.format_exc()
    Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
