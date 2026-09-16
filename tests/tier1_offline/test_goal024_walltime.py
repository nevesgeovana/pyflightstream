"""Tier 1: the wall clock carries its unit (0.21.0, GOAL-024 arm 7).

The author's decision of 2026-09-15. The `WALLTIME` cell writes `240m`
or `4h`: the unit is part of the value, because a bare number read as SECONDS
in this package and as minutes on the scheduler it was written for, and neither
reading is visible in the file. A bare number is refused by name.

What the DESCRIPTOR carries is the HPC profile's to say, not the row's:
`walltime_arithmetic = "wall"`, the default, puts the cell in as written, and
`"seconds"` puts the whole clock in integer seconds, which is what this package
wrote until 0.20.x. Neither touches the watchdog: the Python clock counts down
to the same deadline either way, which is the half this asserts rather than
describes.

This module is the evidence of FR-106.

The test names carry ``goal024_walltime`` so the goal's checker can select them.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import CampaignConfigError, SimCase, SweepAxis
from pyflightstream.cases.workflows import (
    WALLTIME_UNITS,
    row_walltime_s,
    row_walltime_text,
    walltime_margin_s,
)
from pyflightstream.run import SubmittingExecutor, _bind_submission_values
from pyflightstream.workspace.inputs import InputArtifactError, read_hpc_profile

#: A profile whose descriptor field takes the walltime, and nothing else of note.
PROFILE = """\
application_id = "flightstream"

[descriptor]
format = "yaml"
name = "submit.yaml"

[descriptor.fields]
ApplicationId = "{application_id}"
job_name      = "FTS{sim}"
walltime      = "{walltime}"
workdir       = "{work_dir}"

[submit]
command = ["esub", "{descriptor_path}"]
"""


def _case(walltime: str | None) -> SimCase:
    """A case stating one wall clock, or none."""
    variables = {} if walltime is None else {"WALLTIME": walltime}
    return SimCase(
        sim_id="5001",
        aircraft="WB",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        outputs=["loads.txt"],
        variables={"VELOCITY": "68.058", **variables},
    )


def _profile(tmp_path, arithmetic=None, text=PROFILE):
    """Write one profile and read it back, with the arithmetic at the TOP LEVEL.

    A key appended to the end of a TOML file belongs to the last table it
    carries, not to the document, which is how the first writing of this test
    asked for `seconds` and got the default.
    """
    if arithmetic is not None:
        line = 'walltime_arithmetic = "' + arithmetic + '"'
        text = text.replace(
            'application_id = "flightstream"',
            'application_id = "flightstream"\n' + line,
            1,
        )
    path = tmp_path / "h001.toml"
    path.write_text(text, encoding="utf-8")
    return read_hpc_profile(path)


def test_goal024_walltime_a_unit_is_read_and_the_units_are_the_four(tmp_path):
    """240m and 4h are the same four hours, and the seconds are what the clock counts."""
    assert row_walltime_s(_case("240m")) == 4 * 3600.0
    assert row_walltime_s(_case("4h")) == 4 * 3600.0
    assert row_walltime_s(_case("90s")) == 90.0
    assert row_walltime_s(_case("1d")) == 86400.0
    assert sorted(WALLTIME_UNITS) == ["d", "h", "m", "s"]
    # And the text is kept as written, which is what a descriptor carries.
    assert row_walltime_text(_case("240m")) == "240m"


def test_goal024_walltime_a_bare_number_is_refused_by_name(tmp_path):
    """The refusal says what to write, and why a bare number cannot stand."""
    with pytest.raises(CampaignConfigError) as caught:
        row_walltime_s(_case("240"))
    message = str(caught.value)
    assert "240" in message and "no unit" in message, message
    assert "240m or 4h" in message
    assert "s (seconds), m (minutes), h (hours), d (days)" in message


def test_goal024_walltime_a_value_that_is_not_a_number_and_a_unit_is_refused(tmp_path):
    """And so is a cell whose number is not one."""
    with pytest.raises(CampaignConfigError, match="which is not a"):
        row_walltime_s(_case("soonh"))
    with pytest.raises(CampaignConfigError, match="positive"):
        row_walltime_s(_case("0h"))


def test_goal024_walltime_the_descriptor_carries_the_value_as_written(tmp_path):
    """The default arithmetic: the scheduler's field gets `4h` where the row wrote `4h`."""
    executor = SubmittingExecutor(_profile(tmp_path), values={})
    case = _case("4h")
    _bind_submission_values(executor, case, case)
    assert executor.values["walltime"] == "4h"
    # Both spellings are offered, so a profile can ask for either by name.
    assert executor.values["walltime_s"] == 4 * 3600
    assert executor.values["walltime_written"] == "4h"


def test_goal024_walltime_the_profile_can_ask_for_seconds_instead(tmp_path):
    """`walltime_arithmetic = "seconds"` is what this package wrote until 0.20.x."""
    profile = _profile(tmp_path, "seconds")
    assert profile.walltime_arithmetic == "seconds"
    executor = SubmittingExecutor(profile, values={})
    case = _case("240m")
    _bind_submission_values(executor, case, case)
    assert executor.values["walltime"] == 14400


def test_goal024_walltime_the_arithmetic_never_moves_the_clock_s_deadline(tmp_path):
    """The watchdog counts the ROW's clock, whatever the descriptor was given.

    This is the half that matters: the arithmetic is about one scheduler's
    field, and a package that let it move the deadline would stop a run early
    or late on a cluster whose field simply reads differently.
    """
    case = _case("240m")
    seconds = row_walltime_s(case)
    for arithmetic in ("wall", "seconds"):
        executor = SubmittingExecutor(_profile(tmp_path, arithmetic), values={})
        _bind_submission_values(executor, case, case)
        assert row_walltime_s(case) == seconds == 14400.0
        assert executor.values["walltime_s"] == 14400
    # The margin the clock leaves for the exports is the setup's and is
    # untouched by any of this.
    assert walltime_margin_s(case) == 1200.0


def test_goal024_walltime_a_profile_asking_for_an_unknown_arithmetic_is_refused(tmp_path):
    """An arithmetic nobody implemented is refused by name rather than taken as the default."""
    with pytest.raises(InputArtifactError) as caught:
        _profile(tmp_path, "per_task")
    message = str(caught.value)
    assert "per_task" in message and "seconds, wall" in message, message


def test_goal024_walltime_a_row_that_states_none_leaves_the_field_unfilled(tmp_path):
    """A row with no wall clock fills no field, which is the refusal the profile makes."""
    executor = SubmittingExecutor(_profile(tmp_path), values={})
    case = _case(None)
    _bind_submission_values(executor, case, case)
    assert "walltime" not in executor.values
    assert row_walltime_s(case) is None
