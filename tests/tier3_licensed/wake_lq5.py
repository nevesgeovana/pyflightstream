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
import re
import sys
from pathlib import Path

from tests.support_tier3 import (
    _MATRIX_HEADER as _MATRIX_HEADER,
)
from tests.support_tier3 import (
    _PPROC as _PPROC,
)
from tests.support_tier3 import (
    _REFERENCE as _REFERENCE,
)
from tests.support_tier3 import (
    _SETUP as _SETUP,
)
from tests.support_tier3 import (
    ALIAS as ALIAS,
)
from tests.support_tier3 import (
    BLADES as BLADES,
)
from tests.support_tier3 import (
    BUILD as BUILD,
)
from tests.support_tier3 import (
    DEFAULT_POL as DEFAULT_POL,
)
from tests.support_tier3 import (
    DELTA_THETA_DEG as DELTA_THETA_DEG,
)
from tests.support_tier3 import (
    GEOMETRY as GEOMETRY,
)
from tests.support_tier3 import HERE as HERE
from tests.support_tier3 import (
    MATRIX as MATRIX,
)
from tests.support_tier3 import (
    MOVED_PLANE_R as MOVED_PLANE_R,
)
from tests.support_tier3 import (
    MOVED_POL as MOVED_POL,
)
from tests.support_tier3 import (
    R_M as R_M,
)
from tests.support_tier3 import (
    REVOLUTIONS as REVOLUTIONS,
)
from tests.support_tier3 import (
    RHO as RHO,
)
from tests.support_tier3 import (
    SLIP_POINTS as SLIP_POINTS,
)
from tests.support_tier3 import (
    SLIP_R as SLIP_R,
)
from tests.support_tier3 import (
    STEPS_PER_REV as STEPS_PER_REV,
)
from tests.support_tier3 import (
    TIP_POINTS as TIP_POINTS,
)
from tests.support_tier3 import (
    TIP_R as TIP_R,
)
from tests.support_tier3 import (
    V_INF as V_INF,
)
from tests.support_tier3 import (
    WAKE_SHARE as WAKE_SHARE,
)
from tests.support_tier3 import (
    X_END_R as X_END_R,
)
from tests.support_tier3 import (
    X_START_R as X_START_R,
)
from tests.support_tier3 import (
    J as J,
)
from tests.support_tier3 import (
    _column as _column,
)
from tests.support_tier3 import (
    _floats as _floats,
)
from tests.support_tier3 import (
    _row_variables as _row_variables,
)
from tests.support_tier3 import (
    build as build,
)
from tests.support_tier3 import (
    convection_speed as convection_speed,
)
from tests.support_tier3 import (
    harmonic as harmonic,
)
from tests.support_tier3 import (
    matrix_text as matrix_text,
)
from tests.support_tier3 import (
    momentum_ratio as momentum_ratio,
)
from tests.support_tier3 import (
    probe_histories as probe_histories,
)
from tests.support_tier3 import (
    slipstream as slipstream,
)
from tests.support_tier3 import (
    tip_line as tip_line,
)

#: The control (DEFAULT plane) and the run whose plane is moved to 8 R.
#: The wheel: tip radius, blades (one meshed, five periodic copies), advance ratio.
#: PHY-05's free stream: 49 m/s at sea-level density.
#: The clock: 5 degrees a step, 4 revolutions.
#: The moved plane, in rotor radii downstream of the hub at x = 0.
#: The tip line: x/R from -1 to 6 every 0.1, at r = 0.9 R; the slipstream line every 0.5 R.
#: The harmonic amplitude below which a point is outside the wake, as a share of its
#: level near the disc.


def _local_executable() -> Path:
    """This machine's installation of :data:`BUILD`, the way the tier-3 rows resolve it."""
    from tests.tier3_licensed.prepare import executable

    return Path(executable(BUILD))


# --- the analysis ---------------------------------------------------------------


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
