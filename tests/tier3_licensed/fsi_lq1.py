"""The licensed run LQ1 of 0.34.0: why CDo reads zero (FR-338) and the XZ moment (FR-340).

GOAL-039, arm FS, package FSI-OFF; the report it feeds is RPT-128. One
geometry serves both questions, so the run is two points of one matrix, one
solver instance at a time, FlightStream 26.124, far field 5 layers:

* ``9341``, the rigid wing (no FSI);
* ``9342``, the same wing coupled (``FSI: f340``, the fixed-wing route).

The wing is the closed right half of a synthetic NACA 4412 wing (public shape
law, :func:`pyflightstream.qa.geometry.naca4_contour`), chord 1 m, semi-span
4 m, 25 chordwise panels per side and 20 spanwise, the mesh of RPT-092 with a
cambered profile: on the symmetric NACA 0012 of RPT-092 the section moment
about the quarter chord is small and changes sign along the span, so it cannot
decide FR-340; a 4 percent camber gives a moment of one sign everywhere.

WHAT SEPARATES THE CAUSE OF FR-338. On 0.33.0 the rigid row's script updates
the sections, computes their loads and updates the probe points BEFORE its
loads spreadsheet, exactly as the coupled row's aeroelastic post does
(measured offline on the emitted scripts, 2026-10-01): the order of the
updates against the spreadsheet is the same in both, and the rigid run of
RPT-092 read CDo 0.0093534. So the coupled point here runs the 0.33.0 post
with ONE line pair added at its head, before any update:
``EXPORT_SOLVER_ANALYSIS_SPREADSHEET`` to :data:`CDO_FIRST`. The point then
leaves two loads spreadsheets of the same coupled solve:

* :data:`CDO_FIRST`, written before the post updates anything;
* the row's own ``P9342-...txt``, written where 0.33.0 writes it.

``cdo_first != 0`` and the row's ``== 0``: the package's order zeroes it
(``package_order``). Both 0, the rigid one not: the coupled analysis
itself carries no viscous drag (``solver``). Anything else is reported as
undetermined, and RPT-128 says so. The added line pair is this probe's, made
by :func:`run` patching the post in its own process; nothing in the package
changes.

THE XZ RATIOS OF FR-340 (R2, fixed before the run): on each point, the
summed cut moments over their strips against the solver's ``CMy q S c``
about the same line (the moment point on the quarter chord, the MRP the cuts
are taken in), and the summed cut forces ``Fz`` against ``Cz q S``. The
magnitude is confirmed when the moment ratio lies at least as close to 1 as
the force ratio of the same run. :func:`analyze` prints both runs' ratios;
RPT-128's front matter states the run it judges by.

Commands (from the worktree root, with the package's Python)::

    python -m tests.tier3_licensed.fsi_lq1 build C:/WORK/release-0340/lq1-fsi-ws
    python -m tests.tier3_licensed.fsi_lq1 plan  C:/WORK/release-0340/lq1-fsi-ws
    python -m tests.tier3_licensed.fsi_lq1 run   C:/WORK/release-0340/lq1-fsi-ws
    python -m tests.tier3_licensed.fsi_lq1 analyze C:/WORK/release-0340/lq1-fsi-ws

``analyze`` also reads RPT-092's own workspace as a control
(``--rigid 9211 --coupled 9212``), where it must print the 44 and 98.4
percent of that report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

#: The loads spreadsheet the probe adds at the head of the coupled point's post.
CDO_FIRST = "lq1_cdo_first.txt"
#: The two points of the matrix.
RIGID_POL, COUPLED_POL = "9341", "9342"
MATRIX = "lq1_fsi.fs"
GEOMETRY = "61_WING4412_HALF_OBJ"
NACA = "4412"
CHORD_M, SEMI_SPAN_M, N_CHORD, N_SPAN = 1.0, 4.0, 25, 20
#: Dynamic viscosity of the setup's flight condition [Pa s], for rho = Re mu / (V c).
MU_PA_S = 1.789e-5
DEFAULT_EXE = (
    "C:/GeoverseGoddess/GeoverseCloud/pyflightstream/exe/FlightStream_26124/Flightstream_26124.exe"
)

_SETUP = """# s340: steady preset of LQ1 (0.34.0, RPT-128), the s110 of RPT-092;
# far field at five layers.
boundary_layer_type = "TURBULENT"
viscous_coupling = false
convergence = 1e-5
max_parallel_threads = 8
NITER = 500
set_solver_model = "SUBSONIC_PRANDTL_GLAUERT"
proximity_avoidance = "DISABLE"
stabilization = "ENABLE"
stabilization_strength = 1.0
induced_wake_velocity = true
farfield_layers = 5
significant_digits = 7
convergence_iterations = 20
solver_minimum_cp = -100

