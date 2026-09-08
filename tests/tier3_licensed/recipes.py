"""Recipes of the tier-3 workspace: the LEGACY rows of its matrices.

A run matrix row whose WORKFLOW cell says ``LEGACY`` names a recipe in its
``RECIPE`` key, ``module:function``, and the recipe writes the script the
package does not know how to write. Two live here.

``prepare_geometry`` turns a synthetic shape into a saved simulation. A
workflow opens ``.fsm`` files only (``docs/mesh-inputs.md``, route 1), and the
shapes of this workspace are generated, never drawn, so a preparation row
generates the STL parts of one shape, imports them with their length units
declared, and saves the result under the name the row's ``OUTPUTS`` key
declares. The campaign stage collects that file into the run's ``raw/``
folder; the tier-3 fixture installs it into ``inputs/geometries/`` beside its
boundary sidecar and its provenance record. Every shape is public: the wing
and the blade come from ``pyflightstream.qa.geometry`` (a NACA 4-digit section,
textbook blade-element shape laws), the body is a cylinder with a hemispherical
nose and a flat base built here from its two radii. Nothing of the author's
enters (CONTRIBUTING invariant 5).

``steady_with_a_log`` is the tour's LEGACY row: a steady point written the
way a recipe writes one, opening the geometry the row resolved through the
library, reading the row's ``VELOCITY`` key, exporting the loads the row's
``OUTPUTS`` declares and the log its ``LOG_OUTPUT`` names. It exists so the
tour states every key a LEGACY row can carry.

``actions_reread_probe`` is GOAL-012 item 7b: the one licensed measurement the
unsteady-actions design of the 0.13.0 scope report waits on. It is written and
run once, and its verdict is read from the files the run leaves, never from
this module's own log.

The recipes are functions of ``(case, script)`` and nothing else, which is the
recipe protocol; where a path is needed they derive it from this file's own
location, so a clone runs them wherever it sits.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from pyflightstream.qa.geometry import (
    BladeSpec,
    WingSpec,
    blade_triangles,
    wing_triangles,
    write_stl,
)

HERE = Path(__file__).resolve().parent
#: Where the STL parts are generated. Regenerated on every build, never
#: committed: the committed artifact is the saved simulation they become.
GENERATED = HERE / "_generated"

#: The synthetic wing: NACA 0012, chord 1 m, span 8 m, meshed coarsely so a
#: tier-3 point costs seconds. The PHY-01 physics case runs the same section
#: and planform at 25 by 40; the coefficients here are judged against
#: identities and against the bands the author sets, never against PHY-01's.
WING = WingSpec(naca="0012", chord_m=1.0, span_m=8.0, n_chord=12, n_span=16)

#: The synthetic blade: the qa layer's generic BladeSpec, tip radius 1.8288 m,
#: meshed coarsely. Rotor axis along +X, blade along +Z.
BLADE = BladeSpec(n_chord=10, n_span=12)

#: The synthetic body: a cylinder of radius 0.5 m along +X from the nose at
#: x = 0 to the base at x = 4 m, with a hemispherical nose, and a flat base
#: disk as its own boundary so a BASE_REGIONS row has a base to detect.
BODY_RADIUS_M = 0.5
BODY_LENGTH_M = 4.0
BODY_N_AROUND = 24
BODY_N_ALONG = 16
BODY_N_NOSE = 6

#: Hub position of the pusher rotor behind the base, and of the twin rotors
#: beside it: the reference points ERP1, ERP2 and HUB of the workspace.
HUB_X_M = 4.5
TWIN_Y_M = 2.5


# ----------------------------------------------------------------- shapes


def _orient_outward(triangles: np.ndarray, outward_of) -> np.ndarray:
    """Flip every triangle whose normal points against ``outward_of(centroid)``."""
    out = triangles.copy()
    for i, tri in enumerate(out):
        normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        centroid = tri.mean(axis=0)
        if float(np.dot(normal, outward_of(centroid))) < 0.0:
            out[i] = tri[[0, 2, 1]]
    return out


def _ring(x: float, radius: float, n: int) -> np.ndarray:
    theta = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    return np.column_stack([np.full(n, x), radius * np.cos(theta), radius * np.sin(theta)])


def _quads_between(a: np.ndarray, b: np.ndarray) -> list[np.ndarray]:
    tris = []
    n = len(a)
    for i in range(n):
        j = (i + 1) % n
        tris.append(np.array([a[i], a[j], b[i]]))
        tris.append(np.array([a[j], b[j], b[i]]))
    return tris


def body_triangles() -> tuple[np.ndarray, np.ndarray]:
    """The body's hull and its base disk, as two outward-oriented meshes."""
    r, length = BODY_RADIUS_M, BODY_LENGTH_M
    hull: list[np.ndarray] = []
    # the nose, a hemisphere from the tip at x = 0 to the shoulder at x = r
    phis = np.linspace(0.0, np.pi / 2.0, BODY_N_NOSE + 1)
    rings = [_ring(r - r * np.cos(phi), r * np.sin(phi), BODY_N_AROUND) for phi in phis]
    tip = np.array([0.0, 0.0, 0.0])
    for i in range(BODY_N_AROUND):
        j = (i + 1) % BODY_N_AROUND
        hull.append(np.array([tip, rings[1][i], rings[1][j]]))
    for a, b in zip(rings[1:-1], rings[2:], strict=True):
        hull += _quads_between(a, b)
    # the cylinder from the shoulder to the base
    xs = np.linspace(r, length, BODY_N_ALONG + 1)
    cyl = [_ring(x, r, BODY_N_AROUND) for x in xs]
    for a, b in zip(cyl[:-1], cyl[1:], strict=True):
        hull += _quads_between(a, b)
    hull_arr = _orient_outward(
        np.array(hull), lambda c: np.array([c[0] - r if c[0] < r else 0.0, c[1], c[2]])
    )
    # the base disk at x = length, a fan from its center
    center = np.array([length, 0.0, 0.0])
    last = cyl[-1]
    base = [
        np.array([center, last[i], last[(i + 1) % BODY_N_AROUND]]) for i in range(BODY_N_AROUND)
    ]
    base_arr = _orient_outward(np.array(base), lambda c: np.array([1.0, 0.0, 0.0]))
    return hull_arr, base_arr


