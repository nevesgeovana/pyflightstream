"""Tier 1: the FLIGHT_CONDITION cell parses, and refuses what it does not know.

PFS-2027.01, and the format change of D5 that carries it: the RE and
MACH columns were REMOVED at 0.9.0 and the flight condition replaced
them, so a row states its whole flow condition in one place.

WHAT THIS MODULE TESTS AND WHAT IT DOES NOT. The parser turns a cell
into canonical keys and floats and refuses what is not in the closed
set. It does NOT resolve: deciding which unknown a constraint set leaves
and solving for it is PFS-2027.02, one layer up, where a row can reach
the reference artifact for a length. The refusal that stands in for that
resolver until it lands is tested here too, because a constraint that is
parsed and then dropped would be worse than one that is refused.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases.matrix import (
    FLIGHT_CONDITION_KEYS,
    _parse_flight_condition,
)
from pyflightstream.exceptions import MatrixError


def test_the_authors_two_examples_parse_to_the_pairs_they_name():
    """The acceptance sentence's own two examples, verbatim."""
    assert _parse_flight_condition("MACH:0.20, REmi:5.5", "P1") == {
        "MACH": 0.20,
        "REmi": 5.5,
    }
    assert _parse_flight_condition("TASmps:68.08, ALTFT:10000, dISA:5", "P1") == {
        "TASmps": 68.08,
        "ALTFT": 10000.0,
        "dISA": 5.0,
    }


@pytest.mark.parametrize(
    "cell",
    [
        "MACH:0.20, REmi:5.5",
        "  MACH:0.20,   REmi:5.5  ",
        "MACH : 0.20 , REmi : 5.5",
        "MACH:0.20,REmi:5.5",
        "\tMACH:\t0.20\t,\tREmi:\t5.5\t",
    ],
)
def test_whitespace_around_the_separators_and_the_colon_is_accepted(cell):
    """One spacing per case, so a failure names the spacing that broke."""
    assert _parse_flight_condition(cell, "P1") == {"MACH": 0.20, "REmi": 5.5}


def test_an_empty_cell_is_no_condition_rather_than_a_refusal():
    """A row that states none is legal; what that means is decided above."""
    assert _parse_flight_condition("", "P1") == {}
    assert _parse_flight_condition("   ", "P1") == {}


def test_an_unrecognised_key_is_refused_naming_it_and_the_accepted_set():
    """The clause the whole closed-set design exists for."""
    with pytest.raises(MatrixError) as raised:
        _parse_flight_condition("MACH:0.20, KEAS:120", "P7")
    message = str(raised.value)
    assert "'KEAS'" in message
    assert "P7" in message
    for key in FLIGHT_CONDITION_KEYS:
        assert key in message, f"the refusal does not list the accepted key {key}"


def test_a_value_that_is_not_a_number_is_refused_naming_key_and_value():
    with pytest.raises(MatrixError) as raised:
        _parse_flight_condition("MACH:fast", "P7")
    message = str(raised.value)
    assert "MACH" in message
    assert "'fast'" in message
    assert "P7" in message
    # And the unit is named, because a reader who typed a word into a
    # number field is the reader who most needs to know which number.
    assert FLIGHT_CONDITION_KEYS["MACH"][0] in message


def test_a_duplicated_key_is_refused_rather_than_last_wins():
    """The clause where this parser deliberately differs from its neighbour.

    The general VAR_NAMES_VALUES parser beside this one takes the last
    value silently. That is right for free case data and wrong for a
    constraint on a flow state.
    """
    with pytest.raises(MatrixError) as raised:
        _parse_flight_condition("MACH:0.20, MACH:0.35", "P7")
    message = str(raised.value)
    assert "MACH" in message
    assert "more than once" in message
    assert "0.35" in message


