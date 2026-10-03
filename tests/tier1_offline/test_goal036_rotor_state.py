"""Tier 1: a quasi-steady wheel point states the rotor state its correction routes need (0.31.0).

P0310-CAL-POINT-STATE. Per wheel point, beside the validity columns in
``_qs_avg.csv`` and in ``<point>_qsteady_validity.json``: ``CT_ROTOR`` (rotor
convention) and ``CT_PROPELLER``, ``MU_ROTOR``, ``LAMBDA_C``, the momentum-theory
``LAMBDA_I`` (Glauert, converged to 1e-10) and the wake skew ``CHI_DEG``, from
the mean loads over the clockings. An inflow that does not converge is ``NA``
and a WARNING line of ``post.log``.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pytest

from pyflightstream.cases import qsteady as arithmetic
from pyflightstream.post import qsteady as post_qsteady
from tests.tier1_offline.test_goal036_rotor_mean import _QS, _posted

OMEGA_R = 2.0 * math.pi * 20.0 * 1.0  # 1200 rev/min on a 2 m rotor: Omega R, m/s
RHO = 1.2
V = 30.0


def _record(axis: tuple[float, float, float]) -> arithmetic.QsteadyRecord:
    return arithmetic.QsteadyRecord(
        case="wheel",
        rotor_alias="PROP",
        blades=2,
        rpm=1200.0,
        shaft_frame_axis="X",
        hub_m=(0.0, 0.0, 0.0),
        axis_vector=axis,
        diameter_m=2.0,
        families_general=(),
        families_blades=("B1", "B2"),
        blade1_azimuth_deg=0.0,
        positions=(
            arithmetic.QsteadyClocking(0, 0.0, 0.0, "DP.txt"),
            arithmetic.QsteadyClocking(1, 90.0, 90.0, "DP_qs01.txt"),
        ),
        validity=None,
    )


def _clockings(*thrusts: float) -> list[post_qsteady.Clocking]:
    """Clockings whose rotor THRUST is each of ``thrusts``; every other load 0."""
    at = post_qsteady.LOAD_NAMES.index("THRUST")
    return [
        post_qsteady.Clocking(index, 0.0, tuple(thrust if k == at else 0.0 for k in range(3 * 8)))
        for index, thrust in enumerate(thrusts)
    ]


def test_the_glauert_inflow_of_axial_flight_is_the_closed_form():
    """mu = 0: l (lambda_c + l) = CT / 2, so l = -lambda_c / 2 + sqrt(lambda_c^2 / 4 + CT / 2)."""
    # P0310-CAL-POINT-STATE
    assert arithmetic.glauert_induced_inflow(0.01, 0.0, 0.05) == pytest.approx(0.05, abs=1e-12)
    closed = -0.05 + math.sqrt(0.1**2 / 4.0 + 0.008 / 2.0)
    assert arithmetic.glauert_induced_inflow(0.008, 0.0, 0.1) == pytest.approx(closed, abs=1e-12)


def test_the_glauert_inflow_of_edgewise_flight_is_the_closed_form():
    """lambda_c = 0: l^2 (mu^2 + l^2) = CT^2 / 4, so l^2 = (-mu^2 + sqrt(mu^4 + CT^2)) / 2."""
    # P0310-CAL-POINT-STATE
    closed = math.sqrt((-(0.1**2) + math.sqrt(0.1**4 + 0.01**2)) / 2.0)
    assert arithmetic.glauert_induced_inflow(0.01, 0.1, 0.0) == pytest.approx(closed, abs=1e-12)
    # And a general state satisfies the relation it solves, to the tolerance.
    ct, mu, climb = 0.006, 0.15, 0.03
    solved = arithmetic.glauert_induced_inflow(ct, mu, climb)
    assert solved is not None
    assert solved == pytest.approx(ct / (2.0 * math.hypot(mu, climb + solved)), abs=1e-10)


def test_an_axial_wheel_point_has_no_skew_and_the_axial_inflow():
    """Axis forward (-x), alpha 0: alpha_p = 0, MU_ROTOR 0, LAMBDA_C = V / (Omega R), CHI 0.

    T is the mean over the clockings, (400 + 600) / 2 = 500 N; A = pi m^2.
    CT_PROPELLER / CT_ROTOR = pi A (Omega R)^2 / (n^2 D^4) = pi^3 / 4.
    """
    # P0310-CAL-POINT-STATE
    state = post_qsteady.rotor_state(
        _record((-1.0, 0.0, 0.0)),
        _clockings(400.0, 600.0),
        density_kg_m3=RHO,
        velocity_m_s=V,
        alpha_deg=0.0,
        beta_deg=0.0,
    )
    values = state.values
    ct = 500.0 / (RHO * math.pi * OMEGA_R**2)
    climb = V / OMEGA_R
    assert state.notes == ()
    assert values["CT_ROTOR"] == pytest.approx(ct, rel=1e-12)
    assert values["CT_PROPELLER"] == pytest.approx(500.0 / (RHO * 20.0**2 * 2.0**4), rel=1e-12)
    assert values["CT_PROPELLER"] / values["CT_ROTOR"] == pytest.approx(math.pi**3 / 4.0)
    assert values["MU_ROTOR"] == 0.0
    assert values["LAMBDA_C"] == pytest.approx(climb, rel=1e-12)
    induced = -climb / 2.0 + math.sqrt(climb**2 / 4.0 + ct / 2.0)
    assert values["LAMBDA_I"] == pytest.approx(induced, abs=1e-12)
    assert values["CHI_DEG"] == 0.0


def test_an_edgewise_wheel_point_has_the_edgewise_inflow_and_its_skew():
    """Axis up (+z), level flight: alpha_p = 90 deg, LAMBDA_C 0, MU_ROTOR = V / (Omega R)."""
    # P0310-CAL-POINT-STATE
    state = post_qsteady.rotor_state(
        _record((0.0, 0.0, 1.0)),
        _clockings(500.0, 500.0),
        density_kg_m3=RHO,
        velocity_m_s=V,
        alpha_deg=0.0,
        beta_deg=0.0,
    )
    values = state.values
    ct = 500.0 / (RHO * math.pi * OMEGA_R**2)
    mu = V / OMEGA_R
    induced = math.sqrt((-(mu**2) + math.sqrt(mu**4 + ct**2)) / 2.0)
    assert values["LAMBDA_C"] == 0.0
    assert values["MU_ROTOR"] == pytest.approx(mu, rel=1e-12)
    assert values["LAMBDA_I"] == pytest.approx(induced, abs=1e-12)
    assert values["CHI_DEG"] == pytest.approx(math.degrees(math.atan2(mu, induced)), abs=1e-9)
    # A shaft tilted 10 deg from the flight direction: MU = V sin 10 / (Omega R).
    tilted = post_qsteady.rotor_state(
        _record((-1.0, 0.0, 0.0)),
        _clockings(500.0, 500.0),
        density_kg_m3=RHO,
        velocity_m_s=V,
        alpha_deg=10.0,
        beta_deg=0.0,
    ).values
    assert tilted["MU_ROTOR"] == pytest.approx(V * math.sin(math.radians(10.0)) / OMEGA_R)
    assert tilted["LAMBDA_C"] == pytest.approx(V * math.cos(math.radians(10.0)) / OMEGA_R)


def test_an_inflow_that_does_not_converge_is_na_and_said(monkeypatch):
    """One Newton step: LAMBDA_I and CHI_DEG are NA, the rest stands, and a note says why."""
    # P0310-CAL-POINT-STATE
    assert arithmetic.glauert_induced_inflow(0.01, 0.1, 0.0, iterations=1) is None
    monkeypatch.setattr(arithmetic, "INFLOW_ITERATIONS", 1)
    state = post_qsteady.rotor_state(
        _record((0.0, 0.0, 1.0)),
        _clockings(500.0, 500.0),
        density_kg_m3=RHO,
        velocity_m_s=V,
        alpha_deg=0.0,
        beta_deg=0.0,
    )
    assert state.values["LAMBDA_I"] is None and state.values["CHI_DEG"] is None
    assert state.values["MU_ROTOR"] == pytest.approx(V / OMEGA_R)
    (note,) = state.notes
    assert "LAMBDA_I and CHI_DEG of rotor PROP read NA" in note and "did not converge" in note


def _average_rows(folder: Path) -> list[dict[str, str]]:
    (path,) = sorted(folder.rglob("*_qs_avg.csv"))
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.requirement("FR-187")
def test_the_average_table_and_the_validity_file_carry_the_state_of_the_mean_loads(tmp_path):
    """The recorded wheel of two clockings: T is the mean of 0.0274326 and 0.0374326 of q S.

    Its axis is +x and the air moves +x at alpha 0, so the flight direction is
    against the axis: alpha_p = 180 deg, LAMBDA_C = -V / (Omega R).
    """
    # P0310-CAL-POINT-STATE
    products, folder = _posted(tmp_path, "wheel", ((0.0193288, 0.01), (0.0293288, 0.03)))
    rows = _average_rows(folder)
    assert len(rows) == 2
    heading = list(rows[0])
    validity_end = heading.index("K_1P_SOURCE")
    assert heading[validity_end + 1 : validity_end + 7] == list(post_qsteady.STATE_COLUMNS)
    thrust = 0.0324326 * _QS
    ct = thrust / (1.225 * math.pi * OMEGA_R**2)
    for row in rows:
        alpha = math.radians(float(row["ALPHA"]))
        assert float(row["CT_ROTOR"]) == pytest.approx(ct, abs=1e-5)
        assert float(row["CT_PROPELLER"]) == pytest.approx(ct * math.pi**3 / 4.0, abs=1e-5)
        mu, climb = float(row["MU_ROTOR"]), float(row["LAMBDA_C"])
        assert mu == pytest.approx(68.058 * abs(math.sin(alpha)) / OMEGA_R, abs=1e-5)
        assert climb == pytest.approx(-68.058 * math.cos(alpha) / OMEGA_R, abs=1e-5)
        induced = float(row["LAMBDA_I"])
        assert induced == pytest.approx(ct / (2.0 * math.hypot(mu, climb + induced)), abs=1e-4)
        chi = math.degrees(math.atan2(mu, climb + induced))
        assert float(row["CHI_DEG"]) == pytest.approx(chi, abs=1e-3)
    (entry,) = [e for n, e in products["products"].items() if n.endswith("_qs_avg.csv")]
    for relative in entry["validity_files"].values():
        written = json.loads((folder / relative).read_text(encoding="utf-8"))
        state = written["rotor_state"]
        assert list(state) == list(post_qsteady.STATE_COLUMNS)
        assert state["CT_ROTOR"] == pytest.approx(ct, rel=1e-5)
        assert state["LAMBDA_I"] is not None


def test_the_post_says_an_inflow_it_cannot_solve_in_its_log(tmp_path, monkeypatch):
    """With one Newton step the post writes NA and a WARNING line naming the point and the table."""
    # P0310-CAL-POINT-STATE
    monkeypatch.setattr(arithmetic, "INFLOW_ITERATIONS", 1)
    _, folder = _posted(tmp_path, "wheel", ((0.0193288, 0.01), (0.0293288, 0.03)))
    for row in _average_rows(folder):
        assert row["LAMBDA_I"] == "NA" and row["CHI_DEG"] == "NA"
        assert row["CT_ROTOR"] != "NA"
    log = (folder / "post.log").read_text(encoding="utf-8")
    said = [line for line in log.splitlines() if "LAMBDA_I and CHI_DEG of rotor PROP" in line]
    assert len(said) == 2, log
    assert all("WARNING" in line and "_qs_avg.csv" in line for line in said)
