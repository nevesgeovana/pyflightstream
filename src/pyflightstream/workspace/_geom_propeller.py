"""Propeller sub-step adapters for the geometry runner and its persistent log.

Pipeline role: measure pure blade construction, then inspect the actual IGES
trim curves and sewn topology. Kernel work stays behind the guarded adapter.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

from pyflightstream._lengths import METRES_PER_UNIT
from pyflightstream.geometry import Propeller
from pyflightstream.geometry._propeller_spinner import SEW_MM
from pyflightstream.geometry.stages import check_entry, stage_row, unpack
from pyflightstream.geometry.stages import propeller_measurement as measure
from pyflightstream.workspace._geom_assembly import Assembly
from pyflightstream.workspace._gmsh_worker import _ENV as WORKER_ENV
from pyflightstream.workspace._gmsh_worker import run_isolated

#: Largest parameter-space distance, in (u, v) units, between a written junction pcurve piece
#: and the declared junction piece it refits.
JUNCTION_UV = 1e-4
PURE_CHECKS = {
    "S1.P": ("propeller.section_fit",),
    "S4.P": (
        "propeller.solidity",
        "propeller.activity_factor",
        "propeller.beta_reference",
        "propeller.beta_0p7R",
    ),
    "S5.P": ("propeller.section_plane", "propeller.handedness"),
    "S6.P": ("propeller.loft_exact", "propeller.loft_c2"),
    "S8.P": ("propeller.closure",),
}
#: The pure spinner checks of S8.P (design-spinner section 9), recorded skipped without one.
SPINNER_CHECKS = (
    "spinner.periodic_net",
    "spinner.periodic_surface",
    "spinner.seam_shared",
    "spinner.split_exact",
    "spinner.circle",
    "spinner.continuity",
    "spinner.junction_in_band",
    "spinner.junction_gap",
)
PURE_CHECKS["S8.P"] += SPINNER_CHECKS
PROPELLER_STAGES = {*PURE_CHECKS, "S11.PU", "S11.PC", "S11.PS"}


class PropellerAssembly(Assembly):
    """Count geometrical boundaries of cap poles consistently with sewn imports."""

    def edge_counts(self, faces):
        counts = super().edge_counts(faces)
        result = {}
        for edge, count in counts.items():
            points = self._samples(edge)
            if float(np.linalg.norm(points - points[0], axis=1).max()) > 1e-12:
                result[edge] = count
        return result


def applicable_stages(planned, resolved, members):
    """Select the propeller-only surface workflow; mixed assemblies keep their full plan."""
    components = unpack(resolved)["components"]
    propellers = [
        n for n in members if components[n]["type"] == "propeller" and "definition" in components[n]
    ]
    if not propellers:
        return [stage for stage in planned if stage.row.stage not in PROPELLER_STAGES]
    if len(propellers) != len(members):
        return planned
    keep = {"S0", "S11", "S11.V", "S11.P", "S11.R", "S11.S"} | PROPELLER_STAGES
    return [stage for stage in planned if stage.row.stage in keep]


def _models(context):
    if "propellers" not in context.state:
        components = unpack(context.resolved)["components"]
        context.state["propellers"] = {
            n: Propeller(components[n]["definition"])
            for n in context.members
            if components[n]["type"] == "propeller" and "definition" in components[n]
        }
    return context.state["propellers"]


def stage_result(context, stage):
    """Measure one registered propeller sub-step, retaining every input in its record."""
    models = _models(context)
    if not models:
        return {
            "checks": [
                check_entry(cid, "skipped", note="no propeller definition in this run")
                for cid, _ in stage_row(stage).checks
            ]
        }
    inputs = {name: model.config for name, model in models.items()}
    if stage in PURE_CHECKS:
        checks = []
        for name, model in models.items():
            blade = model.blade()
            candidates = (
                model.report()["checks"]
                + [
                    measure("propeller.loft_exact", blade.info["loft_error_mm"], 1e-8, "mm"),
                    measure("propeller.loft_c2", blade.info["loft_c2_violations"], 0, "knots"),
                ]
                + (spinner_checks(model) if stage == "S8.P" else [])
            )
            checks += [
                {**c, "where": {"component": name}}
                for c in candidates
                if c["id"] in PURE_CHECKS[stage]
            ]
        return {"checks": checks, "outputs": {"inputs": inputs}}
    source = context.state["export"]["iges"]
    if stage == "S11.PU":
        checks = unit_checks(context.state["export"], models, len(models) == len(context.members))
    elif stage == "S11.PC":
        checks = trim_checks(source, declared_trims(context.state["export"]))
    else:
        expected = sum(_open_edges(model) for model in models.values())
        arguments = {"file": str(source), "expected": expected}
        checks = (
            sewn_checks(**arguments)
            if os.environ.get(WORKER_ENV) == "1"
            else run_isolated(f"{__name__}:sewn_checks", arguments, sewn_checks)
        )
        checks += _reimport_spinners(context, models)
    return {"checks": checks, "outputs": {"inputs": {"iges": source, "definitions": inputs}}}


def spinner_checks(model):
    """Return the pure spinner checks of one design, each recorded skipped without a spinner."""
    if "spinner" not in model.config:
        return [check_entry(c, "skipped", note="no [spinner] table") for c in SPINNER_CHECKS]
    return model.spinner().info["checks"]


def _open_edges(model):
    one = model.config["output"]["blades"] == "one"
    if "spinner" in model.config:
        return int(model.spinner().info["open_edges"]["one" if one else "all"])
    blades = 1 if one else model.config["propeller"]["blades"]
    return model.report()["closure"]["expected_open_edges"] * blades


def _reimport_spinners(context, models):
    """Measure every written spinner's periodicity and write its spinner.json beside the IGES."""
    from pyflightstream.geometry.stages import placement_transform, write_record

    export = context.state["export"]
    folder = Path(export["manifest"]).parent
    manifest = json.loads(Path(export["manifest"]).read_text(encoding="utf-8"))
    components = unpack(context.resolved)["components"]
    checks = []
    for name, model in models.items():
        if "spinner" not in model.config:
            continue
        info = model.spinner().info
        rotation, translation = placement_transform(components, name)
        axis = (
            rotation @ np.asarray(info["axis_point_mm"]) + 1000 * np.asarray(translation),
            rotation @ np.asarray(info["axis_dir"]),
        )
        faces = [
            (face["base"], folder / face["iges"])
            for piece in manifest["pieces"]
            if piece["component"] == name
            for face in piece["face_records"]
            if face["base"].startswith("spinner_")
        ]
        if model.config["output"]["blades"] == "one" or info["blades"] == 1:
            entry = check_entry(
                "spinner.periodic_reimport", "skipped", note="one sector or one blade written"
            )
        else:
            worst = periodic_reimport(faces, axis, info["sectors"])
            entry = measure("spinner.periodic_reimport", worst, 0.01, "mm")
        checks.append({**entry, "where": {"component": name}})
        write_record(folder / f"{name}.spinner.json", {**info, "periodic_reimport": entry})
    return checks or [
        check_entry("spinner.periodic_reimport", "skipped", note="no [spinner] table")
    ]


