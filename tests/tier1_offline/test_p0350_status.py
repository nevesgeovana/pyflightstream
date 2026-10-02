"""Tier 1 offline: ``pyfs-matrix status`` and the ledger under it (0.35.0).

FR-379 to FR-385 and FR-388: one row per polar with its mixed counts, the
selection flags, the planned points and the freshness footer, the effective
record of each datapoint read from one home, the read-only guarantee, the
recorded words printed as recorded, and the machine forms. Every workspace is a
synthetic ``tmp_path`` tree; nothing runs a solver.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-379, FR-380, FR-381, FR-382, FR-383, FR-384, FR-385, FR-388.

from __future__ import annotations

import csv
import io
import json
import os
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.run import cli as matrix_cli
from pyflightstream.run._continuation_frame import latest_record_of_point as run_rule
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace._effective import latest_record_of_point
from pyflightstream.workspace.ledger import PLANNED, STATUS_COLUMNS, listed_sims, read_ledger

MATRIX = "l1_g6"
CAMPAIGN = "camp"


def _record(sim: str, name: str, status: RunStatus, **fields: object) -> dict:
    record = RunRecord(
        run_id=f"{CAMPAIGN}/sim_{sim}/{name}",
        sim_id=sim,
        matrix_stem=MATRIX,
        sweep_name="M144AL+sweep",
        fs_version_requested="26.124",
        package_version="0.35.0",
        script_sha256="c" * 64,
        recipe="steady",
        raw_flag=False,
        status=status,
        outputs=[],
        script_path=None,
        inputs_sha256={},
    )
    return record.model_copy(update=fields).model_dump(mode="json")


def _plan_point(sim: str, name: str, alpha: float) -> dict:
    return {
        "run_id": f"{CAMPAIGN}/sim_{sim}/{name}",
        "sim_id": sim,
        "point": {"alpha": alpha},
        "script_name": None,
        "status": "READY",
    }


def _rows() -> list[dict]:
    """The manifest of the fixture, in file order, each row commented by what it tests."""
    return [
        # 2006: a steady JOB over three points, one diverged; the plan names a fourth.
        _record(
            "2006",
            "sweep",
            RunStatus.FAILED_DIVERGED,
            points_ran=[
                {"tag": "M144AL-040", "point": {"alpha": -4.0}, "status": "CONVERGED"},
                {"tag": "M144AL+000", "point": {"alpha": 0.0}, "status": "CONVERGED"},
                {"tag": "M144AL+040", "point": {"alpha": 4.0}, "status": "FAILED_DIVERGED"},
            ],
        ),
        # 2008: an unsteady point stopped by the clock, then CONTINUED to CONVERGED,
        # then a refused continuation that never started (a note, not a state).
        _record("2008", "M144AL+000", RunStatus.WALLTIME_REACHED, point={"alpha": 0.0}),
        _record(
            "2008",
            "r20261002-101010/M144AL+000",
            RunStatus.CONVERGED,
            point={"alpha": 0.0},
            continues=f"{CAMPAIGN}/sim_2008/M144AL+000",
        ),
        _record(
            "2008",
            "r20261002-111111/M144AL+000",
            RunStatus.FAILED_SCRIPT,
            point={"alpha": 0.0},
            script_sha256="",
            recipe=None,
            error="the saved simulation is gone",
        ),
        # 2009: marked failed after it converged.
        _record(
            "2009",
            "M144AL+000",
            RunStatus.FAILED_MARKED,
            point={"alpha": 0.0},
            marked={"from": "CONVERGED", "at": "2026-10-02T10:00:00+00:00", "reason": "wrong"},
        ),
        # A delete-sims note: not a datapoint.
        {
            "run_id": "deleted/sim_2010/20261002-090000",
            "deleted_sim": "2010",
            "deleted_at": "2026-10-02T09:00:00+00:00",
            "deleted_run_ids": [f"{CAMPAIGN}/sim_2010/M144AL+000"],
        },
        # 2011: a steady job SUBMITTED, no point ran yet; it stands for both its points.
        _record(
            "2011",
            "sweep",
            RunStatus.SUBMITTED,
            submission={
                "points_by_tag": {"M144AL+000": {"alpha": 0.0}, "M144AL+040": {"alpha": 4.0}},
                "job": {"label": f"{MATRIX}_b1", "kind": "batch"},
            },
        ),
        # 10001: numbered after 2006 as a number, before it as text.
        _record("10001", "M144AL+000", RunStatus.CONVERGED, point={"alpha": 0.0}),
    ]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / CAMPAIGN
    CampaignWorkspace.init(root)
    (root / "runs.json").write_text(json.dumps(_rows(), indent=1) + "\n", encoding="utf-8")
    matrix = root / f"{MATRIX}.fs"
    matrix.write_text("POL,SIM\n", encoding="utf-8")
    plan = {
        "campaign": CAMPAIGN,
        "matrix_sha256": file_sha256(matrix),
        "points": [
            _plan_point("2006", "M144AL-040", -4.0),
            _plan_point("2006", "M144AL+000", 0.0),
            _plan_point("2006", "M144AL+040", 4.0),
            _plan_point("2006", "M144AL+080", 8.0),
            _plan_point("2007", "M144AL-040", -4.0),
            _plan_point("2007", "M144AL+040", 4.0),
            _plan_point("2008", "M144AL+000", 0.0),
            _plan_point("2011", "M144AL+000", 0.0),
            _plan_point("2011", "M144AL+040", 4.0),
        ],
    }
    post = root / "post" / MATRIX
    post.mkdir(parents=True, exist_ok=True)
    (post / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    products = {
        "complete": True,
        "products": {},
        "provenance": {f"{CAMPAIGN}/sim_2006/sweep": "provenance/a.json"},
    }
    (post / "products.json").write_text(json.dumps(products) + "\n", encoding="utf-8")
    return root


def _status(root: Path, capsys: pytest.CaptureFixture[str], *flags: str) -> tuple[int, str, str]:
    code = matrix_cli.main(["status", "--workspace", str(root), *flags])
    out, err = capsys.readouterr()
    return code, out, err


def _table(out: str) -> list[list[str]]:
    """The table's rows split on two or more spaces, the heading first, the footer left out."""
    lines = out.splitlines()
    heading = next(index for index, line in enumerate(lines) if line.startswith("SIM"))
    rows = []
    for line in lines[heading:]:
        if " polar(s), " in line or " datapoint(s): " in line:
            break
        rows.append([cell for cell in line.split("  ") if cell.strip()])
    return [[cell.strip() for cell in row] for row in rows]


