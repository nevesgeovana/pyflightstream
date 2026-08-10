"""Tier 1: the build correspondence page, generated from the registry.

The page answers "which build do I have" for a reader holding an
install and a paper. Its whole value is that the mapping cannot drift
from the registry, so these guards check the derivation rather than the
prose, and they check that the page never reconstructs the solver's
banner: the 25.0 build prints two spaces where the 26.1 builds print
one, so a rendered banner line would be wrong for some readers in a way
no reader could report.
"""

import re

from pyflightstream.reference import markdown_build_table
from pyflightstream.versions import known_versions


def _rows(page: str) -> list[list[str]]:
    """Table rows of the page, as trimmed cell lists."""
    rows = []
    for line in page.splitlines():
        if not line.startswith("|") or set(line) <= set("|- "):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows.append(cells)
    return rows[1:]  # drop the header


def test_every_registered_build_has_a_row_with_its_number():
    page = markdown_build_table()
    rows = _rows(page)
    versions = known_versions()
    assert len(rows) == len(versions), f"{len(rows)} rows for {len(versions)} versions"

    for row, version in zip(rows, versions, strict=True):
        alias, build, canonical = row
        assert alias.startswith(version.alias), row
        assert canonical == f"`{version.canonical}`", row
        if version.build is None:
            assert build == "not recorded here yet", row
        else:
            assert build == f"#{version.build}", row


def test_the_page_marks_every_release_name_that_names_two_builds():
    """An unmarked ambiguous name is the failure this page exists to prevent.

    A reader who writes "26.1" in a paper has not said which solver ran,
    and the table is where they learn it. Marking is derived from the
    registry, so a future build sharing a name is marked without anyone
    remembering to.
    """
    page = markdown_build_table()
    counts: dict[str, int] = {}
    for version in known_versions():
        counts[version.alias] = counts.get(version.alias, 0) + 1

    for row in _rows(page):
        alias_cell = row[0]
        alias = alias_cell.split(" (")[0]
        marked = "names more than one build" in alias_cell
        assert marked == (counts[alias] > 1), (alias, marked, counts[alias])


def test_the_page_never_reconstructs_the_solver_banner():
    """Show the fields, never a sentence the solver is claimed to print.

    The first draft of this page rendered
    ``FlightStream version 25.0, build #12162024`` as the thing to look
    for. That build prints two spaces after "version", so the line was
    wrong for the oldest install in the registry, and wrong in the one
    column a reader would compare character by character.
    """
    page = markdown_build_table()
    assert not re.search(r"FlightStream version\s+\d", page), (
        "the page reconstructs the solver's banner; the format is not "
        "identical across builds, so show the fields separately"
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
