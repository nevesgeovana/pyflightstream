"""Tier 1: the scorer every mutation battery trusts.

Pipeline role: quality gate on the guards' own instrument.
``scripts/_mutation_harness.py`` decides whether a mutant was KILLED, and
whether an anchor is safe to apply, for every battery under ``scripts/``.
Nothing under ``tests/`` referenced it until 2026-08-18, so a defect in
either function would have mis-scored every mutation claim this
repository makes, silently and in the reassuring direction.

The two functions are exactly the ones written to remove real defects:

* ``verdict`` exists because four batteries read a kill off any non-zero
  exit. pytest exits 1 on a failure, 2 on a collection or import error, 4
  on a usage error and 5 when the selection matched no test; only the
  first is a guard denying, and a battery whose test id has drifted gets
  exit 5 on every mutant and prints "N of N mutants killed".
* ``apply_mutant`` exists because a drifted anchor replaces nothing, so
  the battery measures the UNMUTATED tree, and because several files here
  are CRLF on disk where a line-feed anchor matches nothing at all.

Every case below drives the real function against a throwaway tree, so
this is a test of the instrument rather than a restatement of it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from _mutation_harness import apply_mutant, verdict  # noqa: E402

_PASSING = "def test_ok():\n    assert True\n"
_FAILING = "def test_no():\n    assert False\n"
_UNIMPORTABLE = "import a_module_that_does_not_exist_anywhere\n\n\ndef test_never():\n    pass\n"
_NO_TESTS = "x = 1\n"


def _write(tmp_path: Path, body: str) -> str:
    """Write a throwaway test module and return its path for pytest."""
    path = tmp_path / "test_throwaway.py"
    path.write_text(body, encoding="utf-8")
    return str(path)


@pytest.mark.parametrize(
    ("body", "expected", "why"),
    [
        (_FAILING, "KILLED", "a failing test is the guard denying, the only real kill"),
        (_PASSING, "SURVIVED", "a passing test is the guard letting the mutant through"),
        (
            _UNIMPORTABLE,
            "INCONCLUSIVE",
            "a collection error is pytest exit 2 and proves nothing about the guard",
        ),
        (
            _NO_TESTS,
            "INCONCLUSIVE",
            "no test selected is pytest exit 5, the trap a renamed guard falls into",
        ),
    ],
)
def test_verdict_reads_the_four_outcomes_a_battery_can_meet(tmp_path, body, expected, why):
    outcome, tail = verdict(_write(tmp_path, body))
    assert outcome == expected, f"{why}; got {outcome} ({tail})"


def test_verdict_refuses_a_selector_that_matches_nothing(tmp_path):
    """The failure mode with the worst consequence, driven directly.

    A battery selects its guard by node id. Rename the guard and the id
    stops resolving; pytest exits 4 or 5, both non-zero, and a
    two-valued scorer reports every mutant killed while judging none.
    """
    module = _write(tmp_path, _PASSING)
    outcome, tail = verdict(f"{module}::test_this_name_does_not_exist")
    assert outcome == "INCONCLUSIVE", (
        f"a drifted node id scored as {outcome}, so a battery whose guard was renamed "
        f"would publish a tally over mutants nothing judged ({tail})"
    )


def test_apply_mutant_refuses_an_anchor_that_is_absent(tmp_path):
    target = tmp_path / "subject.py"
    target.write_text("alpha = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit) as refused:
        apply_mutant(target, "beta = 1\n", "beta = 2\n")
    assert "0 times" in str(refused.value), str(refused.value)


def test_apply_mutant_refuses_an_anchor_that_appears_twice(tmp_path):
    """Uniqueness, not just presence.

    An anchor matching twice replaces both, so the mutant is not the one
    the table describes and the label is a lie about what was measured.
    """
    target = tmp_path / "subject.py"
    target.write_text("alpha = 1\nbeta = 2\nalpha = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit) as refused:
        apply_mutant(target, "alpha = 1\n", "alpha = 9\n")
    assert "2 times" in str(refused.value), str(refused.value)


def test_apply_mutant_refuses_a_mutation_that_changes_nothing(tmp_path):
    target = tmp_path / "subject.py"
    target.write_text("alpha = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        apply_mutant(target, "alpha = 1\n", "alpha = 1\n")


def test_apply_mutant_translates_a_line_feed_anchor_onto_a_crlf_target(tmp_path):
    """The property that makes a battery reproducible on a fresh clone.

    Several files here are CRLF on disk, and on a checkout with
    `autocrlf` on all of them are. A battery writes its anchors with line
    feeds, so without this translation the anchor matches nothing and the
    battery aborts on every mutant, which is what one of them did.
    """
    target = tmp_path / "subject.py"
    target.write_bytes(b"alpha = 1\r\nbeta = 2\r\n")
    mutated = apply_mutant(target, "alpha = 1\n", "alpha = 9\n")
    assert mutated == b"alpha = 9\r\nbeta = 2\r\n", mutated
    assert target.read_bytes() == b"alpha = 1\r\nbeta = 2\r\n", (
        "apply_mutant wrote to the file; it must RETURN the mutated bytes and leave "
        "the caller to park the original first"
    )


def test_the_harness_imports_nothing_from_the_package():
    """The layer rule its own docstring states, held to.

    "Nothing in src/ imports this, and nothing here imports src." A
    harness that imported the package would make a mutant of the package
    able to break the instrument measuring it.
    """
    source = (REPO_ROOT / "scripts" / "_mutation_harness.py").read_text(encoding="utf-8")
    assert "pyflightstream" not in source, (
        "the mutation harness references the package it is used to mutate"
    )
    grep = subprocess.run(
        ["git", "grep", "-l", "_mutation_harness", "--", "src"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        # Explicit, and identical to the inherited default: git needs the
        # ambient environment to find its own configuration.
        env=os.environ.copy(),
    )
    assert not grep.stdout.strip(), f"src/ imports the mutation harness: {grep.stdout}"
