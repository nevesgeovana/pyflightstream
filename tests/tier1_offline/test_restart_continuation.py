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

import json
import shutil
import warnings
from datetime import datetime
from pathlib import Path

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
    workflow_registry,
)
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.post.products import plots_table_series, write_campaign_products
from pyflightstream.run import PlanStatus
from pyflightstream.run._continuation_frame import (
    continuation_block,
    continuation_verdict,
    refuse_what_cannot_continue,
)
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import CampaignWorkspace, PointName, RunRecord, RunStatus
from tests.tier1_offline.test_goal021_inputs_absolute import (
    _rotor_row as _fr96_converged_continuation___rotor_row,
)
from tests.tier1_offline.test_goal021_inputs_absolute import (
    _workspace as _fr96_converged_continuation___workspace,
)
from tests.tier1_offline.test_goal021_swept_row import _run as _fr96_converged_continuation___run
from tests.tier1_offline.test_matrix_run import (
    WRITES_EVERY_EXPORT as _FR96_CONVERGED_CONTINUATION__WRITES_EVERY_EXPORT,
)
from tests.tier1_offline.test_matrix_run import (
    CountingStub as _Fr96ConvergedContinuationCountingStub,
)
from tests.tier1_offline.test_post_products import (
    PLOTS_HEADER as _FR96_CONVERGED_CONTINUATION__PLOTS_HEADER,
)
from tests.tier1_offline.test_post_products import (
    _unsteady_workspace as _fr96_converged_continuation___unsteady_workspace,
)

SAVED = "datapoints/DP-AL+000/archive/20260914-010000/point.fsm"


def _continuing_case(restart: str, **variables) -> SimCase:
    return SimCase(
        sim_id="9001",
        aircraft="Rig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady",
        outputs=["loads_AL+000.txt", "run_AL+000_log.txt"],
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


@pytest.mark.requirement("FR-96")
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


@pytest.mark.parametrize("workflow", ["unsteady", "unsteady_rotor"])
def test_p0430_a_continuation_refuses_a_key_its_run_type_does_not_register(workflow):
    """X-F-0505: a mistyped key on a continuation row is refused, not ignored.

    The continuation branch returned before the unregistered-key guard, so a key
    nothing reads passed silently; the run layer's own continuation facts
    (RESTART_FROM, RESTART_ITERATIONS) are not the row's keys and pass.
    """
    case = _continuing_case(
        "{ADDITIONAL_ITERS=120}",
        **{RESTART_FROM_VARIABLE: SAVED, RESTART_ITERATIONS_VARIABLE: "120"},
        **{WORKFLOW_KEY: workflow, "TIME_ITERATON": "400"},
    ).model_copy(update={"recipe": workflow})
    with pytest.raises(CampaignConfigError, match="TIME_ITERATON"):
        build_script(case, Script("26.123"))


def test_goal020_restart_marches_the_remainder_and_not_the_rows_original_count():
    """The row asks for 400; the continuation owes 120, and the script says 120."""
    case = _continuing_case(
        "{ADDITIONAL_ITERS=120}",
        **{RESTART_FROM_VARIABLE: SAVED, RESTART_ITERATIONS_VARIABLE: "120"},
    )
    script = Script("26.123")
    build_script(case, script)
    lines = script.render().splitlines()
    # The count is the command's own argument: the remainder, never the row's 400.
    assert "TIME_ITERATIONS 120" in lines, lines
    assert not [line for line in lines if line.startswith("TIME_ITERATIONS 400")], lines


def _over_a_raw_mesh(case: SimCase, tmp_path) -> SimCase:
    """The same row over a raw mesh with its boundaries, which an ordinary row imports."""
    from pyflightstream.cases import (
        MeshImport,
        RawMeshConditions,
        TrailingEdgeMarking,
    )

    return case.model_copy(
        update={
            "geometry": str(tmp_path / "rig.obj"),
            "inventory": ("W", "B"),
            "inventory_source": "sidecar",
            "variables": {**case.variables, "LAST_ITERS_AVG": "100"},
            "mesh_import": MeshImport(units="METER"),
            "raw_mesh_conditions": RawMeshConditions(
                trailing_edges=TrailingEdgeMarking(route="detect")
            ),
        }
    )


def test_goal020_restart_imports_no_mesh_and_declares_no_boundaries(tmp_path):
    """Everything the saved file carries is a line this script does not emit.

    The row carries a raw mesh. The CONTROL is the same row without the RESTART: it imports
    the mesh, so the absence below is the continuation's and not the case's (PFS-2135.068).
    """
    continuing = _over_a_raw_mesh(
        _continuing_case(
            "{ADDITIONAL_ITERS=120}",
            **{RESTART_FROM_VARIABLE: SAVED, RESTART_ITERATIONS_VARIABLE: "120"},
        ),
        tmp_path,
    )
    ordinary = continuing.model_copy(
        update={
            "variables": {
                key: value
                for key, value in continuing.variables.items()
                if key not in {RESTART_VARIABLE, RESTART_FROM_VARIABLE, RESTART_ITERATIONS_VARIABLE}
            }
        }
    )
    imported = Script("26.123")
    build_script(ordinary, imported)
    assert "IMPORT" in imported.render(), "the control row does not import its mesh"

    script = Script("26.123")
    build_script(continuing, script)
    text = script.render()
    assert "IMPORT" not in text
    assert "CREATE_NEW_COORDINATE_SYSTEM" not in text
    assert SAVED in text


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
        outputs=["loads_AL+000.txt"],
        variables={WORKFLOW_KEY: "unsteady", "VELOCITY": "30.0", "TIME_ITERATIONS": "400"},
        point={"alpha": 0.0},
    )
    assert continuation_of(case) is None


