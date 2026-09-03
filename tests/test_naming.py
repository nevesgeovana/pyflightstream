"""PFS-2029.19: the author's naming convention names every point and its exports.

Her third sentence of 2026-09-02: the output names were bad, look at how
her master's scripts did it. Measured there: the case name carried the
polar, the Mach, the angles and the advance ratio, fixed width, and every
export hung off it. The matrix command line names points that way unless
told otherwise; the library default stays ``{point}`` so hand-built
campaigns, goldens and manifests are what they were.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.run import RunStatus, run_campaign
from pyflightstream.run.cli import _build_parser
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.naming import (
    MATRIX_POINT_NAME,
    NamingTemplate,
    NamingTemplateError,
    polar_name,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_the_default_template_is_her_convention():
    """POLAR-<sim>_M<mach*100>AL<alpha*10>BE<beta*10>[J<J*100>], fixed width."""
    template = NamingTemplate(point_name=MATRIX_POINT_NAME)
    assert template.render_point(campaign="c", sim="3207", point={"alpha": -2.0}, mach=0.2) == (
        "POLAR-3207_M20AL-020BE+000"
    ), "row 3207 at Mach 0.20 and alpha -2; beta not swept is zero"
    assert (
        template.render_point(
            campaign="c",
            sim="9001",
            point={"alpha": 0.0, "beta": 0.0},
            mach=0.1441,
            advance_ratio=1.7,
        )
        == "POLAR-9001_M14AL+000BE+000J+170"
    ), "a rotor point at Mach 0.1441 and J 1.7"
    assert polar_name("3224", 0.2, 0.0, 0.0, 1.3) == "POLAR-3224_M20AL+000BE+000J+130"
    # Her fixed widths sort: alpha 10 and alpha -2 keep their four characters.
    assert polar_name("3207", 0.2, 10.0) == "POLAR-3207_M20AL+100BE+000"
    # The convention needs the Mach number, and says so.
    with pytest.raises(NamingTemplateError, match=r"\{polar\}.*Mach"):
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
        campaign="c", sim="3224", point={"alpha": 0.0}, mach=0.2, advance_ratio=1.3
    )
    rendered = template.render_output(
        "{name}_cp.txt", campaign="c", sim="3224", point={"alpha": 0.0}, mach=0.2, stem=stem
    )
    assert rendered == "POLAR-3224_M20AL+000BE+000J+130_cp.txt"
    # {name} is an OUTPUT placeholder: a point-name template naming it is refused.
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="unknown placeholder"):
        NamingTemplate(point_name="{name}")


def _campaign(tmp_path, *, mach=0.2, variables=None):
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
    assert record.outputs == ["raw/POLAR-3207_M20AL-020BE+000.txt"]
    assert record.script_path is not None and "POLAR-3207_M20AL-020BE+000" in record.script_path

    other = CampaignWorkspace(tmp_path / "other", naming=NamingTemplate(point_name="{sim}_{point}"))
    run_campaign(_campaign(tmp_path), Stub(), other, assess=_converged, recipes={"steady": _recipe})
    record = other.read_manifest()[0]
    assert record.point_name_template == "{sim}_{point}"
    assert record.outputs == ["raw/3207_a-02.0.txt"]


def test_a_stated_advance_ratio_on_a_rotorless_row_reaches_the_name(tmp_path):
    """Her 3224 was a wing-body at J 1.3 with no rotor meshed, and its name carried the J."""
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
    campaign = _campaign(tmp_path, variables={"ADVANCE_RATIO": "1.3"})
    run_campaign(campaign, Stub(), workspace, assess=_converged, recipes={"steady": _recipe})
    assert workspace.read_manifest()[0].outputs == ["raw/POLAR-3207_M20AL-020BE+000J+130.txt"]


# --- the QA lens of 2026-09-03: three properties no test discriminated --------------


def test_beta_and_the_swept_advance_ratio_reach_the_name():
    """A non-zero sideslip is rendered, and a swept J wins over a case-level one."""
    from pyflightstream.workspace.naming import _values

    assert polar_name("3207", 0.2, -2.0, 3.5) == "POLAR-3207_M20AL-020BE+035"
    values = _values("camp", "3207", {"alpha": -2.0, "beta": 3.5, "advance_ratio": 1.7}, 0.2, 1.3)
    assert values["advance_ratio"] == 1.7, "the case-level J overrode the swept axis"
    assert values["polar"] == "POLAR-3207_M20AL-020BE+035J+170"
    assert (
        _values("camp", "3207", {"alpha": 0.0}, 0.2, 1.3)["polar"]
        == "POLAR-3207_M20AL+000BE+000J+130"
    )
