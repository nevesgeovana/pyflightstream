"""Reproduce a forced rerun whose earlier collected outputs can no longer be archived."""

# ruff: noqa: N999 - the release lane requires this filename.

from pathlib import Path

import pytest

from pyflightstream.run import run_campaign
from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_matrix_run import WRITES_LOADS, StubSolver, converged
from tests.tier1_offline.test_run_campaign import make_campaign, steady_recipe


def _first_run(tmp_path):
    campaign = make_campaign(tmp_path, alphas=(0.0,))
    workspace = CampaignWorkspace(tmp_path / "campaign")
    (record,) = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        quiet=True,
    )
    return campaign, workspace, record


@pytest.mark.requirement("FR-108")
def test_p0400_lita_a_missing_recorded_output_is_rerun_and_recorded(tmp_path, monkeypatch):
    campaign, workspace, record = _first_run(tmp_path)
    output = workspace.sim_dir(record.sim_id) / record.outputs[0]
    original = Path.replace

    def disappeared(source, target):
        # The file disappears between directory enumeration and archiving.
        if source == output:
            source.unlink()
        return original(source, target)

    monkeypatch.setattr(Path, "replace", disappeared)
    (again,) = run_campaign(
        campaign,
        StubSolver(WRITES_LOADS),
        workspace,
        assess=converged,
        recipes={"steady": steady_recipe},
        quiet=True,
        force_rerun=[record.run_id],
    )
    assert again.run_id == record.run_id
    assert workspace.read_manifest() == [again]
    assert output.is_file()


@pytest.mark.requirement("FR-108")
def test_p0400_lita_an_archive_failure_keeps_the_manifest_record(tmp_path, monkeypatch):
    campaign, workspace, record = _first_run(tmp_path)
    original = Path.replace

    def refused(source, target):
        if "archive" in Path(target).parts:
            raise PermissionError("archive destination is unwritable")
        return original(source, target)

    monkeypatch.setattr(Path, "replace", refused)
    with pytest.raises(PermissionError, match="unwritable"):
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
            quiet=True,
            force_rerun=[record.run_id],
        )
    assert workspace.read_manifest() == [record]


@pytest.mark.requirement("FR-108")
def test_p0400_lita_a_failure_after_superseding_keeps_a_record(tmp_path, monkeypatch):
    campaign, workspace, record = _first_run(tmp_path)
    from pyflightstream.run import _campaign

    def interrupted(state):
        raise RuntimeError("interrupted before replacement")

    monkeypatch.setattr(_campaign, "_prepare_campaign_case", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            workspace,
            assess=converged,
            recipes={"steady": steady_recipe},
            quiet=True,
            force_rerun=[record.run_id],
        )
    assert workspace.read_manifest() == [record]


@pytest.mark.requirement("FR-108")
def test_p0400_lita_a_long_archive_destination_keeps_the_existing_output(tmp_path):
    from pyflightstream.workspace.naming import PointName

    workspace = CampaignWorkspace(tmp_path / "campaign")
    folder = workspace.create_sim("9001") / "datapoints/DP-AL+000"
    folder.mkdir(parents=True)
    # Archiving adds 24 characters, reproducing the study's long destination.
    name = "x" * (250 - len(str(folder)) - 5) + ".txt"
    source = folder / name
    source.write_bytes(b"recorded output")
    archive = workspace.archive_datapoint("9001", PointName("AL+000"))
    assert archive is not None
    assert (archive / name).read_bytes() == b"recorded output"
