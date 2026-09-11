"""FR-89: one derived file per polar and group carries everything the workspace knows.

THE UNION IS BUILT FROM THE WORKSPACE HERE AND NEVER LISTED, which is the
whole requirement and the reason this module is shaped the way it is. A test
that spelled the expected column names out would pass for ever while a field
added upstream never reached the file, and that defect is exactly what the
author's acceptance sentence rules out: if she has to open a second file to
know something about that simulation, it failed.

So :func:`_the_union_the_workspace_knows` READS the workspace: the header of
every polar table, the header of ``campaign_sweep.csv``, the header of every
plots table, the cells of the run matrix and the keys inside them, and the
manifest's own flight condition, rotor speeds and solver flags. It parses the
matrix and the manifest with the standard library rather than through the
package's own readers, deliberately: a gatherer shared with the writer would
agree with the writer by construction, which is a fixture encoding the defect
it should expose.

The fixture is built from the shape of the workspace that RAN on the licensed
machine on 2026-09-11, `GeoverseResearch/tools/fts_workspace/pfs0160`: two
polars of one matrix, one steady with a two-point alpha sweep and one unsteady
rotor whose row declares `ADVANCE_RATIO:sweep` and whose sweep resolved to a
SINGLE value.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# The workspace, in the shape of the one that ran.

_LOADS = """\




                              Aerodynamic loads


     Simulation file:                            c:/campaign/POINT.fsm
     Angle of attack (Deg)                       {alpha}
     Side-slip angle (Deg)                       .000
     Freestream velocity (m/s)                   {velocity}
     Requested solver iterations                 500
     Solver convergence limit                     1.000E-05
     Force solver to run all iterations           F
     Time increment (sec)                        1.000
     Solver model:                               Subsonic (Prandtl-Glauert)
     Solver mode:                                {mode}
     Reference velocity (m/s)                    {velocity}
     Reference length (m)                        2.526
     Reference area (m^2)                        50.000
     Altitude (ft)                               .000

     Wake refinement size (% average mesh size)  1000.000
     Reynolds Number                             11771675.
     Coordinate frame for analysis:              MRP
     Current solver iteration number:            198
     ------------------------------------------------------------------
     Surface, Cx, Cy, Cz, CL, CDi, CDo, CMx, CMy, CMz
     ------------------------------------------------------------------
     W,+0.0193288,+0.0000000,+0.1620516,+0.1631176,+0.0012085,+0.0124530,+0.0000000,-0.0077298,+0.0000000
     B,+0.0081038,+0.0000000,+0.0251063,+0.0251653,+0.0000333,+0.0071894,-0.0000000,-0.0892137,+0.0000000
     Total,+0.0274326,+0.0000000,+0.1871579,+0.1882829,+0.0012418,+0.0196424,-0.0000000,-0.0969435,+0.0000000
     ------------------------------------------------------------------
     Force Units: Coefficients
     Moment Units: Coefficients
     Software : Flightstream version 26.1, build #8112026
     Company  : Altair
     Date: 8/3/2026, Time: 2305 hours (local)
"""

_PLOTS = """\




                              Unsteady plots


     Simulation file:                            c:/campaign/POINT.fsm
     Angle of attack (Deg)                       .000
     Side-slip angle (Deg)                       .000
     Freestream velocity (m/s)                   49.036
     Requested solver iterations                 500
     Solver convergence limit                     1.000E-05
     Force solver to run all iterations           F
     Time increment (sec)                        .004
     Solver model:                               Subsonic (Prandtl-Glauert)
     Solver mode:                                Unsteady
     Reference velocity (m/s)                    49.036
     Reference length (m)                        2.526
     Reference area (m^2)                        50.000
     Altitude (ft)                               .000

     Wake refinement size (% average mesh size)  1000.000
     Reynolds Number                             4380000.
     Coordinate frame for analysis:              MRP
     Current solver iteration number:            2
----------------------------------------------------------------------
Time-step,CL_MRP_TOTAL,CDI_MRP_TOTAL,FX_MRP_TOTAL,CL_ROTOR_PUSHER,MACH1,VELOCITY1,STATIC_PRESSURE_RATIO1
----------------------------------------------------------------------
1.0000,.22538,.0000,1411.9,.11000,.20000,48.000,.99000,
2.0000,.22600,.0010,1412.0,.11100,.20100,48.100,.99100,
----------------------------------------------------------------------
     Force Units: Coefficients
     Moment Units: Coefficients
     Software : Flightstream version 26.1, build #8112026
     Company  : Altair
     Date: 8/3/2026, Time: 2305 hours (local)
