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

from pathlib import Path

from pyflightstream.commands import CommandEntry, CommandRegistry
from pyflightstream.reference import markdown_compatibility_matrix
from pyflightstream.versions import known_versions

MARK = "base</sup>"


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

    # Absent: no record anywhere in reach.
    absent = registry.commands["AIR_ALTITUDE"].evidence_in(versions["26.000"])
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
