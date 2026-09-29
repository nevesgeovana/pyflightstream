"""Tier 1: the defects the short licensed runs of 0.30.0 (L1, RPT-090 to RPT-092) found.

1. A coupled row with the pproc's DEFAULT exports did not build: the
   aeroelastic post-processing script exported the loads the structural
   program reads, and the row's export block then updated the sections again,
   an analysis command after an export (``ScriptOrderError``), on the
   quasi-steady sector and on the fixed wing alike. The earlier tests built
   their coupled rows with a loads table and a log only, so they never
   declared a section export.
2. A quasi-steady wheel solved at k clockings exports ONE solver log holding
   its k solves in sequence, each residual table counting from 1 again, and
   the residual reader refused it as two logs concatenated: no log was read,
   the point carried no residual, and on the points-file route the
   trailing-edge verdict failed the point for want of the log that said the
   edges were imported (RPT-091 F1).
3. A clocked wheel's section distribution was created with the wheel at
   clocking 1, and the solver freezes the cut planes over the blade's extent
   in that pose, so at clocking 0, where the sections are exported, the cuts
   missed the blade's root and left its outer part uncut (RPT-091 F2).
4. No quasi-steady point got a rotor table: the table reads a rotor's speed
   from the record's reductions, which a steady run does not plan (RPT-090
   F3, RPT-091 F3).

Every expected value is worked from the definitions and the fixture, never
read off the implementation.
"""

from __future__ import annotations

import json
import math
import warnings
from pathlib import Path

import pytest

from pyflightstream.cases import PprocSpec, SimCase
from pyflightstream.cases import fsi_workspace as ws
from pyflightstream.results import (
    MalformedOutputError,
    parse_residual_history,
    parse_residual_solves,
)
from pyflightstream.run import LoadsAssessor
from pyflightstream.run._wake_edge_verdict import collected_solver_log, wake_edge_import_verdict
from pyflightstream.workspace import RunRecord, RunStatus
from tests.tier1_offline.test_fsig_fixed_wing import steady_wing_case
from tests.tier1_offline.test_goal035_qsteady_completion import _sector_fsi_case
from tests.tier1_offline.test_goal035_qsteady_rotor import (
    LOADS,
    _blade_obj,
    _case,
    _lines,
    _with_obj,
)

#: The analysis commands the row's exports read (the phase order places every
#: one of them before the first export).
UPDATES = ("UPDATE_ALL_SURFACE_SECTIONS", "COMPUTE_SURFACE_SECTIONAL_LOADS", "UPDATE_PROBE_POINTS")


def _with_default_outputs(case: SimCase, stem: str = "DP") -> SimCase:
    """The row as the campaign renders it: its pproc's default outputs, named for the point."""
    assert case.pproc is not None
    names = [name.replace("{name}", stem) for name in case.pproc.outputs(False)]
    return case.model_copy(update={"outputs": names})


def _post_commands(case: SimCase) -> list[str]:
    """Plan the row and return the command lines of its post-processing script."""
    _, script = _lines(case)
    text = script.pending_input_files[ws.POST_FILE]
    return [line.split()[0] for line in text.splitlines() if line.strip() and line[0].isupper()]


def _assert_one_valid_order(commands: list[str]) -> None:
    exports = [
        at
        for at, command in enumerate(commands)
        if command.startswith(("EXPORT_", "SAVEAS", "SAVE_PLOT", "SET_PLOT_TYPE"))
    ]
    updates = [at for at, command in enumerate(commands) if command in UPDATES]
    # The sections are updated and their loads computed ONCE, the probe points
    # once, and every update precedes every export.
    assert [commands[at] for at in updates] == list(UPDATES)
    assert max(updates) < min(exports)


def _declares_the_section_kinds(case: SimCase) -> None:
    names = " ".join(case.outputs)
    for suffix in ("_cp.txt", "_sloads.txt", "_probes.txt", "_plot_cp_sections.txt"):
        assert suffix in names, suffix