"""

#: Where the run matrix of the fixture lives: three rows of the shape of
#: `pfs0160`'s own, a steady alpha sweep of two values, a rotor row that
#: DECLARES `ADVANCE_RATIO:sweep` and resolves to ONE value, and a third
#: with RUN 0 that never ran and carries a variable of its own. It is a
#: FILE and not a string in this module because a matrix line is 270
#: characters wide and the line limit is 100: wrapped into source it would
#: stop being a matrix.
FIXTURES = Path(__file__).parent / "fixtures"
_MATRIX = (FIXTURES / "superfile_matriz.fs").read_text(encoding="utf-8")

#: One rotor with a SPEED, so the file has an RPM to carry: the rotor block
#: `reduction_windows` writes for a row that names its rotors (FR-68).
_ROTOR_PLAN: dict[str, object] = {
    "time_iterations": 2,
    "steps_per_revolution": 2.0,
    "blades": 6,
    "rotors": {
        "PUSHER": {
            "blades": 6,
            "rpm": 2200.0,
            "steps_per_revolution": 2.0,
            "period_steps": 1,
        }
    },
}

#: A solver-flag snapshot, keyed by the solver command, as the run layer
#: records it: the FLAGS her sentence asks for, by their own names.
_SOLVER_SETUP: dict[str, object] = {
    "fs_version": "26.123",
    "flags": {
        "SET_SOLVER_CONVERGENCE_ITERATIONS": {
            "command": "SET_SOLVER_CONVERGENCE_ITERATIONS",
            "family": "advanced_settings",
            "provenance": "explicit",
            "value": 20,
            "emitted": True,
            "evidence": None,
        },
        "SOLVER_MINIMUM_CP": {
            "command": "SOLVER_MINIMUM_CP",
            "family": "advanced_settings",
            "provenance": "explicit",
            "value": -100.0,
            "emitted": True,
            "evidence": None,
        },
    },
}


def _loads(alpha: float, *, velocity: str = "68.058", mode: str = "Steady") -> str:
    return _LOADS.format(alpha=f"{alpha:.3f}", velocity=velocity, mode=mode)


def _workspace(tmp_path: Path):
    """A two-polar campaign of one matrix, recorded as a run leaves it."""
    from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.root / "matriz.fs").write_text(_MATRIX, encoding="utf-8")
    for pproc in ("p001", "p002"):
        (workspace.inputs_dir / "pproc" / f"{pproc}.toml").write_text(
            '[groups]\n"1" = ["W", "B"]\n"2" = ["W"]\n', encoding="utf-8"
        )

    steady = workspace.sim_dir("6001") / "outputs"
    steady.mkdir(parents=True)
    for tag, alpha in (("AL-020", -2.0), ("AL+000", 0.0)):
        (steady / f"POLAR-6001_M20{tag}BE+000.txt").write_text(_loads(alpha), encoding="utf-8")
        workspace.append_record(
            RunRecord(
                run_id=f"camp/sim_6001/{tag}",
                sim_id="6001",
                point={"alpha": alpha, "beta": 0.0},
                fs_version_requested="26.123",
                fs_build="8112026",
                velocity_requested_m_s=68.058,
                flight_condition={"MACH": 0.2, "REmi": 11.7716754},
                flight_condition_defaults={"TK": 288.15, "PPA": 101325.0},
                flight_condition_defaults_from="setup 's001' (inputs/setups/s001.toml)",
                matrix_stem="matriz",
                density_kg_m3=1.225,
                temperature_k=288.15,
                viscosity_pa_s=1.789e-05,
                density_source="solved-from-reynolds",
                reference_length_m=2.526,
                package_version="0.16.0.dev0",
                script_sha256="",
                raw_flag=False,
                status=RunStatus.CONVERGED,
                iterations=100,
                residual=9.18e-06,
                wall_time_s=12.17,
                outputs=[f"outputs/POLAR-6001_M20{tag}BE+000.txt"],
                pproc="p001",
                recipe="steady",
                description="CRUISE_wing_body_alpha_sweep",
                mach=0.2,
                reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0},
                solver_setup=_SOLVER_SETUP,
            )
        )

    unsteady = workspace.sim_dir("6002") / "outputs"
    unsteady.mkdir(parents=True)
    stem = "POLAR-6002_M14AL+000BE+000J+170"
    (unsteady / f"{stem}.txt").write_text(
        _loads(0.0, velocity="49.036", mode="Unsteady"), encoding="utf-8"
    )
    (unsteady / f"{stem}_plots.txt").write_text(_PLOTS, encoding="utf-8")
    workspace.append_record(
        RunRecord(
            run_id=f"camp/sim_6002/{stem}",
            sim_id="6002",
            point={"alpha": 0.0, "beta": 0.0, "advance_ratio": 1.7},
            fs_version_requested="26.123",
            fs_build="8112026",
            velocity_requested_m_s=49.036,
            flight_condition={"MACH": 0.1441, "REmi": 4.38},
            flight_condition_defaults={"TK": 288.15, "PPA": 101325.0},
            flight_condition_defaults_from="setup 's002' (inputs/setups/s002.toml)",
            matrix_stem="matriz",
            density_kg_m3=0.6326,
            temperature_k=288.15,
            viscosity_pa_s=1.789e-05,
            density_source="solved-from-reynolds",
            reference_length_m=2.526,
            package_version="0.16.0.dev0",
            script_sha256="",
            raw_flag=False,
            status=RunStatus.CONVERGED,
            iterations=81,
            residual=5.38e-06,
            wall_time_s=184.87,
            outputs=[f"outputs/{stem}.txt", f"outputs/{stem}_plots.txt"],
            pproc="p002",
            recipe="unsteady_rotor",
            description="ROTOR_sector_periodic_J_sweep",
            mach=0.1441,
            reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0},
            motions=[{"MOVING_BC_ALIAS": "PUSHER"}],
            reductions=_ROTOR_PLAN,
            solver_setup=_SOLVER_SETUP,
        )
    )
    return workspace


def _post(workspace):
    """Run the post stage over the matrix and leave the campaign sweep table beside it."""
    from pyflightstream.post.products import write_campaign_products
    from pyflightstream.results.tables import sweep_table, write_table

    written = write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)
    # What `run` leaves beside the products (FR-90), written here because the
    # superfile cites it as one of its sources and the union below READS it.
    write_table(
        sweep_table(workspace, require_loads=False, matrix_stem="matriz"),
        workspace.sweep_dir("matriz") / "campaign_sweep.csv",
    )
    return written


# ---------------------------------------------------------------------------
# The union, read off the workspace.


def _header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle))


def _matrix_names(path: Path, pols: set[str]) -> set[str]:
    """Every input of the matrix row: its columns, and the keys inside its cells.

    Parsed here with `str.split` and not with the package's own matrix
    reader, so this set is independent of the writer under test.

    ``pols`` is the set of simulations the manifest RECORDED. The matrix's
    own column names are a fact about the format and belong to every row;
    the keys inside a cell belong to the row that wrote them, and a row
    that never ran is a different simulation whose variables say nothing
    about this one.
    """
    if not path.is_file():
        # A workspace whose matrix is not in reach knows no matrix cell, and
        # the file may then carry none: the two sides stay in step.
        return set()
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and set(line.strip()) != {"-"}
    ]
    header = [cell.strip() for cell in lines[0].split("|")]
    names = set(header)
    for line in lines[1:]:
        cells = dict(zip(header, [cell.strip() for cell in line.split("|")], strict=True))
        if cells.get("POL", "") not in pols:
            continue
        for pair in cells.get("FLIGHT_CONDITION", "").split(","):
            if ":" in pair:
                names.add(pair.split(":", 1)[0].strip())
        for pair in cells.get("VAR_NAMES_VALUES", "").split("/"):
            if ":" in pair:
                names.add(pair.split(":", 1)[0].strip())
    return names


def _the_union_the_workspace_knows(workspace) -> set[str]:
    """Everything the workspace knows about a simulation, gathered from the workspace."""
    out = workspace.products_dir("matriz")
    known: set[str] = set()
    for table in sorted((out / "polars").glob("POLAR-*.csv")):
        known |= set(_header(table))
    known |= set(_header(out / "campaign_sweep.csv"))
    for table in sorted((out / "probes").glob("*_plots.csv")):
        known |= set(_header(table))
    # RPM and the advance ratio are named by the requirement itself, which is
    # why they are the only two words written here rather than read.
    known |= {"RPM", "J"}
    pols: set[str] = set()
    for record in json.loads((workspace.root / "runs.json").read_text(encoding="utf-8")):
        pols.add(str(record.get("sim_id")))
        known |= set(record.get("flight_condition") or {})
        known |= set(record.get("flight_condition_defaults") or {})
        known |= set(((record.get("solver_setup") or {}).get("flags")) or {})
        rotors = ((record.get("reductions") or {}).get("rotors")) or {}
        known |= {f"RPM_{alias}" for alias in rotors}
    known |= _matrix_names(workspace.root / "matriz.fs", pols)
    return known


def _superfiles(workspace) -> dict[str, tuple[list[str], list[dict[str, str]]]]:
    from pyflightstream.post.products import read_csv_table

    found = {}
    for path in sorted((workspace.products_dir("matriz") / "polars").glob("SUPER-*.csv")):
        columns, rows = read_csv_table(path)
        found[path.name] = (list(columns), rows)
    return found


# ---------------------------------------------------------------------------
# The requirement.


def test_one_superfile_per_polar_and_group_named_with_sweep_and_the_group(tmp_path):
    """FR-89's name: SUPER- instead of POLAR-, the swept variable as `sweep`, `_g<NN>`."""
    workspace = _workspace(tmp_path)
    _post(workspace)
    names = sorted(_superfiles(workspace))
    assert names == [
        "SUPER-6001_M20AL+sweepBE+000_g01.csv",
        "SUPER-6001_M20AL+sweepBE+000_g02.csv",
        "SUPER-6002_M14AL+000BE+000J+sweep_g01.csv",
        "SUPER-6002_M14AL+000BE+000J+sweep_g02.csv",
    ], "one file per polar and per group, the swept variable written literally as sweep"


