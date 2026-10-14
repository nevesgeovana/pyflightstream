"""P0400-RECOUNTGREEN (PFS-2135.052): mypy_recount states no headline it has just refused.

The shipped-configuration run "must be green" by the docstring and was only
printed; a count that disagreed with the tracked modules printed "do not
state either number" and then the bold headline stating them, exiting 0. Both
now exit 1 with no headline. mypy itself is replaced by canned final lines.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "mypy_recount_p0400", REPO / "scripts" / "mypy_recount.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("shipped", "extra", "code"),
    [
        ("Found 2 errors in 1 file (checked {n} source files)", 0, 1),
        ("Success: no issues found in {n} source files", 1, 1),
        ("Success: no issues found in {n} source files", 0, 0),
    ],
    ids=["shipped-red", "count-mismatch", "control"],
)
def test_p0400_recountgreen_a_refusal_states_no_headline(
    monkeypatch, capsys, shipped: str, extra: int, code: int
) -> None:
    """P0400-RECOUNTGREEN: red shipped run or mismatched count exits 1 without the headline."""
    module = _load()
    n = 2

    def git_result(argv, **kwargs):
        if argv == ["git", "ls-tree", "-r", "HEAD", "--name-only", "src/pyflightstream"]:
            return subprocess.CompletedProcess(
                argv, 0, "src/pyflightstream/x.py\nsrc/pyflightstream/y.py\n"
            )
        assert argv == ["git", "status", "--short"]
        return subprocess.CompletedProcess(argv, 0, "")

    monkeypatch.setattr(module, "subprocess", SimpleNamespace(run=git_result))
    bare = f"Found 1 error in 1 file (checked {n + extra} source files)"
    finding = "src/pyflightstream/x.py:1: error: wrong [arg-type]"

    def run_mypy(config):
        return ([finding], bare) if config is not None else ([], shipped.format(n=n))

    monkeypatch.setattr(module, "_run_mypy", run_mypy)
    monkeypatch.setattr(sys, "argv", ["mypy_recount.py"])
    assert module.main() == code
    assert ("**mypy recount" in capsys.readouterr().out) is (code == 0)
