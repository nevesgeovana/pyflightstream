"""Calibration examples must refuse a template they cannot edit as intended."""

import runpy
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "docs/examples/_sources/workspace_fsi_calibration.py"


@pytest.mark.parametrize("factor", ["1.07", "1.05"], ids=lambda x: f"P0410-template-{x}")
def test_p0410_calibration_refuses_changed_template(tmp_path, factor):
    example = runpy.run_path(str(SOURCE))
    run = example["run_example"]
    run.__globals__["FSI_TEMPLATE"] = example["FSI_TEMPLATE"].replace(
        "bending_stiffness_n_m2 = 1.0", f"bending_stiffness_n_m2 = {factor}"
    )
    with pytest.raises(ValueError, match="template"):
        run(tmp_path)
    assert not list(tmp_path.rglob("*.toml"))


def test_p0410_calibration_reports_resolved_file_factor(tmp_path, monkeypatch):
    example = runpy.run_path(str(SOURCE))
    original = Path.write_text

    def write(path, data, **kwargs):
        if path.name == "f_calculated.toml":
            data = data.replace("bending_stiffness_n_m2 = 1.05", "bending_stiffness_n_m2 = 1.09")
        return original(path, data, **kwargs)

    monkeypatch.setattr(Path, "write_text", write)
    result = example["run_example"](tmp_path)
    assert result["file_factor"] == pytest.approx(1.09)
    assert result["matrix_factor"] == pytest.approx(1.15)
