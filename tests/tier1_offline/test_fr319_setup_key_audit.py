"""Tier 1: every choosable command of the six solver chapters has a key, or a measured reason.

The evidence line of FR-319 cites this module (docs/srs/functional-requirements.md).

The audit is ``reports/RPT-106_setup-key-audit_2026-09-30.md``. These tests
walk its table against the command database and the code: a command of the
six chapters (the sixth is Solver Initialization, which the first version of
the audit left out, so INITIALIZE_SOLVER and its arguments had no row)
missing from the table, a command marked covered whose key does
not reach it, a command marked not choosable that takes an argument, a
cannot-be-covered row without its evidence, and a hard-coded choosable value
in the emitters each fail. Each check also runs once on a planted defect, so a
check that accepts everything cannot pass.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

from pyflightstream.cases import SOLVER_SETTING_COMMANDS, PprocSpec, SolverSettings
from pyflightstream.cases.matrix import MATRIX_COLUMNS
from pyflightstream.cases.workflows import ROW_KEY_MEANINGS
from pyflightstream.commands import CommandRegistry
from pyflightstream.workspace.inputs import ReferenceArtifact

REPO = Path(__file__).resolve().parents[2]
REPORT = REPO / "reports" / "RPT-106_setup-key-audit_2026-09-30.md"
COMMANDS = REPO / "src" / "pyflightstream" / "commands"
CHAPTERS = (
    "runtime_settings",
    "solver_settings",
    "advanced_settings",
    "unsteady_solver",
    "solver_analysis",
    "solver_initialization",
)
#: The keyword blocks whose arguments are each a choice: every argument of the
#: current grammar is a row of its own, ``COMMAND argument``.
ARGUMENT_AUDITED = ("INITIALIZE_SOLVER",)
#: The commands the 26.124 census files under the five sections and the
#: database does not carry, each a row of the audit.
CENSUS_ONLY = frozenset({"SOLVER_INITIALIZATION"})
STATUSES = ("covered", "given a key now", "not a choosable value", "cannot be covered")
#: The emitters a hard-coded choosable value would sit in: every module of the
#: package ``cases/workflows/`` (a module until 0.33.0, AD-12) and the setup link.
EMITTERS = (
    *sorted((REPO / "src" / "pyflightstream" / "cases" / "workflows").glob("*.py")),
    REPO / "src" / "pyflightstream" / "cases" / "_setup_link.py",
)
#: The keyword of each analysis helper argument, and the command it reaches.
HELPER_KEYWORDS = {
    "moments_model": "SET_ANALYSIS_MOMENTS_MODEL",
    "loads_frame": "SET_SOLVER_ANALYSIS_LOADS_FRAME",
    "symmetry_loads": "SET_ANALYSIS_SYMMETRY_LOADS",
    "load_units": "SET_LOADS_AND_MOMENTS_UNITS",
    "inviscid_only": "SET_INVISCID_LOADS",
}


def _chapter_commands() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for chapter in CHAPTERS:
        entries = yaml.safe_load((COMMANDS / f"{chapter}.yaml").read_text(encoding="utf-8"))
        found.update({name: entry for name, entry in entries.items() if isinstance(entry, dict)})
    return found


def _rows(text: str) -> list[dict[str, str]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        command, section, status, key, where, did = cells
        rows.append(
            {
                "command": command.strip("`"),
                "section": section,
                "status": status,
                "key": key,
                "where": where,
                "did": did,
            }
        )
    return rows


def _key_problems(row: dict[str, str]) -> list[str]:
    """Why a covered row's key does not reach its command, or nothing."""
    command = row["command"].split()[0]
    kind, _, name = row["key"].partition(": ")
    if kind == "setup":
        if name not in SolverSettings.model_fields:
            return [f"{command}: setup key {name!r} is no setup field"]
        if SOLVER_SETTING_COMMANDS.get(name) != command:
            return [f"{command}: setup key {name!r} reaches {SOLVER_SETTING_COMMANDS.get(name)}"]
        return []
    known = {
        "row": set(ROW_KEY_MEANINGS),
        "column": set(MATRIX_COLUMNS),
        "reference": set(ReferenceArtifact.model_fields),
        "pproc": set(PprocSpec.model_fields),
    }
    if kind not in known:
        return [f"{command}: covered with no key ({row['key']!r})"]
    if name not in known[kind]:
        return [f"{command}: {kind} key {name!r} does not exist"]
    return []