def test_a_coupled_sector_with_the_default_exports_plans_in_one_valid_order(tmp_path):
    # P0300-QS-SECTOR-FSI
    case = _with_default_outputs(_sector_fsi_case(tmp_path))
    _declares_the_section_kinds(case)
    commands = _post_commands(case)
    _assert_one_valid_order(commands)
    text = _lines(case)[1].pending_input_files[ws.POST_FILE]
    # The loads the structural program reads come first, the row's own
    # section exports after them, each once.
    assert text.index(ws.LOADS_FILE) < min(text.index("DP_cp.txt"), text.index("DP_sloads.txt"))
    assert commands.count("EXPORT_SURFACE_SECTIONAL_LOADS") == 2
    assert commands.count("EXPORT_ALL_SURFACE_SECTIONS") == 1
    assert commands.count("EXPORT_PROBE_POINTS") == 1


def test_a_coupled_fixed_wing_with_the_default_exports_plans_in_one_valid_order(tmp_path):
    # P0300-FSIG-STEADY
    case = _with_default_outputs(steady_wing_case(tmp_path))
    _declares_the_section_kinds(case)
    commands = _post_commands(case)
    _assert_one_valid_order(commands)
    assert commands.count("EXPORT_ALL_SURFACE_SECTIONS") == 1
    assert commands.count("EXPORT_PROBE_POINTS") == 1


# ------------------------------------ 2: a clocked wheel's log of k solves --

#: The line shapes of a real 26.124 log of a wheel solved at two clockings
#: (the L1 run of RPT-091): every line followed by a line holding one NUL,
#: CRLF endings, the residual table's header and its dashed rules, each row
#: an iteration padded to 19 columns and five tab-separated cells. The values
#: are synthetic; the structure is the log's.
_RULE = "-" * 300
_HEADER = (
    "Iteration                      Res. Vel.                 Res. Pres.                "
    "CL                             CDi (vorticity)               CM"
)


def _cell(value: float) -> str:
    """A cell as the log prints it: sign, seven decimals, an unpadded exponent."""
    mantissa, exponent = f"{value:+.7E}".split("E")
    return f"{mantissa}E{int(exponent):+d}      "


def _solve(rows: int, final: float) -> list[str]:
    """One solve's residual table: from 1.0 at iteration 1 down to ``final`` at ``rows``."""
    lines = ["", "Angle of attack (Deg): 5.000", "", _RULE, _HEADER, _RULE]
    for iteration in range(1, rows + 1):
        residual = final ** ((iteration - 1) / (rows - 1))
        cells = [residual, residual * 0.8, 1.2e-2, -6.5e-2, 4.2e-4]
        lines.append(f"{iteration:<19}\t" + "\t".join(_cell(value) for value in cells).rstrip())
    return [*lines, _RULE, "Solver run time: .0614167 minutes."]


def _initialisation() -> list[str]:
    return [
        "Symmetry is disabled.",
        "Following geometry is being initialized:",
        "Poly\tBoundary",
        *(f"Yes\tBlade{blade}" for blade in (1, 2, 3)),
        "150 trailing edges found.",
        "Solver initialized in .63 seconds",
        "Solver mode: Steady",
    ]


def _wheel_log(finals: tuple[float, ...], rows: tuple[int, ...]) -> str:
    """The log of a wheel solved at len(finals) clockings, in the order the run solves them.

    As the run writes it: the trailing edges imported once, a first
    initialisation cleared, then each clocking initialised and solved, the
    clockings 1 to k - 1 each writing its loads export, clocking 0 last.
    """
    lines = [
        "FlightStream version 26.1, build #8172026",
        "Running script file: P.txt",
        "3 bodies, 54 vertices and 48 faces imported.",
        "150 trailing edges imported for boundary Blade3",
        *_initialisation(),
    ]
    count = len(finals)
    for solve, (final, rows_of) in enumerate(zip(finals, rows, strict=True)):
        lines += ["Solution cleared. Initialization removed.", *_initialisation()]
        lines += _solve(rows_of, final)
        written = f"DP_qs{solve + 1:02d}.txt" if solve < count - 1 else "DP.txt"
        lines += ["Data written to external text file:", written, ""]
    return "".join(f"{line}\r\n\x00\r\n" for line in lines)


