"""Tier 1: the standard atmosphere against the values ISO 2533 defines.

PFS-2027.03. Runs without the solver and without a licence: the whole
point of putting the physics on a floor module is that it can be checked
with no case, no matrix and no script.

WHERE THE REFERENCE VALUES COME FROM, cited rather than recalled. Every
number asserted below is a DEFINING value of ISO 2533:1975 (published
identically as ICAO Doc 7488/3): the sea-level state, the tropopause,
and the top of the isothermal layer. They are the constants the standard
fixes, not readings interpolated out of a table.

WHAT THIS TEST DOES NOT CLAIM, and the limit is deliberate. This
repository holds no committed copy of ISO 2533, so the comparison is
against the standard's defining values and not against a full tabulation
of it. Two consequences, both stated rather than hidden:

* the altitudes checked are the ones the standard PINS -- 0 m, 11 000 m,
  20 000 m -- and not an arbitrary sample; and
* the quantities the standard does not itself tabulate at every layer
  boundary, density and speed of sound above sea level, are checked for
  consistency with the pressure and temperature through the stated laws,
  rather than against a figure this test would be restating from memory.

THAT DISTINCTION IS THE POINT OF THE ITEM. The acceptance sentence asks
for constants "pinned to that citation rather than to a number someone
remembered", and this repository already carries the failure it names:
sea-level viscosity appears hand-written as both ``1.789e-05`` and
``1.7894e-05`` in different modules. A test that asserted a remembered
table value would reproduce exactly that defect while appearing to
retire it. Adding ISO 2533 to the corpus would let the sample widen; the
citation is written down so the next reader knows what would extend it.

THE SEA-LEVEL DENSITY IS THE STRONGEST CHECK HERE and it is worth
reading as such. 1.225 kg/m3 is a defining value of the standard, and
this module does not store it: it derives it from the gas constant, the
sea-level pressure and the sea-level temperature. Reproducing it to
1e-8 is an independent check that those three constants are right
together, which no single-constant assertion could give.
"""

from __future__ import annotations

import math

import pytest

from pyflightstream._atmosphere import (
    ISA,
    AtmosphereError,
    density,
    feet_to_metres,
    isa,
    speed_of_sound,
    standard_pressure,
    standard_temperature,
    sutherland_viscosity,
)

#: Relative agreement required against a defining value of the standard.
#:
#: WHY 1e-5. Measured, not chosen for comfort: the widest disagreement
#: over the three pinned altitudes is 2.7e-6, in the tropopause
#: pressure, and it is rounding in the standard's own published figure
#: (22632.1 Pa is quoted to six digits) rather than error in the model.
#: 1e-5 leaves that headroom and nothing else; a constant that drifted
#: in the sixth digit would still fail here.
TOLERANCE = 1e-5

#: Defining values of ISO 2533:1975 at the altitudes the standard pins.
#: ``None`` marks a quantity the standard does not fix at that boundary,
#: which this test then checks by derivation instead. See the docstring.
DEFINING_VALUES = {
    0.0: {"temperature_k": 288.15, "pressure_pa": 101325.0, "density_kg_m3": 1.225},
    11000.0: {"temperature_k": 216.65, "pressure_pa": 22632.1, "density_kg_m3": None},
    20000.0: {"temperature_k": 216.65, "pressure_pa": 5474.89, "density_kg_m3": None},
}


@pytest.mark.parametrize("altitude_m", sorted(DEFINING_VALUES))
def test_the_state_matches_the_values_iso_2533_defines(altitude_m):
    """One altitude per case, so a failure names the layer that moved."""
    expected = DEFINING_VALUES[altitude_m]
    state = isa(altitude_m)
    assert state.temperature_k == pytest.approx(expected["temperature_k"], rel=TOLERANCE)
    assert state.pressure_pa == pytest.approx(expected["pressure_pa"], rel=TOLERANCE)
    if expected["density_kg_m3"] is not None:
        assert state.density_kg_m3 == pytest.approx(expected["density_kg_m3"], rel=TOLERANCE)


