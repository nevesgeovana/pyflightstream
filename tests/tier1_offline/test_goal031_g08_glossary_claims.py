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

import json
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamError
from pyflightstream._fsi_calibration import MATERIAL_FACTORS, MATRIX_FACTORS
from pyflightstream.cases import (
    ActuatorBlock,
    FluidState,
    FrameSpec,
    MeshImport,
    PprocSpec,
    RawCommand,
    RawMeshConditions,
    ReferenceData,
    SimCase,
    SolverSettings,
    TrailingEdgeMarking,
    case_at_point,
)
from pyflightstream.cases.acoustics import with_acoustic_signals
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
from pyflightstream.run._ids import _is_cold_start
from pyflightstream.script import Script
from pyflightstream.workspace.fsi_setup import resolve_row_fsi
from pyflightstream.workspace.inputs import read_raw_mesh_conditions
from pyflightstream.workspace.matrix import _bind_setup_ports
from tests.tier1_offline.test_aeroelastic_typed_setup import coupled_case
from tests.tier1_offline.test_goal031_g08_input_glossary import parsed_page
from tests.tier1_offline.test_rotor_by_alias import saved_simulation, two_rotor_case
from tests.tier1_offline.test_workflows import (
    qsteady_case,
    rotor_case,
    steady_case,
    steady_case_resolved,
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

    ``refusal`` is for a key REFUSED IN THIS RELEASE whatever its value: then
    ``first`` does not state the key and builds, ``second`` states it, and
    every build refuses ``second``, in these words wherever ``first`` builds
    (:func:`test_a_key_refused_in_this_release_is_refused_on_every_build`).
    Two values of such a key would both be refused and measure nothing.
    """

    first: Make
    second: Make
    sweep: bool = False
    refusal: str = ""


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


#: A CCS file on the file route with one Relaxed_TE line stating no direction.
_CCS_WITH_RELAXED_TE = (
    "Aircraft;T\nUnits;Meter\n\nComponent;FUS\nLiftingSurface;false\n"
    "Relaxed_TE;0.5;0.2;0.8\nCrossSection;0.0;0.0;0.1;0.0;0.1;0.0;0.0;0.0;0.1\n"
)


def _ccs_shedding(tmp: Path, direction: str) -> SimCase:
    """CCS_SHEDDING as the plan binds it (0.32.0, G35): a CCS file on the file route.

    The value reaches the run's own copy of the file, which CCS_IMPORT reads,
    and no line of the script: both directions name the same copy.
    """
    path = tmp / "g35.csv"
    path.write_text(_CCS_WITH_RELAXED_TE, encoding="utf-8")
    return steady_case(CCS_SHEDDING=direction).model_copy(
        update={
            "geometry": str(path),
            "mesh_import": MeshImport(units="FILE", ccs={"kind": "file"}),
            "inventory": ("FUS",),
            "inventory_source": "sidecar",
        }
    )


def _raw(line: str) -> SimCase:
    """RAW reaches the case as its raw commands; the reader takes it out of the cell."""
    return steady_case().model_copy(
        update={"raw_commands": [RawCommand(command=line, before="exec")]}
    )


def _custom_units(tmp: Path, units: str) -> SimCase:
    """FREESTREAM_UNITS beside a resolved field, on a simulation whose unit is known."""
    case = _freestream(tmp, "fs_units", 30.0)
    return _stated(case, FREESTREAM_UNITS=units).model_copy(
        update={"solver": SolverSettings(simulation_length_unit="METER")}
    )


#: The sources and the observer time an acoustic observer needs (0.32.0, E2).
_ACOUSTIC = {"ACOUSTIC_SOURCES": "ENABLE", "ACOUSTIC_OBSERVER_TIME": "0.05 0.2 16"}
_SECTION = (
    "{{PLANE:YZ / OFFSET:0.0 / RADIAL_OBSERVERS:2 / AZIMUTH_OBSERVERS:4 / INNER_RADIUS:5.0 / "
    "OUTER_RADIUS:{outer}}}"
)


def _acoustic_row(tmp: Path, **variables: str) -> SimCase:
    """An unsteady row stating acoustic keys, its export declared as the run layer does;
    ``ACOUSTIC_OBSERVERS_FILE`` as the plan resolves it, a file of that stem."""
    case = unsteady_case(**variables)
    stem = variables.get("ACOUSTIC_OBSERVERS_FILE")
    if stem is not None:
        path = tmp / f"{stem}.csv"
        path.write_text("1\n0.0,10.0,0.0\n" if stem.endswith("a") else "1\n0.0,12.0,0.0\n")
        case = case.model_copy(update={"acoustic_observers_file": str(path)})
    outputs = with_acoustic_signals(["loads_a+00.0.txt"], case, "loads_a+00.0")
    return case.model_copy(update={"outputs": outputs})


#: Two FSI inputs of the supplied mode, a beam with every property non-zero so
#: a factor on any of them changes it, and one of the calculated mode, the only
#: mode a MATERIAL factor applies in. Codes as the matrix names them.
_SUPPLIED, _SUPPLIED_STIFFER, _CALCULATED = "f001", "f002", "f101"


def _toml(table: str, values: dict[str, object]) -> list[str]:
    return [f"[{table}]", *(f"{key} = {json.dumps(value)}" for key, value in values.items())]


def _fsi_sources(tmp: Path) -> Path:
    """Write the three FSI inputs of ``inputs/fsi/``, for the coupled rotor's clock and speed."""
    config = coupled_case(tmp).fsi
    assert config is not None
    scalars = config.model_dump(mode="json", exclude={"blade", "phases"})
    phases = config.phases.model_dump(mode="json")
    stations = len(config.blade.station_radii_m)
    blade = {
        **config.blade.model_dump(mode="json", exclude={"provenance"}),
        "elastic_axis_offset_chordwise_m": [0.01] * stations,
        "elastic_axis_offset_normal_m": [0.002] * stations,
        "cg_offset_chordwise_m": [0.015] * stations,
        "cg_offset_normal_m": [0.001] * stations,
        "geometric_pitch_deg": [3.0] * stations,
    }
    stiffer = {**blade, "bending_stiffness_n_m2": [2 * v for v in blade["bending_stiffness_n_m2"]]}
    folder = tmp / "inputs" / "fsi"
    folder.mkdir(parents=True, exist_ok=True)
    for code, beam in ((_SUPPLIED, blade), (_SUPPLIED_STIFFER, stiffer)):
        lines = [
            'mode = "supplied"',
            *_toml("config", scalars),
            *_toml("config.phases", phases),
            *_toml("config.blade", beam),
        ]
        (folder / f"{code}.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    contour = [[-0.01, -0.001], [0.03, -0.001], [0.03, 0.003], [-0.01, 0.003]]
    calculated = [
        'mode = "calculated"',
        'material = "ti-6al-4v-grade5-annealed"',
        *_toml("config", {k: scalars[k] for k in ("blade_count", "omega_rad_per_s")}),
        f"time_increment_s = {json.dumps(scalars['time_increment_s'])}",
        *_toml(
            "sections",
            {
                "station_radii_m": [0.2, 1.2],
                "chord_m": [0.04, 0.04],
                "geometric_pitch_deg": [3.0, 1.0],
                "geometry_source": "Synthetic closed contours in metres",
                "torsion_grid_cells": 16,
                "sections_m": [contour, contour],
            },
        ),
    ]
    (folder / f"{_CALCULATED}.toml").write_text("\n".join(calculated) + "\n", encoding="utf-8")
    return tmp / "inputs"


def _fsi_row(tmp: Path, code: str, **cells: str) -> SimCase:
    """FSI as the plan resolves it: the code and its factor cells, read into the beam staged.

    The matrix reader calls ``resolve_row_fsi`` on the row's cells and puts the
    effective beam and its provenance on the case; the builder reads that
    beam, and the row's cells stay on the case beside it.
    """
    resolved = resolve_row_fsi(_fsi_sources(tmp), {"FSI": code, **cells})
    assert resolved is not None
    case = coupled_case(tmp)
    return case.model_copy(
        update={
            "fsi": resolved.effective,
            "fsi_provenance": resolved.provenance(),
            "variables": {**case.variables, "FSI": code, **cells},
        }
    )


def _fsi_factor(key: str) -> Variation:
    """One calibration factor at two values, on the input whose mode applies it."""
    code = _CALCULATED if MATRIX_FACTORS[key] in MATERIAL_FACTORS else _SUPPLIED
    return Variation(
        lambda tmp: _fsi_row(tmp, code, **{key: "0.9"}),
        lambda tmp: _fsi_row(tmp, code, **{key: "1.1"}),
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
    "CCS_SHEDDING": Variation(
        lambda tmp: _ccs_shedding(tmp, "AXIAL"), lambda tmp: _ccs_shedding(tmp, "AZIMUTH")
    ),
    "FREESTREAM": Variation(
        lambda tmp: _freestream(tmp, "fs_a", 30.0), lambda tmp: _freestream(tmp, "fs_b", 32.0)
    ),
    # NATIVE hands the solver the file as written, SI a converted copy.
    "FREESTREAM_UNITS": Variation(
        lambda tmp: _custom_units(tmp, "NATIVE"), lambda tmp: _custom_units(tmp, "SI")
    ),
    # The case field stands for the key: the beam resolve_row_fsi reads off the
    # code, staged beside the script, on the coupled rotor.
    "FSI": Variation(
        lambda tmp: _fsi_row(tmp, _SUPPLIED), lambda tmp: _fsi_row(tmp, _SUPPLIED_STIFFER)
    ),
    **{key: _fsi_factor(key) for key in MATRIX_FACTORS},
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
    "EXPORT_UNSTEADY_LAST_ITER": _rows(unsteady_case, "EXPORT_UNSTEADY_LAST_ITER", "10", "20"),
    "RESTART": Variation(
        lambda _: _continuing("{ADDITIONAL_ITERS=120}", "120"),
        lambda _: _continuing("{ADDITIONAL_ITERS=200}", "200"),
    ),
    "LAST_REVS_AVG": _rows(rotor_case, "LAST_REVS_AVG", "0.25", "0.5"),
    # 0.32.0 (E2): the acoustic toolbox, each key moved beside the others it needs.
    "ACOUSTIC_SOURCES": Variation(
        lambda tmp: _acoustic_row(tmp, ACOUSTIC_SOURCES="ENABLE"),
        lambda tmp: _acoustic_row(tmp, ACOUSTIC_SOURCES="DISABLE"),
    ),
    "ACOUSTIC_OBSERVERS": Variation(
        lambda tmp: _acoustic_row(tmp, **_ACOUSTIC, ACOUSTIC_OBSERVERS="MIC1 0.0 10.0 0.0"),
        lambda tmp: _acoustic_row(tmp, **_ACOUSTIC, ACOUSTIC_OBSERVERS="MIC1 0.0 12.0 0.0"),
    ),
    "ACOUSTIC_OBSERVERS_FILE": Variation(
        lambda tmp: _acoustic_row(tmp, **_ACOUSTIC, ACOUSTIC_OBSERVERS_FILE="ring_a"),
        lambda tmp: _acoustic_row(tmp, **_ACOUSTIC, ACOUSTIC_OBSERVERS_FILE="ring_b"),
    ),
    "ACOUSTIC_OBSERVER_TIME": Variation(
        lambda tmp: _acoustic_row(
            tmp,
            ACOUSTIC_SOURCES="ENABLE",
            ACOUSTIC_OBSERVERS="M 0 1 0",
            ACOUSTIC_OBSERVER_TIME="0.05 0.2 16",
        ),
        lambda tmp: _acoustic_row(
            tmp,
            ACOUSTIC_SOURCES="ENABLE",
            ACOUSTIC_OBSERVERS="M 0 1 0",
            ACOUSTIC_OBSERVER_TIME="0.05 0.3 16",
        ),
    ),
    "ACOUSTIC_SECTION": Variation(
        lambda tmp: _acoustic_row(tmp, **_ACOUSTIC, ACOUSTIC_SECTION=_SECTION.format(outer=10.0)),
        lambda tmp: _acoustic_row(tmp, **_ACOUSTIC, ACOUSTIC_SECTION=_SECTION.format(outer=12.0)),
    ),
    # 0.30.0: the quasi-steady wheel's clockings, two and three of one passage.
    "PASSAGE_POSITIONS": _rows(qsteady_case, "PASSAGE_POSITIONS", "2", "3"),
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
    # Refused in 0.29.0 whatever its value: absent against stated.
    "ROTOR_SHEDDING": Variation(
        lambda _: rotor_case(),
        lambda _: rotor_case(ROTOR_SHEDDING="AZIMUTH"),
        refusal="0.29.0 refuses it in every matrix workflow",
    ),
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
    "EXPORT_UNSTEADY_LAST_REV": _rows(rotor_case, "EXPORT_UNSTEADY_LAST_REV", "0.1", "0.2"),
    "RUN_WAKE_LENGTH_R": _rows(rotor_case, "RUN_WAKE_LENGTH_R", "4", "6", TIME_ITERATIONS=None),
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


def _setting_on(base: Make, name: str, first: object, second: object, **fixed: object) -> Variation:
    """A solver setting at two values on the case ``base`` builds, beside ``fixed`` settings.

    For the 0.29 setup fields whose value matters only on a shaped case: a raw
    mesh whose sidecar declares what an ``apply_*`` choice applies, a disc an
    actuator action names, or the wing whose boundaries a selection names.
    """

    def build(tmp: Path, value: object) -> SimCase:
        return base(tmp).model_copy(update={"solver": SolverSettings(**{**fixed, name: value})})

    return Variation(lambda tmp: build(tmp, first), lambda tmp: build(tmp, second))


def _plain(_: Path) -> SimCase:
    return steady_case()


def _over_wing(tmp: Path) -> SimCase:
    """The saved wing, whose boundaries Wing, Body and Base a selection names."""
    return _on_wing(tmp, steady_case())


def _slow_rotor_in_air(_: Path) -> SimCase:
    """A rotor at 1 m/s in sea-level air: the thrust's induced velocity exceeds the free stream."""
    air = FluidState(
        velocity_m_per_s=1.0,
        density_kg_m3=1.225,
        pressure_pa=101325.0,
        temperature_k=288.15,
        viscosity_pa_s=1.789e-5,
        sonic_velocity_m_per_s=340.29,
        source="isa",
    )
    return rotor_case(VELOCITY="1.0").model_copy(update={"fluid": air})


def _raw_mesh(tmp: Path) -> SimCase:
    """A raw mesh whose sidecar detects its trailing edges, wake termination and base.

    The three declarations an ``apply_*`` choice applies or leaves, and the
    detection a base-region bending angle precedes.
    """
    return steady_case().model_copy(
        update={
            "geometry": str(tmp / "wing.obj"),
            "mesh_import": MeshImport(units="METER"),
            "inventory": ("Wing", "Base"),
            "inventory_source": "sidecar",
            "raw_mesh_conditions": RawMeshConditions(
                trailing_edges=TrailingEdgeMarking(route="detect"),
                wake_termination="auto",
                base_regions="auto",
            ),
        }
    )


def _disc(_: Path) -> SimCase:
    """The disc an actuator action names, created before the action."""
    return _with_disc(steady_case(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"))


def _ported(tmp: Path, port: str, kind: str, speed: str) -> SimCase:
    """One setup port as the matrix reader binds it: the sidecar's surface, the row's speed."""
    sidecar = tmp / "duct.boundaries.toml"
    sidecar.write_text(
        '[ports]\nfeed="Inlet"\nexit="Outlet"\n[trailing_edges]\nnone=true\n', encoding="utf-8"
    )
    ports = [{"port": port, "kind": kind, "velocity_variable": "PORT_SPEED"}]
    case = steady_case(PORT_SPEED=speed).model_copy(
        update={
            "geometry": str(tmp / "duct.obj"),
            "mesh_import": MeshImport(units="METER"),
            "inventory": ("Inlet", "Outlet"),
            "inventory_source": "sidecar",
            "raw_mesh_conditions": read_raw_mesh_conditions(sidecar),
            "solver": SolverSettings(ports=ports),
        }
    )
    return _bind_setup_ports(case, tmp)


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
    # FR-321 and FR-323 (0.34.0): the length the rotor builder converts, the
    # cap that bounds it, and the thrust whose induced velocity convects it,
    # this last on a slow rotor in air so that v_i exceeds the free stream.
    "wake_termination_length": _setting("wake_termination_length", 4.0, 8.0, rotor_case),
    "wake_termination_revolutions_cap": _setting(
        "wake_termination_revolutions_cap", 1.0, 2.0, rotor_case
    ),
    "wake_termination_thrust_n": _setting_on(
        _slow_rotor_in_air, "wake_termination_thrust_n", 1000.0, 4000.0
    ),
    "wake_termination_x_m": _setting("wake_termination_x_m", 2.0, 5.0, rotor_case),
    "significant_digits": _setting("significant_digits", 6, 8),
    "reference_velocity_m_per_s": _setting("reference_velocity_m_per_s", 30.0, 40.0),
    "vorticity_drag_families": _setting(
        "vorticity_drag_families", ["Wing"], ["Body"], on_wing=True
    ),
    "axial_separation_families": _setting(
        "axial_separation_families", ["Wing"], ["Body"], on_wing=True
    ),
    "delete_surfaces": _setting("delete_surfaces", ["Wing"], ["Body"], on_wing=True),
    "slipstream_wake_stabilization": _setting(
        "slipstream_wake_stabilization", True, False, rotor_case
    ),
    "load_solver_initialization": _setting("load_solver_initialization", True, False, on_wing=True),
    "analysis_families": _setting("analysis_families", ["Wing"], ["Body"], on_wing=True),
    "load_units": _setting("load_units", "NEWTONS", "POUND-FORCE"),
    "unsteady_viscous_coupling_iteration": _setting(
        "unsteady_viscous_coupling_iteration", 5, 10, unsteady_case
    ),
    # --- the setup fields 0.33.0 adds (FR-317, FR-319) -------------------
    "moments_model": _setting("moments_model", "PRESSURE", "VORTICITY", on_wing=True),
    "unsteady_solver_actions": _setting(
        "unsteady_solver_actions",
        [{"type": "COMMAND_LINE", "name": "first", "filename": "echo first"}],
        [{"type": "COMMAND_LINE", "name": "second", "filename": "echo second"}],
        unsteady_case,
    ),
    # --- the setup fields of the commands 26.125 adds (item S10) -----------
    "aeroelastic_convergence_threshold": _setting("aeroelastic_convergence_threshold", 1e-4, 1e-5),
    "solver_time_averaging": _setting("solver_time_averaging", [1, 3], [2, 3], unsteady_case),
    # --- the setup fields 0.29.0 adds ------------------------------------
    # Geometry controls, applied after the saved wing opens and before frames.
    "simulation_length_unit": _setting_on(
        _over_wing, "simulation_length_unit", "METER", "MILLIMETER"
    ),
    "vertex_merge_tolerance_m": _setting_on(_over_wing, "vertex_merge_tolerance_m", 1e-4, 2e-4),
    "geometric_edge_bluntness_angle_deg": _setting_on(
        _over_wing, "geometric_edge_bluntness_angle_deg", 100.0, 120.0
    ),
    # The sidecar's declarations applied or left, on the raw mesh declaring them.
    **{
        name: _setting_on(_raw_mesh, name, True, False)
        for name in ("apply_trailing_edges", "apply_wake_termination", "apply_base_regions")
    },
    "base_region_bending_angle_deg": _setting_on(
        _raw_mesh, "base_region_bending_angle_deg", 20.0, 30.0
    ),
    "base_region_operations": _setting_on(
        _over_wing,
        "base_region_operations",
        [{"operation": "create", "boundary": "Base", "model": "USER", "cp": -0.2}],
        [{"operation": "create", "boundary": "Base", "model": "USER", "cp": -0.3}],
    ),
    # Boundary selections, by the wing's own boundary names.
    **{
        name: _setting_on(_over_wing, name, ["Wing"], ["Body"])
        for name in (
            "viscous_excluded",
            "thin_boundaries",
            "valarezo_separation_boundaries",
            "crossflow_separation_boundaries",
            "leading_edge_wake_boundaries",
            "proximal_boundaries",
        )
    },
    "stratford_bulk_separation": _setting_on(
        _over_wing,
        "stratford_bulk_separation",
        [{"name": "STRUT", "boundaries": ["Wing"]}],
        [{"name": "STRUT", "boundaries": ["Body"]}],
    ),
    "clear_vorticity_drag_boundaries": _setting_on(
        _over_wing, "clear_vorticity_drag_boundaries", None, True
    ),
    # Separation models and their legacy criteria, stated before initialisation.
    "bulk_separation": _setting_on(
        _plain,
        "bulk_separation",
        {"name": "GEAR", "separation_type": "CYLINDRICAL", "diameter": 0.2},
        {"name": "GEAR", "separation_type": "FLAT_PLATE", "diameter": 0.2},
    ),
    "airfoil_separation": _setting_on(
        _plain,
        "airfoil_separation",
        [{"name": "WING", "valarezo_criterion": False}],
        [{"name": "WING", "valarezo_criterion": True}],
    ),
    "axial_vortex_separation": _setting_on(
        _plain,
        "axial_vortex_separation",
        [{"name": "FUSELAGE", "diameter": 0.5}],
        [{"name": "FUSELAGE", "diameter": 0.6}],
    ),
    "cylindrical_bulk_separation": _setting_on(
        _plain,
        "cylindrical_bulk_separation",
        [{"name": "GEAR", "diameter": 0.2}],
        [{"name": "GEAR", "diameter": 0.3}],
    ),
    "delete_separations": _setting_on(_plain, "delete_separations", 1, "all"),
    "valarezo_criterion": _setting_on(_plain, "valarezo_criterion", True, False),
    "crossflow_separation_diameter": _setting_on(_plain, "crossflow_separation_diameter", 3.5, 4.5),
    "crossflow_separation_mean_diameter": _setting_on(
        _plain, "crossflow_separation_mean_diameter", 3.5, 4.5
    ),
    "crossflow_separation_axisymmetric": _setting_on(
        _plain, "crossflow_separation_axisymmetric", True, False
    ),
    # Refused in 0.29.0 whatever the value, by the build guard naming the
    # command: absent against stated, as for ROTOR_SHEDDING.
    "legacy_solver_model": Variation(
        _plain,
        lambda _: steady_case().model_copy(
            update={"solver": SolverSettings(legacy_solver_model="INCOMPRESSIBLE")}
        ),
        refusal="SET_SOLVER_MODEL",
    ),
    "surface_roughness": _setting_on(_plain, "surface_roughness", 10.0, 20.0),
    "sonic_velocity_m_per_s": Variation(
        _plain,
        lambda _: steady_case().model_copy(
            update={"solver": SolverSettings(sonic_velocity_m_per_s=340.0)}
        ),
        refusal="SONIC_VELOCITY",
    ),
    # PHYSICS takes both arguments, so each is varied with the other held.
    "physics_auto_trailing_edges": _setting_on(
        _plain, "physics_auto_trailing_edges", True, False, physics_auto_wake_nodes=True
    ),
    "physics_auto_wake_nodes": _setting_on(
        _plain, "physics_auto_wake_nodes", True, False, physics_auto_trailing_edges=True
    ),
    # Normalisation and the free-stream input, on a case whose fluid is resolved.
    "freestream_input": _setting_on(
        lambda _: steady_case_resolved(), "freestream_input", "velocity", "mach"
    ),
    "reference_mach": _setting_on(_plain, "reference_mach", 0.1, 0.2),
    "disable_reference_velocity": _setting_on(_plain, "disable_reference_velocity", None, True),
    "remove_initialization": _setting_on(_plain, "remove_initialization", None, True),
    "mark_wake_termination_nodes": _setting_on(_plain, "mark_wake_termination_nodes", None, True),
    # Existing entities by their one-based index, in the declared order.
    **{
        name: _setting_on(_plain, name, [1], [2])
        for name in (
            "delete_inlets",
            "delete_outlets",
            "delete_transition_trips",
            "disabled_wake_trailing_edges",
        )
    },
    "trailing_edge_types": _setting_on(
        _plain, "trailing_edge_types", {1: "STANDARD"}, {1: "JET_OUTFLOW"}
    ),
    "actuator_operations": _setting_on(
        _disc,
        "actuator_operations",
        [{"op": "rename", "actuator": "PROP", "name": "Front"}],
        [{"op": "rename", "actuator": "PROP", "name": "Rear"}],
    ),
    # The case field stands for the setup's port once the reader has bound it.
    "ports": Variation(
        lambda tmp: _ported(tmp, "feed", "inlet", "-10"),
        lambda tmp: _ported(tmp, "exit", "outlet", "10"),
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
def rotor_fsi_route_open():
    """Open the unsteady_rotor FSI route the FSI keys are measured on.

    0.30.0 refuses FSI on unsteady_rotor while the rotor morph is in debug
    (FSI-GUARD), and no other workflow is wired yet, so without this the FSI
    keys would build no script on any build. What the glossary claims is what
    the key sets in the script of the route that reads it; the route's wiring
    is kept behind the guard, so it is measured with the guard opened.
    """
    from pyflightstream.cases import fsi_workspace

    guard = fsi_workspace.fsi_workflow_refusal
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            fsi_workspace,
            "fsi_workflow_refusal",
            lambda workflow: None if workflow == "unsteady_rotor" else guard(workflow),
        )
        yield


@pytest.fixture(scope="module")
def measured(tmp_path_factory, rotor_fsi_route_open) -> dict[tuple[tuple[str, str], str], Outcome]:
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


@pytest.mark.requirement("FR-317")
@pytest.mark.requirement("FR-319")
@pytest.mark.requirement("FR-321")
@pytest.mark.requirement("FR-323")
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


def _states(case: SimCase, table: tuple[str, str], key: str) -> bool:
    """Whether a case states a row key in its variables, or a setting in its solver."""
    if table == ROW_KEYS:
        return key in case.variables
    return getattr(case.solver, key) is not None


#: The keys refused in 0.29.0 whatever their value, by table.
REFUSED_IN_THIS_RELEASE = {
    (ROW_KEYS, "ROTOR_SHEDDING"),
    (SETTINGS, "legacy_solver_model"),
    (SETTINGS, "sonic_velocity_m_per_s"),
}


@pytest.mark.requirement("FR-164")
def test_a_key_refused_in_this_release_is_refused_on_every_build(tmp_path, meanings):
    """A key refused whatever its value: its row says so, and every build refuses it.

    ``ROTOR_SHEDDING``, ``legacy_solver_model`` and ``sonic_velocity_m_per_s``
    in 0.29.0: each variation is absent against stated, which the claims above
    count as a difference; this holds what that difference is. Every build the
    run type covers refuses the stated case, in the key's own words wherever
    the case without the key builds, and where that case does not build (no
    workflow writes 25.000's INITIALIZE_SOLVER) with the very refusal the
    keyless case gets, so the build's refusal cannot stand in for the key's.
    The case without the key must build on at least one build.
    """
    refused = {
        (table, key): variation
        for table, variations in ((ROW_KEYS, ROW_KEY_VARIATIONS), (SETTINGS, SETTING_VARIATIONS))
        for key, variation in variations.items()
        if variation.refusal
    }
    assert set(refused) == REFUSED_IN_THIS_RELEASE, sorted(refused)
    for (table, key), variation in refused.items():
        assert "Refused in 0.29.0" in meanings[(table, key)], meanings[(table, key)]
        first, second = variation.first(tmp_path), variation.second(tmp_path)
        assert not _states(first, table, key) and _states(second, table, key)
        builds = covered_builds(WORKFLOWS[select_workflow(first)])
        assert builds
        not_refused = []
        for build in builds:
            script, why = _render(second, build, variation.sweep)
            keyless, keyless_why = _render(first, build, variation.sweep)
            in_its_words = variation.refusal in why
            as_the_build_refuses = keyless is None and why == keyless_why
            if script is not None or not (in_its_words or as_the_build_refuses):
                not_refused.append(build)
        assert not not_refused, f"{key} is not refused in its words on {not_refused}"
        assert any(_render(first, build, variation.sweep)[0] for build in builds), (
            f"the case without {key} builds on no build, so its refusal measures nothing"
        )


FSI_KEYS = ("FSI", *MATRIX_FACTORS)


@pytest.mark.parametrize("key", FSI_KEYS)
def test_an_fsi_key_changes_the_beam_the_run_stages(tmp_path, key):
    """The other half of an FSI row's byte-identical script: its value reaches the staged beam.

    No line of the script carries an FSI key's value; the effective driver
    configuration the run stages beside it does. Two values that staged the
    same beam would pass the claims above while varying nothing.
    """
    variation = ROW_KEY_VARIATIONS[key]
    first, second = variation.first(tmp_path), variation.second(tmp_path)
    assert first.fsi is not None and second.fsi is not None
    assert first.fsi != second.fsi, f"{key} at its two values stages the same beam"
