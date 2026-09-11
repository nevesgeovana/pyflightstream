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
    ("pyfs-qa", "fsm"): CASE,
    # physics and drift read a campaign workspace since 0.13.0 (PFS-2031.17)
    ("pyfs-qa", "workspace"): SUBJECT,
    ("pyfs-qa", "matrix"): SUBJECT,
    ("pyfs-qa", "name"): CASE,
    ("pyfs-qa", "resume"): SWITCH,
    ("pyfs-qa", "label"): CASE,
    ("pyfs-qa", "identity_only"): SWITCH,
    ("pyfs-qa", "include_smi"): SWITCH,
    ("pyfs-qa", "report_dir"): OUTPUT,
    ("pyfs-qa", "report"): SUBJECT,
    ("pyfs-qa", "root"): SUBJECT,
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
    # FR-82, her design of 2026-09-11. A SWITCH: whether THIS plan also
    # prints what the campaign is expected to cost is a property of the
    # invocation, not of the machine. Nothing about the estate decides
    # whether a reader wants the table, and a plan that always printed it
    # would put an extrapolation in front of someone who asked for a
    # pre-flight.
    ("pyfs-matrix", "cost"): SWITCH,
    # PFS-2035.13, the author's design of 2026-09-10. A SWITCH and deliberately not a
    # registry knob: whether a family the opened mesh lacks is a skip or a
    # refusal is a property of THIS invocation's intent, not of the machine.
    # A study planned across a wing and a rotor wants the skip; the same
    # matrix planned against the one geometry that should carry everything
    # wants the refusal, and neither is a setting the estate holds for you.
    ("pyfs-matrix", "ignore_missing_families"): SWITCH,
    # The same choice spelled as a flag, so the effect-bearing form is the
    # one you can type bare (the interface lens of the 0.15.0 release
    # review). Stating both is refused, so it is one switch with two names.
    ("pyfs-matrix", "refuse_missing_families"): SWITCH,
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
    ("pyfs-qa", "drift", "workroot"): ("qa.scratch_root", "probe-root-of-this-test"),
    ("pyfs-qa", "probe", "timeout"): ("qa.probe_timeout_s", 61.5),
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


