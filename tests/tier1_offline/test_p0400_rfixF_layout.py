"""P0400-RFIXF-LAYOUT: the far field integrates exactly the probes the run laid (PFS-2081.56, .58).

The plan chooses the far-field plane and lattice once, by frame and by the
exact laid-out points (a declared ``[[probes]]`` shape reused, or the far
field's own added), records the choice on the script, the run carries it in
its record, and post matches every exported position to it before it
integrates; what it cannot match exactly once is a named skip. Every fixture is
synthetic: a box mesh, a uniform stream, a uniform crossflow.
"""
# ruff: noqa: N999 - the assigned lane name is rfixF.

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.cases._farfield_spec import LatticeShape
from pyflightstream.cases.workflows._farfield import plan_record
from pyflightstream.probes.layouts import farfield_plane, lattice_points
from pyflightstream.workspace import RunRecord, RunStatus
from tests.tier1_offline import test_p0400_ffproof_post as ffpost
from tests.tier1_offline.test_p0400_farfield_plan import _case, _script

_RHO = ffpost._RHO
_SPEED = 68.058  # the free stream of the loads fixture, m/s
_ALPHA = -2.0  # its incidence, deg
_SREF = 50.0
_Q = 0.5 * _RHO * _SPEED**2


def _export(points: np.ndarray, velocity: np.ndarray) -> str:
    """A steady probe-points export of ``points`` (native) with ``velocity`` (m/s) at each."""
    rows = "".join(
        "     "
        + ", ".join(
            f"{v: .6E}"
            for v in (*p, 0.1, 0.0, *u, float(np.linalg.norm(u)), 0.0)  # X Y Z Mach Cp_ref vxyz
        )
        + ", 0.0000E+00" * 6
        + ",\n"
        for p, u in zip(points, velocity, strict=True)
    )
    fixture = Path(ffpost.__file__).parent / "fixtures" / "probe_points_26.120.txt"
    text = fixture.read_text(encoding="utf-8")
    columns = (
        "     X, Y, Z, Mach, Cp_ref, vx, vy, vz, vtot, Cp, s_len, momentum_thickness, disp_thick,"
    )
    head, _, tail = text.partition(columns)
    head = head.replace(
        "Number of Probe Points:                     12",
        f"Number of Probe Points:                     {len(points)}",
    )
    footer = tail.split(ffpost._RULE)[-1]
    rule = ffpost._RULE
    return head + columns + tail.split("\n", 1)[0] + "\n" + rule + rows + rule + footer


def _rows(root: Path, pattern: str) -> list[dict[str, str]]:
    found = sorted(root.rglob(pattern))
    if not found:
        return []
    with found[0].open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _skipped(root: Path) -> dict[str, str]:
    manifest = json.loads(ffpost._one(root, "products.json").read_text(encoding="utf-8"))
    return {k: v for k, v in manifest.get("skipped", {}).items() if k.startswith("farfield/")}


# ------------------------------------------------------------- the plane (PFS-2081.58)

_DIRECTION = (math.cos(math.radians(_ALPHA)), 0.0, math.sin(math.radians(_ALPHA)))
#: The plane the run laid: 3 by 3 points 1 m apart, 4 m^2 by the trapezoid rule.
_LAID = farfield_plane(
    (30.0, 0.0, 1.0), _DIRECTION, distance=0.0, half_width=1.0, half_height=1.0, spacing=1.0
)
#: The table as it stands at post states another 3 by 3 grid, 2 m apart (16 m^2).
_TABLE_2M = (
    '[farfield]\nfamilies = "all"\n[farfield.trefftz]\nvariant = "plane"\n'
    "half_width_bref = 0.1\nhalf_height_bref = 0.1\nspacing_bref = 0.1\n"
)
_TABLE_1M = _TABLE_2M.replace("0.1", "0.05")
_PLANE_RECORD = {
    "shapes": [
        {
            "kind": "plane",
            "source": "added",
            "entry": None,
            "count": 9,
            "center_m": [30.0, 0.0, 1.0],
            "direction": list(_DIRECTION),
            "half_width_m": 1.0,
            "half_height_m": 1.0,
            "spacing_m": 1.0,
        }
    ]
}


