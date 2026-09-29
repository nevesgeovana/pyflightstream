"""The rotor table's in-plane coefficients: CN, CS, CMN and CMS (0.31.0, G8).

The rotor's axes are ``(T, S, N)``, right-handed: ``T`` its axis as declared,
``N`` the part of the reference frame's up (+z) square to ``T``, normalised,
and ``S = N x T``. ``N`` and ``S`` are the force along them and ``MN`` and
``MS`` the moment about them at the HUB, from the force and moment the table
already turns into ``CT`` and ``CQ``, each over ``rho n^2 D^4`` (forces) or
``rho n^2 D^5`` (moments).

Every number below is by hand. The loads: ``SREF`` 10 m2, ``CREF`` 1 m,
density 1.225 kg/m3 at 40 m/s, so ``q S = 0.5 * 1.225 * 40^2 * 10 = 9800`` N
per unit coefficient and 9800 N m per unit moment coefficient. The rotor: D 2
m at 3000 rev/min, ``n = 50`` rev/s, so ``rho n^2 D^4 = 1.225 * 2500 * 16 =
49000`` and ``rho n^2 D^5 = 98000``.
"""

from __future__ import annotations

import math
import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.post.axes import rotor_in_plane_axes, rotor_in_plane_loads
from pyflightstream.post.products import (
    ROTOR_IN_PLANE_COLUMNS,
    read_csv_table,
    rotor_coefficients,
    write_rotor_table,
)
from tests.tier1_offline.test_goal026_item06_rotor_loads import _reference, _surfaces

FORCE_SCALE = 49000.0
MOMENT_SCALE = 98000.0
IN_PLANE = ("CN_PUSHER", "CS_PUSHER", "CMN_PUSHER", "CMS_PUSHER")


def _rotor(axis, *, hub=(0.0, 0.0, 0.0), zero="Y"):
    from pyflightstream.cases import BladeDatum, RotorBlock

    return RotorBlock(
        alias="PUSHER",
        axis=axis,
        x_m=hub[0],
        y_m=hub[1],
        z_m=hub[2],
        diameter_m=2.0,
        families_blades=["Blade1", "Blade2"],
        blade1=BladeDatum(zero=zero),
    )


def _row(run_id="camp/sim_1/P1", **coefficients):
    return {
        "run_id": run_id,
        "surfaces": _surfaces(Blade1=coefficients),
        "condition": {"MACH": 0.12, "ALPHA": 0.0, "VINF": 40.0},
        "rpm": 3000.0,
        "density": 1.225,
        "speed": 40.0,
        "free_stream": 40.0,
        "air": (40.0, 340.0),
    }


def _table(tmp_path, rotor, *rows, reference=None):
    written = write_rotor_table(
        tmp_path / "P1-PUSHER_rotor.csv",
        rotor=rotor,
        rows=list(rows),
        reference=reference or _reference(),
    )
    assert written is not None
    return read_csv_table(written)


def _in_plane(row):
    return tuple(float(row[name]) for name in IN_PLANE)


