"""PFS-2232 (FR-3778, D24): the averaged surface carries the run block in Tecplot and VTK."""

from __future__ import annotations

from pyflightstream.post._block_scope import (
    add_run_block_to_vtk,
    block_of_point,
    run_block_text,
    run_blocks,
    tecplot_run_block,
    vtk_run_block_lines,
)
from pyflightstream.post._run_block import run_block_columns, run_block_row
from pyflightstream.post.surfaces import write_point_surface_average
from tests.tier1_offline.test_g25_surface_time_average import (
    _averaged_record,
    _exports,
    _read_dat,
)

BLOCK = run_block_columns((), ())


def _row():
    return run_block_row(
        pol="7003",
        point_id=1,
        point="AL+000",
        run_type="unsteady",
        condition={"ALPHA": 2.0, "VINF": 40.0, "FIRST_STEP": 3, "LAST_STEP": 6, "STEPS": 4},
    )


def test_p0580_the_text_forms_of_a_value():
    assert run_block_text(None) == "NA" and run_block_text(float("nan")) == "NA"
    assert run_block_text('a"b') == "a'b" and run_block_text(2.5) == "2.5"


def test_p0580_the_vtk_field_block_has_one_array_per_column_in_order():
    lines = vtk_run_block_lines(_row())
    assert lines[0] == f"FIELD FieldData {len(BLOCK)}"
    names = [line.split()[0] for line in lines[1:][::2]]
    assert names == list(BLOCK)
    kinds = {line.split()[0]: line.split()[3] for line in lines[1:][::2]}
    assert kinds["POL"] == kinds["POINT"] == kinds["RUN_TYPE"] == "string"
    assert kinds["ALPHA"] == kinds["VINF"] == "double"
    values = dict(zip(names, lines[2:][::2], strict=True))
    assert (values["ALPHA"], values["RHO"], values["STEPS"]) == ("2", "nan", "4")


def test_p0580_the_field_block_lands_before_the_attribute_data(tmp_path):
    path = tmp_path / "s.vtk"
    path.write_text("# vtk DataFile Version 3.0\nt\nASCII\nPOINTS 0 float\nPOINT_DATA 0\n")
    add_run_block_to_vtk(path, {"POL": "7003"})
    lines = path.read_text().splitlines()
    assert lines.index("FIELD FieldData 1") < lines.index("POINT_DATA 0")
    plain = tmp_path / "p.vtk"
    plain.write_text("# vtk DataFile Version 3.0\nt\nASCII\n")
    add_run_block_to_vtk(plain, {"POL": "7003"})
    assert plain.read_text().splitlines()[-1] == "7003"


def test_p0580_the_averaged_surface_carries_the_block_as_auxdata_and_field_data(tmp_path):
    sim = tmp_path / "sims" / "sim_7003"
    sim.mkdir(parents=True)
    _exports(sim, range(3, 7))
    record = _averaged_record()
    out = tmp_path / "post"
    with run_blocks({"AL+000": _row()}):
        assert block_of_point("AL+000") is not None
        files, _ = write_point_surface_average(
            tmp_path, sim_dir=sim, record=record, out=out, target=lambda path: path, vtk=True
        )
    assert [p.name for p in files] == ["p_time_average.dat", "p_time_average.vtk"]
    aux = _read_dat(out / "surfaces" / "p_time_average.dat")["auxdata"]
    assert list(aux)[: len(BLOCK)] == list(BLOCK)
    assert aux["POL"] == "7003" and aux["ALPHA"] == "2.0" and aux["RHO"] == "NA"
    assert "AVERAGE_OF" in aux and list(aux).index("AVERAGE_OF") >= len(BLOCK)
    text = (out / "surfaces" / "p_time_average.vtk").read_text(encoding="utf-8")
    assert f"FIELD FieldData {len(BLOCK)}" in text and "ALPHA 1 1 double" in text


def test_p0580_outside_a_post_the_average_is_as_before(tmp_path):
    sim = tmp_path / "sims" / "sim_7003"
    sim.mkdir(parents=True)
    _exports(sim, range(3, 7))
    out = tmp_path / "post"
    write_point_surface_average(
        tmp_path,
        sim_dir=sim,
        record=_averaged_record(),
        out=out,
        target=lambda path: path,
        vtk=True,
    )
    assert "FIELD FieldData" not in (out / "surfaces" / "p_time_average.vtk").read_text()
    assert "POL" not in _read_dat(out / "surfaces" / "p_time_average.dat")["auxdata"]
    assert tecplot_run_block({"A": 1}) == {"A": "1"}