# --------------------------------------------------------- the archive it owes


def test_goal020_restart_archives_what_it_replaces_under_a_day_and_hour_stamp(tmp_path):
    """HER DECISION, and the clause that decided the shape: there can be more than one restart."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    folder = workspace.sim_dir("9001") / "datapoints" / "DP-AL+000"
    folder.mkdir(parents=True)
    (folder / "loads.txt").write_text("the stopped run", encoding="utf-8")

    first = workspace.archive_datapoint(
        "9001", PointName("AL+000"), stamp=datetime(2026, 9, 14, 1, 0, 0)
    )
    assert first is not None
    assert first.name == "20260914-010000"
    assert (first / "loads.txt").read_text(encoding="utf-8") == "the stopped run"
    assert [p.name for p in folder.iterdir()] == ["archive"]

    # A SECOND CONTINUATION, which is why the stamp is there at all.
    (folder / "loads.txt").write_text("the first continuation", encoding="utf-8")
    second = workspace.archive_datapoint(
        "9001", PointName("AL+000"), stamp=datetime(2026, 9, 14, 2, 0, 0)
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
    assert workspace.archive_datapoint("9001", PointName("AL+000")) is None


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
        " / RESTART_STEP_OFFSET: 250",
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
        run_id="camp/sim_9001/AL+000",
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
        outputs=["datapoints/DP-AL+000/state.fsm", "datapoints/DP-AL+000/loads.txt"],
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
    saved = workspace.sim_dir("9001") / "datapoints" / "DP-AL+000"
    saved.mkdir(parents=True)
    (saved / "state.fsm").write_text("a stopped march", encoding="utf-8")
    workspace.append_record(_stopped_record())
    case = _continuing_case("{FINISH_PENDING}")
    resolved = resolve_continuation(workspace, case, {"alpha": 0.0}, run_id="camp/sim_9001/AL+000")
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


_FR96_CONVERGED_CONTINUATION__TAG = "V0300RE120AL+000"


_FR96_CONVERGED_CONTINUATION__POINT = f"rotor/sim_7001/{_FR96_CONVERGED_CONTINUATION__TAG}"


def _fr96_converged_continuation___converged(tmp_path):
    """A workspace whose rotor point ran once and was recorded CONVERGED."""
    workspace = _fr96_converged_continuation___workspace(tmp_path)
    _fr96_converged_continuation___run(
        workspace,
        _fr96_converged_continuation___rotor_row(tmp_path, sweep="0.0"),
        _Fr96ConvergedContinuationCountingStub(_FR96_CONVERGED_CONTINUATION__WRITES_EVERY_EXPORT),
    )
    (record,) = workspace.read_manifest()
    assert record.status is RunStatus.CONVERGED and record.recipe == "unsteady_rotor", record
    assert record.export_window is None, "the row exports nothing per step: no azimuthal step"
    return workspace


def _fr96_converged_continuation___restart(tmp_path, request):
    return _fr96_converged_continuation___rotor_row(
        tmp_path, sweep="0.0", extra=f" / RESTART: {{{request}}}"
    )


def _fr96_converged_continuation___plan(workspace, matrix):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        return plan_matrix(
            matrix,
            workspace,
            name="rotor",
            recipes={},
            recipe_registry=workflow_registry(),
            write_plan=False,
        )


def _fr96_converged_continuation___continue(workspace, matrix, **extra):
    stub = _Fr96ConvergedContinuationCountingStub(_FR96_CONVERGED_CONTINUATION__WRITES_EVERY_EXPORT)
    records = _fr96_converged_continuation___run(workspace, matrix, stub, **extra)
    return records, stub


# ------------------------------------------- the verdict, record by record
def _fr96_converged_continuation___record(
    status,
    *,
    recipe="unsteady_rotor",
    continues=None,
    restart=None,
    run_id=_FR96_CONVERGED_CONTINUATION__POINT,
):
    return RunRecord(
        run_id=run_id,
        sim_id="7001",
        point={"alpha": 0.0},
        status=status,
        recipe=recipe,
        fs_version_requested="26.123",
        package_version="0.33.0",
        script_sha256="c" * 64,
        raw_flag=False,
        continues=continues,
        restart=restart,
    )


class _Fr96ConvergedContinuationCase:
    def __init__(self, request):
        self.sim_id = "7001"
        self.variables = {"RESTART": f"{{{request}}}"}


def _fr96_converged_continuation___verdict(request, record):
    return continuation_verdict(parse_restart(_Fr96ConvergedContinuationCase(request)), record)


def _fr96_converged_continuation___as_recorded_before_0_33(workspace):
    """Remove the stated request from every record, as a 0.32 manifest has none."""
    data = workspace.read_raw_manifest()
    for entry in data:
        entry.pop("restart", None)
    workspace._replace_manifest(data)
    assert all(record.restart is None for record in workspace.read_manifest())


# ------------------------------------------------- post: the window of the whole march
_FR96_CONVERGED_CONTINUATION__STAMP = "20261001-120000"


_FR96_CONVERGED_CONTINUATION__PLAN = {
    "window_stated": True,
    "time_iterations": 8,
    "steps_per_revolution": 4.0,
    "blades": None,
    "time_average": {"windows": [[5, 8]], "window_from": "LAST_REVS_AVG = 1 at run time"},
}


def _fr96_converged_continuation___export(steps, offset=0):
    """A plots export of the given steps whose CL is 0.1 times (step + offset)."""
    table = "Time-step,CL_MRP_TOTAL,CDI_MRP_TOTAL\n" + "".join(
        f"{step}.0000,{0.1 * (step + offset):.5f},{0.01 * (step + offset):.5f},\n" for step in steps
    )
    return (
        _FR96_CONVERGED_CONTINUATION__PLOTS_HEADER
        + table
        + "-" * 60
        + "\n     Force Units: Coefficients\n"
    )


def _fr96_converged_continuation___continued_workspace(tmp_path, shape, *, archived=True):
    """The original eight steps archived, and a continuation of four, in ``shape``."""
    workspace = _fr96_converged_continuation___unsteady_workspace(
        tmp_path, reductions=_FR96_CONVERGED_CONTINUATION__PLAN
    )
    outputs = workspace.sim_dir("7001") / "outputs"
    archive = outputs / "archive" / _FR96_CONVERGED_CONTINUATION__STAMP
    archive.mkdir(parents=True)
    shutil.move(str(outputs / "AL-020_plots.txt"), archive / "AL-020_plots.txt")
    (archive / "AL-020_plots.txt").write_text(
        _fr96_converged_continuation___export(range(1, 9)), encoding="utf-8"
    )
    if not archived:
        shutil.rmtree(archive)
    exported = {
        "whole march": _fr96_converged_continuation___export(range(1, 13)),
        "numbered on": _fr96_converged_continuation___export(range(9, 13)),
        "count restarted": _fr96_converged_continuation___export(range(1, 5), offset=8),
    }[shape]
    (outputs / "AL-020_plots.txt").write_text(exported, encoding="utf-8")
    (original,) = workspace.read_manifest()
    workspace.append_record(
        original.model_copy(
            update={
                "run_id": f"camp/sim_7001/r{_FR96_CONVERGED_CONTINUATION__STAMP}/AL-020",
                "continues": original.run_id,
                "restart": {"form": "ADDITIONAL_REVS", "value": 1.0},
            }
        )
    )
    return workspace


def _fr96_converged_continuation___posted(workspace):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace, overwrite=True)
    out = workspace.root / "post" / "products"
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    columns, series = plots_table_series(out / "probes" / "AL-020_plots.csv")
    said = [str(w.message) for w in caught if "product=plots" in str(w.message)]
    return manifest, columns, series, said


def _fr96_converged_continuation___march_with(tmp_path, exported):
    workspace = _fr96_converged_continuation___continued_workspace(tmp_path, "numbered on")
    (workspace.sim_dir("7001") / "outputs" / "AL-020_plots.txt").write_text(
        exported, encoding="utf-8"
    )
    return _fr96_converged_continuation___posted(workspace)


class TestFr96ConvergedContinuation:
    """FR-96, amended in 0.33.0: ADDITIONAL_REVS and ADDITIONAL_ITERS continue a CONVERGED march.

    THE DEFECT. ``RESTART: {ADDITIONAL_REVS=n}`` continued only a run recorded
    WALLTIME_REACHED or COMPLETED_MAX_ITER, and a point whose latest run had
    CONVERGED was passed over in silence: the plan listed it as recorded and the
    run ran nothing. Every unsteady rotor point of a real campaign is recorded
    CONVERGED, because for a march CONVERGED is the residual test at its last step,
    so the scheme for marching the revolutions an average needs did nothing on
    every point it was written for.

    WHAT HOLDS NOW, each tested below on the path a user takes (plan, run, post):

    - a CONVERGED unsteady point with ADDITIONAL_REVS or ADDITIONAL_ITERS plans and
      runs as a continuation, by the same machinery a wall-clock stop uses, and
      its record states the request it answered; a CONVERGED steady run does not;
    - the same request does not continue it twice: running again is a stated skip,
      a different request continues it again, and a continuation recorded before
      0.33.0 is taken to answer the request its row carries;
    - FINISH_PENDING on a CONVERGED run is refused with the reason, and every point
      a RESTART key cannot continue is said, in the plan and in the run;
    - the averaging window of a continued point lands in the last revolutions of
      the WHOLE march, whichever history its plots export holds, with the seam
      exact; the wall-clock continuation of 0.32.0 is unchanged.
    """

    @staticmethod
    # ------------------------------------------------- plan and run: the continuation
    def test_a_converged_unsteady_point_plans_and_runs_as_a_continuation_fr_96(tmp_path):
        workspace = _fr96_converged_continuation___converged(tmp_path)
        matrix = _fr96_converged_continuation___restart(tmp_path, "ADDITIONAL_REVS=1")
        (entry,) = _fr96_converged_continuation___plan(workspace, matrix).points
        assert entry.status is PlanStatus.READY, (entry.status, entry.error)
        assert entry.continuation == (
            f"continuing a CONVERGED unsteady run, {_FR96_CONVERGED_CONTINUATION__POINT!r}, by 1 revolution(s)"  # noqa: E501
        ), entry.continuation
        records, stub = _fr96_converged_continuation___continue(workspace, matrix)
        (record,) = records
        assert record.continues == _FR96_CONVERGED_CONTINUATION__POINT and record.run_id.startswith(
            "rotor/sim_7001/r"
        )
        assert record.restart == {"form": "ADDITIONAL_REVS", "value": 1.0}, record.restart
        assert record.status is RunStatus.CONVERGED, (record.status, record.error)
        script = workspace.sim_dir("7001") / record.script_path
        lines = script.read_text(encoding="utf-8").splitlines()
        opened = Path(lines[lines.index("OPEN") + 1])
        assert opened.is_absolute() and opened.is_file() and "archive" in opened.parts, opened
        # ONE REVOLUTION IS 500 STEPS on this row's clock (1200 rev/min, 0.0001 s a
        # step), read off the record's reductions plan because the row exports
        # nothing per step and so records no azimuthal step.
        assert "TIME_ITERATIONS 500" in lines, [
            line for line in lines if line.startswith("SET_SOLVER_UNSTEADY")
        ]
        assert len(stub.invocations) == 1

    @staticmethod
    def test_p0430_a_continuation_refused_before_the_solver_gives_back_its_archive(
        tmp_path, monkeypatch
    ):
        """X-F-0549: a continuation never built leaves the stopped run's outputs in place.

        The continuation archived the datapoint folder before the point was known to
        build, so a point refused at its script left the stopped record naming an
        emptied folder. A point recorded FAILED_SCRIPT with no executor moves the
        archived outputs back.
        """
        import pyflightstream.run._campaign as campaign

        workspace = _fr96_converged_continuation___converged(tmp_path)
        folders = list((workspace.sim_dir("7001") / "datapoints").iterdir())
        before = {f: sorted(p.name for p in f.iterdir()) for f in folders}
        assert any(before.values()), before

        def _refused(**kwargs):
            case = kwargs["case"]
            return RunRecord(
                run_id=kwargs["run_id"],
                sim_id=case.sim_id,
                point=dict(kwargs["point"]),
                fs_version_requested="26.123",
                package_version="0.43.0",
                script_sha256="",
                raw_flag=False,
                status=RunStatus.FAILED_SCRIPT,
                error="refused at its script",
            )

        monkeypatch.setattr(campaign, "_execute_point", _refused)
        matrix = _fr96_converged_continuation___restart(tmp_path, "ADDITIONAL_REVS=1")
        with pytest.raises(Exception, match="refused at its script"):
            _fr96_converged_continuation___continue(workspace, matrix)
        after = {f: sorted(p.name for p in f.iterdir()) for f in folders}
        assert after == before, (before, after)

    @staticmethod
    def test_additional_iters_continues_a_converged_unsteady_point_fr_96(tmp_path):
        workspace = _fr96_converged_continuation___converged(tmp_path)
        records, _ = _fr96_converged_continuation___continue(
            workspace, _fr96_converged_continuation___restart(tmp_path, "ADDITIONAL_ITERS=120")
        )
        (record,) = records
        assert record.continues == _FR96_CONVERGED_CONTINUATION__POINT
        assert record.restart == {"form": "ADDITIONAL_ITERS", "value": 120.0}
        script = (workspace.sim_dir("7001") / record.script_path).read_text(encoding="utf-8")
        assert "TIME_ITERATIONS 120" in script.splitlines()

    @staticmethod
    def test_running_again_with_the_same_request_continues_once_and_says_so_fr_96(tmp_path, capsys):
        workspace = _fr96_converged_continuation___converged(tmp_path)
        matrix = _fr96_converged_continuation___restart(tmp_path, "ADDITIONAL_REVS=1")
        first, _ = _fr96_converged_continuation___continue(workspace, matrix)
        assert len(first) == 1
        capsys.readouterr()
        again, stub = _fr96_converged_continuation___continue(workspace, matrix, resume=True)
        assert again == [] and stub.invocations == [], [(r.run_id, r.status) for r in again]
        said = "".join(capsys.readouterr())
        assert (
            f"already continued by ADDITIONAL_REVS=1: its latest run, {first[0].run_id!r}" in said
        )
        assert "change the request to march further" in said
        (entry,) = _fr96_converged_continuation___plan(workspace, matrix).points
        assert entry.status is PlanStatus.ALREADY_RECORDED
        assert entry.continuation.startswith("already continued by ADDITIONAL_REVS=1"), entry
        assert len(workspace.read_manifest()) == 2

    @staticmethod
    def test_changing_the_request_continues_the_continuation_again_fr_96(tmp_path):
        workspace = _fr96_converged_continuation___converged(tmp_path)
        first, _ = _fr96_converged_continuation___continue(
            workspace, _fr96_converged_continuation___restart(tmp_path, "ADDITIONAL_REVS=1")
        )
        second, _ = _fr96_converged_continuation___continue(
            workspace, _fr96_converged_continuation___restart(tmp_path, "ADDITIONAL_REVS=2")
        )
        (record,) = second
        assert record.continues == first[0].run_id, "a new request continues the latest run"
        assert record.restart == {"form": "ADDITIONAL_REVS", "value": 2.0}
        script = (workspace.sim_dir("7001") / record.script_path).read_text(encoding="utf-8")
        assert "TIME_ITERATIONS 1000" in script.splitlines()

    @staticmethod
    def test_finish_pending_on_a_converged_run_is_refused_with_the_reason_fr_96(tmp_path, capsys):
        workspace = _fr96_converged_continuation___converged(tmp_path)
        matrix = _fr96_converged_continuation___restart(tmp_path, "FINISH_PENDING")
        (entry,) = _fr96_converged_continuation___plan(workspace, matrix).points
        assert entry.status is PlanStatus.ALREADY_RECORDED
        assert entry.continuation.startswith(
            f"nothing is pending: its latest run, {_FR96_CONVERGED_CONTINUATION__POINT!r}"
        ), entry
        assert "ADDITIONAL_REVS=n" in entry.continuation
        capsys.readouterr()
        records, stub = _fr96_converged_continuation___continue(workspace, matrix)
        assert records == [] and stub.invocations == []
        assert "nothing is pending" in "".join(capsys.readouterr())
        # THE RESOLVER REFUSES IT, the run's own pre-flight and the library's entry.
        request = parse_restart(_Fr96ConvergedContinuationCase("FINISH_PENDING"))
        with pytest.raises(CampaignConfigError, match="nothing is pending") as raised:
            refuse_what_cannot_continue(
                workspace, "7001", _FR96_CONVERGED_CONTINUATION__TAG, request
            )
        assert "finishes only a run its wall clock stopped" in str(raised.value)

    @staticmethod
    def test_a_converged_steady_point_is_not_continued_control_fr_96():
        verdict = _fr96_converged_continuation___verdict(
            "ADDITIONAL_ITERS=10",
            _fr96_converged_continuation___record(RunStatus.CONVERGED, recipe="steady"),
        )
        assert not verdict.pending
        assert verdict.said.startswith("nothing to march: its latest run"), verdict.said
        assert _fr96_converged_continuation___verdict(
            "ADDITIONAL_ITERS=10", _fr96_converged_continuation___record(RunStatus.CONVERGED)
        ).pending

    @staticmethod
    def test_a_point_its_request_cannot_continue_is_said_not_passed_over_fr_96(tmp_path):
        for status in (RunStatus.SUBMITTED, RunStatus.CONVERGED):
            verdict = _fr96_converged_continuation___verdict(
                "FINISH_PENDING", _fr96_converged_continuation___record(status)
            )
            assert not verdict.pending and verdict.said, (status, verdict)
        workspace = _fr96_converged_continuation___workspace(tmp_path)
        queued = _fr96_converged_continuation___record(RunStatus.SUBMITTED).model_copy(
            update={"matrix_stem": "rotor"}
        )
        workspace.append_record(queued)
        plan = _fr96_converged_continuation___plan(
            workspace, _fr96_converged_continuation___restart(tmp_path, "ADDITIONAL_REVS=1")
        )
        (entry,) = plan.points
        assert entry.status is PlanStatus.ALREADY_RECORDED, (entry.status, entry.error)
        assert "is SUBMITTED and still in a scheduler's queue" in entry.continuation
        block = "\n".join(continuation_block(plan.points))
        assert _FR96_CONVERGED_CONTINUATION__POINT in block and "SUBMITTED" in block, block

    @staticmethod
    def test_a_continuation_recorded_before_0_33_that_cannot_be_read_is_not_continued_fr_96():
        # With nothing to read its request off (no script, no predecessor), a
        # continuation recorded before 0.33.0 is taken to answer the request.
        old = _fr96_converged_continuation___record(
            RunStatus.CONVERGED,
            continues=_FR96_CONVERGED_CONTINUATION__POINT,
            run_id="rotor/sim_7001/r20260901-100000/x",
        )
        verdict = _fr96_converged_continuation___verdict("ADDITIONAL_REVS=3", old)
        assert not verdict.pending and "recorded without a request" in verdict.said, verdict
        capped = old.model_copy(update={"status": RunStatus.COMPLETED_MAX_ITER})
        assert not _fr96_converged_continuation___verdict("ADDITIONAL_REVS=3", capped).pending

    @staticmethod
    def test_a_continuation_recorded_before_0_33_skips_the_same_request_continues_a_new_one_fr_96(
        tmp_path, capsys
    ):
        workspace = _fr96_converged_continuation___converged(tmp_path)
        first, _ = _fr96_converged_continuation___continue(
            workspace, _fr96_converged_continuation___restart(tmp_path, "ADDITIONAL_REVS=1")
        )
        _fr96_converged_continuation___as_recorded_before_0_33(workspace)
        capsys.readouterr()
        # THE SAME REQUEST: the record marched the 500 steps it asks, so it answered it.
        again, stub = _fr96_converged_continuation___continue(
            workspace,
            _fr96_converged_continuation___restart(tmp_path, "ADDITIONAL_REVS=1"),
            resume=True,
        )
        assert again == [] and stub.invocations == [], [(r.run_id, r.status) for r in again]
        said = "".join(capsys.readouterr())
        assert "already continued by ADDITIONAL_REVS=1" in said, said
        assert "recorded without a request" in said, said
        (entry,) = _fr96_converged_continuation___plan(
            workspace, _fr96_converged_continuation___restart(tmp_path, "ADDITIONAL_REVS=1")
        ).points
        assert entry.status is PlanStatus.ALREADY_RECORDED, entry
        # A CHANGED n continues it, exactly as a 0.33 continuation is continued.
        (entry,) = _fr96_converged_continuation___plan(
            workspace, _fr96_converged_continuation___restart(tmp_path, "ADDITIONAL_REVS=2")
        ).points
        assert entry.status is PlanStatus.READY, (entry.status, entry.error)
        second, _ = _fr96_converged_continuation___continue(
            workspace, _fr96_converged_continuation___restart(tmp_path, "ADDITIONAL_REVS=2")
        )
        (record,) = second
        assert record.continues == first[0].run_id
        assert record.restart == {"form": "ADDITIONAL_REVS", "value": 2.0}

    @staticmethod
    def test_the_walltime_continuation_of_0_32_is_unchanged_control_fr_96():
        stopped = _fr96_converged_continuation___record(RunStatus.WALLTIME_REACHED)
        for request in ("FINISH_PENDING", "ADDITIONAL_ITERS=50", "ADDITIONAL_REVS=1"):
            assert _fr96_converged_continuation___verdict(request, stopped).pending, request
        # A continuation the clock stopped again goes on whatever it answered.
        again = _fr96_converged_continuation___record(
            RunStatus.WALLTIME_REACHED,
            continues=_FR96_CONVERGED_CONTINUATION__POINT,
            restart={"form": "ADDITIONAL_REVS", "value": 1.0},
        )
        assert _fr96_converged_continuation___verdict("ADDITIONAL_REVS=1", again).pending
        # A failed run and a point nothing records go to the resolver, refused by name.
        assert _fr96_converged_continuation___verdict(
            "ADDITIONAL_REVS=1", _fr96_converged_continuation___record(RunStatus.FAILED_EXECUTION)
        ).pending
        assert _fr96_converged_continuation___verdict("ADDITIONAL_REVS=1", None).pending

    @staticmethod
    @pytest.mark.parametrize(
        "shape, how",
        [
            ("whole march", "restating the march from step 1"),
            ("numbered on", "numbered on from step 9"),
            ("count restarted", "counting again from 1, numbered on from step 9"),
        ],
    )
    def test_the_window_lands_in_the_last_revolutions_of_the_whole_march_fr_96(
        tmp_path, shape, how
    ):
        manifest, columns, series, said = _fr96_converged_continuation___posted(
            _fr96_converged_continuation___continued_workspace(tmp_path, shape)
        )
        # THE SEAM IS EXACT: every step of the march once, in order, none missing.
        assert list(series.steps) == list(range(1, 13)), list(series.steps)
        cl = series.fields["CL_MRP_TOTAL"][:, 0]
        scale = cl[0] / 0.1
        assert cl == pytest.approx([0.1 * step * scale for step in range(1, 13)], rel=1e-6)
        # ONE REVOLUTION IS FOUR STEPS: the last of the whole march is 9 to 12, and
        # the run recorded 5 to 8, the last revolution of the run it continued.
        entry = manifest["products"]["probes/AL-020_time_average.csv"]
        assert entry["windows"] == [[9, 12]], entry
        assert entry["runs"] == [f"camp/sim_7001/r{_FR96_CONVERGED_CONTINUATION__STAMP}/AL-020"], (
            entry["runs"]
        )
        assert len(said) == 1 and how in said[0], said
        assert "The averaging window ends at step 12" in said[0], said[0]
        assert "camp/sim_7001/AL-020" not in json.dumps(manifest["products"]), "the stop is posted"

    @staticmethod
    def test_a_history_not_found_is_said_and_the_window_ends_at_the_export_fr_96(tmp_path):
        workspace = _fr96_converged_continuation___continued_workspace(
            tmp_path, "numbered on", archived=False
        )
        manifest, _, series, said = _fr96_converged_continuation___posted(workspace)
        assert list(series.steps) == [9, 10, 11, 12]
        assert manifest["products"]["probes/AL-020_time_average.csv"]["windows"] == [[9, 12]]
        assert len(said) == 1 and "Not joined: the history of 'camp/sim_7001/AL-020'" in said[0]
        assert "restore that file and post again" in said[0], said[0]

    @staticmethod
    def test_a_point_that_continues_nothing_posts_as_before_control_fr_96(tmp_path):
        workspace = _fr96_converged_continuation___unsteady_workspace(
            tmp_path, reductions=_FR96_CONVERGED_CONTINUATION__PLAN
        )
        manifest, _, series, said = _fr96_converged_continuation___posted(workspace)
        assert list(series.steps) == list(range(1, 9)) and said == []
        assert manifest["products"]["probes/AL-020_time_average.csv"]["windows"] == [[5, 8]]

    @staticmethod
    def test_an_export_restating_only_the_last_step_keeps_the_seam_exact_fr_96(tmp_path):
        # Verifies FR-96.
        _, _, series, said = _fr96_converged_continuation___march_with(
            tmp_path, _fr96_converged_continuation___export(range(8, 13))
        )
        assert list(series.steps) == list(range(1, 13)), (list(series.steps), said)

    @staticmethod
    def test_an_export_starting_inside_the_history_with_other_values_is_not_joined_fr_96(tmp_path):
        # Verifies FR-96.
        _, _, series, said = _fr96_converged_continuation___march_with(
            tmp_path, _fr96_converged_continuation___export(range(3, 7), offset=100)
        )
        assert list(series.steps) == [3, 4, 5, 6], (list(series.steps), said)
        assert "cannot be joined" in said[0], said
