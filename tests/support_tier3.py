"""Tier-neutral fixtures, renderers and evidence readers shared by tiers 1 and 3.

The fixture root stays the licensed tier data directory; no solver is launched
by importing this module or by its offline readers.
"""

from __future__ import annotations

import csv
import math
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream._fsm import surface_mesh, trailing_edge_midpoints

HERE = Path(__file__).resolve().parent / "tier3_licensed"


def _one_file(folder: Path, name: str) -> Path | None:
    """The point's own copy of ``name``, when exactly one exists.

    The package keeps a per-call copy of each structural call's input under
    the point's ``fsi_archive/`` folder (:data:`pyflightstream.fsi.cli.ARCHIVE_DIR`);
    that copy is a different artifact, not a second pass of the post, so the
    count leaves that folder out by name and counts everything else.
    """
    from pyflightstream.fsi.cli import ARCHIVE_DIR

    found = sorted(
        path for path in folder.rglob(name) if ARCHIVE_DIR not in path.relative_to(folder).parts
    )
    return found[0] if len(found) == 1 else None


def one_pass(folder: Path) -> tuple[bool, str]:
    """Whether the capped point's post ran once, and the evidence read.

    One row in its convergence log, and the sectional loads export left on
    disk carrying the solver iteration that row records: the last pass of the
    post is the one the only structural call read.
    """
    from pyflightstream.fsi.driver import LOADS_FILE, LOG_FILE

    log, loads = _one_file(folder, LOG_FILE), _one_file(folder, LOADS_FILE)
    if log is None or loads is None:
        return False, f"{folder}: not exactly one {LOG_FILE} and one {LOADS_FILE}"
    body = [line for line in log.read_text(encoding="utf-8").splitlines() if line[:1] != "#"]
    rows = list(csv.DictReader(body))
    found = re.search(
        r"Current solver iteration number:\s+(\d+)", loads.read_text(encoding="utf-8")
    )
    iteration = found.group(1) if found else None
    evidence = f"{len(rows)} log row(s); the loads export left on disk is iteration {iteration}"
    if len(rows) != 1 or iteration is None:
        return False, evidence
    return rows[0]["solver_iteration"].strip() == iteration, (
        evidence + f", the row records {rows[0]['solver_iteration'].strip()}"
    )


_CAPTURE_HEADER = (
    "# synthetic duct fixture: eight vertices, six quads (inlet, outlet, four walls)\n"
)


def write_duct_obj(path: Path) -> Path:
    """Write the existing synthetic fixture to a new path; refuse overwrite."""
    vertices = [
        (0, -0.5, -0.5),
        (0, 0.5, -0.5),
        (0, 0.5, 0.5),
        (0, -0.5, 0.5),
        (2, -0.5, -0.5),
        (2, 0.5, -0.5),
        (2, 0.5, 0.5),
        (2, -0.5, 0.5),
    ]
    groups = [
        ("Inlet", [(1, 4, 3, 2)]),
        ("Outlet", [(5, 6, 7, 8)]),
        ("Wall", [(1, 2, 6, 5), (4, 8, 7, 3), (1, 5, 8, 4), (2, 3, 7, 6)]),
    ]
    lines = _CAPTURE_HEADER.splitlines()
    lines.extend("v " + " ".join(f"{value:g}" for value in v) for v in vertices)
    for name, faces in groups:
        lines.append("g " + name)
        lines.extend("f " + " ".join(map(str, face)) for face in faces)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(("\r\n".join(lines) + "\r\n").encode("ascii"))
    return path


FOLDER = HERE / "inputs" / "freestreams"


WING = HERE / "inputs" / "geometries" / "12_WING_PHY.fsm"


SPEED_M_S = 30.0


MARGIN_M = 4.0


STEP_Y_M = 2.0


STEP_Z_M = 1.0


SHEAR_PER_S = 2.5


FIELDS: dict[str, Callable[[float], float]] = {
    "fs_uniform": lambda z: SPEED_M_S,
    "fs_shear": lambda z: SPEED_M_S + SHEAR_PER_S * z,
}


MEANING = {
    "fs_uniform": "vx = 30 m/s everywhere (the rows' TASmps), vy = vz = 0",
    "fs_shear": "vx = 30 + 2.5 z m/s (sheared in z about the rows' TASmps), vy = vz = 0",
}