def _loads(iteration: int) -> str:
    return LOADS.replace(
        "Current solver iteration number:            60",
        f"Current solver iteration number:            {iteration}",
    ).format(c1="+0.1", c2="+0.2", c3="+0.3")


def _clocked_wheel(
    tmp_path: Path, finals: tuple[float, ...], rows: tuple[int, ...] | None = None
) -> tuple[SimCase, Path]:
    """A wheel point of len(finals) clockings as its run leaves it, and its simulation folder.

    Its record is the one the builder parks (clockings 0, 40 and 80 deg on
    three blades at k = 3; 0 and 60 deg at k = 2); each loads export is
    written at its solve's last iteration.
    """
    rows = rows or tuple(61 for _ in finals)
    case = _case(PASSAGE_POSITIONS=str(len(finals)), ALPHA_POINT=5.0)
    _, script = _lines(case)
    sim = tmp_path / "sim"
    outputs = sim / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "DP_qsteady.json").write_text(
        str(script.pending_input_files["DP_qsteady.json"]), encoding="utf-8"
    )
    # Log order: clockings 1 to k - 1, then 0.
    for solve, rows_of in enumerate(rows):
        name = f"DP_qs{solve + 1:02d}.txt" if solve < len(rows) - 1 else "DP.txt"
        (outputs / name).write_text(_loads(rows_of), encoding="utf-8")
    (outputs / "DP_log.txt").write_bytes(_wheel_log(finals, rows).encode("utf-8"))
    return case, sim


def test_a_log_of_two_clockings_reads_as_two_solves_and_never_as_one():
    # P0300-QS-WHEEL
    text = _wheel_log((1.2e-6, 1.1e-6), (61, 61))
    solves = parse_residual_solves(text)
    assert [[sample.iteration for sample in solve][::60] for solve in solves] == [[1, 61], [1, 61]]
    assert [solve[-1].velocity_residual for solve in solves] == pytest.approx([1.2e-6, 1.1e-6])
    # The guard of a log of one solve stands: 61 back to 1 is two logs to it.
    with pytest.raises(MalformedOutputError, match="from 61 to 1"):
        parse_residual_history(text)


def test_a_restart_that_is_not_a_new_table_from_one_is_refused():
    text = _wheel_log((1.2e-6, 1.1e-6), (61, 61))
    # A restart at 5 opening the second table is no solve the solver started.
    at = text.index("1                  \t", text.index("Data written"))
    with pytest.raises(MalformedOutputError, match="from 61 to 5"):
        parse_residual_solves(text[:at] + "5" + text[at + 1 :])
    # A counter falling inside one table is refused as before.
    fallen = text.replace("30                 \t", "3                  \t", 1)
    with pytest.raises(MalformedOutputError, match="from 29 to 3"):
        parse_residual_solves(fallen)


def test_a_restart_to_one_without_a_new_page_is_refused():
    """Counter 1, 2, 3, 1, 2 with no new Iteration header: one bad table, not two solves."""
    # P0300-QS-WHEEL
    lines = ["", "Angle of attack (Deg): 5.000", "", _RULE, _HEADER, _RULE]
    for iteration in (1, 2, 3, 1, 2):
        cells = [1.0e-3, 0.8e-3, 1.2e-2, -6.5e-2, 4.2e-4]
        lines.append(f"{iteration:<19}\t" + "\t".join(_cell(value) for value in cells).rstrip())
    lines += [_RULE, "Solver run time: .0614167 minutes."]
    text = "".join(f"{line}\r\n\x00\r\n" for line in lines)
    match = "goes from 3 to 1 inside one solve, so it does not increase"
    with pytest.raises(MalformedOutputError, match=match):
        parse_residual_solves(text)


