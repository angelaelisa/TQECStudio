"""Local sampling and plots using TQEC's task generation and plotting helpers."""

import json
import os
import re
import uuid
from copy import deepcopy
from functools import partial
from importlib.metadata import version

import sinter
from flask import jsonify, request, send_from_directory
from tqec import compile_block_graph
from tqec.compile.convention import ALL_CONVENTIONS
from tqec.compile.detectors.database import DetectorDatabase
from tqec.simulation.generation import generate_sinter_tasks
from tqec.simulation.split import split_stats_for_observables
from tqec.utils.scale import LinearFunction

from .compilation import compilation_settings, noise_model, number


def sweep_noise(p, settings):
    settings = deepcopy(settings)
    if settings["noise_model"] == "custom":
        reference = settings["noise_p"]
        if reference <= 0:
            raise ValueError(
                "Custom noise sweeps require a positive reference probability p in Compile."
            )
        factor = p / reference
        config = settings["custom_noise"]
        for key in ("idle_depolarization", "additional_depolarization_waiting_for_m_or_r"):
            config[key] = config.get(key, 0) * factor
        rules = [config.get(key) for key in ("any_clifford_1q_rule", "any_clifford_2q_rule")]
        for key in ("gate_rules", "measure_rules"):
            rules.extend((config.get(key) or {}).values())
        for rule in rules:
            if rule is not None:
                rule["after"] = {
                    key: value * factor for key, value in rule.get("after", {}).items()
                }
                rule["flip_result"] = rule.get("flip_result", 0) * factor
    settings["noise_p"] = p
    return noise_model(settings)


def simulation_settings(data):
    settings = compilation_settings(data.get("compilation", {}))
    if settings["noise_model"] == "custom":
        settings["noise_p"] = number(
            data.get("custom_reference_p", 0.001), "Custom reference probability"
        )
    if settings["noise_model"] == "none":
        raise ValueError("Choose a noise model in Compile before running a noise sweep.")
    if settings["observable_mode"] == "none":
        raise ValueError("Choose automatic or selected observables in Compile before plotting.")
    if settings["manhattan_radius"] <= 0:
        raise ValueError(
            "Logical error-rate simulations require detectors. Set a positive detector radius in Compile."
        )
    ks, ps = data.get("ks"), data.get("ps")
    if (
        not isinstance(ks, list)
        or not ks
        or any(type(k) is not int or k < 1 for k in ks)
        or len(set(ks)) != len(ks)
    ):
        raise ValueError("Scales must be a nonempty list of distinct positive integers.")
    if not isinstance(ps, list) or not ps:
        raise ValueError("Provide at least one noise probability.")
    for p in ps:
        if not 0 < number(p, "Sweep probability") <= 1:
            raise ValueError("Sweep probabilities must be greater than 0 and at most 1.")
        sweep_noise(p, settings)
    if len(set(ps)) != len(ps):
        raise ValueError("Sweep probabilities must be distinct.")
    for k in ks:
        compilation_settings({**settings, "k": k})
    result = dict(ks=sorted(ks), ps=sorted(ps), compilation=settings)
    for key, default in [("max_shots", 10000), ("max_errors", 100), ("num_workers", 1)]:
        value = data.get(key, default)
        if type(value) is not int or value < 1:
            raise ValueError(f"{key} must be a positive integer.")
        result[key] = value
    if result["num_workers"] > (os.cpu_count() or 1):
        raise ValueError(
            f"This computer has {os.cpu_count() or 1} available CPUs; reduce the worker count."
        )
    if data.get("decoder", "pymatching") != "pymatching":
        raise ValueError("PyMatching is the installed supported decoder.")
    result["decoder"] = "pymatching"
    result["observable_inset"] = data.get("observable_inset", True)
    if type(result["observable_inset"]) is not bool:
        raise ValueError("Observable inset must be a checkbox value.")
    zoom = data.get("zoom_bounds")
    if zoom is not None:
        if not isinstance(zoom, list) or len(zoom) != 4:
            raise ValueError(
                "Zoom bounds require p minimum, rate minimum, p maximum, rate maximum."
            )
        for value in zoom:
            number(value, "Zoom bound")
        if not (0 < zoom[0] < zoom[2] <= 1 and 0 < zoom[1] < zoom[3] <= 1):
            raise ValueError("Zoom bounds must increase and lie between 0 and 1.")
    result["zoom_bounds"] = zoom
    return result


