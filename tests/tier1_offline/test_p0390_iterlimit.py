"""P0390-ITERLIMIT (FR-434): a steady run at its iteration limit, unsettled, is MAX_ITER_REACHED.

Expected values are worked from the requirement and the fixtures: the steady
loads export prints 312 of a requested 500 and the unsteady one 1575; a log
ending at the requested iteration with a velocity residual of 9.6e-2 is
unsettled against the export's convergence limit of 1e-5.
"""

from __future__ import annotations

import json
import os
import re
import time
import warnings
from pathlib import Path

import pytest

from pyflightstream.run import LoadsAssessor
from pyflightstream.run.collect import collect_once
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from pyflightstream.workspace.record_document import read_rows as _read_record_rows
from tests.support_helpers import no_sleep
from tests.tier1_offline import test_goal031_local_run_log as local_run
from tests.tier1_offline.test_goal028_hpc_log_completeness import _log
from tests.tier1_offline.test_p0370_s1_matrix_home import MATRIX, grouped_workspace, pyfs
from tests.tier1_offline.test_run_campaign import FIXTURES, make_collected

UNSETTLED = "+9.6000000E-2"
STEADY = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
UNSTEADY = (FIXTURES / "loads_unsteady_26.120.txt").read_text(encoding="utf-8")
COUNTER = "Current solver iteration number:            "


def _at(text: str, counter: int, *, was: str = "312") -> str:
    """The export with its iteration counter replaced."""
    return text.replace(f"{COUNTER}{was}", f"{COUNTER}{counter}")


def _assess(tmp_path: Path, loads: str, log: str | None = None):
    sim_dir = make_collected(tmp_path, "", text=loads)
    if log is not None:
        make_collected(tmp_path, "", name="log.txt", text=log)
    return LoadsAssessor("loads.txt")(None, None, sim_dir)


def test_p0390_iterlimit_a_steady_point_at_the_limit_with_a_log_is_max_iter_reached(tmp_path):
    """P0390-ITERLIMIT (FR-974): log counter at the limit 500, residual above the limit.

    The record states the requested limit and the iterations reached. A mutant
    that keeps the 0.38.0 status fails this test.
    """
    assessment = _assess(tmp_path, _at(STEADY, 500), _log(ends_at=500, final_velocity=UNSETTLED))
    assert assessment.status is RunStatus.MAX_ITER_REACHED, assessment.error
    assert assessment.iterations == 500
    assert assessment.iterations_requested == 500
    note = assessment.residual_note or ""
    assert "500" in note and "iteration limit" in note, note


def test_p0390_iterlimit_a_steady_point_at_the_limit_without_a_log_stays_completed(tmp_path):
    """P0390-ITERLIMIT (FR-975): the footer supplies the counter only, never the verdict.

    A steady export at 500 of 500 and no solver log has no readable residual,
    so the status stays COMPLETED_MAX_ITER and no limit is written. A mutant
    that infers the verdict from the footer alone fails this test.
    """
    assessment = _assess(tmp_path, _at(STEADY, 500))
    assert assessment.status is RunStatus.COMPLETED_MAX_ITER, assessment.error
    assert assessment.iterations == 500
    assert assessment.iterations_requested is None


def test_p0390_iterlimit_a_log_at_the_limit_that_settled_is_converged(tmp_path):
    """P0390-ITERLIMIT (FR-974): the residual settled at the limit, so the point converged."""
    assessment = _assess(tmp_path, _at(STEADY, 500), _log(ends_at=500))
    assert assessment.status is RunStatus.CONVERGED
    assert assessment.iterations_requested is None


def test_p0390_iterlimit_a_point_short_of_the_limit_keeps_the_0_38_status(tmp_path):
    """P0390-ITERLIMIT (FR-975): unsettled at 400 of 500 stays COMPLETED_MAX_ITER.

    A mutant that maps every unsettled steady point to the new status fails
    this test.
    """
    assessment = _assess(tmp_path, _at(STEADY, 400), _log(ends_at=400, final_velocity=UNSETTLED))
    assert assessment.status is RunStatus.COMPLETED_MAX_ITER, assessment.error
    assert "iteration limit" not in (assessment.residual_note or "")
    assert assessment.iterations_requested is None


