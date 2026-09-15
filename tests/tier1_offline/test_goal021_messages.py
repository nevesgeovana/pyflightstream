"""GOAL-021 item 5: the messages a first cluster smoke test printed wrongly.

EVERY ASSERTION COUNTS A CLAUSE. A test that a message merely CONTAINS its
pointer passes on the per-rotor skip line exactly as it stood in 0.18.0, which
said its reason twice and then named the file; counting the reason is what a
mutation to either half of the message breaks.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.results import LoadsNotFoundError, sweep_table
from pyflightstream.results import tables as tables_module
from pyflightstream.workspace import CampaignWorkspace, RunStatus
from tests.tier1_offline.test_tables import collect_text, make_record

COMPLAINT = "successful runs yielded a coefficient table"


# --- PFS-2010.01.03: SUBMITTED is not a run that owed coefficients ------------


def test_goal021_loads_message_the_allow_list_is_every_status_that_ran_without_failing():
    """The tuple is named by value, so it is held to the enum here."""
    ran = {
        status.value
        for status in RunStatus
        if not status.value.startswith("FAILED") and status is not RunStatus.SUBMITTED
    }
    assert set(tables_module._RAN_TO_OUTPUTS) == ran, (
        f"_RAN_TO_OUTPUTS is {tables_module._RAN_TO_OUTPUTS} and the statuses that finish "
        f"without failing are {sorted(ran)}"
    )
    assert RunStatus.SUBMITTED.value not in tables_module._RAN_TO_OUTPUTS


def test_goal021_loads_message_a_submitted_only_manifest_raises_nothing_and_warns_nothing(
    tmp_path,
):
    """A cluster row's normal first state: every point is in a queue."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    for alpha in (0.0, 2.0, 4.0):
        workspace.append_record(
            make_record(
                run_id=f"camp/sim_9001/a+{alpha:04.1f}",
                point={"alpha": alpha},
                status=RunStatus.SUBMITTED,
                outputs=[],
            )
        )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        frame = sweep_table(workspace, require_loads=True)
    said = [str(w.message) for w in caught if COMPLAINT in str(w.message)]
    assert said == [], f"a queued point was complained about as a run with no loads: {said}"
    assert frame.shape[0] == 3, "the identity rows of the queued points are still the table"


def test_goal021_loads_message_a_submitted_point_beside_a_finished_one_is_not_counted(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.append_record(make_record(run_id="camp/sim_9001/AL+000", status=RunStatus.SUBMITTED))
    workspace.append_record(make_record(run_id="camp/sim_9001/AL+020", status=RunStatus.CONVERGED))
    with pytest.raises(LoadsNotFoundError) as raised:
        sweep_table(workspace, require_loads=True)
    message = str(raised.value)
    assert message.count("none of the 1 successful runs") == 1, message


# --- PFS-2010.01.04: the hint never renders an empty collection ---------------


def test_goal021_loads_message_the_example_is_a_record_that_collected_something(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.append_record(make_record(run_id="camp/sim_9001/AL+000", outputs=[]))
    collected = collect_text(workspace, "9001", tmp_path, "notes_a2.txt", "not a loads table\n")
    workspace.append_record(
        make_record(run_id="camp/sim_9001/AL+020", point={"alpha": 2.0}, outputs=collected)
    )
    with pytest.raises(LoadsNotFoundError) as raised:
        sweep_table(workspace, require_loads=True)
    message = str(raised.value)
    assert "[]" not in message, message
    assert message.count("for example") == 1, message
    assert message.count("camp/sim_9001/AL+020") == 1, (
        f"the example is not the record that collected something: {message}"
    )


def test_goal021_loads_message_no_record_collected_anything_is_said_in_words(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    for alpha in (0.0, 2.0):
        workspace.append_record(
            make_record(run_id=f"camp/sim_9001/a+{alpha:04.1f}", point={"alpha": alpha}, outputs=[])
        )
    with pytest.raises(LoadsNotFoundError) as raised:
        sweep_table(workspace, require_loads=True)
    message = str(raised.value)
    assert "[]" not in message, message
    assert message.count("None of them recorded a collected output") == 1, message
    assert "for example" not in message, message


# --- PFS-2015.05: the per-rotor skip line states its reason once --------------


def test_goal021_skip_line_a_rotor_naming_row_states_its_reason_once(tmp_path):
    """The reason is the PLANNER'S OWN sentence, not a fixture typed to match."""
    from pyflightstream.cases.workflows import reduction_windows
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_post_products import (
        TWO_ROTOR_PLAN,
        _products_manifest,
        _unsteady_workspace,
    )
    from tests.tier1_offline.test_reduce_by_rotor import transition_case

    planned = reduction_windows(transition_case())
    assert "names its rotors" in planned["per_blade"]["skipped"], planned["per_blade"]
    plan = {
        **TWO_ROTOR_PLAN,
        "phase_locked": planned["phase_locked"],
        "per_blade": planned["per_blade"],
    }
    workspace = _unsteady_workspace(tmp_path, reductions=plan)
    write_campaign_products(workspace)
    skipped = _products_manifest(workspace)["skipped"]
    for reduction in ("per_blade", "phase_locked"):
        said = skipped[f"probes/AL-020_{reduction}.csv"]
        assert said.count("names its rotors") == 1, said
        for rotor in ("LIFT_L1", "PUSHER"):
            assert said.count(f"probes/AL-020_{reduction}_{rotor}.csv") == 1, said
        assert said.count("blade passage") == 1, said


# --- the double emission ------------------------------------------------------


def test_goal021_single_warning_pyfs_matrix_run_says_a_complaint_once(tmp_path, monkeypatch):
    """One invocation derived the sweep table twice and warned from both."""
    from pyflightstream.run.cli import main
    from tests.tier1_offline import test_run_cli as cli_tests

    monkeypatch.setattr("pyflightstream.run.matrix.LocalExecutor", cli_tests.StubSolver)

    def no_loads(*_args, **_kwargs):
        raise LoadsNotFoundError("no collected output parses as a loads spreadsheet")

    workspace = cli_tests.make_workspace(tmp_path)
    matrix = cli_tests.single_point_matrix(tmp_path)
    argv = cli_tests.planned(workspace, matrix)
    monkeypatch.setattr(tables_module, "parse_run_loads", no_loads)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        main(argv)
    said = [str(w.message) for w in caught if COMPLAINT in str(w.message)]
    assert len(said) == 1, f"one invocation printed the complaint {len(said)} time(s): {said}"
    assert issubclass(
        next(w.category for w in caught if COMPLAINT in str(w.message)), PyflightstreamWarning
    )
