"""Tier 1: the wall-time cost view over run manifests (PFS-2018.02).

Pipeline role: quality gate on :mod:`pyflightstream.qa.cost`, the reader
that turns the wall time FR-19 already records in ``runs.json`` into a
table two solver builds can be compared in.

The reproduction the item exists for, as a user would type it::

    from pyflightstream.qa.cost import cost_view

    view = cost_view("runs/my-campaign")
    for row in view.rows():
        print(row)

Before this module existed nothing in the package could answer it:
``results.tables.run_table`` carries no ``fs_exe_sha256`` column and maps
a missing ``wall_time_s`` to ``math.nan``, which is a number, and the
acceptance sentence for this item says absence must not be readable as
zero or as anything else arithmetic.

Nothing here runs a solver. Every fixture is a synthetic manifest, which
is what makes the reader testable without a licensed seat; the real
cross-build numbers are a separate, licensed step.
"""

from __future__ import annotations

import ast
import math
import re
from pathlib import Path

import pytest
import yaml

from pyflightstream.exceptions import PyflightstreamError
from pyflightstream.qa.cli import main
from pyflightstream.qa.cost import (
    BuildKey,
    CostView,
    cost_rows,
    cost_view,
)
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.physics import PHYSICS_SCHEMA, read_physics_report
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Two executables that report the same vendor build string. The pair is
#: the whole reason the column key is (fs_build, fs_exe_sha256) and not
#: fs_build alone: a hotfix rebuilt from the same source tag prints the
#: same number and is a different program.
SHA_A = "a" * 64
SHA_B = "b" * 64


def _record(
    run_id: str,
    *,
    sim_id: str = "SIM-01",
    alpha_deg: float = 2.0,
    fs_build: str | None = "2122026",
    fs_exe_sha256: str | None = SHA_A,
    wall_time_s: float | None = 40.0,
    status: RunStatus = RunStatus.CONVERGED,
) -> RunRecord:
    """One synthetic manifest record; only the cost fields vary."""
    return RunRecord(
        run_id=run_id,
        sim_id=sim_id,
        point={"alpha_deg": alpha_deg},
        fs_version_requested="26.120",
        fs_build=fs_build,
        fs_exe_sha256=fs_exe_sha256,
        package_version="0.8.0.dev0",
        script_sha256="0" * 64,
        raw_flag=False,
        status=status,
        wall_time_s=wall_time_s,
    )


def _parse_printed_table(block: str) -> list[dict[str, str]]:
    """Read the CLI's space-padded table back into label-keyed rows.

    Columns are resolved by their HEADING, never by position: the order
    of the build columns is the renderer's choice and no test here may
    depend on it.
    """
    lines = [line for line in block.splitlines() if line.strip()]
    headings = re.split(r"\s{2,}", lines[0].strip())
    rows = []
    for line in lines[1:]:
        cells = re.split(r"\s{2,}", line.strip())
        assert len(cells) == len(headings), f"row {line!r} does not fit {headings}"
        rows.append(dict(zip(headings, cells, strict=True)))
    return rows


def _campaign(tmp_path: Path, records: list[RunRecord]) -> Path:
    """A real campaign root carrying those records in ``runs.json``."""
    workspace = CampaignWorkspace.init(tmp_path / "campaign")
    for record in records:
        workspace.append_record(record)
    return workspace.root


def test_wall_time_is_reported_per_sim_and_point():
    """One row per (sim, point); the cell carries the recorded seconds."""
    view = cost_view(
        [
            _record("r1", sim_id="SIM-01", alpha_deg=0.0, wall_time_s=31.0),
            _record("r2", sim_id="SIM-01", alpha_deg=4.0, wall_time_s=44.5),
            _record("r3", sim_id="SIM-02", alpha_deg=0.0, wall_time_s=61.0),
        ]
    )
    keyed = {(point.sim_id, point.point["alpha_deg"]): point for point in view.points}
    assert set(keyed) == {("SIM-01", 0.0), ("SIM-01", 4.0), ("SIM-02", 0.0)}
    build = view.builds[0]
    assert view.wall_time_s(keyed[("SIM-01", 0.0)], build) == pytest.approx(31.0)
    assert view.wall_time_s(keyed[("SIM-01", 4.0)], build) == pytest.approx(44.5)
    assert view.wall_time_s(keyed[("SIM-02", 0.0)], build) == pytest.approx(61.0)