def test_a_wheel_is_judged_clocking_by_clocking_from_its_one_log(tmp_path):
    """Two converged clockings: CONVERGED, the log named, one verdict each, the largest residual.

    The residual of a solve is the larger of its final velocity and pressure
    residuals, the velocity one here (the pressure one is 0.8 of it); the
    limit is 1e-5.
    """
    # P0300-QS-WHEEL
    case, sim = _clocked_wheel(tmp_path, (2.0e-6, 3.0e-6))
    assessment = LoadsAssessor()(case, None, sim)
    assert assessment.status is RunStatus.CONVERGED, assessment.error
    assert assessment.log_file_used == "DP_log.txt"
    assert assessment.iterations == 61
    assert assessment.residual == pytest.approx(3.0e-6)
    # In the order the run solved them: clocking 1 (60 deg), then clocking 0.
    verdicts = assessment.clocking_verdicts
    assert verdicts is not None
    assert [(v["index"], v["clocking_deg"], v["status"]) for v in verdicts] == [
        (1, 60.0, "CONVERGED"),
        (0, 0.0, "CONVERGED"),
    ]
    assert [v["residual"] for v in verdicts] == pytest.approx([2.0e-6, 3.0e-6])
    assert [v["iterations"] for v in verdicts] == [61, 61]
    # The record carries them, and a record of any other point carries no key.
    stated = {
        "run_id": "r",
        "sim_id": "9001",
        "fs_version_requested": "26.124",
        "package_version": "0.30.0",
        "script_sha256": "0" * 64,
        "raw_flag": False,
    }
    record = RunRecord(**stated, status=assessment.status, clocking_verdicts=verdicts)
    assert json.loads(record.model_dump_json())["clocking_verdicts"][0]["index"] == 1
    plain = RunRecord(**stated, status=RunStatus.CONVERGED)
    assert "clocking_verdicts" not in json.loads(plain.model_dump_json())


def test_the_worst_clocking_is_the_point_s_verdict(tmp_path):
    """Clocking 1 of three stops above the limit: the point is COMPLETED_MAX_ITER, naming it."""
    case, sim = _clocked_wheel(tmp_path, (4.0e-5, 2.0e-6, 3.0e-6), (500, 61, 70))
    assessment = LoadsAssessor()(case, None, sim)
    assert assessment.status is RunStatus.COMPLETED_MAX_ITER, assessment.error
    assert assessment.residual == pytest.approx(4.0e-5)
    assert assessment.iterations == 70
    verdicts = assessment.clocking_verdicts
    assert verdicts is not None
    assert [(v["index"], v["status"], v["iterations"]) for v in verdicts] == [
        (1, "COMPLETED_MAX_ITER", 500),
        (2, "CONVERGED", 61),
        (0, "CONVERGED", 70),
    ]


def test_a_clocking_whose_export_is_not_of_its_solve_fails_the_point(tmp_path):
    case, sim = _clocked_wheel(tmp_path, (2.0e-6, 3.0e-6))
    (sim / "outputs" / "DP_qs01.txt").write_text(_loads(40), encoding="utf-8")
    assessment = LoadsAssessor()(case, None, sim)
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    assert "clocking 1" in (assessment.error or "") and "iteration 40" in (assessment.error or "")


def test_a_log_short_of_a_clocking_is_refused(tmp_path):
    """The record says two clockings and the log holds one solve: nothing is judged from it."""
    case, sim = _clocked_wheel(tmp_path, (2.0e-6, 3.0e-6))
    (sim / "outputs" / "DP_log.txt").write_bytes(_wheel_log((3.0e-6,), (61,)).encode("utf-8"))
    assessment = LoadsAssessor(log_file="DP_log.txt")(case, None, sim)
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    assert "1 solve(s)" in (assessment.error or "") and "2 clockings" in (assessment.error or "")


