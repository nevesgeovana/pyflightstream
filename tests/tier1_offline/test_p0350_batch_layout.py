"""Tier 1: the 0.35.0 batch layout, grouping receipt and job entry.

Pipeline role: quality gate on the workspace-layer contract every grouped
package builds on: folder names and IDs, the receipt and its JSON, the gate that
refuses a run whose receipt does not match, and the entry a grouped point carries.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-358, FR-365, FR-366.

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pyflightstream.run._grouped import batch_receipt_error, read_receipt
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace._batches import (
    GroupedJob,
    GroupingReceipt,
    batch_dir,
    batch_dirs,
    batch_label,
    batch_script_name,
    batch_sim_dirs,
    job_of,
    next_batch_id,
)


def _job(batch_id: int, sims: tuple[str, ...]) -> GroupedJob:
    label = batch_label("mtx", batch_id)
    return GroupedJob(
        name=f"BATCH-{sims[0]}-{sims[-1]}",
        batch_id=batch_id,
        label=label,
        dir=f"sims/batch/{label}/",
        script=f"sims/batch/{label}/BATCH-{sims[0]}-{sims[-1]}.txt",
        sims=sims,
        points=tuple(f"run/{s}/AL+000" for s in sims),
        fs_build="26.124",
        ncpus=16,
        estimate_s=11100.0,
        estimate_basis="fitted",
        fallback_points=(),
        unestimated_points=("x",),
        overheads_s={"start": 2.0, "reinit": 0.08, "refresh": 2.0},
        factor=1.25,
        margin_s=1200.0,
        walltime_s=15120,
        walltime_written="252m",
        walltime_source="BEST",
        fits=True,
        shortfall_s=None,
    )


def _receipt() -> GroupingReceipt:
    return GroupingReceipt(
        schema="pyfs-grouping/1",
        mode="batch",
        requested=2,
        selection={"sims": None, "points": None},
        jobs=(_job(1, ("2006", "2007")), _job(2, ("2008",))),
        left_out=({"sim": "2010", "reason": "a steady row"},),
        total_estimate_s=21300.0,
        longest_estimate_s=11100.0,
        max_walltime_s=172800,
        warnings=("w",),
    )


def test_p0350_layout_fr358_ids_labels_and_names(tmp_path: Path) -> None:
    """P0350-BATCH-RECEIPT: labels, folders, script names and the next free ID."""
    assert batch_label("mtx", 3) == "mtx_b3"
    assert batch_dir(tmp_path, "mtx", 3) == tmp_path / "sims" / "batch" / "mtx_b3"
    assert batch_script_name("2006", "2007") == "BATCH-2006-2007.txt"
    assert batch_script_name("2006", "2006") == "BATCH-2006-2006.txt"
    assert next_batch_id(tmp_path, "mtx") == 1
    for name in ("mtx_b1", "mtx_b3", "other_b9", "mtx_bx"):
        (tmp_path / "sims" / "batch" / name).mkdir(parents=True)
    (tmp_path / "sims" / "batch" / "mtx_b3" / "sim_2006").mkdir()
    assert next_batch_id(tmp_path, "mtx") == 4
    assert next_batch_id(tmp_path, "another") == 1
    assert [p.name for p in batch_dirs(tmp_path)] == ["mtx_b1", "mtx_b3", "other_b9"]
    assert batch_sim_dirs(tmp_path) == {"2006": [tmp_path / "sims/batch/mtx_b3/sim_2006"]}


def test_p0350_layout_fr365_receipt_round_trip() -> None:
    """P0350-BATCH-RECEIPT: to_json then from_json is identity; another schema is refused."""
    receipt = _receipt()
    payload = receipt.to_json()
    assert payload["batch_count"] == 2
    assert GroupingReceipt.from_json(json.loads(json.dumps(payload))) == receipt
    with pytest.raises(ValueError, match="pyfs-grouping/2"):
        GroupingReceipt.from_json({**payload, "schema": "pyfs-grouping/2"})


def _planned(tmp_path: Path, receipt: GroupingReceipt | None) -> tuple[CampaignWorkspace, Path]:
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.init(tmp_path / "camp")
    matrix = tmp_path / "mtx.fs"
    matrix.write_bytes(b"matrix\n")
    plan: dict[str, object] = {"matrix_sha256": hashlib.sha256(matrix.read_bytes()).hexdigest()}
    if receipt is not None:
        plan["grouping"] = receipt.to_json()
    folder = workspace.plan_dir("mtx")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    return workspace, matrix


def test_p0350_layout_fr365_the_gate_refuses_by_name(tmp_path: Path) -> None:
    """P0350-BATCH-RECEIPT: the gate answers None for a match and a sentence for each mismatch."""
    ask = {"mode": "batch", "batch": 2, "sims": None, "points": None}
    workspace, matrix = _planned(tmp_path, _receipt())
    assert read_receipt(workspace, "mtx") == _receipt()
    assert batch_receipt_error(workspace, matrix, "mtx", **ask) is None
    for change, word in (
        ({"mode": "polar_sweep"}, "polar_sweep"),
        ({"batch": 3}, "--batch 2"),
        ({"sims": ["2006"]}, "selection"),
    ):
        assert word in (batch_receipt_error(workspace, matrix, "mtx", **{**ask, **change}) or "")
    matrix.write_bytes(b"matrix\nchanged")
    assert "changed" in (batch_receipt_error(workspace, matrix, "mtx", **ask) or "")
    matrix.write_bytes(b"matrix\n")
    folder = workspace.root / "sims/batch/mtx_b1"
    folder.mkdir(parents=True)
    (folder / "x.txt").write_text("x", encoding="utf-8")
    assert "already holds" in (batch_receipt_error(workspace, matrix, "mtx", **ask) or "")
    bare, bare_matrix = _planned(tmp_path / "bare", None)
    assert "no grouping" in (batch_receipt_error(bare, bare_matrix, "mtx", **ask) or "")


def test_p0350_layout_fr366_job_of_reads_the_entry() -> None:
    """P0350-BATCH-RECEIPT: job_of returns submission["job"], and None without one."""
    base = {
        "run_id": "r",
        "sim_id": "1",
        "fs_version_requested": "26.124",
        "package_version": "0.35.0.dev0",
        "script_sha256": "c" * 64,
        "raw_flag": False,
        "status": RunStatus.SUBMITTED,
    }
    entry = {"kind": "batch", "name": "BATCH-1-1", "order": 1}
    assert job_of(RunRecord(**base, submission={"job": entry})) == entry
    assert job_of(RunRecord(**base, submission={"submitted": False})) is None
    assert job_of(RunRecord(**base)) is None