def test_p0390_iterlimit_an_unsteady_point_at_its_requested_count_stays_completed(tmp_path):
    """P0390-ITERLIMIT (FR-976): an unsteady point whose counter equals the requested 500.

    The time loop reaches its prescribed end, so the counter says nothing; with
    and without a log it stays COMPLETED_MAX_ITER. A mutant that applies the
    new status to an unsteady point fails this test.
    """
    loads = _at(UNSTEADY, 500, was="1575")
    assert "Requested solver iterations                 500" in loads
    assert _assess(tmp_path / "a", loads).status is RunStatus.COMPLETED_MAX_ITER
    with_log = _assess(tmp_path / "b", loads, _log(ends_at=500, final_velocity=UNSETTLED))
    assert with_log.status is RunStatus.COMPLETED_MAX_ITER, with_log.error


@pytest.mark.parametrize("sweep", ["2.0", "-2.0,0.0,2.0"], ids=["alone", "steady-job"])
def test_p0390_iterlimit_a_steady_run_through_the_run_layer(sweep, tmp_path, monkeypatch):
    """P0390-ITERLIMIT (FR-974, FR-977): a point alone and a steady job's points, through
     run_matrix.

    The stand-in solver prints the counter at 500 of 500 and writes a log whose
    residual stays above the convergence limit: every point and the job are
    MAX_ITER_REACHED, and each record or `points_ran` entry carries the
    iterations reached, the requested limit and the note naming it. A mutant
    that drops the note or the limit from the points of a steady job fails.
    """
    from tests.tier1_offline.test_matrix_run import HPC_PROFILE

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "loads_steady_26.120.txt").write_text(_at(STEADY, 500), encoding="utf-8")
    monkeypatch.setattr(local_run, "FIXTURES", fixtures)
    # The stand-in writes the log at its first EXPORT_LOG only; a steady job exports one per point.
    marker = '            printed = "-"' + chr(10)
    every_log = local_run.STUB.replace(marker, "            pass" + chr(10))
    assert every_log != local_run.STUB
    monkeypatch.setattr(local_run, "STUB", every_log)
    _, records, _ = local_run._run(
        tmp_path / "ws",
        monkeypatch,
        cluster=True,
        profile=HPC_PROFILE,
        prints=_log(ends_at=500, final_velocity=UNSETTLED),
        at_log="write",
        sweep=sweep,
    )
    (job,) = records
    assert job.status is RunStatus.MAX_ITER_REACHED, (job.status, job.error)
    entries = job.points_ran or [{"status": str(job.status), **job.model_dump(mode="json")}]
    assert len(entries) == len(sweep.split(","))
    for entry in entries:
        assert entry["status"] == "MAX_ITER_REACHED", entry
        assert entry["iterations"] == 500, entry
        assert entry["iterations_requested"] == 500, entry
        note = entry.get("residual_note") or ""
        assert "iteration limit (500)" in note, entry


def _rows(root: Path) -> list[dict]:
    return _read_record_rows(root / "runs.json")


def _limit_workspace(tmp_path: Path) -> CampaignWorkspace:
    """A collected workspace whose steady job and points carry what the real assessor wrote.

    The status, counter, requested limit and note are those of the package's
    LoadsAssessor reading a footer at 500 of 500 and a log whose residual is
    above the convergence limit, not a sentence written by hand.
    """
    read = _assess(tmp_path / "read", _at(STEADY, 500), _log(ends_at=500, final_velocity=UNSETTLED))
    assert read.status is RunStatus.MAX_ITER_REACHED, read.error
    workspace = grouped_workspace(tmp_path, mode="alone", logs=False, sims=("7002",))
    rows = _rows(workspace.root)
    fields = {
        "status": str(read.status),
        "iterations": read.iterations,
        "iterations_requested": read.iterations_requested,
        "residual_note": read.residual_note,
    }
    for row in rows:
        row.update(fields)
        if row.get("points_ran"):
            # The sweep writer records the limit and note only on the entries.
            row.pop("iterations_requested", None)
            row.pop("residual_note", None)
        for entry in row.get("points_ran") or []:
            entry.update(fields)
    workspace._replace_manifest(rows)
    return workspace