def _rotate_about_x(triangles: np.ndarray, angle_deg: float) -> np.ndarray:
    a = np.radians(angle_deg)
    rot = np.array([[1.0, 0.0, 0.0], [0.0, np.cos(a), -np.sin(a)], [0.0, np.sin(a), np.cos(a)]])
    return triangles @ rot.T


def _translate(triangles: np.ndarray, dx: float, dy: float, dz: float) -> np.ndarray:
    return triangles + np.array([dx, dy, dz])


def two_blade_rotor(hub: tuple[float, float, float], *, mirrored: bool = False) -> np.ndarray:
    """Two BladeSpec blades opposite each other, hub at ``hub``.

    ``mirrored`` reflects the blade through the XZ plane before it is
    placed, which is the blade of the OTHER hand: a counter-rotating pair
    is one blade and its mirror image spun the opposite way, so both
    thrust forward and their torques cancel. The same blade spun backwards
    is not a counter-rotating rotor, it is a rotor working in reverse
    (measured 2026-09-08 on the first twin row: a rolling moment a quarter
    of the thrust where the pair should cancel).
    """
    one = blade_triangles(BLADE)
    if mirrored:
        # y -> -y flips the winding, so the vertex order is swapped back to
        # keep every normal outward.
        one = (one * np.array([1.0, -1.0, 1.0]))[:, [0, 2, 1], :]
    both = np.concatenate([one, _rotate_about_x(one, 180.0)])
    return _translate(both, *hub)


#: The physics cases' own resolution, so the rows of matriz_physics.fs are
#: judged against the references under qa/references on the meshes those
#: references were seeded with: the wing at 25 by 40, the blade at 25 by 30.
WING_PHY = WingSpec(naca="0012", chord_m=1.0, span_m=8.0, n_chord=25, n_span=40)
BLADE_PHY = BladeSpec()

#: Every shape the preparation matrix can name, as the STL parts it is made
#: of: (boundary name, triangles). The boundary name is the STL solid name,
#: which is what the solver reads the boundary label from.
SHAPES = {
    "wing": lambda: [("Wing", wing_triangles(WING))],
    "halfwing": lambda: [("Wing", wing_triangles(WING, half=True))],
    "body": lambda: [("Body", body_triangles()[0]), ("Base", body_triangles()[1])],
    "blade": lambda: [("Blade1", blade_triangles(BLADE))],
    "pusher": lambda: [
        ("Body", body_triangles()[0]),
        ("Base", body_triangles()[1]),
        ("Blade1", two_blade_rotor((HUB_X_M, 0.0, 0.0))),
    ],
    "wing_phy": lambda: [("Wing", wing_triangles(WING_PHY))],
    "halfwing_phy": lambda: [("Wing", wing_triangles(WING_PHY, half=True))],
    "blade_phy": lambda: [("Blade1", blade_triangles(BLADE_PHY))],
    "twin": lambda: [
        ("Body", body_triangles()[0]),
        ("Base", body_triangles()[1]),
        ("Blade1", two_blade_rotor((HUB_X_M, TWIN_Y_M, 0.0))),
        ("Blade2", two_blade_rotor((HUB_X_M, -TWIN_Y_M, 0.0), mirrored=True)),
    ],
}


