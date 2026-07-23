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
