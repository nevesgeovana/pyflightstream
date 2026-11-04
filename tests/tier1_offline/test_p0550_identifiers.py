"""P0550-IDENTIFIERS: what a row states as IDENTIFIERS reaches the tables of the post alone.

A row writes ``IDENTIFIERS: {FLAP:0,TESTE:10}`` in its VAR_NAMES_VALUES cell. This module holds the
reader's half and the post's half, on real posts of the fixture campaigns; the run's half, a real
plan and run through the command line, is in ``test_run_cli.py``, beside its stub solver.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases._matrix_identifiers import matrix_run_digests
from pyflightstream.cases.matrix import MATRIX_COLUMNS, MatrixError, MatrixRow, read_matrix
from pyflightstream.post.products import write_campaign_products
from pyflightstream.results._identifier_columns import (
    stamped_table,
    stated_identifiers,
    tables_of_polar,
)
from pyflightstream.results.tables import sweep_table, write_sweep_table, write_table
from pyflightstream.run.cli import main
from pyflightstream.workspace import CampaignWorkspace, find_matrix
from tests.tier1_offline.test_b01_frozen_solve import _post_workspace
from tests.tier1_offline.test_p0320_noise_post import _unsteady_rotor_workspace
from tests.tier1_offline.test_sims_selection import _SECOND, _three_sims

STATED = "IDENTIFIERS: {FLAP:0,TESTE:10}"


def _state(matrix: Path, by_pol: dict[str, str]) -> None:
    """Add to each row of ``by_pol`` the text given, the way a person edits the cell."""
    lines = []
    for line in matrix.read_text(encoding="utf-8").splitlines():
        cells = line.split("|")
        if cells[0].strip() in by_pol:
            last = cells[-1].rstrip()
            line = line.rstrip() + (" / " if last.strip() else " ") + by_pol[cells[0].strip()]
        lines.append(line)
    matrix.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _one_row(tmp_path: Path, variables: str, **stated: str) -> Path:
    cells = dict.fromkeys(MATRIX_COLUMNS, "NA")
    cells.update(
        POL="9001",
        HIDDEN="0",
        RUN="1",
        AIRCRAFT="Wing",
        DESCRIPTION="POLAR",
        FLIGHT_CONDITION="MACH:0.1, ALPHA:sweep",
        SWEEP_VALUES="0.0,2.0",
        FS_BUILD="MANUAL",
        WORKFLOW="LEGACY",
        VAR_NAMES_VALUES=variables,
    )
    cells.update(stated)
    path = tmp_path / "one.fs"
    path.write_text(" | ".join(cells) + "\n" + " | ".join(cells.values()) + "\n", encoding="utf-8")
    return path


def _table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    return rows[0], [dict(zip(rows[0], row, strict=True)) for row in rows[1:]]


def _tables(root: Path) -> list[Path]:
    return sorted(root.rglob("*.csv"))


# ------------------------------------------------------------------ the reader


def test_p0550_identifiers_leave_the_variables_for_a_field_of_their_own(tmp_path):
    (row,) = read_matrix(_one_row(tmp_path, f"RECIPE: 003 / {STATED} / OUTPUTS: l_{{point}}.txt"))
    (plain,) = read_matrix(_one_row(tmp_path, "RECIPE: 003 / OUTPUTS: l_{point}.txt"))
    assert row.identifiers == {"FLAP": "0", "TESTE": "10"}
    assert row.variables == plain.variables
    assert plain.identifiers == {}


def test_p0550_identifier_values_are_text_as_written(tmp_path):
    cell = "IDENTIFIERS: {FLAP:0.10,RUN NAME:a/b,CLOCK:12:30,EMPTY:} / RECIPE: 003"
    (row,) = read_matrix(_one_row(tmp_path, cell))
    assert row.identifiers == {"FLAP": "0.10", "RUN NAME": "a/b", "CLOCK": "12:30", "EMPTY": ""}
    assert row.variables["RECIPE"] == "003"


@pytest.mark.parametrize(
    "value",
    [
        "FLAP",
        "FLAP:0",
        "{FLAP}",
        "{FLAP:0",
        "FLAP:0}",
        "{A:1}{B:2}",
        "{A:1} tail",
        "{:1}",
        "{A:1,A:2}",
        "{\"A\":1,'A':2}",
    ],
)
def test_p0550_a_malformed_identifiers_value_warns_and_states_none(tmp_path, value):
    """Nothing else of the row moves, the keys after a brace left open included."""
    with pytest.warns(PyflightstreamWarning, match="POL 9001: IDENTIFIERS"):
        (row,) = read_matrix(_one_row(tmp_path, f"IDENTIFIERS: {value} / RECIPE: 003"))
    assert row.identifiers == {}
    assert row.variables["RECIPE"] == "003"
    assert "IDENTIFIERS" not in row.variables


def test_p0550_the_key_stated_twice_warns_with_its_row_and_states_none(tmp_path):
    path = _one_row(tmp_path, "IDENTIFIERS: {A:1} / RECIPE: 003 / IDENTIFIERS: {A:2}")
    with pytest.warns(PyflightstreamWarning, match="POL 9001: IDENTIFIERS .*states it again"):
        (row,) = read_matrix(path)
    assert row.identifiers == {}
    assert row.variables["RECIPE"] == "003"
    assert "IDENTIFIERS" not in row.variables


def test_p0550_a_slash_before_a_pair_warns_and_keeps_the_text(tmp_path):
    path = _one_row(tmp_path, "IDENTIFIERS: {FLAP:0 / TESTE:10} / RECIPE: 003")
    with pytest.warns(PyflightstreamWarning, match="POL 9001: IDENTIFIERS gives FLAP"):
        (row,) = read_matrix(path)
    assert row.identifiers == {"FLAP": "0 / TESTE:10"}


def test_p0550_a_missing_slash_names_the_text_the_run_does_not_read(tmp_path):
    path = _one_row(tmp_path, "IDENTIFIERS: {X:1} RECIPE: 003")
    with pytest.warns(PyflightstreamWarning, match="followed by 'RECIPE: 003' with no slash"):
        (row,) = read_matrix(path)
    assert row.identifiers == {}


@pytest.mark.parametrize("name", ["identifiers", "IDENTIFIER", "Identifers"])
def test_p0550_a_key_spelled_nearly_is_pointed_at_the_key(tmp_path, name):
    path = _one_row(tmp_path, f"{name}: 1 / RECIPE: 003")
    with pytest.warns(PyflightstreamWarning, match=f"POL 9001: {name} is not IDENTIFIERS"):
        (row,) = read_matrix(path)
    assert row.identifiers == {}


def test_p0550_a_new_field_of_the_row_stands_last():
    assert dataclasses.fields(MatrixRow)[-1].name == "identifiers"


def test_p0550_a_pipe_in_a_value_is_the_matrix_s_own_refusal(tmp_path):
    """A pipe ends the cell before the key is read, so the row has the wrong number of cells."""
    path = _one_row(tmp_path, "IDENTIFIERS: {A:1|2}")
    with pytest.raises(MatrixError, match="cannot hold one"):
        read_matrix(path)


def test_p0550_a_key_that_only_holds_the_word_is_a_variable(tmp_path):
    (row,) = read_matrix(_one_row(tmp_path, "MY_IDENTIFIERS: 1 / IDENTIFIERS_X: 2 / RECIPE: 003"))
    assert row.identifiers == {}
    assert row.variables["MY_IDENTIFIERS"] == "1"
    assert row.variables["IDENTIFIERS_X"] == "2"


def test_p0550_identifiers_differing_between_the_two_homes_refuse_nothing(tmp_path):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    home = workspace.inputs_dir / "matrices"
    home.mkdir(parents=True, exist_ok=True)
    root = _one_row(workspace.root, "RECIPE: 003")
    other = home / "one.fs"
    shutil.copyfile(root, other)
    _state(other, {"9001": STATED})
    with pytest.warns(PyflightstreamWarning, match="differ in their IDENTIFIERS alone"):
        assert find_matrix(workspace.root, "one") is not None


# ------------------------------------------------------------------ the post


@pytest.fixture
def posted(tmp_path):
    """The rotor fixture campaign, its matrix stating identifiers on the row that ran."""
    workspace = _post_workspace(tmp_path, 2411, (60, 61), rotor=True)
    _state(workspace.root / "products.fs", {"7001": STATED})
    return workspace


def test_p0550_every_table_of_a_post_carries_the_row_s_identifiers(posted):
    write_campaign_products(posted, matrix_stem="products")
    tables = _tables(posted.root / "post")
    assert len(tables) >= 7
    for table in tables:
        header, rows = _table(table)
        assert header[0] == "POL", table
        at = 2 if header[1] == "ROTOR" else 1
        assert header[at : at + 2] == ["FLAP", "TESTE"], table
        assert {(row["FLAP"], row["TESTE"]) for row in rows} == {("0", "10")}, table


def test_p0550_identifiers_follow_rotor_on_the_rotor_table_and_mesh_faces_stays_last(posted):
    write_campaign_products(posted, matrix_stem="products")
    polars = posted.root / "post" / "products" / "polars"
    assert _table(next(polars.glob("*_rotor.csv")))[0][:4] == ["POL", "ROTOR", "FLAP", "TESTE"]
    assert _table(next(polars.glob("*_uns_avg.csv")))[0][-1] == "MESH_FACES"


def test_p0550_a_row_stating_none_writes_tables_with_no_such_column(tmp_path):
    """The post has a matrix with identifiers, on another row."""
    workspace = _post_workspace(tmp_path, 2411, (60, 61), rotor=True)
    _state(workspace.root / "products.fs", {"6001": STATED})
    write_campaign_products(workspace, matrix_stem="products")
    for table in _tables(workspace.root / "post"):
        assert "FLAP" not in _table(table)[0], table


def test_p0550_a_post_with_no_matrix_row_states_none(tmp_path):
    workspace = _post_workspace(tmp_path, 2411, (60, 61))
    write_campaign_products(workspace)
    for table in _tables(workspace.root / "post"):
        assert "FLAP" not in _table(table)[0], table


def test_p0550_post_sims_writes_them_on_a_posted_simulation_and_nothing_else_moves(tmp_path):
    """Her use: the campaign has run and been posted; the columns arrive with one command."""
    workspace = _post_workspace(tmp_path, 2411, (60, 61), rotor=True)
    write_campaign_products(workspace, matrix_stem="products")
    manifest = workspace.manifest_path.read_bytes()
    sim = workspace.sim_dir("7001")
    solver_files = {path: path.read_bytes() for path in sim.rglob("*") if path.is_file()}
    _state(workspace.root / "products.fs", {"7001": STATED})
    assert main(["post", "--workspace", str(workspace.root), "--sims", "7001"]) == 0
    polar = next((workspace.root / "post").rglob("*_uns_avg.csv"))
    header, rows = _table(polar)
    assert header[1:3] == ["FLAP", "TESTE"]
    assert rows[0]["TESTE"] == "10"
    assert workspace.manifest_path.read_bytes() == manifest, "no record moved"
    assert {path: path.read_bytes() for path in solver_files} == solver_files


def test_p0550_empty_identifiers_write_every_table_byte_for_byte(tmp_path):
    """A matrix whose key states nothing writes what a matrix with no key writes."""
    plain = _post_workspace(tmp_path / "plain", 2411, (60, 61), rotor=True)
    write_campaign_products(plain, matrix_stem="products")
    empty = _post_workspace(tmp_path / "empty", 2411, (60, 61), rotor=True)
    _state(empty.root / "products.fs", {"7001": "IDENTIFIERS: {}"})
    write_campaign_products(empty, matrix_stem="products")
    tables = _tables(plain.root / "post")
    assert tables
    for table in tables:
        other = empty.root / table.relative_to(plain.root)
        assert other.read_bytes() == table.read_bytes(), table


def test_p0550_a_changed_or_removed_identifier_follows_the_matrix_at_the_next_post(posted):
    write_campaign_products(posted, matrix_stem="products")
    matrix = posted.root / "products.fs"
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace("TESTE:10", "TESTE:11"), encoding="utf-8"
    )
    assert main(["post", "--workspace", str(posted.root), "--sims", "7001"]) == 0
    polar = next((posted.root / "post").rglob("*_uns_avg.csv"))
    assert _table(polar)[1][0]["TESTE"] == "11"
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace(" / IDENTIFIERS: {FLAP:0,TESTE:11}", ""),
        encoding="utf-8",
    )
    assert main(["post", "--workspace", str(posted.root), "--sims", "7001"]) == 0
    assert "TESTE" not in _table(polar)[0]


def test_p0550_a_name_a_table_holds_keeps_the_table_s_value_and_warns_once(tmp_path):
    plain = _post_workspace(tmp_path / "plain", 2411, (60, 61), rotor=True)
    write_campaign_products(plain, matrix_stem="products")
    stated = _post_workspace(tmp_path / "stated", 2411, (60, 61), rotor=True)
    _state(stated.root / "products.fs", {"7001": "IDENTIFIERS: {ALPHA:99,POL:5}"})
    with pytest.warns(PyflightstreamWarning) as caught:
        write_campaign_products(stated, matrix_stem="products")
    said = [str(w.message) for w in caught if "already holds" in str(w.message)]
    assert len([text for text in said if "identifier ALPHA" in text]) == 1, said
    assert any("POL 7001: the identifier ALPHA" in text for text in said), said
    assert len([text for text in said if "identifier POL" in text]) == 1, said
    name = next((plain.root / "post").rglob("*_uns_avg.csv")).name
    before = _table(next((plain.root / "post").rglob(name)))
    after = _table(next((stated.root / "post").rglob(name)))
    assert after[0].count("ALPHA") == 1
    assert after[0].count("POL") == 1
    assert after[1][0]["ALPHA"] == before[1][0]["ALPHA"]
    assert after[1][0]["POL"] == before[1][0]["POL"]
    plots = _table(next((stated.root / "post").rglob("*_plots.csv")))
    assert plots[0][:2] == ["POL", "ALPHA"], "a table without the name has the column"
    assert plots[1][0]["ALPHA"] == "99"


def test_p0550_a_name_differing_in_case_from_a_column_is_another_column(tmp_path):
    """Names are as written: `alpha` stands beside `ALPHA`, whose values stay the table's."""
    plain = _post_workspace(tmp_path / "plain", 2411, (60, 61), rotor=True)
    write_campaign_products(plain, matrix_stem="products")
    stated = _post_workspace(tmp_path / "stated", 2411, (60, 61), rotor=True)
    _state(stated.root / "products.fs", {"7001": "IDENTIFIERS: {alpha:99}"})
    write_campaign_products(stated, matrix_stem="products")
    name = next((plain.root / "post").rglob("*_rotor.csv")).name
    header, rows = _table(next((stated.root / "post").rglob(name)))
    assert header[:3] == ["POL", "ROTOR", "alpha"]
    assert rows[0]["alpha"] == "99"
    assert rows[0]["ALPHA"] == _table(next((plain.root / "post").rglob(name)))[1][0]["ALPHA"]


