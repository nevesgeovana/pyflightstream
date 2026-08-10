"""Tier 1: the per-build census, pinned so a silent loss of rows fails.

The database's evidence rows are checked one at a time everywhere else:
a citation exists, a status matches its report, an override differs from
its base. Nothing checked the TOTAL, and the total is what the release
notes, the SRS and the support levels all quote.

That gap has a shape. 122 version rows were written in one pass during
v0.5.0 from manual pages that cannot be committed, so no test in this
repository can re-derive them; a later edit deleting a chapter's worth
would leave every per-row guard green while the emitter quietly began
refusing commands the caller's own manual documents, which is the exact
failure those rows were written to end. A census cannot tell a right row
from a wrong one, but it can tell 345 from 305, and the drop is the
thing that goes unnoticed.
"""

import pytest

from pyflightstream.commands import CommandNotInVersionError, CommandRegistry, Status
from pyflightstream.support import SupportLevel, support_table
from pyflightstream.versions import known_versions

#: Measured 2026-08-08 on the v0.5.0 tree. Emittable means the version
#: view returns the entry: present with recorded evidence, of any status
#: except `removed`, hotfix inheritance honoured.
EMITTABLE = {
    "25.000": 241,
    "25.100": 256,
    "26.000": 262,
    "26.100": 345,
    "26.101": 363,
    "26.120": 363,
    "26.121": 368,
}

#: Rows recording `verified` per build, measured the same day. Pinned
#: beside the emittable counts because the release notes quote a
#: TRANSITION in this figure ("from 66 verified to 84") and nothing
#: checked either endpoint: the shipped sentence said 67, which is not
#: what the full run of that day recorded, and the arithmetic then did
#: not close against its own two compat reports.
VERIFIED = {
    "25.000": 0,
    "25.100": 0,
    "26.000": 0,
    "26.100": 13,
    "26.101": 35,
    "26.120": 66,
    "26.121": 84,
}

ENTRIES = 388


def _emittable(canonical: str) -> int:
    registry = CommandRegistry.load()
    version = next(v for v in known_versions() if v.canonical == canonical)
    view = registry.for_version(version)
    total = 0
    for name in registry.commands:
        try:
            view[name]
        except CommandNotInVersionError:
            continue
        total += 1
    return total


def test_the_database_holds_every_command_the_registered_editions_document():
    """388, the figure the release notes and the SRS both quote."""
    assert len(CommandRegistry.load().commands) == ENTRIES, (
        "the entry count moved. If a chapter was added the figure rises and this "
        "line moves with it; if it FELL, a chapter file stopped loading and every "
        "per-entry guard is still green"
    )


@pytest.mark.parametrize("canonical", sorted(EMITTABLE))
def test_each_build_emits_the_number_of_commands_it_did_at_release(canonical):
    """A per-build count, because a loss is never spread evenly.

    The 122 backfilled pairs were concentrated: forty on the February
    build alone. A deletion would be concentrated the same way, and a
    single total across all builds would absorb it.
    """
    assert _emittable(canonical) == EMITTABLE[canonical], (
        f"{canonical} emits a different number of commands than it did at v0.5.0. A "
        "RISE is new evidence and this table moves with it. A FALL means rows were "
        "lost, and the manual pages they were read from are not committed, so "
        "nothing in this repository can put them back"
    )


def test_the_february_build_is_not_quietly_behind_its_successors_again():
    """26.100 reached `operational` by gaining rows, not by anything solver-side.

    It sat at `verified` for most of this database's life because forty
    of its rows were missing, and the level is derived, so the shortfall
    read as a property of the build. Deleting those rows would put it
    back without touching a single status.
    """
    levels = {row.canonical: row.level for row in support_table()}
    assert levels["26.100"] is SupportLevel.OPERATIONAL, (
        "26.100 is no longer operational. Check for lost version rows before "
        "reading this as a fact about the solver"
    )
    assert {levels[canonical] for canonical in ("26.100", "26.101", "26.120", "26.121")} == {
        SupportLevel.OPERATIONAL
    }, "the four documented builds are all operational at v0.5.0"


@pytest.mark.parametrize("canonical", sorted(VERIFIED))
def test_each_build_records_the_verified_count_it_did_at_release(canonical):
    """The figure the release notes quote as a transition.

    `verified` is the only status a probe run can raise, so this count
    is what a licensed session moves and what the notes report moving.
    It was reported wrongly at this release, as 67 to 84 where the full
    run of that day recorded 66, and the error survived because the
    endpoints lived only in prose while the reports that produce them
    lived in `reports/compat/`.
    """
    registry = CommandRegistry.load()
    version = next(v for v in known_versions() if v.canonical == canonical)
    counted = sum(
        1
        for entry in registry.commands.values()
        if (evidence := entry.evidence_in(version)) is not None
        and not evidence.inherited
        and evidence.record.status is Status.VERIFIED
    )
    assert counted == VERIFIED[canonical], (
        f"{canonical} records {counted} verified rows and this table says "
        f"{VERIFIED[canonical]}. A RISE is a licensed run and this table moves with "
        "it, citing the compat report; a FALL is evidence lost"
    )