[flight_condition]
MUPas = 1.789e-5
ASMPS = 340.29
TK = 288.15
PPA = 101325
"""

_REFERENCE = """# r340: the closed right half of the synthetic NACA 4412 wing (public shape law),
# chord 1 m, semi-span 4 m, root at y = 0; moment point on the quarter chord, the
# FSI-G pitch axis and the origin of the MRP frame the sections are cut in.
area_m2 = 4.0
chord_m = 1.0
span_m = 4.0

[moment_point]
x_m = 0.25
y_m = 0.0
z_m = 0.0
"""

_PPROC = """# p340: the fixed wing: one spanwise distribution normal to Y in MRP
# (the FSI-G route's).
[groups]
TOTAL = "all"

[sections]
count = 20
include_symmetry = false

[[sections.distributions]]
families = ["Wing"]
frame = "MRP"
planes = ["XZ"]

[products]
polars = true
sections = true
"""

_BOUNDARIES = f"""# Closed right half of the synthetic NACA {NACA} wing, one OBJ group.
boundaries = ["Wing"]

[import]
units = "METER"

[trailing_edges]
file = "{GEOMETRY}.te.txt"

[wake_termination]
detect = "auto"
"""

_MATRIX_HEADER = (
    "POL  | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION | FLIGHT_CONDITION | "
    "SWEEP_VALUES | GEOMETRY | REF | SET | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS | "
    "WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES\n" + "-" * 96 + "\n"
)


def section_contour() -> list[list[float]]:
    """The NACA 4412 contour as the FSI input takes it: (toward the LE, toward suction) [m]."""
    from pyflightstream.qa.geometry import naca4_contour

    contour = naca4_contour(NACA, N_CHORD)[:-1] * CHORD_M
    return [[round(0.25 * CHORD_M - x, 9), round(z, 9)] for x, z in contour]


def wing_obj() -> tuple[str, int]:
    """The closed half wing as OBJ text (one group), and its vertex count."""
    from pyflightstream.qa.geometry import WingSpec, wing_triangles

    spec = WingSpec(naca=NACA, chord_m=CHORD_M, span_m=SEMI_SPAN_M, n_chord=N_CHORD, n_span=N_SPAN)
    triangles = wing_triangles(spec, translation_m=(0.0, SEMI_SPAN_M / 2.0, 0.0))
    index: dict[tuple[float, float, float], int] = {}
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for triangle in triangles:
        ids = []
        for point in triangle:
            key = (round(float(point[0]), 9), round(float(point[1]), 9), round(float(point[2]), 9))
            key = tuple(0.0 if v == 0.0 else v for v in key)  # no negative zero
            if key not in index:
                index[key] = len(vertices) + 1
                vertices.append(key)
            ids.append(index[key])
        if len(set(ids)) == 3:
            faces.append((ids[0], ids[1], ids[2]))
    lines = [
        f"# closed right half of the synthetic NACA {NACA} wing (public shape law), "
        f"chord {CHORD_M:g} m, semi-span {SEMI_SPAN_M:g} m; metres",
        "o Wing",
        *(f"v {x:.9f} {y:.9f} {z:.9f}" for x, y, z in vertices),
        *(f"f {a} {b} {c}" for a, b, c in faces),
    ]
    return "\n".join(lines) + "\n", len(vertices)


def trailing_edge_points() -> str:
    """One trailing-edge point per spanwise panel, at mid-panel, in metres."""
    rows = ["METER"]
    for k in range(N_SPAN):
        y = SEMI_SPAN_M * (k + 0.5) / N_SPAN
        rows.append(f"{CHORD_M:.9f},{y:.9f},{0.0:.9f}")
    return "\n".join(rows) + "\n"


def fsi_input() -> str:
    """f340: the f011 of RPT-092 with the NACA 4412 contour at every station."""
    stations = [0.5 * k for k in range(9)]
    contour = json.dumps(section_contour())
    sections = ",\n  ".join(contour for _ in stations)
    return (
        f"# f340: the closed right half of the synthetic NACA {NACA} wing as SOLID Ti-6Al-4V\n"
        "# (grade 5, annealed), clamped at the root, under its aerodynamic loads and its own\n"
        "# weight (FSI-G). Sections: the contour of the mesh, toward the leading edge and\n"
        "# toward the suction side, about the quarter chord (the pitch axis).\n"
        'mode = "calculated"\nmaterial = "ti-6al-4v-grade5-annealed"\n\n'
        "[config]\nblade_count = 1\nomega_rad_per_s = 0.0\n\n"
        "[config.wing]\nself_weight = true\ngravity_m_per_s2 = [0.0, 0.0, -9.80665]\n"
        'span_axis = "+Y"\norigin_m = [0.25, 0.0, 0.0]\n\n'
        f"[sections]\nstation_radii_m = {json.dumps(stations)}\n"
        f"chord_m = {json.dumps([CHORD_M] * len(stations))}\n"
        f"geometric_pitch_deg = {json.dumps([0.0] * len(stations))}\n"
        f'geometry_source = "Synthetic NACA {NACA} (public shape law, '
        'pyflightstream.qa.geometry), chord 1 m, metres"\n'
        "torsion_grid_cells = 64\n"
        f"sections_m = [\n  {sections}\n]\n"
    )


def build(workspace: Path, exe: str) -> None:
    """Write the LQ1 workspace: inputs, the mesh with its sidecars, and the matrix."""
    inputs = workspace / "inputs"
    geometry = inputs / "geometries" / GEOMETRY
    for folder in ("setups", "references", "pproc", "fsi", "freestreams", "profiles"):
        (inputs / folder).mkdir(parents=True, exist_ok=True)
    geometry.mkdir(parents=True, exist_ok=True)
    obj, count = wing_obj()
    (geometry / f"{GEOMETRY}.obj").write_text(obj, encoding="utf-8")
    (geometry / f"{GEOMETRY}.boundaries.toml").write_text(_BOUNDARIES, encoding="utf-8")
    (geometry / f"{GEOMETRY}.te.txt").write_text(trailing_edge_points(), encoding="utf-8")
    (inputs / "setups" / "s340.toml").write_text(_SETUP, encoding="utf-8")
    (inputs / "references" / "r340.toml").write_text(_REFERENCE, encoding="utf-8")
    (inputs / "pproc" / "p340.toml").write_text(_PPROC, encoding="utf-8")
    (inputs / "fsi" / "f340.toml").write_text(fsi_input(), encoding="utf-8")
    (inputs / "executables.toml").write_text(
        '"26.124" = { path = "FlightStream_26124.exe", version = "26.124" }\n', encoding="utf-8"
    )
    (inputs / "executables.local.toml").write_text(
        f'# THIS MACHINE\'s installation of build #8172026.\n"26.124" = "{exe}"\n',
        encoding="utf-8",
    )
    row = (
        "{pol} | 1 | 1 | WINGSYN | - | {desc} | MACH:0.147, REmi:3.42, ALPHA:sweep | 5.0 | "
        f"{GEOMETRY}.obj | r340 | s340 | p340 | NONE | - | - | 2h | 26.124 | steady |"
    )
    matrix = (
        _MATRIX_HEADER
        + row.format(pol=RIGID_POL, desc="LQ1_WING4412_RIGID")
        + "\n"
        + row.format(pol=COUPLED_POL, desc="LQ1_WING4412_FSI_TI")
        + " FSI: f340\n"
    )
    (workspace / MATRIX).write_text(matrix, encoding="utf-8")
    print(f"built {workspace} ({count} vertices, matrix {MATRIX})")


class _EarlyExport:
    """The 0.33.0 post with the probe's spreadsheet export at its head."""

    def __init__(self, post: object) -> None:
        self._post = post
        self.surface_translations = post.surface_translations  # type: ignore[attr-defined]

    def render(self) -> str:
        head = f"EXPORT_SOLVER_ANALYSIS_SPREADSHEET\n{CDO_FIRST}\n\n"
        return head + self._post.render()  # type: ignore[attr-defined]


