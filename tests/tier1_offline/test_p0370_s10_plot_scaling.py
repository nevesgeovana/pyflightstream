"""The new drag plots carry free-stream coefficients through post-processing."""

import csv
import re
from pathlib import Path

import pytest

from pyflightstream.post.point_tables import write_plots_table
from pyflightstream.results import parse_unsteady_plots


@pytest.mark.parametrize("speed", ["nan", "inf", "-inf"])
def test_p0430_w012_nonfinite_freestream_warns_and_writes_missing(tmp_path, speed):
    from pyflightstream._errors import collecting_warnings

    source = Path(__file__).parent / "fixtures/s10_26125/plots_26.125.txt"
    text = re.sub(
        r"(Freestream velocity \(m/s\)\s+)\S+",
        lambda m: m[1] + speed,
        source.read_text(encoding="utf-8"),
    )
    with collecting_warnings() as caught:
        target = write_plots_table(tmp_path / "plots.csv", text)
    assert caught and "free-stream velocity" in str(caught[0].message)
    with target.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows and all(row["CL_G1"] == "NA" for row in rows)


def test_p0430_w012_reduction_documents_significant_precision():
    from pyflightstream.post.point_tables import write_reduction_table

    assert "six significant" in write_reduction_table.__doc__


def test_p0430_f149_unreadable_reference_velocity_is_not_unit_scale(tmp_path):
    from pyflightstream._errors import ProductError

    source = Path(__file__).parent / "fixtures/s10_26125/plots_26.125.txt"
    text = source.read_text(encoding="utf-8")
    text = re.sub(r"(Reference velocity \(m/s\)\s+)\S+", r"\g<1>unreadable", text)
    with pytest.raises(ProductError):
        write_plots_table(tmp_path / "plots.csv", text)


@pytest.mark.parametrize("split", [("CDP", "CDV"), ("CDI", "CDO")])
def test_drag_plots_use_the_same_free_stream_scale_as_lift(tmp_path, split):
    """P0370-S10-DRAG-COLUMNS (FR-423): both drag pairs use (Vref / Vinf)^2."""
    source = Path(__file__).parent / "fixtures/s10_26125/plots_26.125.txt"
    text = source.read_text(encoding="utf-8")
    text = text.replace("CDI_G1", f"{split[0]}_G1").replace("CDO_G1", f"{split[1]}_G1")
    text = re.sub(r"(Reference velocity \(m/s\)\s+)49.036", r"\g<1>98.072", text)
    report = parse_unsteady_plots(text)
    target = write_plots_table(tmp_path / "plots.csv", text)
    with target.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for native, row in zip(report.values, rows, strict=True):
        for name, value in zip(report.columns, native, strict=True):
            multiplier = 4 if name in ("CL_G1", "CD_G1", *(f"{s}_G1" for s in split)) else 1
            assert float(row[name]) == pytest.approx(value * multiplier, abs=5e-6)
