"""The parity instrument's tests share one fixture home and cover its refusal fallback (NFR-42).

``scripts/check_parity.py`` compares the refusals of a matrix at two versions. Its reader of a
refusal has three branches: the structured per-point reasons of ``plan.json``, a message that
lists points (parsed), and the whole message (a refusal before planning). Every branch is tested
with a one-line change, and the grouped-plan workspace the parity tests use is defined once, in
``tests/support_helpers.py``. The FR-421 comparison of left-out reasons is tested through the real
``parity()`` verdict over controlled collector observations.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

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


def _tier1_imports(source: str) -> list[str]:
    """Return every tier-1 test module a source imports, at any depth of the source."""
    modules = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            modules.append(str(node.args[0].value))
    return [name for name in modules if name.split(".")[:2] == ["tests", "tier1_offline"]]


def _builder_definitions(source: str) -> list[str]:
    return [
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name in FIXTURE_BUILDERS
    ]


#: The builders the grouped-plan workspace is made of: each is defined once, in the support module.
FIXTURE_BUILDERS = (
    "grouped_plan_fixture",
    "rotor_workspace",
    "rotor_row",
    "make_library",
    "fixture_codes",
    "stage_geometry",
)


def test_p0370_s9_the_fixture_has_one_definition_in_the_support_module():
    """P0370-S9-PARITY-TESTS (FR-1183): the fixture and every builder it uses live in one module.

    The dependency graph is walked, not one spelling: the support module imports no tier-1 test
    module at any depth, each builder of the fixture is defined there and nowhere in tier 1, and
    no tier-1 module imports the fixture from another test module under any name. A planted lazy
    import and a planted second definition are caught.
    """
    support = (REPO / "tests" / "support_helpers.py").read_text(encoding="utf-8")
    assert _tier1_imports(support) == []
    assert sorted(_builder_definitions(support)) == sorted(FIXTURE_BUILDERS)
    second = {
        path.name: found
        for path in TIER1.glob("*.py")
        if (found := _builder_definitions(path.read_text(encoding="utf-8")))
    }
    assert not second
    homes = {
        path.name: hits
        for path in TIER1.glob("*.py")
        if (
            hits := [
                f"{node.module}.{item.name}"
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                if isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("tests.tier1_offline")
                for item in node.names
                if item.name in ("_fixture", "grouped_plan_fixture")
            ]
        )
    }
    assert not homes
    lazy = "def grouped_plan_fixture():\n    from tests.tier1_offline.test_x import _workspace\n"
    assert _tier1_imports(lazy) == ["tests.tier1_offline.test_x"]
    assert _builder_definitions("def make_library(tmp_path):\n    pass\n") == ["make_library"]


def test_p0370_s9_the_shared_fixture_builds_the_grouped_plan_workspace(tmp_path):
    """P0370-S9-PARITY-TESTS (FR-1183): the support fixture returns the matrix it names.

    One rotor row per walltime cell, each with its own pol, in a workspace that holds the row's
    geometry.
    """
    workspace, matrix = grouped_plan_fixture(tmp_path, walltimes=("1h", "2h"), sweep="0.0")
    rows = matrix.read_text(encoding="utf-8").splitlines()[2:]
    assert [row.split("|")[0].strip() for row in rows] == ["7001", "7002"]
    assert (workspace.inputs_dir / "geometries" / "wing_clean.fsm").is_file()


def test_p0370_s9_without_a_plan_a_one_line_config_message_change_is_a_difference(tmp_path):
    """P0370-S9-PARITY-TESTS (FR-1184): the whole-message fallback compares the message.

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
    """P0370-S9-PARITY-TESTS (FR-1184): the parsed-message branch counts the point lines only.

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
    """P0370-S9-PARITY-TESTS (FR-1184): plan.json reasons decide, a heading change does not.

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
    """P0370-S9-PARITY-TESTS (FR-1184): a pair refused at the release only is reported."""
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


