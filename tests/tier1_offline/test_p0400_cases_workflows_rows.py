"""P0400-CW-ROWS: the row readers refuse what they cannot read, naming the case and the key.

0.40.0 items PFS-2097.003, PFS-2097.014, PFS-2093.010, PFS-2095.042,
PFS-2097.004, PFS-2097.015 and PFS-2093.009: every numeric cell goes through
the one reader that refuses NaN and infinity, counts are counts, a wall clock's
unit is all of its trailing letters, and the averaging window is read for its
value at build rather than only for its presence.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import BladeDatum, CampaignConfigError, RotorBlock, SimCase, SweepAxis
from pyflightstream.cases.workflows import build_script
from pyflightstream.cases.workflows._rows import (
    _angle,
    _require_the_averaging_window,
    _stated_rate,
    parse_restart,
    restart_iterations,
    row_ncpus,
    row_walltime_s,
)
from pyflightstream.script import Script

ROTOR = RotorBlock(
    alias="ROTOR",
    x_m=0.1,
    y_m=0.2,
    z_m=0.3,
    axis="X",
    rpm_sign=1,
    diameter_m=3.6576,
    families_general=[],
    families_blades=["Blade1"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
)


def _case(workflow: str = "unsteady", *, point: dict | None = None, **overrides) -> SimCase:
    variables: dict[str, str | float | int | bool] = {
        "WORKFLOW": workflow,
        "VELOCITY": "30.0",
        "DELTA_TIME": "0.0001",
        "TIME_ITERATIONS": "720",
        "LAST_ITERS_AVG": "10",
    }
    if workflow == "unsteady_rotor":
        variables.update({"RPM": "1200", "ROTOR_AXIS": "X", "BLADES": "1"})
        variables.pop("LAST_ITERS_AVG")
        variables["LAST_REVS_AVG"] = "0.5"
    for key, value in overrides.items():
        if value is None:
            variables.pop(key, None)
        else:
            variables[key] = value
    return SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe=workflow,
        outputs=["loads_a+00.0.txt"],
        variables=variables,
        point={"alpha": 0.0} if point is None else point,
        rotors={ROTOR.alias: ROTOR} if workflow == "unsteady_rotor" else {},
    )


@pytest.mark.parametrize("text", ["nan", "inf", "abc"])
def test_p0400_cw_rows_a_row_angle_is_read_through_the_finite_reader(text):
    """P0400-CW-ROWS (PFS-2097.003, PFS-2097.014): an ALPHA cell off the point is refused by key."""
    requirement = "P0400-CW-ROWS"
    case = _case("steady", point={}, ALPHA=text)
    with pytest.raises(CampaignConfigError, match="'7001' declares ALPHA as") as refusal:
        _angle(case, "alpha")
    assert str(refusal.value), requirement


@pytest.mark.parametrize("text", ["nan", "inf"])
def test_p0400_cw_rows_a_non_finite_body_rate_is_refused(text):
    """P0400-CW-ROWS (PFS-2097.003, PFS-2097.014): a NaN rate compared unequal to 0."""
    requirement = "P0400-CW-ROWS"
    case = _case("steady", ROLL_RATE=text)
    with pytest.raises(CampaignConfigError, match="not a finite number") as refusal:
        _stated_rate(case, "ROLL_RATE")
    assert str(refusal.value), requirement


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_p0400_cw_rows_a_resolved_angle_is_finite_too(value):
    """P0400-CW-ROWS (PFS-2097.003, PFS-2097.014): resolved angles use the same reader."""
    requirement = "P0400-CW-ROWS"
    with pytest.raises(CampaignConfigError, match="ALPHA.*not a finite number") as refusal:
        _angle(_case("steady", point={"alpha": value}), "alpha")
    assert str(refusal.value), requirement


@pytest.mark.parametrize("text", ["nanh", "infm", "nan h"])
def test_p0400_cw_rows_a_non_finite_wall_clock_is_refused(text):
    """P0400-CW-ROWS (PFS-2097.014): WALLTIME 'nanh' read as NaN and turned the watchdog on."""
    requirement = "P0400-CW-ROWS"
    with pytest.raises(CampaignConfigError, match="not a finite number") as refusal:
        row_walltime_s(_case(WALLTIME=text))
    assert str(refusal.value), requirement


@pytest.mark.parametrize(("text", "unit"), [("30min", "min"), ("2hrs", "hrs")])
def test_p0400_cw_rows_a_wall_clock_unit_is_every_trailing_letter(text, unit):
    """P0400-CW-ROWS (PFS-2093.010): `30min` was told it carries no unit."""
    requirement = "P0400-CW-ROWS"
    with pytest.raises(CampaignConfigError) as raised:
        row_walltime_s(_case(WALLTIME=text))
    message = str(raised.value)
    assert f"the unit {unit!r} is not one of" in message, (requirement, message)
    assert "no unit" not in message


def test_p0400_cw_rows_a_wall_clock_still_reads_its_four_units():
    """P0400-CW-ROWS (PFS-2093.010), control: the four units and the bare-number refusal hold."""
    requirement = "P0400-CW-ROWS"
    assert row_walltime_s(_case(WALLTIME="4h")) == 4 * 3600.0, requirement
    assert row_walltime_s(_case(WALLTIME=" 240 m ")) == 240 * 60.0
    assert row_walltime_s(_case(WALLTIME="1.5d")) == 1.5 * 86400.0
    with pytest.raises(CampaignConfigError, match="no unit"):
        row_walltime_s(_case(WALLTIME="240"))


def test_p0400_cw_rows_ncpus_is_read_as_every_count_is():
    """P0400-CW-ROWS (PFS-2095.042): NCPUS 4.0 is four processors; 4.5 is refused by key."""
    requirement = "P0400-CW-ROWS"
    assert row_ncpus(_case(NCPUS="4.0"), None) == 4, requirement
    with pytest.raises(CampaignConfigError, match="NCPUS"):
        row_ncpus(_case(NCPUS="4.5"), None)


@pytest.mark.parametrize(
    "text",
    [
        "{ADDITIONAL_ITERS=0.5}",
        "{ADDITIONAL_ITERS=2.7}",
        "{ADDITIONAL_ITERS=nan}",
        "{ADDITIONAL_REVS=inf}",
        "{ADDITIONAL_REVS=nan}",
    ],
)
def test_p0400_cw_rows_a_restart_count_is_finite_and_a_step_count_whole(text):
    """P0400-CW-ROWS (PFS-2097.004, PFS-2097.015): 0.5 became a 0-step continuation."""
    requirement = "P0400-CW-ROWS"
    with pytest.raises(CampaignConfigError, match="'7001' declares RESTART as") as refusal:
        parse_restart(_case(RESTART=text))
    assert str(refusal.value), requirement


def test_p0400_cw_rows_a_whole_restart_count_still_reads():
    """P0400-CW-ROWS (PFS-2097.004), control: 2.0 more steps are two more steps."""
    requirement = "P0400-CW-ROWS"
    request = parse_restart(_case(RESTART="{ADDITIONAL_ITERS=2.0}"))
    assert request is not None, requirement
    assert restart_iterations(request, {}) == 2


def test_p0400_cw_rows_additional_revolutions_round_before_the_ceiling():
    """P0400-CW-ROWS (PFS-2097.015): one turn at the recorded step of 11 per turn is 11 steps.

    The record keeps the step as round(360 / 11, 9), a hair under the true
    step, so the unrounded quotient is 11.00000000009 and its ceiling 12.
    """
    requirement = "P0400-CW-ROWS"
    request = parse_restart(_case(RESTART="{ADDITIONAL_REVS=1}"))
    assert request is not None, requirement
    record = {"export_window": {"step_deg": round(360.0 / 11, 9)}}
    assert restart_iterations(request, record) == 11


@pytest.mark.parametrize(
    ("workflow", "overrides", "named"),
    [
        ("unsteady", {"LAST_ITERS_AVG": "0"}, "LAST_ITERS_AVG"),
        ("unsteady", {"LAST_ITERS_AVG": "abc"}, "LAST_ITERS_AVG"),
        ("unsteady", {"LAST_ITERS_AVG": "-"}, "LAST_ITERS_AVG"),
        ("unsteady", {"LAST_ITERS_AVG": "100.5"}, "LAST_ITERS_AVG"),
        ("unsteady", {"LAST_REVS_AVG": "0.5"}, "both"),
        ("unsteady_rotor", {"LAST_REVS_AVG": "0"}, "LAST_REVS_AVG"),
        ("unsteady_rotor", {"LAST_REVS_AVG": "nan"}, "LAST_REVS_AVG"),
    ],
)
def test_p0400_cw_rows_the_averaging_window_is_read_for_its_value_at_build(
    workflow, overrides, named
):
    """P0400-CW-ROWS (PFS-2093.009): a zero, unreadable or doubled window planned READY."""
    requirement = "P0400-CW-ROWS"
    case = _case(workflow, **overrides)
    with pytest.raises(CampaignConfigError, match=named) as refusal:
        _require_the_averaging_window(case, workflow)
    with pytest.raises(CampaignConfigError, match=named):
        build_script(case, Script("26.124"))
    assert str(refusal.value), requirement
