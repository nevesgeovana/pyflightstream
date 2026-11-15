"""FR-89: the polar of a point carries everything the workspace knows of its condition.

Until 0.57.0 one derived super file per polar and group carried it. The super file is retired
(design-post-outputs 2.2): the FAM and group files of ``polars/`` open with the run block, the
setup codes are in ``settings/`` and the matrix row's description is in ``products.json``. The
cases that remain on the library functions (`matrix_rows`,
`measure_sections`, `release_tag`) pin helpers the post still calls; the cases that drove the
post now read the files that replace the super file, and compare their cells with the run
records, which this module reads with the standard library rather than through the package's
own readers: a gatherer shared with the writer would agree with the writer by construction.

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

from pyflightstream.workspace.record_document import read_rows as _read_record_rows


def test_p0440_a_matrix_of_two_homes_that_differ_reads_as_no_rows(tmp_path):
    from pyflightstream.post.superfile import matrix_rows

    folder = tmp_path / "inputs" / "matrices"
    folder.mkdir(parents=True)
    (tmp_path / "study.fs").write_text("POL|FIRST\n1|x\n", encoding="utf-8")
    (folder / "study.fs").write_text("POL|SECOND\n1|y\n", encoding="utf-8")
    assert matrix_rows(tmp_path, "study") == {}


def test_p0430_w012_release_tags_are_unambiguous_and_keep_existing_names():
    from pyflightstream.post.superfile import release_tag

    versions = ["0.1.10", "0.11.0", "1.1.10", "1.11.0", "11.1.0", "1.11.0rc1"]
    assert len({release_tag(version) for version in versions}) == len(versions)
    assert release_tag("0.11.0") == "0110"
    assert release_tag("0.40.0rc1") == "0400rc1"


def test_p0430_w012_missing_recorded_section_count_has_context(tmp_path):
    from pyflightstream._errors import ProductError
    from pyflightstream.post.superfile import measure_sections

    with pytest.raises((ValueError, KeyError)) as caught:
        measure_sections(tmp_path, [dict(sim_id="1", run_id="run/point", sections_layout=[{}])])
    assert isinstance(caught.value, ProductError)
    assert "run/point" in str(caught.value) and "count" in str(caught.value)


def test_p0430_the_matrix_is_read_from_its_inputs_home(tmp_path):
    from pyflightstream.post.superfile import matrix_rows

    folder = tmp_path / "inputs" / "matrices"
    folder.mkdir(parents=True)
    (folder / "study.fs").write_text(_MATRIX, encoding="utf-8")
    (tmp_path / "root").mkdir()
    (tmp_path / "root" / "study.fs").write_text(_MATRIX, encoding="utf-8")
    at_inputs = matrix_rows(tmp_path, "study")
    assert at_inputs, "a matrix of the inputs home reads as its rows"
    assert list(at_inputs) == list(matrix_rows(tmp_path / "root", "study"))


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
            '[groups]\n"1" = "all"\n"2" = "W"\n', encoding="utf-8"
        )

    steady = workspace.sim_dir("6001") / "outputs"
    steady.mkdir(parents=True)
    for tag, alpha in (("AL-020", -2.0), ("AL+000", 0.0)):
        (steady / f"POLAR-6001_M20{tag}BE+000.txt").write_text(_loads(alpha), encoding="utf-8")
        workspace.append_record(
            RunRecord(
                run_id=f"camp/sim_6001/M200RE1177{tag}BE+000",
                # 0.21.0: the names the run records, in the row's declared order.
                point_name=f"M200RE1177{tag}BE+000",
                sweep_name="M200RE1177AL+sweepBE+000",
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
            run_id="camp/sim_6002/M144RE438AL+000BE+000J+170",
            point_name="M144RE438AL+000BE+000J+170",
            sweep_name="M144RE438AL+000BE+000J+sweep",
            sim_id="6002",
            point={"alpha": 0.0, "beta": 0.0, "advance_ratio": 1.7},
            fs_version_requested="26.123",
            fs_build="8112026",
            velocity_requested_m_s=49.036,
            flight_condition={"MACH": 0.1441, "REmi": 4.38},
            flight_condition_defaults={"TK": 288.15, "PPA": 101325.0},
            flight_condition_defaults_from="setup 's002' (inputs/setups/s002.toml)",
            matrix_stem="matriz",
            # Explicit source units make this recorded scalar visible to the
            # union guard, just like the nonempty clock/operator fields below.
            freestream_units="SI",
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
            # FR-98, 0.17.0: the rotor row is the one that states a wall
            # clock, as the row of pfs0170 it is modelled on does. Without
            # it the record's two clock fields are None and the union
            # cannot see them, so nothing would require the superfile to
            # carry a number it is supposed to carry.
            walltime_s=3600.0,
            walltime_margin_s=1200.0,
            march_strategy="actions",
            # GOAL-026 item 12: the fixture NAMES its operator for the same
            # reason it names its clock above. With None here the union
            # cannot see the field, and nothing would require a superfile to
            # carry a value it is supposed to carry.
            submitted_by="an.operator",
            # GOAL-024: a verdict read past an overflowed residual field says so.
            residual_note="the pressure residual of iteration 1535 did not fit its printed field",
            solver_run_time_s=333.6,
            solver_initialization_s=1.7,
            time_steps=54,
            reductions=_ROTOR_PLAN,
            solver_setup=_SOLVER_SETUP,
        )
    )
    return workspace


def _post(workspace):
    """Run the post stage over the matrix; no campaign sweep table is written (FR-3777)."""
    from pyflightstream.post.products import write_campaign_products

    return write_campaign_products(workspace, matrix_stem="matriz", overwrite=True)


# ---------------------------------------------------------------------------
# The files the post writes in place of the retired super file.


def _header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle))


def _polar_files(workspace) -> dict[str, tuple[list[str], list[dict[str, str]]]]:
    """Every table of ``polars/``: the FAM files and the group files, by name."""
    from pyflightstream.post.products import read_csv_table

    found = {}
    for path in sorted((workspace.products_dir("matriz") / "polars").glob("*.csv")):
        columns, rows = read_csv_table(path)
        found[path.name] = (list(columns), rows)
    return found


def _records_by_run(workspace) -> dict[str, dict]:
    return {
        str(record.get("run_id")): record
        for record in _read_record_rows(workspace.root / "runs.json")
    }


# ---------------------------------------------------------------------------
# The requirement.


def test_one_file_set_per_polar_named_with_its_pol_and_its_groups(tmp_path):
    """FR-89's successor: polars/ holds the FAM files and the group files of each POL.

    The super file is retired (design-post-outputs 2.2): its name, with the sweep
    and the group number, gives way to ``FAM-<KIND>-P<POL>.csv`` and
    ``P<POL>-<GROUP>-<KIND>.csv``; the numbered groups of the pproc are ``g01``
    and ``g02``, AIRFRAME and TOTAL are the reserved ones.
    """
    workspace = _workspace(tmp_path)
    _post(workspace)
    names = set(_polar_files(workspace))
    expected = set()
    for pol in ("6001", "6002"):
        expected |= {f"FAM-{kind}-P{pol}.csv" for kind in ("DIM", "ACOEF")}
        expected |= {
            f"P{pol}-{group}-{kind}.csv"
            for group in ("TOTAL", "AIRFRAME", "g01", "g02")
            for kind in ("DIM", "ACOEF")
        }
    assert names == expected, "one file set per polar and per group, no RCOEF without a rotor"
    assert not [name for name in names if name.startswith("SUPER-")]


def test_p0430_an_unemitted_documented_default_is_written_as_a_default(tmp_path, monkeypatch):
    """NL-RECS-2: a flag the script never set is the solver's default, not a measured value.

    The setup codes left the polar rows for ``settings/`` (design-post-outputs
    2.2, "setup codes in settings/"), so the class of each flag is read from the
    settings table through its codebook: provenance 1 is explicit, 2 a
    documented default, 3 unknown; a documented default keeps its value, an
    unknown flag has none (NA).
    """
    flags = _SOLVER_SETUP["flags"]
    assert isinstance(flags, dict)
    monkeypatch.setitem(
        flags,
        "SET_WAKE_ON_WAKE_INDUCTION",
        {
            "command": "SET_WAKE_ON_WAKE_INDUCTION",
            "family": "advanced_settings",
            "provenance": "default",
            "value": True,
            "emitted": False,
            "evidence": "FSM-26.123 p.1 (synthetic citation)",
        },
    )
    monkeypatch.setitem(
        flags,
        "SET_WAKE_TERMINATION_TIME_STEPS",
        {
            "command": "SET_WAKE_TERMINATION_TIME_STEPS",
            "family": "advanced_settings",
            "provenance": "unknown",
            "value": None,
            "emitted": False,
            "evidence": None,
        },
    )
    workspace = _workspace(tmp_path)
    _post(workspace)
    from pyflightstream.post.products import read_csv_table

    out = workspace.products_dir("matriz") / "settings"
    codebook = json.loads((out / "matriz_settings.codebook.json").read_text(encoding="utf-8"))
    ids = codebook["flag_ids"]
    codes = codebook["provenance_codes"]
    _, rows = read_csv_table(out / "matriz_settings.csv")
    rows = [row for row in rows if row["POL"] == "6001"]
    assert rows, "no settings row of simulation 6001"
    default_id = ids["SET_WAKE_ON_WAKE_INDUCTION"]
    unknown_id = ids["SET_WAKE_TERMINATION_TIME_STEPS"]
    explicit_id = ids["SET_SOLVER_CONVERGENCE_ITERATIONS"]
    assert {row[f"f{default_id}_prov"] for row in rows} == {str(codes["default"])}
    assert {row[f"f{default_id}_value"] for row in rows} == {"1.0"}
    assert {row[f"f{unknown_id}_prov"] for row in rows} == {str(codes["unknown"])}
    assert {row[f"f{unknown_id}_value"] for row in rows} == {"NA"}
    assert {row[f"f{explicit_id}_prov"] for row in rows} == {str(codes["explicit"])}
    assert {row[f"f{explicit_id}_value"] for row in rows} == {"20"}


def test_every_polar_file_carries_the_whole_run_block_and_no_variable_of_a_run_that_never_ran(
    tmp_path,
):
    """The acceptance of FR-89 in its new form: the condition is in the file, not in a second one.

    Every table of ``polars/`` opens with the run block (design-post-outputs 3), so
    a reader never opens another file to know the condition of a point. Row 6003 has
    RUN 0 and never ran, so its own variable is a fact about a simulation this
    campaign does not have.
    """
    from pyflightstream.post._run_block import run_block_columns

    workspace = _workspace(tmp_path)
    _post(workspace)
    block = run_block_columns((), ())
    found = _polar_files(workspace)
    assert found, "no polar file was written"
    for name, (columns, _rows) in found.items():
        assert columns[: len(block)] == list(block), f"{name} does not open with the run block"
        assert "digits" not in columns, f"{name} carries the variable of a run that never ran"


def test_one_row_per_converged_point_and_no_time_series(tmp_path):
    """A group file is written AFTER the unsteady post-process, so nothing repeats down the file."""
    workspace = _workspace(tmp_path)
    _post(workspace)
    found = _polar_files(workspace)
    groups = {name: v for name, v in found.items() if not name.startswith("FAM-")}
    rows_by_polar = {name: len(rows) for name, (_columns, rows) in groups.items()}
    assert rows_by_polar == {
        f"P{pol}-{group}-{kind}.csv": count
        for pol, count in (("6001", 2), ("6002", 1))
        for group in ("TOTAL", "AIRFRAME", "g01", "g02")
        for kind in ("DIM", "ACOEF")
    }, "one row per converged point, and the unsteady point's two time steps are not two rows"
    for name, (_columns, rows) in groups.items():
        points = {(row["ALPHA"], row["BETA"], row["J"]) for row in rows}
        assert len(points) == len(rows), f"{name} repeats a point down the file"
        assert len({row["POINT_ID"] for row in rows}) == len(rows)


@pytest.mark.requirement("FR-68")
def test_a_reader_cannot_tell_a_steady_polar_from_an_unsteady_one(tmp_path):
    """The steady file and the unsteady one carry the SAME columns, which is the transparency."""
    workspace = _workspace(tmp_path)
    _post(workspace)
    found = _polar_files(workspace)
    for kind in ("DIM", "ACOEF"):
        steady = found[f"P6001-TOTAL-{kind}.csv"]
        unsteady = found[f"P6002-TOTAL-{kind}.csv"]
        assert steady[0] == unsteady[0], (
            "the column set is the campaign's, so a reader cannot tell from the header "
            "whether the run behind a row was steady or unsteady"
        )
        assert {row["RUN_TYPE"] for row in steady[1]} == {"steady"}
        assert {row["RUN_TYPE"] for row in unsteady[1]} == {"unsteady_rotor"}


def test_the_flight_condition_variables_are_all_there(tmp_path):
    """Her second instruction of the same evening: every variable that defines the condition."""
    workspace = _workspace(tmp_path)
    _post(workspace)
    found = _polar_files(workspace)
    columns = set(found["P6002-TOTAL-ACOEF.csv"][0])
    stated = {"MACH", "RE", "ALPHA", "BETA", "J", "VINF", "RHO", "TEMP", "MU"}
    assert stated <= columns
    (row,) = found["P6002-TOTAL-ACOEF.csv"][1]
    assert float(row["MACH"]) == pytest.approx(0.1441)
    assert float(row["J"]) == pytest.approx(1.7)


def test_the_post_stage_writes_its_own_measurement(tmp_path):
    """The report the goal's arm reads: products.json lists every polar file written."""
    workspace = _workspace(tmp_path)
    _post(workspace)
    assert not (workspace.root / "reports").exists(), "the workspace root holds no reports"
    document = json.loads(
        (workspace.products_dir("matriz") / "products.json").read_text(encoding="utf-8")
    )
    listed = {key for key in document["products"] if key.startswith("polars/")}
    on_disk = {f"polars/{name}" for name in _polar_files(workspace)}
    assert listed == on_disk
    assert len(listed) == 20
    for key in listed:
        assert document["products"][key]["sim_id"] in {"6001", "6002"}