def test_p0390_iterlimit_readers_treat_it_as_an_ended_run(tmp_path, capsys):
    """P0390-ITERLIMIT (FR-977): post, status, show and resume read an ended, non-failed run.

    The post writes the products and one WARNING per point naming the limit,
    `run --resume` plans nothing, `status` counts the word apart, and `show`
    names it.
    """
    from tests.tier1_offline.test_p0370_s1_ran_missing_log import _resume

    workspace = _limit_workspace(tmp_path)
    rows = _rows(workspace.root)
    points = [entry for row in rows for entry in (row.get("points_ran") or [row])]
    code, said = pyfs(["post", MATRIX], workspace.root, capsys)
    assert code == 0, said
    folder = workspace.root / "post" / MATRIX
    products = json.loads((folder / "products.json").read_text("utf-8"))
    assert not [key for key in products["skipped"] if key.startswith("runs/")], products["skipped"]
    assert [name for name in products["products"] if name.startswith("polars/P7002")]
    log = (folder / "post.log").read_text("utf-8")
    lines = [line for line in log.splitlines() if "MAX_ITER_REACHED" in line]
    assert len(lines) == len(points), lines
    assert all("iteration limit (500)" in line for line in lines), lines
    code, said = pyfs(["status"], workspace.root, capsys)
    assert code == 0 and "MAX_ITER_REACHED" in said, said
    assert "FAILED" not in said, said
    code, said = pyfs(["show", "7002_1"], workspace.root, capsys)
    assert code == 0 and "MAX_ITER_REACHED" in said, said
    before = workspace.manifest_path.read_bytes()
    assert _resume(workspace) == []
    assert workspace.manifest_path.read_bytes() == before, "run --resume ran an ended point"


def test_p0390_iterlimit_a_0_38_manifest_reads_unchanged(tmp_path):
    """P0390-ITERLIMIT (FR-978): a record written before 0.39.0 is read as it was."""
    workspace = grouped_workspace(tmp_path, mode="alone", logs=False, sims=("7002",))
    rows = _rows(workspace.root)
    for row in rows:
        row["status"] = "COMPLETED_MAX_ITER"
        for entry in row.get("points_ran") or []:
            entry["status"] = "COMPLETED_MAX_ITER"
    workspace._replace_manifest(rows)
    before = workspace.manifest_path.read_bytes()
    read = workspace.read_manifest()
    assert {record.status for record in read} == {RunStatus.COMPLETED_MAX_ITER}
    assert workspace.manifest_path.read_bytes() == before


def test_p0390_iterlimit_a_forced_run_at_its_budget_keeps_the_0_38_status(tmp_path):
    """P0390-ITERLIMIT (FR-975): forced iterations run the whole budget by design.

    The threshold is off, so reaching 500 of 500 is not a stop that failed to
    settle; the evidence shows no such stop and the 0.38.0 status is kept.
    """
    forced = STEADY.replace(
        "Force solver to run all iterations           F",
        "Force solver to run all iterations           T",
    )
    assert forced != STEADY
    assessment = _assess(tmp_path, _at(forced, 500))
    assert assessment.status is RunStatus.COMPLETED_MAX_ITER


# --- the footer fallback (FR-974), the neither-counter control (FR-975)
# -----------------------------


def _counterless(log: str) -> str:
    """The log with every residual row's counter cell printed as a field of asterisks."""
    rows = re.compile(r"^\d+(?=[ \t])", re.MULTILINE)
    assert len(rows.findall(log)) == 4
    return rows.sub("*****", log)