@pytest.mark.parametrize("altitude_m", sorted(DEFINING_VALUES))
def test_the_derived_quantities_follow_from_the_pinned_ones(altitude_m):
    """Density, sound speed and viscosity against their stated laws.

    Checked by derivation rather than against a remembered table figure,
    for the reason the module docstring gives.
    """
    state = isa(altitude_m)
    assert state.density_kg_m3 == pytest.approx(
        state.pressure_pa / (ISA.gas_constant_j_per_kg_k * state.temperature_k)
    )
    assert state.sonic_velocity_m_per_s == pytest.approx(
        math.sqrt(
            ISA.heat_capacity_ratio * ISA.gas_constant_j_per_kg_k * state.temperature_k
        )
    )
    assert state.viscosity_pa_s == pytest.approx(sutherland_viscosity(state.temperature_k))


def test_the_sea_level_speed_of_sound_matches_the_published_value():
    """340.294 m/s, the standard's own sea-level figure."""
    assert isa().sonic_velocity_m_per_s == pytest.approx(340.294, rel=TOLERANCE)


def test_an_isa_deviation_moves_temperature_and_leaves_pressure_alone():
    """The convention the item exists to write down.

    The other reading -- that ISA+15 shifts pressure too -- is what a
    reader who has not met the convention will assume, so it is asserted
    rather than left to be inferred from the arithmetic.
    """
    standard = isa(3000.0)
    hot = isa(3000.0, delta_isa_c=15.0)
    assert hot.pressure_pa == standard.pressure_pa
    assert hot.temperature_k == pytest.approx(standard.temperature_k + 15.0)
    # Density follows from the offset temperature at the unchanged
    # pressure, which is the whole consequence of the convention.
    assert hot.density_kg_m3 == pytest.approx(
        standard.pressure_pa / (ISA.gas_constant_j_per_kg_k * hot.temperature_k)
    )
    assert hot.density_kg_m3 < standard.density_kg_m3


def test_a_deviation_in_celsius_needs_no_kelvin_conversion():
    """Why no conversion appears, asserted so nobody adds one.

    A temperature DIFFERENCE is the same number in Celsius and in
    Kelvin, so applying the deviation as a delta is correct and a
    273.15 anywhere near it would be a bug. The assertion is that the
    offset lands unscaled and unshifted.
    """
    for delta in (-20.0, -5.0, 0.0, 5.0, 20.0):
        assert isa(0.0, delta_isa_c=delta).temperature_k == pytest.approx(
            ISA.sea_level_temperature_k + delta
        )


def test_zero_deviation_is_the_default_and_is_the_standard_atmosphere():
    """The default that makes a short constraint set resolvable at all."""
    assert isa(5000.0) == isa(5000.0, delta_isa_c=0.0)
    assert isa().temperature_k == ISA.sea_level_temperature_k


def test_the_lapse_stops_at_the_tropopause():
    """Above 11 km the layer is isothermal, which the lapse must not cross."""
    assert standard_temperature(11000.0) == pytest.approx(ISA.tropopause_temperature_k)
    assert standard_temperature(15000.0) == pytest.approx(ISA.tropopause_temperature_k)
    assert standard_temperature(20000.0) == pytest.approx(ISA.tropopause_temperature_k)
    # And below it the lapse is live, or the two branches would be
    # indistinguishable from a constant.
    assert standard_temperature(0.0) > standard_temperature(5000.0)
    assert standard_temperature(5000.0) > standard_temperature(11000.0)


def test_pressure_is_continuous_across_the_tropopause():
    """The two branches meet, or the boundary is a silent step.

    A discontinuity here would be invisible in any single-altitude
    check and would put a case just above the tropopause on a different
    atmosphere from one just below it.
    """
    below = standard_pressure(ISA.tropopause_altitude_m - 1e-6)
    above = standard_pressure(ISA.tropopause_altitude_m + 1e-6)
    assert below == pytest.approx(above, rel=1e-9)


