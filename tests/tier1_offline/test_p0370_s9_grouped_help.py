"""The grouped modes name every row they leave out, and the remedy (FR-421, scope item S9).

``--batch`` and ``--polar-sweep`` leave out the classes of row that ``LEFT_OUT_REASONS`` holds.
Their help names every class; the plan's left-out line of a coupled row names the remedy (run
those rows point by point) and no report id; every reason the plan can print comes from one table.
The parity side of FR-421 is tested through the real verdict in
``test_p0370_s9_parity_tests.py``.
"""

from __future__ import annotations

import re

import pytest

from pyflightstream.cases import SimCase, SweepAxis
from pyflightstream.cases.workflows import (
    COLD_START_VARIABLE,
    RESTART_VARIABLE,
    WORKFLOW_KEY,
    workflow_registry,
)
from pyflightstream.run._batch_plan import (
    LEFT_OUT_REASONS,
    eligibility,
    grouping_table_lines,
    plan_grouped_matrix,
)
from pyflightstream.run.cli import main
from pyflightstream.workspace import RunRecord, RunStatus
from pyflightstream.workspace._batches import GroupingReceipt
from tests.support_helpers import grouped_plan_fixture

BUILD = "26.123"
REMEDY = "run these rows point by point, without --batch or --polar-sweep"

#: The phrase of the shared help that names each key of the reasons table. A key with no entry
#: here fails the first test below, so a class added to the table cannot stay out of the help.
HELP_PHRASE = {
    "run_type": "LEGACY rows",
    "coupled": "coupled rows on steady or qsteady_rotor",
    "warm": "steady rows stating COLD_START false",
    "restart": "RESTART rows",
    "unsteady_action": "build without the unsteady action command",
    "splice": "points do not splice into one job",
    "recorded": "points are all recorded",
}


def _flat(text: str) -> str:
    return " ".join(text.split())


def _case(workflow: str, *, coupled: bool = False, **variables: str) -> SimCase:
    case = SimCase(
        sim_id="9001",
        aircraft="Rig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe=workflow,
        outputs=["loads.txt"],
        variables={WORKFLOW_KEY: workflow, **variables},
        point={"alpha": 0.0},
    )
    return case.model_copy(update={"fsi": object()}) if coupled else case


def _eligibility(case: SimCase, version: str = BUILD) -> str | None:
    return eligibility(case, workspace=None, version=version)  # type: ignore[arg-type]


def _plan(workspace, matrix, registry=None):
    return plan_grouped_matrix(
        matrix,
        workspace,
        mode="batch",
        batch=2,
        name="rotor",
        recipes={},
        recipe_registry=registry or workflow_registry(),
    )


@pytest.mark.parametrize("command", ["plan", "run"])
def test_p0370_s9_both_help_texts_name_every_class_left_out(command, capsys):
    """P0370-S9-GROUPED-HELP (FR-421): both flags name every key of the reasons table.

    The help of ``plan`` and of ``run`` is read through the real parser, one entry per flag, and
    held against ``HELP_PHRASE``, whose keys must be exactly the table's keys.
    """
    assert set(HELP_PHRASE) == set(LEFT_OUT_REASONS)
    with pytest.raises(SystemExit):
        main([command, "--help"])
    entries = re.split(r"\n  (?=-)", capsys.readouterr().out)
    for flag in ("--polar-sweep", "--batch N"):
        (entry,) = (_flat(chunk) for chunk in entries if chunk.startswith(flag))
        for key, phrase in HELP_PHRASE.items():
            assert phrase in entry, (flag, key)
        assert "point by point, without this flag" in entry, flag


def test_p0370_s9_each_class_the_help_names_is_a_real_left_out_case():
    """P0370-S9-GROUPED-HELP (FR-421): the classes of the help are judged by the real planner.

    ``eligibility`` over a LEGACY, a coupled steady, a warm steady, a RESTART and an old-build
    unsteady row returns the table's reason for the class, and a row of none of those classes
    joins.
    """
    legacy = _eligibility(_case(""))
    assert legacy == LEFT_OUT_REASONS["run_type"].format(workflow="LEGACY")
    assert _eligibility(_case("steady", coupled=True)) == LEFT_OUT_REASONS["coupled"]
    warm = _eligibility(_case("steady", **{COLD_START_VARIABLE: "false"}))
    assert warm == LEFT_OUT_REASONS["warm"]
    restart = _eligibility(_case("unsteady", **{RESTART_VARIABLE: "{FINISH_PENDING}"}))
    assert restart == LEFT_OUT_REASONS["restart"]
    old = _eligibility(_case("unsteady"), "26.121")
    assert old == LEFT_OUT_REASONS["unsteady_action"].format(version="26.121")
    assert _eligibility(_case("unsteady")) is None
    assert _eligibility(_case("steady")) is None
    assert len({legacy, warm, restart, old}) == 4