def test_exact_values_on_a_constructed_load_with_a_known_axis(tmp_path):
    """A forward-pointing rotor (-x), its hub 1 m ahead of the moment point.

    F = 9800 (-0.4, 0.03, 0.05) = (-3920, 294, 490) N and, about the moment
    point, M = 9800 (0.01, 0.02, -0.015) = (98, 196, -147) N m. The moment
    point lies at +1 m in x from the hub, so at the hub
    M_hub = M + (1, 0, 0) x F = (98, 196 - 490, -147 + 294) = (98, -294, 147).
    T = -x, N = +z, S = N x T = -y, so N = +FZ = 490, S = -FY = -294,
    MN = +MZ_hub = 147, MS = -MY_hub = 294:
    CN = 0.01, CS = -0.006, CMN = 0.0015, CMS = 0.003.
    """
    # P0310-G8-TUNNEL
    columns, rows = _table(
        tmp_path,
        _rotor((-1.0, 0.0, 0.0)),
        _row(Cx=-0.4, Cy=0.03, Cz=0.05, CMx=0.01, CMy=0.02, CMz=-0.015),
        reference=_reference(XMOM=1.0),
    )
    assert tuple(columns[-6:]) == ("MTIP_PUSHER", "MHEL_PUSHER", *IN_PLANE), columns
    (row,) = rows
    assert _in_plane(row) == pytest.approx((0.01, -0.006, 0.0015, 0.003), abs=1e-9)
    # The same force gives the thrust, so the two sets cannot come from two loads.
    assert float(row["CT_PUSHER"]) == pytest.approx(3920.0 / FORCE_SCALE, abs=1e-9)
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
    ("load", "expected"),
    [
        # Purely along N (+z on a forward-pointing axis): CN only, positive.
        ({"Cz": 0.1}, (0.02, 0.0, 0.0, 0.0)),
        # Purely along S (-y): CS only, positive.
        ({"Cy": -0.1}, (0.0, 0.02, 0.0, 0.0)),
        # A moment purely about N (+z) and purely about S (-y), at the hub.
        ({"CMz": 0.1}, (0.0, 0.0, 0.01, 0.0)),
        ({"CMy": -0.1}, (0.0, 0.0, 0.0, 0.01)),
    ],
)
def test_a_load_purely_along_one_in_plane_axis_reaches_that_column_with_its_sign(
    tmp_path, load, expected
):
    # P0310-G8-TUNNEL
    _columns, rows = _table(tmp_path, _rotor((-1.0, 0.0, 0.0)), _row(**load))
    assert _in_plane(rows[0]) == pytest.approx(expected, abs=1e-9)


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
    """F = (-3920, 0, 490) N on the rotor tilted 10 degrees nose up.

    N = F . (sin 10, 0, cos 10) = -3920 sin 10 + 490 cos 10, S = 0; the same
    force on a level rotor gives N = 490. CT reads the tilted thrust,
    F . T = 3920 cos 10 + 490 sin 10.
    """
    # P0310-G8-TUNNEL
    tilt = math.radians(10.0)
    rotor = _rotor((-math.cos(tilt), 0.0, math.sin(tilt)))
    _columns, rows = _table(tmp_path, rotor, _row(Cx=-0.4, Cz=0.05))
    (row,) = rows
    normal = -3920.0 * math.sin(tilt) + 490.0 * math.cos(tilt)
    assert float(row["CN_PUSHER"]) == pytest.approx(normal / FORCE_SCALE, abs=1e-5)
    assert float(row["CS_PUSHER"]) == pytest.approx(0.0, abs=1e-9)
    thrust = 3920.0 * math.cos(tilt) + 490.0 * math.sin(tilt)
    assert float(row["CT_PUSHER"]) == pytest.approx(thrust / FORCE_SCALE, abs=1e-5)
    assert float(row["CN_PUSHER"]) < 490.0 / FORCE_SCALE - 0.01


def test_an_axis_along_up_reads_na_and_is_said_once(tmp_path):
    # P0310-G8-TUNNEL
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _columns, rows = _table(
            tmp_path,
            _rotor((0.0, 0.0, 1.0), zero="X"),
            _row("camp/sim_1/P1", Cz=0.5, Cx=0.1),
            _row("camp/sim_1/P2", Cz=0.4, Cy=0.1),
        )
    assert len(rows) == 2
    for row in rows:
        assert tuple(row[name] for name in IN_PLANE) == ("NA",) * 4, row
        assert row["CT_PUSHER"] != "NA"
    said = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    about = [text for text in said if "CN_PUSHER" in text]
    assert len(about) == 1, said
    assert "P1-PUSHER_rotor.csv" in about[0] and "up direction" in about[0], about[0]
    assert rotor_in_plane_axes((0.0, 0.0, -3.0)) is None


def test_the_in_plane_columns_are_defined_on_the_variables_page(tmp_path):
    # P0310-G8-TUNNEL
    from pyflightstream.post.guides import VARIABLE_DEFINITIONS, write_pproc_guides

    assert set(ROTOR_IN_PLANE_COLUMNS) <= set(VARIABLE_DEFINITIONS)
    variables, _guide = write_pproc_guides(tmp_path)
    text = variables.read_text(encoding="utf-8")
    for name in ROTOR_IN_PLANE_COLUMNS:
        assert f"`{name}_<alias>`: -. " in text, name
