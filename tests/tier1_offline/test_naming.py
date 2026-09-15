"""PFS-2029.19 and 0.21.0: the author's naming convention names every point and its exports.

The author's third sentence of 2026-09-02: the output names were bad, look at how
the author's master's scripts did it. Measured there: the case name carried the
polar, the Mach, the angles and the advance ratio, fixed width, and every
export hung off it. At 0.21.0 her decision of 2026-09-15 makes the name every
variable the row's flight condition declares, in its order, and the file stem
``P<POL>-<name>``. The matrix command line names points by ``{polar}``; the
library default is ``{point}``, the bare name.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pyflightstream.cases import Campaign, SimCase, SweepAxis, point_name
from pyflightstream.run import RunStatus, run_campaign
from pyflightstream.run.cli import _build_parser
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.naming import (
    MATRIX_POINT_NAME,
    NamingTemplate,
    NamingTemplateError,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _case(order, *, sim="9001", point_values=None, variables=None, flow=None, mach=None):
    return SimCase(
        sim_id=sim,
        aircraft="X",
        mach=mach,
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="steady",
        flight_condition=flow or {},
        condition_order=order,
        variables=variables or {},
    )


def test_the_default_template_is_her_convention():
    """P<sim>-<every declared variable, in row order, at the digits of its code> (0.21.0)."""
    template = NamingTemplate(point_name=MATRIX_POINT_NAME)
    rotor = _case(
        ["MACH", "REmi", "ALPHA", "BETA", "ADVANCE_RATIO"],
        flow={"MACH": 0.1441, "REmi": 4.38},
        mach=0.1441,
    )
    name = point_name(rotor, {"alpha": 0.0, "beta": 0.0, "advance_ratio": 0.8007})
    assert name == "M144RE438AL+000BE+000J+080", "her example of 2026-09-15"
    assert template.render_point(campaign="c", sim="2001", point={}, name=name) == (
        "P2001-M144RE438AL+000BE+000J+080"
    )
    # Fixed widths sort: alpha 10 and alpha -2 keep their four characters.
    wing = _case(["MACH", "ALPHA"], flow={"MACH": 0.2}, mach=0.2)
    assert point_name(wing, {"alpha": 10.0}) == "M200AL+100"
    assert point_name(wing, {"alpha": -2.0}) == "M200AL-020"
    # The order is the row's, not a fixed one.
    assert point_name(_case(["ALPHA", "MACH"], flow={"MACH": 0.2}), {"alpha": 1.0}) == "AL+010M200"
    # The stem needs the name, and says so.
    with pytest.raises(NamingTemplateError, match=r"\{polar\}"):
        template.render_point(campaign="c", sim="1", point={"alpha": 0.0})
    # The command line's default is this template on both subcommands.
    parser = _build_parser()
    for command in ("plan", "run"):
        args = parser.parse_args([command, "m.fs", "--name", "x"])
        assert args.point_name == MATRIX_POINT_NAME, command
    # The library default is untouched: a hand-built campaign keeps its names.
    assert NamingTemplate().point_name == "{point}"


def test_every_export_hangs_off_the_rendered_name():
    """``{name}`` inside an output name is the point's stem, whatever template made it."""
    template = NamingTemplate(point_name=MATRIX_POINT_NAME)
    stem = template.render_point(
        campaign="c", sim="3224", point={"alpha": 0.0}, mach=0.2, name="M200AL+000J+130"
    )
    rendered = template.render_output(
        "{name}_cp.txt", campaign="c", sim="3224", point={"alpha": 0.0}, mach=0.2, stem=stem
    )
    assert rendered == "P3224-M200AL+000J+130_cp.txt"
    # {name} is an OUTPUT placeholder: a point-name template naming it is refused.
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="unknown placeholder"):
        NamingTemplate(point_name="{name}")


def _campaign(tmp_path, *, mach=0.2, variables=None, order=None):
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    case = SimCase(
        sim_id="3207",
        aircraft="WB",
        velocity=68.058,
        mach=mach,
        geometry=str(geometry),
        sweep=SweepAxis(type="alpha", values=[-2.0]),
        recipe="steady",
        outputs=["{name}.txt"],
        variables=variables or {},
        condition_order=order or [],
    )
    return Campaign(name="camp", fs_version="26.120", fs_exe=sys.executable, sims=[case])


