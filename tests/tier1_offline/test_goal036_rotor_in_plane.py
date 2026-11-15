"""The rotor's in-plane coefficients: CN, CS, CMN and CMS (0.31.0, G8), now CFZ, CFY, CMZ, CMY.

The rotor's axes were ``(T, S, N)``, right-handed: ``T`` its axis as declared,
``N`` the part of the reference frame's up (+z) square to ``T``, normalised,
and ``S = N x T``. ``N`` and ``S`` are the force along them and ``MN`` and
``MS`` the moment about them at the HUB, from the force and moment the table
already turns into ``CT`` and ``CQ``, each over ``rho n^2 D^4`` (forces) or
``rho n^2 D^5`` (moments).

0.58.0 (design of the post outputs, 2.3 and 5.3): the rotor table is the rotor group's
``polars/P<POL>-<ALIAS>-RCOEF.csv`` and the in-plane coefficients are in the rotor frame
``R<id>`` (x forward along the shaft, y right, z down), ``CFZ = CN``, ``CFY = -CS``,
``CMZ = -CMN``, ``CMY = -CMS``; thrust is positive forward whatever the declared sense; a
vertical shaft has a defined frame (toe 0) and its in-plane coefficients are numbers.

The expected numbers are formed here from the loads written into the export, with the
definitions of the design page (the export frame x aft, y right, z up; the body frame
forward, right, down; the moment transferred from the moment point to the hub), never
read back from a product.
"""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.post.axes import rotor_in_plane_axes, rotor_in_plane_loads
from pyflightstream.post.products import (
    ROTOR_IN_PLANE_COLUMNS,
    read_csv_table,
    rotor_coefficients,
)
from pyflightstream.workspace import RunRecord

#: The fixture's export (polar 6001): reference velocity, reference area and chord.
_VREF, _SREF, _CREF, _RHO = 68.058, 50.0, 2.526, 1.225
_RPM, _DIAMETER = 1200.0, 2.0
#: q S, the Newtons of one unit force coefficient; rho n^2 D^4 and D^5.
_QS = 0.5 * _RHO * _VREF**2 * _SREF
_F4 = _RHO * (_RPM / 60.0) ** 2 * _DIAMETER**4
_F5 = _F4 * _DIAMETER
IN_PLANE = ("CFZ", "CFY", "CMZ", "CMY")
_EMPTY = {"Cx": 0.0, "Cy": 0.0, "Cz": 0.0, "CMx": 0.0, "CMy": 0.0, "CMz": 0.0}
_POINT = "POLAR-6001_M20AL+000BE+000"
FORWARD = (1.0, 0.0, 0.0)


def _shaft_of(axis):
    return "XYZ"[max(range(3), key=lambda i: abs(axis[i]))]


def _reference(axis, hub):
    shaft = _shaft_of(axis)
    along = tuple(1.0 if i == "XYZ".index(shaft) else 0.0 for i in range(3))
    if tuple(abs(c) for c in axis) == along:
        declared = f'"{shaft}"'
    else:
        declared = f'{{ shaft = "{shaft}", vector_wrt_global = {list(axis)!r} }}'
    zero = "Y" if shaft == "X" else "X"
    return (
        "area_m2 = 50.0\nchord_m = 2.526\nspan_m = 20.0\n\n"
        '[rotors.PUSHER]\nalias = "PUSHER"\n'
        f"x_m = {hub[0]}\ny_m = {hub[1]}\nz_m = {hub[2]}\n"
        f"axis = {declared}\nrpm_sign = 1\ndiameter_m = {_DIAMETER}\n"
        'families_blades = ["B"]\n'
        f'blade1 = {{ azimuth_deg = 0.0, zero = "{zero}" }}\n'
    )