def test_p0550_a_quote_or_a_slash_in_an_identifier_reaches_the_file_under_the_cell_rule(tmp_path):
    """G16: no cell or name of a table holds a double quote; a slash stays."""
    workspace = _post_workspace(tmp_path, 2411, (60, 61), rotor=True)
    _state(workspace.root / "products.fs", {"7001": 'IDENTIFIERS: {A"B:x"y,C/D:1/2}'})
    write_campaign_products(workspace, matrix_stem="products")
    polar = next((workspace.root / "post").rglob("*_uns_avg.csv"))
    header, rows = _table(polar)
    assert header[1:3] == ["A'B", "C/D"]
    assert rows[0]["A'B"] == "x'y"
    assert rows[0]["C/D"] == "1/2"
    assert '"' not in polar.read_text(encoding="utf-8")


def test_p0550_the_merged_polar_holds_each_identifier_once_with_the_current_value(posted):
    for pproc in (posted.inputs_dir / "pproc").glob("*.toml"):
        pproc.write_text(
            pproc.read_text(encoding="utf-8") + "\n[products]\nmerged_polar = true\n",
            encoding="utf-8",
        )
    write_campaign_products(posted, matrix_stem="products")
    merged = next((posted.root / "post").rglob("*_merge.csv"))
    header, rows = _table(merged)
    assert header[:3] == ["POL", "FLAP", "TESTE"]
    assert header.count("FLAP") == header.count("TESTE") == 1
    matrix = posted.root / "products.fs"
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace("FLAP:0", "FLAP:7"), encoding="utf-8"
    )
    write_campaign_products(posted, matrix_stem="products", overwrite=True)
    header, rows = _table(merged)
    assert header.count("FLAP") == 1
    assert rows[0]["FLAP"] == "7"
    assert rows[0]["ROTOR"] == "PUSHER", "the rotor's columns still join"


