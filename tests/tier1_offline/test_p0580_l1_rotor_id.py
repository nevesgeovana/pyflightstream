"""PFS-2231 (0.58.0, lane L1): every rotor declares an integer id, default 0, unique.

The design of the 0.58.0 post outputs (section 5.3, decision D6): ``id = <int>``
in the rotor block of the reference, ``>= 0``, unique within the reference,
default 0; two rotors without ids, or two with the same id, are refused by
name, naming both aliases.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import InputValueError
from pyflightstream.cases.reference_blocks import RotorBlock, refuse_duplicate_rotor_ids

_BLOCK = {"axis": "Z", "diameter_m": 1.2, "families_blades": ["Blade1", "Blade2"]}


def _rotor(alias: str, **extra: object) -> RotorBlock:
    return RotorBlock(alias=alias, **_BLOCK, **extra)


def test_a_rotor_that_writes_no_id_is_rotor_zero():
    assert _rotor("PUSHER").id == 0


def test_a_rotor_states_its_id():
    assert _rotor("LIFT_L1", id=3).id == 3


@pytest.mark.parametrize("value", [-1, 1.5, "2", True])
def test_an_id_that_is_not_a_non_negative_integer_is_refused(value):
    with pytest.raises(ValueError):
        _rotor("PUSHER", id=value)


def test_two_rotors_with_one_id_are_refused_naming_both():
    rotors = {"LEFT": _rotor("LEFT", id=2), "RIGHT": _rotor("RIGHT", id=2)}
    with pytest.raises(InputValueError) as caught:
        refuse_duplicate_rotor_ids(rotors)
    message = str(caught.value)
    assert "LEFT" in message and "RIGHT" in message and "id = 2" in message


def test_two_rotors_without_ids_are_refused_naming_both():
    rotors = {"TRACTOR": _rotor("TRACTOR"), "PUSHER": _rotor("PUSHER")}
    with pytest.raises(InputValueError) as caught:
        refuse_duplicate_rotor_ids(rotors)
    message = str(caught.value)
    assert "TRACTOR" in message and "PUSHER" in message and "id = 0" in message


def test_distinct_ids_and_one_default_pass():
    refuse_duplicate_rotor_ids({"A": _rotor("A"), "B": _rotor("B", id=1), "C": _rotor("C", id=7)})
