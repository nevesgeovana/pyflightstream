"""Post a campaign normally to warn, or pass check_frozen=True to refuse doubts."""

import json
import re

import pytest

from pyflightstream.post.products import freeze_of_log, write_campaign_products
from pyflightstream.results import UnjudgeableSolve
from tests.tier1_offline.test_b01_frozen_solve import (
    _log,
    _make_one_step_unreadable,
    _post_workspace,
    _products_manifest,
)


def test_every_post_writes_and_archives_its_log(tmp_path):
    workspace = _post_workspace(tmp_path, 2411, (60, 61))
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert manifest.get("log") == "post.log", "a clean post names no log"
    log = workspace.products_dir(None) / manifest["log"]
    before = log.read_bytes()
    text = before.decode()
    assert all(word in text for word in ("0.26.0", str(workspace.root), "matrix", "time", "False"))
    for name, reason in manifest["skipped"].items():
        assert name in text and reason in text
    write_campaign_products(workspace, overwrite=True)
    copies = list(log.parent.glob("archive/*/post.log"))
    assert len(copies) == 1 and copies[0].read_bytes() == before


def test_default_keeps_every_product_with_frozen_and_unread_steps(tmp_path):
    """Since 0.26.0 doubts warn in post.log and never withhold computable products."""
    workspace = _post_workspace(tmp_path, 2411, (58, 61))
    write_campaign_products(workspace)
    baseline = set(_products_manifest(workspace)["products"])
    path = workspace.sim_dir("7001") / "datapoints/DP-AL-020/AL-020_log.txt"
    path.write_text(_log(2413), encoding="utf-8")
    _make_one_step_unreadable(workspace, 58)
    write_campaign_products(workspace, overwrite=True)
    manifest = _products_manifest(workspace)
    assert set(manifest["products"]) == baseline
    log = workspace.products_dir(None) / "post.log"
    assert log.is_file(), "frozen and unread steps have no post log"
    lines = log.read_text(encoding="utf-8").splitlines()
    assert any(
        all(
            word in line
            for word in ("WARNING", "AL-020", "time_average", "58", "unread", "recollect")
        )
        for line in lines
    )
    assert any(
        all(word in line for word in ("WARNING", "AL-020", "time_average", "60", "frozen", "run"))
        for line in lines
    )


@pytest.mark.parametrize("asked", [False, True])
def test_partial_iteration_anchor_is_unread_at_the_product(tmp_path, asked):
    workspace = _post_workspace(tmp_path, 2413, (60, 61))
    path = workspace.sim_dir("7001") / "datapoints/DP-AL-020/AL-020_log.txt"
    text = path.read_text(encoding="utf-8")
    anchor = text.index("Iteration", text.rfind("Solving unsteady time-step iteration"))
    path.write_text(text[: anchor + len("Iterat")], encoding="utf-8")
    verdict = freeze_of_log(path)
    assert isinstance(verdict, UnjudgeableSolve), "a cut before Iteration was treated as readable"
    assert 61 in verdict.steps
    write_campaign_products(workspace, check_frozen=asked)
    manifest = _products_manifest(workspace)
    product = "probes/AL-020_time_average.csv"
    assert (product in manifest["products"]) is not asked
    assert "61" in (workspace.products_dir(None) / "post.log").read_text()


@pytest.mark.parametrize("row", [2411, 2413])
def test_repeated_markers_are_not_unread(tmp_path, row):
    """A marker immediately followed by the same step is an export block, not a cut."""
    source = _log(row)
    repeated = re.sub(
        r"(Solving unsteady time-step iteration \(\d+/\d+\))", r"\1\nExporting...\n\1", source
    )
    path = tmp_path / "repeat.txt"
    path.write_text(repeated, encoding="utf-8")
    verdict = freeze_of_log(path)
    if row == 2411:
        assert verdict is None
    else:
        assert verdict is not None and not isinstance(verdict, UnjudgeableSolve)
        assert (verdict.first_step, verdict.count) == (60, 2)


