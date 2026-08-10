"""Tier 1: anchor-based parsing primitives and the loads parser.

Fixtures mirror the structure of real 26.120 (build 7012026) output
files from a local run; values, paths, and surface names are
synthetic.
"""

from pathlib import Path

import numpy as np
import pytest

from pyflightstream.results import (
    SOLVER_MODES,
    AnchorNotFoundError,
    IncompleteOutputError,
    VersionMismatchWarning,
    classify_solver_mode,
    delimited_table,
    labeled_value,
    parse_count,
    parse_loads,
    parse_number,
    parse_probe_points,
    parse_residual_history,
    reject_duplicate_columns,
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


def test_a_coarse_mismatch_still_warns_where_no_build_is_registered(monkeypatch):
    """The fallback for a build whose number is not recorded yet.

    This used to run against 26.000, which carried no build number until
    2026-08-09. Every registered build carries one now, so the registry
    can no longer produce the case and the version this test needs is
    made rather than found. The branch is not dead: a build is
    registered before it is ever run, and the whole evening of
    2026-08-09 had three builds in exactly this state.
    """
    from pyflightstream import results as results_module
    from pyflightstream.versions import FsVersion

    unrecorded = FsVersion(canonical="26.000", alias="26.0", index=2, build=None)
    monkeypatch.setattr(results_module, "resolve", lambda _requested: unrecorded)

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


# --- PYFS-009: six ways a malformed export produced a plausible number -----
#
# Every one of these parsed clean before the fix, and every one produced a
# NUMBER rather than an error, which is why none of them was ever noticed.


def _steady() -> str:
    return read_fixture("loads_steady_26.120.txt")


def test_a_repeated_header_column_is_refused():
    """It did not just confuse a column; it deleted one.

    Measured: a header naming CL twice built the row dict with CL winning
    twice, so `total` lost CDi ENTIRELY and CL held CDi's value. A drag
    coefficient was published as a lift coefficient, with the right
    magnitude for a drag number and no complaint anywhere.
    """
    doubled = _steady().replace("Surface, Cx, Cy, Cz, CL, CDi,", "Surface, Cx, Cy, Cz, CL, CL,")
    with pytest.raises(ValueError, match="names CL more than once"):
        parse_loads(doubled)


def test_a_second_total_row_is_refused():
    """Which total the run produced stops being determined by the file."""
    text = _steady()
    lines = text.splitlines(keepends=True)
    total_line = next(line for line in lines if line.strip().lower().startswith("total"))
    doubled = text.replace(total_line, total_line + total_line.replace("+0.0089000", "+9.9999999"))
    with pytest.raises(ValueError, match="more than one Total row"):
        parse_loads(doubled)


def test_a_repeated_surface_name_is_refused():
    """Same defect, the per-surface half: the later row replaced the earlier."""
    text = _steady()
    lines = text.splitlines(keepends=True)
    surface_line = next(
        line
        for line in lines
        if "," in line and not line.strip().lower().startswith(("total", "surface", "-"))
    )
    with pytest.raises(ValueError, match="more than once"):
        parse_loads(text.replace(surface_line, surface_line + surface_line))


def test_a_fractional_iteration_count_is_refused_rather_than_truncated():
    """312.9 used to become 312, and 312 is a perfectly ordinary count."""
    with pytest.raises(ValueError, match="not a whole number"):
        parse_loads(_steady().replace("number:            312", "number:            312.9"))
    with pytest.raises(ValueError, match="not a whole number"):
        parse_loads(
            _steady().replace("iterations                 500", "iterations                 500.5")
        )


@pytest.mark.parametrize("token", ["yes", "0", "banana", "TRUEISH", ""])
def test_an_unrecognised_solver_flag_token_is_refused(token):
    """Anything not starting with T used to read as OFF, silently.

    A flag read wrongly as off is worse than an unreadable one: the run then
    carries a setting it did not have, and PYFS-008's judgment now depends on
    this exact flag.
    """
    text = _steady().replace("iterations           F", f"iterations           {token}")
    with pytest.raises(ValueError, match="not one of the tokens"):
        parse_loads(text)


@pytest.mark.parametrize(("token", "expected"), [("T", True), ("F", False), ("true", True)])
def test_the_documented_flag_tokens_still_parse(token, expected):
    """The control: the refusal above is about unknown tokens, not all of them."""
    text = _steady().replace("iterations           F", f"iterations           {token}")
    assert parse_loads(text).forced_iterations is expected


def test_the_real_fixture_still_parses():
    """The control for the whole block.

    Five refusals landed in one function. Without this, a mutation that
    refused every loads file would leave all five green.
    """
    report = parse_loads(_steady())
    assert report.current_iteration == 312
    assert report.requested_iterations == 500
    assert report.forced_iterations is False
    assert set(report.total) == {"Cx", "Cy", "Cz", "CL", "CDi", "CDo", "CMx", "CMy", "CMz"}


def test_a_residual_counter_that_repeats_or_decreases_is_refused():
    """The convergence judgment reads the LAST row.

    A history of [1, 2, 1574, 2] parsed clean, which is two logs
    concatenated or a table that wrapped. The run would then be judged on a
    residual belonging to an earlier iteration of a different solve, and the
    number would look entirely reasonable.
    """
    real = read_fixture("log_residuals_26.120.txt")
    assert [sample.iteration for sample in parse_residual_history(real)][:2] == [1, 2]

    # The counter of the real log runs 1, 2, 1574. Rewrite the middle row's
    # counter so the sequence repeats, then the last row's so it decreases.
    for original, replacement in (("\n2 ", "\n1 "), ("\n1574 ", "\n2 ")):
        broken = real.replace(original, replacement, 1)
        assert broken != real, (original, replacement)
        with pytest.raises(ValueError, match="does not increase"):
            parse_residual_history(broken)


def test_a_fractional_residual_iteration_is_refused():
    """Same count rule, in the log table."""
    real = read_fixture("log_residuals_26.120.txt")
    fractional = real.replace("\n1574 ", "\n1574.5 ", 1)
    assert fractional != real
    with pytest.raises(ValueError, match="not a whole number"):
        parse_residual_history(fractional)


# --- REV010-002: integrality was only half of what a count means -----------
#
# The independent review's reproduction: replacing the current iteration
# with -1 produced CONVERGED at iteration -1, and replacing the solver mode
# with "Warp" produced COMPLETED_MAX_ITER, both with no error. Every mutant
# below is taken from the real fixture and asserted to differ from it, so a
# replacement that stops matching cannot leave the test passing on pristine
# input.


def test_a_negative_iteration_number_is_refused():
    """-1 is a perfectly whole number and not a possible iteration.

    Integrality passed it, so it reached the assessor and became the
    iteration count of a CONVERGED run.
    """
    negative = _steady().replace("number:            312", "number:            -1")
    assert negative != _steady()
    with pytest.raises(ValueError, match="cannot be below 0"):
        parse_loads(negative)


def test_a_zero_or_negative_requested_budget_is_refused():
    """A solve of zero iterations did not produce the export it is printed in."""
    for token in ("0", "-500"):
        broken = _steady().replace(
            "iterations                 500", f"iterations                 {token}"
        )
        assert broken != _steady(), token
        with pytest.raises(ValueError, match="cannot be below 1"):
            parse_loads(broken)


def test_the_pristine_fixture_still_parses():
    """The control. Without it the four mutants above could pass on a parser
    that refuses everything, which is the failure mode a mutation test is
    supposed to be immune to."""
    report = parse_loads(_steady())
    assert report.current_iteration == 312
    assert report.requested_iterations == 500
    assert report.solver_mode.strip() == "Steady"


@pytest.mark.parametrize("printed", ["Steady", "  steady ", "Unsteady", "UNSTEADY"])
def test_the_known_solver_modes_classify(printed):
    assert classify_solver_mode(printed) in SOLVER_MODES


@pytest.mark.parametrize("printed", ["Warp", "", "Stead", "steady-state", "transient"])
def test_an_unknown_solver_mode_classifies_as_nothing(printed):
    """None rather than a guess. The caller decides what unknown means; what
    it must not do is fall through to the rule for a mode it did not read."""
    assert classify_solver_mode(printed) is None


@pytest.mark.parametrize(
    ("token", "minimum", "expected"),
    [("5", 0, 5), ("0", 0, 0), ("1", 1, 1), ("5.", 0, 5), ("1.000E+01", 0, 10)],
)
def test_parse_count_accepts_the_valid_domain(token, minimum, expected):
    assert parse_count(token, label="a count", minimum=minimum) == expected


@pytest.mark.parametrize(
    ("token", "minimum"),
    [("-1", 0), ("0", 1), ("-0.0001", 0), ("312.9", 0), ("banana", 0)],
)
def test_parse_count_refuses_outside_the_domain(token, minimum):
    with pytest.raises(ValueError):
        parse_count(token, label="a count", minimum=minimum)


# --- REV010-003 and REV010-006: two ambiguities the loads parser already ---
# refused and the probe parser did not, plus one neither refused.


def _probe() -> str:
    return read_fixture("probe_points_26.120.txt")


def test_a_duplicate_probe_column_is_refused():
    """The review's reproduction: `Cp_ref` twice returned the Mach value.

    Worse here than in the loads table, because ProbePointsReport.field
    returns the FIRST tuple index of a name while fields() collapses
    duplicates into one key, so the export looked complete and one
    physical quantity answered to another's name.
    """
    text = _probe()
    header = next(line for line in text.splitlines() if line.strip().startswith("X, Y, Z,"))
    columns = [cell.strip() for cell in header.split(",") if cell.strip()]
    assert len(columns) >= 5, columns
    doubled_header = header.replace(columns[3], columns[4], 1)
    doubled = text.replace(header, doubled_header)
    assert doubled != text
    with pytest.raises(ValueError, match="more than once"):
        parse_probe_points(doubled)


def test_a_case_folded_duplicate_is_still_a_duplicate():
    """`Cp_ref` and `CP_REF` name the same field to any reader."""
    with pytest.raises(ValueError, match="more than once"):
        reject_duplicate_columns(["X", "Cp_ref", "CP_REF"], what="probe export")


def test_distinct_columns_pass():
    """The control for both refusals above."""
    reject_duplicate_columns(["X", "Y", "Z", "Cp_ref"], what="probe export")


@pytest.mark.parametrize("fixture", ["loads_steady_26.120.txt", "probe_points_26.120.txt"])
def test_two_concatenated_exports_are_refused(fixture):
    """parse_loads(loads_fixture + loads_fixture) used to succeed and return
    the first report, so appended or stale output was silently ignored and
    the consumer could not know which export was intended."""
    text = read_fixture(fixture)
    parser = parse_loads if "loads" in fixture else parse_probe_points
    parser(text)  # the control: one export still parses
    with pytest.raises(ValueError, match="more than one complete export"):
        parser(text + text)


def test_a_second_export_with_different_values_is_still_refused():
    """The dangerous form: the appended export is not a copy, so choosing
    the first by position picks a different physical answer."""
    text = read_fixture("loads_steady_26.120.txt")
    second = text.replace("2.000", "8.000")
    assert second != text
    with pytest.raises(ValueError, match="more than one complete export"):
        parse_loads(text + second)