def test_p0550_a_derived_polar_built_from_a_stamped_table_holds_each_name_once(posted):
    """The trimmed and the interpolated polars read the polar back and write it again."""
    for pproc in (posted.inputs_dir / "pproc").glob("*.toml"):
        pproc.write_text(
            pproc.read_text(encoding="utf-8") + "\n[products]\ntrimmed_polar = true\n",
            encoding="utf-8",
        )
    with pytest.warns(Warning):
        write_campaign_products(posted, matrix_stem="products")
    for table in _tables(posted.root / "post"):
        header = _table(table)[0]
        assert len(header) == len(set(header)), table


def _superfile_campaign(tmp_path: Path) -> tuple[CampaignWorkspace, Path]:
    workspace = _three_sims(tmp_path)
    _state(
        workspace.root / "matriz.fs",
        {"6001": "IDENTIFIERS: {FLAP:1}", "6002": "IDENTIFIERS: {TESTE:2}"},
    )
    return workspace, workspace.root / "matriz.fs"


def _supers(workspace: CampaignWorkspace) -> dict[str, Path]:
    out = workspace.products_dir("matriz") / "polars"
    return {path.name.split("-")[1]: path for path in out.glob("SUPER-*.csv")}


def test_p0550_super_files_share_one_header_and_each_row_reads_its_own_polar(tmp_path):
    workspace, _ = _superfile_campaign(tmp_path)
    write_campaign_products(workspace, matrix_stem="matriz")
    supers = _supers(workspace)
    headers = {tuple(_table(path)[0]) for path in supers.values()}
    assert len(headers) == 1, "FR-89: one union"
    assert next(iter(headers))[:3] == ("POL", "FLAP", "TESTE")
    assert {row["FLAP"] for row in _table(supers["6001"])[1]} == {"1"}
    assert {row["TESTE"] for row in _table(supers["6001"])[1]} == {"NA"}
    assert {row["FLAP"] for row in _table(supers["6002"])[1]} == {"NA"}
    assert {row["TESTE"] for row in _table(supers["6002"])[1]} == {"2"}


