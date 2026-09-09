"""Tier 1: every command-line option of every console script has chosen.

PFS-2022.06.01, on the decision of design/68 section PFS-2022.06. FR-40
promises that "every command-line option" resolves through the options
registry (:mod:`pyflightstream.options`), and until this module nothing
held a console script to it: the registry had three keys, one CLI read
them, and a new flag could be added anywhere with a literal default and
no test would notice.

The rule this module enforces is weaker than the sentence and honest
about it. An option is either RESOLVED, its default read from a
registry key (measured below by moving the key and watching the default
move), or ALLOWLISTED here with the reason it is not a knob: the subject
of the command, a fact of the case the manifest records, a mode switch
of one invocation, a place to write, or licensed material named
explicitly. The value of the test is that a NEW option must choose,
in this file, in the commit that adds it.
"""

from __future__ import annotations

import argparse
import importlib
import tomllib
from pathlib import Path

import pytest

from pyflightstream.options import option_context

REPO = Path(__file__).resolve().parents[2]

#: The function of each console-script module that builds its parser
#: without parsing anything. A script absent here fails the first test,
#: which is what makes a new script choose too.
PARSER_BUILDERS = {
    "pyflightstream.qa.cli": "_build_parser",
    "pyflightstream.fsi.cli": "_build_parser",
    "pyflightstream.workspace.cli": "_build_parser",
    "pyflightstream.run.cli": "_build_parser",
    "pyflightstream.utils.cli": "_parser",
}

SUBJECT = "names what the command works on (a file, an id, a directory); a subject is never a knob"
SOLVER = "identifies the solver build; the manifest records it, so it is a case fact, not a knob"
CASE = "part of the case definition the manifest records; changing it changes what is run"
SWITCH = "a mode switch of one invocation, with no process-wide meaning"
OUTPUT = "where this invocation writes; the registry holds the scratch ROOT, the leaf is per call"
MANUAL = "licensed vendor material or its citation, named explicitly per call (invariant 1)"
RECORD = "text written into the record of this invocation"

#: (console script, destination) -> why it is not a registry knob.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("pyfs-qa", "fs_version"): SOLVER,
    ("pyfs-qa", "fs_versions"): SOLVER,
    ("pyfs-qa", "fs_exe"): SOLVER,
    ("pyfs-qa", "commands"): CASE,
    ("pyfs-qa", "cases"): CASE,
    ("pyfs-qa", "fsm"): CASE,
    ("pyfs-qa", "label"): CASE,
    ("pyfs-qa", "identity_only"): SWITCH,
    ("pyfs-qa", "include_smi"): SWITCH,
    ("pyfs-qa", "report_dir"): OUTPUT,
    ("pyfs-qa", "report"): SUBJECT,
    ("pyfs-qa", "root"): SUBJECT,
    ("pyfs-qa", "smi_root"): SUBJECT,
    ("pyfs-qa", "campaign"): SUBJECT,
    ("pyfs-qa", "compare"): SUBJECT,
    ("pyfs-qa", "case"): SUBJECT,
    ("pyfs-qa", "from_report"): SUBJECT,
    ("pyfs-qa", "reason"): RECORD,
    ("pyfs-fsi", "node_count"): CASE,
    ("pyfs-fsi", "dir"): SUBJECT,
    ("pyfs-workspace", "root"): SUBJECT,
    ("pyfs-workspace", "sim_id"): SUBJECT,
    ("pyfs-matrix", "matrix"): SUBJECT,
    ("pyfs-matrix", "inputs"): SUBJECT,
    ("pyfs-matrix", "geometry"): SUBJECT,
    ("pyfs-matrix", "workspace"): SUBJECT,
    ("pyfs-matrix", "name"): CASE,
    ("pyfs-matrix", "recipe"): CASE,
    ("pyfs-matrix", "workflow"): CASE,
    ("pyfs-matrix", "point_name"): CASE,
    ("pyfs-matrix", "sweep_csv"): CASE,
    ("pyfs-matrix", "fs_version"): SOLVER,
    ("pyfs-matrix", "fs_exe"): SOLVER,
    ("pyfs-matrix", "in_place"): SWITCH,
    ("pyfs-matrix", "overwrite"): SWITCH,
    ("pyfs-matrix", "resume"): SWITCH,
    ("pyfs-matrix", "strict"): SWITCH,
    ("pyfs-matrix", "output"): OUTPUT,
    ("pyfs-manual", "manual"): MANUAL,
    ("pyfs-manual", "source"): MANUAL,
    ("pyfs-manual", "chapter_pages"): MANUAL,
    ("pyfs-manual", "index_pages"): MANUAL,
    ("pyfs-manual", "editions"): MANUAL,
    ("pyfs-manual", "versions"): SUBJECT,
    ("pyfs-manual", "only"): SUBJECT,
    ("pyfs-manual", "build"): SUBJECT,
    ("pyfs-manual", "commands_dir"): SUBJECT,
    ("pyfs-manual", "out"): OUTPUT,
    ("pyfs-manual", "write"): SWITCH,
    ("pyfs-manual", "by_section"): SWITCH,
    ("pyfs-manual", "fail_if_absent"): SWITCH,
    ("pyfs-manual", "names"): SWITCH,
    ("pyfs-manual", "markdown"): SWITCH,
}