@pytest.mark.parametrize("shape", ["totals", "fractional", "alias"])
@pytest.mark.parametrize("asked", [False, True])
@pytest.mark.parametrize("inside", [False, True])
def test_reducer_samples_control_product_warning_or_refusal(tmp_path, shape, asked, inside):
    from tests.tier1_offline.test_unread_steps_and_freezes import _log as blocks

    workspace = _post_workspace(tmp_path, 2411, (59, 61), rotor=True)
    reference = workspace.inputs_dir / "references" / "r002.toml"
    if shape == "alias":
        reference.write_text(reference.read_text() + '\n[aliases]\nB = ["Blade1", "Blade2"]\n')
    else:
        reference.write_text(
            reference.read_text().replace(
                'families_blades = ["B"]', 'families_blades = ["Blade1", "Blade2"]'
            )
        )
    records = json.loads((workspace.root / "runs.json").read_text())
    span, depth, last, first = (3.6, 4.0, 20, 6) if shape == "fractional" else (3.0, 1.0, 61, 59)
    entry = {
        "windows": [[first, last]],
        "shape": "azimuthal",
        "revolutions": depth,
        "steps_per_revolution": span,
    }
    plan = records[0]["reductions"]
    plan["phase_locked"] = entry
    plan["rotors"] = {
        "PUSHER": {
            "blades": 2,
            "blade_families": (["B"] if shape == "alias" else ["Blade1", "Blade2"]),
            "rpm": 2200.0,
            "blade1_azimuth_deg": 0.0,
            "phase_locked": entry,
        }
    }
    (workspace.root / "runs.json").write_text(json.dumps(records))
    raw = workspace.sim_dir("7001") / "datapoints/DP-AL-020"
    if shape != "alias":
        path = raw / "AL-020_plots.txt"
        lines = path.read_text().splitlines()
        path.write_text(
            "\n".join(
                line.rsplit(",", 3)[0] + ","
                if re.match(r"\d+\.0000,", line)
                else line.replace(",CL_MRP_Blade1,CL_MRP_Blade2", "")
                for line in lines
            )
            + "\n"
        )
    earliest = 58 if shape == "alias" else first
    unread = earliest if inside else earliest - 1
    (raw / "AL-020_log.txt").write_text(
        blocks(*[(step, "unread" if step == unread else "live") for step in range(1, 62)])
    )
    write_campaign_products(workspace, matrix_stem="products", check_frozen=asked)
    manifest = _products_manifest(workspace)
    product = "probes/AL-020_phase_locked_PUSHER.csv"
    assert (product in manifest["products"]) is not (inside and asked), manifest["skipped"]
    log = workspace.products_dir("products") / "post.log"
    assert log.is_file(), "the product's sample verdict was not logged"
    affected = [
        line for line in log.read_text().splitlines() if product in line and "unread" in line
    ]
    assert bool(affected) is inside, affected


@pytest.mark.parametrize(
    ("span", "depth", "last", "columns", "expected"),
    [
        (3.0, 1.0, 61, ["CL_TOTAL"], {59, 60, 61}),
        (3.6, 4.0, 20, ["CL_TOTAL"], set(range(6, 21))),
        (3.0, 1.0, 61, ["CL_Blade1", "CL_Blade2"], {58, 59, 60, 61}),
        (2.0000000001, 1.0, 61, ["CL_Blade1", "CL_Blade2"], {59, 60, 61}),
    ],
)
def test_reducer_states_exactly_the_nonzero_samples(span, depth, last, columns, expected):
    import numpy as np

    from pyflightstream.post.unsteady import TimestepSeries, phase_locked_rows

    steps = np.arange(1, last + 1)
    series = TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={name: steps[:, None] for name in columns},
        sources=(),
    )
    read = set()
    rows = phase_locked_rows(
        series,
        columns,
        last_step=last,
        revolutions=depth,
        steps_per_revolution=span,
        blade1_azimuth_deg=0.0,
        blades=2,
        blade_families=["Blade1", "Blade2"],
        read_steps=read,
    )
    assert read == expected
    # The reported samples belong to the numerical path: perturb every plotted
    # value independently, and compare the rows the same reducer computes.
    for step in steps:
        changed = TimestepSeries(
            steps=steps,
            times_s=None,
            points=series.points,
            fields={name: values.astype(float).copy() for name, values in series.fields.items()},
            sources=(),
        )
        for values in changed.fields.values():
            values[step - 1] += 1e10
        measured = phase_locked_rows(
            changed,
            columns,
            last_step=last,
            revolutions=depth,
            steps_per_revolution=span,
            blade1_azimuth_deg=0.0,
            blades=2,
            blade_families=["Blade1", "Blade2"],
        )
        assert (measured != rows) is (int(step) in expected)