def test_a_point_whose_record_is_missing_borrows_no_other_points_values(tmp_path):
    """A row states what is known about ITS point, and is EMPTY about the rest.

    The campaign writer resolved a point's manifest record as
    `by_run.get(run_id, records[0])`, so a run id that did not resolve would
    silently take an ARBITRARY other point of the same simulation, and
    blocks 3 and 4 would write that record's flight condition, velocity,
    density and rotor speeds into this point's row.

    THIS CASE DOES NOT GUARD THAT PATH AND DOES NOT CLAIM TO. It pins the
    contract the removal relies on: handed no record, this function borrows
    nothing. A case that drove the campaign writer was written and then
    DELETED, because restoring the fallback left it green: `sources` and
    `by_run` are built from the same records in the same loop, so a run id
    the first names is one the second holds, and the fallback is not
    reachable today. It was removed anyway, as a branch that would do the
    wrong thing silently if it ever became reachable, and this case is what
    says what the right thing is.

    That is the worst failure this file can have and the one its own
    acceptance forbids: not a missing cell, which a reader sees, but a cell
    that is WRONG and indistinguishable from a right one, in the file whose
    whole claim is that it says everything about THAT simulation.

    Empty and not absent, which is what `_rotor_speeds` already chooses for
    a row that turns none or several.
    """
    from pyflightstream.post.superfile import superfile_row

    class _Record:
        flight_condition = {"MACH": "0.15", "REmi": "5.0"}
        flight_condition_defaults = {"ALTITUDE": "0"}
        flight_condition_defaults_from = "the setup"
        velocity_requested_m_s = 51.0
        density_kg_m3 = 1.225
        temperature_k = 288.15
        viscosity_pa_s = 1.81e-5
        density_source = "the resolver"
        reference_length_m = 1.322
        reductions = {"rpm": -837.3278}

    theirs = superfile_row(
        polar_columns=("POLAR",),
        polar_values=("0001",),
        matrix_row=None,
        record=_Record(),
        sweep_row=None,
        plots_row=None,
    )
    mine = superfile_row(
        polar_columns=("POLAR",),
        polar_values=("0001",),
        matrix_row=None,
        record=None,
        sweep_row=None,
        plots_row=None,
    )
    # NOT ONE VALUE THE RECORD WOULD HAVE SUPPLIED APPEARS IN THE ROW THAT
    # HAS NO RECORD. Asserted over the keys the OTHER row gained rather than
    # over a list typed here, so a field added to block 3 is covered the day
    # it lands and nothing is left out by judgement.
    from_record = set(theirs) - set(mine)
    assert from_record, "the fixture record supplied nothing, so this proves nothing"
    borrowed = {
        k: mine[k]
        for k in set(mine) & set(theirs)
        if k != "POLAR" and mine[k] and mine[k] == theirs[k]
    }
    assert not borrowed, f"a point with no record carried {borrowed}"
    # AND THE FILE'S HEADER IS STILL WHOLE, because `write_superfiles` unions
    # the keys of every row and writes an empty cell for a row that lacks
    # one. That is where the column set is decided, not here.
    from pyflightstream.post.superfile import SuperfileDraft, write_superfiles

    _files, _entries, columns = write_superfiles(
        [SuperfileDraft(path=tmp_path / "SUPER-x_sweep_g01.csv", rows=[theirs, mine], entry={})],
        target=lambda p: p,
    )
    assert from_record <= set(columns)