def test_status_prints_one_row_per_polar_in_matrix_then_numeric_order(workspace, capsys):
    """P0350-STATUS-POLAR (FR-379): one row per polar with its six columns, R1 and R4."""
    code, out, _ = _status(workspace, capsys)
    assert code == 0
    table = _table(out)
    assert table[0] == ["SIM", "POLAR", "SWEEP", "POINTS", "MATRIX", "STATUS"]
    # R4: by matrix, then by simulation id as a number (10001 after 2011, not before 2006).
    assert [row[0] for row in table[1:]] == ["2006", "2007", "2008", "2009", "2011", "10001"]
    rows = {row[0]: row for row in table[1:]}
    assert rows["2006"][1:5] == ["M144AL+sweep", "alpha", "3/4", MATRIX]
    # A polar only planned has no recorded sweep name; the one its points imply.
    assert rows["2007"][1:5] == ["M144AL+sweep", "alpha", "0/2", MATRIX]
    # R1: a one-point polar sweeps what its name marks swept.
    assert rows["10001"][1:5] == ["M144AL+sweep", "alpha", "1", MATRIX]


def test_a_mixed_polar_counts_each_word_and_a_uniform_one_states_its_word(workspace, capsys):
    """P0350-STATUS-MIXED (FR-379): R2 one word when all agree, R3 the counts of a mixed polar."""
    _, out, _ = _status(workspace, capsys)
    rows = {row[0]: row for row in _table(out)[1:]}
    # R3: concluded, then failed, then submitted or running, then planned, each a number.
    assert rows["2006"][5] == "CONVERGED 2, FAILED_DIVERGED 1, planned 1"
    # R2: every datapoint the same word.
    assert rows["2011"][5] == "SUBMITTED"
    assert rows["10001"][5] == "CONVERGED"
    totals = next(line for line in out.splitlines() if " polar(s), " in line)
    assert totals == (
        "6 polar(s), 11 datapoint(s): CONVERGED 4, FAILED_DIVERGED 1, FAILED_MARKED 1, "
        "SUBMITTED 2, planned 3"
    )


