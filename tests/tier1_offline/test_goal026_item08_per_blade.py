"""Tier 1, v0.23.0 item 8: per_blade is ONE window, one row per blade, azimuth in columns.

THE OWNER'S WORDS, 2026-09-17, after reading the files the package had written
for her own periodic case:

    "Nao faz sentido isso pra mim, o caso que eu rodei com simetria periódica,
    faz sentido sempre olhar a ultima janela convergida. E mesmo pro wheel, faz
    sentido olhar todas as blades na mesma janela."

    "Nao importa que as blades estão em posições azimutais diferentes, nos
    podemos ter uma coluna que mostra a posição azimutal de inicio e fim de
    cada para a mesma janela."

WHAT WAS WRONG. `per_blade` averaged each blade over ITS OWN passage window, so
the blades were compared across different parts of the run: blade 1 from one
stretch of the history and blade 4 from another. Any difference between them
then mixes a real azimuthal difference with a difference in WHEN they were
sampled, and nothing in the file says which is which.

ONE WINDOW FOR EVERY BLADE, and the azimuths in columns. The blades genuinely
are at different azimuths at any instant, and that is not a problem to be
averaged away: it is a fact to be WRITTEN DOWN. Each row says where that blade
started and ended over the window they all share.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream._errors import ProductError
from pyflightstream.post.unsteady import TimestepSeries, per_blade_rows


@pytest.mark.parametrize("blades,period,window", [(0, 8, (1, 8)), (2, 0, (1, 8)), (2, 8, (20, 21))])
def test_p0420_per_blade_rows_uses_product_refusal(blades, period, window):
    with pytest.raises(ProductError):
        per_blade_rows(_series(), window=window, blades=blades, steps_per_revolution=period)


def test_p0420_per_blade_rows_has_explicit_public_status():
    from pyflightstream.post import unsteady

    assert "per_blade_rows" in unsteady.__all__


def _series(n_steps: int = 8) -> TimestepSeries:
    steps = np.arange(1, n_steps + 1)
    return TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={
            "Blade1_CMx": np.full((n_steps, 1), 1.0),
            "Blade2_CMx": np.full((n_steps, 1), 2.0),
        },
        sources=(),
    )


def test_one_row_per_blade_and_not_one_row_per_passage():
    rows = per_blade_rows(
        _series(), window=(1, 8), blades=2, steps_per_revolution=8.0, blade1_azimuth_deg=0.0
    )
    assert len(rows) == 2, rows
    assert [row["BLADE"] for row in rows] == [1, 2], rows


def test_every_blade_is_averaged_over_the_same_window():
    """Her rule, and the whole point of the item.

    A difference between two blades averaged over different windows mixes a
    real azimuthal difference with a difference in WHEN they were sampled, and
    nothing in the file says which is which.
    """
    rows = per_blade_rows(
        _series(), window=(3, 6), blades=2, steps_per_revolution=8.0, blade1_azimuth_deg=0.0
    )
    assert {row["FIRST_STEP"] for row in rows} == {3}, rows
    assert {row["LAST_STEP"] for row in rows} == {6}, rows


def test_p0430_a_row_states_the_span_it_averaged_and_not_the_one_asked_for():
    """F-211: a history that holds only part of the window says which part was averaged.

    The rows stated the requested first and last step although the history held
    steps 2, 3 and 5 of the window 1 to 7; they now state 2 and 5, the three steps
    that entered the average, and the azimuths at those two steps.
    """
    steps = np.array([2, 3, 5, 9])
    series = TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={
            "Blade1_CMx": np.array([[1.0], [2.0], [3.0], [100.0]]),
            "Blade2_CMx": np.array([[4.0], [5.0], [6.0], [100.0]]),
        },
        sources=(),
    )
    rows = per_blade_rows(
        series, window=(1, 7), blades=2, steps_per_revolution=8.0, blade1_azimuth_deg=0.0
    )
    assert [(row["FIRST_STEP"], row["LAST_STEP"]) for row in rows] == [(2, 5), (2, 5)], rows
    assert [row.get("STEPS") for row in rows] == [3, 3], rows
    # Blade one is at 0 degrees at step 1, so at 45 at step 2 and at 180 at step 5.
    assert [(row["AZIMUTH_START"], row["AZIMUTH_END"]) for row in rows] == [
        (45.0, 180.0),
        (225.0, 0.0),
    ], rows
    assert [row["CMx"] for row in rows] == [2.0, 5.0], rows


def test_the_azimuth_of_each_blade_is_written_at_both_ends_of_that_window():
    """The fact she asked to be recorded rather than averaged away."""
    rows = per_blade_rows(
        _series(), window=(1, 5), blades=4, steps_per_revolution=8.0, blade1_azimuth_deg=0.0
    )
    assert [row["AZIMUTH_START"] for row in rows] == [0.0, 90.0, 180.0, 270.0], rows
    # Four steps of an eight-step revolution is half a turn.
    assert [row["AZIMUTH_END"] for row in rows] == [180.0, 270.0, 0.0, 90.0], rows


def test_the_azimuth_wraps_rather_than_running_past_a_full_turn():
    rows = per_blade_rows(
        _series(), window=(1, 8), blades=2, steps_per_revolution=8.0, blade1_azimuth_deg=350.0
    )
    for row in rows:
        assert 0.0 <= row["AZIMUTH_START"] < 360.0, row
        assert 0.0 <= row["AZIMUTH_END"] < 360.0, row


def test_each_row_carries_that_blades_own_average_and_not_the_rotors():
    """Blade 1 and blade 2 hold different values here, so a mix would be visible."""
    rows = per_blade_rows(
        _series(), window=(1, 8), blades=2, steps_per_revolution=8.0, blade1_azimuth_deg=0.0
    )
    assert rows[0]["CMx"] == pytest.approx(1.0), rows[0]
    assert rows[1]["CMx"] == pytest.approx(2.0), rows[1]


def test_a_window_outside_the_history_is_refused():
    """Could-not-measure is never a pass."""
    with pytest.raises(ValueError):
        per_blade_rows(
            _series(), window=(90, 99), blades=2, steps_per_revolution=8.0, blade1_azimuth_deg=0.0
        )


def test_the_plan_hands_out_one_window_and_not_one_per_blade():
    """ITEM 8 AT THE PLAN, which is where the windows are actually decided.

    The six tests above exercise `per_blade_rows`, and it had NO CALLER: the
    reduction the stage writes takes its windows from the PLAN, and the plan
    cut one window PER BLADE --

        blade k: last_step - (blades - k) * period + 1  ..  last_step - (blades - 1 - k) * period

    -- so blade 1 came from one stretch of the history and blade 4 from
    another. Any difference between two blades then mixes a real azimuthal
    difference with a difference in WHEN they were sampled, and nothing in the
    file says which is which.

    One window removes the second cause entirely, which is the whole of her
    reading: "mesmo pro wheel, faz sentido olhar todas as blades na mesma
    janela".
    """
    from pyflightstream.cases.workflows import per_blade_window

    # Four blades, 40 steps a revolution, a history ending at step 400.
    window = per_blade_window(last_step=400, blades=4, period_steps=10)
    assert window == (361, 400), window
    # ONE window, covering ONE whole revolution: four blades of ten steps.
    assert window[1] - window[0] + 1 == 4 * 10, window


def test_a_run_holding_no_complete_revolution_gets_no_window():
    """None rather than a short window: a partial turn is not every blade."""
    from pyflightstream.cases.workflows import per_blade_window

    assert per_blade_window(last_step=30, blades=4, period_steps=10) is None


def test_p0420_an_empty_history_is_a_product_refusal_not_an_index_error():
    """F-1405: formatting the refusal indexed the first step of a history that has none."""
    empty = TimestepSeries(
        steps=np.array([], dtype=int), times_s=None, points=np.zeros((1, 3)), fields={}, sources=()
    )
    with pytest.raises(ProductError, match="holds no step"):
        per_blade_rows(empty, window=(1, 4), blades=2, steps_per_revolution=8.0)


def test_p0420_a_shorter_family_name_does_not_take_a_longer_familys_columns():
    """F-212: a column ending _Blade_1 belongs to family Blade_1, not to family 1."""
    steps = np.arange(1, 5)
    series = TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={"CL_Blade_1": np.full((4, 1), 5.0), "CL_1": np.full((4, 1), 7.0)},
        sources=(),
    )
    rows = per_blade_rows(
        series,
        window=(1, 4),
        blades=2,
        steps_per_revolution=8.0,
        blade_families=["Blade_1", "1"],
    )
    first, second = rows
    assert first["CL"] == 5.0 and "CL_Blade" not in first
    assert second["CL"] == 7.0 and "CL_Blade" not in second
