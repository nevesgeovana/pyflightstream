"""Tier 1, v0.23.0 item 17: the native export is a health check, the assessor reads the plots.

THE OWNER'S WORDS, 2026-09-17, in two messages:

    "Pro unsteady, nem faz sentido exportar aquele arquivo nativo com coefs do
    flightstream porque ele e' so para ultima iteracao, acho que ja vale tirar
    ele pois o unsteady plots cobre"

    "Vamos manter o arquivo nativo somente para esse fim então, pra saber que
    nao explodiu a simula'cao, mas convergência temporal mesmo a gente ja sabe
    que vem de analise posterior"

WHY THE FILE STAYS. On an oscillating rotor the last step is ONE INSTANT of a
cycle, so a coefficient read from it is not the point's answer and reads as
though it were. But it is still evidence the run did not blow up, which is
worth one file, and REMOVING it would have broken the run assessor: the
standard judgment parses a loads table, so an unsteady point with none would be
judged unassessed rather than converged, which is worse than the ambiguity
being removed.

SO THIS ITEM IS TWO CHANGES AND THE ASSESSOR HALF COMES FIRST. It is harmless
on its own: judging an unsteady point from the plots history is strictly more
information than the last iteration ever carried.

THE CONVERGENCE THRESHOLD IS HERS AND IS NOT INVENTED HERE. The goal reserves
every tolerance and band to the owner. So this judges the half that needs no
threshold -- whether the history is finite, which is "it did not blow up" -- and
returns the status the package already returns when it cannot judge temporal
convergence. Passing a tolerance she sets turns the second half on. A default
threshold would be a number the package chose about her physics.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.post.unsteady import TimestepSeries
from pyflightstream.run import assess_unsteady_from_plots


def _series(values: list[float]) -> TimestepSeries:
    steps = np.arange(1, len(values) + 1)
    return TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={"CL_MRP_TOTAL": np.asarray(values, dtype=float)[:, None]},
        sources=(),
    )


def test_a_history_that_blew_up_is_diverged():
    """The half that needs no threshold, and the one the native file was kept for."""
    status = assess_unsteady_from_plots(_series([1.0, 1.1, float("nan"), 1.2]))
    assert status == "FAILED_DIVERGED", status


def test_an_infinite_coefficient_is_diverged_too():
    status = assess_unsteady_from_plots(_series([1.0, float("inf")]))
    assert status == "FAILED_DIVERGED", status


def test_a_finite_history_with_no_tolerance_is_what_the_package_already_said():
    """No silent change of verdict. Without a threshold, the answer is today's answer.

    An unsteady time loop always runs to its prescribed end, so completion is
    `COMPLETED_MAX_ITER`. Returning CONVERGED here would be the package
    deciding her physics on a number nobody set.
    """
    status = assess_unsteady_from_plots(_series([1.0, 1.01, 1.0, 1.005]))
    assert status == "COMPLETED_MAX_ITER", status


def test_a_settled_history_is_converged_once_she_sets_the_tolerance():
    """The second half, switched on by a number she owns."""
    settled = _series([1.02, 1.01, 1.00, 1.005])
    assert assess_unsteady_from_plots(settled, settle_tolerance=0.05) == "CONVERGED"


def test_a_history_still_moving_is_not_converged_at_the_same_tolerance():
    """The other side of the same threshold, so it is not satisfied by always agreeing."""
    moving = _series([5.0, 4.0, 3.0, 2.0, 1.0, 0.1])
    assert assess_unsteady_from_plots(moving, settle_tolerance=0.05) == "COMPLETED_MAX_ITER"


def test_the_transient_is_excluded_by_the_window_and_not_by_luck():
    """THE FIXTURE THAT CAUGHT THE DESIGN ERROR, kept as a case.

    A run that settles perfectly after a large transient is CONVERGED, and the
    first writing of this function called it unsettled: it compared the two
    halves of the WHOLE history, so the transient sat in one half and the
    answer in the other. Judging settledness is only meaningful over the
    converged window, which item 16 derives and the CALLER passes -- this
    function does not guess one.
    """
    history = _series([5.0, 2.0, 1.02, 1.01, 1.00, 1.005])
    whole = assess_unsteady_from_plots(history, settle_tolerance=0.05)
    windowed = assess_unsteady_from_plots(history, settle_tolerance=0.05, window=(3, 6))
    assert whole == "COMPLETED_MAX_ITER", whole
    assert windowed == "CONVERGED", windowed


def test_a_window_the_history_does_not_hold_is_refused():
    """Could-not-measure is never a pass, at the window as much as at the history."""
    with pytest.raises(ValueError):
        assess_unsteady_from_plots(_series([1.0, 1.0]), settle_tolerance=0.05, window=(90, 99))


def test_an_empty_history_cannot_be_judged_and_says_so():
    """Could-not-measure is never a pass, which is this estate's standing rule."""
    with pytest.raises(ValueError):
        assess_unsteady_from_plots(_series([]))
