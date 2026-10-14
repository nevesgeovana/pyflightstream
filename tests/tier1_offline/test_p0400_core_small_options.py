"""P0400-SECONDSFINITE (PFS-2097.006): the positive_seconds validator refuses NaN and infinity.

``nan <= 0`` is False, so set_option('qa.probe_timeout_s', float('nan')) was
accepted and every later probe timed out against NaN.
"""

from __future__ import annotations

import math

import pytest

from pyflightstream.options import OptionError, get_option, option_context, set_option


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_p0400_secondsfinite_nan_and_infinity_are_refused(value: float) -> None:
    """P0400-SECONDSFINITE: NaN and both infinities raise OptionError and change nothing."""
    before = get_option("qa.probe_timeout_s")
    with option_context("qa.probe_timeout_s", get_option("qa.probe_timeout_s")):
        with pytest.raises(OptionError, match="finite"):
            set_option("qa.probe_timeout_s", value)
        assert get_option("qa.probe_timeout_s") == before


def test_p0400_secondsfinite_a_finite_positive_value_is_kept() -> None:
    """P0400-SECONDSFINITE: the control: 30.5 seconds is accepted."""
    with option_context("qa.probe_timeout_s", get_option("qa.probe_timeout_s")):
        set_option("qa.probe_timeout_s", 30.5)
        assert get_option("qa.probe_timeout_s") == 30.5
        for value in (math.nan, math.inf, -math.inf):
            with pytest.raises(OptionError, match="finite"):
                set_option("qa.probe_timeout_s", value)
            assert get_option("qa.probe_timeout_s") == 30.5
