"""Each rotor's diameter reaches the super content, and a quasi-steady point its clock (S11).

THE REPORT (2026-10-05): the diameter did not reach the super file of an unsteady
point; the owner's decision was to correct it in 0.37.0. FR-89 asks the super file
for every variable that defines the flight condition, and a rotor's speed states
nothing without the diameter every rotor coefficient and the advance ratio divide
by. Measured before the change: the unsteady polar of a rotor point carried
`RPM_<alias>` and no diameter, and a quasi-steady point's super file carried
neither, its `J_CLOCK` and `RPM_CLOCK` reading `NA` while its rotor table had the
speed (its record's plan states none; the speed is in its quasi-steady record).

THE FIXTURES are the suite's real-shaped campaigns: the unsteady rotor campaign of
the clock-columns test, its record given the per-rotor plan block a real
`unsteady_rotor` record carries (`reductions.rotors.<alias>.rpm` beside the flat
`rpm`), and the quasi-steady campaign of the L1 defects (polar 6001 re-recorded as
a `qsteady_rotor` sector at 1200 rev/min, rotor `PROP` of diameter 2.0 m, the
record's `reductions` null as the run writes it).
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

from pyflightstream.post.products import write_campaign_products
from pyflightstream.post.superfile import superfile_row, union_the_workspace_knows
from tests.tier1_offline.test_b01_frozen_solve import _post_workspace
from tests.tier1_offline.test_goal035_l1_defects import _posted_qsteady

REPO = Path(__file__).resolve().parents[2]

#: The unsteady rotor campaign's two products: its unsteady polar and its rotor table.
UNSTEADY_POLAR = "polars/P7001_AL-020_uns_avg.csv"
ROTOR_TABLE = "polars/P7001-PUSHER_rotor.csv"


def _rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        return header, [dict(zip(header, row, strict=True)) for row in reader]


def _posted_unsteady_rotor(tmp_path: Path) -> Path:
    """Post the unsteady rotor campaign with its record's per-rotor plan block; return post/."""
    workspace = _post_workspace(tmp_path, 2411, (60, 61), rotor=True)
    runs = workspace.root / "runs.json"
    recorded = json.loads(runs.read_text(encoding="utf-8"))
    plan = recorded[0]["reductions"]
    # A real unsteady_rotor record states the speed twice: flat, and in the
    # rotor's own block (measured on a 0.37 record of the research workspace).
    plan["rotors"] = {
        "PUSHER": {"rpm": plan["rpm"], "steps_per_revolution": plan["steps_per_revolution"]}
    }
    runs.write_text(json.dumps(recorded, indent=1), encoding="utf-8")
    write_campaign_products(workspace, matrix_stem="products")
    return workspace.root / "post" / "products"


def test_p0370_s11_the_unsteady_polar_states_the_rotor_table_diameter(tmp_path):
    """P0370-S11-SUPER-DIAMETER (FR-89): `DIAMETER_PUSHER` right after `RPM_PUSHER`.

    Its value is the rotor table's own `DIAMETER_PUSHER`, the rotor block's
    `diameter_m` the table divides by.
    """
    products = _posted_unsteady_rotor(tmp_path)
    header, (row,) = _rows(products / UNSTEADY_POLAR)
    _table_header, table = _rows(products / ROTOR_TABLE)
    assert "DIAMETER_PUSHER" in header, header
    assert header.index("DIAMETER_PUSHER") == header.index("RPM_PUSHER") + 1, header
    assert {line["DIAMETER_PUSHER"] for line in table} == {"2.00000"}, table
    assert float(row["DIAMETER_PUSHER"]) == pytest.approx(2.0)
    assert float(row["RPM_PUSHER"]) == pytest.approx(2200.0)


def test_p0370_s11_a_quasi_steady_super_file_states_its_speed_diameter_and_clock(tmp_path):
    """P0370-S11-SUPER-DIAMETER (FR-89): speed, diameter and clock with the reductions null.

    The speed is the quasi-steady record's, 1200 rev/min, the rotor table's; the
    diameter the reference block's, 2.0 m; `J_CLOCK = V / (n D) = 68.058 / (20 *
    2.0) = 1.70145` at the products' five decimals. The rotor table states the
    same clock.
    """
    products, folder = _posted_qsteady(tmp_path, "sector")
    runs = json.loads((folder.parents[1] / "runs.json").read_text(encoding="utf-8"))
    sector = [record for record in runs if str(record["sim_id"]) == "6001"]
    assert sector and all(record["reductions"] is None for record in sector), sector
    supers = sorted((folder / "polars").glob("SUPER-6001-*_g01.csv"))
    assert len(supers) == 1, sorted(products["products"])
    header, rows = _rows(supers[0])
    assert header.index("DIAMETER_PROP") == header.index("RPM_PROP") + 1, header
    assert len(rows) == 2
    for row in rows:
        assert float(row["RPM_PROP"]) == pytest.approx(1200.0)
        assert float(row["DIAMETER_PROP"]) == pytest.approx(2.0)
        assert row["RPM_CLOCK"] == "1200.00000", row
        assert row["J_CLOCK"] == "1.70145", row
    (table,) = sorted((folder / "polars").glob("P6001-PROP_rotor.csv"))
    _header, lines = _rows(table)
    assert {(line["RPM_CLOCK"], line["J_CLOCK"]) for line in lines} == {("1200.00000", "1.70145")}


