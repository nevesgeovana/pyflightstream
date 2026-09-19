"""A product not written is a product EXPLAINED, and one bad export costs one product.

Three defects of one shape, each reproduced through the STAGE over a recorded
workspace, because every one of them had a caller that a unit test could reach
and a campaign could not:

- NL-01. The unsteady probe table is written only where the steady probe export
  produced none. The gate asked whether the steady export EXISTED, and every
  default unsteady row leaves one declaring ZERO probe points: a file that is
  there and yields no table. The product was unreachable on the rows it is for.
- MT-04. A record marked successful whose loads table is not on disk was passed
  over on a bare ``continue``: the point left every product and nothing said so.
- MT-01. A sectional-loads export the reader refuses raised out of the whole
  simulation after the polars were already written, so the manifest disowned
  files that were on disk.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_post_products import (  # noqa: E402
    LOADS,
    PLOTS_HEADER,
    _plots_export,
    _products_manifest,
    _unsteady_workspace,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _give(workspace, **update):
    """Replace the workspace's one record with a copy carrying ``update``."""
    from pyflightstream.workspace import RunRecord

    (record,) = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    workspace.append_record(RunRecord(**record.model_copy(update=update).model_dump()))


def test_a_default_unsteady_row_gets_its_probe_table(tmp_path):
    from pyflightstream.post.products import read_csv_table, write_campaign_products
    from pyflightstream.run import _write_probe_points

    workspace = _unsteady_workspace(tmp_path, reductions=None)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = ["W", "B"]\n\n[[probes]]\nframe = "PUSHER_SMRP"\n'
        'parameters = ["MACH", "VELOCITY"]\n',
        encoding="utf-8",
    )
    history = "Time-step,CL_MRP_TOTAL,MACH1,VELOCITY1\n" + "".join(
        f"{i}.0000,{0.1 * i:.5f},{0.2 + i:.5f},{70.0 + i:.5f},\n" for i in range(1, 5)
    )
    outputs = workspace.sim_dir("7001") / "outputs"
    (outputs / "AL-020_plots.txt").write_text(
        PLOTS_HEADER + history + "-" * 60 + "\n     Force Units: Coefficients\n", encoding="utf-8"
    )
    # WHAT EVERY REAL UNSTEADY RUN LEAVES: a steady probe export of zero points.
    zero = (FIXTURES / "probe_points_zero_26.123.txt").read_text(encoding="utf-8")
    (outputs / "AL-020_probes.txt").write_text(zero, encoding="utf-8")
    relative = _write_probe_points(
        workspace.sim_dir("7001"), "7001", [(1, 0.0, 1.0, 2.0, "PUSHER_SMRP")]
    )
    _give(
        workspace,
        probe_points_file=relative,
        outputs=["outputs/AL-020.txt", "outputs/AL-020_plots.txt", "outputs/AL-020_probes.txt"],
    )

    write_campaign_products(workspace)
    table = workspace.root / "post" / "products" / "probes" / "AL-020_probes.csv"
    assert table.is_file(), (
        "the unsteady probe table was not written: a steady export of zero points "
        f"satisfied the gate. skipped: {_products_manifest(workspace).get('skipped')}"
    )
    columns, rows = read_csv_table(table)
    assert "MACH" in columns and len(rows) == 4, (columns, len(rows))


def test_a_successful_run_whose_loads_table_is_gone_is_named(tmp_path):
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.workspace import RunRecord

    workspace = _unsteady_workspace(tmp_path, reductions=None)
    (record,) = workspace.read_manifest()
    lost = record.model_copy(
        update={
            "run_id": "camp/sim_7001/AL+020",
            "point_name": "AL+020",
            "point": {"alpha": 2.0},
            "outputs": ["outputs/AL+020.txt"],
        }
    )
    workspace.append_record(RunRecord(**lost.model_dump()))  # its loads table was never there

    write_campaign_products(workspace)
    skipped = _products_manifest(workspace).get("skipped", {})
    named = [key for key in skipped if "AL+020" in key]
    assert named, f"the point left every product and nothing names it: {skipped}"
    assert "loads table" in skipped[named[0]]


