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

#: An evidence count written as digits. The author's decision is that the
#: guide states none: the compatibility matrix generates them on every
#: docs build, and a number typed here goes stale on the next probe run.
#:
#: The first version of this pattern matched ``<digits> commands`` alone,
#: and the QA pass measured what that leaves through: re-inserting the
#: exact sentence this session DELETED for being stale
#: ("26.120 fully covered (65 verified, 74 documented, 3 broken, 2
#: removed)") matched nothing at all, so two of the three sites fixed
#: here could come back untouched. One spelling of the class was
#: removed, not the class. The vocabulary below is the one the guide
#: actually used, and PHRASES_THAT_WENT_STALE pins the pattern against
#: that history rather than against itself.
COMMAND_COUNT = re.compile(
    r"(?<![\w.])(\d+)\s+(commands?|verified|documented|broken|removed|entries)\b"
)

#: The sentences this session removed from the guide for having gone
#: stale, verbatim. The pattern above must match every one of them; a
#: pattern that does not is not guarding the class that actually
#: occurred. Kept as data rather than as prose so the claim is testable.
PHRASES_THAT_WENT_STALE = (
    "144 commands, one YAML file per manual chapter",
    "65 commands verified and 3 found broken on 26.120.",
    "Current evidence: 26.120 fully covered (65 verified, 74 documented, "
    "3 broken, 2 removed); 26.100 partially backfilled (37 documented, "
    "1 removed); 26.000 registered, honestly empty.",
)

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

#: A canonical version identifier, YY.XXX.
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


def test_the_pattern_matches_the_sentences_that_actually_went_stale():
    """Guard the guard, against history rather than against itself.

    A pattern asserted only over the current file is satisfied by the
    current file. These three sentences were really in the guide and
    were really removed for drifting, so a pattern that misses any of
    them is not guarding the class that occurred.
    """
    for phrase in PHRASES_THAT_WENT_STALE:
        assert COMMAND_COUNT.search(phrase), (
            f"the count pattern does not match {phrase!r}, a sentence this "
            "repository deleted for going stale. It could be restored today "
            "without turning anything red"
        )


def test_the_guide_states_no_evidence_count():
    found = COMMAND_COUNT.findall(guide_text())
    assert not found, (
        f"the guide states an evidence count ({found}). The author's decision of "
        "2026-08-03 is that it states none: the number changed three times in "
        "three days, and the compatibility matrix generates the current one on "
        "every docs build. Point at the matrix instead of typing a number that "
        "nothing regenerates"
    )


#: The package version the guide's title page states, in ``\institute``.
GUIDE_PACKAGE_VERSION = re.compile(r"\\institute\[\]\{pyflightstream ([0-9][^,}]*)")


