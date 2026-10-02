"""Synthetic, offline evidence for history, diff and the plain Python query API."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

from pyflightstream.run.cli import main
from pyflightstream.workspace import RunRecord, RunStatus
from pyflightstream.workspace.ledger import (
    activity_rows,
    additional_rows,
    diff,
    history,
    point_card,
    point_rows,
    post_log_groups,
    read_ledger,
    status_rows,
    trace_product,
)

RUN = "sample/sim_2006/A0"
NEXT = "sample/sim_2006/r20261002-120000/A0"
STAMP = "20261001-120000"


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _record(run_id: str = RUN, **fields: object) -> dict:
    row = RunRecord(
        run_id=run_id,
        sim_id="2006",
        matrix_stem="sample",
        point={"alpha": 0.0},
        fs_version_requested="26.124",
        package_version="0.35.0",
        recipe="steady",
        raw_flag=False,
        status=RunStatus.CONVERGED,
        outputs=[],
        script_sha256="",
    ).model_dump(mode="json")
    return {**row, **fields}


def _script(root: Path, name: str, text: str) -> tuple[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return name, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    old_path, old_sha = _script(
        tmp_path,
        f"sims/sim_2006/datapoints/DP-A0/archive/{STAMP}/run.txt",
        "SET_PLOT_TYPE\nold_plot\nSOLVER_SET_AOA\n0\n",
    )
    new_path, new_sha = _script(
        tmp_path, "sims/sim_2006/scripts/run.txt", "SET_PLOT_TYPE\nnew_plot\nSOLVER_SET_AOA\n2\n"
    )
    old = _record(
        status="WALLTIME_REACHED",
        package_version="0.34.0",
        script_path=old_path,
        script_sha256=old_sha,
        inputs_sha256={"pproc/p1.toml": "a" * 64},
        solver_setup={"flags": {"wake": {"provenance": "explicit", "value": False}}},
        flight_condition={"mach": 0.1},
    )
    new = _record(
        NEXT,
        continues=RUN,
        point={"alpha": 2.0},
        script_path=new_path,
        script_sha256=new_sha,
        inputs_sha256={"pproc/p1.toml": "b" * 64},
        solver_setup={"flags": {"wake": {"provenance": "explicit", "value": True}}},
        flight_condition={"mach": 0.2},
    )
    _write(tmp_path / "runs.json", [old, new])
    _write(tmp_path / "archive" / f"runs-{STAMP}.json", [old])
    _write(tmp_path / "sims/sim_2006/datapoints/DP-A0/archive" / STAMP / "record.json", old)
    (tmp_path / "inputs/pproc").mkdir(parents=True)
    (tmp_path / "inputs/pproc/p1.toml").write_text('plot = "new_plot"\n', encoding="utf-8")
    _write(
        tmp_path / "additional.json",
        [{"extraction_id": "extra", "status": "COMPLETED", "custom": {"count": 3}, "run_id": NEXT}],
    )
    return tmp_path


def _call(root: Path, capsys, verb: str, *args: str) -> tuple[int, str, str]:
    code = main([verb, *args, "--workspace", str(root)])
    out, err = capsys.readouterr()
    return code, out, err


def _tree(root: Path) -> dict[str, tuple[bytes | None, int]]:
    """Every path under ``root`` with its bytes (None for a folder) and modification time."""
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes() if path.is_file() else None,
            path.lstat().st_mtime_ns,
        )
        for path in root.rglob("*")
    }


def test_history_reads_present_archived_and_datapoint_records(workspace, capsys):
    """P0350-QUERY-HISTORY FR-390: every attempt, stamp and continuation stays visible."""
    code, out, _ = _call(workspace, capsys, "history", "2006", "--json")
    rows = json.loads(out)["rows"]
    assert code == 0 and len(rows) == 4
    assert {row["archive_stamp"] for row in rows} == {None, STAMP}
    assert any("datapoints/DP-A0/archive/" in row["source"] for row in rows)
    assert rows[-1]["continues"] == RUN and rows[-1]["run_id"] == NEXT
    assert rows[-1]["datapoint_archives"][0]["stamp"] == STAMP
    assert {row["status"] for row in rows} == {"WALLTIME_REACHED", "CONVERGED"}
    assert history(workspace, "A0") == rows
    assert len(point_rows(workspace)) == 1
    assert point_card(workspace, RUN) is None
    job = _record(
        "sample/sim_2006/sweep",
        status="SUBMITTED",
        submission={"points_by_tag": {"A4": {"alpha": 4.0}}},
    )
    _write(workspace / "archive/runs-20260929-120000.json", [job])
    assert history(workspace, "A4")[0]["record"]["point"] == {"alpha": 4.0}


def test_diff_compares_recorded_fields_and_attributes_script_lines(workspace, capsys):
    """P0350-QUERY-DIFF FR-391: stamped run ids and rebuild's input-attributed comparison."""
    code, out, _ = _call(workspace, capsys, "diff", f"{RUN}@{STAMP}", NEXT, "--json")
    rows = json.loads(out)["rows"]
    fields = {row["field"]: row for row in rows}
    assert code == 0
    assert fields["package_version"]["a"] == "0.34.0"
    assert fields["package_version"]["b"] == "0.35.0"
    assert fields["solver_setup.flags.wake.value"]["a"] is False
    assert fields["flight_condition.mach"]["b"] == 0.2
    assert fields["point.alpha"]["b"] == 2.0
    assert fields["status"]["a"] == "WALLTIME_REACHED"
    assert fields["inputs_sha256.pproc/p1.toml"]["b"] == "b" * 64
    detail = fields["script_comparison"]["detail"]
    assert "line 1" in detail and "inputs/pproc/p1.toml" in detail
    assert "old_plot" in detail and "new_plot" in detail
    assert diff(workspace, f"{RUN}@{STAMP}", NEXT) == rows


