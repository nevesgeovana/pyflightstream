"""PFS-2231 (0.58.0, lane L1): the RCOEF values of a family or group inside a rotor.

The design of the 0.58.0 post outputs, section 4.3: T, Q and P (kW) in the
rotor frame; CT, CQ, CP; CFZ to CMY in the R axes; ETA; TC to MCA; and the
per-frame set CT<f>, CQ<f>, ETA<f> with CTR<own id> == CT; the NA rules of a
static point and of a rotor not turning or of unknown speed; and the warning
for a rotor declared aft (section 2.3). The expected numbers are computed here
from the formulas of the page, on a hand case.
"""

from __future__ import annotations

import math
import warnings

import numpy as np
import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.post.axes import frame_rotations, rotor_frame
from pyflightstream.post.rotor_table import rotor_frame_coefficients, warn_rotor_declared_aft

TRACTOR = (-1.0, 0.0, 0.0)  # declared forward, in the export frame (x aft)
RHO, VINF, D, RPM = 1.2, 15.0, 0.5, 1200.0
SREF, CREF, BREF = 2.0, 0.5, 4.0
# Export frame: F = (-120, 30, 40) N is, in body axes, 120 N forward, 30 right, 40 up.
FORCE = (-120.0, 30.0, 40.0)
# Export frame: M = (-8, 6, 2) N m is, in body axes, (8, 6, -2).
MOMENT = (-8.0, 6.0, 2.0)

ROTOR_FRAME_SET = (
    "T",
    "Q",
    "P",
    "CT",
    "CQ",
    "CP",
    "CFZ",
    "CFY",
    "CMZ",
    "CMY",
    "ETA",
    "TC",
    "YC",
    "ZC",
    "QC",
    "NC",
    "MC",
    "TCA",
    "YCA",
    "ZCA",
    "QCA",
    "NCA",
    "MCA",
)
LOADINGS = ("TC", "YC", "ZC", "QC", "NC", "MC", "TCA", "YCA", "ZCA", "QCA", "NCA", "MCA")


def _row(axis=TRACTOR, rpm=RPM, vinf=VINF, rotors=None, force=FORCE, moment=MOMENT):
    frame = rotor_frame(axis, 0)
    frames = [frame] if rotors is None else rotors
    return rotor_frame_coefficients(
        force_n=force,
        moment_hub_nm=moment,
        frame=frame,
        rotations=frame_rotations(4.0, 2.0, frames),
        rpm=rpm,
        diameter_m=D,
        density_kg_m3=RHO,
        vinf_m_s=vinf,
        sref_m2=SREF,
        cref_m=CREF,
        bref_m=BREF,
    )


def test_the_hand_case():
    row = _row()
    n = RPM / 60.0
    t, y, z, q_torque, m, yaw = 120.0, 30.0, 40.0, 8.0, 6.0, -2.0
    f4, f5 = RHO * n**2 * D**4, RHO * n**2 * D**5
    j = VINF / (n * D)
    q = 0.5 * RHO * VINF**2
    area = math.pi * D**2 / 4.0
    cq = q_torque / f5
    cp = 2.0 * math.pi * cq
    expected = {
        "T": t,
        "Q": q_torque,
        "P": 2.0 * math.pi * n * q_torque / 1000.0,
        "CT": t / f4,
        "CQ": cq,
        "CP": cp,
        "CFZ": z / f4,
        "CFY": y / f4,
        "CMZ": yaw / f5,
        "CMY": m / f5,
        "ETA": j * (t / f4) / cp,
        "TC": t / (q * area),
        "YC": y / (q * area),
        "ZC": z / (q * area),
        "QC": q_torque / (q * area * D),
        "NC": yaw / (q * area * D),
        "MC": m / (q * area * D),
        "TCA": t / (q * SREF),
        "YCA": y / (q * SREF),
        "ZCA": z / (q * SREF),
        "QCA": q_torque / (q * SREF * BREF),
        "NCA": yaw / (q * SREF * BREF),
        "MCA": m / (q * SREF * CREF),
    }
    for name, value in expected.items():
        assert row[name] == pytest.approx(value, rel=1e-12), name
    assert row["P"] == pytest.approx(1.0053096491487339, rel=1e-12)  # kW