def test_a_log_with_a_clocking_too_many_is_refused(tmp_path):
    """The record says two clockings and the log holds three solves: nothing is judged from it."""
    # P0300-QS-WHEEL
    case, sim = _clocked_wheel(tmp_path, (2.0e-6, 3.0e-6))
    (sim / "outputs" / "DP_log.txt").write_bytes(
        _wheel_log((2.0e-6, 3.0e-6, 4.0e-6), (61, 61, 61)).encode("utf-8")
    )
    assessment = LoadsAssessor(log_file="DP_log.txt")(case, None, sim)
    assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    assert "3 solve(s)" in (assessment.error or "") and "2 clockings" in (assessment.error or "")


def test_the_trailing_edge_verdict_reads_the_wheel_s_log(tmp_path):
    """The points-file route: the log read says 150 edges imported, the count the script wrote."""
    case, sim = _clocked_wheel(tmp_path, (2.0e-6, 3.0e-6))
    assessment = LoadsAssessor()(case, None, sim)
    collected = ["outputs/DP.txt", "outputs/DP_log.txt"]
    log_text = collected_solver_log(sim, collected, assessment.log_file_used)
    assert log_text is not None
    assert wake_edge_import_verdict(150, log_text) is None


# ------------------------------- 3: a clocked wheel's sections cover its blade --


def _cuts_the_solver_places(
    lines: list[str], obj: Path, family: str, *, which: int = 0
) -> list[float]:
    """Where the solver puts a distribution's cuts, by the rule L1 measured.

    The solver freezes the cut planes when the distribution is created, over
    the surface's extent along the plane's normal in the pose it then holds,
    and places N cuts at the middles of N equal intervals of that extent
    (RPT-091: created with a six-blade wheel clocked 30 deg, whose blade one
    then spanned 0.3253 to 1.6078 m along the normal, the 30 cuts ran from
    0.3467 to 1.5860 m, 0.04275 m apart). The pose is the sum of the
    ROTATE_SURFACE angles about the shaft (x) the script emitted before it.
    ``which`` picks the distribution by its order in the script, -1 the last.
    """
    at = [n for n, line in enumerate(lines) if line == "NEW_SURFACE_SECTION_DISTRIBUTION"][which]
    pose = sum(float(line.split()[3]) for line in lines[:at] if line.startswith("ROTATE_SURFACE"))
    block = lines[at : at + 8]
    plane = next(line.split()[1] for line in block if line.startswith("PLANE"))
    count = int(next(line.split()[1] for line in block if line.startswith("NUM_SECTIONS")))
    normal = {"XY": 2, "XZ": 1, "YZ": 0}[plane]
    turn = math.radians(pose)
    extent = []
    for x, y, z in _vertices(obj, family):
        # A turn about x by the pose; the extent along y or z is even in the
        # angle, so the sense of the turn does not matter here.
        turned = (
            x,
            y * math.cos(turn) - z * math.sin(turn),
            y * math.sin(turn) + z * math.cos(turn),
        )
        extent.append(turned[normal])
    low, high = min(extent), max(extent)
    step = (high - low) / count
    return [low + (index + 0.5) * step for index in range(count)]


def _vertices(obj: Path, family: str) -> list[tuple[float, float, float]]:
    vertices: list[tuple[float, float, float]] = []
    used: set[int] = set()
    group = None
    for line in obj.read_text(encoding="utf-8").splitlines():
        if line.startswith("o "):
            group = line.split()[1]
        elif line.startswith("v "):
            x, y, z = (float(value) for value in line.split()[1:4])
            vertices.append((x, y, z))
        elif line.startswith("f ") and group == family:
            used.update(int(token) - 1 for token in line.split()[1:])
    return [vertices[index] for index in sorted(used)]