@pytest.mark.parametrize("named", [False, True], ids=["found-by-content", "named-log"])
def test_p0390_iterlimit_a_log_without_a_counter_takes_the_footer_s(named, tmp_path):
    """P0390-ITERLIMIT (FR-974): the footer fallback, the footer supplies the counter only.

    The log's residual table prints no readable counter on any row and its final
    residual is above the limit; the loads footer states 500 of 500. The point is
    MAX_ITER_REACHED with the footer's counter, whether the log is found by its
    content or named by the assessor. A mutant without the fallback leaves it
    COMPLETED_MAX_ITER (found) or FAILED_INCOMPLETE_OUTPUT (named) and fails.
    """
    sim_dir = make_collected(tmp_path, "", text=_at(STEADY, 500))
    log = _counterless(_log(ends_at=500, final_velocity=UNSETTLED))
    make_collected(tmp_path, "", name="log.txt", text=log)
    assessor = LoadsAssessor("loads.txt", log_file="log.txt" if named else None)
    assessment = assessor(None, None, sim_dir)
    assert assessment.status is RunStatus.MAX_ITER_REACHED, assessment.error
    assert (assessment.iterations, assessment.iterations_requested) == (500, 500)
    assert assessment.log_file_used == "log.txt"
    assert "iteration limit (500)" in (assessment.residual_note or "")


def test_p0390_iterlimit_both_footer_routes_carry_the_log_s_times(tmp_path):
    """P0390-ITERLIMIT (FR-974): a log found by content and one named give the same times.

    The same counterless log at the limit is read once found by its content and
    once named by the assessor; both verdicts are MAX_ITER_REACHED and carry the
    times the log prints, ``solver_run_time_s`` (841.2 s here), ``solver_initialization_s``
    and ``time_steps``, equal on both routes. A fallback that skips the log's times
    leaves the run time None on the route found by content.
    """
    log = _counterless(_log(ends_at=500, final_velocity=UNSETTLED))
    got = {}
    for named in (False, True):
        sim_dir = make_collected(tmp_path / str(named), "", text=_at(STEADY, 500))
        make_collected(tmp_path / str(named), "", name="log.txt", text=log)
        assessor = LoadsAssessor("loads.txt", log_file="log.txt" if named else None)
        assessment = assessor(None, None, sim_dir)
        assert assessment.status is RunStatus.MAX_ITER_REACHED, assessment.error
        got[named] = (
            assessment.solver_run_time_s,
            assessment.solver_initialization_s,
            assessment.time_steps,
        )
    assert got[False] == got[True], got
    assert got[True][0] == pytest.approx(841.2), got


def test_p0390_iterlimit_neither_counter_nor_a_settled_counterless_log_gives_the_new_status(
    tmp_path,
):
    """P0390-ITERLIMIT (FR-975): without both pieces of evidence the 0.38.0 status stands.

    A loads footer with no counter is refused as 0.38.0 refuses it, a counterless
    log beside a footer short of the limit keeps the count judgment the same footer
    gets with no log, and a counterless log that settled decides nothing (0.38.0
    left it unread).
    """
    log = _counterless(_log(ends_at=500, final_velocity=UNSETTLED))
    no_counter = "\n".join(
        line for line in _at(STEADY, 500).splitlines() if COUNTER.strip() not in line
    )
    neither = _assess(tmp_path / "a", no_counter, log)
    assert neither.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, neither.status
    assert "Current solver iteration number" in (neither.error or "")
    short = _assess(tmp_path / "b", _at(STEADY, 400), log)
    assert short.status is _assess(tmp_path / "b0", _at(STEADY, 400)).status, short.status
    assert short.status is not RunStatus.MAX_ITER_REACHED and short.iterations == 400
    assert short.iterations_requested is None
    settled = _assess(tmp_path / "c", _at(STEADY, 500), _counterless(_log(ends_at=500)))
    assert settled.status is RunStatus.COMPLETED_MAX_ITER and settled.iterations_requested is None


