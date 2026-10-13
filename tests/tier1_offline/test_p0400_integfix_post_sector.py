"""P0400-SECTORWHOLE: the sector offset helper refuses a sector not proven whole-rotor.

At the 0.40.0 base sector_offset_calibration subtracted the sector's rotor row
from the whole wheel's without reading whether the sector's export carried the
whole rotor (symmetry loads on) or the modelled sector alone, so a sector
solved with symmetry loads off gave an offset of one sector against a wheel
(PFS-2093.002, option A: refused, never scaled on a guess).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import pyflightstream.post.corrections as corrections
from pyflightstream._digest import text_sha256
from pyflightstream.cases.corrections import CalibrationError
from pyflightstream.workspace import CampaignWorkspace

_LOADS = {"ALPHA": 0.0, "BETA": 0.0, "J": 0.5, "THRUST": 1.0, "TORQUE": 1.0, "CT": 0.1, "CQ": 0.01}
_SECTOR = "camp/sim_2/S"


def _workspace(tmp_path, monkeypatch, script: str | None):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    sector = SimpleNamespace(run_id=_SECTOR, sim_id="2", script_path=None, script_sha256=None)
    if script is not None:
        folder = workspace.sim_dir("2")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "S.txt").write_bytes(script.encode("utf-8"))
        sector.script_path, sector.script_sha256 = "S.txt", text_sha256(script)
    runs = [SimpleNamespace(run_id="camp/sim_1/W"), sector]
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda _self: runs)
    out = workspace.products_dir(None)
    out.mkdir(parents=True, exist_ok=True)
    (out / "products.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(corrections, "_rotor_row", lambda *_args: ("t", "PROP", {}))
    monkeypatch.setattr(corrections, "_loads_of", lambda *_args: dict(_LOADS))
    return workspace


def _call(workspace):
    return corrections.sector_offset_calibration(
        workspace, wheel_run_id="camp/sim_1/W", sector_run_id=_SECTOR, calibration_id="c001"
    )


@pytest.mark.parametrize(
    ("script", "named"),
    [
        ("SYMMETRY PERIODIC 6\nSET_ANALYSIS_SYMMETRY_LOADS DISABLE\n", "DISABLE"),
        ("SYMMETRY PERIODIC 6\n", "not stated"),
        (None, "no hashed script"),
    ],
)
def test_p0400_sectorwhole_a_sector_not_proven_whole_rotor_is_refused(
    tmp_path, monkeypatch, script, named
):
    """P0400-SECTORWHOLE (PFS-2093.002): refused, naming the sector run and what it states."""
    workspace = _workspace(tmp_path, monkeypatch, script)
    with pytest.raises(CalibrationError, match="does not prove whole-rotor loads") as refused:
        _call(workspace)
    assert _SECTOR in str(refused.value) and named in str(refused.value)
    assert not (workspace.inputs_dir / "calibrations" / "c001.toml").exists()


@pytest.mark.parametrize(
    "script",
    [
        "SYMMETRY PERIODIC 6\nSET_ANALYSIS_SYMMETRY_LOADS ENABLE\n",
        "SYMMETRY NONE\nSET_ANALYSIS_SYMMETRY_LOADS DISABLE\n",
    ],
)
def test_p0400_sectorwhole_a_sector_proven_whole_rotor_is_written(tmp_path, monkeypatch, script):
    """P0400-SECTORWHOLE control: symmetry loads on, or no symmetry at all, is accepted."""
    workspace = _workspace(tmp_path, monkeypatch, script)
    calibration = corrections.read_calibration(_call(workspace))
    assert calibration.route == "sector_offset" and len(calibration.rows) == 4


def test_p0400_sectorwhole_a_script_edited_after_the_run_is_refused(tmp_path, monkeypatch):
    """P0400-SECTORWHOLE: the script is read only as the record hashed it."""
    workspace = _workspace(tmp_path, monkeypatch, "SYMMETRY PERIODIC 6\n")
    (workspace.sim_dir("2") / "S.txt").write_bytes(
        b"SYMMETRY PERIODIC 6\nSET_ANALYSIS_SYMMETRY_LOADS ENABLE\n"
    )
    with pytest.raises(CalibrationError, match="no longer hashes as recorded"):
        _call(workspace)
