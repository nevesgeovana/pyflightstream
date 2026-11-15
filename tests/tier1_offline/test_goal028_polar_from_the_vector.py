"""The steady polar's twenty-four coefficients come from ONE vector, under sideslip too.

THE REQUIREMENT (block X, answers 8 and 8b of 2026-09-18). A steady polar row is
built from the force vector `(Cx, Cy, Cz)` and the moment vector `(CMx, CMy, CMz)`
the loads export states in its own frame, x aft, y right, z up, through the one
axes module (the airframe coefficients of the ACOEF files, in N and N m):

- body axes are the export's own: `CDB == Cx`, `CYB == Cy`, `CLB == Cz`;
- stability axes by `C2(-alpha_s)` and wind axes by `C3(beta_w) C2(-alpha_s)`, the
  angles read off the velocity vector the solver builds, `(ca cb, ca sb, sa)`;
- the moments turn by the same matrices as ONE vector in one length, and only then
  take the chord or the span, which is where the c/b exchange between roll and
  pitch comes from.

THE DEFECT IT REPLACES. The row took the export's `CL` and `CDi + CDo` as
stability-axis forces and turned them BACK to body axes, so `CDB` was not the `Cx`
printed two columns away, and a point under sideslip was refused outright because
that path had been checked at zero sideslip only.

THE ORACLE is scipy's rotation, which is ACTIVE, hence the transpose; nothing here
is computed by the module under test.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

# scipy is a TEST oracle and one CI leg does not install it.
from scipy.spatial.transform import Rotation

from pyflightstream._errors import ProductError  # noqa: E402
from pyflightstream.post.axes import airframe_axis_coefficients, frame_rotations  # noqa: E402
from pyflightstream.results import parse_loads  # noqa: E402
from tests.tier1_offline.test_post_products import LOADS, _recorded_rows  # noqa: E402

CREF, BREF = 2.526, 20.0
STEMS = ("CD", "CY", "CL", "Cl", "Cm", "Cn")


def test_p0430_f152_missing_analysis_frame_is_refused(tmp_path):
    text = LOADS.replace("     Coordinate frame for analysis:              MRP\n", "")
    assert text != LOADS, "the fixture's frame line moved"
    with pytest.raises(ProductError, match="frame"):
        _recorded_rows(tmp_path, {"1": ["W"]}, loads_text=text)


def _passive(axis, angle_rad: float) -> np.ndarray:
    return Rotation.from_rotvec(np.asarray(axis, dtype=float) * angle_rad).as_matrix().T


def _oracle(force, moment, alpha_deg: float, beta_deg: float) -> dict[str, float]:
    """The eighteen axis coefficients by the written convention, through scipy."""
    a, b = math.radians(alpha_deg), math.radians(beta_deg)
    u, v, w = math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a)
    alpha_s, beta_w = math.atan2(w, u), math.asin(v)
    to_body = _passive((0, 1, 0), math.pi)
    to_stability = _passive((0, 1, 0), -alpha_s)
    to_wind = _passive((0, 0, 1), beta_w) @ to_stability
    values: dict[str, float] = {}
    for tag, turn in (("B", np.eye(3)), ("S", to_stability), ("W", to_wind)):
        f = turn @ to_body @ np.asarray(force, dtype=float)
        m = turn @ to_body @ np.asarray(moment, dtype=float)
        values |= {
            f"CD{tag}": -f[0], f"CY{tag}": f[1], f"CL{tag}": -f[2],
            f"Cl{tag}": m[0] / BREF, f"Cm{tag}": m[1] / CREF, f"Cn{tag}": m[2] / BREF,
        }  # fmt: skip
    return values


def _coefficients(force, moment, alpha_deg: float, beta_deg: float) -> dict[str, float | str]:
    """The airframe coefficients of the export's vectors, against a unit dynamic pressure."""
    return airframe_axis_coefficients(
        force,
        moment,
        frame_rotations(alpha_deg, beta_deg),
        q_ref_pa=1.0,
        sref_m2=1.0,
        cref_m=CREF,
        bref_m=BREF,
    )