def install_probe_post() -> None:
    """Make every aeroelastic post this process builds carry the probe's head export.

    Only a coupled point builds an aeroelastic post, so the rigid point's
    script is the package's own.
    """
    from pyflightstream.cases import fsi_workspace

    original = fsi_workspace.aeroelastic_post

    def aeroelastic_post(*args: object, **kwargs: object) -> object:
        return _EarlyExport(original(*args, **kwargs))  # type: ignore[arg-type]

    fsi_workspace.aeroelastic_post = aeroelastic_post  # type: ignore[assignment]


def _patched_cli(argv: list[str]) -> int:
    """Run ``pyfs-matrix`` in this process with the probe's post (the coupled point only)."""
    from pyflightstream.run import cli

    install_probe_post()
    return cli.main(argv)


def _datapoint(workspace: Path, pol: str) -> Path:
    found = sorted((workspace / "sims" / f"sim_{pol}" / "datapoints").glob("DP-*"))
    if len(found) != 1:
        raise SystemExit(f"sim_{pol}: expected one datapoint folder, found {found}")
    return found[0]


def _loads(folder: Path, name: str | None = None) -> object:
    from pyflightstream.results.loads import parse_loads

    if name is None:
        named = [p for p in folder.glob("P*.txt") if re.fullmatch(r"P\d+-[^_]+\.txt", p.name)]
        if len(named) != 1:
            raise SystemExit(f"{folder}: expected one loads spreadsheet, found {named}")
        path = named[0]
    else:
        path = folder / name
    return parse_loads(path.read_text(encoding="utf-8"))


