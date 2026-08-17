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

#: Measured 2026-08-08 on the v0.5.0 tree, and the three oldest builds
#: moved on 2026-08-10 when their own manual pages were read command by
#: command. Emittable means the version view returns the entry: present
#: with recorded evidence, of any status except `removed`, hotfix
#: inheritance honoured.
#:
#: The rise decomposes three times over, and stating the arithmetic is
#: the point of pinning the numbers: a rise that does not decompose into
#: named work is a rise nobody can account for. Reading the three
#: editions' own pages gave nineteen per-version grammar rows, +10, +5
#: and +4. Entering the sixteen commands only those editions document
#: gave +16, +8 and +7. And the row-level completeness measure found one
#: command missing its row on each of the three, +1 each: the coverage
#: sweep compares entry NAMES and cannot see an entry missing an
#: edition, so EXPORT_ALL_SURFACE_STREAMLINES read as covered while
#: three builds could not emit it.
EMITTABLE = {
    "25.000": 268,
    "25.100": 270,
    "26.000": 274,
    "26.100": 345,
    "26.101": 363,
    "26.120": 363,
    "26.121": 368,
    # Registered 2026-08-10. Ten entries of its own, six rows catching up
    # with what 26.121 added (inheritance runs from the base release, so
    # a sibling hotfix's rows do not reach here), and the rest inherited
    # from 26.120 less FOUR: the two commands this edition replaces, and
    # two that the preceding hotfix has a negative record for, which
    # inheritance from the base would otherwise have overturned.
    "26.122": 375,
    # Registered 2026-08-17 inheriting NOTHING, so it started at zero and
    # every one of these is a row somebody wrote or measured on THIS
    # build. That is the whole point of the flag: the other two hotfixes
    # entered this table already carrying most of 26.120's surface.
    #
    # 369 of the 371 its own edition documents, written the same day by
    # `pyfs-manual register`, which compares WHAT THE TWO EDITIONS SAY
    # about each command rather than which page they say it on. The two
    # it leaves are the work of their own nodes: SET_SCENE_CONTOUR,
    # which the edition describes differently, and
    # SET_OUTLET_TRAILING_EDGES, which it documents and this database
    # does not carry at all.
    #
    # IT WAS 368 FOR AN HOUR and the third exclusion was an artefact of
    # the reader rather than a fact about the edition.
    # DISABLE_WAKE_NODES_ON_TRAILING_EDGE is word for word what it was;
    # the new edition simply breaks the page in the middle of its block,
    # and the reader was page-local, so it compared a full record
    # against a truncation. The reader now reads the chapter as one
    # stream and the exclusion is gone.
    "26.123": 369,
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
    # It had zero of its own until 2026-08-11, deriving `operational`
    # from 26.120's records by hotfix inheritance, and the comment here
    # said a reader should be able to see that the first probe run had
    # not happened yet. It has now: CMP-26122_2026-08-11_full promoted
    # 84 statuses, 83 verified and one broken.
    #
    # And the run refuted the inheritance once, which is the argument
    # for measuring a hotfix rather than deriving it. AIR_ALTITUDE is
    # `broken` on 26.100, 26.101 and 26.120, where the solver reads its
    # METERS argument as feet, and this build reports the 5000 m
    # standard-atmosphere density correctly, so the inherited status was
    # PESSIMISTIC and the user guide was about to tell a reader to avoid
    # a command that works. The one broken row confirmed its
    # inheritance instead: NEW_OFF_BODY_STREAMLINE was already broken on
    # both older builds and crashes this one too (0xC0000005).
    "26.122": 83,
    # Measured 2026-08-17, the first probe run on this build, and the
    # figure to read it against is 26.122's 83: one MORE, and the one is
    # SET_INVISCID_LOADS, which was unprobed there. Nothing 26.122
    # verified is unverified here, so the newer build refuses nothing the
    # older one accepted (CMP-26123_2026-08-17_full-sim).
    "26.123": 84,
}

#: 388 at v0.5.0, then +16 on 2026-08-10 for the commands only the
#: pre-26.100 editions document and +10 the same day for the ones the
#: 26.122 edition is the first to document. The sixteen are absent from
#: every edition after the one that drops them, so none of them raises
#: the newest builds' counts by anything.
ENTRIES = 414


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
    """The figure the release notes and the SRS both quote."""
    assert len(CommandRegistry.load().commands) == ENTRIES, (
        "the entry count moved. If a chapter was added the figure rises and this "
        "line moves with it; if it FELL, a chapter file stopped loading and every "
        "per-entry guard is still green"
    )


def test_both_census_tables_cover_every_registered_build():
    """The tables are parametrized over their OWN keys, so a gap is silent.

    Every other guard in this file walks `sorted(EMITTABLE)` or
    `sorted(VERIFIED)`, which means a build registered without a row in
    either table passes all of them: there is simply one fewer case. The
    file's whole subject is a loss nothing notices, and its own coverage
    was the one loss it could not notice.

    Found by a skeptic reading this file during the 26.123 registration,
    not by the file failing. Both tables did gain their row that day; the
    point is that nothing would have said so.
    """
    registered = {version.canonical for version in known_versions()}
    for label, table in (("EMITTABLE", EMITTABLE), ("VERIFIED", VERIFIED)):
        missing = sorted(registered - set(table))
        extra = sorted(set(table) - registered)
        assert not missing, (
            f"{label} has no row for {', '.join(missing)}, which the ordering "
            "authority registers. Every guard here iterates this table's own keys, "
            "so the build is not merely unpinned, it is unwalked. Add the row with "
            "the measured number, and zero is a legitimate number for a build "
            "registered with inheritance off"
        )
        assert not extra, (
            f"{label} pins {', '.join(extra)}, which is not a registered build. "
            "Versions are only ever added, never dropped (CLAUDE.md invariant 4), "
            "so this is a typo in the table rather than a version that went away"
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