def periodic_reimport(faces, axis, count):
    """Largest distance, mm, between each written spinner face turned by 360/N and its neighbour.

    Each face is read back from its own IGES file and sampled on a 9 by 9 grid of its domain;
    the neighbour is evaluated at the same parameters, an upper bound of the nearest distance.
    """
    from pyflightstream.workspace._geom_gate import _Surface
    from pyflightstream.workspace._iges_names import read_iges_names
    from pyflightstream.workspace._iges_write import read_iges

    surfaces = {}
    for base, file in faces:
        entities = read_iges(file)["entities"]
        surface = next(e for e in entities if e["type"] == 128)
        scale = 1000 * METRES_PER_UNIT[read_iges_names(file).unit or "m"]
        sector, part = int(base.split("_")[1]), base.split("_")[2]
        surfaces[(sector, part)] = (_Surface(surface["parameters"]), scale)
    point, direction = axis
    k = direction / np.linalg.norm(direction)
    cross = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    angle = 2 * np.pi / count
    turn = np.eye(3) + np.sin(angle) * cross + (1 - np.cos(angle)) * cross @ cross
    worst = 0.0
    for (sector, part), (surface, scale) in surfaces.items():
        other, other_scale = surfaces[(sector % count + 1, part)]
        u0, u1, v0, v1 = surface.domain
        for u in np.linspace(u0, u1, 9):
            for v in np.linspace(v0, v1, 9):
                mine = turn @ (scale * surface.at(float(u), float(v)) - point) + point
                theirs = other_scale * other.at(float(u), float(v))
                worst = max(worst, float(np.linalg.norm(mine - theirs)))
    return worst


