"""Regression coverage grouped by subject."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pytest

from pyflightstream._atmosphere import ISA, isa, sutherland_viscosity
from pyflightstream.cases.workflows import _freestream
from pyflightstream.results import bind_conditions as _integfix_conditions__bind_conditions
from pyflightstream.results import parse_loads
from pyflightstream.results.conditions import (
    bind_conditions as _results_conditions__bind_conditions,
)
from pyflightstream.script import Script
from pyflightstream.workspace import flight_condition
from pyflightstream.workspace.flight_condition import FlightConditionError, resolve_flight_condition
from tests.tier1_offline.test_workflows import (
    steady_case as _cases_workflows_freestream__steady_case,
)

_CASES_WORKFLOWS_FREESTREAM__FIELD = (
    b"2 2\n0 -2 -1 11 3 5\n0 -2 1 12 4 6\n0 2 -1 13 5 7\n0 2 1 14 6 8\n"
)


def _cases_workflows_freestream___with_field(tmp_path, unit: str) -> Script:
    source = tmp_path / "field.txt"
    source.write_bytes(_CASES_WORKFLOWS_FREESTREAM__FIELD)
    custom = _freestream._RowFreestream(
        path=str(source), form="STRUCTURED", source_units=None, extent=(-3.0, 3.0, -1.0, 1.0)
    )
    script = Script("26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", unit)
    _freestream._free_stream(_cases_workflows_freestream__steady_case(), script, {}, custom)
    return script


class TestCasesWorkflowsFreestream:
    """P0400-CW-FREESTREAM: the custom field's coverage, in the unit the field is known in.

    0.40.0 item PFS-2104.006: a field that declares no unit was read as metres in
    every simulation but MILLIMETER, so an INCH grid was compared with the body as
    if it were metres.
    """

    @staticmethod
    @pytest.mark.parametrize("unit", ["INCH", "FEET", "CENTIMETER", "MILLIMETER"])
    def test_p0400_cw_freestream_an_undeclared_field_is_unknown_outside_metres(tmp_path, unit):
        """P0400-CW-FREESTREAM (PFS-2104.006): the coverage record says unknown, and why."""
        requirement = "P0400-CW-FREESTREAM"
        with pytest.warns(UserWarning, match="coverage is not checked"):
            script = _cases_workflows_freestream___with_field(tmp_path, unit)
        assert script.custom_field_extent_m is None, requirement
        assert script.custom_field_coverage is not None
        assert script.custom_field_coverage["state"] == "unknown"
        assert unit in script.custom_field_coverage["reason"]

    @staticmethod
    def test_p0400_cw_freestream_an_undeclared_field_in_metres_is_checked(tmp_path):
        """P0400-CW-FREESTREAM (PFS-2104.006), control: a METER simulation keeps the check."""
        requirement = "P0400-CW-FREESTREAM"
        script = _cases_workflows_freestream___with_field(tmp_path, "METER")
        assert script.custom_field_extent_m == (-3.0, 3.0, -1.0, 1.0), requirement
        assert script.custom_field_coverage is None


_INTEGFIX_CONDITIONS__FIXTURE = Path(__file__).parent / "fixtures" / "loads_steady_26.120.txt"


def _integfix_conditions___export(printed: str) -> str:
    lines = _INTEGFIX_CONDITIONS__FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
    out = []
    for line in lines:
        if line.strip().startswith("Freestream velocity (m/s)"):
            line = line.replace("30.000", printed)
        out.append(line)
    text = "".join(out)
    assert f"Freestream velocity (m/s)                   {printed}" in text
    return text


class TestIntegfixConditions:
    """Tier 1, 0.40.0 integration fixes: a requested velocity is compared at the printed precision."""  # noqa: E501

    @staticmethod
    def test_p0400_a_velocity_is_held_to_the_digits_the_export_printed():
        """P0400-VELOCITY-PRINTED-PRECISION (PFS-2092.001): tolerance from the printed digits.

        The free-stream velocity was compared at 5e-4 m/s whatever width the export
        printed it with, so an export printing two decimals refused a requested
        velocity that rounds to the printed one. It is held to half a count of the
        printed digit; the three-decimal export keeps 5e-4 (the control).
        """
        coarse = parse_loads(_integfix_conditions___export("30.00"))
        assert coarse.print_tolerances == {"freestream_velocity_m_s": 0.005}
        assert not _integfix_conditions__bind_conditions(
            {"velocity": 30.003}, reported=coarse
        ).mismatches
        assert _integfix_conditions__bind_conditions(
            {"velocity": 30.006}, reported=coarse
        ).mismatches
        fine = parse_loads(_integfix_conditions___export("30.000"))
        assert abs(fine.print_tolerances["freestream_velocity_m_s"] - 5e-4) < 1e-12
        assert _integfix_conditions__bind_conditions({"velocity": 30.003}, reported=fine).mismatches


@dataclass
class _ResultsConditionsPrinted:
    """The three fields the binding reads, and nothing else."""

    angle_of_attack_deg: float = 2.0
    sideslip_deg: float = 0.0
    freestream_velocity_m_s: float = 30.0


class TestResultsConditions:
    """P0400-RESULTS (PFS-2105.044): the condition binding at the exact half count of the print."""

    pytestmark = pytest.mark.requirement("P0400-RESULTS-CONDITIONS")

    @staticmethod
    def test_p0400_results_half_count_is_within_the_print_tolerance():
        """P0400-RESULTS (PFS-2105.044): requested 0.0625 printed 0.063 is rounding, not a mismatch."""  # noqa: E501
        binding = _results_conditions__bind_conditions(
            {"alpha": 0.0625, "velocity": 30.0625},
            reported=_ResultsConditionsPrinted(
                angle_of_attack_deg=0.063, freestream_velocity_m_s=30.063
            ),
        )
        alpha = next(check for check in binding.checks if check.axis == "alpha")
        assert alpha.deviation > alpha.tolerance, (
            "the control: binary floating point puts the difference just past 5e-4"
        )
        assert binding.mismatch_free, binding.describe()

    @staticmethod
    def test_p0400_results_one_count_past_the_half_is_still_a_mismatch():
        """P0400-RESULTS (PFS-2105.044): the slack absorbs representation, not a real offset."""
        binding = _results_conditions__bind_conditions(
            {"alpha": 0.0624}, reported=_ResultsConditionsPrinted(angle_of_attack_deg=0.063)
        )
        assert not binding.mismatch_free


_REVIEWS2_FLIGHT_CONDITION__R = ISA.gas_constant_j_per_kg_k


_REVIEWS2_FLIGHT_CONDITION__GAMMA = ISA.heat_capacity_ratio


def _reviews2_flight_condition___triple_holds(state) -> bool:
    return state.pressure_pa == pytest.approx(
        state.density_kg_m3 * _REVIEWS2_FLIGHT_CONDITION__R * state.temperature_k, rel=1e-12
    )


class TestReviews2FlightCondition:
    """P0400-TKPIN (PFS-2081.23) and P0400-PTRIPLE (PFS-2104.050): one consistent gas state.

    A ``TK`` pin is the state's temperature, so the speed of sound, the Sutherland
    viscosity, the Mach conversion and the density follow it, exactly as they
    follow a ``dISA``. A solved or pinned density is emitted beside the pressure
    ``p = rho R T`` of that density at the state's temperature, unless ``PPA``
    pins it; an unconstrained density is the ideal-gas density of the pressure
    and temperature. Unpinned states keep the atmosphere's values to the bit.
    """

    @staticmethod
    def test_p0400_tkpin_sound_speed_viscosity_and_density_follow_the_pinned_temperature():
        """P0400-TKPIN: TK=400 moves a, mu, the Mach conversion and rho; the pressure stays."""
        state = resolve_flight_condition(
            {"MACH": 0.2, "TK": 400.0}, pol="P1", reference_length_m=1.0
        )
        sea = isa()
        assert state.temperature_k == 400.0
        assert state.sonic_velocity_m_per_s == pytest.approx(
            math.sqrt(_REVIEWS2_FLIGHT_CONDITION__GAMMA * _REVIEWS2_FLIGHT_CONDITION__R * 400.0),
            rel=1e-12,
        )
        assert state.viscosity_pa_s == pytest.approx(sutherland_viscosity(400.0), rel=1e-12)
        assert state.velocity_m_per_s == pytest.approx(
            0.2
            * math.sqrt(_REVIEWS2_FLIGHT_CONDITION__GAMMA * _REVIEWS2_FLIGHT_CONDITION__R * 400.0),
            rel=1e-12,
        )
        assert state.mach == pytest.approx(0.2, rel=1e-12)
        assert state.pressure_pa == sea.pressure_pa
        assert state.density_kg_m3 == pytest.approx(
            sea.pressure_pa / (_REVIEWS2_FLIGHT_CONDITION__R * 400.0), rel=1e-12
        )
        assert state.reynolds == pytest.approx(
            state.density_kg_m3 * state.velocity_m_per_s * 1.0 / state.viscosity_pa_s, rel=1e-12
        )
        assert _reviews2_flight_condition___triple_holds(state)

    @staticmethod
    def test_p0400_tkpin_its_own_pins_still_replace_what_the_temperature_would_give():
        """P0400-TKPIN: ASMPS and MUPas pins beside TK are emitted as written."""
        state = resolve_flight_condition(
            {"TASmps": 50.0, "TK": 400.0, "ASMPS": 340.29, "MUPas": 1.789e-5}, pol="P1"
        )
        assert state.sonic_velocity_m_per_s == 340.29
        assert state.viscosity_pa_s == 1.789e-5
        assert state.mach == pytest.approx(50.0 / 340.29, rel=1e-12)

    @staticmethod
    def test_p0400_tkpin_an_unpinned_state_is_the_atmosphere_to_the_bit():
        """P0400-TKPIN: with nothing pinned the resolved state equals isa() exactly."""
        state = resolve_flight_condition({"MACH": 0.3, "ALTFT": 10000, "dISA": 5}, pol="P1")
        air = isa(10000 * 0.3048, delta_isa_c=5)
        assert state.temperature_k == air.temperature_k
        assert state.sonic_velocity_m_per_s == air.sonic_velocity_m_per_s
        assert state.viscosity_pa_s == air.viscosity_pa_s
        assert state.density_kg_m3 == air.density_kg_m3
        assert state.pressure_pa == air.pressure_pa

    @staticmethod
    def test_p0400_ptriple_a_solved_density_carries_its_own_pressure():
        """P0400-PTRIPLE: REmi solves rho and the emitted pressure is rho R T, not sea level's."""
        state = resolve_flight_condition(
            {"MACH": 0.2, "REmi": 5.5}, pol="P1", reference_length_m=1.0
        )
        assert state.density_source == "solved-from-reynolds"
        assert state.density_kg_m3 == pytest.approx(1.446, abs=5e-4)
        assert state.pressure_pa == pytest.approx(119.6e3, rel=1e-3)
        assert _reviews2_flight_condition___triple_holds(state)

    @staticmethod
    def test_p0400_ptriple_a_pinned_density_carries_its_own_pressure():
        """P0400-PTRIPLE: RHOkgm3 alone gives p = rho R T at the state's temperature."""
        state = resolve_flight_condition({"MACH": 0.2, "RHOkgm3": 1.0, "TK": 300.0}, pol="P1")
        assert state.pressure_pa == pytest.approx(
            1.0 * _REVIEWS2_FLIGHT_CONDITION__R * 300.0, rel=1e-12
        )
        assert _reviews2_flight_condition___triple_holds(state)

    @staticmethod
    def test_p0400_ptriple_a_pinned_pressure_sets_the_density_and_pins_stay_as_written():
        """P0400-PTRIPLE: PPA alone sets rho = p / (R T); PPA beside a solved rho is kept."""
        alone = resolve_flight_condition({"MACH": 0.2, "PPA": 80000.0}, pol="P1")
        assert alone.pressure_pa == 80000.0
        assert alone.density_kg_m3 == pytest.approx(
            80000.0 / (_REVIEWS2_FLIGHT_CONDITION__R * isa().temperature_k), rel=1e-12
        )
        assert _reviews2_flight_condition___triple_holds(alone)
        pinned = resolve_flight_condition(
            {"MACH": 0.2, "REmi": 5.5, "PPA": 90000.0}, pol="P1", reference_length_m=1.0
        )
        assert pinned.pressure_pa == 90000.0

    @staticmethod
    def test_p0400_ptriple_the_module_no_longer_admits_an_inconsistent_triple():
        """P0400-PTRIPLE: the public docstring states the consistent triple, not an open question."""  # noqa: E501
        doc = " ".join((flight_condition.__doc__ or "").split())
        assert "not a consistent triple" not in doc
        assert "p = rho R T" in doc


