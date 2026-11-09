"""The named IGES writer is deterministic and carries no account name (PFS-2220, lane G2)."""

from __future__ import annotations

import getpass
import hashlib
import subprocess
import sys
import time

import pytest

from pyflightstream.workspace._iges_write import (
    FIXED_STAMP,
    normalize_global,
    read_iges,
    serialize_iges,
)

_WRITE = (
    "import sys\n"
    "from pyflightstream.workspace._gmsh import session\n"
    "from pyflightstream.workspace._iges_write import write_iges\n"
    "with session('test') as g:\n"
    "    t = g.model.occ.addRectangle(0, 0, 0, 1, 2)\n"
    "    g.model.occ.synchronize()\n"
    "    write_iges(g, {'PANEL': [t]}, sys.argv[1])\n"
)


def _write_in_fresh_process(path):
    done = subprocess.run(
        [sys.executable, "-c", _WRITE, str(path)], capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stderr[-400:]
    return path.read_bytes()


def test_normalize_global_fixes_stamps_and_empties_the_author():
    values = [""] * 26
    values[17], values[20], values[24] = "15H20261109.114612", "5Hgeova", "15H20261109.114612"
    out = normalize_global(values)
    assert out[17] == out[24] == FIXED_STAMP
    assert out[20] == ""
    assert values[20] == "5Hgeova"  # the input is not changed


def test_serialize_iges_without_stamp_positions_is_left_alone():
    document = {"start": ["x"], "global": ["", "", "1HA"], "entities": []}
    assert "1HA" in serialize_iges(document)


def _need_gmsh():
    try:
        import gmsh  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("gmsh is not usable here")


def test_two_fresh_processes_write_byte_identical_iges_with_no_login(tmp_path):
    _need_gmsh()
    first = _write_in_fresh_process(tmp_path / "a.igs")
    time.sleep(1.1)  # the kernel's own stamp has a resolution of one second
    second = _write_in_fresh_process(tmp_path / "b.igs")
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    text = first.decode("ascii")
    assert getpass.getuser() not in text
    document = read_iges(tmp_path / "a.igs")
    assert document["global"][17] == document["global"][24] == FIXED_STAMP
    assert document["global"][20] == ""
    assert any(e["type"] == 406 for e in document["entities"])