def _posted(tmp_path: Path, axis, loads, *, hub=(0.0, 0.0, 0.0), mrp=(0.0, 0.0, 0.0)):
    """Polar 6001 as a quasi-steady sector at 1200 rev/min with rotor PUSHER = family B.

    The family B row of every export is the coefficient row ``loads`` states; the moment
    point of the records is ``mrp`` and the rotor's hub ``hub``. Returns the row of the
    rotor group's RCOEF file at the point AL+000 and the warnings the post said.
    """
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    unit = math.sqrt(sum(c * c for c in axis))
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r001.toml").write_text(
        _reference(axis, hub), encoding="utf-8"
    )
    c = {**_EMPTY, **loads}
    row = (
        f"     B,{c['Cx']:+.7f},{c['Cy']:+.7f},{c['Cz']:+.7f},{c['Cz']:+.7f},"
        f"+0.0000000,+0.0000000,{c['CMx']:+.7f},{c['CMy']:+.7f},{c['CMz']:+.7f}"
    )
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6001":
            loads_file = workspace.sim_dir("6001") / record.outputs[0]
            lines = loads_file.read_text(encoding="utf-8").splitlines()
            lines = [row if line.startswith("     B,") else line for line in lines]
            loads_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            quasi = {
                "schema_version": 1,
                "run_type": "qsteady_rotor",
                "case": "sector",
                "rotor": "PUSHER",
                "blades": 2,
                "rpm": _RPM,
                "shaft_frame_axis": _shaft_of(axis),
                "hub_m": list(hub),
                "axis_vector": [value / unit for value in axis],
                "diameter_m": _DIAMETER,
                "families_general": [],
                "families_blades": ["B"],
                "blade1_azimuth_deg": 0.0,
                "positions": [
                    {
                        "index": 0,
                        "clocking_deg": 0.0,
                        "rotated_deg": 0.0,
                        "loads": loads_file.name,
                    }
                ],
                "validity": None,
            }
            loads_file.with_name(loads_file.stem + "_qsteady.json").write_text(json.dumps(quasi))
            reference = {**record.reference, "XMOM": mrp[0], "YMOM": mrp[1], "ZMOM": mrp[2]}
            record = record.model_copy(update={"recipe": "qsteady_rotor", "reference": reference})
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _post(workspace)
    (manifest,) = workspace.root.rglob("products.json")
    _columns, rows = read_csv_table(manifest.parent / "polars" / "P6001-PUSHER-RCOEF.csv")
    said = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    (point,) = [row for row in rows if row["POINT"] == _POINT]
    return point, said


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def _expected(loads, axis, *, hub=(0.0, 0.0, 0.0), mrp=(0.0, 0.0, 0.0)):
    """CT, CQ and the four in-plane coefficients of the loads, from the design page.

    The export frame is x aft, y right, z up; the body frame is forward, right, down. The
    rotor frame's x is the declared shaft in body axes with the sense rule of section 5.3
    (thrust positive forward, a lift rotor's up), y the horizontal to the right (toe 0) and
    z = x cross y. ``Z`` is up, ``-F_R,z``; ``N`` and ``M`` are the hub moment's z and y.
    """
    force = tuple(loads.get(name, 0.0) * _QS for name in ("Cx", "Cy", "Cz"))
    moment = tuple(loads.get(name, 0.0) * _QS * _CREF for name in ("CMx", "CMy", "CMz"))
    arm = tuple(mrp[i] - hub[i] for i in range(3))
    transfer = _cross(arm, force)
    at_hub = tuple(moment[i] + transfer[i] for i in range(3))
    unit = math.sqrt(sum(c * c for c in axis))
    a = (-axis[0] / unit, axis[1] / unit, -axis[2] / unit)
    if a[0] < -1e-12 or (abs(a[0]) <= 1e-12 and a[2] > 0.0):
        a = (-a[0], -a[1], -a[2])
    x_r, y_r = a, (0.0, 1.0, 0.0)
    z_r = _cross(x_r, y_r)
    body_force = (-force[0], force[1], -force[2])
    body_moment = (-at_hub[0], at_hub[1], -at_hub[2])
    return {
        "CT": _dot(body_force, x_r) / _F4,
        "CQ": _dot(body_moment, x_r) / _F5,
        "CFZ": -_dot(body_force, z_r) / _F4,
        "CFY": _dot(body_force, y_r) / _F4,
        "CMZ": _dot(body_moment, z_r) / _F5,
        "CMY": _dot(body_moment, y_r) / _F5,
    }


def _check(row, expected):
    for name in ("CT", "CQ", *IN_PLANE):
        assert float(row[name]) == pytest.approx(expected[name], rel=1e-5, abs=1e-9), (
            name,
            row,
            expected,
        )