def test_every_record_scalar_is_carried_or_excluded_on_purpose(tmp_path):
    """A field added to a manifest record forces a decision rather than slipping past.

    The union could not see a single one of the record's own scalars until
    2026-09-11, so dropping one from the file passed the completeness check.
    They now live in ONE tuple the writer loops and the union requires.

    THIS CASE IS THE OTHER HALF: it takes a real record's top-level keys and
    demands each one be either CARRIED or EXCLUDED BY NAME below. A field
    added to `RunRecord` lands in neither and fails here, which is the
    decision the completeness claim needs someone to make, rather than a
    silent absence.
    """
    from pyflightstream.post.superfile import RECORD_SCALARS

    #: Read as: these are NOT in the superfile, and here is why. Grouped, and
    #: every group is a reason rather than a list.
    carried_by_their_contents = {
        # containers whose KEYS become columns of their own
        "flight_condition",
        "flight_condition_defaults",
        "reductions",
        "solver_setup",
        "point",
    }
    carried_under_the_matrix_or_polar_name = {
        "description",
        "mach",
        "pproc",
        "recipe",
        "reference",
        "aliases",
        "motions",
        "conditions",
        "raw_commands",
        "raw_flag",
        "matrix_stem",
    }
    about_the_INVOCATION_and_not_the_simulation = {
        "argv",
        "cwd",
        "executor",
        "fs_exe",
        "fs_exe_sha256",
        "script_path",
        "script_sha256",
        "recipe_sha256",
        "inputs_sha256",
        "outputs_sha256",
        "staged_as",
        "staged_as_reason",
        "log_file_used",
        "manifest_schema",
        "package_commit",
        "package_dirty",
        "timeout_s",
        "started_at",
        "finished_at",
        "error",
        "outputs",
        "action_count",
        "action_program",
        "action_script",
        "campaign_name_from",
        "point_name_template",
        "inventory_source",
        "fs_version_source",
        "export_window",
        "waived_commands",
        # FR-91. The path of the file this run's probe positions were
        # written to. It is an INDEX into another file and not a fact about
        # the simulation, and the positions themselves reach a reader
        # through `probes/<point>_probes.csv`, where they sit beside the
        # sample they place. A column holding a path would tell a reader to
        # go and open something, which is the one thing the superfile
        # exists so that they never have to do.
        "probe_points_file",
    }
    carried_by_the_campaign_sweep_table = {
        "run_id",
        "sim_id",
        "status",
        "iterations",
        "residual",
        "wall_time_s",
        "fs_build",
        "fs_version_reported",
        "fs_version_requested",
        "package_version",
    }
    excluded = (
        carried_by_their_contents
        | carried_under_the_matrix_or_polar_name
        | about_the_INVOCATION_and_not_the_simulation
        | carried_by_the_campaign_sweep_table
    )

    workspace = _workspace(tmp_path)
    payload = json.loads((workspace.root / "runs.json").read_text(encoding="utf-8"))
    runs = payload["runs"] if isinstance(payload, dict) else payload
    keys = {key for record in runs for key in record}
    assert keys, "the fixture wrote no record, so this proves nothing"

    undecided = sorted(keys - set(RECORD_SCALARS) - excluded)
    assert not undecided, (
        f"the manifest record carries {undecided}, which the superfile neither "
        "carries nor excludes by name. Add each to RECORD_SCALARS if the "
        "superfile should state it, or to one of the groups above with the "
        "reason it should not."
    )
    # AND THE TUPLE IS NOT A DEAD LETTER: every name in it is a field the
    # record actually has, so a typo there cannot sit unnoticed.
    typos = sorted(set(RECORD_SCALARS) - keys)
    assert not typos, f"RECORD_SCALARS names {typos}, which no record carries"


