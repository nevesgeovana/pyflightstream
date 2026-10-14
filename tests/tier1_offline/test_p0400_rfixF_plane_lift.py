"""P0400-RFIXF-PLANELIFT: the Trefftz C plane states its own lift, and is flagged short of it.

PFS-2081.95: a plane whose probe field does not hold the circulation the
loads shed gives a crossflow energy that is not their induced drag (RPT-171:
one build's probe field carried 0.74 of a wing's lift). The C row now states
``CL_T``, the Kutta-Joukowski lift of the plane's own streamwise vorticity
(FR-453 R9), and post warns where it departs from the solver's CL by more
than 10 percent. Synthetic: a pair of Lamb-Oseen vortices of known
circulation behind the loads fixture's wing.
"""
# ruff: noqa: N999 - the assigned lane name is rfixF.

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.probes.layouts import farfield_plane
from tests.tier1_offline import test_p0400_ffproof_post as ffpost
from tests.tier1_offline.test_p0400_rfixF_layout import _export, _rows

_RHO, _SPEED, _SREF = ffpost._RHO, 68.058, 50.0
_CL = 0.1882829  # the loads fixture's total CL
_ALPHA = math.radians(-2.0)
_DIRECTION = (math.cos(_ALPHA), 0.0, math.sin(_ALPHA))
_PLANE = farfield_plane(
    (30.0, 0.0, 0.0),
    direction=_DIRECTION,
    distance=0.0,
    half_width=10.0,
    half_height=5.0,
    spacing=0.25,
)
_LAYOUT = {
    "shapes": [
        {
            "kind": "plane",
            "source": "added",
            "entry": None,
            "count": len(_PLANE.points),
            "center_m": [30.0, 0.0, 0.0],
            "direction": list(_DIRECTION),
            "half_width_m": 10.0,
            "half_height_m": 5.0,
            "spacing_m": 0.25,
        }
    ]
}
_TABLE = (
    '[farfield]\nfamilies = "all"\n[farfield.trefftz]\nvariant = "plane"\n'
    "half_width_bref = 0.5\nhalf_height_bref = 0.25\nspacing_bref = 0.0125\n"
)
_SPAN = 6.0  # half the distance between the two vortices, m
_CORE = 0.6  # Lamb-Oseen core radius, m


def _gamma() -> float:
    """The circulation whose pair lifts the fixture's CL: L = rho V Gamma 2 s."""
    lift = _CL * 0.5 * _RHO * _SPEED**2 * _SREF
    return lift / (_RHO * _SPEED * 2.0 * _SPAN)


def _crossflow(scale: float) -> np.ndarray:
    """Velocities at the plane's points: the free stream plus the pair's crossflow, times scale."""
    yy, zz = np.meshgrid(_PLANE.y, _PLANE.z, indexing="ij")
    v = np.zeros_like(yy)
    w = np.zeros_like(yy)
    for y0, gamma in ((_SPAN, _gamma()), (-_SPAN, -_gamma())):
        dy, dz = yy - y0, zz
        r2 = dy * dy + dz * dz
        safe = np.where(r2 > 0.0, r2, 1.0)
        # (1 - exp(-r^2 / c^2)) / r^2, whose limit on the axis is 1 / c^2
        shape = np.where(r2 > 0.0, (1.0 - np.exp(-r2 / _CORE**2)) / safe, 1.0 / _CORE**2)
        swirl = gamma / (2.0 * math.pi) * shape
        v += -swirl * dz
        w += swirl * dy
    cross = scale * (v.ravel()[:, None] * _PLANE.axes[1] + w.ravel()[:, None] * _PLANE.axes[2])
    return np.asarray(_DIRECTION) * _SPEED + cross


def _post(tmp_path: Path, scale: float) -> tuple[dict[str, str], list[str]]:
    workspace = ffpost._campaign(
        tmp_path,
        pproc=_TABLE,
        files={f"{ffpost._STEM}_probes.txt": _export(_PLANE.points, _crossflow(scale))},
    )
    ffpost._set_record(workspace, farfield_layout=_LAYOUT)
    ffpost._post(workspace)
    root = Path(workspace.root)
    (row,) = [r for r in _rows(root, "farfield/*_trefftz.csv") if r["VARIANT"] == "C"]
    flags = [line for line in ffpost._warnings_of(root) if "carries a lift of its own" in line]
    return row, flags


@pytest.mark.requirement("FR-453")
def test_p0400_rfixf_the_plane_states_the_lift_of_its_vorticity(tmp_path):
    """P0400-RFIXF-PLANELIFT (FR-453 R9): CL_T of C is rho V Gamma 2 s, and no flag.

    Before the fix the C row's CL_T was NA, so a plane holding a fraction of
    the shed circulation could not be told from one holding all of it.
    """
    row, flags = _post(tmp_path, 1.0)
    assert float(row["CL_T"]) == pytest.approx(_CL, rel=0.02)
    assert not flags


@pytest.mark.requirement("FR-453")
def test_p0400_rfixf_a_plane_short_of_the_lift_is_flagged(tmp_path):
    """P0400-RFIXF-PLANELIFT (FR-453 R9, PFS-2081.95): 0.74 of the circulation is flagged.

    The field of one build's probes on a wing carried 0.74 of the lift
    (RPT-171). The row is written, its CL_T says 0.74 CL, and post.log names
    the point, both values and the ratio.
    """
    row, flags = _post(tmp_path, 0.74)
    assert float(row["CL_T"]) == pytest.approx(0.74 * _CL, rel=0.02)
    assert float(row["CDI_T"]) > 0.0, "the row is written"
    (flag,) = flags
    assert "0.74" in flag and "RPT-171" in flag