@pytest.mark.requirement("FR-188")
def test_exact_values_on_a_constructed_load_with_a_known_axis(tmp_path):
    """A rotor on the x axis (thrust forward), its hub 1 m behind the moment point.

    F = q S (-0.4, 0.03, 0.05) and, about the moment point, M = q S c (0.01, 0.02, -0.015)
    in the export frame. The moment point lies at +1 m in x from the hub, so at the hub
    M_hub = M + (1, 0, 0) x F = (Mx, My - Fz, Mz + Fy). In the rotor frame (x forward,
    y right, z down) CFZ is the upward force, CFY the force to the right, CMZ and CMY the
    hub moment about z (down) and y, which is the mapping of the design (2.3): CFZ = CN,
    CFY = -CS, CMZ = -CMN, CMY = -CMS of 0.57.0.
    """
    # P0310-G8-TUNNEL
    loads = {"Cx": -0.4, "Cy": 0.03, "Cz": 0.05, "CMx": 0.01, "CMy": 0.02, "CMz": -0.015}
    row, _said = _posted(tmp_path, FORWARD, loads, mrp=(1.0, 0.0, 0.0))
    assert float(row["XMOM"]) == 1.0, row
    expected = _expected(loads, FORWARD, mrp=(1.0, 0.0, 0.0))
    _check(row, expected)
    # The mapping to 0.57.0's N, S, MN, MS, formed apart from `_expected`.
    force = (-0.4 * _QS, 0.03 * _QS, 0.05 * _QS)
    moment = (0.01 * _QS * _CREF, 0.02 * _QS * _CREF, -0.015 * _QS * _CREF)
    hub_moment = (moment[0], moment[1] - force[2], moment[2] + force[1])
    assert expected["CFZ"] == pytest.approx(force[2] / _F4, rel=1e-12)
    assert expected["CFY"] == pytest.approx(force[1] / _F4, rel=1e-12)
    assert expected["CMZ"] == pytest.approx(-hub_moment[2] / _F5, rel=1e-12)
    assert expected["CMY"] == pytest.approx(hub_moment[1] / _F5, rel=1e-12)
    # The same force gives the thrust, so the two sets cannot come from two loads.
    assert float(row["CT"]) == pytest.approx(0.4 * _QS / _F4, rel=1e-5)
    assert rotor_in_plane_loads((-3920.0, 294.0, 490.0), (98.0, -294.0, 147.0), (-1, 0, 0)) == (
        pytest.approx((490.0, -294.0, 147.0, 294.0), abs=1e-9)
    )


def test_rotor_coefficients_normalise_the_in_plane_loads_by_the_magnitude_of_the_rate():
    # P0310-G8-TUNNEL
    for rps in (50.0, -50.0):
        values = rotor_coefficients(
            thrust_n=3920.0,
            torque_nm=98.0,
            rps=rps,
            diameter_m=2.0,
            density_kg_m3=1.225,
            speed_m_s=40.0,
            wind_force_n=3920.0,
            in_plane_loads=(490.0, -294.0, 147.0, 294.0),
        )
        got = tuple(values[name] for name in ROTOR_IN_PLANE_COLUMNS)
        assert got == pytest.approx((0.01, -0.006, 0.0015, 0.003), abs=1e-12), rps
    silent = rotor_coefficients(
        thrust_n=3920.0,
        torque_nm=98.0,
        rps=50.0,
        diameter_m=2.0,
        density_kg_m3=1.225,
        speed_m_s=40.0,
    )
    assert all(silent[name] == "NA" for name in ROTOR_IN_PLANE_COLUMNS), silent
    unknown = rotor_coefficients(
        thrust_n=3920.0,
        torque_nm=98.0,
        rps=50.0,
        diameter_m=2.0,
        density_kg_m3=1.225,
        speed_m_s=40.0,
        in_plane_loads=(math.nan, 0.0, 0.0, 0.0),
    )
    assert all(unknown[name] == "NA" for name in ROTOR_IN_PLANE_COLUMNS), unknown


@pytest.mark.parametrize(
    ("load", "only", "sign"),
    [
        # Purely up (the old N, +z on a forward-pointing axis): CFZ only, positive.
        ({"Cz": 0.1}, "CFZ", 1.0),
        # Purely to the right (the old -S): CFY only, positive.
        ({"Cy": 0.1}, "CFY", 1.0),
        # A moment about +z (up) is about -z of the rotor frame (down): CMZ negative.
        ({"CMz": 0.1}, "CMZ", -1.0),
        # A moment about +y (right) is the same about y of the rotor frame: CMY positive.
        ({"CMy": 0.1}, "CMY", 1.0),
    ],
)
def test_a_load_purely_along_one_in_plane_axis_reaches_that_column_with_its_sign(
    tmp_path, load, only, sign
):
    # P0310-G8-TUNNEL
    row, _said = _posted(tmp_path, FORWARD, load)
    _check(row, _expected(load, FORWARD))
    assert float(row[only]) * sign > 0.0, row
    for name in IN_PLANE:
        if name != only:
            assert float(row[name]) == pytest.approx(0.0, abs=1e-9), (name, row)


