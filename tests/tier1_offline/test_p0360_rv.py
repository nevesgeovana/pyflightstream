"""Tier 1: the 0.36.0 review ratchets and parity comparison inventory."""

from __future__ import annotations

import ast
import builtins
import importlib.util
import inspect
import json
import re
import tomllib
from argparse import Namespace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
#: Measured on 2026-10-03, opening 0.36.0 development from v0.35.1.
MYPY_EXEMPT_MODULE_LIMIT = 16


def test_mypy_exempt_module_count_cannot_grow() -> None:
    """P0360-RV-ARCH-1 (NFR-27): the named exemption count may only fall."""
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    count = 0
    for override in config["tool"]["mypy"]["overrides"]:
        if override.get("ignore_errors") is True:
            modules = override["module"]
            count += 1 if isinstance(modules, str) else len(modules)
    assert count <= MYPY_EXEMPT_MODULE_LIMIT, (
        f"{count} mypy-exempt modules exceed the {MYPY_EXEMPT_MODULE_LIMIT} "
        "measured on 2026-10-03; NFR-27 allows the exemption set only to shrink"
    )


def test_fr180_evidence_cites_the_per_revolution_test() -> None:
    """P0360-RV-VV-3 (FR-180): its evidence names the existing scale-rule test."""
    text = (REPO / "docs/srs/functional-requirements.md").read_text(encoding="utf-8")
    entry = re.search(r'^!!! requirement "FR-180\b.*?(?=^!!! |\Z)', text, re.M | re.S)
    assert entry, "FR-180 is absent from the functional requirements"
    evidence = re.search(r"\bEvidence:\s*(.*?)(?:\n\s*\n|\Z)", entry[0], re.S)
    assert evidence, "FR-180 has no Evidence line"
    path = "tests/tier1_offline/test_goal036_per_revolution.py"
    assert f"`{path}`" in evidence[1], f"FR-180 Evidence must cite {path}"
    assert (REPO / path).is_file(), f"FR-180 evidence file does not exist: {path}"


def test_parity_comparison_lists_the_sorted_base_names() -> None:
    """The comparison inventory includes every base name in sorted order."""
    spec = importlib.util.spec_from_file_location(
        "check_parity_under_test", REPO / "scripts/check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = {"zeta.txt": "old\n", "alpha.txt": "same\n"}
    release = {"alpha.txt": "same\n", "zeta.txt": "new\n", "added.txt": "extra\n"}
    block = module.compare_texts("scripts", "script", base, release, set())
    assert block.get("compared") == ["alpha.txt", "zeta.txt"]


def test_plan_resolves_the_patched_cold_start_check(tmp_path, monkeypatch):
    """P0360-RV-QA2 (FR-364): the shared cold-start patch changes the plan."""
    import pyflightstream.run._ids as ids_mod
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run import PlanStatus
    from pyflightstream.run.matrix import plan_matrix
    from tests.tier1_offline.test_matrix_run import RECIPES, _steady_sweep_matrix

    workspace, matrix = _steady_sweep_matrix(tmp_path)

    def plan():
        return plan_matrix(
            matrix,
            workspace,
            name="cold",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
        )

    assert {point.status for point in plan().points} == {PlanStatus.READY}
    seen = []

    def refuse(case):
        seen.append(case.sim_id)
        raise CampaignConfigError("COLD_START: patched shared check refused this row")

    monkeypatch.setattr(ids_mod, "_is_cold_start", refuse)
    blocked = plan()
    assert {point.status for point in blocked.points} == {PlanStatus.BLOCKED}
    assert len(seen) == len(blocked.points) == 3
    assert all(
        point.error == "COLD_START: patched shared check refused this row"
        for point in blocked.points
    )


def test_parity_compares_grouped_scripts_from_a_synthetic_workspace(tmp_path) -> None:
    """GATEFIX (NFR-40): both grouped modes contribute written job scripts."""
    from tests.support_helpers import grouped_plan_fixture as _fixture

    workspace, matrix = _fixture(tmp_path / "source", walltimes=("1h", "1h"))
    (workspace.root / matrix.name).write_bytes(matrix.read_bytes())
    spec = importlib.util.spec_from_file_location(
        "grouped_parity", REPO / "scripts/check_parity.py"
    )
    assert spec and spec.loader
    parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parity)
    collected = parity.collect_workspace_scripts(workspace.root, tmp_path / "render")
    block = parity.compare_texts(
        "scripts", "name", collected["scripts"], collected["scripts"], set()
    )
    for prefix in ("BATCH-", "FULL-POLAR-"):
        assert any(name.startswith(prefix) for name in block["compared"]), block["compared"]
    assert not block["differing"]
    assert not collected["grouped_skipped"]


