"""Every product states the WHOLE condition, and the definitions page is the authority.

THE DEFECT (scope 4c, CC-04, WT-05). 0.23.0 made every product state "the flight
condition" and the tuple it shared was short: no density, no temperature, no
viscosity, and no reference velocity. A coefficient is a force divided by
``1/2 rho V^2 S``, so a file that states the coefficient and the area and neither
the density nor the velocity it was divided by is a number nobody can take back
to a force. Five review rounds read that tuple as complete, because the test
that guarded it took its REQUIRED list from the tuple itself.

So the required list here is read OFF THE DEFINITIONS PAGE, the definition of
record, and the package's tuple is compared to it, never the other way round.
The values are compared with what the RUN RECORD and the EXPORT state, read here
directly, not with anything the writers computed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyflightstream.post._tables import CONTEXT_COLUMNS
from pyflightstream.post.products import read_csv_table
from pyflightstream.results import parse_loads
from tests.tier1_offline.test_post_superfile import _post, _workspace

PAGE = Path(__file__).resolve().parents[2] / "docs" / "post-processing-definitions.md"
MARKER = re.compile(r"<!--\s*condition-columns:(?P<names>.*?)-->", flags=re.S)

#: Families that stay RAW on purpose and state no condition: the plots table is
#: the export's own header, read back column by column by the reductions.
RAW = ("_plots.csv",)


def _page_columns() -> list[str]:
    found = MARKER.search(PAGE.read_text(encoding="utf-8"))
    assert found, f"{PAGE.name} carries no condition-columns marker"
    return [
        name.strip() for name in found.group("names").replace("\n", " ").split(",") if name.strip()
    ]


def test_the_page_states_the_divisors_of_a_coefficient():
    stated = _page_columns()
    for name in ("VINF", "VREF", "RHO", "TEMP", "MU", "SREF", "CREF", "BREF"):
        assert name in stated, f"the definitions page does not list {name}"


def test_the_package_writes_the_block_the_page_defines_in_the_pages_order():
    assert list(CONTEXT_COLUMNS) == _page_columns()


@pytest.fixture
def posted(tmp_path):
    workspace = _workspace(tmp_path)
    return workspace, [Path(path) for path in _post(workspace)]


def _tables(written: list[Path]) -> list[Path]:
    return [
        path
        for path in written
        if path.suffix == ".csv"
        and path.parent.name in ("polars", "probes", "sections")
        and not path.name.endswith(RAW)
        and not path.name.startswith("SUPER-")
    ]


def test_every_table_the_stage_writes_carries_every_column_of_the_block(posted):
    _workspace_, written = posted
    tables = _tables(written)
    assert len(tables) >= 3, [path.name for path in written]
    required = _page_columns()
    for path in tables:
        skip = 1 if path.name.endswith("_rotor.csv") else 0
        columns, _rows = read_csv_table(path, skip=skip)
        missing = [name for name in required if name not in columns]
        assert not missing, f"{path.name} does not state {missing}; it states {columns}"


def test_the_air_is_the_runs_and_the_reference_velocity_is_the_exports(posted):
    workspace, written = posted
    record = next(r for r in workspace.read_manifest() if r.sim_id == "6001")
    loads_file = workspace.sim_dir("6001") / record.outputs[0]
    report = parse_loads(loads_file.read_text(encoding="utf-8"))
    (polar,) = [
        path
        for path in written
        if path.parent.name == "polars"
        and path.name.startswith("P6001-")
        and "_g01" in path.name
        and path.suffix == ".csv"
    ]
    _columns, rows = read_csv_table(polar)
    for row in rows:
        assert float(row["RHO"]) == pytest.approx(record.density_kg_m3, rel=1e-5)
        assert float(row["TEMP"]) == pytest.approx(record.temperature_k, rel=1e-5)
        assert float(row["MU"]) == pytest.approx(record.viscosity_pa_s, rel=1e-4)
        assert float(row["VREF"]) == pytest.approx(report.reference_velocity_m_s, rel=1e-5)


def test_the_stage_says_so_when_the_reference_velocity_is_not_the_free_stream(tmp_path):
    """A coefficient by VREF beside a VINF column is the one divisor a row could hide."""
    import warnings

    workspace = _workspace(tmp_path)
    record = next(r for r in workspace.read_manifest() if r.sim_id == "6001")
    loads_file = workspace.sim_dir("6001") / record.outputs[0]
    text = loads_file.read_text(encoding="utf-8")
    report = parse_loads(text)
    stated = f"{report.reference_velocity_m_s:.3f}"
    line = next(ln for ln in text.splitlines() if "Reference velocity (m/s)" in ln)
    assert stated in line, (stated, line)
    doubled = f"{2.0 * report.reference_velocity_m_s:.3f}"
    loads_file.write_text(text.replace(line, line.replace(stated, doubled)), encoding="utf-8")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _post(workspace)
    said = [str(w.message) for w in caught if "reference velocity" in str(w.message)]
    assert len(said) == 1, [str(w.message) for w in caught]
    assert doubled.rstrip("0").rstrip(".") in said[0] or doubled in said[0], said[0]
    assert "VREF" in said[0] and "VINF" in said[0]
