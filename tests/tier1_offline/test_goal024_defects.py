"""Tier 1: the two defects GOAL-024 fixes before its features (0.21.0).

A final residual the solver printed as a field of asterisks is not a divergence
when the column was already within the limit, and a section distribution writes
no ``INCLUDE_SYMMETRY`` unless the pproc asks for it.

The test names carry ``goal024_defects`` so the goal's checker can select them.
"""

from __future__ import annotations

import pytest

from pyflightstream.results import parse_residual_history
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_run_campaign import (
    FIXTURES,
    LAST_PRESSURE,
    LAST_VELOCITY,
    _assess_log,
    _log_with,
)

#: The width of a residual field, as the solver fills it when a number does not fit.
OVERFLOW = "*" * len(LAST_PRESSURE)


def test_goal024_defects_a_final_overflowed_residual_within_the_limit_is_read_from_the_row_before(
    tmp_path,
):
    """The 26.100 rotor case: asterisks at the last iteration, a tiny value on the row before."""
    assessment = _assess_log(tmp_path, _log_with(OVERFLOW, LAST_PRESSURE))
    assert assessment.status is RunStatus.CONVERGED, assessment.error
    assert assessment.iterations == 1575
    # The pressure column is read from iteration 1574 (2.83e-8), and the verdict
    # is the larger of the two columns, the velocity residual of the last row.
    assert assessment.residual == 9.6e-8
    assert assessment.residual_note is not None
    assert "pressure" in assessment.residual_note and "1574" in assessment.residual_note
    assert "2.83e-08" in assessment.residual_note


def test_goal024_defects_the_overflowed_column_is_the_one_read_earlier_whichever_it_is(tmp_path):
    """The velocity column overflows: its earlier value decides, and the note names velocity."""
    assessment = _assess_log(tmp_path, _log_with(OVERFLOW, LAST_VELOCITY))
    assert assessment.status is RunStatus.CONVERGED, assessment.error
    assert assessment.residual == 1.12e-7
    assert "velocity" in assessment.residual_note and "1574" in assessment.residual_note


def test_goal024_defects_an_overflow_after_a_value_above_the_limit_stays_unjudged(tmp_path):
    """A column that overflowed from above the limit may have grown: not called converged."""
    text = _log_with(OVERFLOW, LAST_PRESSURE)
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("1574"):
            lines[index] = line.replace("+2.8300000E-8", "+5.0000000E-3")
            break
    assessment = _assess_log(tmp_path, "".join(lines))
    assert assessment.status is RunStatus.FAILED_DIVERGED
    assert assessment.residual_note is None
    assert "asterisks" in assessment.error and "pressure" in assessment.error


def test_goal024_defects_a_printed_nan_is_still_a_divergence(tmp_path):
    """The control: a NaN the solver PRINTED is not an overflow and is never read from earlier."""
    assessment = _assess_log(tmp_path, _log_with("NaN", LAST_PRESSURE))
    assert assessment.status is RunStatus.FAILED_DIVERGED
    assert assessment.residual_note is None
    assert "asterisks" not in assessment.error


def test_goal024_defects_the_history_says_which_column_overflowed():
    """The parser keeps an overflow apart from a printed NaN, row by row."""
    text = (FIXTURES / "log_residuals_26.120.txt").read_text(encoding="utf-8")
    history = parse_residual_history(_log_with(OVERFLOW, LAST_PRESSURE))
    assert history[-1].overflowed == frozenset({"pressure"})
    assert all(not sample.overflowed for sample in history[:-1])
    assert all(not sample.overflowed for sample in parse_residual_history(text))
    printed = parse_residual_history(_log_with("NaN", LAST_PRESSURE))
    assert printed[-1].overflowed == frozenset()


# -------------------------------------------------- the section symmetry switch --


def _sections_case(tmp_path, *, include_symmetry: bool = False):
    from tests.tier1_offline.test_workflows import (
        _her_pproc,
        _wb_geometry,
        _with_pproc,
        unsteady_case,
    )

    pproc = _her_pproc()
    pproc = pproc.model_copy(
        update={
            "sections": pproc.sections.model_copy(update={"include_symmetry": include_symmetry})
        }
    )
    return _with_pproc(unsteady_case(), _wb_geometry(tmp_path), pproc)


def _blocks(text: str) -> list[list[str]]:
    from tests.tier1_offline.test_workflows import _distribution_blocks

    return _distribution_blocks(text.splitlines())


@pytest.mark.parametrize("build", ["26.100", "26.101"])
def test_goal024_defects_a_section_distribution_plans_on_a_build_without_the_symmetry_switch(
    tmp_path, build
):
    """pfs0201: every distribution was refused on 26.100 and 26.101 for an unneeded DISABLE."""
    from tests.tier1_offline.test_workflows import rendered

    blocks = _blocks(rendered(_sections_case(tmp_path), build))
    assert blocks, f"no section distribution was emitted on {build}"
    assert all(not any(entry.startswith("INCLUDE_SYMMETRY") for entry in block) for block in blocks)


def test_goal024_defects_a_build_with_the_switch_still_writes_it(tmp_path):
    """The control: 26.120 and later render exactly what they rendered before."""
    from tests.tier1_offline.test_workflows import rendered

    blocks = _blocks(rendered(_sections_case(tmp_path), "26.123"))
    assert blocks and all("INCLUDE_SYMMETRY DISABLE" in block for block in blocks)


def test_goal024_defects_asking_an_old_build_to_include_the_symmetry_copy_is_refused_by_name(
    tmp_path,
):
    """Nothing is dropped silently: wanting the copy is refused where the build cannot give it."""
    from pyflightstream.cases import CampaignConfigError
    from tests.tier1_offline.test_workflows import rendered

    with pytest.raises(CampaignConfigError) as refused:
        rendered(_sections_case(tmp_path, include_symmetry=True), "26.100")
    message = str(refused.value)
    assert (
        "26.100" in message
        and "INCLUDE_SYMMETRY" in message
        and "include_symmetry = false" in message
    )