def _crossflow_plane(tmp_path: Path, table: str, **record: object):
    """A point whose export holds the laid plane in the free stream plus 1 m/s along its y."""
    velocity = np.tile(np.asarray(_DIRECTION) * _SPEED + _LAID.axes[1], (len(_LAID.points), 1))
    workspace = ffpost._campaign(
        tmp_path,
        pproc=table,
        files={f"{ffpost._STEM}_probes.txt": _export(_LAID.points, velocity)},
    )
    if record:
        ffpost._set_record(workspace, **record)
    ffpost._post(workspace)
    return Path(workspace.root)


@pytest.mark.requirement("FR-453")
@pytest.mark.requirement("FR-455")
def test_p0400_rfixf_the_recorded_plane_is_integrated_with_its_own_grid(tmp_path):
    """P0400-RFIXF-LAYOUT (PFS-2081.58): the table changed to a grid of the same count.

    The run laid 3 by 3 points 1 m apart; the table now states 3 by 3 points
    2 m apart. Before the fix post took the plane by its count and gave it the
    table's grid, 16 m^2 for 4, so the crossflow energy of a 1 m/s crossflow
    was 4 times too large; it integrates the recorded grid now.
    """
    root = _crossflow_plane(tmp_path, _TABLE_2M, farfield_layout=_PLANE_RECORD)
    (row,) = [r for r in _rows(root, "farfield/*_trefftz.csv") if r["VARIANT"] == "C"]
    drag = 0.5 * _RHO * 1.0 * 4.0  # rho/2 * v^2 * the laid plane's area, N
    assert float(row["CDI_T"]) == pytest.approx(drag / (_Q * _SREF), rel=1e-5)
    assert float(row["N_TRACE"]) == 9


@pytest.mark.requirement("FR-453")
def test_p0400_rfixf_a_record_without_a_layout_matches_the_plane_by_shape(tmp_path):
    """P0400-RFIXF-LAYOUT (PFS-2081.58): no layout recorded, the table's grid is matched.

    The same export posted against a table stating the laid grid gives the
    4 m^2 value; against a table stating another grid of the same count it is
    a named skip and no C row, never the 16 m^2 value.
    """
    (tmp_path / "same").mkdir()
    root = _crossflow_plane(tmp_path / "same", _TABLE_1M)
    (row,) = [r for r in _rows(root, "farfield/*_trefftz.csv") if r["VARIANT"] == "C"]
    assert float(row["CDI_T"]) == pytest.approx(0.5 * _RHO * 4.0 / (_Q * _SREF), rel=1e-5)
    (tmp_path / "other").mkdir()
    root = _crossflow_plane(tmp_path / "other", _TABLE_2M)
    assert not [r for r in _rows(root, "farfield/*_trefftz.csv") if r["VARIANT"] == "C"]
    (reason,) = _skipped(root).values()
    assert "shape of the plane" in reason


# ----------------------------------------------- a frame's lattice (PFS-2081.58)

_POINTS = ffpost._POINTS_M
_LATTICE = ffpost._SHAPE.build(1.0)
_OTHER = 20


def _lattice_then_another_entry(tmp_path: Path, **record: object):
    """The MRP lattice in a 20 m/s stream, then twenty probes of another entry at 50 m/s."""
    other = np.array([[5.0, float(k), 0.0] for k in range(_OTHER)])
    positions = np.vstack([_POINTS, other])
    stream = np.tile([20.0, 0.0, 0.0], (len(_POINTS), 1))
    velocity = np.vstack([stream, np.tile([50.0, 0.0, 0.0], (_OTHER, 1))])
    workspace = ffpost._campaign(
        tmp_path,
        pproc=ffpost._LEDGERS,
        files={f"{ffpost._STEM}_probes.txt": _export(positions, velocity)},
    )
    if record:
        ffpost._set_record(workspace, **record)
    ffpost._post(workspace)
    return _rows(Path(workspace.root), "farfield/*_ledgers.csv")


def _annulus() -> float:
    edges = _LATTICE.ring_edges
    return math.pi * (edges[-1] ** 2 - edges[0] ** 2) * _LATTICE.tip_radius**2


