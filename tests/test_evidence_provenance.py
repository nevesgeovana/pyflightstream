"""Tier 1: an inherited evidence record is never shown as a probed one.

Pipeline role: quality gate on what the command database CLAIMS, as
opposed to what it holds. A hotfix build inherits its base release's
record until a probe on the hotfix overrides it, which is the right
default: a hotfix that does not touch a command really does carry the
base evidence, and the alternative, every hotfix starting from nothing,
is worse.

The defect was that the inheritance was invisible. `status_in` returned
the base record with nothing saying it had, so the published
compatibility matrix showed 26.121 as fully covered while 76 of its 147
cells were assumptions carrying a citation to a report run on 26.120.
That mattered because a hotfix had ALREADY been measured changing a
command's behaviour: AIR_ALTITUDE is broken on 26.120 and verified on
26.121, so the assumption is known to be falsifiable
(PLN-20260802-2016).

What this guards, and the third one is the load-bearing one:

* `evidence_in` reports where a record came from;
* `status_in` and `evidence_in` never disagree, since a second lookup
  path is a second chance to drift;
* every inherited cell in the rendered matrix is MARKED, and every
  marked cell is really inherited. Prose in the matrix preamble would
  not have caught the 65-verified row that was measured before anything
  was promoted, which is why this is a test and not a paragraph.
"""

import importlib.util
import re
from pathlib import Path

import pytest

from pyflightstream.commands import CommandEntry, CommandRegistry
from pyflightstream.reference import markdown_compatibility_matrix
from pyflightstream.versions import UnknownVersionError, known_versions

MARK = "base</sup>"

REPO = Path(__file__).resolve().parents[1]
GOLDENS = REPO / "tests" / "goldens"


