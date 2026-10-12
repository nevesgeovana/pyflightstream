"""P0400-WS3-SIDECARS: geometry sidecar readers and the geometry layout migration."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace.sidecars import load_toml, migrate_geometry_layout, read_inventory
from tests.tier1_offline.test_raw_mesh_conditions import FILE_ROUTE, _case, _library

CP1252_TOML = 'name = "référence"\n'.encode("cp1252")


def test_p0400_load_toml_names_a_file_that_is_not_utf8(tmp_path: Path):
    """P0400-TOML-UTF8 (PFS-2095.035): a cp1252 artifact is refused by name, not by codec."""
    path = tmp_path / "setup.toml"
    path.write_bytes(CP1252_TOML)
    with pytest.raises(InputArtifactError) as raised:
        load_toml(path, "setup")
    message = str(raised.value)
    assert str(path) in message and "UTF-8" in message, message


def test_p0400_load_toml_accepts_a_byte_order_mark(tmp_path: Path):
    """P0400-TOML-BOM (PFS-2095.035): a UTF-8 file with a BOM, as PowerShell 5.1 writes, reads."""
    path = tmp_path / "setup.toml"
    path.write_bytes(b"\xef\xbb\xbf" + b'name = "x"\n')
    assert load_toml(path, "setup") == {"name": "x"}


def test_p0400_a_sidecar_that_is_not_utf8_is_refused_by_name(tmp_path: Path):
    """P0400-SIDECAR-UTF8 (PFS-2095.035): the sidecar reader names a cp1252 sidecar."""
    sidecar = tmp_path / "wing.boundaries.toml"
    sidecar.write_bytes('boundaries = ["Étage"]\n'.encode("cp1252"))
    with pytest.raises(InputArtifactError) as raised:
        read_inventory(sidecar)
    message = str(raised.value)
    assert str(sidecar) in message and "UTF-8" in message, message


def test_p0400_migration_carries_the_points_file_and_companions_and_the_row_binds(tmp_path: Path):
    """P0400-MIGRATE-COMPANIONS (PFS-2096.013): the trailing-edge points file and the
    ``<stem>.*`` companions move with their geometry, a ``<stem>.v2`` geometry keeps a
    folder of its own, and the row still binds against the migrated library."""
    workspace = _library(tmp_path, FILE_ROUTE)
    geometries = workspace.inputs_dir / "geometries"
    (geometries / "wing.audit.json").write_text("{}\n", encoding="utf-8")
    (geometries / "blade.fsm").write_bytes(b"one")
    (geometries / "blade.v2.fsm").write_bytes(b"two")

    migrate_geometry_layout(workspace.inputs_dir)

    assert sorted(path.name for path in (geometries / "wing").iterdir()) == [
        "wing.audit.json",
        "wing.boundaries.toml",
        "wing.stl",
        "wing.te.txt",
    ]
    assert (geometries / "blade" / "blade.fsm").is_file()
    assert (geometries / "blade.v2" / "blade.v2.fsm").is_file()
    assert not (geometries / "wing.te").exists() and not (geometries / "wing.audit").exists()
    case = _case(tmp_path, workspace)
    marking = case.raw_mesh_conditions.trailing_edges
    assert Path(marking.points_file) == geometries / "wing" / "wing.te.txt"