#: (console script, subcommand, destination) -> the registry key its
#: default reads, and a probe value that must show in the default when
#: the key is set to it. Measured, not declared: the parser is rebuilt
#: under ``option_context`` and the default must move.
RESOLVED: dict[tuple[str, str, str], tuple[str, object]] = {
    ("pyfs-qa", "probe", "workroot"): ("qa.scratch_root", "probe-root-of-this-test"),
    ("pyfs-qa", "physics", "workroot"): ("qa.scratch_root", "probe-root-of-this-test"),
    ("pyfs-qa", "drift", "workroot"): ("qa.scratch_root", "probe-root-of-this-test"),
    ("pyfs-qa", "probe", "timeout"): ("qa.probe_timeout_s", 61.5),
    ("pyfs-qa", "physics", "timeout"): ("qa.case_timeout_s", 61.5),
    ("pyfs-qa", "drift", "timeout"): ("qa.case_timeout_s", 61.5),
}


def _console_scripts() -> dict[str, str]:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return {name: target.split(":")[0] for name, target in data["project"]["scripts"].items()}


def _build(module_name: str) -> argparse.ArgumentParser:
    module = importlib.import_module(module_name)
    builder = PARSER_BUILDERS[module_name]
    assert hasattr(module, builder), (
        f"{module_name} has no {builder}(); a console script builds its parser in a "
        "function this test can call without parsing, so its options can be held to FR-40"
    )
    return getattr(module, builder)()


def _options(parser: argparse.ArgumentParser, subcommand: str = "") -> list[tuple[str, str]]:
    """Every (subcommand, destination) the parser accepts, help excluded."""
    found: list[tuple[str, str]] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                found.extend(_options(sub, name))
        elif not isinstance(action, argparse._HelpAction):
            found.append((subcommand, action.dest))
    return found


def _subparser(parser: argparse.ArgumentParser, subcommand: str) -> argparse.ArgumentParser:
    (group,) = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    return group.choices[subcommand]


def test_every_console_script_builds_its_parser_in_a_callable_function():
    """RED on the base tree: pyfs-fsi built its parser inside main()."""
    scripts = _console_scripts()
    missing = set(scripts.values()) - set(PARSER_BUILDERS)
    assert not missing, f"console scripts with no parser builder listed here: {sorted(missing)}"
    for module_name in scripts.values():
        assert isinstance(_build(module_name), argparse.ArgumentParser)


@pytest.mark.requirement("FR-40")
def test_every_command_line_option_has_chosen():
    """FR-40's quantifier, held to every console script.

    An option resolves through the registry (RESOLVED, measured in the
    test below) or is allowlisted here with the reason it is not a knob.
    A new option that does neither fails this test in the commit that
    adds it, which is the whole value of the file.
    """
    undecided = []
    for script, module_name in _console_scripts().items():
        for subcommand, dest in _options(_build(module_name)):
            if (script, subcommand, dest) in RESOLVED or (script, dest) in ALLOWLIST:
                continue
            undecided.append(f"{script} {subcommand} --{dest}")
    assert not undecided, (
        "options that neither resolve through pyflightstream.options nor carry a "
        f"reason in ALLOWLIST: {undecided}. Read the registry's docstring: a machine "
        "knob (a scratch root, a timeout) is registered and the flag defaults from "
        "it; anything else is allowlisted with the reason beside it"
    )


@pytest.mark.parametrize("entry", sorted(RESOLVED), ids=lambda e: " ".join(e))
def test_a_resolved_option_reads_its_default_from_the_registry(entry):
    """The claim RESOLVED makes, measured: move the key, the default moves."""
    script, subcommand, dest = entry
    key, probe = RESOLVED[entry]
    module_name = _console_scripts()[script]
    with option_context(key, probe):
        default = _subparser(_build(module_name), subcommand).get_default(dest)
    assert default == probe or (isinstance(default, str) and str(probe) in default), (
        f"{script} {subcommand} --{dest} defaults to {default!r} with {key} set to {probe!r}; "
        "the default does not read the registry, so the option is not RESOLVED"
    )


def test_the_allowlist_names_only_options_that_exist():
    """A row for a flag that was removed is a reason nobody reads."""
    present = {
        (script, dest)
        for script, module_name in _console_scripts().items()
        for _sub, dest in _options(_build(module_name))
    }
    stale = set(ALLOWLIST) - present
    assert not stale, f"ALLOWLIST rows for options no console script has: {sorted(stale)}"
    resolved_flat = {(script, dest) for script, _sub, dest in RESOLVED}
    assert not resolved_flat & set(ALLOWLIST), "an option is both resolved and allowlisted"


def test_the_registry_requirement_says_command_line_option():
    """The SRS sentence this test holds the scripts to (design/68, PFS-2022.06)."""
    text = (REPO / "docs" / "srs" / "functional-requirements.md").read_text(encoding="utf-8")
    start = text.index('requirement "FR-40')
    statement = text[start : text.index("!!! requirement", start + 1)]
    assert "every command-line option" in statement.lower(), (
        "FR-40 no longer says 'every command-line option'; this test enforces that sentence"
    )