def extents(path: Path = WING) -> tuple[float, float, float, float]:
    """The body's (y min, y max, z min, z max), m, from its saved mesh block."""
    vertices, _ = surface_mesh(path)
    ys = [vertex[1] for vertex in vertices]
    zs = [vertex[2] for vertex in vertices]
    return min(ys), max(ys), min(zs), max(zs)


def axis(low: float, high: float, step: float) -> list[float]:
    """The stations from ``low - MARGIN_M`` to ``high + MARGIN_M``, outward to a whole step."""
    start = math.floor((low - MARGIN_M) / step) * step
    stop = math.ceil((high + MARGIN_M) / step) * step
    return [start + index * step for index in range(round((stop - start) / step) + 1)]


def grid() -> tuple[list[float], list[float]]:
    """The field's y and z stations, covering the wing's YZ extent with the margin."""
    ymin, ymax, zmin, zmax = extents()
    return axis(ymin, ymax, STEP_Y_M), axis(zmin, zmax, STEP_Z_M)


def field_text(name: str) -> str:
    """The STRUCTURED file of one field: ``Npts Mpts``, then y outer and z inner."""
    ys, zs = grid()
    speed = FIELDS[name]
    rows = [f"{len(ys)} {len(zs)}"]
    rows += [f"0.0 {y:.1f} {z:.1f} {speed(z):.2f} 0.00 0.00" for y in ys for z in zs]
    return "\n".join(rows) + "\n"


def provenance_text(name: str) -> str:
    """The provenance record beside one field."""
    ymin, ymax, zmin, zmax = extents()
    ys, zs = grid()
    return (
        f"# Provenance of the tier-3 custom free stream {name}.txt, read by the rows of\n"
        f"# matriz_gui.fs stating FREESTREAM: {name} through SET_FREESTREAM CUSTOM STRUCTURED.\n"
        "# Written by tests/tier3_licensed/freestreams.py from the mesh block of\n"
        "# 12_WING_PHY.fsm, in the STRUCTURED form of the 26.124 manual. The package reads\n"
        "# the file against that form at plan and converts nothing: metres and metres per\n"
        "# second, in the global frame.\n"
        'form = "STRUCTURED: Npts Mpts, then Npts x Mpts rows x y z vx vy vz, y outer, z inner"\n'
        f'field = "{MEANING[name]}"\n'
        f"body_y_m = [{ymin!r}, {ymax!r}]\n"
        f"body_z_m = [{zmin!r}, {zmax!r}]\n"
        f"margin_m = {MARGIN_M!r}\n"
        f"grid_y_m = [{ys[0]!r}, {ys[-1]!r}]\n"
        f"grid_z_m = [{zs[0]!r}, {zs[-1]!r}]\n"
        f"points = [{len(ys)}, {len(zs)}]\n"
        "x_m = 0.0\n"
    )


def expected() -> dict[Path, str]:
    """Every file this module writes, by its path, with its text."""
    files: dict[Path, str] = {}
    for name in FIELDS:
        files[FOLDER / f"{name}.txt"] = field_text(name)
        files[FOLDER / f"{name}.provenance.toml"] = provenance_text(name)
    return files


def stale() -> list[str]:
    """The files on disk that differ from what this module writes, by name."""
    return [
        path.name
        for path, text in expected().items()
        if not path.is_file() or path.read_text(encoding="utf-8").replace("\r\n", "\n") != text
    ]


PROBE_POL = "6001"


SIM = HERE / "sims" / f"sim_{PROBE_POL}"


LOG = SIM / "actions_probe.log"


EXPORT_STEM = "probe_export"


def invocations(sim: Path = SIM) -> int:
    log = sim / LOG.name
    if not log.is_file():
        return 0
    return sum(1 for line in log.read_text(encoding="utf-8").splitlines() if line.strip())


_NUMBERED = re.compile(rf"^{EXPORT_STEM}_(\d{{3}})(_iteration=\d+)?\.txt$")


