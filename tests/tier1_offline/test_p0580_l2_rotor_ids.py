"""The rotor ids of a reference (PFS-2231, lane L2).

THE REQUIREMENT (design of the post outputs, sections 4.4 and 5.3). Two rotors of
one id are refused naming both, two rotors without ids included; an id of 90 or
more is refused naming the group id rule (the group of rotor <id> is 10 + id and
the declared groups are 100 + k).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-L2-ROTOR-IDS")])


def _reference(tmp_path, ids, names=None):
    from pyflightstream.workspace.inputs import resolve_reference

    text = "area_m2 = 1.0\nchord_m = 1.0\nspan_m = 1.0\n"
    for index, rotor_id in enumerate(ids):
        alias = names[index] if names is not None else f"R{index}"
        text += (
            f'\n[rotors."{alias}"]\nalias = "{alias}"\naxis = "X"\ndiameter_m = 1.0\n'
            f'families_blades = ["B{index}"]\nblade1 = {{ azimuth_deg = 0.0, zero = "Y" }}\n'
        )
        if rotor_id is not None:
            text += f"id = {rotor_id}\n"
    folder = tmp_path / "references"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "r.toml").write_text(text, encoding="utf-8")
    return resolve_reference(tmp_path, "r")


def test_two_rotors_without_ids_are_refused_naming_both(tmp_path):
    with pytest.raises(Exception) as caught:
        _reference(tmp_path, [None, None])
    assert "R0" in str(caught.value) and "R1" in str(caught.value)


def test_distinct_rotor_ids_are_read(tmp_path):
    artifact = _reference(tmp_path, [1, 2])
    assert [block.id for block in artifact.rotors.values()] == [1, 2]


def test_a_rotor_id_of_90_is_refused_naming_the_group_id_rule(tmp_path):
    with pytest.raises(Exception) as caught:
        _reference(tmp_path, [90])
    text = str(caught.value)
    assert "id = 90" in text and "10 + id" in text and "101" in text, text
    assert _reference(tmp_path / "ok", [89]).rotors["R0"].id == 89


@pytest.mark.parametrize(
    "names", [("TOTAL",), ("airframe",), ("Total/",), ("Left/Right", "Left_Right")]
)
def test_p0580_rotor_group_file_collisions_are_refused_at_reference_read(tmp_path, names):
    from pyflightstream.exceptions import InputArtifactError

    with pytest.raises(InputArtifactError, match="group file") as refused:
        _reference(tmp_path, list(range(len(names))), names)
    for alias in names:
        assert alias in str(refused.value)
    assert "another alias" in str(refused.value)
