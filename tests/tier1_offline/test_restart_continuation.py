"""GOAL-020 item 4, FR-96: RESTART continues a march the wall clock stopped.

THE MEASURED FACT the whole item rests on: the solver DOES resume an unsteady
march from a saved file, picking up where it stopped and running the new
iteration count it is given. Until that was known, the release before this one
REFUSED the key by name, because building either of the two possible features
without knowing which one the solver implements would have built one of them
wrong.

What these tests hold is the part a grep cannot see. That the refusal is gone
is one line. That a continuation OPENS THE SAVED FILE WITH THE STATE LOADED,
and marches the REMAINDER rather than the row's original count, is the
difference between continuing and starting over with a better initial
condition, and a user cannot see that difference in the numbers afterwards.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from pyflightstream.cases import CampaignConfigError, SimCase, SweepAxis
from pyflightstream.cases.workflows import (
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    RESTART_VARIABLE,
    WORKFLOW_KEY,
    build_script,
    continuation_of,
    parse_restart,
    restart_iterations,
)
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace

SAVED = "datapoints/DP-a+00.0/archive/20260914-010000/point.fsm"


def _continuing_case(restart: str, **variables) -> SimCase:
    return SimCase(
        sim_id="9001",
        aircraft="Rig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=["loads_a+00.0.txt", "run_a+00.0_log.txt"],
        variables={
            WORKFLOW_KEY: "unsteady",
            "VELOCITY": "30.0",
            "TIME_ITERATIONS": "400",
            "DELTA_TIME": "0.001",
            RESTART_VARIABLE: restart,
            **variables,
        },
        point={"alpha": 0.0},
    )


# ------------------------------------------------------- the three forms live


@pytest.mark.parametrize(
    "written",
    ["{FINISH_PENDING}", "{ADDITIONAL_ITERS=120}", "{ADDITIONAL_REVS=2}"],
)
def test_goal020_restart_all_three_forms_still_parse(written):
    """The parser was built a release before the builder; all three forms land at 0.18.0."""
    request = parse_restart(_continuing_case(written))
    assert request is not None


def test_goal020_restart_finish_pending_subtracts_what_the_run_reached():
    """FINISH_PENDING is the remainder, which is the whole reason the key exists."""
    request = parse_restart(_continuing_case("{FINISH_PENDING}"))
    record = {"export_window": {"time_iterations": 400}, "stopped_at": {"step": 250}}
    assert restart_iterations(request, record) == 150


def test_goal020_restart_additional_iters_is_the_count_it_states():
    request = parse_restart(_continuing_case("{ADDITIONAL_ITERS=120}"))
    assert restart_iterations(request, {"export_window": {}, "stopped_at": {"step": 250}}) == 120


def test_goal020_restart_additional_revs_becomes_steps_through_the_azimuthal_step():
    request = parse_restart(_continuing_case("{ADDITIONAL_REVS=2}"))
    record = {"export_window": {"step_deg": 10.0}, "stopped_at": {"step": 250}}
    assert restart_iterations(request, record) == 72


def test_goal020_restart_finish_pending_refuses_a_record_that_cannot_say():
    """A record that does not say what the row asked for has nothing to subtract from."""
    request = parse_restart(_continuing_case("{FINISH_PENDING}"))
    with pytest.raises(CampaignConfigError) as refused:
        restart_iterations(request, {"export_window": {}, "stopped_at": {"step": 250}})
    assert "does not say how many time steps" in str(refused.value)


# ------------------------------------------------------------- the build path


def test_goal020_restart_the_refusal_that_named_0_18_0_is_gone():
    """0.18.0 is the release that REMOVES the refusal, not one that keeps it."""
    import pyflightstream.cases.workflows as workflows

    assert not hasattr(workflows, "_refuse_a_restart_that_nothing_runs")


def test_goal020_restart_opens_the_saved_simulation_with_the_state_loaded():
    """ENABLE, always. A DISABLE here would silently march the row from a mesh again."""
    case = _continuing_case(
        "{ADDITIONAL_ITERS=120}",
        **{RESTART_FROM_VARIABLE: SAVED, RESTART_ITERATIONS_VARIABLE: "120"},
    )
    script = Script("26.123")
    build_script(case, script)
    text = script.render()
    assert "OPEN" in text
    assert SAVED in text
    open_block = text[text.index("OPEN") : text.index("OPEN") + 200]
    assert "ENABLE" in open_block, "a continuation that does not load the stored state is not one"


def test_goal020_restart_marches_the_remainder_and_not_the_rows_original_count():
    """The row asks for 400; the continuation owes 120, and the script says 120."""
    case = _continuing_case(
        "{ADDITIONAL_ITERS=120}",
        **{RESTART_FROM_VARIABLE: SAVED, RESTART_ITERATIONS_VARIABLE: "120"},
    )
    script = Script("26.123")
    build_script(case, script)
    text = script.render()
    assert "120" in text
    # The row's own count must NOT be what the solver is told to march.
    assert "\n400\n" not in text


def test_goal020_restart_imports_no_mesh_and_declares_no_boundaries():
    """Everything the saved file carries is a line this script does not emit."""
    case = _continuing_case(
        "{ADDITIONAL_ITERS=120}",
        **{RESTART_FROM_VARIABLE: SAVED, RESTART_ITERATIONS_VARIABLE: "120"},
    )
    script = Script("26.123")
    build_script(case, script)
    text = script.render()
    assert "IMPORT" not in text
    assert "CREATE_NEW_COORDINATE_SYSTEM" not in text


def test_goal020_restart_refuses_a_row_with_nothing_to_continue():
    """A continuation needs a recorded run that STOPPED; the row alone cannot say which."""
    case = _continuing_case("{ADDITIONAL_ITERS=120}")
    with pytest.raises(CampaignConfigError) as refused:
        continuation_of(case)
    message = str(refused.value)
    assert "nothing resolved the run it continues" in message
    assert "recorded run that STOPPED" in message


def test_goal020_restart_an_ordinary_row_is_not_a_continuation():
    case = SimCase(
        sim_id="9002",
        aircraft="Rig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=["loads_a+00.0.txt"],
        variables={WORKFLOW_KEY: "unsteady", "VELOCITY": "30.0", "TIME_ITERATIONS": "400"},
        point={"alpha": 0.0},
    )
    assert continuation_of(case) is None


# --------------------------------------------------------- the archive it owes


def test_goal020_restart_archives_what_it_replaces_under_a_day_and_hour_stamp(tmp_path):
    """HER DECISION, and the clause that decided the shape: there can be more than one restart."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    folder = workspace.sim_dir("9001") / "datapoints" / "DP-a+00.0"
    folder.mkdir(parents=True)
    (folder / "loads.txt").write_text("the stopped run", encoding="utf-8")

    first = workspace.archive_datapoint(
        "9001", {"alpha": 0.0}, stamp=datetime(2026, 9, 14, 1, 0, 0)
    )
    assert first is not None
    assert first.name == "20260914-010000"
    assert (first / "loads.txt").read_text(encoding="utf-8") == "the stopped run"
    assert [p.name for p in folder.iterdir()] == ["archive"]

    # A SECOND CONTINUATION, which is why the stamp is there at all.
    (folder / "loads.txt").write_text("the first continuation", encoding="utf-8")
    second = workspace.archive_datapoint(
        "9001", {"alpha": 0.0}, stamp=datetime(2026, 9, 14, 2, 0, 0)
    )
    assert second is not None and second.name == "20260914-020000"
    assert (second / "loads.txt").read_text(encoding="utf-8") == "the first continuation"
    # BOTH are still there, in order, which a flat folder could not have done.
    stamps = sorted(p.name for p in (folder / "archive").iterdir())
    assert stamps == ["20260914-010000", "20260914-020000"]


