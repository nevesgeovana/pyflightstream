"""Tier 1: the small items of 0.54.0 (PFS-2186.11, .16): two lanes on one workspace, low items."""

from __future__ import annotations

import pytest


@pytest.mark.requirement("FR-3509")
def test_p0540_finished_by_refusal_names_the_valid_values(tmp_path):
    """PFS-2186.16: the refusal says which values the option takes, not only that it is wrong."""
    from pyflightstream._errors import InputValueError
    from pyflightstream.run._plan_report import visual_inspect

    with pytest.raises(InputValueError) as caught:
        visual_inspect(tmp_path, [], finished_by="polars", name="fig")
    text = str(caught.value)
    assert "'polars'" in text and "'products'" in text and "'sims'" in text
    assert "--finished-by" in text


@pytest.mark.requirement("FR-3509")
def test_p0540_turned_about_is_in_the_script_package_all():
    """PFS-2186.16: a name the rotor workflow imports from the package is a listed public name."""
    import pyflightstream.script as script

    assert "turned_about" in script.__all__
    assert script.turned_about((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), 90.0) == pytest.approx(
        (0.0, 1.0, 0.0), abs=1e-12
    )
