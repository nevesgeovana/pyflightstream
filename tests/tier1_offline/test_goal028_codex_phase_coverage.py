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