def verdict(sim: Path = SIM) -> dict[str, object]:
    """Read the run folder and say what it shows.

    The two worlds are told apart by the NAME PATTERN and not by a literal:
    the solver stamps ``_iteration=<n>`` on every export an action makes,
    so a NO world holds ``probe_export_initial_iteration=1.txt`` and so on,
    and a verdict that looked for ``probe_export_initial.txt`` scored that
    world as YES (review of 2026-09-08). A numbered export is one the
    rewritten script asked for; an initial export is one the
    registration-time text asked for.
    """
    exports = sorted(path.name for path in sim.glob(f"{EXPORT_STEM}_*.txt"))
    numbered = [name for name in exports if _NUMBERED.match(name)]
    count = invocations(sim)
    if count == 0:
        word = "NOT_RUN"
        meaning = (
            "the COMMAND_LINE action never ran this module: no invocation was logged, so "
            "nothing here says anything about the SCRIPT action"
        )
    elif len(numbered) >= 2:
        word = "YES"
        meaning = (
            "the SCRIPT action's file is re-read on every invocation: the folder holds "
            f"{len(numbered)} exports named for distinct invocations"
        )
    elif not exports:
        word = "NONE"
        meaning = (
            "the COMMAND_LINE action ran and the SCRIPT action exported nothing, neither "
            "the registration-time file nor a rewritten one"
        )
    elif numbered:
        word = "PARTIAL"
        meaning = "exactly one rewritten export exists, which neither reading predicts"
    else:
        word = "NO"
        meaning = (
            "the SCRIPT action's file is read once, at registration: only the export the "
            "registration-time text names exists, after every rewrite"
        )
    return {
        "verdict": word,
        "meaning": meaning,
        "invocations": count,
        "exports": exports,
        "simulation_folder": str(sim),
    }


INPUTS = HERE / "inputs"


LIBRARY = INPUTS / "geometries"


@dataclass(frozen=True)
class MeshInput:
    """One raw-mesh geometry of the mesh matrix, made from a saved simulation.

    ``surface`` is the name the stand-in gives the file's one surface, which
    is the name its sidecar's ``boundaries`` states; the sidecar renames it to
    the saved simulation's own name by position, so the solver's name for an
    imported surface does not decide what the loads table calls it.
    ``scale`` multiplies every vertex: 1000 writes the metres of the saved
    simulation as millimetres.
    """

    source: str
    surface: str
    scale: float = 1.0


MESH_INPUTS: dict[str, MeshInput] = {
    "15_WING_OBJ_TE": MeshInput("10_WING.fsm", "WING_OBJ"),
    "16_WING_OBJ_DET": MeshInput("10_WING.fsm", "WING_OBJ"),
    "17_WING_OBJ_MM": MeshInput("10_WING.fsm", "WING_OBJ", scale=1000.0),
    "32_BLADE_OBJ_TE": MeshInput("30_BLADE.fsm", "BLADE_OBJ"),
    "33_BLADE_OBJ_DET": MeshInput("30_BLADE.fsm", "BLADE_OBJ"),
}


def mesh_path(name: str) -> Path:
    """The OBJ of one raw mesh of the mesh matrix, in its own folder."""
    return LIBRARY / name / f"{name}.obj"


def points_path(name: str) -> Path:
    """The trailing-edge points file beside one raw mesh; only the file route has one."""
    return LIBRARY / name / f"{name}.te.txt"


def obj_text(
    vertices: Any, triangles: Any, *, surface: str, scale: float = 1.0, note: str = ""
) -> str:
    """An OBJ of one surface: its vertices scaled, its triangles 1-based, in order."""
    rows = [f"# {note}"] if note else []
    rows.append(f"o {surface}")
    rows += [f"v {x * scale!r} {y * scale!r} {z * scale!r}" for x, y, z in vertices]
    rows += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in triangles]
    return "\n".join(rows) + "\n"


def _write_atomically(target: Path, text: str) -> None:
    """Write through a temporary name, so a concurrent reader sees one file or the other."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, target)


def write_stand_in(name: str) -> Path:
    """Write one raw mesh from its source's saved mesh block; return the OBJ."""
    spec = MESH_INPUTS[name]
    vertices, triangles = surface_mesh(LIBRARY / spec.source)
    note = (
        f"stand-in: the mesh block of {spec.source}, written by tests.tier3_licensed.prepare "
        "where no export is on disk; `prepare mesh` replaces it with the solver's export"
    )
    target = mesh_path(name)
    _write_atomically(
        target, obj_text(vertices, triangles, surface=spec.surface, scale=spec.scale, note=note)
    )
    return target


