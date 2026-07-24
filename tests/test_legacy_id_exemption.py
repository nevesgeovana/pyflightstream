"""Tier 1: the legacy-id grandfather exemption waives ONLY the shape guard.

Adopting the kit plan checker (``check_plan_kit.py``) turns on a real waiver of
the timestamp-id shape guard, which the checker's own docstring names as the
guard against the silent central-counter regression (itaca founding failure
number two). The kit ships a mutation companion, but it never writes a
``legacy_ids.txt``, so the exemption BRANCH the adoption relies on is otherwise
unexercised in this repository's suite. A future kit re-vendor that turned the
exact-string exemption into a prefix match, widened it beyond the shape guard,
or resolved the file by an absolute path would keep the rest of the suite
green while re-opening exactly the regression the guard exists to stop.

This test exercises the vendored checker against throwaway plan directories in
the OS temp dir (never ``_private``), pinning the four boundaries of the
waiver: absent list rejects a counter id; a listed id passes the shape guard;
a listed id still fails the OTHER guards (a missing ``ref``); an unlisted
counter id is still rejected even with a list present (exact match, not
blanket). It complements the kit mutation companion run by test_plan_checker.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECKER = REPO / ".claude" / "tools" / "check_plan_kit.py"

_ENTRY = """\
---
id: {id}
milestone: v0.1
priority: P1
status: open
ref: {ref}
---

A statement of the work.
"""


def _write_entry(plan_dir: Path, entry_id: str, ref: str = "commit abc123") -> None:
    (plan_dir / f"{entry_id}.md").write_text(_ENTRY.format(id=entry_id, ref=ref), encoding="utf-8")


def _run(plan_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(plan_dir)],
        capture_output=True,
        text=True,
    )


def test_a_counter_id_is_rejected_without_a_legacy_list(tmp_path: Path) -> None:
    """Absent legacy_ids.txt means no exemptions: the shape guard fires."""
    _write_entry(tmp_path, "PLN-001")
    done = _run(tmp_path)
    assert done.returncode == 1, done.stdout
    assert "PLN-001" in done.stdout


def test_a_listed_counter_id_passes_the_shape_guard(tmp_path: Path) -> None:
    """A grandfathered id validates when every other guard is satisfied."""
    _write_entry(tmp_path, "PLN-001")
    (tmp_path / "legacy_ids.txt").write_text("PLN-001\n", encoding="utf-8")
    done = _run(tmp_path)
    assert done.returncode == 0, done.stdout


def test_a_listed_id_still_fails_the_other_guards(tmp_path: Path) -> None:
    """The waiver is shape-only: a listed id with no ref is still rejected."""
    _write_entry(tmp_path, "PLN-001", ref="")
    (tmp_path / "legacy_ids.txt").write_text("PLN-001\n", encoding="utf-8")
    done = _run(tmp_path)
    assert done.returncode == 1, done.stdout
    assert "ref" in done.stdout.lower()


def test_an_unlisted_counter_id_is_still_rejected(tmp_path: Path) -> None:
    """Exact-string match, not a prefix: PLN-089 is rejected even with a list.

    This is what keeps the exemption finite and closed to new counter ids.
    """
    _write_entry(tmp_path, "PLN-001")
    _write_entry(tmp_path, "PLN-089")
    (tmp_path / "legacy_ids.txt").write_text("PLN-001\n", encoding="utf-8")
    done = _run(tmp_path)
    assert done.returncode == 1, done.stdout
    assert "PLN-089" in done.stdout