def test_status_selects_by_sims_matrix_status_and_failed(workspace, capsys):
    """P0350-STATUS-SELECT (FR-380): R1 to R4."""
    _, plain, _ = _status(workspace, capsys, "--sims", "2006,2007")
    _, bracketed, _ = _status(workspace, capsys, "--sims", "[2006, 2007]")
    assert [row[0] for row in _table(plain)[1:]] == ["2006", "2007"]
    assert _table(bracketed) == _table(plain)
    assert listed_sims("[2006,2007]") == listed_sims("2006,2007") == ["2006", "2007"]
    # R2: a stem, its file name, or its path in a home all name the matrix.
    for name in (MATRIX, f"{MATRIX}.fs", f"inputs/matrices/{MATRIX}.fs"):
        _, out, _ = _status(workspace, capsys, "--matrix", name)
        assert len(_table(out)) == 7
    _, out, _ = _status(workspace, capsys, "--matrix", "another")
    assert len(_table(out)) == 1
    # R3: a recorded word, repeatable, with a trailing *; --failed.
    _, out, _ = _status(workspace, capsys, "--status", "FAILED_DIVERGED")
    assert [row[0] for row in _table(out)[1:]] == ["2006"]
    _, out, _ = _status(workspace, capsys, "--status", "FAILED_*")
    assert [row[0] for row in _table(out)[1:]] == ["2006", "2009"]
    _, out, _ = _status(workspace, capsys, "--status", "SUBMITTED", "--status", "WALLTIME_REACHED")
    assert [row[0] for row in _table(out)[1:]] == ["2011"]
    _, out, _ = _status(workspace, capsys, "--failed")
    assert [row[0] for row in _table(out)[1:]] == ["2006", "2009"]
    code, _, err = _status(workspace, capsys, "--status", "SUCCESS")
    assert code == 2 and "status (CLI: --status)" in err and "'SUCCESS'" in err
    # R4: an id that names nothing is named on standard error; the others print.
    code, out, err = _status(workspace, capsys, "--sims", "2006,9999")
    assert code == 0
    assert "sims (CLI: --sims): simulation 9999 holds no record and no planned point" in err
    assert [row[0] for row in _table(out)[1:]] == ["2006"]
    # The exit status of an id that matches nothing is open (FR-380 R4); today's is 1.
    code, _, err = _status(workspace, capsys, "--sims", "9999")
    assert code == 1 and "9999" in err


def test_planned_points_are_counted_in_lower_case_and_the_footer_states_freshness(
    workspace, capsys
):
    """P0350-STATUS-PLANNED (FR-382): R1 to R4."""
    _, out, _ = _status(workspace, capsys)
    rows = {row[0]: row for row in _table(out)[1:]}
    # R1 and R3: a polar only planned reads `planned`; a partly planned one counts both.
    assert rows["2007"][5] == PLANNED == "planned"
    assert rows["2006"][3] == "3/4" and "planned 1" in rows["2006"][5]
    # The job SUBMITTED for its row carries both its points, so neither is planned.
    assert rows["2011"][3] == "2/2"
    # R2: no recorded status word is lower case.
    assert all(status.value.isupper() for status in RunStatus)
    assert PLANNED not in {status.value for status in RunStatus}
    # R4: the plan is the matrix's on disk; the post is complete and indexes 1 of 7 runs.
    assert f"plan/{MATRIX}: made from the matrix on disk" in out
    assert f"post/{MATRIX}: written " in out and ", complete, 6 recorded run(s)" in out
    (workspace / f"{MATRIX}.fs").write_text("POL,SIM,ALPHA\n", encoding="utf-8")
    products = workspace / "post" / MATRIX / "products.json"
    products.write_text(json.dumps({"complete": False, "provenance": {}}), encoding="utf-8")
    _, out, _ = _status(workspace, capsys)
    assert f"plan/{MATRIX}: made from another revision of the matrix" in out
    assert "NOT complete, 7 recorded run(s) not yet posted" in out


def test_each_datapoint_is_counted_once_by_its_effective_record(workspace):
    """P0350-QUERY-EFFECTIVE (FR-381): R1 to R6."""
    ledger = read_ledger(workspace)
    points = {(row["sim"], row["point"]): row for row in ledger.points()}
    # R1: the steady job is three datapoints, each with its own status.
    assert [points[("2006", name)]["status"] for name in ("M144AL-040", "M144AL+000")] == [
        "CONVERGED",
        "CONVERGED",
    ]
    assert points[("2006", "M144AL+040")]["status"] == "FAILED_DIVERGED"
    # R2, R3, R5: the continued point is ONE datapoint, the continuation's, by name;
    # the refused continuation after it is a note and does not replace it.
    assert [key for key in points if key[0] == "2008"] == [("2008", "M144AL+000")]
    assert points[("2008", "M144AL+000")]["status"] == "CONVERGED"
    assert points[("2008", "M144AL+000")]["run_id"].endswith("r20261002-101010/M144AL+000")
    assert any(note.get("kind") == "refused continuation" for note in ledger.notes)
    # R4: the delete-sims note is no datapoint.
    assert not any(key[0] == "2010" for key in points)
    assert any(note.get("deleted_sim") == "2010" for note in ledger.notes)
    # R6: the run layer reads the rule from the workspace home, not a copy of its own.
    assert run_rule is latest_record_of_point
    records = [RunRecord.model_validate(row) for row in _rows() if "deleted_sim" not in row]
    latest = latest_record_of_point(records, "2008", "M144AL+000")
    assert latest is not None and latest.status is RunStatus.CONVERGED
    card = ledger.card(points[("2008", "M144AL+000")]["run_id"])
    assert card is not None and card["continues"] == f"{CAMPAIGN}/sim_2008/M144AL+000"


