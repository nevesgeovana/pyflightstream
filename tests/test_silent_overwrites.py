"""Tier 1: the writers that replaced a file without saying so (PFS-2011.02).

Pipeline role: quality gate on the class PYFS-005 records. One point of a
campaign overwrote another's output while the run record listed both
complete; that cost licensed solver time and could have published a
report from one point counted twice. The guard written afterwards covers
the surface where it was found, and three others took a caller-chosen
path with no case and no manifest to key on, so refusing there was a
product decision rather than a transcription of the existing check.

FOUR SURFACES, and each one refuses differently because the SIGNAL is
different in each:

* the two flow-visualization writers end in a plain file write, so the
  signal is that the destination exists;
* ``export_probes`` asks the SOLVER to write, so nothing exists yet at
  script-build time and the signal is that this script already asked for
  that path;
* the coupling driver APPENDS by design, so the signal is neither the
  log's presence nor its absence but the pair: a log with no
  ``state.json`` beside it, which is a previous run's history in a folder
  being reused.

WHAT IS DELIBERATELY OUT. ``script.helpers.export_results`` is a FIFTH
writer of the same shape, the four above being the covered ones, and it
is not covered, because the item names the
probe exports, the two field writers and the coupling driver, and
widening a guard here would put a decision nobody made into the tree.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.exceptions import (
    CommandArgumentError,
    FsiInputError,
    OutputExistsError,
)
from pyflightstream.post.writers import (
    OutputProvenance,
    write_tecplot_points,
    write_vtk_points,
)
from pyflightstream.script import Script, helpers

POINTS = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
FIELDS = {"cp": np.array([0.1, 0.2])}


def _provenance() -> OutputProvenance:
    """The settings record both writers require since PFS-2012.11.

    Built from a real snapshot rather than a stub, so these cases keep
    exercising the writers as a campaign calls them.
    """
    script = Script(version="26.120")
    return OutputProvenance(
        run_id="overwrite/sim_1/a+00.0",
        campaign="overwrite",
        setup=helpers.solver_settings(script, velocity=30.0),
    )


@pytest.mark.parametrize(
    ("writer", "suffix"),
    [(write_vtk_points, ".vtk"), (write_tecplot_points, ".dat")],
)
def test_a_field_writer_refuses_an_existing_destination(writer, suffix, tmp_path):
    """Both writers ended in an unconditional write_text.

    A second call with the same path replaced the first silently, and
    nothing in the record said which content survived.
    """
    destination = tmp_path / f"probes{suffix}"
    writer(destination, POINTS, FIELDS, provenance=_provenance())
    first = destination.read_text(encoding="utf-8")

    with pytest.raises(OutputExistsError, match="already exists"):
        writer(destination, POINTS, FIELDS, provenance=_provenance())
    assert destination.read_text(encoding="utf-8") == first, (
        "a refused write still changed the file"
    )


@pytest.mark.parametrize(
    ("writer", "suffix"),
    [(write_vtk_points, ".vtk"), (write_tecplot_points, ".dat")],
)
def test_a_field_writer_replaces_when_asked_deliberately(writer, suffix, tmp_path):
    """`overwrite=True` is the only way through, and it works.

    A refusal with no way past it is not a guard, it is a removed
    feature: a caller re-running a survey into the same folder has a
    legitimate reason to replace.
    """
    destination = tmp_path / f"probes{suffix}"
    writer(destination, POINTS, FIELDS, provenance=_provenance())
    other = {"cp": np.array([0.9, 0.8])}
    writer(destination, POINTS, other, provenance=_provenance(), overwrite=True)
    assert "9.000000000e-01" in destination.read_text(encoding="utf-8")


def test_the_catalogued_type_keeps_the_handler_a_caller_already_has():
    """FR-39: catalogued, and the standard-library base is kept.

    `except FileExistsError` is what a caller writing a file already has
    around the call, so the new type must not take that away.
    """
    from pyflightstream.exceptions import PyflightstreamError

    assert issubclass(OutputExistsError, PyflightstreamError)
    assert issubclass(OutputExistsError, FileExistsError)


def test_a_script_refuses_to_export_probes_to_one_path_twice():
    """The solver writes one file per path, so the second export wins.

    Nothing existed to check at script-build time, which is why this
    surface needed a register rather than a file test: the script emitted
    two identical lines and the collision happened later, inside the
    solver, with nothing recording it.
    """
    script = Script(version="26.120")
    helpers.export_probes(script, "probes.csv")

    with pytest.raises(CommandArgumentError) as refused:
        helpers.export_probes(script, "probes.csv")

    message = str(refused.value)
    assert "already exports" in message
    assert "export_probes" in message, (
        "the refusal must name the EARLIER call site as well as this one; a message "
        "naming only the second sends the reader to the line they do not need to change"
    )
    assert script.render().count("EXPORT_PROBE_POINTS") == 1


def test_a_script_still_exports_two_different_paths():
    """The control: distinct paths are the ordinary case.

    The second call passes ``update=False`` because UPDATE_PROBE_POINTS
    is an ANALYSIS-phase command and EXPORT_PROBE_POINTS an EXPORT-phase
    one, so refreshing again after an export would run the script
    backwards and the phase order refuses it. That is the real shape of
    the usage this control protects: refresh once, export several times.
    """
    script = Script(version="26.120")
    helpers.export_probes(script, "probes_a.csv")
    helpers.export_probes(script, "probes_b.csv", update=False)
    assert script.render().count("EXPORT_PROBE_POINTS") == 2


def _stage_fsi_run(tmp_path: Path) -> Path:
    """A coupling run folder, staged exactly as the driver tests do."""
    from test_fsi_driver import stage_run, write_loads

    stage_run(tmp_path)
    write_loads(tmp_path, 100)
    return tmp_path


def test_the_coupling_driver_refuses_a_folder_holding_another_runs_log(tmp_path):
    """A log with no state beside it is a previous run's history.

    `_append_log` appends BY DESIGN, so refusing an existing log would
    refuse the normal case: within one run the log is present on every
    call after the first. The signal is the PAIR.
    """
    from pyflightstream.fsi import driver

    run_dir = _stage_fsi_run(tmp_path)
    (run_dir / driver.LOG_FILE).write_text("iteration,phase,residual\n1,1,0.5\n", encoding="utf-8")
    assert not (run_dir / driver.STATE_FILE).is_file()

    with pytest.raises(FsiInputError, match="previous run's convergence history"):
        driver.coupling_step(run_dir)


def test_the_coupling_driver_still_appends_within_one_run(tmp_path):
    """The control, and it is why the signal is not the log's presence.

    After the first call the log exists and `state.json` exists beside
    it, which is the normal case and must keep appending.
    """
    from pyflightstream.fsi import driver

    run_dir = _stage_fsi_run(tmp_path)
    driver.coupling_step(run_dir)
    assert (run_dir / driver.STATE_FILE).is_file()
    assert (run_dir / driver.LOG_FILE).is_file()

    patched = re.sub(
        r"(Current solver iteration number:\s+)\d+",
        r"\g<1>140",
        (run_dir / driver.LOADS_FILE).read_text(encoding="utf-8"),
    )
    (run_dir / driver.LOADS_FILE).write_text(patched, encoding="utf-8")

    driver.coupling_step(run_dir)
    rows = (run_dir / driver.LOG_FILE).read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) >= 3, f"the second call did not append its row: {rows}"


# --- PFS-2029.19.02: the name carries the Mach and the advance ratio ---------------


def test_mach_and_advance_ratio_separate_two_rows(tmp_path):
    """Two rows at the same angles and different Mach, or different J, are two names.

    The collision refusal of FR-33c still fires for two rows identical in
    every rendered field, which the last assertion measures.
    """
    import sys

    from pyflightstream.cases import Campaign, SimCase, SweepAxis
    from pyflightstream.run import PlanStatus, plan_campaign
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate

    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")

    def recipe(case, script):
        script.emit("OPEN", case.geometry)
        script.emit("START_SOLVER")
        script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", case.outputs[0])
        script.emit("CLOSE_FLIGHTSTREAM")

    def case(sim_id, mach, variables=None):
        return SimCase(
            sim_id=sim_id,
            aircraft="WB",
            velocity=68.0,
            mach=mach,
            geometry=str(geometry),
            sweep=SweepAxis(type="alpha", values=[0.0]),
            recipe="steady",
            outputs=["{name}.txt"],
            variables=variables or {},
        )

    def names(*sims):
        campaign = Campaign(
            name="camp", fs_version="26.120", fs_exe=sys.executable, sims=list(sims)
        )
        workspace = CampaignWorkspace(
            tmp_path / "camp", naming=NamingTemplate(point_name=MATRIX_POINT_NAME)
        )
        plan = plan_campaign(campaign, workspace, recipes={"steady": recipe})
        return [(point.status, point.script_name) for point in plan.points]

    two_mach = names(case("3207", 0.2), case("3208", 0.3))
    assert [status for status, _ in two_mach] == [PlanStatus.READY, PlanStatus.READY]
    assert two_mach[0][1] == "POLAR-3207_M20AL+000BE+000.txt"
    assert two_mach[1][1] == "POLAR-3208_M30AL+000BE+000.txt", "the Mach is in the name"
    two_ratios = names(
        case("3224", 0.2, {"ADVANCE_RATIO": "1.3"}), case("3225", 0.2, {"ADVANCE_RATIO": "1.7"})
    )
    assert [name for _, name in two_ratios] == [
        "POLAR-3224_M20AL+000BE+000J+130.txt",
        "POLAR-3225_M20AL+000BE+000J+170.txt",
    ], "the advance ratio is in the name"
    # The control: two points whose every rendered field is the same still
    # collide before anything runs (FR-33c), here a constant output name
    # over a two-point sweep.
    constant = case("3207", 0.2).model_copy(
        update={"sweep": SweepAxis(type="alpha", values=[0.0, 2.0]), "outputs": ["loads.txt"]}
    )
    same = names(constant)
    assert {status for status, _ in same} == {PlanStatus.BLOCKED}, (
        "two rows identical in every rendered field still collide (FR-33c)"
    )