def _load_generator():
    """Load scripts/gen_absent_commands.py by path.

    By path rather than by putting ``scripts/`` on ``sys.path``: a
    permanently prepended directory shadows later imports for the rest of
    the session, which this workspace already has an incident about, and
    the module name here is generic enough to shadow something real.
    ``tests/test_extras.py`` loads ``scripts/chm_to_pdf.py`` the same way
    and states the same reason.
    """
    spec = importlib.util.spec_from_file_location(
        "gen_absent_commands_under_test", REPO / "scripts" / "gen_absent_commands.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inherited_pairs() -> set[tuple[str, str]]:
    """Every (command, version) whose evidence comes from the base release."""
    registry = CommandRegistry.load()
    return {
        (name, version.canonical)
        for name, entry in registry.commands.items()
        for version in known_versions()
        if (evidence := entry.evidence_in(version)) is not None and evidence.inherited
    }


def test_evidence_in_reports_where_the_record_came_from():
    registry = CommandRegistry.load()
    versions = {version.canonical: version for version in known_versions()}

    # Direct: the command holds its own record for that build.
    direct = registry.commands["AIR_ALTITUDE"].evidence_in(versions["26.121"])
    assert direct is not None
    assert direct.inherited is False
    assert direct.source == "26.121"
    assert direct.record.status.value == "verified"

    # The same command on the base release, also direct, and DIFFERENT.
    # This pair is the measured counter-example to hotfix inheritance, so
    # it is the right anchor for this test: if it ever stops differing,
    # the reason to distinguish the two lookups weakened.
    base = registry.commands["AIR_ALTITUDE"].evidence_in(versions["26.120"])
    assert base is not None
    assert base.inherited is False
    assert base.record.status.value == "broken"

    # Absent: no record anywhere in reach. The pair has now moved twice
    # in one day, and the second move is the more instructive. It went
    # first from 26.000, which by then carried evidence for nothing at
    # all, to AIR_ALTITUDE on 25.000, on the reading that the oldest
    # edition sets the altitude with a bare number and the units token
    # arrives later. Reading that page settled it the other way: the
    # edition DOES document the command, taking one argument instead of
    # two, so what looked like an absence was a grammar difference and
    # is recorded as one. An anchor for absence has to be a command the
    # edition does not carry at all, which is what this one is: the
    # trailing-edge autodetection arrives at 26.000.
    absent = registry.commands["AUTO_DETECT_TRAILING_EDGES"].evidence_in(versions["25.000"])
    assert absent is None


def test_an_inherited_record_names_the_version_it_came_from():
    registry = CommandRegistry.load()
    versions = {version.canonical: version for version in known_versions()}
    pairs = _inherited_pairs()
    assert pairs, (
        "no command inherits its evidence from a base release, so every "
        "assertion in this module is vacuous. If the database genuinely has no "
        "hotfix build left, delete this module rather than leaving it green "
        "over nothing."
    )
    name, canonical = sorted(pairs)[0]
    evidence = registry.commands[name].evidence_in(versions[canonical])
    assert evidence is not None
    assert evidence.inherited is True
    assert evidence.source != canonical
    assert evidence.source == canonical[:-1] + "0"


def test_status_in_and_evidence_in_never_disagree():
    """One lookup, two spellings. A second path is a second chance to drift."""
    registry = CommandRegistry.load()
    for entry in registry.commands.values():
        for version in known_versions():
            evidence = entry.evidence_in(version)
            record = entry.status_in(version)
            if evidence is None:
                assert record is None, f"{entry.name} at {version.canonical}"
            else:
                assert record is evidence.record, f"{entry.name} at {version.canonical}"


def test_the_matrix_marks_every_inherited_cell_and_only_those():
    """The guard the review asked for, stated over the RENDERED page.

    Measured against the registry rather than against a literal count,
    so a probe that promotes a command moves both sides together and
    this test keeps meaning the same thing.
    """
    versions = [version.canonical for version in known_versions()]
    inherited = _inherited_pairs()

    marked: set[tuple[str, str]] = set()
    seen_commands = 0
    for line in markdown_compatibility_matrix().splitlines():
        if not line.startswith("| ["):
            continue
        seen_commands += 1
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        name = cells[0].split("]", 1)[0].lstrip("[")
        for canonical, cell in zip(versions, cells[1:], strict=True):
            if MARK in cell:
                marked.add((name, canonical))

    assert seen_commands == len(CommandRegistry.load().commands), (
        f"the matrix parser read {seen_commands} command rows and the database "
        f"holds {len(CommandRegistry.load().commands)}. A parser that stopped "
        "matching would report a clean page it never read."
    )
    missing = sorted(inherited - marked)
    spurious = sorted(marked - inherited)
    assert not missing, (
        f"the matrix shows {len(missing)} inherited cell(s) as though the build "
        f"had been probed, for example {missing[:3]}. A reader takes an "
        "assumption for a measurement, which is the whole of PLN-20260802-2016."
    )
    assert not spurious, (
        f"the matrix marks {len(spurious)} cell(s) as inherited that the "
        f"database records directly, for example {spurious[:3]}. Marking a "
        "measurement as an assumption is the same defect pointing the other way."
    )


def test_no_surface_that_reaches_a_person_asks_the_weaker_question():
    """The class, closed at its cause rather than per surface.

    `status_in` cannot tell a probed record from an assumed one, and its
    own docstring says to prefer `evidence_in` wherever the answer
    reaches a person or a report. The v0.4.0 review found three
    consumers still asking the weaker question, and the sharpest was not
    a rendered page: `BrokenCommandUse.version` is written into the run
    manifest, read years later, and named the requested build while
    citing a report run on another one.

    This asserts the rule mechanically, over the source, so the next
    consumer added to a person-facing path cannot quietly use the weaker
    call. `VersionView.__getitem__` composes refusals, `_check_not_broken`
    composes a refusal and a manifest record, and `version_support`
    composes a sentence.
    """
    import re

    root = Path(__file__).parents[1] / "src" / "pyflightstream"
    person_facing = {
        "commands/__init__.py": "VersionView.__getitem__ composes user-facing refusals",
        "script/__init__.py": "BrokenCommandUse is written into the run manifest",
    }
    offenders = []
    for relative, why in person_facing.items():
        source = (root / relative).read_text(encoding="utf-8")
        for match in re.finditer(r"^.*\.status_in\(.*$", source, re.MULTILINE):
            line = match.group(0)
            if "def status_in" in line or "evidence_in" in line:
                continue
            lineno = source[: match.start()].count("\n") + 1
            offenders.append(f"{relative}:{lineno} ({why}): {line.strip()}")
    assert not offenders, (
        "these call sites reach a person or a permanent record and ask "
        "`status_in`, which cannot tell an inherited record from a probed one:\n  "
        + "\n  ".join(offenders)
        + "\n\nUse `evidence_in` and say `inherited` in what you compose."
    )


def _inheriting_broken_registry():
    """A two-key registry whose 26.121 answer is inherited and broken.

    Built rather than hunted for. The previous version of this test
    searched the live database for a command inheriting a broken record,
    found none, and skipped, so the field this release exists to fix had
    no executing assertion (`PLN-20260804-0400` item 5). Worse, it could
    not have passed if the skip had lifted: it called ``allow_broken``
    and then asserted ``broken_commands`` was non-empty, and a waiver
    that is never exercised deliberately records nothing.

    A record on 26.120 alone makes 26.121 inherit it, which is the whole
    hotfix rule, so the inherited case exists by construction and stays
    true whatever a probe later does to the real database.
    """
    entry = CommandEntry(
        name="SET_EXAMPLE_BROKEN",
        layout="inline",
        phase="setup",
        args=[{"name": "value", "type": "float", "unit": "m/s"}],
        manual_ref="SRC-003 p.328",
        versions={
            "26.120": {
                "status": "broken",
                "report": "reports/compat/CMP-26120_2026-07-23_pln012.yaml",
                "note": "the probe watched it abort",
            }
        },
    )
    return CommandRegistry(commands={"SET_EXAMPLE_BROKEN": entry})


def test_a_waived_broken_command_records_which_build_the_evidence_belongs_to():
    """The manifest field the architect pass found wrong.

    Written once and read years later, so it is the surface where an
    inherited record shown as a direct one does the most damage. The two
    keys must disagree here: ``version`` is the build the script targeted
    and ``source_version`` is the build whose record is broken, which is
    the build the cited report was run on.
    """
    from pyflightstream.script import Script

    registry = _inheriting_broken_registry()
    name = "SET_EXAMPLE_BROKEN"
    script = Script(version="26.121", registry=registry)
    script.allow_broken(name, reason="testing the provenance field")
    script.emit(name, 1.0)

    uses = [use for use in script.broken_commands if use.command == name]
    assert uses, "the waived emission recorded no BrokenCommandUse"
    use = uses[0]
    assert use.version == "26.121", "version holds the build the script targeted"
    assert use.source_version == "26.120", (
        "source_version holds the build whose record is broken, which is where "
        "the cited report was run"
    )
    assert use.source_version != use.version, "this fixture is the inherited case"
    # first_line had no assertion anywhere in the suite while the release
    # note promised it. It is the one field that is a property of the
    # EMISSION rather than of the command, so nothing else pins it.
    assert use.first_line == "SET_EXAMPLE_BROKEN 1.0", (
        f"first_line must hold the rendered line of the first waived emission, got "
        f"{use.first_line!r}"
    )


def test_a_direct_broken_record_reports_the_two_builds_as_equal():
    """The agreeing half, which no assertion reached.

    Its sibling above pins ``source_version`` only where it DIFFERS from
    ``version``, so a mutant returning ``version`` for both is caught and
    a mutant returning the record's source for both is not. This is the
    other input. Note the build: at 26.120 the inheritance rule
    ``canonical[:-1] + "0"`` is the identity, so a fixture there cannot
    tell the two apart either and would prove nothing. It has to be a
    hotfix build carrying its OWN record.
    """
    from pyflightstream.script import Script

    entry = CommandEntry(
        name="SET_EXAMPLE_DIRECT",
        layout="inline",
        phase="setup",
        args=[{"name": "value", "type": "float", "unit": "m/s"}],
        manual_ref="SRC-003 p.328",
        versions={
            "26.121": {
                "status": "broken",
                "report": "reports/compat/CMP-26121_2026-08-02_full.yaml",
                "note": "the probe watched it abort on this very build",
            }
        },
    )
    registry = CommandRegistry(commands={"SET_EXAMPLE_DIRECT": entry})
    script = Script(version="26.121", registry=registry)
    script.allow_broken("SET_EXAMPLE_DIRECT", reason="testing the agreeing case")
    script.emit("SET_EXAMPLE_DIRECT", 2.0)

    use = script.broken_commands[0]
    assert use.version == "26.121"
    assert use.source_version == "26.121", (
        "the record is this build's own, so the two keys agree; source_version is "
        "still a positive statement of where the evidence came from, not a null"
    )


def test_an_unexercised_waiver_records_nothing():
    """Control for the test above, and the contract it must not break.

    A recipe is version portable, so a waiver written for the build where
    a command is broken travels to the build where it is not. Recording
    it there would report a dependency the run does not have
    (``Script.__init__`` says so at the two dicts it keeps). Without this
    control, a mutation that recorded every waiver at registration time
    would leave the test above green.
    """
    from pyflightstream.script import Script

    registry = _inheriting_broken_registry()
    script = Script(version="26.121", registry=registry)
    script.allow_broken("SET_EXAMPLE_BROKEN", reason="registered and never used")
    assert script.broken_commands == (), (
        "a waiver that was never exercised must leave no trace in the manifest"
    )


def test_the_summary_counts_the_inherited_cells_it_renders():
    """The per-version summary and the cells below it are one claim."""
    inherited = _inherited_pairs()
    expected = {canonical: 0 for canonical in (v.canonical for v in known_versions())}
    for _name, canonical in inherited:
        expected[canonical] += 1

    rows = {}
    for line in markdown_compatibility_matrix().splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 9 and cells[0] in expected:
            rows[cells[0]] = int(cells[7])

    assert rows == expected, (
        f"the summary's 'Of which inherited' column says {rows} and the database "
        f"holds {expected}. The summary is the first thing a reader sees, so it "
        "cannot disagree with the cells under it."
    )


# --- inheritance is a fact about the two builds, not about the index --------


def test_a_hotfix_index_that_does_not_state_its_inheritance_is_refused():
    """The silent default is what was wrong, so silence is now an error.

    Until 2026-08-05 the last canonical digit decided inheritance on its
    own: nonzero meant hotfix, and a hotfix inherited. That held while
    the only hotfix was 26.121. The renumbering of 2026-08-04 put the
    February 2026 build at 26.100 and appended the May build as 26.101,
    and the rule then said the May release was a hotfix of the February
    one and carried its evidence. It is not, and it does not.

    A default cannot be right for both cases, so no default is offered:
    a hotfix index states the flag or the registry refuses to load.
    """
    from pyflightstream.versions import _inherits_base

    with pytest.raises(UnknownVersionError, match="states no inherits_base flag"):
        _inherits_base({"canonical": "26.121", "alias": "26.12"})
    # A base release has nothing to inherit from, so the flag is inert
    # there and its absence is not an error.
    assert _inherits_base({"canonical": "26.120", "alias": "26.12"}) is True
    assert _inherits_base({"canonical": "26.121", "inherits_base": False}) is False


def test_the_two_hotfix_indices_answer_differently_and_the_registry_says_why():
    """26.121 descends from 26.120; 26.101 only sits after 26.100."""
    by_canonical = {version.canonical: version for version in known_versions()}
    assert by_canonical["26.121"].inherits_base is True
    assert by_canonical["26.101"].inherits_base is False


def test_a_command_recorded_only_for_the_february_build_answers_for_no_other():
    """The emitter wrote these on a May script until 2026-08-05.

    RPT-018 measured the February flow-separation family recognised,
    reported deprecated and then refused by the 26.101 and 26.121
    solvers. The database records it for 26.100 alone; before the
    inheritance flag, 26.101 answered `documented` by falling back to
    26.100 and `Script(version="26.101")` emitted the line.
    """
    registry = CommandRegistry.load()
    entry = registry.commands["SET_AXIAL_SEPARATION_BOUNDARIES"]
    by_canonical = {version.canonical: version for version in known_versions()}
    assert entry.evidence_in(by_canonical["26.100"]).source == "26.100"
    assert entry.evidence_in(by_canonical["26.101"]) is None
    assert entry.evidence_in(by_canonical["26.120"]) is None
    assert entry.evidence_in(by_canonical["26.121"]) is None


def test_the_hotfix_that_does_inherit_still_does():
    """The control: closing one fallback must not close the other.

    A guard that refused every inheritance would satisfy the assertions
    above and silently drop the 26.121 column of the compatibility
    matrix to almost nothing.
    """
    registry = CommandRegistry.load()
    by_canonical = {version.canonical: version for version in known_versions()}

    # The witness is FOUND rather than named. This test used to name
    # SET_BOUNDARY_LAYER_TYPE, and the 2026-08-08 backfill gave that
    # command its own 26.121 row, at which point the test failed while
    # inheritance itself was working perfectly. A guard whose subject
    # can be taken away by unrelated correct work is a guard that will
    # be edited under time pressure.
    inheriting = sorted(
        name
        for name, entry in registry.commands.items()
        if "26.121" not in entry.versions and "26.120" in entry.versions
    )
    assert inheriting, (
        "no command inherits 26.120 evidence on 26.121 any more, so this control "
        "asserts nothing. Either every command now carries its own row, in which "
        "case delete this test and say so, or inheritance broke"
    )
    for name in inheriting:
        entry = registry.commands[name]
        evidence = entry.evidence_in(by_canonical["26.121"])
        assert evidence is not None, name
        assert evidence.source == "26.120" and evidence.inherited, name


def test_the_newest_build_inherits_nothing_so_a_command_with_no_row_is_absent():
    """26.123 claims support for what was measured or read on IT, not on 26.120.

    The two hotfixes before it inherit, and the default is right for
    them: a hotfix that does not touch a command really does carry the
    base evidence. The author's instruction for this build is the
    opposite, and the reason is a number rather than a preference. With
    inheritance on, a build issued the day before would have answered
    for every command 26.120 records without a page of its own manual
    being read or a single line being run, and the compatibility matrix
    would have shown a full column on the strength of it.

    The control beside it (`test_the_hotfix_that_does_inherit_still_does`)
    is what stops this being satisfied by breaking inheritance outright.
    """
    canonicals = [version.canonical for version in known_versions()]
    assert "26.123" in canonicals, (
        "26.123 is not in commands/_meta.yaml, the only ordering authority, so "
        "nothing can be attributed to it. The registry row is what this test is "
        "written against"
    )

    registry = CommandRegistry.load()
    by_canonical = {version.canonical: version for version in known_versions()}
    target = by_canonical["26.123"]
    assert not target.inherits_base, (
        "26.123 is registered as inheriting from 26.120. Every command with a "
        "26.120 row would then answer for a build nothing has been measured on"
    )

    rowless = sorted(
        name for name, entry in registry.commands.items() if "26.123" not in entry.versions
    )
    assert rowless, (
        "every command now carries its own 26.123 row, so this guard asserts "
        "nothing. Say so and delete it rather than leaving it green and empty"
    )
    for name in rowless:
        assert registry.commands[name].evidence_in(target) is None, (
            f"{name} answers for 26.123 with no 26.123 row of its own, so the "
            "inheritance flag is not being honoured"
        )


def test_the_committed_enumeration_matches_what_the_emitter_refuses():
    """The gap on an inheriting-nothing build is a list, not an impression.

    A build that inherits nothing owes a row for every command, and
    nothing fails while it does not have them: the emitter simply
    refuses, one command at a time, wherever a caller happens to reach
    one. So the set is committed and compared, and the file states its
    own counts, because a reader deciding whether to run on this build
    wants the number more than the names.

    The generator is `scripts/gen_absent_commands.py` and it takes any
    registered build, so the next build the author decides should
    inherit nothing reuses it rather than having this copied for it.
    This walks EVERY committed enumeration rather than naming 26.123,
    for the same reason: a second one committed unguarded is exactly the
    failure a guard pinned to one literal cannot see.
    """
    generator = _load_generator()
    committed_files = sorted(GOLDENS.glob("absent_on_*.txt"))
    assert committed_files, (
        "no absent-command enumeration is committed under tests/goldens/. One is "
        "owed by every build registered with inheritance off, and 26.123 is such a "
        "build; regenerate with python scripts/gen_absent_commands.py 26.123"
    )

    registered = {version.canonical for version in known_versions()}
    for path in committed_files:
        undotted = path.stem.removeprefix("absent_on_")
        canonical = f"{undotted[:2]}.{undotted[2:]}"
        assert canonical in registered, (
            f"{path.name} names {canonical}, which is not a registered build. An "
            "enumeration outlived the build it describes, or its name is wrong"
        )
        committed = path.read_bytes()
        assert b"\r" not in committed, (
            f"{path.name} carries a carriage return. Its bytes are the comparison "
            "and read_text would hide the difference; re-save as LF"
        )
        assert committed.decode("utf-8") == generator.render(canonical), (
            f"{path.name} disagrees with the database. Two edits move it and the "
            "message cannot tell them apart: a row written for {canonical}, which "
            "shrinks the list and is the point of the file, and any entry added to "
            "or removed from the database, which moves the total in the header. "
            "Either way regenerate it in the same commit: "
            f"python scripts/gen_absent_commands.py {canonical}"
        )


def test_the_documented_pass_wrote_rows_from_a_reading_and_not_from_a_copy():
    """26.123's documented rows say what SRC-751 says, per command.

    The bulk pass writes a row for a command whose PARSED RECORD is
    identical between the two editions: same argument placeholders, same
    sample block, same parameter table. That is a stronger rule than the
    page-membership one the plan node asks for, and it subsumes it: a
    command on an unchanged page necessarily parses identically, while
    two commands that parse identically sit on a page that MOVED and a
    page rule would have dropped them.

    So the two halves are asserted separately, and the second is the one
    that makes this a test of the rule rather than of a count.
    """
    registry = CommandRegistry.load()
    by_canonical = {version.canonical: version for version in known_versions()}
    target = by_canonical["26.123"]

    # UNCHANGED: it answers, it says documented, and it cites the new
    # edition rather than inheriting a page from the old one.
    #
    # DISABLE_WAKE_NODES_ON_TRAILING_EDGE is here deliberately and is the
    # sharpest of the three. It is word for word what it was, and the new
    # edition breaks the page in the MIDDLE of its block. A page-local
    # reader compared a full record against a truncation and reported a
    # change the vendor had not made; it was excluded from the pass for
    # an hour on 2026-08-17 on exactly that reading, and the CHANGELOG
    # published the falsehood before a skeptic reconstructed the block
    # across the break and refuted it.
    for name in (
        "START_SOLVER",
        "IMPORT_WAKE_EDGES_FROM_FILE",
        "DISABLE_WAKE_NODES_ON_TRAILING_EDGE",
    ):
        entry = registry.commands[name]
        evidence = entry.evidence_in(target)
        assert evidence is not None, (
            f"{name} answers ABSENT on 26.123. Its documentation is unchanged "
            "between SRC-750 and SRC-751, so the documented pass owes it a row"
        )
        assert evidence.source == "26.123" and not evidence.inherited, (
            f"{name}'s 26.123 answer comes from {evidence.source} rather than from a "
            "row of its own, so inheritance is back on"
        )
        note = evidence.record.note or ""
        assert "SRC-751" in note, (
            f"{name}'s 26.123 row does not cite SRC-751. A row written from a reading "
            "names the edition it was read in"
        )
        page = re.search(r"SRC-751 p\.(\d+)", note)
        assert page is not None, (
            f"{name}'s 26.123 note names SRC-751 without a page: {note!r}. The page is "
            "the checkable half, and `pyfs-manual citations` re-reads it"
        )
        assert 283 <= int(page.group(1)) <= 383, (
            f"{name} cites SRC-751 p.{page.group(1)}, outside that edition's scripting "
            "reference pp.283-383. A page outside the range is a citation nobody can "
            "follow to a command"
        )

    # CHANGED: the edition says something different about it, so the bulk
    # pass must NOT have written it a row. Its own node owes the reading.
    # CHANGED, so the bulk pass withheld it and its own node read it. The
    # gate is now the other way round: the row exists, states its own
    # 36-value grammar and cites the page it was read from. It was written
    # on 2026-08-19 (PFS-2026.07); until then this asserted the row's
    # ABSENCE, which is the state the bulk pass left behind. Inverted
    # rather than deleted, because the absence and the read row are the
    # two states this node passes through and neither may be reached by
    # a copy.
    entry = registry.commands["SET_SCENE_CONTOUR"]
    row = entry.versions.get("26.123")
    assert row is not None, (
        "SET_SCENE_CONTOUR carries no 26.123 row. The two editions do NOT say the "
        "same thing about it, so the bulk pass rightly withheld one; its own node "
        "owes the reading and this is where the reading is recorded as done"
    )
    assert row.args is not None, (
        "the 26.123 row states no grammar of its own, so it inherits the 32-value "
        "base set and the four values the edition adds cannot be emitted at all. A "
        "row without the override records that the editions agree, which is the one "
        "thing known to be false about this command"
    )
    (variable,) = row.args
    assert set(variable.values) - set(entry.args[0].values) == {
        "FSI_dx",
        "FSI_dy",
        "FSI_dz",
        "FSI_displacement",
    }, "the 26.123 value set differs from the base set in something other than the four"
    assert "SRC-751 p.355" in (row.note or ""), (
        "the 26.123 row does not cite the page it was read from"
    )