def test_status_prints_recorded_words_as_recorded(workspace, capsys):
    """P0350-QUERY-RECORDED-WORDS (FR-384): R1, R3 and R4."""
    _, out, _ = _status(workspace, capsys, "--points")
    table = _table(out)
    heading = table[0]
    assert heading[:5] == ["SIM", "POINT", "MATRIX", "STATUS", "WAS"]
    rows = {(row[0], row[1]): row for row in table[1:]}
    # R3: the marked verdict as recorded, with the status it replaced beside it.
    assert rows[("2009", "M144AL+000")][3:5] == ["FAILED_MARKED", "CONVERGED"]
    # R1: every word printed is a recorded word or the derived one.
    words = {row[3] for row in table[1:]}
    assert words <= {status.value for status in RunStatus} | {PLANNED}
    assert "WALLTIME_REACHED" not in words  # superseded by its continuation, not renamed
    # R4: a planned point reads `planned`, a form no recorded word takes.
    assert rows[("2006", "M144AL+080")][3] == "planned"
    # The batch job's points say where they run.
    assert rows[("2011", "M144AL+000")][-1] == f"{MATRIX}_b1"


def _tree(root: Path) -> dict[str, tuple[bool, int, int]]:
    """Every path under ``root``: whether a folder, its size and its modification time."""
    found = {}
    for folder, dirs, files in os.walk(root):
        for name in dirs + files:
            path = Path(folder) / name
            info = path.lstat()
            found[path.relative_to(root).as_posix()] = (
                path.is_dir(),
                0 if path.is_dir() else info.st_size,
                info.st_mtime_ns,
            )
    return found


def _leaves_the_tree_as_it_was(root: Path, action: Callable[[], object]) -> bool:
    before = _tree(root)
    time.sleep(0.02)
    action()
    return _tree(root) == before


def test_status_writes_nothing_and_takes_no_lock(workspace, capsys):
    """P0350-QUERY-READ-ONLY (FR-383): R1 to R4, with a planted writer as the control."""
    # A held lock of a campaign writing now: the query neither waits on it nor touches it.
    lock = workspace / "runs.json.lock"
    lock.write_text('{"pid": 1, "token": "held"}', encoding="utf-8")
    (workspace / "sims" / "sim_2009.zip").write_bytes(b"PK\x05\x06" + b"\0" * 18)
    rows = json.loads((workspace / "runs.json").read_text(encoding="utf-8"))
    rows.append({"run_id": f"{CAMPAIGN}/sim_2012/M144AL+000", "sim_id": "2012", "status": "X"})
    (workspace / "runs.json").write_text(json.dumps(rows), encoding="utf-8")
    calls = (
        (),
        ("--points",),
        ("--json",),
        ("--csv",),
        ("--sims", "2006,9999"),
        ("--matrix", MATRIX, "--failed"),
    )
    started = time.monotonic()
    for flags in calls:

        def query(flags: tuple[str, ...] = flags) -> None:
            assert _status(workspace, capsys, *flags)[0] in (0, 1)

        assert _leaves_the_tree_as_it_was(workspace, query), flags
    assert time.monotonic() - started < 30
    # R4: the row it cannot read is named by its position and run id; the others print.
    _, out, err = _status(workspace, capsys)
    assert f"runs.json row 9 (run {CAMPAIGN}/sim_2012/M144AL+000) cannot be read" in err
    assert len(_table(out)) == 7
    # R3: the compacted simulation is found where it is and left compacted.
    assert read_ledger(workspace).sim_folders("2009") == ["sims/sim_2009.zip"]
    assert not (workspace / "sims" / "sim_2009").exists()

    # THE CONTROL: the same comparison around a query that also writes must fail.
    def planted() -> None:
        _status(workspace, capsys)
        (workspace / "logs").mkdir(exist_ok=True)
        (workspace / "logs" / "activity.log").write_text("status\n", encoding="utf-8")

    assert not _leaves_the_tree_as_it_was(workspace, planted)
    assert not _leaves_the_tree_as_it_was(workspace, lambda: os.utime(lock))


