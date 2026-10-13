"""P0400-CW-QSTEADY: the quasi-steady rotor reads its inflow and its raw lines as one.

0.40.0 item PFS-2104.010: ``qsteady_inflow_fft`` read a NATIVE or undeclared
custom inflow in the raw mesh file's import unit, while the builder reads it in
the simulation's unit, which is metres for a raw mesh. PFS-2104.042: the
clockings before the last skipped the row's raw exec, analysis and export lines.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import CampaignConfigError, MeshImport, RawCommand
from pyflightstream.cases import freestream as _freestream_module
from pyflightstream.cases.workflows import qsteady_inflow_fft
from tests.tier1_offline.test_goal035_qsteady_rotor import (
    RING,
    _blade_obj,
    _case,
    _field,
    _lines,
    _with_obj,
)


@pytest.mark.parametrize("declared", ["NATIVE", None])
def test_p0400_cw_qsteady_the_plan_reads_the_inflow_in_the_simulations_unit(
    tmp_path, monkeypatch, declared
):
    """P0400-CW-QSTEADY (PFS-2104.010): a millimetre OBJ is a metre simulation."""
    requirement = "P0400-CW-QSTEADY"
    obj = _blade_obj(tmp_path / "prop.obj")
    case = _with_obj(_case(tmp_path), obj, ("Blade1", "Blade2", "Blade3"))
    case = case.model_copy(update={"mesh_import": MeshImport(units="MILLIMETER")})
    path = _field(tmp_path, [(*p, 30.0, 0.0, 0.0) for p in RING])
    variables = {**case.variables, "FREESTREAM": path.stem}
    if declared is not None:
        variables["FREESTREAM_UNITS"] = declared
    case = case.model_copy(update={"variables": variables, "freestream_profile": str(path)})
    seen: list[object] = []

    def recording(*args, **kwargs):
        seen.append(kwargs.get("native_unit"))
        raise CampaignConfigError("stopped by the test")

    monkeypatch.setattr(_freestream_module, "field_rows_in_metres", recording)
    record = qsteady_inflow_fft(case)
    assert record is not None and "stopped by the test" in str(record.get("note")), requirement
    assert seen == ["METER"], seen


def test_p0400_cw_qsteady_every_clocking_gets_the_rows_raw_phase_lines():
    """P0400-CW-QSTEADY (PFS-2104.042): a raw exec or analysis line reached the last solve alone.

    Three clockings on three blades: each solve carries the init-phase setting
    the row declares before exec, and the analysis line it declares after.
    """
    requirement = "P0400-CW-QSTEADY"
    case = _case(PASSAGE_POSITIONS="3", ALPHA_POINT=5.0).model_copy(
        update={
            "raw_commands": [
                RawCommand(command="SOLVER_SET_ITERATIONS 321", before="exec"),
                RawCommand(command="DELETE_VORTICITY_DRAG_BOUNDARIES", before="analysis"),
            ]
        }
    )
    lines, _ = _lines(case)
    assert lines.count("START_SOLVER") == 3, requirement
    assert lines.count("SOLVER_SET_ITERATIONS 321") == 3, lines
    assert lines.count("DELETE_VORTICITY_DRAG_BOUNDARIES") == 3, lines
    starts = [at for at, line in enumerate(lines) if line == "START_SOLVER"]
    settings = [at for at, line in enumerate(lines) if line == "SOLVER_SET_ITERATIONS 321"]
    assert all(setting < start for setting, start in zip(settings, starts, strict=True))
