"""FR-345, P0340-RELEASE-TITLE: the report-index test names no release title.

``test_rpt096`` used to look for the section titled with one release and fell
back to ``[Unreleased]``, so opening the next release section failed the tag CI
of 0.32.0. It now finds the section that carries its report by the report's
identifier. These tests hold that reading: a new empty section above the one
that carries the report changes nothing, and the old form, which read the
newest section, is the control that fails on the same text.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
import yaml

from tests.tier1_offline import test_rpt096
from tests.tier1_offline.test_rpt096 import release_section_carrying

REPO = Path(__file__).resolve().parents[2]
CHANGELOG = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
RELEASE_YML = REPO / ".github" / "workflows" / "release.yml"
NEEDLE = "reports/RPT-096"
EMPTY_SECTION = "## [99.0.0] - 2099-01-01\n\n"


def _with_empty_section_on_top(changelog: str) -> str:
    """The change log with a new, empty release section above every other."""
    first = changelog.index("\n## [") + 1
    return changelog[:first] + EMPTY_SECTION + changelog[first:]


def _newest_section(changelog: str) -> str:
    """The 0.33.0 form of the lookup: the first release section, whatever it carries."""
    return changelog.split("\n## [", 2)[1]


@pytest.mark.requirement("FR-345")
def test_a_new_empty_release_section_does_not_change_the_verdict_fr_345():
    """P0340-RELEASE-TITLE, R2: the section found carries the report before and after."""
    before = release_section_carrying(CHANGELOG, NEEDLE)
    opened = _with_empty_section_on_top(CHANGELOG)
    assert opened != CHANGELOG
    after = release_section_carrying(opened, NEEDLE)
    assert NEEDLE in before and after == before
    # The control: the newest-section form, which the new section would have failed.
    assert NEEDLE not in _newest_section(opened)


@pytest.mark.requirement("FR-345")
def test_the_section_is_found_by_its_report_and_not_by_a_title_fr_345():
    """P0340-RELEASE-TITLE, R1: a synthetic change log in which the report moves between titles."""
    for title in ("Unreleased", "7.8.9", "0.0.1"):
        log = f"# Change log\n\n## [8.0.0]\n\n- nothing\n\n## [{title}]\n\n- {NEEDLE}\n"
        assert release_section_carrying(log, NEEDLE).startswith(f"{title}]")
    try:
        release_section_carrying("# Change log\n\n## [1.0.0]\n\n- nothing\n", NEEDLE)
    except AssertionError as error:
        assert NEEDLE in str(error)
    else:
        raise AssertionError("a change log that does not carry the report was accepted")


@pytest.mark.requirement("FR-345")
def test_the_report_index_test_writes_no_release_title_fr_345():
    """P0340-RELEASE-TITLE, R1: no version string in the index test or in its helper."""
    for function in (
        test_rpt096.test_rpt096_is_indexed_where_the_tree_indexes_reports,
        release_section_carrying,
    ):
        source = inspect.getsource(function)
        assert not re.search(r"\d+\.\d+\.\d+", source), function.__name__


@pytest.mark.requirement("FR-345")
def test_the_first_of_several_carrying_sections_is_the_one_chosen_fr_345():
    """P0340-RELEASE-TITLE, R2: with the report in two sections, the newest (first) is found."""
    log = f"# Log\n\n## [B]\n\n- {NEEDLE} newest\n\n## [A]\n\n- {NEEDLE} older\n"
    assert "newest" in release_section_carrying(log, NEEDLE)


@pytest.mark.requirement("FR-345")
def test_a_dry_run_branch_rehearses_the_release_and_only_a_tag_publishes_fr_345():
    """P0340-RELEASE-TITLE, R3: dry-run/** triggers; publish and the version check are tag-gated."""
    document = yaml.safe_load(RELEASE_YML.read_text(encoding="utf-8"))
    trigger = document.get("on", document.get(True))
    assert "dry-run/**" in trigger["push"]["branches"]
    assert "v*" in trigger["push"]["tags"]
    tag_only = "startsWith(github.ref, 'refs/tags/v')"
    assert document["jobs"]["publish"]["if"] == tag_only
    gated = [
        step
        for job in document["jobs"].values()
        for step in job.get("steps", [])
        if "tag matches the package version" in step.get("name", "")
    ]
    assert gated and all(step.get("if") == tag_only for step in gated)
