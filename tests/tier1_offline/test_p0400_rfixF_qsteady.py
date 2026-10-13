"""P0400-RFIXF-QSTEADY: the quasi-steady rotor's far field reads the row's own speed (PFS-2081.93).

A ``qsteady_rotor`` run plans no reductions, so its record states no rotor
speed; the builder writes the row's speed, signed by the rotor's hand, in the
quasi-steady record beside the loads export, which every other product reads.
The far-field balances read it there too, and turn the probes to the hub frame
by that signed speed alone. Synthetic: a still stream of 12 m/s sampled in the
frame that turns with the blades.
"""
# ruff: noqa: N999 - the assigned lane name is rfixF.

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.cases._farfield_spec import LatticeShape
from pyflightstream.cases.qsteady import QsteadyClocking, QsteadyRecord
from pyflightstream.probes.layouts import lattice_points
from tests.tier1_offline import test_p0400_ffproof_post as ffpost
from tests.tier1_offline.test_p0400_rfixF_layout import _export, _rows

_SHAPE = {"rotor": "ROTOR", "stations": [-1.0, 1.0], "n_r": 2, "n_psi": 8}
_LEDGERS = (
    '[farfield]\nfamilies = "all"\n[farfield.ledgers]\nrotor = "ROTOR"\n'
    "stations = [-1.0, 1.0]\nn_r = 2\nn_psi = 8\nm_max = 2\n"
)
_HUB = np.array([0.5, 0.0, 0.0])
_LATTICE = LatticeShape.model_validate(_SHAPE).build(1.0)
_POINTS = lattice_points(_LATTICE, axis="X") + _HUB


def _quasi(rpm: float) -> str:
    """The quasi-steady record of the row, its speed signed by the rotor's hand."""
    return QsteadyRecord(
        case="wheel",
        rotor_alias="ROTOR",
        blades=2,
        rpm=rpm,
        shaft_frame_axis="X",
        hub_m=(0.5, 0.0, 0.0),
        axis_vector=(1.0, 0.0, 0.0),
        diameter_m=2.0,
        families_general=(),
        families_blades=("B1", "B2"),
        blade1_azimuth_deg=0.0,
        positions=(QsteadyClocking(0, 0.0, 0.0, f"{ffpost._STEM}.txt"),),
        validity=None,
    ).to_text()


def _ledgers(tmp_path: Path, rpm: float) -> list[dict[str, str]]:
    """Post a qsteady point whose probes read a 12 m/s still stream in the turning frame."""
    omega = np.array([1.0, 0.0, 0.0]) * 2.0 * math.pi * rpm / 60.0
    turning = np.tile([12.0, 0.0, 0.0], (len(_POINTS), 1)) - np.cross(omega, _POINTS - _HUB)
    workspace = ffpost._campaign(
        tmp_path,
        pproc=_LEDGERS,
        recipe="qsteady_rotor",
        files={
            f"{ffpost._STEM}_probes.txt": _export(_POINTS, turning),
            f"{ffpost._STEM}_qsteady.json": _quasi(rpm),
        },
    )
    shape = {
        "kind": "lattice",
        "source": "added",
        "entry": None,
        "count": len(_POINTS),
        "lattice": _LATTICE.model_dump(mode="json"),
        "axis": "X",
        "origin_m": list(_HUB),
        "positions_frame": "REFERENCE",
    }
    ffpost._set_record(workspace, farfield_layout={"shapes": [shape]})
    ffpost._post(workspace)
    return _rows(Path(workspace.root), "farfield/*_ledgers.csv")


@pytest.mark.requirement("FR-453")
@pytest.mark.requirement("FR-38")
@pytest.mark.parametrize("rpm", [600.0, -600.0], ids=["right-hand", "left-hand"])
def test_p0400_rfixf_the_qsteady_balances_read_the_rows_own_speed(tmp_path, rpm):
    """P0400-RFIXF-QSTEADY (FR-453 R8, PFS-2081.93): the ledgers are written, swirl-free.

    Before the fix the far field asked the record's plan for the speed, which a
    quasi-steady run never writes, and skipped the point ("states no speed").
    Converted by the row's own signed speed, the still stream has no swirl:
    torque flux and crossflow energy zero at every station, mass flow
    ``rho V A``. A left-handed rotor, whose recorded speed is negative, is
    converted by that sign once; the hand applied a second time would leave a
    swirl of twice the frame's.
    """
    rows = _ledgers(tmp_path, rpm)
    assert [float(row["STATION_X_R"]) for row in rows] == [-1.0, 1.0]
    edges = _LATTICE.ring_edges
    area = math.pi * (edges[-1] ** 2 - edges[0] ** 2)
    for row in rows:
        assert float(row["MDOT_KG_S"]) == pytest.approx(ffpost._RHO * 12.0 * area, rel=1e-5)
        assert float(row["TORQUE_NM"]) == pytest.approx(0.0, abs=0.1)  # printed digits
        assert float(row["E_TOTAL_W"]) == pytest.approx(0.0, abs=1.0)