def _recipe(case, script):
    script.emit("OPEN", case.geometry)
    script.emit("START_SOLVER")
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", case.outputs[0])
    script.emit("CLOSE_FLIGHTSTREAM")


def _converged(case, execution, sim_dir):
    from pyflightstream.run import Assessment

    return Assessment(status=RunStatus.CONVERGED, iterations=10, residual=1e-6)


def test_the_record_names_the_template(tmp_path):
    """The record carries the template that rendered the names; an override records its own."""
    from pyflightstream.run import LocalExecutor

    class Stub(LocalExecutor):
        def __init__(self):
            super().__init__(fs_exe=sys.executable, hidden=True)

        def _argv(self, script_path):
            code = (
                "import pathlib, sys; "
                "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
                "[pathlib.Path(lines[i + 1]).write_text('LOADS') "
                "for i, line in enumerate(lines) if line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET']"
            )
            return [sys.executable, "-c", code, str(script_path)]

    workspace = CampaignWorkspace(
        tmp_path / "camp", naming=NamingTemplate(point_name=MATRIX_POINT_NAME)
    )
    run_campaign(
        _campaign(tmp_path), Stub(), workspace, assess=_converged, recipes={"steady": _recipe}
    )
    record = workspace.read_manifest()[0]
    assert record.point_name_template == "{polar}"
    assert record.outputs == ["datapoints/DP-M200AL-020/P3207-M200AL-020.txt"]
    assert record.script_path is not None and "P3207-M200AL-020" in record.script_path
    assert record.point_name == "M200AL-020"

    other = CampaignWorkspace(tmp_path / "other", naming=NamingTemplate(point_name="{sim}_{point}"))
    run_campaign(_campaign(tmp_path), Stub(), other, assess=_converged, recipes={"steady": _recipe})
    record = other.read_manifest()[0]
    assert record.point_name_template == "{sim}_{point}"
    assert record.outputs == ["datapoints/DP-M200AL-020/3207_M200AL-020.txt"]


def test_a_stated_advance_ratio_on_a_rotorless_row_reaches_the_name(tmp_path):
    """The author's 3224 was a wing-body at J 1.3 with no rotor meshed, and its name carried the
    J."""
    from pyflightstream.run import LocalExecutor

    class Stub(LocalExecutor):
        def __init__(self):
            super().__init__(fs_exe=sys.executable, hidden=True)

        def _argv(self, script_path):
            code = (
                "import pathlib, sys; "
                "lines = pathlib.Path(sys.argv[1]).read_text().splitlines(); "
                "[pathlib.Path(lines[i + 1]).write_text('LOADS') "
                "for i, line in enumerate(lines) if line == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET']"
            )
            return [sys.executable, "-c", code, str(script_path)]

    workspace = CampaignWorkspace(
        tmp_path / "camp", naming=NamingTemplate(point_name=MATRIX_POINT_NAME)
    )
    campaign = _campaign(
        tmp_path, variables={"ADVANCE_RATIO": "1.3"}, order=["MACH", "ALPHA", "ADVANCE_RATIO"]
    )
    run_campaign(campaign, Stub(), workspace, assess=_converged, recipes={"steady": _recipe})
    assert workspace.read_manifest()[0].outputs == [
        "datapoints/DP-M200AL-020J+130/P3207-M200AL-020J+130.txt"
    ]


# --- the QA lens of 2026-09-03: three properties no test discriminated --------------


def test_beta_and_the_swept_advance_ratio_reach_the_name():
    """A non-zero sideslip is written, and a swept J wins over a case-level one."""
    case = _case(
        ["MACH", "ALPHA", "BETA", "ADVANCE_RATIO"],
        flow={"MACH": 0.2},
        variables={"ADVANCE_RATIO": "1.3"},
    )
    assert point_name(case, {"alpha": -2.0, "beta": 3.5, "advance_ratio": 1.7}) == (
        "M200AL-020BE+035J+170"
    ), "the case-level J overrode the swept axis"
    assert point_name(case, {"alpha": 0.0, "beta": 0.0}) == "M200AL+000BE+000J+130"