def test_history_has_its_own_batch_transparency_test(workspace, capsys):
    """P0350-BATCH-TRANSPARENT FR-372: pyfs-matrix history in a running batch and home."""
    home = workspace / "sims/sim_2006"
    batch = workspace / "sims/batch/sample_b1/sim_2006"
    batch.parent.mkdir(parents=True)
    home.rename(batch)
    for folder in (batch, home):
        code, out, _ = _call(workspace, capsys, "history", "2006", "--json")
        rows = json.loads(out)["rows"]
        assert code == 0 and len(rows) == 4
        assert all(row["sim_folders"] == [folder.relative_to(workspace).as_posix()] for row in rows)
        assert any("record.json" in row["source"] for row in rows)
        if folder == batch:
            batch.rename(home)


def test_diff_has_its_own_batch_transparency_test(workspace, capsys):
    """P0350-BATCH-TRANSPARENT FR-372: pyfs-matrix diff in a running batch and home."""
    home = workspace / "sims/sim_2006"
    batch = workspace / "sims/batch/sample_b1/sim_2006"
    batch.parent.mkdir(parents=True)
    home.rename(batch)
    for folder in (batch, home):
        code, out, _ = _call(workspace, capsys, "diff", f"{RUN}@{STAMP}", NEXT, "--json")
        changes = {row["field"]: row for row in json.loads(out)["rows"]}
        comparison = changes["script_comparison"]
        assert code == 0 and "line 1" in comparison["detail"]
        assert comparison["b"].startswith(folder.relative_to(workspace).as_posix() + "/")
        if folder == batch:
            batch.rename(home)


def test_queries_write_nothing_and_keep_the_additional_register(workspace, capsys):
    """P0350-QUERY-READ-ONLY FR-383; P0350-QUERY-ADDITIONAL FR-393: plant control bytes."""
    (workspace / "control.bin").write_bytes(b"do not change\x00\xff")
    (workspace / "runs.json.lock").write_bytes(b"a running writer owns this")
    before = _tree(workspace)
    time.sleep(0.02)
    for verb, args in (("history", ["2006"]), ("diff", [f"{RUN}@{STAMP}", NEXT])):
        for output in ([], ["--json"], ["--csv"]):
            code, _, _ = _call(workspace, capsys, verb, *args, *output)
            assert code == 0
    assert additional_rows(workspace) == json.loads(before["additional.json"][0])
    assert _tree(workspace) == before
    # THE CONTROL: the same comparison must fail after a planted writer, even an mtime-only one.
    (workspace / "planted.bin").write_bytes(b"x")
    assert _tree(workspace) != before
    (workspace / "planted.bin").unlink()
    assert _tree(workspace) == before
    os.utime(workspace / "runs.json.lock")
    assert _tree(workspace) != before


