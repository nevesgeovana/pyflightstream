"""Tier 1: the build correspondence page, generated from the registry.

The page answers "which build do I have" for a reader holding an
install and a paper. Its whole value is that the mapping cannot drift
from the registry, so these guards check the derivation rather than the
prose.

Two of them exist because a first draft got the identifying value
wrong in a way that was worse than having no page. It keyed the "release
name it prints" column on ``FsVersion.alias``, the name the VENDOR SELLS
the build under. Those two facts differ for every build of the 26.12
release: all of them are sold as 26.12 and all of them print 26.1. No
count is written here, because it has moved twice. A reader with
any of those installs would have found no row carrying
their printed name, matched one of the rows that does, and left with the
identifier of a different solver. The page is keyed on
``FsVersion.prints`` now, and one guard below cross-checks that field
against the solver banners in the committed reports, which is the check
whose absence let the defect through.

The other is about the banner LINE. It is not byte-identical across
builds: the 25.0 solver writes a NUL byte into its console banner where
the newer builds write a space (RPT-023). A first draft of this file
said "two spaces", which is what a terminal draws that byte as; reading
a rendering is not reading bytes, and this repository has an incident on
exactly that (INC-20260724-0410-shared).
"""

import re
from pathlib import Path

import yaml

from pyflightstream.reference import markdown_build_table
from pyflightstream.versions import known_versions

#: Anchored on this file, never on the working directory. A cwd-relative
#: glob returns nothing when pytest is invoked from elsewhere, and this
#: guard then accuses the registry of seven unevidenced values, which is
#: the most expensive kind of wrong message to hand a maintainer.
REPO = Path(__file__).resolve().parents[1]


def _rows(page: str) -> list[list[str]]:
    """Table rows of the page, as trimmed cell lists."""
    rows = []
    for line in page.splitlines():
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows.append(cells)
    # Assert the shape here rather than in each consumer: two of the
    # four below pass over an empty list, so a page that lost its table
    # would satisfy them.
    assert rows, "the page carries no table at all"
    assert rows[0][0] == "Release name it prints", f"unexpected header: {rows[0]}"
    assert len(rows) > 1, "the table has a header and no rows"
    return rows[1:]  # drop the header


def test_every_registered_build_has_a_row_with_its_number():
    page = markdown_build_table()
    rows = _rows(page)
    versions = known_versions()
    assert len(rows) == len(versions), f"{len(rows)} rows for {len(versions)} versions"

    for row, version in zip(rows, versions, strict=True):
        printed, build, canonical, sold = row
        assert canonical == f"`{version.canonical}`", row
        assert printed.split(" (")[0] == (version.prints or "not recorded here yet"), row
        assert sold.split(" (")[0] == version.alias, row
        if version.build is None:
            assert build == "not recorded here yet", row
        else:
            assert build == f"#{version.build}", row


def test_the_printed_name_comes_from_a_solver_banner_and_not_from_the_alias():
    """The field is evidence, so it may not be typed in from the alias.

    This is the guard whose absence let the first draft ship the sold
    name as the printed one. It is the shape of
    ``test_every_registered_build_comes_from_a_committed_report``,
    applied to the other half of the same banner line.
    """
    observed: dict[str, set[str]] = {}
    for path in sorted((REPO / "reports").rglob("*.yaml")):
        with open(path, encoding="utf-8") as handle:
            document = yaml.safe_load(handle)
        if not isinstance(document, dict):
            continue
        version = document.get("fs_version")
        for line in document.get("solver_identity") or ():
            match = re.search(r"version\s*\W*\s*([0-9]+\.[0-9]+)", str(line))
            if version and match:
                observed.setdefault(str(version), set()).add(match.group(1))

    registered = {v.canonical: v.prints for v in known_versions() if v.prints is not None}
    assert registered, "no printed name is registered; this test would prove nothing"
    unevidenced = {
        canonical: printed
        for canonical, printed in registered.items()
        if printed not in observed.get(canonical, set())
    }
    assert not unevidenced, (
        f"these registered printed names appear in no committed report for their own "
        f"version: {unevidenced}. The printed name is solver evidence; record it from a "
        "report's solver_identity, never from the vendor alias (CLAUDE.md invariant 3)."
    )


def test_the_printed_name_and_the_sold_name_actually_differ_somewhere():
    """Non-vacuity for the two guards above.

    If every build's printed name equalled its alias, both would pass
    over a distinction that carries nothing, and the page could go back
    to rendering the alias with no test noticing.
    """
    differing = [v.canonical for v in known_versions() if v.prints and v.prints != v.alias]
    assert differing, (
        "no registered build prints a name different from its vendor alias, so the "
        "distinction this page is built on is untested; if the vendor stopped doing "
        "this, simplify the page deliberately rather than leaving a guard that cannot "
        "fail"
    )


def test_the_page_marks_every_printed_name_that_more_than_one_build_prints():
    """An unmarked shared name is the failure this page exists to prevent.

    A reader who reads "26.1" off their banner has four candidates, and
    the table is where they learn to match on the build number instead.
    Marking is derived from the registry, so a future build sharing a
    printed name is marked without anyone remembering to.
    """
    page = markdown_build_table()
    counts: dict[str, int] = {}
    for version in known_versions():
        if version.prints is not None:
            counts[version.prints] = counts.get(version.prints, 0) + 1

    for row in _rows(page):
        printed = row[0].split(" (")[0]
        marked = "(shared)" in row[0]
        assert marked == (counts.get(printed, 0) > 1), (printed, marked, counts.get(printed))


def test_the_page_flags_a_build_whose_sold_name_is_not_what_it_prints():
    """The reader must not match on the name they saw on the download page."""
    page = markdown_build_table()
    rows = _rows(page)
    for row, version in zip(rows, known_versions(), strict=True):
        differs = version.prints is not None and version.prints != version.alias
        assert ("not what it prints" in row[3]) == differs, row


def test_the_page_never_reconstructs_the_solver_banner():
    """Show the fields, never a sentence the solver is claimed to print.

    The first draft of this page rendered
    ``FlightStream version 25.0, build #12162024`` as the thing to look
    for. That build writes a NUL byte where the newer ones write a
    space, so the line was wrong for the oldest install in the registry,
    and wrong in the one column a reader would compare character by
    character.
    """
    page = markdown_build_table()
    assert not re.search(r"flightstream version\s+\d", page, re.IGNORECASE), (
        "the page reconstructs the solver's banner; the line is not byte-identical "
        "across builds, so show the fields separately"
    )


def test_the_page_points_at_support_rather_than_restating_it():
    """Registered is not supported, and this page must not decide which.

    Support level is derived in pyflightstream.support and rendered on
    the compatibility matrix. A level word copied onto this page would
    be a second home for a fact that changes with the evidence
    (NFR-11).
    """
    page = markdown_build_table()
    assert "compatibility.md" in page
    assert "support_table()" in page
    for level in ("`registered`", "`documented`", "`verified`", "`operational`"):
        assert level not in page, f"{level} restated on the build page"