def test_every_stage_warning_is_logged_even_if_the_caller_filters_it(tmp_path, monkeypatch):
    import warnings

    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.post import products

    original = products._write_the_products

    def warn(*args, **kwargs):
        warnings.warn(
            "point=AL-020 product=probes: restore the missing probe coordinates",
            PyflightstreamWarning,
            stacklevel=2,
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(products, "_write_the_products", warn)
    workspace = _post_workspace(tmp_path, 2411, (60, 61))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        write_campaign_products(workspace)
    assert (
        "restore the missing probe coordinates"
        in (workspace.products_dir(None) / "post.log").read_text()
    )


def test_a_clean_empty_campaign_also_has_a_log(tmp_path):
    from pyflightstream.workspace import CampaignWorkspace

    workspace = CampaignWorkspace.init(tmp_path / "empty")
    assert write_campaign_products(workspace) == []
    manifest = _products_manifest(workspace)
    assert manifest["log"] == "post.log"
    assert "WARNING" not in (workspace.products_dir(None) / "post.log").read_text()


def test_failed_incomplete_point_keeps_computable_products_by_default(tmp_path):
    """Since 0.26.0 an unread block is a warning even on a failed record."""
    from pyflightstream.workspace import RunStatus

    workspace = _post_workspace(tmp_path, 2411, (58, 61), status=RunStatus.FAILED_INCOMPLETE_OUTPUT)
    _make_one_step_unreadable(workspace, 58)
    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert "probes/AL-020_time_average.csv" in manifest["products"]
    assert "unread" in (workspace.products_dir(None) / "post.log").read_text()


def test_guard_judges_the_sample_set_not_its_envelope():
    import numpy as np

    from pyflightstream.post.products import _frozen_window_reason, _window_the_reduction_reads
    from pyflightstream.post.unsteady import TimestepSeries

    steps = np.array([1, 59, 60, 61])
    series = TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={"CL_Blade2": steps[:, None]},
        sources=(),
    )
    reads = _window_the_reduction_reads(
        "phase_locked",
        {"shape": "azimuthal", "revolutions": 1, "steps_per_revolution": 3},
        (59, 61),
        series,
        ["CL_Blade2"],
        2,
        {"families": ["Blade1", "Blade2"], "rpm": 1},
    )
    assert reads == {1, 59, 60, 61}
    assert _frozen_window_reason(UnjudgeableSolve(58, 1, steps=(58,)), reads) is None
    assert _frozen_window_reason(UnjudgeableSolve(1, 1, steps=(1,)), reads) is not None


def test_interrupted_post_keeps_its_log_and_warning(tmp_path, monkeypatch):
    import warnings

    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream.post import products

    def interrupt(*args, **kwargs):
        warnings.warn(
            "point=AL-020 product=probe: restore the missing data",
            PyflightstreamWarning,
            stacklevel=2,
        )
        raise RuntimeError("interrupted by the test")

    monkeypatch.setattr(products, "_write_the_products", interrupt)
    workspace = _post_workspace(tmp_path, 2411, (60, 61))
    with pytest.raises(RuntimeError, match="interrupted by the test"):
        write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert manifest["log"] == "post.log" and manifest["complete"] is False
    log = (workspace.products_dir(None) / "post.log").read_text()
    assert "restore the missing data" in log and "interrupted by the test" in log