def test_goal020_restart_archiving_nothing_is_not_an_error(tmp_path):
    """A first run of a point has no previous outputs; that is ordinary, not a mistake."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    assert workspace.archive_datapoint("9001", {"alpha": 0.0}) is None


# --- a row may not forge the two facts the run path resolves ------------------


def _matrix_with(tmp_path, extra: str):
    """One unsteady-rotor row, with whatever free-variable text is given."""
    header = (
        "POL  | HIDDEN | RUN | AIRCRAFT | CONFIGURATION | DESCRIPTION | FLIGHT_CONDITION | "
        "SWEEP_VALUES | GEOMETRY | REF | SET | PPROC | SYMMETRY | SYMMETRY_LOADS | NCPUS | "
        "WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES\n"
    )
    row = (
        "9001 |    0   |  1  | W | - | ROW | MACH:0.1, REmi:2.3, ALPHA:sweep | 0.0 | g.fsm | "
        "r001 | s001 | p001 | NONE | false | 8 | - | 26.123 | unsteady_rotor | "
        "DELTA_THETA: 30 / REVOLUTIONS: 1.0 / CLOCK_MOTION: P / "
        "MOTIONS: {MOVING_BC_ALIAS: P / RPM: 800}" + extra + "\n"
    )
    path = tmp_path / "m.fs"
    path.write_text(header + "-" * 80 + "\n" + row, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "cell",
    [
        " / RESTART_FROM: stolen.fsm / RESTART_ITERATIONS: 3",
        " / RESTART_FROM: stolen.fsm",
        " / RESTART_ITERATIONS: 3",
    ],
)
def test_goal020_restart_a_row_may_not_state_the_packages_continuation_keys(tmp_path, cell):
    """A row writing RESTART_FROM or RESTART_ITERATIONS is refused at plan time.

    THE DEFECT, found by the architect lens of the 0.18.0 release round: the
    two names travel in the same free-variable namespace a user's cell writes
    into, so a row stating them reached the builder with the continuation
    facts already present and built one DIRECTLY, skipping the resolution
    that checks a recorded run exists, that it stopped in a state a
    continuation may resume, and that its outputs are archived before they
    are replaced. The continuation then overwrote the stopped run in place
    under its own run id, which is the collision the stamp exists to prevent.

    Each key is refused ALONE as well as together, because either one on its
    own is enough to make the row's continuation facts partly the user's.
    """
    from pyflightstream.cases.matrix import MatrixError, read_matrix

    with pytest.raises(MatrixError) as caught:
        read_matrix(_matrix_with(tmp_path, cell))
    message = str(caught.value)
    assert "set by the package and not by a row" in message, message
    # THE REFUSAL NAMES THE FIX, and the fix is the user's actual intent.
    assert "RESTART: {FINISH_PENDING}" in message, message


@pytest.mark.parametrize(
    "cell", ["", " / RESTART: {FINISH_PENDING}", " / RESTART: {ADDITIONAL_ITERS=40}"]
)
def test_goal020_restart_the_refusal_does_not_reach_a_row_that_asks_properly(tmp_path, cell):
    """THE CONTROL. A refusal that also refused the legitimate row would be a feature removed.

    Asserted over an ordinary row AND over both spellings a continuation is
    actually written in, because a guard shown only to refuse has not been
    shown to discriminate.
    """
    from pyflightstream.cases.matrix import read_matrix

    rows = read_matrix(_matrix_with(tmp_path, cell))
    assert len(rows) == 1


def _stopped_record():
    """One WALLTIME_REACHED record that collected a saved simulation.

    The fields are the ones `resolve_continuation` actually reads: the sim
    id, a run id ending in the point tag, a continuable status, the outputs
    carrying a `.fsm`, and the export window the remainder is subtracted
    from. Everything else is the minimum a RunRecord requires.
    """
    from pyflightstream.workspace import RunRecord, RunStatus

    return RunRecord(
        run_id="camp/sim_9001/a+00.0",
        sim_id="9001",
        point={"alpha": 0.0},
        status=RunStatus.WALLTIME_REACHED,
        matrix_stem="matriz",
        fs_version_requested="26.123",
        fs_build="8112026",
        fs_exe="C:/builds/26123/FlightStream.exe",
        fs_exe_sha256="e" * 64,
        package_version="0.18.0.dev0",
        package_commit="ff98166",
        package_dirty=False,
        script_path="scripts/point.fs",
        script_sha256="c" * 64,
        inputs_sha256={"10_WING.fsm": "a" * 64},
        raw_flag=False,
        pproc="p001",
        description="STOPPED_BY_THE_CLOCK",
        mach=0.15,
        reference={"SREF": 50.0, "CREF": 2.5, "BREF": 20.0, "XMOM": 9.0},
        outputs=["datapoints/DP-a+00.0/state.fsm", "datapoints/DP-a+00.0/loads.txt"],
        export_window={"time_iterations": 400},
        stopped_at={"step": 250},
    )


# --- the pre-flight rehearses a continuation instead of blocking it ------------


def test_goal020_restart_a_continuation_row_resolves_at_plan_time(tmp_path):
    """`plan` resolves the continuation, so a RESTART row is not reported BLOCKED.

    THE DEFECT THIS IS ON, found by the architect lens of the 0.18.0 release
    round, which said plainly that it could not settle it by reading and
    named the command. `_plan_point` built the script from the row's own
    variables with nothing resolved, so the builder met a RESTART row with no
    saved file and no step count, raised, and the point was reported BLOCKED.
    Since v0.17.0 a run REQUIRES a plan, so the release's headline feature was
    unreachable through its own documented sequence.

    ASSERTED ON THE SEAM AND NOT ON THE PARSER. Every other test in this file
    hands the builder a case with the two facts already injected, which is the
    channel the run path uses; none of them crosses the seam between resolving
    and building, and the seam is where this lived.
    """
    from pyflightstream.run import resolve_continuation

    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    saved = workspace.sim_dir("9001") / "datapoints" / "DP-a+00.0"
    saved.mkdir(parents=True)
    (saved / "state.fsm").write_text("a stopped march", encoding="utf-8")
    workspace.append_record(_stopped_record())
    case = _continuing_case("{FINISH_PENDING}")
    resolved = resolve_continuation(workspace, case, {"alpha": 0.0}, run_id="camp/sim_9001/a+00.0")
    assert resolved is not None, (
        "the row states RESTART and a continuable record exists, so the pre-flight has "
        "everything it needs; None here is what made the plan block"
    )
    assert str(resolved["saved"]).endswith("state.fsm")
    assert int(resolved["iterations"]) > 0


def test_goal020_restart_finish_pending_refuses_a_record_that_never_says_where_it_stopped():
    """An absent `stopped_at` is REFUSED, not read as zero.

    THE DEFECT, measured by the independent lens of the 0.18.0 release round
    on 2026-09-14 and severe because it is silent and costs a licensed seat.
    `stopped_at` is written by the WALL CLOCK. `CONTINUABLE` also admits
    COMPLETED_MAX_ITER, which never carries it, so a row that asked for 400
    steps and reached all 400 came back owing 400 MORE: the run path printed
    "continuing for 400 more step(s)" and re-marched the entire history from
    a saved state that already held it.

    It is reachable from ONE CELL: a row whose post-processing artifact turns
    the log off has no residual history, so an unsteady run is recorded at
    its iteration limit rather than as converged.
    """
    request = parse_restart(_continuing_case("{FINISH_PENDING}"))
    with pytest.raises(CampaignConfigError) as refused:
        restart_iterations(request, {"export_window": {"time_iterations": 400}})
    message = str(refused.value)
    assert "does not say where it stopped" in message, message
    # THE REFUSAL NAMES THE TWO FORMS THAT WORK, because the user's row is
    # legitimate and only its FORM is wrong for this record.
    assert "ADDITIONAL_ITERS" in message and "ADDITIONAL_REVS" in message, message


def test_goal020_restart_a_zero_stopped_at_is_a_measurement_and_not_an_absence():
    """A run the clock stopped at step ZERO owes the whole march, and that is not the same thing.

    THE CONTROL for the refusal above, and it is the case a careless fix
    breaks: `stopped_at: {step: 0}` is a RECORDED zero, so the continuation
    legitimately owes every step. A guard written as `if not reached` would
    refuse it and a guard written as `reached or 0` would accept an absence;
    the distinction is None against 0 and this is what holds it.
    """
    request = parse_restart(_continuing_case("{FINISH_PENDING}"))
    owed = restart_iterations(
        request, {"export_window": {"time_iterations": 400}, "stopped_at": {"step": 0}}
    )
    assert owed == 400, owed
