"""B01: recorded residual freezes must fail assessment and suppress affected averages."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyflightstream import results
from pyflightstream.post.products import write_campaign_products
from pyflightstream.run import LoadsAssessor
from pyflightstream.run.collect import collect_once
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace
from tests.tier1_offline.test_post_products import (
    LOADS,
    SLOADS,
    _plots_export,
    _products_manifest,
    _unsteady_workspace,
)

FIXTURES = Path(__file__).parent / "fixtures"
# These are the last INNER iteration numbers printed in the verbatim excerpts.
LAST_ITERATION = {2413: 1933, 2411: 1728}


def _log(row):
    return (FIXTURES / f"pfs0240_row{row}_steps58-61_log.txt").read_text(encoding="utf-8")


def _loads(row):
    text = (FIXTURES / "loads_unsteady_26.120.txt").read_text(encoding="utf-8")
    # Synthetic companion export: align its final iteration with the excerpt,
    # without changing any byte of the log used as the freeze oracle.
    return text.replace("1575", str(LAST_ITERATION[row]))


def test_recorded_freeze_and_negative_controls():
    detector = getattr(results, "frozen_time_steps", None)
    assert callable(detector), "results must expose the pure frozen_time_steps detector"
    frozen = detector(_log(2413))
    assert frozen is not None, "row 2413 freezes at solver step 60"
    assert (frozen.first_step, frozen.count) == (60, 2)
    assert detector(_log(2411)) is None, "the healthy sector has no frozen steps"
    steady = re.sub(r"Solving unsteady time-step iteration \(\d+/\d+\)", "Steady", _log(2413))
    assert detector(steady) is None, "a steady log cannot trigger this unsteady rule"
    one = _log(2413).split("Solving unsteady time-step iteration (61/144)")[0]
    assert detector(one) is None, "one frozen step is insufficient"


def test_freeze_requires_consecutive_steps_and_exact_printed_zeros():
    detector = getattr(results, "frozen_time_steps", None)
    assert callable(detector), "results must expose the pure frozen_time_steps detector"
    text = _log(2413)
    assert detector(text.replace("(61/144)", "(62/144)")) is None
    assert detector(text.replace("+0.0000000E+0", "+1.0000000E-999")) is None
    # The first iteration may be nonzero; the final pressure must be zero.
    lines = text.splitlines(keepends=True)
    last = next(i for i, line in enumerate(lines) if line.startswith("1933 "))
    cells = lines[last].split("\t")
    cells[2] = cells[2].replace("+0.0000000E+0", "+1.0000000E-9")
    lines[last] = "\t".join(cells)
    assert detector("".join(lines)) is None
    # No later iterations exist in a one-iteration step, so the final pair
    # decides it under the stated rule. Two consecutive such steps still count.
    single_iterations = "".join(
        f"Solving unsteady time-step iteration ({step}/2)...\n"
        f"Iteration Res. Vel. Res. Pres.\n{step} 0 0\n------\n"
        for step in (1, 2)
    )
    frozen = detector(single_iterations)
    assert frozen is not None and (frozen.first_step, frozen.count) == (1, 2)
    assert detector(single_iterations.replace(" 0 0", " 1 0")) is None


def test_assessor_rejects_frozen_log_and_accepts_healthy_log(tmp_path):
    for row in (2411, 2413):
        sim = tmp_path / str(row)
        outputs = sim / "outputs"
        outputs.mkdir(parents=True)
        (outputs / "point.txt").write_text(_loads(row), encoding="utf-8")
        (outputs / "point_log.txt").write_bytes(
            (FIXTURES / f"pfs0240_row{row}_steps58-61_log.txt").read_bytes()
        )
        assessment = LoadsAssessor()(None, None, sim)
        if row == 2411:
            assert assessment.status is RunStatus.CONVERGED, assessment.error
        else:
            assert assessment.status is RunStatus.FAILED_DIVERGED, (
                f"frozen point was assessed {assessment.status}: {assessment.error}"
            )
            assert "step 60" in assessment.error and "2 frozen steps" in assessment.error


def test_collect_persists_frozen_failure_and_reason(tmp_path):
    for row in (2411, 2413):
        workspace, sim = _submitted_workspace(tmp_path / str(row))
        (sim / "loads.txt").write_text(_loads(row), encoding="utf-8")
        (sim / "run_log.txt").write_text(_log(row), encoding="utf-8")
        collect_once(workspace, interval=0.0, sleep=_no_sleep)
        record = workspace.read_manifest()[0]
        if row == 2411:
            assert record.status is RunStatus.CONVERGED, record.error
        else:
            assert record.status is RunStatus.FAILED_DIVERGED, (
                f"collect recorded frozen point as {record.status}: {record.error}"
            )
            assert "step 60" in record.error and "2 frozen steps" in record.error
            assert record.log_file_used == "run_log.txt"


def _post_workspace(tmp_path, row, window, *, rotor=False, passages=None):
    plan = {
        "time_iterations": 61,
        "window_stated": True,
        "steps_per_revolution": 4.0,
        "blades": 2,
        "blade_families": ["Blade1", "Blade2"],
        "time_average": {"windows": [list(window)]},
        # THE PASSAGES OF THE PER-BLADE REDUCTION, one window each, are the
        # shape a rotor row has and the only one where a freeze can reach
        # some windows of a file and not others.
        "per_blade": {"windows": [list(w) for w in (passages or [window])]},
        "phase_locked": {"windows": [list(window)]},
    }
    # Use the existing stage fixture's record and pproc, then collect all
    # evidence beside the loads in the current datapoint layout.
    template = _unsteady_workspace(tmp_path / "template", reductions=plan, rows=61)
    record = template.read_manifest()[0]
    workspace = CampaignWorkspace.init(tmp_path / "test")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_bytes(
        (template.inputs_dir / "pproc" / "p001.toml").read_bytes()
    )
    folder = "datapoints/DP-AL-020"
    raw = workspace.sim_dir("7001") / folder
    raw.mkdir(parents=True)
    (raw / "AL-020.txt").write_text(LOADS.replace("Steady", "Unsteady"), encoding="utf-8")
    (raw / "AL-020_plots.txt").write_text(_plots_export(61), encoding="utf-8")
    (raw / "AL-020_log.txt").write_bytes(
        (FIXTURES / f"pfs0240_row{row}_steps58-61_log.txt").read_bytes()
    )
    # An instant sections product must remain explicitly instant.
    (raw / "AL-020_sloads.txt").write_text(SLOADS, encoding="utf-8")
    outputs = [
        f"{folder}/{name}"
        for name in ("AL-020.txt", "AL-020_plots.txt", "AL-020_log.txt", "AL-020_sloads.txt")
    ]
    fields = record.model_dump(exclude={"outputs"})
    if rotor:
        from tests.tier1_offline.test_goal028_rotor_table_average import REFERENCE, _pproc

        matrix = (FIXTURES / "superfile_matriz.fs").read_text(encoding="utf-8")
        matrix = matrix.replace("6002", "7001").replace("p002", "p001")
        (workspace.root / "products.fs").write_text(matrix, encoding="utf-8")
        (workspace.inputs_dir / "references" / "r002.toml").write_text(REFERENCE, encoding="utf-8")
        (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
            _pproc("HUB_PUSHER", "MRP", '["B"]'), encoding="utf-8"
        )
        plots = _plots_export(61)
        plots = plots.replace(
            "Time-step,CL_MRP_TOTAL,CDI_MRP_TOTAL,CL_MRP_Blade1,CL_MRP_Blade2",
            "Time-step,FX_HUB_PUSHER,FY_HUB_PUSHER,FZ_HUB_PUSHER,MX_HUB_PUSHER,"
            "MY_HUB_PUSHER,MZ_HUB_PUSHER,CL_MRP_Blade1,CL_MRP_Blade2",
        )
        plots = re.sub(
            r"(?m)^(\d+)\.0000,.*$",
            lambda match: f"{match[1]}.0000,100,0,0,0,0,0,1,2,",
            plots,
        )
        (raw / "AL-020_plots.txt").write_text(plots, encoding="utf-8")
        fields.update(matrix_stem="products", density_kg_m3=1.225)
        fields["reductions"]["rpm"] = 2200.0
    workspace.append_record(RunRecord(**fields, outputs=outputs))
    return workspace


@pytest.mark.parametrize("window", [(58, 60), (60, 61), (61, 61)])
def test_post_skips_frozen_averages_by_name_and_keeps_healthy_control(tmp_path, window):
    for row in (2411, 2413):
        workspace = _post_workspace(tmp_path / str(row), row, window)
        written = write_campaign_products(workspace)
        manifest = _products_manifest(workspace)
        averaged = [
            "probes/AL-020_time_average.csv",
            "probes/AL-020_per_blade.csv",
            "probes/AL-020_phase_locked.csv",
        ]
        polar = next(
            key
            for key in manifest["products"] | manifest["skipped"]
            if key.endswith("_uns_avg.csv")
        )
        for name in [*averaged, polar]:
            if row == 2411:
                assert name in manifest["products"], manifest["skipped"]
            else:
                assert name not in manifest["products"], f"frozen average published: {name}"
                assert "step 60" in manifest["skipped"][name]
                assert not (workspace.root / "post/products" / name).exists()
        assert "probes/AL-020_plots.csv" in manifest["products"]
        assert manifest["products"]["sections/AL-020_sections.csv"]["kind"] == "instant"
        assert all(path.is_file() for path in written)


def test_post_preserves_windows_before_freeze_and_archives_stale_averages(tmp_path):
    workspace = _post_workspace(tmp_path, 2413, (58, 59))
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert "probes/AL-020_time_average.csv" in manifest["products"]
    # Re-posting an old success whose former native log was healthy must remove
    # the stale averages as well as report the new skips.
    workspace = _post_workspace(tmp_path / "repost", 2411, (60, 61))
    write_campaign_products(workspace)
    log_path = workspace.sim_dir("7001") / "datapoints/DP-AL-020/AL-020_log.txt"
    log_path.write_text(_log(2413), encoding="utf-8")
    write_campaign_products(workspace, overwrite=True)
    manifest = _products_manifest(workspace)
    name = "probes/AL-020_time_average.csv"
    assert name not in manifest["products"], "re-post retained a stale frozen average"
    assert "step 60" in manifest["skipped"][name]
    assert not (workspace.root / "post/products" / name).exists()


def test_post_rotor_table_rejects_frozen_window_and_keeps_healthy_control(tmp_path):
    for row in (2411, 2413):
        workspace = _post_workspace(tmp_path / str(row), row, (60, 61), rotor=True)
        write_campaign_products(workspace, matrix_stem="products")
        manifest = _products_manifest(workspace)
        rotor = next(
            name
            for name in manifest["products"] | manifest["skipped"]
            if name.endswith("_rotor.csv")
        )
        if row == 2411:
            assert rotor in manifest["products"], manifest["skipped"]
        else:
            assert rotor not in manifest["products"], "frozen CT was published in the rotor table"
            assert "step 60" in manifest["skipped"][rotor]
            assert not (workspace.root / "post/products" / rotor).exists()


def test_post_checks_each_reduction_window_independently(tmp_path):
    # The polar/time average ends before the freeze, while a separately planned
    # rotor reduction reaches step 60. Only that reduction should disappear.
    workspace = _post_workspace(tmp_path, 2413, (58, 59))
    record = workspace.read_manifest()[0]
    plan = dict(record.reductions)
    plan["phase_locked"] = {"windows": [[59, 60]]}
    # Use the workspace's archive-and-replace API for this synthetic record.
    workspace.supersede_records([record.run_id])
    workspace.append_record(record.model_copy(update={"reductions": plan}))
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert "probes/AL-020_time_average.csv" in manifest["products"]
    assert "probes/AL-020_per_blade.csv" in manifest["products"]
    phase = "probes/AL-020_phase_locked.csv"
    assert phase not in manifest["products"], "a separate frozen reduction was published"
    assert "step 60" in manifest["skipped"][phase]


def test_a_frozen_passage_does_not_take_the_passages_that_end_before_it(tmp_path):
    """GH-03 of the independent review of GitHub main, 2026-09-20.

    The definitions page: an average whose window ends at or after the first
    frozen step is skipped by name, and "windows wholly before that step keep
    their products". The reduction refused the whole file as soon as ONE of
    its windows reached the freeze, so a row whose earlier passages are clean
    lost them together with the dead one, and the manifest said only that the
    file was skipped for a freeze at step 60.
    """
    workspace = _post_workspace(tmp_path, 2413, (58, 59), passages=[(58, 59), (60, 61)])
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    name = "probes/AL-020_per_blade.csv"
    # the clean passage keeps its product
    assert name in manifest["products"], manifest["skipped"]
    assert (workspace.root / "post/products" / name).is_file()
    assert manifest["products"][name]["windows"] == [[58, 59]]
    # and the passage that reaches the freeze is named, under the file's own name
    partial = manifest["skipped"][f"{name}#windows"]
    assert "step 60" in partial
    assert "60" in partial and "61" in partial


def _cut_the_log_mid_table(workspace) -> None:
    """Leave the last residual page without its closing separator, as a killed run does."""
    log_path = workspace.sim_dir("7001") / "datapoints/DP-AL-020/AL-020_log.txt"
    text = log_path.read_text(encoding="latin-1")
    marker = text.rfind("Solving unsteady time-step iteration")
    page = text.index("Iteration", marker)
    log_path.write_text(text[: page + 260], encoding="latin-1")


@pytest.mark.parametrize("row", [2411, 2413])
def test_a_log_the_solver_stopped_under_does_not_kill_the_whole_post(tmp_path, row):
    """Measured on the cluster and on Windows alike, 2026-09-22.

    `pyfs-matrix collect` and `pyfs-matrix post` both died with
    IncompleteOutputError out of `frozen_time_steps`: the freeze check reads the
    native log, and a block the solver stopped under has a residual header with
    no rows and no closing rule. The exception left `write_campaign_products`,
    so ONE such block cost every product of every simulation.
    """
    workspace = _post_workspace(tmp_path / str(row), row, (58, 60))
    _cut_the_log_mid_table(workspace)
    write_campaign_products(workspace)  # must not raise
    manifest = _products_manifest(workspace)
    assert "probes/AL-020_plots.csv" in manifest["products"]
    assert manifest["products"]["sections/AL-020_sections.csv"]["kind"] == "instant"


def test_an_unreadable_step_refuses_only_the_windows_it_falls_in(tmp_path):
    """The real log decided this, against the first version of this test.

    It carries 144 step blocks and exactly ONE cannot be read -- the second
    block of step 1, a header the walltime guard stopped under -- while a second
    attempt runs to step 72 and parses to the end. Refusing every average of
    that point would be far more than the evidence requires. An unread block
    says nothing about the steps around it, which is exactly what a freeze does
    not: a freeze contaminates every step after its first.
    """
    kept = _post_workspace(tmp_path / "before", 2411, (58, 60))
    _cut_the_log_mid_table(kept)  # the unreadable block is step 61
    write_campaign_products(kept)
    name = "probes/AL-020_time_average.csv"
    manifest = _products_manifest(kept)
    assert name in manifest["products"], manifest["skipped"]
    assert manifest["products"][name]["windows"] == [[58, 60]]

    covered = _post_workspace(tmp_path / "covering", 2411, (58, 61))
    _cut_the_log_mid_table(covered)
    write_campaign_products(covered)
    manifest = _products_manifest(covered)
    assert name not in manifest["products"], "an average was published over a step nobody read"
    assert "cannot be read for time step(s) 61" in manifest["skipped"][name]


def test_a_freeze_in_the_readable_blocks_still_refuses_everything_after_it(tmp_path):
    """Tolerating an unreadable block may not cost the detector a freeze it CAN see.

    Row 2413 freezes at step 60. With its last block unreadable, the freeze is
    still in the blocks that parse, and it wins: the reason is the freeze, not
    the unread step, and the window is refused for it.
    """
    workspace = _post_workspace(tmp_path, 2413, (58, 60))
    _cut_the_log_mid_table(workspace)
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    name = "probes/AL-020_time_average.csv"
    assert name not in manifest["products"], "an average of a frozen solve was published"
    # Step 60 froze and step 61 could not be read, so the pair may be the freeze
    # the detector needs two consecutive steps to declare. It is named as unread
    # rather than asserted as frozen -- what matters is that the average over it
    # is refused, which is what a silent publish would have cost her.
    assert "60" in manifest["skipped"][name]
    assert "cannot be read for time step(s)" in manifest["skipped"][name]
