"""B03: an existing invalid artifact must not be reported as missing."""

import pytest

from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.inputs import InputArtifactError
from pyflightstream.workspace.matrix import _resolve_code


@pytest.mark.parametrize(
    ("kind", "subdir", "code", "column"),
    [
        ("reference", "references", "rBad", "REF"),
        ("setup", "setups", "sBad", "SET"),
        ("pproc", "pproc", "pBad", "PPROC"),
    ],
)
def test_existing_invalid_artifact_leads_with_validation(tmp_path, kind, subdir, code, column):
    workspace = CampaignWorkspace(tmp_path)
    path = workspace.inputs_dir / subdir / f"{code}.toml"
    path.parent.mkdir(parents=True)
    content = 'frames = "unknown_field"\n' if kind == "setup" else 'unknown_field = "invalid"\n'
    path.write_text(content, encoding="utf-8", newline="\n")
    with pytest.raises(InputArtifactError) as caught:
        _resolve_code(workspace, kind, code, "7001")
    message = str(caught.value)
    assert message.startswith(
        f"matrix row POL 7001: the {kind} artifact at {path} does not validate."
    ), message
    assert "unknown_field" in message
    assert "cannot resolve" not in message
    assert "put the artifact" not in message


@pytest.mark.parametrize(
    ("kind", "subdir", "code", "column"),
    [
        ("reference", "references", "rMissing", "REF"),
        ("setup", "setups", "sMissing", "SET"),
        ("pproc", "pproc", "pMissing", "PPROC"),
    ],
)
def test_missing_artifact_leads_with_resolution_remedy(tmp_path, kind, subdir, code, column):
    workspace = CampaignWorkspace(tmp_path)
    with pytest.raises(InputArtifactError) as caught:
        _resolve_code(workspace, kind, code, "7001")
    assert str(caught.value).startswith(
        f"matrix row POL 7001: the {column} column names {kind} {code!r}, which "
        "the workspace input library cannot resolve; "
        f"put the artifact at inputs/{subdir}/{code}.toml, "
        "or fix the matrix code."
    )
