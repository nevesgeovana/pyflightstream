"""Tier 1: anchor-based parsing primitives and the loads parser.

Fixtures mirror the structure of real 26.120 (build 7012026) output
files from a local run; values, paths, and surface names are
synthetic.
"""

import warnings
from pathlib import Path

import numpy as np
import pytest
from conftest import REPO

from pyflightstream.results import (
    SOLVER_MODES,
    AnchorNotFoundError,
    FieldNotInExportError,
    IncompleteOutputError,
    MalformedOutputError,
    VersionMismatchWarning,
    classify_solver_mode,
    delimited_table,
    labeled_value,
    parse_count,
    parse_force_distributions,
    parse_loads,
    parse_number,
    parse_off_body_streamlines,
    parse_probe_points,
    parse_residual_history,
    parse_solver_analysis_csv,
    parse_surface_sections,
    parse_sweep_spreadsheet,
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


def test_the_coarse_fallback_is_silent_when_the_version_string_agrees(monkeypatch):
    """Control for the fallback above, and it took two attempts.

    A fallback that warned unconditionally would satisfy the test above
    and be worse than no check: every correct run would cry wolf. A QA
    pass measured exactly that, turning the comparison into ``if True``
    and finding 200 tests still green, because the control had been
    DELETED on the ground that no fixture could produce the silent case.

    It can, and this is it. The fixture's footer version is rewritten to
    one no registered build prints, and the version resolved to is a
    synthetic build carrying that same name and no number. Same branch,
    agreement instead of disagreement, and the alias is unshared so the
    second branch below it cannot fire either.
    """
    import warnings

    from pyflightstream import results as results_module
    from pyflightstream.versions import FsVersion

    text = read_fixture("loads_steady_26.120.txt").replace("26.1", "27.9")
    unrecorded = FsVersion(canonical="27.900", alias="27.9", index=99, build=None)
    monkeypatch.setattr(results_module, "resolve", lambda _requested: unrecorded)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        parse_loads(text, requested_version="27.900")


def test_every_registered_build_comes_from_a_committed_report(recwarn):
    """A build number is evidence, so it may not be typed in from memory.

    Each registered build must appear in the solver_identity of some
    committed report for that same version. This is the invariant-3 rule
    applied to the registry: nothing about solver behaviour is recorded
    without the evidence that observed it.
    """
    import yaml

    from pyflightstream.versions import known_versions

    # From the declared anchor, never from the working directory
    # (OPS-2009.02.04). This walked `reports/**/*.yaml` relative to
    # wherever pytest was invoked, so a run from any directory but the
    # root matched no file and reported EVERY registered build as
    # unevidenced: the strongest finding this module can make, produced
    # by a lookup that never read a report at all.
    reports = REPO / "reports"
    assert reports.is_dir(), (
        f"the committed report tree is not at {reports}. Every build number below is "
        "checked against it, so its absence must be reported as a missing tree and "
        "never as nine builds recorded from memory."
    )
    documents = sorted(reports.rglob("*.yaml"))
    assert documents, (
        f"{reports} holds no .yaml report. An empty tree makes every registered build "
        "unevidenced by construction, which is a fact about the search and not about "
        "the registry."
    )
    observed: dict[str, set[str]] = {}
    for path in documents:
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


# --- PFS-2015.02.02: the unsteady plot export, the one per-timestep file ---
#
# READ THE FIXTURE'S OWN HEADER BEFORE READING THESE TESTS. Every other
# fixture in this directory mirrors the structure of a real 26.120 output
# file; `unsteady_plots_26.120.txt` mirrors the manual's SENTENCE about
# one, because no export of UNSTEADY_SOLVER_EXPORT_PLOTS exists in this
# repository and producing one costs a licensed solver seat. What these
# tests establish is that the parser reads the documented shape and
# refuses the three malformations; what they do NOT establish is that the
# documented shape is the shape the solver writes.


UNSTEADY_HEADER = "Time (sec), CL, CDi, CM"


def _unsteady(rows: str, header: str = UNSTEADY_HEADER) -> str:
    """A minimal export body: a banner with no comma, then the table."""
    return f"UNSTEADY PLOT EXPORT\n\n{header}\n{rows}"


def _parse_unsteady(text: str):
    """Call the public parser, failing on its ABSENCE with a sentence.

    A bare import would make this module fail to collect while the parser
    does not exist, and a collection error is not the finding: the
    finding is that the results layer publishes no reader for the only
    export carrying per-timestep history.
    """
    from pyflightstream import results

    parser = getattr(results, "parse_unsteady_plots", None)
    assert parser is not None and "parse_unsteady_plots" in results.__all__, (
        "pyflightstream.results publishes no parse_unsteady_plots. The unsteady "
        "plot export is the only file in the whole pipeline that carries one row "
        "per time step, so without it every time-resolved quantity a run produces "
        "is unreadable by this package (PFS-2015.02.02)."
    )
    return parser(text)


def test_the_unsteady_export_reads_into_per_column_time_series():
    """The documented shape: one column per plot, one row per time step.

    Columns are resolved by LABEL and never by position: the export's
    column set is what a plot list makes it, so the order is data and
    not a contract.
    """
    report = _parse_unsteady(read_fixture("unsteady_plots_26.120.txt"))
    assert set(report.columns) == {"Time (sec)", "CL", "CDi", "CM"}
    assert report.steps == 5
    assert report.series("CL")[0] == pytest.approx(2.35e-3)
    assert report.series("CL")[-1] == pytest.approx(1.75e-3)
    assert report.series("Time (sec)")[1] == pytest.approx(0.004)
    assert len(report.series("CM")) == report.steps
    assert set(report.series_by_name()) == set(report.columns)


def test_a_column_the_export_does_not_carry_is_refused_by_name():
    report = _parse_unsteady(read_fixture("unsteady_plots_26.120.txt"))
    with pytest.raises(FieldNotInExportError, match="CDo"):
        report.series("CDo")


def test_a_duplicated_plot_column_is_refused():
    """Two plots printed under one name lose one of the two.

    The same refusal the probe parser carries: the row is read into a
    mapping, so the repeated name takes the other plot's history and
    that plot disappears with nothing saying so.
    """
    text = _unsteady("0., 1., 2., 3.\n", header="Time (sec), CL, CL, CM")
    with pytest.raises(MalformedOutputError, match="more than once"):
        _parse_unsteady(text)


def test_an_unparseable_cell_names_the_step_and_the_column():
    text = _unsteady("0., 1., 2., 3.\n.004, 1., diverged, 3.\n")
    with pytest.raises(MalformedOutputError) as caught:
        _parse_unsteady(text)
    message = str(caught.value)
    assert "diverged" in message
    assert "CDi" in message, f"the refusal does not name the column it read: {message}"
    assert "2" in message, f"the refusal does not name the step it read: {message}"


def test_a_short_row_is_refused_rather_than_padded():
    """A row narrower than the header is a write that stopped (FR-17)."""
    text = _unsteady("0., 1., 2., 3.\n.004, 1., 2.\n")
    with pytest.raises(IncompleteOutputError) as caught:
        _parse_unsteady(text)
    assert "3" in str(caught.value) and "4" in str(caught.value)


def test_a_wide_row_is_refused_as_a_changed_layout():
    text = _unsteady("0., 1., 2., 3.\n.004, 1., 2., 3., 4.\n")
    with pytest.raises(MalformedOutputError, match="5 values"):
        _parse_unsteady(text)


def test_a_header_with_no_time_step_at_all_is_refused():
    """An empty table is not a run of zero steps; it is a truncated file."""
    with pytest.raises(IncompleteOutputError, match="no time step"):
        _parse_unsteady(_unsteady(""))


def test_a_file_carrying_no_table_is_refused_by_its_anchor():
    with pytest.raises(AnchorNotFoundError, match="header"):
        _parse_unsteady("UNSTEADY PLOT EXPORT\n\nnothing here is a table\n")


def test_a_probe_export_is_refused_rather_than_read_as_a_history():
    """Measured on the committed probe fixture, not imagined.

    The probe export is also a comma table of numbers under a header,
    so it parsed cleanly here and returned twelve "time steps" that are
    twelve positions in space. Nothing in the documented shape of the
    unsteady export distinguishes the two, so the refusal keys on the
    probe export's own declaration of itself.
    """
    with pytest.raises(MalformedOutputError, match="parse_probe_points"):
        _parse_unsteady(read_fixture("probe_points_26.120.txt"))


def test_a_loads_export_refuses_on_its_first_surface_name():
    """The other real fixture, refused by the cells rather than by a label."""
    with pytest.raises(MalformedOutputError, match="not a solver-printed number"):
        _parse_unsteady(read_fixture("loads_steady_26.120.txt"))


def test_the_unsteady_fixture_says_in_its_own_header_that_it_is_synthetic():
    """The corpus means something only while its exceptions are labelled.

    Every other fixture here mirrors a real solver file. This one was
    written from the manual's paraphrase, and a reader who takes it for
    an observation would read the delimiter, the column names and the
    banner as evidence about FlightStream. The label is the only thing
    stopping that, so it is asserted rather than trusted.
    """
    text = read_fixture("unsteady_plots_26.120.txt")
    banner = text.split(UNSTEADY_HEADER)[0]
    assert "SYNTHETIC" in banner
    assert "NOT A SOLVER EXPORT" in banner


# --- PFS-2014.02: every solver export is classified ------------------------
#
# Her requirement of 2026-08-16, with her scoping the same day. The default
# conversion set excludes the Tecplot, VTK and Nastran exports, whose own
# tools already read them; everything else a solver run writes should be
# readable without leaving the package.
#
# THE CENSUS CANNOT BE THE DEFAULT SET, which is why the classification is
# explicit data. Two of the eighteen `phase: export` entries export nothing
# at all: SET_VTK_EXPORT_VARIABLES chooses what a later export writes, and
# DELETE_BL_VELOCITY_PROFILE deletes a profile. A filter over the phase would
# have owed parsers for both.


def _export_census() -> set[str]:
    """Every `phase: export` command name in the live database.

    Read from the registry rather than from the yaml text, so the census
    is whatever the package itself resolves and a new file under
    `commands/` needs no second list here.
    """
    from pyflightstream.commands import CommandRegistry, Phase

    registry = CommandRegistry.load()
    return {name for name, entry in registry.commands.items() if entry.phase == Phase.EXPORT}


def test_every_export_command_is_classified():
    """A new export command fails the suite until somebody classifies it.

    The equality is two-sided on purpose. A key with no census entry is
    a classification for a command that no longer exists, which is the
    same failure as an unclassified command one field over: it makes the
    table look complete while covering something else.
    """
    from pyflightstream.results import EXPORT_CONVERSIONS

    census = _export_census()
    assert set(EXPORT_CONVERSIONS) == census, (
        "the export classification and the phase: export census disagree.\n  "
        f"classified and not in the census: {sorted(set(EXPORT_CONVERSIONS) - census)}\n  "
        f"in the census and unclassified: {sorted(census - set(EXPORT_CONVERSIONS))}\n"
        "Every export command needs a verdict (parsed, excluded, not_an_export "
        "or owed) before this package can claim to know what it can read."
    )
    # Non-vacuity: an empty registry would satisfy the equality against an
    # empty table and report green over nothing at all.
    assert len(census) >= 18, (
        f"the census resolved only {len(census)} export command(s); the database "
        "held eighteen when this guard was written and commands are only added"
    )


def test_every_parsed_verdict_names_an_importable_callable():
    """A verdict of `parsed` is a claim, and this is what checks it.

    The parser is recorded as a dotted STRING so that naming the
    sectional-loads parser does not make the results layer require the
    optional [fsi] extra. A string is exactly what can rot, so it is
    resolved here.
    """
    import importlib

    from pyflightstream.results import EXPORT_CONVERSIONS, EXPORT_PARSED

    resolved = 0
    for command, entry in sorted(EXPORT_CONVERSIONS.items()):
        if entry.verdict != EXPORT_PARSED:
            assert entry.parser is None, (
                f"{command} is classified {entry.verdict!r} and still names a parser"
            )
            continue
        assert entry.parser, f"{command} is classified parsed and names no parser"
        module_name, _, attribute = entry.parser.rpartition(".")
        module = importlib.import_module(module_name)
        assert callable(getattr(module, attribute, None)), (
            f"{command} names {entry.parser!r}, which is not a callable of "
            f"{module_name}; the classification claims this package can read the "
            "export and the claim has to resolve"
        )
        resolved += 1
    assert resolved >= 10, (
        f"only {resolved} parsed verdict(s) were resolved; ten exports have "
        "parsers today and this walk is what proves the claim rather than "
        "repeating it. The floor was four until PFS-2014.02 wrote the six "
        "parsers the classification owed (2026-08-20); it is a NON-VACUITY "
        "floor, so it rises when parsers are added and a fall in it is a "
        "parser that went missing rather than a number to relax"
    )


def test_the_excluded_set_is_exactly_the_three_structured_formats():
    """Her scoping, pinned: tecplot, vtk and nastran, and nothing else.

    An entry quietly moved to `excluded` is how the default set shrinks
    without anyone deciding to shrink it, and `excluded` is the one
    verdict that owes nobody any work.
    """
    from pyflightstream.results import EXPORT_CONVERSIONS, EXPORT_EXCLUDED

    excluded = {
        command: entry.format
        for command, entry in EXPORT_CONVERSIONS.items()
        if entry.verdict == EXPORT_EXCLUDED
    }
    assert set(excluded.values()) == {"tecplot", "vtk", "nastran"}
    assert excluded == {
        "EXPORT_SOLVER_ANALYSIS_TECPLOT": "tecplot",
        "EXPORT_VOLUME_SECTION_TECPLOT": "tecplot",
        "EXPORT_SOLVER_ANALYSIS_VTK": "vtk",
        "EXPORT_VOLUME_SECTION_VTK": "vtk",
        "EXPORT_SOLVER_ANALYSIS_PLOAD_BDF": "nastran",
    }, (
        "the excluded set moved. It is the author's scoping of 2026-08-16 and "
        "not an implementation convenience: a format leaving the default set "
        "is a decision, announced in the changelog"
    )


def test_asking_for_a_conversion_that_does_not_exist_names_the_format():
    """Refused naming the format, never silently skipped.

    Three different absences, three different sentences, because "this
    package cannot convert it" and "nothing was ever exported" are
    different facts and a caller acts on them differently.
    """
    from pyflightstream.results import (
        EXPORT_CONVERSIONS,
        EXPORT_OWED,
        FieldNotInExportError,
        require_export_parser,
    )

    assert require_export_parser("EXPORT_PROBE_POINTS") == (
        "pyflightstream.results.parse_probe_points"
    )
    with pytest.raises(MalformedOutputError, match="vtk file"):
        require_export_parser("EXPORT_SOLVER_ANALYSIS_VTK")
    with pytest.raises(MalformedOutputError, match="writes no data file"):
        require_export_parser("SET_VTK_EXPORT_VARIABLES")
    owed = sorted(
        command for command, entry in EXPORT_CONVERSIONS.items() if entry.verdict == EXPORT_OWED
    )
    assert owed, "the owed tranche is empty; delete this arm or restore the debt"
    with pytest.raises(MalformedOutputError, match="cannot read it yet"):
        require_export_parser(owed[0])
    with pytest.raises(FieldNotInExportError, match="not a classified export"):
        require_export_parser("EXPORT_NOTHING_AT_ALL")


# --- PFS-2014.04: the conversion path is NumPy, and this proves it ---------
#
# Her standing rule, restated for this batch on 2026-08-16: all of these
# operations are pure NumPy, with scipy only where a specific need requires
# it. THE REASON IS NOT PERFORMANCE. A file conversion is the last place a
# user should meet an install problem, and every table library in the world
# would do this job, which is exactly why the boundary needs a mechanism
# rather than a habit.
#
# The proof is STRUCTURAL, over the sources and the call graph, because a
# test that merely calls the functions proves nothing: it stays green with a
# convenience dependency added beside the work it does.
#
# THE GUARD LIVES HERE rather than in tests/test_conventions.py, whose
# `_imported_module_names` it reuses, because six agents were editing this
# tree the day it was written and that module belonged to another one. It is
# a conventions guard by nature and moving it there is a one-import edit.

_GOVERNED_ROOTS = ("pyflightstream.results", "pyflightstream.post")

#: The one third-party package this path may reach for without a record.
_ALWAYS_ALLOWED = frozenset({"numpy"})

#: A scipy import is admitted only on a module that states, in one line
#: beside it, which specific need requires it. The marker is a comment, so
#: the justification cannot be satisfied by a docstring somewhere else.
_SCIPY_MARKER = "AD-06 scipy:"

#: THE AD-06 RESIDUALS, one recorded (module, package) pair each. This is a
#: ratchet in the shape `MYPY_EXEMPTIONS` uses (tests/test_traceability.py):
#: the table IS the debt, an unrecorded arrival fails, and an entry that
#: outlives its import fails too, because an exemption for an import nobody
#: makes is a free slot for the next one.
#:
#: MEASURED 2026-08-19 AND THE COUNT IS THREE, not the two this item's own
#: plan named. `pydantic` arrived in `post/writers.py` with the layer hoist
#: of commit 2c5179e, for `OutputProvenance`, one day before this guard was
#: written; the plan was authored against the tree as it stood before it.
#: Recorded rather than refused, because refusing it would delete a model
#: this release just shipped, and named rather than folded into the always
#: allowed set, because the point of the boundary is that each crossing is
#: somebody's decision.
_AD06_RESIDUALS = {
    ("pyflightstream.results.tables", "pandas"): (
        "the tabular substrate itself (SRS AD-06); the module's own docstring "
        "says the tables rest on pandas and that downstream code depends on the "
        "column schema rather than on the library holding the values"
    ),
    ("pyflightstream.post.writers", "xarray"): (
        "the labeled physical-field substrate (SRS AD-06); the writers take a "
        "Dataset of sampled fields and flatten it to points"
    ),
    ("pyflightstream.post.writers", "pydantic"): (
        "OutputProvenance is a validated model, and validation is a generic need "
        "the engineering policy sends to a public library; every layer of this "
        "package already carries pydantic for the same reason"
    ),
}

#: MODULES THAT ARE NOT REACHABLE FROM THEIR OWN PACKAGE ROOT, which the
#: reachability arm below otherwise refuses outright. One entry, and it is
#: the arm working rather than failing: `post/settings_table.py` is a public
#: module with its own tests, and `post/__init__.py` names it in prose only,
#: so `import pyflightstream.post` does not bring it in. Fixing it is one
#: line in a file this session did not own; the fix is in the handover, and
#: the entry goes stale and fails the moment it lands.
_UNREACHABLE_FROM_ITS_PACKAGE_ROOT = {
    "pyflightstream.post.settings_table": (
        "post/__init__.py mentions it in its docstring and imports nothing from "
        "it; the re-export is owed and this entry goes stale the moment it lands"
    ),
}


def _package_src() -> Path:
    """The installed package directory the guards below walk."""
    import pyflightstream

    return Path(pyflightstream.__file__).parent


def _module_file(dotted: str) -> Path | None:
    """The source file of one dotted name, or None when it names no module.

    `_imported_module_names` deliberately records both readings of a
    `from X import y`, so half of what it returns names an OBJECT rather
    than a module. Resolving against the tree is what tells them apart,
    and it does so without importing anything.
    """
    if not dotted.startswith("pyflightstream"):
        return None
    parts = dotted.split(".")[1:]
    base = _package_src().joinpath(*parts) if parts else _package_src()
    if base.is_dir() and (base / "__init__.py").is_file():
        return base / "__init__.py"
    plain = base.with_suffix(".py")
    return plain if plain.is_file() else None


def _internal_import_closure(roots) -> set[str]:
    """Every module of this package reachable by import from `roots`.

    Derived rather than listed: a hand-kept list is a second home for a
    fact the source already states, and it would go stale on the first
    module either package gains.
    """
    from test_conventions import _imported_module_names

    seen: set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = _module_file(name)
        if path is None:
            continue
        seen.add(name)
        package = name if path.name == "__init__.py" else name.rsplit(".", 1)[0]
        source = path.read_text(encoding="utf-8")
        for imported in _imported_module_names(source, package):
            if imported.startswith("pyflightstream") and imported not in seen:
                pending.append(imported)
    return seen


def _modules_under_governed_directories() -> dict[str, Path]:
    """Every .py under results/ and post/, as dotted name to file.

    The governed set is the DIRECTORIES rather than the closure, so a
    module that is not reachable is still held to the dependency rule
    while the reachability arm reports it separately. Taking the closure
    alone would have let `post/settings_table.py` import anything it
    liked, unseen by both arms at once.
    """
    found: dict[str, Path] = {}
    src = _package_src()
    for root in _GOVERNED_ROOTS:
        directory = src.joinpath(*root.split(".")[1:])
        for path in sorted(directory.rglob("*.py")):
            parts = list(path.relative_to(src).parts)
            if parts[-1] == "__init__.py":
                parts = parts[:-1]
            else:
                parts[-1] = parts[-1][: -len(".py")]
            found["pyflightstream." + ".".join(parts)] = path
    return found


def _third_party_top_level(module_name: str, source: str) -> set[str]:
    """Top-level names this source imports from outside this package.

    Function-body imports included, because deferring an import to call
    time changes nothing about what has to be installed and is exactly
    how a dependency hides from a module-level reader.
    """
    import sys

    from test_conventions import _imported_module_names

    path = _module_file(module_name)
    if path is not None and path.name == "__init__.py":
        package = module_name
    else:
        package = module_name.rsplit(".", 1)[0]
    tops = set()
    for imported in _imported_module_names(source, package):
        top = imported.split(".")[0]
        if not top or top == "pyflightstream" or top in sys.stdlib_module_names:
            continue
        tops.add(top)
    return tops


def _unrecorded_third_party(module_name: str, source: str) -> set[str]:
    """The dependency policy of PFS-2014.04, as a pure function.

    Separated from the walk so the guard and its proof run the SAME
    decision: a proof over a synthetic tree that re-implements the rule
    is a proof of the re-implementation.
    """
    offenders = set()
    for top in _third_party_top_level(module_name, source):
        if top in _ALWAYS_ALLOWED:
            continue
        if (module_name, top) in _AD06_RESIDUALS:
            continue
        if top == "scipy" and _SCIPY_MARKER in source:
            continue
        offenders.add(top)
    return offenders


def test_no_module_under_results_or_post_reaches_for_an_unrecorded_dependency():
    """The conversion and reduction path is NumPy, proved over the sources.

    The canary is here rather than only in the policy test beside it,
    and the adversarial pass is why: replacing `_unrecorded_third_party`
    with `lambda *a: set()` left THIS test green over eight real modules,
    since a guard that reports no offender cannot tell "none" from "not
    looking". The module floor below counts subjects and cannot see it.
    """
    assert _unrecorded_third_party("pyflightstream.results.conditions", "import polars\n") == {
        "polars"
    }, "the policy decision this guard rests on reports nothing at all"
    governed = _modules_under_governed_directories()
    offenders = {
        name: sorted(found)
        for name, path in sorted(governed.items())
        if (found := _unrecorded_third_party(name, path.read_text(encoding="utf-8")))
    }
    assert not offenders, (
        f"these modules under {' and '.join(_GOVERNED_ROOTS)} import a third-party "
        f"package this path does not admit: {offenders}. The rule is numpy, plus "
        "scipy where one line beside the import states the specific need, plus the "
        "AD-06 substrate residuals recorded in _AD06_RESIDUALS. A file conversion "
        "is the last place a user should meet an install problem."
    )
    assert len(governed) >= 8, (
        f"only {len(governed)} module(s) were governed; eight .py files sat under "
        "those two directories when this was written, so a smaller number means "
        "the walk stopped seeing them rather than that the rule is satisfied"
    )


def test_the_ad06_residual_ratchet_holds_only_imports_that_still_exist():
    """A residual entry that outlives its import is a free slot.

    The failure it prevents is precise: delete the pandas import from
    results/tables.py and the entry stays, so the next module to import
    pandas under that name inherits an exemption nobody granted.
    """
    governed = _modules_under_governed_directories()
    stale = {}
    for module_name, top in sorted(_AD06_RESIDUALS):
        path = governed.get(module_name)
        if path is None:
            stale[(module_name, top)] = "the module is gone"
        elif top not in _third_party_top_level(module_name, path.read_text(encoding="utf-8")):
            stale[(module_name, top)] = "the import is gone"
    assert not stale, (
        f"the AD-06 residual ratchet records {sorted(stale)}, which the walk no "
        "longer sees. Delete the entry in the same commit that removes the "
        "import: the whole value of the list is that it only shrinks"
    )


def test_every_module_under_results_and_post_is_reachable_from_its_package_root():
    """A module cannot hide from the dependency rule by being unimportable.

    Reachability is asserted separately from the rule itself, so an
    unreachable module fails by NAME rather than by silently sitting
    outside a closure nobody re-measured.
    """
    closure = _internal_import_closure(_GOVERNED_ROOTS)
    unreachable = sorted(
        name
        for name in _modules_under_governed_directories()
        if name not in closure and name not in _UNREACHABLE_FROM_ITS_PACKAGE_ROOT
    )
    assert not unreachable, (
        f"these modules are not reachable by import from {list(_GOVERNED_ROOTS)}: "
        f"{unreachable}. Re-export them from their package __init__, or record the "
        "reason in _UNREACHABLE_FROM_ITS_PACKAGE_ROOT with the row that closes it"
    )


def test_the_unreachability_ratchet_holds_only_modules_that_are_still_hidden():
    """The companion that makes the exception above a debt rather than a hole."""
    closure = _internal_import_closure(_GOVERNED_ROOTS)
    governed = _modules_under_governed_directories()
    stale = sorted(
        name
        for name in _UNREACHABLE_FROM_ITS_PACKAGE_ROOT
        if name in closure or name not in governed
    )
    assert not stale, (
        f"{stale} are recorded as unreachable and are reachable now (or gone). "
        "Delete the entry in the same commit that re-exports the module"
    )


def test_the_dependency_policy_admits_and_refuses_the_right_imports():
    """The decision itself, over synthetic sources, arm by arm.

    Every arm is exercised here INCLUDING the ones no real module
    reaches, which is the point: the scipy branch admits nothing in this
    tree today, so without this test it would be an untested rule
    published as a guarantee.
    """
    numpy_only = "import numpy as np\nfrom pathlib import Path\n"
    assert _unrecorded_third_party("pyflightstream.results.conditions", numpy_only) == set()

    # A recorded residual is admitted for ITS module and for no other.
    pandas_source = "import pandas as pd\n"
    assert _unrecorded_third_party("pyflightstream.results.tables", pandas_source) == set()
    assert _unrecorded_third_party("pyflightstream.results.conditions", pandas_source) == {"pandas"}
    xarray_source = "import xarray as xr\n"
    assert _unrecorded_third_party("pyflightstream.post.writers", xarray_source) == set()
    assert _unrecorded_third_party("pyflightstream.post.unsteady", xarray_source) == {"xarray"}

    # A fourth residual is refused wherever it lands.
    assert _unrecorded_third_party("pyflightstream.results.tables", "import polars\n") == {"polars"}

    # scipy, with and without its one-line justification.
    plain_scipy = "from scipy import integrate\n"
    assert _unrecorded_third_party("pyflightstream.post.reductions", plain_scipy) == {"scipy"}
    justified = (
        "# AD-06 scipy: the quadrature this reduction needs has no numpy form\n" + plain_scipy
    )
    assert _unrecorded_third_party("pyflightstream.post.reductions", justified) == set()

    # An import deferred into a function body is seen exactly the same.
    deferred = "def f():\n    import pandas as pd\n    return pd\n"
    assert _unrecorded_third_party("pyflightstream.post.reductions", deferred) == {"pandas"}

    # Internal and standard-library imports are not third party at all.
    internal = (
        "from __future__ import annotations\n"
        "import json\n"
        "from pyflightstream.results import parse_loads\n"
        "from pyflightstream import versions\n"
    )
    assert _unrecorded_third_party("pyflightstream.post.writers", internal) == set()


def test_the_import_closure_is_not_vacuous_and_follows_a_chain():
    """Floors on the walk, so a broken traversal is not a green verdict.

    Named modules rather than a count: a count reds on any unrelated edit
    one layer down, which teaches a maintainer to adjust a number without
    reading it.
    """
    closure = _internal_import_closure(_GOVERNED_ROOTS)
    for name in (
        "pyflightstream.results",
        "pyflightstream.results.tables",
        "pyflightstream.results.conditions",
        "pyflightstream.post",
        "pyflightstream.post.writers",
        "pyflightstream.post.reductions",
        "pyflightstream.post.unsteady",
    ):
        assert name in closure, f"{name} fell out of the closure; the walk is broken"
    # Depth: neither of these is imported by a package root, so seeing them
    # proves the walk followed an edge rather than listing its seeds.
    assert "pyflightstream.extras" in closure, (
        "reached only through results.tables, so its absence means the walk never left the roots"
    )
    assert "pyflightstream.script.solver_setup" in closure, (
        "reached only through post.writers, on the other root"
    )
    # And it stops at this package: a third-party name is never a module here.
    assert all(name.startswith("pyflightstream") for name in closure)


# --- PFS-2014.02: the six formats the classification owed a parser ---------
#
# Every fixture below is a REAL export off a licensed solver, captured by
# `scripts/capture_export_corpus.py` on a coarse generated NACA 0012 wing:
# five on 26.123 (build 8112026) on 2026-08-20 and two on 26.120 (build
# 7012026). None of them is synthetic and none of the assertions below is a
# shape the manual suggested.
#
# TWO OF THE FILES ARE DEGENERATE and they are kept deliberately, one as a
# case and one as a warning. `surface_sections_26.120.txt` cut a plane laid
# on a spanwise panel boundary, so it declares `Edges=0` and holds no row;
# `force_distributions_26.120.txt` was exported at iteration zero and holds
# none either. Both are complete files with correct headers and terminators,
# which is exactly the shape a parser passes against while never having read
# a row, so every format here is ALSO asserted against a file with rows in
# it, by count and by value.

FORCE_HEADER = "Boundary, X, Y, Z, Cx, Cy, Cz, Cxv, Cyv, Czv"
STREAMLINE_HEADER = "X, Y, Z, Mach, Cp_ref, vx, vy, vz, vtot, Cp"
SECTION_HEADER = (
    "Section_direction_value, X, Y, Z, nx, ny, nz, L, Cp, Mach, vx, vy, vz, vtot, "
    "Cp_ref, Theta, CF, Delta*, Delta, H"
)
SWEEP_HEADER = "AOA (deg), Beta (deg), Velocity (m/sec), Cx, Cy, Cz, CL, CDi, CDo, CMx, CMy, CMz"

#: The four text formats and the parser each is read by, for the guards that
#: apply to all of them (footer, concatenation, header pin, version check).
TEXT_EXPORTS = [
    ("force_distributions_26.123.txt", "parse_force_distributions"),
    ("off_body_streamlines_26.123.txt", "parse_off_body_streamlines"),
    ("all_surface_sections_26.123.txt", "parse_surface_sections"),
    ("sweeper_spreadsheet_26.123.txt", "parse_sweep_spreadsheet"),
]


def test_the_force_distribution_fixture_reads_every_panel():
    """96 panel rows off the real 26.123 export, checked by count and by value."""
    from pyflightstream.results import FORCE_DISTRIBUTION_COLUMNS, parse_force_distributions

    report = parse_force_distributions(
        read_fixture("force_distributions_26.123.txt"), requested_version="26.123"
    )
    assert report.columns == FORCE_DISTRIBUTION_COLUMNS
    assert report.count == 96, "the committed 26.123 export holds 96 panel rows"
    assert report.values.shape == (96, 10)
    assert report.boundary_indices.tolist() == [1] * 96
    # The first row, verbatim from the file.
    assert report.values[0][1] == pytest.approx(0.9665063514165755)
    assert report.values[0][3] == pytest.approx(-0.4665757602364896e-02)
    assert report.field("Cz")[0] == pytest.approx(-0.6270321115917074e-03)
    assert report.field("Cxv")[0] == pytest.approx(0.4707505061189517e-04)
    assert report.positions.shape == (96, 3)
    assert report.solution.angle_of_attack_deg == 4.0
    assert report.solution.sideslip_deg == 0.0
    assert report.solution.freestream_velocity_m_s == 30.0
    assert report.solution.solver_mode == "Steady"
    assert report.solution.current_iteration == 65
    assert report.solution.frame == "Reference"
    assert report.solution.reported_build == "8112026"
    assert report.force_units == "Coefficients"
    assert report.moment_units == "Coefficients"


def test_an_empty_force_distribution_is_reported_rather_than_refused():
    """The 26.120 capture ran at iteration zero: a complete file with no rows.

    It is also the file that made `delimited_table` the wrong helper for
    these formats: that one treats every dashed rule as a separator until it
    has a row, so a table with none never terminates for it and this
    complete export came back as "the file ends mid-table".
    """
    from pyflightstream.results import parse_force_distributions

    report = parse_force_distributions(read_fixture("force_distributions_26.120.txt"))
    assert report.count == 0
    assert report.values.shape == (0, 10), (
        "an empty table still has to know how many columns it does not have; a "
        "one-dimensional empty array cannot be indexed by column downstream"
    )
    assert report.solution.current_iteration == 0
    assert report.solution.reported_build == "7012026"


def test_the_streamline_fixture_reads_three_streamlines_by_their_markers():
    """Three streamlines of thirty points each, off the real 26.123 export."""
    from pyflightstream.results import OFF_BODY_STREAMLINE_COLUMNS, parse_off_body_streamlines

    report = parse_off_body_streamlines(
        read_fixture("off_body_streamlines_26.123.txt"), requested_version="26.123"
    )
    assert report.columns == OFF_BODY_STREAMLINE_COLUMNS
    assert report.declared_count == 3
    assert report.count == 3
    assert [line.index for line in report.streamlines] == [1, 2, 3]
    assert [line.points for line in report.streamlines] == [30, 30, 30]
    assert report.points == 90
    first = report.streamlines[0]
    # The seed point of streamline 1, verbatim from the file.
    assert first.positions[0].tolist() == pytest.approx([2.0, -1.0, 0.3])
    assert first.field("vtot")[0] == pytest.approx(0.2990135e02)
    assert first.field("Mach")[0] == pytest.approx(0.8786685e-01)
    assert first.values[-1][0] == pytest.approx(0.1382484e02)
    assert report.solution.solver_mode == "Steady"
    assert report.solution.reported_build == "8112026"


def test_the_streamline_point_count_is_recorded_verbatim_and_not_asserted():
    """The measured off-by-one, pinned as a measurement rather than assumed away.

    Every streamline of the observed export prints 31 and writes 30 rows.
    Nothing in the file or the manual settles what the extra one is, so the
    parser records the printed number and refuses to equate it with the row
    count: equating them would refuse every real export of this format. This
    test is the record of the measurement, and it goes red on the build that
    changes it, which is the point of writing a defect down rather than
    tolerating it silently.
    """
    from pyflightstream.results import parse_off_body_streamlines

    report = parse_off_body_streamlines(read_fixture("off_body_streamlines_26.123.txt"))
    for line in report.streamlines:
        assert line.declared_points == 31
        assert line.declared_points == line.points + 1, (
            f"streamline {line.index} declares {line.declared_points} points and holds "
            f"{line.points}. The one-row shortfall is what build 8112026 was measured "
            "doing on 2026-08-20; a different relation means the export changed, and "
            "what the printed number counts is a question to reopen rather than a "
            "number to adjust"
        )


@pytest.mark.parametrize(
    ("fixture", "edges", "build"),
    [
        ("all_surface_sections_26.123.txt", 12, "8112026"),
        ("surface_sections_26.120.txt", 0, "7012026"),
    ],
)
def test_one_parser_reads_both_surface_section_commands(fixture, edges, build):
    """The all-sections and the single-section exports share one format.

    Two observed files on two builds, one written by each command: same
    banner, same count label, same twenty-column header, same `Edges=` block
    structure. The zero-edge one is a real complete file whose cutting plane
    lay on a panel boundary, and it is reported as a section with no rows
    rather than refused.
    """
    from pyflightstream.results import SURFACE_SECTION_COLUMNS, parse_surface_sections

    report = parse_surface_sections(read_fixture(fixture))
    assert report.columns == SURFACE_SECTION_COLUMNS
    assert report.declared_count == 1
    assert report.count == 1
    section = report.sections[0]
    assert section.index == 1
    assert section.edges == edges
    assert section.count == edges
    assert section.values.shape == (edges, 20)
    assert report.points == edges
    assert report.solution.reported_build == build


def test_the_surface_section_fixture_with_rows_is_checked_by_value():
    """The twelve cut points of the 26.123 export, against the file itself."""
    from pyflightstream.results import parse_surface_sections

    section = parse_surface_sections(
        read_fixture("all_surface_sections_26.123.txt"), requested_version="26.123"
    ).sections[0]
    assert section.field("Cp")[0] == pytest.approx(-0.5171173e-01)
    assert section.field("Cp")[-1] == pytest.approx(-0.2291439e00)
    assert section.field("Cp_ref")[0] == pytest.approx(-0.5171173e-01)
    assert section.field("vtot")[0] == pytest.approx(0.3076049e02)
    assert section.field("Delta*")[0] == pytest.approx(0.5382381e-03)
    assert section.field("H")[0] == pytest.approx(0.1447456e01)
    assert section.positions[0].tolist() == pytest.approx([0.9665064, 0.5, -0.4665754e-02])
    # The section was cut at y = 0.5 m, off the panel boundary on purpose.
    assert set(section.field("Y").tolist()) == {0.5}


def test_the_sweep_fixture_reads_the_polar_the_solver_assembled():
    """Three sweep points off the real 26.123 sweeper export."""
    from pyflightstream.results import SWEEP_COLUMNS, parse_sweep_spreadsheet

    report = parse_sweep_spreadsheet(
        read_fixture("sweeper_spreadsheet_26.123.txt"), requested_version="26.123"
    )
    assert report.columns == SWEEP_COLUMNS
    assert report.points == 3
    assert report.values.shape == (3, 12)
    assert report.field("AOA (deg)").tolist() == [0.0, 2.0, 4.0]
    assert report.field("Beta (deg)").tolist() == [0.0, 0.0, 0.0]
    assert report.field("Velocity (m/sec)").tolist() == [30.0, 30.0, 30.0]
    assert report.field("CL").tolist() == pytest.approx([0.0, 0.1247, 0.2485])
    assert report.field("CDi").tolist() == pytest.approx([-0.0125, -0.0082, 0.0046])
    assert report.force_units == "Coefficients"
    # The solution block belongs to the LAST point solved, not to the sweep.
    assert report.solution.angle_of_attack_deg == 4.0
    assert report.solution.current_iteration == 90


def test_the_csv_fixture_reads_four_columns_that_no_header_names():
    """The header-less FEM csv, checked against the geometry that produced it.

    The column identification is the parser docstring's evidence, asserted
    here so it stays a measurement rather than a claim: seven chordwise node
    stations over a 1 m chord, seven spanwise stations over an 8 m span, the
    NACA 0012 ordinate at each, and a scalar that agrees with the Cp column
    of the surface-section export captured in the same run.
    """
    from pyflightstream.results import (
        SOLVER_ANALYSIS_CSV_COLUMNS,
        SOLVER_ANALYSIS_CSV_FIELD_UNSTATED,
        parse_solver_analysis_csv,
    )

    text = read_fixture("solver_analysis_26.123.csv")
    report = parse_solver_analysis_csv(text, field="cp-freestream")
    assert report.columns == SOLVER_ANALYSIS_CSV_COLUMNS == ("x", "y", "z", "scalar")
    assert report.count == 86
    assert report.values.shape == (86, 4)
    assert report.scalar_field == "CP-FREESTREAM", "the declared format is recorded upper cased"

    x, y, z = (report.positions[:, index] for index in range(3))
    assert sorted(set(np.round(x, 6).tolist())) == [
        0.0,
        0.066987,
        0.25,
        0.5,
        0.75,
        0.933013,
        1.0,
    ], "column 1 is X: the seven cosine-spaced chordwise node stations of that mesh"
    assert sorted(set(np.round(y, 6).tolist())) == [
        -4.0,
        -2.666667,
        -1.333333,
        0.0,
        1.333333,
        2.666667,
        4.0,
    ], "column 2 is Y: the seven spanwise node stations of an 8 m span"
    assert sorted(set(np.round(z[np.abs(x - 0.75) < 1e-9], 7).tolist())) == [
        -0.0312044,
        0.0312044,
    ], "column 3 is Z: plus and minus the NACA 0012 half-thickness at x/c = 0.75"
    assert float(np.abs(z).max()) == pytest.approx(0.0594075)
    # Column 4 against the section export of the same run, which read -0.2293
    # on the upper surface near x = 0.93 and -0.0512 on the lower.
    near = report.values[np.abs(report.values[:, 0] - 0.9330127) < 1e-6]
    assert len(near) == 14, "seven spanwise stations, upper and lower surface"
    assert float(near[:, 3].min()) == pytest.approx(-0.2293, abs=2e-3)
    assert float(near[:, 3].max()) == pytest.approx(-0.0512, abs=6e-3)

    unstated = parse_solver_analysis_csv(text)
    assert unstated.scalar_field == SOLVER_ANALYSIS_CSV_FIELD_UNSTATED == "UNSTATED", (
        "a word rather than an empty cell: an empty one reads back out of a csv as NaN"
    )


@pytest.mark.parametrize(
    ("fixture", "parser_name", "header", "moved"),
    [
        (
            "force_distributions_26.123.txt",
            "parse_force_distributions",
            FORCE_HEADER,
            "Boundary, X, Y, Z, Cx, Cy, Cz, Cyv, Cxv, Czv",
        ),
        (
            "off_body_streamlines_26.123.txt",
            "parse_off_body_streamlines",
            STREAMLINE_HEADER,
            "X, Y, Z, Mach, Cp, vx, vy, vz, vtot, Cp_ref",
        ),
        (
            "all_surface_sections_26.123.txt",
            "parse_surface_sections",
            SECTION_HEADER,
            SECTION_HEADER.replace("Cp, Mach", "Mach, Cp"),
        ),
        (
            "sweeper_spreadsheet_26.123.txt",
            "parse_sweep_spreadsheet",
            SWEEP_HEADER,
            SWEEP_HEADER.replace("CL, CDi", "CDi, CL"),
        ),
    ],
)
def test_a_reordered_header_is_refused_rather_than_read_by_position(
    fixture, parser_name, header, moved
):
    """The pin, and the reason it is a pin rather than a read.

    These layouts are the solver's, so two swapped column names mean the
    build reordered the numbers. Read by position, every value would come
    back under its neighbour's label and not one of them would look wrong.
    """
    import pyflightstream.results as results

    text = read_fixture(fixture)
    assert text.count(header) == 1, "the anchor this mutation rewrites must be present and unique"
    assert header != moved
    with pytest.raises(MalformedOutputError, match="fixed by the solver"):
        getattr(results, parser_name)(text.replace(header, moved))


@pytest.mark.parametrize(("fixture", "parser_name"), TEXT_EXPORTS)
def test_a_missing_software_footer_is_incomplete_output(fixture, parser_name):
    """The footer is structural in every text export here (FR-17)."""
    import pyflightstream.results as results

    text = read_fixture(fixture)
    assert "Software :" in text
    with pytest.raises(IncompleteOutputError, match="no software footer"):
        getattr(results, parser_name)(text[: text.index("Software :")])


@pytest.mark.parametrize(("fixture", "parser_name"), TEXT_EXPORTS)
def test_two_concatenated_exports_are_refused_by_every_new_parser(fixture, parser_name):
    """A second complete export after the first is not silently ignored."""
    import pyflightstream.results as results

    text = read_fixture(fixture)
    with pytest.raises(MalformedOutputError, match="more than one complete export"):
        getattr(results, parser_name)(text + text)


@pytest.mark.parametrize(("fixture", "parser_name"), TEXT_EXPORTS)
def test_the_new_parsers_cross_check_the_build_they_were_asked_for(fixture, parser_name):
    """FR-18 on the four formats that print a footer to check against."""
    import pyflightstream.results as results

    parser = getattr(results, parser_name)
    text = read_fixture(fixture)
    with warnings.catch_warnings():
        warnings.simplefilter("error", VersionMismatchWarning)
        parser(text, requested_version="26.123")
    with pytest.raises(VersionMismatchWarning, match="the wrong executable ran"):
        with warnings.catch_warnings():
            warnings.simplefilter("error", VersionMismatchWarning)
            parser(text, requested_version="26.120")


def test_a_streamline_count_the_file_does_not_hold_raises():
    """Declared versus written, raising rather than returning fewer (FR-17)."""
    from pyflightstream.results import parse_off_body_streamlines

    text = read_fixture("off_body_streamlines_26.123.txt")
    anchor = "Number of Off-body Streamlines:             3"
    assert text.count(anchor) == 1
    with pytest.raises(IncompleteOutputError, match="declares 4 streamline"):
        parse_off_body_streamlines(text.replace(anchor, anchor.replace("3", "4")))


def test_a_section_count_the_file_does_not_hold_raises():
    """The same rule on the other block-structured format."""
    from pyflightstream.results import parse_surface_sections

    text = read_fixture("all_surface_sections_26.123.txt")
    anchor = "Number of Surface Sections:                 1"
    assert text.count(anchor) == 1
    with pytest.raises(IncompleteOutputError, match="declares 2 surface section"):
        parse_surface_sections(text.replace(anchor, anchor.replace("1", "2")))


def test_a_section_that_lost_a_row_it_declared_raises():
    """`Edges=N` and the row count are equal in every observed export."""
    from pyflightstream.results import parse_surface_sections

    text = read_fixture("all_surface_sections_26.123.txt")
    assert text.count("Edges=12") == 1
    with pytest.raises(IncompleteOutputError, match="declares 13 edge"):
        parse_surface_sections(text.replace("Edges=12", "Edges=13"))


def test_streamlines_numbered_out_of_order_are_refused():
    """A gap or a repeat means a block was lost or two exports interleaved."""
    from pyflightstream.results import parse_off_body_streamlines

    text = read_fixture("off_body_streamlines_26.123.txt")
    assert text.count("Streamline 2") == 1
    with pytest.raises(MalformedOutputError, match="numbers its streamlines 3 where 2"):
        parse_off_body_streamlines(text.replace("Streamline 2", "Streamline 3"))


def test_each_block_keeps_its_own_declared_count_and_not_its_successor_s():
    """The handover this parser's ordering exists to prevent, made visible.

    The count of block N+1 is printed BEFORE the marker that closes block N,
    so a parser that closes on the marker after consuming the count stamps
    every block with its successor's number. All three streamlines of the
    real export declare 31, which would hide it, so the fixture is rewritten
    to give the second block a count of its own.
    """
    from pyflightstream.results import parse_off_body_streamlines

    lines = read_fixture("off_body_streamlines_26.123.txt").splitlines()
    marker = lines.index("Streamline 2")
    assert lines[marker - 1].strip() == "31"
    lines[marker - 1] = "        44"
    report = parse_off_body_streamlines("\n".join(lines) + "\n")
    assert [line.declared_points for line in report.streamlines] == [31, 44, 31], (
        "block 1 must keep the 31 printed above its own marker; reading 44 there "
        "means the counts were handed over one block late"
    )


def test_a_data_row_before_any_block_marker_is_refused():
    """A row outside a block belongs to no streamline at all."""
    from pyflightstream.results import parse_off_body_streamlines

    lines = read_fixture("off_body_streamlines_26.123.txt").splitlines()
    marker = lines.index("Streamline 1")
    lines.insert(marker, lines[marker + 1])
    with pytest.raises(MalformedOutputError, match="before any 'Streamline N' marker"):
        parse_off_body_streamlines("\n".join(lines) + "\n")


def test_a_block_marker_with_no_count_above_it_is_refused():
    """Every block of both formats is introduced by its own count line."""
    from pyflightstream.results import parse_off_body_streamlines, parse_surface_sections

    lines = read_fixture("off_body_streamlines_26.123.txt").splitlines()
    del lines[lines.index("Streamline 1") - 1]
    with pytest.raises(MalformedOutputError, match="no point count printed above it"):
        parse_off_body_streamlines("\n".join(lines) + "\n")

    sections = read_fixture("all_surface_sections_26.123.txt")
    with pytest.raises(MalformedOutputError, match="no 'Edges=' line above it"):
        parse_surface_sections(sections.replace("Edges=12\n", ""))


def test_a_later_block_marker_without_its_own_count_is_refused_too():
    """The half of that guard the first block cannot exercise.

    FOUND BY THE ADVERSARIAL PASS of this item, not by review. Deleting the
    count above streamline ONE is caught by any implementation, because
    nothing has been read yet; deleting the one above streamline TWO is
    caught only if the count is CLEARED when its own block consumes it. A
    parser that leaves it standing gives block two block one's number in
    silence, and 31 is as plausible a point count for the second streamline
    as it is for the first.
    """
    from pyflightstream.results import parse_off_body_streamlines

    lines = read_fixture("off_body_streamlines_26.123.txt").splitlines()
    marker = lines.index("Streamline 2")
    assert lines[marker - 1].strip() == "31"
    del lines[marker - 1]
    with pytest.raises(MalformedOutputError, match="no point count printed above it"):
        parse_off_body_streamlines("\n".join(lines) + "\n")


def _two_sections(text: str) -> str:
    """Duplicate the observed section block, so a second section exists.

    DERIVED FROM THE OBSERVED FILE rather than invented: the capture run cut
    one section, so the committed export has one block and the multi-block
    machinery (the per-section edge count, the section numbering, the key
    column of the table) has nothing in it to act on. Every byte here comes
    from the real export; what is synthetic is the REPETITION, which is the
    one thing the format's own structure already tells us how to do.
    """
    lines = text.splitlines()
    start = lines.index("Edges=12")
    block = lines[start : start + 14]
    assert block[1] == "Surface cross-section 1"
    assert len([line for line in block if "," in line]) == 12
    second = [block[0], "Surface cross-section 2", *block[2:]]
    lines[start + 14 : start + 14] = second
    return (
        "\n".join(lines).replace(
            "Number of Surface Sections:                 1",
            "Number of Surface Sections:                 2",
        )
        + "\n"
    )


def test_two_sections_each_keep_their_own_edge_count_and_number():
    """The multi-block path, on a text derived from the observed export."""
    from pyflightstream.results import parse_surface_sections

    report = parse_surface_sections(_two_sections(read_fixture("all_surface_sections_26.123.txt")))
    assert report.declared_count == 2
    assert [(section.index, section.edges, section.count) for section in report.sections] == [
        (1, 12, 12),
        (2, 12, 12),
    ]
    assert report.points == 24


def test_a_second_section_without_its_own_edge_count_is_refused():
    """The section half of the cleared-count rule (see the streamline one)."""
    from pyflightstream.results import parse_surface_sections

    lines = _two_sections(read_fixture("all_surface_sections_26.123.txt")).splitlines()
    marker = lines.index("Surface cross-section 2")
    assert lines[marker - 1] == "Edges=12"
    del lines[marker - 1]
    with pytest.raises(MalformedOutputError, match="no 'Edges=' line above it"):
        parse_surface_sections("\n".join(lines) + "\n")


def test_a_second_section_that_declares_a_different_edge_count_is_checked_alone():
    """Each block is measured against ITS OWN count, not against its neighbour's.

    The count of block N+1 is printed before the marker that closes block N,
    so a parser that closes on the marker after consuming the count stamps
    every block with its successor's number. Giving the second section an
    edge count that does not match its rows is what makes that visible: the
    first section must still pass and the second must not.
    """
    from pyflightstream.results import parse_surface_sections

    text = _two_sections(read_fixture("all_surface_sections_26.123.txt"))
    lines = text.splitlines()
    marker = lines.index("Surface cross-section 2")
    lines[marker - 1] = "Edges=11"
    with pytest.raises(IncompleteOutputError, match="section 2 .* declares 11 edge"):
        parse_surface_sections("\n".join(lines) + "\n")


def test_a_short_row_is_incomplete_and_a_wide_row_is_a_changed_layout():
    """The two arities fail differently because they mean different things."""
    from pyflightstream.results import parse_force_distributions

    text = read_fixture("force_distributions_26.123.txt")
    row = text.splitlines()[29]
    assert text.count(row) == 1 and row.strip().startswith("1,")
    with pytest.raises(IncompleteOutputError, match="ends part way through a row"):
        parse_force_distributions(text.replace(row, row.rsplit(",", 1)[0]))
    with pytest.raises(MalformedOutputError, match="the table layout changed"):
        parse_force_distributions(text.replace(row, row + ", 0.0"))


def test_a_cell_that_is_not_a_number_names_the_row_and_the_column():
    """Didactic policy: the message says which value of which column."""
    from pyflightstream.results import parse_force_distributions

    text = read_fixture("force_distributions_26.123.txt")
    row = text.splitlines()[29]
    broken = row.replace("0.8734723819011840E-04", "Coefficients")
    assert broken != row
    with pytest.raises(MalformedOutputError, match=r"row 1 .* in column 'Cx'"):
        parse_force_distributions(text.replace(row, broken))


def test_a_boundary_index_that_is_not_a_whole_number_is_refused():
    """The Boundary column indexes the mesh boundaries, counting from one."""
    from pyflightstream.results import parse_force_distributions

    text = read_fixture("force_distributions_26.123.txt")
    row = text.splitlines()[29]
    for bad in ("1.5,", "0,", "-1,"):
        with pytest.raises(MalformedOutputError, match="whole boundary index"):
            parse_force_distributions(text.replace(row, row.replace("1,", bad, 1)))


def test_no_new_parser_reads_another_export_as_its_own():
    """The whole confusion matrix, on every committed export of this package.

    THE CLASS OF DEFECT THIS PREVENTS HAS HAPPENED HERE: the committed probe
    fixture parsed cleanly as an unsteady plot history and returned twelve
    "time steps" that were twelve positions in space. Every one of these
    formats is a comma table of numbers under a header, so nothing but the
    anchors distinguishes them, and an anchor is only a distinguisher if it
    is measured against the other files.

    The diagonal must be the only thing that reads, and each refusal must be
    a catalogued class (FR-39) rather than an IndexError from reading a row
    of the wrong width.
    """
    from pyflightstream._errors import PyflightstreamError
    from pyflightstream.results import (
        parse_force_distributions,
        parse_off_body_streamlines,
        parse_solver_analysis_csv,
        parse_surface_sections,
        parse_sweep_spreadsheet,
    )

    owner = {
        "force_distributions_26.123.txt": parse_force_distributions,
        "off_body_streamlines_26.123.txt": parse_off_body_streamlines,
        "all_surface_sections_26.123.txt": parse_surface_sections,
        "sweeper_spreadsheet_26.123.txt": parse_sweep_spreadsheet,
        "solver_analysis_26.123.csv": parse_solver_analysis_csv,
    }
    strangers = ["loads_steady_26.120.txt", "probe_points_26.120.txt"]
    checked = 0
    for fixture in [*owner, *strangers]:
        text = read_fixture(fixture)
        for name, parser in owner.items():
            if name == fixture:
                parser(text)
                continue
            with pytest.raises(PyflightstreamError):
                parser(text)
            checked += 1
    assert checked == 7 * 5 - 5, f"the matrix covered {checked} off-diagonal cells"


def test_the_csv_refuses_a_labelled_text_export():
    """Four bare columns of numbers, or it is a different export entirely."""
    from pyflightstream.results import parse_solver_analysis_csv

    with pytest.raises(MalformedOutputError, match="software footer"):
        parse_solver_analysis_csv(read_fixture("loads_steady_26.120.txt"))


def test_the_csv_refuses_a_row_that_is_not_four_numbers():
    """Including a header row, which this export never writes."""
    from pyflightstream.results import parse_solver_analysis_csv

    text = read_fixture("solver_analysis_26.123.csv")
    with pytest.raises(MalformedOutputError, match="not a solver-printed number"):
        parse_solver_analysis_csv("x, y, z, Cp\n" + text)
    with pytest.raises(MalformedOutputError, match="the table layout changed"):
        parse_solver_analysis_csv("1.0, 2.0, 3.0, 4.0, 5.0\n")
    # NOT "ends part way through a row": this export has no header to be short
    # of and no footer to be truncated before, so the shared mid-write sentence
    # would be a diagnosis the format cannot support. An api-designer pass on
    # 2026-08-20 found the shared refusal naming a header for a format whose
    # two explanations both shout that it writes none. Line 1716 keeps the old
    # wording deliberately: that format HAS a header and a footer.
    with pytest.raises(IncompleteOutputError, match="NAMES none of its columns"):
        parse_solver_analysis_csv("1.0, 2.0, 3.0\n")
    with pytest.raises(IncompleteOutputError, match="holds no row at all"):
        parse_solver_analysis_csv("   \n\n")
    with pytest.raises(MalformedOutputError, match="declared as blank"):
        parse_solver_analysis_csv(text, field="   ")


def test_the_owed_tranche_is_the_boundary_layer_profile_alone():
    """One format still owed, and its note says why the SOLVER is the reason.

    That distinction is the whole content of the entry: every other owed
    format was owed a capture, and this one has had two licensed runs spent
    on it. A note reading "no observed export captured" would send the next
    reader to spend a third.
    """
    from pyflightstream.results import EXPORT_CONVERSIONS, EXPORT_OWED

    owed = {
        command: entry
        for command, entry in EXPORT_CONVERSIONS.items()
        if entry.verdict == EXPORT_OWED
    }
    assert set(owed) == {"EXPORT_BL_VELOCITY_PROFILE"}
    note = owed["EXPORT_BL_VELOCITY_PROFILE"].note
    assert "never been observed" in note
    assert "RPT-027" in note, "the note points at the report that measured the cause"
    assert "modal window" in note
    assert "1800" in note and "240" in note, "both bounded runs are named"


def test_every_default_set_export_now_has_a_parser_and_a_conversion():
    """The acceptance of PFS-2014.02, read off the classification itself.

    Default set means: not excluded, and not one of the two entries that
    export nothing. Every member of it but one names a parser, that parser
    resolves to a callable, and the one that does not is the format the
    solver will not write unattended.
    """
    import importlib

    from pyflightstream.results import (
        EXPORT_CONVERSIONS,
        EXPORT_EXCLUDED,
        EXPORT_NOT_AN_EXPORT,
        EXPORT_PARSED,
    )

    default_set = {
        command: entry
        for command, entry in EXPORT_CONVERSIONS.items()
        if entry.verdict not in (EXPORT_EXCLUDED, EXPORT_NOT_AN_EXPORT)
    }
    assert len(default_set) == 11, (
        f"the default set resolved {len(default_set)} command(s); eighteen exports "
        "less five excluded and two that export nothing is eleven"
    )
    parsed = {
        command: entry.parser
        for command, entry in default_set.items()
        if entry.verdict == EXPORT_PARSED
    }
    assert len(parsed) == 10, f"ten of the eleven are parsed today, not {len(parsed)}"
    for command, dotted in parsed.items():
        assert dotted is not None
        module_name, _, attribute = dotted.rpartition(".")
        assert callable(getattr(importlib.import_module(module_name), attribute, None)), (
            f"{command} claims {dotted!r} reads it"
        )
    # Both surface-section commands are read by one parser, on the evidence
    # of two observed files that carry the same format.
    assert (
        parsed["EXPORT_SURFACE_SECTIONS"]
        == parsed["EXPORT_ALL_SURFACE_SECTIONS"]
        == "pyflightstream.results.parse_surface_sections"
    )


def test_every_new_public_name_is_exported():
    """A parser reachable only by its dotted path is not part of the API."""
    from pyflightstream import results

    for name in (
        "ExportSolution",
        "FORCE_DISTRIBUTION_COLUMNS",
        "ForceDistributionReport",
        "OFF_BODY_STREAMLINE_COLUMNS",
        "OffBodyStreamline",
        "OffBodyStreamlinesReport",
        "SOLVER_ANALYSIS_CSV_COLUMNS",
        "SOLVER_ANALYSIS_CSV_FIELD_UNSTATED",
        "SURFACE_SECTION_COLUMNS",
        "SWEEP_COLUMNS",
        "SolverAnalysisCsvReport",
        "SurfaceSection",
        "SurfaceSectionsReport",
        "SweepSpreadsheetReport",
        "parse_force_distributions",
        "parse_off_body_streamlines",
        "parse_solver_analysis_csv",
        "parse_surface_sections",
        "parse_sweep_spreadsheet",
    ):
        assert name in results.__all__, f"{name} is public and missing from __all__"
        assert hasattr(results, name)


def _assert_same_report(under_crlf, under_lf, parser_name, fixture_name):
    """Compare two parsed reports field by field, arrays included.

    A plain ``==`` on these records is not merely inconvenient, it is
    WRONG in the direction that matters: the reports hold numpy arrays,
    so dataclass equality raises ``ValueError: the truth value of an
    array ... is ambiguous``. Found by writing the naive version first
    and watching it fail; a version that had caught that exception and
    called it a difference, or swallowed it and called it a match, would
    have reported on nothing.
    """
    import dataclasses

    assert type(under_crlf) is type(under_lf), (
        f"{parser_name} returned different TYPES for {fixture_name} under the two "
        f"line endings: {type(under_crlf).__name__} and {type(under_lf).__name__}"
    )
    fields = dataclasses.fields(under_crlf)
    assert fields, f"{type(under_crlf).__name__} has no fields, so this compared nothing"
    for field in fields:
        left = getattr(under_crlf, field.name)
        right = getattr(under_lf, field.name)
        _assert_same_value(left, right, f"{parser_name}.{field.name}", fixture_name)


def _assert_same_value(left, right, where, fixture_name):
    """Compare two parsed values, descending into records and sequences.

    THE RECURSION IS NOT GENERALITY FOR ITS OWN SAKE. Two of these
    reports hold a TUPLE OF RECORDS, one per streamline and one per
    surface section, and each of those records holds the array. A
    comparison that stopped at the report's own fields would hit the same
    ambiguous-array `ValueError` one level down, which is exactly what it
    did before this function existed.
    """
    import dataclasses

    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        assert np.array_equal(left, right, equal_nan=True), (
            f"{where} is a different array for {fixture_name} under CRLF"
        )
        return
    if dataclasses.is_dataclass(left) and not isinstance(left, type):
        assert type(left) is type(right), (
            f"{where} is {type(left).__name__} under CRLF and "
            f"{type(right).__name__} under LF for {fixture_name}"
        )
        for field in dataclasses.fields(left):
            _assert_same_value(
                getattr(left, field.name),
                getattr(right, field.name),
                f"{where}.{field.name}",
                fixture_name,
            )
        return
    if isinstance(left, (list, tuple)) and not isinstance(left, str):
        assert len(left) == len(right), (
            f"{where} holds {len(left)} entries under CRLF and {len(right)} under LF "
            f"for {fixture_name}"
        )
        for position, (one, other) in enumerate(zip(left, right, strict=True)):
            _assert_same_value(one, other, f"{where}[{position}]", fixture_name)
        return
    assert left == right, (
        f"{where} differs for {fixture_name} under CRLF: {left!r} against {right!r}. "
        "A trailing carriage return on the last column of every row is the usual "
        "shape of this"
    )


def test_every_new_parser_reads_the_line_ending_the_solver_actually_writes():
    """The gap the fixture pin creates, closed by construction.

    `tests/test_matrix.py` pins `tests/fixtures/** text eol=lf`, so every
    fixture is LF in the index AND LF in the checkout, which is what
    makes a case read the same file on every platform. The seven
    captures this release added arrived from the solver as CRLF and were
    normalised on the way in, exactly as the pin intends.

    The consequence is a coverage hole nobody would see: tier 1 then
    exercises a line ending the solver never writes on the machine these
    parsers run on. Storing a second CRLF copy of each fixture would
    close it and would defeat the pin, so the variant is CONSTRUCTED
    here, which is the remedy the pin's own docstring names for the two
    cases that failed this way on 2026-08-19.

    What this asserts is EQUALITY of the parsed result, not merely that
    the CRLF form parses. A parser that read CRLF into a trailing `\r`
    on the last column of every row would still "parse"; it would return
    strings nobody can compare and floats nobody can subtract.

    WHERE THE ROBUSTNESS ACTUALLY LIVES, measured by mutation rather than
    assumed, because the answer was not the obvious one. Rewriting every
    `.splitlines()` in the parsers to `.split(chr(10))`, which is the
    textbook shape of this defect and leaves the carriage return on every
    row, SURVIVES this case. So does removing the per-cell `.strip()`
    from the row split. The property is over-determined: `float()`
    absorbs a trailing carriage return on its own, so a numeric column
    survives two independent mechanisms failing.

    What this case DOES deny is a mutant on the column HEADER, which is
    compared as text and never passes through a numeric conversion:
    dropping the `.strip()` where the pinned columns are read makes the
    CRLF file name its last column `Czv\r` and the LF file name it
    `Czv`, and this case fails naming the field. That is the honest
    scope of the guard, and it is written here so a reader does not
    mistake it for a tight coupling to `splitlines()`.
    """
    cases = (
        ("force_distributions_26.123.txt", parse_force_distributions),
        ("off_body_streamlines_26.123.txt", parse_off_body_streamlines),
        ("all_surface_sections_26.123.txt", parse_surface_sections),
        ("surface_sections_26.120.txt", parse_surface_sections),
        ("sweeper_spreadsheet_26.123.txt", parse_sweep_spreadsheet),
        ("solver_analysis_26.123.csv", parse_solver_analysis_csv),
    )
    for name, parser in cases:
        text = read_fixture(name)
        # THE DECODED TEXT CANNOT CARRY A CARRIAGE RETURN, whatever is on
        # disk: `read_fixture` opens in text mode with universal newlines,
        # so a CRLF file always decodes to bare line feeds. The first
        # version of this case asserted that the decoded text held no
        # carriage return and called it
        # proof that the fixture pin had normalised the file. It proved only
        # that Python decodes, and it could not have failed. What is
        # asserted instead is that the two forms are genuinely different
        # STRINGS, which is what makes the comparison below a comparison
        # rather than a file against itself. Whether the COMMITTED BYTES are
        # LF is a different question with its own guard, in
        # tests/test_matrix.py, which reads the git attributes.
        crlf = text.replace("\n", "\r\n")
        assert crlf != text, f"{name} has no line breaks at all, so nothing was varied"
        _assert_same_report(parser(crlf), parser(text), parser.__name__, name)
