"""Tier 1: a setup selects the surfaces, the units and the loads of the analysis (0.27.0, G09).

Three setup keys, each reaching its own command through the command database for
the row's build, all on a STEADY row only:

* ``analysis_families`` -> ``SET_SOLVER_ANALYSIS_BOUNDARIES``: the families that
  enter the loads, named as the geometry names them and resolved to indices;
* ``load_units`` -> ``SET_LOADS_AND_MOMENTS_UNITS``: the unit the loads table
  prints, one of the five the command takes;
* ``inviscid_loads`` -> ``SET_INVISCID_LOADS``: the loads without the viscous part.

Each is an analysis-phase command, so it follows ``START_SOLVER`` and precedes the
exports, on every point of a sweep. A row of an unsteady run type stating any of
them is refused: set after the solve starts, a march's per-step exports would not
see them. A point whose loads table is not in coefficients writes no polar row.
"""

from __future__ import annotations

import json

import pytest

from pyflightstream.cases import CampaignConfigError, SolverSettings, case_at_point
from pyflightstream.cases.workflows import build_script, build_steady_sweep
from pyflightstream.script import Script
from pyflightstream.workspace.inputs import InputArtifactError
from tests.tier1_offline.test_rel0250_f04_advanced_setup import setup_case
from tests.tier1_offline.test_workflows import _wb_geometry, rotor_case, steady_case, unsteady_case

#: (key, TOML value, the lines it emits). W is boundary 1 of the wing-body file and
#: P is not in it: a family the geometry lacks is left out, as for the other lists.
KEYS = [
    ("load_units", '"NEWTONS"', ["SET_LOADS_AND_MOMENTS_UNITS NEWTONS"]),
    ("inviscid_loads", "true", ["SET_INVISCID_LOADS ENABLE"]),
    ("analysis_families", '["W", "P"]', ["SET_SOLVER_ANALYSIS_BOUNDARIES 1", "1"]),
]
COMMANDS = ("SET_LOADS_AND_MOMENTS_UNITS", "SET_SOLVER_ANALYSIS_BOUNDARIES", "SET_INVISCID_LOADS")


def _render(case, build="26.124") -> list[str]:
    script = Script(build)
    build_script(case, script)
    return script.render().splitlines()


def _with_geometry(case, tmp_path):
    return case.model_copy(update={"geometry": str(_wb_geometry(tmp_path))})


@pytest.mark.parametrize(("key", "value", "emitted"), KEYS, ids=[key for key, _, _ in KEYS])
def test_g09_each_setup_key_emits_its_command_after_the_solve(tmp_path, key, value, emitted):
    """Once, after START_SOLVER and before the first export, on 26.124."""
    case = _with_geometry(setup_case(tmp_path, f"{key} = {value}\n"), tmp_path)
    lines = _render(case)
    at = [index for index, line in enumerate(lines) if line == emitted[0]]
    assert len(at) == 1, f"{key}: {emitted[0]!r} appears {len(at)} times"
    assert lines[at[0] : at[0] + len(emitted)] == emitted, lines[at[0] : at[0] + 3]
    first_export = next(i for i, line in enumerate(lines) if line.startswith(("EXPORT_", "SAVEAS")))
    assert lines.index("START_SOLVER") < at[0] < first_export, (key, at[0], first_export)


@pytest.mark.parametrize(
    ("alias", "value", "line"),
    [
        (
            "set_loads_and_moments_units",
            '"KILO-NEWTONS"',
            "SET_LOADS_AND_MOMENTS_UNITS KILO-NEWTONS",
        ),
        ("set_inviscid_loads", '"DISABLE"', "SET_INVISCID_LOADS DISABLE"),
        ("set_solver_analysis_boundaries", '["B"]', "SET_SOLVER_ANALYSIS_BOUNDARIES 1"),
    ],
)
def test_g09_the_solvers_own_spellings_are_read(tmp_path, alias, value, line):
    """A preset transcribed from a session names the command; it reaches the same line."""
    case = _with_geometry(setup_case(tmp_path, f"{alias} = {value}\n"), tmp_path)
    assert line in _render(case), alias


