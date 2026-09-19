"""A damaged recorded export must not silently shrink the axes oracle."""

import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "text,cause",
    [
        ("", "empty"),
        (
            "Angle of attack (Deg) 4\nSide-slip angle (Deg) 2\nSurface, Cx, Cy, Cz, CL, CDi, CDo\n",
            "Total row",
        ),
    ],
)
def test_rows_refuses_a_damaged_export_with_its_path(tmp_path, monkeypatch, text, cause):
    script = Path(__file__).parents[2] / "scripts" / "extract_recorded_total_rows.py"
    spec = importlib.util.spec_from_file_location("extract_recorded_total_rows", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "sim_1" / "raw" / "loads.txt"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(module, "SIMS", tmp_path)
    with pytest.raises(ValueError, match=cause) as error:
        module.rows()
    assert str(path) in str(error.value)
