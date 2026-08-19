"""Tier 1: anchor-based parsing primitives and the loads parser.

Fixtures mirror the structure of real 26.120 (build 7012026) output
files from a local run; values, paths, and surface names are
synthetic.
"""

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
    assert resolved >= 4, (
        f"only {resolved} parsed verdict(s) were resolved; four exports have "
        "parsers today and this walk is what proves the claim rather than "
        "repeating it"
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
