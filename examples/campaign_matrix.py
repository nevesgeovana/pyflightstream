# %% [markdown]
# # A campaign from a run matrix, with workspace pre-flight
#
# This example shows the campaign side of the library end to end,
# without a FlightStream license:
#
# 1. the run matrix as the input format (one row per simulation);
# 2. converting a matrix to the canonical `campaign.toml`;
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
from pyflightstream.cases.matrix import convert_matrix, read_matrix
from pyflightstream.run import plan_campaign
from pyflightstream.script import helpers
from pyflightstream.workspace import CampaignWorkspace

workdir = Path(tempfile.mkdtemp(prefix="pyfs_campaign_"))

# %% [markdown]
# ## 1. The run matrix as input
#
# The run matrix is a pipe-delimited table, one row per simulation:
# aircraft, Reynolds and Mach, the sweep type and values, the
# reference/setup/entry/script codes that resolve against the input
# library, and a free `VAR_NAMES_VALUES` cell. `read_matrix` parses it
# into typed rows; by default only the rows with `RUN = 1` come back.

# %%
_HEADER = (
    "POL|AIRCRAFT|DESCRIPTION|RE|MACH|SWEEP_TYPE|SWEEP_VALUES|REF|SET"
    "|ENTRY|FS_SCRIPT|FS_BUILD|HIDDEN|RUN|VAR_NAMES_VALUES"
)
_ROW_1 = (
    "9001|TestWing|POLAR|4.38|0.1441|AL|0.0,2.0,4.0|003|003|001|003|MANUAL|0|1|FSM_FILE:wing_clean"
)
_ROW_2 = "9002|TestWing|PARKED|3.10|0.0890|AL|0.0|003|002|001|003|MANUAL|0|0|FSM_FILE:wing_clean"
MATRIX = "\n".join([_HEADER, "-" * len(_HEADER), _ROW_1, _ROW_2]) + "\n"
matrix_path = workdir / "campaign.fs"
matrix_path.write_text(MATRIX, encoding="utf-8")

rows = read_matrix(matrix_path)  # active_only=True skips the RUN=0 row
print(f"active matrix rows: {[row.pol for row in rows]}")

# %% [markdown]
# ## 2. Matrix to canonical campaign.toml
#
# `convert_matrix` renders the same rows as a `campaign.toml`, the
# canonical internal form. The `recipes` mapping binds each
# `FS_SCRIPT` code to a `module:function` recipe that emits the script
# for that row.

# %%
campaign_toml = convert_matrix(
    matrix_path,
    name="wing_steady",
    fs_version="26.12",
    fs_exe="C:/FlightStream/26.12/FlightStream.exe",
    recipes={"003": "examples.campaign_matrix:steady"},
)
print("--- campaign.toml (first lines) ---")
print("\n".join(campaign_toml.splitlines()[:8]))

# %% [markdown]
# ## 3. The recipe
#
# A recipe turns one swept point into script emissions. It receives
# the per-point case (with `case.point` filled) and an empty `Script`
# bound to the campaign version; it emits through the curated helpers,
# so every line still passes database validation.


# %%
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
        vorticity_drag_boundaries="all",
        aoa=case.point["alpha"],
        velocity=case.velocity,
    )
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", "loads.txt")
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
    fs_version="26.12",
    fs_exe=sys.executable,
    sims=[
        SimCase(
            sim_id="9001",
            aircraft="TestWing",
            velocity=30.0,
            geometry=str(geometry),
            sweep=SweepAxis(type="alpha", values=[0.0, 2.0, 4.0]),
            recipe="steady",
            outputs=["loads.txt"],
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
# assess=LoadsAssessor("loads.txt"))`. The assessor is required: the
# loop refuses to invent convergence evidence, so you name how each
# point is judged. `resume=True` skips points already in the manifest,
# so a sweep can grow point by point across sessions. The pre-flight
# above is the
# zero-cost rehearsal of exactly that run.