def test_json_and_csv_print_the_table_rows_and_nothing_else(workspace, capsys):
    """P0350-QUERY-MACHINE (FR-385): R1 to R4."""
    _, table_out, _ = _status(workspace, capsys)
    code, out, err = _status(workspace, capsys, "--json")
    assert code == 0
    document = json.loads(out)  # R1: stdout is the document alone
    assert document["schema"] == "pyfs-status/1"
    assert document["workspace"] == str(workspace.resolve())
    assert document["read_at"].endswith("+00:00")
    assert set(document["sources"]) == {
        "runs.json",
        f"post/{MATRIX}/plan.json",
        f"post/{MATRIX}/products.json",
    }
    assert "status" in err  # the opening block is on stderr
    table = _table(table_out)
    # R4: the same rows, in the same order, with the same cells.
    assert [[str(row[key]) for key in STATUS_COLUMNS] for row in document["rows"]] == table[1:]
    code, out, _ = _status(workspace, capsys, "--csv")
    assert code == 0
    assert "\r" not in out  # R3: LF line ends
    parsed = list(csv.reader(io.StringIO(out)))
    assert parsed[0] == list(STATUS_COLUMNS)
    assert parsed[1:] == table[1:]
    _, out, _ = _status(workspace, capsys, "--csv", "--points")
    points = list(csv.reader(io.StringIO(out)))
    assert len(points) == 1 + 11


def test_the_python_mirror_returns_plain_rows(workspace):
    """P0350-QUERY-PYTHON (FR-388): R1 (status, points, card) and R3, the rows the CLI prints."""
    ledger = read_ledger(workspace)
    rows = ledger.status(sims=["2006"])
    assert json.loads(json.dumps(rows)) == rows  # plain dictionaries, nothing else
    assert rows[0]["counts"] == {"CONVERGED": 2, "FAILED_DIVERGED": 1, "planned": 1}
    assert rows[0]["recorded"] == 3 and rows[0]["planned"] == 4
    points = ledger.points(sims=["2006"], statuses=["planned"])
    assert [row["point"] for row in points] == ["M144AL+080"]
    assert json.loads(json.dumps(ledger.document(rows)))["rows"] == rows


def test_a_continued_run_is_not_counted_even_after_its_continuation(tmp_path):
    """P0350-QUERY-EFFECTIVE (FR-381): R2, the chain read from what the continuation states.

    A merged manifest can carry the continued run AFTER its continuation in file
    order; the run it continues is still not the point's state.
    """
    root = tmp_path / CAMPAIGN
    root.mkdir()
    stopped = _record("2008", "M144AL+000", RunStatus.WALLTIME_REACHED, point={"alpha": 0.0})
    continued = _record(
        "2008",
        "r20261002-101010/M144AL+000",
        RunStatus.CONVERGED,
        point={"alpha": 0.0},
        continues=f"{CAMPAIGN}/sim_2008/M144AL+000",
    )
    (root / "runs.json").write_text(json.dumps([continued, stopped]), encoding="utf-8")
    rows = read_ledger(root).points()
    assert [(row["point"], row["status"]) for row in rows] == [("M144AL+000", "CONVERGED")]


def test_a_planned_point_whose_record_cannot_be_read_is_not_called_planned(workspace, capsys):
    """P0350-STATUS-PLANNED (FR-382): R1, a point is planned only when NO row records it.

    The rule's one home (``planned_points_without_record``) reads every row that
    names a run, read or not: a row this version cannot read still says the
    point ran, so the point is named as unreadable rather than counted planned.
    """
    rows = json.loads((workspace / "runs.json").read_text(encoding="utf-8"))
    rows.append({"run_id": f"{CAMPAIGN}/sim_2007/M144AL+040", "sim_id": "2007", "status": "X"})
    (workspace / "runs.json").write_text(json.dumps(rows), encoding="utf-8")
    _, out, err = _status(workspace, capsys, "--sims", "2007")
    assert _table(out)[1][3:] == ["0/2", MATRIX, "planned"]
    assert read_ledger(workspace).status(sims=["2007"])[0]["counts"] == {"planned": 1}
    assert f"(run {CAMPAIGN}/sim_2007/M144AL+040) cannot be read" in err
