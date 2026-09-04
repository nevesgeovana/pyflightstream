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

from pyflightstream.cases import FluidState, ReferenceData, SimCase, SweepAxis
from pyflightstream.cases.matrix import (
    FLIGHT_CONDITION_KEYS,
    _parse_flight_condition,
)
from pyflightstream.cases.workflows import build_script
from pyflightstream.exceptions import MatrixError
from pyflightstream.script import Script
from pyflightstream.workspace.flight_condition import (
    PINNED_KEYS,
    FlightConditionError,
    resolve_flight_condition,
)


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
    # The five the author specified at 0.9.0, plus the five PINS of 0.11.0
    # (FR-54, PFS-2030.02), and no eleventh arrived unnoticed.
    assert set(FLIGHT_CONDITION_KEYS) == {"MACH", "TASmps", "REmi", "ALTFT", "dISA", *PINNED_KEYS}


def test_integers_and_negatives_and_exponents_are_numbers():
    """dISA is signed, and a user may write any float spelling."""
    assert _parse_flight_condition("dISA:-10", "P1") == {"dISA": -10.0}
    assert _parse_flight_condition("ALTFT:1e4", "P1") == {"ALTFT": 10000.0}
    assert _parse_flight_condition("MACH:.2", "P1") == {"MACH": 0.2}


# --- FR-54, PFS-2030.02: the five fluid pins ---------------------------------
#
# A row may state the constants the standard atmosphere would otherwise
# supply, so the emitted fluid block carries the numbers its author pinned.
# The three states below are the author's own, read off the scripts that
# produced her recorded campaign on 2026-09-02, asserted to the last digit:
# the reproduction arm of GOAL-011 compares the emitted line against hers
# as a number, and a fourth-digit difference is a different fluid.

CHORD_M = 2.526
HER_PINS = {"MUPas": 1.789e-5, "ASMPS": 340.29, "TK": 288.15, "PPA": 101325.0}


def test_every_pin_is_a_flight_condition_key():
    """The vocabulary is one table; a pin the reader refuses cannot be stated."""
    for key in PINNED_KEYS:
        assert key in FLIGHT_CONDITION_KEYS, f"{key} is a pin the cell parser does not accept"
        assert _parse_flight_condition(f"TASmps:68, {key}:1.0", "P1")[key] == 1.0


def test_pinned_fluid_constants_reach_the_script_verbatim():
    """Her steady state: density pinned, every constant hers, bit for bit.

    The emitted FLUID_PROPERTIES block is what the solver reads, so the
    assertion is on the rendered lines and not only on the resolver.
    """
    state = resolve_flight_condition(
        {"TASmps": 68.058, "RHOkgm3": 1.225, **HER_PINS}, pol="3207", reference_length_m=CHORD_M
    )
    assert state.density_kg_m3 == 1.225
    assert state.viscosity_pa_s == 1.789e-5
    assert state.sonic_velocity_m_per_s == 340.29
    assert state.density_source == "pinned"
    assert state.pinned == ("RHOkgm3", "MUPas", "ASMPS", "TK", "PPA")
    lines = _render_fluid(state)
    assert "DENSITY 1.225" in lines
    assert "VISCOSITY 1.789e-05" in lines
    assert "TEMPERATURE 288.15" in lines
    assert "PRESSURE 101325.0" in lines


def test_a_reynolds_constraint_solves_against_the_pinned_viscosity():
    """Her unsteady state: REmi against a pinned viscosity gives her density exactly."""
    state = resolve_flight_condition(
        {"TASmps": 68.058, "REmi": 11.7717, "MUPas": 1.789e-5},
        pol="3224",
        reference_length_m=CHORD_M,
    )
    assert state.density_kg_m3 == 1.2250025634834727
    assert state.density_source == "solved-from-reynolds"
    assert state.pinned == ("MUPas",)


def test_mach_is_taken_against_the_pinned_sonic_velocity():
    """Her rotor state: MACH times her sonic velocity, then REmi against her viscosity."""
    state = resolve_flight_condition(
        {"MACH": 0.1441, "REmi": 4.38, "MUPas": 1.789e-5, "ASMPS": 340.29},
        pol="9001",
        reference_length_m=CHORD_M,
    )
    assert state.velocity_m_per_s == 49.03578900000001
    assert state.density_kg_m3 == 0.6326127450123294