def test_a_clocked_wheel_cuts_its_sections_over_the_blade_s_radial_span(tmp_path):
    """Two clockings of three blades, 0 and 60 deg: the cuts span 0.2 to 1.0 m, the blade's radii.

    Blade one of the fixture lies along +y from r = 0.2 to 1.0 m, so its
    sections are cut normal to y (plane XZ). Eight cuts over that span sit at
    0.25, 0.35, ... 0.95 m: the first and the last half a spacing, 0.05 m,
    inside each end. Cut with the wheel at 60 deg they would span 0.1 to 0.5
    m along y (r cos 60), the first cut outside the blade and the outer half
    of the blade uncut.
    """
    # P0300-QS-WHEEL
    obj = _blade_obj(tmp_path / "wheel.obj")
    case = _with_obj(
        _case(PASSAGE_POSITIONS="2", ALPHA_POINT=5.0), obj, ("Blade1", "Blade2", "Blade3")
    )
    case = case.model_copy(
        update={
            "pproc": PprocSpec.model_validate(
                {
                    "sections": {
                        "count": 8,
                        "include_symmetry": False,
                        "distributions": [
                            {"families": ["Blade1"], "frame": "PROP_SMRP", "planes": ["XZ"]}
                        ],
                    }
                }
            )
        }
    )
    lines, _ = _lines(case)
    # 0.31.0, the owner's changed requirement (P0310-G1-EVERY-CLOCKING): the
    # distribution is created again at each of the two clockings, the last one
    # at clocking 0; test_goal036_wheel_sections.py cuts every clocking.
    assert lines.count("NEW_SURFACE_SECTION_DISTRIBUTION") == 2
    radii = [math.hypot(y, z) for _, y, z in _vertices(obj, "Blade1")]
    inner, outer = min(radii), max(radii)
    assert (inner, outer) == pytest.approx((0.2, 1.0))
    cuts = _cuts_the_solver_places(lines, obj, "Blade1", which=-1)
    assert inner < cuts[0] and cuts[-1] < outer
    assert cuts == pytest.approx([0.25 + 0.1 * index for index in range(8)])
    # The wheel is back at clocking 0, as the cuts were made, for the solve
    # whose exports carry the sections.
    last_start = max(at for at, line in enumerate(lines) if line == "START_SOLVER")
    assert sum(
        float(line.split()[3]) for line in lines[:last_start] if line.startswith("ROTATE_SURFACE")
    ) == pytest.approx(0.0)
    assert "EXPORT_ALL_SURFACE_SECTIONS" not in lines[:last_start]


# ------------------------------------ 4: the rotor table of a qsteady_rotor point --

#: The reference of polar 6001 of the recorded campaign, now declaring its two
#: surfaces a rotor, PROP: shaft X through the origin, 2 m.
_PROP_REFERENCE = """area_m2 = 50.0
chord_m = 2.526
span_m = 20.0

[rotors.PROP]
alias = "PROP"
x_m = 0.0
y_m = 0.0
z_m = 0.0
axis = "X"
rpm_sign = 1
diameter_m = 2.0
families_blades = ["W", "B"]
blade1 = { azimuth_deg = 0.0, zero = "Y" }
"""