def test_p0550_the_key_is_no_field_the_super_file_measurement_misses(tmp_path):
    workspace, _ = _superfile_campaign(tmp_path)
    write_campaign_products(workspace, matrix_stem="matriz")
    manifest = workspace.products_dir("matriz") / "products.json"
    name = json.loads(manifest.read_text(encoding="utf-8"))["superfile_report"]
    report = json.loads((workspace.root / name).read_text(encoding="utf-8"))
    assert report["files"]
    assert "IDENTIFIERS" not in report["known"], "the key is a field no super file can hold"
    assert {"FLAP", "TESTE"} <= set(report["known"]), "its columns are, read from the tables"
    for entry in report["files"]:
        assert set(report["known"]) <= set(entry["columns"]), entry["name"]


def test_p0550_post_sims_on_one_super_file_keeps_the_others_rows_and_one_of_each_name(tmp_path):
    """The named simulation takes the matrix's value; the other's file is not rewritten."""
    workspace, matrix = _superfile_campaign(tmp_path)
    write_campaign_products(workspace, matrix_stem="matriz")
    before = _supers(workspace)
    kept = before["6002"].read_bytes()
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace("FLAP:1", "FLAP:3"), encoding="utf-8"
    )
    write_campaign_products(
        workspace,
        matrix_stem="matriz",
        overwrite=True,
        archive=True,
        archive_stamp=_SECOND,
        sims=["6001"],
    )
    supers = _supers(workspace)
    assert supers["6002"].read_bytes() == kept, "a simulation not reposted is not blanked"
    header, rows = _table(supers["6001"])
    assert header == _table(supers["6002"])[0], "one header"
    assert len(header) == len(set(header))
    assert {row["FLAP"] for row in rows} == {"3"}
    assert {row["TESTE"] for row in rows} == {"NA"}


def test_p0550_a_name_of_the_others_no_row_states_any_more_stays_na_in_a_super_file(tmp_path):
    """The kept files hold the column, so the file reposted holds it too, read as NA."""
    workspace, matrix = _superfile_campaign(tmp_path)
    write_campaign_products(workspace, matrix_stem="matriz")
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace(" / IDENTIFIERS: {FLAP:1}", ""),
        encoding="utf-8",
    )
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace(" IDENTIFIERS: {FLAP:1}", ""),
        encoding="utf-8",
    )
    write_campaign_products(
        workspace,
        matrix_stem="matriz",
        overwrite=True,
        archive=True,
        archive_stamp=_SECOND,
        sims=["6001"],
    )
    header, rows = _table(_supers(workspace)["6001"])
    assert header.count("FLAP") == 1
    assert {row["FLAP"] for row in rows} == {"NA"}
    assert {row["TESTE"] for row in rows} == {"NA"}


