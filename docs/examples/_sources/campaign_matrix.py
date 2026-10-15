# %% [markdown]
# # A campaign from a run matrix, with workspace pre-flight
#
# This example shows the campaign side of the library end to end,
# without a FlightStream license:
#
# 1. the run matrix as the input format (one row per simulation);
# 2. the matrix as the sole campaign declaration;
# 3. the managed workspace and a zero-solver pre-flight
#    (`plan_campaign`) that builds every script and checks every
#    geometry before any run.
#
# Everything here is pure Python; the only licensed step is the final
# `run_campaign`, shown but not executed.

# %%
"""Campaign from a run matrix, with a workspace pre-flight (no solver)."""

import sys
import tempfile
from pathlib import Path

from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.cases.matrix import read_matrix
from pyflightstream.run import plan_campaign
from pyflightstream.script import helpers
from pyflightstream.workspace import CampaignWorkspace

workdir = Path(tempfile.mkdtemp(prefix="pyfs_campaign_"))

# %% [markdown]
# ## 1. The run matrix as input
#
# The run matrix is a pipe-delimited table, one row per simulation:
# aircraft, the flight condition, the sweep type and values, the
# reference/setup/entry/script codes that resolve against the input
# library, the `WORKFLOW` type, and a free `VAR_NAMES_VALUES` cell.
# `read_matrix` parses it into typed rows; by default only the rows with
# `RUN = 1` come back.
#
# Three things in the header are newer than the format itself.
# `FLIGHT_CONDITION` states the whole flow condition of a row in one
# cell, as comma-separated `KEY:value` pairs from a closed set; it
# REPLACED the `RE` and
# `MACH` columns at 0.9.0, and which quantity the resolver solves for
# follows from which keys are present rather than from which columns are
# mandatory. The cell also says WHICH VARIABLE THE ROW SWEEPS, by
# carrying the word `sweep` where that key's value would be: `ALPHA:sweep`
# below means the values in `SWEEP_VALUES` are incidences, and `BETA:0.0`
# beside it is the sideslip held at every one of them. Exactly one key may
# carry the word, which is why the `SWEEP_TYPE` column that named it a
# second time went at 0.15.0. `WORKFLOW`
# names which workflow builds the row's script, in a column of its own
# so the type never competes with the free `KEY:VALUE` case data;
# `LEGACY` is the workflow every row written before the column existed
# asks for. See docs/upgrading.md for earlier layouts.
# The `REF`, `SET` and `PPROC` codes carry a
# letter naming their kind (`r`, `s`, `p`), so a number mistyped between
# the three columns cannot resolve to another artifact's file.

# %%
_HEADER = (
    "POL|HIDDEN|RUN|AIRCRAFT|CONFIGURATION|DESCRIPTION|FLIGHT_CONDITION|SWEEP_VALUES"
    "|GEOMETRY|REF|SET|PPROC|SYMMETRY|SYMMETRY_LOADS|NCPUS|WALLTIME|FS_BUILD"
    "|WORKFLOW|VAR_NAMES_VALUES"
)
# HIDDEN and RUN come first, straight after POL, so the two cells deciding
# whether a row runs are the first thing read. A column a row does not use
# reads `-`; nothing here is mandatory that was optional before.
_ROW_1 = (
    "9001|0|1|TestWing|-|POLAR|MACH:0.1441, REmi:4.38, ALPHA:sweep, BETA:0.0|0.0,2.0,4.0"
    "|-|r003|s003|p001|-|-|-|-|MANUAL|LEGACY"
    "|FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt / RECIPE: 003"
)
_ROW_2 = (
    "9002|0|0|TestWing|-|PARKED|MACH:0.0890, REmi:3.10, ALPHA:sweep, BETA:0.0|0.0"
    "|-|r003|s002|p001|-|-|-|-|MANUAL|LEGACY"
    "|FSM_FILE:wing_clean / OUTPUTS: loads_{point}.txt / RECIPE: 003"
)
MATRIX = "\n".join([_HEADER, "-" * len(_HEADER), _ROW_1, _ROW_2]) + "\n"
matrix_path = workdir / "campaign.fs"
matrix_path.write_text(MATRIX, encoding="utf-8")

rows = read_matrix(matrix_path)  # active_only=True skips the RUN=0 row
print(f"active matrix rows: {[row.pol for row in rows]}")

