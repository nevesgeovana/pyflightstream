"""Tier 1: the exports and the log of FlightStream 26.125 read as every earlier build's (FR-423).

26.125 prints a new product name in every export footer (``Software : Simcenter
Flightstream version 2612, build #10052026``) and in the log banner, and its loads
spreadsheet names the drag split ``CDp, CDv`` where every earlier build printed
``CDi, CDo``; each is carried under the names the solver wrote. The fixtures
under ``fixtures/s10_26125/`` keep each line of the
real 26.125 exports of 2026-10-05 that is not a data row, and replace every
number of a data row by a synthetic value printed in the same form; the names
are neutral. The recorded 26.124 export is the committed ``rpt128/rigid.txt``.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream.post.custom_polar import write_custom_polar_format
from pyflightstream.post.polar import declined_induced_drag
from pyflightstream.post.products import COEFFICIENT_COLUMNS, ReferenceValues, read_csv_table
from pyflightstream.qa.physics import PointResult, phy01_metrics, phy05_metrics
from pyflightstream.results import (
    VersionMismatchWarning,
    drag_pair,
    parse_loads,
    parse_probe_points,
    parse_surface_sections,
    parse_unsteady_plots,
)
from pyflightstream.results.core import SOFTWARE_LINE, cross_check_version
from pyflightstream.results.sectional_loads import parse_sectional_loads
from pyflightstream.run import (
    ExecutionResult,
    ExecutorConfigurationError,
    check_solver_identity,
)
from pyflightstream.versions import resolve
from tests.tier1_offline.test_post_products import LOADS, posted_polar, posted_polars_dir

FIXTURES = Path(__file__).resolve().parent / "fixtures"
S10 = FIXTURES / "s10_26125"
RECORDED_26124 = FIXTURES / "rpt128" / "rigid.txt"


def _text(name: str) -> str:
    return (S10 / name).read_text(encoding="utf-8")


def _strictly(call):
    """Run ``call`` with every warning raised, so a version mismatch fails the test."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        return call()


def test_every_26125_export_reads_with_its_simcenter_footer():
    """P0370-S10-SIMCENTER-HEADERS (FR-423): loads, probes, plots, sections and sectional loads."""
    loads = _strictly(lambda: parse_loads(_text("loads_26.125.txt"), "26.125"))
    assert (loads.fs_version_reported, loads.fs_build) == ("2612", "10052026")
    assert sorted(loads.surfaces) == ["S1", "S2"]
    probes = _strictly(lambda: parse_probe_points(_text("probes_26.125.txt"), "26.125"))
    assert probes.columns[:3] == ("X", "Y", "Z")
    plots = _strictly(lambda: parse_unsteady_plots(_text("plots_26.125.txt")))
    assert plots.columns[:2] == ("Time-step", "CL_G1")
    sections = _strictly(
        lambda: parse_surface_sections(_text("sections_26.125.txt"), requested_version="26.125")
    )
    assert len(sections.sections) == 1
    sloads = _strictly(lambda: parse_sectional_loads(_text("sloads_26.125.txt")))
    assert sloads.columns == ("Offset", "Chord", "X_QC", "Z_QC", "Fx", "Fz", "Moment")


def test_the_26125_loads_keep_the_drag_split_under_its_printed_names():
    """P0370-S10-DRAG-COLUMNS (FR-423): CDp and CDv parse as CDp and CDv, never as CDi and CDo."""
    text = _text("loads_26.125.txt")
    assert "CL, CDp, CDv, CMx" in text
    loads = parse_loads(text, "26.125")
    # The Total row of the fixture prints CDp -0.61 and CDv +0.98.
    assert (loads.total["CDp"], loads.total["CDv"]) == (-0.61, 0.98)
    assert "CDi" not in loads.total and "CDo" not in loads.total
    assert drag_pair(loads.total) == ("CDp", "CDv")
    assert list(loads.surfaces["S1"]) == list(loads.total)


def _group_acoef(tmp_path, points):
    """The drag-split columns and rows of the all-family group file of polar 3207."""
    workspace = posted_polar(tmp_path, {"1": "all"}, points=points)
    columns, rows = read_csv_table(posted_polars_dir(workspace) / "P3207-g01-ACOEF.csv")
    split = [name for name in columns if name in ("CD0", "CDI", "CDV", "CDP")]
    return split, [[row[name] for name in split] for row in rows]


def test_a_26125_polar_writes_cdv_and_cdp_with_its_numbers(tmp_path):
    """P0370-S10-DRAG-COLUMNS (FR-423): a 26.125 point's group file names its split CDV, CDP."""
    split, rows = _group_acoef(tmp_path, [("AL000", 0.0, _text("loads_26.125.txt"))])
    assert split == ["CDV", "CDP"]
    assert rows == [["0.87000", "-0.66000"]]


def test_a_polar_of_both_builds_carries_both_splits_na_where_absent(tmp_path):
    """P0370-S10-DRAG-COLUMNS (FR-423): one file, both pairs, the absent one NA and never 0."""
    points = [("AL-020", -2.0, LOADS), ("AL000", 0.0, _text("loads_26.125.txt"))]
    split, rows = _group_acoef(tmp_path, points)
    assert split == ["CD0", "CDI", "CDV", "CDP"]
    assert rows == [
        ["0.0196424", "0.0012418", "NA", "NA"],
        ["NA", "NA", "0.87000", "-0.66000"],
    ]


