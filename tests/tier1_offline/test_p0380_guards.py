"""P0380-GUARDS (NFR-44): the guards command and the separator fold of pinned digests."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

from tests.support_helpers import fold_separators

REPO = Path(__file__).resolve().parents[2]


def _run_guards():
    spec = importlib.util.spec_from_file_location("run_guards", REPO / "scripts" / "run_guards.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_p0380_guards_every_listed_guard_file_exists():
    """P0380-GUARDS (NFR-44 R1): the list names files that are on disk, this one among them."""
    guards = _run_guards()
    assert guards.missing_guards() == []
    assert "tests/tier1_offline/test_p0380_guards.py" in guards.GUARDS
    assert len(set(guards.GUARDS)) == len(guards.GUARDS)


def test_p0380_guards_a_missing_guard_file_exits_2(monkeypatch, capsys):
    """P0380-GUARDS (NFR-44 R1): a listed file not on disk makes the command exit 2, naming it."""
    guards = _run_guards()
    absent = "tests/tier1_offline/test_p0380_not_a_guard.py"
    monkeypatch.setattr(guards, "GUARDS", (*guards.GUARDS, absent))
    assert guards.main([]) == 2
    assert absent in capsys.readouterr().out


def test_p0380_guards_a_failing_guard_exits_1_and_is_named(tmp_path, monkeypatch, capsys):
    """P0380-GUARDS (NFR-44 R1): a failing guard, or one that ran no test, exits 1 naming its file.

    The shipped command line runs (with pytest-xdist), and the red test sits in
    a test class, the case whose junit class name is longer than its module.
    """
    guards = _run_guards()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_green.py").write_text("def test_green():\n    assert True\n", "utf-8")
    (tests_dir / "test_red.py").write_text(
        "class TestRed:\n    def test_red(self):\n        assert False\n", "utf-8"
    )
    (tests_dir / "test_empty.py").write_text("X = 1\n", "utf-8")
    monkeypatch.setattr(guards, "ROOT", tmp_path)
    monkeypatch.setattr(
        guards, "GUARDS", ("tests/test_green.py", "tests/test_red.py", "tests/test_empty.py")
    )
    assert guards.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL    tests/test_red.py (1: test_red)" in out
    assert "PASS    tests/test_green.py" in out
    assert "NOT RUN tests/test_empty.py" in out
    assert "guards: RED" in out


def test_p0380_guards_green_only_when_every_guard_ran_and_passed(tmp_path, monkeypatch, capsys):
    """P0380-GUARDS (NFR-44 R1), control: the same command on green guards exits 0."""
    guards = _run_guards()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_green.py").write_text("def test_green():\n    assert True\n", "utf-8")
    monkeypatch.setattr(guards, "ROOT", tmp_path)
    monkeypatch.setattr(guards, "GUARDS", ("tests/test_green.py",))
    assert guards.main([]) == 0
    assert "guards: green" in capsys.readouterr().out


@pytest.mark.parametrize(
    "text", ["run TMP\\sims\\a.fsm then TMP\\b.txt", "run TMP/sims/a.fsm then TMP/b.txt"]
)
def test_p0380_guards_the_fold_gives_one_digest_for_either_separator(text):
    """P0380-GUARDS (NFR-44 R2): the same text with either separator hashes to one value."""
    digest = hashlib.sha256(fold_separators(text).encode("utf-8")).hexdigest()
    assert digest == hashlib.sha256(b"run TMP/sims/a.fsm then TMP/b.txt").hexdigest()


def test_p0380_guards_the_fold_is_needed():
    """P0380-GUARDS (NFR-44 R2), control: without the fold the two spellings hash apart."""
    a, b = "TMP\\sims\\a.fsm", "TMP/sims/a.fsm"
    assert hashlib.sha256(a.encode()).hexdigest() != hashlib.sha256(b.encode()).hexdigest()
    assert fold_separators(a) == b  # the Linux half of R2 is the CI run of this file


def test_p0380_guards_a_guard_that_ran_no_test_is_red(tmp_path, monkeypatch, capsys):
    """P0380-GUARDS (NFR-44 R1): a guard file that collects nothing turns a green run red."""
    guards = _run_guards()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_green.py").write_text("def test_green():\n    assert True\n", "utf-8")
    (tests_dir / "test_empty.py").write_text("X = 1\n", "utf-8")
    monkeypatch.setattr(guards, "ROOT", tmp_path)
    monkeypatch.setattr(guards, "GUARDS", ("tests/test_green.py", "tests/test_empty.py"))
    assert guards.main([]) == 1
    out = capsys.readouterr().out
    assert "NOT RUN tests/test_empty.py" in out
    assert "guards: RED" in out


def test_p0380_guards_run_four_workers(tmp_path, monkeypatch):
    """P0380-GUARDS (NFR-44 R1): the command runs four pytest workers, never one per CPU.

    One worker per CPU, twenty on the development machine, exhausted its memory
    beside other test runs (2026-10-06).
    """
    guards = _run_guards()
    seen: list[list[str]] = []

    def record(command, **kwargs):
        seen.append(list(command))
        raise SystemExit(0)

    monkeypatch.setattr(guards.subprocess, "run", record)
    with pytest.raises(SystemExit):
        guards.main([])
    command = seen[0]
    assert command[command.index("-n") + 1] == "4"
