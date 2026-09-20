"""The standalone history assessor retires without changing its answers."""

from types import SimpleNamespace

import numpy as np
import pytest

from pyflightstream._deprecations import DEPRECATIONS, expired_promise
from pyflightstream._errors import PyflightstreamDeprecationWarning
from pyflightstream.run import assess_unsteady_from_plots


@pytest.mark.parametrize(
    "values, tolerance, expected",
    [
        ([1.0, 1.0], None, "COMPLETED_MAX_ITER"),
        ([1.0, 1.0], 0.05, "CONVERGED"),
        ([1.0, float("nan")], None, "FAILED_DIVERGED"),
    ],
)
def test_assessor_warns_and_preserves_result(values, tolerance, expected):
    series = SimpleNamespace(steps=np.array([1, 2]), fields={"FX": np.array(values)})
    with pytest.warns(
        PyflightstreamDeprecationWarning, match=r"assess_unsteady_from_plots.*0\.27\.0"
    ):
        assert assess_unsteady_from_plots(series, settle_tolerance=tolerance) == expected


def test_assessor_removal_is_in_ledger():
    entries = [entry for entry in DEPRECATIONS if "assess_unsteady_from_plots" in entry.subject]
    assert len(entries) == 1, "the history assessor has no ledger removal promise"
    assert expired_promise(entries[0], "0.25.0") is None
    assert expired_promise(entries[0], "0.26.0") is None
    assert "promised removal in v0.27.0" in expired_promise(entries[0], "0.27.0")
