"""Existing-document remedies distinguish archiving from replacement."""

from __future__ import annotations

import json

import pytest

import pyflightstream._digest as digest_module
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


def test_an_output_that_cannot_be_opened_is_recorded_from_the_record(tmp_path, monkeypatch):
    """The tech-writer lens of the v0.25.1 closing round: a digest never ends the post.

    The provenance document hashes every recorded output, native logs included,
    in every mode. A file that `is_file()` and refuses to open raised out of the
    digest and ended the whole post, the defect shape the release exists for,
    through a door the freeze check never opened. It is now recorded from the
    record, as a file that is not there is.
    """
    workspace = CampaignWorkspace(tmp_path)
    sim_dir = workspace.sim_dir("1")
    sim_dir.mkdir(parents=True)
    (sim_dir / "AL-020_log.txt").write_text("a log the run wrote", encoding="utf-8")
    record = RunRecord(
        run_id="camp/sim_1/point",
        sim_id="1",
        fs_version_requested="26.124",
        package_version="0.25.1",
        script_sha256="0" * 64,
        raw_flag=False,
        status=RunStatus.CONVERGED,
        outputs=["AL-020_log.txt"],
        outputs_sha256={"AL-020_log.txt": "1" * 64},
    )

    def refuse(*args, **kwargs):
        raise PermissionError("the cluster holds the log open")

    monkeypatch.setattr(digest_module, "open", refuse, raising=False)
    out = tmp_path / "post"
    run_provenance(workspace, [record], out, archive=False, overwrite=False)
    document = json.loads(
        (out / "provenance" / "camp_sim_1_point.prov.json").read_text(encoding="utf-8")
    )
    entity = document["entity"]["pyfs:output/AL-020_log.txt"]
    assert entity["pyfs:sha256"] == "1" * 64
    assert entity["pyfs:sha256_from"] == "record"