def _verdict(
    tmp_path,
    monkeypatch,
    base_skipped,
    release_skipped,
    *,
    interfaces=None,
    base_version="0.36.0",
    renders=None,
):
    """Run the real ``parity()`` over controlled collector observations at both trees.

    The two sides render the same workspace script and differ only in what the grouped plan left
    out (``grouped_skipped``), so the receipt's differences and verdict are the instrument's own
    answer about that one change. FR-421 is the only requirement the release SRS defines here.
    """
    parity = _parity()

    def git(*args, binary=False):
        if args[0] == "show" and args[1].endswith(":pyproject.toml"):
            return f'version = "{base_version}"'  # scopes named entries (P0400)
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
                or (interfaces is not None and f"{module}.{name}" in interfaces["missing"])
            ]
        if mode == "cli":
            if interfaces is not None:
                return interfaces[work.name]
            return {"spellings": ["pyfs-matrix"], "unavailable": {}}
        if mode == "scripts":
            if renders is not None:
                (work / "script-inventories.json").write_text(
                    json.dumps(
                        {
                            "render/control.txt": renders.get(
                                "release_inventory", renders["inventory"]
                            )
                            if work.name == "release"
                            else renders["inventory"]
                        }
                    ),
                    encoding="utf-8",
                )
                return {"render/control.txt": renders[work.name]}
            return {"render/control.txt": "render\n"}
        assert mode == "workspace-scripts"
        skipped = base_skipped if work.name == "base" else release_skipped
        return {
            "scripts": {"sims/sim_7002/control.txt": "workspace\n"},
            "grouped_skipped": [
                {"matrix": "m.fs", "mode": "--batch", "reasons": skipped},
            ],
            "grouped_attempted": ["--batch"],
            "workspace_refused": [],
            "workspace_rendered": [{"matrix": "m.fs", "mode": "--per-point"}],
        }

    def post(python, tree, source, ws, keep):
        keep.mkdir()
        (keep / "control.txt").write_bytes(b"post\n")
        return {"exit": 0, "stderr_tail": ""}

    monkeypatch.setattr(parity, "git", git)
    monkeypatch.setattr(parity, "export", lambda sha, tree: tree.mkdir(exist_ok=True))
    monkeypatch.setattr(parity, "run_child", collect)
    monkeypatch.setattr(parity, "run_post", post)
    monkeypatch.setattr(
        parity,
        "srs_ids",
        lambda tree: {"FR-421"} if renders is None else renders.get("defined", {"FR-3831"}),
    )
    return parity, parity.parity(
        Namespace(
            base="base",
            release="release",
            workspace=tmp_path,
            temp=tmp_path,
            python="unused",
            keep=False,
            allow_no_grouped=True,
        )
    )


def _sim(reason):
    return [{"sim": "7001", "reason": reason}]


def _interfaces():
    return {
        "missing": ["pyflightstream.other.public"],
        "base": {"spellings": ["pyfs-matrix show", "pyfs-matrix show --json"], "unavailable": {}},
        "release": {
            "spellings": ["pyfs-workspace show", "pyfs-workspace show --json"],
            "unavailable": {},
            "retirements": {
                "api": {
                    "pyflightstream.other.public": {
                        "since": "0.58.0",
                        "replacement": "current",
                        "message": "the registered actionable refusal",
                        "decision": "AD-15",
                        "migration": "docs/upgrading.md",
                    }
                },
                "cli": {
                    "pyfs-matrix show": {
                        "since": "0.58.0",
                        "replacement": "pyfs-workspace show",
                        "message": "the registered actionable refusal",
                        "decision": "AD-15",
                        "migration": "docs/upgrading.md",
                    }
                },
            },
        },
    }


def test_p0580_parity_checks_documented_retirements_and_exact_command_homes(tmp_path, monkeypatch):
    """P0580-PARITY-INTERFACES (AD-15): a verified refusal and exact moved suffix pass."""
    _, receipt = _verdict(tmp_path, monkeypatch, [], [], interfaces=_interfaces())
    assert receipt["verdict"] == "PARITY: PASS"
    assert not receipt["api"]["missing"] and not receipt["cli"]["missing"]
    assert "pyflightstream.other.public" in receipt["api"]["retired"]
    assert receipt["cli"]["migrated"]["pyfs-matrix show --json"]["current"] == (
        "pyfs-workspace show --json"
    )
    assert any("moved command" in entry for entry in receipt["controls"]["detail"])


