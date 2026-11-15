"""PFS-2260: the geometry group of pyfs-workspace split into pyfs-mesh, pyfs-geom and pyfs-fsi.

Mesh operations live in ``pyfs-mesh``, the CAD rewrite ``iges-convert`` in ``pyfs-geom`` and the
FSI beam cut in ``pyfs-fsi``; every old ``pyfs-workspace geometry <verb>`` form is refused by name
before parsing, naming the new command.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from pyflightstream.fsi import cli as fsi_cli
from pyflightstream.run import geom_cli


@pytest.mark.requirement("FR-3705")
def test_p0580_pyfs_geom_iges_convert_refuses_a_missing_iges_with_exit_2(tmp_path, capsys):
    out = tmp_path / "config.igs"
    code = geom_cli.main(["iges-convert", str(tmp_path / "absent.igs"), "--out", str(out)])
    assert code == 2
    assert capsys.readouterr().err.strip()
    assert not out.exists()


def test_p0580_pyfs_geom_iges_convert_help_lists_its_options(capsys):
    with pytest.raises(SystemExit) as stop:
        geom_cli.main(["iges-convert", "--help"])
    assert stop.value.code == 0
    said = capsys.readouterr().out
    assert "usage: pyfs-geom iges-convert" in said
    assert "--out" in said and "--name-encoding" in said


def test_p0580_pyfs_fsi_beam_refuses_an_unreadable_mesh_with_exit_2(tmp_path, capsys):
    missing = tmp_path / "nothing.obj"
    code = fsi_cli.main(["beam", str(missing), "--families", "Blade1", "--stations", "5"])
    assert code == 2
    assert capsys.readouterr().err.strip()
    assert not list(tmp_path.iterdir())


def test_p0580_pyfs_fsi_beam_help_lists_its_options(capsys):
    with pytest.raises(SystemExit) as stop:
        fsi_cli.main(["beam", "--help"])
    assert stop.value.code == 0
    said = capsys.readouterr().out
    assert "usage: pyfs-fsi beam" in said
    for option in ("--families", "--stations", "--visual-inspection"):
        assert option in said


def test_p0580_pyfs_fsi_beam_is_there_in_a_fresh_interpreter():
    # The console script imports only pyflightstream.fsi.cli; the command must be registered
    # by then, not only after a test session has imported the run layer.
    code = (
        "import sys; from pyflightstream.fsi.cli import main; "
        "sys.argv = ['pyfs-fsi', 'beam', '--help']; main()"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300, check=False
    )
    assert done.returncode == 0, done.stderr
    assert "usage: pyfs-fsi beam" in done.stdout
