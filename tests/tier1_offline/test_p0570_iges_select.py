"""0.57.0 item 3 (iges-grid defects): component selection and the junction check.

``--component NAME`` resolves names against the 406 NAME index of the files; a crossing
component is gridded from its own faces and the junction is measured against the originals.
The selection rules run without the geometry kernel; the grid runs skip where the optional
extra is absent.
"""

from __future__ import annotations

import json

import pytest

from pyflightstream._errors import InputValueError
from pyflightstream.workspace._iges_select import resolve_components
from pyflightstream.workspace._refine._obj import read_obj
from tests.tier1_offline.test_p0560_iges import (
    PLATE_GRID,
    cli,
    gmsh_or_skip,
    grid_file,
    plate_and_flap,
    run_grid,
)


def test_p0570_select_an_exact_name_keeps_the_files_order():
    assert resolve_components(["Flap", "Plate", "Fin"], ["Fin", "Flap"]) == ["Flap", "Fin"]


def test_p0570_select_a_name_differing_in_case_or_blanks_picks_the_one_component():
    assert resolve_components(["Flap", "Plate"], [" plate "]) == ["Plate"]


def test_p0570_select_an_unknown_name_is_refused_with_the_names_found():
    with pytest.raises(InputValueError) as error:
        resolve_components(["Flap", "Plate"], ["Wing"])
    message = str(error.value)
    assert "'Wing'" in message
    assert "'Flap', 'Plate'" in message
    assert "Nothing was written" in message


def test_p0570_select_a_name_matching_two_components_is_ambiguous():
    with pytest.raises(InputValueError, match="ambiguous.*'Wing'.*'wing'"):
        resolve_components(["Wing", "wing"], ["WING"])
    assert resolve_components(["Wing", "wing"], ["wing"]) == ["wing"]  # the exact name wins


def test_p0570_select_nothing_is_refused():
    with pytest.raises(InputValueError, match="at least one"):
        resolve_components(["Flap"], [])


def grid_with(tmp_path, capsys, *flags, text=PLATE_GRID):
    gmsh_or_skip()
    grid = grid_file(tmp_path, text)
    out = tmp_path / "model.obj"
    code, stdout, stderr = cli(
        [
            "geometry",
            "iges-grid",
            str(plate_and_flap(tmp_path)),
            "--grid",
            str(grid),
            "--out",
            str(out),
            *flags,
        ],
        capsys,
    )
    return code, stderr, out


def test_p0570_the_first_component_selected_leaves_the_model_with_its_own_faces(tmp_path, capsys):
    code, stderr, out = grid_with(tmp_path, capsys, "--component", "Plate")
    assert code == 0, stderr
    mesh = read_obj(out)
    assert list(mesh.families) == ["Plate"]
    record = json.loads((tmp_path / "model.obj.json").read_text(encoding="utf-8"))
    assert list(record["components"]) == ["Plate"]
    assert record["selection"] == {
        "requested": ["Plate"],
        "selected": ["Plate"],
        "left_out": ["Flap"],
    }
    assert record["junctions"] == []


def test_p0570_a_component_left_after_dropping_the_first_faces_is_still_gridded(tmp_path, capsys):
    """Flap is imported after Plate: dropping Plate renumbers the healed faces."""
    code, stderr, out = grid_with(tmp_path, capsys, "--component", "flap")
    assert code == 0, stderr
    record = json.loads((tmp_path / "model.obj.json").read_text(encoding="utf-8"))
    assert list(record["components"]) == ["Flap"]
    assert record["components"]["Flap"]["faces"] > 0
    assert list(read_obj(out).families) == ["Flap"]


def test_p0570_an_unknown_component_refuses_with_the_names_found_and_writes_nothing(
    tmp_path, capsys
):
    code, stderr, out = grid_with(tmp_path, capsys, "--component", "Wing")
    assert code == 2
    assert "'Wing'" in stderr
    assert "'Plate', 'Flap'" in stderr
    assert not out.exists()


def test_p0570_the_component_flag_repeats(tmp_path, capsys):
    code, stderr, out = grid_with(tmp_path, capsys, "--component", "Plate", "--component", "Flap")
    assert code == 0, stderr
    record = json.loads((tmp_path / "model.obj.json").read_text(encoding="utf-8"))
    assert record["selection"]["left_out"] == []
    assert len(record["junctions"]) == 1


def test_p0570_without_a_selection_the_record_says_none_and_measures_the_junction(tmp_path, capsys):
    _, record, _ = run_grid(tmp_path, capsys, [plate_and_flap(tmp_path)], PLATE_GRID)
    assert record["selection"] is None
    (junction,) = record["junctions"]
    assert sorted(junction["components"]) == ["Flap", "Plate"]
    assert junction["nodes"] >= 2
    assert 0 < junction["checked"] <= 200
    assert set(junction["distance"]) == {"Flap", "Plate"}
    assert junction["within_tolerance"]
    assert max(junction["distance"].values()) <= junction["tolerance"]


def test_p0570_a_table_for_a_component_known_but_not_selected_is_not_warned(tmp_path, capsys):
    gmsh_or_skip()
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        code, stderr, _ = grid_with(tmp_path, capsys, "--component", "Plate")
    assert code == 0, stderr
    assert not [w for w in caught if "names no component" in str(w.message)]
