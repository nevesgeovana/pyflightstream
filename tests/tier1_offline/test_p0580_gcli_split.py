"""PFS-2260: the geometry group of pyfs-workspace split into pyfs-mesh, pyfs-geom and pyfs-fsi.

Mesh operations live in ``pyfs-mesh``, the CAD rewrite ``iges-convert`` in ``pyfs-geom`` and the
FSI beam cut in ``pyfs-fsi``; every old ``pyfs-workspace geometry <verb>`` form is refused by name
before parsing, naming the new command.
"""

from __future__ import annotations

import json

import pytest

from pyflightstream.run import geom_cli


@pytest.mark.requirement("FR-3705")
def test_p0580_pyfs_geom_iges_convert_runs_the_conversion_with_its_arguments(
    monkeypatch, tmp_path, capsys
):
    seen = {}

    def convert(sources, out, *, name_encoding):
        seen.update(sources=sources, out=out, name_encoding=name_encoding)
        return {"written": out}

    monkeypatch.setattr("pyflightstream.workspace.iges_convert.convert_iges", convert)
    out = str(tmp_path / "config.igs")
    code = geom_cli.main(["iges-convert", "a.igs", "b.igs", "--out", out])
    assert code == 0, capsys.readouterr().err
    assert seen == {"sources": ["a.igs", "b.igs"], "out": out, "name_encoding": "latin-1"}
    assert json.loads(capsys.readouterr().out) == {"written": out}


def test_p0580_pyfs_geom_iges_convert_help_lists_its_options(capsys):
    with pytest.raises(SystemExit) as stop:
        geom_cli.main(["iges-convert", "--help"])
    assert stop.value.code == 0
    said = capsys.readouterr().out
    assert "usage: pyfs-geom iges-convert" in said
    assert "--out" in said and "--name-encoding" in said
