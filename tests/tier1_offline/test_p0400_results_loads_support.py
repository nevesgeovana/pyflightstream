"""Shared recorded loads and workspace builders for the results regressions."""

from pyflightstream.workspace import CampaignWorkspace, PointName
from tests.tier1_offline.test_tables import make_record, read_fixture


def _one_run(tmp_path, *outputs, **overrides):
    """A workspace of one steady run whose collected outputs are ``(datapoint, name, text)``."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    collected: list[str] = []
    for number, (datapoint, name, text) in enumerate(outputs):
        source = tmp_path / f"src{number}"
        source.mkdir()
        (source / name).write_text(text, encoding="utf-8")
        collected += workspace.collect_outputs(
            "9001", [source / name], datapoint=PointName(datapoint)
        )
    record = make_record(
        run_id="camp/sim_9001/AL+020",
        point_name="AL+020",
        sweep_name="AL+020",
        point={"alpha": 2.0},
        outputs=collected,
        **overrides,
    )
    workspace.append_record(record)
    return workspace, record


STEADY = read_fixture("loads_steady_26.120.txt")
TRUNCATED = STEADY[: STEADY.index("Force Units")]
