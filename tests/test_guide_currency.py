"""Tier 1: the user guide's claims about versions and evidence are current.

Pipeline role: quality gate on the didactic material, beside
``test_guide_api_names.py``. That guard checks the NAMES the guide
teaches; this one checks the FACTS it states. They are different failure
classes and the second had no guard at all: the guide is not built or
executed by CI, so every claim in it was true only until the next
licensed session moved the evidence underneath it.

Scope, and it is deliberately narrow. Four classes went stale between
the 26.120 and 26.121 onboarding, and each has a check here:

* a count restated by hand ("144 commands") drifted twice in three days,
  once in the guide and once in the plan item recording the drift. The
  author's decision of 2026-08-03 is that the guide states no command
  counts at all and points at the generated compatibility matrix, so the
  check is that no such count comes back. The class is removed rather
  than guarded, and this test keeps it removed;
* the registered version list and its diagram ended at 26.120 while the
  library had four versions;
* a pinned error transcript listed two recorded versions where the
  library now prints three. Nothing compared the two, so the guide
  taught a message the library does not emit;
* the pitfall table said three commands are broken without saying on
  which build, which stopped being true the moment one of them was fixed
  by a vendor hotfix and another was found broken only on that hotfix.

What this does NOT check: prose. A sentence that describes solver
behaviour wrongly passes here. The guard is on the machine-checkable
claims, which is what mechanically went stale.
"""

import re
from pathlib import Path

import pytest

from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.script import Script, helpers
from pyflightstream.versions import known_versions

GUIDE = Path(__file__).parents[1] / "guide" / "pyflightstream_user_guide.tex"

#: A command count written as digits. The author's decision is that the
#: guide states none: the compatibility matrix generates them on every
#: docs build, and a number typed here goes stale on the next probe run.
COMMAND_COUNT = re.compile(r"(?<![\w.])(\d+)\s+commands\b")

#: ``N curated helpers``, in digits or as an English word. This count
#: stays in the guide because it is a fact about the module rather than
#: about evidence, so it moves only when the API moves, and then this
#: test moves with it.
HELPER_COUNT = re.compile(r"\b([A-Za-z]+|\d+)\s+curated helpers\b")

#: A pinned interpreter transcript: the call, then everything the guide
#: claims the library prints, up to the end of the listing.
TRANSCRIPT = re.compile(
    r'>>> Script\(version="([^"]+)"\)\.emit\("([^"]+)"\)\n(.*?)\n\\end\{lstlisting\}',
    re.DOTALL,
)

#: The pitfall table's body, located by its header row so that adding an
#: unrelated table to the guide cannot silently become the subject.
PITFALL_TABLE = re.compile(
    r"Finding\s*&\s*Builds\s*&\s*Practical rule\s*\\\\\s*\\midrule(.*?)\\bottomrule",
    re.DOTALL,
)

#: A FlightStream command name as the guide escapes it for LaTeX.
COMMAND_IN_TEX = re.compile(r"\b[A-Z][A-Z0-9]*(?:\\_[A-Z0-9]+)+\b")

#: A canonical version identifier, 26.XXX.
CANONICAL = re.compile(r"\b\d\d\.\d\d\d\b")