def test_the_column_set_is_a_superset_of_what_the_workspace_knows(tmp_path):
    """The acceptance: no field is left out, and the union is BUILT rather than listed."""
    workspace = _workspace(tmp_path)
    _post(workspace)
    known = _the_union_the_workspace_knows(workspace)
    assert known, "a superset test over an empty union passes on any file at all"
    assert "digits" not in known, (
        "row 6003 has RUN 0 and never ran, so its own variable is a fact about a "
        "simulation this campaign does not have"
    )
    found = _superfiles(workspace)
    assert found, "no superfile was written"
    for name, (columns, _rows) in found.items():
        missing = sorted(known - set(columns))
        assert not missing, (
            f"{name} leaves out {len(missing)} field(s) the workspace knows: {missing}"
        )


def test_one_row_per_converged_point_and_no_time_series(tmp_path):
    """It is written AFTER the unsteady post-process, so nothing is repeated down the file."""
    workspace = _workspace(tmp_path)
    _post(workspace)
    found = _superfiles(workspace)
    rows_by_polar = {name: len(rows) for name, (_columns, rows) in found.items()}
    assert rows_by_polar == {
        "SUPER-6001_M20AL+sweepBE+000_g01.csv": 2,
        "SUPER-6001_M20AL+sweepBE+000_g02.csv": 2,
        "SUPER-6002_M14AL+000BE+000J+sweep_g01.csv": 1,
        "SUPER-6002_M14AL+000BE+000J+sweep_g02.csv": 1,
    }, "one row per converged point, and the unsteady point's two time steps are not two rows"
    for name, (_columns, rows) in found.items():
        points = {(row["ALPHA"], row["BETA"], row["J"]) for row in rows}
        assert len(points) == len(rows), f"{name} repeats a point down the file"