def test_the_sections_measurement_lands_beside_the_matrix_products(tmp_path):
    """FR-3292: the sections report is written in post/<matrix>/reports/, none at the root."""
    import hashlib

    import pyflightstream
    from pyflightstream.post.superfile import release_tag

    workspace = _workspace(tmp_path)
    first = workspace.read_manifest()[0]
    script = workspace.sim_dir("6001") / "P1.txt"
    script.write_text(
        "NEW_SURFACE_SECTION_DISTRIBUTION\nFRAME 1\nNUM_SECTIONS 10\n", encoding="utf-8"
    )
    workspace.supersede_records([first.run_id])
    workspace.append_record(
        first.model_copy(
            update={
                "script_path": "P1.txt",
                "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                "sections_layout": [{"families": ["W"], "planes": ["XZ"], "count": 10}],
            }
        )
    )
    _post(workspace)
    tag = release_tag(pyflightstream.__version__)
    report = workspace.root / "post" / "matriz" / "reports" / f"sections-{tag}.json"
    assert report.is_file(), f"no sections measurement at {report}"
    assert not (workspace.root / "reports").exists(), "the workspace root holds no reports"
    manifest = json.loads(
        (workspace.root / "post" / "matriz" / "products.json").read_text(encoding="utf-8")
    )
    assert manifest["sections_report"] == f"post/matriz/reports/sections-{tag}.json"


