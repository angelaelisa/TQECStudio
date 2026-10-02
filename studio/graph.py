"""Graph validation, pipe inference and port editing, independent of HTTP."""

import json
from hashlib import sha256

from tqec import Basis, BlockGraph
from tqec.computation.cube import ZXCube, cube_kind_from_string
from tqec.computation.pipe import PipeKind
from tqec.utils.position import Direction3D, Position3D

KINDS = ("ZXZ", "ZXX", "XZX", "XZZ", "XXZ", "ZZX", "Y", "P")
PIPE_KINDS = ("OXZ", "OZX", "XOZ", "ZOX", "XZO", "ZXO")


def check_junction_directions(graph):
    """Enforce the documented no-3D-corner rule missing in the installed engine.

    Its shadowed-face exception otherwise lets three-axis junctions hide
    mismatched walls, including the swapped walls at a Hadamard tail.
    """
    for cube in graph.cubes:
        directions = {pipe.direction for pipe in graph.pipes_at(cube.position)}
        if len(directions) == 3:
            raise ValueError(
                f"Invalid junction at {cube.position.as_tuple()}: pipes meet along x, y and z. "
                "A junction must stay in one plane (at most two axes). "
                "Move or remove one branch; a Hadamard transition does not remove this restriction."
            )


def validate_graph(graph):
    graph.validate()
    try:
        # The same positioned-ZX preconditions used by correlation discovery.
        graph.to_zx_graph()
    except Exception:
        # Translate a 3D corner into an actionable coordinate-based message.
        check_junction_directions(graph)
        raise


def cap_port(graph, label, kind):
    if label not in graph.ports or kind not in KINDS[:-1]:
        raise ValueError("Drop a concrete cube onto an open port.")
    graph.fill_ports({label: cube_kind_from_string(kind)})
    validate_graph(graph)
    return graph


def cap_ports_minimally(graph, basis):
    """Cap each port in place using TQEC's endpoint wall/basis convention."""
    if basis not in ("X", "Z"):
        raise ValueError("Choose X or Z measurement caps.")
    if not graph.ports:
        raise ValueError("The graph has no open ports to cap.")
    validate_graph(graph)
    fills = {}
    caps = []
    for label, pos in graph.ports.items():
        pipes = graph.pipes_at(pos)
        if len(pipes) != 1:
            raise ValueError(f"Port {label} must have exactly one connected pipe.")
        pipe = pipes[0]
        at_head = pipe.u.position == pos
        # Same rule as TQEC's minimal-simulation port filling: known walls
        # come from this endpoint; the pipe-axis boundary sets the port Pauli.
        kind = ZXCube(
            *[
                pipe.kind.get_basis_along(direction, at_head) or Basis(basis)
                for direction in Direction3D.all_directions()
            ]
        )
        fills[label] = kind
        caps.append(dict(label=label, position=list(pos.as_tuple()), kind=str(kind)))
    result = graph_from_data(graph.to_dict())
    result.fill_ports(fills)
    validate_graph(result)
    return result, caps


def replace_cube(graph, coord, kind):
    pos = position(coord)
    if pos not in graph or graph[pos].is_port:
        raise ValueError("Select a concrete cube to replace.")
    if kind not in KINDS:
        raise ValueError("Choose a supported cube kind.")
    if kind == "P" and len(graph.pipes_at(pos)) != 1:
        raise ValueError("Only an end cube with exactly one pipe can be reopened as a port.")
    data = graph.to_dict()
    label = ""
    if kind == "P":
        number = 1
        while f"Port{number}" in graph.ports:
            number += 1
        label = f"Port{number}"
    for cube in data["cubes"]:
        if tuple(cube["position"]) == pos.as_tuple():
            cube.update(kind=kind, label=label)
    result = graph_from_data(data)
    validate_graph(result)
    return result


def pipe_proposal(graph, u, v, kind, choices=None):
    """Infer internal junctions; dangling endpoints stay explicit open ports."""
    if kind not in PIPE_KINDS + tuple(k + "H" for k in PIPE_KINDS):
        raise ValueError("Choose a supported pipe kind.")
    u, v = position(u), position(v)
    if not u.is_neighbour(v):
        raise ValueError("A pipe must connect neighbouring lattice positions.")
    u, v = sorted((u, v))
    parsed = PipeKind.from_str(kind)
    if list(u.as_tuple())[parsed.direction.value] + 1 != list(v.as_tuple())[parsed.direction.value]:
        raise ValueError("The pipe orientation must match its open axis.")
    if graph.cubes and u not in graph and v not in graph:
        raise ValueError("Snap the pipe to an existing endpoint or cube.")
    if not graph.cubes and u != Position3D(0, 0, 0):
        raise ValueError("Start the first pipe at the origin.")
    if graph.has_pipe_between(u, v):
        raise ValueError("A pipe already occupies this edge.")
    data = graph.to_dict()
    cubes = {tuple(c["position"]): dict(c) for c in data["cubes"]}
    labels = {c["label"] for c in data["cubes"]}
    for p in (u, v):
        if p.as_tuple() not in cubes:
            number = 1
            while f"Port{number}" in labels:
                number += 1
            label = f"Port{number}"
            labels.add(label)
            cubes[p.as_tuple()] = dict(position=p.as_tuple(), kind="P", label=label)
    if len(cubes) > 150:
        raise ValueError("This preview supports up to 150 cubes.")
    pipes = data["pipes"] + [dict(u=u.as_tuple(), v=v.as_tuple(), kind=kind)]
    choices = choices or {}
    ambiguities = []
    inferred = []
    for endpoint in (u, v):
        coord = endpoint.as_tuple()
        cube = cubes[coord]
        incident = [p for p in pipes if coord in (tuple(p["u"]), tuple(p["v"]))]
        if cube["kind"] not in ("P", "PORT") or len(incident) < 2:
            continue
        fits = []
        # A star isolates the local wall constraints without guessing neighbours' kinds.
        for candidate in KINDS:
            if candidate in ("Y", "P"):
                continue
            star = BlockGraph("junction check")
            star.add_cube(endpoint, candidate)
            try:
                for i, p in enumerate(incident):
                    other = tuple(p["v"]) if tuple(p["u"]) == coord else tuple(p["u"])
                    star.add_cube(Position3D(*other), "P", f"end{i}")
                    star.add_pipe(Position3D(*p["u"]), Position3D(*p["v"]), p["kind"])
                validate_graph(star)
                fits.append(candidate)
            except Exception:
                continue
        if not fits:
            raise ValueError(f"Pipe colours conflict at {coord}; no compatible cube exists.")
        chosen = choices.get(",".join(map(str, coord)))
        if chosen is not None and chosen not in fits:
            raise ValueError(f"The selected cube at {coord} does not match the pipe colours.")
        if len(fits) == 1:
            chosen = fits[0]
        if chosen is None:
            ambiguities.append(dict(position=list(coord), kinds=fits))
            chosen = fits[0]  # Validate a possible completion, never commit it implicitly.
        cube.update(kind=chosen, label="")
        inferred.append(dict(position=list(coord), kind=chosen))
    result = graph_from_data(dict(name=graph.name, cubes=list(cubes.values()), pipes=pipes))
    validate_graph(result)
    return result, ambiguities, inferred


