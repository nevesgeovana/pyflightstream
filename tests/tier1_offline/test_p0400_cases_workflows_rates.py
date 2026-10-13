"""A matrix body-rate sweep builds a fresh free stream at every point."""

from pyflightstream.cases.workflows import build_script
from pyflightstream.run._ids import runs_as_one_job
from pyflightstream.script import Script
from tests.tier1_offline.test_goal024_point_name import _matrix
from tests.tier1_offline.test_goal024_sweep_any_variable import AXES, _resolved


def test_p0400_cw_rates_a_matrix_sweep_runs_each_rate_as_its_own_job(tmp_path):
    """P0400-CW-RATES (PFS-2104.043): the job router cannot group different body rates."""
    requirement = "P0400-CW-RATES"
    workspace, matrix = _matrix(
        tmp_path,
        condition="MACH:0.2, REmi:2.3, ALPHA:0.0, pitch_rate:sweep",
        values="2.0,4.0",
    )
    reference = workspace.inputs_dir / "references" / "r003.toml"
    reference.write_text(reference.read_text(encoding="utf-8") + AXES, encoding="utf-8")
    resolved = _resolved(workspace, matrix)
    case = resolved.campaign.sims[0]
    assert not runs_as_one_job(resolved.campaign, case), requirement
    texts = []
    for point in case.sweep.points():
        script = Script("26.120")
        build_script(case.model_copy(update={"point": point}), script)
        texts.append(script.render())
    assert all(text.count("SET_FREESTREAM ROTATION") == 1 for text in texts)
    assert texts[0] != texts[1]
