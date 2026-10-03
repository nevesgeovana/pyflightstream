"""Tier 1: the qsteady products of 0.32.0, package G (G5 disc maps, G7 chord in the plan).

* G5 (FR-270, FR-271, FR-272): the sectional load by radius and azimuth over the
  disc, one CSV per rotor and quantity, from a wheel's sections at every
  clocking and from an unsteady point's last complete revolution. Every
  expected value is worked from the definition the fixtures' loads are written
  with (``test_goal036_harmonics``), never read off the implementation.
* G7 (FR-273, FR-274): the plan reads the chord of the ``.fsm`` and warns before
  the run when a point's reduced frequency passes the limit; the same
  geometry as an OBJ and as a saved simulation gives the same stations.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream._errors import ProductError, PyflightstreamWarning
from pyflightstream._fsm import boundary_vertices, saved_mesh_coordinate_unit
from pyflightstream.cases import MeshImport
from pyflightstream.cases import qsteady as arithmetic
from pyflightstream.cases.workflows import qsteady_validity
from pyflightstream.post import disc_maps
from pyflightstream.post.harmonics import HarmonicRotor
from pyflightstream.post.products import read_csv_table
from pyflightstream.run.matrix import _warn_when_a_quasi_steady_point_leaves_its_assumption
from tests.tier1_offline.test_goal035_qsteady_rotor import OMEGA, _blade_obj, _case
from tests.tier1_offline.test_goal036_harmonics import (
    DIAMETER,
    KNOWN,
    RADII,
    _load,
    _post,
    _unsteady,
    _unsteady_azimuth,
    _wheel,
    _wheel_azimuth,
)

_QUANTITIES = tuple(KNOWN)


def _disc(out: Path, point: str, quantity: str) -> tuple[list[str], list[dict[str, str]]]:
    return read_csv_table(out / "sections" / disc_maps.disc_map_name(point, "PROP", quantity))


# ------------------------------------------------------------------ G5 --


@pytest.mark.requirement("FR-270")
@pytest.mark.parametrize("rpm", [1200.0, -1200.0])
def test_a_wheel_s_disc_map_gives_back_the_load_at_every_radius_and_azimuth(
    tmp_path, monkeypatch, rpm
):
    """N = 6, k = 2, three stations: 6 x 2 x 3 = 36 rows per quantity, three files.

    Each row's VALUE is the fixture's load at the row's own radius and azimuth,
    and its azimuth is blade n's at clocking i worked by hand (either hand).
    """
    # P0320-G5-DISC-MAP
    workspace = _wheel(tmp_path, monkeypatch, blades=6, clockings=2, rpm=rpm)
    out, manifest, _ = _post(workspace)
    sign = 1 if rpm > 0 else -1
    for quantity in _QUANTITIES:
        columns, rows = _disc(out, "DP", quantity)
        assert tuple(columns) == disc_maps.DISC_MAP_COLUMNS
        assert columns[0] == "POL" and columns[1] == "ALPHA"
        assert len(rows) == 6 * 2 * len(RADII)
        assert {row["POL"] for row in rows} == {"7001"}
        assert {row["QUANTITY"] for row in rows} == {quantity}
        for row in rows:
            blade, clocking = int(row["BLADE"]), int(row["SAMPLE"])
            psi = _wheel_azimuth(blade, 6, clocking, 2, sign)
            radius = float(row["STATION_R_M"])
            assert float(row["AZIMUTH_DEG"]) == pytest.approx(psi, abs=1e-4)
            assert float(row["R_OVER_R"]) == pytest.approx(radius / (0.5 * DIAMETER), abs=1e-5)
            assert float(row["VALUE"]) == pytest.approx(_load(quantity, radius, psi), abs=1e-4)
        places = [(float(r["AZIMUTH_DEG"]), float(r["STATION_R_M"])) for r in rows]
        assert places == sorted(places), "the disc reads by azimuth, then radius"
        entry = manifest["products"][f"sections/DP_disc_PROP_{quantity}.csv"]
        assert entry["kind"] == "disc_map"
        assert entry["source"] == "wheel clockings"
        assert entry["samples"] == 12
        assert entry["rotor"] == "PROP" and entry["quantity"] == quantity
        assert entry["runs"] == ["camp/sim_7001/DP"]


@pytest.mark.requirement("FR-271")
def test_an_unsteady_rotor_s_disc_map_holds_its_last_revolution_only(tmp_path, monkeypatch):
    """Three blades over steps 7 to 12: 18 blade samples x 3 stations = 54 rows per quantity.

    Every step outside the last complete revolution carries 999 in every load,
    so a map that read one would show it.
    """
    # P0320-G5-DISC-MAP
    workspace = _unsteady(tmp_path, monkeypatch, blades=3, rpm=1200.0)
    out, manifest, _ = _post(workspace)
    for quantity in _QUANTITIES:
        _, rows = _disc(out, "AL-020", quantity)
        assert len(rows) == 18 * len(RADII)
        assert {int(row["SAMPLE"]) for row in rows} == set(range(7, 13))
        for row in rows:
            psi = _unsteady_azimuth(int(row["BLADE"]), 3, int(row["SAMPLE"]), 1)
            radius = float(row["STATION_R_M"])
            assert float(row["AZIMUTH_DEG"]) == pytest.approx(psi, abs=1e-4)
            assert float(row["VALUE"]) == pytest.approx(_load(quantity, radius, psi), abs=1e-4)
            assert row["R_OVER_R"] == "NA"
        entry = manifest["products"][f"sections/AL-020_disc_PROP_{quantity}.csv"]
        assert entry["kind"] == "disc_map"
        assert entry["source"] == "unsteady last revolution"
        assert entry["samples"] == 18
        assert entry["revolution"] == {"PROP": [7, 12]}


def test_the_disc_map_writer_maps_a_written_table_by_its_rotor(tmp_path, monkeypatch):
    """The standalone writer reads a written sections table and names its files by point."""
    # P0320-G5-DISC-MAP
    workspace = _wheel(tmp_path, monkeypatch, blades=3, clockings=2, rpm=1200.0)
    out, _, _ = _post(workspace)
    rotor = HarmonicRotor(
        alias="PROP",
        blades=tuple((f"Blade{n}",) for n in (1, 2, 3)),
        diameter_m=DIAMETER,
        azimuth_is_blade_one=False,
    )
    target = tmp_path / "maps"
    written = disc_maps.write_disc_map(
        out / "sections" / "DP_sections.csv",
        {"PROP": rotor},
        sample_column="CLOCKING",
        out_dir=target,
    )
    assert [path.name for path in written] == [
        f"DP_disc_PROP_{name}.csv" for name in sorted(_QUANTITIES)
    ]
    _, rows = read_csv_table(target / "DP_disc_PROP_Fz.csv")
    assert len(rows) == 3 * 2 * len(RADII)


@pytest.mark.requirement("FR-272")
def test_a_table_with_no_blade_of_the_rotor_refuses_to_map_and_names_why(tmp_path, monkeypatch):
    """A rotor whose blades are named nowhere in the table has nothing to map: refused, by name."""
    # P0320-G5-DISC-MAP
    workspace = _wheel(tmp_path, monkeypatch, blades=3, clockings=2, rpm=1200.0)
    out, _, _ = _post(workspace)
    stranger = HarmonicRotor(
        alias="PROP",
        blades=(("Wing1",), ("Wing2",)),
        diameter_m=None,
        azimuth_is_blade_one=False,
    )
    with pytest.raises(ProductError, match="no disc map to write"):
        disc_maps.write_disc_map(
            out / "sections" / "DP_sections.csv",
            {"PROP": stranger},
            sample_column="CLOCKING",
            out_dir=tmp_path / "none",
        )
    assert not (tmp_path / "none").exists()


# ------------------------------------------------------------------ G7 --


def _fsm_of_blades(path: Path, *, blades: int = 3, owners: bool = True) -> Path:
    """A saved simulation of ``blades`` flat rectangular blades, the OBJ fixture's geometry.

    Chord 0.2 m along x, radius 0.2 to 1.0 m in nine rows of two vertices, in
    metres (the ``1`` / ``5`` head of a saved metre unit); the block's
    boundary row (the seventh row before the T/F rows) tells each face to its
    blade, as the solver's own saves do (measured on the tier-3 library).
    """
    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    owner: list[int] = []
    for blade in range(blades):
        angle = 2.0 * math.pi * blade / blades
        first = len(vertices)
        for step in range(9):
            radius = 0.2 + 0.1 * step
            for x in (-0.1, 0.1):
                vertices.append((x, radius * math.cos(angle), radius * math.sin(angle)))
        for step in range(8):
            a = first + 2 * step
            triangles.append((a, a + 1, a + 3))
            triangles.append((a, a + 3, a + 2))
        owner += [blade + 1] * 16
    faces = len(triangles)

    def row(values) -> str:
        return ",".join(str(value) for value in values) + ","

    lines = ["26,1", "8172026", "$GLOBAL_START$", "1", "5", "$GLOBAL_END$", "$MESH_START$"]
    lines += ["header one", "header two", str(blades)]
    for blade in range(blades):
        lines += [f"{blade + 1}, T, F, F", f"Blade{blade + 1}", ".494,.573,.576"]
    lines += [str(faces), row(range(1, faces + 1)), row([3] * faces)]
    lines += [row(t[slot] + 1 for t in triangles) for slot in range(3)]
    for index in range(15):
        lines.append(row(owner if owners and index == 6 else [0] * faces))
    lines += [" " + ",".join([" F"] * faces) + ","] * 5
    lines += ["0", str(len(vertices))]
    lines += [row(f"{v[axis]:.9f}" for v in vertices) for axis in range(3)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _with_fsm(case, fsm: Path):
    return case.model_copy(
        update={"geometry": str(fsm), "inventory": ("Blade1", "Blade2", "Blade3")}
    )


def test_the_saved_simulation_tells_each_face_to_its_boundary(tmp_path):
    """Three blades of 18 vertices each: each boundary holds exactly its own, in metres."""
    # P0320-G7-CHORD-PLAN
    fsm = _fsm_of_blades(tmp_path / "prop.fsm")
    assert saved_mesh_coordinate_unit(fsm) == "METER"
    by_name = boundary_vertices(fsm)
    assert by_name is not None and sorted(by_name) == ["Blade1", "Blade2", "Blade3"]
    assert {len(vertices) for vertices in by_name.values()} == {18}
    # Blade 2 lies 120 deg from blade 1 about the x axis: y = r cos 120, z = r sin 120.
    radii = sorted({round(math.hypot(y, z), 6) for _, y, z in by_name["Blade2"]})
    assert radii == pytest.approx([0.2 + 0.1 * step for step in range(9)], abs=1e-6)
    assert all(abs(y) > 0 or abs(z) > 0 for _, y, z in by_name["Blade2"])
    assert min(y for _, y, _ in by_name["Blade2"]) < -0.05
    assert boundary_vertices(_fsm_of_blades(tmp_path / "no_row.fsm", owners=False)) is None


@pytest.mark.requirement("FR-273")
def test_the_plan_reads_the_chord_of_the_fsm_as_it_reads_the_obj(tmp_path):
    """The same wheel as an OBJ and as a saved simulation: the same chord at every station.

    Chord 0.2 m by construction, so k = 0.2 Omega / (2 V_rel) with V_rel the
    free stream 30 m/s and the station's own speed, worked by hand.
    """
    # P0320-G7-CHORD-PLAN
    obj = _blade_obj(tmp_path / "prop.obj")
    base = _case()
    with_obj = base.model_copy(
        update={
            "geometry": str(obj),
            "mesh_import": MeshImport(units="METER"),
            "inventory": ("Blade1", "Blade2", "Blade3"),
        }
    )
    from_fsm = _with_fsm(base, _fsm_of_blades(tmp_path / "prop.fsm"))
    seen_obj, seen_fsm = qsteady_validity(with_obj), qsteady_validity(from_fsm)
    assert seen_obj is not None and seen_fsm is not None
    assert seen_fsm["chord_source"] == "mesh" and seen_fsm["note"] is None
    assert seen_fsm["chord_m"] == pytest.approx(seen_obj["chord_m"], rel=1e-9)
    assert seen_fsm["chord_m"] == pytest.approx([0.2] * len(seen_fsm["chord_m"]), rel=1e-3)
    by_hand = [OMEGA * 0.2 / (2.0 * math.hypot(30.0, OMEGA * r)) for r in seen_fsm["radius_m"]]
    assert seen_fsm["k"] == pytest.approx(by_hand, rel=1e-3)
    assert seen_fsm["k_max"] > arithmetic.REDUCED_FREQUENCY_LIMIT > seen_fsm["k_min"]


@pytest.mark.requirement("FR-274")
def test_the_plan_warns_before_the_run_when_the_fsm_chord_passes_the_limit(tmp_path):
    """k passes 0.1 over the inner span of this wheel: warned, never refused."""
    # P0320-G7-CHORD-PLAN
    case = _with_fsm(_case(), _fsm_of_blades(tmp_path / "prop.fsm"))
    validity = qsteady_validity(case)
    assert validity is not None
    plan = SimpleNamespace(
        points=[
            SimpleNamespace(
                sim_id="9001", run_id="c/sim_9001/P", point={}, qsteady_validity=validity
            )
        ]
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _warn_when_a_quasi_steady_point_leaves_its_assumption(
            SimpleNamespace(campaign=SimpleNamespace(sims=[])), plan
        )
    said = [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]
    above = validity["span_pct_k_gt_0_1"]
    assert 0.0 < above < 100.0
    assert any(f"k > 0.1 over {above:.1f} % of the span" in text for text in said), said


def test_a_saved_simulation_that_cannot_tell_its_faces_says_why_and_never_refuses(tmp_path):
    """No boundary row: the plan states the reason in its note and gives k per metre of chord."""
    # P0320-G7-CHORD-PLAN
    fsm = _fsm_of_blades(tmp_path / "prop.fsm", owners=False)
    validity = qsteady_validity(_with_fsm(_case(), fsm))
    assert validity is not None
    assert "does not tell its faces to their boundaries" in str(validity["note"])
    assert validity["k_per_chord_m_tip"] is not None


# ------------------------------------------------- review of package G --


def _table(offsets: list[str], azimuth: str) -> tuple[list[str], list[dict[str, str]]]:
    columns = ["POL", "ALPHA", "ROTOR", "FAMILY", "AZIMUTH", "Offset", "Fz"]
    rows = [
        {
            "POL": "1",
            "ALPHA": "0",
            "ROTOR": "PROP",
            "FAMILY": "Blade1",
            "AZIMUTH": azimuth,
            "Offset": offset,
            "Fz": str(10 + index),
            "CLOCKING": "0",
        }
        for index, offset in enumerate(offsets)
    ]
    return columns, rows


def test_a_station_left_of_the_axis_maps_at_its_radius_and_an_azimuth_is_a_turn():
    """Offset -0.4 is radius 0.4; 370 deg is 10 deg; a missing offset sorts last."""
    # P0320-G5-DISC-MAP
    rotor = HarmonicRotor(
        alias="PROP", blades=(("Blade1",),), diameter_m=2.0, azimuth_is_blade_one=False
    )
    columns, rows = _table(["-0.4", "NA", "0.2"], "370")
    mapped = disc_maps.disc_map_rows(columns, rows, {"PROP": rotor}, sample_column="CLOCKING")
    entries = mapped.maps[("PROP", "Fz")]
    assert [entry[5] for entry in entries[:2]] == [0.2, 0.4]
    assert math.isnan(entries[2][5])
    assert {entry[4] for entry in entries} == {10.0}
    assert entries[1][6] == pytest.approx(0.4)


def test_a_rotor_short_of_a_revolution_is_named_in_the_skips_of_the_disc_maps(
    tmp_path, monkeypatch
):
    """No complete revolution, so no rows: a named skip and a post.log line, never a file."""
    # P0320-G5-DISC-MAP
    workspace = _unsteady(tmp_path, monkeypatch, blades=3, rpm=1200.0)
    record = workspace.read_manifest()[0]
    record.reductions["rotors"]["PROP"]["steps_per_revolution"] = 20.0  # type: ignore[index]
    out, manifest, log = _post(workspace)
    assert not list((out / "sections").glob("*_disc_*"))
    reason = manifest["skipped"]["sections/AL-020_disc_#rotor=PROP"]
    assert "no disc map" in reason
    assert any("AL-020_disc_" in line and "no disc map" in line for line in log)
