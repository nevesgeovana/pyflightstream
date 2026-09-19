"""The products and the sweep table take the END of a continuation chain (N11).

THE DEFECT (CONTINUATION-REBIND, the post half). A continuation archives the
CONTENTS of the datapoint folder and writes into that same folder, and the stopped
run's record is never rewritten, so its `outputs` go on naming the files its
continuation wrote. A run that reached `COMPLETED_MAX_ITER` and was then continued
to convergence left TWO successful records naming ONE loads table: both entered the
products and the sweep table, two run ids carrying the continuation's coefficients.

The run half records `continues: <run_id>` on the continuation. This half reads it:
the superseded record is left out and NAMED, so a table is one row per point again.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_post_products import _products_manifest, _unsteady_workspace  # noqa: E402

from pyflightstream.post.products import read_csv_table, write_campaign_products  # noqa: E402
from pyflightstream.results.tables import sweep_table  # noqa: E402
from pyflightstream.workspace import RunRecord, RunStatus  # noqa: E402

STOPPED = "camp/sim_7001/AL-020"
CONTINUED = "camp/sim_7001/20260919T120000/AL-020"


def _a_chain(tmp_path, *, linked: bool):
    """One point run to its iteration limit, then continued to convergence."""
    workspace = _unsteady_workspace(tmp_path, reductions=None)
    (first,) = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    stopped = first.model_copy(update={"status": RunStatus.COMPLETED_MAX_ITER})
    continued = first.model_copy(
        update={"run_id": CONTINUED, "continues": STOPPED if linked else None}
    )
    for record in (stopped, continued):
        workspace.append_record(RunRecord(**record.model_dump()))
    return workspace


def _polar_rows(workspace) -> list[dict[str, str]]:
    polars = workspace.root / "post" / "products" / "polars"
    (table,) = [path for path in polars.glob("P*.csv") if "SUPER" not in path.name]
    return read_csv_table(table)[1]


def test_the_products_hold_one_row_of_a_continued_point_and_name_the_other(tmp_path):
    workspace = _a_chain(tmp_path, linked=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace)
    assert len(_polar_rows(workspace)) == 1, "the point is in its polar twice"
    manifest = _products_manifest(workspace)
    reason = manifest["skipped"].get(f"runs/{STOPPED}", "")
    assert CONTINUED in reason, manifest["skipped"]
    runs = {run for entry in manifest["products"].values() for run in entry.get("runs", ())}
    assert STOPPED not in runs and CONTINUED in runs, runs


def test_two_runs_no_record_links_are_both_kept(tmp_path):
    """The control: nothing is dropped on a resemblance, only on the record's word."""
    workspace = _a_chain(tmp_path, linked=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        write_campaign_products(workspace)
    assert f"runs/{STOPPED}" not in _products_manifest(workspace).get("skipped", {})


def test_the_sweep_table_holds_the_end_of_the_chain_and_says_what_it_left_out(tmp_path):
    workspace = _a_chain(tmp_path, linked=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        table = sweep_table(workspace, require_loads=False)
    assert list(table["run_id"]) == [CONTINUED], list(table["run_id"])
    assert any(STOPPED in str(w.message) and CONTINUED in str(w.message) for w in caught)
