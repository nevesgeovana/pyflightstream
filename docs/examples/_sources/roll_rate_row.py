# %% [markdown]
# # A row that rolls: the free stream turned by a body rate
#
# A row states ONE body rate in its `FLIGHT_CONDITION`, `roll_rate`,
# `pitch_rate` or `yaw_rate`, in degrees per second and in flight-mechanics
# signs, and the script turns the free stream about the moment point of the
# row's reference at that rate:
#
# ```
# SET_FREESTREAM ROTATION <frame of the moment point> <axis> <rev/min>
# ```
#
# Which axis of the mesh each rate turns about belongs to the configuration,
# so the reference artifact declares it in `[body_axes]`. The SIGN of the
# emitted rotation is the sign of the body axis in the geometry's frame (x
# aft, y right, z up, against body axes forward, right, down): p = -omega_x,
# q = +omega_y, r = -omega_z. The solver's sense was measured on FlightStream
# 26.124, pitch in RPT-052 and roll and yaw in RPT-060. See the upgrade
# guidance for historical roll and yaw sign corrections.
# Only roll=X, pitch=Y, yaw=Z is supported. Permuted mappings are refused:
# RPT-052 and RPT-060 did not measure their signs.
#
# This example sweeps the roll rate over one row and prints the free-stream
# line each point's script carries, without a solver.

# %%
"""A row sweeping a roll rate: the free-stream rotation each point emits, no solver."""

import tempfile
from pathlib import Path

from pyflightstream.cases import case_at_point
from pyflightstream.cases.workflows import build_script, workflow_registry
from pyflightstream.qa.geometry import WingSpec, wing_triangles
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.matrix import resolve_matrix

BUILD = "26.124"  # the build the roll and yaw sense was measured on
ROLL_RATES_DEG_S = [-40.0, 0.0, 40.0]

workdir = Path(tempfile.mkdtemp(prefix="pyfs_roll_rate_"))
workspace = CampaignWorkspace.init(workdir / "roll_study")
inputs = workspace.inputs_dir
print(f"workspace: {workspace.root}")

# %% [markdown]
# ## 1. The wing and its reference
#
# The synthetic NACA 0012 wing of `pyflightstream.qa.geometry`, chord 1 m and
# span 8 m, written as an OBJ in metres with its surface named `Wing`, and a
# sidecar stating that unit and marking the trailing edge by the solver's
# detection (written, so applied). The reference places the moment point at
# the quarter chord and declares the body axes: the wing flies along x, so the
# roll rate turns about X.

# %%
vertices = wing_triangles(
    WingSpec(naca="0012", chord_m=1.0, span_m=8.0, n_chord=12, n_span=16)
).reshape(-1, 3)
with (inputs / "geometries" / "wing.obj").open("w", encoding="utf-8") as obj:
    obj.write("o Wing\n")
    obj.writelines(f"v {x:.8f} {y:.8f} {z:.8f}\n" for x, y, z in vertices)
    obj.writelines(f"f {i + 1} {i + 2} {i + 3}\n" for i in range(0, len(vertices), 3))
(inputs / "geometries" / "wing.boundaries.toml").write_text(
    'boundaries = ["Wing"]\n\n[import]\nunits = "METER"\n\n[trailing_edges]\ndetect = "auto"\n',
    encoding="utf-8",
)
(inputs / "references" / "r001.toml").write_text(
    "area_m2 = 8.0\nchord_m = 1.0\nspan_m = 8.0\n\n"
    "[moment_point]\nx_m = 0.25\ny_m = 0.0\nz_m = 0.0\n\n"
    '[body_axes]\nroll = "X"\npitch = "Y"\nyaw = "Z"\n',
    encoding="utf-8",
)
(inputs / "setups" / "s001.toml").write_text("NITER = 300\n", encoding="utf-8")
(inputs / "pproc" / "p001.toml").write_text('[groups]\n"1" = "Wing"\n', encoding="utf-8")
# The installation's path is machine configuration; the plan binds the build
# without launching it, so a placeholder serves here.
(inputs / "executables.toml").write_text(f'"{BUILD}" = "FlightStream.exe"\n', encoding="utf-8")

# %% [markdown]
# ## 2. The row
#
# The rate is a key of `FLIGHT_CONDITION` like any other, so the row can
# sweep it: `roll_rate:sweep` with `SWEEP_VALUES` in deg/s, at a held angle of
# attack. A row states one non-zero rate at a time; two would be composed
# into an axis the row does not write, and are refused.

# %%
HEADER = (
    "POL | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION | FLIGHT_CONDITION "
    "| SWEEP_VALUES | GEOMETRY | REF | SET | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS "
    "| WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES"
)
ROW = (
    "2001 | 0 | 1 | Wing | - | roll_damping "
    "| MACH:0.1, REmi:2.3, ALPHA:4.0, roll_rate:sweep "
    f"| {','.join(str(rate) for rate in ROLL_RATES_DEG_S)} | wing.obj | r001 | s001 | p001 "
    f"| NONE | - | - | - | {BUILD} | steady |"
)
matrix = workspace.root / "roll.fs"
matrix.write_text("\n".join([HEADER, "-" * len(HEADER), ROW]) + "\n", encoding="utf-8")

plan = plan_matrix(
    matrix, workspace, name="roll_study", recipes={}, recipe_registry=workflow_registry()
)
print(plan.summary())
if plan.blocked:
    raise AssertionError(f"the plan blocked a point: {[point.error for point in plan.blocked]}")
for point in plan.points:
    print(f"  {point.run_id}")

# %% [markdown]
# ## 3. The free-stream line of each point
#
# A positive roll rate is right wing down. About the geometry's x axis, which
# points aft, that is a NEGATIVE rotation, so +40 deg/s writes about -6.67
# rev/min about X, and -40 deg/s the opposite; a zero rate writes the constant
# free stream. The check below holds the example to that, so it fails rather
# than prints a wrong sign.

# %%
resolved = resolve_matrix(matrix, workspace, name="roll_study", fs_version=BUILD, recipes={})
(case,) = resolved.campaign.sims
print(f"{'roll_rate [deg/s]':>18}  free stream")
for rate in case.sweep.values:
    if isinstance(rate, tuple):
        raise AssertionError("this example requires a scalar roll-rate sweep")
    script = Script(BUILD)
    build_script(case_at_point(case, {case.sweep.type: rate}), script)
    line = next(line for line in script.render().splitlines() if line.startswith("SET_FREESTREAM"))
    print(f"{rate:>18.1f}  {line}")
    words = line.split()
    if rate == 0.0:
        if words[1:] != ["CONSTANT"]:
            raise AssertionError(f"a zero rate wrote {line!r}")
        continue
    rev_per_min = float(words[4])
    if words[3] != "X" or abs(rev_per_min + rate * 60.0 / 360.0) > 1e-9:
        raise AssertionError(
            f"roll_rate {rate:+.1f} deg/s wrote {line!r}; flight mechanics asks a rotation "
            f"of {-rate * 60.0 / 360.0:+.4f} rev/min about X"
        )

# %% [markdown]
# ## 4. Running it (licensed)
#
# On a licensed machine with the build registered, `pyfs-matrix plan roll.fs`
# and then `pyfs-matrix run roll.fs` from the workspace root. Each point's
# name carries its rate (`P` for roll), so the three points of the row read
# as one roll-rate sweep of the same wing at the same angle of attack.