def test_python_query_results_are_plain_json_data(workspace, capsys):
    """P0350-QUERY-PYTHON FR-388: json.dumps every public query result with real rows."""
    logs = workspace / "logs"
    logs.mkdir()
    events = [
        {
            "timestamp": "2026-10-02T12:00:00Z",
            "stage": "run",
            "sim_id": "2006",
            "event": "finish",
            "run_id": NEXT,
        }
    ]
    (logs / "activity.log.jsonl").write_text(json.dumps(events[0]) + "\n", encoding="utf-8")
    post = workspace / "post/sample"
    _write(
        post / "post.log.json",
        {
            "records": [
                {
                    "category": "convergence",
                    "product": "polar",
                    "message": "residual 3",
                    "point": NEXT,
                },
                {
                    "category": "convergence",
                    "product": "polar",
                    "message": "residual 4",
                    "point": NEXT,
                },
            ]
        },
    )
    _write(
        post / "products.json",
        {
            "products": {"polar.csv": {"runs": [NEXT]}},
            "provenance": {NEXT: "provenance/point.json"},
        },
    )
    snapshot = read_ledger(workspace)
    results = [
        status_rows(snapshot),
        point_rows(snapshot),
        point_card(snapshot, NEXT),
        activity_rows(snapshot),
        post_log_groups(snapshot, "sample"),
        trace_product(snapshot, "post/sample/polar.csv"),
        history(snapshot, "2006"),
        diff(snapshot, f"{RUN}@{STAMP}", NEXT),
        additional_rows(snapshot),
    ]
    for result in results:
        assert result and json.loads(json.dumps(result)) == result
    expected = [{**events[0], "source": "logs/activity.log.jsonl"}]
    assert activity_rows(snapshot, sims=["2006"], stage="run", run=NEXT) == expected
    assert activity_rows(snapshot, sims=["9999"]) == []
    assert results[4][0]["count"] == 2
    assert results[5][0]["runs"][0]["identity"]["run_id"] == NEXT
    _, out, _ = _call(workspace, capsys, "status", "--json")
    assert json.loads(out)["rows"] == results[0]
    assert point_card(snapshot, "absent") is None
    assert trace_product(snapshot, "absent.csv") == []
    # The Python rows are the command line's rows once the CLI-only alias
    # decoration is set aside (FR-388).
    for argv, python_rows in (
        (("show", NEXT), [results[2]]),
        (("log",), results[3]),
        (("trace", "post/sample/polar.csv"), results[5]),
    ):
        _, out, _ = _call(workspace, capsys, *argv, "--json")
        assert _undecorated(json.loads(out)["rows"]) == python_rows


def _undecorated(value):
    """Drop the ``run_id_alias`` keys the command line adds to its rows."""
    if isinstance(value, list):
        return [_undecorated(item) for item in value]
    if isinstance(value, dict):
        return {k: _undecorated(v) for k, v in value.items() if k != "run_id_alias"}
    return value


def test_python_query_import_and_calls_need_no_pandas(workspace):
    """P0350-QUERY-PYTHON FR-388: a fresh interpreter refuses pandas and optional extras."""
    probe = """
import json
import sys
sys.path.insert(0, sys.argv[1])
class NoOptionalImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'pandas', 'matplotlib', 'openpyxl', 'PyNite'}:
            raise AssertionError('forbidden import: ' + fullname)
sys.meta_path.insert(0, NoOptionalImports())
from pyflightstream.workspace.ledger import (
    status_rows, point_rows, point_card, activity_rows, post_log_groups,
    trace_product, history, diff, additional_rows,
)
root, run_a, run_b = sys.argv[2:]
results = [status_rows(root), point_rows(root), point_card(root, run_b),
           activity_rows(root), post_log_groups(root, 'sample'),
           trace_product(root, 'unknown.csv'), history(root, '2006'),
           diff(root, run_a, run_b), additional_rows(root)]
print(json.dumps(results))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            probe,
            str(Path(__file__).resolve().parents[2] / "src"),
            str(workspace),
            f"{RUN}@{STAMP}",
            NEXT,
        ],
        capture_output=True,
        env=os.environ.copy(),
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)
    assert len(rows) == 9 and rows[1][0]["run_id"] == NEXT


def test_machine_renderers_carry_the_same_rows(workspace, capsys):
    """FR-388 FR-390 FR-391: table, JSON and CSV render the ledger's rows."""
    for verb, args in (("history", ["2006"]), ("diff", [f"{RUN}@{STAMP}", NEXT])):
        _, json_text, _ = _call(workspace, capsys, verb, *args, "--json")
        _, csv_text, _ = _call(workspace, capsys, verb, *args, "--csv")
        _, table, _ = _call(workspace, capsys, verb, *args)
        rows = json.loads(json_text)["rows"]
        csv_rows = list(csv.DictReader(io.StringIO(csv_text)))
        assert len(csv_rows) == len(rows)
        key = "run_id" if verb == "history" else "field"
        assert [row[key] for row in csv_rows] == [row[key] for row in rows]
        assert all(str(row[key]) in table for row in rows)
        assert "\r" not in csv_text