def ensure_mesh_inputs() -> list[str]:
    """Write the stand-in of every raw mesh with no OBJ on disk; return their names."""
    missing = [name for name in MESH_INPUTS if not mesh_path(name).is_file()]
    for name in missing:
        write_stand_in(name)
    return missing


def points_text(source: str) -> str:
    """The points file of a saved simulation's trailing edge, as committed beside its OBJ.

    The mid-points of the edges its saved mesh block flags as trailing
    (``pyflightstream._fsm.trailing_edge_midpoints``, the reader of RPT-065),
    in the simulation's metres, under the unit line the package's reader
    asks for.
    """
    points = trailing_edge_midpoints(LIBRARY / source)
    return "METER\n" + "".join(f"{x!r},{y!r},{z!r}\n" for x, y, z in points)


def read_obj(path: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """The vertices, triangles (0-based) and object or group names an OBJ writes.

    Read line by line rather than through the mesh reader, which merges and
    may reorder what it loads: the round trip is a question about the file.
    A polygon is split into a fan; ``a/b/c`` references keep their vertex.
    """
    vertices: list[list[float]] = []
    faces: list[tuple[int, int, int]] = []
    names: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "v":
            vertices.append([float(value) for value in fields[1:4]])
        elif fields[0] == "f":
            refs = [int(field.split("/")[0]) for field in fields[1:]]
            refs = [ref - 1 if ref > 0 else len(vertices) + ref for ref in refs]
            faces += [(refs[0], refs[k], refs[k + 1]) for k in range(1, len(refs) - 1)]
        elif fields[0] in ("o", "g"):
            names.append(" ".join(fields[1:]))
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=int), names