def test_p0550_the_fixed_width_super_file_is_not_widened(tmp_path):
    workspace, _ = _superfile_campaign(tmp_path)
    for pproc in (workspace.inputs_dir / "pproc").glob("*.toml"):
        pproc.write_text(
            pproc.read_text(encoding="utf-8") + '\n[products]\nsuperfile_format = "legacy_polar"\n',
            encoding="utf-8",
        )
    write_campaign_products(workspace, matrix_stem="matriz")
    files = list(workspace.products_dir("matriz").rglob("SUPER-*"))
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "FLAP" not in text and "TESTE" not in text, path


def test_p0550_the_custom_polar_is_not_widened_and_the_csv_beside_it_is_stamped(tmp_path):
    workspace, _ = _superfile_campaign(tmp_path)
    for pproc in (workspace.inputs_dir / "pproc").glob("*.toml"):
        pproc.write_text(
            pproc.read_text(encoding="utf-8") + "\n[products]\ncustom_polar_format = true\n",
            encoding="utf-8",
        )
    write_campaign_products(workspace, matrix_stem="matriz")
    out = workspace.products_dir("matriz")
    dats = list(out.rglob("*.dat"))
    assert dats
    for path in dats:
        assert "FLAP" not in path.read_text(encoding="utf-8"), path
    assert any("FLAP" in _table(path)[0] for path in (out / "polars").glob("P6001-*.csv"))