def render_plots(folder, graph, observables, selected, stats, settings):
    # Figure API avoids pyplot's global GUI state in a background Flask worker.
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from tqec.simulation.plotting.inset import plot_observable_as_inset, plot_threshold_as_inset

    split = split_stats_for_observables(stats, len(observables))
    plots, rows = [], []
    zx = graph.to_zx_graph()
    for index, (surface, obs_stats) in enumerate(zip(observables, split)):
        fig = Figure(figsize=(8, 5.8))
        fig.subplots_adjust(left=0.12, right=0.97, top=0.91, bottom=0.16)
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        sinter.plot_error_rate(
            ax=ax,
            stats=obs_stats,
            x_func=lambda stat: stat.json_metadata["p"],
            group_func=lambda stat: stat.json_metadata["d"],
            highlight_max_likelihood_factor=1000,
            plot_args_func=lambda index, key, stats: {"marker": "o"},
        )
        for stat in sorted(obs_stats, key=lambda s: (s.json_metadata["d"], s.json_metadata["p"])):
            kept = stat.shots - stat.discards
            fit = sinter.fit_binomial(
                num_shots=kept, num_hits=stat.errors, max_likelihood_factor=1000
            )
            rows.append(
                dict(
                    observable=selected[index] + 1,
                    k=(stat.json_metadata["d"] - 1) // 2,
                    nominal_distance=stat.json_metadata["d"],
                    p=stat.json_metadata["p"],
                    shots=stat.shots,
                    discards=stat.discards,
                    errors=stat.errors,
                    rate=stat.errors / kept if kept else None,
                    likelihood_low=fit.low,
                    likelihood_high=fit.high,
                    decoder=stat.decoder,
                )
            )
            if kept and not stat.errors:
                ax.scatter(
                    [stat.json_metadata["p"]],
                    [fit.high],
                    marker="v",
                    color="#64748b",
                    s=25,
                    zorder=5,
                )
        if settings["observable_inset"]:
            plot_observable_as_inset(ax, zx, surface, bounds=(0.57, 0.02, 0.4, 0.37))
            ax.child_axes[-1].set_title("Observable support", fontsize=8, color="#526c76")
        if settings["zoom_bounds"]:
            plot_threshold_as_inset(ax, obs_stats, tuple(settings["zoom_bounds"]))
        ax.set(
            xscale="log",
            yscale="log",
            xlabel="Physical noise strength p",
            ylabel="Logical error probability per shot",
            title=f"Observable {selected[index] + 1} · {settings['decoder']}",
        )
        ax.grid(True, which="both", alpha=0.2)
        ax.legend(title="Nominal distance 2k+1", loc="upper left")
        fig.text(
            0.5,
            0.025,
            "Shading: likelihood-ratio bounds (factor 1000). Gray ▼: upper bound when no errors were observed.",
            ha="center",
            va="bottom",
            fontsize=7,
        )
        filename = f"observable-{index + 1}"
        fig.savefig(folder / (filename + ".png"), dpi=170, bbox_inches="tight")
        fig.savefig(folder / (filename + ".svg"), bbox_inches="tight")
        plots.append(
            dict(observable=selected[index] + 1, png=filename + ".png", svg=filename + ".svg")
        )
        fig.clear()
    return plots, rows


