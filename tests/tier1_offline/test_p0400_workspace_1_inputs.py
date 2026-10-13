"""P0400-WSINPUTS: the reference artifact's lifted tables (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import pytest

from pyflightstream.workspace import CampaignWorkspace, InputArtifactError

pytestmark = pytest.mark.requirement("P0400-WSINPUTS")


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ('[frames]\nname = "F1"\norigin = [0.0, 0.0, 0.0]\n', r"\[\[frames\]\] once per frame"),
        ('aliases = ["a"]\n', r"\[aliases\] with \['a'\] not a list"),
        ('[aliases]\nlifters = "Wing"\n', r"\[aliases\] with lifters not a list"),
    ],
    ids=["frames-single-brackets", "aliases-a-list", "alias-not-a-list"],
)
def test_p0400_wsinputs_a_malformed_frames_or_aliases_table_is_refused(tmp_path, text, named):
    """P0400-WSINPUTS (PFS-2095.058): the reference refuses the shape, as the setup preset does."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "references" / "r001.toml").write_text(text, encoding="utf-8")
    with pytest.raises(InputArtifactError, match=named):
        workspace.resolve_reference("r001")