def test_p0390_iterlimit_a_log_counter_present_and_different_is_still_refused(tmp_path):
    """P0390-ITERLIMIT (FR-974): the footer is the counter only when the log has none.

    A log that prints its counter at 499 beside a footer at 500 is refused as the
    log of another state; the footer does not replace a counter the log states.
    """
    assessment = _assess(tmp_path, _at(STEADY, 500), _log(ends_at=499, final_velocity=UNSETTLED))
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, assessment.status
    assert "499" in (assessment.error or "") and "500" in (assessment.error or "")
    assert assessment.iterations_requested is None


# --- precedence (FR-976) and the field written for MAX_ITER_REACHED alone (FR-974)
# -------------------

#: The batch point the precedence cases read; its job's log is its own cumulative copy.
FIRST = "V0300RE120AL+000"


def _the_word_owns_the_field(rows: list[dict]) -> None:
    """No row or point entry holds ``iterations_requested`` unless it is MAX_ITER_REACHED.

    And every POINT at that word holds it: a point record, or a steady job's entry.
    A steady job's own row carries its worst point's word and no limit of its own.
    """
    for row in rows:
        entries = row.get("points_ran") or []
        for unit in (row, *entries):
            if "iterations_requested" in unit:
                assert unit["status"] == "MAX_ITER_REACHED", unit
        for unit in entries or [row]:
            if unit["status"] == "MAX_ITER_REACHED":
                assert unit.get("iterations_requested") == 500, unit


def _solved_at_the_limit(
    tmp_path: Path, mode: str, *, refused: bool = False, walltime: bool = False, log: bool = True
) -> CampaignWorkspace:
    """A workspace whose submitted steady points wrote 500 of 500 and an unsettled log, collected.

    ``refused`` adds a G06 refusal line to every log, ``walltime`` leaves the
    first batch point's fired wall-clock stop, and without ``log`` the first
    batch point's log is deleted.
    """
    from tests.tier1_offline.test_g06_actuator_disc import PROFILE_REFUSALS

    workspace = grouped_workspace(tmp_path, mode=mode, logs=True, sims=("7002",), collect=False)
    line = f"{PROFILE_REFUSALS[2]}{tmp_path / 'disc.txt'}" + chr(10) if refused else ""
    for path in (workspace.root / "sims").rglob("*.txt"):
        if "scripts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if path.name.endswith(("_log.txt", ".cumulative-log.txt")):
            path.write_text(_log(ends_at=500, final_velocity=UNSETTLED) + line, encoding="utf-8")
        elif f"{COUNTER}312" in text:
            path.write_text(_at(text, 500), encoding="utf-8")
    first = [p for p in (workspace.root / "sims").rglob(f"DP-{FIRST}") if "batch" in p.parts]
    if walltime:
        (state,) = [folder / "actions" / "pfs_walltime_clock.json" for folder in first]
        state.parent.mkdir(parents=True, exist_ok=True)
        stop = {"fired": True, "steps": 3, "stopped_at": {"step": 3}}
        state.write_text(json.dumps(stop), encoding="utf-8")
    if not log:
        (folder,) = first
        (folder / f"{FIRST}.cumulative-log.txt").unlink()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        collect_once(workspace, interval=0.0, sleep=no_sleep)
    return workspace


def _first(workspace: CampaignWorkspace) -> dict:
    (row,) = [row for row in _rows(workspace.root) if row["run_id"].endswith(FIRST)]
    return row


def test_p0390_iterlimit_the_collected_point_at_the_limit_is_the_control(tmp_path):
    """P0390-ITERLIMIT (FR-974, FR-977): the same evidence, nothing overriding it, through collect.

    The control of the precedence cases below: the grouped collect records the
    point MAX_ITER_REACHED with the limit, and in the steady job every point.
    """
    batch = _solved_at_the_limit(tmp_path / "batch", "batch")
    row = _first(batch)
    assert (row["status"], row["iterations_requested"]) == ("MAX_ITER_REACHED", 500), row
    _the_word_owns_the_field(_rows(batch.root))
    alone = _solved_at_the_limit(tmp_path / "alone", "alone")
    (job,) = _rows(alone.root)
    assert {entry["status"] for entry in job["points_ran"]} == {"MAX_ITER_REACHED"}, job
    _the_word_owns_the_field(_rows(alone.root))