def _audit_problems(text: str) -> list[str]:
    db = _chapter_commands()
    rows = _rows(text)
    problems: list[str] = []
    listed = [row["command"].split()[0] for row in rows]
    missing = sorted((set(db) | CENSUS_ONLY) - set(listed))
    if missing:
        problems.append(f"commands of the five chapters the audit does not list: {missing}")
    argument_rows = {row["command"] for row in rows}
    for command in ARGUMENT_AUDITED:
        for arg in db.get(command, {}).get("args", []):
            if f"{command} {arg['name']}" not in argument_rows:
                problems.append(f"{command}: the audit does not list argument {arg['name']!r}")
    for row in rows:
        command = row["command"].split()[0]
        if row["status"] not in STATUSES:
            problems.append(f"{command}: unknown status {row['status']!r}")
        elif row["status"] in ("covered", "given a key now"):
            problems += _key_problems(row)
        elif row["status"] == "not a choosable value":
            if db.get(command, {}).get("args"):
                problems.append(f"{command}: marked not choosable and takes arguments")
        else:
            evidence = re.findall(r"reports/[\w./-]+\.(?:yaml|md|json)", row["did"])
            without_entry = command not in db and "no entry in the command database" in row["did"]
            decided = "product decision" in row["did"] or "design decision" in row["did"]
            if not (without_entry or decided or evidence):
                problems.append(f"{command}: cannot be covered, with no measured reason")
            for path in evidence:
                if not (REPO / path).is_file():
                    problems.append(f"{command}: cites {path}, which is not in the repository")
    return problems


def test_every_choosable_command_of_the_five_chapters_has_a_key_or_a_reason():
    """FR-319: the committed audit agrees with the command database and the code."""
    text = REPORT.read_text(encoding="utf-8")
    rows = _rows(text)
    # THE NON-VACUITY FLOOR: the six chapters hold 90 database entries and one
    # census-only name; an audit that lost its rows could agree with nothing.
    assert len(rows) >= 80, len(rows)
    assert _audit_problems(text) == []


@pytest.mark.parametrize(
    ("planted", "said"),
    [
        (("| `SET_WAKE_RELAXATION` |", "| `SET_WAKE_RELAXATIONX` |"), "does not list"),
        (("setup: wake_relaxation |", "setup: wake_relaxed |"), "is no setup field"),
        (("setup: wake_relaxation |", "setup: wake_streamwise_agglomeration |"), "reaches"),
        (("setup: moments_model |", "none |"), "covered with no key"),
    ],
)
def test_each_audit_defect_is_caught(planted, said):
    """FR-319 control: a dropped row, a wrong key and a key-less covered row each fail."""
    old, new = planted
    text = REPORT.read_text(encoding="utf-8")
    assert old in text, old
    problems = _audit_problems(text.replace(old, new, 1))
    assert any(said in problem for problem in problems), problems


def test_the_audit_lists_initialize_solver_and_each_of_its_arguments():
    """FR-319 control: the chapter the first audit missed is read, and dropping its rows fails."""
    text = REPORT.read_text(encoding="utf-8")
    assert "INITIALIZE_SOLVER" in _chapter_commands()
    kept = [line for line in text.splitlines() if not line.startswith("| `INITIALIZE_SOLVER")]
    problems = _audit_problems(chr(10).join(kept))
    assert any("INITIALIZE_SOLVER" in p and "does not list" in p for p in problems), problems


def test_every_argument_of_initialize_solver_has_a_row():
    """FR-319: each argument of the current grammar is a row; a dropped argument row fails."""
    text = REPORT.read_text(encoding="utf-8")
    args = [a["name"] for a in _chapter_commands()["INITIALIZE_SOLVER"]["args"]]
    assert "wake_termination_x" in args
    listed = {row["command"] for row in _rows(text)}
    assert all(f"INITIALIZE_SOLVER {name}" in listed for name in args)
    old = "| `INITIALIZE_SOLVER wake_termination_x` |"
    assert old in text
    problems = _audit_problems(text.replace(old, "| `INITIALIZE_SOLVER wake_term` |", 1))
    assert any("does not list argument 'wake_termination_x'" in p for p in problems), problems


