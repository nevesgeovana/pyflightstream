"""The merged polar: the unsteady polar, its rotor tables and ROTATE angles on one row."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pyflightstream.cases.pproc import ProductsSpec
from pyflightstream.post._merged_polar import (
    RotorRows,
    merged_polar_products,
    merged_polar_rows,
)

pytestmark = [pytest.mark.requirement("FR-3511"), pytest.mark.requirement("FR-3512")]

COLUMNS = ("POL", "ALPHA", "J", "run_id")


def _polar_row(alpha: str, run: str, j: str = "0.5") -> dict[str, str]:
    return {"POL": "7", "ALPHA": alpha, "J": j, "run_id": run}


def _rotor(alias: str, rows: list[tuple[str, str]]) -> RotorRows:
    columns = ("POL", "ROTOR", "ALPHA", f"J_{alias}", f"CT_{alias}")
    return RotorRows(
        alias,
        columns,
        [
            {"POL": "7", "ROTOR": alias, "ALPHA": "x", f"J_{alias}": "0.5", f"CT_{alias}": ct}
            for _, ct in rows
        ],
        [run for run, _ in rows],
    )


def _as_dicts(header: list[str], body: list[list[object]]) -> list[dict[str, object]]:
    return [dict(zip(header, row, strict=True)) for row in body]


def test_p0550_rows_of_one_advance_ratio_each_take_their_own_rotor_row():
    """A sweep of incidence at one J: matching on J would give every row the first thrust."""
    rows = [_polar_row("-2", "a"), _polar_row("0", "b"), _polar_row("2", "c")]
    table = _rotor("PROP", [("a", "0.11"), ("b", "0.22"), ("c", "0.33")])
    header, body, notes = merged_polar_rows(COLUMNS, rows, [table])
    out = _as_dicts(header, body)
    assert [row["CT_PROP"] for row in out] == ["0.11", "0.22", "0.33"]
    assert notes == []


def test_p0550_the_polar_columns_lead_and_keep_their_values():
    rows = [_polar_row("-2", "a")]
    header, body, _ = merged_polar_rows(COLUMNS, rows, [_rotor("PROP", [("a", "0.11")])])
    assert header == [*COLUMNS, "ROTOR", "J_PROP", "CT_PROP"]
    out = _as_dicts(header, body)[0]
    assert out["ALPHA"] == "-2", "the rotor table's own ALPHA does not replace the polar's"
    assert out["ROTOR"] == "PROP"


def test_p0550_a_point_a_rotor_left_out_reads_na_and_is_named():
    rows = [_polar_row("-2", "a"), _polar_row("0", "b")]
    header, body, notes = merged_polar_rows(COLUMNS, rows, [_rotor("PROP", [("b", "0.22")])])
    out = _as_dicts(header, body)
    assert out[0]["CT_PROP"] is None and out[0]["ROTOR"] is None
    assert out[1]["CT_PROP"] == "0.22"
    assert notes == ["run a has no row of rotor PROP"]


def test_p0550_two_rotors_each_add_their_columns_and_the_row_names_both():
    rows = [_polar_row("-2", "a")]
    tables = [_rotor("LEFT", [("a", "0.1")]), _rotor("RIGHT", [("a", "0.2")])]
    header, body, _ = merged_polar_rows(COLUMNS, rows, tables)
    out = _as_dicts(header, body)[0]
    assert (out["CT_LEFT"], out["CT_RIGHT"], out["ROTOR"]) == ("0.1", "0.2", "LEFT+RIGHT")


def test_p0550_a_table_whose_rows_do_not_each_name_a_run_is_not_joined():
    table = RotorRows("PROP", ("POL", "CT_PROP"), [{"CT_PROP": "1"}, {"CT_PROP": "2"}], ["a"])
    header, body, notes = merged_polar_rows(COLUMNS, [_polar_row("-2", "a")], [table])
    assert _as_dicts(header, body)[0]["CT_PROP"] is None
    assert "rotor PROP reads NA" in notes[0]


def test_p0550_a_declared_rotation_becomes_a_column_of_its_angle():
    rotations = [
        {"ANGLE": "3.5", "AXIS": "NAC-Y", "ALIAS": "STAR"},
        {"ANGLE": "1e-1", "AXIS": "NAC-Z", "ALIAS": "STAR"},
    ]
    rules = {"TILT": "STAR:NAC-Y", "TOE": "STAR:NAC-Z"}
    header, body, notes = merged_polar_rows(COLUMNS, [_polar_row("-2", "a")], [], rules, rotations)
    out = _as_dicts(header, body)[0]
    assert (out["TILT"], out["TOE"]) == (3.5, 0.1), "an exponent reads as a number"
    assert notes == []
    assert "ROTOR" not in header, "no rotor table, no rotor column"


def test_p0550_a_rotation_the_row_does_not_state_is_zero_and_named():
    rotations = [{"ANGLE": "3", "AXIS": "NAC-Y", "ALIAS": "OTHER"}]
    header, body, notes = merged_polar_rows(
        COLUMNS, [_polar_row("-2", "a")], [], {"TILT": "STAR:NAC-Y"}, rotations
    )
    assert _as_dicts(header, body)[0]["TILT"] == 0.0
    assert notes == ["TILT reads 0: the row states no ROTATE of STAR:NAC-Y"]


def test_p0550_a_simulation_with_no_matrix_row_states_no_angle():
    header, body, notes = merged_polar_rows(
        COLUMNS, [_polar_row("-2", "a")], [], {"TILT": "STAR:NAC-Y"}, None
    )
    assert _as_dicts(header, body)[0]["TILT"] is None
    assert notes == ["TILT read NA: this simulation has no matrix row"]


def test_p0550_a_column_the_table_holds_is_left_as_it_is_and_named():
    header, body, notes = merged_polar_rows(
        COLUMNS,
        [_polar_row("-2", "a")],
        [],
        {"ALPHA": "STAR:NAC-Y"},
        [{"ANGLE": "9", "AXIS": "NAC-Y", "ALIAS": "STAR"}],
    )
    assert _as_dicts(header, body)[0]["ALPHA"] == "-2"
    assert notes == ["ALPHA is not added: the table already holds that column"]


@pytest.mark.parametrize(
    "columns",
    [{"TILT": "STAR"}, {"TILT": ":NAC-Y"}, {"TILT": "STAR:"}, {"A,B": "STAR:NAC-Y"}],
)
def test_p0550_a_rotate_column_that_names_no_rotation_is_refused(columns):
    with pytest.raises(ValidationError, match="rotate_columns"):
        ProductsSpec(merged_polar=True, rotate_columns=columns)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_p0550_the_post_writes_the_merged_polar_when_asked(tmp_path):
    """Through the real post: off by default, then the file, its join and its manifest entry."""
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_b01_frozen_solve import _post_workspace

    workspace = _post_workspace(tmp_path, 2411, (60, 61), rotor=True)
    write_campaign_products(workspace, matrix_stem="products")
    folder = workspace.root / "post" / "products" / "polars"
    (polar_file,) = folder.glob("*_uns_avg.csv")
    (rotor_file,) = folder.glob("*_rotor.csv")
    merged = polar_file.with_name(polar_file.name.replace("_uns_avg.csv", "_merge.csv"))
    assert not merged.exists(), "off by default"
    pprocs = sorted((workspace.inputs_dir / "pproc").glob("*.toml"))
    assert pprocs
    for pproc in pprocs:
        pproc.write_text(
            pproc.read_text(encoding="utf-8")
            + "\n[products]\nmerged_polar = true\n"
            + '[products.rotate_columns]\nTILT = "STAR:NAC-Y"\n',
            encoding="utf-8",
        )
    with pytest.warns(Warning, match="TILT reads 0"):
        write_campaign_products(workspace, matrix_stem="products", overwrite=True)
    polar, rotor, out = _read(polar_file), _read(rotor_file), _read(merged)
    assert len(out) == len(polar) == len(rotor) == 1
    assert out[0]["ALPHA"] == polar[0]["ALPHA"]
    assert out[0]["CT_PUSHER"] == rotor[0]["CT_PUSHER"]
    assert out[0]["J_PUSHER"] == rotor[0]["J_PUSHER"]
    assert out[0]["ROTOR"] == "PUSHER"
    assert float(out[0]["TILT"]) == 0.0
    manifest = json.loads((folder.parent / "products.json").read_text(encoding="utf-8"))
    entry = manifest["products"][f"polars/{merged.name}"]
    assert entry["kind"] == "merged_polar"
    assert entry["rotors"] == ["PUSHER"]
    assert entry["runs"] == [polar[0]["run_id"]]
    assert "TILT reads 0" in manifest["skipped"][f"polars/{merged.name}"]


def _context(tmp_path: Path, **products: object) -> SimpleNamespace:
    return SimpleNamespace(
        pproc=SimpleNamespace(products=ProductsSpec(**products)),
        written_names={},
        skipped={},
        sim_id="7",
        out=tmp_path,
    )


def test_p0550_a_simulation_with_no_unsteady_polar_says_so(tmp_path):
    ctx = _context(tmp_path, merged_polar=True)
    with pytest.warns(Warning, match="no unsteady polar"):
        merged_polar_products(ctx)
    assert "no unsteady polar" in ctx.skipped["polars/7#merged_polar"]
    assert not list(tmp_path.iterdir())


def test_p0550_rotate_columns_without_the_product_say_so(tmp_path):
    ctx = _context(tmp_path, rotate_columns={"TILT": "STAR:NAC-Y"})
    with pytest.warns(Warning, match="only with merged_polar"):
        merged_polar_products(ctx)


def test_p0550_the_product_is_off_and_silent_by_default(tmp_path):
    ctx = _context(tmp_path)
    merged_polar_products(ctx)
    assert ctx.skipped == {}