def test_p0580_parity_does_not_allow_other_attributes_or_options_of_a_retired_home(
    tmp_path, monkeypatch
):
    """P0580-PARITY-INTERFACES (AD-15): a ledger row never exempts its entire owner."""
    for kind in ("api", "cli"):
        data = _interfaces()
        if kind == "api":
            data["release"]["retirements"]["api"].clear()
        else:
            data["base"]["spellings"].append("pyfs-matrix show --invented")
        _, receipt = _verdict(tmp_path, monkeypatch, [], [], interfaces=data)
        assert receipt["verdict"] == "PARITY: FAIL", kind
        assert receipt[kind]["missing"], kind


def test_p0580_parity_collects_observed_refusals_not_just_ledger_rows(monkeypatch):
    """P0580-PARITY-INTERFACES (AD-15): the actual old API and CLI must refuse by name."""
    parity = _parity()
    first = parity.collect_cli(REPO).get("retirements", {})
    name = "pyflightstream.post.polar.GroupCoefficients"
    assert name in first.get("api", {})
    assert "pyfs-matrix show" in first.get("cli", {})
    # The negative observation is a synthetic import fixture: the ledger claims
    # retirement while its owner still offers the binding and its CLI exits 0.
    api = SimpleNamespace(
        owner="example",
        old="GroupCoefficients",
        new="current",
        retired_in="0.58.0",
        message=lambda: "the registered actionable refusal",
    )
    command = SimpleNamespace(
        owner="pyfs-matrix",
        old="show",
        new="pyfs-workspace show",
        retired_in="0.58.0",
        message=lambda: "the registered actionable refusal",
    )
    imports = {
        "pyflightstream._retired_names": SimpleNamespace(
            RETIRED_ATTRIBUTES={"example.GroupCoefficients": api},
            REMOVED_FORMS={"pyfs-matrix.show": command},
            RetiredAttributeError=AttributeError,
        ),
        "example": SimpleNamespace(GroupCoefficients=object(), main=lambda argv: 0),
    }
    monkeypatch.setattr(parity.importlib, "import_module", imports.__getitem__)
    second = parity._collect_retirements(REPO, {"pyfs-matrix": "example:main"})
    assert "example.GroupCoefficients" not in second.get("api", {})
    assert "pyfs-matrix show" not in second.get("cli", {})


def test_p0580_parity_retirement_policy_does_not_cover_a_current_base(tmp_path, monkeypatch):
    """P0580-PARITY-INTERFACES (AD-15): a migration cannot excuse a later regression."""
    _, receipt = _verdict(
        tmp_path, monkeypatch, [], [], interfaces=_interfaces(), base_version="0.58.0"
    )
    assert receipt["verdict"] == "PARITY: FAIL"
    assert receipt["api"]["missing"] == ["pyflightstream.other.public"]
    assert len(receipt["cli"]["missing"]) == 2


def test_p0580_parity_keeps_only_the_exact_retired_option_and_empty_container():
    """P0580-PARITY-INTERFACES (AD-15, FR-3833): no unknown child or flag is waived."""
    parity = _parity()
    records = {
        "pyfs-workspace geometry": {
            "replacement": "pyfs-mesh for mesh verbs, pyfs-geom iges-convert and pyfs-fsi beam"
        },
        "pyfs-matrix run --sweep-csv": {"replacement": "the group files of each polar"},
    }
    known = {
        "pyfs-workspace geometry",
        "pyfs-workspace geometry --help",
        "pyfs-workspace geometry -h",
        "pyfs-matrix run --sweep-csv",
    }
    unknown = {
        "pyfs-workspace geometry invented",
        "pyfs-workspace geometry --invented",
        "pyfs-matrix run --sweep-csv=choice",
    }
    release = {
        p + suffix
        for p in ("pyfs-mesh", "pyfs-geom", "pyfs-fsi")
        for suffix in ("", " -h", " --help")
    }
    assert parity.cli_refused(known | unknown, release, records) == sorted(unknown)
    assert "pyfs-workspace geometry -h" in parity.cli_refused(
        known, release - {"pyfs-fsi -h"}, records
    )