def _nearest(points: np.ndarray, candidates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gaps = np.linalg.norm(points[:, None, :] - candidates[None, :, :], axis=2)
    chosen = gaps.argmin(axis=1)
    return chosen, gaps[np.arange(len(points)), chosen]


def _turned(face: tuple[int, ...]) -> tuple[int, ...]:
    """A triangle turned to start at its smallest index, its orientation kept."""
    start = face.index(min(face))
    return face[start:] + face[:start]


def mesh_round_trip(source: Path, obj: Path, *, scale: float = 1.0) -> dict[str, Any]:
    """How far an OBJ of a saved simulation is from that simulation's own mesh block.

    Each OBJ vertex is matched to its nearest block vertex (the block scaled
    by ``scale``), and each OBJ triangle is read through that match: the
    same triangles in the same order, the same set with the same
    orientation, or the same set in any orientation.
    """
    block_vertices, block_faces = surface_mesh(source)
    block = np.asarray(block_vertices, dtype=float) * scale
    faces = [tuple(face) for face in block_faces]
    vertices, triangles, names = read_obj(obj)
    matched, distance = _nearest(vertices, block)
    _, back = _nearest(block, vertices)
    mapped = [tuple(int(matched[i]) for i in face) for face in triangles.tolist()]
    return {
        "vertices": [len(block), len(vertices)],
        "faces": [len(faces), len(mapped)],
        "max_vertex_distance": float(max(distance.max(), back.max())),
        "vertices_matched_one_to_one": len(set(matched.tolist())) == len(block) == len(vertices),
        "faces_in_the_same_order": mapped == faces,
        "faces_same_set_same_orientation": {_turned(f) for f in mapped}
        == {_turned(f) for f in faces},
        "faces_same_set": {tuple(sorted(f)) for f in mapped} == {tuple(sorted(f)) for f in faces},
        "surface_names": names,
    }


def check_points(name: str, obj: Path | None = None) -> dict[str, Any]:
    """Run a raw mesh's points file through the check the plan runs (T05)."""
    from pyflightstream.workspace.inputs import read_mesh_import
    from pyflightstream.workspace.wake_edges import (
        matched_trailing_edge_points,
        read_trailing_edge_points,
    )

    sidecar = LIBRARY / name / f"{name}.boundaries.toml"
    spec = read_mesh_import(sidecar)
    assert spec is not None, f"{sidecar.name} states no [import] table"
    read = read_trailing_edge_points(points_path(name))
    checked = matched_trailing_edge_points(
        read.points,
        points_unit=read.unit,
        mesh=obj or mesh_path(name),
        mesh_unit=spec.units,
        simulation_unit="METER",
        source=points_path(name).name,
        lines=read.lines,
    )
    return {"points": len(checked), "unit": read.unit, "mesh_unit": spec.units}


REPO = HERE.parents[1]


GOLDENS = HERE / "goldens"


PLACEHOLDER = "<tier3>"


INTERPRETER = "<python>"


def matrices() -> list[Path]:
    return sorted(HERE.glob("*.fs"))


def portable(text: str) -> str:
    """The rendered script with this folder's absolute path replaced, separators too.

    A path the builders render under the placeholder is spelled with the
    machine's own separator, so a golden written on Windows read
    ``<tier3>\\inputs`` where Linux renders ``<tier3>/inputs``; CI measured
    every tier-3 golden as differing on 2026-09-08. The placeholder's paths
    are therefore written with forward slashes on every machine. The
    interpreter of the machine that rendered is replaced the same way.

    FROM THE PLACEHOLDER TO THE END OF ITS LINE, wherever it stands. Until
    0.27.0 every such path began its line; a raw mesh's import writes
    ``FILE <path>`` on one line (G01), so the separators of the path after
    the keyword are rewritten too, and the text before the placeholder is
    left as the builder wrote it.

    THE WINDOWLESS SIBLING IS THE SAME INTERPRETER. Since 0.29 a Windows
    action line names ``pythonw.exe`` beside the building interpreter so no
    console opens per callback (``workflows._action_interpreter``), where
    every other platform names the building interpreter itself; both are
    replaced, so one golden holds on either. Which one Windows picks is
    pinned by ``tests/tier1_offline/test_hidden_action_python.py``.
    """
    for spelling in (HERE.as_posix(), str(HERE), str(HERE).replace("\\", "\\\\")):
        text = text.replace(spelling, PLACEHOLDER)
    text = text.replace(str(Path(sys.executable).with_name("pythonw.exe")), INTERPRETER)
    text = text.replace(sys.executable, INTERPRETER)
    lines = []
    for line in text.replace("\r\n", "\n").split("\n"):
        at = line.find(PLACEHOLDER)
        lines.append(line if at < 0 else line[:at] + line[at:].replace("\\", "/"))
    return "\n".join(lines)


def render(matrix: Path) -> tuple[int, dict[str, str]]:
    """Plan one matrix against this workspace; return (points, {point: script})."""
    for entry in (str(REPO / "src"), str(REPO)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    import pyflightstream.run._plan as plan_module
    from pyflightstream.cases import workflows
    from pyflightstream.run.matrix import plan_matrix
    from pyflightstream.script import Script
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate

    # The raw meshes of the mesh matrix are generated and never committed:
    # where no OBJ is on disk, its stand-in is written from the saved
    # simulation's own mesh block, so a clone plans the matrix it cannot run.
    ensure_mesh_inputs()

    rendered: dict[str, str] = {}
    original = plan_module._plan_point

    def hooked(campaign, case, point, ws, recipe, case_error, recorded, *, fs_version, **options):
        plan = original(
            campaign,
            case,
            point,
            ws,
            recipe,
            case_error,
            recorded,
            fs_version=fs_version,
            **options,
        )
        if plan.status.name in ("READY", "ALREADY_RECORDED") and recipe is not None:
            stem, outputs = plan_module._point_names(campaign, case, point, ws)
            point_case = case.model_copy(update={"point": dict(point), "outputs": outputs})
            script = Script(version=fs_version)
            recipe(point_case, script)
            rendered[stem] = portable(script.render())
        return plan

    # THE ACTIVITY LOG GOES TO A THROWAWAY FOLDER (GEO-060 M5). The planner's
    # stages log under ``<root>/logs`` unless an activity folder is already
    # active, and the root here is this committed folder, so every offline
    # render appended ``logs/activity.log(.jsonl)`` into the source tree. A
    # render is a plan and never a campaign, so nothing reads that log.
    from pyflightstream._progress import _ACTIVE

    plan_module._plan_point = hooked
    with tempfile.TemporaryDirectory(prefix="pyfs-offline-activity-") as activity:
        token = _ACTIVE.set(Path(activity))
        try:
            plan = plan_matrix(
                matrix,
                CampaignWorkspace(HERE, naming=NamingTemplate(point_name=MATRIX_POINT_NAME)),
                name=matrix.stem,
                recipes={},
                recipe_registry=workflows.workflow_registry(),
                write_plan=False,
            )
        finally:
            _ACTIVE.reset(token)
            plan_module._plan_point = original
    blocked = [p for p in plan.points if p.status.name not in ("READY", "ALREADY_RECORDED")]
    if blocked:
        first = blocked[0]
        raise RuntimeError(
            f"{matrix.name}: {len(blocked)} point(s) blocked at pre-flight, for example "
            f"{first.run_id}: {first.error}"
        )
    return len(plan.points), rendered


def golden_of(matrix: Path, stem: str) -> Path:
    return GOLDENS / matrix.stem / f"{stem}.txt"


def compare(matrix: Path) -> tuple[int, list[str], list[str], list[str]]:
    """Return (points, scripts without a golden, scripts differing, orphan goldens).

    An orphan is a golden no rendered point produced, left behind when a row
    is renumbered, deactivated or deleted; it is reported so the goldens
    folder cannot quietly carry a script of a row that no longer exists.
    """
    count, rendered = render(matrix)
    absent, differ = [], []
    for stem, text in rendered.items():
        golden = golden_of(matrix, stem)
        if not golden.is_file():
            absent.append(stem)
        elif golden.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            differ.append(stem)
    folder = GOLDENS / matrix.stem
    orphans = (
        sorted(p.stem for p in folder.glob("*.txt") if p.stem not in rendered)
        if folder.is_dir()
        else []
    )
    return count, absent, differ, orphans


DEFAULT_POL, MOVED_POL = "9501", "9502"


MATRIX = "lq5_wake.fs"


GEOMETRY = "31_BLADE_PHY"


BUILD = "26.124"


ALIAS = "PROP"


R_M, BLADES, J = 1.8288, 6, 0.8


V_INF, RHO = 49.0, 1.225


DELTA_THETA_DEG, REVOLUTIONS = 5.0, 4.0


STEPS_PER_REV = round(360.0 / DELTA_THETA_DEG)


MOVED_PLANE_R = 8.0


TIP_POINTS, TIP_R = 71, 0.9


SLIP_POINTS, SLIP_R = 15, 0.5


X_START_R, X_END_R = -1.0, 6.0


WAKE_SHARE = 0.2


_SETUP = """# s530: the LQ5 preset (0.34.0, RPT-130): s006 of the tier-3 tour without its
# custom flag; far field at five layers; no wake key, so the rotor row keeps the
# 4 R default of FR-321.
boundary_layer_type = "TURBULENT"
viscous_coupling = false
convergence = 1e-5
NITER = 300
set_solver_model = "SUBSONIC_PRANDTL_GLAUERT"
proximity_avoidance = "DISABLE"
stabilization = "ENABLE"
stabilization_strength = 1.0
induced_wake_velocity = true
farfield_layers = 5
significant_digits = 7
convergence_iterations = 10
solver_minimum_cp = -100
unsteady_pressure_kutta = "DISABLE"
additional_wake_relaxation_iteration = "DISABLE"
reynolds_averaged_drag_forces = "DISABLE"
wake_on_wake_induction = "ENABLE"

[flight_condition]
MUPas = 1.789e-5
ASMPS = 340.29
TK = 288.15
PPA = 101325
"""


_REFERENCE = f"""# r530: the synthetic blades-only wheel of the tier-3 31_BLADE_PHY (public shape
# law), one blade meshed and five periodic copies, hub at the origin, axis X.
area_m2 = 10.507
chord_m = 1.0
span_m = 3.6576
rotor_diameter_m = 3.6576

[aliases]
rotors = ["{ALIAS}"]

[moment_point]
x_m = 0.0
y_m = 0.0
z_m = 0.0

[{ALIAS}]
kind = "rotor"
x_m = 0.0
y_m = 0.0
z_m = 0.0
axis = "X"
rpm_sign = 1
diameter_m = 3.6576
families_general = []
families_blades = ["Blade1"]
blade1 = {{ azimuth_deg = 0.0, zero = "Y" }}
"""


_PPROC = f"""# p530: the LQ5 probes, along the rotor axis in the hub's static frame, in rotor
# radii: the tip line (the tip vortex) and the slipstream line (the induced
# velocity); the rotor's loads for its thrust coefficient.
[groups]
"1" = "all"
"2" = "rotors"

[plots]
parameters = ["FX", "FY", "FZ", "MX", "MY", "MZ"]

[[plots.groups]]
name = "TOTAL"
frame = "MRP"
families = "all"

[[plots.groups]]
name = "HUB_{{family}}"
frame = "SMRP"
families = "rotors"

[[probes]]
frame = "{ALIAS}_SMRP"
parameters = ["VX", "VZ"]
points = {TIP_POINTS}
scale = "rotor_radius"

[[probes.lines]]
start = [{X_START_R}, 0.0, {TIP_R}]
end = [{X_END_R}, 0.0, {TIP_R}]

[[probes]]
frame = "{ALIAS}_SMRP"
parameters = ["VX"]
points = {SLIP_POINTS}
scale = "rotor_radius"

[[probes.lines]]
start = [{X_START_R}, 0.0, {SLIP_R}]
end = [{X_END_R}, 0.0, {SLIP_R}]
"""


_MATRIX_HEADER = (
    "POL  | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION | FLIGHT_CONDITION | "
    "SWEEP_VALUES | GEOMETRY | REF | SET | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS | "
    "WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES\n" + "-" * 96 + "\n"
)


def _row_variables(plane: str | None) -> str:
    cells = [
        "PERIODIC_COPIES: 6",
        "ROTOR_AXIS: X",
        f"ADVANCE_RATIO: {J}",
        f"DELTA_THETA: {DELTA_THETA_DEG:g}",
        f"REVOLUTIONS: {REVOLUTIONS:g}",
        "LAST_REVS_AVG: 1",
    ]
    if plane is not None:
        cells.append(f"wake_termination_x_m: {plane}")
    return " / ".join(cells)


def matrix_text() -> str:
    """The two rows of LQ5: the DEFAULT plane, and the plane moved to 8 R."""
    row = (
        "{pol} | 1 | 1 | Rotor | - | {desc} | TASmps:{v:g}, RHOkgm3:{rho}, ALPHA:sweep | 0.0 | "
        f"{GEOMETRY}.fsm | r530 | s530 | p530 | PERIODIC | - | 8 | 4h | {BUILD} | "
        "unsteady_rotor | {cells}\n"
    )
    moved = f"{MOVED_PLANE_R * R_M:.4f}"
    return (
        _MATRIX_HEADER
        + row.format(
            pol=DEFAULT_POL,
            desc="LQ5_WAKE_4R_DEFAULT_PLANE",
            v=V_INF,
            rho=RHO,
            cells=_row_variables(None),
        )
        + row.format(
            pol=MOVED_POL,
            desc="LQ5_WAKE_4R_PLANE_AT_8R",
            v=V_INF,
            rho=RHO,
            cells=_row_variables(moved),
        )
    )


def build(workspace: Path, exe: str) -> None:
    """Write the LQ5 workspace: the inputs, the staged wheel and the matrix."""
    inputs = workspace / "inputs"
    for folder in ("setups", "references", "pproc", "geometries"):
        (inputs / folder).mkdir(parents=True, exist_ok=True)
    library = HERE / "inputs" / "geometries"
    for suffix in (".fsm", ".boundaries.toml"):
        shutil.copyfile(
            library / f"{GEOMETRY}{suffix}", inputs / "geometries" / f"{GEOMETRY}{suffix}"
        )
    (inputs / "setups" / "s530.toml").write_text(_SETUP, encoding="utf-8", newline="\n")
    (inputs / "references" / "r530.toml").write_text(_REFERENCE, encoding="utf-8", newline="\n")
    (inputs / "pproc" / "p530.toml").write_text(_PPROC, encoding="utf-8", newline="\n")
    (inputs / "executables.toml").write_text(
        f'"{BUILD}" = {{ path = "FlightStream_26124.exe", version = "{BUILD}" }}\n',
        encoding="utf-8",
        newline="\n",
    )
    (inputs / "executables.local.toml").write_text(
        # Forward slashes: a Windows path's backslashes are escapes in a TOML string.
        "# THIS MACHINE's installation of build #8172026.\n"
        f'"{BUILD}" = "{Path(exe).as_posix()}"\n',
        encoding="utf-8",
        newline="\n",
    )
    (workspace / MATRIX).write_text(matrix_text(), encoding="utf-8", newline="\n")
    print(f"built {workspace} (matrix {MATRIX}, rows {DEFAULT_POL} and {MOVED_POL})")


def _floats(row: dict[str, str], key: str) -> float | None:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _column(header: list[str], name: str) -> str | None:
    """The column of ``name``: exactly, else the one whose name starts with it."""
    if name in header:
        return name
    found = [column for column in header if column.upper().startswith(name.upper())]
    return found[0] if found else None


def probe_histories(table: Path, parameter: str) -> dict[int, list[tuple[int, float]]]:
    """Every probe's ``(STEP, value)`` history of one parameter, read with the csv module."""
    histories: dict[int, list[tuple[int, float]]] = {}
    with table.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        column = _column(list(reader.fieldnames or []), parameter)
        if column is None:
            return {}
        for row in reader:
            probe, step, value = row.get("PROBE"), row.get("STEP"), _floats(row, column)
            if probe is None or step is None or value is None or not step.strip().isdigit():
                continue
            histories.setdefault(int(probe), []).append((int(step), value))
    return {probe: sorted(points) for probe, points in histories.items()}


def harmonic(series: list[tuple[int, float]], window: int, cycles: int) -> complex | None:
    """The complex amplitude of ``cycles`` periods over the last ``window`` steps."""
    if len(series) < window:
        return None
    values = np.array([value for _, value in series[-window:]], dtype=float)
    return complex(np.fft.rfft(values - values.mean())[cycles]) * 2.0 / window


def tip_line(
    histories: dict[int, list[tuple[int, float]]], first: int
) -> list[tuple[float, complex]]:
    """``(x/R, harmonic)`` of the tip line, whose probes are numbered from ``first``."""
    spacing = (X_END_R - X_START_R) / (TIP_POINTS - 1)
    out = []
    for index in range(TIP_POINTS):
        amplitude = harmonic(histories.get(first + index, []), STEPS_PER_REV, BLADES)
        if amplitude is not None:
            out.append((X_START_R + index * spacing, amplitude))
    return out


def convection_speed(line: list[tuple[float, complex]]) -> tuple[float | None, float | None]:
    """``(V_ax / V_inf, wake end x/R)`` from the phase slope and the amplitude of the tip line."""
    downstream = [(x, a) for x, a in line if x >= 0.3]
    near = [abs(a) for x, a in downstream if x <= 1.0]
    if len(downstream) < 5 or not near:
        return None, None
    level = float(np.median(near))
    inside = []
    for x, a in downstream:
        if abs(a) < WAKE_SHARE * level:
            break
        inside.append((x, a))
    end = inside[-1][0] if inside else None
    if len(inside) < 5:
        return None, end
    xs = np.array([x * R_M for x, _ in inside])
    phases = np.unwrap(np.array([np.angle(a) for _, a in inside]))
    slope = float(np.polyfit(xs, phases, 1)[0])
    omega = 2.0 * math.pi * V_INF / (J * 2.0 * R_M)
    omega_b = BLADES * omega
    return (omega_b / abs(slope)) / V_INF if slope else None, end


def slipstream(
    histories: dict[int, list[tuple[int, float]]], first: int
) -> list[tuple[float, float]]:
    """``(x/R, mean VX / V_inf - 1)`` over the last revolution along the slipstream line."""
    spacing = (X_END_R - X_START_R) / (SLIP_POINTS - 1)
    out = []
    for index in range(SLIP_POINTS):
        series = histories.get(first + index, [])
        if len(series) >= STEPS_PER_REV:
            mean = float(np.mean([value for _, value in series[-STEPS_PER_REV:]]))
            out.append((X_START_R + index * spacing, mean / V_INF - 1.0))
    return out


def momentum_ratio(ct: float) -> float:
    """``(V_inf + v_i) / V_inf`` from momentum theory, T = 2 rho A v_i (V_inf + v_i)."""
    n = V_INF / (J * 2.0 * R_M)
    thrust = ct * RHO * n**2 * (2.0 * R_M) ** 4
    area = math.pi * R_M**2
    induced = (-V_INF + math.sqrt(V_INF**2 + 2.0 * thrust / (RHO * area))) / 2.0
    return (V_INF + induced) / V_INF
