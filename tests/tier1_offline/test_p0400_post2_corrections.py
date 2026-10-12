"""P0400-CALWRITE: the sector offset calibration is validated before it is written.

At the 0.40.0 base sector_offset_calibration wrote the file first and read it
back after, so a refused text stayed in the calibrations folder and, with
overwrite, the calibration it replaced was already gone.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import pyflightstream.post.corrections as corrections
from pyflightstream._digest import text_sha256
from pyflightstream.cases.corrections import CalibrationError, calibration_path
from pyflightstream.workspace import CampaignWorkspace

_LOADS = {"ALPHA": 0.0, "BETA": 0.0, "J": 0.5, "THRUST": 1.0, "TORQUE": 1.0, "CT": 0.1, "CQ": 0.01}


def _workspace(tmp_path, monkeypatch):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    # The sector's script proves whole-rotor loads (PFS-2093.002).
    script = "SYMMETRY PERIODIC 6\nSET_ANALYSIS_SYMMETRY_LOADS ENABLE\n"
    (workspace.sim_dir("2") / "S.txt").parent.mkdir(parents=True, exist_ok=True)
    (workspace.sim_dir("2") / "S.txt").write_bytes(script.encode("utf-8"))
    sector = SimpleNamespace(
        run_id="camp/sim_2/S", sim_id="2", script_path="S.txt", script_sha256=text_sha256(script)
    )
    runs = [SimpleNamespace(run_id="camp/sim_1/W"), sector]
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda _self: runs)
    out = workspace.products_dir(None)
    out.mkdir(parents=True, exist_ok=True)
    (out / "products.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(corrections, "_rotor_row", lambda *_args: ("t", "PROP", {}))
    monkeypatch.setattr(corrections, "_loads_of", lambda *_args: dict(_LOADS))
    return workspace


def _call(workspace, **kwargs):
    return corrections.sector_offset_calibration(
        workspace,
        wheel_run_id="camp/sim_1/W",
        sector_run_id="camp/sim_2/S",
        calibration_id="c001",
        **kwargs,
    )


def test_p0400_calwrite_a_refused_text_never_replaces_the_calibration(tmp_path, monkeypatch):
    """P0400-CALWRITE: with overwrite, a text the reader refuses leaves the old file whole."""
    workspace = _workspace(tmp_path, monkeypatch)
    path = calibration_path(workspace.inputs_dir, "c001")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("the calibration that was there\n", encoding="utf-8")
    monkeypatch.setattr(corrections, "calibration_text", lambda *_a, **_k: "route = [[[\n")
    with pytest.raises(CalibrationError):
        _call(workspace, overwrite=True)
    assert path.read_text(encoding="utf-8") == "the calibration that was there\n"


def test_p0400_calwrite_a_refused_text_leaves_no_file(tmp_path, monkeypatch):
    """P0400-CALWRITE: with no file before, a refused text writes none."""
    workspace = _workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(corrections, "calibration_text", lambda *_a, **_k: "route = [[[\n")
    with pytest.raises(CalibrationError):
        _call(workspace)
    assert not calibration_path(workspace.inputs_dir, "c001").exists()


def test_p0400_calwrite_a_valid_text_is_written(tmp_path, monkeypatch):
    """P0400-CALWRITE control: the helper's own text is written and reads back."""
    workspace = _workspace(tmp_path, monkeypatch)
    path = _call(workspace)
    calibration = corrections.read_calibration(path)
    assert calibration.route == "sector_offset" and len(calibration.rows) == 4
