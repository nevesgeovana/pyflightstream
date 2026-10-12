"""Tier 1, 0.40.0 lane run-2: a refusal inside the submitting executor fails its point alone.

The executor writes its descriptor and calls no scheduler (``submit=False``).
"""

from __future__ import annotations

import sys

from pyflightstream.run import CampaignErrors, SubmittingExecutor, run_campaign
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_goal024_walltime import _case, _profile


def _recipe(case, script):
    script.emit("CLOSE_FLIGHTSTREAM")


def _converged(case, result, sim_dir):
    from pyflightstream.run import Assessment

    return Assessment(status=RunStatus.CONVERGED)


def test_p0400_a_row_the_descriptor_refuses_fails_alone_and_the_campaign_goes_on(tmp_path):
    """P0400-SUBMIT-REFUSAL (PFS-2094.037): the refusal is the point's, not the campaign's.

    The profile's descriptor asks for {walltime}; row 5001 states it, row 5002
    does not. render_descriptor's refusal escaped run_script, the campaign
    ended there, and row 5002 got no record.
    """
    from pyflightstream.cases import Campaign

    first = _case("4h")
    second = _case(None).model_copy(update={"sim_id": "5002"})
    campaign = Campaign(
        name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[first, second]
    )
    workspace = CampaignWorkspace(tmp_path / "camp")
    executor = SubmittingExecutor(_profile(tmp_path), values={}, submit=False)
    try:
        records = run_campaign(
            campaign, executor, workspace, assess=_converged, recipes={"steady": _recipe}
        )
    except CampaignErrors as error:
        records = error.records
    status = {record.sim_id: record for record in workspace.read_manifest()}
    assert status["5001"].status is RunStatus.SUBMITTED, status["5001"].error
    assert str(status["5002"].status).startswith("FAILED"), status["5002"].status
    assert "walltime" in (status["5002"].error or ""), status["5002"].error
    assert {record.sim_id for record in records} == {"5001", "5002"}


def test_p0400_a_submit_command_naming_an_unresolved_value_writes_no_descriptor(tmp_path):
    """P0400-SUBMIT-REFUSAL (PFS-2094.037): the argv is formatted before the descriptor.

    A KeyError from formatting the submit command escaped run_script after the
    descriptor had been written.
    """
    text = (
        _profile(tmp_path).path.read_text(encoding="utf-8").replace("{descriptor_path}", "{queue}")
    )
    path = tmp_path / "h002.toml"
    path.write_text(text, encoding="utf-8")
    from pyflightstream.workspace.inputs import read_hpc_profile

    executor = SubmittingExecutor(read_hpc_profile(path), values={"walltime": "4h"}, submit=False)
    script = tmp_path / "point.txt"
    script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
    result = executor.run_script(script, working_dir=tmp_path / "work")
    assert result.return_code != 0 and "{queue}" in result.stderr
    assert not (tmp_path / "work" / "submit.yaml").exists()
