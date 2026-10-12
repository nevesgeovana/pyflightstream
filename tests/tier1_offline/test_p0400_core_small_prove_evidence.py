"""P0400-EVIDENCEBATTERY: scripts/prove_evidence_guards.py can pass, and scores by exit code.

P0400-EVIDENCEBATTERY-ANCHOR (PFS-2135.078): the motion-prelude mutant
anchored on qa/specs.py after the prelude moved to qa/_spec_catalog_b.py, so
the battery recorded an ANCHOR MISS and could never pass; nothing in tier 1 ran
it. Every mutant's anchor is now held here to exactly one match in its file,
the check the battery makes before it mutates anything.

P0400-EVIDENCEBATTERY-SCORE (PFS-2135.053): run() scored a selection from its
output text alone, so "3 passed, 1 error" (a fixture error, exit 1) read as
passed. score() reads the exit code first.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "prove_evidence_guards_p0400", REPO / "scripts" / "prove_evidence_guards.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p0400_evidencebattery_anchor_every_mutant_anchors_once() -> None:
    """P0400-EVIDENCEBATTERY-ANCHOR: each anchor appears exactly once, line ends normalised."""
    counts = {}
    for label, rel, old, *_ in _load().MUTANTS:
        text = (REPO / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")
        counts[label] = text.count(old)
    assert {label: n for label, n in counts.items() if n != 1} == {}


@pytest.mark.parametrize(
    ("returncode", "summary", "expected"),
    [
        (1, "3 passed, 1 error in 0.5s", "INCONCLUSIVE"),
        (2, "1 error in 0.5s", "INCONCLUSIVE"),
        (5, "no tests ran in 0.1s", "INCONCLUSIVE"),
        (1, "1 failed, 2 passed in 0.5s", "FAILED"),
        (0, "3 passed in 0.5s", "passed"),
    ],
)
def test_p0400_evidencebattery_score_reads_the_exit_code(
    returncode: int, summary: str, expected: str, monkeypatch
) -> None:
    """P0400-EVIDENCEBATTERY-SCORE: an error beside passes is inconclusive, not passed."""
    module = _load()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=returncode, stdout=summary, stderr=""),
    )
    assert module.run("test_guard.py", "selection")[0] == expected