def test_an_unreadable_sections_export_costs_the_sections_table_and_nothing_else(tmp_path):
    from pyflightstream.post.products import write_campaign_products

    workspace = _unsteady_workspace(tmp_path, reductions=None)
    outputs = workspace.sim_dir("7001") / "outputs"
    (outputs / "AL-020_sloads.txt").write_text("not a sectional loads export\n", encoding="utf-8")
    _give(
        workspace,
        outputs=["outputs/AL-020.txt", "outputs/AL-020_plots.txt", "outputs/AL-020_sloads.txt"],
    )

    written = write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    assert "sections/AL-020_sections.csv" in manifest.get("skipped", {}), manifest.get("skipped")
    assert "7001" not in manifest.get("skipped", {}), "the whole simulation was refused"
    on_disk = {
        path.relative_to(workspace.root / "post" / "products").as_posix()
        for path in (workspace.root / "post" / "products").rglob("*.csv")
        if "archive" not in path.parts
    }
    claimed = set(manifest["products"])
    assert on_disk and on_disk <= claimed, f"on disk and not in the manifest: {on_disk - claimed}"
    assert any("polars" in Path(path).parts for path in map(str, written))
    assert json.dumps(manifest)  # the manifest is whole


def _windowed(tmp_path, *, pproc: str):
    """An unsteady record with a STATED window, which is what reaches the unsteady polar."""
    plan = {
        "window_stated": True,
        "time_iterations": 8,
        "steps_per_revolution": None,
        "blades": None,
        "time_average": {"windows": [[5, 8]], "window_from": "LAST_ITERS_AVG = 4"},
    }
    workspace = _unsteady_workspace(tmp_path, reductions=plan, recipe="unsteady")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(pproc, encoding="utf-8")
    return workspace


def test_a_pproc_that_writes_no_polar_tables_still_posts_an_unsteady_row(tmp_path):
    """MC-06. `[products] polars = false` on a windowed unsteady row was an
    UnboundLocalError, which no handler catches, so the stage died for everyone."""
    from pyflightstream.post.products import write_campaign_products

    workspace = _windowed(
        tmp_path, pproc='[groups]\n"1" = ["W", "B"]\n\n[products]\npolars = false\n'
    )
    written = write_campaign_products(workspace)
    names = {Path(path).name for path in written}
    assert "AL-020_time_average.csv" in names, sorted(names)


def test_the_unsteady_polar_vouches_only_for_the_points_it_holds(tmp_path):
    """MT-03. Two points, one whose history stops short of the window."""
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.workspace import RunRecord

    workspace = _windowed(tmp_path, pproc='[groups]\n"1" = ["W", "B"]\n')
    (record,) = workspace.read_manifest()
    outputs = workspace.sim_dir("7001") / "outputs"
    (outputs / "AL+020.txt").write_text(LOADS, encoding="utf-8")
    (outputs / "AL+020_plots.txt").write_text(_plots_export(6), encoding="utf-8")  # stops at 6
    short = record.model_copy(
        update={
            "run_id": "camp/sim_7001/AL+020",
            "point_name": "AL+020",
            "point": {"alpha": 2.0},
            "outputs": ["outputs/AL+020.txt", "outputs/AL+020_plots.txt"],
        }
    )
    workspace.append_record(RunRecord(**short.model_dump()))

    write_campaign_products(workspace)
    manifest = _products_manifest(workspace)
    (polar,) = [
        key
        for key in manifest["products"]
        if key.startswith("polars/") and key.endswith("_uns_avg.csv")
    ]
    assert manifest["products"][polar]["runs"] == ["camp/sim_7001/AL-020"], manifest["products"][
        polar
    ]
    assert "AL+020" in manifest["skipped"][polar]