def test_an_untimed_record_is_absent_and_never_zero():
    """The acceptance's negative clause, asserted as a negative.

    A manifest written before the field existed, or by a run that died
    before the timer stopped, carries ``wall_time_s: null``. Reading
    that as 0.0 makes the build look infinitely fast; reading it as
    ``math.nan`` makes it a number that propagates through any sum a
    caller writes. It is neither: it is absent.
    """
    view = cost_view([_record("r1", wall_time_s=None)])
    point, build = view.points[0], view.builds[0]
    cell = view.cell(point, build)

    assert cell.wall_time_s is None
    assert cell.absent is True
    assert cell.recorded is True, "the RUN is recorded; only its wall time is not"
    assert cell.run_count == 1

    value = view.rows()[0][build.label]
    assert value is None
    assert value != 0
    assert not isinstance(value, float), "absence must not be a float, nan included"

    long_form = cost_rows([_record("r1", wall_time_s=None)])[0]
    assert long_form["wall_time_s"] is None
    absent = long_form["wall_time_s"]
    assert not (isinstance(absent, float) and math.isnan(absent)), "nan is a number"


def test_two_executables_sharing_a_build_string_are_two_columns():
    """The column key is the PAIR, so a rebuild is not merged away."""
    view = cost_view(
        [
            _record("r1", fs_build="2122026", fs_exe_sha256=SHA_A, wall_time_s=40.0),
            _record("r2", fs_build="2122026", fs_exe_sha256=SHA_B, wall_time_s=52.0),
        ]
    )
    assert len(view.builds) == 2, (
        "two executables reporting the same vendor build string are two "
        "columns; merging them hides exactly the regression this view exists "
        "to show"
    )
    assert {build.fs_exe_sha256 for build in view.builds} == {SHA_A, SHA_B}
    assert len({build.label for build in view.builds}) == 2, "column labels must be distinct"


def test_a_column_is_resolved_by_its_label_and_maps_back_to_its_build():
    """Labels and meanings are the contract; the sequence is not."""
    view = cost_view(
        [
            _record("r1", fs_build="2122026", fs_exe_sha256=SHA_A),
            _record("r2", fs_build="2900000", fs_exe_sha256=SHA_B),
        ]
    )
    labels = {build.label for build in view.builds}
    row = view.rows()[0]
    assert set(row) == {"sim_id", "point"} | labels, (
        "every column of the pivot is either a fixed identity column or one "
        "build label; a reader resolves a column by its label"
    )
    for label in labels:
        resolved = view.build(label)
        assert isinstance(resolved, BuildKey)
        assert resolved.label == label
        assert resolved.fs_build in {"2122026", "2900000"}
        assert resolved.fs_exe_sha256 in {SHA_A, SHA_B}


def test_the_long_form_carries_fs_build_and_fs_exe_sha256_as_columns():
    """The acceptance names both fields; the long form spells them."""
    rows = cost_rows([_record("r1"), _record("r2", fs_exe_sha256=SHA_B)])
    assert [row["run_id"] for row in rows] == ["r1", "r2"], "manifest order is evidence order"
    for row in rows:
        assert set(row) == {
            "run_id",
            "sim_id",
            "point",
            "fs_build",
            "fs_exe_sha256",
            "status",
            "wall_time_s",
        }
    assert rows[0]["fs_exe_sha256"] == SHA_A
    assert rows[1]["fs_exe_sha256"] == SHA_B, "the long form carries the FULL hash, not a prefix"


