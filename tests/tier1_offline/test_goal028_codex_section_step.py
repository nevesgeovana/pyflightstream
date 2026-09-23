"""An export's inner-iteration count is not an unsteady time step."""

from types import SimpleNamespace

import pytest

from pyflightstream.post.products import _last_time_step, read_csv_table, write_sections_table


@pytest.mark.parametrize("stopped,expected", [({}, 144), ({"step": 96}, 96)])
def test_a_legacy_clock_labels_the_end_export_without_a_reduction_plan(tmp_path, stopped, expected):
    from tests.tier1_offline.test_post_products import SLOADS

    record = SimpleNamespace(
        recipe="unsteady_rotor",
        reductions=None,
        stopped_at=stopped,
        export_window={"time_iterations": 144},
    )
    path = write_sections_table(
        tmp_path / "sections.csv",
        SLOADS,
        mach=0.2,
        step=_last_time_step(record),
    )
    _, rows = read_csv_table(path)
    assert {row["STEP"] for row in rows} == {str(expected)}
    assert {row["AZIMUTH"] for row in rows} == {"NA"}


def test_an_unrecorded_time_step_is_not_replaced_by_inner_iterations(tmp_path):
    from pyflightstream.post.products import _sim_products
    from tests.tier1_offline.test_post_products import SLOADS, _unsteady_workspace

    workspace = _unsteady_workspace(tmp_path, reductions=None)
    record = workspace.read_manifest()[0]
    # Amend only the in-memory record; the run manifest is left as written.
    record = record.model_copy(
        update={
            "outputs": [*record.outputs, "outputs/AL-020_sloads.txt"],
            "export_window": None,
        }
    )
    (workspace.sim_dir("7001") / "outputs/AL-020_sloads.txt").write_text(SLOADS)
    out = workspace.root / "post/review"
    _sim_products(workspace, "7001", [record], out, overwrite=True, archive=False)
    _, rows = read_csv_table(out / "sections/AL-020_sections.csv")
    assert {row["STEP"] for row in rows} == {"NA"}