class TestWorkspace2FlightCondition:
    """P0400-FCSIGNS: a flight condition's speed and Reynolds number are refused with the wrong sign."""  # noqa: E501

    @staticmethod
    @pytest.mark.parametrize(
        ("stated", "cell"),
        [
            ({"MACH": 0.2, "REmi": -5.5}, "REmi:-5.5"),
            ({"MACH": 0.2, "REmi": 0.0}, "REmi:0"),
            ({"MACH": -0.2}, "MACH:-0.2"),
            ({"TASmps": -50.0}, "TASmps:-50"),
        ],
    )
    def test_p0400_fcsigns_a_negative_speed_or_nonpositive_reynolds_is_refused(stated, cell):
        """P0400-FCSIGNS (PFS-2097.013): REmi <= 0 and a negative MACH or TASmps are refused
        naming the POL and the cell, never resolved into a zero or negative density or speed."""
        with pytest.raises(FlightConditionError) as caught:
            resolve_flight_condition(stated, pol="P7", reference_length_m=1.0)
        message = str(caught.value)
        assert "POL P7" in message and cell in message, message

    @staticmethod
    @pytest.mark.parametrize("stated", [{"MACH": 0.0}, {"TASmps": 0.0}])
    def test_p0400_fcsigns_hover_stays_legal(stated):
        """P0400-FCSIGNS (PFS-2097.013): zero speed is hover and is not refused."""
        state = resolve_flight_condition(stated, pol="P7", reference_length_m=1.0)
        assert state.velocity_m_per_s == 0.0