def unit_checks(source, names, complete):
    """Measure the written units of each propeller file, including isolated face files."""
    from pyflightstream.workspace._iges_names import read_iges_names

    folder = Path(source["manifest"]).parent
    manifest = json.loads(Path(source["manifest"]).read_text(encoding="utf-8"))
    files = [Path(source["iges"])] if complete else []
    for piece in manifest["pieces"]:
        if piece["component"] in names:
            files.append(folder / piece["file"])
            files.extend(folder / face["iges"] for face in piece["face_records"])
    wrong = [
        str(file)
        for file in dict.fromkeys(files)
        if float(METRES_PER_UNIT.get(read_iges_names(file).unit or "", 0)) != 0.001
    ]
    return [measure("propeller.output_units", len(wrong), 0, "files", note=", ".join(wrong))]


def sewn_checks(file, expected):
    """Count actual sewn edge adjacencies, permitting only declared uncapped rims."""
    from pyflightstream.workspace._gmsh import open_kernel

    kernel = open_kernel("checking propeller closure")
    try:
        topology = kernel.inspect_file(Path(file), 1e-5)
        free = sum(len(faces) == 1 for _, faces in topology.edges)
        triple = sum(len(faces) > 2 for _, faces in topology.edges)
        return [
            measure(
                "propeller.sewn_free_edges",
                abs(free - expected),
                0,
                "unexpected edges",
                note=f"{free} free; {expected} declared by uncapped rims",
            ),
            measure("propeller.sewn_triple_edges", triple, 0, "edges"),
        ]
    finally:
        kernel.close()


def _image(point, entity, by_id):
    transform = int(entity["d1"][6])
    if not transform:
        return point
    matrix = np.asarray(
        [float(v.replace("D", "E")) for v in by_id[transform]["parameters"][1:13]]
    ).reshape(3, 4)
    return matrix[:, :3] @ point + matrix[:, 3]


def _curve_samples(curves):
    """Return each curve's 33-point search grid, its points and a bound on its chords."""
    result = []
    for curve in curves:
        grid = np.linspace(curve.low, curve.high, 33)
        points = np.array([curve.at(float(t)) for t in grid])
        chord = float(np.linalg.norm(np.diff(points, axis=0), axis=1).max())
        result.append((grid, points, 2 * chord))
    return result


def _curve_distance(point, curves, samples=None):
    """Return the distance from ``point`` to the nearest of ``curves``.

    Each curve is searched from its nearest grid point and refined by a bounded scalar
    minimisation. A curve whose grid lies farther than the best distance found plus twice its
    longest grid chord cannot hold a nearer point and is not refined, so the result is the
    minimum over every curve, as before.
    """
    samples = _curve_samples(curves) if samples is None else samples
    coarse = [float(np.linalg.norm(points - point, axis=1).min()) for _, points, _ in samples]
    best = float("inf")
    for index in np.argsort(coarse):
        curve, (grid, points, margin) = curves[index], samples[index]
        if coarse[index] - margin > best:
            continue

        def error(t, curve=curve):
            return float(np.linalg.norm(curve.at(t) - point))

        j = int(np.argmin(np.linalg.norm(points - point, axis=1)))
        low, high = grid[max(0, j - 1)], grid[min(len(grid) - 1, j + 1)]
        opt = minimize_scalar(error, bounds=(low, high), method="bounded", options={"xatol": 1e-14})
        best = min(best, error(curve.low), error(curve.high), float(opt.fun))
    return best


def trim_segments(trims):
    """Return the junction and the iso pieces, in (u, v), that the source ``trims`` declare.

    ``trims`` are the plain-data trims of the layout records. A piece listed in a trim's
    ``junction`` and every piece of an inner loop is a junction piece; every other piece of an
    outer loop is an iso piece. Each result is an array of shape ``(n, 2, 2)``.
    """

    def key(piece):
        return tuple(tuple(map(float, point)) for point in piece)

    junction, iso = [], []
    for trim in trims:
        declared = {key(p) for p in trim.get("junction", ())}
        for piece in trim["loop"]:
            (junction if key(piece) in declared else iso).append(key(piece))
        junction += [key(p) for loop in trim.get("inner", ()) for p in loop]
    return np.asarray(junction, float).reshape(-1, 2, 2), np.asarray(iso, float).reshape(-1, 2, 2)


def _gap_to(point, pieces):
    """Distance from ``point`` to the nearest of the line ``pieces``, shape ``(n, 2, 2)``."""
    if not len(pieces):
        return float("inf")
    a, d = pieces[:, 0], pieces[:, 1] - pieces[:, 0]
    t = np.clip(((point - a) * d).sum(axis=1) / np.maximum((d * d).sum(axis=1), 1e-30), 0, 1)
    return float(np.linalg.norm(point - (a + t[:, None] * d), axis=1).min())


