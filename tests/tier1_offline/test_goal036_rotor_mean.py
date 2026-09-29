"""Tier 1: the rotor table of a quasi-steady wheel is the mean of its clockings (0.31.0).

P0310-ROTOR-MEAN (0.31.0): a wheel point's row
of ``polars/P<sim>-<ALIAS>_rotor.csv`` is taken from the mean of the rotor's
force and moment over its k clockings, each clocking's own loads export, and
every coefficient (``CT``, ``CQ``, ``CP``, ``ETA``, ``ETAW``, ``CN``, ``CS``,
``CMN``, ``CMS``) is then computed from those mean loads, never averaged
itself. A sector (one solve) is unchanged, and a clocking whose export is
missing costs the point its row, named, rather than a mean of the rest.

Polar 6001 of the recorded campaign is re-recorded as a quasi-steady wheel of
two clockings at 1200 rev/min on a 2 m rotor PROP whose surfaces are W and B.
"""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import pytest

from pyflightstream.workspace import RunRecord
from tests.tier1_offline.test_goal035_l1_defects import _PROP_REFERENCE

#: W's row of the recorded export up to its CMx, and the same row with W's Cx
#: and CMx set to a clocking's own values.
_W_ROW = "W,+0.0193288,+0.0000000,+0.1620516,+0.1631176,+0.0012085,+0.0124530,+0.0000000"
_B_CX = 0.0081038
_CREF = 2.526
_SPEED = 68.058
#: q S, the Newtons of one unit of force coefficient; rho n^2 D^4 and D^5.
_QS = 0.5 * 1.225 * _SPEED**2 * 50.0
_RHO_N2_D4 = 1.225 * 20.0**2 * 2.0**4
_RHO_N2_D5 = _RHO_N2_D4 * 2.0
_J = _SPEED / (20.0 * 2.0)


def _w_row(cx: float, cmx: float, cz: float = 0.1620516) -> str:
    return (
        _W_ROW.replace("+0.0193288", f"{cx:+.7f}")
        .replace(",+0.0124530,+0.0000000", f",+0.0124530,{cmx:+.7f}")
        .replace("+0.1620516", f"{cz:+.7f}")
    )


def _posted(
    tmp_path: Path,
    case: str,
    clockings: tuple[tuple[float, ...], ...],
    *,
    drop: int | None = None,
) -> tuple[dict, Path]:
    """Post polar 6001 as a quasi-steady ``case``; clocking i states W's (Cx, CMx[, Cz]).

    ``drop`` removes that clocking's loads export from disk before the post.
    """
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r001.toml").write_text(
        _PROP_REFERENCE, encoding="utf-8"
    )
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6001":
            loads = workspace.sim_dir("6001") / record.outputs[0]
            recorded = loads.read_text(encoding="utf-8")
            assert _W_ROW in recorded
            positions = []
            for index, stated in enumerate(clockings):
                path = loads if index == 0 else loads.with_name(f"{loads.stem}_qs{index:02d}.txt")
                path.write_text(recorded.replace(_W_ROW, _w_row(*stated)), encoding="utf-8")
                positions.append(
                    {
                        "index": index,
                        "clocking_deg": 90.0 * index,
                        "rotated_deg": 90.0 * index,
                        "loads": path.name,
                    }
                )
                if drop is not None and index == drop:
                    path.unlink()
            quasi = {
                "schema_version": 1,
                "run_type": "qsteady_rotor",
                "case": case,
                "rotor": "PROP",
                "blades": 2,
                "rpm": 1200.0,
                "shaft_frame_axis": "X",
                "hub_m": [0.0, 0.0, 0.0],
                "axis_vector": [1.0, 0.0, 0.0],
                "diameter_m": 2.0,
                "families_general": [],
                "families_blades": ["W", "B"],
                "blade1_azimuth_deg": 0.0,
                "positions": positions,
                "validity": None,
            }
            loads.with_name(loads.stem + "_qsteady.json").write_text(json.dumps(quasi))
            record = record.model_copy(update={"recipe": "qsteady_rotor"})
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _post(workspace)
    (manifest,) = workspace.root.rglob("products.json")
    return json.loads(manifest.read_text(encoding="utf-8")), manifest.parent


def _rotor_table(products: dict, folder: Path) -> tuple[str, list[dict[str, str]]]:
    (name,) = [name for name in products["products"] if name.endswith("PROP_rotor.csv")]
    head, *rows = (folder / name).read_text(encoding="utf-8").splitlines()
    return name, [dict(zip(head.split(","), row.split(","), strict=True)) for row in rows]


def _eta(cx: float, cmx: float) -> float:
    """ETA = J CT / CP of loads (Cx q S, CMx q S c) along a +x shaft at +1200 rev/min."""
    ct = cx * _QS / _RHO_N2_D4
    cp = 2.0 * math.pi * cmx * _QS * _CREF / _RHO_N2_D5
    return _J * ct / cp


