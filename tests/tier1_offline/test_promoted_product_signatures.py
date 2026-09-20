"""Promoted product helpers expose optional controls with usable defaults."""

from __future__ import annotations

from inspect import Parameter, signature

import pytest

from pyflightstream.post.custom_polar import group_number
from pyflightstream.post.products import ProductError
from pyflightstream.post.provenance import run_provenance
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus


def test_numeric_group_needs_no_position():
    assert group_number(1) == 1


def test_named_group_refusal_names_position_keyword():
    with pytest.raises(ProductError, match="position="):
        group_number("wing", position=None)


def test_group_position_is_an_optional_keyword():
    position = signature(group_number).parameters["position"]
    assert position.kind is Parameter.KEYWORD_ONLY
    assert position.default is None
    assert group_number("wing", position=2) == 2


def test_run_provenance_defaults_to_archiving_without_overwrite(tmp_path):
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

    written = run_provenance(workspace, [record], out)

    assert written == {record.run_id: "provenance/camp_sim_1_point.prov.json"}
    archived = list((target.parent / "archive").glob("*/" + target.name))
    assert len(archived) == 1
    assert archived[0].read_text(encoding="utf-8") == "original document\n"
    assert target.read_text(encoding="utf-8") != "original document\n"
    overwrite = signature(run_provenance).parameters["overwrite"]
    assert overwrite.kind is Parameter.KEYWORD_ONLY
    assert overwrite.default is False