def test_the_axes_are_right_handed_and_follow_a_tilted_axis():
    """A forward axis tilted 10 degrees nose up: T = (-cos 10, 0, sin 10).

    N = up - (up . T) T, normalised, = (sin 10, 0, cos 10); S = N x T = (0, -1, 0).
    """
    # P0310-G8-TUNNEL
    tilt = math.radians(10.0)
    axes = rotor_in_plane_axes((-math.cos(tilt), 0.0, math.sin(tilt)))
    assert axes is not None
    thrust, side, normal = (tuple(float(c) for c in vector) for vector in axes)
    assert normal == pytest.approx((math.sin(tilt), 0.0, math.cos(tilt)), abs=1e-12)
    assert side == pytest.approx((0.0, -1.0, 0.0), abs=1e-12)
    cross = (
        thrust[1] * side[2] - thrust[2] * side[1],
        thrust[2] * side[0] - thrust[0] * side[2],
        thrust[0] * side[1] - thrust[1] * side[0],
    )
    assert cross == pytest.approx(normal, abs=1e-12)


def test_a_tilted_rotor_resolves_its_load_on_its_own_normal(tmp_path):
    """F = q S (-0.4, 0, 0.05) on the rotor tilted 10 degrees nose up.

    The shaft is declared along +x tilted down in the export frame, (cos 10, 0, -sin 10),
    the same line as the forward axis (-cos 10, 0, sin 10) of 0.57.0 (a negative
    direction is no longer a valid declaration; the sense rule of the design gives the
    same thrust direction). N = F . (sin 10, 0, cos 10) = q S (-0.4 sin 10 + 0.05 cos 10),
    S = 0; the same force on a level rotor gives N = 0.05 q S. CT reads the tilted
    thrust, F . T = q S (0.4 cos 10 + 0.05 sin 10).
    """
    # P0310-G8-TUNNEL
    tilt = math.radians(10.0)
    axis = (math.cos(tilt), 0.0, -math.sin(tilt))
    loads = {"Cx": -0.4, "Cz": 0.05}
    row, _said = _posted(tmp_path, axis, loads)
    _check(row, _expected(loads, axis))
    normal = (-0.4 * math.sin(tilt) + 0.05 * math.cos(tilt)) * _QS
    assert float(row["CFZ"]) == pytest.approx(normal / _F4, rel=1e-5)
    assert float(row["CFY"]) == pytest.approx(0.0, abs=1e-9)
    thrust = (0.4 * math.cos(tilt) + 0.05 * math.sin(tilt)) * _QS
    assert float(row["CT"]) == pytest.approx(thrust / _F4, rel=1e-5)
    assert float(row["CFZ"]) < 0.5 * 0.05 * _QS / _F4


def test_p0410_a_vertical_axis_has_a_defined_frame_and_its_in_plane_coefficients_are_numbers(
    tmp_path,
):
    """A lift rotor (shaft +z) has toe 0 and thrust up (design 5.3): nothing reads NA.

    0.57.0 read NA for the four in-plane coefficients and said so once, naming a
    vertical axis; the design gives the vertical shaft a frame, so the replacement
    assertion is that the numbers are the hand calculation and no such warning is said.
    """
    # P0310-G8-TUNNEL
    axis = (0.0, 0.0, 1.0)
    loads = {"Cz": 0.4, "Cx": 0.1}
    row, said = _posted(tmp_path, axis, loads)
    for name in IN_PLANE:
        assert row[name] != "NA", row
    assert row["CT"] != "NA"
    _check(row, _expected(loads, axis))
    assert not [text for text in said if "vertical axis" in text], said
    assert rotor_in_plane_axes((0.0, 0.0, -3.0)) is None


def test_the_in_plane_columns_are_defined_on_the_variables_page(tmp_path):
    # P0310-G8-TUNNEL
    from pyflightstream.post.guides import VARIABLE_DEFINITIONS, write_pproc_guides

    assert set(ROTOR_IN_PLANE_COLUMNS) <= set(VARIABLE_DEFINITIONS)
    variables, _guide = write_pproc_guides(tmp_path)
    text = variables.read_text(encoding="utf-8")
    for name in ROTOR_IN_PLANE_COLUMNS:
        assert f"`{name}_<alias>`: -. " in text, name
