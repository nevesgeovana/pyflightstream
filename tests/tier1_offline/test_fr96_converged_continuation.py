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

# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-96.

from __future__ import annotations

import json
import shutil
import warnings
from pathlib import Path

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.workflows import parse_restart, workflow_registry
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.post.products import plots_table_series, write_campaign_products
from pyflightstream.run import PlanStatus
from pyflightstream.run._continuation_frame import (
    continuation_block,
    continuation_verdict,
    refuse_what_cannot_continue,
)
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.workspace import RunRecord, RunStatus
from tests.tier1_offline.test_goal021_inputs_absolute import _rotor_row, _workspace
from tests.tier1_offline.test_goal021_swept_row import _run
from tests.tier1_offline.test_matrix_run import WRITES_EVERY_EXPORT, CountingStub
from tests.tier1_offline.test_post_products import PLOTS_HEADER, _unsteady_workspace

TAG = "V0300RE120AL+000"
POINT = f"rotor/sim_7001/{TAG}"


def _converged(tmp_path):
    """A workspace whose rotor point ran once and was recorded CONVERGED."""
    workspace = _workspace(tmp_path)
    _run(workspace, _rotor_row(tmp_path, sweep="0.0"), CountingStub(WRITES_EVERY_EXPORT))
    (record,) = workspace.read_manifest()
    assert record.status is RunStatus.CONVERGED and record.recipe == "unsteady_rotor", record
    assert record.export_window is None, "the row exports nothing per step: no azimuthal step"
    return workspace


def _restart(tmp_path, request):
    return _rotor_row(tmp_path, sweep="0.0", extra=f" / RESTART: {{{request}}}")


def _plan(workspace, matrix):
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


def _continue(workspace, matrix, **extra):
    stub = CountingStub(WRITES_EVERY_EXPORT)
    records = _run(workspace, matrix, stub, **extra)
    return records, stub


# ------------------------------------------------- plan and run: the continuation


def test_a_converged_unsteady_point_plans_and_runs_as_a_continuation_fr_96(tmp_path):
    workspace = _converged(tmp_path)
    matrix = _restart(tmp_path, "ADDITIONAL_REVS=1")
    (entry,) = _plan(workspace, matrix).points
    assert entry.status is PlanStatus.READY, (entry.status, entry.error)
    assert entry.continuation == (
        f"continuing a CONVERGED unsteady run, {POINT!r}, by 1 revolution(s)"
    ), entry.continuation
    records, stub = _continue(workspace, matrix)
    (record,) = records
    assert record.continues == POINT and record.run_id.startswith("rotor/sim_7001/r")
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


def test_additional_iters_continues_a_converged_unsteady_point_fr_96(tmp_path):
    workspace = _converged(tmp_path)
    records, _ = _continue(workspace, _restart(tmp_path, "ADDITIONAL_ITERS=120"))
    (record,) = records
    assert record.continues == POINT
    assert record.restart == {"form": "ADDITIONAL_ITERS", "value": 120.0}
    script = (workspace.sim_dir("7001") / record.script_path).read_text(encoding="utf-8")
    assert "TIME_ITERATIONS 120" in script.splitlines()


def test_running_again_with_the_same_request_continues_once_and_says_so_fr_96(tmp_path, capsys):
    workspace = _converged(tmp_path)
    matrix = _restart(tmp_path, "ADDITIONAL_REVS=1")
    first, _ = _continue(workspace, matrix)
    assert len(first) == 1
    capsys.readouterr()
    again, stub = _continue(workspace, matrix, resume=True)
    assert again == [] and stub.invocations == [], [(r.run_id, r.status) for r in again]
    said = "".join(capsys.readouterr())
    assert f"already continued by ADDITIONAL_REVS=1: its latest run, {first[0].run_id!r}" in said
    assert "change the request to march further" in said
    (entry,) = _plan(workspace, matrix).points
    assert entry.status is PlanStatus.ALREADY_RECORDED
    assert entry.continuation.startswith("already continued by ADDITIONAL_REVS=1"), entry
    assert len(workspace.read_manifest()) == 2