def test_a_wheel_s_rotor_row_is_taken_from_the_mean_loads_of_its_clockings(tmp_path):
    """Two clockings, W's (Cx, CMx) (0.0193288, 0.01) then (0.0293288, 0.03).

    The rotor's thrust coefficient is W's Cx plus B's 0.0081038: 0.0274326 and
    0.0374326, mean 0.0324326; its torque is W's CMx q S c, mean 0.02 q S c.
    ETA from the mean loads is J CT / CP of those means, 1.62163 of J D / (2 pi c)
    (0.3477), and the mean of the two clockings' own ETA is 1.99551 of it (0.4278).
    """
    # P0310-ROTOR-MEAN
    products, folder = _posted(tmp_path, "wheel", ((0.0193288, 0.01), (0.0293288, 0.03)))
    name, rows = _rotor_table(products, folder)
    assert len(rows) == 2
    thrust = ((0.0193288 + _B_CX) + (0.0293288 + _B_CX)) / 2.0
    for row in rows:
        assert float(row["CT_PROP"]) == pytest.approx(thrust * _QS / _RHO_N2_D4, rel=1e-5)
        assert float(row["CQ_PROP"]) == pytest.approx(0.02 * _QS * _CREF / _RHO_N2_D5, rel=1e-5)
        eta = float(row["ETA_PROP"])
        assert eta == pytest.approx(_eta(thrust, 0.02), rel=1e-4)
        assert abs(eta - (_eta(0.0274326, 0.01) + _eta(0.0374326, 0.03)) / 2.0) > 0.05
        # The shaft lies along the stream at alpha 0, where ETAW is ETA of the same loads.
        if float(row["ALPHA"]) == 0.0:
            assert float(row["ETAW_PROP"]) == pytest.approx(eta, rel=1e-4)
    entry = products["products"][name]
    assert entry["source"] == "mean of 2 clockings"
    assert entry["clockings"] == 2


def test_the_in_plane_coefficients_of_a_wheel_are_of_the_mean_loads(tmp_path):
    """W's Cz is 0.1620516 then 0.2620516, so CN is the up component of the mean force.

    The shaft is +x, so N is +z: CN = (0.2120516 + 0.0251063) q S / (rho n^2 D^4),
    B's Cz being the recorded 0.0251063 at both clockings.
    """
    # P0310-ROTOR-MEAN
    products, folder = _posted(
        tmp_path, "wheel", ((0.0193288, 0.01, 0.1620516), (0.0293288, 0.03, 0.2620516))
    )
    _, rows = _rotor_table(products, folder)
    for row in rows:
        assert float(row["CN_PROP"]) == pytest.approx(
            (0.2120516 + 0.0251063) * _QS / _RHO_N2_D4, rel=1e-5
        )


def test_a_sector_is_its_one_solve_as_before(tmp_path):
    """A sector's row and entry are unchanged: its one export, no mean, the steady source."""
    # P0310-ROTOR-MEAN
    products, folder = _posted(tmp_path, "sector", ((0.0193288, 0.01),))
    name, rows = _rotor_table(products, folder)
    assert len(rows) == 2
    for row in rows:
        assert float(row["CT_PROP"]) == pytest.approx(
            (0.0193288 + _B_CX) * _QS / _RHO_N2_D4, rel=1e-5
        )
    entry = products["products"][name]
    assert entry["source"] == "the loads export of a steady run"
    assert "clockings" not in entry


def test_a_wheel_whose_clocking_export_is_missing_is_a_named_skip(tmp_path):
    """Clocking 1's export is gone: no row, named in skipped, never the mean of clocking 0 alone."""
    # P0310-ROTOR-MEAN
    products, folder = _posted(tmp_path, "wheel", ((0.0193288, 0.01), (0.0293288, 0.03)), drop=1)
    assert not [name for name in products["products"] if name.endswith("PROP_rotor.csv")]
    (reason,) = [
        text for key, text in products["skipped"].items() if key.endswith("PROP_rotor.csv")
    ]
    assert "_qs01.txt" in reason and "is not on disk" in reason
    assert "the row of a wheel is the mean of all its clockings" in reason


def test_each_clocking_is_taken_back_to_the_point_s_speed_before_the_mean(tmp_path):
    """Clocking 1 is exported at TWICE the point's reference velocity.

    Its coefficients are normalised by (2 V)^2, so its loads are 4 times what
    the same coefficient means at V: taken back to V, W's Cx of 0.0193288 at
    clocking 1 stands for 4 x 0.0193288, and the mean over the two clockings
    is (1 + 4) / 2 = 2.5 times 0.0193288. Read at face value it would be
    0.0193288 itself.
    """
    # P0310-ROTOR-MEAN
    from pyflightstream.cases import qsteady as arithmetic
    from pyflightstream.post import qsteady as post_qsteady
    from tests.tier1_offline.test_post_superfile import _loads

    for index, velocity in ((0, "68.058"), (1, "136.116")):
        (tmp_path / f"c{index}.txt").write_text(_loads(0.0, velocity=velocity), encoding="utf-8")
    record = arithmetic.QsteadyRecord(
        case="wheel",
        rotor_alias="PROP",
        blades=2,
        rpm=1200.0,
        shaft_frame_axis="X",
        hub_m=(0.0, 0.0, 0.0),
        axis_vector=(1.0, 0.0, 0.0),
        diameter_m=2.0,
        families_general=(),
        families_blades=("W", "B"),
        blade1_azimuth_deg=0.0,
        positions=(
            arithmetic.QsteadyClocking(0, 0.0, 0.0, "c0.txt"),
            arithmetic.QsteadyClocking(1, 90.0, 90.0, "c1.txt"),
        ),
        validity=None,
    )
    mean = post_qsteady.mean_clocking_surfaces(record, tmp_path, speed_m_s=68.058)
    assert isinstance(mean, post_qsteady.ClockingMean) and mean.clockings == 2
    assert mean.surfaces["W"]["Cx"] == pytest.approx(2.5 * 0.0193288, rel=1e-12)
    assert mean.surfaces["B"]["CMy"] == pytest.approx(2.5 * -0.0892137, rel=1e-12)
    assert mean.surfaces["W"]["Cx"] != pytest.approx(0.0193288, rel=1e-3)
