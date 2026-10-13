"""P0400-MIRRORCQ: the installed-frame copy places CQ, YMOM and the harmonic phases.

At the 0.40.0 base the mirror through y = 0 negated TORQUE and RPM but copied
CQ as written, so a mirrored rotor table broke ``CP = 2 pi CQ sign(RPM)``
(PFS-2105.013); it also copied YMOM, the y of the moment point, and the phase
of a harmonic in azimuth, which maps ``PHI_k -> -PHI_k`` (PFS-2105.014).
"""

from __future__ import annotations

import csv
import math

from pyflightstream.post import inflow_tools

_HEADER = (
    "POL,ROTOR,J_PROP,CT_PROP,CQ_PROP,CP_PROP,TORQUE_PROP,RPM_PROP,"
    "YMOM,H1_PHASE_DEG,H2_PHASE_DEG,C_PHASE_DEG,S_PHASE_DEG"
)


def _rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_p0400_mirrorcq_a_rotor_table_copy_keeps_cp_equal_to_2_pi_cq_sign_rpm(tmp_path):
    """P0400-MIRRORCQ (PFS-2105.013): CQ flips with TORQUE and RPM, so CP still holds."""
    cq, rpm = 0.004, 2400.0
    cp = 2.0 * math.pi * cq * math.copysign(1.0, rpm)
    table = tmp_path / "rotor.csv"
    table.write_text(
        f"{_HEADER}\n7001,PROP,0.5,0.1,{cq},{cp!r},12.0,{rpm},0.75,30.0,350.0,10.0,20.0\n",
        encoding="utf-8",
    )
    classes = inflow_tools.installed_frame_columns(_HEADER.split(","))
    assert {"CQ_PROP", "TORQUE_PROP", "RPM_PROP"} <= set(classes.flipped)
    assert "CP_PROP" not in classes.flipped and "CT_PROP" not in classes.flipped
    (row,) = _rows(inflow_tools.to_installed_frame(table))
    copy_cq, copy_rpm, copy_cp = (float(row[c]) for c in ("CQ_PROP", "RPM_PROP", "CP_PROP"))
    assert copy_cq == -cq and copy_rpm == -rpm and float(row["TORQUE_PROP"]) == -12.0
    assert math.isclose(copy_cp, 2.0 * math.pi * copy_cq * math.copysign(1.0, copy_rpm))


def test_p0400_mirrorcq_ymom_and_the_harmonic_phases_are_mirrored(tmp_path):
    """P0400-MIRRORCQ (PFS-2105.014): YMOM flips, H1/H2 phases map to -PHI mod 360."""
    table = tmp_path / "harmonics.csv"
    table.write_text(
        f"{_HEADER}\n7001,PROP,0.5,0.1,0.004,0.025,12.0,2400.0,0.75,30.0,350.0,10.0,20.0\n",
        encoding="utf-8",
    )
    classes = inflow_tools.installed_frame_columns(_HEADER.split(","))
    assert "YMOM" in classes.flipped
    assert {"H1_PHASE_DEG", "H2_PHASE_DEG"} <= set(classes.mapped)
    # The Theodorsen and Sears phases are functions of the reduced frequency alone.
    assert not {"C_PHASE_DEG", "S_PHASE_DEG"} & {*classes.flipped, *classes.mapped}
    (row,) = _rows(inflow_tools.to_installed_frame(table))
    assert float(row["YMOM"]) == -0.75
    assert float(row["H1_PHASE_DEG"]) == 330.0 and float(row["H2_PHASE_DEG"]) == 10.0
    assert row["C_PHASE_DEG"] == "10.0" and row["S_PHASE_DEG"] == "20.0"
    # A harmonic cos(k psi - PHI_k) read at -psi is cos(k psi + PHI_k): the copy's phase.
    for psi in (0.0, 45.0, 200.0):
        source = math.cos(math.radians(-psi - 30.0))
        mirrored = math.cos(math.radians(psi - float(row["H1_PHASE_DEG"])))
        assert math.isclose(source, mirrored, abs_tol=1e-12)
