"""Public testing assertions with quantified violation reports.

Pipeline role: cross-cutting support module (the pandas/numpy testing
model, PLN-045 adoption). User campaigns and this repository's own
suites compare two kinds of artifacts, and each gets the matching
assertion under the golden philosophy split of the 2026-07-23 library
review:

- Solver scripts and other deterministic ASCII artifacts compare
  exactly: :func:`assert_scripts_equal` reports the first differing
  line and the total count of differing lines, never a fuzzy match.
- Numeric records (parsed coefficients, ledger values) compare within
  tolerances: :func:`assert_records_close` reports how many values
  were compared, how many violate, and the worst offender, so a
  failure names the size of the disagreement instead of a bare
  mismatch.

Failure messages carry statistics because a lone "not equal" hides
whether one digit moved in one value or the whole record diverged;
the count and the worst offender make the difference visible at the
first read.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

__all__ = [
    "assert_records_close",
    "assert_scripts_equal",
]


def assert_records_close(
    actual: Mapping[str, float],
    expected: Mapping[str, float],
    *,
    rtol: float = 1.0e-7,
    atol: float = 0.0,
    label: str = "records",
) -> None:
    """Assert two named numeric records agree within tolerances.

    Parameters
    ----------
    actual : mapping of str to float
        Values under test, keyed by quantity name.
    expected : mapping of str to float
        Reference values; the key sets must match exactly.
    rtol : float
        Relative tolerance, applied to the expected magnitude.
    atol : float
        Absolute tolerance floor, for quantities passing through zero.
    label : str
        Name of the record pair in the failure message (openmdao
        caller-named message contract).

    Raises
    ------
    AssertionError
        Key sets differ, or any value violates
        ``|actual - expected| <= atol + rtol * |expected|``. The
        message reports the compared count, the violating count with
        keys, and the worst offender with both values and its
        deviation.
    """
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing or extra:
        raise AssertionError(
            f"{label}: key sets differ before any value comparison; "
            f"missing from actual: {missing or 'none'}; unexpected in "
            f"actual: {extra or 'none'}."
        )
    violations: list[tuple[str, float, float, float]] = []
    for key in expected:
        a, e = float(actual[key]), float(expected[key])
        deviation = abs(a - e)
        if math.isnan(a) or math.isnan(e):
            if math.isnan(a) != math.isnan(e):
                violations.append((key, a, e, math.inf))
            continue
        if deviation > atol + rtol * abs(e):
            violations.append((key, a, e, deviation))
    if violations:
        worst_key, worst_a, worst_e, worst_dev = max(violations, key=lambda v: v[3])
        keys = ", ".join(v[0] for v in violations)
        raise AssertionError(
            f"{label}: {len(violations)} of {len(expected)} values violate "
            f"rtol={rtol}, atol={atol} ({keys}). Worst offender "
            f"{worst_key!r}: actual {worst_a!r} against expected "
            f"{worst_e!r}, deviation {worst_dev:.3e}."
        )


def assert_scripts_equal(
    actual: str,
    expected: str,
    *,
    label: str = "script",
) -> None:
    """Assert two ASCII scripts are exactly equal, line by line.

    Deterministic ASCII artifacts (solver scripts, goldens) compare
    exactly by policy; a tolerance would hide an emission change.

    Parameters
    ----------
    actual : str
        Script text under test.
    expected : str
        Reference text.
    label : str
        Name of the pair in the failure message.

    Raises
    ------
    AssertionError
        Any difference. The message reports the first differing line
        (number and both texts) and the total count of differing
        lines, including a trailing length difference.
    """
    if actual == expected:
        return
    actual_lines = actual.splitlines()
    expected_lines = expected.splitlines()
    # strict=False: the pair compares up to the common length and the
    # length difference is reported separately.
    differing = [
        index
        for index, (a, e) in enumerate(zip(actual_lines, expected_lines, strict=False), start=1)
        if a != e
    ]
    length_delta = len(actual_lines) - len(expected_lines)
    total = len(differing) + abs(length_delta)
    if differing:
        first = differing[0]
        detail = (
            f"first difference at line {first}: actual {actual_lines[first - 1]!r} "
            f"against expected {expected_lines[first - 1]!r}"
        )
    else:
        first = min(len(actual_lines), len(expected_lines)) + 1
        detail = f"the texts agree up to line {first - 1} and then one of them ends"
    raise AssertionError(
        f"{label}: {total} differing line(s) "
        f"({len(actual_lines)} actual against {len(expected_lines)} expected "
        f"lines); {detail}. Scripts compare exactly by policy; regenerate the "
        "golden only through its documented update path."
    )
