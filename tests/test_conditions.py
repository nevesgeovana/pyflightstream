"""Tier 1: binding a requested operating point to the one an export printed.

REV010-001. The failure this closes is not a malformed file: it is a
valid, complete, converged export of a DIFFERENT engineering case being
accepted as the evidence of this one. Every test here drives
``bind_conditions`` directly, through its ``bindings`` seam where the
case needs one, so the comparison is exercised rather than a report
constructor.
"""

from dataclasses import dataclass

import pytest

from pyflightstream.results.conditions import (
    FIELD_BINDINGS,
    ConditionBinding,
    bind_conditions,
)


@dataclass
class FakeReport:
    """The three fields the binding reads, and nothing else."""

    angle_of_attack_deg: float = 2.0
    sideslip_deg: float = 0.0
    freestream_velocity_m_s: float = 30.0


def test_a_matching_point_binds_with_no_mismatch():
    binding = bind_conditions({"alpha": 2.0, "beta": 0.0, "velocity": 30.0}, reported=FakeReport())
    assert binding.mismatch_free
    assert binding.mismatches == ()
    assert {check.axis for check in binding.checks} == {"alpha", "beta", "velocity"}
    assert all(check.within for check in binding.checks)


def test_print_rounding_is_inside_the_tolerance_and_a_real_offset_is_not():
    """The tolerance is print resolution, not an allowance for drift.

    Loads spreadsheets print three decimals, so half a count of the last
    digit is the tightest comparison that cannot fire on rounding alone.
    A requested value that differs by MORE than that is a different
    point, however small the number looks.
    """
    rounding = bind_conditions({"alpha": 2.0004}, reported=FakeReport(angle_of_attack_deg=2.0))
    assert rounding.mismatch_free, "half a printed count must not be called a mismatch"

    real = bind_conditions({"alpha": 2.001}, reported=FakeReport(angle_of_attack_deg=2.0))
    assert not real.mismatch_free
    assert real.mismatches[0].axis == "alpha"


def test_the_reviews_own_reproduction_is_refused():
    """A campaign point requested alpha=0; the export printed alpha=2."""
    binding = bind_conditions({"alpha": 0.0}, reported=FakeReport(angle_of_attack_deg=2.0))
    assert not binding.mismatch_free
    (mismatch,) = binding.mismatches
    assert mismatch.requested == 0.0
    assert mismatch.reported == 2.0
    assert mismatch.deviation == pytest.approx(2.0)
    assert "off by 2.0000" in mismatch.describe()


def test_an_axis_the_export_does_not_print_is_recorded_as_unchecked():
    """Not compared and compared-and-agreed are different claims.

    Collapsing them is how a binding that checks nothing reads as a
    binding that passed.
    """
    report = FakeReport()
    report.sideslip_deg = None
    binding = bind_conditions({"alpha": 2.0, "beta": 1.0}, reported=report)
    assert binding.unprinted == ("beta",)
    assert {check.axis for check in binding.checks} == {"alpha"}
    assert binding.mismatch_free, "an unprintable axis is unchecked, not failed"


def test_an_axis_the_campaign_does_not_sweep_is_simply_absent():
    binding = bind_conditions({"alpha": 2.0}, reported=FakeReport())
    assert {check.axis for check in binding.checks} == {"alpha"}
    assert binding.unprinted == ()


def test_a_unit_confusion_is_a_mismatch_rather_than_a_match():
    """30 m/s is 58.32 knots. Requesting the knots number against an
    export printing m/s must fail, because the two are the same physical
    speed expressed in different units and the package promises m/s."""
    binding = bind_conditions(
        {"velocity": 58.3196}, reported=FakeReport(freestream_velocity_m_s=30.0)
    )
    assert not binding.mismatch_free
    assert binding.mismatches[0].unit == "m/s"


def test_a_requested_value_of_none_is_not_requested():
    binding = bind_conditions({"alpha": None, "velocity": 30.0}, reported=FakeReport())
    assert {check.axis for check in binding.checks} == {"velocity"}


def test_an_empty_binding_is_not_evidence_of_agreement():
    """`mismatch_free` is vacuously true with nothing to compare, and
    `compared` is the property that says so.

    The predecessor of `mismatch_free` was called `matched`, which meant a
    caller writing the obvious `if binding.matched:` re-created REV010-001
    at the API level: no comparison happened and the name said it had
    (api-designer pass, 2026-08-03).
    """
    empty = ConditionBinding()
    assert empty.mismatch_free
    assert not empty.compared
    assert empty.checks == ()
    assert empty.as_records() == []


def test_a_real_binding_reports_that_it_compared_something():
    """The control for `compared`: a property that always returned False
    would satisfy the assertion above forever."""
    binding = bind_conditions({"alpha": 2.0}, reported=FakeReport())
    assert binding.compared and binding.mismatch_free


def test_a_requested_axis_the_table_cannot_bind_is_recorded():
    """`advance_ratio` is a supported sweep axis and the loads export does
    not print it back, so nothing can compare it. Silently dropping it
    produced a binding that looked complete for a J sweep."""
    binding = bind_conditions({"advance_ratio": 0.7, "alpha": 2.0}, reported=FakeReport())
    assert binding.unbound == ("advance_ratio",)
    assert {check.axis for check in binding.checks} == {"alpha"}


def test_every_bound_attribute_exists_on_the_report_it_binds():
    """The table names attributes of LoadsReport, and every test here uses
    FakeReport, whose fields mirror it only by authorship. A row bound to
    an attribute LoadsReport lacks would pass tier 1 and degrade to
    "unprinted" in production (QA pass, 2026-08-03)."""
    from pyflightstream.results import LoadsReport

    fields = set(LoadsReport.__dataclass_fields__)
    missing = [attribute for _, attribute, _, _ in FIELD_BINDINGS if attribute not in fields]
    assert not missing, f"FIELD_BINDINGS names attributes LoadsReport does not have: {missing}"
    fake = set(FakeReport.__dataclass_fields__)
    assert {a for _, a, _, _ in FIELD_BINDINGS} <= fake, (
        "the test double no longer covers every bound attribute"
    )


@pytest.mark.parametrize(("axis", "attribute", "tolerance", "unit"), FIELD_BINDINGS)
def test_every_declared_binding_is_driven_by_at_least_one_case(axis, attribute, tolerance, unit):
    """The table is data, so a row added without a test would otherwise be
    silently unexercised. Each row must detect its own mismatch."""
    report = FakeReport()
    baseline = getattr(report, attribute)
    binding = bind_conditions({axis: baseline + 10 * tolerance}, reported=report)
    assert binding.mismatches, (axis, attribute)
    assert binding.mismatches[0].unit == unit


def test_the_records_carry_the_whole_decision():
    """REV010-001's closure asks for requested, reported, deviation and
    decision to be PERSISTED, not just acted on."""
    (record,) = bind_conditions(
        {"alpha": 0.0}, reported=FakeReport(angle_of_attack_deg=2.0)
    ).as_records()
    assert record == {
        "axis": "alpha",
        "requested": 0.0,
        "reported": 2.0,
        "deviation": 2.0,
        "tolerance": 5e-4,
        "unit": "deg",
        "within": False,
    }
