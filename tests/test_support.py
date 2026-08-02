"""Tier 1: per-version support levels, derived and reported (FR-49).

REV-002 finding PYFS-019. Every registered version was called supported
by every public surface, and the four states hiding under that word are
far apart: 26.000 constructs a `Script`, is accepted by a campaign, and
carries evidence for zero of the 145 commands. The README said so in a
sentence. Nothing said it in a value.
"""

import re
from pathlib import Path

import pytest

import pyflightstream
from pyflightstream.commands import (
    CommandEntry,
    CommandNotInVersionError,
    CommandRegistry,
    Status,
)
from pyflightstream.support import (
    MINIMAL_WORKFLOW_COMMANDS,
    SUPPORT_LADDER,
    SupportLevel,
    minimal_workflow,
    support_table,
    version_support,
)
from pyflightstream.versions import known_versions

REPO = Path(__file__).resolve().parents[1]


def test_the_levels_are_a_closed_named_set_in_ascending_order():
    """The taxonomy itself, which is half of what the finding asked for.

    A fifth level, or a reordering of the four, changes what every
    published claim means, so neither happens silently.
    """
    assert [level.value for level in SupportLevel] == [
        "registered",
        "documented",
        "verified",
        "operational",
    ]
    assert SUPPORT_LADDER == tuple(SupportLevel), (
        "SUPPORT_LADDER and the enum's declaration order have diverged, so the "
        "ladder no longer describes the enum it orders"
    )


def test_a_version_with_no_evidence_is_reported_registered_and_not_supported():
    """The finding, stated as its own assertion.

    26.000 is the case: registered, ordered, accepted by `Script`, and
    carrying evidence for nothing. The level has to say so out loud.
    """
    row = version_support("26.000")
    assert row.level is SupportLevel.REGISTERED
    assert row.commands_available == 0
    assert row.commands_probed == 0
    assert "nothing can be built" in row.summary
    # The control, so a mutation reporting REGISTERED for everything
    # cannot pass: a version that IS usable must not be registered.
    assert version_support("26.120").level is not SupportLevel.REGISTERED


def test_every_registered_version_has_exactly_one_level():
    """Total, so no version falls through the ladder into nothing."""
    rows = support_table()
    assert len(rows) == len(known_versions())
    assert [row.canonical for row in rows] == [v.canonical for v in known_versions()]
    for row in rows:
        assert row.level in SUPPORT_LADDER


def test_the_level_is_derived_from_the_database_and_not_declared():
    """Recompute each level from the raw statuses and compare.

    The point is that nothing hand-sets a level. This test derives the
    same answer by a different route, so a level that ever stops
    following the evidence disagrees with it.
    """
    registry = CommandRegistry.load()
    for version in known_versions():
        records = [entry.status_in(version) for entry in registry.commands.values()]
        live = [r for r in records if r is not None and r.status is not Status.REMOVED]
        probed = [r for r in live if r.status in (Status.VERIFIED, Status.BROKEN)]
        row = version_support(version)
        assert row.commands_available == len(live), version.canonical
        assert row.commands_probed == len(probed), version.canonical
        if not live:
            expected = SupportLevel.REGISTERED
        elif not probed:
            expected = SupportLevel.DOCUMENTED
        elif row.workflow_missing:
            expected = SupportLevel.VERIFIED
        else:
            expected = SupportLevel.OPERATIONAL
        assert row.level is expected, version.canonical


@pytest.mark.parametrize(
    "canonical",
    [row.canonical for row in support_table() if row.level is SupportLevel.OPERATIONAL],
)
def test_every_operational_version_builds_the_minimal_workflow(canonical):
    """The second half of the assertion PYFS-019 owes.

    `operational` is the only level that claims a user can get from
    geometry to a loads file, so the claim is checked by doing it: the
    workflow builds, and it emits every command it declares.
    """
    script = minimal_workflow(canonical)
    lines = script.render()
    for command in MINIMAL_WORKFLOW_COMMANDS:
        assert re.search(rf"^{command}\b", lines, re.MULTILINE), (
            f"{canonical} is reported operational but the minimal workflow never emitted {command}"
        )
    # No waiver was needed, so the reference workflow leans on no
    # command a probe measured broken (FR-48).
    assert script.broken_commands == ()