def test_two_builds_of_the_same_points_are_comparable():
    """The comparison a slower build has to show up in."""
    view = cost_view(
        [
            _record("b1", alpha_deg=0.0, fs_exe_sha256=SHA_A, wall_time_s=10.0),
            _record("b2", alpha_deg=4.0, fs_exe_sha256=SHA_A, wall_time_s=20.0),
            _record("c1", alpha_deg=0.0, fs_exe_sha256=SHA_B, wall_time_s=15.0),
            _record("c2", alpha_deg=4.0, fs_exe_sha256=SHA_B, wall_time_s=30.0),
        ]
    )
    baseline = next(build for build in view.builds if build.fs_exe_sha256 == SHA_A)
    candidate = next(build for build in view.builds if build.fs_exe_sha256 == SHA_B)
    comparison = view.compare(baseline, candidate)

    assert len(comparison.paired) == 2
    assert comparison.unpaired == ()
    assert comparison.baseline_total_s == pytest.approx(30.0)
    assert comparison.candidate_total_s == pytest.approx(45.0)
    assert comparison.ratio == pytest.approx(1.5), "the candidate is half again slower"
    assert all(pair.ratio == pytest.approx(1.5) for pair in comparison.paired)


def test_a_point_timed_on_only_one_build_is_unpaired_and_left_out_of_the_totals():
    """A total over two different sets of work is not a comparison."""
    view = cost_view(
        [
            _record("b1", alpha_deg=0.0, fs_exe_sha256=SHA_A, wall_time_s=10.0),
            _record("b2", alpha_deg=4.0, fs_exe_sha256=SHA_A, wall_time_s=99.0),
            _record("c1", alpha_deg=0.0, fs_exe_sha256=SHA_B, wall_time_s=12.0),
            _record("c2", alpha_deg=4.0, fs_exe_sha256=SHA_B, wall_time_s=None),
        ]
    )
    baseline = next(build for build in view.builds if build.fs_exe_sha256 == SHA_A)
    candidate = next(build for build in view.builds if build.fs_exe_sha256 == SHA_B)
    comparison = view.compare(baseline, candidate)

    assert [pair.point.point["alpha_deg"] for pair in comparison.paired] == [0.0]
    assert [point.point["alpha_deg"] for point in comparison.unpaired] == [4.0]
    assert comparison.baseline_total_s == pytest.approx(10.0), (
        "99.0 s was measured on the baseline alone; adding it to the baseline "
        "total while the candidate has nothing there invents a speed-up"
    )
    assert comparison.candidate_total_s == pytest.approx(12.0)


def test_repeated_runs_of_one_point_are_averaged_and_stay_countable():
    """A re-run is a second sample, not a silent overwrite."""
    view = cost_view(
        [
            _record("r1", wall_time_s=10.0),
            _record("r2", wall_time_s=20.0),
        ]
    )
    cell = view.cell(view.points[0], view.builds[0])
    assert cell.samples == (10.0, 20.0)
    assert cell.run_count == 2
    assert cell.wall_time_s == pytest.approx(15.0)


def test_a_failed_run_is_counted_so_its_time_is_not_read_as_a_solution():
    """Time to failure is time, and it is not the time to an answer."""
    view = cost_view(
        [
            _record("r1", wall_time_s=10.0, status=RunStatus.CONVERGED),
            _record("r2", wall_time_s=2.0, status=RunStatus.FAILED_EXECUTION),
        ]
    )
    cell = view.cell(view.points[0], view.builds[0])
    assert cell.run_count == 2
    assert cell.failed_count == 1, (
        "a failed run is kept, because dropping evidence silently is worse "
        "than reporting it with a count beside it"
    )


def test_an_unrecorded_build_field_is_labelled_rather_than_guessed():
    """A manifest written before the build fields is still a column."""
    view = cost_view([_record("r1", fs_build=None, fs_exe_sha256=None)])
    label = view.builds[0].label
    assert "unrecorded-build" in label and "unrecorded-exe" in label, label


def test_every_run_status_is_deliberately_classified_as_failed_or_not():
    """A status added to the enum must not land in "not failed" by silence.

    ``_FAILED_STATUSES`` is derived from the ``FAILED_`` prefix. That is
    the right default and it has one hole: a future terminal status
    named otherwise, ``ABORTED_BY_TIMEOUT`` say, would be counted as a
    solution. This pins the complement, so the hole fails a test rather
    than a report.
    """
    from pyflightstream.qa.cost import _FAILED_STATUSES

    assert set(RunStatus) - _FAILED_STATUSES == {
        RunStatus.CONVERGED,
        RunStatus.COMPLETED_MAX_ITER,
    }, "a new RunStatus arrived; decide whether its wall time is time to an answer"


