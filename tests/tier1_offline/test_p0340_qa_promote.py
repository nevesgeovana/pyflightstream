"""Tier 1: the acoustic, CCS, surface-removal and wake commands are probed through pyfs-qa (FR-333).

Marker P0340-QA-PROMOTE, arm CN of GOAL-039, package QA-SPECS. The licensed run that
judges these commands is the session's (RPT-126); what is measured here is the part
that needs no solver: the set of R1 is counted from the three round reports, every
command of it and of the four chapters the goal names has a catalog entry that builds a
probe script for 26.124, the wake entry reads an effect, and the database status of each
follows the verdict of the run's committed report (a planted mismatch is its control).
"""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

import pytest
import yaml

from pyflightstream.commands import CommandRegistry
from pyflightstream.qa import specs
from pyflightstream.qa.compat import apply_compat
from pyflightstream.qa.probes import generate_probe_script
from pyflightstream.script import BrokenCommandError
from tests.tier1_offline._p0340_probe_support import (
    BUILD,
    COMMANDS,
    RUN_LABEL_CN,
    build_script,
    census_of_reports,
    chapter_commands,
    run_report,
    status_on,
    target_line,
    verdict_mismatches,
    verdicts_of,
)

#: R1: every command whose 26.124 status was `documented` and which ran on 26.124 in RPT-096,
#: RPT-097 or RPT-098, less the CCS-wing control surface that FR-334 owns. Counted when the
#: package started: 17 (seven acoustic, DELETE_SURFACES, the wake stabilisation, and eight
#: CCS lofting commands). The FR names six acoustic commands and the reports name seven.
R1_SET = (
    "ACOUSTIC_SOURCES",
    "CREATE_NEW_ACOUSTIC_OBSERVER",
    "ACOUSTIC_OBSERVERS_IMPORT",
    "SET_ACOUSTIC_OBSERVER_TIME",
    "COMPUTE_ACOUSTIC_SIGNALS",
    "EXPORT_ACOUSTIC_SIGNALS",
    "CREATE_ACOUSTIC_SECTION",
    "DELETE_SURFACES",
    "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION",
    "CAD_CREATE_INITIALIZE",
    "CAD_CREATE_IMPORT_CURVE_CCS",
    "CAD_CREATE_CURVE_SELECT",
    "CAD_CREATE_WING_MESH_FROM_CCS",
    "CAD_CREATE_FUSELAGE_MESH_FROM_CCS",
    "CAD_CREATE_REVOLVE_MESH_FROM_CCS",
    "CCS_IMPORT",
    "CCS_WING_MESH_SUBDIVISIONS",
)

#: The chapters the goal reads for arm CN, and the one command of the sixth file.
CHAPTERS = (
    "acoustics.yaml",
    "ccs_wing_mesh.yaml",
    "ccs_fuselage_mesh.yaml",
    "ccs_revolve_mesh.yaml",
)
#: The arm reads the chapters as they stood for 26.124, the build it ran on: the
#: curve assignments the 26.125 edition adds to the three CCS chapters (item S10)
#: have no 26.124 row and are judged by the 26.125 campaign instead.
ARM_CN = tuple(
    name
    for name in (*chapter_commands(*CHAPTERS), "DELETE_SURFACES")
    if "26.124" in CommandRegistry.load().commands[name].versions
)
EVERY = tuple(dict.fromkeys((*R1_SET, *ARM_CN)))


def test_the_set_of_r1_is_the_commands_the_three_round_reports_name_fr_333():
    """FR-333 R1, marker P0340-QA-PROMOTE: the set is counted from RPT-096, RPT-097 and RPT-098."""
    named = census_of_reports("RPT-096", "RPT-097", "RPT-098") - {"NEW_CCS_WING_CONTROL_SURFACE"}
    assert named == set(R1_SET), (
        f"the three round reports name {sorted(named ^ set(R1_SET))} differently from the "
        "recorded set; recount and list it in RPT-126"
    )
    assert len(R1_SET) == 17


def test_every_command_of_the_set_and_of_the_chapters_has_a_catalog_entry_fr_333():
    """FR-333 R2, marker P0340-QA-PROMOTE: each has a probe specification the probe runs."""
    missing = [name for name in EVERY if name not in specs.PROBE_SPECS]
    assert not missing, f"commands without a catalog entry: {missing}"
    assert len(ARM_CN) >= 40


@pytest.mark.parametrize("command", EVERY)
def test_each_entry_builds_a_script_that_emits_its_command_on_26124_fr_333(command):
    """FR-333 R2, marker P0340-QA-PROMOTE: the generated script emits the command under test."""
    entry = specs.PROBE_SPECS[command]
    assert entry.command == command
    assert entry.assert_effect is not None or entry.expects_halt
    assert target_line(command).startswith(command)
    assert f"PYFS_PROBE_BEGIN_{command}" in build_script(command)