def test_p0550_the_sweep_table_carries_each_row_s_own_and_follows_the_matrix(tmp_path):
    workspace, matrix = _superfile_campaign(tmp_path)
    sweep = workspace.sweep_dir("matriz") / "campaign_sweep.csv"
    sweep.parent.mkdir(parents=True, exist_ok=True)
    sweep.parent.mkdir(parents=True, exist_ok=True)
    write_table(sweep_table(workspace, require_loads=False, matrix_stem="matriz"), sweep)
    write_campaign_products(workspace, matrix_stem="matriz")
    header, rows = _table(sweep)
    assert header[:3] == ["POL", "FLAP", "TESTE"]
    assert {row["FLAP"] for row in rows if row["POL"] == "6001"} == {"1"}
    assert {row["FLAP"] for row in rows if row["POL"] != "6001"} == {"NA"}
    assert {row["TESTE"] for row in rows if row["POL"] == "6002"} == {"2"}

    # Removed from the matrix: the next post takes the columns back out.
    matrix.write_text(
        re.sub(r"\s*/?\s*IDENTIFIERS: \{[^}]*\}", "", matrix.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    assert "FLAP" not in _table(sweep)[0]
    assert "TESTE" not in _table(sweep)[0]


def test_p0550_the_sweep_table_keeps_the_identifiers_of_a_polar_the_matrix_left(tmp_path):
    workspace, matrix = _superfile_campaign(tmp_path)
    sweep = workspace.sweep_dir("matriz") / "campaign_sweep.csv"
    sweep.parent.mkdir(parents=True, exist_ok=True)
    sweep.parent.mkdir(parents=True, exist_ok=True)
    write_table(sweep_table(workspace, require_loads=False, matrix_stem="matriz"), sweep)
    write_campaign_products(workspace, matrix_stem="matriz")
    lines = matrix.read_text(encoding="utf-8").splitlines()
    matrix.write_text(
        "\n".join(line for line in lines if not line.startswith("6002")) + "\n", encoding="utf-8"
    )
    write_campaign_products(workspace, matrix_stem="matriz", overwrite=True, sims=["6001"])
    _, rows = _table(sweep)
    assert {row["TESTE"] for row in rows if row["POL"] == "6002"} == {"2"}
    assert {row["TESTE"] for row in rows if row["POL"] == "6001"} == {"NA"}


def test_p0550_a_table_opening_without_pol_carries_them_as_its_last_columns(tmp_path):
    """The acoustic tables of one point open with their own columns."""
    workspace = _unsteady_rotor_workspace(tmp_path, listed=True)
    record = workspace.read_manifest()[0]
    workspace.manifest_path.unlink()
    workspace.append_record(record.model_copy(update={"matrix_stem": "noisy"}))
    _one_row(workspace.root, STATED, POL=record.sim_id).rename(workspace.root / "noisy.fs")
    write_campaign_products(workspace, matrix_stem="noisy", overwrite=True)
    tables = list(workspace.products_dir("noisy").glob("acoustics/*.csv"))
    assert tables
    for table in tables:
        header, rows = _table(table)
        assert header[0] != "POL", table
        assert header[-2:] == ["FLAP", "TESTE"], table
        assert {(row["FLAP"], row["TESTE"]) for row in rows} == {("0", "10")}, table


def _fingerprint(root: Path) -> dict[str, bytes]:
    """Every file of a workspace but the tables and what records the moment it ran."""
    volatile = (".csv", ".log", ".json", ".jsonl")
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix not in volatile and path.name != "products.fs"
    }


def test_p0550_every_file_that_is_not_a_table_keeps_its_bytes(tmp_path):
    plain = _post_workspace(tmp_path / "plain", 2411, (60, 61), rotor=True)
    write_campaign_products(plain, matrix_stem="products")
    stated = _post_workspace(tmp_path / "stated", 2411, (60, 61), rotor=True)
    _state(stated.root / "products.fs", {"7001": STATED})
    write_campaign_products(stated, matrix_stem="products")
    assert _fingerprint(stated.root) == _fingerprint(plain.root)
    for path in (stated.root / "sims").rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (plain.root / path.relative_to(stated.root)).read_bytes()


def test_p0550_the_additional_post_s_tables_carry_them_too(tmp_path):
    """Under additional/<pid>/, products like the others (G12)."""
    from tests.tier1_offline.test_additional_post import (
        POST_ADDITIONAL_TOML,
        a_recorded_campaign,
        a_stub,
        extract,
        products_of,
    )

    workspace, matrix = a_recorded_campaign(tmp_path, additional=POST_ADDITIONAL_TOML)
    _, records = extract(workspace, matrix, a_stub(tmp_path))
    assert records
    _state(matrix, {"3207": STATED})
    products = products_of(workspace, matrix)["products"]
    out = workspace.products_dir(matrix.stem)
    tables = [name for name in products if name.startswith("additional/") and name.endswith(".csv")]
    assert any(name.startswith("additional/p002/polars/") for name in tables), sorted(products)
    assert any(name.startswith("additional/p002/sections/") for name in tables), sorted(products)
    for name in tables:
        header, rows = _table(out / name)
        at = 2 if header[1] == "ROTOR" else 1
        assert header[at : at + 2] == ["FLAP", "TESTE"], name
        assert {row["TESTE"] for row in rows} == {"10"}, name


def test_p0550_the_structure_s_table_carries_them_and_its_log_copy_does_not(tmp_path):
    """`_deflection.csv` writes its own rows, past the funnel; its condition stays in place."""
    import numpy as np

    from pyflightstream._digest import file_sha256
    from pyflightstream.fsi import kinematics, nodes
    from tests.tier1_offline.test_fsig_fixed_wing import wing_config
    from tests.tier1_offline.test_post_products import ROTOR_PLAN, _unsteady_workspace

    seed = _unsteady_workspace(tmp_path / "seed", reductions=ROTOR_PLAN, recipe="unsteady")
    record = seed.read_manifest()[0]
    workspace = CampaignWorkspace.init(tmp_path / "target")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text('[groups]\n"1" = "all"\n')
    for relative in record.outputs:
        target = workspace.sim_dir(record.sim_id) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(seed.sim_dir(record.sim_id) / relative, target)
    folder = workspace.sim_dir(record.sim_id) / "structural"
    folder.mkdir()
    config = wing_config(self_weight=False)
    (folder / "config.json").write_text(config.model_dump_json())
    layout = nodes.generate_node_layout(config)
    size = len(config.blade.station_radii_m)
    local = kinematics.encode_station_translations(
        np.linspace(0, 0.008, size),
        np.zeros(size),
        np.asarray(layout.le_offset_m),
        np.asarray(layout.te_offset_m),
    )
    nodes.write_fsidisp(folder / "FSIDisp.txt", nodes.flatten_blade_translations(layout, [local]))
    log = "iteration,residual\n1,0.5\n"
    (folder / "fsi_convergence_log.csv").write_text(log, encoding="utf-8", newline="")
    workspace.append_record(
        record.model_copy(
            update={
                "cwd": str(folder),
                "matrix_stem": "coupled",
                "inputs_sha256": {
                    "config.json": file_sha256(folder / "config.json"),
                    "fsi-provenance.json": "0" * 64,
                },
            }
        )
    )
    _one_row(workspace.root, STATED, POL=record.sim_id).rename(workspace.root / "coupled.fs")
    write_campaign_products(workspace, matrix_stem="coupled")
    (table,) = workspace.root.glob("post/**/structure/*_deflection.csv")
    header, rows = _table(table)
    assert header[:3] == ["POL", "FLAP", "TESTE"]
    assert header[3:5] == ["ALPHA", "BETA"]
    assert {row["TESTE"] for row in rows} == {"10"}
    (history,) = workspace.root.glob("post/**/structure/*_history.csv")
    assert history.read_text(encoding="utf-8") == log, "a copy of the log, byte for byte"
    polar = next(workspace.root.glob("post/**/polars/*_uns_avg.csv"))
    tips = _table(polar)
    assert "tip_deflection_m_blade_1" in tips[0], "a table rewritten in place keeps its columns"
    assert tips[0].count("FLAP") == 1
    assert tips[1][0]["TESTE"] == "10"


def test_p0550_the_installed_copy_carries_them_turning_none_and_naming_none(tmp_path):
    """An identifier named as a mirrored column is still a label, and no unplaced column."""
    from tests.tier1_offline.test_p0370_s8_installed import BOTH, MATRIX, SIM, _name
    from tests.tier1_offline.test_p0370_s8_installed import _workspace as installed_workspace

    workspace = installed_workspace(tmp_path, key=BOTH)
    _one_row(workspace.root, "IDENTIFIERS: {CYAW:3,RUNLABEL:abc}", POL=SIM, PPROC="p001").rename(
        workspace.root / f"{MATRIX}.fs"
    )
    write_campaign_products(workspace, matrix_stem=MATRIX)
    out = workspace.products_dir(MATRIX)
    point = f"POLAR-{SIM}_{_name(0)}"
    source = _table(out / "probes" / f"{point}_probes.csv")
    copy = _table(out / "probes" / f"{point}_probes_installed.csv")
    assert source[0][:3] == copy[0][:3] == ["POL", "CYAW", "RUNLABEL"]
    assert {row["CYAW"] for row in copy[1]} == {"3"}, "the mirror turned a label"
    log = (out / "post.log").read_text(encoding="utf-8")
    assert not [line for line in log.splitlines() if "RUNLABEL" in line and "installed" in line]


# ------------------------------------------------------------------ the review's cases


def test_p0550_a_column_the_frame_lost_is_no_identifier(tmp_path):
    workspace = _three_sims(tmp_path)
    frame = sweep_table(workspace, require_loads=False, matrix_stem="matriz")
    target = tmp_path / "sweep.csv"
    write_table(frame, target, overwrite=True)
    plain = target.read_bytes()
    rows = list(csv.reader(target.read_text(encoding="utf-8").splitlines()))
    rows[0].append("CL_GONE")
    for row in rows[1:]:
        row.append("0.5")
    with target.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)
    write_sweep_table(frame, target)
    assert target.read_bytes() == plain


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows locks a file held open")
def test_p0550_a_locked_sweep_table_costs_its_columns_and_not_the_post(tmp_path):
    workspace = _three_sims(tmp_path)
    matrix = find_matrix(workspace.root, "matriz")
    _state(matrix, {"6001": STATED})
    sweep = workspace.sweep_dir("matriz") / "campaign_sweep.csv"
    sweep.parent.mkdir(parents=True, exist_ok=True)
    write_table(
        sweep_table(workspace, require_loads=False, matrix_stem="matriz"), sweep, overwrite=True
    )
    with sweep.open("rb"), pytest.warns(PyflightstreamWarning, match="not updated.*--sims"):
        write_campaign_products(workspace, matrix_stem="matriz")
    assert sweep.is_file(), "a table held open is warned, never retired"
    # REL55-3: what the warning promises. With every simulation posted, a plain post writes none.
    root = str(workspace.root)
    assert main(["post", "matriz", "--workspace", root]) == 0
    assert "FLAP" not in _table(sweep)[0]
    assert main(["post", "matriz", "--workspace", root, "--sims", "6001"]) == 0
    assert "FLAP" in _table(sweep)[0]


