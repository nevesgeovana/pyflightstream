"""Retained runtime, privacy and link checks, with shared test support."""

import hashlib
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


WITHDRAWN_DIGESTS = frozenset(
    {
        "d93125dbc131d47f14803547e9f1db94d5969a9cf8001c56e5fb81b47926863b",
        "0f608a31f7262521adfd5d50d28b666a5c15b02e496c5435607ec2865988bf6f",
        "4a703dad98bd1766f813b9c6fb60fc8dc641de8989d2e41e717a1a14b0b4c81e",
        "bc069fc5d097f6a15722568bb2d4c1c91972c6c16f42522218c5aab0f8e80a86",
    }
)


FILE_NAMES = (
    "user manual, pdf",
    "user manual, chm",
    "2026.1 release notes, pdf",
    "eula, pdf",
)


HEX_RUN = re.compile(r"[0-9A-Fa-f]{64,}")


HEX_TOKEN = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")


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
    """P0340-VENDOR-DIGESTS, FR-688: the tracked tree is clean."""
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
    assert not offenders, "\n".join(offenders)


def test_the_guard_refuses_a_withdrawn_digest_and_a_named_line():
    """P0340-VENDOR-DIGESTS, FR-688: a planted digest and a planted line are found."""
    sample = hashlib.sha256(b"P0340-VENDOR-DIGESTS a planted digest").hexdigest()
    withdrawn = frozenset({hashlib.sha256(sample.encode("utf-8")).hexdigest()})
    assert _offences("clean prose, no value here\n", withdrawn) == []
    assert _offences(f"| a row | `{sample}` |\n", withdrawn)
    assert _offences(f"glued 0{sample}f to other hex\n", withdrawn)
    other = hashlib.sha256(b"P0340-VENDOR-DIGESTS another value").hexdigest()
    for name in ("User Manual, PDF", "user manual, chm", "2026.1 Release Notes, pdf", "EULA, pdf"):
        assert _offences(f"| {name} | `{other}` | the same |\n"), name


def test_the_guard_keeps_its_negative_controls():
    """P0340-VENDOR-DIGESTS, FR-688: a commit id and an unrelated name pass."""
    commit = hashlib.sha1(b"P0340-VENDOR-DIGESTS a commit").hexdigest()
    assert len(commit) == 40
    other = hashlib.sha256(b"P0340-VENDOR-DIGESTS an unrelated value").hexdigest()
    assert _offences(f"EULA, pdf measured at commit {commit}\n") == []
    assert _offences(f"user manual, pdf at {commit}\n") == []
    assert _offences(f"| some other file, pdf | `{other}` | the same |\n") == []
    assert _offences(f"`CompGeom.dll` {other}\n") == []