def test_two_points_a_hair_apart_keep_distinct_labels():
    """The row label is an identity, so it must not round two rows into one."""
    view = cost_view(
        [
            _record("r1", alpha_deg=2.0, wall_time_s=10.0),
            _record("r2", alpha_deg=2.0000001, wall_time_s=90.0),
        ]
    )
    assert len(view.points) == 2
    labels = [point.label for point in view.points]
    assert len(set(labels)) == 2, (
        f"{labels} name the same point twice; a six-significant-digit format "
        "gives two different sweep points one name"
    )


def test_a_point_with_no_sweep_axes_is_labelled_rather_than_blank():
    view = cost_view([_record("r1", wall_time_s=10.0).model_copy(update={"point": {}})])
    assert view.points[0].label == "(no axes)"


def test_two_builds_whose_hashes_share_a_label_are_refused_not_merged():
    """The one place a column could silently swallow another."""
    twin_a = BuildKey("2122026", "c" * 12 + "1" * 52)
    twin_b = BuildKey("2122026", "c" * 12 + "2" * 52)
    assert twin_a.label == twin_b.label, "the fixture must actually collide"
    with pytest.raises(QaEvidenceError) as raised:
        CostView(builds=(twin_a, twin_b))
    assert "same cost column label" in str(raised.value)
    assert "merges two columns into one" in str(raised.value)
    assert isinstance(raised.value, ValueError), (
        "the catalogued class must keep the standard-library base the site raised "
        "before it, so an existing `except ValueError` catches what it always did"
    )


def test_a_source_that_is_not_a_manifest_is_refused_by_name():
    with pytest.raises(QaEvidenceError) as raised:
        cost_view(17)  # type: ignore[arg-type]
    assert "run manifests and from nothing else" in str(raised.value)


def test_every_refusal_of_this_reader_is_catchable_as_one_thing():
    """FR-39's first clause, held on the module rather than assumed.

    Three refusals live here and a caller reading a campaign's cost wants
    one `except` around the read. Before this they were two bare
    standard-library types, so `except PyflightstreamError` caught none
    of them, which is exactly what the catalogue ratchet refused.
    """
    twin_a = BuildKey("2122026", "d" * 12 + "1" * 52)
    twin_b = BuildKey("2122026", "d" * 12 + "2" * 52)
    view = cost_view([_record("r1", wall_time_s=10.0)])
    for call in (
        lambda: CostView(builds=(twin_a, twin_b)),
        lambda: view.build("no-such-label"),
        lambda: cost_view(17),
    ):
        with pytest.raises(PyflightstreamError):
            call()


def test_a_build_compared_with_itself_is_exactly_one():
    """The degenerate comparison, which must not be a special case."""
    view = cost_view([_record("r1", wall_time_s=12.0)])
    comparison = view.compare(view.builds[0], view.builds[0])
    assert comparison.ratio == pytest.approx(1.0)
    assert comparison.unpaired == ()


def test_a_comparison_with_nothing_paired_reports_unknown_rather_than_no_change():
    """No overlap is not a null result; it is an unanswered question."""
    view = cost_view(
        [
            _record("r1", alpha_deg=0.0, fs_exe_sha256=SHA_A, wall_time_s=10.0),
            _record("r2", alpha_deg=4.0, fs_exe_sha256=SHA_B, wall_time_s=10.0),
        ]
    )
    baseline = next(build for build in view.builds if build.fs_exe_sha256 == SHA_A)
    candidate = next(build for build in view.builds if build.fs_exe_sha256 == SHA_B)
    comparison = view.compare(baseline, candidate)
    assert comparison.paired == ()
    assert comparison.ratio is None, "1.0 would read as 'no change' where nothing was compared"
    assert len(comparison.unpaired) == 2