def test_the_body_axis_forces_are_the_vector_the_export_prints():
    loads = parse_loads(LOADS)
    total = loads.total
    row = _coefficients(
        (total["Cx"], total["Cy"], total["Cz"]),
        (total["CMx"], total["CMy"], total["CMz"]),
        loads.angle_of_attack_deg,
        0.0,
    )
    assert row["CDB"] == pytest.approx(total["Cx"], abs=1e-12)
    assert row["CYB"] == pytest.approx(total["Cy"], abs=1e-12)
    assert row["CLB"] == pytest.approx(total["Cz"], abs=1e-12)


def _under_both_angles() -> str:
    """The loads fixture as a run at alpha 4, beta 6 prints it, with a full vector."""
    text = LOADS.replace("(Deg)                       -2.000", "(Deg)                       4.000")
    text = text.replace(
        "Side-slip angle (Deg)                       .000",
        "Side-slip angle (Deg)                       6.000",
    )  # noqa: E501
    wing = "W,+0.0193288,+0.0000000,+0.1620516,+0.1631176,+0.0012085,+0.0124530,+0.0000000,-0.0077298,+0.0000000"  # noqa: E501
    turned = "W,+0.0193288,-0.0412000,+0.1620516,+0.1631176,+0.0012085,+0.0124530,+0.0310000,-0.0077298,-0.0150000"  # noqa: E501
    assert wing in text
    return text.replace(wing, turned)


def test_every_axis_agrees_with_the_written_convention_under_both_angles():
    loads = parse_loads(_under_both_angles())
    assert (loads.angle_of_attack_deg, loads.sideslip_deg) == (4.0, 6.0)
    wing = loads.surfaces["W"]
    force = (wing["Cx"], wing["Cy"], wing["Cz"])
    moment = (wing["CMx"], wing["CMy"], wing["CMz"])
    row = _coefficients(force, moment, 4.0, 6.0)
    for name, expected in _oracle(force, moment, 4.0, 6.0).items():
        assert row[name] == pytest.approx(expected, abs=1e-12), name


def test_a_pure_pitching_moment_under_sideslip_shows_in_roll_by_the_span():
    """One vector turns, THEN each axis takes its length: the exchange between roll and pitch.

    A moment `m` about body y, at alpha 0 and beta 30, has a wind-axis roll component
    `m sin 30` and a pitch component `m cos 30`, which take the span and the chord.
    """
    text = LOADS.replace("(Deg)                       -2.000", "(Deg)                       .000")
    loads = parse_loads(text)
    body = loads.surfaces["B"]
    pitch = body["CMy"]
    row = _coefficients((0.0, 0.0, 0.0), (0.0, pitch, 0.0), 0.0, 30.0)
    assert row["CmW"] == pytest.approx(pitch * math.cos(math.radians(30.0)) / CREF, abs=1e-12)
    assert row["ClW"] == pytest.approx(pitch * math.sin(math.radians(30.0)) / BREF, abs=1e-12)


def test_a_point_under_sideslip_gets_its_polar_row(tmp_path):
    row = _recorded_rows(tmp_path, {"1": ["W"]}, loads_text=_under_both_angles())["1"]
    assert float(row["BETA"]) == 6.0
    assert float(row["CYW"]) != 0.0 and float(row["CYW"]) != float(row["CYB"])


def test_the_drag_the_solver_integrates_is_the_wind_axis_drag_of_its_own_vector(tmp_path):
    """`CDW == CDi + CDo`, the solver's own statement, on the fixture's total row.

    At the written precision of the file, five decimals, so 2e-5 out.
    """
    loads = parse_loads(LOADS)
    row = _recorded_rows(tmp_path, {"1": ["W", "B"]})["1"]
    assert float(row["CDW"]) == pytest.approx(loads.total["CDi"] + loads.total["CDo"], abs=2e-5)
    assert float(row["CD0"]) + float(row["CDI"]) == pytest.approx(float(row["CDW"]), abs=2e-5)
