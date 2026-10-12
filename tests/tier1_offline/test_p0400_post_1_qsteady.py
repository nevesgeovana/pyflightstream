"""P0400 quasi-steady defects (post-1 lane).

P0400-CLOCKINGSPEED (PFS-2105.036): a clocking whose export states no reference
velocity is named in the clockings and average tables, as the rotor table names
it, never read at the free-stream speed.
P0400-MRPRADIUS (PFS-2105.035): a cut in the MRP frame places its station at
Offset minus the hub's coordinate along the cut normal, and is NA where the hub
sits off the plane's radial line.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from pyflightstream.cases.qsteady import reduced_frequency
from pyflightstream.post.qsteady import add_reduced_frequency_to_sections
from tests.tier1_offline.test_goal036_qsteady_corrections import _post_recorded, _recorded_wheel


@pytest.mark.parametrize((), [pytest.param(id="P0400-CLOCKINGSPEED")])
def test_p0400_clockingspeed_a_clocking_without_reference_velocity_is_named(tmp_path):
    """P0400-CLOCKINGSPEED: clocking 1 states no reference velocity; its point is left out."""
    workspace = _recorded_wheel(tmp_path)
    # Clocking 1 of every point of the polar (the recorded wheel holds two points).
    seconds = sorted(workspace.sim_dir("6001").rglob("*_qs01.txt"))
    assert seconds
    for second in seconds:
        lines = second.read_text(encoding="utf-8").splitlines(keepends=True)
        second.write_text(
            "".join(line for line in lines if "Reference velocity" not in line), encoding="utf-8"
        )
    products, _folder, _log = _post_recorded(workspace)
    named = {
        key: why
        for key, why in products["skipped"].items()
        if key.split("#", 1)[0].endswith("_qs_positions.csv")
    }
    assert any(
        "clocking 1" in why and "states no reference velocity" in why for why in named.values()
    ), products["skipped"]


def _sections(tmp_path, hub):
    path = tmp_path / "sections.csv"
    path.write_text(
        "ROTOR,FAMILY,PLANE,Offset,Chord,Fx,Fz\n"
        "PROP,B,XZ,1.5,0.2,10.0,2.0\n"
        "PROP,B,XZ,2.0,0.2,12.0,3.0\n"
        "PROP,B,XY,1.0,0.2,8.0,1.0\n",
        encoding="utf-8",
    )
    record = SimpleNamespace(
        rotor_alias="PROP",
        rpm=1200.0,
        families_blades=["B"],
        hub_m=hub,
        axis_vector=(1.0, 0.0, 0.0),
        shaft_frame_axis="X",
    )
    layout = [
        {"families": ["B"], "plane": "XZ", "frame": "MRP"},
        {"families": ["B"], "plane": "XY", "frame": "PROP_RMRP"},
    ]
    validity = add_reduced_frequency_to_sections(
        path, cast(Any, record), velocity_m_per_s=30.0, layout=layout
    )
    rows = path.read_text(encoding="utf-8").splitlines()
    return validity, rows


@pytest.mark.parametrize((), [pytest.param(id="P0400-MRPRADIUS")])
def test_p0400_mrpradius_the_station_is_measured_from_the_hub(tmp_path):
    """P0400-MRPRADIUS: hub at y = 0.5; the station at Offset 1.5 is at r = 1.0."""
    validity, rows = _sections(tmp_path, (0.0, 0.5, 0.0))
    header = rows[0].split(",")
    first = dict(zip(header, rows[1].split(","), strict=True))
    omega = 1200.0 * 2.0 * 3.141592653589793 / 60.0
    expected = reduced_frequency(
        omega_rad_s=omega, chord_m=0.2, radius_m=1.0, velocity_m_per_s=30.0
    )
    assert float(first["K_1P"]) == pytest.approx(expected, rel=1e-4)
    assert validity is not None


@pytest.mark.parametrize((), [pytest.param(id="P0400-MRPRADIUS")])
def test_p0400_mrpradius_a_hub_off_the_radial_line_is_na(tmp_path):
    """P0400-MRPRADIUS: hub at z = 0.3 (off the XZ cut's radial line): K_1P NA, said."""
    validity, rows = _sections(tmp_path, (0.0, 0.0, 0.3))
    header = rows[0].split(",")
    first = dict(zip(header, rows[1].split(","), strict=True))
    assert first["K_1P"] == "NA"
    assert validity is not None
    assert any("K_1P of rotor PROP reads NA" in note for note in validity.notes), validity.notes
    assert validity.values["THRUST_PCT_K_GT_0_1"] is None
