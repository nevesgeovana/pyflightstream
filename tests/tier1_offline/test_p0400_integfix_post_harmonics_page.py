"""P0400-COVERAGEPAGE: the per-station harmonics page states the coverage criterion.

The fit leaves a harmonic out where the samples' azimuths do not go round the
circle (PFS-2086.007), and the definitions page, the record, stated only the
count of distinct azimuths.
"""

from __future__ import annotations

from pathlib import Path

from pyflightstream.post.harmonics import fit_harmonics

PAGE = Path(__file__).resolve().parents[2] / "docs" / "definitions" / "the-per-station-harmonics.md"


def test_p0400_coveragepage_the_page_states_the_criterion_the_fit_applies():
    """P0400-COVERAGEPAGE (PFS-2086.007): the 180 deg gap rule, on the page and in the fit."""
    crowded = fit_harmonics([0.0, 0.1, 0.2, 0.3, 0.4], [1.0, 1.0, 1.0, 1.0, 1.0])
    assert crowded.h1_amp is None and crowded.h2_amp is None
    assert "no gap over 180 deg" in str(crowded.reason)
    text = " ".join(PAGE.read_text(encoding="utf-8").split())
    assert "leave no gap larger than 180 deg around the circle" in text
    assert "do not go round the circle: a 1P fit needs the angles 1 psi with no gap over" in text