def test_archives_in_a_compacted_sim_are_read_without_expansion(workspace, capsys):
    """FR-390 FR-383: archived JSON and scripts in a compacted simulation remain zipped."""
    home = workspace / "sims/sim_2006"
    with zipfile.ZipFile(workspace / "sims/sim_2007.zip", "w") as archive:
        archive.writestr(
            f"sim_2007/datapoints/DP-A0/archive/{STAMP}/record.json",
            json.dumps(_record("sample/sim_2007/A0", sim_id="2007")),
        )
    before = _tree(workspace)
    code, out, _ = _call(workspace, capsys, "history", "2007", "--json")
    rows = json.loads(out)["rows"]
    assert code == 0 and len(rows) == 1
    assert "sim_2007.zip!" in rows[0]["source"]
    assert home.is_dir() and not (workspace / "sims/sim_2007").exists()
    assert _tree(workspace) == before


def test_missing_ambiguous_and_unreadable_records_are_named(workspace, capsys):
    """FR-390 FR-391 FR-383: an absent selector and bad row never look like clean history."""
    _write(workspace / "archive/runs-20260930-120000.json", [17, _record()])
    code, out, err = _call(workspace, capsys, "history", "2006", "--json")
    assert code == 0 and "row 1" in err and "cannot be read" in err
    assert any("error" in row for row in json.loads(out)["rows"])
    code, _, err = _call(workspace, capsys, "history", "absent", "--json")
    assert code == 1 and "target (CLI: history)" in err
    code, _, err = _call(workspace, capsys, "diff", RUN + "@absent", NEXT)
    assert code == 2 and "run (CLI: diff)" in err
    _write(workspace / "archive" / f"runs-{STAMP}.json", [_record(), _record(status="FAILED_EXEC")])
    code, _, err = _call(workspace, capsys, "diff", f"{RUN}@{STAMP}", NEXT)
    assert code == 2 and "several archived copies" in err


def test_diff_refuses_to_compare_a_script_with_the_wrong_digest(workspace, capsys):
    """FR-391: a later script at the same path is unavailable, never falsely attributed."""
    (workspace / "sims/sim_2006/scripts/run.txt").write_text("CHANGED\n", encoding="utf-8")
    code, out, _ = _call(workspace, capsys, "diff", f"{RUN}@{STAMP}", NEXT, "--json")
    row = next(row for row in json.loads(out)["rows"] if row["field"] == "script_comparison")
    assert code == 0 and row["b"] is None and "unavailable" in row["detail"]


def test_history_honors_an_alternate_manifest(workspace, capsys):
    """FR-390: --runs selects the present manifest and its own archived copies."""
    _write(workspace / "other.json", [_record("other/sim_2006/A0")])
    _write(workspace / "archive" / f"other-{STAMP}.json", [_record("other/sim_2006/A0")])
    code, out, _ = _call(workspace, capsys, "history", "2006", "--runs", "other.json", "--json")
    rows = json.loads(out)["rows"]
    assert code == 0
    manifest_rows = [row for row in rows if "/datapoints/" not in row["source"]]
    assert [row["run_id"] for row in manifest_rows] == ["other/sim_2006/A0"] * 2