@pytest.mark.requirement("FR-38")
@pytest.mark.parametrize("recorded", [False, True], ids=["legacy-record", "recorded-layout"])
def test_p0400_rfixf_a_frame_lattice_before_another_entry_is_found(tmp_path, recorded):
    """P0400-RFIXF-LAYOUT (PFS-2081.58): the lattice, not the last points of the export.

    Before the fix post took a frame's lattice as the last points of the
    export, here the last 48: 28 lattice points and the 20 probes of the next
    entry at 50 m/s, which landed on the lateral rings and the outlet
    station, so the outlet's mass flow was not the lattice's. It is the
    uniform stream's ``rho V A`` at every station now, with the layout
    recorded and without it.
    """
    record = {}
    if recorded:
        shape = {
            "kind": "lattice",
            "source": "declared",
            "entry": 1,
            "count": len(_POINTS),
            "lattice": _LATTICE.model_dump(mode="json"),
            "axis": "X",
            "origin_m": [0.0, 0.0, 0.0],
            "positions_frame": "MRP",
        }
        record = {"farfield_layout": {"shapes": [shape]}}
    rows = _lattice_then_another_entry(tmp_path, **record)
    assert [float(row["STATION_X_R"]) for row in rows] == [-1.0, 1.0]
    for row in rows:
        assert float(row["MDOT_KG_S"]) == pytest.approx(_RHO * 20.0 * _annulus(), rel=1e-6)


# ---------------------------------------------------- planning (PFS-2081.56)


def _states(record: dict, analysis: str) -> set[str]:
    return {
        item["state"]
        for item in record["inputs"]
        if item["analysis"] == analysis and item["input"] == "probe_points"
    }


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf_a_unique_nondefault_lattice_is_reused(tmp_path):
    """P0400-RFIXF-LAYOUT (FR-455 R2): a table stating no geometry reuses the one declared.

    The ledgers name the rotor and state no lattice key; one ``[[probes]]``
    lattice is declared on that rotor with its own stations and rings. It is
    reused: the script lays its points once, adds none, records it as the
    declared entry, and the plan says reused. Before the fix the raw fields
    differed, the plan said added and the default lattice was laid beside it.
    """
    declared = {"rotor": "ROTOR", "stations": [2.0], "n_r": 2, "n_psi": 16}
    case = _case(
        tmp_path,
        {"families": "all", "ledgers": {"rotor": "ROTOR", "m_max": 2}},
        probes=[{"frame": "REFERENCE", "parameters": ["VX"], "lattices": [declared]}],
    )
    script = _script(case)
    count = LatticeShape.model_validate(declared).build(1.0).point_count
    assert len(script.probe_points) == count, "laid once, the declared entry"
    (shape,) = script.farfield_layout[-1]["shapes"]
    assert (shape["kind"], shape["source"], shape["entry"]) == ("lattice", "declared", 1)
    assert shape["lattice"]["stations"] == [2.0]
    assert _states(plan_record(case, "26.124", script), "ledgers") == {"reused"}


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf_a_default_equivalent_geometry_is_reused(tmp_path):
    """P0400-RFIXF-LAYOUT (FR-455 R2): a stated key equal to its default is the same lattice.

    The ledgers state ``r_inner = 0.05``, the default the declared lattice
    takes by leaving it unstated: the same points after layout, so the
    declaration is reused; the raw fields differed before the fix.
    """
    shape = {"rotor": "ROTOR", "stations": [2.0], "n_r": 2, "n_psi": 16}
    case = _case(
        tmp_path,
        {"families": "all", "ledgers": dict(shape, r_inner=0.05, m_max=2)},
        probes=[{"frame": "REFERENCE", "parameters": ["VX"], "lattices": [shape]}],
    )
    script = _script(case)
    assert len(script.probe_points) == LatticeShape.model_validate(shape).build(1.0).point_count
    assert script.farfield_layout[-1]["shapes"][0]["source"] == "declared"
    assert _states(plan_record(case, "26.124", script), "ledgers") == {"reused"}


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf_a_declared_plane_is_reused(tmp_path):
    """P0400-RFIXF-LAYOUT (FR-455 R2): the one rectangle that is a Trefftz plane is reused.

    No plane key is stated; one rectangle is declared behind the box, normal
    to the free stream, 5 by 3 points 0.5 m apart. It is the far field's
    plane: no plane is added, the layout names the entry with the
    rectangle's center and grid, and the plan says reused. Before the fix the
    plan always added its own plane.
    """
    rectangle = {
        "origin": [3.0, -1.0, -0.5],
        "along_u": [3.0, 1.0, -0.5],
        "along_v": [3.0, -1.0, 0.5],
        "points_u": 5,
        "points_v": 3,
    }
    case = _case(
        tmp_path,
        {"families": "all", "trefftz": {"variant": "plane"}},
        probes=[{"frame": "REFERENCE", "parameters": ["VX"], "rectangles": [rectangle]}],
    )
    script = _script(case)
    assert len(script.probe_points) == 15, "the declared rectangle alone"
    assert "PROBE_POINTS_IMPORT" not in script.render(), "no far-field plane added"
    (shape,) = script.farfield_layout[-1]["shapes"]
    assert (shape["kind"], shape["source"], shape["entry"]) == ("plane", "declared", 1)
    assert shape["center_m"] == pytest.approx([3.0, 0.0, 0.0])
    assert (shape["half_width_m"], shape["half_height_m"], shape["spacing_m"]) == pytest.approx(
        (1.0, 0.5, 0.5)
    )
    record = plan_record(case, "26.124", script)
    assert _states(record, "trefftz:plane") == {"reused"}
    assert record["probes"][0]["entry"] == 1


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf_a_rectangle_that_is_no_trefftz_plane_is_not_reused(tmp_path):
    """P0400-RFIXF-LAYOUT (FR-455 R2): a rectangle in front of the body is not the plane."""
    rectangle = {
        "origin": [-3.0, -1.0, -0.5],
        "along_u": [-3.0, 1.0, -0.5],
        "along_v": [-3.0, -1.0, 0.5],
        "points_u": 5,
        "points_v": 3,
    }
    case = _case(
        tmp_path,
        {"families": "all", "trefftz": {"variant": "plane", "spacing_bref": 0.25}},
        probes=[{"frame": "REFERENCE", "parameters": ["VX"], "rectangles": [rectangle]}],
    )
    script = _script(case)
    (shape,) = script.farfield_layout[-1]["shapes"]
    assert shape["source"] == "added"
    assert len(script.probe_points) == 15 + 7 * 5


