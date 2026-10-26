"""Retained direct CCS emitters and parsers after removal of matrix CCS rows."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases._ccs import CcsImportOptions
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import CommandArgumentError, Script, helpers
from pyflightstream.workspace.inputs import read_mesh_import
from pyflightstream.workspace.matrix import resolve_matrix
from tests.tier1_offline.test_matrix_run import RECIPES, make_library, write_matrix

BUILD = "26.124"


@pytest.mark.parametrize(
    "start,end", [(0, 0), (90, 45), (-1, 90), (0, 361), (float("nan"), 360), (0, float("inf"))]
)
def test_p0420_revolution_angles_must_form_a_forward_turn(start, end):
    """Only the documented interval 0 <= start < end <= 360 is admitted."""
    with pytest.raises(ValueError, match="0 <= start_angle_deg < end_angle_deg <= 360"):
        CcsImportOptions(kind="revolution", component=1, start_angle_deg=start, end_angle_deg=end)


@pytest.mark.parametrize("start,end", [(0, 360), (90, 180)])
def test_p0420_revolution_angles_accept_full_and_partial_turns(start, end):
    spec = CcsImportOptions(
        kind="revolution", component=1, start_angle_deg=start, end_angle_deg=end
    )
    assert (spec.start_angle_deg, spec.end_angle_deg) == (start, end)


#: One steady row naming a CCS file; ``{tail}`` appends row keys.
ROW = (
    "7001 | TestCcs | CCS | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
    "| 003 | {build} |  0 | 1 | OUTPUTS: loads_{{point}}.txt "
    "/ GEOMETRY: {geometry}{tail}"
)


def _fmt(value: float) -> str:
    return f"{value + 0.0:.6f}"


def _airfoil(chord: float = 1.0, n: int = 7) -> list[tuple[float, float]]:
    """A closed symmetric section, trailing edge upper, leading edge, trailing edge lower."""
    xs = [0.5 * (1.0 - math.cos(math.pi * i / (n - 1))) for i in range(n)]

    def half(x: float) -> float:
        return 0.6 * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3)

    upper = [(chord * x, chord * half(x)) for x in reversed(xs)]
    lower = [(chord * x, -chord * half(x)) for x in xs[1:]]
    return upper + lower


def _wing(name: str) -> list[str]:
    lines = [f"Component;{name}", "LiftingSurface;true"]
    for y in (0.0, 4.0):
        flat = [f"{_fmt(x)};{_fmt(y)};{_fmt(z)}" for x, z in _airfoil()]
        lines.append("CrossSection;" + ";".join(flat))
    return lines


def _fuselage(name: str, extra: tuple[str, ...] = ()) -> list[str]:
    lines = [f"Component;{name}", "LiftingSurface;false", *extra]
    for x in (0.1, 1.0, 2.0):
        radius = 0.5 * math.sin(math.pi * x / 2.1) ** 0.5
        points = [
            f"{_fmt(x)};{_fmt(radius * math.cos(t))};{_fmt(radius * math.sin(t))}"
            for t in (2.0 * math.pi * k / 8 for k in range(9))
        ]
        lines.append("CrossSection;" + ";".join(points))
    return lines


def _revolution(name: str) -> list[str]:
    profile = [
        f"{_fmt(x)};{_fmt(0.4 * math.sqrt(max(0.0, 1.0 - ((x - 1.5) / 1.5) ** 2)))};0.000000"
        for x in (3.0 * k / 6 for k in range(7))
    ]
    return [
        f"Component;{name}",
        "LiftingSurface;false",
        "RevolveBody;0.0;0.0;0.0;1.0;0.0;0.0;0.0;360.0",
        "CrossSection;" + ";".join(profile),
    ]


def ccs_file(*components: list[str]) -> str:
    body: list[str] = ["Aircraft;PYFS_TEST", "Units;Meter", ""]
    for component in components:
        body.extend(component)
        body.append("")
    return "\n".join(body)


#: One file, three components: 1 wing, 2 fuselage, 3 body of revolution.
THREE = ccs_file(_wing("CCS_WING"), _fuselage("CCS_FUS"), _revolution("CCS_REV"))


def _sidecar(boundaries: list[str], ccs: str, units: str = "METER") -> str:
    names = ", ".join(f'"{name}"' for name in boundaries)
    return f'boundaries = [{names}]\n\n[import]\nunits = "{units}"\n\n[import.ccs]\n{ccs}'


def _library(tmp_path, stem: str, text: str, sidecar: str, suffix: str = ".csv"):
    workspace = make_library(tmp_path, register_build=(BUILD, Path(sys.executable).as_posix()))
    geometries = workspace.inputs_dir / "geometries"
    (geometries / f"{stem}{suffix}").write_text(text, encoding="utf-8")
    (geometries / f"{stem}.boundaries.toml").write_text(sidecar, encoding="utf-8")
    return workspace


def _case(tmp_path, workspace, geometry: str, tail: str = ""):
    """Bind the one row through the plan's own binding and return its case at alpha 0."""
    matrix = write_matrix(
        tmp_path / "ccs.fs", [ROW.format(build=BUILD, geometry=geometry, tail=tail)]
    )
    resolved = resolve_matrix(matrix, workspace, name="matrix", fs_version=BUILD, recipes=RECIPES)
    case = resolved.campaign.sims[0]
    return case.model_copy(update={"point": {"alpha": 0.0}, "outputs": ["loads_a+00.0.txt"]})