def test_no_pin_leaves_the_standard_atmosphere_unchanged():
    """Every condition written before 0.11.0 resolves exactly as it did."""
    state = resolve_flight_condition({"MACH": 0.20, "REmi": 5.5}, pol="P1", reference_length_m=1.0)
    assert round(state.velocity_m_per_s, 4) == 68.0588
    assert state.pinned == ()
    assert state.density_source == "solved-from-reynolds"
    assert state.viscosity_pa_s != 1.789e-5, "the standard viscosity is not her pinned one"


def test_a_pinned_density_beside_a_reynolds_number_is_refused():
    with pytest.raises(FlightConditionError, match="RHOkgm3") as refused:
        resolve_flight_condition(
            {"TASmps": 68.0, "RHOkgm3": 1.2, "REmi": 5.0}, pol="P1", reference_length_m=1.0
        )
    assert "REmi" in str(refused.value)


@pytest.mark.parametrize("key", sorted(PINNED_KEYS))
def test_a_non_positive_pin_is_refused_naming_the_key(key):
    with pytest.raises(FlightConditionError, match=key):
        resolve_flight_condition({"TASmps": 68.0, key: 0.0}, pol="P1", reference_length_m=1.0)


# --- FR-58, PFS-2030.08: a setup supplies the pins a row leaves out ----------
#
# Her instruction of 2026-09-04: the four constants her tool writes on every
# script are constants of the campaign's fluid, so they belong in the SETUP
# artifact a row names and not repeated down the FLIGHT_CONDITION column. The
# resolver owns which keys may be defaulted, because it owns the pin table;
# the caller supplies the origin string, because it knows which file the
# table came from and the refusal has to name it.

ORIGIN = "setup s001"


def test_a_setup_supplies_the_pins_a_row_leaves_out():
    """Her steady state, with the four constants moved out of the row.

    The assertion that carries the change is the LAST one: the same
    resolved state, to the last digit, as the row that stated all five.
    """
    state = resolve_flight_condition(
        {"TASmps": 68.058, "RHOkgm3": 1.225},
        pol="3207",
        reference_length_m=CHORD_M,
        defaults=HER_PINS,
        defaults_origin=ORIGIN,
    )
    assert state.viscosity_pa_s == 1.789e-5
    assert state.sonic_velocity_m_per_s == 340.29
    assert state.temperature_k == 288.15
    assert state.pressure_pa == 101325.0
    # AS WRITTEN stays as written: the row stated two keys and the record
    # says two, with the inherited four beside them rather than folded in.
    assert state.stated == {"TASmps": 68.058, "RHOkgm3": 1.225}
    assert state.defaulted == HER_PINS
    assert state.defaults_origin == ORIGIN
    # THE TWO MAPPINGS ARE DISJOINT, always, and the resolver's merge
    # therefore decides nothing: what the row states never enters
    # `defaulted`, which is where the row's precedence actually lives.
    assert not set(state.defaulted) & set(state.stated)
    # `pinned` is the union, in the pin table's own order, because what it
    # answers is which quantities were pinned rather than where from.
    assert state.pinned == ("RHOkgm3", "MUPas", "ASMPS", "TK", "PPA")
    stated_in_the_row = resolve_flight_condition(
        {"TASmps": 68.058, "RHOkgm3": 1.225, **HER_PINS},
        pol="3207",
        reference_length_m=CHORD_M,
    )
    assert _render_fluid(state) == _render_fluid(stated_in_the_row)


def test_a_row_pin_overrides_the_setup_default():
    """The row is the narrower statement and wins, key by key."""
    state = resolve_flight_condition(
        {"TASmps": 68.058, "ASMPS": 300.0},
        pol="P1",
        reference_length_m=CHORD_M,
        defaults=HER_PINS,
        defaults_origin=ORIGIN,
    )
    assert state.sonic_velocity_m_per_s == 300.0
    assert state.viscosity_pa_s == 1.789e-5, "the other three still come from the setup"
    assert "ASMPS" not in state.defaulted
    assert state.defaulted == {"MUPas": 1.789e-5, "TK": 288.15, "PPA": 101325.0}


def test_a_setup_density_default_yields_to_a_stated_reynolds():
    """The one default a row can supersede without contradicting it.

    A row stating RHOkgm3 AND REmi is refused, because each fixes the
    density and the two together are a contradiction. A SETUP that pins a
    density is not making that statement about this row: it is the
    campaign's fluid, and a row that solves its own density has simply
    determined that quantity itself. Refusing here would mean a setup
    carrying a density could never serve a Reynolds row, so the default is
    DROPPED, and the record says so by not listing it.
    """
    state = resolve_flight_condition(
        {"TASmps": 68.058, "REmi": 11.7717},
        pol="3224",
        reference_length_m=CHORD_M,
        defaults={"RHOkgm3": 1.225, "MUPas": 1.789e-5},
        defaults_origin=ORIGIN,
    )
    assert state.density_kg_m3 == 1.2250025634834727
    assert state.density_source == "solved-from-reynolds"
    assert state.defaulted == {"MUPas": 1.789e-5}
    assert state.pinned == ("MUPas",)


