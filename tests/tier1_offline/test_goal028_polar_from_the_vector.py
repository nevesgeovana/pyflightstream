"""The steady polar's twenty-four coefficients come from ONE vector, under sideslip too.

THE REQUIREMENT (block X, answers 8 and 8b of 2026-09-18). A steady polar row is
built from the force vector `(Cx, Cy, Cz)` and the moment vector `(CMx, CMy, CMz)`
the loads export states in its own frame, x aft, y right, z up, through the one
axes module:

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
import sys
from pathlib import Path

import numpy as np
import pytest

# scipy is a TEST oracle and one CI leg does not install it.
Rotation = pytest.importorskip("scipy.spatial.transform").Rotation

sys.path.insert(0, str(Path(__file__).parent))

from test_post_products import LOADS, REFERENCE  # noqa: E402

from pyflightstream.post.products import (  # noqa: E402
    PolarPoint,
    _polar_rows,
    group_coefficients,
    polar_row,
)
from pyflightstream.results import parse_loads  # noqa: E402

NAMES = (
    "ALPHA BETA MACH RE CDB CYB CLB CRB CMB CNB CDS CYS CLS CRS CMS CNS "
    "CDW CYW CLW CRW CMW CNW CD0 CDI"
).split()
CREF, BREF = 2.526, 20.0


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
            f"CR{tag}": m[0] * CREF / BREF, f"CM{tag}": m[1], f"CN{tag}": m[2] * CREF / BREF,
        }  # fmt: skip
    return values


def _row(loads, families, alpha_deg=None):
    coefficients = group_coefficients(loads, families, bref_m=BREF)
    alpha = loads.angle_of_attack_deg if alpha_deg is None else alpha_deg
    row = polar_row(alpha, 0.2, 11.77, coefficients, cref_m=CREF, bref_m=BREF)
    return dict(zip(NAMES, row, strict=True))


def test_the_body_axis_forces_are_the_vector_the_export_prints():
    loads = parse_loads(LOADS)
    row = _row(loads, ["W", "B"])
    total = loads.total
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
    coefficients = group_coefficients(loads, ["W"], bref_m=BREF)
    row = dict(
        zip(
            NAMES,
            polar_row(4.0, 0.2, 11.77, coefficients, cref_m=CREF, bref_m=BREF, beta_deg=6.0),
            strict=True,
        )
    )
    assert row["BETA"] == 6.0, "the row states the sideslip the point flew"
    for name, expected in _oracle(force, moment, 4.0, 6.0).items():
        assert row[name] == pytest.approx(expected, abs=1e-12), name


def test_a_pure_pitching_moment_under_sideslip_shows_in_roll_by_the_chord_over_the_span():
    """The c/b exchange, from the definition: one vector turns, THEN each axis takes its length.

    A moment `m` about body y, at alpha 0 and beta 30, has a wind-axis roll component
    `m sin 30` in chord units, which is `m sin 30 c/b` as a span-normalised `CRW`.
    """
    text = LOADS.replace("(Deg)                       -2.000", "(Deg)                       .000")
    loads = parse_loads(text)
    body = loads.surfaces["B"]
    coefficients = group_coefficients(loads, ["B"], bref_m=BREF)
    row = dict(
        zip(
            NAMES,
            polar_row(0.0, 0.2, 11.77, coefficients, cref_m=CREF, bref_m=BREF, beta_deg=30.0),
            strict=True,
        )
    )
    assert row["CMW"] == pytest.approx(body["CMy"] * math.cos(math.radians(30.0)), abs=1e-12)
    assert row["CRW"] == pytest.approx(
        body["CMy"] * math.sin(math.radians(30.0)) * CREF / BREF, abs=1e-12
    )


def test_a_point_under_sideslip_gets_its_polar_row(tmp_path):
    loads = parse_loads(_under_both_angles())
    path = tmp_path / "P.txt"
    point = PolarPoint(name="P", loads=loads, loads_path=path, point={"alpha": 4.0, "beta": 6.0})
    (row,) = _polar_rows([point], ["W"], mach=0.2, reference=REFERENCE)
    stated = dict(zip(NAMES, row, strict=True))
    assert stated["BETA"] == 6.0
    assert stated["CYW"] != 0.0 and stated["CYW"] != stated["CYB"]


def test_the_drag_the_solver_integrates_is_the_wind_axis_drag_of_its_own_vector():
    """`CDW == CDi + CDo`, the solver's own statement, on the fixture's total row.

    At the export's printed precision: seven decimals in, so 1e-6 out.
    """
    loads = parse_loads(LOADS)
    row = _row(loads, ["W", "B"])
    assert row["CDW"] == pytest.approx(loads.total["CDi"] + loads.total["CDo"], abs=1e-6)
    assert row["CD0"] + row["CDI"] == pytest.approx(row["CDW"], abs=1e-6)
