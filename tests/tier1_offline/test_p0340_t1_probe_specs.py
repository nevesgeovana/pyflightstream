"""Tier 1: every command the package emits has a probe specification, for tier 2 (FR-342).

Marker P0340-T1-PROBE-SPECS, arm RG of GOAL-039, package QA-SPECS (PFS-2073.06). The census of R1
is read from the byte-identity goldens of the workflows (``tests/tier1_offline/goldens/workflows``):
every command a golden renders, on the build the golden is rendered for, that the build's database
holds. Counted when the package started, six commands had no catalog entry: ROTATE_SURFACE,
SURFACE_ROTATE, SONIC_VELOCITY, SET_MOTION_ANGULAR_VELOCITY, SET_MOTION_IS_ROTOR and
SET_NEW_UNSTEADY_SOLVER_ACTION. SONIC_VELOCITY is in no build's database view, so no probe could
run it and the census leaves it out; the other five carry entries, two of them on 26.124. The
tier-2 verdicts are the session's (RPT-127); each recorded status must follow the run's report.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest

from pyflightstream.commands import CommandRegistry
from pyflightstream.qa import specs
from pyflightstream.versions import known_versions
from tests.tier1_offline._p0340_probe_support import (
    RUN_LABEL_T1,
    build_script,
    run_report,
    status_on,
    target_line,
    verdict_mismatches,
    verdicts_of,
)

GOLDENS = Path(__file__).resolve().parent / "goldens" / "workflows"
#: The three commands the census found and covered, each with the builds that hold it.
CENSUS = {
    "ROTATE_SURFACE": ("26.122", "26.123", "26.124"),
    "SURFACE_ROTATE": ("25.000", "25.100", "26.000", "26.100", "26.101", "26.120", "26.121"),
    "SET_NEW_UNSTEADY_SOLVER_ACTION": ("26.122", "26.123", "26.124"),
}
ON_26124 = ("ROTATE_SURFACE", "SET_NEW_UNSTEADY_SOLVER_ACTION")
#: Rendered by the goldens of builds before 26.101, held by no database view of 26.120 or later
#: (SONIC_VELOCITY by none at all), so no authorised run can judge them and they carry no entry.
UNREACHABLE = ("SET_MOTION_ANGULAR_VELOCITY", "SET_MOTION_IS_ROTOR", "SONIC_VELOCITY")


def emitted_by_the_goldens() -> dict[str, set[str]]:
    """Return {build: commands the workflow goldens render for it that its database holds}."""
    registry = CommandRegistry.load()
    views = {v.canonical: registry.for_version(v) for v in known_versions()}
    found: dict[str, set[str]] = {}
    for path in sorted(GOLDENS.glob("*__*__*.txt")):
        build = path.stem.rsplit("__", 1)[-1]
        if build not in views:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            word = line.split(" ")[0]
            if word in views[build]:
                found.setdefault(build, set()).add(word)
    return found


def unspecified(
    emitted: Mapping[str, Iterable[str]], catalog: Iterable[str]
) -> dict[str, set[str]]:
    """Return {command: builds} for every emitted command the catalog has no entry for."""
    have = set(catalog)
    missing: dict[str, set[str]] = {}
    for build, commands in emitted.items():
        for command in commands:
            if command not in have:
                missing.setdefault(command, set()).add(build)
    return missing


def test_the_census_finds_no_emitted_command_without_an_entry_fr_342():
    """FR-342 R1 and R2, marker P0340-T1-PROBE-SPECS: the goldens render nothing the catalog lacks.

    The three commands of the builds no authorised run reaches are the only ones left, named.
    """
    missing = unspecified(emitted_by_the_goldens(), specs.PROBE_SPECS)
    assert set(missing) == set(UNREACHABLE), missing


def test_the_census_counts_the_commands_it_found_when_the_package_started_fr_342():
    """FR-342 R1, marker P0340-T1-PROBE-SPECS: three commands, in the builds the goldens name."""
    emitted = emitted_by_the_goldens()
    for command, builds in CENSUS.items():
        assert command in specs.PROBE_SPECS
        assert {b for b, names in emitted.items() if command in names} <= set(builds), command
    assert {c for c, builds in CENSUS.items() if "26.124" in builds} == set(ON_26124)


def test_a_planted_command_without_an_entry_is_refused_by_the_census_fr_342():
    """FR-342 R2, marker P0340-T1-PROBE-SPECS: the control of the census test."""
    planted = {"26.124": {"ROTATE_SURFACE", "PYFS_PLANTED_COMMAND"}}
    assert unspecified(planted, specs.PROBE_SPECS) == {"PYFS_PLANTED_COMMAND": {"26.124"}}


@pytest.mark.parametrize(
    ("command", "build"), [(c, b) for c, builds in CENSUS.items() for b in builds]
)
def test_each_entry_builds_for_every_build_that_holds_its_command_fr_342(command, build):
    """FR-342 R2, marker P0340-T1-PROBE-SPECS: the script emits the command on that build."""
    assert target_line(command, build).startswith(command)
    assert f"PYFS_PROBE_END_{command}" in build_script(command, build)


def test_the_unsteady_action_probe_registers_a_script_that_prints_a_marker_fr_342():
    """FR-342 R2, marker P0340-T1-PROBE-SPECS: the action is observed through the log it writes."""
    script = build_script("SET_NEW_UNSTEADY_SOLVER_ACTION")
    assert "SET_NEW_UNSTEADY_SOLVER_ACTION SCRIPT PYFS_ACTION" in script
    assert script.index("SET_NEW_UNSTEADY_SOLVER_ACTION") < script.index("INITIALIZE_SOLVER")
    end = script.index("PYFS_PROBE_END_SET_NEW_UNSTEADY_SOLVER_ACTION")
    assert script.index("START_SOLVER") > end


def test_the_rotation_probe_changes_the_saved_mesh_not_a_placeholder_fr_342():
    """FR-342 R2, marker P0340-T1-PROBE-SPECS: the rotation is judged on the saved simulation."""
    for command in ("ROTATE_SURFACE", "SURFACE_ROTATE"):
        assert specs.PROBE_SPECS[command].save_state


def test_each_status_equals_the_verdict_the_tier_2_report_records_fr_342():
    """FR-342 R3, marker P0340-T1-PROBE-SPECS: the database follows the report of the native run.

    Until ``CMP-26124_<date>_t1-probe.yaml`` is committed the two commands of 26.124 keep the
    status they had; afterwards each status equals the verdict its line records.
    """
    statuses = {name: status_on(name) for name in ON_26124}
    report = run_report(RUN_LABEL_T1)
    if report is None:
        assert set(statuses.values()) == {"documented"}
        return
    assert verdict_mismatches(verdicts_of(report), statuses, ON_26124) == []


def test_a_planted_mismatch_is_found_for_the_tier_2_report_fr_342():
    """FR-342 R3, marker P0340-T1-PROBE-SPECS: the control of the status check."""
    report = {"ROTATE_SURFACE": {"outcome": "verified"}}
    assert verdict_mismatches(report, {"ROTATE_SURFACE": "documented"}, ["ROTATE_SURFACE"])
    assert not verdict_mismatches(report, {"ROTATE_SURFACE": "verified"}, ["ROTATE_SURFACE"])
