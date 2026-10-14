"""Regression coverage for the documented pproc artifact refusal boundary."""

import json

import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamError
from pyflightstream.workspace.inputs import PprocArtifact, resolve_pproc


@pytest.mark.parametrize("entry", ["constructor", "mapping", "json"])
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"groups": {"Blade": ["Blade1"]}},
            "pproc [groups] entry 'Blade': member lists were removed in 0.26.0. "
            'Write Blade = "Blade1" instead.',
        ),
        (
            {"vtk_variables": ["NOT_A_VARIABLE"]},
            "vtk_variables: unknown variable(s) NOT_A_VARIABLE",
        ),
        ({"unexpected": True}, "unexpected: Extra inputs are not permitted"),
        (
            {"probes": [{"points": 1}]},
            "probes.0.points: Input should be greater than or equal to 2",
        ),
    ],
    ids=["P0400-MEMBER-LIST", "P0400-VTK", "P0400-EXTRA", "P0400-NESTED"],
)
def test_p0400_artifact_refusals_keep_the_public_class_and_message(entry, payload, message):
    with pytest.raises(InputArtifactError) as caught:
        if entry == "constructor":
            PprocArtifact(**payload)
        elif entry == "mapping":
            PprocArtifact.model_validate(payload)
        else:
            PprocArtifact.model_validate_json(json.dumps(payload))
    assert type(caught.value) is InputArtifactError
    assert isinstance(caught.value, PyflightstreamError)
    assert str(caught.value) == message
    assert caught.value.kind == "pproc"


def test_p0400_artifact_loader_keeps_the_path_with_the_public_refusal(tmp_path):
    path = tmp_path / "pproc" / "p001.toml"
    path.parent.mkdir()
    path.write_text('[groups]\nBlade = ["Blade1"]\n', encoding="utf-8")
    with pytest.raises(InputArtifactError) as caught:
        resolve_pproc(tmp_path, "p001")
    assert str(path) in str(caught.value)
    assert 'Write Blade = "Blade1" instead.' in str(caught.value)