def _posted_qsteady(tmp_path: Path, case: str) -> tuple[dict, Path]:
    """Polar 6001 re-recorded as a quasi-steady ``case`` at 1200 rev/min, then posted.

    A wheel of two clockings (0 and 90 deg) whose clocking 1 export carries a
    W surface Cx 0.01 higher; a sector of one solve.
    """
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r001.toml").write_text(
        _PROP_REFERENCE, encoding="utf-8"
    )
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6001":
            loads = workspace.sim_dir("6001") / record.outputs[0]
            positions = [{"index": 0, "clocking_deg": 0.0, "rotated_deg": 0.0, "loads": loads.name}]
            if case == "wheel":
                clocked = loads.with_name(loads.stem + "_qs01.txt")
                clocked.write_text(
                    loads.read_text().replace("W,+0.0193288", "W,+0.0293288"), encoding="utf-8"
                )
                positions.append(
                    {"index": 1, "clocking_deg": 90.0, "rotated_deg": 90.0, "loads": clocked.name}
                )
            # 0.31.0: the whole record the builder writes, which its one
            # reader refuses to take in part.
            quasi = {
                "schema_version": 1,
                "run_type": "qsteady_rotor",
                "case": case,
                "rotor": "PROP",
                "blades": 2,
                "rpm": 1200.0,
                "shaft_frame_axis": "X",
                "hub_m": [0.0, 0.0, 0.0],
                "axis_vector": [1.0, 0.0, 0.0],
                "diameter_m": 2.0,
                "families_general": [],
                "families_blades": ["W", "B"],
                "blade1_azimuth_deg": 0.0,
                "positions": positions,
                "validity": None,
            }
            loads.with_name(loads.stem + "_qsteady.json").write_text(json.dumps(quasi))
            record = record.model_copy(update={"recipe": "qsteady_rotor"})
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _post(workspace)
    (manifest,) = workspace.root.rglob("products.json")
    return json.loads(manifest.read_text(encoding="utf-8")), manifest.parent


def _rotor_rows(products: dict, folder: Path) -> list[dict[str, str]]:
    (name,) = [name for name in products["products"] if name.endswith("PROP_rotor.csv")]
    head, *rows = (folder / name).read_text(encoding="utf-8").splitlines()
    return [dict(zip(head.split(","), row.split(","), strict=True)) for row in rows]


#: The dynamic pressure of polar 6001's exports and what divides a thrust into
#: CT: 0.5 * 1.225 * 68.058^2 Pa over 50 m2; rho n^2 D^4 = 1.225 * 20^2 * 2^4.
_QS = 0.5 * 1.225 * 68.058**2 * 50.0
_RHO_N2_D4 = 1.225 * 20.0**2 * 2.0**4


def test_a_quasi_steady_wheel_gets_its_rotor_table_at_the_row_s_speed(tmp_path):
    """The speed from the row's record, 1200 rev/min; CT from clocking 0, the point's own solve.

    The definitions page: a quasi-steady point's rotor table is written as any
    steady point's, the instant of its own solve, on a wheel clocking 0, and the
    mean over the clockings is the average table's. The thrust is the force
    along the shaft (+x): W's Cx plus B's, 0.0274326 at clocking 0 (0.0374326
    at clocking 1), so CT = 0.0274326 q S / (rho n^2 D^4).
    """
    # P0300-QS-WHEEL
    products, folder = _posted_qsteady(tmp_path, "wheel")
    rows = _rotor_rows(products, folder)
    assert len(rows) == 2
    for row in rows:
        assert float(row["RPM_PROP"]) == pytest.approx(1200.0)
        assert float(row["DIAMETER_PROP"]) == pytest.approx(2.0)
        assert float(row["CT_PROP"]) == pytest.approx(0.0274326 * _QS / _RHO_N2_D4, rel=1e-5)
        # J = V / (n D) at the free stream the export states, 68.058 m/s.
        assert float(row["J_PROP"]) == pytest.approx(68.058 / (20.0 * 2.0), rel=1e-5)


def test_a_quasi_steady_sector_gets_its_rotor_table_from_its_one_solve(tmp_path):
    """The sector's export read as it stands: the package never multiplies by copies or blades."""
    # P0300-QS-SECTOR
    products, folder = _posted_qsteady(tmp_path, "sector")
    rows = _rotor_rows(products, folder)
    assert len(rows) == 2
    for row in rows:
        assert float(row["RPM_PROP"]) == pytest.approx(1200.0)
        assert float(row["CT_PROP"]) == pytest.approx(0.0274326 * _QS / _RHO_N2_D4, rel=1e-5)
