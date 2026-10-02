"""The licensed run LQ5 of 0.34.0: the wake a rotor keeps, and the speed it convects at.

Package WAKE; the report it will feed is RPT-130 (FR-321 R3,
FR-324), owed by a commit after the 0.34.0 release, when this run is made.
One synthetic propeller (the tier-3 ``31_BLADE_PHY`` blade of the public
shape law of :mod:`tests.tier3_licensed.recipes`, tip radius
1.8288 m, one blade meshed, six periodic copies), a blades-only wheel, at
the advance ratio J = 0.8, a step of 5 degrees and 4 revolutions, on
FlightStream 26.124, far field 5 layers, one solver instance at a time:

* ``9501``, the wake termination left to the package's default (4 rotor
  radii, FR-321 R4) and the wake end plane left at ``DEFAULT``: the control,
  where a blades-only wheel's default plane was measured at x/R = 2.08
  (RPT-137 section 7) and may cut the wake before 4 R;
* ``9502``, the same row with the wake end plane moved to x = 8 R
  (``wake_termination_x_m``, FR-324): the run whose wake reaches L.

At J = 0.8 a length of 4 R needs L / (2 J) = 2.5 revolutions at V_inf, so 4
revolutions reach it with margin; the default converts to
ceil(4 R Omega / (V_inf dtheta)) = 180 steps at 5 degrees.

WHAT IS MEASURED. Two probe tables, in the hub's static frame, laid along the
rotor axis:

* the TIP line, 71 points from x = -1 R to 6 R every 0.1 R at r = 0.9 R,
  ``VX`` and ``VZ``: the tip vortex passes each point once per blade. The
  phase of the blade-passing harmonic (6 per revolution) of ``VZ`` over the
  last revolution falls linearly with x, by ``omega_b / V_ax``, so its slope
  is the axial convection speed of the tip vortex, ``V_ax = omega_b / |slope|``,
  read from 0.3 R to where the harmonic's amplitude falls below a fifth of
  its level near the disc. The same amplitude says where the wake ends.
  The 0.1 R spacing keeps the phase step between neighbours below pi for any
  V_ax above 0.75 V_inf, so the unwrapped slope is not aliased there.
* the SLIPSTREAM line, 15 points from x = -1 R to 6 R every 0.5 R at
  r = 0.5 R, ``VX``: the time-mean axial velocity inside the slipstream, so
  ``(VX - V_inf) / V_inf`` is the induced velocity measured on the run.

:func:`analyze` prints, nondimensionally, ``V_ax / V_inf`` of each row, the
measured induced velocity ratio near the disc and far behind it, the
momentum-theory ratio ``(V_inf + v_i) / V_inf`` from the rotor table's
``CT``, the wake end x/R of each row, and the solver log's lines naming the
wake termination, then the reading RPT-130 will state: V_ax closer to V_inf,
or closer to V_inf + v_i (FR-321 R3). It decides nothing on its own: RPT-130
will, and will state its conditions.

Commands (from the worktree root, with the package's Python)::

    python -m tests.tier3_licensed.wake_lq5 build <workspace>
    python -m tests.tier3_licensed.wake_lq5 plan  <workspace>
    python -m tests.tier3_licensed.wake_lq5 run   <workspace>
    python -m tests.tier3_licensed.wake_lq5 analyze <workspace>

``build`` reads the 26.124 executable from the tier-3
``inputs/executables.local.toml`` (gitignored) unless ``--exe`` names one;
nothing in this file names a machine path.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
#: The control (DEFAULT plane) and the run whose plane is moved to 8 R.
DEFAULT_POL, MOVED_POL = "9501", "9502"
MATRIX = "lq5_wake.fs"
GEOMETRY = "31_BLADE_PHY"
BUILD = "26.124"
ALIAS = "PROP"
#: The wheel: tip radius, blades (one meshed, five periodic copies), advance ratio.
R_M, BLADES, J = 1.8288, 6, 0.8
#: PHY-05's free stream: 49 m/s at sea-level density.
V_INF, RHO = 49.0, 1.225
#: The clock: 5 degrees a step, 4 revolutions.
DELTA_THETA_DEG, REVOLUTIONS = 5.0, 4.0
STEPS_PER_REV = round(360.0 / DELTA_THETA_DEG)
#: The moved plane, in rotor radii downstream of the hub at x = 0.
MOVED_PLANE_R = 8.0
#: The tip line: x/R from -1 to 6 every 0.1, at r = 0.9 R; the slipstream line every 0.5 R.
TIP_POINTS, TIP_R = 71, 0.9
SLIP_POINTS, SLIP_R = 15, 0.5
X_START_R, X_END_R = -1.0, 6.0
#: The harmonic amplitude below which a point is outside the wake, as a share of its
#: level near the disc.
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


def _local_executable() -> Path:
    """This machine's installation of :data:`BUILD`, the way the tier-3 rows resolve it."""
    from tests.tier3_licensed.prepare import executable

    return Path(executable(BUILD))


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


