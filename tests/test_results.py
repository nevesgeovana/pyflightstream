"""Tier 1: anchor-based parsing primitives and the loads parser.

Fixtures mirror the structure of real 26.120 (build 7012026) output
files from a local run; values, paths, and surface names are
synthetic.
"""

from pathlib import Path

import pytest

from pyflightstream.results import (
    AnchorNotFoundError,
    IncompleteOutputError,
    VersionMismatchWarning,
    delimited_table,
    labeled_value,
    parse_loads,
    parse_number,
    parse_residual_history,
)

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_labeled_value_finds_by_label_never_by_line():
    text = read_fixture("loads_unsteady_26.120.txt")
    assert labeled_value(text, "Angle of attack (Deg)") == ".000"
    assert labeled_value(text, "Solver mode:") == "Unsteady"
    with pytest.raises(AnchorNotFoundError, match="refuses\\s+line offsets"):
        labeled_value(text, "No such label")


def test_parse_number_accepts_the_solver_forms():
    assert parse_number(".000") == 0.0
    assert parse_number("4380000.") == 4380000.0
    assert parse_number("1.000E-05") == 1e-5
    assert parse_number("+0.0002056") == 0.0002056
    with pytest.raises(ValueError, match="not a solver-printed number"):
        parse_number("Coefficients")


def test_delimited_table_reads_header_to_terminator():
    text = read_fixture("loads_unsteady_26.120.txt")
    rows = delimited_table(text, "Surface,")
    assert [row[0] for row in rows] == ["Blade1", "Wing", "Tail", "Total"]
    with pytest.raises(AnchorNotFoundError, match="header"):
        delimited_table(text, "NoSuchHeader,")


def test_delimited_table_without_terminator_is_incomplete():
    text = read_fixture("loads_truncated_26.120.txt")
    with pytest.raises(IncompleteOutputError, match="ends mid-table"):
        delimited_table(text, "Surface,")


def test_parse_loads_reads_the_whole_report():
    report = parse_loads(read_fixture("loads_unsteady_26.120.txt"))
    assert report.angle_of_attack_deg == 0.0
    assert report.freestream_velocity_m_s == 49.036
    assert report.requested_iterations == 500
    assert report.convergence_limit == 1e-5
    assert report.solver_mode == "Unsteady"
    assert report.current_iteration == 1575
    assert report.forced_iterations is False
    assert report.reference_area == 50.0
    assert report.reynolds == 4380000.0
    assert set(report.surfaces) == {"Blade1", "Wing", "Tail"}
    assert report.surfaces["Wing"]["CL"] == -0.0015
    assert report.total["CDi"] == -0.009075
    assert report.force_units == "Coefficients"
    assert report.fs_version_reported == "26.1"
    assert report.fs_build == "7012026"
    assert report.diverged_columns() == []


def test_parse_loads_without_footer_is_incomplete():
    with pytest.raises(IncompleteOutputError, match="no software footer"):
        parse_loads(read_fixture("loads_truncated_26.120.txt"))


def test_version_cross_check_is_prefix_lax_and_warns_on_mismatch():
    text = read_fixture("loads_unsteady_26.120.txt")
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        parse_loads(text, requested_version="26.12")
    with pytest.warns(VersionMismatchWarning, match="wrong executable"):
        parse_loads(text, requested_version="26.0")


def test_parse_residual_history_reads_the_log_table():
    history = parse_residual_history(read_fixture("log_residuals_26.120.txt"))
    assert len(history) == 4
    assert history[0].iteration == 1
    assert history[-1].iteration == 1575
    assert history[-1].velocity_residual == pytest.approx(9.6e-8)
    assert history[-1].pressure_residual == pytest.approx(2.62e-8)