def test_the_columns_come_in_the_registry_order():
    assert list(_row())[: len(ROTOR_FRAME_SET)] == list(ROTOR_FRAME_SET)
    per_frame = list(_row())[len(ROTOR_FRAME_SET) :]
    assert per_frame == [f"{s}{f}" for f in ("W", "S", "B", "R0") for s in ("CT", "CQ", "ETA")]


def test_the_own_frame_repeats_the_bare_values():
    row = _row()
    assert row["CTR0"] == row["CT"] and row["CQR0"] == row["CQ"] and row["ETAR0"] == row["ETA"]


def test_the_per_frame_set_is_the_force_along_each_frame_x():
    row = _row()
    n = RPM / 60.0
    turns = frame_rotations(4.0, 2.0, [rotor_frame(TRACTOR, 0)])
    for name in ("W", "S", "B"):
        along = float((turns[name] @ np.asarray(FORCE))[0])
        about = float((turns[name] @ np.asarray(MOMENT))[0])
        assert row[f"CT{name}"] == pytest.approx(along / (RHO * n**2 * D**4), rel=1e-12)
        assert row[f"CQ{name}"] == pytest.approx(about / (RHO * n**2 * D**5), rel=1e-12)
        j = VINF / (n * D)
        assert row[f"ETA{name}"] == pytest.approx(j * row[f"CT{name}"] / row["CP"], rel=1e-12)


def test_another_rotors_frame_keeps_the_own_rotors_normalisation():
    other = rotor_frame((0.0, 0.0, 1.0), 1)
    row = _row(rotors=[rotor_frame(TRACTOR, 0), other])
    n = RPM / 60.0
    along = float((other.body_to_rotor @ np.diag([-1.0, 1.0, -1.0]) @ FORCE)[0])
    assert row["CTR1"] == pytest.approx(along / (RHO * n**2 * D**4), rel=1e-12)


def test_a_rotor_declared_aft_reads_the_same_as_declared_forward():
    forward = _row(axis=TRACTOR, rpm=RPM)
    # The same rotor, its axis declared aft: the same physical spin is -RPM about it.
    aft = _row(axis=(1.0, 0.0, 0.0), rpm=-RPM)
    for name in ROTOR_FRAME_SET:
        assert aft[name] == pytest.approx(forward[name], rel=1e-12), name


def test_a_rotor_declared_aft_is_warned_with_its_alias():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert warn_rotor_declared_aft("PUSHER", rotor_frame((1.0, 0.0, 0.0)))
        assert not warn_rotor_declared_aft("TRACTOR", rotor_frame(TRACTOR))
    messages = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    assert messages == [
        "Rotor PUSHER declares its axis aft; 0.58.0 counts thrust positive forward, so CT, T "
        "and the in-plane signs of this rotor are opposite to 0.57.0. "
        "See docs/upgrading.md#0580-post-tree."
    ]


def _na(row):
    return {name for name, value in row.items() if value == "NA"}


def test_a_static_point_states_exactly_the_na_set():
    row = _row(vinf=0.0)
    eta = {f"ETA{f}" for f in ("W", "S", "B", "R0")}
    assert _na(row) == {"ETA", *eta, *LOADINGS}
    for name in ("T", "Q", "P", "CT", "CQ", "CP", "CFZ", "CFY", "CMZ", "CMY"):
        assert isinstance(row[name], float), name


def test_a_rotor_not_turning_states_no_coefficient_over_n_squared():
    row = _row(rpm=0.0)
    over_n = {"CT", "CQ", "CP", "CFZ", "CFY", "CMZ", "CMY", "ETA"}
    per_frame = {f"{s}{f}" for f in ("W", "S", "B", "R0") for s in ("CT", "CQ", "ETA")}
    assert _na(row) == over_n | per_frame
    assert row["P"] == 0.0 and row["T"] == pytest.approx(120.0) and row["Q"] == pytest.approx(8.0)
    assert all(isinstance(row[name], float) for name in LOADINGS)


def test_a_rotor_of_unknown_speed_states_no_power():
    row = _row(rpm=None)
    assert row["P"] == "NA"
    assert row["T"] == pytest.approx(120.0) and isinstance(row["TC"], float)


def test_loads_that_are_not_numbers_give_na():
    row = _row(force=(math.nan, math.nan, math.nan), moment=(math.nan, math.nan, math.nan))
    assert set(row.values()) == {"NA"}