@pytest.mark.parametrize("family", ["FUSELAGE", "REVOLVE"])
def test_a_broken_precondition_is_waived_and_stays_visible_in_the_script_fr_333(family, tmp_path):
    """FR-333 R2, marker P0340-QA-PROMOTE: RPT-126 records NEW_CCS_*_RELAXED_TE broken on 26.124.

    The deletion's probe needs it, so the build of the script waives it (it used to end in
    BrokenCommandError) and names it in the script; the control is the same spec with the
    waiver removed, which must still refuse.
    """
    command = f"DELETE_CCS_{family}_RELAXED_TE"
    precondition = f"NEW_CCS_{family}_RELAXED_TE"
    entry = specs.PROBE_SPECS[command]
    assert entry.preconditions == (precondition,)
    script = generate_probe_script(entry, "26.124", tmp_path, fsm=tmp_path / "x.fsm")
    text = build_script(command)
    assert f"precondition {precondition}" in text
    lines = text.splitlines()
    emitted = [i for i, line in enumerate(lines) if line.startswith(f"{precondition} ")]
    begin = [i for i, line in enumerate(lines) if f"PYFS_PROBE_BEGIN_{command}" in line]
    assert emitted and begin, (emitted, begin)
    assert emitted[0] < begin[0], "the precondition command precedes the probe's begin marker"
    assert precondition in [use.command for use in script.waived_commands]
    bare = dataclasses.replace(entry, preconditions=())
    with pytest.raises(BrokenCommandError):
        generate_probe_script(bare, "26.124", tmp_path, fsm=tmp_path / "x.fsm")


def test_the_wake_stabilisation_reads_the_saved_simulation_not_a_placeholder_fr_333():
    """FR-333 R2, marker P0340-QA-PROMOTE: the wake entry saves state and judges a change."""
    entry = specs.PROBE_SPECS["SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION"]
    assert entry.save_state, "the stored key is read from the saved simulation"
    line = target_line("SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION")
    assert line.split(" ")[2] == "DISABLE", "the probe turns it off after turning it on"
    script = build_script("SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION")
    assert script.index(" ENABLE ") < script.index(line)


def test_the_database_follows_the_verdict_of_the_runs_report_fr_333():
    """FR-333 R3 and R4, marker P0340-QA-PROMOTE: each status equals the verdict the report records.

    Until the licensed run commits its report (``CMP-26124_<date>_qa-promote.yaml``) nothing
    moved, and every command of R1 keeps the status it had; once it exists, every command of
    the set has a line in it and each status equals its verdict.
    """
    statuses = {name: status_on(name) for name in EVERY}
    report = run_report(RUN_LABEL_CN)
    if report is None:
        moved = {name: s for name, s in statuses.items() if name in R1_SET and s != "documented"}
        assert not moved, f"a status moved without a committed report of the run: {moved}"
        return
    verdicts = verdicts_of(report)
    assert not [name for name in EVERY if name not in verdicts], "the report lacks a command"
    assert verdict_mismatches(verdicts, statuses, EVERY) == []


def test_a_planted_mismatch_between_the_report_and_the_database_is_found_fr_333():
    """FR-333 R4, marker P0340-QA-PROMOTE: the check names a status that differs from a verdict."""
    report = {
        "A": {"outcome": "verified"},
        "B": {"outcome": "unprobed"},
        "C": {"outcome": "broken"},
    }
    statuses = {"A": "documented", "B": "documented", "C": "broken"}
    wrong = verdict_mismatches(report, statuses, ["A", "B", "C"])
    assert wrong == ["A: the report says verified, the database says documented"]
    assert verdict_mismatches(report, {**statuses, "A": "verified"}, ["A", "B", "C"]) == []


def _chapter_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "commands"
    shutil.copytree(COMMANDS, destination, ignore=shutil.ignore_patterns("__pycache__", "*.py"))
    return destination


def _report(tmp_path: Path, outcome: str) -> Path:
    document = {
        "schema": "pyflightstream-compat-report/1",
        "fs_version": BUILD,
        "date": "2026-10-02",
        "commands": {"ACOUSTIC_SOURCES": {"outcome": outcome, "detail": "planted"}},
    }
    path = tmp_path / "reports" / "compat" / f"CMP-26124_2026-10-02_{outcome}.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def test_a_promotion_from_a_report_that_judged_nothing_changes_nothing_fr_333(tmp_path):
    """FR-333 R4, marker P0340-QA-PROMOTE: an unprobed report leaves the chapters byte for byte."""
    commands = _chapter_copy(tmp_path)
    before = {p.name: p.read_bytes() for p in commands.glob("*.yaml")}
    report = _report(tmp_path, "unprobed")
    assert apply_compat(report, repo_root=tmp_path, commands_dir=commands) == []
    assert {p.name: p.read_bytes() for p in commands.glob("*.yaml")} == before


def test_a_promotion_from_a_report_that_judged_the_command_moves_it_fr_333(tmp_path):
    """FR-333 R4, marker P0340-QA-PROMOTE: the control of the test above, a verdict promotes.

    The planted verdict is one that MOVES the row as it stands: `verified` while the row is not
    verified, `broken` once the licensed run of RPT-126 promoted it, because a second `verified`
    from another report corroborates the row and keeps its line, by design of the promotion tool.
    """
    commands = _chapter_copy(tmp_path)
    chapter = commands / "acoustics.yaml"
    before = chapter.read_bytes().replace(b"\r\n", b"\n")
    outcome = "broken" if status_on("ACOUSTIC_SOURCES") == "verified" else "verified"
    report = _report(tmp_path, outcome)
    promoted = apply_compat(report, repo_root=tmp_path, commands_dir=commands)
    assert promoted == [("ACOUSTIC_SOURCES", outcome, "acoustics.yaml")]
    after = chapter.read_bytes().replace(b"\r\n", b"\n")
    assert after != before, "the line endings alone do not count as a promotion"
