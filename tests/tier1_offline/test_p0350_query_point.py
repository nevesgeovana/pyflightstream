"""QV1 query contracts on synthetic records, including running batches and ZIPs."""

# SRS evidence: FR-372, FR-383, FR-386, FR-387, FR-389, FR-392, FR-393, FR-394.

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from zipfile import ZipFile

import pytest

from pyflightstream.run.cli import main
from pyflightstream.workspace import RunRecord, RunStatus
from pyflightstream.workspace.ledger import read_ledger
from pyflightstream.workspace.storage import STORAGE_SCHEMA

RUN = "synthetic/sim_9101/A0"
PRODUCT = "post/demo/polars/polar.csv"


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _event(stage, event, stamp="2026-01-01T10:00:00+00:00", **extra):
    return {
        "timestamp": stamp,
        "stage": stage,
        "event": event,
        "run_id": RUN,
        "sim_id": "9101",
        **extra,
    }


def _logfile(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


@pytest.fixture
def workspace(tmp_path):
    record = RunRecord(
        run_id=RUN,
        sim_id="9101",
        point_name="A0",
        matrix_stem="demo",
        point={"alpha": 0},
        fs_version_requested="26.124",
        package_version="0.35.0",
        script_sha256="a" * 64,
        raw_flag=False,
        status=RunStatus.FAILED_MARKED,
        marked={"from": "CONVERGED", "at": "2026-01-01T12:00:00Z", "reason": "synthetic check"},
        error="synthetic error",
        warnings=["synthetic warning"],
        residual_note="residual high",
        stopped_at={"reason": "clock"},
        iterations=12,
        residual=0.2,
        conditions=[{"axis": "alpha", "within": False, "tolerance": 0.01}],
        package_commit="b" * 40,
        fs_build="synthetic-build",
        recipe_sha256="c" * 64,
        inputs_sha256={"mesh.obj": "d" * 64},
        pproc="p001",
        solver_setup={
            "flags": {
                "kept": {"provenance": "explicit", "value": True},
                "omitted": {"provenance": "default", "value": False},
            }
        },
        reference={"area": 1.0},
        log_file_used="datapoints/DP-A0/solver.log",
        outputs=["datapoints/DP-A0/solver.log", "datapoints/DP-A0/loads.csv"],
    ).model_dump(mode="json")
    _write(tmp_path / "runs.json", [record])
    _write(
        tmp_path / "post/demo/plan.json",
        {"points": [{"run_id": RUN, "sim_id": "9101", "point": {"alpha": 0}}]},
    )
    point = tmp_path / "sims/sim_9101/datapoints/DP-A0"
    point.mkdir(parents=True)
    (point / "solver.log").write_text(
        "line1\nline2\nline3\nline4\nline5\nline6\nlast solver line\n", encoding="utf-8"
    )
    (point / "loads.csv").write_text("CL\n0.4\n", encoding="utf-8")
    _logfile(point / "logs/activity.log.jsonl", [_event("solver", "started")])
    _logfile(
        tmp_path / "logs/activity.log.jsonl",
        [
            _event("post", "finished", "2026-01-01T12:00:00Z"),
            _event("post", "started", "2026-01-01T11:00:00Z"),
            _event("collect", "failed", "2026-01-01T13:00:00Z", outcomes={"FAILED_DIVERGED": 1}),
        ],
    )
    _write(
        tmp_path / "post/demo/post.log.json",
        {
            "records": [
                {"point": RUN, "product": "polars/a.csv", "message": "missing 12 samples"},
                {"point": RUN, "product": "polars/b.csv", "message": "missing 15 samples"},
                {
                    "point": "synthetic/sim_9102/A0",
                    "product": "sections/c.csv",
                    "message": "missing samples",
                },
            ]
        },
    )
    _write(
        tmp_path / "post/demo/products.json",
        {
            "products": {"polars/polar.csv": {"sim_id": "9101", "pproc": "p001", "runs": [RUN]}},
            "provenance": {RUN: "provenance/A0.prov.json"},
        },
    )
    _write(
        tmp_path / "post/demo/provenance/A0.prov.json",
        {
            "entity": {
                "mesh": {"sha256": "d" * 64},
                "script": {"sha256": "a" * 64},
                "output": {"sha256": "e" * 64},
            }
        },
    )
    _write(tmp_path / "post/demo/polars/polar.csv.json", {"units": "nondimensional"})
    return tmp_path


def _query(workspace, capsys, *args):
    code = main([*args, "--workspace", str(workspace)])
    out, err = capsys.readouterr()
    return code, out, err


def _rows(workspace, capsys, *args):
    code, out, err = _query(workspace, capsys, *args, "--json")
    assert code == 0, err
    return json.loads(out)["rows"]


def test_show_outcome_evidence_identity_inputs_and_polar(workspace, capsys):
    """P0350-QUERY-SHOW FR-386: card order, alias, evidence and failed polar cards."""
    row = _rows(workspace, capsys, "show", "9101_1")[0]
    assert list(row) == ["outcome", "evidence", "activity", "post", "chain", "identity", "inputs"]
    assert row["outcome"]["status"] == "FAILED_MARKED"
    assert row["outcome"]["marked"]["from"] == "CONVERGED"
    assert row["outcome"]["error"] == "synthetic error"
    assert row["outcome"]["warnings"] == ["synthetic warning"]
    assert row["outcome"]["iterations"] == 12 and row["outcome"]["residual"] == 0.2
    assert row["outcome"]["stopped_at"]["reason"] == "clock"
    assert row["outcome"]["outside_tolerance"][0]["axis"] == "alpha"
    assert row["evidence"][0]["last_lines"] == [
        "line3",
        "line4",
        "line5",
        "line6",
        "last solver line",
    ]
    assert len(row["activity"]) == 4 and len(row["post"]) == 2
    assert row["identity"]["run_id"] == RUN and row["identity"]["run_id_alias"] == "9101_1"
    assert row["identity"]["recipe_sha256"] == "c" * 64
    assert list(row["inputs"]["solver_setup"]["flags"]) == ["kept"]
    assert row["inputs"]["inputs_sha256"] == {"mesh.obj": "d" * 64}
    assert _rows(workspace, capsys, "show", "9101", "--point", "A0")[0] == row
    polar = _rows(workspace, capsys, "show", "9101")[0]
    assert len(polar["points"]) == 1 and polar["failed"] == [row]
    code, out, _ = _query(workspace, capsys, "show", RUN)
    assert code == 0 and out.index("outcome:") < out.index("identity:")
    code, out, _ = _query(workspace, capsys, "show", "9101")
    assert code == 0 and any(
        "9101" in line and "A0" in line and "FAILED_MARKED" in line for line in out.splitlines()
    )


def test_show_uses_current_chain_and_names_archived_outputs(workspace, capsys):
    """P0350-QUERY-SHOW FR-386: continuation card never merges archived manifests."""
    old = json.loads((workspace / "runs.json").read_text())[0]
    new = {
        **old,
        "run_id": "synthetic/sim_9101/r20260101/A0",
        "continues": RUN,
        "status": "CONVERGED",
    }
    _write(workspace / "runs.json", [new, old])
    _write(workspace / "archive/runs-20251231.json", [{**old, "status": "FAILED_DIVERGED"}])
    archived = workspace / "sims/sim_9101/datapoints/DP-A0/archive/20251231/solver.log"
    archived.parent.mkdir(parents=True)
    archived.write_text("old solver", encoding="utf-8")
    row = _rows(workspace, capsys, "show", "9101_1")[0]
    assert row["outcome"]["status"] == "CONVERGED"
    assert row["chain"]["continues"] == RUN
    assert row["chain"]["archives"] == [archived.relative_to(workspace).as_posix()]


def test_show_coupling_record_last_exchange_and_absence(workspace, capsys):
    """P0350-QUERY-SHOW-FSI FR-394: only coupled points show FSI and absent files."""
    assert "coupling" not in _rows(workspace, capsys, "show", RUN)[0]
    point = workspace / "sims/sim_9101/datapoints/DP-A0"
    _write(point / "fsi-provenance.json", {"config_sha256": "f" * 64})
    _write(point / "state.json", {"phase": 4, "iteration": 2})
    (point / "fsi_convergence_log.csv").write_text("iteration,residual\n1,0.2\n2,0.01\n")
    fsi = _rows(workspace, capsys, "show", RUN)[0]["coupling"]
    assert fsi["state.json"]["record"] == {"phase": 4, "iteration": 2}
    assert fsi["fsi_convergence_log.csv"]["last_row"] == {"iteration": "2", "residual": "0.01"}
    (point / "state.json").unlink()
    assert _rows(workspace, capsys, "show", RUN)[0]["coupling"]["state.json"]["state"] == "absent"
    assert not (point / "state.json").exists()


def test_log_filters_order_open_and_relative_since(workspace, capsys):
    """P0350-QUERY-LOG FR-387: chronology, intersected filters, problems and unfinished stages."""
    rows = _rows(workspace, capsys, "log")
    assert [row["stage"] for row in rows] == ["solver", "post", "post", "collect"]
    rows = _rows(
        workspace,
        capsys,
        "log",
        "--sims",
        "[9101]",
        "--run",
        "9101_1",
        "--stage",
        "collect",
        "--problems",
        "--since",
        "2026-01-01T12:30:00Z",
    )
    assert [row["event"] for row in rows] == ["failed"]
    assert _rows(workspace, capsys, "log", "--run", "synthetic/sim_9999/old") == []
    assert _rows(workspace, capsys, "log", "--sims", "9102") == []
    rows = _rows(workspace, capsys, "log", "--open")
    assert [(row["stage"], row["event"]) for row in rows] == [("solver", "started")]
    _logfile(
        workspace / "logs/activity.log.jsonl",
        [_event("fresh", "started", datetime.now(UTC).isoformat())],
    )
    assert [row["stage"] for row in _rows(workspace, capsys, "log", "--since", "2h")] == ["fresh"]


def test_log_post_groups_category_family_shape(workspace, capsys):
    """P0350-QUERY-LOG FR-387: post grouping keeps count and example, filtered by sim."""
    groups = _rows(workspace, capsys, "log", "--post", "demo", "--sims", "9101")
    assert len(groups) == 1
    assert groups[0]["category"] == "missing-data" and groups[0]["family"] == "polars"
    assert groups[0]["count"] == 2 and groups[0]["shape"] == "missing # samples"
    assert groups[0]["example"]["message"] == "missing 12 samples"
    assert len(_rows(workspace, capsys, "log", "--post", "demo")) == 2


def test_log_storage_preserves_calls_and_filters(workspace, capsys):
    """P0350-QUERY-LOG-STORAGE FR-392: raw storage calls, read-only meaningful filters."""
    calls = [
        {
            "at": "2026-01-02T10:00:00Z",
            "action": "delete-sims",
            "sims": [{"sim_id": "9101"}],
            "unknown_future_field": {"kept": True},
        },
        {"at": "2026-01-01T10:00:00Z", "action": "space-in-use", "sims": 2},
    ]
    _write(workspace / "storage_management.json", {"schema": STORAGE_SCHEMA, "calls": calls})
    assert _rows(workspace, capsys, "log", "--storage") == list(reversed(calls))
    assert (
        _rows(
            workspace,
            capsys,
            "log",
            "--storage",
            "--sims",
            "9101",
            "--stage",
            "delete-sims",
            "--since",
            "2026-01-02",
        )
        == calls[:1]
    )


def test_additional_register_is_printed_without_derived_fields(workspace, capsys):
    """P0350-QUERY-ADDITIONAL FR-393: status --additional returns each recorded field."""
    entries = [{"extraction_id": "x1", "run_id": RUN, "status": "COLLECTED", "future": [1, 2]}]
    _write(workspace / "additional.json", entries)
    assert _rows(workspace, capsys, "status", "--additional") == entries


def test_trace_product_identity_sidecar_and_provenance_tree(workspace, capsys):
    """P0350-QUERY-TRACE FR-389: indexed runs, effective digests, sidecar and provenance."""
    row = _rows(workspace, capsys, "trace", PRODUCT)[0]
    assert row["sim_id"] == "9101" and row["pproc"] == "p001"
    assert row["sidecar"] == PRODUCT + ".json"
    run = row["runs"][0]
    assert run["provenance"] == "post/demo/provenance/A0.prov.json"
    assert run["identity"]["package_version"] == "0.35.0"
    assert run["identity"]["fs_build"] == "synthetic-build"
    assert run["identity"]["inputs_sha256"]["mesh.obj"] == "d" * 64
    assert run["identity"]["script_sha256"] == "a" * 64
    assert _rows(workspace, capsys, "trace", "--run", "9101_1") == [run]
    code, out, _ = _query(workspace, capsys, "trace", "--run", RUN)
    assert code == 0 and "entity:" in out and "d" * 64 in out


def _batch(workspace):
    home = workspace / "sims/sim_9101"
    batch = workspace / "sims/batch/demo_b7/sim_9101"
    batch.parent.mkdir(parents=True)
    assert home.resolve().is_relative_to(workspace.resolve())
    assert batch.resolve().is_relative_to(workspace.resolve())
    home.rename(batch)
    return home, batch


def test_batch_status_before_and_after_home(workspace, capsys):
    """P0350-BATCH-TRANSPARENT FR-372: pyfs-matrix status during a batch and after it moves home."""
    home, batch = _batch(workspace)
    assert read_ledger(workspace).sim_folders("9101") == ["sims/batch/demo_b7/sim_9101"]
    before = _rows(workspace, capsys, "status", "--points")
    assert before[0]["status"] == "FAILED_MARKED"
    batch.rename(home)
    assert _rows(workspace, capsys, "status", "--points") == before
    assert read_ledger(workspace).sim_folders("9101") == ["sims/sim_9101"]


def test_batch_show_before_and_after_home(workspace, capsys):
    """P0350-BATCH-TRANSPARENT FR-372: pyfs-matrix show during a batch and after it moves home."""
    home, batch = _batch(workspace)
    before = _rows(workspace, capsys, "show", RUN)[0]
    assert before["evidence"]
    assert before["evidence"][0]["path"].startswith("sims/batch/demo_b7/")
    batch.rename(home)
    after = _rows(workspace, capsys, "show", RUN)[0]
    assert after["outcome"] == before["outcome"]
    assert after["evidence"][0]["last_lines"] == before["evidence"][0]["last_lines"]
    assert after["evidence"][0]["path"].startswith("sims/sim_9101/")


def test_batch_log_before_and_after_home(workspace, capsys):
    """P0350-BATCH-TRANSPARENT FR-372: pyfs-matrix log during a batch and after it moves home."""
    home, batch = _batch(workspace)
    before = _rows(workspace, capsys, "log", "--stage", "solver")
    assert len(before) == 1 and before[0]["source"].startswith("sims/batch/demo_b7/")
    batch.rename(home)
    after = _rows(workspace, capsys, "log", "--stage", "solver")
    assert after[0]["source"].startswith("sims/sim_9101/")
    assert after[0]["run_id"] == before[0]["run_id"]


def test_batch_trace_before_and_after_home(workspace, capsys):
    """P0350-BATCH-TRANSPARENT FR-372: pyfs-matrix trace during a batch and after it moves home."""
    home, batch = _batch(workspace)
    assert read_ledger(workspace).sim_folders("9101") == ["sims/batch/demo_b7/sim_9101"]
    before = _rows(workspace, capsys, "trace", PRODUCT)
    assert before[0]["runs"][0]["identity"].get("run_id") == RUN
    batch.rename(home)
    assert _rows(workspace, capsys, "trace", PRODUCT) == before


def _tree(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


def test_queries_read_compacted_logs_and_write_no_bytes(workspace, capsys):
    """P0350-QUERY-READ-ONLY FR-383; FR-392 logs in ZIP stay compacted, no lock or writes."""
    home, batch = _batch(workspace)
    archive = home.with_suffix(".zip")
    with ZipFile(archive, "w") as target:
        for path in batch.rglob("*"):
            if path.is_file():
                target.write(path, path.relative_to(batch).as_posix())
    # Leave the synthetic batch outside sims to prove every file is read from the ZIP.
    batch.rename(workspace / "control-original")
    (workspace / "control.bin").write_bytes(b"unchanged\x00\xff")
    (workspace / "runs.json.lock").write_text("held", encoding="utf-8")
    before = _tree(workspace)
    card = _rows(workspace, capsys, "show", RUN)[0]
    assert "sim_9101.zip!/" in card["evidence"][0]["path"]
    assert card["evidence"][0]["last_lines"][-1] == "last solver line"
    log = _rows(workspace, capsys, "log", "--stage", "solver")
    assert "sim_9101.zip!/" in log[0]["source"]
    for args in [
        ("trace", PRODUCT),
        ("log", "--post", "demo"),
        ("log", "--storage"),
        ("status", "--additional"),
    ]:
        _rows(workspace, capsys, *args)
    assert _tree(workspace) == before and not home.exists()


def test_query_errors_and_machine_csv(workspace, capsys):
    """FR-386 FR-387 FR-389: missing subjects are named; CSV preserves nested fields."""
    for args, code, word in [
        (("show", "9101_9"), 1, "9101_9"),
        (("trace", "unknown.csv"), 1, "products index"),
        (("log", "--since", "yesterday"), 2, "since (CLI: --since)"),
    ]:
        got, _, err = _query(workspace, capsys, *args)
        assert got == code and word in err
    code, out, _ = _query(workspace, capsys, "show", RUN, "--csv")
    assert code == 0
    row = next(csv.DictReader(io.StringIO(out)))
    assert json.loads(row["outcome"])["status"] == "FAILED_MARKED"
    assert "\r" not in out
