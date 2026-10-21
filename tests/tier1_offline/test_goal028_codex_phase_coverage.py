"""A fixed azimuth must retain every requested revolution, including fractional steps."""

import numpy as np
import pytest

from pyflightstream._errors import ProductError
from pyflightstream.post.unsteady import TimestepSeries, phase_locked_rows


def history(first):
    steps = np.arange(first, 11)
    return TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={
            "Q_B1": (steps.astype(float) ** 2)[:, None],
            "Q_B2": (steps.astype(float) ** 2)[:, None],
        },
        sources=(),
    )


@pytest.mark.parametrize("clock,blades", [(2.5, 1), (2.0, 3)])
def test_missing_earliest_fractional_sample_is_refused(clock, blades):
    # 2.5-step turns need step 5.5 for the row at step 8. Three blades on
    # 2-step turns need a fractional sample between steps 6 and 7.
    first = 6 if clock == 2.5 else 7
    if clock == 2.5:
        # With interpolation support, the same request must still succeed.
        # At 5.5: (25+36)/2=30.5, then (64+30.5)/2=47.25 at step 8.
        rows = phase_locked_rows(
            history(5),
            ["Q_B1"],
            last_step=10,
            revolutions=2,
            steps_per_revolution=2.5,
            blade1_azimuth_deg=0,
        )
        row = next(row for row in rows if row["STEP"] == 8)
        assert row["REVOLUTIONS"] == 2
        assert row["Q_B1"] == pytest.approx(47.25)
    with pytest.raises(ProductError, match="history"):
        phase_locked_rows(
            history(first),
            ["Q_B1", "Q_B2"],
            last_step=10,
            revolutions=2,
            steps_per_revolution=clock,
            blade1_azimuth_deg=20,
            blades=blades,
            blade_families=["B1"] if blades == 1 else ["B1", "B2"],
        )


@pytest.mark.parametrize(
    "clock,depth", [(float("nan"), 2.0), (float("inf"), 2.0), (4.0, float("nan"))]
)
def test_p0420_a_clock_or_depth_that_is_no_finite_number_is_a_product_refusal(clock, depth):
    """F-1406: NaN and infinity leak ValueError or OverflowError instead of naming the input."""
    with pytest.raises(ProductError, match="finite"):
        phase_locked_rows(
            history(1),
            ["Q_B1"],
            last_step=10,
            revolutions=depth,
            steps_per_revolution=clock,
            blade1_azimuth_deg=0,
        )


def _ramp(first=1, last=8):
    steps = np.arange(first, last + 1)
    return TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={
            "Q_A_1": steps.astype(float)[:, None],
            "Q_1": steps.astype(float)[:, None],
            "Q_B1": steps.astype(float)[:, None],
            "Q_B2": steps.astype(float)[:, None],
        },
        sources=(),
    )


def test_p0420_the_longest_family_suffix_owns_a_column_when_two_families_overlap():
    """F-165: a column ending _A_1 is blade one's, not blade two's because blade two is named 1."""
    rows = phase_locked_rows(
        _ramp(),
        ["Q_A_1", "Q_1"],
        last_step=8,
        revolutions=1,
        steps_per_revolution=4.0,
        blade1_azimuth_deg=0,
        blades=2,
        blade_families=["A_1", "1"],
    )
    row = next(row for row in rows if row["STEP"] == 8)
    assert row["Q_A_1"] == pytest.approx(8.0)  # blade one: sampled where blade one is
    assert row["Q_1"] == pytest.approx(6.0)  # blade two: two steps of a four-step turn before


def test_p0420_revolutions_states_the_fewest_samples_of_any_column_of_the_row():
    """F-213: at a depth of 1.5 turns a shifted blade holds one sample less than blade one."""
    rows = phase_locked_rows(
        _ramp(),
        ["Q_B1", "Q_B2"],
        last_step=8,
        revolutions=1.5,
        steps_per_revolution=4.0,
        blade1_azimuth_deg=0,
        blades=2,
        blade_families=["B1", "B2"],
    )
    row = next(row for row in rows if row["STEP"] == 7)
    assert row["REVOLUTIONS"] == 1
