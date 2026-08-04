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

from pyflightstream.commands import CommandRegistry
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
