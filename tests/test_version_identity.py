"""Tier 1: a built artifact may not claim an identity it does not have.

REV010-015. HEAD was 66 commits past ``v0.3.0`` and carried landed
v0.4.0 breaking removals, while ``pyproject.toml`` still read ``0.3.0``
and the built wheel imported as ``0.3.0``. Two behaviorally
incompatible artifacts identified as the same version, so bug reports,
manifests, cached environments, citations and compatibility decisions
could not tell them apart.

The trap this file is written around, recorded in
``PLN-20260803-1650`` before the guard existed: the obvious form of
this check ("the version must name the current commit") fails on every
ordinary commit, because ordinary commits are not tagged, and a suite
that is red by construction is worse than no suite. The check here is
conditional instead. It does not require a development version. It
requires that a FINAL version and unreleased behavior never coexist,
which is exactly the state that produces two meanings for one number.

Choosing the versioning SCHEME (a static development version as now, or
a VCS-derived one such as setuptools_scm) is the author's release-time
decision and is deliberately not made here.
"""

import re
import tomllib
from pathlib import Path

import pytest
from packaging.version import parse as parse_version

REPO = Path(__file__).resolve().parents[1]
CHANGELOG = REPO / "CHANGELOG.md"


def _pyproject_version() -> str:
    with (REPO / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def _unreleased_body() -> str:
    """Return the text of the changelog's Unreleased section.

    Empty string when the section is absent or holds nothing but
    whitespace and headings.
    """
    text = CHANGELOG.read_text(encoding="utf-8")
    match = re.search(r"^## \[Unreleased\]\s*$(.*?)^## \[", text, re.M | re.S)
    if match is None:
        return ""
    body = match.group(1)
    # Section headings alone are not content: "### API surface delta" with
    # nothing under it is an empty section, not an unreleased change.
    without_headings = re.sub(r"^#+ .*$", "", body, flags=re.M)
    return without_headings.strip()


def test_a_final_version_never_coexists_with_unreleased_behavior():
    """The release identity may not be worn by a tree that has moved past it.

    If this fails at a release commit, the fix is to finish the release:
    move the Unreleased section under the new version heading. If it
    fails during development, the fix is a development version.
    """
    version = _pyproject_version()
    parsed = parse_version(version)
    if not _unreleased_body():
        pytest.skip("nothing unreleased; a final version is exactly right here")
    assert parsed.is_prerelease or parsed.is_devrelease, (
        f"pyproject.toml declares the final version {version!r} while CHANGELOG.md's "
        "Unreleased section describes behavior that is not in that release. A wheel "
        "built here would import as a released version and behave differently from "
        "it, which is REV010-015: two incompatible artifacts answering to one "
        "number. Use a development version (for example "
        f"{parsed.base_version}.dev0) until the release commit, or complete the "
        "release by moving the Unreleased section under its version heading."
    )


def test_the_version_is_a_valid_pep440_string():
    """A version nothing can parse is its own identity problem."""
    parse_version(_pyproject_version())


def test_the_unreleased_reader_can_tell_empty_from_full():
    """Mutation proof for the condition the guard rests on.

    Without this, `_unreleased_body` could return "" unconditionally and
    the guard above would skip forever while reporting green.
    """
    assert _unreleased_body(), (
        "this repository currently HAS unreleased entries, so the reader "
        "returning nothing would mean it is broken rather than that the "
        "section is empty"
    )


@pytest.mark.parametrize(
    ("version", "unreleased", "should_pass"),
    [
        ("0.4.0.dev0", "* something", True),
        ("0.4.0rc1", "* something", True),
        ("0.4.0", "", True),
        ("0.4.0", "* something", False),
        ("0.3.0", "* a landed breaking removal", False),
    ],
)
def test_the_rule_itself_accepts_and_refuses_the_right_pairs(version, unreleased, should_pass):
    """The rule driven directly, so it is exercised for states this
    repository is not currently in. The test above can only ever see one
    of these five, which is why it is not enough on its own."""
    parsed = parse_version(version)
    holds = bool(not unreleased.strip() or parsed.is_prerelease or parsed.is_devrelease)
    assert holds is should_pass, (version, unreleased)