def test_changing_the_request_continues_the_continuation_again_fr_96(tmp_path):
    workspace = _converged(tmp_path)
    first, _ = _continue(workspace, _restart(tmp_path, "ADDITIONAL_REVS=1"))
    second, _ = _continue(workspace, _restart(tmp_path, "ADDITIONAL_REVS=2"))
    (record,) = second
    assert record.continues == first[0].run_id, "a new request continues the latest run"
    assert record.restart == {"form": "ADDITIONAL_REVS", "value": 2.0}
    script = (workspace.sim_dir("7001") / record.script_path).read_text(encoding="utf-8")
    assert "TIME_ITERATIONS 1000" in script.splitlines()


def test_finish_pending_on_a_converged_run_is_refused_with_the_reason_fr_96(tmp_path, capsys):
    workspace = _converged(tmp_path)
    matrix = _restart(tmp_path, "FINISH_PENDING")
    (entry,) = _plan(workspace, matrix).points
    assert entry.status is PlanStatus.ALREADY_RECORDED
    assert entry.continuation.startswith(f"nothing is pending: its latest run, {POINT!r}"), entry
    assert "ADDITIONAL_REVS=n" in entry.continuation
    capsys.readouterr()
    records, stub = _continue(workspace, matrix)
    assert records == [] and stub.invocations == []
    assert "nothing is pending" in "".join(capsys.readouterr())
    # THE RESOLVER REFUSES IT, the run's own pre-flight and the library's entry.
    request = parse_restart(_Case("FINISH_PENDING"))
    with pytest.raises(CampaignConfigError, match="nothing is pending") as raised:
        refuse_what_cannot_continue(workspace, "7001", TAG, request)
    assert "finishes only a run its wall clock stopped" in str(raised.value)


# ------------------------------------------- the verdict, record by record


def _record(status, *, recipe="unsteady_rotor", continues=None, restart=None, run_id=POINT):
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


class _Case:
    def __init__(self, request):
        self.sim_id = "7001"
        self.variables = {"RESTART": f"{{{request}}}"}


def _verdict(request, record):
    return continuation_verdict(parse_restart(_Case(request)), record)


def test_a_converged_steady_point_is_not_continued_control_fr_96():
    verdict = _verdict("ADDITIONAL_ITERS=10", _record(RunStatus.CONVERGED, recipe="steady"))
    assert not verdict.pending
    assert verdict.said.startswith("nothing to march: its latest run"), verdict.said
    assert _verdict("ADDITIONAL_ITERS=10", _record(RunStatus.CONVERGED)).pending


def test_a_point_its_request_cannot_continue_is_said_not_passed_over_fr_96(tmp_path):
    for status in (RunStatus.SUBMITTED, RunStatus.CONVERGED):
        verdict = _verdict("FINISH_PENDING", _record(status))
        assert not verdict.pending and verdict.said, (status, verdict)
    workspace = _workspace(tmp_path)
    queued = _record(RunStatus.SUBMITTED).model_copy(update={"matrix_stem": "rotor"})
    workspace.append_record(queued)
    plan = _plan(workspace, _restart(tmp_path, "ADDITIONAL_REVS=1"))
    (entry,) = plan.points
    assert entry.status is PlanStatus.ALREADY_RECORDED, (entry.status, entry.error)
    assert "is SUBMITTED and still in a scheduler's queue" in entry.continuation
    block = "\n".join(continuation_block(plan.points))
    assert POINT in block and "SUBMITTED" in block, block


def test_a_continuation_recorded_before_0_33_that_cannot_be_read_is_not_continued_fr_96():
    # With nothing to read its request off (no script, no predecessor), a
    # continuation recorded before 0.33.0 is taken to answer the request.
    old = _record(RunStatus.CONVERGED, continues=POINT, run_id="rotor/sim_7001/r20260901-100000/x")
    verdict = _verdict("ADDITIONAL_REVS=3", old)
    assert not verdict.pending and "recorded before 0.33.0" in verdict.said, verdict
    capped = old.model_copy(update={"status": RunStatus.COMPLETED_MAX_ITER})
    assert not _verdict("ADDITIONAL_REVS=3", capped).pending


