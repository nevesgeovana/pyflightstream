"""P0400-WSCLEAN: a geometry clean whose write is refused (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyflightstream.workspace.inputs import InputArtifactError, clean_saved_actions
from tests.tier1_offline.test_fr312_inventory_clean import TIER3, _dirty, _text

pytestmark = pytest.mark.requirement("P0400-WSCLEAN")


def test_p0400_wsclean_a_held_file_is_a_refusal_and_leaves_no_temporary(tmp_path, monkeypatch):
    """P0400-WSCLEAN (PFS-2099.012): a refused replace names the file and leaves no .tmp."""
    target = tmp_path / "10_WING.fsm"
    target.write_bytes(_dirty(_text(TIER3 / "10_WING.fsm")).encode("latin-1"))
    before = target.read_bytes()
    real = os.replace

    def held(source, destination, *args, **kwargs):
        if Path(destination) == target:
            raise PermissionError(13, "The process cannot access the file", str(target))
        return real(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", held)
    with pytest.raises(InputArtifactError, match="10_WING.fsm"):
        clean_saved_actions(target, stamp="20261012-000000")
    assert target.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_p0400_wsclean_a_refused_cleanup_is_named_in_the_same_error_class(tmp_path, monkeypatch):
    """P0400-WSCLEAN (PFS-2099.012): a held temporary file never leaks a raw OSError."""
    target = tmp_path / "10_WING.fsm"
    target.write_bytes(_dirty(_text(TIER3 / "10_WING.fsm")).encode("latin-1"))
    before = target.read_bytes()
    real_unlink = Path.unlink

    def held_replace(source, destination, *args, **kwargs):
        raise PermissionError("geometry held")

    def held_unlink(path, *args, **kwargs):
        if path.name.endswith(".tmp"):
            raise PermissionError("temporary held")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "replace", held_replace)
    monkeypatch.setattr(Path, "unlink", held_unlink)
    with pytest.raises(InputArtifactError, match="temporary file.*could not be removed"):
        clean_saved_actions(target, stamp="20261012-000000")
    assert target.read_bytes() == before