def register_simulation(
    app, root, executor, jobs, lock, graph_from_data, graph_hash, checked_surfaces
):
    def update(job_id, **values):
        with lock:
            jobs[job_id].update(values)

    def run(job_id, graph_data, selected, settings):
        folder = root / job_id
        try:
            folder.mkdir()
            update(job_id, status="running", phase="Compiling sweep circuits")
            graph = graph_from_data(graph_data)
            found = checked_surfaces(graph)
            observables = [found[i] for i in selected]
            config = settings["compilation"]
            compiled = compile_block_graph(
                graph,
                convention=ALL_CONVENTIONS[config["convention"]],
                observables=observables,
                block_temporal_height=LinearFunction(**config["block_temporal_height"]),
            )
            database_path = root / "databases" / (config["database_name"] + ".json")
            database = (
                DetectorDatabase.from_file(database_path)
                if config["detector_cache"] != "disabled" and database_path.exists()
                else DetectorDatabase()
            )
            if config["detector_cache"] == "only" and not len(database):
                raise ValueError(
                    "Database-only mode requires a nonempty database. Use Reuse and update first."
                )
            tasks = list(
                generate_sinter_tasks(
                    compiled,
                    settings["ks"],
                    settings["ps"],
                    partial(sweep_noise, settings=config),
                    config["manhattan_radius"],
                    detector_database=database,
                    database_path=database_path,
                    do_not_use_database=config["detector_cache"] == "disabled",
                    only_use_database=config["detector_cache"] == "only",
                )
            )
            for task in tasks:
                k = (task.json_metadata["d"] - 1) // 2
                task.json_metadata = {
                    "d": 2 * k + 1,
                    "k": k,
                    "p": task.json_metadata["p"],
                    "block_stabilizer_rounds": config["block_temporal_height"]["slope"] * k
                    + config["block_temporal_height"]["offset"],
                }
            # Let the sampler fail explicitly when a decoder cannot handle a detector model.
            update(job_id, phase="Sampling and decoding", tasks=len(tasks))
            totals = {}

            def progress(value):
                for stat in value.new_stats:
                    previous = totals.get(stat.strong_id)
                    totals[stat.strong_id] = stat if previous is None else previous + stat
                update(
                    job_id,
                    sampled_shots=sum(s.shots for s in totals.values()),
                    sampled_errors=sum(s.errors for s in totals.values()),
                )

            stats = sinter.collect(
                num_workers=settings["num_workers"],
                tasks=tasks,
                decoders=[settings["decoder"]],
                max_shots=settings["max_shots"],
                max_errors=settings["max_errors"],
                count_observable_error_combos=True,
                progress_callback=progress,
                save_resume_filepath=folder / "samples.csv",
                print_progress=False,
            )
            update(job_id, phase="Rendering plots")
            plots, rows = render_plots(folder, graph, observables, selected, stats, settings)
            record = dict(
                schema="tqec-studio-simulation/1",
                graph=graph_data,
                revision=graph_hash(graph),
                selected_surfaces=selected,
                settings=settings,
                rows=rows,
                plots=plots,
                versions={name: version(name) for name in ("tqec", "stim", "sinter", "pymatching")},
                notes="Rates are per shot. Error budget counts any observable failure per task, not errors per individual observable. Likelihood bounds use factor 1000, not a stated confidence level. No threshold estimate is inferred.",
            )
            (folder / "simulation.json").write_text(json.dumps(record, indent=2))
            update(job_id, status="complete", phase="Complete", plots=plots, rows=rows)
        except Exception as exc:
            app.logger.exception("Simulation failed")
            update(job_id, status="failed", error=str(exc))

    @app.post("/api/simulate")
    def simulate():
        data = request.get_json()
        graph = graph_from_data(data["graph"])
        if data.get("revision") != graph_hash(graph):
            raise ValueError(
                "The graph changed. Refresh the correlation surfaces before simulating."
            )
        if graph.ports:
            raise ValueError("Fill every open port before simulating.")
        if any(c.is_y_cube for c in graph.cubes):
            raise ValueError("The installed TQEC compilers do not yet implement Y cubes.")
        settings = simulation_settings(data)
        found = checked_surfaces(graph)
        selected = (
            list(range(len(found)))
            if settings["compilation"]["observable_mode"] == "auto"
            else data.get("surfaces")
        )
        if (
            not isinstance(selected, list)
            or not selected
            or any(type(i) is not int or not 0 <= i < len(found) for i in selected)
            or len(set(selected)) != len(selected)
        ):
            raise ValueError(
                "Select one or more correlation surfaces, or choose automatic observables in Compile."
            )
        with lock:
            if any(j["status"] in ("queued", "running") for j in jobs.values()):
                return jsonify(
                    error="A compilation or simulation is already running. Wait for it to finish."
                ), 409
            job_id = uuid.uuid4().hex
            jobs[job_id] = dict(
                id=job_id,
                kind="simulation",
                status="queued",
                revision=graph_hash(graph),
                sampled_shots=0,
                sampled_errors=0,
                tasks=len(settings["ks"]) * len(settings["ps"]),
            )
        executor.submit(run, job_id, graph.to_dict(), selected, settings)
        return jsonify(id=job_id), 202

    @app.get("/api/simulations/<job_id>/<filename>")
    def simulation_artifact(job_id, filename):
        if not re.fullmatch("[0-9a-f]{32}", job_id) or not (
            filename in ("samples.csv", "simulation.json")
            or re.fullmatch(r"observable-[1-9][0-9]*\.(png|svg)", filename)
        ):
            return jsonify(error="Artifact not found."), 404
        return send_from_directory(
            root / job_id,
            filename,
            as_attachment=request.args.get("download") == "1"
            or filename.endswith((".csv", ".json")),
        )
