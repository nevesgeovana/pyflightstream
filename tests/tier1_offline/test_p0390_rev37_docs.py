"""P0390-REV37 (NFR-45 R5): the 0.37 document findings and the owed 0.38 limit.

Each test reads the committed text, so a sentence that returns to its old place or
wording fails here.
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.tier1_offline._docs_site import FUNCTIONAL_REQUIREMENTS

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
S6_TEST = ROOT / "tests/tier1_offline/test_p0370_s6_direct_morphing.py"
OLD_SENTENCE = "take one comma-separated value"
CONTRACT = "take comma-separated, bracketed or blank-separated ids, quoted or not"
#: What the one ``git show`` below needs to start and find its config, and nothing else.
_GIT_ENV_KEYS = ("PATH", "SYSTEMROOT", "SystemRoot", "HOME", "USERPROFILE")
FROZEN = "migrating-to-*.md"  # a frozen record of its release is never edited after the tag


def _read(path: Path) -> str:
    return path.read_text("utf-8").replace("\r\n", "\n")


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_rpt_160_addendum_names_the_campaign_folder_by_its_role():
    """P0390-REV37 (NFR-45 R5): R37-05, the RPT-160 addendum names the folder by role."""
    (path,) = glob.glob(str(ROOT / "reports/RPT-160_*.md"))
    text = _flat(_read(Path(path)))
    assert "probe-campaign working folder" not in text
    assert "folder where the probes of CMP-26125_2026-10-05 ran" in text


def test_the_sims_contract_lives_once_wrapped_in_restore_and_rebuild():
    """P0390-REV37 (NFR-45 R5): R37-06, one home for the 0.39.0 four-command --sims contract."""
    live = [p for p in DOCS.rglob("*.md") if not p.match(FROZEN)]
    homes = [p.name for p in live if CONTRACT in _flat(_read(p))]
    assert homes == ["restore-and-rebuild.md"]
    assert not [p.name for p in live if OLD_SENTENCE in _flat(_read(p))]
    page = _read(DOCS / "restore-and-rebuild.md")
    opening = "All four commands (`mark-converged`, `mark-failed`, `rebuild`, `delete-sims`) take"
    assert opening in page
    paragraph = (opening + page.split(opening)[1].split("\n\n")[0]).splitlines()
    assert len(paragraph) >= 2 and all(len(ln) <= 100 for ln in paragraph)
    assert "(restore-and-rebuild.md)" in _read(DOCS / "migrating-to-0.37.0.md")


def test_the_frozen_0_37_0_page_is_the_page_the_tag_published():
    """P0390-REV37 (NFR-45 R5): R37-06, a frozen migrating-to record keeps the bytes of its tag."""
    tagged = subprocess.run(
        ["git", "show", "v0.37.0:docs/migrating-to-0.37.0.md"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        env={key: os.environ[key] for key in _GIT_ENV_KEYS if key in os.environ},
    )
    if tagged.returncode != 0:
        pytest.skip("the v0.37.0 tag is not in this checkout")
    current = (DOCS / "migrating-to-0.37.0.md").read_bytes()
    assert current.replace(b"\r\n", b"\n") == tagged.stdout.replace(b"\r\n", b"\n")


def test_the_fr_414_changelog_entry_says_a_quoted_pair_is_two_ids():
    """P0390-REV37 (NFR-45 R5): R37-07, the FR-414 entry states the quoted '2006 2007' reading."""
    text = _read(ROOT / "CHANGELOG.md")
    entry = re.search(r"- `pyfs-matrix mark-converged.*?\(FR-414\)\.", text, re.S)
    assert entry is not None
    flat = _flat(entry.group(0))
    assert '`"2006 2007"` is read as two ids' in flat


def test_the_s6_hash_is_documented_as_separator_folded_and_the_file_line_is_native():
    """P0390-REV37 (NFR-45 R5): R37-10, comment, docstring, FR-341 R3 and the native assertion."""
    source = _read(S6_TEST)
    comment = source.split("MAPPED_SCRIPT_SHA256 =")[0].rsplit("\n\n", 1)[-1]
    assert "SEPARATOR-FOLDED" in comment
    docstring = source.split("def test_a_row_that_chooses_no_route_is_byte_identical")[1]
    assert "separator-folded render" in docstring.split('"""')[1]
    native = 'assert f"FILE TMP{os.sep}blade.obj" in masked.splitlines()'
    body = docstring
    assert native in body and body.index(native) < body.index("fold_separators(masked)")
    srs = _flat(_read(ROOT / FUNCTIONAL_REQUIREMENTS))
    assert "The comparison of the rendered script is separator-folded" in srs


def test_the_grid_recovery_limit_of_a_pole_fan_tube_is_in_the_0_38_changelog():
    """P0390-REV37 (NFR-45 R5): IND4-01 and PUSH-IND3-QA-3, the owed Known limitations line."""
    text = _read(ROOT / "CHANGELOG.md")
    section = text.split("## [0.38.0]")[1].split("\n## [")[0]
    limits = section.split("### Known limitations")[1].split("\n### ")[0]
    flat = _flat(limits)
    assert "closed at both ends by pole fans" in flat
    assert "shared by more than two nodes" in flat
    assert "5 on split cells" in flat
    assert "remeshed, never refined as a wrong grid" in flat