def test_the_wake_end_plane_row_states_its_measured_reason_and_the_release_owed():
    """FR-319: wake_termination_x is written DEFAULT, has no key, and is owed to 0.34."""
    rows = {row["command"]: row for row in _rows(REPORT.read_text(encoding="utf-8"))}
    row = rows["INITIALIZE_SOLVER wake_termination_x"]
    assert row["status"] == "cannot be covered"
    assert "DEFAULT" in row["where"]
    assert "reports/probes/RPT-066_2026-09-24_evidence.yaml" in row["did"]
    assert "0.34" in row["did"] and "WAKE-LENGTH" in row["did"]


def _hard_coded(source: str, commands: set[str]) -> list[str]:
    """Constant values the source passes for a chapter command, by command."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        if attr == "emit" and node.args and isinstance(node.args[0], ast.Constant):
            command = node.args[0].value
            values = [*node.args[1:], *(keyword.value for keyword in node.keywords)]
            if command in commands and any(
                isinstance(value, ast.Constant) and value.value is not None for value in values
            ):
                found.append(command)
        if attr in ("analysis_setup", "solver_settings"):
            for keyword in node.keywords:
                if (
                    keyword.arg in HELPER_KEYWORDS
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is not None
                ):
                    found.append(HELPER_KEYWORDS[keyword.arg])
    return found


def test_no_emitter_hard_codes_a_choosable_value_of_the_five_chapters():
    """FR-319: a new hard-coded choosable value in the emitters fails, with a planted control."""
    commands = set(_chapter_commands())
    found = {
        str(path.name): _hard_coded(path.read_text(encoding="utf-8"), commands) for path in EMITTERS
    }
    assert found == {path.name: [] for path in EMITTERS}
    planted = 'helpers.analysis_setup(script, loads_frame=frame, moments_model="PRESSURE")\n'
    assert _hard_coded(planted, commands) == ["SET_ANALYSIS_MOMENTS_MODEL"]
    emitted = 'script.emit("SET_WAKE_RELAXATION", "ENABLE")\n'
    assert _hard_coded(emitted, commands) == ["SET_WAKE_RELAXATION"]


def test_the_keys_given_now_are_routed_to_their_commands_on_26124():
    """FR-319: each key the audit gave is in the routing table and its command runs on 26.124."""
    registry = CommandRegistry.load()
    for key, command in (
        ("moments_model", "SET_ANALYSIS_MOMENTS_MODEL"),
        ("unsteady_solver_actions", "SET_NEW_UNSTEADY_SOLVER_ACTION"),
    ):
        assert SOLVER_SETTING_COMMANDS[key] == command
        status = registry.commands[command].versions["26.124"].status
        assert str(status) in ("documented", "verified"), (command, status)


def _actions_case(make):
    from pyflightstream.cases import SolverSettings as Settings

    actions = [{"type": "COMMAND_LINE", "name": "log_step", "filename": "python log_step.py"}]
    return make().model_copy(update={"solver": Settings(unsteady_solver_actions=actions)})


def test_a_marching_row_registers_the_setups_actions_and_a_steady_row_refuses_them():
    """FR-319: unsteady_solver_actions reaches SET_NEW_UNSTEADY_SOLVER_ACTION; steady refuses."""
    from pyflightstream.cases import CampaignConfigError
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script
    from tests.tier1_offline.test_workflows import steady_case, unsteady_case

    script = Script("26.124")
    build_script(_actions_case(unsteady_case), script)
    lines = script.render().splitlines()
    at = lines.index("SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE log_step")
    assert lines[at + 1] == "python log_step.py"
    assert at < lines.index("START_SOLVER")
    # THE CONTROL: the same row without the key registers no action of that name.
    bare = Script("26.124")
    build_script(unsteady_case(), bare)
    assert "log_step" not in bare.render()
    with pytest.raises(CampaignConfigError, match="unsteady_solver_actions"):
        build_script(_actions_case(steady_case), Script("26.124"))
