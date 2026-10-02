"""Flask application factory and graph/circuit HTTP endpoints."""

import json
import secrets
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from platformdirs import user_data_path
from tqec import Basis, BlockGraph, compile_block_graph
from tqec.compile.convention import ALL_CONVENTIONS
from tqec.compile.detectors.database import DetectorDatabase
from tqec.gallery import cnot
from tqec.utils.exceptions import TQECError
from tqec.utils.position import Position3D
from tqec.utils.scale import LinearFunction
from werkzeug.exceptions import HTTPException

from .compilation import compilation_settings, noise_model
from .graph import (
    KINDS,
    CubeKindsError,
    cap_port,
    cap_ports_minimally,
    check_junction_directions,
    checked_surfaces,
    corrected_cube_kinds,
    delete_cube_proposal,
    delete_pipe_proposal,
    graph_from_data,
    graph_hash,
    pipe_options,
    pipe_proposal,
    position,
    replace_cube,
    validate_graph,
)


def create_studio_app(data_dir=None):
    app = Flask(__name__)
    from .security import configure_security

    configure_security(app)
    app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024
    root = Path(data_dir or user_data_path("TQEC Studio", appauthor=False))
    root.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tqec-compile")
    jobs, lock = {}, threading.Lock()
    app.extensions["studio_executor"] = executor

    @app.before_request
    def local_requests():
        if request.method == "POST" and not secrets.compare_digest(
            request.headers.get("X-Studio-Token", ""), token
        ):
            return jsonify(error="Reload the app before trying again."), 403

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc, HTTPException):
            return jsonify(error=exc.description), exc.code
        app.logger.debug("Studio request failed", exc_info=True)
        if isinstance(exc, CubeKindsError):
            return jsonify(error=str(exc), repairable=True), 400
        if isinstance(exc, (ValueError, TQECError, NotImplementedError)):
            return jsonify(error=str(exc)), 400
        if isinstance(exc, (KeyError, TypeError, AttributeError)):
            return jsonify(error="Missing or invalid request fields."), 400
        app.logger.error("Unexpected request failure", exc_info=exc)
        return jsonify(error="Studio could not complete this request. Check the local log."), 500

    @app.get("/")
    def index():
        return render_template("studio.html", token=token, tqec_version=version("tqec"))

    @app.get("/api/example/<name>")
    def example(name):
        if name == "cnot":
            g = cnot(Basis.Z)
        elif name == "memory":
            g = BlockGraph("Z memory")
            g.add_cube(Position3D(0, 0, 0), "ZXZ")
        elif name == "hadamard":
            g = BlockGraph("Logical Hadamard · Z to X")
            g.add_cube(Position3D(0, 0, 0), "ZXZ")
            g.add_cube(Position3D(0, 0, 1), "XZX")
            g.add_pipe(Position3D(0, 0, 0), Position3D(0, 0, 1), "ZXOH")
        elif name == "empty":
            g = BlockGraph("Untitled graph")
        else:
            raise ValueError("Unknown example.")
        return jsonify(graph=g.to_dict())

    @app.post("/api/graph")
    def normalize():
        payload = request.get_json()
        g = graph_from_data(payload)
        if payload.get("validate_edit"):
            check_junction_directions(g)
        warning = None
        repairable = False
        try:
            check_junction_directions(g)
            validate_graph(g)
        except CubeKindsError as exc:
            warning, repairable = str(exc), True
        except (ValueError, TQECError) as exc:
            warning = str(exc)
        return jsonify(
            graph=g.to_dict(), revision=graph_hash(g), warning=warning, repairable=repairable
        )

    @app.post("/api/pipe-hadamard")
    def set_pipe_hadamard():
        data = request.get_json()
        g = graph_from_data(data["graph"])
        enabled = data.get("enabled")
        if type(enabled) is not bool:
            raise ValueError("Choose whether the Hadamard transition is enabled.")
        u, v = sorted((position(data.get("u")), position(data.get("v"))))
        if not g.has_pipe_between(u, v):
            raise ValueError("Select an existing pipe.")
        graph = g.to_dict()
        for pipe in graph["pipes"]:
            if tuple(pipe["u"]) == u.as_tuple() and tuple(pipe["v"]) == v.as_tuple():
                pipe["kind"] = pipe["kind"][:3] + ("H" if enabled else "")
        result = graph_from_data(graph)
        try:
            validate_graph(result)
        except Exception as exc:
            raise ValueError(
                "This transition conflicts with the connected cube walls. "
                "Build with Hadamard pipes from the palette so junctions can be inferred, "
                "or use the Logical Hadamard example."
            ) from exc
        return jsonify(graph=result.to_dict())

    @app.post("/api/repair-cubes")
    def repair_cubes():
        data = request.get_json()
        graph = graph_from_data(data["graph"])
        if data.get("revision") != graph_hash(graph):
            raise ValueError("The graph changed. Check cube kinds again.")
        fixed, changes = corrected_cube_kinds(graph)
        validate_graph(fixed)
        return jsonify(graph=fixed.to_dict(), changes=changes)

    @app.post("/api/import")
    def import_graph():
        upload = request.files.get("file")
        if not upload or not upload.filename:
            raise ValueError("Choose a DAE or JSON project.")
        suffix = Path(upload.filename).suffix.lower()
        if suffix == ".json":
            data = json.load(upload)
            if "schema" in data:
                if data["schema"] != "tqec-studio/1":
                    raise ValueError("Unsupported Studio project version.")
                data = data["graph"]
            g = graph_from_data(data)
        elif suffix == ".dae":
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "import.dae"
                from .security import validate_dae

                contents = upload.read()
                validate_dae(contents)
                path.write_bytes(contents)
                g = graph_from_data(BlockGraph.from_dae_file(path).to_dict())
        else:
            raise ValueError("Use .json or .dae. BGRAPH requires a newer TQEC engine.")
        return jsonify(graph=g.to_dict())

    @app.post("/api/pipe-placements")
    def pipe_placements():
        data = request.get_json()
        return jsonify(placements=pipe_options(graph_from_data(data["graph"]), data.get("kind")))

    @app.post("/api/place-pipe")
    def place_pipe():
        data = request.get_json()
        result, ambiguities, inferred = pipe_proposal(
            graph_from_data(data["graph"]),
            data.get("u"),
            data.get("v"),
            data.get("kind"),
            data.get("choices"),
        )
        if ambiguities:
            return jsonify(ambiguities=ambiguities)
        return jsonify(graph=result.to_dict(), inferred=inferred)

    @app.post("/api/delete-pipe")
    def delete_pipe():
        data = request.get_json()
        result, ambiguities, inferred = delete_pipe_proposal(
            graph_from_data(data["graph"]), data.get("u"), data.get("v"), data.get("choices")
        )
        if ambiguities:
            return jsonify(ambiguities=ambiguities)
        return jsonify(graph=result.to_dict(), inferred=inferred)

    @app.post("/api/delete-cube")
    def delete_cube():
        data = request.get_json()
        result, ambiguities, inferred = delete_cube_proposal(
            graph_from_data(data["graph"]), data.get("position"), data.get("choices")
        )
        if ambiguities:
            return jsonify(ambiguities=ambiguities)
        return jsonify(graph=result.to_dict(), inferred=inferred)

    @app.post("/api/surfaces")
    def surfaces():
        g = graph_from_data(request.get_json())
        found = checked_surfaces(g)
        v2p = {v: list(p.as_tuple()) for p, v in g.to_zx_graph().p2v.items()}
        result = []
        for i, s in enumerate(found):
            result.append(
                dict(
                    index=i,
                    stabilizer=s.external_stabilizer_on_graph(g),
                    edges=[
                        dict(u=v2p[e.u.id], v=v2p[e.v.id], ub=e.u.basis.value, vb=e.v.basis.value)
                        for e in sorted(
                            s.span, key=lambda e: (e.u.id, e.v.id, e.u.basis.value, e.v.basis.value)
                        )
                    ],
                )
            )
        return jsonify(surfaces=result, revision=graph_hash(g), open_ports=list(g.ports))

    @app.post("/api/surface-viewer/<axis>")
    def surface_viewer(axis):
        axis = axis.upper()
        if axis not in ("X", "Y", "Z"):
            raise ValueError("Choose X, Y or Z faces.")
        data = request.get_json()
        g = graph_from_data(data["graph"])
        if data.get("revision") != graph_hash(g):
            raise ValueError("The graph changed. Find correlation surfaces again.")
        found = checked_surfaces(g)
        index = data.get("surface")
        if type(index) is not int or not 0 <= index < len(found):
            raise ValueError("Select a correlation surface to export.")
        viewer = str(
            g.view_as_html(
                pipe_length=2.0,
                pop_faces_at_directions=[f"+{axis}"],
                show_correlation_surface=found[index],
            )
        )
        caption = (
            f"<h2>Observable {index + 1} · +{axis} face opened</h2>"
            f"<p>Only the +{axis} face is removed. "
            "The embedded COLLADA model includes the correlation surface. "
            "The interactive viewer requires internet access to load Three.js.</p>"
        )
        viewer = viewer.replace("<body>", "<body>" + caption, 1)
        return Response(
            viewer,
            mimetype="text/html",
            headers={
                "Content-Disposition": f'attachment; filename="surface-{index + 1}-open-{axis}.html"',
                "Cache-Control": "no-store",
            },
        )

    @app.post("/api/cap-options")
    def cap_options():
        data = request.get_json()
        g = graph_from_data(data["graph"])
        if data.get("kind") not in KINDS[:-1]:
            raise ValueError("Choose a concrete cube kind.")
        options = []
        for label, pos in g.ports.items():
            try:
                cap_port(graph_from_data(g.to_dict()), label, data["kind"])
            except Exception:
                continue
            options.append(dict(position=list(pos.as_tuple()), label=label))
        return jsonify(placements=options)

    @app.post("/api/cube-options")
    def cube_options():
        data = request.get_json()
        g = graph_from_data(data["graph"])
        pos = position(data.get("position"))
        if pos not in g or g[pos].is_port:
            raise ValueError("Select a concrete cube.")
        kinds = []
        for kind in KINDS:
            try:
                replace_cube(g, pos.as_tuple(), kind)
                kinds.append(kind)
            except Exception:
                continue
        return jsonify(
            kinds=[kind for kind in kinds if kind != str(g[pos].kind) and kind != "P"],
            can_reopen="P" in kinds,
        )

    @app.post("/api/replace-cube")
    def replace_selected_cube():
        data = request.get_json()
        result = replace_cube(
            graph_from_data(data["graph"]), data.get("position"), data.get("kind")
        )
        return jsonify(graph=result.to_dict())

    @app.post("/api/cap-minimal")
    def cap_minimal():
        data = request.get_json()
        g, caps = cap_ports_minimally(graph_from_data(data["graph"]), data.get("basis"))
        return jsonify(graph=g.to_dict(), caps=caps)

    @app.post("/api/fill")
    def fill():
        data = request.get_json()
        g = graph_from_data(data["graph"])
        cap_port(g, data.get("label"), data.get("kind"))
        return jsonify(graph=g.to_dict())

    def run_compile(job_id, graph, selected, settings):
        folder = root / job_id
        try:
            with lock:
                jobs[job_id]["status"] = "running"
            g = graph_from_data(graph)
            found = checked_surfaces(g)
            folder.mkdir()
            observable_mode = settings["observable_mode"]
            observables = (
                [found[i] for i in selected]
                if observable_mode == "selected"
                else ("auto" if observable_mode == "auto" else None)
            )
            compiled = compile_block_graph(
                g,
                convention=ALL_CONVENTIONS[settings["convention"]],
                observables=observables,
                block_temporal_height=LinearFunction(**settings["block_temporal_height"]),
            )
            database_path = root / "databases" / (settings["database_name"] + ".json")
            # Supply an explicit empty database when disabled, avoiding the engine's default pickle load.
            database = (
                DetectorDatabase.from_file(database_path)
                if settings["detector_cache"] != "disabled" and database_path.exists()
                else DetectorDatabase()
            )
            if (
                settings["detector_cache"] == "only"
                and settings["manhattan_radius"] > 0
                and len(database) == 0
            ):
                # TQEC's empty-database parallel branch ignores only_use_database.
                raise ValueError(
                    "Database-only mode requires a nonempty detector database. Import one or run Reuse and update first."
                )
            circuit = compiled.generate_stim_circuit(
                k=settings["k"],
                noise_model=noise_model(settings),
                manhattan_radius=settings["manhattan_radius"],
                detector_database=database,
                database_path=database_path,
                do_not_use_database=settings["detector_cache"] == "disabled",
                only_use_database=settings["detector_cache"] == "only",
            )
            if settings["detector_cache"] != "disabled":
                database.to_file(folder / "detectors.json")
            # Validate detectors and observables; a successful compile alone is insufficient.
            circuit.detector_error_model()
            circuit.to_file(folder / "circuit.stim")
            metadata = dict(
                schema="tqec-studio-run/1",
                graph=graph,
                revision=graph_hash(g),
                settings=settings,
                selected_surfaces=selected,
                versions={"tqec": version("tqec"), "stim": version("stim")},
                statistics=dict(
                    qubits=circuit.num_qubits,
                    detectors=circuit.num_detectors,
                    observables=circuit.num_observables,
                    measurements=circuit.num_measurements,
                ),
                validation="Stim detector error model generated successfully",
            )
            (folder / "run.json").write_text(json.dumps(metadata, indent=2))
            diagram = False
            if circuit.num_qubits <= 150:
                try:
                    (folder / "circuit.svg").write_text(str(circuit.diagram("timeline-svg")))
                    diagram = True
                except Exception:
                    app.logger.exception("Circuit diagram unavailable")
            with lock:
                jobs[job_id].update(
                    status="complete",
                    statistics=metadata["statistics"],
                    diagram=diagram,
                    detector_database=settings["detector_cache"] != "disabled",
                )
        except Exception as exc:
            with lock:
                jobs[job_id].update(status="failed", error=str(exc))

    @app.post("/api/compile")
    def compile_job():
        data = request.get_json()
        g = graph_from_data(data["graph"])
        if data.get("revision") != graph_hash(g):
            raise ValueError("The graph changed. Find surfaces again before compiling.")
        if g.ports:
            raise ValueError("Fill each open port before compiling a closed experiment.")
        if any(c.is_y_cube for c in g.cubes):
            raise ValueError(
                "Y caps can be validated and inspected, but the installed TQEC fixed-bulk compiler does not implement Y cubes yet."
            )
        found = checked_surfaces(g)
        settings = compilation_settings(data)
        selected = data.get("surfaces", []) if settings["observable_mode"] == "selected" else []
        if settings["observable_mode"] == "selected" and (
            not isinstance(selected, list)
            or not selected
            or any(type(i) is not int or i < 0 or i >= len(found) for i in selected)
            or len(set(selected)) != len(selected)
        ):
            raise ValueError(
                "Select one or more distinct correlation surfaces, or choose automatic / no observables."
            )
        with lock:
            if any(j["status"] in ("queued", "running") for j in jobs.values()):
                return jsonify(
                    error="A compilation is already running. Wait for it to finish."
                ), 409
            job_id = uuid.uuid4().hex
            jobs[job_id] = dict(id=job_id, status="queued", revision=graph_hash(g))
        executor.submit(run_compile, job_id, g.to_dict(), selected, settings)
        return jsonify(id=job_id), 202

    @app.post("/api/detector-database")
    def import_detector_database():
        data = request.get_json()
        name = data.get("name", "")
        # Reuse the same bounded cache-name validation as compilation.
        compilation_settings({"database_name": name, "noise_model": "none"})
        database = DetectorDatabase.from_dict(data["database"])
        with lock:
            if any(j["status"] in ("queued", "running") for j in jobs.values()):
                return jsonify(
                    error="Wait for compilation to finish before replacing a database."
                ), 409
            database.to_file(root / "databases" / (name + ".json"))
        return jsonify(name=name, entries=len(database))

    @app.get("/api/jobs/<job_id>")
    def job(job_id):
        with lock:
            if job_id not in jobs:
                return jsonify(error="Job not found. This app may have restarted."), 404
            return jsonify(jobs[job_id])

    @app.get("/api/jobs/<job_id>/crumble")
    def crumble_viewer(job_id):
        if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            return jsonify(error="Compiled circuit not found."), 404
        circuit_path = root / job_id / "circuit.stim"
        if not circuit_path.is_file() or not (root / job_id / "run.json").is_file():
            return jsonify(error="Compile a circuit before opening Crumble."), 404
        import stim

        circuit = stim.Circuit.from_file(circuit_path)
        return Response(
            str(circuit.diagram("interactive")),
            mimetype="text/html",
            headers={"Cache-Control": "no-store"},
        )

    def physical_circuit(job_id):
        if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            raise ValueError("Choose a compiled circuit.")
        folder = root / job_id
        if not (folder / "run.json").is_file() or not (folder / "circuit.stim").is_file():
            raise ValueError("Compile a circuit before viewing physical qubit layers.")
        import stim

        return stim.Circuit.from_file(folder / "circuit.stim")

    @app.get("/api/jobs/<job_id>/physical-layers")
    def physical_layers(job_id):
        circuit = physical_circuit(job_id)
        return render_template(
            "physical_layers.html",
            job_id=job_id,
            ticks=circuit.num_ticks,
            qubits=circuit.num_qubits,
        )

    @app.get("/api/jobs/<job_id>/physical-slice.svg")
    def physical_slice(job_id):
        circuit = physical_circuit(job_id)
        try:
            tick = int(request.args.get("tick", "0"))
        except ValueError:
            raise ValueError("Choose an integer circuit time slice.") from None
        if not 0 <= tick <= circuit.num_ticks:
            raise ValueError("The time slice is outside this circuit.")
        return Response(str(circuit.diagram("timeslice-svg", tick=tick)), mimetype="image/svg+xml")

    @app.get("/api/jobs/<job_id>/<filename>")
    def artifact(job_id, filename):
        if (
            len(job_id) != 32
            or any(c not in "0123456789abcdef" for c in job_id)
            or filename not in ("circuit.stim", "run.json", "circuit.svg", "detectors.json")
        ):
            return jsonify(error="Artifact not found."), 404
        return send_from_directory(root / job_id, filename, as_attachment=filename != "circuit.svg")

    from .simulation import register_simulation

    register_simulation(
        app, root, executor, jobs, lock, graph_from_data, graph_hash, checked_surfaces
    )
    return app
