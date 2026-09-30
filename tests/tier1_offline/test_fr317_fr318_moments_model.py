"""Tier 1: the moments model is a setup key, linked to the vorticity drag on a rotor.

The evidence lines of FR-317 and FR-318 cite this module
(docs/srs/functional-requirements.md).

FR-317: ``moments_model`` states SET_ANALYSIS_MOMENTS_MODEL; unstated, the
script is byte-identical to the one the package wrote before the key existed.
FR-318: on a row turning a rotor, ``vorticity_drag_families`` with no
``moments_model`` implies VORTICITY (warned, recorded in the snapshot), and
``moments_model = PRESSURE`` beside it is refused at plan naming both keys.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import (
    CampaignConfigError,
    MeshImport,
    RawMeshConditions,
    ReferenceData,
    SimCase,
    SolverSettings,
    SweepAxis,
    TrailingEdgeMarking,
)
from pyflightstream.cases._setup_link import analysis_frame_and_moments, moments_model_of
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script, helpers
from tests.tier1_offline.test_workflows import rotor_case

BUILD = "26.124"


def _wing(tmp_path, **solver: object) -> SimCase:
    """A steady wing-body row over a saved geometry whose boundaries are W and B."""
    return SimCase(
        sim_id="6201",
        aircraft="WB",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[2.0]),
        variables={"WORKFLOW": "steady", "VELOCITY": "30.0"},
        geometry=str(tmp_path / "wb.obj"),
        inventory=("W", "B"),
        inventory_source="sidecar",
        mesh_import=MeshImport(units="METER"),
        raw_mesh_conditions=RawMeshConditions(trailing_edges=TrailingEdgeMarking(route="detect")),
        solver=SolverSettings(**solver),
        reference=ReferenceData(area=50.0, length=2.5, span_m=20.0, moment_point_m=(0.6, 0.0, 0.0)),
        point={"alpha": 2.0, "beta": 0.0},
        outputs=["AL+020.txt"],
    )


def _lines(case: SimCase) -> list[str]:
    script = Script(BUILD)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        build_script(case, script)
    return script.render().splitlines()


def test_an_unstated_moments_model_leaves_the_script_byte_identical(tmp_path):
    """FR-317 control: unstated and PRESSURE write the same bytes, as before the key."""
    unstated = _lines(_wing(tmp_path))
    pressure = _lines(_wing(tmp_path, moments_model="PRESSURE"))
    assert unstated == pressure
    assert "SET_ANALYSIS_MOMENTS_MODEL PRESSURE" in unstated


def test_a_stated_moments_model_changes_that_line_and_no_other(tmp_path):
    """FR-317: VORTICITY reaches SET_ANALYSIS_MOMENTS_MODEL, before START_SOLVER."""
    control = _lines(_wing(tmp_path))
    stated = _lines(_wing(tmp_path, moments_model="vorticity"))
    changed = [(a, b) for a, b in zip(control, stated, strict=True) if a != b]
    assert changed == [
        ("SET_ANALYSIS_MOMENTS_MODEL PRESSURE", "SET_ANALYSIS_MOMENTS_MODEL VORTICITY")
    ]
    assert stated.index("SET_ANALYSIS_MOMENTS_MODEL VORTICITY") < stated.index("START_SOLVER")


def test_a_moments_model_the_command_does_not_take_is_refused():
    """FR-317: the tokens are the command database's, PRESSURE and VORTICITY."""
    with pytest.raises(ValueError, match=r"PRESSURE, VORTICITY"):
        SolverSettings(moments_model="CIRCULATION")


def test_a_stated_moments_model_is_emitted_where_no_frame_is_placed():
    """FR-317: without a moment point the model is still stated; unstated, nothing is emitted."""
    stated = SimCase(
        sim_id="1",
        aircraft="A",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        solver=SolverSettings(moments_model="VORTICITY"),
    )
    script = Script(BUILD)
    analysis_frame_and_moments(stated, script, None, rotor=False)
    assert script.render().splitlines() == ["SET_ANALYSIS_MOMENTS_MODEL VORTICITY"]
    bare = Script(BUILD)
    analysis_frame_and_moments(
        stated.model_copy(update={"solver": SolverSettings()}), bare, None, rotor=False
    )
    assert bare.render().strip() == ""


def _families(moments_model: str | None = None) -> SimCase:
    solver = SolverSettings(vorticity_drag_families=["Blade"], moments_model=moments_model)
    return rotor_case().model_copy(update={"solver": solver})


def test_on_a_rotor_vorticity_drag_implies_vorticity_moments_warned_and_recorded():
    """FR-318: an unstated model follows the drag list on a rotor, warned and recorded."""
    case = _families()
    script = Script(BUILD)
    helpers.solver_settings(script, iterations=10)
    with pytest.warns(PyflightstreamWarning, match=r"vorticity_drag_families.*moments_model"):
        analysis_frame_and_moments(case, script, None, rotor=True)
    assert "SET_ANALYSIS_MOMENTS_MODEL VORTICITY" in script.render().splitlines()
    assert script.solver_setup is not None
    derived = script.solver_setup.model_dump(mode="json")["derived"]
    assert derived["moments_model"].startswith("VORTICITY"), derived
    assert "FR-318" in derived["moments_model"]


def test_on_a_rotor_pressure_moments_beside_vorticity_drag_are_refused():
    """FR-318: an explicit PRESSURE beside the drag list is refused, naming both keys."""
    with pytest.raises(CampaignConfigError) as refused:
        moments_model_of(_families("PRESSURE"), rotor=True)
    said = str(refused.value)
    assert "vorticity_drag_families" in said and "moments_model = PRESSURE" in said, said
    assert "7001" in said, said


def test_the_link_holds_only_on_a_rotor_and_only_with_a_drag_list():
    """FR-318 controls: no rotor, or no drag list, leaves the model as stated."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", PyflightstreamWarning)
        assert moments_model_of(_families(), rotor=False) == (None, False)
        bare = rotor_case()
        assert moments_model_of(bare, rotor=True) == (None, False)
        assert moments_model_of(_families("VORTICITY"), rotor=True) == ("VORTICITY", False)
        assert moments_model_of(_families("PRESSURE"), rotor=False) == ("PRESSURE", False)


def test_a_rotor_row_is_recognised_by_the_builder(tmp_path):
    """FR-318 through the builder: the unsteady_rotor row with a drag list states VORTICITY.

    It also pins the order the requirement states as its limit: the moments
    model precedes START_SOLVER, the vorticity drag list follows it.
    """
    case = rotor_case().model_copy(
        update={
            "geometry": str(tmp_path / "rotor.obj"),
            "inventory": ("Blade", "Hub"),
            "inventory_source": "sidecar",
            "mesh_import": MeshImport(units="METER"),
            "raw_mesh_conditions": RawMeshConditions(
                trailing_edges=TrailingEdgeMarking(route="detect")
            ),
            "reference": ReferenceData(area=1.0, length=0.1, span_m=1.0),
            "solver": SolverSettings(vorticity_drag_families=["Blade"]),
        }
    )
    script = Script(BUILD)
    with pytest.warns(PyflightstreamWarning, match="FR-318"):
        build_script(case, script)
    lines = script.render().splitlines()
    start = lines.index("START_SOLVER")
    assert lines.index("SET_ANALYSIS_MOMENTS_MODEL VORTICITY") < start
    drag = next(
        i for i, line in enumerate(lines) if line.startswith("SET_VORTICITY_DRAG_BOUNDARIES")
    )
    assert drag > start