def _sweep_of(workspace: CampaignWorkspace) -> Path:
    sweep = workspace.sweep_dir("matriz") / "campaign_sweep.csv"
    sweep.parent.mkdir(parents=True, exist_ok=True)
    write_table(
        sweep_table(workspace, require_loads=False, matrix_stem="matriz"), sweep, overwrite=True
    )
    return sweep


def test_p0550_a_sweep_table_saved_in_another_encoding_costs_its_columns_and_not_the_post(tmp_path):
    """REL55-2: read as UTF-8 it raised out of the post, past the handler of a locked file."""
    workspace = _three_sims(tmp_path)
    _state(find_matrix(workspace.root, "matriz"), {"6001": STATED})
    sweep = _sweep_of(workspace)
    saved = sweep.read_bytes().replace(b"raw", "cru\u00e7".encode("cp1252"), 1)
    sweep.write_bytes(saved)
    with pytest.warns(PyflightstreamWarning, match="cannot be read as UTF-8"):
        write_campaign_products(workspace, matrix_stem="matriz")
    manifest = workspace.products_dir("matriz") / "products.json"
    assert json.loads(manifest.read_text(encoding="utf-8"))["complete"] is True
    assert sweep.read_bytes() == saved, "what cannot be read is left as it is"


def test_p0550_the_run_replaces_a_sweep_table_saved_in_another_encoding(tmp_path):
    """REL55-2: a table it could not read stopped the rewrite; 0.54.0 replaced it."""
    workspace = _three_sims(tmp_path)
    sweep = _sweep_of(workspace)
    sweep.write_bytes(sweep.read_bytes().replace(b"raw", "cru\u00e7".encode("cp1252"), 1))
    frame = sweep_table(workspace, require_loads=False, matrix_stem="matriz")
    with pytest.warns(PyflightstreamWarning, match="cannot be read as UTF-8"):
        write_sweep_table(frame, sweep)
    assert sweep.read_text(encoding="utf-8").startswith("POL,run_id,")


def test_p0550_a_sweep_table_saved_with_a_signature_takes_the_columns(tmp_path):
    """REL55-2: the signature hid POL, so the post said nothing and wrote nothing."""
    workspace = _three_sims(tmp_path)
    _state(find_matrix(workspace.root, "matriz"), {"6001": STATED})
    sweep = _sweep_of(workspace)
    sweep.write_bytes(b"\xef\xbb\xbf" + sweep.read_bytes())
    write_campaign_products(workspace, matrix_stem="matriz")
    assert sweep.read_text(encoding="utf-8").startswith("POL,FLAP,TESTE,run_id,")


@pytest.mark.parametrize(
    "edited",
    [
        " OUTPUTS: a/IDENTIFIERS:{X:1} / RECIPE: 003",
        " OUTPUTS: a / IDENTIFIERS:{X:1}/RECIPE: 003",
        "IDENTIFIERS:{X:1} / OUTPUTS: a / RECIPE: 003",
        " OUTPUTS: a / IDENTIFIERS: {X:1} / RECIPE: 003",
    ],
)
def test_p0550_an_identifier_in_any_spacing_keeps_the_plan_s_digest(tmp_path, edited):
    plain = _one_row(tmp_path, "OUTPUTS: a / RECIPE: 003")
    recorded = matrix_run_digests(plain)[0]
    text = plain.read_text(encoding="utf-8")
    assert (
        text.count(" OUTPUTS: a / RECIPE: 003") == 1 or text.count("OUTPUTS: a / RECIPE: 003") == 1
    )
    plain.write_text(
        text.replace("| OUTPUTS: a / RECIPE: 003", "|" + edited)
        if "| OUTPUTS: a / RECIPE: 003" in text
        else text.replace("OUTPUTS: a / RECIPE: 003", edited),
        encoding="utf-8",
    )
    assert recorded in matrix_run_digests(plain)


