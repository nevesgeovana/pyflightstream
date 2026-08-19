"""Binding between a REQUESTED operating point and the one an export printed.

Pipeline role: sits with the parsers, below the run layer, and is the
single place that decides whether a parsed loads export is evidence of
the point somebody asked for. Both consumers call it: the assessor,
before a terminal status is decided, and the tabular layer, when it
reads a recorded run back.

Why it exists as its own module rather than as a check inside either
consumer. The tabular layer already had this comparison, and the
assessor did not, so a result for the wrong flight condition could be
recorded ``CONVERGED`` in the manifest and only contradicted later, by
a helper the manifest never consults (REV010-001). A guard that lives
in one consumer protects that consumer; the invariant belongs to the
data.

Physical meaning. A loads export prints the conditions the solver
actually ran, so those printed values are the run's identity, not
decoration. If the requested angle of attack is 0 deg and the export
prints 2 deg, the file is a real, valid, converged result of a
DIFFERENT engineering case: nothing about it is malformed, which is
exactly why nothing caught it.

Reference frames and units are those of the loads export: angles in
degrees in the solver's body frame, velocity in m/s.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

#: Requested axis name mapped to the report attribute that prints it,
#: the comparison tolerance, and the unit the tolerance is in.
#:
#: The tolerances are print resolution, not engineering judgment: half a
#: count of the last printed digit is the tightest comparison that cannot
#: fire on rounding alone.
#:
#: WHERE THE PRINTED WIDTH WAS READ, cited rather than recalled. The
#: committed export ``tests/fixtures/loads_steady_26.120.txt`` prints all
#: three of these header fields with three decimals, and its own footer
#: names FlightStream 26.120, build #7012026. Its layout mirrors a real
#: run on that build while its values are synthetic, which is what
#: ``tests/test_results.py`` records in its module docstring. A licensed
#: run on the same build recorded the same width for another header
#: quantity, the unsteady time increment, in
#: ``reports/RPT-006_wp7-nearrigid-pilot_2026-07-21.md``; that is
#: corroboration of the header's print format and not a second reading of
#: these three fields.
#:
#: WHAT THIS DOES NOT CLAIM. One measured build is not a solver
#: guarantee. Nothing here says a build this repository has never read an
#: export from prints the same width, and widening the claim would take a
#: licensed run. Beyond that one file, 5e-4 is a project-chosen threshold
#: and claims nothing about the export. Loosening it further would be a
#: policy about how far from the requested point a result may drift,
#: which is not a decision this module is entitled to make; tightening it
#: below print resolution would fire on rounding.
#:
#: ``tests/test_conditions.py`` reads this citation out of this file,
#: opens the export it names and asserts the three printed widths against
#: these tolerances, so the premise cannot rot back into a recollection.
FIELD_BINDINGS: tuple[tuple[str, str, float, str], ...] = (
    ("alpha", "angle_of_attack_deg", 5e-4, "deg"),
    ("beta", "sideslip_deg", 5e-4, "deg"),
    ("velocity", "freestream_velocity_m_s", 5e-4, "m/s"),
)


@dataclass(frozen=True)
class ConditionCheck:
    """One requested field compared against what the export printed.

    Attributes
    ----------
    axis : str
        Requested axis name, for example ``"alpha"``.
    requested : float
        Value the campaign asked for, in `unit`.
    reported : float
        Value the export printed, in `unit`.
    deviation : float
        Absolute difference, in `unit`.
    tolerance : float
        Largest deviation attributable to print rounding, in `unit`.
        Half a count of the last printed digit, the width being read
        from the committed export
        ``tests/fixtures/loads_steady_26.120.txt`` (FlightStream 26.120,
        build #7012026), which prints these fields with three decimals.
        One measured build is not a solver guarantee: see
        :data:`FIELD_BINDINGS` for what that citation does and does not
        claim.
    unit : str
        Unit of the three quantities above.
    """

    axis: str
    requested: float
    reported: float
    deviation: float
    tolerance: float
    unit: str

    @property
    def within(self) -> bool:
        """True when the deviation is no larger than print rounding."""
        return self.deviation <= self.tolerance

    def describe(self) -> str:
        """Return one human-readable line for an error message."""
        return (
            f"{self.axis} requested {self.requested:+.4f} {self.unit}, "
            f"export prints {self.reported:+.4f} {self.unit} "
            f"(off by {self.deviation:.4f}, tolerance {self.tolerance:g})"
        )

    def as_record(self) -> dict[str, float | str | bool]:
        """Return the check as plain data, for the manifest."""
        return {
            "axis": self.axis,
            "requested": self.requested,
            "reported": self.reported,
            "deviation": self.deviation,
            "tolerance": self.tolerance,
            "unit": self.unit,
            "within": self.within,
        }


@dataclass(frozen=True)
class ConditionBinding:
    """The whole comparison for one export.

    Attributes
    ----------
    checks : tuple of ConditionCheck
        One per requested axis the export also prints.
    unprinted : tuple of str
        Requested axes the export does not print, so they could not be
        compared. Kept rather than dropped: "not checked" and "checked
        and matched" are different states and a reader must be able to
        tell them apart.
    unbound : tuple of str
        Requested axes :data:`FIELD_BINDINGS` does not know at all, so
        nothing could compare them. Distinct from `unprinted`, which is
        an axis the package knows and this export happens not to print.
    """

    checks: tuple[ConditionCheck, ...] = ()
    unprinted: tuple[str, ...] = ()
    unbound: tuple[str, ...] = ()

    @property
    def mismatches(self) -> tuple[ConditionCheck, ...]:
        """Checks whose deviation exceeds print rounding."""
        return tuple(check for check in self.checks if not check.within)

    @property
    def compared(self) -> bool:
        """True when at least one field was actually compared.

        The distinction this whole module is about, expressed as a
        value: "nothing was checked" and "everything agreed" are
        different claims about a result, and a caller must be able to
        ask which one it has.
        """
        return bool(self.checks)

    @property
    def mismatch_free(self) -> bool:
        """True when no comparable field disagrees.

        NAMED FOR WHAT IT MEASURES, deliberately. This was `matched`,
        which returns True for a binding that compared nothing, so a
        caller writing the obvious ``if binding.matched:`` re-created
        REV010-001 at the API level (api-designer pass, 2026-08-03).
        Ask :attr:`compared` alongside it, or read :attr:`mismatches`
        directly, which is what both real consumers do.
        """
        return not self.mismatches

    def describe(self) -> str:
        """Return the mismatching fields as one semicolon-joined line."""
        return "; ".join(check.describe() for check in self.mismatches)

    def as_records(self) -> list[dict[str, float | str | bool]]:
        """Return every check as plain data, for the manifest."""
        return [check.as_record() for check in self.checks]


def bind_conditions(
    requested: Mapping[str, float],
    *,
    reported: object,
    bindings: tuple[tuple[str, str, float, str], ...] = FIELD_BINDINGS,
) -> ConditionBinding:
    """Compare a requested operating point against a parsed export.

    Parameters
    ----------
    requested : mapping of str to float
        The point that was asked for, keyed by axis name. Keys the
        `bindings` table does not know are ignored, because a campaign
        may sweep an axis that the loads export does not print back.
    reported : object
        A parsed report carrying the attributes named in `bindings`,
        in practice a :class:`~pyflightstream.results.LoadsReport`.

        Typed loosely because the comparison is duck typed: any object
        exposing the attributes in `bindings` can be compared, which is
        what lets a test drive the table without constructing a parsed
        report. NOT for a layering reason. An earlier version of this
        docstring said this module "sits below the run layer and must
        not import it back", which is false about `LoadsReport`: it
        lives in :mod:`pyflightstream.results`, the SAME layer as this
        module, so nothing about the layer rule requires `object` here
        (architect pass, 2026-08-03). A wrong rationale propagates,
        which is why it is corrected rather than deleted.
    bindings : tuple, optional
        The axis-to-attribute table; defaults to
        :data:`FIELD_BINDINGS`. Passed explicitly by tests so the
        comparison can be driven without constructing a report.

    Returns
    -------
    ConditionBinding
        Every comparable field with its deviation and decision, plus
        the requested axes the export does not print.

    Notes
    -----
    A requested value of None is treated as "not requested", which is
    the case for an optional field such as free-stream velocity that a
    campaign may leave to the recipe.
    """
    checks: list[ConditionCheck] = []
    unprinted: list[str] = []
    known = {axis for axis, _, _, _ in bindings}
    # A requested axis this table does not know is UNBOUND, not absent.
    # The loop below iterates the table rather than the request, so such an
    # axis used to be dropped with no trace and a sweep over it recorded a
    # binding that looked complete (QA pass, 2026-08-03).
    unbound = tuple(
        sorted(axis for axis, value in requested.items() if axis not in known and value is not None)
    )
    for axis, attribute, tolerance, unit in bindings:
        if axis not in requested or requested[axis] is None:
            continue
        printed = getattr(reported, attribute, None)
        if printed is None:
            unprinted.append(axis)
            continue
        wanted = float(requested[axis])
        got = float(printed)
        checks.append(
            ConditionCheck(
                axis=axis,
                requested=wanted,
                reported=got,
                deviation=abs(got - wanted),
                tolerance=tolerance,
                unit=unit,
            )
        )
    return ConditionBinding(checks=tuple(checks), unprinted=tuple(unprinted), unbound=unbound)


__all__ = [
    "FIELD_BINDINGS",
    "ConditionBinding",
    "ConditionCheck",
    "bind_conditions",
]