@pytest.mark.filterwarnings("ignore::pyflightstream.exceptions.PyflightstreamWarning")
def test_p0370_s9_the_plan_names_a_point_that_does_not_splice_and_a_recorded_polar(tmp_path):
    """P0370-S9-GROUPED-HELP (FR-421): the splice and recorded classes come from the table.

    A steady recipe that initialises the solver twice is refused by the real splice step of the
    plan, which names the count; a polar all of whose points are recorded is left out; both lines
    carry the table's words.
    """
    workspace, matrix = grouped_plan_fixture(tmp_path, walltimes=("1h", "1h", "1h"), sweep="0.0")
    steady = workflow_registry()["steady"]

    def twice(case, script):
        steady(case, script)
        render = script.render
        script.render = lambda *args, **keywords: render(*args, **keywords) + "INITIALIZE_SOLVER\n"

    unsteady = matrix.read_text(encoding="utf-8")
    head, row, tail = unsteady.partition("7001 |")
    line, newline, rest = tail.partition("\n")
    line = line.replace("unsteady_rotor |", "steady         |", 1)
    line = line[: line.rindex("|") + 1] + " VELOCITY: 30.0"
    matrix.write_text(head + row + line + newline + rest, encoding="utf-8")
    plan = _plan(workspace, matrix, {**workflow_registry(), "steady": twice})
    (item,) = (row for row in plan.grouping.left_out if row["sim"] == "7001")
    prefix, _, _ = LEFT_OUT_REASONS["splice"].partition("{error}")
    assert item["reason"].startswith(prefix)
    assert "initialises the solver 2 times" in item["reason"]
    matrix.write_text(unsteady, encoding="utf-8")
    for point in _plan(workspace, matrix).points:
        if point.sim_id == "7002":
            workspace.append_record(
                RunRecord(
                    run_id=point.run_id,
                    sim_id=point.sim_id,
                    fs_version_requested=BUILD,
                    package_version="0.37.0.dev0",
                    script_sha256="c" * 64,
                    raw_flag=False,
                    status=RunStatus.CONVERGED,
                    recipe="unsteady_rotor",
                )
            )
    plan = _plan(workspace, matrix)
    assert {"sim": "7002", "reason": LEFT_OUT_REASONS["recorded"]} in plan.grouping.left_out


def test_p0370_s9_the_coupled_reason_names_the_remedy_and_no_report_id():
    """P0370-S9-GROUPED-HELP (FR-421): ``eligibility`` of a coupled steady row reads the table."""
    for workflow in ("steady", "qsteady_rotor"):
        reason = _eligibility(_case(workflow, coupled=True))
        assert reason == LEFT_OUT_REASONS["coupled"]
        assert REMEDY in reason
        assert "RPT" not in reason
    assert _eligibility(_case("unsteady", coupled=True)) is None


def test_p0370_s9_no_reason_of_the_table_carries_a_report_id():
    """P0370-S9-GROUPED-HELP (FR-421): every entry of the reasons table is free of ``RPT-``.

    Iterated over the whole table, so a reason added later is held to the same rule.
    """
    assert len(LEFT_OUT_REASONS) >= 7
    for key, reason in LEFT_OUT_REASONS.items():
        assert not re.search(r"RPT-?\d*", reason), key
        assert "—" not in reason and "–" not in reason, key
    control = "a coupled row (RPT-150)"
    assert re.search(r"RPT-?\d*", control)


@pytest.mark.filterwarnings("ignore::pyflightstream.exceptions.PyflightstreamWarning")
def test_p0370_s9_the_plan_prints_the_table_reason_of_a_left_out_row(tmp_path):
    """P0370-S9-GROUPED-HELP (FR-421): the plan's left-out line carries the table's words.

    A steady row stating ``COLD_START`` false is left out of a real grouped plan; the receipt and
    the printed table both hold ``LEFT_OUT_REASONS["warm"]`` verbatim.
    """
    workspace, matrix = grouped_plan_fixture(tmp_path, walltimes=("1h", "1h"), sweep="0.0")
    text = matrix.read_text(encoding="utf-8").replace("unsteady_rotor |", "steady         |", 1)
    text = text.replace("LAST_REVS_AVG: 0.25", "LAST_REVS_AVG: 0.25 / COLD_START: false", 1)
    matrix.write_text(text, encoding="utf-8")
    plan = _plan(workspace, matrix)
    assert [item["sim"] for item in plan.grouping.left_out] == ["7001"]
    assert plan.grouping.left_out[0]["reason"] == LEFT_OUT_REASONS["warm"]
    lines = grouping_table_lines(plan.grouping)
    assert f"    POL 7001: {LEFT_OUT_REASONS['warm']}" in lines


def test_p0370_s9_the_printed_line_of_a_coupled_row_names_the_remedy():
    """P0370-S9-GROUPED-HELP (FR-421): the table printer shows the remedy, never a report id."""
    reason = _eligibility(_case("steady", coupled=True))
    receipt = GroupingReceipt(
        schema="pyfs-grouping/1",
        mode="batch",
        requested=2,
        selection={},
        jobs=(),
        left_out=({"sim": "9001", "reason": reason},),  # type: ignore[arg-type]
        total_estimate_s=None,
        longest_estimate_s=None,
        max_walltime_s=None,
        warnings=(),
    )
    printed = "\n".join(grouping_table_lines(receipt))
    assert REMEDY in printed
    assert "RPT" not in printed
