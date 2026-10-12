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
