"""Read-time reproduction: resolve_setup(inputs, 's001') must refuse bad bounds."""

from pathlib import Path

import pytest

from pyflightstream.workspace import InputArtifactError, resolve_setup


@pytest.mark.parametrize(
    ("field", "value", "bound"),
    [
        ("significant_digits", "9", "8"),
        ("solver_stabilization", "1.1", "1"),
        ("significant_digits", "0", "1"),
        ("solver_stabilization", "-0.1", "0"),
        ("farfield_layers", "6", "5"),
    ],
    ids=[
        "P0410-digits-high",
        "P0410-strength-high",
        "P0410-digits-low",
        "P0410-strength-low",
        "P0410-existing-bound",
    ],
)
def test_p0410_fx5_setup_refuses_bounds_when_read(tmp_path, field, value, bound):
    inputs = tmp_path / "inputs"
    setups = inputs / "setups"
    setups.mkdir(parents=True)
    path = setups / "s001.toml"
    content = f"{field} = {value}\n"
    path.write_text(content, encoding="utf-8")
    before = sorted(tmp_path.rglob("*"))

    with pytest.raises(InputArtifactError) as caught:
        resolve_setup(inputs, "s001")

    message = str(caught.value)
    assert str(path) in message
    assert field in message
    assert (
        f"{'less' if float(value) > float(bound) else 'greater'} than or equal to {bound}"
        in message
    )
    assert sorted(tmp_path.rglob("*")) == before
    assert path.read_text(encoding="utf-8") == content


@pytest.mark.parametrize(
    "digits,strength", [(1, 0.0), (8, 1.0)], ids=["P0410-lower-edges", "P0410-upper-edges"]
)
def test_p0410_fx5_setup_keeps_valid_raw_values(tmp_path, digits, strength):
    setups = tmp_path / "setups"
    setups.mkdir()
    (setups / "s001.toml").write_text(
        f"significant_digits = {digits}\nsolver_stabilization = {strength}\n"
        'description = "preset metadata"\n[flight_condition]\naltitude_m = 0\n',
        encoding="utf-8",
    )
    settings = resolve_setup(tmp_path, "s001").settings
    assert settings == {
        "significant_digits": digits,
        "solver_stabilization": strength,
        "description": "preset metadata",
        "flight_condition": {"altitude_m": 0},
    }


def test_p0410_fx5_classic_examples_and_committed_fixture_setups_read():
    root = Path(__file__).resolve().parents[2]
    paths = sorted((root / "examples" / "using-CLI").glob("*/inputs/setups/*.toml"))
    assert len(paths) == 4
    fixtures = sorted((root / "tests" / "tier3_licensed" / "inputs" / "setups").glob("*.toml"))
    assert fixtures
    for path in paths + fixtures:
        assert resolve_setup(path.parent.parent, path.stem).settings