def written_junction(midpoint, segments):
    """Tell whether a written pcurve piece is a junction edge, from the trims' declared origin.

    A piece lying on a declared iso piece is an iso trim. Otherwise it is a junction edge when
    it lies within :data:`JUNCTION_UV` of a declared junction piece, which the kernel refits
    between the junction's vertices. A piece that matches neither keeps the iso limit.
    """
    junction, iso = segments
    if _gap_to(midpoint, iso) <= 1e-9:
        return False
    return _gap_to(midpoint, junction) <= JUNCTION_UV


def pcurve_report(file, trims=()):
    """Compare every written pcurve image against its spatial trim, face by face.

    Returns
    -------
    tuple
        ``(invalid, rows)``: the count of boundaries without both curves or PREF 1, and one
        row per boundary with its entity id, piece counts and the worst image distance in mm
        for its iso and for its junction pieces.
    """
    from pyflightstream.workspace._geom_gate import _boundary_curves, _pieces, _Surface
    from pyflightstream.workspace._iges_names import read_iges_names
    from pyflightstream.workspace._iges_write import read_iges

    document = read_iges(file)
    by_id = {entity["id"]: entity for entity in document["entities"]}
    boundaries = [e for e in document["entities"] if e["type"] == 142]
    scale_mm = 1000 * METRES_PER_UNIT[read_iges_names(file).unit or "m"]
    segments = trim_segments(trims)
    invalid, rows = int(not boundaries), []
    for boundary in boundaries:
        parametric, spatial = _boundary_curves(boundary)
        invalid += int(not parametric or not spatial or int(boundary["parameters"][5]) != 1)
        if not parametric or not spatial:
            continue
        uv = _pieces(by_id[parametric], by_id)
        xyz = _pieces(by_id[spatial], by_id)
        if not uv or not xyz:
            invalid += 1
            continue
        surface_entity = by_id[int(boundary["parameters"][2])]
        surface = _Surface(surface_entity["parameters"])
        samples = _curve_samples(xyz)
        row = {"boundary": boundary["id"], "iso_pieces": 0, "junction_pieces": 0}
        worst = {False: 0.0, True: 0.0}
        for curve in uv:
            kind = bool(len(trims)) and written_junction(
                curve.at((curve.low + curve.high) / 2)[:2], segments
            )
            row["junction_pieces" if kind else "iso_pieces"] += 1
            for t in np.linspace(curve.low, curve.high, 17):
                u, v = curve.at(t)[:2]
                point = _image(surface.at(float(u), float(v)), surface_entity, by_id)
                worst[kind] = max(worst[kind], _curve_distance(point, xyz, samples))
        row["iso_mm"], row["junction_mm"] = worst[False] * scale_mm, worst[True] * scale_mm
        rows.append(row)
    return invalid, rows


def trim_checks(file, trims=()):
    """Check every written pcurve image against its spatial trim, with PREF 1 required.

    Iso trims are held to 1e-4 mm. The curved junction edges the ``trims`` declare are held to
    the 0.01 mm sewing tolerance of the assembly junctions.
    """
    return pcurve_checks(*pcurve_report(file, trims))


def pcurve_checks(invalid, rows):
    """Return the trim checks of a :func:`pcurve_report`: PREF 1, iso trims, junction edges."""
    junctions = sum(row["junction_pieces"] for row in rows)
    if junctions:
        junction = measure(
            "propeller.pcurve_3d_junction",
            max(row["junction_mm"] for row in rows),
            SEW_MM,
            "mm",
            note=f"{junctions} junction pieces",
        )
    else:
        junction = check_entry(
            "propeller.pcurve_3d_junction", "skipped", note="no junction trims declared"
        )
    return [
        measure("propeller.trim_preference", invalid, 0, "boundaries"),
        measure("propeller.pcurve_3d", max([r["iso_mm"] for r in rows], default=0.0), 1e-4, "mm"),
        junction,
    ]


def declared_trims(export):
    """Return the plain-data source trims of every piece of an export, or none without records."""
    manifest = export.get("manifest")
    if not manifest or not Path(manifest).is_file():
        return []
    folder = Path(manifest).parent
    trims = []
    for piece in json.loads(Path(manifest).read_text(encoding="utf-8"))["pieces"]:
        layout = folder / piece.get("layout", "")
        if layout.is_file():
            trims += json.loads(layout.read_text(encoding="utf-8")).get("source_trims", [])
    return trims
