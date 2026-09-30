"""Each block that cuts one blade of an unsteady rotor states THAT blade's azimuth (0.31.0).

The owner's requirement: the azimuth of each blade stated on every section
record. A quasi-steady wheel states it (`test_goal036_wheel_sections.py`); an
unsteady rotor's sections table and sections series used to state blade ONE's
azimuth on every block, whichever blade the block cut. Blade n of N now states
blade one's azimuth placed (n - 1) / N of a turn ahead, through
`post.axes.placed_blade_azimuth_deg`, the one home of that rule, and, as the
definitions page states, ahead of blade one whatever the sense of rotation:
the sense turns the CLOCK (the step), never the place of a blade on the disc.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-182.

from __future__ import annotations

import pytest

from pyflightstream.post._tables import section_identity
from pyflightstream.post.products import read_csv_table
from tests.tier1_offline.test_goal036_harmonics import (
    DATUM,
    PER_REVOLUTION,
    _post,
    _unsteady,
)

BLADES = 4


def _blade_one(step: int, sign: int) -> float:
    """Blade one at ``step``, worked by hand from the datum and the clock."""
    return (DATUM + sign * step * 360.0 / PER_REVOLUTION) % 360.0


@pytest.mark.parametrize("rpm", [1200.0, -1200.0])
def test_a_four_blade_unsteady_rotor_states_four_azimuths_ninety_degrees_apart(
    tmp_path, monkeypatch, rpm
):
    # P0310-H2-BLADE-AZIMUTH
    workspace = _unsteady(tmp_path, monkeypatch, blades=BLADES, rpm=rpm)
    out, _, _ = _post(workspace)
    sign = 1 if rpm > 0 else -1
    _, series = read_csv_table(out / "series" / "AL-020_sections_series.csv")
    assert {row["FAMILY"] for row in series} == {f"Blade{n}" for n in range(1, BLADES + 1)}
    for row in series:
        blade = int(row["FAMILY"].removeprefix("Blade"))
        expected = (_blade_one(int(row["STEP"]), sign) + (blade - 1) * 90.0) % 360.0
        assert float(row["AZIMUTH"]) == pytest.approx(expected, abs=1e-9), row["FAMILY"]
    # THE SECTIONS TABLE, one instant, states the same per block.
    _, table = read_csv_table(out / "sections" / "AL-020_sections.csv")
    assert {row["FAMILY"] for row in table} == {f"Blade{n}" for n in range(1, BLADES + 1)}
    for row in table:
        blade = int(row["FAMILY"].removeprefix("Blade"))
        expected = (_blade_one(int(row["STEP"]), sign) + (blade - 1) * 90.0) % 360.0
        assert float(row["AZIMUTH"]) == pytest.approx(expected, abs=1e-9), row["FAMILY"]
    # FOUR BLOCKS OF ONE STEP, four azimuths a quarter turn apart.
    for step in {int(row["STEP"]) for row in series}:
        at = {row["FAMILY"]: float(row["AZIMUTH"]) for row in series if int(row["STEP"]) == step}
        ordered = [at[f"Blade{n}"] for n in range(1, BLADES + 1)]
        assert [(b - a) % 360.0 for a, b in zip(ordered, ordered[1:], strict=False)] == (
            pytest.approx([90.0] * (BLADES - 1))
        )


def _rotor(**over: object) -> dict[str, dict[str, object]]:
    rotor: dict[str, object] = {
        "families": ["Blade1", "Blade2", "Blade3", "Blade4", "Hub"],
        "blade_families": [["Blade1"], ["Blade2"], ["Blade3"], ["Blade4"]],
        "steps_per_revolution": 72.0,
        "blade1_azimuth_deg": 10.0,
        "rpm": -1200.0,
    }
    rotor.update(over)
    return {"PROP": rotor}


def _layout() -> list[dict[str, object]]:
    plane = "XZ"
    return [
        {"families": ["Blade1"], "plane": plane, "count": 1},
        {"families": ["Blade2"], "plane": plane, "count": 1},
        {"families": ["Blade3"], "plane": plane, "count": 1},
        {"families": ["Blade4"], "plane": plane, "count": 1},
        {"families": ["Blade2", "Blade3"], "plane": plane, "count": 1},
        {"families": ["Hub"], "plane": plane, "count": 1},
        {"families": ["Wing"], "plane": plane, "count": 1},
    ]


def test_the_sections_table_reads_each_blades_own_azimuth_and_a_left_hand_rotor_keeps_the_place():
    # P0310-H2-BLADE-AZIMUTH
    identity = section_identity(7, _layout(), _rotor(), 18, None)
    # rpm < 0: blade one at 18 steps of 5 deg the negative way, 10 - 90 = 280.
    blade_one = 280.0
    assert [cell[3] for cell in identity[:4]] == pytest.approx(
        [(blade_one + 90.0 * n) % 360.0 for n in range(4)]
    )
    assert [cell[2] for cell in identity[:4]] == ["PROP"] * 4


def test_a_block_over_several_families_or_none_keeps_blade_ones_azimuth():
    # P0310-H2-BLADE-AZIMUTH
    identity = section_identity(7, _layout(), _rotor(), 18, None)
    # two blades in one block, and the rotor's general family: blade one's.
    assert identity[4][3] == pytest.approx(280.0)
    assert identity[5][3] == pytest.approx(280.0)
    # a block no rotor owns: none, as before.
    assert identity[6] == ("Wing", "XZ", None, None)


def test_a_rotor_that_states_no_blade_grouping_keeps_blade_ones_azimuth():
    # P0310-H2-BLADE-AZIMUTH
    rotors = _rotor()
    del rotors["PROP"]["blade_families"]
    identity = section_identity(7, _layout(), rotors, 18, None)
    assert [cell[3] for cell in identity[:6]] == pytest.approx([280.0] * 6)