def test_p0400_the_release_tag_is_the_three_numbers_of_a_release_dev_or_local_version():
    """The tag the measurement's name carries, pinned for the forms a build can have."""
    from pyflightstream.post.superfile import release_tag

    assert release_tag("0.39.0") == "0390"
    assert release_tag("0.40.0.dev0") == "0400"
    assert release_tag("0.10.1") == "0101"
    # The fallback version of an uninstalled tree: three numbers, the local part dropped.
    assert release_tag("0.0.0+uninstalled") == "000"


def test_a_workspace_without_its_matrix_still_gets_its_polar_files(tmp_path):
    """The matrix cells are absent from the files, never silently dropped.

    The manifest is the OTHER source of the flight condition, and with no matrix
    row in front of it, it is the only one.
    """
    workspace = _workspace(tmp_path)
    (workspace.root / "matriz.fs").unlink()
    _post(workspace)
    found = _polar_files(workspace)
    assert found, "no polar file was written"
    for name, (columns, rows) in found.items():
        assert {"ALPHA", "MACH", "RE"} <= set(columns), name
        assert "AIRCRAFT" not in columns
        assert rows, f"{name} has no row"
    (row,) = found["P6002-TOTAL-ACOEF.csv"][1]
    assert float(row["MACH"]) == pytest.approx(0.1441)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))