def _as_recorded_before_0_33(workspace):
    """Remove the stated request from every record, as a 0.32 manifest has none."""
    manifest = workspace.root / "runs.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for entry in data["runs"] if isinstance(data, dict) else data:
        entry.pop("restart", None)
    manifest.write_text(json.dumps(data, indent=1), encoding="utf-8")
    assert all(record.restart is None for record in workspace.read_manifest())


def test_a_continuation_recorded_before_0_33_skips_the_same_request_continues_a_new_one_fr_96(
    tmp_path, capsys
):
    workspace = _converged(tmp_path)
    first, _ = _continue(workspace, _restart(tmp_path, "ADDITIONAL_REVS=1"))
    _as_recorded_before_0_33(workspace)
    capsys.readouterr()
    # THE SAME REQUEST: the record marched the 500 steps it asks, so it answered it.
    again, stub = _continue(workspace, _restart(tmp_path, "ADDITIONAL_REVS=1"), resume=True)
    assert again == [] and stub.invocations == [], [(r.run_id, r.status) for r in again]
    said = "".join(capsys.readouterr())
    assert "already continued by ADDITIONAL_REVS=1" in said, said
    assert "recorded before 0.33.0, it states no request" in said, said
    (entry,) = _plan(workspace, _restart(tmp_path, "ADDITIONAL_REVS=1")).points
    assert entry.status is PlanStatus.ALREADY_RECORDED, entry
    # A CHANGED n continues it, exactly as a 0.33 continuation is continued.
    (entry,) = _plan(workspace, _restart(tmp_path, "ADDITIONAL_REVS=2")).points
    assert entry.status is PlanStatus.READY, (entry.status, entry.error)
    second, _ = _continue(workspace, _restart(tmp_path, "ADDITIONAL_REVS=2"))
    (record,) = second
    assert record.continues == first[0].run_id
    assert record.restart == {"form": "ADDITIONAL_REVS", "value": 2.0}


def test_the_walltime_continuation_of_0_32_is_unchanged_control_fr_96():
    stopped = _record(RunStatus.WALLTIME_REACHED)
    for request in ("FINISH_PENDING", "ADDITIONAL_ITERS=50", "ADDITIONAL_REVS=1"):
        assert _verdict(request, stopped).pending, request
    # A continuation the clock stopped again goes on whatever it answered.
    again = _record(
        RunStatus.WALLTIME_REACHED,
        continues=POINT,
        restart={"form": "ADDITIONAL_REVS", "value": 1.0},
    )
    assert _verdict("ADDITIONAL_REVS=1", again).pending
    # A failed run and a point nothing records go to the resolver, refused by name.
    assert _verdict("ADDITIONAL_REVS=1", _record(RunStatus.FAILED_EXECUTION)).pending
    assert _verdict("ADDITIONAL_REVS=1", None).pending


# ------------------------------------------------- post: the window of the whole march

STAMP = "20261001-120000"
PLAN = {
    "window_stated": True,
    "time_iterations": 8,
    "steps_per_revolution": 4.0,
    "blades": None,
    "time_average": {"windows": [[5, 8]], "window_from": "LAST_REVS_AVG = 1 at run time"},
}


def _export(steps, offset=0):
    """A plots export of the given steps whose CL is 0.1 times (step + offset)."""
    table = "Time-step,CL_MRP_TOTAL,CDI_MRP_TOTAL\n" + "".join(
        f"{step}.0000,{0.1 * (step + offset):.5f},{0.01 * (step + offset):.5f},\n" for step in steps
    )
    return PLOTS_HEADER + table + "-" * 60 + "\n     Force Units: Coefficients\n"