def _family_plot(short, family, boundary, frame=17):
    parameter = ("FORCE_" if short[0] == "F" else "MOMENT_") + short[1]
    return (
        "\nUNSTEADY_SOLVER_NEW_FORCE_PLOT\n"
        f"FRAME {frame}\nUNITS NEWTONS\nPARAMETER {parameter}\n"
        f"NAME {short}_MRP_{family}\nBOUNDARIES 1\n{boundary}\n"
    )


def _family_renders():
    before = (
        "OPEN\nfixture.fsm\n\nCREATE_NEW_COORDINATE_SYSTEM\n"
        "EDIT_COORDINATE_SYSTEM\nFRAME 17\nNAME MRP\nORIGIN_X 0\n"
        "\nSET_SOLVER_UNSTEADY\nSTART_SOLVER\n"
    )
    plots = "".join(
        _family_plot(short, family, boundary)
        for boundary, family in enumerate(("Wing", "Tail"), 1)
        for short in ("FX", "FY", "FZ", "MX", "MY", "MZ")
    )
    return {"base": before, "release": before + plots, "inventory": ["Wing", "Tail"]}


def test_p0580_parity_names_only_complete_family_plots_of_the_opened_inventory(
    tmp_path, monkeypatch
):
    """P0580-PARITY-FAMILY-PLOTS (FR-3831): exact components, boundary order and MRP frame."""
    data = _family_renders()
    _, receipt = _verdict(tmp_path, monkeypatch, [], [], renders=data, base_version="0.57.0")
    assert receipt["verdict"] == "PARITY: PASS"
    (change,) = receipt["scripts"]["differing"]
    assert change["requirement"] == "FR-3831"
    assert any("family plot" in entry for entry in receipt["controls"]["detail"])
    # A name already plotted by pproc keeps its previous bytes and is not added twice.
    existing = _family_plot("FX", "Wing", 1).replace("NEWTONS", "COEFFICIENTS")
    data["base"] += existing
    data["release"] = data["release"].replace(_family_plot("FX", "Wing", 1), "") + existing
    _, partial = _verdict(tmp_path, monkeypatch, [], [], renders=data, base_version="0.57.0")
    assert partial["verdict"] == "PARITY: PASS"


def test_p0580_parity_refuses_incomplete_or_unrelated_family_plot_changes(tmp_path, monkeypatch):
    """P0580-PARITY-FAMILY-PLOTS (FR-3831): no changed old line, invented family or wrong id."""
    data = _family_renders()
    correct = data["release"]
    for wrong in (
        correct.replace("BOUNDARIES 1\n1\n", "BOUNDARIES 1\n2\n"),
        correct.replace("MRP_Wing", "MRP_Invented"),
        correct.replace("FRAME 17\nUNITS", "FRAME 2\nUNITS"),
        correct.replace("PARAMETER FORCE_X", "PARAMETER MOMENT_X"),
        correct.replace("UNITS NEWTONS", "UNITS COEFFICIENTS"),
        correct.replace(_family_plot("MZ", "Tail", 2), ""),
        correct + _family_plot("FX", "Tail", 2),
        correct.replace("ORIGIN_X 0", "ORIGIN_X 1"),
        correct + "\n",
    ):
        _, receipt = _verdict(
            tmp_path, monkeypatch, [], [], renders={**data, "release": wrong}, base_version="0.57.0"
        )
        assert receipt["verdict"] == "PARITY: FAIL"
        assert "requirement" not in receipt["scripts"]["differing"][0]
    for overrides in (
        {"defined": set()},
        {"inventory": ["Tail", "Wing"]},
        {"release_inventory": ["Tail", "Wing"]},
    ):
        _, receipt = _verdict(
            tmp_path, monkeypatch, [], [], renders={**data, **overrides}, base_version="0.57.0"
        )
        assert receipt["verdict"] == "PARITY: FAIL"
    _, receipt = _verdict(tmp_path, monkeypatch, [], [], renders=data, base_version="0.58.0")
    assert receipt["verdict"] == "PARITY: FAIL"


