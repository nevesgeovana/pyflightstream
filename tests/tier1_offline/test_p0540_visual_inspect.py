"""Tier 1: pyfs-matrix visual-inspect, the pair plot of the design of experiments (FR-3440).

The four matrices under fixtures/doe are rotor studies: two power-on studies that sweep the advance
ratio, one power-off study that sweeps the angle of attack, and a small power-on study.
"""

import shutil
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import EmptySelectionWarning, NotApplicableWarning
from pyflightstream.cases.matrix import read_matrix
from pyflightstream.run._visual_inspect import (
    OUTPUT_PATTERN,
    design_table,
    output_path,
    visual_inspect,
)
from pyflightstream.run.cli import main

DOE = Path(__file__).parent / "fixtures" / "doe"
COUNTS = {"doe-power-on": 27, "doe-power-off": 55, "doe-rotor-a": 56, "doe-rotor-b": 80}


@pytest.fixture
def workspace(tmp_path):
    for source in DOE.glob("*.fs"):
        shutil.copy(source, tmp_path / source.name)
    return tmp_path


def _table(workspace, names=tuple(COUNTS)):
    return design_table({n: read_matrix(workspace / f"{n}.fs") for n in names})


def test_p0540_each_matrix_expands_into_its_points(workspace):
    table = _table(workspace)
    assert {name: len(points) for name, points in table.items()} == COUNTS


def test_p0540_the_rotate_alias_turned_about_two_axes_is_named_with_its_axis(workspace):
    table = _table(workspace)
    names = {key for points in table.values() for p in points for key in p}
    assert "morph_push:ENGTILT_DN-Y" in names
    assert "morph_push:ENGTOE_RH-Z" in names
    assert "morph_push" not in names
    # an alias turned about one axis keeps its plain name
    assert "elev_RH" in names


def test_p0540_an_unstated_alias_is_not_turned_so_its_angle_is_zero(workspace):
    off = _table(workspace)["doe-power-off"]
    # the power-off matrix never states the toe axis the other matrices turn: 0, not left out
    assert all(p["morph_push:ENGTOE_RH-Z"] == 0.0 for p in off)
    assert {p["elev_RH"] for p in off} >= {0.0, -2.5, -5.0}


def test_p0540_a_parameter_a_row_does_not_state_leaves_the_point_out(workspace):
    table = _table(workspace)
    assert all("MACH" in p and "ALTFT" in p for points in table.values() for p in points)
    # SYMMETRY_LOADS and the other columns are no design parameters
    assert all("NCPUS" not in p for points in table.values() for p in points)


def test_p0540_a_power_off_row_advance_ratio_is_a_clock_and_is_left_out(workspace):
    table = _table(workspace)
    assert all("ADVANCE_RATIO" not in p for p in table["doe-power-off"])
    assert all("ADVANCE_RATIO" in p for p in table["doe-power-on"])
    assert all("ALPHA" in p for p in table["doe-power-off"])


def test_p0540_the_command_writes_the_pdf_and_prints_its_path(workspace, capsys):
    code = main(
        [
            "visual-inspect",
            "--workspace",
            str(workspace),
            "--matrices",
            "doe-rotor-a.fs",
            "doe-power-on",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    expected = output_path(workspace, ["doe-rotor-a.fs", "doe-power-on"])
    assert str(expected) in out
    assert "'doe-rotor-a': 56" in out
    assert expected.read_bytes().startswith(b"%PDF")
    assert expected.parent == workspace / "post" / "visual-inspect"
    assert OUTPUT_PATTERN.startswith("post/visual-inspect/")


def test_p0540_without_params_every_varying_parameter_is_drawn_and_reported(workspace, capsys):
    out = visual_inspect(workspace, ["doe-power-on", "doe-power-off"])
    assert out is not None and out.is_file()
    printed = capsys.readouterr().out
    varying_line = next(
        line for line in printed.splitlines() if line.startswith("varying parameters:")
    )
    assert "ADVANCE_RATIO" in varying_line
    assert "ALPHA" in varying_line
    assert "MACH" not in varying_line


def test_p0540_all_takes_every_matrix_of_the_workspace(workspace, capsys):
    out = visual_inspect(workspace, ["all"], ["ALPHA"])
    assert out == workspace / "post" / "visual-inspect" / "doe_all.pdf"
    printed = capsys.readouterr().out
    for name, count in COUNTS.items():
        assert f"'{name}': {count}" in printed


def test_p0540_an_unknown_parameter_is_warned_and_skipped_naming_what_is_stated(workspace):
    with pytest.warns(NotApplicableWarning) as caught:
        out = visual_inspect(
            workspace, ["doe-rotor-a"], ["ALPHA", "NOT_A_PARAMETER", "ADVANCE_RATIO"]
        )
    assert out is not None and out.is_file()
    text = " ".join(str(w.message) for w in caught)
    assert "NOT_A_PARAMETER" in text
    assert "ADVANCE_RATIO" in text and "morph_push:ENGTILT_DN-Y" in text


def test_p0540_with_no_parameter_left_nothing_is_written(workspace):
    with pytest.warns(EmptySelectionWarning):
        with pytest.warns(NotApplicableWarning):
            assert visual_inspect(workspace, ["doe-rotor-a"], ["NOT_A_PARAMETER"]) is None
    assert not (workspace / "post").exists()


def test_p0540_a_matrix_the_workspace_does_not_hold_is_warned_and_skipped(workspace):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = visual_inspect(workspace, ["doe-rotor-a", "nothing-here"], ["ALPHA"])
    assert out is not None
    assert any(
        issubclass(w.category, NotApplicableWarning) and "nothing-here" in str(w.message)
        for w in caught
    )
