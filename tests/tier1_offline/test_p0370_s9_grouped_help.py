"""The grouped modes name every row they leave out, and the remedy (FR-421, scope item S9).

``--batch`` and ``--polar-sweep`` leave out RESTART rows, LEGACY rows and coupled rows on
``steady`` or ``qsteady_rotor``. Their help names all three classes; the plan's left-out line of a
coupled row names the remedy (run those rows point by point) and no report id; every reason the
plan can print comes from one table.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from pyflightstream.cases import SimCase, SweepAxis
from pyflightstream.cases.workflows import WORKFLOW_KEY, workflow_registry
from pyflightstream.run._batch_plan import (
    LEFT_OUT_REASONS,
    eligibility,
    grouping_table_lines,
    plan_grouped_matrix,
)
from pyflightstream.run.cli import main
from pyflightstream.workspace._batches import GroupingReceipt
from tests.support_helpers import grouped_plan_fixture

REPO = Path(__file__).resolve().parents[2]
BUILD = "26.123"
REMEDY = "run these rows point by point, without --batch or --polar-sweep"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _case(workflow: str, *, coupled: bool = False) -> SimCase:
    case = SimCase(
        sim_id="9001",
        aircraft="Rig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe=workflow,
        outputs=["loads.txt"],
        variables={WORKFLOW_KEY: workflow},
        point={"alpha": 0.0},
    )
    return case.model_copy(update={"fsi": object()}) if coupled else case


@pytest.mark.parametrize("command", ["plan", "run"])
def test_p0370_s9_both_help_texts_name_every_class_left_out(command, capsys):
    """P0370-S9-GROUPED-HELP (FR-421): both flags name RESTART, LEGACY and coupled rows.

    The help of ``plan`` and of ``run`` is read through the real parser, one entry per flag.
    """
    with pytest.raises(SystemExit):
        main([command, "--help"])
    entries = re.split(r"\n  (?=-)", capsys.readouterr().out)
    for flag in ("--polar-sweep", "--batch N"):
        (entry,) = (_flat(chunk) for chunk in entries if chunk.startswith(flag))
        assert "RESTART rows" in entry, flag
        assert "LEGACY rows" in entry, flag
        assert "coupled rows on steady or qsteady_rotor" in entry, flag
        assert "point by point, without this flag" in entry, flag


def test_p0370_s9_the_coupled_reason_names_the_remedy_and_no_report_id():
    """P0370-S9-GROUPED-HELP (FR-421): ``eligibility`` of a coupled steady row reads the table."""
    for workflow in ("steady", "qsteady_rotor"):
        reason = eligibility(_case(workflow, coupled=True), workspace=None, version=BUILD)  # type: ignore[arg-type]
        assert reason == LEFT_OUT_REASONS["coupled"]
        assert REMEDY in reason
        assert "RPT" not in reason
    assert eligibility(_case("unsteady", coupled=True), workspace=None, version=BUILD) is None  # type: ignore[arg-type]


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
    plan = plan_grouped_matrix(
        matrix,
        workspace,
        mode="batch",
        batch=2,
        name="rotor",
        recipes={},
        recipe_registry=workflow_registry(),
    )
    assert [item["sim"] for item in plan.grouping.left_out] == ["7001"]
    assert plan.grouping.left_out[0]["reason"] == LEFT_OUT_REASONS["warm"]
    lines = grouping_table_lines(plan.grouping)
    assert f"    POL 7001: {LEFT_OUT_REASONS['warm']}" in lines


def test_p0370_s9_the_printed_line_of_a_coupled_row_names_the_remedy():
    """P0370-S9-GROUPED-HELP (FR-421): the table printer shows the remedy, never a report id."""
    reason = eligibility(_case("steady", coupled=True), workspace=None, version=BUILD)  # type: ignore[arg-type]
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


def test_p0370_s9_the_parity_script_names_the_changed_reason():
    """P0370-S9-GROUPED-HELP (FR-421 R2): ``check_parity.py`` names the one changed text.

    The base's wording and the release's differ by the report id and the remedy, and that is
    the only left-out difference the script names; any other change of a reason stays unnamed.
    """
    spec = importlib.util.spec_from_file_location(
        "check_parity_fr421", REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parity)
    assert parity.LEFT_OUT_AFTER == LEFT_OUT_REASONS["coupled"]
    assert "(RPT-150)" in parity.LEFT_OUT_BEFORE
    defined = {"FR-421"}
    named = parity.name_difference(
        "left_out", "w", parity.LEFT_OUT_BEFORE, parity.LEFT_OUT_AFTER, defined
    )
    assert named["requirement"] == "FR-421"
    other = parity.name_difference(
        "left_out", "w", parity.LEFT_OUT_BEFORE, parity.LEFT_OUT_AFTER + " now", defined
    )
    assert "requirement" not in other
    unrelated = parity.name_difference("left_out", "w", "a RESTART row", "a restart row", defined)
    assert "requirement" not in unrelated
    undefined = parity.name_difference(
        "left_out", "w", parity.LEFT_OUT_BEFORE, parity.LEFT_OUT_AFTER, set()
    )
    assert "requirement" not in undefined
    scripts = {"differing": []}
    base = {
        "grouped_skipped": [
            {
                "matrix": "m.fs",
                "mode": "--batch",
                "reasons": [{"sim": "9001", "reason": parity.LEFT_OUT_BEFORE}],
            }
        ]
    }
    release = {
        "grouped_skipped": [
            {
                "matrix": "m.fs",
                "mode": "--batch",
                "reasons": [{"sim": "9001", "reason": parity.LEFT_OUT_AFTER}],
            }
        ]
    }
    parity._compare_left_out(scripts, base, release, defined)
    (entry,) = scripts["differing"]
    assert entry["requirement"] == "FR-421"
    scripts = {"differing": []}
    parity._compare_left_out(scripts, base, base, defined)
    assert scripts["differing"] == []