def _parity_receipt(
    tmp_path, monkeypatch, base, release, *, allow_no_grouped=False, refused=None, golden=True
):
    """Run the real verdict over controlled collector observations at both trees."""
    spec = importlib.util.spec_from_file_location(
        "parity_verdict", REPO / "scripts/check_parity.py"
    )
    assert spec and spec.loader
    parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parity)

    def git(*args, binary=False):
        return Path(parity.__file__).read_bytes() if binary else "a" * 40

    def collect(python, mode, tree, work, argument=None):
        if mode == "api":
            return {
                "exports": {"pyflightstream": ["public"]},
                "offered": {"pyflightstream.other": ["public"]},
                "unimportable": {},
                "classifier_control": True,
            }
        if mode == "resolve":
            return [
                f"{module}.{name}"
                for module, name in json.loads(argument.read_text())
                if name == parity.PLANTED_NAME
            ]
        if mode == "cli":
            return {"spellings": ["pyfs-matrix"], "unavailable": {}}
        if mode == "scripts":
            return {"render/control.txt": "render\n"} if golden else {}
        assert mode == "workspace-scripts"
        reasons = [
            {"matrix": "synthetic.fs", "mode": mode, "reasons": [{"reason": "excluded"}]}
            for mode in ("--batch", "--polar-sweep")
        ]
        return {
            "scripts": base if work.name == "base" else release,
            "grouped_skipped": reasons,
            "grouped_attempted": ["--batch", "--polar-sweep"],
            "workspace_refused": (refused or {}).get(work.name, []),
            "workspace_rendered": [
                {"matrix": "synthetic.fs", "mode": mode}
                for mode, prefix in (
                    ("--per-point", "sims/"),
                    ("--batch", "BATCH-"),
                    ("--polar-sweep", "FULL-POLAR-"),
                )
                if any(
                    name.startswith(prefix) for name in (base if work.name == "base" else release)
                )
            ],
        }

    def post(python, tree, source, ws, keep):
        keep.mkdir()
        (keep / "control.txt").write_bytes(b"post\n")
        return {"exit": 0, "stderr_tail": ""}

    monkeypatch.setattr(parity, "git", git)
    monkeypatch.setattr(parity, "export", lambda sha, tree: tree.mkdir(exist_ok=True))
    monkeypatch.setattr(parity, "run_child", collect)
    monkeypatch.setattr(parity, "run_post", post)
    monkeypatch.setattr(parity, "srs_ids", lambda tree: set())
    return parity.parity(
        Namespace(
            base="base",
            release="release",
            workspace=tmp_path,
            temp=tmp_path,
            python="unused",
            keep=False,
            allow_no_grouped=allow_no_grouped,
        )
    )


def _synthetic_refusal(reason="COLD_START: invalid"):
    return {
        "matrix": "synthetic.fs",
        "mode": "--per-point",
        "message": "pre-flight blocked 1 matrix point(s); nothing was executed:\n"
        f"  synthetic/sim_7001/point: CampaignConfigError: {reason}",
    }


def test_parity_lists_equal_workspace_refusals_without_failing(tmp_path, monkeypatch):
    """FIX6: an unchanged refusal permits parity when other workspace scripts compare."""
    row = _synthetic_refusal()
    scripts = {"sims/sim_7002/control.txt": "workspace\n"}
    receipt = _parity_receipt(
        tmp_path,
        monkeypatch,
        scripts,
        scripts,
        allow_no_grouped=True,
        refused={"base": [row], "release": [row]},
    )
    assert receipt["scripts"].get("workspace_refused") == [
        {**row, "version": "base"},
        {**row, "version": "release"},
    ]
    assert receipt["scripts"]["differing"] == []
    assert receipt["scripts"]["workspace_compared"] == 1
    assert receipt["verdict"] == "PARITY: PASS"


