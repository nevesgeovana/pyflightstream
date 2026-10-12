"""Tier 1, 0.40.0: the geometry verbs of pyfs-matrix join pyfs-workspace geometry (FR-477).

P0400-GEOM-GROUP (PFS-2081.41). The group's refine, audit, inventory and
degenerate are the pyfs-matrix parsers and handlers; the pyfs-matrix names
stay as aliases with the identical result and one warning.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.run import _cli_geometry
from pyflightstream.run.cli import main as matrix_main
from pyflightstream.workspace import cli as workspace_cli
from tests.tier1_offline.test_p0400_geometry_build import wing_obj


@pytest.mark.requirement("FR-477")
def test_p0400_geom_group_the_four_verbs_are_registered_with_their_options():
    """P0400-GEOM-GROUP (PFS-2081.41): the group copies each pyfs-matrix parser."""
    parser = workspace_cli._build_parser()
    group = parser._subparsers._group_actions[0].choices["geometry"]
    verbs = group._subparsers._group_actions[0].choices
    assert set(verbs) == set(_cli_geometry.GEOMETRY_VERBS)
    matrix = _cli_geometry._matrix_parsers()
    for name, verb in _cli_geometry.PYFS_MATRIX_ALIASES.items():
        ours = {a.dest for a in verbs[name]._actions}
        theirs = {a.dest for a in matrix[verb]._actions}
        assert ours == theirs, name


@pytest.mark.requirement("FR-477")
def test_p0400_geom_group_audit_gives_the_result_of_audit_mesh(tmp_path, monkeypatch, capsys):
    """P0400-GEOM-GROUP (PFS-2081.41): R1, the same audit, the alias warned once."""
    mesh = wing_obj(tmp_path / "wing.obj")
    monkeypatch.chdir(tmp_path)
    assert workspace_cli.main(["geometry", "audit", str(mesh)]) == 0
    ours = (tmp_path / "wing.audit.json").read_text(encoding="utf-8")
    (tmp_path / "wing.audit.json").unlink()
    with pytest.warns(PyflightstreamWarning, match="alias of `pyfs-workspace geometry audit`"):
        assert matrix_main(["audit-mesh", str(mesh)]) == 0
    assert (tmp_path / "wing.audit.json").read_text(encoding="utf-8") == ours


@pytest.mark.requirement("FR-477")
def test_p0400_geom_group_inventory_writes_what_pyfs_matrix_inventory_writes(tmp_path, monkeypatch):
    """P0400-GEOM-GROUP (PFS-2081.41): the inventory of an OBJ, through both names."""
    mesh = wing_obj(tmp_path / "wing.obj")
    monkeypatch.chdir(tmp_path)
    assert workspace_cli.main(["geometry", "inventory", str(mesh)]) == 0
    ours = (tmp_path / "wing.boundaries.toml").read_text(encoding="utf-8")
    (tmp_path / "wing.boundaries.toml").unlink()
    with pytest.warns(PyflightstreamWarning, match="pyfs-matrix inventory is an alias"):
        assert matrix_main(["inventory", str(mesh)]) == 0
    assert (tmp_path / "wing.boundaries.toml").read_text(encoding="utf-8") == ours