def test_a_duplicate_is_detected_on_the_canonical_key_not_the_spelling():
    """Case-insensitive matching would otherwise open a silent last-wins."""
    with pytest.raises(MatrixError) as raised:
        _parse_flight_condition("MACH:0.20, mach:0.35", "P7")
    assert "more than once" in str(raised.value)


@pytest.mark.parametrize(
    ("written", "canonical"),
    [
        ("MACH:0.2", "MACH"),
        ("mach:0.2", "MACH"),
        ("MaCh:0.2", "MACH"),
        ("REmi:5.5", "REmi"),
        ("remi:5.5", "REmi"),
        ("REMI:5.5", "REmi"),
        ("dISA:5", "dISA"),
        ("disa:5", "dISA"),
        ("DISA:5", "dISA"),
        ("TASmps:68.08", "TASmps"),
        ("tasmps:68.08", "TASmps"),
        ("ALTFT:10000", "ALTFT"),
        ("altft:10000", "ALTFT"),
    ],
)
def test_keys_match_case_insensitively_and_report_canonically(written, canonical):
    """Tested EITHER WAY, which is what the acceptance sentence asks.

    The decision itself is stated in the parser's docstring: matching is
    case-insensitive because REmi, TASmps and dISA carry deliberate
    internal capitals a user types from memory, and refusing 'remi'
    would be refusing a correct intention on a shift key.
    """
    parsed = _parse_flight_condition(written, "P1")
    assert list(parsed) == [canonical]


def test_an_entry_that_is_not_a_key_value_pair_is_refused():
    with pytest.raises(MatrixError) as raised:
        _parse_flight_condition("MACH:0.20, REmi", "P7")
    assert "'REmi'" in str(raised.value)


def test_an_empty_entry_between_commas_is_refused():
    """A trailing or doubled comma is a typo, not an empty constraint."""
    with pytest.raises(MatrixError) as raised:
        _parse_flight_condition("MACH:0.20,,REmi:5.5", "P7")
    assert "empty entry" in str(raised.value)
    with pytest.raises(MatrixError):
        _parse_flight_condition("MACH:0.20,", "P7")


@pytest.mark.parametrize("written", ["nan", "NaN", "inf", "-inf", "Infinity"])
def test_a_non_finite_value_is_refused(written):
    """float() accepts these; a flow condition does not.

    Found by an independent review. A NaN density travels through the
    resolver and out into an emitted script as the text 'nan', and
    nothing downstream refuses it, so the solver reads whatever it
    reads. Refused where every other malformed value is refused.
    """
    with pytest.raises(MatrixError) as raised:
        _parse_flight_condition(f"MACH:{written}", "P7")
    assert "finite" in str(raised.value)
    assert "P7" in str(raised.value)


def test_the_key_order_written_is_the_order_returned():
    """The record has to be able to show the condition AS WRITTEN."""
    parsed = _parse_flight_condition("dISA:5, ALTFT:10000, TASmps:68.08", "P1")
    assert list(parsed) == ["dISA", "ALTFT", "TASmps"]


def test_every_accepted_key_states_its_unit_and_what_it_constrains():
    """The table is the vocabulary, so it may not carry a blank row."""
    for key, (unit, constrains) in FLIGHT_CONDITION_KEYS.items():
        assert unit.strip(), f"{key} declares no unit"
        assert constrains.strip(), f"{key} declares nothing it constrains"
    # The five the author specified, and no sixth arrived unnoticed.
    assert set(FLIGHT_CONDITION_KEYS) == {"MACH", "TASmps", "REmi", "ALTFT", "dISA"}


def test_integers_and_negatives_and_exponents_are_numbers():
    """dISA is signed, and a user may write any float spelling."""
    assert _parse_flight_condition("dISA:-10", "P1") == {"dISA": -10.0}
    assert _parse_flight_condition("ALTFT:1e4", "P1") == {"ALTFT": 10000.0}
    assert _parse_flight_condition("MACH:.2", "P1") == {"MACH": 0.2}