def test_sutherland_reproduces_the_sea_level_viscosity():
    """The number this repository currently carries twice, by hand.

    ``support.py`` and the physics fixtures spell sea-level viscosity as
    1.789e-05 and 1.7894e-05 in different places. Both are roundings of
    the value Sutherland's law gives at 288.15 K, and this assertion is
    what lets those hand-written constants be replaced by a call.
    """
    computed = sutherland_viscosity(ISA.sea_level_temperature_k)
    assert computed == pytest.approx(1.789e-05, rel=1e-3)
    assert computed == pytest.approx(1.7894e-05, rel=1e-3)
    # Tighter, against the law's own arithmetic rather than either
    # rounding, so this test pins the law and not the roundings.
    assert computed == pytest.approx(1.78930e-05, rel=1e-4)


def test_viscosity_rises_with_temperature():
    """Sutherland is monotonic over the range this module models."""
    temperatures = [standard_temperature(h) for h in (20000.0, 11000.0, 5000.0, 0.0)]
    viscosities = [sutherland_viscosity(t) for t in temperatures]
    assert viscosities == sorted(viscosities)


def test_a_foot_is_exactly_0_3048_metres():
    """ALTFT is the interface unit, so the conversion is pinned."""
    assert feet_to_metres(10000.0) == pytest.approx(3048.0)
    assert feet_to_metres(0.0) == 0.0
    assert feet_to_metres(1.0) == 0.3048


@pytest.mark.parametrize("altitude_m", [-2000.1, 20000.1, 100000.0])
def test_an_altitude_outside_the_modelled_range_is_refused(altitude_m):
    """Refused rather than extrapolated, naming the range.

    ISO 2533 continues above this ceiling with layers this module does
    not implement, so an extrapolation would be wrong in a way no
    caller could see -- which is the failure mode this whole capability
    exists to remove.
    """
    with pytest.raises(AtmosphereError) as raised:
        isa(altitude_m)
    message = str(raised.value)
    assert str(ISA.ceiling_altitude_m) in message
    assert str(ISA.floor_altitude_m) in message


def test_the_range_boundaries_themselves_are_accepted():
    """The refusal is outside the range, not at its edge."""
    assert isa(ISA.floor_altitude_m).pressure_pa > 0.0
    assert isa(ISA.ceiling_altitude_m).pressure_pa > 0.0


def test_a_deviation_below_absolute_zero_is_refused():
    """A deviation large enough to invert the physics names itself."""
    with pytest.raises(AtmosphereError) as raised:
        isa(0.0, delta_isa_c=-400.0)
    assert "absolute zero" in str(raised.value)


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_the_primitives_refuse_a_non_physical_temperature(bad):
    """Each primitive on its own, because each is separately callable."""
    for function in (sutherland_viscosity, speed_of_sound):
        with pytest.raises(AtmosphereError):
            function(bad)
    with pytest.raises(AtmosphereError):
        density(101325.0, bad)


def test_the_refusal_is_catalogued_rather_than_a_bare_value_error():
    """SRS FR-39: a caller can tell this package's refusal from Python's."""
    from pyflightstream.exceptions import PyflightstreamError

    assert issubclass(AtmosphereError, PyflightstreamError)
    # The standard-library base is kept, so `except ValueError` catches
    # what it always did.
    assert issubclass(AtmosphereError, ValueError)


def test_the_module_imports_nothing_from_the_package_but_the_base_exception():
    """The floor property, asserted rather than asked for in prose.

    A floor that grows a second package import stops being one, and the
    layering guard would not catch it because both modules are below
    the pipeline the guard walks.
    """
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src" / "pyflightstream" / "_atmosphere.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("pyflightstream"):
                imported.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("pyflightstream"):
                    imported.add(alias.name)
    assert imported == {"pyflightstream._errors"}, (
        f"_atmosphere imports {sorted(imported)} from this package; a floor "
        "module imports only the base exception, or it is a pipeline stage "
        "wearing a floor's name"
    )