@pytest.mark.parametrize(
    ("key", "because"),
    [
        # EACH REFUSAL IS ASSERTED ON ITS OWN REASON and not merely on
        # the key, and a mutation is why: deleting the whole reason table
        # left every one of these green, because the generic "not a pin"
        # refusal below it also names the key, the origin and the pins.
        # A message that refuses for the wrong reason teaches the wrong
        # thing, and the reason is the entire content of this rule.
        ("MACH", "VELOCITY"),
        ("TASmps", "VELOCITY"),
        ("REmi", "DENSITY"),
        ("ALTFT", "atmosphere"),
        ("dISA", "atmosphere"),
    ],
)
def test_a_setup_flight_condition_table_refuses_a_key_that_states_the_point(key, because):
    """A point may not inherit what makes it that point.

    The velocity keys and REmi are what the resolver solves FOR, and a
    preset several rows share cannot state them: a row inheriting MACH
    would be a case nobody wrote, and it would look exactly like a row
    that stated one. ALTFT and dISA locate a point IN the atmosphere,
    which the pins exist to replace rather than to locate.
    """
    with pytest.raises(FlightConditionError, match=key) as refused:
        resolve_flight_condition(
            {"TASmps": 68.058},
            pol="P1",
            reference_length_m=CHORD_M,
            defaults={key: 0.2},
            defaults_origin=ORIGIN,
        )
    assert because in str(refused.value), "refused, but not for the reason the rule has"
    assert ORIGIN in str(refused.value)
    assert "MUPas" in str(refused.value), "the refusal lists what the table may hold"


def test_a_setup_flight_condition_table_refuses_a_key_it_has_never_heard_of():
    """The fallback the parametrised refusals above must NOT be answered by."""
    with pytest.raises(FlightConditionError, match="MUpas") as refused:
        resolve_flight_condition(
            {"TASmps": 68.058},
            pol="P1",
            reference_length_m=CHORD_M,
            defaults={"MUpas": 1.789e-5},
            defaults_origin=ORIGIN,
        )
    assert "not a flight-condition pin" in str(refused.value)
    assert ORIGIN in str(refused.value)


def test_a_non_positive_setup_default_is_refused_naming_the_setup():
    """The same rule as a row pin, and the message names the file to edit."""
    with pytest.raises(FlightConditionError, match="MUPas") as refused:
        resolve_flight_condition(
            {"TASmps": 68.058},
            pol="P1",
            reference_length_m=CHORD_M,
            defaults={"MUPas": 0.0},
            defaults_origin=ORIGIN,
        )
    assert ORIGIN in str(refused.value)


def test_no_defaults_resolves_exactly_as_before():
    """Every condition written before this node, unchanged and unpinned."""
    state = resolve_flight_condition({"MACH": 0.20, "REmi": 5.5}, pol="P1", reference_length_m=1.0)
    assert state.defaulted == {}
    assert state.defaults_origin is None
    assert state.pinned == ()
    assert round(state.velocity_m_per_s, 4) == 68.0588


def _render_fluid(state) -> list[str]:
    fluid = FluidState(
        velocity_m_per_s=state.velocity_m_per_s,
        density_kg_m3=state.density_kg_m3,
        pressure_pa=state.pressure_pa,
        temperature_k=state.temperature_k,
        viscosity_pa_s=state.viscosity_pa_s,
        sonic_velocity_m_per_s=state.sonic_velocity_m_per_s,
        heat_capacity_ratio=state.heat_capacity_ratio,
        source=state.density_source,
        reference_length_m=state.reference_length_m,
    )
    case = SimCase(
        sim_id="3207",
        aircraft="WB",
        sweep=SweepAxis(type="alpha", values=[-2.0]),
        recipe="steady",
        outputs=["loads_a-02.0.txt"],
        variables={"WORKFLOW": "steady"},
        point={"alpha": -2.0},
        velocity=state.velocity_m_per_s,
        reference=ReferenceData(area=50.0, length=CHORD_M),
        fluid=fluid,
    )
    script = Script("26.120")
    build_script(case, script)
    return script.render().splitlines()
