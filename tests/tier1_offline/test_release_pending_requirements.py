"""Tier 1: a release is refused while a requirement or amendment it owns is pending.

The rule of the SRS (docs/unpublished/requirements/index.md, revision 1.76.0):
a release promotes the
requirements it owns in its own docs step, so none stays pending after the release
that ships it. 0.39.0 shipped with its requirements still pending, and the first
commit of 0.40.0 had to promote them; this arm makes that impossible to repeat.

A requirement is owned by the release its ``Plan:`` line names in parentheses
(``Plan: PFS-2080.05 (0.39.0).``, ``(0.39.0; backlog PFS-2012.06)``, or a second
group such as ``R8 PFS-2080.01 (0.39.0, pending)``). An amendment is owned by the
release in its mark: ``(0.39.0, pending)`` or ``Amended in 0.39.0 (R8, pending)``.
The package version is the one in ``pyproject.toml``; during the development of a
release the requirements it owns may be pending, and the release is the moment
this test refuses them.

The control of the arm is planted in this file: the same parser run over a box
that is pending and owned by the version fails, and over the same box implemented,
or owned by another release, passes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PAGES = ("functional-requirements.md", "nonfunctional-requirements.md")

_BOX_START = re.compile(
    r"^!!! requirement \"(?P<id>N?FR-\d+[a-z]?) .*?<span class='srs-(?P<status>\w+)'", re.M
)
_PLAN = re.compile(r"^ {4}Plan:(?P<plan>.*)$", re.M)
_GROUP = re.compile(r"\(([^()]*)\)")


def package_version() -> str:
    """Return the version the package declares in pyproject.toml."""
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    found = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', text, re.M)
    assert found, "pyproject.toml states no package version"
    return found.group(1)


def _boxes(text: str) -> list[tuple[str, str, str]]:
    """Return (id, badge status, whole box text) for every requirement box of a page."""
    starts = list(_BOX_START.finditer(text))
    out = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        out.append((match.group("id"), match.group("status"), text[match.start() : end]))
    return out


def _owned_by(box: str, version: str) -> bool:
    plan = _PLAN.search(box)
    if not plan:
        return False
    for group in _GROUP.findall(plan.group("plan")):
        if re.split(r"[;,]\s*", group.strip())[0] == version:
            return True
    return False


def pending_owned(text: str, version: str) -> list[str]:
    """Return the requirements and amendments of ``version`` that are still pending."""
    refused = []
    amendment = re.compile(
        rf"\({re.escape(version)}, pending\)|in {re.escape(version)} \(R\d+, pending\)"
    )
    for rid, status, box in _boxes(text):
        if status == "pending" and _owned_by(box, version):
            refused.append(f"{rid}: pending, owned by {version}")
        if amendment.search(box):
            refused.append(f"{rid}: an amendment of {version} is still pending")
    return refused


def _live(page: str) -> str:
    return (REPO / "docs" / "srs" / page).read_text(encoding="utf-8")


def test_no_requirement_or_amendment_owned_by_this_release_is_pending():
    """The refusal itself, on the live SRS pages and the package version."""
    version = package_version()
    refused = [line for page in PAGES for line in pending_owned(_live(page), version)]
    assert not refused, (
        f"the release {version} cannot ship while its own requirements are pending: {refused}. "
        "Promote them in the release's docs step (status implemented, Evidence paragraph, "
        "revision row) or move their owner."
    )


_PENDING_BOX = (
    "!!! requirement \"FR-900 A planted requirement <span class='srs-pending'>pending</span>\"\n"
    "    Plan: PFS-9000.01 (9.9.9).\n\n    Need: none.\n"
)


def test_control_a_pending_box_owned_by_the_version_is_refused():
    assert pending_owned(_PENDING_BOX, "9.9.9") == ["FR-900: pending, owned by 9.9.9"]


def test_control_the_same_box_implemented_is_accepted():
    done = _PENDING_BOX.replace("srs-pending'>pending", "srs-implemented'>implemented")
    assert pending_owned(done, "9.9.9") == []


def test_control_a_pending_box_owned_by_another_release_is_not_this_releases():
    assert pending_owned(_PENDING_BOX, "9.9.8") == []


def test_control_a_second_group_and_a_backlog_group_still_name_the_owner():
    second = _PENDING_BOX.replace(
        "PFS-9000.01 (9.9.9).", "PFS-9000.01 (9.9.8); R8 PFS-9000.02 (9.9.9, pending)."
    )
    assert pending_owned(second, "9.9.9") == [
        "FR-900: pending, owned by 9.9.9",
        "FR-900: an amendment of 9.9.9 is still pending",
    ]
    backlog = _PENDING_BOX.replace("(9.9.9)", "(9.9.9; backlog PFS-1.2)")
    assert pending_owned(backlog, "9.9.9") == ["FR-900: pending, owned by 9.9.9"]


@pytest.mark.parametrize(
    "mark",
    [
        "Amended by FR-999 (9.9.9, pending): the set grows.",
        "Amended in 9.9.9 (R8, pending): test, x.",
    ],
)
def test_control_a_pending_amendment_of_an_implemented_box_is_refused(mark):
    done = (
        _PENDING_BOX.replace("srs-pending'>pending", "srs-implemented'>implemented")
        + f"    {mark}\n"
    )
    assert pending_owned(done, "9.9.9") == ["FR-900: an amendment of 9.9.9 is still pending"]


def test_control_the_live_pages_fail_when_a_promoted_box_is_put_back_to_pending():
    """The parser reads the live pages: revert FR-430 to pending and 0.39.0 refuses it."""
    text = _live("functional-requirements.md")
    assert pending_owned(text, "0.39.0") == []
    start = text.index('!!! requirement "FR-430 ')
    end = text.index("\n", start)
    reverted = (
        text[:start]
        + text[start:end].replace("srs-implemented'>implemented", "srs-pending'>pending")
        + text[end:]
    )
    assert pending_owned(reverted, "0.39.0") == ["FR-430: pending, owned by 0.39.0"]
