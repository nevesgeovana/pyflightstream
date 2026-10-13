"""P0400-RFIXF-STATUS: every far-field row carries the point's solver status (PFS-2081.97).

A point that stopped at its iteration limit wrote far-field rows that said
nothing of it; its status was only in the sweep table and the run record.
Every row of the Trefftz table, the spanwise files and the ledgers now ends
with ``STATUS``, the token the sweep table writes, so a row of a point that is
not converged is marked as the near-field products mark it.
"""
# ruff: noqa: N999 - the assigned lane name is rfixF.

from __future__ import annotations

from pathlib import Path

import pytest

from tests.tier1_offline import test_p0400_farfield_products as wing
from tests.tier1_offline import test_p0400_ffproof_post as ffpost
from tests.tier1_offline.test_p0400_rfixF_layout import _rows


@pytest.mark.requirement("FR-456")
@pytest.mark.parametrize("status", ["MAX_ITER_REACHED", "CONVERGED"])
def test_p0400_rfixf_every_trefftz_row_carries_the_status(tmp_path, status):
    """P0400-RFIXF-STATUS (FR-456 R10): A, B and C rows and the spanwise files say the status."""
    workspace = wing._workspace(tmp_path, farfield=True)
    extra = {"iterations": 1500, "iterations_requested": 1500} if status != "CONVERGED" else {}
    ffpost._set_record(workspace, status=status, **extra)
    ffpost._post(workspace)
    root = Path(workspace.root)
    rows = _rows(root, "farfield/*_trefftz.csv")
    assert {row["VARIANT"] for row in rows} == {"A", "B", "C"}
    assert {row["STATUS"] for row in rows} == {status}
    spanwise = sorted(root.rglob("sections/*_trefftz_*.csv"))
    assert spanwise
    for path in spanwise:
        assert {row["STATUS"] for row in _rows(path.parent, path.name)} == {status}


@pytest.mark.requirement("FR-456")
def test_p0400_rfixf_every_ledger_row_carries_the_status(tmp_path):
    """P0400-RFIXF-STATUS (FR-456 R10): the ledgers of a point at its iteration limit say so."""
    workspace = ffpost._campaign(
        tmp_path,
        pproc=ffpost._LEDGERS,
        files={f"{ffpost._STEM}_probes.txt": ffpost._probe_export(ffpost._POINTS_M, 20.0)},
    )
    ffpost._set_record(
        workspace, status="MAX_ITER_REACHED", iterations=900, iterations_requested=900
    )
    ffpost._post(workspace)
    rows = _rows(Path(workspace.root), "farfield/*_ledgers.csv")
    assert len(rows) == 2 and {row["STATUS"] for row in rows} == {"MAX_ITER_REACHED"}
