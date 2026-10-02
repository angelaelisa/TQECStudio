"""JSON settings adapter for the installed TQEC compilation API."""

import math
import re

from tqec import NoiseModel
from tqec.compile.convention import ALL_CONVENTIONS
from tqec.utils.noise_model import ANNOTATION, NOISE, OP_TYPES, NoiseRule


def number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number.")
    return value


def probability(value, label):
    value = number(value, label)
    if not 0 <= value <= 1:
        raise ValueError(f"{label} must be between 0 and 1.")
    return value


def noise_model(settings):
    mode = settings["noise_model"]
    if mode == "none":
        return None
    if mode in ("uniform_depolarizing", "si1000"):
        p = probability(settings["noise_p"], "Noise probability")
        if mode == "si1000" and p > 0.2:
            raise ValueError("SI1000 requires p ≤ 0.2 because measurement flips use 5p.")
        return getattr(NoiseModel, mode)(p) if p else None
    if mode != "custom":
        raise ValueError("Unknown noise model.")
    config = settings["custom_noise"]
    allowed = {
        "idle_depolarization",
        "additional_depolarization_waiting_for_m_or_r",
        "gate_rules",
        "measure_rules",
        "any_clifford_1q_rule",
        "any_clifford_2q_rule",
    }
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError("Custom noise contains unknown fields.")

    def rule(data, label, measurement=True):
        if data is None:
            return None
        if (
            not isinstance(data, dict)
            or set(data) - {"after", "flip_result"}
            or not isinstance(data.get("after", {}), dict)
        ):
            raise ValueError(f"Invalid noise rule: {label}.")
        after = data.get("after", {})
        for channel, p in after.items():
            if channel not in ("DEPOLARIZE1", "DEPOLARIZE2", "X_ERROR", "Y_ERROR", "Z_ERROR"):
                raise ValueError(
                    f"{channel} is not a supported scalar noise channel. TQEC NoiseRule does not accept vector-valued Pauli channels."
                )
            probability(p, channel)
        flip = probability(data.get("flip_result", 0), f"{label} result flip")
        if flip and not measurement:
            raise ValueError(f"{label} does not produce a measurement result.")
        return NoiseRule(after=after, flip_result=flip)

    kwargs = {
        key: probability(config.get(key, 0), key)
        for key in ("idle_depolarization", "additional_depolarization_waiting_for_m_or_r")
    }
    for key in ("any_clifford_1q_rule", "any_clifford_2q_rule"):
        kwargs[key] = rule(config.get(key), key, False)
    for key in ("gate_rules", "measure_rules"):
        entries = config.get(key)
        if entries is None:
            kwargs[key] = None
            continue
        if not isinstance(entries, dict):
            raise ValueError(f"{key} must contain named rules.")
        kwargs[key] = {}
        for name, data in entries.items():
            if key == "gate_rules":
                if name not in OP_TYPES or OP_TYPES[name] in (NOISE, ANNOTATION):
                    raise ValueError(f"Unknown operation: {name}.")
            elif not re.fullmatch("[XYZ]+", name):
                raise ValueError("Measurement rules use a Pauli basis string, such as X, Z or XX.")
            if data is None:
                raise ValueError(f"{name}: use an empty rule for explicitly noiseless operations.")
            kwargs[key][name] = rule(data, name, key == "measure_rules" or name.startswith("M"))
    return NoiseModel(**kwargs)


def compilation_settings(data):
    k = data.get("k", 1)
    if type(k) is not int or k < 1:
        raise ValueError("Scale k must be a positive integer.")
    convention = data.get("convention", "fixed_bulk")
    if convention not in ALL_CONVENTIONS:
        raise ValueError("Choose fixed bulk or fixed boundary.")
    mode = data.get("observable_mode", "selected")
    if mode not in ("selected", "auto", "none"):
        raise ValueError("Unknown observable mode.")
    height = data.get("block_temporal_height", {"slope": 2, "offset": -1})
    if not isinstance(height, dict) or set(height) != {"slope", "offset"}:
        raise ValueError("Temporal height requires slope and offset.")
    a, b = number(height["slope"], "Height slope"), number(height["offset"], "Height offset")
    rounds = a * k + b
    if rounds < 1 or not math.isclose(rounds, round(rounds), abs_tol=1e-8):
        raise ValueError(
            "Temporal height must give a positive integer number of rounds at the chosen k."
        )
    radius = data.get("manhattan_radius", 2)
    if type(radius) is not int:
        raise ValueError(
            "Detector radius must be an integer. Values ≤ 0 disable detector computation."
        )
    cache = data.get("detector_cache", "disabled")
    if cache not in ("disabled", "reuse", "only"):
        raise ValueError("Unknown detector database mode.")
    name = data.get("database_name", "default")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError("Database name must contain 1–64 letters, digits, underscores or hyphens.")
    settings = dict(
        k=k,
        distance=2 * k + 1,
        convention=convention,
        observable_mode=mode,
        block_temporal_height=height,
        manhattan_radius=radius,
        detector_cache=cache,
        database_name=name,
        noise_model=data.get("noise_model", "uniform_depolarizing"),
        noise_p=probability(data.get("noise_p", 0.001), "Noise probability"),
        custom_noise=data.get("custom_noise", {}),
    )
    noise_model(settings)  # Validate before queuing work.
    return settings