def _built(case) -> tuple[Script, list[str]]:
    script = Script(BUILD)
    build_script(case, script)
    return script, script.render().splitlines()


def _row_case(tmp_path, stem: str, ccs: str, boundaries: list[str], **kwargs):
    """Construct a direct Python emitter case; matrix CCS rows were removed by D7."""
    from tests.tier1_offline.test_workflows import steady_case

    tmp_path.mkdir(parents=True, exist_ok=True)
    geometry = tmp_path / f"{stem}.csv"
    geometry.write_text(kwargs.pop("text", THREE), encoding="utf-8")
    sidecar = tmp_path / f"{stem}.boundaries.toml"
    sidecar.write_text(_sidecar(boundaries, ccs, kwargs.pop("units", "METER")), encoding="utf-8")
    return steady_case().model_copy(
        update={
            "geometry": str(geometry),
            "mesh_import": read_mesh_import(sidecar),
            "inventory": tuple(boundaries),
        }
    )


def _index(lines: list[str], line: str) -> int:
    assert line in lines, f"{line!r} is not in the script:\n" + "\n".join(lines[:60])
    return lines.index(line)


def _curve_route(lines: list[str], geometry: str, component: int) -> int:
    """Assert the curve prelude, in order, and return the index of the selection line."""
    initialize = _index(lines, "CAD_CREATE_INITIALIZE")
    imported = _index(lines, f"CAD_CREATE_IMPORT_CURVE_CCS METER 1 {component}")
    assert lines[imported + 1] == geometry
    selected = _index(lines, "CAD_CREATE_CURVE_SELECT -1")
    assert initialize < imported < selected
    return selected


# --- CCS-1: the wing, the fuselage and the body of revolution ---------------------------


@pytest.mark.requirement("FR-241")
def test_p0320_ccs1_the_three_emitters_are_the_route_each_kind_takes(tmp_path):
    """P0320-CCS1-WING, -FUSELAGE, -REVOLUTION: each public emitter refuses another kind."""
    from pyflightstream.cases.ccs_fuselage import emit_ccs_fuselage
    from pyflightstream.cases.ccs_revolution import emit_ccs_revolution
    from pyflightstream.cases.ccs_wing import emit_ccs_wing

    case = _row_case(tmp_path, "wing", 'kind = "wing"\ncomponent = 1\n', ["WING"])
    for emitter in (emit_ccs_fuselage, emit_ccs_revolution):
        with pytest.raises(CampaignConfigError, match="wing"):
            emitter(Script(BUILD), case)
    script = Script(BUILD)
    emit_ccs_wing(script, case)
    assert "CAD_CREATE_WING_MESH_FROM_CCS WING TRUE SHARP TRUE C2 C0" in script.render()


# --- CCS-2: the control surface of a CCS wing -------------------------------------------

AILERON = (
    '[[import.ccs.control_surfaces]]\nname = "AIL"\nv0 = 0.5\nv1 = 0.9\nu0 = 0.25\n'
    "u1 = 0.25\nhinge_height = 0.5\nangle_deg = 20.0\nslot_gap_pct = 1.0\n"
)


@pytest.mark.requirement("FR-298")
def test_p0420_direct_wing_emitter_refuses_real_control_surfaces(tmp_path):
    """The direct public route carries the same measured refusal as the workflow."""
    real = AILERON.replace("v0 = 0.5\nv1 = 0.9\n", "v0 = 2.0\nv1 = 3.6\n") + (
        'space = "REAL"\naxis = "Y"\n'
    )
    case = _row_case(tmp_path, "wing", 'kind = "wing"\ncomponent = 1\n' + real, ["WING"])
    from pyflightstream.cases.ccs_wing import emit_ccs_wing

    script = Script(BUILD)
    before = script.render()
    with pytest.raises(CampaignConfigError, match="RPT-097"):
        emit_ccs_wing(script, case)
    assert script.render() == before


def _real_case(tmp_path):
    real = AILERON.replace("v0 = 0.5\nv1 = 0.9\n", "v0 = 2.0\nv1 = 3.6\n") + (
        'space = "REAL"\naxis = "Y"\n'
    )
    return _row_case(tmp_path, "wing", 'kind = "wing"\ncomponent = 1\n' + real, ["WING"])


