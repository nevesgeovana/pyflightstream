"""P0400-EXPRARITY (PFS-2097.001): an [equations] call with the wrong arity is refused when read.

A call with the wrong number of arguments used to pass the read-time grammar
and then fail with a TypeError on every row at post. A negative base raised to
a non-integer power used to return a Python complex, which ``float`` then
refused with the interpreter's text; it is now a named ValueError.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream._expressions import evaluate_expression, parse_expression


@pytest.mark.parametrize(
    "expression",
    ["min(CT)", "max(CT)", "sqrt(CT, CP)", "abs(CT, CP)", "sin(CT, 1)", "degrees(1, 2, 3)"],
)
def test_p0400_exprarity_wrong_arity_is_refused_when_read(expression: str) -> None:
    """P0400-EXPRARITY: the read-time check names the function and the count it takes."""
    called = expression.split("(")[0]
    with pytest.raises(InputArtifactError, match=rf"calls {called}\(\) with \d argument"):
        parse_expression(expression)


@pytest.mark.parametrize("expression", ["min(CT, CP)", "max(CT, CP, 1)", "sqrt(CT)", "abs(CT)"])
def test_p0400_exprarity_right_arity_is_accepted(expression: str) -> None:
    """P0400-EXPRARITY: the arities the functions really take still parse."""
    parse_expression(expression)


def test_p0400_exprarity_negative_base_non_integer_power_is_named() -> None:
    """P0400-EXPRARITY: a complex power is a ValueError naming the base and the power."""
    with pytest.raises(ValueError, match="negative base -0.25 raised to the non-integer power 1.5"):
        evaluate_expression("CT**1.5", {"CT": -0.25}.__getitem__)
    assert evaluate_expression("CT**2", {"CT": -0.5}.__getitem__) == 0.25
