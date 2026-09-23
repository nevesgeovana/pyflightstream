"""Since 0.26.0 campaign assessment uses LoadsAssessor; the plot helper is gone."""

import pytest

from pyflightstream import run
from pyflightstream._deprecations import DEPRECATIONS


def test_assessor_import_is_refused():
    """An import now refuses the removed helper instead of preserving its answers."""
    with pytest.raises(ImportError, match="assess_unsteady_from_plots"):
        exec("from pyflightstream.run import assess_unsteady_from_plots")
    assert not hasattr(run, "assess_unsteady_from_plots")
    assert "assess_unsteady_from_plots" not in run.__all__
    assert run.LoadsAssessor


def test_assessor_has_no_removal_promise_left():
    assert not any("assess_unsteady_from_plots" in entry.subject for entry in DEPRECATIONS)
