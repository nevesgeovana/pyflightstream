"""Existing-document remedies distinguish archiving from replacement."""

from __future__ import annotations

import pytest

from pyflightstream.post.products import ProductExistsError
from pyflightstream.post.provenance import run_provenance
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus


@pytest.mark.parametrize(
    "remedy",
    [
        "archive=True to keep a copy under archive/<day and hour>/",
        "overwrite=True with archive=False to replace without a copy",
    ],
    ids=["archive", "overwrite"],
)
def test_existing_provenance_names_each_option_and_its_effect(tmp_path, remedy):
    workspace = CampaignWorkspace(tmp_path)
    record = RunRecord(
        run_id="camp/sim_1/point",
        sim_id="1",
        fs_version_requested="26.124",
        package_version="0.25.0",
        script_sha256="0" * 64,
        raw_flag=False,
        status=RunStatus.CONVERGED,
    )
    out = tmp_path / "post"
    target = out / "provenance" / "camp_sim_1_point.prov.json"
    target.parent.mkdir(parents=True)
    target.write_text("original document\n", encoding="utf-8")

    with pytest.raises(ProductExistsError) as refusal:
        run_provenance(workspace, [record], out, archive=False, overwrite=False)

    assert remedy in str(refusal.value)
    assert target.read_text(encoding="utf-8") == "original document\n"
    assert not (target.parent / "archive").exists()