def test_the_guide_states_the_package_version_it_ships_with():
    """The cover, which this guard did not look at and should have.

    The release checklist requires the guide's title version to move
    with `pyproject.toml`. It did not: the tree reached 0.4.0 with the
    cover still reading 0.3.0, and every check in this file passed,
    because they all guard FlightStream versions and evidence counts.
    A guard written to stop the guide going stale watched this exact
    staleness and said nothing.
    """
    import tomllib

    # pyproject, not `pyflightstream.__version__`. The latter reads the
    # INSTALLED distribution's metadata, so in a development checkout it
    # reports whatever was last installed and would compare the guide
    # against a stale wheel rather than against this tree
    # (PLN-20260803-1650 records the same trap).
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]

    # The BASE version, so a development window does not demand that the
    # cover print "0.5.0.dev0". The cover names the release the guide is
    # being written for, and pyproject names the same release with a
    # development suffix while it is being built; comparing the base
    # keeps them moving together without putting a dev marker on a cover.
    from packaging.version import Version

    declared = Version(declared).base_version

    stated = GUIDE_PACKAGE_VERSION.search(guide_text())
    assert stated is not None, (
        "the guide's title page no longer states a package version in "
        r"\institute, so this guard has nothing to read. Restore it or delete "
        "this test rather than leaving it green over an absent claim"
    )
    assert stated.group(1) == declared, (
        f"the guide's cover says pyflightstream {stated.group(1)} and pyproject "
        f"declares {declared}. The cover is the first thing a reader sees, and the "
        "release checklist moves it in the same commit as pyproject.toml and "
        "CITATION.cff"
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


#: The two blocks that enumerate the registered versions, located by
#: their own content. Searching the whole document instead was measured
#: to be worthless for this class: the QA pass deleted the tikz node for
#: 26.121 and the check stayed green, because the identifier still
#: appeared in eleven other places. The staleness this guard exists for
#: is precisely a listing and a diagram DISAGREEING, so each has to be
#: asserted on its own.
DIAGRAM = re.compile(
    r"\\begin\{tikzpicture\}(?:(?!\\end\{tikzpicture\}).)*?26\.000.*?\\end\{tikzpicture\}",
    re.DOTALL,
)
LISTING = re.compile(
    r"\\begin\{lstlisting\}(?:(?!\\end\{lstlisting\}).)*?known_versions.*?\\end\{lstlisting\}",
    re.DOTALL,
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


def test_the_version_diagram_and_the_version_listing_each_carry_every_version():
    """The two blocks that must agree, asserted separately.

    Whole-document membership cannot see them disagree, which is the
    only failure this class has ever had.
    """
    text = guide_text()
    canonicals = [version.canonical for version in known_versions()]
    for label, pattern in (("version diagram", DIAGRAM), ("version listing", LISTING)):
        block = pattern.search(text)
        assert block is not None, (
            f"the {label} was not found in the guide, so this guard read nothing. "
            f"If it was restructured, update the pattern; a guard that stops "
            f"matching reports green over an unread file"
        )
        body = block.group(0)
        missing = [canonical for canonical in canonicals if canonical not in body]
        assert not missing, (
            f"the {label} omits {missing}. The library registers "
            f"{canonicals}, and this is exactly how the guide went stale when "
            f"26.121 landed: the listing printed four and the diagram drew three"
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
    broken_count = sum(
        1
        for entry in registry.commands.values()
        if any(record.status is Status.BROKEN for record in entry.versions.values())
    )
    rows = [row for row in body.group(1).split(r"\\") if row.strip()]
    # EQUAL, not a floor. `>= 3` was satisfied at exactly 3 while the row
    # this guard was written for had been deleted, which the QA pass
    # demonstrated. One row per broken command, no more and no fewer.
    assert len(rows) == broken_count, (
        f"the pitfall table has {len(rows)} row(s) and the database records "
        f"{broken_count} command(s) broken on at least one build. The table is a "
        f"rendering of that set, so the two counts are one claim"
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

        # WHAT THE EMITTER REFUSES, which follows inheritance, together
        # with which of those answers was probed on the build itself.
        # This guard used to read the entry's own rows only, on the
        # reasoning that status_in falls back from a hotfix to its base
        # and would certify a claim the database does not hold
        # (PLN-20260802-2016). That concern is real and is met by the
        # asterisk rather than by narrowing the set: the column tells a
        # reader which builds the builder will refuse the command on, so
        # omitting an inherited build makes the column wrong in the
        # direction that costs a caller a run. Registering 26.122 on
        # 2026-08-10 made the difference visible, three of the four rows
        # gaining a build nobody has probed.
        measured, inherited = set(), set()
        for version in known_versions():
            evidence = entry.evidence_in(version)
            if evidence is None or evidence.record.status is not Status.BROKEN:
                continue
            measured.add(version.canonical)
            if evidence.inherited:
                inherited.add(version.canonical)
        cell = builds.strip()
        starred = {
            token for token in CANONICAL.findall(cell.replace("*", "* ")) if f"{token}*" in cell
        }
        cell_versions = cell.replace("*", "")
        # THE "both" AFFORDANCE IS GONE. It resolved the word against a
        # second computation of the broken set, and when this guard
        # moved to reachability that second computation moved with it,
        # leaving the branch asserting measured == measured. No cell in
        # the guide says "both", so removing the affordance costs
        # nothing and one fewer thing can be tautological; a cell that
        # says it now fails on naming no version this can read.
        declared = set(CANONICAL.findall(cell_versions))
        assert declared, (
            f"the pitfall table's Builds cell for {name} reads {cell!r}, which "
            "names no version this guard can read. Write canonical identifiers"
        )
        assert declared == measured, (
            f"the guide says {name} is broken on {sorted(declared)} and the "
            f"builder refuses it on {sorted(measured)}. A reader avoids "
            f"a command on a build where it works, or uses one on a build where "
            f"it aborts"
        )
        assert starred == inherited, (
            f"the guide marks {sorted(starred)} as inherited for {name} and the "
            f"database inherits {sorted(inherited)}. The asterisk is what keeps "
            f"the column honest: a build listed without one reads as a build "
            f"somebody watched the command fail on"
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

    # The FINDING cell only, never the whole row. Reading all three
    # columns was measured to be satisfied by an incidental mention: the
    # QA pass deleted the SWEEPER_REF_VELOCITY_SAME row, named it in a
    # neighbouring row's advice cell, and this check stayed green. The
    # advice column names the command you should use INSTEAD, so it is
    # the one column that must not count as coverage.
    listed = set()
    for row in body.group(1).split(r"\\"):
        if not row.strip():
            continue
        finding = row.split("&")[0]
        listed |= {match.replace("\\_", "_") for match in COMMAND_IN_TEX.findall(finding)}

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
    spurious = sorted(listed - broken)
    assert not spurious, (
        f"the pitfall table has a Finding row for {spurious}, which the database "
        f"records broken nowhere. A row that outlived its evidence tells a reader "
        f"to avoid a command that works"
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