@pytest.mark.parametrize("side", ["base", "release"])
def test_parity_fails_a_workspace_refused_at_only_one_version(tmp_path, monkeypatch, side):
    """FIX5 (NFR-40): accepting a formerly refused matrix is also a difference."""
    row = _synthetic_refusal()
    receipt = _parity_receipt(
        tmp_path, monkeypatch, {}, {}, allow_no_grouped=True, refused={side: [row]}
    )
    assert receipt["verdict"] == "PARITY: FAIL"
    (difference,) = receipt["scripts"]["differing"]
    assert difference["matrix"] == row["matrix"]
    assert difference["mode"] == row["mode"]
    assert difference[side] == row["message"]


def test_parity_fails_when_workspace_refusal_reasons_change(tmp_path, monkeypatch):
    """FIX5 (NFR-40): the same refused matrix must keep its per-row reasons."""
    receipt = _parity_receipt(
        tmp_path,
        monkeypatch,
        {},
        {},
        allow_no_grouped=True,
        refused={"base": [_synthetic_refusal()], "release": [_synthetic_refusal("new reason")]},
    )
    assert receipt["verdict"] == "PARITY: FAIL"
    assert len(receipt["scripts"]["differing"]) == 1


@pytest.mark.parametrize("swap_details", [False, True])
def test_parity_keeps_multiline_refusal_reasons_attached_to_their_rows(
    tmp_path, monkeypatch, swap_details
):
    """FIX5 (NFR-40): row order is immaterial; exchanging row details is a difference."""
    first = "  synthetic/sim_7001/point: CampaignConfigError: invalid setting\n    detail: first"
    second = "  synthetic/sim_7002/point: CampaignConfigError: invalid setting\n    detail: second"
    row = {**_synthetic_refusal(), "message": "blocked:\n" + first + "\n" + second}
    changed = second + "\n" + first
    if swap_details:
        changed = changed.replace("detail: first", "detail: temporary")
        changed = changed.replace("detail: second", "detail: first")
        changed = changed.replace("detail: temporary", "detail: second")
    scripts = {"sims/sim_7003/control.txt": "workspace\n"}
    receipt = _parity_receipt(
        tmp_path,
        monkeypatch,
        scripts,
        scripts,
        allow_no_grouped=True,
        refused={"base": [row], "release": [{**row, "message": "blocked:\n" + changed}]},
    )
    assert receipt["verdict"] == ("PARITY: FAIL" if swap_details else "PARITY: PASS")


@pytest.mark.parametrize("allow_no_grouped", [False, True])
def test_parity_never_passes_with_only_workspace_refusals(tmp_path, monkeypatch, allow_no_grouped):
    """FIX6 VV-1/VV-2: golden renders cannot cover an entirely refused workspace."""
    rows = [
        {**_synthetic_refusal(), "mode": mode}
        for mode in ("--per-point", "--batch", "--polar-sweep")
    ]
    receipt = _parity_receipt(
        tmp_path,
        monkeypatch,
        {},
        {},
        allow_no_grouped=allow_no_grouped,
        golden=True,
        refused={"base": rows, "release": rows},
    )
    assert receipt["verdict"] == "PARITY: FAIL"
    assert any("no workspace scripts were compared" in f for f in receipt["failures"])
    assert receipt["scripts"]["compared"] == ["render/control.txt"]
    assert receipt["scripts"]["workspace_compared"] == 0
    assert receipt["scripts"]["workspace_coverage"]["rendered"] == []
    assert len(receipt["scripts"]["workspace_coverage"]["refused"]) == 6
    failure = next(f for f in receipt["failures"] if "no workspace scripts were compared" in f)
    assert "synthetic.fs" in failure and "COLD_START" in failure
    assert all(row["mode"] in failure for row in rows)