def test_p0550_a_spaced_edit_of_the_row_s_values_is_still_seen(tmp_path):
    plain = _one_row(tmp_path, "OUTPUTS: a / RECIPE: 003")
    recorded = matrix_run_digests(plain)[0]
    text = plain.read_text(encoding="utf-8")
    plain.write_text(
        text.replace("RECIPE: 003", "IDENTIFIERS:{X:1} / RECIPE: 004"), encoding="utf-8"
    )
    assert recorded not in matrix_run_digests(plain)


def test_p0550_a_comment_naming_the_column_does_not_move_the_digest(tmp_path):
    plain = _one_row(tmp_path, "OUTPUTS: a / RECIPE: 003")
    text = "# old | VAR_NAMES_VALUES | x\n" + plain.read_text(encoding="utf-8")
    plain.write_text(text, encoding="utf-8")
    recorded = matrix_run_digests(plain)[0]
    plain.write_text(
        text.replace("RECIPE: 003", "RECIPE: 003 / IDENTIFIERS: {X:1}"), encoding="utf-8"
    )
    assert recorded in matrix_run_digests(plain)


def test_p0550_a_plots_table_read_outside_the_post_holds_no_label(tmp_path):
    from pyflightstream.post.products import plots_table_series

    workspace = _post_workspace(tmp_path, 2411, (60, 61), rotor=True)
    _state(workspace.root / "products.fs", {"7001": "IDENTIFIERS: {FLAP:up}"})
    write_campaign_products(workspace, matrix_stem="products")
    tables = sorted((workspace.root / "post").rglob("*_plots.csv"))
    assert tables
    for table in tables:
        assert "FLAP" in _table(table)[0]
        columns, _series = plots_table_series(table)
        assert "FLAP" not in columns


def test_p0550_a_plots_table_clocked_by_its_time_alone_holds_no_label(tmp_path):
    """REL55-4: an export with no Time-step opens on Time (sec), and a text label raised."""
    from pyflightstream.post.products import plots_table_series

    table = tmp_path / "AL-020_plots.csv"
    table.write_text("POL,FLAP,Time (sec),CL\n7001,up,0.0,1.0\n7001,up,0.1,2.0\n", encoding="utf-8")
    columns, _series = plots_table_series(table)
    assert columns == ("Time (sec)", "CL")


def test_p0550_a_table_with_no_rows_still_carries_the_columns(tmp_path):
    with stated_identifiers({"7001": {"A": "1"}}), tables_of_polar("7001"):
        columns, rows = stamped_table(tmp_path / "t.csv", ["POL", "X"], [])
    assert list(columns) == ["POL", "A", "X"] and list(rows) == []


def test_p0550_the_settings_table_carries_them_for_every_simulation_it_holds(tmp_path):
    workspace = _three_sims(tmp_path)
    matrix = find_matrix(workspace.root, "matriz")
    _state(matrix, {"6001": "IDENTIFIERS: {FLAP:1}", "6002": "IDENTIFIERS: {FLAP:2}"})
    write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    out = workspace.products_dir("matriz")
    table = out / "settings" / "matriz_settings.csv"
    header, rows = _table(table)
    assert header[:3] == ["POL", "FLAP", "RUN_ID"]
    assert {row["POL"]: row["FLAP"] for row in rows if row["POL"] in {"6001", "6002"}} == {
        "6001": "1",
        "6002": "2",
    }
    # A post limited to one simulation rewrites this table: the others' rows take the matrix too.
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace("FLAP:1", "FLAP:5").replace("FLAP:2", "FLAP:6"),
        encoding="utf-8",
    )
    assert main(["post", "matriz", "--workspace", str(workspace.root), "--sims", "6001"]) == 0
    _header, rows = _table(table)
    assert {row["POL"]: row["FLAP"] for row in rows if row["POL"] in {"6001", "6002"}} == {
        "6001": "5",
        "6002": "6",
    }


def test_p0550_post_sims_with_a_new_name_leaves_the_others_lacking_it(tmp_path):
    workspace, matrix = _superfile_campaign(tmp_path)
    write_campaign_products(workspace, matrix_stem="matriz")
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace("FLAP:1", "FLAP:1,NEW:9"), encoding="utf-8"
    )
    write_campaign_products(
        workspace,
        matrix_stem="matriz",
        overwrite=True,
        archive=True,
        archive_stamp=_SECOND,
        sims=["6001"],
    )
    supers = _supers(workspace)
    assert "NEW" in _table(supers["6001"])[0]
    assert "NEW" not in _table(supers["6002"])[0]
    document = json.loads((workspace.products_dir("matriz") / "products.json").read_text("utf-8"))
    assert supers["6002"].name in json.dumps(document["partial"]["not_rebuilt"])


def test_p0550_the_guide_says_how_the_columns_reach_a_posted_simulation():
    from pyflightstream.cases.workflows import _vocabulary

    text = repr(vars(_vocabulary))
    at = text.index("Columns of every table the post writes for this row")
    assert "--sims" in text[at : at + 320]
    assert "next post" not in text[at : at + 320]