@pytest.mark.parametrize("build", ["26.100", "26.101"])
def test_p0320_ccs2_a_build_with_the_eight_argument_grammar_refuses_the_line(tmp_path, build):
    """P0320-CCS2-CONTROL-SURFACE: refused at the emitter where SPACE and AXIS do not exist."""
    from pyflightstream.cases.ccs_wing import emit_ccs_wing

    case = _row_case(tmp_path, "wing", 'kind = "wing"\ncomponent = 1\n' + AILERON, ["WING"])
    with pytest.raises(CommandArgumentError, match="8 arguments"):
        emit_ccs_wing(Script(build), case)


# --- FR-1600: the row deflects a morphing surface of a CCS wing ----------------------------

MORPHING = (
    '[[import.ccs.morphing_surfaces]]\nname = "FLAP"\nv0 = 0.1\nv1 = 0.4\nu0 = 0.25\n'
    "u1 = 0.25\nhinge_height = 0.5\n"
)


# --- G35: the row chooses the direction of a Relaxed_TE shedding line --------------------

RELAXED_FUSELAGE = ccs_file(_fuselage("CCS_FUS", ("Relaxed_TE;0.5;0.2;0.8",)))
FILE_ROUTE = 'kind = "file"\n'


def _file_case(tmp_path, text=RELAXED_FUSELAGE, tail="", boundaries=("CCS_FUS",)):
    return _row_case(
        tmp_path, "g35", FILE_ROUTE, list(boundaries), text=text, units="FILE", tail=tail
    )


def _ccs_import_file(lines: list[str]) -> str:
    start = _index(lines, "CCS_IMPORT")
    assert lines[start + 1 : start + 4] == [
        "CLOSE_COMPONENT_ENDS DISABLE",
        "UPDATE_PROPERTIES DISABLE",
        "CLEAR_EXISTING ENABLE",
    ]
    assert lines[start + 4].startswith("FILE ")
    return lines[start + 4].removeprefix("FILE ")


# --- G35: the relaxed trailing-edge specification, settled against FSM-26.124 p.85 ----------


def test_p0320_g35_the_manuals_line_carries_three_values_before_the_direction():
    """P0320-G35-SHEDDING: ``Relaxed_TE;u;v1;v2;direction`` (FSM-26.124 p.85), the defect fixed.

    The helper read a four-number text as four leading values with no direction,
    so ``0.5;0.2;0.8;1`` (u, v1, v2 and the azimuth digit) was restated as
    ``0.5;0.2;0.8;1;1``, one value too many.
    """
    edge = helpers.parse_relaxed_trailing_edge("0.5;0.2;0.8;1")
    assert edge.fields == ("0.5", "0.2", "0.8")
    assert edge.direction == "AZIMUTH"
    assert edge.with_shedding("AZIMUTH").render() == "0.5;0.2;0.8;1"
    three = helpers.parse_relaxed_trailing_edge("0.5;0.2;0.8")
    assert three.direction is None and three.render() == "0.5;0.2;0.8"
    assert three.with_shedding(1).render() == "0.5;0.2;0.8;1"


def test_p0320_g35_the_whole_line_keeps_its_keyword():
    """P0320-G35-SHEDDING: the line as a CCS file writes it reads and renders whole."""
    edge = helpers.parse_relaxed_trailing_edge("Relaxed_TE;0.5;0.2;0.8")
    assert edge.fields == ("0.5", "0.2", "0.8") and edge.direction is None
    assert edge.with_shedding("AZIMUTH").render() == "Relaxed_TE;0.5;0.2;0.8;1"
    stated = helpers.parse_relaxed_trailing_edge("Relaxed_TE;0.5;0.2;0.8;0")
    assert stated.direction == "AXIAL" and stated.render() == "Relaxed_TE;0.5;0.2;0.8;0"


@pytest.mark.parametrize("text", ["0.5;0.2", "Relaxed_TE;0.5;0.2", "0.5;0.2;0.8;1;0"])
def test_p0320_g35_a_value_count_the_manual_does_not_print_is_refused(text):
    """P0320-G35-SHEDDING: three values, or four with the direction, and nothing else."""
    with pytest.raises(CommandArgumentError) as refusal:
        helpers.parse_relaxed_trailing_edge(text)
    assert "3" in str(refusal.value) and "4" in str(refusal.value)


def test_p0320_g35_the_sidecar_table_reads_through_the_import_reader(tmp_path):
    """P0320-G35-SHEDDING: ``[import.ccs]`` is read by the reader every import table has."""
    path = tmp_path / "g35.boundaries.toml"
    path.write_text(_sidecar(["CCS_FUS"], FILE_ROUTE, units="FILE"), encoding="utf-8")
    spec = read_mesh_import(path)
    assert spec is not None and spec.units == "FILE"
    assert spec.ccs is not None and spec.ccs.kind == "file"
