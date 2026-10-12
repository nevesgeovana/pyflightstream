"""Tier 1, 0.40.0 lane run-1: ``post --from-sims`` assembles records from the simulation folders.

The from-sims workspace of the 0.32.0 tests: a steady polar run outside the package, its
exports under ``sims/sim_6001/outputs/`` and no ``runs.json``.
"""

from __future__ import annotations

import pytest

from pyflightstream.run import records
from pyflightstream.workspace.storage import _compact_sim
from tests.tier1_offline.test_p0320_b3_post_records import _from_sims_workspace


def _judged(workspace):
    assembled, refusals = records.assemble_records(workspace.root, "matriz")
    steady = sorted(
        (record for record in assembled if record.sim_id == "6001"),
        key=lambda record: record.point["alpha"],
    )
    return [(record.status, record.error) for record in steady], refusals


@pytest.mark.parametrize("folder", ["", "run1"])
def test_p0400_an_export_outside_the_assessors_folders_is_judged_where_it_was_found(
    tmp_path, folder
):
    """P0400-FROM-SIMS-FOLDER (PFS-2103.017): exports in ``sims/sim_X/`` or ``sims/sim_X/run1/``.

    The assessor read only ``datapoints/DP-<name>/``, ``outputs/`` and ``raw/``, so an
    export anywhere else read as no output and the point was FAILED_INCOMPLETE_OUTPUT
    ("no single collected output reads as a loads table"). Each layout is now judged as
    the ``outputs/`` layout is (the control).
    """
    control, _ = _judged(_from_sims_workspace(tmp_path / "control"))
    assert len(control) == 2
    workspace = _from_sims_workspace(tmp_path / "moved")
    sim = workspace.sim_dir("6001")
    target = sim / folder
    target.mkdir(exist_ok=True)
    for path in sorted((sim / "outputs").iterdir()):
        path.replace(target / path.name)
    moved, refusals = _judged(workspace)
    assert moved == control, refusals
    assert not any("reads as a loads table" in str(error) for _status, error in moved)


def test_p0400_post_from_sims_restores_a_compacted_simulation(tmp_path):
    """P0400-FROM-SIMS-COMPACTED (PFS-2103.019): ``sims/sim_6001.zip`` is read, not skipped."""
    control, _ = _judged(_from_sims_workspace(tmp_path / "control"))
    workspace = _from_sims_workspace(tmp_path / "compacted")
    _compact_sim(workspace, "6001")
    assert not workspace.sim_dir("6001").exists()
    compacted, refusals = _judged(workspace)
    assert compacted == control, refusals
    assert workspace.sim_dir("6001").is_dir()


def test_p0400_post_from_sims_refuses_a_compacted_simulation_it_cannot_restore(tmp_path):
    """P0400-FROM-SIMS-COMPACTED (PFS-2103.019): a broken archive is a refusal naming it."""
    workspace = _from_sims_workspace(tmp_path)
    _compact_sim(workspace, "6001")
    archive = workspace.root / "sims" / "sim_6001.zip"
    archive.write_bytes(b"not a zip")
    assembled, refusals = records.assemble_records(workspace.root, "matriz")
    assert "6001" not in {record.sim_id for record in assembled}
    assert "sims/sim_6001.zip" in refusals["sims/sim_6001"]