def test_p0370_s11_a_row_without_a_rotor_has_no_diameter_column(tmp_path):
    """P0370-S11-SUPER-DIAMETER (FR-89): a row that turns no rotor gains no column.

    The steady record of the quasi-steady campaign's workspace, rotorless as the
    run wrote it, assembled against a reference that DOES declare a rotor: no
    `DIAMETER_` or `RPM_<alias>` key. In a campaign whose super file has the
    column through another row, that row's cell is `NA`: polar 6002 turns no
    rotor `PROP`, and its super file reads `NA` under the sector's column.
    """
    _products, folder = _posted_qsteady(tmp_path, "sector")
    from pyflightstream.workspace import RunRecord

    runs = json.loads((folder.parents[1] / "runs.json").read_text(encoding="utf-8"))
    steady = RunRecord(**{**runs[0], "recipe": "steady"})

    class Block:
        diameter_m = 2.0

    row = superfile_row(
        polar_columns=("ALPHA",),
        polar_values=(0.0,),
        matrix_row=None,
        record=steady,
        sweep_row=None,
        plots_row=None,
        rotors={"PROP": Block()},
        own_speeds=None,
    )
    assert not [key for key in row if key.startswith(("DIAMETER_", "RPM_"))], row
    supers = sorted((folder / "polars").glob("SUPER-6002-*_g01.csv"))
    assert len(supers) == 1
    header, rows = _rows(supers[0])
    assert "DIAMETER_PROP" in header
    assert {line["DIAMETER_PROP"] for line in rows} == {"NA"}, rows


def test_p0370_s11_the_union_names_the_diameter_of_a_planned_rotor(tmp_path):
    """P0370-S11-SUPER-DIAMETER (FR-89): the union knows the column from the record alone.

    The rotor table's header and the unsteady polar's (whose name the polar
    glob also matches) name it too, so every polar table is removed first: what
    is left is the record's plan, which names rotor PUSHER.
    """
    products = _posted_unsteady_rotor(tmp_path)
    for table in (products / "polars").glob("*.csv"):
        table.unlink()
    root = products.parents[1]
    known = union_the_workspace_knows(
        root, products, "products", polars_dir="polars", probes_dir="probes"
    )
    assert {"RPM_PUSHER", "DIAMETER_PUSHER"} <= known, sorted(known)


def _parity():
    spec = importlib.util.spec_from_file_location(
        "check_parity_s11", REPO / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_OLD = "POL,J_CLOCK,RPM_CLOCK,RPM_PROP,RPM\n6001,NA,NA,1200.0,1200.0\n6002,NA,NA,NA,NA\n"
_NEW = (
    "POL,J_CLOCK,RPM_CLOCK,RPM_PROP,DIAMETER_PROP,RPM\n"
    "6001,1.70145,1200.00000,1200.0,2.0,1200.0\n6002,NA,NA,NA,NA,NA\n"
)


def test_p0370_s11_the_parity_names_the_change_and_only_it():
    """P0370-S11-SUPER-DIAMETER (FR-89): the inserted columns and the filled clock, and no more.

    Controls: another changed cell, an inserted column of another name, a clock
    cell changed from a number, a removed column, a moved column, an inserted
    column on a product that is not super content, and a line added each stay
    unnamed; the legacy_polar form is named.
    """
    parity = _parity()
    defined = {"FR-89"}
    for name in ("m/polars/SUPER-6001_g01.csv", "m/polars/P7001_AL-020_uns_avg.csv"):
        assert parity.name_difference("post", name, _OLD, _NEW, defined).get("requirement") == (
            "FR-89"
        ), name
    filled_only = _OLD.replace("6001,NA,NA", "6001,1.70145,1200.00000")
    assert (
        parity.name_difference("post", "m/polars/P6001-PROP_rotor.csv", _OLD, filled_only, defined)
    ).get("requirement") == "FR-89"
    unnamed = {
        "another cell": _NEW.replace(",2.0,1200.0\n", ",2.0,1201.0\n"),
        "another column": _NEW.replace("DIAMETER_PROP", "CT_PROP"),
        "a clock not NA before": _NEW,
        "a column removed": (
            "POL,J_CLOCK,RPM_CLOCK,RPM_PROP,DIAMETER_PROP\n"
            "6001,1.70145,1200.00000,1200.0,2.0\n6002,NA,NA,NA,NA\n"
        ),
        "a column moved": (
            "POL,RPM_CLOCK,J_CLOCK,RPM_PROP,DIAMETER_PROP,RPM\n"
            "6001,1200.00000,1.70145,1200.0,2.0,1200.0\n6002,NA,NA,NA,NA,NA\n"
        ),
        "a line added": _NEW + "6003,NA,NA,NA,NA,NA\n",
    }
    for label, new in unnamed.items():
        old = _NEW.replace("1.70145", "1.70000") if label == "a clock not NA before" else _OLD
        named = parity.name_difference("post", "m/polars/SUPER-6001_g01.csv", old, new, defined)
        assert "requirement" not in named, (label, named)
    other = parity.name_difference("post", "m/polars/P6001-PROP_rotor.csv", _OLD, _NEW, defined)
    assert "requirement" not in other, other
    legacy = ["".join(cell.rjust(16) for cell in line.split(",")) for line in _OLD.splitlines()]
    legacy_new = ["".join(cell.rjust(16) for cell in line.split(",")) for line in _NEW.splitlines()]
    named = parity.name_difference(
        "post",
        "m/polars/SUPER-6001_g01.csv",
        "\n".join(legacy) + "\n",
        "\n".join(legacy_new) + "\n",
        defined,
    )
    assert named.get("requirement") == "FR-89", named
