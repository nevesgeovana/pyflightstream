"""P0400-MADV (FR-176 R1): the advancing-tip Mach number beside M_tip and M_hel.

    M_adv = sqrt((Omega R + V_ip)^2 + V_ax^2) / a

with ``V_ax`` the free-stream component along the rotor axis and ``V_ip`` the
component in the rotor plane. Every expected value is computed here from that
line and the numbers of the fixture, never read off the implementation: a
rotor of 2 m diameter at 3000 rev/min has ``Omega R = 100 pi`` = 314.159 m/s,
and the speed of sound is 340 m/s.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases.workflows import (
    RotorMach,
    advancing_tip_mach_number,
    free_stream_direction_at,
    rotor_mach_numbers,
)
from pyflightstream.run._plan import rotor_mach_line
from pyflightstream.run.matrix import _warn_when_a_helical_mach_may_reach_one

TIP_SPEED = 100.0 * math.pi
SOUND = 340.0
Z_AXIS = (0.0, 0.0, 1.0)
X_AXIS = (1.0, 0.0, 0.0)


def _madv(velocity, *, flow, axis):
    return advancing_tip_mach_number(
        rpm=3000.0,
        diameter_m=2.0,
        velocity_m_per_s=velocity,
        sonic_velocity_m_per_s=SOUND,
        flow_direction=flow,
        axis=axis,
    )


@pytest.mark.requirement("FR-176")
def test_p0400_madv_axial_flow_gives_the_helical_number():
    """Flow along the axis (either way): V_ip = 0, so M_adv = sqrt(V^2 + (Omega R)^2) / a."""
    _tip, helical = rotor_mach_numbers(
        rpm=3000.0, diameter_m=2.0, velocity_m_per_s=100.0, sonic_velocity_m_per_s=SOUND
    )
    for flow in (X_AXIS, (-1.0, 0.0, 0.0)):
        madv, used = _madv(100.0, flow=flow, axis=X_AXIS)
        assert used
        assert madv == pytest.approx(helical, rel=1e-12)
    assert helical == pytest.approx(math.hypot(100.0, TIP_SPEED) / SOUND, rel=1e-12)


@pytest.mark.requirement("FR-176")
def test_p0400_madv_edgewise_flow_adds_the_speeds():
    """Flow in the rotor plane: M_adv = (Omega R + V) / a, larger than M_hel."""
    madv, used = _madv(100.0, flow=X_AXIS, axis=Z_AXIS)
    assert used
    assert madv == pytest.approx((TIP_SPEED + 100.0) / SOUND, rel=1e-12)
    assert madv == pytest.approx(1.2181154863, abs=1e-9)
    assert madv > math.hypot(100.0, TIP_SPEED) / SOUND


@pytest.mark.requirement("FR-176")
def test_p0400_madv_an_inclined_case_by_hand():
    """Incidence 30 degrees on a rotor whose axis is Z, V = 100 m/s.

    By hand: V_ax = 100 sin 30 = 50 m/s, V_ip = 100 cos 30 = 86.6025 m/s,
    Omega R + V_ip = 400.7615 m/s, M_adv = sqrt(400.7615^2 + 50^2) / 340 =
    403.8660 / 340 = 1.187849.
    """
    madv, used = _madv(100.0, flow=free_stream_direction_at(30.0, 0.0), axis=Z_AXIS)
    assert used
    assert madv == pytest.approx(1.187849, abs=1e-6)
    # Sideslip moves the flow in the plane of an axis-Z rotor only: edgewise.
    sideslip, _ = _madv(100.0, flow=free_stream_direction_at(0.0, 20.0), axis=Z_AXIS)
    assert sideslip == pytest.approx((TIP_SPEED + 100.0) / SOUND, rel=1e-12)


@pytest.mark.requirement("FR-176")
def test_p0400_madv_an_unresolved_axis_gives_the_edgewise_bound_and_says_so():
    madv, used = _madv(100.0, flow=X_AXIS, axis=None)
    assert not used
    assert madv == pytest.approx((TIP_SPEED + 100.0) / SOUND, rel=1e-12)
    record = RotorMach(
        "P", 3000.0, 2.0, 100.0, SOUND, 0.9, 0.97, None, "rotor", madv, used
    ).record()
    assert record["mach_advancing"] == madv
    assert record["mach_advancing_bound"] == "edgewise"
    assert record["mach_helical"] == 0.97
    assert "edgewise bound" in rotor_mach_line("P", record)
    resolved = RotorMach("P", 3000.0, 2.0, 100.0, SOUND, 0.9, 0.97, None, "rotor", madv, True)
    assert resolved.record()["mach_advancing_bound"] == "axis"
    assert "M_adv 1.218" in rotor_mach_line("P", resolved.record())
    assert "edgewise bound" not in rotor_mach_line("P", resolved.record())


def _plan_of(*machs):
    points = [
        SimpleNamespace(sim_id="9001", run_id=name, point={}, rotor_mach={"P": mach})
        for name, mach in machs
    ]
    return SimpleNamespace(campaign=SimpleNamespace(sims=[])), SimpleNamespace(points=points)


@pytest.mark.requirement("FR-176")
def test_p0400_madv_the_warning_fires_on_the_advancing_tip_with_the_helical_below_one():
    """M_hel 0.9 and M_adv 1.05 is named, by M_adv; M_adv 0.99 is not; nothing is refused."""
    resolved, plan = _plan_of(
        ("EDGE", {"mach_helical": 0.9, "mach_advancing": 1.05, "kind": "rotor"}),
        ("BELOW", {"mach_helical": 0.9, "mach_advancing": 0.99, "kind": "rotor"}),
    )
    with pytest.warns(PyflightstreamWarning, match="M_adv >= 1") as caught:
        _warn_when_a_helical_mach_may_reach_one(resolved, plan)  # type: ignore[arg-type]
    text = " ".join(str(w.message) for w in caught)
    assert "point EDGE," in text and "M_adv 1.050" in text and "M_hel 0.900" in text
    assert "BELOW" not in text
    assert "Nothing is refused" in text
