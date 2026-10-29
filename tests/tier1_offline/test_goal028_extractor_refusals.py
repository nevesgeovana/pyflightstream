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


SCRIPT = Path(__file__).parents[2] / "scripts" / "extract_recorded_total_rows.py"
HEADER = "Surface, CL, CDi, CDo, Cx, Cy, Cz,"


def _extractor():
    spec = importlib.util.spec_from_file_location("extract_recorded_total_rows", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_row_as_long_as_its_header_reads_as_printed_trailing_comma_and_all():
    text = (
        f"{HEADER}\nTotal, +0.18828, +0.0012418, +0.0196424, +0.0274326, -0.0000032, +0.1871579,\n"
    )
    assert _extractor().total_row(text) == {
        "CL": "+0.18828",
        "CDi": "+0.0012418",
        "CDo": "+0.0196424",
        "Cx": "+0.0274326",
        "Cy": "-0.0000032",
        "Cz": "+0.1871579",
    }


def test_a_row_shorter_than_its_header_is_refused_naming_both_counts():
    text = f"{HEADER}\nTotal, +0.18828, +0.0012418, +0.0196424, +0.0274326,\n"
    with pytest.raises(ValueError) as refused:
        _extractor().total_row(text)
    assert "4 cells" in str(refused.value) and "header of 6" in str(refused.value)