def xz_ratios(folder: Path) -> dict[str, float]:
    """The two ratios of FR-340 R2 on one point, from its loads and its section loads."""
    from pyflightstream.results.sectional_loads import parse_sectional_loads

    report = _loads(folder)
    total = report.total  # type: ignore[attr-defined]
    velocity = float(report.freestream_velocity_m_s)  # type: ignore[attr-defined]
    reynolds = float(report.reynolds)  # type: ignore[attr-defined]
    area = float(report.reference_area)  # type: ignore[attr-defined]
    length = float(report.reference_length)  # type: ignore[attr-defined]
    rho = reynolds * MU_PA_S / (velocity * length)
    q = 0.5 * rho * velocity**2
    sloads = [p for p in folder.glob("P*_sloads.txt")]
    if len(sloads) != 1:
        raise SystemExit(f"{folder}: expected one section loads export, found {sloads}")
    sections = parse_sectional_loads(sloads[0].read_text(encoding="utf-8"))
    order = np.argsort(sections.offset_m)
    offsets = sections.offset_m[order]
    moment = sections.moment_qc_nm_per_m[order]
    force = sections.fz_n_per_m[order]
    edges = np.concatenate(([0.0], 0.5 * (offsets[1:] + offsets[:-1]), [SEMI_SPAN_M]))
    width = np.diff(edges)
    cut_moment = float(np.sum(moment * width))
    cut_force = float(np.sum(force * width))
    solver_moment = float(total["CMy"]) * q * area * length
    solver_force = float(total["Cz"]) * q * area
    return {
        "cut_moment_nm": cut_moment,
        "solver_moment_nm": solver_moment,
        "cut_force_n": cut_force,
        "solver_force_n": solver_force,
        "xz_moment_ratio": cut_moment / solver_moment,
        "xz_force_ratio": cut_force / solver_force,
        "rho_kg_m3": rho,
        "q_pa": q,
    }


def xz_verdict(moment_ratio: float, force_ratio: float) -> str:
    """FR-340 R2: confirmed when the moment ratio is at least as close to 1 as the force ratio."""
    return "confirmed" if abs(moment_ratio - 1.0) <= abs(force_ratio - 1.0) else "refuted"


def cdo_reading(rigid: float, coupled: float, coupled_first: float | None) -> str:
    """The cause FR-338 names from the three CDo values, or ``undetermined``."""
    if coupled_first is None:
        return "undetermined"
    if rigid != 0.0 and coupled == 0.0 and coupled_first != 0.0:
        return "package_order"
    if rigid != 0.0 and coupled == 0.0 and coupled_first == 0.0:
        return "solver"
    return "undetermined"


def analyze(workspace: Path, rigid_pol: str, coupled_pol: str) -> dict[str, object]:
    """Read both points and print the fields RPT-128's front matter states."""
    rigid_dir = _datapoint(workspace, rigid_pol)
    coupled_dir = _datapoint(workspace, coupled_pol)
    cdo_rigid = float(_loads(rigid_dir).total["CDo"])  # type: ignore[attr-defined]
    cdo_coupled = float(_loads(coupled_dir).total["CDo"])  # type: ignore[attr-defined]
    first = coupled_dir / CDO_FIRST
    cdo_first = (
        float(_loads(coupled_dir, CDO_FIRST).total["CDo"])  # type: ignore[attr-defined]
        if first.is_file()
        else None
    )
    result: dict[str, object] = {
        "cdo_rigid": cdo_rigid,
        "cdo_coupled": cdo_coupled,
        "cdo_coupled_first": cdo_first,
        "cdo_cause": cdo_reading(cdo_rigid, cdo_coupled, cdo_first),
    }
    for name, folder in (("rigid", rigid_dir), ("coupled", coupled_dir)):
        ratios = xz_ratios(folder)
        ratios["xz_moment_verdict"] = xz_verdict(  # type: ignore[assignment]
            ratios["xz_moment_ratio"], ratios["xz_force_ratio"]
        )
        result[name] = ratios
    print(json.dumps(result, indent=2, default=lambda v: None if v is None else str(v)))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fsi_lq1", description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("build", "plan", "run", "analyze"))
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--exe", default=DEFAULT_EXE, help="the 26.124 executable (build)")
    parser.add_argument("--rigid", default=RIGID_POL, help="the rigid point's POL (analyze)")
    parser.add_argument("--coupled", default=COUPLED_POL, help="the coupled point's POL (analyze)")
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    if args.action == "build":
        build(workspace, args.exe)
        return 0
    if args.action == "analyze":
        analyze(workspace, args.rigid, args.coupled)
        return 0
    return _patched_cli([args.action, str(workspace / MATRIX), "--workspace", str(workspace)])


if __name__ == "__main__":
    sys.exit(main())
