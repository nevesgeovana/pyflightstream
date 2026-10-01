"""Tier 1: FSI-G of 0.30.0, the fixed wing coupled on steady and unsteady.

The owner's decisions of 2026-09-28: "fsi de asa fixa tem que entrar sim, e
basico"; "vamos permitir o FSI para steady, qsteady e unsteady"; "asa parada
nao tem centrifuga, mas tem o peso da asa". So a steady row and an unsteady
row with nothing turning accept FSI, the structure is one clamped wing, and
its structural solve applies the aerodynamic loads plus the wing's own
weight, with no centrifugal term.

Each test here was proved by a mutant of the code it holds, reverted and the
file restored byte-identical (the FSI-G commit message lists them).
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-169, FR-171.

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.cases import (
    CampaignConfigError,
    MeshImport,
    PprocSpec,
    RawMeshConditions,
    ReferenceData,
    SimCase,
)
from pyflightstream.cases import fsi_workspace as ws
from pyflightstream.fsi import beam, centrifugal, driver, nodes, wing
from pyflightstream.fsi.config import BladeProperties, FixedWing, FsiConfig, dump_config
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.run import _is_one_job, _run_until_the_analysis_ends, _write_pending_files
from pyflightstream.script import Script
from tests.tier1_offline.test_g06_actuator_disc import _lines
from tests.tier1_offline.test_workflows import steady_case, unsteady_case

G0 = 9.80665
CHORD_M = 1.0
SPAN_M = 4.0
STATIONS = 9
THICKNESS_RATIO = 0.12


def lens_section(thickness_ratio: float = THICKNESS_RATIO, points: int = 24) -> list[list[float]]:
    """A closed symmetric lens about the quarter chord: (toward the LE, toward suction) [m]."""
    half = points // 2
    upper, lower = [], []
    for k in range(half + 1):
        t = k / half  # 0 at the leading edge, 1 at the trailing edge
        c = (0.25 - t) * CHORD_M
        y = 2.0 * thickness_ratio * CHORD_M * t * (1.0 - t)
        upper.append([c, y])
        lower.append([c, -y])
    return upper + lower[-2:0:-1]


def wing_config(
    *,
    mass_per_length_kg_per_m: float = 3.0,
    bending_stiffness_n_m2: float = 2.0e5,
    self_weight: bool = True,
    pitch_deg: float = 0.0,
    thickness_ratio: float = THICKNESS_RATIO,
) -> FsiConfig:
    """A uniform clamped wing: constant EI, GJ and running mass, the CG on the elastic axis."""
    n = STATIONS
    radii = [SPAN_M * i / (n - 1) for i in range(n)]
    blade = BladeProperties(
        station_radii_m=radii,
        chord_m=[CHORD_M] * n,
        mass_per_length_kg_per_m=[mass_per_length_kg_per_m] * n,
        inertia_major_kg_m=[0.05] * n,
        inertia_minor_kg_m=[0.001] * n,
        bending_stiffness_n_m2=[bending_stiffness_n_m2] * n,
        torsion_stiffness_n_m2=[5.0e4] * n,
        elastic_axis_offset_chordwise_m=[0.0] * n,
        elastic_axis_offset_normal_m=[0.0] * n,
        cg_offset_chordwise_m=[0.0] * n,
        cg_offset_normal_m=[0.0] * n,
        geometric_pitch_deg=[pitch_deg] * n,
        section_contours_m=[lens_section(thickness_ratio) for _ in range(n)],
    )
    return FsiConfig(
        blade_count=1,
        omega_rad_per_s=0.0,
        blade=blade,
        wing=FixedWing(self_weight=self_weight, origin_m=(0.25, 0.0, 0.0)),
    )


def _wing_update(tmp_path: Path, cfg: FsiConfig | None) -> dict[str, object]:
    geometry = tmp_path / "wing.obj"
    geometry.write_text("o Wing\nv 0 0 0\nv 1 0 0\nv 0 4 0\nf 1 2 3\n")
    return {
        "geometry": str(geometry),
        "mesh_import": MeshImport(units="METER"),
        "raw_mesh_conditions": RawMeshConditions.model_validate(
            {"trailing_edges": {"route": "detect"}}
        ),
        "inventory": ["Wing"],
        "reference": ReferenceData(area=8.0, length=1.0, moment_point_m=(0.0, 0.0, 0.0)),
        "fsi": cfg if cfg is not None else wing_config(),
        "pproc": PprocSpec.model_validate(
            {
                "sections": {
                    "count": 20,
                    "include_symmetry": False,
                    "distributions": [{"families": ["Wing"], "frame": "MRP", "planes": ["XZ"]}],
                }
            }
        ),
    }


def steady_wing_case(tmp_path: Path, cfg: FsiConfig | None = None) -> SimCase:
    return steady_case().model_copy(update=_wing_update(tmp_path, cfg))


def unsteady_wing_case(tmp_path: Path, cfg: FsiConfig | None = None) -> SimCase:
    return unsteady_case().model_copy(update=_wing_update(tmp_path, cfg))


# --------------------------------------------------------------------------
# The guard: steady and unsteady accept FSI; unsteady_rotor stays refused.


def test_the_guard_allows_steady_and_unsteady_and_keeps_the_rotor_refused():
    assert ws.fsi_workflow_refusal("steady") is None
    assert ws.fsi_workflow_refusal("unsteady") is None
    assert ws.fsi_workflow_refusal("unsteady_rotor") == ws.FSI_ROTOR_IN_DEBUG
    # The owner's requirement moved (GOAL-035): the qsteady_rotor sector couples
    # in 0.30.0, so the table accepts it; its builder refuses the wheel.
    assert ws.fsi_workflow_refusal("qsteady_rotor") is None
    assert ws.FIXED_WING_WORKFLOWS == ("steady", "unsteady")


def test_a_wing_configuration_on_the_rotor_workflow_is_refused(tmp_path):
    from tests.tier1_offline.test_aeroelastic_typed_setup import coupled_case

    case = coupled_case(tmp_path).model_copy(update={"fsi": wing_config()})
    script = Script("26.124")
    # unsteady_rotor is refused wholesale (FSI_ROTOR_IN_DEBUG), before the wing
    # check ever runs; qsteady_rotor is the rotor workflow FSI now couples on
    # (GOAL-035), so a wing on it is what the wing/workflow check itself refuses.
    with pytest.raises(CampaignConfigError, match="a fixed wing couples on"):
        ws.validate_workspace_fsi(case, script, workflow="qsteady_rotor", continuation=False)


# --------------------------------------------------------------------------
# The emitted scripts.


#: The coupling block of the steady wing, exact (FSI-G). The OBJ boundary at
#: tree position 1 is ID 2; the linked frame and the node import cite the MRP
#: frame the sections are cut in (2); the kernel is the beam line's.
STEADY_COUPLING = [
    "AEROELASTIC_RBF_TYPE MULTI_QUADRATIC",
    "DELETE_AEROELASTIC_STRUCTURAL_NODES",
    "ASSIGN_AEROELASTIC_SURFACES 1",
    "2",
    "ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS 1",
    "2",
    "IMPORT_AEROELASTIC_STRUCTURAL_NODES 2 DISABLE",
    "fsi_nodes.csv",
    "SET_AEROELASTIC_WORKING_DIRECTORY",
    ".",
    "SET_AEROELASTIC_POST_PROCESSING_SCRIPT",
    "fsi_post.txt",
    "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND",
]


def _commands(lines: list[str]) -> list[str]:
    return [line for line in lines if line.strip()]


def test_the_steady_wing_script_ends_at_the_analysis_and_exports_from_the_post(tmp_path):
    # P0300-FSIG-STEADY
    case = steady_wing_case(tmp_path)
    lines, script = _lines(case)
    body = _commands(lines)
    start = body.index("AEROELASTIC_RBF_TYPE MULTI_QUADRATIC")
    assert body[start : start + len(STEADY_COUPLING)] == STEADY_COUPLING
    after = body[start + len(STEADY_COUPLING) + 1 :]
    assert after == [
        f"SET_AEROELASTIC_ITERATIONS {ws.STEADY_AEROELASTIC_ITERATIONS}",
        "SET_SOLVER_ANALYSIS_LOADS_FRAME 2",
        "SET_ANALYSIS_MOMENTS_MODEL PRESSURE",
        "EXECUTE_AEROELASTIC_ANALYSIS",
    ]
    assert body.index("INITIALIZE_SOLVER") < start
    for absent in ("START_SOLVER", "CLOSE_FLIGHTSTREAM", "SET_AEROELASTIC_COUPLING_IN_UNSTEADY"):
        assert not any(line.startswith(absent) for line in body), absent
    assert ws.is_steady_aeroelastic_script(script.render())
    # The row's exports run in the post-processing script, after the loads the
    # structural program reads.
    post = _commands(script.pending_input_files[ws.POST_FILE].splitlines())
    assert post[:4] == [
        "UPDATE_ALL_SURFACE_SECTIONS",
        "COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS",
        "EXPORT_SURFACE_SECTIONAL_LOADS",
        ws.LOADS_FILE,
    ]
    assert post[4:] == ["EXPORT_SOLVER_ANALYSIS_SPREADSHEET", "loads_a+00.0.txt"]
    family = json.loads(script.pending_input_files[ws.FAMILY_FILE])
    assert family["families"] == [{"name": "Wing", "count": 20, "is_blade": True}]


def test_a_steady_wing_s_tecplot_is_recorded_in_the_run_s_loads_frame(tmp_path):
    case = steady_wing_case(tmp_path).model_copy(
        update={"outputs": ["loads_a+00.0.txt", "surface_a+00.0.dat"]}
    )
    _lines_, script = _lines(case)
    post = script.pending_input_files[ws.POST_FILE]
    assert "EXPORT_SOLVER_ANALYSIS_VTK" in post
    assert "EXPORT_SOLVER_ANALYSIS_VTK" not in script.render()
    assert len(script.surface_translations) == 1
    translation = script.surface_translations[0]
    assert translation["dat"] == "surface_a+00.0.dat"
    assert translation["frame"] == script.loads_frame_record()
    assert translation["frame"]["frame"] == 2


def test_the_unsteady_wing_couples_inside_the_march_with_the_post_call_export(tmp_path):
    # P0300-FSIG-UNSTEADY
    case = unsteady_wing_case(tmp_path)
    lines, script = _lines(case)
    body = _commands(lines)
    start = body.index("AEROELASTIC_RBF_TYPE MULTI_QUADRATIC")
    assert body[start : start + len(STEADY_COUPLING)] == STEADY_COUPLING
    at = body.index("SET_AEROELASTIC_ITERATIONS 1")
    assert body[at + 1] == "SET_AEROELASTIC_COUPLING_IN_UNSTEADY ENABLE"
    assert at < body.index("START_SOLVER")
    assert body[-1] == "CLOSE_FLIGHTSTREAM"
    assert "EXECUTE_AEROELASTIC_ANALYSIS" not in body
    assert not ws.is_steady_aeroelastic_script(script.render())
    post = _commands(script.pending_input_files[ws.POST_FILE].splitlines())
    assert post[:4] == [
        "UPDATE_ALL_SURFACE_SECTIONS",
        "COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS",
        "EXPORT_SURFACE_SECTIONAL_LOADS",
        ws.LOADS_FILE,
    ]
    assert post[4:] == [
        "SET_VTK_EXPORT_VARIABLES -1 DISABLE",
        "EXPORT_SOLVER_ANALYSIS_VTK",
        ws.DEFORMED_SURFACE_FILE,
        "SURFACES -1",
    ]


def test_the_staged_wing_files_are_the_configuration_s(tmp_path):
    case = steady_wing_case(tmp_path)
    _lines_, script = _lines(case)
    run_dir = tmp_path / "run"
    hashes = _write_pending_files(script, run_dir, case=case, recorded={})
    assert {"config.json", "fsi_nodes.csv", "fsi_family_map.json", "fsi_post.txt"} <= set(hashes)
    staged = json.loads((run_dir / "config.json").read_text())
    assert staged["wing"]["self_weight"] is True
    assert staged["wing"]["gravity_m_per_s2"] == [0.0, 0.0, -G0]


def test_a_steady_coupled_row_is_one_process_per_point(tmp_path):
    campaign = SimpleNamespace(matrix_stem="matrix")
    case = steady_wing_case(tmp_path)
    assert _is_one_job(campaign, case.model_copy(update={"fsi": None}))
    assert not _is_one_job(campaign, case)


def test_the_steady_coupled_route_refuses_what_it_cannot_export(tmp_path):
    case = steady_wing_case(tmp_path)
    solver = case.solver.model_copy(update={"clear_vorticity_drag_boundaries": True})
    with pytest.raises(CampaignConfigError, match="EXECUTE_AEROELASTIC_ANALYSIS"):
        _lines(case.model_copy(update={"solver": solver}))


def test_sections_in_a_frame_off_the_wing_origin_are_refused(tmp_path):
    case = steady_wing_case(tmp_path)
    moved = case.reference.model_copy(update={"moment_point_m": (0.0, 0.5, 0.0)})
    with pytest.raises(CampaignConfigError, match="origin_m"):
        _lines(case.model_copy(update={"reference": moved}))


# --------------------------------------------------------------------------
# The structure: its own weight, the flag, and nothing centrifugal.


def test_the_weight_of_a_uniform_wing_deflects_it_as_a_cantilever_under_mg():
    # P0300-FSIG-WEIGHT
    mu, ei = 3.0, 2.0e5
    cfg = wing_config(mass_per_length_kg_per_m=mu, bending_stiffness_n_m2=ei)
    solution = wing.solve_wing_static(cfg)
    q = mu * G0  # the weight per unit span, downward: toward -z, against the suction side
    expected = -q * SPAN_M**4 / (8.0 * ei)
    assert solution.flap_deflection_m[-1] == pytest.approx(expected, rel=1e-9)
    assert solution.flap_deflection_m[0] == 0.0
    assert all(abs(t) < 1e-15 for t in solution.elastic_twist_rad)


def test_gravity_is_not_turned_by_the_section_pitch_beyond_its_projection():
    cfg = wing_config(pitch_deg=10.0)
    flap, torsion = wing.weight_loads(cfg)
    assert flap[0] == pytest.approx(-3.0 * G0 * math.cos(math.radians(10.0)), rel=1e-12)
    assert torsion == [0.0] * STATIONS


def test_the_weight_flag_off_removes_the_weight():
    cfg = wing_config(self_weight=False)
    assert wing.weight_loads(cfg) == ([0.0] * STATIONS, [0.0] * STATIONS)
    solution = wing.solve_wing_static(cfg)
    assert all(w == 0.0 for w in solution.flap_deflection_m)
    loaded = wing.solve_wing_static(cfg, flap_load_n_per_m=[10.0] * STATIONS)
    assert loaded.flap_deflection_m[-1] == pytest.approx(10.0 * SPAN_M**4 / (8.0 * 2.0e5))


def test_a_wing_configuration_that_turns_is_refused():
    base = wing_config()
    with pytest.raises(ValueError, match="does not turn"):
        FsiConfig.model_validate({**base.model_dump(), "omega_rad_per_s": 10.0})
    with pytest.raises(ValueError, match="blade_count = 1"):
        FsiConfig.model_validate({**base.model_dump(), "blade_count": 2})


def _wing_loads_export(iteration: int, *, unsteady: bool, fz_n_per_m: float = 50.0) -> str:
    """A synthetic XZ-cut export of the wing: offsets along +y, uniform lift."""
    rows = []
    count = 20
    for k in range(count):
        y = SPAN_M * (k + 0.5) / count
        rows.append(
            f" {y:.4E}, {CHORD_M:.4E}, 0.0000E+00, 0.0000E+00, 0.0000E+00, "
            f"{fz_n_per_m:.4E}, 0.0000E+00,"
        )
    clock = "     Time increment (sec)                        .010\n" if unsteady else ""
    mode = "Unsteady" if unsteady else "Steady"
    return (
        "\n\n                              FlightStream Surface Sectional Loads\n\n"
        "     Simulation file:                            Default.fsm\n"
        "     Angle of attack (Deg)                       5.000\n"
        "     Side-slip angle (Deg)                       .000\n"
        "     Freestream velocity (m/s)                   30.000\n"
        f"{clock}"
        f"     Solver mode:                                {mode}\n"
        "     Reference velocity (m/s)                    30.000\n"
        "     Reference length (m)                        1.000\n"
        "     Reference area (m^2)                        8.000\n"
        "     Coordinate frame for analysis:              MRP\n"
        f"     Current solver iteration number:            {iteration}\n"
        "     " + "-" * 100 + "\n"
        f"     Number of Surface Sections:                 {count}\n"
        "     " + "-" * 100 + "\n"
        "     Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment\n"
        "     " + "-" * 100 + "\n" + "\n".join(rows) + "\n"
        "     " + "-" * 100 + "\n"
        "     Force Units: Newtons\n"
        "     Moment Units: Newton-Meter\n"
    )


def _staged_run(tmp_path: Path, make, cfg: FsiConfig) -> Path:
    case = make(tmp_path, cfg)
    _lines_, script = _lines(case)
    run_dir = tmp_path / "run"
    _write_pending_files(script, run_dir, case=case, recorded={})
    dump_config(cfg, run_dir / "config.json")
    return run_dir


@pytest.mark.parametrize(
    "make, unsteady",
    [(steady_wing_case, False), (unsteady_wing_case, True)],
    ids=["steady", "unsteady"],
)
def test_the_wing_call_reaches_no_centrifugal_term(tmp_path, monkeypatch, make, unsteady):
    # P0300-FSIG-WEIGHT
    def refused(*_args, **_kwargs):
        raise AssertionError("a fixed wing reached the rotating blade's centrifugal solve")

    for name in (
        "solve_rotating_static",
        "axial_load_distribution",
        "propeller_moment_distribution",
        "in_plane_softening_coefficients",
    ):
        monkeypatch.setattr(centrifugal, name, refused)
    cfg = wing_config(self_weight=False)
    run_dir = _staged_run(tmp_path, make, cfg)
    (run_dir / driver.LOADS_FILE).write_text(_wing_loads_export(60, unsteady=unsteady))
    result = driver.coupling_step(run_dir)
    assert result.phase == driver.FIXED_WING_PHASE
    assert result.revolutions is None
    # Uniform lift of 50 N/m and no weight: the tip bends toward the suction
    # side by q L^4 / (8 EI), relaxed once from rest by the configured lambda.
    tip = result.solutions[0].flap_deflection_m[-1]
    assert tip == pytest.approx(50.0 * SPAN_M**4 / (8.0 * 2.0e5), rel=1e-6)
    layout = nodes.load_node_map(run_dir / cfg.node_map_file)
    written = nodes.read_fsidisp(run_dir / driver.DISPLACEMENT_FILE)
    tip_row = layout.row_index(0, STATIONS - 1, "elastic_axis")
    assert written[tip_row] == pytest.approx([0.0, 0.0, cfg.phases.coupling_relaxation * tip])
    # A second call on the same loads is refused as stale.
    with pytest.raises(Exception, match="not ahead"):
        driver.coupling_step(run_dir)


def test_the_wing_call_carries_its_weight_into_the_displacement(tmp_path):
    cfg = wing_config()
    run_dir = _staged_run(tmp_path, steady_wing_case, cfg)
    (run_dir / driver.LOADS_FILE).write_text(_wing_loads_export(60, unsteady=False, fz_n_per_m=0.0))
    result = driver.coupling_step(run_dir)
    assert result.solutions[0].flap_deflection_m[-1] == pytest.approx(
        -3.0 * G0 * SPAN_M**4 / (8.0 * 2.0e5), rel=1e-6
    )


# --------------------------------------------------------------------------
# The nodes: inside the wing's section, stored in the reference frame.


def test_the_wing_nodes_sit_inside_its_sections_in_the_reference_frame():
    cfg = wing_config()
    layout = nodes.generate_node_layout(cfg)
    assert layout.embedding == "wing_frame"
    assert all(item.ok for item in nodes.node_clearances(layout, cfg.blade.section_contours_m))
    positions = nodes.node_positions(layout)
    # Station 0: the elastic-axis node on the quarter chord, the LE node at
    # 10 % chord (x = 0.1) and the TE node at 90 % (x = 0.9), x aft.
    assert positions[0] == pytest.approx([0.25, 0.0, 0.0])
    assert positions[1] == pytest.approx([0.1, 0.0, 0.0])
    assert positions[2] == pytest.approx([0.9, 0.0, 0.0])
    assert positions[-3] == pytest.approx([0.25, SPAN_M, 0.0])


def test_a_wing_too_thin_for_its_nodes_is_refused_at_plan_naming_the_node(tmp_path):
    cfg = wing_config(thickness_ratio=0.004)
    with pytest.raises(FsiInputError, match=r"row 1 \(station 0, .*leading_edge"):
        nodes.generate_node_layout(cfg)
    with pytest.raises(CampaignConfigError, match=r"FSI structural nodes: .*row 1 \(station 0"):
        _lines(steady_wing_case(tmp_path, cfg))


# --------------------------------------------------------------------------
# The run: a steady coupled process is stopped once its analysis ended.


def test_a_steady_coupled_process_is_stopped_after_its_completion_line(tmp_path):
    program = (
        "import sys, time\n"
        "print('Aeroelastic solver residual for FSI iteration-1 is  0.0000000E+0')\n"
        f"print({ws.STEADY_AEROELASTIC_COMPLETION!r} + ': .02 minutes.')\n"
        "sys.stdout.flush()\n"
        "time.sleep(600)\n"
    )
    # The base interpreter, not the venv launcher: on Windows a venv's
    # python.exe starts the interpreter as a child that inherits the stdout
    # handle and still holds it for a moment after the launcher is killed, so
    # the removal of the stdout file can miss. Measured: 2 of 10 and 3 of 20
    # leftover files through the launcher, 0 of 20 with the base interpreter.
    interpreter = getattr(sys, "_base_executable", None) or sys.executable
    argv = [interpreter, "-c", program]
    code, out, err, timed_out = _run_until_the_analysis_ends(argv, tmp_path, 60.0)
    assert (code, timed_out) == (0, False)
    assert ws.STEADY_AEROELASTIC_COMPLETION in out
    assert (
        "stopped after the aeroelastic analysis ended"
        in (tmp_path / "pyfs-aeroelastic-stop.log").read_text()
    )
    assert not (tmp_path / "pyfs-solver-stdout.txt").exists()


def test_a_process_that_exits_first_returns_its_own_code(tmp_path):
    argv = [sys.executable, "-c", "import sys; print('no analysis'); sys.exit(3)"]
    code, out, _err, timed_out = _run_until_the_analysis_ends(argv, tmp_path, 60.0)
    assert (code, timed_out) == (3, False)
    assert "no analysis" in out


def test_the_beam_helpers_are_the_blade_s():
    # The wing reuses the blade's beam: the uniform-load closed form holds on
    # the beam directly, so the wing adds loads and not a second model.
    cfg = wing_config()
    model = beam.build_beam_model(cfg)
    beam.apply_station_loads(model, cfg, flap_load_n_per_m=[1.0] * STATIONS)
    beam.solve_static(model)
    tip = beam.extract_solution(model, cfg).flap_deflection_m[-1]
    assert tip == pytest.approx(SPAN_M**4 / (8.0 * 2.0e5), rel=1e-9)
