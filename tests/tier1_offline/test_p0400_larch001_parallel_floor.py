"""LARCH-001 (0.40.0 architect lens): without psutil the geometry build runs serially, saying why.

psutil is not a dependency of the package (NFR-06). Before the fix the memory check
answered True when it could not measure, so ``--parallel 2`` started a second solver
run on an unmeasured machine.
"""

from __future__ import annotations

import builtins

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.workspace import _geometry_build as build


def test_larch001_an_unmeasurable_memory_floor_runs_the_builds_serially(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With psutil absent the check answers False and warns, naming psutil and the floor."""
    real_import = builtins.__import__

    def no_psutil(name: str, *args: object, **kwargs: object) -> object:
        if name == "psutil":
            raise ImportError("No module named 'psutil'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", no_psutil)
    with pytest.warns(PyflightstreamWarning, match="psutil"):
        assert build._room_for_a_second_run() is False