# ------------------------------------------------- the record (FR-455 R4)


@pytest.mark.requirement("FR-455")
def test_p0400_rfixf_a_job_hands_each_point_its_own_layout():
    """P0400-RFIXF-LAYOUT (FR-455 R4): a steady job keys the layouts by point; absent unset."""
    common = dict(
        sim_id="1",
        status=RunStatus.CONVERGED,
        script_sha256="",
        raw_flag=False,
        fs_version_requested="26.124",
        package_version="0.40.0",
    )
    plain = RunRecord(run_id="c/sim_1/AL+000", **common)
    assert "farfield_layout" not in plain.model_dump(mode="json")
    layouts = {"AL+000": {"shapes": [{"kind": "plane"}]}, "AL+040": {"shapes": [{"kind": "x"}]}}
    job = RunRecord(
        run_id="c/sim_1/sweep",
        farfield_layout={"by_point": layouts},
        points_ran=[{"tag": tag, "point": {}, "status": "CONVERGED"} for tag in layouts],
        **common,
    )
    again = RunRecord.model_validate(json.loads(json.dumps(job.model_dump(mode="json"))))
    points = {p.point_name: p.farfield_layout for p in again.as_points()}
    assert points == layouts


def test_p0400_rfixf_layout_points_rebuild_bit_for_bit():
    """P0400-RFIXF-LAYOUT: a recorded lattice and plane lay again to the same bits after JSON."""
    from pyflightstream.post.farfield_fields import recorded_layout

    lattice = ffpost._SHAPE.build(1.0)
    shapes = [
        json.loads(json.dumps(_PLANE_RECORD["shapes"][0])),
        json.loads(
            json.dumps(
                {
                    "kind": "lattice",
                    "count": lattice.point_count,
                    "lattice": lattice.model_dump(mode="json"),
                    "axis": "X",
                    "origin_m": [0.25, 0.0, 0.1],
                }
            )
        ),
    ]
    layout = recorded_layout(shapes)
    assert np.array_equal(layout.plane_m, _LAID.points)
    assert np.array_equal(layout.lattice_m, lattice_points(lattice, axis="X") + [0.25, 0.0, 0.1])