def test_a_point_run_only_on_a_third_build_is_not_counted_as_unpaired():
    """Unpaired means these two builds disagree, not that a third exists."""
    third = "c" * 64
    view = cost_view(
        [
            _record("r1", alpha_deg=0.0, fs_exe_sha256=SHA_A, wall_time_s=10.0),
            _record("r2", alpha_deg=0.0, fs_exe_sha256=SHA_B, wall_time_s=11.0),
            _record("r3", alpha_deg=9.0, fs_exe_sha256=third, wall_time_s=99.0),
        ]
    )
    comparison = view.compare(
        next(build for build in view.builds if build.fs_exe_sha256 == SHA_A),
        next(build for build in view.builds if build.fs_exe_sha256 == SHA_B),
    )
    assert len(comparison.paired) == 1
    assert comparison.unpaired == (), (
        "alpha=9 was never offered to either build being compared; naming it "
        "unpaired overstates what this comparison failed to cover"
    )


def test_a_campaign_root_is_read_through_its_manifest(tmp_path):
    """The view is built from ``runs.json`` and from nothing else."""
    root = _campaign(tmp_path, [_record("r1", wall_time_s=12.5)])
    view = cost_view(root)
    assert isinstance(view, CostView)
    assert view.wall_time_s(view.points[0], view.builds[0]) == pytest.approx(12.5)
    assert cost_view(CampaignWorkspace(root)).rows() == view.rows()