def test_a_26125_table_declines_no_drag_and_a_26124_table_still_does():
    """P0370-S10-DRAG-COLUMNS (FR-423): the declined rule reads CDi only, never CDp."""
    text = _text("loads_26.125.txt").replace(
        "S1,+0.4800000,-0.8500000,-0.3300000,-0.7000000,+0.1800000,",
        "S1,+0.4800000,-0.8500000,-0.3300000,-0.7000000,+0.0000000,",
    )
    assert "+0.0000000" in text
    assert declined_induced_drag(parse_loads(text), "all") == ()
    control = text.replace("CL, CDp, CDv, CMx", "CL, CDi, CDo, CMx")
    assert declined_induced_drag(parse_loads(control), "all") == ("S1",)


def test_the_custom_twin_and_the_physics_metrics_name_the_26125_split(tmp_path):
    """P0370-S10-DRAG-COLUMNS (FR-423): line 9 of the twin and the PHY metrics say CDV, CDP, CDp."""
    rows = [(1.0,) * 22 + (0.01, 0.02)]
    columns, named = (*COEFFICIENT_COLUMNS[:-2], "CDV", "CDP"), rows
    reference = ReferenceValues.from_mapping(
        {"SREF": 1.0, "CREF": 1.0, "BREF": 1.0, "XMOM": 0, "YMOM": 0, "ZMOM": 0}
    )
    path = write_custom_polar_format(
        tmp_path / "twin.dat",
        polar=1,
        description="d",
        group=1,
        mach=0.144,
        reference=reference,
        rows=named,
        columns=columns,
    )
    assert path.read_text(encoding="ascii").splitlines()[8].split()[-2:] == ["CDV", "CDP"]
    point = PointResult(4.0, {"CL": 0.35, "CDp": 0.0074, "CDv": 0.002, "CMy": 0.0}, 9, True)
    # PHY-01 fits its slope over two angles at least (PFS-2102.009): a 0 deg point beside it.
    level = PointResult(0.0, {"CL": 0.0, "CDp": 0.0, "CDv": 0.002, "CMy": 0.0}, 9, True)
    assert phy01_metrics([level, point])["CDp_a4"] == pytest.approx(0.0074)
    assert set(phy05_metrics(point)) == {"CL", "CDp", "CDv", "CMy"}


def test_a_reported_release_is_matched_on_the_registry_rows_prints():
    """P0370-S10-PRINTS-CHECK (FR-423): 2612 is 26.125's own word, read with no build beside it."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        cross_check_version("2612", "26.125", None)
    with pytest.warns(VersionMismatchWarning, match="wrong executable"):
        cross_check_version("2611", "26.125", None)


def test_f_1435_an_alias_prefix_does_not_stand_in_for_the_printed_release():
    """F-1435 X-F-0171: 26.125 prints 2612, so the shorter 26.12 is a mismatch."""
    with pytest.warns(VersionMismatchWarning, match="wrong executable"):
        cross_check_version("26.12", "26.125", None)
    with pytest.warns(VersionMismatchWarning, match="wrong executable"):
        cross_check_version("26.1", "26.125", None)


class _BannerSolver:
    """Executor stub whose exported pre-flight log is the real 26.125 banner."""

    def __init__(self, banner: str):
        self.banner = banner

    def run_script(self, script_path, working_dir, timeout_s=None):
        (Path(working_dir) / "preflight_log.txt").write_text(
            "PYFS_PREFLIGHT\n" + self.banner, encoding="utf-8"
        )
        return ExecutionResult(
            return_code=0, wall_time_s=0.01, timed_out=False, log_text=None, stdout="", stderr=""
        )


def test_the_26125_identity_lines_name_release_and_build(tmp_path):
    """P0370-S10-IDENTITY-LINE (FR-423): the pre-flight reads the banner, the footer reads too."""
    banner = _text("log_banner_26.125.txt")
    assert "Simcenter Flightstream 2612, build #10052026" in banner
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        check_solver_identity(_BannerSolver(banner), resolve("26.125"), tmp_path / "ok")
    with pytest.raises(ExecutorConfigurationError, match="10052026"):
        check_solver_identity(_BannerSolver(banner), resolve("26.124"), tmp_path / "wrong")
    footer = SOFTWARE_LINE.search(_text("loads_26.125.txt"))
    assert footer is not None
    assert (footer.group("version"), footer.group("build")) == ("2612", "10052026")


def test_a_recorded_26124_export_reads_as_it_always_did():
    """P0370-S10-26124-UNCHANGED (FR-423): the 26.124 footer, its CDi and CDo, no warning."""
    text = RECORDED_26124.read_text(encoding="utf-8")
    assert "Software : Flightstream version 26.1, build #8172026" in text
    loads = _strictly(lambda: parse_loads(text, "26.124"))
    assert (loads.fs_version_reported, loads.fs_build) == ("26.1", "8172026")
    assert list(loads.total) == ["Cx", "Cy", "Cz", "CL", "CDi", "CDo", "CMx", "CMy", "CMz"]
    assert (loads.total["CDi"], loads.total["CDo"]) == (0.0338634, 0.0098384)
