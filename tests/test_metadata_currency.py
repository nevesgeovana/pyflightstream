"""Guards against silent documentation and metadata drift (NFR-11).

Pipeline role: Tier 1 quality gate. These tests encode the
documentation-currency policy adopted 2026-07-22 after the staleness
audit: version-bearing metadata files must agree with each other, and
the changelog must always carry its Unreleased section so in-progress
work has a recorded home. The user guide's version string is checked
by the release skill, not here, because the guide is refreshed per
release rather than per commit.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_citation_version_matches_pyproject() -> None:
    """CITATION.cff and pyproject.toml must state the same version.

    The citation file is the single home of the citation facts
    (NFR-12); a release that bumps one file and not the other would
    publish a wrong citation. Both files are static, so this holds at
    every commit, not only at release time.
    """
    citation = yaml.safe_load((REPO_ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert citation["version"] == _pyproject_version(), (
        "CITATION.cff and pyproject.toml disagree on the package version; "
        "bump both together (release skill, step 3)."
    )


def test_changelog_keeps_an_unreleased_section() -> None:
    """CHANGELOG.md must always contain the Unreleased section.

    Keep a Changelog structure: unreleased work accumulates under
    '## [Unreleased]' at every session close and the release promotes
    the section (recreating an empty one). If this test fails, either
    the section was dropped at release time or the changelog stopped
    being fed.
    """
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]" in changelog, (
        "CHANGELOG.md has no '## [Unreleased]' section; the session-close "
        "protocol records user-visible changes there (NFR-11)."
    )


def test_srs_requirement_ids_are_unique() -> None:
    """The SRS never reuses a requirement identifier.

    Identifiers are stable forever (deprecated ones included), so a
    duplicate means two different requirements claim the same id.
    """
    import re

    seen: dict[str, str] = {}
    srs_dir = REPO_ROOT / "docs" / "srs"
    pattern = re.compile(r'"((?:FR|NFR|NREQ|AD)-\w+)\s')
    for page in sorted(srs_dir.glob("*.md")):
        for match in pattern.finditer(page.read_text(encoding="utf-8")):
            req_id = match.group(1)
            assert req_id not in seen, (
                f"Requirement id {req_id} appears in both {seen[req_id]} "
                f"and {page.name}; identifiers are stable and unique."
            )
            seen[req_id] = page.name
    assert len(seen) >= 40, "The SRS requirement sweep found suspiciously few ids."


def _glossary_rows() -> dict[str, str]:
    """Return the SRS glossary as ``{term: meaning}``, lowercased keys.

    The section runs to the next heading rather than to end of file, so a
    section appended after the glossary cannot silently widen the term
    source.
    """
    index = (REPO_ROOT / "docs" / "srs" / "index.md").read_text(encoding="utf-8")
    body = index.partition("## Glossary")[2]
    assert body, "the SRS index lost its Glossary section"
    rows: dict[str, str] = {}
    for line in body.splitlines():
        if line.startswith("## "):
            break
        if not line.startswith("|") or line.count("|") < 3:
            continue
        cells = line.split("|")
        term = cells[1].strip().strip("`")
        if term.lower() in ("term", "") or set(term) <= {"-", ":"}:
            continue
        rows[term.lower()] = cells[2].strip()
    return rows


def _terms_nfr24_names() -> list[str]:
    """Parse the term list out of NFR-24's own text.

    Derived rather than duplicated, deliberately. A hand-maintained copy of
    this list here would pass whenever a term is added to the requirement
    and not to the glossary, which is the exact direction of drift NFR-24
    exists to stop; the constant that used to sit here had that hole.
    """
    text = (REPO_ROOT / "docs" / "srs" / "nonfunctional-requirements.md").read_text(
        encoding="utf-8"
    )
    body = text.partition("NFR-24")[2]
    assert body, "NFR-24 is gone from the SRS"
    anchor = "requirement's list ("
    assert anchor in body, (
        f"NFR-24 no longer carries its term list behind {anchor!r}. The list is "
        "the requirement's own text and this parse follows it; if the wording "
        "moved, move this anchor with it deliberately."
    )
    start = body.index(anchor) + len(anchor)
    terms = [term.strip().strip("`") for term in body[start : body.index(")", start)].split(",")]
    return [term for term in terms if term]


def test_every_software_term_nfr24_names_has_a_glossary_row() -> None:
    """NFR-24: the declared audience is not a software audience.

    The SRS states a readership of aerodynamicists, so an unglossed
    software term is a clarity defect rather than a style nit. This test is
    the falsifiable half of the requirement: naming a new term in NFR-24
    without adding its glossary row fails here, and so does deleting or
    emptying a row a named term still relies on.

    The requirement's other half, glossing a term at its FIRST use, stays a
    documentation review check. No cheap test tells a first use from a
    later one, and claiming this test covered both would be exactly the
    overstated guard this repository's incident record warns about.
    """
    named = _terms_nfr24_names()
    assert len(named) >= 6, (
        f"NFR-24's term list parsed as {named}, which is too short to be the "
        "real list; the parse or the requirement text changed shape"
    )
    rows = _glossary_rows()

    missing = [term for term in named if term.lower() not in rows]
    assert not missing, (
        f"NFR-24 names software terms with no SRS glossary row: {missing}. "
        f"Glossary terms found: {sorted(rows)}"
    )

    empty = [term for term in named if not rows[term.lower()]]
    assert not empty, (
        f"these glossary rows exist but gloss nothing: {empty}. A row with an "
        "empty meaning satisfies the letter of NFR-24 and none of its purpose."
    )


def test_a_development_version_states_no_release_date() -> None:
    """A version that was never released has no release date.

    CITATION.cff carried `version: 0.4.0.dev0` beside
    `date-released: 2026-07-23`, the v0.3.0 date, so a citation
    generated from the development tree asserted a release date for an
    artifact that does not exist. That is REV010-015 in the citation
    record rather than in the wheel (architect and tech-writer passes,
    2026-08-03), and the version test above could not see it because it
    compares only the version string.
    """
    from packaging.version import parse as parse_version

    citation = yaml.safe_load((REPO_ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    version = parse_version(_pyproject_version())
    if version.is_prerelease or version.is_devrelease:
        assert "date-released" not in citation, (
            f"CITATION.cff declares the development version {_pyproject_version()!r} and a "
            f"date-released of {citation.get('date-released')!r}. Remove the date until the "
            "release commit sets both together."
        )
    else:
        assert "date-released" in citation, (
            "a final version must state its release date in CITATION.cff"
        )


def test_the_installed_metadata_matches_the_source_tree() -> None:
    """A stale editable install stamps the wrong version into evidence.

    Every compat, drift and physics report records
    ``package_version`` from ``importlib.metadata``, which for an
    editable install is whatever was recorded the last time the project
    was installed, NOT what the source says today. On 2026-08-09 that
    gap put ``package_version: 0.5.0`` into seven identity reports
    produced by the 0.6.0 tree, one of them for a build that the
    published 0.5.0 could not drive at all, since the script argument
    it passed was the one that build does not accept.

    The reports themselves are evidence and were not rewritten; the
    report writer refuses to overwrite one, which is the right refusal.
    So the fix has to be upstream of the writer, and this is it: a
    contributor whose environment would stamp the wrong version is told
    before they spend a licensed run, not after they commit the file.

    The remedy is one command, and the message says it rather than
    leaving a version mismatch to be interpreted.
    """
    from importlib import metadata

    installed = metadata.version("pyflightstream")
    source = _pyproject_version()
    assert installed == source, (
        f"the installed pyflightstream reports version {installed} and the source tree "
        f"says {source}. Any report produced in this environment would record "
        f"{installed} as the package that made it, which is not the code that ran. "
        "Re-install the project before producing evidence: "
        "python -m pip install -e . --no-deps"
    )