def test_there_is_at_least_one_operational_version():
    """Guard the guard: the parametrization above can go empty.

    Derived from the database, so a promotion that emptied it would
    leave the workflow test reporting green over zero cases, which is
    how a guard stops guarding without failing.
    """
    operational = [
        row.canonical for row in support_table() if row.level is SupportLevel.OPERATIONAL
    ]
    assert operational, "no version is operational, so the workflow guard proves nothing"


def test_a_version_that_cannot_build_the_workflow_says_which_command_is_missing():
    """The refusal is the honest answer to "can I use this version?".

    26.000 has no commands at all, so the first link of the chain is
    where it stops, and the message names it.
    """
    with pytest.raises(CommandNotInVersionError, match="NEW_SIMULATION"):
        minimal_workflow("26.000")
    assert version_support("26.000").workflow_missing == MINIMAL_WORKFLOW_COMMANDS


def test_the_support_level_is_reachable_from_the_top_level_package():
    """ "Reported by the public surface" means without knowing a module."""
    assert pyflightstream.support_level("26.000") is SupportLevel.REGISTERED
    for name in ("SupportLevel", "support_level", "support_table", "version_support"):
        assert name in pyflightstream.__all__
        assert hasattr(pyflightstream, name)


def test_the_readme_table_agrees_with_the_derived_levels():
    """NFR-11: the published claim and the computed fact are one fact.

    The README carries the table by hand, because a generated README is
    not what a visitor reads on the repository front page. This is what
    keeps it honest: every row must name the level the package derives,
    and every registered version must have a row.
    """
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Supported FlightStream versions", 1)[1].split("\n## ", 1)[0]
    for row in support_table():
        pattern = rf"\|\s*{re.escape(row.canonical)}\s*\|[^|]*\|\s*`{row.level.value}`\s*\|"
        assert re.search(pattern, section), (
            f"the README's supported-versions table does not show "
            f"{row.canonical} at level {row.level.value}, which is what "
            f"pyflightstream.support_table() derives today"
        )


def _registry_with(statuses):
    """Build a throwaway registry: {command: (canonical, status, report)}."""
    commands = {}
    for name, (canonical, status, report) in statuses.items():
        record = {"status": status}
        if report is not None:
            record["report"] = report
        commands[name] = CommandEntry(
            name=name,
            chapter="fixture",
            layout="bare",
            phase="control",
            args=[],
            manual_ref="SRC-003 p.281",
            versions={canonical: record},
        )
    return CommandRegistry(commands=commands)


def test_probe_evidence_without_a_working_workflow_is_verified_not_operational():
    """The rung no registered version stands on today.

    Measured, not assumed: a mutation that collapsed `verified` into
    `operational` passed every other test in this file, because the
    branch is unreachable on the live database. Every version there is
    either at zero commands, at zero probes, or complete. A level whose
    only guard is data that happens not to exercise it is not guarded,
    so this reaches it with a registry built for the purpose.

    The state is not hypothetical: it is what the next version looks
    like on the day its first probe run lands, before its command
    coverage catches up.
    """
    registry = _registry_with(
        {
            "PRINT": ("26.100", "verified", "reports/compat/CMP-fixture.yaml"),
            "STOP": ("26.100", "documented", None),
        }
    )
    row = version_support("26.100", registry=registry)
    assert row.level is SupportLevel.VERIFIED
    assert row.commands_available == 2
    assert row.commands_probed == 1
    assert row.workflow_missing == MINIMAL_WORKFLOW_COMMANDS
    assert "does not build" in row.summary
    assert "NEW_SIMULATION" in row.summary
    # The control on the same registry shape: add nothing probed and the
    # level drops a rung, so this is not just "any fixture is verified".
    documented_only = _registry_with({"STOP": ("26.100", "documented", None)})
    assert version_support("26.100", registry=documented_only).level is SupportLevel.DOCUMENTED


def test_a_broken_record_still_counts_as_a_measurement():
    """`broken` is probe evidence: somebody ran it and watched it fail.

    Counting only `verified` would report a version as documented while
    a licensed machine had already measured half of it, which is the
    opposite of what the level is for.
    """
    registry = _registry_with({"PRINT": ("26.100", "broken", "reports/compat/CMP-fixture.yaml")})
    row = version_support("26.100", registry=registry)
    assert row.commands_probed == 1
    assert row.level is SupportLevel.VERIFIED