def test_every_record_scalar_reaches_the_file_with_its_value(tmp_path):
    """Round two, finding 1: the completeness claim was about column NAMES only.

    Measured by mutation at 67f7a8b: a writer that put an empty cell under every
    record scalar left the suite green because the column survived. So this reads
    the VALUES back. The record's condition now reaches the run block of every
    point row (design-post-outputs 3); each is compared with the record's own
    number, point by point.
    """
    workspace = _workspace(tmp_path)
    _post(workspace)

    records = list(_records_by_run(workspace).values())
    assert records, "the fixture recorded nothing, so this proves nothing"
    by_point = {(str(r["sim_id"]), float(r["point"]["alpha"])): r for r in records}
    from_record = {
        "RHO": "density_kg_m3",
        "TEMP": "temperature_k",
        "MU": "viscosity_pa_s",
        "MACH": "mach",
        "VINF": "velocity_requested_m_s",
    }
    found = _polar_files(workspace)
    checked = 0
    for name in ("P6001-TOTAL-ACOEF.csv", "P6002-TOTAL-ACOEF.csv"):
        for row in found[name][1]:
            record = by_point[(row["POL"], float(row["ALPHA"]))]
            for column, field in from_record.items():
                want = record[field]
                got = row[column].strip()
                assert got and got != "NA", f"{name}: {column} is empty, the record says {want!r}"
                assert float(got) == pytest.approx(want, rel=1e-4), (
                    f"{name}: {column} reads {got!r}, the record says {want!r}"
                )
                checked += 1
    assert checked >= 3 * len(from_record), (
        f"only {checked} cell(s) were compared against a record; a case that "
        "matches no row asserts nothing"
    )