def test_a_reader_cannot_tell_a_steady_polar_from_an_unsteady_one(tmp_path):
    """The steady file and the unsteady one carry the SAME columns, which is the transparency."""
    workspace = _workspace(tmp_path)
    _post(workspace)
    found = _superfiles(workspace)
    steady = found["SUPER-6001_M20AL+sweepBE+000_g01.csv"][0]
    unsteady = found["SUPER-6002_M14AL+000BE+000J+sweep_g01.csv"][0]
    assert steady == unsteady, (
        "the column set is the campaign's, so a reader cannot tell from the file "
        "whether the run behind a row was steady or unsteady"
    )
    assert "CL_MRP_TOTAL" in steady, "the unsteady plots' parameters reach the steady file too"


def test_the_flight_condition_variables_are_all_there(tmp_path):
    """Her second instruction of the same evening: every variable that defines the condition."""
    workspace = _workspace(tmp_path)
    _post(workspace)
    columns = set(_superfiles(workspace)["SUPER-6002_M14AL+000BE+000J+sweep_g01.csv"][0])
    stated = {"MACH", "REmi", "ALPHA", "BETA", "ADVANCE_RATIO"}
    # DERIVED, not a second literal: four of the seven names were written
    # out here, which is a partial snapshot of a tuple that can grow.
    # Round two, finding 3.
    from pyflightstream.post.superfile import RECORD_SCALARS

    assert stated <= columns and set(RECORD_SCALARS) <= columns


def test_the_post_stage_writes_its_own_measurement(tmp_path):
    """The report the goal's superfile arm reads: the files written and the union."""
    import pyflightstream

    workspace = _workspace(tmp_path)
    _post(workspace)
    major, minor, patch = pyflightstream.__version__.split(".")[:3]
    report = workspace.root / "reports" / f"superfile-{major}{minor}{patch}.json"
    assert report.is_file(), f"no superfile measurement at {report}"
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["known"], "the arm refuses an empty union, and so does this"
    assert len(payload["files"]) == 4
    for entry in payload["files"]:
        assert entry["rows"] >= 1
        assert set(payload["known"]) <= set(entry["columns"])