def generate_parts(shape: str) -> list[Path]:
    """Write the STL parts of ``shape`` under ``_generated/`` and return them."""
    if shape not in SHAPES:
        raise ValueError(
            f"SHAPE {shape!r} names no synthetic shape; one of {', '.join(sorted(SHAPES))}"
        )
    GENERATED.mkdir(exist_ok=True)
    paths = []
    for name, triangles in SHAPES[shape]():
        path = GENERATED / f"{shape}_{name}.stl"
        write_stl(triangles, path, name=name)
        paths.append(path)
    return paths


# ---------------------------------------------------------------- recipes


def prepare_geometry(case, script) -> None:
    """Import one synthetic shape and save it as the simulation the row names.

    The row states ``SHAPE: <name>`` among its variables and ``OUTPUTS:
    <file>.fsm``; the saved file lands in the solver's working directory,
    the simulation folder, and the campaign stage collects it into ``raw/``.
    """
    shape = str(case.variables.get("SHAPE", "")).strip().lower()
    parts = generate_parts(shape)
    script.emit("NEW_SIMULATION")
    for index, part in enumerate(parts):
        script.emit("IMPORT", "METER", "STL", part.as_posix(), clear=(index == 0))
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    script.emit("AUTO_DETECT_TRAILING_EDGES")
    # The qa cases detect the wake termination nodes right after the
    # trailing edges, and a workflow opens the saved simulation as it is,
    # so the detection has to be in the file (measured 2026-09-08: the
    # PHY-01 row's induced drag missed its band with geometries prepared
    # without it, among other differences).
    script.emit("AUTO_DETECT_WAKE_TERMINATION_NODES")
    script.emit("SAVEAS", case.outputs[0])
    script.emit("CLOSE_FLIGHTSTREAM")


def _log_name(case) -> str:
    """The row's ``LOG_OUTPUT`` with ``{point}`` filled the way ``OUTPUTS`` was.

    The package names the declared outputs per point and leaves every other
    variable as the row wrote it, so a recipe that wants a per-point log
    takes the point token from the first named output, ``loads_<point>.txt``.
    """
    log = str(case.variables.get("LOG_OUTPUT", "")).strip()
    if "{point}" in log:
        point = Path(case.outputs[0]).stem.split("_", 1)[-1]
        log = log.replace("{point}", point)
    return log


def steady_with_a_log(case, script) -> None:
    """One steady point of the row's geometry, the recipe way, with a log."""
    from pyflightstream.script import helpers

    script.emit("NEW_SIMULATION")
    script.emit("OPEN", str(case.geometry))
    helpers.free_stream(script)
    helpers.initialize_solver(script)
    helpers.solver_settings(
        script,
        vorticity_drag_boundaries="all",
        aoa=float(case.point.get("alpha", 0.0)),
        velocity=case.velocity,
        iterations=case.solver.iterations,
        convergence=case.solver.convergence,
    )
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", case.outputs[0])
    log = _log_name(case)
    if log:
        script.emit("EXPORT_LOG", log)
    script.emit("CLOSE_FLIGHTSTREAM")


def actions_reread_probe(case, script) -> None:
    """The action re-read probe: an unsteady point with two actions registered.

    GOAL-012 item 7b, PFS-2031.08. Before ``INITIALIZE_SOLVER`` and in this
    order, a ``COMMAND_LINE`` action running ``actions_probe.cmd`` beside
    this module, and a ``SCRIPT`` action pointing at ``actions/reread.txt``
    in the row's simulation folder, whose registration-time text the run
    layer writes (PFS-2031.13) and which every invocation of the command
    rewrites. The paths are absolute and derived from this file's location,
    because nothing documented says which directory the solver runs an
    action from (RPT-030). The row's ``DELTA_TIME`` and ``TIME_ITERATIONS``
    keys set the stepping; the loads export at the end is what the assessor
    judges the point by.
    """
    from pyflightstream.script import helpers
    from tests.tier3_licensed import actions_probe

    script.emit("NEW_SIMULATION")
    script.emit("OPEN", str(case.geometry))
    helpers.free_stream(script)
    helpers.unsteady_solver(
        script,
        time_iterations=int(case.variables.get("TIME_ITERATIONS", 8)),
        delta_time=float(case.variables.get("DELTA_TIME", 0.01)),
    )
    helpers.solver_settings(
        script,
        vorticity_drag_boundaries="all",
        aoa=float(case.point.get("alpha", 0.0)),
        velocity=case.velocity,
        iterations=case.solver.iterations,
        convergence=case.solver.convergence,
    )
    helpers.unsteady_action(
        script,
        name="probe_count",
        kind="COMMAND_LINE",
        filename=str(HERE / "actions_probe.cmd"),
    )
    helpers.unsteady_action(
        script,
        name="probe_reread",
        kind="SCRIPT",
        filename=str(actions_probe.ACTION_SCRIPT),
        action_script=actions_probe.initial_script(),
    )
    helpers.initialize_solver(script)
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", case.outputs[0])
    log = _log_name(case)
    if log:
        script.emit("EXPORT_LOG", log)
    script.emit("CLOSE_FLIGHTSTREAM")
