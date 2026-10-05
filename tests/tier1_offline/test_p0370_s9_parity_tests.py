"""The parity instrument's tests share one fixture home and cover its refusal fallback (NFR-42).

``scripts/check_parity.py`` compares the refusals of a matrix at two versions. Its reader of a
refusal has three branches: the structured per-point reasons of ``plan.json``, a message that
lists points (parsed), and the whole message (a refusal before planning). Every branch is tested
with a one-line change, and the grouped-plan workspace the parity tests use is defined once, in
``tests/support_helpers.py``.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

from tests.support_helpers import grouped_plan_fixture

REPO = Path(__file__).resolve().parents[2]
TIER1 = REPO / "tests" / "tier1_offline"
HEAD = "pre-flight blocked: 2 points cannot run"
POINTS = ("rotor/sim_7001/DP-1", "rotor/sim_7002/DP-1")


def _parity():
    spec = importlib.util.spec_from_file_location(
        "check_parity_nfr42", REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _message(head: str = HEAD, first: str = "no geometry", second: str = "no setup") -> str:
    return f"{head}\n  {POINTS[0]}: {first}\n  {POINTS[1]}: {second}"


def _refusal(tmp_path: Path, message: str, *, plan: dict | None) -> dict:
    """Run the real ``_workspace_refusal`` over a workspace with or without a plan.json."""
    workspace = tmp_path / "ws"
    matrix = workspace / "m.fs"
    plan_file = workspace / "post" / "m" / "plan.json"
    plan_file.parent.mkdir(parents=True, exist_ok=True)
    if plan_file.exists():
        plan_file.unlink()
    if plan is not None:
        plan_file.write_text(json.dumps(plan), encoding="utf-8")
    return _parity()._workspace_refusal(RuntimeError(message), matrix, workspace)


def _plan(first: str = "no geometry", second: str = "no setup") -> dict:
    return {
        "points": [
            {"run_id": POINTS[0], "error": first},
            {"run_id": POINTS[1], "error": second},
            {"run_id": "rotor/sim_7003/DP-1", "error": None},
        ]
    }


def _differences(before: dict, after: dict) -> list[dict]:
    parity = _parity()
    scripts: dict = {"differing": []}
    row = {"matrix": "m.fs", "mode": "--batch"}
    parity._compare_workspace_refusals(
        scripts,
        {"workspace_refused": [{**row, **before}]},
        {"workspace_refused": [{**row, **after}]},
        {"base": "base", "release": "release"},
    )
    return scripts["differing"]


def test_p0370_s9_the_fixture_has_one_definition_in_the_support_module():
    """P0370-S9-PARITY-TESTS (NFR-42 R1): no tier-1 test defines or imports the fixture elsewhere.

    The scan walks every tier-1 module: a ``def _fixture`` of the grouped plan, or an import of
    a fixture out of ``test_p0350_batch_plan``, is a second home. The planted source is caught.
    """

    def offences(source: str) -> list[str]:
        found = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == "grouped_plan_fixture":
                found.append(f"defines {node.name}")
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.endswith("test_p0350_batch_plan")
            ):
                found.extend(
                    f"imports {item.name}" for item in node.names if item.name == "_fixture"
                )
        return found

    found = {
        path.name: hits
        for path in TIER1.glob("*.py")
        if (hits := offences(path.read_text(encoding="utf-8")))
    }
    assert not found
    support = (REPO / "tests" / "support_helpers.py").read_text(encoding="utf-8")
    assert offences(support) == ["defines grouped_plan_fixture"]
    planted = "from tests.tier1_offline.test_p0350_batch_plan import _fixture\n"
    assert offences(planted) == ["imports _fixture"]


def test_p0370_s9_the_shared_fixture_builds_the_grouped_plan_workspace(tmp_path):
    """P0370-S9-PARITY-TESTS (NFR-42 R1): the support fixture returns the matrix it names.

    One rotor row per walltime cell, each with its own pol, in a workspace that holds the row's
    geometry.
    """
    workspace, matrix = grouped_plan_fixture(tmp_path, walltimes=("1h", "2h"), sweep="0.0")
    rows = matrix.read_text(encoding="utf-8").splitlines()[2:]
    assert [row.split("|")[0].strip() for row in rows] == ["7001", "7002"]
    assert (workspace.inputs_dir / "geometries" / "wing_clean.fsm").is_file()


def test_p0370_s9_without_a_plan_a_one_line_config_message_change_is_a_difference(tmp_path):
    """P0370-S9-PARITY-TESTS (NFR-42 R2): the whole-message fallback compares the message.

    A refusal before planning has one line and no plan.json; the script reads it whole, so one
    changed word is reported with both messages, and an unchanged message is not.
    """
    message = "the matrix names a build that is not registered: 26.999"
    base = _refusal(tmp_path, message, plan=None)
    assert "reasons" not in base
    assert _differences(base, base) == []
    changed = _refusal(tmp_path, message.replace("registered", "known"), plan=None)
    (entry,) = _differences(base, changed)
    assert entry["state"] == "workspace_refused"
    assert (entry["base"], entry["release"]) == (base["message"], changed["message"])


def test_p0370_s9_without_a_plan_a_point_line_of_the_message_is_compared(tmp_path):
    """P0370-S9-PARITY-TESTS (NFR-42 R2): the parsed-message branch counts the point lines only.

    A pre-flight message that lists points but has no plan.json is parsed into its point rows:
    one changed reason is a difference, and a changed heading alone is not.
    """
    base = _refusal(tmp_path, _message(), plan=None)
    assert "reasons" not in base
    reason = _refusal(tmp_path, _message(second="no setup, again"), plan=None)
    assert len(_differences(base, reason)) == 1
    heading = _refusal(tmp_path, _message(head="pre-flight blocked: two points"), plan=None)
    assert _differences(base, heading) == []


def test_p0370_s9_with_a_plan_only_the_per_point_reasons_count(tmp_path):
    """P0370-S9-PARITY-TESTS (NFR-42 R2): plan.json reasons decide, a heading change does not.

    The same pre-flight refusal with a structured plan: a new heading is no difference, a
    changed per-point reason is, and a point that gains a reason is.
    """
    base = _refusal(tmp_path, _message(), plan=_plan())
    assert [row["error"] for row in base["reasons"]] == ["no geometry", "no setup"]
    heading = _refusal(tmp_path, _message(head="pre-flight blocked: two points"), plan=_plan())
    assert _differences(base, heading) == []
    reason = _refusal(tmp_path, _message(first="no geometry file"), plan=_plan("no geometry file"))
    (entry,) = _differences(base, reason)
    assert entry["matrix"] == "m.fs"
    gained = _plan()
    gained["points"][2]["error"] = "no pproc"
    third = _refusal(tmp_path, _message(), plan=gained)
    assert len(_differences(base, third)) == 1


def test_p0370_s9_a_refusal_on_one_side_only_is_a_difference():
    """P0370-S9-PARITY-TESTS (NFR-42 R2): a pair refused at the release only is reported."""
    parity = _parity()
    scripts: dict = {"differing": []}
    row = {"matrix": "m.fs", "mode": "--batch", "message": "refused"}
    parity._compare_workspace_refusals(
        scripts,
        {"workspace_refused": []},
        {"workspace_refused": [row]},
        {"base": "base", "release": "release"},
    )
    (entry,) = scripts["differing"]
    assert entry["base"] is None and entry["release"] == "refused"
