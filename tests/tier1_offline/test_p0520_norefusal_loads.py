"""P0520-NOREFUSAL-LOADS (FR-3404): the loads selections of an unsteady row, before the solve.

On a march the selections must precede ``START_SOLVER`` to reach the step
exports (RPT-064 measured the loads frame, RPT-133 the vorticity drag list).
The vorticity-drag clear and the loads selections of an unsteady row are
emitted there; the selections whose placement no run measured are warned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.cases import CampaignConfigError, SolverSettings
from tests.tier1_offline.test_p0520_norefusal import build, first_words, messages
from tests.tier1_offline.test_workflows import rotor_case, unsteady_case


@pytest.mark.requirement("FR-3404")
@pytest.mark.parametrize("make", [unsteady_case, rotor_case], ids=["unsteady", "unsteady_rotor"])
def test_p0520_the_vorticity_drag_clear_of_an_unsteady_row_precedes_the_solve(make):
    # P0520-NOREFUSAL-CLEAR-VORTICITY
    case = make().model_copy(
        update={"solver": SolverSettings(clear_vorticity_drag_boundaries=True)}
    )
    script, _ = build(case)
    words = first_words(script.render())
    assert words.count("DELETE_VORTICITY_DRAG_BOUNDARIES") == 1
    assert words.index("DELETE_VORTICITY_DRAG_BOUNDARIES") < words.index("START_SOLVER")


@pytest.mark.requirement("FR-3404")
def test_p0520_the_loads_selections_of_an_unsteady_row_precede_the_solve_and_warn():
    # P0520-NOREFUSAL-LOADS-SELECTIONS
    case = unsteady_case().model_copy(
        update={"solver": SolverSettings(inviscid_loads=True, load_units="NEWTONS")}
    )
    script, caught = build(case)
    words = first_words(script.render())
    start = words.index("START_SOLVER")
    assert words.count("SET_INVISCID_LOADS") == 1
    assert words.index("SET_INVISCID_LOADS") < start
    assert words.index("SET_LOADS_AND_MOMENTS_UNITS") < start
    named = [m for m in messages(caught) if "SET_INVISCID_LOADS" in m]
    assert named and "before START_SOLVER" in named[0], messages(caught)


@pytest.mark.requirement("FR-3404")
@pytest.mark.parametrize(
    "solver",
    [{"clear_vorticity_drag_boundaries": True}, {"inviscid_loads": True}],
    ids=["clear", "inviscid"],
)
def test_p0520_no_campaign_error_remains_for_the_lifted_loads_cases(solver):
    case = unsteady_case().model_copy(update={"solver": SolverSettings(**solver)})
    try:
        build(case)
    except CampaignConfigError as error:  # pragma: no cover - the failure message
        pytest.fail(f"refused: {error}")


def test_p0520_the_four_refusal_sentences_are_gone():
    # P0520-NOREFUSAL: the release goal searches the tag for these sentences.
    root = Path(__file__).resolve().parents[2] / "src" / "pyflightstream"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    for sentence in (
        "normal probes of an unsteady run are verified only",
        "The loads selections are applied after the solve starts",
        "FSI on unsteady_rotor is still in debug",
        "direct morphing (morphing = 'direct' in the FSI input) is not offered on",
    ):
        assert sentence not in text, sentence
