"""The polar files by family and by group, steady and unsteady (PFS-2231, lane L2).

THE REQUIREMENT (design of the post outputs, sections 2.1, 4.1 to 4.4 and 4.7;
FR-3771 to FR-3783). Every polar writes, under ``polars/``, ``FAM-DIM``, ``FAM-ACOEF``
and, when the reference declares a rotor, ``FAM-RCOEF-P<POL>.csv``: one row per point
and family keyed by ``FAMILY`` and ``FAMILY_ID``; and for every group (TOTAL,
AIRFRAME, each rotor, each declared group) ``P<POL>-<GROUP>-<KIND>.csv``, one row per
point, its values formed from the SUM of its members' dimensional loads. No Mach
token, no ``uns_avg``, no SUPER file, no rotor table. An unsteady row is the window
average of the plots, the coefficients formed from the averaged loads.

The expected numbers are computed here from the INPUTS (the loads export, the plots
the fixture writes, the record's density and the reference), never read back from
a product.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import pytest

from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.results import parse_loads
from pyflightstream.workspace import RunRecord
from tests.tier1_offline.test_post_products import PLOTS_HEADER
from tests.tier1_offline.test_post_superfile import _MATRIX, _loads, _workspace

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-L2-POLAR-FILES")])

SREF, CREF, BREF = 50.0, 2.526, 20.0
DIAMETER = 2.0
RPM = 2200.0

#: The six components of each family over four steps, in N and N m, export frame.
#: The row's window is steps 3 and 4 (LAST_REVS_AVG 0.5 of a four-step turn).
W_STEPS = [(10.0, 0.0, 100.0, 0.0, -50.0, 0.0)] * 4
B_STEPS = [(100.0 * k, 2.0 * k, 5.0 * k, 3.0 * k, 0.0, 1.0 * k) for k in (1, 2, 3, 5)]


def _reference(*rotors: tuple[str, int | None, str]) -> str:
    text = f"area_m2 = {SREF}\nchord_m = {CREF}\nspan_m = {BREF}\n"
    for alias, rotor_id, family in rotors:
        text += (
            f'\n[rotors.{alias}]\nalias = "{alias}"\nx_m = 0.5\ny_m = 0.0\nz_m = 0.0\n'
            f'axis = "X"\nrpm_sign = 1\ndiameter_m = {DIAMETER}\n'
            f'families_blades = ["{family}"]\n'
            'blade1 = { azimuth_deg = 0.0, zero = "Y" }\n'
        )
        if rotor_id is not None:
            text += f"id = {rotor_id}\n"
    return text


def _mean(steps, window=(3, 4)):
    chosen = steps[window[0] - 1 : window[1]]
    return [sum(values[i] for values in chosen) / len(chosen) for i in range(6)]


def _posted(tmp_path, *, rotors=(("PUSHER", None, "B"),), families=True, groups=""):
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(
        _reference(*rotors), encoding="utf-8"
    )
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text(
        f"[groups]\n{groups}", encoding="utf-8"
    )
    row = next(line for line in _MATRIX.splitlines() if line.startswith("6002"))
    (workspace.root / "matriz.fs").write_text(
        _MATRIX.replace(row, row.rstrip() + " / LAST_REVS_AVG: 0.5"), encoding="utf-8"
    )
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    parts = ("FX", "FY", "FZ", "MX", "MY", "MZ")
    for record in records:
        if record.sim_id == "6002":
            names = [f"{part}_MRP_TOTAL" for part in parts]
            if families:
                names = [f"{part}_MRP_{fam}" for fam in ("W", "B") for part in parts] + names
            table = "Time-step," + ",".join(names) + "\n" + "-" * 70 + "\n"
            for step in range(4):
                w, b = W_STEPS[step], B_STEPS[step]
                total = [w[i] + b[i] for i in range(6)]
                cells = (list(w) + list(b) if families else []) + total
                table += f"{step + 1}.0000," + ",".join(f"{v:.4f}" for v in cells) + ",\n"
            export = (
                PLOTS_HEADER
                + table
                + "-" * 70
                + "\n     Force Units: Coefficients\n"
                + "Software : Flightstream version 26.1, build #7012026\n"
            )
            plots = next(o for o in record.outputs if o.endswith("_plots.txt"))
            (workspace.sim_dir("6002") / plots).write_text(export, encoding="utf-8")
            plan = dict(record.reductions or {})
            plan.update(time_iterations=4, steps_per_revolution=4.0)
            plan["rotors"] = {
                alias: {"blades": 6, "rpm": RPM, "steps_per_revolution": 4.0, "period_steps": 1}
                for alias, _id, _family in rotors
            }
            record = record.model_copy(update={"reductions": plan})
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    polars = workspace.root / "post" / "matriz" / "polars"
    density = float(next(r for r in records if r.sim_id == "6002").density_kg_m3)
    return polars, [str(w.message) for w in caught], density


def _rows(path: Path) -> list[dict[str, str]]:
    return read_csv_table(path)[1]


def test_a_steady_polar_writes_the_family_and_group_files_and_nothing_of_0570(tmp_path):
    polars, _said, _rho = _posted(tmp_path)
    names = sorted(path.name for path in polars.iterdir())
    for kind in ("DIM", "ACOEF"):
        assert f"FAM-{kind}-P6001.csv" in names, names
        for group in ("TOTAL", "AIRFRAME", "g01", "g02"):
            assert f"P6001-{group}-{kind}.csv" in names, (group, names)
    # 6001's reference declares no rotor: no RCOEF file of that polar.
    assert not [name for name in names if name.startswith("FAM-RCOEF-P6001")], names
    for retired in ("SUPER", "uns_avg", "_rotor", "M20", "M14", "sweep"):
        assert not [name for name in names if retired in name], (retired, names)


def test_a_steady_family_row_is_its_export_coefficient_times_its_dynamic_pressure(tmp_path):
    polars, _said, _rho = _posted(tmp_path)
    loads = parse_loads(_loads(-2.0))
    # The 6001 records state density 1.225; the export states its reference velocity.
    pressure = 0.5 * 1.225 * float(loads.reference_velocity_m_s) ** 2
    rows = [row for row in _rows(polars / "FAM-DIM-P6001.csv") if row["POINT_ID"] == "1"]
    assert [row["FAMILY"] for row in rows] == list(loads.surfaces)
    for row in rows:
        surface = loads.surfaces[row["FAMILY"]]
        assert float(row["FX_MRP"]) == pytest.approx(surface["Cx"] * pressure * SREF, rel=1e-5)
        assert float(row["FZ_MRP"]) == pytest.approx(surface["Cz"] * pressure * SREF, rel=1e-5)
        assert float(row["MY_MRP"]) == pytest.approx(
            surface["CMy"] * pressure * SREF * CREF, rel=1e-5
        )


def test_a_group_row_is_the_sum_of_its_members_dimensional_loads(tmp_path):
    polars, _said, _rho = _posted(tmp_path)
    family = _rows(polars / "FAM-DIM-P6001.csv")
    total = _rows(polars / "P6001-TOTAL-DIM.csv")
    assert [row["GROUP_ID"] for row in total] == ["0", "0"]
    for row in total:
        members = [f for f in family if f["POINT_ID"] == row["POINT_ID"]]
        for column in ("FX_MRP", "FZ_MRP", "MY_MRP"):
            assert float(row[column]) == pytest.approx(
                sum(float(f[column]) for f in members), rel=1e-5
            )
    # CD in body axes is positive aft: the export's x force over q SREF.
    loads = parse_loads(_loads(-2.0))
    pressure = 0.5 * 1.225 * float(loads.reference_velocity_m_s) ** 2
    (first,) = [r for r in _rows(polars / "P6001-TOTAL-ACOEF.csv") if r["POINT_ID"] == "1"]
    summed_x = sum(float(f["FX_MRP"]) for f in family if f["POINT_ID"] == "1")
    assert float(first["CDB"]) == pytest.approx(summed_x / (pressure * SREF), rel=1e-4)


def test_family_id_is_the_position_in_the_recorded_boundary_inventory():
    from pyflightstream.post._family_polar import family_ids

    assert family_ids(["Wing", "Blade1"], ["Body", "Wing", "Blade1"]) == {"Wing": 2, "Blade1": 3}
    # No inventory: the export prints one row per boundary in the inventory's order.
    assert family_ids(["W", "B"], None) == {"W": 1, "B": 2}


def test_an_unsteady_family_row_is_the_window_average_of_its_plots(tmp_path):
    polars, _said, _rho = _posted(tmp_path)
    rows = _rows(polars / "FAM-DIM-P6002.csv")
    by_family = {row["FAMILY"]: row for row in rows}
    assert set(by_family) == {"W", "B"}
    mean_b = _mean(B_STEPS)
    for column, value in zip(("FX_MRP", "FY_MRP", "FZ_MRP", "MX_MRP"), mean_b, strict=False):
        assert float(by_family["B"][column]) == pytest.approx(value, rel=1e-6), column
    block = by_family["B"]
    assert (block["RUN_TYPE"], block["FIRST_STEP"], block["LAST_STEP"], block["STEPS"]) == (
        "unsteady_rotor",
        "3",
        "4",
        "2",
    )
    assert float(block["RPM0"]) == RPM and float(block["D0"]) == DIAMETER
    group = _rows(polars / "P6002-TOTAL-DIM.csv")[0]
    mean_w = _mean(W_STEPS)
    assert float(group["FX_MRP"]) == pytest.approx(mean_w[0] + mean_b[0], rel=1e-6)


def test_fam_rcoef_holds_only_the_rotor_families_and_the_rotor_group_has_its_own(tmp_path):
    polars, said, rho = _posted(tmp_path)
    rows = _rows(polars / "FAM-RCOEF-P6002.csv")
    assert [(row["FAMILY"], row["ROTOR_ID"]) for row in rows] == [("B", "0")]
    names = {path.name for path in polars.iterdir()}
    assert "P6002-PUSHER-RCOEF.csv" in names
    assert "P6002-AIRFRAME-RCOEF.csv" not in names and "P6002-TOTAL-RCOEF.csv" not in names
    # Declared along +x of the export (aft): thrust is positive forward, so T is
    # minus the export's x force, and CT = T / (rho n^2 D^4).
    mean_b = _mean(B_STEPS)
    rotor = _rows(polars / "P6002-PUSHER-RCOEF.csv")[0]
    assert float(rotor["T"]) == pytest.approx(-mean_b[0], rel=1e-6)
    assert float(rotor["CT"]) == pytest.approx(
        -mean_b[0] / (rho * (RPM / 60.0) ** 2 * DIAMETER**4), rel=1e-4
    )
    assert float(rotor["CTR0"]) == pytest.approx(float(rotor["CT"]), rel=1e-9)
    assert any("declares its axis aft" in text and "PUSHER" in text for text in said), said


def test_an_undeclared_rotor_id_is_r0_and_two_rotors_give_r1_and_r2(tmp_path):
    polars, _said, _rho = _posted(tmp_path / "one")
    header = read_csv_table(polars / "FAM-ACOEF-P6002.csv")[0]
    assert "CDR0" in header and "CDR1" not in header
    polars, _said, _rho = _posted(tmp_path / "two", rotors=(("PUSHER", 1, "B"), ("LIFTER", 2, "W")))
    header = read_csv_table(polars / "FAM-ACOEF-P6002.csv")[0]
    frames = [name[2:] for name in header if name.startswith("CD") and name[2:] not in ("0", "I")]
    assert frames == ["W", "S", "B", "R1", "R2"], frames
    rows = _rows(polars / "FAM-RCOEF-P6002.csv")
    assert sorted((row["FAMILY"], row["ROTOR_ID"]) for row in rows) == [("B", "1"), ("W", "2")]
    block = read_csv_table(polars / "P6002-LIFTER-RCOEF.csv")[0]
    assert {"RPM1", "RPM2", "D1", "D2", "GROUP", "GROUP_ID"} <= set(block)
    assert _rows(polars / "P6002-LIFTER-RCOEF.csv")[0]["GROUP_ID"] == "12"


def test_a_record_without_the_family_plots_gives_na_family_rows_and_group_rows_from_its_plots(
    tmp_path,
):
    polars, said, _rho = _posted(tmp_path, families=False)
    for row in _rows(polars / "FAM-DIM-P6002.csv"):
        assert row["FX_MRP"] == "NA", row
    total = _rows(polars / "P6002-TOTAL-DIM.csv")[0]
    mean_w, mean_b = _mean(W_STEPS), _mean(B_STEPS)
    assert float(total["FX_MRP"]) == pytest.approx(mean_w[0] + mean_b[0], rel=1e-6)
    (warning,) = [text for text in said if "MRP_B" in text and "MRP_W" in text]
    assert "NA" in warning, warning


def test_no_coefficient_over_a_dynamic_pressure_at_a_static_point():
    """The NA rules of section 4.3 reach the file: VINF = 0 gives no ETA and no TC."""
    from pyflightstream.post._family_polar import (
        Family,
        PolarPointLoads,
        PolarRotor,
        polar_files,
        polar_groups,
    )
    from pyflightstream.post._tables import ReferenceValues
    from pyflightstream.post.axes import rotor_frame

    rotor = PolarRotor("PUSHER", 0, rotor_frame((-1.0, 0.0, 0.0)), 1.0, (0.0, 0.0, 0.0), ("B",))
    families = [Family("B", 1, 0)]
    loads = {"B": ((-10.0, 0.0, 0.0), (-1.0, 0.0, 0.0))}
    point = PolarPointLoads(
        run_block={"POL": "1"},
        alpha_deg=0.0,
        beta_deg=0.0,
        density_kg_m3=1.0,
        vref_m_s=10.0,
        vinf_m_s=0.0,
        family_loads=loads,
        rpm={0: 600.0},
    )
    files = polar_files(
        pol="1",
        points=[point],
        families=families,
        groups=polar_groups(families, [rotor], {}),
        rotors=[rotor],
        reference=ReferenceValues(1.0, 1.0, 1.0),
        load_frame="MRP",
    )
    (rcoef,) = [f for f in files if f.name == "FAM-RCOEF-P1.csv"]
    row = dict(zip(rcoef.columns, rcoef.rows[0], strict=True))
    assert row["ETA"] == "NA" and row["TC"] == "NA" and row["MCA"] == "NA"
    assert row["T"] == pytest.approx(10.0) and not math.isnan(float(row["CT"]))