# --- the analysis ---------------------------------------------------------------


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


def _one(workspace: Path, pattern: str) -> Path | None:
    found = sorted((workspace / "post").rglob(pattern))
    return found[-1] if found else None


def _rotor_ct(workspace: Path, pol: str) -> float | None:
    table = _one(workspace, f"P{pol}-{ALIAS}_rotor.csv")
    if table is None:
        return None
    with table.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return _floats(rows[-1], f"CT_{ALIAS}") if rows else None


def _log_lines(workspace: Path, pol: str) -> list[str]:
    """The lines of the point's collected solver log that name the wake termination."""
    lines = []
    for log in sorted(workspace.rglob(f"P{pol}*_log.txt")):
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.search(r"(?i)wake.*terminat|terminat.*wake|trefftz", line):
                lines.append(line.strip())
    return lines[:12]


def analyze(workspace: Path) -> int:
    """Print the nondimensional readings RPT-130 will state, per row."""
    print(f"LQ5 at J = {J}, {DELTA_THETA_DEG:g} degrees a step, {REVOLUTIONS:g} revolutions")
    for pol, label in (
        (DEFAULT_POL, "DEFAULT plane"),
        (MOVED_POL, f"plane at {MOVED_PLANE_R:g} R"),
    ):
        table = _one(workspace, f"P{pol}*_probes.csv")
        print(f"\nrow {pol} ({label}):")
        if table is None:
            print("  no probes table under post/: run, then post")
            continue
        vz, vx = probe_histories(table, "VZ"), probe_histories(table, "VX")
        first = min(vz) if vz else 1
        ratio, end = convection_speed(tip_line(vz, first))
        print(f"  tip vortex V_ax / V_inf = {ratio if ratio is None else round(ratio, 4)}")
        print(f"  wake end (blade-passing amplitude above {WAKE_SHARE:g} of its level) x/R = {end}")
        slip_first = first + TIP_POINTS
        for x, induced in slipstream(vx, slip_first):
            if x in (0.0, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0):
                print(
                    f"  slipstream r/R = {SLIP_R}, x/R = {x:g}: "
                    f"(VX - V_inf) / V_inf = {induced:.4f}"
                )
        ct = _rotor_ct(workspace, pol)
        if ct is None:
            print(f"  no rotor table CT_{ALIAS}")
        else:
            momentum = momentum_ratio(ct)
            print(f"  CT_{ALIAS} = {ct:.5f}; momentum (V_inf + v_i) / V_inf = {momentum:.4f}")
            if ratio is not None:
                nearer = "V_inf" if abs(ratio - 1.0) <= abs(ratio - momentum) else "V_inf + v_i"
                print(f"  V_ax is closer to {nearer} (FR-321 R3)")
        for line in _log_lines(workspace, pol):
            print(f"  log: {line}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wake_lq5", description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("build", "plan", "run", "analyze"))
    parser.add_argument("workspace", type=Path)
    parser.add_argument(
        "--exe",
        default=None,
        help="the 26.124 executable (build); default: this machine's installation as the "
        "tier-3 inputs/executables.local.toml names it",
    )
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    if args.action == "build":
        build(workspace, args.exe or str(_local_executable()))
        return 0
    if args.action == "analyze":
        return analyze(workspace)
    from pyflightstream.run import cli

    return cli.main([args.action, str(workspace / MATRIX), "--workspace", str(workspace)])


if __name__ == "__main__":
    sys.exit(main())
