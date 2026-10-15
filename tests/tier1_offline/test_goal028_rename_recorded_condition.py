"""Tier 1: a record is named by the condition IT ran at, never by today's row (0.24.0).

RENAME-CURRENT-CONDITION. The rename built its naming case from the CURRENT
matrix row, and its "the matrix changed since the run" check compared the point
tags alone. A fixed Mach number edited after the run therefore passed the
check, and a record that ran at Mach 0.2 was renamed ``M100...`` because the
row says 0.1 today: historical evidence relabeled with a condition it never
saw, in its folder, its files and its manifest row.

The requirement: the name describes the RECORDED condition, and a row that
disagrees with a record is refused BY NAME (which record, which variable, both
values) with the workspace untouched.

Expected names are written from the approved naming table (Mach x 1000 in three
digits, REmi x 100, alpha x 10 signed), never read off the renamer.
"""

from __future__ import annotations

from pyflightstream.workspace import CampaignWorkspace


def _tree(workspace: CampaignWorkspace) -> dict[str, bytes | None]:
    """Return every path under the workspace root with its bytes (None for a folder)."""
    root = workspace.root
    return {
        path.relative_to(root).as_posix(): (path.read_bytes() if path.is_file() else None)
        for path in sorted(root.rglob("*"))
    }


def _edit(matrix, before: str, after: str) -> None:
    text = matrix.read_text(encoding="utf-8")
    assert text.count(before) == 1, (before, text.count(before))
    matrix.write_text(text.replace(before, after), encoding="utf-8")
