"""Tier 1: no tracked file carries the control plane's private provenance header.

The public repository and every distribution built from it describe the package,
not how it was produced. A header block naming the producing agents and the
private control plane was added to 194 tracked files during the 0.29.0 cycle and
removed before the release; this walks the tracked tree so it cannot return.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ("GEOVERSE_HEADER", "geoverse-goddess-control-plane", "_geoverse_header")


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return [ROOT / p.decode("utf-8") for p in out.split(b"\0") if p]


def test_no_tracked_file_carries_the_private_provenance_header():
    offenders = []
    for path in _tracked_files():
        if path.resolve() == Path(__file__).resolve() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        offenders.extend(f"{path.relative_to(ROOT)}: {word}" for word in FORBIDDEN if word in text)
    assert not offenders, "\n".join(offenders)