# --- PFS-2038.02, GEO-039-F02: a recorded point's conditions are its own ------


def test_goal019_bandd_editing_the_matrix_does_not_relabel_a_recorded_point(tmp_path):
    """The worst of the eight, because it rewrites history with UNCHANGED data.

    The row took matrix values before recorded conditions, and the matrix is read
    from the CURRENT workspace rather than from anything bound to the run. The
    reviewer moved a recorded REmi of 11.7716754 to 99.0 in a regenerated
    historical row while the run record still said 11.7716754. The Reynolds
    number is column RE of the run block now.

    Taken WHOLE. This adds no gate: it removes a wrong number.
    """
    workspace = _workspace(tmp_path)
    _post(workspace)
    files = _polar_files(workspace)
    before = {
        name: [row["RE"] for row in rows]
        for name, (_columns, rows) in files.items()
        if "6001" in name
    }
    assert before, f"no polar file of simulation 6001 among {sorted(files)}"
    assert all(
        float(value) == pytest.approx(11.7716754, abs=1e-4)
        for values in before.values()
        for value in values
    ), before

    # ONLY THE MATRIX CHANGES. Nothing else in the workspace is touched:
    # the manifest, the outputs and their bytes are exactly as the run
    # left them.
    matrix = workspace.root / "matriz.fs"
    text = matrix.read_text(encoding="utf-8")
    assert "11.7716754" in text, "the fixture's matrix does not state the value under test"
    matrix.write_text(text.replace("11.7716754", "99.0"), encoding="utf-8")

    _post(workspace)
    after = {
        name: [row["RE"] for row in rows]
        for name, (_columns, rows) in _polar_files(workspace).items()
        if "6001" in name
    }
    assert after == before, (
        "the current matrix relabelled a point that had already run: the record still says "
        "11.7716754"
    )


def test_goal019_bandd_the_matrix_still_supplies_what_the_record_does_not(tmp_path):
    """The control. The record wins where the two speak; the matrix speaks elsewhere.

    A precedence change that simply dropped the matrix would empty what the post is
    supposed to carry, so what must be shown is that every matrix cell the record
    says nothing about is still there. DESCRIPTION leaves the polar rows for
    ``products.json`` ``polars.<POL>.description`` (design-post-outputs 2.3 and 6);
    WORKFLOW is the RUN_TYPE of the run block.
    """
    workspace = _workspace(tmp_path)
    _post(workspace)
    document = json.loads(
        (workspace.products_dir("matriz") / "products.json").read_text(encoding="utf-8")
    )
    assert document["polars"]["6001"]["description"] == "CRUISE_wing_body_alpha_sweep"
    assert document["polars"]["6002"]["description"] == "ROTOR_sector_periodic_J_sweep"
    for name, (_columns, rows) in _polar_files(workspace).items():
        if "6001" not in name:
            continue
        assert rows, name
        for row in rows:
            assert row["RUN_TYPE"] == "steady", f"{name} lost the matrix WORKFLOW cell"