def _continued_workspace(tmp_path, shape, *, archived=True):
    """The original eight steps archived, and a continuation of four, in ``shape``."""
    workspace = _unsteady_workspace(tmp_path, reductions=PLAN)
    outputs = workspace.sim_dir("7001") / "outputs"
    archive = outputs / "archive" / STAMP
    archive.mkdir(parents=True)
    shutil.move(str(outputs / "AL-020_plots.txt"), archive / "AL-020_plots.txt")
    (archive / "AL-020_plots.txt").write_text(_export(range(1, 9)), encoding="utf-8")
    if not archived:
        shutil.rmtree(archive)
    exported = {
        "whole march": _export(range(1, 13)),
        "numbered on": _export(range(9, 13)),
        "count restarted": _export(range(1, 5), offset=8),
    }[shape]
    (outputs / "AL-020_plots.txt").write_text(exported, encoding="utf-8")
    (original,) = workspace.read_manifest()
    workspace.append_record(
        original.model_copy(
            update={
                "run_id": f"camp/sim_7001/r{STAMP}/AL-020",
                "continues": original.run_id,
                "restart": {"form": "ADDITIONAL_REVS", "value": 1.0},
            }
        )
    )
    return workspace


def _posted(workspace):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace, overwrite=True)
    out = workspace.root / "post" / "products"
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    columns, series = plots_table_series(out / "probes" / "AL-020_plots.csv")
    said = [str(w.message) for w in caught if "product=plots" in str(w.message)]
    return manifest, columns, series, said


@pytest.mark.parametrize(
    "shape, how",
    [
        ("whole march", "restating the march from step 1"),
        ("numbered on", "numbered on from step 9"),
        ("count restarted", "counting again from 1, numbered on from step 9"),
    ],
)
def test_the_window_lands_in_the_last_revolutions_of_the_whole_march_fr_96(tmp_path, shape, how):
    manifest, columns, series, said = _posted(_continued_workspace(tmp_path, shape))
    # THE SEAM IS EXACT: every step of the march once, in order, none missing.
    assert list(series.steps) == list(range(1, 13)), list(series.steps)
    cl = series.fields["CL_MRP_TOTAL"][:, 0]
    scale = cl[0] / 0.1
    assert cl == pytest.approx([0.1 * step * scale for step in range(1, 13)], rel=1e-6)
    # ONE REVOLUTION IS FOUR STEPS: the last of the whole march is 9 to 12, and
    # the run recorded 5 to 8, the last revolution of the run it continued.
    entry = manifest["products"]["probes/AL-020_time_average.csv"]
    assert entry["windows"] == [[9, 12]], entry
    assert entry["runs"] == [f"camp/sim_7001/r{STAMP}/AL-020"], entry["runs"]
    assert len(said) == 1 and how in said[0], said
    assert "The averaging window ends at step 12" in said[0], said[0]
    assert "camp/sim_7001/AL-020" not in json.dumps(manifest["products"]), "the stop is posted"


def test_a_history_not_found_is_said_and_the_window_ends_at_the_export_fr_96(tmp_path):
    workspace = _continued_workspace(tmp_path, "numbered on", archived=False)
    manifest, _, series, said = _posted(workspace)
    assert list(series.steps) == [9, 10, 11, 12]
    assert manifest["products"]["probes/AL-020_time_average.csv"]["windows"] == [[9, 12]]
    assert len(said) == 1 and "Not joined: the history of 'camp/sim_7001/AL-020'" in said[0]
    assert "restore that file and post again" in said[0], said[0]


def test_a_point_that_continues_nothing_posts_as_before_control_fr_96(tmp_path):
    workspace = _unsteady_workspace(tmp_path, reductions=PLAN)
    manifest, _, series, said = _posted(workspace)
    assert list(series.steps) == list(range(1, 9)) and said == []
    assert manifest["products"]["probes/AL-020_time_average.csv"]["windows"] == [[5, 8]]