def test_parity_collects_a_refused_matrix_and_continues(tmp_path):
    """FIX5 (NFR-40): collect_workspace_scripts(source, copy) survives a blocked row."""
    from tests.support_helpers import grouped_plan_fixture as _fixture

    workspace, matrix = _fixture(tmp_path / "source", walltimes=("1h",))
    text = matrix.read_text(encoding="utf-8")
    matrix.unlink()
    (workspace.root / "refused.fs").write_text(
        text.replace("LAST_REVS_AVG: 0.25", "LAST_REVS_AVG: 0.25 / COLD_START: invalid"),
        encoding="utf-8",
    )
    (workspace.root / "z-valid.fs").write_text(text.replace("7001", "7002"), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "refusal_collector", REPO / "scripts/check_parity.py"
    )
    assert spec and spec.loader
    parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parity)
    collected = parity.collect_workspace_scripts(workspace.root, tmp_path / "render")
    (row,) = collected["workspace_refused"]
    assert row["matrix"] == "refused.fs" and row["mode"] == "--per-point"
    assert row["message"].startswith("pre-flight blocked 3 matrix point(s)")
    assert len(row["message"].splitlines()) == 4
    assert all("COLD_START" in line for line in row["message"].splitlines()[1:])
    assert len(row["reasons"]) == 3
    assert all("COLD_START" in point["error"] for point in row["reasons"])
    assert {point["run_id"] for point in row["reasons"]} == {
        line.strip().split(": ", 1)[0] for line in row["message"].splitlines()[1:]
    }
    assert collected["workspace_rendered"] == [
        {"matrix": "z-valid.fs", "mode": mode}
        for mode in ("--per-point", "--batch", "--polar-sweep")
    ]
    assert any("sim_7002" in name for name in collected["scripts"])
    assert any(name.startswith("BATCH-") for name in collected["scripts"])
    assert any(name.startswith("FULL-POLAR-") for name in collected["scripts"])


@pytest.mark.parametrize("error_name", ["MatrixError", "CampaignConfigError", "RuntimeError"])
def test_parity_preserves_planning_refusals_and_propagates_other_errors(
    tmp_path, monkeypatch, error_name
):
    """FIX5 (NFR-40): expected planning exceptions are data; other failures propagate."""
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.matrix import MatrixError

    source = tmp_path / "source"
    source.mkdir()
    (source / "synthetic.fs").write_text("synthetic", encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "planning_refusal", REPO / "scripts/check_parity.py"
    )
    assert spec and spec.loader
    parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parity)
    error_type = {
        "MatrixError": MatrixError,
        "CampaignConfigError": CampaignConfigError,
        "RuntimeError": RuntimeError,
    }[error_name]

    def refuse(*args):
        raise error_type("synthetic config refusal\nrow 7001: invalid setting")

    monkeypatch.setattr(parity, "_workspace_render", refuse)
    if error_type is RuntimeError:
        with pytest.raises(RuntimeError, match="synthetic config refusal"):
            parity.collect_workspace_scripts(source, tmp_path / "copy")
    else:
        collected = parity.collect_workspace_scripts(source, tmp_path / "copy")
        assert len(collected["workspace_refused"]) == 3
        assert all(
            "row 7001: invalid setting" in row["message"] for row in collected["workspace_refused"]
        )


def test_parity_collector_failure_keeps_the_full_exception(tmp_path, monkeypatch):
    """FIX5: a cause before the final 2000 stderr characters remains visible."""
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "collector_failure", REPO / "scripts/check_parity.py"
    )
    assert spec and spec.loader
    parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parity)
    stderr = "RuntimeError: synthetic cause\n" + "per-row details\n" * 300
    monkeypatch.setattr(
        parity.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr=stderr.encode("utf-8")),
    )
    with pytest.raises(SystemExit) as caught:
        parity.run_child("unused", "workspace-scripts", tmp_path, tmp_path)
    assert stderr in str(caught.value)