def test_the_cost_view_imports_nothing_but_the_manifest_layer():
    """Structural guard on "built only from run manifests".

    The acceptance sentence is a claim about the SOURCE of the numbers,
    which no behavioural test can pin: a future edit could reach into a
    committed physics report or start a solver and every assertion above
    would still pass. This one reads the module's own import graph.
    """
    source = (REPO_ROOT / "src" / "pyflightstream" / "qa" / "cost.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    package = {name for name in imported if name.split(".")[0] == "pyflightstream"}
    # `qa.errors` is admitted and the reason is stated rather than left to
    # be inferred from its presence. It is a NAME rather than a SOURCE: the
    # module holds exception classes, imports only `_errors`, reads no file
    # and computes no number, so it cannot be a second origin for anything
    # this view reports. It is here because FR-39's first clause is not
    # optional for a new module, and the catalogue ratchet refuses the bare
    # standard-library raises this module opened with.
    assert package == {"pyflightstream.workspace", "pyflightstream.qa.errors"}, (
        f"qa.cost imports {sorted(package)}; the cost view is built from run "
        "manifests alone, so the manifest layer plus the QA exception module "
        "are the only package imports it may take. Adding another is a "
        "deliberate change to what this view is."
    )
    errors = (REPO_ROOT / "src" / "pyflightstream" / "qa" / "errors.py").read_text(encoding="utf-8")
    assert "open(" not in errors and "read_text" not in errors, (
        "the exception module admitted above has grown a reader; the exemption "
        "rests on it holding classes and nothing that could be a second source"
    )
    assert "subprocess" not in imported, "nothing here runs a solver"


def test_physics_schema_is_unchanged_and_every_committed_report_still_loads():
    """The clause this item had to leave alone, asserted as a guard.

    The earlier reading of PFS-2018.02 would have moved the physics
    report to schema ``/2``. ``read_physics_report`` refuses any other
    schema, and ``update_reference`` seeds every stored reference
    through it, so the bump would have made the committed evidence
    unreadable. This test is what makes that failure loud.
    """
    assert PHYSICS_SCHEMA == "pyflightstream-physics-report/1"

    physics_reports = sorted((REPO_ROOT / "reports" / "physics").glob("PHY-*.yaml"))
    assert len(physics_reports) >= 16, (
        "the committed physics corpus shrank; a guard over an empty or "
        "shrinking glob reports green for the wrong reason"
    )
    for report in physics_reports:
        document = read_physics_report(report)
        assert document["schema"] == PHYSICS_SCHEMA, report

    # The same folder holds drift reports, which carry their own schema
    # and are REFUSED by this reader by design. Asserted so the loop
    # above is read as a deliberate selection rather than a filter that
    # happens to skip whatever would fail.
    drift_reports = sorted((REPO_ROOT / "reports" / "physics").glob("DRF-*.yaml"))
    assert drift_reports, "no drift reports found; the split below is untested"
    for report in drift_reports:
        assert yaml.safe_load(report.read_text(encoding="utf-8"))["schema"] != PHYSICS_SCHEMA
        with pytest.raises(QaEvidenceError):
            read_physics_report(report)


def test_the_cli_prints_one_column_per_build_and_names_absence(tmp_path, capsys):
    """``pyfs-qa cost`` renders the pivot with a legend a reader can use.

    The table block is asserted SEPARATELY from the legend. The first
    version of this test looked for "absent" anywhere in the output and
    passed with the cell printing 0.00, because the legend explaining
    the word was itself the match: the mutation battery for this item
    found it. A guard satisfied by a mention is not a guard.
    """
    root = _campaign(
        tmp_path,
        [
            _record("r1", alpha_deg=0.0, fs_exe_sha256=SHA_A, wall_time_s=10.0),
            _record("r2", alpha_deg=0.0, fs_exe_sha256=SHA_B, wall_time_s=None),
            _record("r3", alpha_deg=4.0, fs_exe_sha256=SHA_A, wall_time_s=20.0),
        ],
    )
    assert main(["cost", str(root)]) == 0
    out = capsys.readouterr().out
    table, _, legend = out.partition("\n\n")
    printed = _parse_printed_table(table)

    label_a = f"2122026@{SHA_A[:12]}"
    label_b = f"2122026@{SHA_B[:12]}"
    assert set(printed[0]) == {"SIM", "POINT", label_a, label_b}, (
        "each build is its own column, resolved by its label"
    )
    by_point = {row["POINT"]: row for row in printed}
    assert by_point["alpha_deg=0.0"][label_a] == "10.00"
    assert by_point["alpha_deg=0.0"][label_b] == "absent", (
        "the run is recorded there and carries no wall time"
    )
    assert by_point["alpha_deg=4.0"][label_a] == "20.00"
    assert by_point["alpha_deg=4.0"][label_b] == "not-run", (
        "that point never ran on that build, which is a different fact"
    )

    assert SHA_A in legend and SHA_B in legend, "the legend carries the full hash"
    assert "never as zero" in legend, "the reader is told what absent is not"


def test_the_cli_refuses_a_campaign_with_no_recorded_runs(tmp_path, capsys):
    """Nothing to cost is a refusal that names the file it looked in."""
    root = _campaign(tmp_path, [])
    assert main(["cost", str(root)]) == 2
    error = capsys.readouterr().err
    assert "runs.json" in error, error
    assert str(root) in error, error


def test_the_cli_refuses_an_unknown_build_label_and_lists_the_real_ones(tmp_path, capsys):
    """A typo in a column label is answered with the column labels."""
    root = _campaign(tmp_path, [_record("r1", fs_exe_sha256=SHA_A, wall_time_s=10.0)])
    assert main(["cost", str(root), "--compare", "nosuch,alsonosuch"]) == 2
    error = capsys.readouterr().err
    assert "nosuch" in error, error
    assert SHA_A[:12] in error, "the refusal lists the labels that do exist"


def test_the_cli_refuses_a_compare_without_two_names(tmp_path, capsys):
    """One name is not a comparison, and the refusal says what is missing."""
    root = _campaign(tmp_path, [_record("r1", wall_time_s=10.0)])
    assert main(["cost", str(root), "--compare", "onlyone"]) == 2
    error = capsys.readouterr().err
    assert "BASELINE,CANDIDATE" in error, error


def test_the_cli_names_the_missing_manifest_of_a_path_that_is_no_campaign(tmp_path, capsys):
    """Pointed at the wrong folder, it says which file it looked for."""
    assert main(["cost", str(tmp_path / "nowhere")]) == 2
    error = capsys.readouterr().err
    assert "runs.json" in error and "does not exist" in error, error


def test_the_cli_compares_two_builds_and_says_which_is_slower(tmp_path, capsys):
    root = _campaign(
        tmp_path,
        [
            _record("r1", fs_exe_sha256=SHA_A, wall_time_s=10.0),
            _record("r2", fs_exe_sha256=SHA_B, wall_time_s=15.0),
        ],
    )
    view = cost_view(root)
    baseline = next(build for build in view.builds if build.fs_exe_sha256 == SHA_A)
    candidate = next(build for build in view.builds if build.fs_exe_sha256 == SHA_B)
    assert main(["cost", str(root), "--compare", f"{baseline.label},{candidate.label}"]) == 0
    out = capsys.readouterr().out
    assert "1.50" in out, out
    assert "1 point(s) compared" in out, out
