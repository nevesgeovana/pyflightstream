"""The public tree carries no executable digest of a user's machine (NFR-31).

The solver build identifies the executable (FlightStream 26.124 is build
8172026); the SHA-256 of the executable a run used stays in that run's record
on the machine that ran it. This guard scans every tracked text file for
64-character hexadecimal tokens and refuses any whose own SHA-256 is a
withheld digest's. It compares digests of digests, so the guard never carries
the value it refuses, in any form.

A control proves the scan can find what it refuses: it plants a different
64-hex token in a temporary copy of a tracked file and points the constant at
that token's digest. The unmutated copy passes and the planted one is found,
in both cases of hexadecimal letters.
"""

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: SHA-256 (of the lowercase token, UTF-8) of each executable digest the
#: public tree withholds. The digests themselves are never written here.
WITHHELD_DIGESTS = frozenset({"9befdea3801ebe353c647118c0f5c33ec9462215cb59475744bce3bb2905ed50"})

#: A run of hexadecimal characters at least one digest long. A longer run is
#: scanned at every offset, so a digest glued to other hex is still found.
HEX_RUN = re.compile(r"[0-9A-Fa-f]{64,}")

#: Fewer files read than this means the scan did not see the tree.
FILES_READ_FLOOR = 1000


def _tracked() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, (
        f"git could not list the tracked files (exit {result.returncode}: "
        f"{result.stderr.strip()}); an unscanned tree must not read as a clean one"
    )
    return [ROOT / name for name in result.stdout.split("\0") if name]


def _withheld_tokens(text: str) -> list[str]:
    digests = sys.modules[__name__].WITHHELD_DIGESTS
    found = []
    for run in HEX_RUN.finditer(text):
        value = run.group().lower()
        for start in range(len(value) - 63):
            token = value[start : start + 64]
            if hashlib.sha256(token.encode("utf-8")).hexdigest() in digests:
                found.append(token)
    return found


def scan(paths: list[Path]) -> tuple[list[str], int]:
    """Return the files carrying a withheld digest, and how many text files were read."""
    offenders, read = [], 0
    for path in paths:
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue  # binary
        read += 1
        if _withheld_tokens(data.decode("utf-8", errors="ignore")):
            offenders.append(path.as_posix())
    return offenders, read


def test_no_tracked_text_file_carries_a_withheld_executable_digest():
    # P0330-NO-EXE-HASH: every tracked text file, scanned for the withheld digest.
    offenders, read = scan(_tracked())
    assert read >= FILES_READ_FLOOR, (
        f"the scan read {read} tracked text files, below the floor of {FILES_READ_FLOOR}; "
        "a scan that reads nothing reports green over an unscanned tree"
    )
    assert offenders == [], (
        f"these tracked files carry a withheld executable digest: {offenders}. The public "
        "tree identifies the executable by its solver build (NFR-31); state the build, and "
        "write a digest field as 'withheld; build <build>'"
    )


def test_the_scan_finds_a_planted_digest_and_passes_the_unmutated_copy(tmp_path, monkeypatch):
    # P0330-NO-EXE-HASH: the mutant control, with a different token and its digest.
    token = hashlib.sha256(b"P0330-NO-EXE-HASH planted control").hexdigest()
    monkeypatch.setattr(
        sys.modules[__name__],
        "WITHHELD_DIGESTS",
        frozenset({hashlib.sha256(token.encode("utf-8")).hexdigest()}),
    )
    source = ROOT / "reports" / "RPT-032_executable-identity-baseline_2026-08-19.md"
    text = source.read_text(encoding="utf-8")
    clean = tmp_path / "clean.md"
    clean.write_text(text, encoding="utf-8")
    assert scan([clean]) == ([], 1)
    lower = tmp_path / "lower.md"
    lower.write_text(text.replace("withheld; build 8172026", f"`{token}`", 1), encoding="utf-8")
    upper = tmp_path / "upper.yaml"
    upper.write_text(f"fs_exe_sha256: {token.upper()}\n", encoding="utf-8")
    glued = tmp_path / "glued.txt"
    glued.write_text(f"ab{token}cd\n", encoding="utf-8")
    offenders, read = scan([clean, lower, upper, glued])
    assert read == 4
    assert [Path(name).name for name in offenders] == ["lower.md", "upper.yaml", "glued.txt"]
    assert token not in text


def test_the_guard_carries_no_withheld_digest_itself():
    # P0330-NO-EXE-HASH: the guard's own source holds only digests of digests.
    own = Path(__file__).read_text(encoding="utf-8")
    assert _withheld_tokens(own) == []
    assert all(len(value) == 64 for value in WITHHELD_DIGESTS)