def pipe_options(graph, kind):
    if kind not in PIPE_KINDS + tuple(k + "H" for k in PIPE_KINDS):
        raise ValueError("Choose a supported pipe kind.")
    axis = PipeKind.from_str(kind).direction.value
    options = []
    seen = set()
    sources = [c.position for c in graph.cubes] or [Position3D(0, 0, 0)]
    for source in sources:
        for delta in (-1, 1) if graph.cubes else (1,):
            coords = list(source.as_tuple())
            coords[axis] += delta
            if abs(coords[axis]) > 100:
                continue
            u, v = sorted((source, Position3D(*coords)))
            edge = (u, v)
            if edge in seen:
                continue
            seen.add(edge)
            try:
                _, ambiguities, _ = pipe_proposal(graph, u.as_tuple(), v.as_tuple(), kind)
                options.append(
                    dict(
                        u=list(u.as_tuple()),
                        v=list(v.as_tuple()),
                        position=[(a + b) / 2 for a, b in zip(u.as_tuple(), v.as_tuple())],
                        ambiguous=bool(ambiguities),
                    )
                )
            except ValueError:
                continue
            except Exception:
                continue
    return options


def position(value):
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or any(type(n) is not int or abs(n) > 100 for n in value)
    ):
        raise ValueError("Positions must contain three integers between -100 and 100.")
    return Position3D(*value)


def graph_from_data(data):
    if not isinstance(data, dict):
        raise ValueError("A graph object is required.")
    cubes, pipes = data.get("cubes"), data.get("pipes")
    if (
        not isinstance(cubes, list)
        or not isinstance(pipes, list)
        or len(cubes) > 150
        or len(pipes) > 450
    ):
        raise ValueError("This preview supports up to 150 cubes and 450 pipes.")
    name = data.get("name", "Untitled graph")
    if not isinstance(name, str) or len(name) > 120:
        raise ValueError("Use a project name of up to 120 characters.")
    g = BlockGraph(name)
    seen = set()
    for cube in sorted(cubes, key=lambda c: tuple(position(c.get("position")).as_tuple())):
        p = position(cube.get("position"))
        if p in seen:
            raise ValueError(f"Position {p} is already occupied.")
        seen.add(p)
        if cube.get("transform", [[1, 0, 0], [0, 1, 0], [0, 0, 1]]) != [
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
        ]:
            raise ValueError(
                "Transformed JSON blocks are not supported; import a normalized DAE instead."
            )
        kind = cube.get("kind", "")
        if kind == "PORT":
            kind = "P"
        if kind not in KINDS:
            raise ValueError(f"Unsupported cube kind: {kind}.")
        label = cube.get("label", "")
        if not isinstance(label, str) or len(label) > 120:
            raise ValueError("Labels must be text of up to 120 characters.")
        g.add_cube(p, kind, label)
    edges = set()
    for pipe in sorted(
        pipes,
        key=lambda p: (
            tuple(position(p.get("u")).as_tuple()),
            tuple(position(p.get("v")).as_tuple()),
        ),
    ):
        u, v = position(pipe.get("u")), position(pipe.get("v"))
        edge = tuple(sorted((u, v)))
        if edge in edges:
            raise ValueError("A pipe already connects these cubes.")
        edges.add(edge)
        if pipe.get("transform", [[1, 0, 0], [0, 1, 0], [0, 0, 1]]) != [
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
        ]:
            raise ValueError("Transformed JSON pipes are not supported.")
        g.add_pipe(u, v, pipe.get("kind") or None)
    return g


def graph_hash(g):
    return sha256(json.dumps(g.to_dict(), sort_keys=True).encode()).hexdigest()


def checked_surfaces(g):
    if not g.cubes:
        raise ValueError("Add at least one cube before finding surfaces.")
    validate_graph(g)
    surfaces = g.find_correlation_surfaces()
    return sorted(
        surfaces,
        key=lambda s: sorted((e.u.id, e.u.basis.value, e.v.id, e.v.basis.value) for e in s.span),
    )
