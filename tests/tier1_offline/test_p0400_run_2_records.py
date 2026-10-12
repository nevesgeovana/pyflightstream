"""Tier 1, 0.40.0 lane run-2: the records commands, the manifests they read and archive.

Every fixture is synthetic.
"""

from __future__ import annotations

import pytest

from pyflightstream.run import records
from pyflightstream.workspace import CampaignWorkspace


def test_p0400_from_sims_name_is_refused_in_any_case(tmp_path):
    """P0400-FROM-SIMS-FOLD (PFS-2094.033): ``--runs Sims.json`` is refused like ``sims.json``.

    On a case-insensitive file system post/<matrix>@Sims/ is the folder of the
    from-sims post.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.root / "Sims.json").write_text("[]", encoding="utf-8")
    with pytest.raises(records.RunsManifestError, match="--from-sims"):
        records.manifest_workspace(workspace.root, "Sims.json")


def test_p0400_mark_failed_numbers_a_second_archive_within_one_stamp(tmp_path, monkeypatch):
    """P0400-ARCHIVE-FREE (PFS-2096.006): two marks in one second keep both copies of runs.json.

    The hand-built name overwrote the first copy; free_root_archive numbers
    the second ``.2``, which restore finds.
    """
    from tests.tier1_offline.test_mark_failed import _workspace

    workspace = _workspace(tmp_path)
    monkeypatch.setattr(records, "_now_stamp", lambda: "20261012-120000")
    first = workspace.manifest_path.read_bytes()
    records.mark_failed(workspace.root, ["2006"], reason="first", apply=True)
    second = workspace.manifest_path.read_bytes()
    records.mark_failed(workspace.root, ["2008"], reason="second", apply=True)
    archive = workspace.root / "archive"
    assert (archive / "runs-20261012-120000.json").read_bytes() == first
    assert (archive / "runs-20261012-120000.2.json").read_bytes() == second


@pytest.mark.parametrize("sims", ["2006,2007", "2006"])
def test_p0400_mark_failed_refuses_a_bare_string_of_ids(tmp_path, sims):
    """P0400-SIMS-STRING (PFS-2089.009): a str is refused in Python terms, never iterated.

    ``"2006,2007"`` read character by character was refused as simulations
    2, 0, 6, and the message told a Python caller to write the ids comma separated.
    """
    from tests.tier1_offline.test_mark_failed import _workspace

    workspace = _workspace(tmp_path)
    with pytest.raises(records.RunsManifestError, match=r"sims takes a list of ids, e\.g\. \["):
        records.mark_failed(workspace.root, sims)
