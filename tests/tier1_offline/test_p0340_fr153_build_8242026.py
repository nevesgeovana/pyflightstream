"""FR-153 (0.34.0): build 8242026 of 26.124 writes fields as build 8172026 does, no warning.

The owner identified 8242026 as the Linux build of the same 26.124 build
8172026 on 2026-10-15. Registration cites that identity and RPT-083 measurements.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.field_frames import VELOCITY_EVIDENCE, native_velocity_proof
from pyflightstream.script.motion import _ROTARY_PROOFS, resolve_frame_motion
from tests.tier1_offline.test_probe_fields import _FR153_FIELD_BUILD_WARNING__DIGEST as DIGEST
from tests.tier1_offline.test_probe_fields import _FR153_FIELD_BUILD_WARNING__MEASURED as MEASURED
from tests.tier1_offline.test_probe_fields import _fr153_field_build_warning___point as _point
from tests.tier1_offline.test_probe_fields import _fr153_field_build_warning___rotating as _rotating

REGISTERED = "8242026"
SAME_BUILD = "Linux build of 8172026; owner identity statement 2026-10-15"


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
def test_p0420_p2_1a_8242026_proof_cites_same_build_measurement(kind, unit):
    """P0340-FR153-8242026 FR-153: equal scale cites the same-build measurement."""
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
    assert registered["evidence"]["basis"] == SAME_BUILD
    assert registered["evidence"]["receipt"] == "RPT-083"
    assert ("26.124", REGISTERED, kind, unit) in VELOCITY_EVIDENCE


def test_p0340_fr153_8242026_rotating_frame_writes_with_no_warning(tmp_path):
    """P0340-FR153-8242026 FR-153: a rotating frame of 8242026 is written unwarned."""
    entries, warned = _point(tmp_path, build=REGISTERED, rotating=True)
    assert warned == []
    assert any(p.name.endswith("_step_2.vtk") for p in entries)
    assert all(entry == {"kind": "probe-field"} for entry in entries.values())


@pytest.mark.parametrize("unit", ["METER", "MILLIMETER"])
def test_p0420_p2_1a_8242026_rotation_timing_cites_same_build_measurement(unit):
    """P0340-FR153-8242026 FR-153: timing agrees through the Linux build identity."""
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
    assert registered["evidence"]["kind"] == SAME_BUILD
    assert _ROTARY_PROOFS[("26.124", unit, REGISTERED)]["evidence"]["receipt"] == "RPT-083"