def test_parity_fails_when_both_trees_have_zero_grouped_scripts(tmp_path, monkeypatch):
    """FIX4 F1: attempted modes with zero grouped scripts cannot claim parity."""
    receipt = _parity_receipt(tmp_path, monkeypatch, {}, {})
    assert receipt["controls"]["caught"] == "caught 7 of 7"
    assert receipt["verdict"] == "PARITY: FAIL"
    for mode in ("--batch", "--polar-sweep"):
        assert any(mode in failure and "excluded" in failure for failure in receipt["failures"])


def test_parity_allow_no_grouped_is_explicit_in_the_receipt(tmp_path, monkeypatch):
    """FIX6: the opt-in permits missing grouped coverage with per-point coverage."""
    scripts = {"sims/sim_7001/control.txt": "workspace\n"}
    receipt = _parity_receipt(tmp_path, monkeypatch, scripts, scripts, allow_no_grouped=True)
    assert receipt["verdict"] == "PARITY: PASS"
    assert receipt["scripts"]["allow_no_grouped"] is True
    assert receipt["scripts"]["grouped_skipped"]["base"]
    assert receipt["scripts"]["workspace_compared"] == 1
    assert receipt["scripts"]["workspace_coverage"] == {
        "rendered": [
            {"matrix": "synthetic.fs", "mode": "--per-point", "version": side}
            for side in ("base", "release")
        ],
        "refused": [],
    }


def test_parity_requires_each_attempted_grouped_mode(tmp_path, monkeypatch):
    """FIX4 F1: a batch comparison does not cover an empty polar-sweep mode."""
    scripts = {"BATCH-synthetic.txt": "batch\n"}
    receipt = _parity_receipt(tmp_path, monkeypatch, scripts, scripts)
    assert receipt["verdict"] == "PARITY: FAIL"
    assert len(receipt["failures"]) == 1
    assert "--polar-sweep" in receipt["failures"][0]


def test_parity_lists_a_grouped_script_difference(tmp_path, monkeypatch):
    """FIX4 F3: a changed grouped job is in differing and fails the verdict."""
    base = {"BATCH-synthetic.txt": "batch\n", "FULL-POLAR-synthetic.txt": "old\n"}
    control = _parity_receipt(tmp_path, monkeypatch, base, base)
    assert control["verdict"] == "PARITY: PASS"
    receipt = _parity_receipt(
        tmp_path, monkeypatch, base, {**base, "FULL-POLAR-synthetic.txt": "new\n"}
    )
    assert receipt["verdict"] == "PARITY: FAIL"
    assert [entry["name"] for entry in receipt["scripts"]["differing"]] == [
        "FULL-POLAR-synthetic.txt"
    ]


def test_parity_keeps_exclusions_and_point_errors_when_a_batch_exists(tmp_path):
    """FIX4 F2: a written batch cannot hide other rows or blocked points."""
    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run.matrix import plan_matrix
    from pyflightstream.workspace import RunRecord, RunStatus
    from tests.support_helpers import grouped_plan_fixture as _fixture

    workspace, matrix = _fixture(tmp_path / "source", walltimes=("1h", "1h", "1h"))
    lines = matrix.read_text(encoding="utf-8").splitlines()
    lines[-1] = lines[-1].replace(
        "LAST_REVS_AVG: 0.25", "LAST_REVS_AVG: 0.25 / COLD_START: invalid"
    )
    matrix = workspace.root / matrix.name
    matrix.write_text("\n".join(lines) + "\n", encoding="utf-8")
    plan = plan_matrix(
        matrix, workspace, name=workspace.root.name, recipe_registry=workflow_registry(), recipes={}
    )
    for point in plan.points:
        if point.sim_id == "7002":
            workspace.append_record(
                RunRecord(
                    run_id=point.run_id,
                    sim_id=point.sim_id,
                    fs_version_requested="26.123",
                    package_version="synthetic",
                    script_sha256="c" * 64,
                    raw_flag=False,
                    status=RunStatus.CONVERGED,
                    recipe="unsteady_rotor",
                )
            )
    spec = importlib.util.spec_from_file_location(
        "partial_grouped_parity", REPO / "scripts/check_parity.py"
    )
    assert spec and spec.loader
    parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parity)
    result = parity._workspace_render(matrix, workspace.root, ["--batch", "2"])
    assert any(name.startswith("BATCH-") for name in result["scripts"])
    assert {"sim": "7002", "reason": "every point is already recorded"} in result["skipped"]
    blocked = [entry for entry in result["skipped"] if "run_id" in entry]
    assert len(blocked) == 3
    assert all("COLD_START" in entry["reason"] for entry in blocked)


