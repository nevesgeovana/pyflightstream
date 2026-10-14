"""A pproc refusal identifies each invalid field, including its probe index."""

import json

import pytest

from pyflightstream.workspace import InputArtifactError, PprocArtifact, resolve_pproc


@pytest.mark.parametrize("entry", ["constructor", "mapping", "json", "file"])
def test_pproc_refusal_keeps_field_locations(entry, tmp_path):
    """An engineer can locate both mistakes from the displayed refusal alone."""
    payload = {"unexpected": True, "probes": [{"points": 3}, {"points": 1}]}
    path = tmp_path / "pproc" / "p001.toml"
    if entry == "file":
        path.parent.mkdir()
        path.write_text(
            "unexpected = true\n[[probes]]\npoints = 3\n[[probes]]\npoints = 1\n",
            encoding="utf-8",
        )
    with pytest.raises(InputArtifactError) as caught:
        if entry == "constructor":
            PprocArtifact(**payload)
        elif entry == "mapping":
            PprocArtifact.model_validate(payload)
        elif entry == "json":
            PprocArtifact.model_validate_json(json.dumps(payload))
        else:
            resolve_pproc(tmp_path, "p001")
    message = str(caught.value)
    assert "probes.1.points: Input should be greater than or equal to 2" in message
    assert "unexpected: Extra inputs are not permitted" in message
    if entry == "file":
        assert str(path) in message
