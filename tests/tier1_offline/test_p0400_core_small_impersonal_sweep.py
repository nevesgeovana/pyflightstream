"""P0400-SWEEPGONE (PFS-2135.049): the dead pronoun sweep is removed, not left to be run.

scripts/impersonal_sweep.py was referenced by nothing, defined its
FORBIDDEN_MATCHES guard after the ``__main__`` block where nothing applied it,
rewrote every touched file to CRLF on Windows under ``--write``, and turned an
objective "her" into a possessive. A script with a write mode and no guard is
a hazard to whoever finds it, so it is deleted rather than repaired.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_p0400_sweepgone_the_script_is_not_shipped() -> None:
    """P0400-SWEEPGONE: scripts/ carries no impersonal_sweep.py."""
    assert not (REPO / "scripts" / "impersonal_sweep.py").exists()