@pytest.mark.parametrize(
    ("override", "word"),
    [
        ({"refused": True}, "FAILED_SCRIPT"),
        ({"walltime": True}, "WALLTIME_REACHED"),
        ({"log": False}, "RAN_MISSING_LOG"),
    ],
    ids=["failed", "walltime", "missing-log"],
)
def test_p0390_iterlimit_a_stronger_word_takes_precedence_through_collect(override, word, tmp_path):
    """P0390-ITERLIMIT (FR-976, FR-974): FAILED_, WALLTIME_REACHED and RAN_MISSING_LOG outrank it.

    On the evidence of the control (500 of 500, unsettled), a G06 refusal line in
    the log, a fired wall-clock stop and a deleted log each give their own word,
    and the record then carries no ``iterations_requested``. A mutant that stamps
    the field before the log and clock verdicts fails the failed and walltime cases.
    """
    workspace = _solved_at_the_limit(tmp_path, "batch", **override)
    row = _first(workspace)
    assert row["status"] == word, row
    assert "iterations_requested" not in row, row
    _the_word_owns_the_field(_rows(workspace.root))


def test_p0390_iterlimit_a_steady_job_point_refused_by_its_log_carries_no_limit(tmp_path):
    """P0390-ITERLIMIT (FR-976): the points of a steady job, collected, under a refusal line."""
    workspace = _solved_at_the_limit(tmp_path, "alone", refused=True)
    (job,) = _rows(workspace.root)
    assert {entry["status"] for entry in job["points_ran"]} == {"FAILED_SCRIPT"}, job
    _the_word_owns_the_field(_rows(workspace.root))


@pytest.mark.parametrize(
    ("command", "word"),
    [
        (["mark-failed", "--reason", "read by hand", "--sims", "7002"], "FAILED_MARKED"),
        (["mark-converged", "--reason", "read by hand", "--sims", "7002"], "CONVERGED"),
    ],
    ids=["mark-failed", "mark-converged"],
)
def test_p0390_iterlimit_the_person_s_verdict_outranks_it(command, word, tmp_path, capsys):
    """P0390-ITERLIMIT (FR-976, FR-974): mark-failed and mark-converged outrank MAX_ITER_REACHED.

    The marked record keeps the word it had under ``marked`` and drops the limit,
    which is written for MAX_ITER_REACHED alone. A mutant that leaves the field
    on the marked record fails.
    """
    workspace = _solved_at_the_limit(tmp_path, "batch")
    assert _first(workspace)["status"] == "MAX_ITER_REACHED"
    code, said = pyfs([*command, "--apply"], workspace.root, capsys)
    assert code == 0, said
    row = _first(workspace)
    assert (row["status"], row["marked"]["from"]) == (word, "MAX_ITER_REACHED"), row
    assert "iterations_requested" not in row, row
    _the_word_owns_the_field(_rows(workspace.root))


def test_p0390_iterlimit_mark_converged_on_a_steady_job_s_points_drops_their_limit(
    tmp_path, capsys
):
    """P0390-ITERLIMIT (FR-976, FR-974): each marked point of a steady job drops its limit.

    The points of the job were MAX_ITER_REACHED with the limit; marked
    converged, each entry is CONVERGED with no limit, and the job's row takes
    its worst point's word. A mutant that leaves the field on the entry fails.
    """
    workspace = _solved_at_the_limit(tmp_path, "alone")
    argv = ["mark-converged", "--sims", "7002", "--reason", "read by hand", "--apply"]
    code, said = pyfs(argv, workspace.root, capsys)
    assert code == 0, said
    (job,) = _rows(workspace.root)
    assert job["status"] == "CONVERGED", job
    for entry in job["points_ran"]:
        assert (entry["status"], entry["marked"]["from"]) == ("CONVERGED", "MAX_ITER_REACHED")
        assert "iterations_requested" not in entry, entry
    _the_word_owns_the_field([job])


