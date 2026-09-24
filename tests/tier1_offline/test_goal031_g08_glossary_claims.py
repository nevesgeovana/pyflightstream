"""Tier 1, 0.27.0 item G08: a key the glossary says SETS something reaches the script.

THE FINDING THIS HOLDS, from an independent reading of block 7: ``INPUTS.md``
listed ``ROTOR_SHEDDING`` under "What it sets" as the direction a rotor's
relaxed wake sheds in, and two rotor rows stating ``AXIAL`` and ``AZIMUTH``
built byte-identical scripts. A user following the page to change the wake
ran the wake unchanged. No check existed that could have noticed, because the
glossary test asks whether a key HAS a meaning and never whether the meaning
is true.

WHAT IS HELD, key by key, for the two tables whose keys a run's builders read
off the case: the row keys of the matrix and the solver settings of the setup.
Each key is built twice, once with each of two values, in a case shaped so the
value can matter (a geometry for a key that names families, a disc for a disc
key, a sweep for a cold start), on every build its run type covers. Then:

* a row that does not say "No line of the script carries its value" must name
  a key whose two scripts DIFFER on at least one build, or whose one value
  refuses where the other builds (a refusal is what some keys decide);
* a row that says it must name a key whose two scripts are byte-identical on
  every build: the sentence is a claim too, and a claim the script contradicts
  is as wrong as the one it replaced.

Every key of either table must have its two values here. A key the package
gains without them fails, which is the point: a new key arrives either
reaching the script or saying what takes its value instead.

A VARIATION IS A MODEL OF THE ROUTE, said plainly. A key the matrix reader or
the plan turns into a case field (``ALPHA`` into the point, ``ROTATE`` into
the rotations, ``PROFILE`` into the resolved file, ``RESTART`` into the owed
step count) is varied where the builder reads it, and each such variation says
which field stands for the key.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import (
    ActuatorBlock,
    FrameSpec,
    PprocSpec,
    RawCommand,
    ReferenceData,
    SimCase,
    SolverSettings,
    case_at_point,
)
from pyflightstream.cases.workflows import (
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    ROW_KEY_MEANINGS,
    WORKFLOWS,
    build_script,
    build_steady_sweep,
    covered_builds,
    select_workflow,
)
from pyflightstream.post.guides import input_glossary_markdown
from pyflightstream.run import _is_cold_start
from pyflightstream.script import Script
from tests.tier1_offline.test_goal031_g08_input_glossary import parsed_page
from tests.tier1_offline.test_rotor_by_alias import saved_simulation, two_rotor_case
from tests.tier1_offline.test_workflows import (
    rotor_case,
    steady_case,
    unsteady_case,
    unsteady_case_full,
)

#: The words a row says when no line of the script carries its key's value.
NO_SCRIPT_LINE = "No line of the script carries its value"

ROW_KEYS = ("matrix", "The row keys, by run type")
SETTINGS = ("setup", "Solver settings")

Make = Callable[[Path], SimCase]


@dataclass(frozen=True)
class Variation:
    """Two cases that differ in one key's value, and the route they are built by.

    ``sweep`` builds the steady sweep's one script from three points, with the
    cold flag the run layer reads off the row: the route of ``COLD_START``,
    which a single point never takes.
    """

    first: Make
    second: Make
    sweep: bool = False


# --- the shapes the variations stand on --------------------------------------

HUB = FrameSpec(name="HUB", origin=(1.0, 0.0, 0.0))
NAC = FrameSpec(name="NAC", origin=(0.4, 0.0, 0.1))
PROP = ActuatorBlock(frame="HUB", axis="X", tip_radius_m=0.5, hub_radius_m=0.1, blades=3)
#: A moment point, the three body axes and a rotor diameter: what a rate, a
#: section frame and an advance ratio each need of the reference.
REFERENCE = ReferenceData(
    area=10.0,
    length=1.2,
    rotor_diameter=3.6576,
    moment_point_m=(2.0, 0.0, 0.5),
    body_axes={"roll": "X", "pitch": "Y", "yaw": "Z"},
)
TWO_FAMILIES = PprocSpec.model_validate(
    {"sections": {"distributions": [{"families": ["Wing", "Tail"], "planes": ["XZ"]}]}}
)
THREE_OUTPUTS = ["loads_a+00.0.txt", "forces_a+00.0.txt", "loads_a+00.0_log.txt"]


def _wing(tmp: Path, name: str = "wing.fsm") -> str:
    return str(saved_simulation(tmp / name, ["Wing", "Body", "Base"]))


def _on_wing(tmp: Path, case: SimCase, **update: object) -> SimCase:
    return case.model_copy(update={"geometry": _wing(tmp), "reference": REFERENCE, **update})


def _stated(case: SimCase, **variables: str) -> SimCase:
    return case.model_copy(update={"variables": {**case.variables, **variables}})


def _with_disc(case: SimCase, **update: object) -> SimCase:
    blocks = {"PROP": PROP, "FAN": PROP}
    return case.model_copy(update={"frames": [HUB], "actuators": blocks, **update})


def _moved(tmp: Path, field: str, record: dict[str, str]) -> SimCase:
    """A wing moved by one record: ``ROTATE`` and ``TRANSLATE`` reach the case as these."""
    return _on_wing(
        tmp, steady_case(), frames=[NAC], aliases={"Wing": ["Wing"]}, **{field: [record]}
    )


def _azimuthal_clock(tmp: Path, **variables: str) -> SimCase:
    """The two-rotor row on the azimuthal clock, whose step is the clock motion's."""
    case = two_rotor_case(tmp)
    kept = {k: v for k, v in case.variables.items() if k not in ("DELTA_TIME", "TIME_ITERATIONS")}
    kept.update({"DELTA_THETA": "10", "REVOLUTIONS": "2", **variables})
    return case.model_copy(update={"variables": kept})


