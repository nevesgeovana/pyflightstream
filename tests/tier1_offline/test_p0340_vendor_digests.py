"""No tracked file carries a digest of the solver package's documentation (FR-344).

Marker P0340-VENDOR-DIGESTS. The digests of the vendor's user manual (pdf and
chm), release notes and licence agreement identify files this repository does
not need to publish; the private corpus keeps the manual's digest. This guard
reads every tracked text file and refuses two shapes:

1. A withdrawn digest anywhere, compared by the SHA-256 of its lowercase form,
   so this file never carries the value it refuses. A longer hexadecimal run is
   scanned at every offset, so a digest glued to other hex is still found.
2. A line holding a token of exactly 64 hexadecimal digits together with the
   name of one of the four files as RPT-050 records it (case folded). A
   40-hex commit id beside such a name, and a 64-hex value beside a name that
   is not one of the four, are not refused.

Past commits are not rewritten: the digests stay in the history and only the
tree from 0.34.0 on is clean (FR-344 R4). The controls plant each shape.
"""

import hashlib
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: SHA-256 (of the lowercase token, UTF-8) of each digest RPT-050 once recorded
#: for the manual pdf, the manual chm, the release notes and the licence
#: agreement. The digests themselves are never written here.
WITHDRAWN_DIGESTS = frozenset(
    {
        "d93125dbc131d47f14803547e9f1db94d5969a9cf8001c56e5fb81b47926863b",
        "0f608a31f7262521adfd5d50d28b666a5c15b02e496c5435607ec2865988bf6f",
        "4a703dad98bd1766f813b9c6fb60fc8dc641de8989d2e41e717a1a14b0b4c81e",
        "bc069fc5d097f6a15722568bb2d4c1c91972c6c16f42522218c5aab0f8e80a86",
    }
)

#: The four files as RPT-050's table names them, case folded.
FILE_NAMES = (
    "user manual, pdf",
    "user manual, chm",
    "2026.1 release notes, pdf",
    "eula, pdf",
)

HEX_RUN = re.compile(r"[0-9A-Fa-f]{64,}")
HEX_TOKEN = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")

#: Fewer files read than this means the scan did not see the tree.
FILES_READ_FLOOR = 1000

RPT_050 = next((ROOT / "reports").glob("RPT-050_*.md"))
NFR_PAGE = ROOT / "docs" / "srs" / "nonfunctional-requirements.md"


def _tracked() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, (
        f"git could not list the tracked files (exit {result.returncode}: "
        f"{result.stderr.strip()}); an unscanned tree must not read as a clean one"
    )
    return [ROOT / name for name in result.stdout.split("\0") if name]


def _offences(text: str, digests: frozenset[str] = WITHDRAWN_DIGESTS) -> list[str]:
    found = []
    for run in HEX_RUN.finditer(text):
        value = run.group().lower()
        for start in range(len(value) - 63):
            token = value[start : start + 64]
            if hashlib.sha256(token.encode("utf-8")).hexdigest() in digests:
                found.append(f"a withdrawn digest at offset {run.start() + start}")
    for number, line in enumerate(text.splitlines(), start=1):
        folded = line.casefold()
        if HEX_TOKEN.search(line) and any(name in folded for name in FILE_NAMES):
            found.append(f"a 64-hex value beside a documentation file name, line {number}")
    return found


def test_no_tracked_file_carries_a_documentation_digest():
    """P0340-VENDOR-DIGESTS, FR-344 R2: the tracked tree is clean."""
    files = _tracked()
    offenders = []
    read = 0
    for path in files:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        read += 1
        for offence in _offences(text):
            offenders.append(f"{path.relative_to(ROOT).as_posix()}: {offence}")
    assert read >= FILES_READ_FLOOR, f"only {read} tracked text files were read"
    assert not offenders, "\n".join(offenders)


def test_the_guard_refuses_a_withdrawn_digest_and_a_named_line():
    """P0340-VENDOR-DIGESTS, FR-344 R2: a planted digest and a planted line are found."""
    sample = hashlib.sha256(b"P0340-VENDOR-DIGESTS a planted digest").hexdigest()
    withdrawn = frozenset({hashlib.sha256(sample.encode("utf-8")).hexdigest()})
    assert _offences("clean prose, no value here\n", withdrawn) == []
    assert _offences(f"| a row | `{sample}` |\n", withdrawn)
    assert _offences(f"glued 0{sample}f to other hex\n", withdrawn)
    other = hashlib.sha256(b"P0340-VENDOR-DIGESTS another value").hexdigest()
    for name in ("User Manual, PDF", "user manual, chm", "2026.1 Release Notes, pdf", "EULA, pdf"):
        assert _offences(f"| {name} | `{other}` | the same |\n"), name


def test_the_guard_keeps_its_negative_controls():
    """P0340-VENDOR-DIGESTS, FR-344 R2: a commit id and an unrelated name pass."""
    commit = hashlib.sha1(b"P0340-VENDOR-DIGESTS a commit").hexdigest()
    assert len(commit) == 40
    other = hashlib.sha256(b"P0340-VENDOR-DIGESTS an unrelated value").hexdigest()
    assert _offences(f"EULA, pdf measured at commit {commit}\n") == []
    assert _offences(f"user manual, pdf at {commit}\n") == []
    assert _offences(f"| some other file, pdf | `{other}` | the same |\n") == []
    assert _offences(f"`CompGeom.dll` {other}\n") == []


def test_rpt_050_withholds_the_four_digests_with_a_dated_amendment():
    """P0340-VENDOR-DIGESTS, FR-344 R1: each row keeps file, size and reading."""
    text = RPT_050.read_text(encoding="utf-8")
    amendments = re.findall(r"Amended (\d{4}-\d{2}-\d{2}):((?:(?!Amended )[^\n])*)", text)
    dated = [date for date, line in amendments if "FR-344" in line]
    assert dated, "RPT-050 carries no amendment line naming FR-344"
    assert all(date >= "2026-10-01" for date in dated), dated
    rows = {}
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].casefold() in FILE_NAMES:
            rows[cells[0].casefold()] = cells
    assert sorted(rows) == sorted(FILE_NAMES), sorted(rows)
    for name, (_, older, newer, size) in rows.items():
        assert "withheld" in older and "FR-344" in older, name
        assert newer == "the same", name
        assert size.isdigit(), name


def test_nfr_31_r1_points_to_fr_344_instead_of_excluding_the_documentation():
    """P0340-VENDOR-DIGESTS, FR-344 R5: the amendment of NFR-31 R1 landed."""
    text = " ".join(NFR_PAGE.read_text(encoding="utf-8").split())
    start = text.index('requirement "NFR-31')
    end = text.index('requirement "NFR-32', start)
    box = text[start:end]
    old = (
        "The digests of the package's documentation (manual, release notes, licence agreement) "
        "are not covered."
    )
    assert old not in box
    assert "documentation (manual, release notes, licence agreement)" in box
    assert "FR-344" in box