def test_g09_every_point_of_a_steady_sweep_restates_them(tmp_path):
    """A warm sweep is one script; each point's solve is followed by its selections."""
    base = _with_geometry(
        setup_case(tmp_path, 'load_units = "NEWTONS"\ninviscid_loads = true\n'), tmp_path
    )
    cases = [case_at_point(base, {"alpha": alpha}) for alpha in (0.0, 2.0, 4.0)]
    script = Script("26.124")
    build_steady_sweep(cases, script)
    lines = script.render().splitlines()
    starts = [index for index, line in enumerate(lines) if line == "START_SOLVER"]
    units = [
        index for index, line in enumerate(lines) if line == "SET_LOADS_AND_MOMENTS_UNITS NEWTONS"
    ]
    assert len(starts) == len(units) == 3, (starts, units)
    assert all(start < unit for start, unit in zip(starts, units, strict=True)), (starts, units)


def test_g09_a_unit_the_command_does_not_know_is_refused(tmp_path):
    """Refused when the preset is read, naming the five units the command takes."""
    with pytest.raises(InputArtifactError) as raised:
        setup_case(tmp_path, 'load_units = "FOO"\n')
    text = str(raised.value)
    assert "load_units" in text, text
    assert "COEFFICIENTS, NEWTONS, KILO-NEWTONS, POUND-FORCE, KILOGRAM-FORCE" in text, text


def test_g09_analysis_families_the_geometry_lacks_are_refused_naming_the_key(tmp_path):
    """No family resolves: refused at plan; an empty list: refused when the file is read."""
    case = steady_case(geometry=str(_wb_geometry(tmp_path))).model_copy(
        update={"solver": SolverSettings(analysis_families=["P", "N"])}
    )
    with pytest.raises(CampaignConfigError, match="analysis_families") as raised:
        _render(case)
    assert "carries none of them" in str(raised.value), raised.value
    with pytest.raises(InputArtifactError, match="analysis_families = \\[\\]"):
        setup_case(tmp_path, "analysis_families = []\n")


@pytest.mark.parametrize("make", [unsteady_case, rotor_case], ids=["unsteady", "unsteady_rotor"])
@pytest.mark.parametrize(
    "solver",
    [
        {"load_units": "NEWTONS"},
        {"inviscid_loads": True},
        {"analysis_families": ["W"]},
    ],
    ids=["load_units", "inviscid_loads", "analysis_families"],
)
def test_g09_the_keys_are_refused_on_an_unsteady_row(make, solver):
    """Set after the solve starts, a march's step exports would not see them."""
    case = make().model_copy(update={"solver": SolverSettings(**solver)})
    with pytest.raises(CampaignConfigError) as raised:
        _render(case)
    text = str(raised.value)
    (key,) = solver
    assert key in text and repr(case.recipe) in text, text


def test_g09_a_preset_that_says_nothing_emits_none_of_the_three(tmp_path):
    """The control, and the state of every tier-3 setup: none of the three commands."""
    lines = _render(_with_geometry(setup_case(tmp_path, "iterations = 250\n"), tmp_path))
    emitted = [line for line in lines if line.split(" ")[0] in COMMANDS]
    assert emitted == [], emitted


def test_g09_a_point_exported_in_newtons_writes_no_coefficient_product(tmp_path):
    """The polar sums coefficients by name; a table in Newtons is skipped, naming load_units."""
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_post_products import _steady_workspace_with_provenance

    written = {}
    for units in ("Coefficients", "Newtons"):
        workspace = _steady_workspace_with_provenance(tmp_path / units)
        loads = workspace.sim_dir("3207") / "outputs" / "POLAR-3207_M20AL-020BE+000.txt"
        text = loads.read_text(encoding="utf-8")
        loads.write_text(
            text.replace("Force Units: Coefficients", f"Force Units: {units}").replace(
                "Moment Units: Coefficients",
                "Moment Units: " + ("Newton-Meter" if units == "Newtons" else "Coefficients"),
            ),
            encoding="utf-8",
        )
        write_campaign_products(workspace)
        products = workspace.root / "post" / "products"
        manifest = json.loads((products / "products.json").read_text(encoding="utf-8"))
        written[units] = (manifest, sorted(path.name for path in products.rglob("*.csv")))
    control, _ = written["Coefficients"]
    assert "runs/camp/sim_3207/AL-020" not in control["skipped"], control["skipped"]
    newtons, _ = written["Newtons"]
    why = newtons["skipped"].get("runs/camp/sim_3207/AL-020", "")
    assert "load_units" in why and "Newtons" in why, newtons["skipped"]
