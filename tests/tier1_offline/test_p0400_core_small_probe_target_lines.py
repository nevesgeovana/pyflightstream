"""P0400-PRELUDEBUCKET (PFS-2135.051): only a reference refusal is filed as needing a prelude.

measure_probe_target_lines caught every Exception under ``needs_prelude``, so a
TypeError in a specification read as a missing prelude. A ScriptReferenceError
is still ``needs_prelude``; anything else goes to its own bucket, named with its
type.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from pyflightstream.script.entities import ScriptReferenceError

REPO = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "measure_probe_target_lines_p0400", REPO / "scripts" / "measure_probe_target_lines.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _raising(error: Exception) -> SimpleNamespace:
    def build_target(script, workdir):
        raise error

    return SimpleNamespace(build_target=build_target)


def test_p0400_preludebucket_a_spec_defect_is_not_a_missing_prelude(monkeypatch) -> None:
    """P0400-PRELUDEBUCKET: a TypeError lands in raised_something_else, a reference in prelude."""
    module = _load()
    specs = {
        "CITES_A_FRAME": _raising(ScriptReferenceError("frame 2 was never created")),
        "BAD_SPEC": _raising(TypeError("build_target() takes 1 argument")),
    }
    monkeypatch.setattr(module, "PROBE_SPECS", specs)
    groups = module.classify()
    assert groups["needs_prelude"] == ["CITES_A_FRAME"]
    assert groups["raised_something_else"] == ["BAD_SPEC (TypeError)"]