#: WHICH SUBCOMMANDS EACH DESTINATION APPEARS ON, generated from the
#: parsers and pinned. The allowlist is keyed on (script, dest) and the
#: lookup drops the subcommand, so a row exempts its destination on
#: every subcommand the script has AND on every subcommand it ever
#: gains: a new option that IS a machine knob, added on a different
#: subcommand under an allowlisted dest, passed without choosing (the
#: architecture lens of the 0.15.0 release review).
#:
#: Re-keying was measured and rejected: 26 of the 59 destinations
#: genuinely appear on several subcommands and mean the same thing
#: there, so re-keying turns 59 rows into about 100 re-attributed by
#: hand. The pin closes the hole instead, and it fails in BOTH
#: directions: a dest that spreads to a new subcommand, and one that
#: stops appearing on a subcommand it used to cover.
COVERS: dict[tuple[str, str], frozenset[str]] = {
    ("pyfs-fsi", "dir"): frozenset({"init-dummy", "step"}),
    ("pyfs-fsi", "node_count"): frozenset({"init-dummy"}),
    ("pyfs-manual", "build"): frozenset({"register"}),
    ("pyfs-manual", "by_section"): frozenset({"sweep"}),
    ("pyfs-manual", "chapter_pages"): frozenset({"coverage", "draft"}),
    ("pyfs-manual", "commands_dir"): frozenset({"register"}),
    ("pyfs-manual", "editions"): frozenset({"citations", "register", "surface", "sweep"}),
    ("pyfs-manual", "fail_if_absent"): frozenset({"sweep"}),
    ("pyfs-manual", "index_pages"): frozenset({"coverage", "draft"}),
    ("pyfs-manual", "manual"): frozenset({"coverage", "draft"}),
    ("pyfs-manual", "markdown"): frozenset({"surface"}),
    ("pyfs-manual", "names"): frozenset({"surface"}),
    ("pyfs-manual", "only"): frozenset({"draft"}),
    ("pyfs-manual", "out"): frozenset({"draft"}),
    ("pyfs-manual", "source"): frozenset({"coverage", "draft"}),
    ("pyfs-manual", "versions"): frozenset({"draft"}),
    ("pyfs-manual", "write"): frozenset({"draft", "register"}),
    ("pyfs-matrix", "fs_exe"): frozenset({"convert", "plan", "run"}),
    ("pyfs-matrix", "fs_version"): frozenset({"convert", "plan", "run"}),
    ("pyfs-matrix", "geometry"): frozenset({"inventory"}),
    ("pyfs-matrix", "ignore_missing_families"): frozenset({"plan", "run"}),
    ("pyfs-matrix", "in_place"): frozenset({"upgrade"}),
    ("pyfs-matrix", "inputs"): frozenset({"upgrade"}),
    ("pyfs-matrix", "matrix"): frozenset({"convert", "plan", "post", "run", "upgrade"}),
    ("pyfs-matrix", "name"): frozenset({"convert", "plan", "run"}),
    ("pyfs-matrix", "output"): frozenset({"convert"}),
    ("pyfs-matrix", "overwrite"): frozenset({"inventory", "post"}),
    ("pyfs-matrix", "point_name"): frozenset({"plan", "run"}),
    ("pyfs-matrix", "recipe"): frozenset({"convert", "plan", "run"}),
    ("pyfs-matrix", "refuse_missing_families"): frozenset({"plan", "run"}),
    ("pyfs-matrix", "resume"): frozenset({"run"}),
    ("pyfs-matrix", "cost"): frozenset({"plan"}),
    ("pyfs-matrix", "strict"): frozenset({"post"}),
    ("pyfs-matrix", "sweep_csv"): frozenset({"run"}),
    ("pyfs-matrix", "workflow"): frozenset({"plan", "run"}),
    ("pyfs-matrix", "workspace"): frozenset({"plan", "post", "run"}),
    ("pyfs-qa", "campaign"): frozenset({"cost"}),
    ("pyfs-qa", "case"): frozenset({"update-reference"}),
    ("pyfs-qa", "commands"): frozenset({"probe"}),
    ("pyfs-qa", "compare"): frozenset({"cost"}),
    ("pyfs-qa", "from_report"): frozenset({"update-reference"}),
    ("pyfs-qa", "fs_exe"): frozenset({"drift", "probe"}),
    ("pyfs-qa", "fs_version"): frozenset({"probe"}),
    ("pyfs-qa", "fs_versions"): frozenset({"drift"}),
    ("pyfs-qa", "fsm"): frozenset({"probe"}),
    ("pyfs-qa", "identity_only"): frozenset({"probe"}),
    ("pyfs-qa", "include_smi"): frozenset({"cases"}),
    ("pyfs-qa", "label"): frozenset({"drift", "physics", "probe"}),
    ("pyfs-qa", "matrix"): frozenset({"drift", "physics"}),
    ("pyfs-qa", "name"): frozenset({"drift", "physics"}),
    ("pyfs-qa", "reason"): frozenset({"update-reference"}),
    ("pyfs-qa", "report"): frozenset({"apply-compat"}),
    ("pyfs-qa", "report_dir"): frozenset({"drift", "physics", "probe"}),
    ("pyfs-qa", "resume"): frozenset({"physics"}),
    ("pyfs-qa", "root"): frozenset({"apply-compat"}),
    ("pyfs-qa", "timeout"): frozenset({"probe"}),
    ("pyfs-qa", "workroot"): frozenset({"drift", "probe"}),
    ("pyfs-qa", "workspace"): frozenset({"drift", "physics"}),
    ("pyfs-workspace", "root"): frozenset({"archive", "init", "migrate-geometries"}),
    ("pyfs-workspace", "sim_id"): frozenset({"archive"}),
}


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


def test_every_allowlisted_destination_covers_the_subcommands_it_says():
    """The allowlist's scope is pinned, because its key cannot express one.

    A row is keyed (script, dest) and the lookup at the guard above drops
    the subcommand, so nothing in the key says where the exemption applies.
    This is what says it, and it is generated from the parsers rather than
    written by hand, so it cannot drift into agreeing with itself.
    """
    live: dict[tuple[str, str], set[str]] = {}
    for script, module_name in _console_scripts().items():
        for subcommand, dest in _options(_build(module_name)):
            live.setdefault((script, dest), set()).add(subcommand)
    moved = []
    for key, subs in sorted(live.items()):
        pinned = COVERS.get(key)
        if pinned is None:
            moved.append(f"{key[0]} --{key[1]} is on {sorted(subs)} and is pinned nowhere")
        elif frozenset(subs) != pinned:
            moved.append(f"{key[0]} --{key[1]} is on {sorted(subs)}, pinned to {sorted(pinned)}")
    for key in sorted(set(COVERS) - set(live)):
        moved.append(f"{key[0]} --{key[1]} is pinned and appears on no subcommand")
    assert not moved, (
        "the subcommands an option appears on moved:\n  "
        + "\n  ".join(moved)
        + "\n\nAn ALLOWLIST row exempts its destination wherever that destination "
        "appears, so a destination reaching a NEW subcommand widens an exemption "
        "nobody wrote. Decide there: register the new option through "
        "pyflightstream.options if it is a machine knob, or update this pin in the "
        "same commit if the spread is intended."
    )