WORD_NUMBERS = {
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


def guide_text() -> str:
    assert GUIDE.is_file(), f"the user guide is not at {GUIDE}; update this guard's path"
    return GUIDE.read_text(encoding="utf-8")


def curated_helper_count() -> int:
    """How many helper functions the helpers module actually defines.

    Counted by definition site rather than by ``dir()``: the module
    imports ``Script``, ``Mapping`` and several exception types, and
    counting those would make the guide's number wrong in the direction
    that looks right.
    """
    import inspect

    return sum(
        1
        for name, value in vars(helpers).items()
        if not name.startswith("_")
        and inspect.isfunction(value)
        and value.__module__ == helpers.__name__
    )


def test_the_guide_states_no_command_count():
    found = COMMAND_COUNT.findall(guide_text())
    assert not found, (
        f"the guide states a command count ({found}). The author's decision of "
        "2026-08-03 is that it states none: the number changed three times in "
        "three days, and the compatibility matrix generates the current one on "
        "every docs build. Point at the matrix instead of typing a number that "
        "nothing regenerates"
    )


def test_the_helper_count_the_guide_states_matches_the_module():
    actual = curated_helper_count()
    stated = HELPER_COUNT.findall(guide_text())
    assert stated, (
        "the guide no longer says how many curated helpers there are, so this "
        "guard has nothing to check. Either restore the phrase or delete this "
        "test; leaving it green over an absent claim is the failure mode the "
        "floor tests in this repository exist to prevent"
    )
    for token in stated:
        value = WORD_NUMBERS.get(token.lower(), None)
        if value is None:
            assert token.isdigit(), (
                f"the guide says {token!r} curated helpers, which this guard "
                f"cannot read as a number. Write the digit, or add the word to "
                f"WORD_NUMBERS"
            )
            value = int(token)
        assert value == actual, (
            f"the guide says {token} curated helpers and the module defines "
            f"{actual}. A reader counting the tour against the module finds the "
            f"guide wrong about the section it is introducing"
        )


def test_every_registered_version_appears_in_the_guide():
    text = guide_text()
    missing = [str(v) for v in known_versions() if v.canonical not in text]
    assert not missing, (
        f"the guide never mentions {missing}, which the library registers. The "
        f"version list and its diagram went stale exactly this way when 26.121 "
        f"landed: the listing printed four versions and the diagram beside it "
        f"drew three"
    )


def test_every_pinned_refusal_matches_what_the_library_says():
    found = TRANSCRIPT.findall(guide_text())
    assert found, (
        "no pinned transcript was found in the guide, so this guard read "
        "nothing. If the guide dropped its transcripts, drop this test; do not "
        "leave it passing over material it cannot see"
    )
    for version, command, claimed in found:
        with pytest.raises(Exception) as raised:  # noqa: PT011, B017
            Script(version=version).emit(command)
        real = f"{type(raised.value).__name__}: {raised.value}"
        assert " ".join(claimed.split()) == " ".join(real.split()), (
            f"the guide pins this transcript for "
            f'Script(version="{version}").emit("{command}"):\n\n'
            f"  {' '.join(claimed.split())}\n\n"
            f"and the library prints:\n\n  {real}\n\n"
            f"A reader who runs the sample sees a different message from the "
            f"one the guide taught them to expect, and the difference is "
            f"usually the evidence that moved underneath it"
        )


def test_the_pitfall_table_names_the_builds_the_database_calls_broken():
    body = PITFALL_TABLE.search(guide_text())
    assert body is not None, (
        "the pitfall table's header row was not found, so this guard checked "
        "no rows. If the table was restructured, update PITFALL_TABLE; a guard "
        "that stops matching reports green over an unread file"
    )
    registry = CommandRegistry.load()
    rows = [row for row in body.group(1).split(r"\\") if row.strip()]
    assert len(rows) >= 3, (
        f"the pitfall table parsed as {len(rows)} row(s), which is too few to be it"
    )

    for row in rows:
        cells = row.split("&")
        assert len(cells) == 3, f"the pitfall row {row.strip()!r} did not split into three cells"
        finding, builds, _rule = cells
        name_match = COMMAND_IN_TEX.search(finding)
        assert name_match is not None, f"no command name in the pitfall row {finding.strip()!r}"
        name = name_match.group(0).replace("\\_", "_")
        entry = registry.commands.get(name)
        assert entry is not None, f"the pitfall table names {name}, which is not in the database"

        # Read the entry's OWN records, never status_in: that accessor
        # falls back from a hotfix build to its base release, so a
        # command recorded broken on 26.120 alone would answer "broken"
        # for 26.121 too and this guard would certify a claim the
        # database does not hold (PLN-20260802-2016).
        measured = {
            canonical
            for canonical, record in entry.versions.items()
            if record.status is Status.BROKEN
        }
        cell = builds.strip()
        declared = set(entry.versions) if cell == "both" else set(CANONICAL.findall(cell))
        assert declared, (
            f"the pitfall table's Builds cell for {name} reads {cell!r}, which "
            f"names no version this guard can read. Write canonical "
            f"identifiers, or the word 'both'"
        )
        assert declared == measured, (
            f"the guide says {name} is broken on {sorted(declared)} and the "
            f"database records it broken on {sorted(measured)}. A reader avoids "
            f"a command on a build where it works, or uses one on a build where "
            f"it aborts"
        )


def test_every_broken_command_has_a_pitfall_row():
    """The table is complete, not merely correct about the rows it has.

    The row check above reads the rows that are present, so a MISSING
    row is invisible to it, and a missing row is exactly what happened:
    SWEEPER_REF_VELOCITY_SAME was probed broken on 26.121 and the table
    went on listing three findings. A reader consulting the pitfalls page
    concluded the command was fine.
    """
    body = PITFALL_TABLE.search(guide_text())
    assert body is not None, "the pitfall table's header row was not found"
    listed = {match.replace("\\_", "_") for match in COMMAND_IN_TEX.findall(body.group(1))}

    registry = CommandRegistry.load()
    broken = {
        name
        for name, entry in registry.commands.items()
        if any(record.status is Status.BROKEN for record in entry.versions.values())
    }
    missing = sorted(broken - listed)
    assert not missing, (
        f"the database records {missing} broken on at least one registered "
        f"build and the guide's pitfall table does not list them. The table is "
        f"where a reader looks before trusting a command, so a probe that "
        f"promotes something to broken is not finished until the row exists"
    )


def test_the_patterns_still_find_the_material():
    # Floors, so that none of the checks above can pass by matching
    # nothing. Every guard in this file is a search over a file that is
    # never executed, so a pattern that quietly stopped matching would
    # be indistinguishable from a guide with nothing wrong in it.
    text = guide_text()
    assert len(CANONICAL.findall(text)) >= 20
    assert len(COMMAND_IN_TEX.findall(text)) >= 20
    assert len(TRANSCRIPT.findall(text)) >= 1
    assert PITFALL_TABLE.search(text) is not None
