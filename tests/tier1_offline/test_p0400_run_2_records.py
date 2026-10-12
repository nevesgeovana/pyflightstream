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
