"""The standalone plot assessor is removed in 0.26.0; native LoadsAssessor remains."""

import pytest

from pyflightstream import run


def test_history_assessment_is_no_longer_a_run_helper():
    """The former finite, drifting and empty-history cases no longer bind an API."""
    with pytest.raises(ImportError, match="assess_unsteady_from_plots"):
        exec("from pyflightstream.run import assess_unsteady_from_plots")
    assert run.LoadsAssessor