def test_a_workspace_without_its_matrix_still_gets_a_superfile(tmp_path):
    """The matrix cells are absent from the file AND from the union, never silently dropped.

    And the union still holds: the manifest is the OTHER source of the flight
    condition, and with no matrix row in front of it, it is the only one.
    """
    workspace = _workspace(tmp_path)
    (workspace.root / "matriz.fs").unlink()
    _post(workspace)
    found = _superfiles(workspace)
    assert found, "no superfile was written"
    known = _the_union_the_workspace_knows(workspace)
    for name, (columns, _rows) in found.items():
        missing = sorted(known - set(columns))
        assert not missing, f"{name} leaves out {missing}"
    columns = set(next(iter(found.values()))[0])
    assert {"ALPHA", "MACH", "REmi"} <= columns and "AIRCRAFT" not in columns


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))


def test_every_record_scalar_reaches_the_file_with_its_value(tmp_path):
    """Round two, finding 1: the completeness claim was about column NAMES only.

    Measured by mutation in an isolated tree at 67f7a8b: replacing the writer's
    `_take(row, field, getattr(record, field, None))` with `_take(row, field,
    "")` left every superfile in every test with an empty cell under all seven
    record scalars, and the suite reported 104 passed, exit 0. The column
    survives, so the superset check, the union, the report arm and the
    flight-condition case were all satisfied by a file whose values were gone.

    So this reads the VALUES back. It is not one asserted cell: every scalar
    the record actually carries must appear under its own name in the row for
    that point, which is the claim her acceptance sentence makes and the one no
    case was making.
    """
    from pyflightstream.post.superfile import RECORD_SCALARS

    workspace = _workspace(tmp_path)
    _post(workspace)

    records = {
        str(record.get("run_id")): record
        for record in json.loads((workspace.root / "runs.json").read_text(encoding="utf-8"))
    }
    assert records, "the fixture recorded nothing, so this proves nothing"

    checked = 0
    for name, (_columns, rows) in _superfiles(workspace).items():
        for row in rows:
            record = records.get(str(row.get("run_id", "")))
            if record is None:
                continue
            for field in RECORD_SCALARS:
                want = record.get(field)
                if want is None:
                    continue
                got = str(row.get(field, "")).strip()
                assert got, (
                    f"{name}: the row for {record['run_id']} carries a {field} column "
                    f"and nothing under it; the record says {want!r}"
                )
                if isinstance(want, float):
                    assert float(got) == want, (
                        f"{name}: {field} reads {got!r}, the record says {want!r}"
                    )
                else:
                    assert got == str(want), (
                        f"{name}: {field} reads {got!r}, the record says {want!r}"
                    )
                checked += 1
    assert checked >= len(RECORD_SCALARS), (
        f"only {checked} scalar cell(s) were compared against a record; a case that "
        "matches no row asserts nothing"
    )


def test_the_union_sees_every_record_scalar(tmp_path):
    """Round two, finding 2: the UNION half was undefended per field.

    The mirror of the defect round one fixed. Narrowing the package's union
    comprehension to `RECORD_SCALARS[:-1]` re-blinded the superset check to
    `reference_length_m` and left the suite green, because the superset check
    reads that union: a name the union cannot see is a name no file is required
    to carry.

    Asserted against the PACKAGE's union and not against the test module's own,
    because it is the package's that the report arm and the superset check
    consume. It cannot be written as a superset over the superfile's own
    columns, which would be the check-that-accepts-everything this module's
    docstring already rules out.
    """
    from pyflightstream.post.products import POLARS_DIR, PROBES_DIR
    from pyflightstream.post.superfile import RECORD_SCALARS, union_the_workspace_knows

    workspace = _workspace(tmp_path)
    _post(workspace)
    known = union_the_workspace_knows(
        workspace.root,
        workspace.products_dir("matriz"),
        "matriz",
        polars_dir=POLARS_DIR,
        probes_dir=PROBES_DIR,
    )
    assert known, "an empty union proves nothing"
    missing = sorted(set(RECORD_SCALARS) - known)
    assert not missing, (
        f"the union cannot see {missing}, so nothing requires a superfile to carry them"
    )
