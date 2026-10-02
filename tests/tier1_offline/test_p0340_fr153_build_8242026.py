"""FR-153 (0.34.0): build 8242026 of 26.124 writes fields as build 8172026 does, no warning.

The registration is by decision of 2026-10-01, not by measurement (RPT-136).
Each test names the marker P0340-FR153-8242026 and the requirement FR-153 in its
own source; the rows it reads say "not measured" in their evidence.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.field_frames import VELOCITY_EVIDENCE, native_velocity_proof
from pyflightstream.script.motion import _ROTARY_PROOFS, resolve_frame_motion
from tests.tier1_offline.test_fr153_field_build_warning import (
    DIGEST,
    MEASURED,
    _point,
    _rotating,
)

REGISTERED = "8242026"
DECISION = "decision of 2026-10-01, not measured"


@pytest.mark.parametrize("unit", ["METER", "MILLIMETER"])
def test_p0340_fr153_8242026_fluid_plot_writes_with_no_warning(tmp_path, unit):
    """P0340-FR153-8242026 FR-153: the unsteady fluid plot of 8242026 is written unwarned."""
    to_m = 1 if unit == "METER" else 0.001
    measured, _ = _point(tmp_path / "measured", unit=unit, native_to_m=to_m)
    entries, warned = _point(tmp_path / "registered", build=REGISTERED, unit=unit, native_to_m=to_m)
    assert warned == []
    assert all(entry == {"kind": "probe-field"} for entry in entries.values())
    inflows = sorted(p for p in entries if p.name.endswith(".inflow.dat"))
    assert inflows
    for path in inflows:
        twin = next(p for p in measured if p.name == path.name)
        assert path.read_bytes() == twin.read_bytes()


@pytest.mark.parametrize("unit", ["METER", "MILLIMETER"])
@pytest.mark.parametrize("kind", ["unsteady-fluid-plot", "steady-probe"])
def test_p0340_fr153_8242026_proof_is_proven_and_says_not_measured(kind, unit):
    """P0340-FR153-8242026 FR-153: the proof is proven, equal in scale, and marked as a decision."""
    args = {"solver_version": "26.124", "length_unit": unit}
    registered = native_velocity_proof(
        args,
        solver_identity={"fs_exe_sha256": DIGEST, "fs_build": REGISTERED},
        export_kind=kind,
    )
    measured = native_velocity_proof(
        args,
        solver_identity={"fs_exe_sha256": DIGEST, "fs_build": MEASURED},
        export_kind=kind,
    )
    assert "proven" not in registered and "measured_on_build" not in registered
    assert registered["velocity_to_m_s"] == measured["velocity_to_m_s"]
    assert registered["fs_build"] == REGISTERED
    assert registered["evidence"]["basis"] == DECISION
    assert registered["evidence"]["receipt"] == "RPT-136"
    assert ("26.124", REGISTERED, kind, unit) in VELOCITY_EVIDENCE


def test_p0340_fr153_8242026_rotating_frame_writes_with_no_warning(tmp_path):
    """P0340-FR153-8242026 FR-153: a rotating frame of 8242026 is written unwarned."""
    entries, warned = _point(tmp_path, build=REGISTERED, rotating=True)
    assert warned == []
    assert any(p.name.endswith("_step_2.vtk") for p in entries)
    assert all(entry == {"kind": "probe-field"} for entry in entries.values())


@pytest.mark.parametrize("unit", ["METER", "MILLIMETER"])
def test_p0340_fr153_8242026_rotation_timing_is_the_measured_sense_and_says_not_measured(unit):
    """P0340-FR153-8242026 FR-153: timing of 8242026 equals 8172026's and is marked a decision."""
    _, motion = _rotating()
    motion = {**motion, "length_unit": unit}
    resolved = {}
    for build in (MEASURED, REGISTERED):
        resolved[build] = resolve_frame_motion(
            motion, solver_identity={"fs_exe_sha256": DIGEST, "fs_build": build}
        )["proof"]["timing"]
    registered = resolved[REGISTERED]
    assert "proven" not in registered
    assert registered["fs_build"] == REGISTERED
    assert registered["signed_rpm_factor"] == resolved[MEASURED]["signed_rpm_factor"]
    assert registered["step_time_origin"] == resolved[MEASURED]["step_time_origin"]
    assert registered["evidence"]["kind"] == DECISION
    assert _ROTARY_PROOFS[("26.124", unit, REGISTERED)]["evidence"]["receipt"] == "RPT-136"