@pytest.mark.parametrize("side", ["base", "release"])
def test_parity_refuses_workspace_names_overlapping_render_keys(tmp_path, monkeypatch, side):
    """FIX4 A3: collecting a workspace must not replace a golden or tier-3 render."""
    overlap = {"render/control.txt": "workspace\n"}
    with pytest.raises(AssertionError, match="render/control.txt"):
        _parity_receipt(
            tmp_path,
            monkeypatch,
            overlap if side == "base" else {},
            overlap if side == "release" else {},
        )


@pytest.mark.parametrize("change", ["reorder", "swap", "run_id"])
def test_parity_compares_structured_plan_refusal_pairs(tmp_path, monkeypatch, change):
    """FIX6 A2: plan row identity and multiline errors define equality, not messages."""
    points = [
        {"run_id": "synthetic row A", "error": "invalid setting\n  detail: first"},
        {"run_id": "synthetic row B", "error": "invalid setting\n  detail: second"},
    ]
    changed = [dict(point) for point in reversed(points)]
    if change == "swap":
        changed[0]["error"], changed[1]["error"] = changed[1]["error"], changed[0]["error"]
    elif change == "run_id":
        changed[0]["run_id"] = "synthetic row C"
    row = {**_synthetic_refusal(), "message": "old heading", "reasons": points}
    scripts = {"sims/sim_7003/control.txt": "workspace\n"}
    receipt = _parity_receipt(
        tmp_path,
        monkeypatch,
        scripts,
        scripts,
        allow_no_grouped=True,
        refused={
            "base": [row],
            "release": [{**row, "message": "new heading", "reasons": changed}],
        },
    )
    assert receipt["verdict"] == ("PARITY: PASS" if change == "reorder" else "PARITY: FAIL")
    assert len(receipt["scripts"]["differing"]) == (0 if change == "reorder" else 1)


@pytest.mark.parametrize("helper", ["runner_for", "planner_for"])
def test_parity_missing_dispatcher_names_both_helpers(tmp_path, monkeypatch, helper):
    """FIX6 A1: either missing private dispatcher names the entire required pair."""
    spec = importlib.util.spec_from_file_location(
        "missing_dispatcher", REPO / "scripts/check_parity.py"
    )
    assert spec and spec.loader
    parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parity)
    original_import = builtins.__import__

    def missing(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pyflightstream.run._grouped" and helper in fromlist:
            raise ImportError(f"cannot import {helper}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(RuntimeError) as caught:
        parity._workspace_render(tmp_path / "synthetic.fs", tmp_path, [])
    assert "runner_for" in str(caught.value) and "planner_for" in str(caught.value)
    assert isinstance(caught.value.__cause__, ImportError)


def test_parity_dispatch_namespace_matches_cli_plan_attributes():
    """FIX6 A1: pin the namespace's attribute names to the real CLI plan parser."""
    spec = importlib.util.spec_from_file_location(
        "plan_attributes", REPO / "scripts/check_parity.py"
    )
    assert spec and spec.loader
    parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parity)
    source = ast.parse(inspect.getsource(parity._workspace_render))
    (namespace,) = [
        node
        for node in ast.walk(source)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "argparse"
        and node.func.attr == "Namespace"
    ]
    attributes = {keyword.arg for keyword in namespace.keywords}
    parser = parity._capture_parser("pyflightstream.run.cli:main")
    (plan,) = [
        action.choices["plan"]
        for action in parser._actions
        if getattr(action, "choices", None) and "plan" in action.choices
    ]
    cli_attributes = {
        action.dest
        for action in plan._actions
        if {"--batch", "--polar-sweep"}.intersection(action.option_strings)
    }
    assert attributes == cli_attributes