def _ran_at_the_limit(tmp_path: Path, monkeypatch, *, line: str = "") -> CampaignWorkspace:
    """A point run here by the stand-in solver: 500 of 500 and an unsettled log, plus ``line``."""
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "loads_steady_26.120.txt").write_text(_at(STEADY, 500), encoding="utf-8")
    monkeypatch.setattr(local_run, "FIXTURES", fixtures)
    workspace, _, _ = local_run._run(
        tmp_path / "ws",
        monkeypatch,
        cluster=False,
        profile=None,
        prints=_log(ends_at=500, final_velocity=UNSETTLED) + line,
        at_log="write",
        sweep="2.0",
    )
    return workspace


def _rebuilt(workspace: CampaignWorkspace, matrix: Path, capsys, out: str) -> list[dict]:
    old = time.time() - 3600
    for path in (workspace.root / "sims").rglob("*"):
        os.utime(path, (old, old))
    argv = ["rebuild", "--all-sims", "--matrix", str(matrix), "--out", out, "--apply"]
    code, said = pyfs(argv, workspace.root, capsys)
    assert code == 0, said
    return _read_record_rows(workspace.root / out)


def test_p0390_iterlimit_rebuild_keeps_the_person_s_verdict_without_the_limit(
    tmp_path, monkeypatch, capsys
):
    """P0390-ITERLIMIT (FR-976, FR-974): a rebuild of a marked point keeps CONVERGED, no limit.

    Control: rebuilt unmarked, the files give MAX_ITER_REACHED with the limit.
    Marked converged, the rebuild keeps the person's CONVERGED (FR-871) and
    drops the limit the files would give. A mutant whose kept verdict carries
    the field fails.
    """
    workspace = _ran_at_the_limit(tmp_path, monkeypatch)
    (row,) = _rows(workspace.root)
    assert (row["status"], row["iterations_requested"]) == ("MAX_ITER_REACHED", 500), row
    matrix = tmp_path / "ws" / "local.fs"
    (control,) = _rebuilt(workspace, matrix, capsys, "control.json")
    assert (control["status"], control["iterations_requested"]) == ("MAX_ITER_REACHED", 500)
    argv = ["mark-converged", "--sims", row["sim_id"], "--reason", "read by hand", "--apply"]
    code, said = pyfs(argv, workspace.root, capsys)
    assert code == 0, said
    (kept,) = _rebuilt(workspace, matrix, capsys, "kept.json")
    assert (kept["status"], kept["marked"]["from"]) == ("CONVERGED", "MAX_ITER_REACHED"), kept
    assert "iterations_requested" not in kept, kept
    assert any("support MAX_ITER_REACHED" in line for line in kept["warnings"]), kept


def test_p0390_iterlimit_a_local_point_refused_by_its_log_carries_no_limit(tmp_path, monkeypatch):
    """P0390-ITERLIMIT (FR-976, FR-974): the run layer's point path, a refusal line in its log.

    The stand-in solver prints 500 of 500 and an unsettled log carrying a G06
    refusal line: the point is FAILED_SCRIPT and its record has no limit. A
    mutant that writes the assessor's limit whatever the final status fails.
    """
    from tests.tier1_offline.test_g06_actuator_disc import PROFILE_REFUSALS

    line = f"{PROFILE_REFUSALS[2]}{tmp_path / 'disc.txt'}" + chr(10)
    workspace = _ran_at_the_limit(tmp_path, monkeypatch, line=line)
    (record,) = workspace.read_manifest()
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    assert record.iterations_requested is None
    _the_word_owns_the_field(_rows(workspace.root))


# --- the readers of FR-977 the first writing left out -----------------------------------------