# %% [markdown]
# ## 2. The matrix declares the campaign
#
# Plan a workspace matrix through `pyflightstream.run.matrix.plan_matrix`.
# The four paired CLI and API examples live in `examples/using-CLI/` and
# `examples/using-API/`. Campaign-file conversion is removed.
#
# ## 3. The recipe
#
# A recipe turns one swept point into script emissions. It receives
# the per-point case (with `case.point` filled) and an empty `Script`
# bound to the campaign version; it emits through the curated helpers,
# so every line still passes database validation.
#
# READ ONE THING ABOUT `case.geometry` BEFORE YOU COPY THIS RECIPE. The
# recipe below opens `case.geometry`, and there are three routes to that
# field of which only two fill it, which is the whole of what this note
# is for.
#
# Section 4 sets it BY HAND, on a `SimCase` built in Python.
#
# A MATRIX ROW SETS IT with `GEOMETRY: <file name>` in `VAR_NAMES_VALUES`,
# resolved against `inputs/geometries/` the way `REF`, `SET` and `PPROC`
# are (v0.8.1). `resolve_matrix` is what assigns it, for every active row
# THAT NAMES THE KEY; a row naming none leaves the field absent, which is
# the property the whole release rests on. So a recipe of your own
# receives the field exactly as a built-in workflow does, and both
# `plan_matrix` and `run_matrix` go through there.
#


def steady(case: SimCase, script) -> None:
    """Emit the steady one-point script for one matrix row.

    Parameters
    ----------
    case : SimCase
        The per-point case; ``case.point['alpha']`` is the angle of
        attack in degrees for this sweep point.
    script : pyflightstream.script.Script
        Empty script bound to the campaign FlightStream version.
    """
    script.emit("OPEN", case.geometry)
    helpers.free_stream(script)
    helpers.initialize_solver(script)
    helpers.solver_settings(
        script,
        # Every boundary of this clean wing carries a trailing edge, so
        # the vorticity integration applies to all of them. On a mixed
        # geometry, list the lifting boundaries instead: a bluff body on
        # this list reports zero induced drag (SRC-003 p.202), and
        # omitting the argument keeps the solver's pressure integration.
        vorticity_drag_boundaries="all",
        # NANOMETRES, unlike every other length this helper takes.
        # A polished metal skin is a few hundred nm; passing 0.5
        # thinking millimetres would be a half-nanometre surface, and
        # zero states a smooth wall outright (SRC-003 p.341).
        surface_roughness=800.0,
        aoa=case.point["alpha"],
        velocity=case.velocity,
    )
    helpers.start_solver(script)
    # case.outputs carries the declared names with the point rendered
    # in, so what the script exports is what the loop collects, and one
    # sweep point cannot overwrite the evidence of another.
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", case.outputs[0])
    script.emit("CLOSE_FLIGHTSTREAM")


# %% [markdown]
# ## 4. Workspace and pre-flight
#
# The managed workspace owns the campaign folder tree and the run
# manifest. `plan_campaign` is the pre-flight: it resolves every
# recipe, builds every script in dry-run, and checks that every
# geometry file exists, all before a single solver call. A broken
# recipe or a missing mesh surfaces here as a `BLOCKED` point instead
# of failing mid-run.

# %%
geometry = workdir / "wing_clean.fsm"
geometry.write_bytes(b"stand-in geometry for the pre-flight")

campaign = Campaign(
    name="wing_steady",
    fs_version="26.120",
    fs_exe=sys.executable,
    sims=[
        SimCase(
            sim_id="9001",
            aircraft="TestWing",
            velocity=30.0,
            geometry=str(geometry),
            sweep=SweepAxis(type="alpha", values=[0.0, 2.0, 4.0]),
            recipe="steady",
            outputs=["loads_{point}.txt"],
        )
    ],
)

workspace = CampaignWorkspace(workdir / "campaign")
plan = plan_campaign(campaign, workspace, recipes={"steady": steady})
print(f"pre-flight: {plan.summary()}")
for point in plan.points:
    print(f"  {point.run_id}: {point.status.value}")

# %% [markdown]
# ## 5. Running it (licensed)
#
# On a licensed machine the same campaign runs with
# `run_campaign(campaign, LocalExecutor(fs_exe), workspace,
# assess=LoadsAssessor())`. The assessor is required: the
# loop refuses to invent convergence evidence, so you name how each
# point is judged. `resume=True` skips points already in the manifest,
# so a sweep can grow point by point across sessions. The pre-flight
# above is the
# zero-cost rehearsal of exactly that run.