def _continuing(restart: str, owed: str) -> SimCase:
    """A continuation as the plan leaves it: the saved file and the steps it owes."""
    return unsteady_case(
        RESTART=restart,
        **{RESTART_FROM_VARIABLE: "saved/point.fsm", RESTART_ITERATIONS_VARIABLE: owed},
    )


def _profile(tmp: Path, stem: str) -> SimCase:
    """PROFILE as the plan resolves it: the stem, and the file of that stem."""
    path = tmp / f"{stem}.txt"
    path.write_text("0.10,1.0\n0.50,2.0\n", encoding="utf-8")
    case = steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", PROFILE=stem)
    return _with_disc(case, actuator_profile=str(path))


def _freestream(tmp: Path, stem: str, vx: float) -> SimCase:
    """FREESTREAM as the plan resolves it: the stem, and a STRUCTURED field of that stem."""
    path = tmp / f"{stem}.txt"
    rows = [f"0.0 {y} {z} {vx} 0.0 0.0" for y in (-2.0, 2.0) for z in (-1.0, 1.0)]
    path.write_text("2 2\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return steady_case(FREESTREAM=stem).model_copy(update={"freestream_profile": str(path)})


def _raw(line: str) -> SimCase:
    """RAW reaches the case as its raw commands; the reader takes it out of the cell."""
    return steady_case().model_copy(
        update={"raw_commands": [RawCommand(command=line, before="exec")]}
    )


def _rows(
    make: Callable[..., SimCase], key: str, first: str, second: str, **context: str
) -> Variation:
    """The common shape: one factory, the key stated at two values beside ``context``."""
    return Variation(
        lambda _: make(**{**context, key: first}), lambda _: make(**{**context, key: second})
    )


#: TWO VALUES OF EVERY ROW KEY, in a case where the value can matter.
ROW_KEY_VARIATIONS: dict[str, Variation] = {
    "GEOMETRY": Variation(
        lambda tmp: steady_case(geometry=_wing(tmp, "a.fsm")),
        lambda tmp: steady_case(geometry=_wing(tmp, "b.fsm")),
    ),
    "SYMMETRY": _rows(steady_case, "SYMMETRY", "NONE", "MIRROR"),
    "SYMMETRY_LOADS": _rows(steady_case, "SYMMETRY_LOADS", "true", "false"),
    # The point carries a swept or held angle; the key is read where it does not.
    "ALPHA": Variation(
        lambda _: steady_case(ALPHA="0.0").model_copy(update={"point": {}}),
        lambda _: steady_case(ALPHA="4.0").model_copy(update={"point": {}}),
    ),
    "BETA": _rows(steady_case, "BETA", "0.0", "4.0"),
    # A section distribution naming a family the wing lacks: skipped or refused.
    "IGNORE_MISSING_FAMILIES": Variation(
        lambda tmp: _on_wing(tmp, steady_case(IGNORE_MISSING_FAMILIES="true"), pproc=TWO_FAMILIES),
        lambda tmp: _on_wing(tmp, steady_case(IGNORE_MISSING_FAMILIES="false"), pproc=TWO_FAMILIES),
    ),
    "EXPORT_LOG": Variation(
        lambda _: _stated(unsteady_case_full(), EXPORT_LOG="true"),
        lambda _: _stated(unsteady_case_full(), EXPORT_LOG="false"),
    ),
    "PERIODIC_COPIES": _rows(steady_case, "PERIODIC_COPIES", "4", "6", SYMMETRY="PERIODIC"),
    "BASE_REGIONS": Variation(
        lambda tmp: _on_wing(tmp, steady_case(BASE_REGIONS="Base")),
        lambda tmp: _on_wing(tmp, steady_case(BASE_REGIONS="Body")),
    ),
    "ROTATE": Variation(
        lambda tmp: _moved(tmp, "rotations", {"ANGLE": "-2", "AXIS": "NAC-Z", "ALIAS": "Wing"}),
        lambda tmp: _moved(tmp, "rotations", {"ANGLE": "3", "AXIS": "NAC-Z", "ALIAS": "Wing"}),
    ),
    "TRANSLATE": Variation(
        lambda tmp: _moved(
            tmp, "translations", {"DISTANCE": "0.05", "AXIS": "NAC-X", "ALIAS": "Wing"}
        ),
        lambda tmp: _moved(
            tmp, "translations", {"DISTANCE": "0.10", "AXIS": "NAC-X", "ALIAS": "Wing"}
        ),
    ),
    "VELOCITY": _rows(steady_case, "VELOCITY", "30.0", "40.0"),
    "ADVANCE_RATIO": Variation(
        lambda _: rotor_case(RPM=None, ADVANCE_RATIO="0.5").model_copy(
            update={"reference": REFERENCE}
        ),
        lambda _: rotor_case(RPM=None, ADVANCE_RATIO="0.9").model_copy(
            update={"reference": REFERENCE}
        ),
    ),
    **{
        rate: Variation(
            lambda _, rate=rate: steady_case(**{rate: "5"}).model_copy(
                update={"reference": REFERENCE}
            ),
            lambda _, rate=rate: steady_case(**{rate: "10"}).model_copy(
                update={"reference": REFERENCE}
            ),
        )
        for rate in ("roll_rate", "pitch_rate", "yaw_rate")
    },
    "LOG_OUTPUT": Variation(
        lambda _: _stated(unsteady_case_full(), LOG_OUTPUT="2").model_copy(
            update={"outputs": THREE_OUTPUTS}
        ),
        lambda _: _stated(unsteady_case_full(), LOG_OUTPUT="3").model_copy(
            update={"outputs": THREE_OUTPUTS}
        ),
    ),
    "NCPUS": _rows(steady_case, "NCPUS", "4", "8"),
    # On the run type whose watchdog counts it down.
    "WALLTIME": _rows(unsteady_case, "WALLTIME", "10h", "20h"),
    "CONFIGURATION": _rows(steady_case, "CONFIGURATION", "A", "B"),
    "ACTUATOR": Variation(
        lambda _: _with_disc(
            steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120")
        ),
        lambda _: _with_disc(
            steady_case(ACTUATOR="FAN", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120")
        ),
    ),
    "ACTUATOR_RPM": Variation(
        lambda _: _with_disc(
            steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120")
        ),
        lambda _: _with_disc(
            steady_case(ACTUATOR="PROP", ACTUATOR_RPM="3000", ACTUATOR_THRUST="120")
        ),
    ),
    "ACTUATOR_THRUST": Variation(
        lambda _: _with_disc(
            steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120")
        ),
        lambda _: _with_disc(
            steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="150")
        ),
    ),
    "PROFILE": Variation(
        lambda tmp: _profile(tmp, "prop_ct"), lambda tmp: _profile(tmp, "prop_cq")
    ),
    "FREESTREAM": Variation(
        lambda tmp: _freestream(tmp, "fs_a", 30.0), lambda tmp: _freestream(tmp, "fs_b", 32.0)
    ),
    "ADDITIONAL_PPROC": _rows(steady_case, "ADDITIONAL_PPROC", "p002", "p003"),
    "COLD_START": Variation(
        lambda _: steady_case(COLD_START="false"),
        lambda _: steady_case(COLD_START="true"),
        sweep=True,
    ),
    "DELTA_TIME": _rows(unsteady_case, "DELTA_TIME", "0.0001", "0.0002"),
    "TIME_ITERATIONS": _rows(unsteady_case, "TIME_ITERATIONS", "480", "600"),
    "DELTA_THETA": Variation(
        lambda tmp: _azimuthal_clock(tmp), lambda tmp: _azimuthal_clock(tmp, DELTA_THETA="15")
    ),
    "REVOLUTIONS": Variation(
        lambda tmp: _azimuthal_clock(tmp), lambda tmp: _azimuthal_clock(tmp, REVOLUTIONS="3")
    ),
    "LAST_ITERS_AVG": _rows(unsteady_case, "LAST_ITERS_AVG", "100", "200"),
    "BLADES": _rows(rotor_case, "BLADES", "4", "6"),
    "EXPORT_UNSTEADY_AFTER_ITER": _rows(unsteady_case, "EXPORT_UNSTEADY_AFTER_ITER", "10", "20"),
    "RESTART": Variation(
        lambda _: _continuing("{ADDITIONAL_ITERS=120}", "120"),
        lambda _: _continuing("{ADDITIONAL_ITERS=200}", "200"),
    ),
    "LAST_REVS_AVG": _rows(rotor_case, "LAST_REVS_AVG", "0.25", "0.5"),
    "CLOCK_MOTION": Variation(
        lambda tmp: _azimuthal_clock(tmp, CLOCK_MOTION="LIFT_L1"),
        lambda tmp: _azimuthal_clock(tmp, CLOCK_MOTION="PUSHER"),
    ),
    "RPM": _rows(rotor_case, "RPM", "1200", "1500"),
    "RPM_SIGN": Variation(
        lambda _: rotor_case(RPM=None, ADVANCE_RATIO="0.5", RPM_SIGN="1").model_copy(
            update={"reference": REFERENCE}
        ),
        lambda _: rotor_case(RPM=None, ADVANCE_RATIO="0.5", RPM_SIGN="-1").model_copy(
            update={"reference": REFERENCE}
        ),
    ),
    "ROTOR_AXIS": _rows(rotor_case, "ROTOR_AXIS", "X", "Z"),
    "ROTOR_ORIGIN": _rows(rotor_case, "ROTOR_ORIGIN", "0.1,0.2,0.3", "0.4,0.5,0.6"),
    "ROTOR_SHEDDING": _rows(rotor_case, "ROTOR_SHEDDING", "AXIAL", "AZIMUTH"),
    "MOVING_BOUNDARIES": _rows(rotor_case, "MOVING_BOUNDARIES", "1", "1,2"),
    "MOTIONS": Variation(
        lambda tmp: two_rotor_case(tmp),
        lambda tmp: two_rotor_case(tmp).model_copy(
            update={
                "motions": [
                    {"MOVING_BC_ALIAS": "LIFT_L1", "RPM": "2600"},
                    {"MOVING_BC_ALIAS": "PUSHER", "ADVANCE_RATIO": "0.85"},
                ]
            }
        ),
    ),
    "EXPORT_UNSTEADY_AFTER_REV": _rows(rotor_case, "EXPORT_UNSTEADY_AFTER_REV", "0.1", "0.2"),
    "RAW": Variation(
        lambda _: _raw("SOLVER_SET_ITERATIONS 100"), lambda _: _raw("SOLVER_SET_ITERATIONS 200")
    ),
}


def _setting(
    name: str,
    first: object,
    second: object,
    make: Callable[..., SimCase] = steady_case,
    *,
    on_wing: bool = False,
    **variables: str,
) -> Variation:
    """A solver setting at two values, on ``make``'s run type, over the wing where it names one."""

    def build(tmp: Path, value: object) -> SimCase:
        case = make(**variables).model_copy(update={"solver": SolverSettings(**{name: value})})
        return _on_wing(tmp, case) if on_wing else case

    return Variation(lambda tmp: build(tmp, first), lambda tmp: build(tmp, second))


_TOGGLES = (
    "forced_iterations",
    "viscous_coupling",
    "wall_collision_avoidance",
    "mesh_induced_wake_velocity",
    "unsteady_pressure_and_kutta",
    "wake_on_wake_induction",
    "additional_wake_relaxation",
    "reynolds_averaged_drag",
    "laminar_separation",
    "kutta_joukowski_lift",
    "print_rotor_induced_velocities",
    "adaptive_field_grid_refinement",
    "wake_relaxation",
    "wake_streamwise_agglomeration",
    "jet_wake_filaments_grid_induction",
    "adverse_gradient_boundary_layer",
    "vortex_ring_normalization",
    "symmetry_loads",
    "inviscid_loads",
    "vorticity_lift_model",
)
_NUMBERS = (
    "solver_stabilization",
    "rotor_induced_velocity_blending",
    "wake_numerical_relaxation",
    "wake_decay_constant_per_m",
    "jet_wake_decay_normalized_length",
)

#: TWO VALUES OF EVERY SOLVER SETTING, on a run type that takes it.
SETTING_VARIATIONS: dict[str, Variation] = {
    **{name: _setting(name, True, False) for name in _TOGGLES},
    **{name: _setting(name, 0.5, 0.7) for name in _NUMBERS},
    "iterations": _setting("iterations", 500, 800),
    "convergence": _setting("convergence", 1e-5, 1e-6),
    "boundary_layer": _setting("boundary_layer", "TRANSITIONAL", "TURBULENT"),
    "max_threads": _setting("max_threads", 4, 8),
    # The executor's and the wall-clock program's: on the run type that has a clock.
    "timeout_s": _setting("timeout_s", 100.0, 200.0, unsteady_case, WALLTIME="10h"),
    "walltime_margin_s": _setting(
        "walltime_margin_s", 600.0, 1200.0, unsteady_case, WALLTIME="10h"
    ),
    "solver_model": _setting("solver_model", "INCOMPRESSIBLE", "SUBSONIC_PRANDTL_GLAUERT"),
    "convergence_iterations": _setting("convergence_iterations", 5, 10),
    "minimum_cp": _setting("minimum_cp", -3.0, -5.0),
    "farfield_layers": _setting("farfield_layers", 3, 5),
    "aeroelastic_rbf_type": _setting("aeroelastic_rbf_type", "GAUSSIAN", "LINEAR"),
    "wake_termination_revolutions": _setting("wake_termination_revolutions", 1.0, 2.0, rotor_case),
    "wake_termination_steps": _setting("wake_termination_steps", 10, 20, rotor_case),
    "significant_digits": _setting("significant_digits", 6, 8),
    "reference_velocity_m_per_s": _setting("reference_velocity_m_per_s", 30.0, 40.0),
    "vorticity_drag_families": _setting(
        "vorticity_drag_families", ["Wing"], ["Body"], on_wing=True
    ),
    "axial_separation_families": _setting(
        "axial_separation_families", ["Wing"], ["Body"], on_wing=True
    ),
    "load_solver_initialization": _setting("load_solver_initialization", True, False, on_wing=True),
    "analysis_families": _setting("analysis_families", ["Wing"], ["Body"], on_wing=True),
    "load_units": _setting("load_units", "NEWTONS", "POUND-FORCE"),
    "unsteady_viscous_coupling_iteration": _setting(
        "unsteady_viscous_coupling_iteration", 5, 10, unsteady_case
    ),
}


# --- the measurement ----------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    """What the two values did, over every build the run type covers."""

    differs: list[str]
    rendered: list[str]
    refused: str


def _render(case: SimCase, build: str, sweep: bool) -> tuple[str | None, str]:
    script = Script(build)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if sweep:
                points = [case_at_point(case, {"alpha": alpha}) for alpha in (-2.0, 0.0, 2.0)]
                build_steady_sweep(points, script, cold=_is_cold_start(case))
            else:
                build_script(case, script)
    except PyflightstreamError as error:
        return None, str(error)
    return script.render(), ""


def _measure(variation: Variation, tmp: Path) -> Outcome:
    first, second = variation.first(tmp), variation.second(tmp)
    differs, rendered, refused = [], [], ""
    for build in covered_builds(WORKFLOWS[select_workflow(first)]):
        (one, why_one), (two, _) = (
            _render(first, build, variation.sweep),
            _render(second, build, variation.sweep),
        )
        if one is None and two is None:
            refused = refused or why_one
            continue
        rendered.append(build)
        if one != two:
            differs.append(build)
    return Outcome(differs, rendered, refused)


@pytest.fixture(scope="module")
def measured(tmp_path_factory) -> dict[tuple[tuple[str, str], str], Outcome]:
    tmp = tmp_path_factory.mktemp("glossary_claims")
    outcomes = {}
    for table, variations in ((ROW_KEYS, ROW_KEY_VARIATIONS), (SETTINGS, SETTING_VARIATIONS)):
        for key, variation in variations.items():
            outcomes[(table, key)] = _measure(variation, tmp)
    return outcomes


@pytest.fixture(scope="module")
def meanings() -> dict[tuple[tuple[str, str], str], str]:
    """Each row's "What it sets" cell, read back off the rendered page."""
    page = parsed_page(input_glossary_markdown())
    return {(table, key): cells[0] for table in (ROW_KEYS, SETTINGS) for key, cells in page[table]}


def test_every_row_key_and_every_setting_has_two_values_here():
    """A key the package gains arrives with the two values this module builds it at."""
    assert set(ROW_KEY_VARIATIONS) == set(ROW_KEY_MEANINGS), (
        f"row keys with no variation: {sorted(set(ROW_KEY_MEANINGS) - set(ROW_KEY_VARIATIONS))}; "
        f"variations of no row key: {sorted(set(ROW_KEY_VARIATIONS) - set(ROW_KEY_MEANINGS))}"
    )
    assert set(SETTING_VARIATIONS) == set(SolverSettings.model_fields), (
        "settings with no variation: "
        f"{sorted(set(SolverSettings.model_fields) - set(SETTING_VARIATIONS))}; variations of no "
        f"setting: {sorted(set(SETTING_VARIATIONS) - set(SolverSettings.model_fields))}"
    )


def test_every_variation_builds_a_script_on_some_build(measured):
    """The control: a variation refused on every build measures nothing, and says so."""
    idle = [
        f"{table[1]} / {key}: {outcome.refused[:240]}"
        for (table, key), outcome in measured.items()
        if not outcome.rendered
    ]
    assert not idle, "these variations build no script on any build:\n  " + "\n  ".join(idle)


def test_a_row_saying_a_key_sets_something_names_a_key_whose_value_reaches_the_script(
    measured, meanings
):
    """THE FINDING: a key a row presents as a setting changes the script it names."""
    silent = [
        f"{table[1]} / {key}"
        for (table, key), outcome in measured.items()
        if outcome.rendered and not outcome.differs and NO_SCRIPT_LINE not in meanings[(table, key)]
    ]
    assert not silent, (
        "these rows say what the key sets, and changing the key's value leaves every "
        f"workflow script byte-identical; say '{NO_SCRIPT_LINE}' and what takes it instead, "
        "where the key is registered:\n  " + "\n  ".join(silent)
    )


def test_a_row_saying_no_line_carries_the_value_is_not_contradicted_by_the_script(
    measured, meanings
):
    """The mirror: the sentence is a claim, and a script that carries the value refutes it."""
    wrong = [
        f"{table[1]} / {key}: differs on {', '.join(outcome.differs)}"
        for (table, key), outcome in measured.items()
        if outcome.differs and NO_SCRIPT_LINE in meanings[(table, key)]
    ]
    assert not wrong, (
        f"these rows say '{NO_SCRIPT_LINE}' and the script carries it:\n  " + "\n  ".join(wrong)
    )