def test_p0390_iterlimit_the_cost_estimate_reads_an_ended_run(tmp_path):
    """P0390-ITERLIMIT (FR-977): the cost view counts it as time to an answer, not excluded.

    Control: the same records as WALLTIME_REACHED are excluded.
    """
    from pyflightstream.qa.cost import cost_view

    workspace = _limit_workspace(tmp_path)
    cells = list(cost_view(workspace).cells.values())
    assert cells and sum(cell.run_count for cell in cells) == len(_rows(workspace.root))
    assert sum(cell.excluded_count for cell in cells) == 0, cells
    rows = _rows(workspace.root)
    for row in rows:
        row["status"] = "WALLTIME_REACHED"
        for entry in row.get("points_ran") or []:
            entry.pop("iterations_requested", None)
        row.pop("iterations_requested", None)
    workspace._replace_manifest(rows)
    walltime = list(cost_view(workspace).cells.values())
    assert sum(cell.excluded_count for cell in walltime) == len(rows), walltime


def test_p0390_iterlimit_delete_sims_reads_an_ended_run(tmp_path, capsys):
    """P0390-ITERLIMIT (FR-977): delete-sims takes it without --force, as an ended run.

    Control: the same simulation SUBMITTED is refused without --force.
    """
    workspace = _limit_workspace(tmp_path)
    code, said = pyfs(["delete-sims", "7002"], workspace.root, capsys)
    assert code == 0, said
    rows = _rows(workspace.root)
    for row in rows:
        row["status"] = "SUBMITTED"
        row.pop("iterations_requested", None)
    workspace._replace_manifest(rows)
    code, said = pyfs(["delete-sims", "7002"], workspace.root, capsys)
    assert code != 0 and "SUBMITTED" in said, said


def test_p0390_iterlimit_the_grouped_collect_reads_an_ended_run(tmp_path):
    """P0390-ITERLIMIT (FR-977): collected, not failed; a second collect leaves it as it is."""
    workspace = _solved_at_the_limit(tmp_path, "batch")
    before = workspace.manifest_path.read_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = collect_once(workspace, interval=0.0, sleep=no_sleep)
    outcomes = [*report.collected, *report.waiting, *report.failed]
    assert not [o for o in outcomes if o.run_id.endswith(FIRST)], outcomes
    assert workspace.manifest_path.read_bytes() == before
    assert _first(workspace)["status"] == "MAX_ITER_REACHED"


# --- FR-978: the 0.38.0 reader refuses the new value ------------------------------------------

#: The RunStatus member set of the published 0.38.0 package, recorded here (FR-46).
RUN_STATUS_0380 = frozenset(
    {
        "CONVERGED",
        "COMPLETED_MAX_ITER",
        "FAILED_EXECUTION",
        "FAILED_SCRIPT",
        "FAILED_INCOMPLETE_OUTPUT",
        "FAILED_DIVERGED",
        "WALLTIME_REACHED",
        "SUBMITTED",
        "FAILED_MARKED",
        "RAN_MISSING_LOG",
    }
)


def test_p0390_iterlimit_a_0_38_reader_refuses_the_new_value(tmp_path):
    """P0390-ITERLIMIT (FR-978, FR-46): the 0.38.0 member set reads none of MAX_ITER_REACHED.

    The set grows by exactly the new value, and a record validated against the
    0.38.0 set (a closed enum, as the 0.38.0 reader is) is refused when it holds
    it; control: a record of COMPLETED_MAX_ITER validates.
    """
    import enum

    import pydantic

    assert {member.value for member in RunStatus} == RUN_STATUS_0380 | {"MAX_ITER_REACHED"}
    old = enum.Enum("RunStatus0380", {name: name for name in sorted(RUN_STATUS_0380)})
    reader = pydantic.create_model("Record0380", status=(old, ...))
    row = _rows(_limit_workspace(tmp_path).root)[0]
    with pytest.raises(pydantic.ValidationError, match="MAX_ITER_REACHED"):
        reader.model_validate({"status": row["status"]})
    assert reader.model_validate({"status": "COMPLETED_MAX_ITER"}).status.value == (
        "COMPLETED_MAX_ITER"
    )
