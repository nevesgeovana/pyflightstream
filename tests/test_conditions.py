"""Tier 1: binding a requested operating point to the one an export printed.

REV010-001. The failure this closes is not a malformed file: it is a
valid, complete, converged export of a DIFFERENT engineering case being
accepted as the evidence of this one. Every test here drives
``bind_conditions`` directly, through its ``bindings`` seam where the
case needs one, so the comparison is exercised rather than a report
constructor.

THE SECOND THING THIS MODULE GUARDS, and the reproduction of the defect
that put it here. The 5e-4 tolerances are not engineering judgment: they
are half a count of the last digit of a THREE-DECIMAL print, so the
number is only as good as the measurement of that width. Until
2026-08-18 the claim was written three times, in the ``FIELD_BINDINGS``
comment, in ``ConditionCheck.tolerance`` and in a test docstring below,
and cited nothing in any of them::

    >>> from pyflightstream.results.conditions import FIELD_BINDINGS
    >>> [tolerance for _, _, tolerance, _ in FIELD_BINDINGS]
    [0.0005, 0.0005, 0.0005]

A reader meeting those numbers could not tell a measurement from a
solver guarantee from a recollection, which is the first sentence a
reviewer pulls on. The tests at the end of this module read the citation
out of the source and open the export it names, so the premise is
measured on every run rather than remembered.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from pyflightstream.results import labeled_value
from pyflightstream.results.conditions import (
    FIELD_BINDINGS,
    ConditionBinding,
    ConditionCheck,
    bind_conditions,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
CONDITIONS_SOURCE = REPO_ROOT / "src" / "pyflightstream" / "results" / "conditions.py"

#: A repository-relative citation of a committed loads export.
_CITED_EXPORT = re.compile(r"tests/fixtures/([A-Za-z0-9._+-]+\.txt)")

#: Bound report attribute mapped to the label the loads export prints it
#: under. Kept here rather than imported because the point of these
#: tests is to read the FILE the citation names, not to trust the parser
#: to have read it; the labels are the ones ``parse_loads`` uses.
PRINTED_LABELS = {
    "angle_of_attack_deg": "Angle of attack (Deg)",
    "sideslip_deg": "Side-slip angle (Deg)",
    "freestream_velocity_m_s": "Freestream velocity (m/s)",
}


def _cited_exports(text: str) -> list[str]:
    """Return the distinct committed exports a block of prose cites."""
    return sorted(set(_CITED_EXPORT.findall(text)))


def _tolerance_premise() -> str:
    """Return the comment block that declares the tolerances.

    The contiguous run of ``#:`` lines immediately above the
    ``FIELD_BINDINGS`` assignment, and nothing else. Sliced rather than
    read from ``__doc__`` because a ``#:`` comment is not carried into
    the runtime object, and narrowed to that block deliberately: a
    citation that satisfies this guard from the module docstring would
    leave the tolerance declaration itself as uncited as it was before,
    which is the whole defect.
    """
    source = CONDITIONS_SOURCE.read_text(encoding="utf-8")
    head, marker, _ = source.partition("FIELD_BINDINGS:")
    assert marker, "conditions.py no longer declares FIELD_BINDINGS at module level"
    block: list[str] = []
    for line in reversed(head.splitlines()):
        if not line.startswith("#:"):
            break
        block.append(line)
    assert block, "no #: comment declares where the FIELD_BINDINGS tolerances come from"
    return "\n".join(reversed(block))


def _printed_decimals(token: str) -> int:
    """Return how many digits a solver-printed fixed-point token shows.

    The export prints a zero integer part as ``.000`` with no leading
    zero, so the integer half is optional here; a pattern requiring a
    digit before the point silently skips the side-slip row.
    """
    match = re.fullmatch(r"[+-]?\d*\.(\d+)", token.strip())
    assert match, f"{token!r} is not a fixed-point number this test can measure"
    return len(match.group(1))


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

    The committed export ``tests/fixtures/loads_steady_26.120.txt``
    prints these fields with three decimals, so half a count of the last
    digit is the tightest comparison that cannot fire on rounding alone.
    A requested value that differs by MORE than that is a different
    point, however small the number looks. The width is measured rather
    than recalled by
    ``test_the_cited_export_prints_three_decimals_for_every_bound_field``
    at the end of this module; this docstring was the third uncited copy
    of the claim and is now the third citation of the same file.
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


# --- The tolerance's premise, cited and then measured ---------------------
#
# OPS-2009.01.01. A published precision number stands on a source or it
# stands on nothing. These four tests hold the citation and the file it
# names together: the first two check that the two places declaring the
# tolerance name a committed export and the build it came from, and the
# third opens that export and measures the width the tolerance is derived
# from, so the citation cannot rot back into a recollection.


def test_the_precision_premise_is_cited_where_the_tolerances_are_declared():
    """The FIELD_BINDINGS comment names the export and the build.

    Red before OPS-2009.01.01: the comment asserted a three-decimal print
    width and derived 5e-4 from it while citing nothing at all.
    """
    premise = _tolerance_premise()
    cited = _cited_exports(premise)
    assert cited == ["loads_steady_26.120.txt"], (
        "the comment declaring FIELD_BINDINGS must name the committed export "
        f"its three-decimal width was read from; it cites {cited}"
    )
    assert "7012026" in premise, (
        "the citation must name the build the width was measured on, so a "
        "reader can tell one measured build from a solver guarantee"
    )


def test_the_tolerance_attribute_carries_the_same_citation():
    """The docstring a user actually reads carries the source too.

    A reader meets ``ConditionCheck.tolerance`` through ``help()`` and the
    API pages, never through the module's own comment, so a citation that
    lives only in the comment is a citation that reader never sees.
    """
    doc = ConditionCheck.__doc__ or ""
    assert _cited_exports(doc) == ["loads_steady_26.120.txt"], (
        "ConditionCheck's docstring must name the export the tolerance was "
        f"read from; it cites {_cited_exports(doc)}"
    )
    assert "7012026" in doc
    assert "tolerance :" in doc, "the citation must sit on the tolerance attribute"


def test_the_cited_export_prints_three_decimals_for_every_bound_field():
    """The carrier: open the file the citation names and measure it.

    This is the test the acceptance asks for. If the export stops printing
    three decimals, or a binding's tolerance stops being half a count of
    the last printed digit, the derivation is no longer true and this
    fails rather than the comment quietly becoming wrong.
    """
    cited = _cited_exports(_tolerance_premise())
    assert len(cited) == 1, (
        f"exactly one committed export must be named as the source of the "
        f"printed width; the comment cites {cited}"
    )
    (name,) = cited
    export = FIXTURES / name
    assert export.is_file(), f"the cited export {name} is not committed at {export}"
    text = export.read_text(encoding="utf-8")
    assert "7012026" in text, (
        "the build cited beside the width must be the build this export's own "
        "footer names, or the citation names a file it did not come from"
    )
    for axis, attribute, tolerance, unit in FIELD_BINDINGS:
        printed = labeled_value(text, PRINTED_LABELS[attribute])
        decimals = _printed_decimals(printed)
        assert decimals == 3, (
            f"{axis} prints {printed!r} ({decimals} decimals) in {name}; the "
            "tolerance is derived from a three-decimal print"
        )
        assert tolerance == pytest.approx(0.5 * 10**-decimals), (
            f"{axis} carries tolerance {tolerance:g} in {unit}, which is not "
            f"half a count of the {decimals} decimals {name} prints"
        )


def test_every_bound_attribute_has_a_printed_label_to_measure():
    """The control for the test above.

    It iterates FIELD_BINDINGS through PRINTED_LABELS, so a row added
    without a label would raise a KeyError rather than report the gap, and
    a label map that lost a row would silently measure fewer fields.
    """
    bound = {attribute for _, attribute, _, _ in FIELD_BINDINGS}
    assert bound <= set(PRINTED_LABELS), (
        f"no printed label for {sorted(bound - set(PRINTED_LABELS))}; the "
        "precision premise cannot be measured for a field this test cannot find"
    )


def test_the_reproduction_in_this_modules_docstring_still_runs():
    """The reproduction above is a doctest, and nothing else collects it.

    Sybil runs docstring doctests under ``src/pyflightstream`` only (see
    the root ``conftest.py``), so an example living in a TEST module's
    docstring is executed nowhere and rots silently. This runs it, which
    is what makes the numbers printed in that reproduction a measurement
    rather than a second uncited recollection of the same three values.
    """
    import doctest
    import sys

    outcome = doctest.testmod(sys.modules[__name__], verbose=False)
    assert outcome.attempted, "the reproduction disappeared from the module docstring"
    assert outcome.failed == 0, outcome
