"""An export's inner-iteration count is not an unsteady time step."""

from types import SimpleNamespace

import pytest

from pyflightstream.post._condition import _last_time_step
from pyflightstream.post.products import read_csv_table, write_sections_table


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
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.workspace import CampaignWorkspace
    from tests.tier1_offline.test_post_products import SLOADS, _unsteady_workspace

    recorded = _unsteady_workspace(tmp_path / "recorded", reductions=None)
    record = recorded.read_manifest()[0]
    workspace = CampaignWorkspace.init(tmp_path / "posted")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text('[groups]\n"1" = "all"\n')
    outputs = workspace.sim_dir("7001") / "outputs"
    outputs.mkdir(parents=True)
    for name in ("AL-020.txt", "AL-020_plots.txt"):
        (outputs / name).write_text(
            (recorded.sim_dir("7001") / "outputs" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (outputs / "AL-020_sloads.txt").write_text(SLOADS)
    workspace.append_record(
        record.model_copy(
            update={
                "outputs": [*record.outputs, "outputs/AL-020_sloads.txt"],
                "export_window": None,
            }
        )
    )
    write_campaign_products(workspace)
    (table,) = workspace.root.glob("post/**/sections/AL-020_sections.csv")
    _, rows = read_csv_table(table)
    assert {row["STEP"] for row in rows} == {"NA"}
