"""Tier 1: every independent-review identifier the code cites resolves here.

Pipeline role: a repository guard rather than a behavior test. It reads
the tree as data and decides one question, whether a citation a reader
can see leads anywhere inside the repository.

REPRODUCTION, and it needs no import. At HEAD before this module,
searching ``src`` and ``tests`` for ``PYFS-001`` returned a citing site
in ``tests/test_script.py`` and searching ``reports`` for the same
string returned nothing at all. Forty-one distinct identifiers were in
that state, 23 of the ``PYFS-nnn`` series and 18 of the ``REV010-nnn``
series, and exactly one of the forty-one, ``PYFS-025``, was named
anywhere under ``reports`` (in the body of RPT-016, not in a heading).
A reader following any of the others left the repository and arrived
nowhere, which is what one read-only survey did before concluding from
the dead end that the findings could not be worked.

The requirement is NFR-11, documentation currency: a fact is stated in
one home and a public statement may not quietly stop being true. A
citation whose target lives only in another repository is that failure
in its purest form, because nothing in this repository can ever notice
it going stale.

THE WALK REFUSES TO WALK NOTHING, and that is the half worth stating
twice. A sweep that collects zero identifiers passes every "each
collected identifier resolves" assertion ever written, so a renamed
series or a broken enumeration would report green while guarding
nothing. :class:`VacuousWalkError` is raised instead, and a test below
proves it fires by handing the walk a source that cites nothing.

The report side needs no such refusal and deliberately does not have
one: an empty heading index leaves EVERY citation unresolved, so a
deleted or restructured report fails loudly through the main assertion
rather than quietly through a missing floor. A separate test asserts the
heading index is non-empty anyway, so the diagnosis is one line rather
than forty.

THE RESIDUAL, stated rather than left to be discovered. The enforced
roots are ``src`` and ``tests``, which is the scope of the work item
this module closes, and prose elsewhere can cite the same identifiers.
Measured on 2026-08-18 over ``docs``, ``examples``, ``README.md`` and
``CONTRIBUTING.md``: 11 distinct identifiers are cited there and all 11
already resolve to a heading, because the report heads every finding of
both reviews rather than only the cited ones. Nothing holds that, and
widening the roots is registered rather than done here.

THE SWEEP NEVER READS THE REPORTS IT RESOLVES AGAINST. If it did, the
answering report would satisfy itself: every identifier it names in a
heading would also be an identifier it cites, and the walk would be
green with the code's own citations unchecked. The source roots are
``src`` and ``tests`` alone, and a test below asserts that no swept path
lies under ``reports``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: The two roots whose citations must resolve. Deliberately NOT
#: ``reports``: see the module docstring.
SOURCE_ROOTS: tuple[Path, ...] = (REPO / "src", REPO / "tests")

#: Where a citation is allowed to resolve. Every narrative report,
#: including the ones nested under ``compat``, ``fsi`` and ``physics``.
REPORTS = REPO / "reports"

#: The two published identifier series of the independent reviews.
#: ``PYFS-nnn`` is the 2026-07-28 review, ``REV010-nnn`` the 2026-08-03
#: one. Three digits in both, which is what the reviews published.
IDENTIFIER = re.compile(r"\b(?:PYFS|REV010)-[0-9]{3}\b")

#: A floor on the source sweep itself, so a broken enumeration cannot
#: report clean by reading nothing. The number is a floor and not a
#: measurement: the tree held far more than this when it was written.
MINIMUM_SOURCE_FILES = 40


class VacuousWalkError(AssertionError):
    """A walk collected nothing, which is how this class of guard dies.

    An ``AssertionError`` subclass rather than a bare exception so that
    a caller who does not know about it still sees a failed assertion
    rather than an error, and so ``pytest.raises`` below is narrow.
    """


def python_sources(roots: Iterable[Path]) -> list[Path]:
    """Return every ``.py`` file under the given roots, sorted.

    Read from the filesystem rather than from ``git ls-files`` on
    purpose. A file that is not yet committed can carry a citation just
    as a committed one can, and the drift this module exists to catch is
    cheapest to catch before the commit. Compiled caches are excluded by
    the suffix rather than by a directory name.

    Parameters
    ----------
    roots : iterable of pathlib.Path
        Directories to walk. Missing directories contribute nothing.

    Returns
    -------
    list of pathlib.Path
        Absolute paths, sorted, no duplicates.
    """
    found: set[Path] = set()
    for root in roots:
        if root.is_dir():
            found.update(path for path in root.rglob("*.py") if path.is_file())
    return sorted(found)


def _where(path: Path) -> str:
    """Name a file for a message: repository-relative when it is inside.

    A temporary file handed in by a test is outside the repository, and
    ``relative_to`` raises there rather than returning something useful,
    which turned three of this module's own guards into errors before
    they could assert anything.
    """
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def cited_identifiers(paths: Iterable[Path]) -> dict[str, list[str]]:
    """Return {identifier: ["path:line", ...]} over the given files.

    Parameters
    ----------
    paths : iterable of pathlib.Path
        Files to read as utf-8 text.

    Returns
    -------
    dict
        One key per distinct identifier, with every site that cites it
        in repository-relative ``path:line`` form, in file order.
    """
    sites: dict[str, list[str]] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            for match in IDENTIFIER.finditer(line):
                where = f"{_where(path)}:{number}"
                sites.setdefault(match.group(0), []).append(where)
    return sites


def heading_identifiers(paths: Iterable[Path]) -> dict[str, list[str]]:
    """Return {identifier: [report path, ...]} for identifiers in HEADINGS.

    A heading and not a mention, for the same reason the command
    database requires a probe report to NAME the command it backs: a
    report that happens to say ``PYFS-005`` in a sentence about
    something else is not a place where that finding is written down.
    A heading is a promise that the section under it is about the
    identifier it names.

    Fenced code blocks are skipped, so a shell comment inside a
    reproduction block cannot be read as a heading.

    Parameters
    ----------
    paths : iterable of pathlib.Path
        Markdown files to read as utf-8 text.

    Returns
    -------
    dict
        One key per distinct identifier named in at least one heading,
        with the reports whose headings name it.
    """
    found: dict[str, list[str]] = {}
    for path in paths:
        fenced = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced or not line.startswith("#"):
                continue
            for match in IDENTIFIER.finditer(line):
                where = _where(path)
                if where not in found.setdefault(match.group(0), []):
                    found[match.group(0)].append(where)
    return found


def unresolved_citations(sources: Iterable[Path], reports: Iterable[Path]) -> dict[str, list[str]]:
    """Return the citations that resolve to no report heading.

    Parameters
    ----------
    sources : iterable of pathlib.Path
        Python files whose citations must resolve.
    reports : iterable of pathlib.Path
        Markdown reports the citations may resolve into.

    Returns
    -------
    dict
        {identifier: sites} for every identifier with no heading, empty
        when every citation resolves.

    Raises
    ------
    VacuousWalkError
        When the sources carry no identifier at all, which makes every
        per-identifier assertion vacuously true, so the walk refuses
        rather than reports green. There is deliberately no matching
        refusal on the report side: reports that head nothing leave
        every citation unresolved, which is loud already.
    """
    cited = cited_identifiers(sources)
    if not cited:
        raise VacuousWalkError(
            "the sweep collected no review identifier at all. Either the source "
            "roots are wrong, the series was renamed, or the enumeration is "
            "broken; in every case this guard is walking nothing and must not "
            "report green"
        )
    headings = heading_identifiers(reports)
    return {name: sites for name, sites in cited.items() if name not in headings}


def test_every_review_identifier_cited_in_the_code_resolves_to_a_report_heading():
    """The item itself. A citation a reader can see leads somewhere.

    NFR-11. Before RPT-028 existed this failed with 41 identifiers, each
    naming the sites that cite it, which is the falsifying measurement
    recorded for this work item.
    """
    sources = python_sources(SOURCE_ROOTS)
    reports = sorted(REPORTS.rglob("*.md"))
    unresolved = unresolved_citations(sources, reports)
    assert not unresolved, (
        f"{len(unresolved)} review identifiers cited in src/ or tests/ resolve to "
        "no heading in any report under reports/:\n"
        + "\n".join(
            f"  {name}: {sites[0]}" + (f" and {len(sites) - 1} more" if len(sites) > 1 else "")
            for name, sites in sorted(unresolved.items())
        )
        + "\n\nA citation whose target is not in this repository sends a reader "
        "out of it, and nothing here can notice it going stale."
    )


def test_the_walk_refuses_a_source_set_that_carries_no_identifier(tmp_path):
    """Zero collected identifiers is a refusal, never a pass.

    This is the failure mode the acceptance sentence names, and it is
    silent by construction: every assertion of the form "each collected
    identifier resolves" is true of an empty collection.
    """
    empty = tmp_path / "carries_nothing.py"
    empty.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(VacuousWalkError, match="collected no review identifier"):
        unresolved_citations([empty], sorted(REPORTS.rglob("*.md")))


def test_a_report_set_that_heads_nothing_leaves_every_citation_unresolved(tmp_path):
    """The other direction, and it needs no floor of its own.

    A report deleted, renamed out of the scan, or rewritten so its
    findings stop being headings answers nothing, and the resolution
    loop says so about every identifier rather than going quiet. This is
    why the report side has no vacuity refusal: it cannot fail silently.
    """
    silent = tmp_path / "no_headings.md"
    silent.write_text("# RPT-000: a report about nothing\n\nProse only.\n", encoding="utf-8")
    sources = python_sources(SOURCE_ROOTS)
    unresolved = unresolved_citations(sources, [silent])
    assert len(unresolved) == len(cited_identifiers(sources)), (
        "a report set naming no identifier in any heading must leave every "
        "citation unresolved, which is what makes a deleted report loud"
    )


def test_the_committed_reports_head_at_least_one_identifier():
    """A one-line diagnosis for the state that would otherwise print forty.

    Not a substitute for the assertion above: it is the same fact read
    from the report side, so a reader of a red suite learns whether the
    report is gone or whether one identifier drifted.
    """
    headings = heading_identifiers(sorted(REPORTS.rglob("*.md")))
    assert headings, (
        "no report under reports/ names a review identifier in a heading; the "
        "report that answers the code's citations is missing or restructured"
    )


def test_an_identifier_no_report_heads_is_reported(tmp_path):
    """The guard is not vacuously green: give it a dangling citation.

    The synthetic identifier is assembled from fragments so that this
    file, which the sweep reads, does not itself carry a citation that
    would have to resolve.
    """
    dangling = "PYFS" + "-" + "997"
    source = tmp_path / "cites_a_ghost.py"
    source.write_text(f"# see {dangling} for the reasoning\n", encoding="utf-8")
    unresolved = unresolved_citations([source], sorted(REPORTS.rglob("*.md")))
    assert list(unresolved) == [dangling]
    assert unresolved[dangling] == [f"{source.as_posix()}:1"], (
        "the failure must name the site, since a reader fixes the citation and not the identifier"
    )


def test_a_body_mention_does_not_resolve_a_citation_but_a_heading_does(tmp_path):
    """Naming a finding in passing is not writing it down.

    Both halves are asserted from one pair of files, so the test cannot
    pass by the mention rule and the heading rule agreeing.
    """
    dangling = "REV010" + "-" + "998"
    source = tmp_path / "cites.py"
    source.write_text(f'"""Closed under {dangling}."""\n', encoding="utf-8")

    mention = tmp_path / "mentions.md"
    mention.write_text(
        f"# RPT-000: a report about something else\n\nRelated to {dangling}.\n",
        encoding="utf-8",
    )
    assert list(unresolved_citations([source], [mention])) == [dangling]

    heads = tmp_path / "heads.md"
    heads.write_text(f"# RPT-000: findings\n\n## {dangling}: the statement\n", encoding="utf-8")
    assert unresolved_citations([source], [heads]) == {}


def test_a_fenced_line_is_not_a_heading(tmp_path):
    """A shell comment in a reproduction block must not answer a citation."""
    dangling = "PYFS" + "-" + "996"
    source = tmp_path / "cites.py"
    source.write_text(f"# {dangling}\n", encoding="utf-8")
    fenced = tmp_path / "fenced.md"
    fenced.write_text(
        f"# RPT-000: a report\n\n```\n# {dangling} is a comment here\n```\n",
        encoding="utf-8",
    )
    assert list(unresolved_citations([source], [fenced])) == [dangling]


def test_the_sweep_never_reads_the_reports_it_resolves_against():
    """Otherwise the answering report satisfies itself.

    Every identifier a report heads is also an identifier that report
    cites, so a sweep that included ``reports`` would be green with the
    code's own citations never checked. Asserted against the paths the
    sweep actually returns rather than against the constant it walks.
    """
    swept = python_sources(SOURCE_ROOTS)
    assert swept, "the source sweep returned nothing"
    intruders = [path.relative_to(REPO).as_posix() for path in swept if REPORTS in path.parents]
    assert not intruders, (
        f"the sweep reached {intruders} under reports/. A report that answers a "
        "citation must never be a source of one, or the walk grades its own work"
    )
    assert all(any(root in path.parents for root in SOURCE_ROOTS) for path in swept), (
        "the sweep reached outside src/ and tests/"
    )


def test_the_source_sweep_reaches_the_files_it_claims():
    """A floor and two anchors, so a broken enumeration cannot read clean.

    The count floor catches a walk that collapses to nothing; the two
    anchors catch a walk that reaches one root and not the other, which
    a count alone would hide.
    """
    swept = python_sources(SOURCE_ROOTS)
    assert len(swept) >= MINIMUM_SOURCE_FILES, (
        f"the sweep found {len(swept)} python files under src/ and tests/, below "
        f"the floor of {MINIMUM_SOURCE_FILES}; the enumeration is broken"
    )
    relative = {path.relative_to(REPO).as_posix() for path in swept}
    assert "src/pyflightstream/__init__.py" in relative
    assert "tests/test_review_citations.py" in relative
