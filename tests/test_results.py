"""Tier 1: anchor-based parsing primitives and the loads parser.

Fixtures mirror the structure of real 26.120 (build 7012026) output
files from a local run; values, paths, and surface names are
synthetic.
"""

from pathlib import Path

import numpy as np
import pytest

from pyflightstream.results import (
    AnchorNotFoundError,
    IncompleteOutputError,
    VersionMismatchWarning,
    delimited_table,
    labeled_value,
    parse_loads,
    parse_number,
    parse_probe_points,
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
        parse_loads(text, requested_version="26.120")
    with pytest.warns(VersionMismatchWarning, match="wrong executable"):
        parse_loads(text, requested_version="26.0")


def test_parse_residual_history_reads_the_log_table():
    history = parse_residual_history(read_fixture("log_residuals_26.120.txt"))
    assert len(history) == 4
    assert history[0].iteration == 1
    assert history[-1].iteration == 1575
    assert history[-1].velocity_residual == pytest.approx(9.6e-8)
    assert history[-1].pressure_residual == pytest.approx(2.62e-8)


def test_parse_residual_history_scrubs_the_nul_bytes_of_real_exports():
    text = read_fixture("log_residuals_26.120.txt").replace("\n\n", "\n\x00\n")
    history = parse_residual_history(text)
    assert history[-1].iteration == 1575


def test_parse_probe_points_reads_the_fixture():
    report = parse_probe_points(read_fixture("probe_points_26.120.txt"))
    assert report.count == 12
    assert report.columns[:3] == ("X", "Y", "Z")
    assert report.columns[-1] == "Transition"
    assert report.positions[0] == pytest.approx([-0.5, 2.0, -0.6])
    assert report.field("vtot")[0] == pytest.approx(29.29, abs=0.01)
    assert report.angle_of_attack_deg == 4.0
    assert report.freestream_velocity_m_s == 30.0
    assert report.current_iteration == 58
    assert report.reported_build == "7012026"
    # Boundary-layer columns are inert in the fixture rows.
    for name in ("momentum_thickness", "disp_thick", "thickness", "CF", "Transition"):
        assert report.field(name) == pytest.approx(np.zeros(12))
    assert "vtot" in report.fields() and "X" not in report.fields()


def test_parse_probe_points_checks_completeness_and_version():
    text = read_fixture("probe_points_26.120.txt")
    truncated = text[: text.index("Force Units")]
    with pytest.raises(IncompleteOutputError, match="software footer|closing separator"):
        parse_probe_points(truncated)
    with pytest.warns(VersionMismatchWarning, match="wrong executable"):
        parse_probe_points(text, requested_version="26.0")
    with pytest.raises(KeyError, match="not in this export"):
        parse_probe_points(text).field("entropy")


def test_the_build_number_catches_the_hotfix_the_version_string_cannot(recwarn):
    """The run-time half of the ambiguous-alias refusal (PLN-20260802-2013).

    The concrete case, and the reason this exists: a user takes the
    build-time refusal of the vendor name seriously, changes fs_version
    to 26.121, and leaves fs_exe pointing at the 26.120 install. Both
    builds print "26.1", so the version-string check cannot see it, and
    AIR_ALTITUDE reads its METERS argument on one build and not on the
    other. Before the build was registered and compared, this was
    silent.
    """
    import warnings

    text = read_fixture("loads_steady_26.120.txt")  # footer: build #7012026

    with pytest.warns(VersionMismatchWarning) as caught:
        parse_loads(text, requested_version="26.121")
    message = str(caught[0].message)
    assert "#7012026" in message, message
    assert "#7262026" in message, message
    assert "26.121" in message, message

    # The control that makes the case above mean something: asking for
    # the build that actually ran must stay silent. Without this, a
    # check that warned unconditionally would pass the test above.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        parse_loads(text, requested_version="26.120")


def test_a_coarse_mismatch_still_warns_where_no_build_is_registered():
    # 26.000 has no committed report recording a build, so the check
    # falls back to the version string, which is enough for a mismatch
    # this coarse. The fallback must not be lost to the new path.
    text = read_fixture("loads_steady_26.120.txt")
    with pytest.warns(VersionMismatchWarning, match="wrong executable may have run"):
        parse_loads(text, requested_version="26.000")


def test_every_registered_build_comes_from_a_committed_report(recwarn):
    """A build number is evidence, so it may not be typed in from memory.

    Each registered build must appear in the solver_identity of some
    committed report for that same version. This is the invariant-3 rule
    applied to the registry: nothing about solver behaviour is recorded
    without the evidence that observed it.
    """
    import glob

    import yaml

    from pyflightstream.versions import known_versions

    observed: dict[str, set[str]] = {}
    for path in glob.glob("reports/**/*.yaml", recursive=True):
        with open(path, encoding="utf-8") as handle:
            document = yaml.safe_load(handle)
        if not isinstance(document, dict):
            continue
        version = document.get("fs_version")
        for line in document.get("solver_identity") or ():
            digits = "".join(ch for ch in str(line).split("build")[-1] if ch.isdigit())
            if version and digits:
                observed.setdefault(str(version), set()).add(digits)

    registered = {v.canonical: v.build for v in known_versions() if v.build is not None}
    assert registered, "no build is registered; this test would prove nothing"
    unevidenced = {
        canonical: build
        for canonical, build in registered.items()
        if build not in observed.get(canonical, set())
    }
    assert not unevidenced, (
        f"these registered build numbers appear in no committed report for their own "
        f"version: {unevidenced}. A build number is solver evidence; record it from a "
        "report's solver_identity, never from memory (CLAUDE.md invariant 3)."
    )