def test_p0580_parity_family_inventory_is_read_from_the_opened_fsm_inside_the_tree():
    """P0580-PARITY-FAMILY-PLOTS (FR-3831): missing and escaped paths supply no allowance."""
    parity = _parity()
    inventories = parity._script_inventories(
        REPO,
        {
            "valid": "OPEN\n<tier3>/inputs/geometries/10_WING.fsm\n",
            "escaped": "OPEN\n<tier3>/../../../pyproject.toml\n",
            "missing": "OPEN\n<tier3>/inputs/geometries/not-present.fsm\n",
        },
    )
    assert inventories == {"valid": ["Wing"]}


def test_p0370_s9_the_verdict_names_exactly_the_changed_coupled_reason(tmp_path, monkeypatch):
    """P0370-S9-GROUPED-HELP (FR-421): ``parity()`` passes the one exact old to new pair.

    The release's reason is the 0.36.0 text replaced by the 0.37.0 text, and nothing else
    differs: the receipt lists one difference, named FR-421, and the verdict is PASS. The same
    run with the comparison removed from the pipeline would list none.
    """
    parity = _parity()
    _, receipt = _verdict(
        tmp_path, monkeypatch, _sim(parity.LEFT_OUT_BEFORE), _sim(parity.LEFT_OUT_AFTER)
    )
    (entry,) = receipt["scripts"]["differing"]
    assert entry["requirement"] == "FR-421"
    assert entry["name"] == "workspace/m.fs (--batch) left out sim 7001"
    assert receipt["verdict"] == "PARITY: PASS"
    _, same = _verdict(
        tmp_path, monkeypatch, _sim(parity.LEFT_OUT_AFTER), _sim(parity.LEFT_OUT_AFTER)
    )
    assert same["scripts"]["differing"] == []
    assert same["verdict"] == "PARITY: PASS"


def test_p0370_s9_the_verdict_refuses_every_other_change_of_a_left_out_reason(
    tmp_path, monkeypatch
):
    """P0370-S9-GROUPED-HELP (FR-421): append-only, newline, reverse, unrelated are unnamed.

    Each change reaches the final verdict as a difference without a requirement, and the verdict
    is FAIL: a reason with the pair appended to it, the new text with a trailing newline, the
    pair reversed, an unrelated reason changed, an exclusion the release added and one it dropped.
    """
    parity = _parity()
    before, after = parity.LEFT_OUT_BEFORE, parity.LEFT_OUT_AFTER
    restart = "a RESTART row opens a datapoint's saved simulation"
    cases = {
        "append-only": (_sim(restart), _sim(f"{restart}\n{before}\n{after}")),
        "extra newline": (_sim(before), _sim(after + "\n")),
        "reverse": (_sim(after), _sim(before)),
        "unrelated": (_sim(restart), _sim("a restart row")),
        "pair on another reason": (_sim(restart), _sim(after)),
        "added exclusion": ([], _sim(after)),
        "dropped exclusion": (_sim(after), []),
    }
    for label, (base, release) in cases.items():
        _, receipt = _verdict(tmp_path, monkeypatch, base, release)
        (entry,) = receipt["scripts"]["differing"]
        assert "requirement" not in entry, label
        assert receipt["verdict"] == "PARITY: FAIL", label


def test_p0370_s9_the_verdict_compares_grouped_point_errors(tmp_path, monkeypatch):
    """P0370-S9-GROUPED-HELP (FR-421): a changed per-point error fails the verdict.

    A point the grouped plan blocked beside a written batch carries ``run_id`` and ``reason``;
    its reason changing between the trees is a difference, and the same error on both sides is not.
    """
    point = "rotor/sim_7002/V0300RE120AL+000"
    old = [{"run_id": point, "reason": "old failure"}]
    _, same = _verdict(tmp_path, monkeypatch, old, old)
    assert same["scripts"]["differing"] == []
    assert same["verdict"] == "PARITY: PASS"
    _, receipt = _verdict(tmp_path, monkeypatch, old, [{"run_id": point, "reason": "new failure"}])
    (entry,) = receipt["scripts"]["differing"]
    assert entry["name"] == f"workspace/m.fs (--batch) left out point {point}"
    assert "requirement" not in entry
    assert receipt["verdict"] == "PARITY: FAIL"
