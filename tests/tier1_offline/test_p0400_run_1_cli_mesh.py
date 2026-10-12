"""Tier 1, 0.40.0 lane run-1: ``pyfs-matrix audit-mesh``, in process.

The synthetic panel meshes of the 0.38.0 tests; no solver runs.
"""

from __future__ import annotations

import pytest

from pyflightstream.run import cli
from pyflightstream.workspace import MeshAudit
from tests.tier1_offline.test_p0390_rev38_mesh_cli import _run, _source


def test_p0400_audit_mesh_states_the_exit_of_a_csv_it_cannot_write(tmp_path, capsys, monkeypatch):
    """P0400-AUDIT-MESH-CSV-EXIT (PFS-2094.035): the help says what exit 2 also covers.

    The audit is written and only the --out CSV fails; the command exits 2 and names the
    audit written, and the help, which said 2 meant a refused input, now says so too.
    """
    src = _source(tmp_path)

    def refuse(self, path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(MeshAudit, "write_csv", refuse)
    code, _, err, _ = _run(capsys, "audit-mesh", str(src), "--out", str(tmp_path / "a.csv"))
    assert code == 2 and "could not be written" in err and ".audit.json was written" in err
    with pytest.raises(SystemExit):
        cli.main(["audit-mesh", "--help"])
    help_text = " ".join(capsys.readouterr().out.split())
    assert "when the --out CSV cannot be written after the audit was" in help_text
