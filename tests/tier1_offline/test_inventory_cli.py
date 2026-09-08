"""`pyfs-matrix inventory` writes the boundary sidecar from the file (PFS-2029.06.02)."""

from __future__ import annotations

import tomllib

from pyflightstream._fsm import MESH_MARKER
from pyflightstream.run.cli import main


def _saved_simulation(path, names):
    body = [MESH_MARKER, "9999", "99", str(len(names))]
    for offset, name in enumerate(names):
        body += [f"{offset + 2}, T, T, F", name, ".500,.500,.500"]
    body += ["$MESH_END$"]
    path.write_text("\r\n".join(body) + "\r\n", encoding="utf-8", newline="")
    return path


def test_inventory_writes_the_sidecar_beside_the_geometry(tmp_path, capsys):
    geometry = _saved_simulation(tmp_path / "30_WB.fsm", ["W", "B", "Blade1"])
    assert main(["inventory", str(geometry)]) == 0
    sidecar = tmp_path / "30_WB.boundaries.toml"
    assert sidecar.is_file()
    assert capsys.readouterr().out.strip() == str(sidecar)
    data = tomllib.loads(sidecar.read_text(encoding="utf-8"))
    assert data == {"file": "30_WB.fsm", "boundaries": ["W", "B", "Blade1"]}


def test_inventory_refuses_to_overwrite_without_the_flag(tmp_path, capsys):
    geometry = _saved_simulation(tmp_path / "30_WB.fsm", ["W", "B"])
    sidecar = tmp_path / "30_WB.boundaries.toml"
    sidecar.write_text('boundaries = ["edited"]\n', encoding="utf-8")
    assert main(["inventory", str(geometry)]) == 2
    err = capsys.readouterr().err
    assert "30_WB.boundaries.toml" in err and "--overwrite" in err
    assert sidecar.read_text(encoding="utf-8") == 'boundaries = ["edited"]\n', (
        "the refusal rewrote it"
    )
    assert main(["inventory", str(geometry), "--overwrite"]) == 0
    assert tomllib.loads(sidecar.read_text(encoding="utf-8"))["boundaries"] == ["W", "B"]


def test_a_file_without_a_mesh_block_is_refused_by_name(tmp_path, capsys):
    raw = tmp_path / "raw_blade.stl"
    raw.write_bytes(b"solid blade\n")
    assert main(["inventory", str(raw)]) == 2
    err = capsys.readouterr().err
    assert "raw_blade.stl" in err and "no mesh block" in err
    assert not (tmp_path / "raw_blade.boundaries.toml").exists()
    assert main(["inventory", str(tmp_path / "absent.fsm")]) == 2
    assert "absent.fsm" in capsys.readouterr().err


def test_a_missing_geometry_is_named_before_a_stale_sidecar(tmp_path, capsys):
    """The refusal names the cause that is the cause: a file that is not there."""
    stale = tmp_path / "renamed.boundaries.toml"
    stale.write_text('boundaries = ["W"]\n', encoding="utf-8")
    assert main(["inventory", str(tmp_path / "renamed.fsm")]) == 2
    err = capsys.readouterr().err
    assert "renamed.fsm" in err and "not a file" in err
    assert "--overwrite" not in err, "the stale sidecar was named as the cause"
