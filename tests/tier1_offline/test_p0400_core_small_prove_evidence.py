"""Retained runtime, privacy and link checks, with shared test support."""

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
