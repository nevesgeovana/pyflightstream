"""Tier 1: how the post stage names and files what it writes.

FR-85, FR-86, FR-87, FR-88 and FR-90, which are five readings of the
same workspace the author sent back after running 0.15.0 on a real
geometry: the per-polar tables loose at the top level beside the
directories, under a second naming convention, with no column telling
their rows apart, the flow-field samples under the name of the solver
verb that produced them, the provenance documents under a third
convention, and one table written twice.

The campaign here sweeps the ADVANCE RATIO at a fixed incidence, which
is the shape the author ran and the shape that exposes all of it: every
row of such a polar carries the same ALPHA, BETA, MACH and RE, so a
table whose rows are told apart by their order is not caught by any
sweep over angle.
"""

from __future__ import annotations

import json
from pathlib import Path

from pyflightstream.post.products import (
    COEFFICIENT_COLUMNS,
    read_csv_table,
    read_custom_polar_format,
    write_campaign_products,
)
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

FIXTURES = Path(__file__).parent / "fixtures"

#: The three advance ratios of the swept polar, and the lift each point
#: came back with, so the rows are not identical for a reason unrelated
#: to the sweep.
SWEPT = ((1.0, "+0.4308000"), (1.5, "+0.5120000"), (2.0, "+0.6010000"))

MATRIX = "matriz"
SIM = "0001"
MACH = 0.15

#: An unsteady plots export carrying the forces AND the fluid
#: quantities, which is what UNSTEADY_SOLVER_EXPORT_PLOTS writes when the
#: row created fluid plots ("every unsteady solver plot, force and
#: fluid", the command database entry for it).
PLOTS_EXPORT = """\
                              FlightStream Unsteady Solver Plots


     Simulation file:                            c:/campaign/P.fsm
     Angle of attack (Deg)                       2.000
     Side-slip angle (Deg)                       .000
     Freestream velocity (m/s)                   30.000
     Solver mode:                                Unsteady
     Reference velocity (m/s)                    30.000
     Reference length (m)                        1.500
     Reference area (m^2)                        11.500
     Current solver iteration number:            2
----------------------------------------------------------------------------------------------------
Time-step,CL_MRP_TOTAL,FX_MRP_TOTAL,CP_FREE1,VELOCITY1
----------------------------------------------------------------------------------------------------
1.0000,.22538,1411.9,-.32000,30.100,
2.0000,.22600,1412.0,-.34000,30.400,
----------------------------------------------------------------------------------------------------
     Force Units: Coefficients
     Moment Units: Coefficients
     Software : Flightstream version 26.1, build #7012026
     Company  : Altair
     Date: 8/3/2026, Time: 2305 hours (local)
"""


def _loads(lift: str) -> str:
    """The committed steady export with one point's lift substituted in."""
    text = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
    return text.replace("+0.4308000", lift)


def _point_name(advance_ratio: float) -> str:
    """The author's own point convention, which the scripts already carry."""
    return f"POLAR-{SIM}_M15AL+020BE+000J{round(advance_ratio * 100):+04d}"


def _workspace(tmp_path: Path, *, plots: bool = False) -> CampaignWorkspace:
    """A recorded advance-ratio sweep of one simulation, ready to post-process."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    products = "custom_polar_format = true\n"
    if plots:
        products += "plots = true\n"
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        f'[groups]\n"1" = ["Wing"]\n\n[products]\n{products}', encoding="utf-8"
    )
    collected = workspace.sim_dir(SIM) / "outputs"
    collected.mkdir(parents=True)
    for advance_ratio, lift in SWEPT:
        stem = _point_name(advance_ratio)
        (collected / f"{stem}.txt").write_text(_loads(lift), encoding="utf-8")
        outputs = [f"outputs/{stem}.txt"]
        if plots:
            (collected / f"{stem}_plots.txt").write_text(PLOTS_EXPORT, encoding="utf-8")
            outputs.append(f"outputs/{stem}_plots.txt")
        workspace.append_record(
            RunRecord(
                run_id=f"camp/sim_{SIM}/a+02.0_b+00.0_j{advance_ratio:+05.1f}",
                sim_id=SIM,
                point={"alpha": 2.0, "beta": 0.0, "advance_ratio": advance_ratio},
                matrix_stem=MATRIX,
                fs_version_requested="26.120",
                package_version="0.16.0.dev0",
                script_path=f"scripts/{stem}.txt",
                script_sha256="c" * 64,
                raw_flag=False,
                pproc="p001",
                description="ROTOR_SWEEP",
                mach=MACH,
                reference={"SREF": 11.5, "CREF": 1.5, "BREF": 8.0, "XMOM": 1.0},
                status=RunStatus.CONVERGED,
                outputs=outputs,
            )
        )
    return workspace


def _out(workspace: CampaignWorkspace) -> Path:
    return workspace.products_dir(MATRIX)


def _the_polar_table(out: Path) -> Path:
    """The one polar table the stage wrote, found by shape and not by name."""
    tables = sorted(path for path in out.rglob("*.csv") if path.name != "campaign_sweep.csv")
    assert len(tables) == 1, f"expected one polar table, found {[p.name for p in tables]}"
    return tables[0]


def _files_under(out: Path) -> list[str]:
    """Every file the post stage left, relative to the products folder."""
    return sorted(path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file())


# --- FR-88: the per-polar tables live in a polars subfolder ------------------------


def test_the_polar_tables_and_their_dat_companions_land_under_polars(tmp_path):
    """FR-88, first half. Every other family of file has a directory; these had none."""
    workspace = _workspace(tmp_path)
    write_campaign_products(workspace, matrix_stem=MATRIX)
    out = _out(workspace)
    written = _files_under(out)
    tables = [name for name in written if name.endswith((".csv", ".dat"))]
    assert tables, f"the stage wrote no table at all: {written}"
    assert all(name.startswith("polars/") for name in tables), (
        f"a per-polar table is not under polars/: {tables}"
    )


def test_nothing_per_polar_is_left_loose_at_the_top_of_the_matrix_folder(tmp_path):
    """FR-88, first half, from the reader's side: the top level is a directory."""
    workspace = _workspace(tmp_path)
    write_campaign_products(workspace, matrix_stem=MATRIX)
    out = _out(workspace)
    loose = sorted(path.name for path in out.iterdir() if path.is_file())
    assert loose == ["products.json"], (
        f"the top of {out.name}/ holds {loose}; only the campaign's own manifest belongs there"
    )


def test_the_campaign_level_files_stay_where_they_are(tmp_path):
    """FR-88, second half, and it is the half a check for an empty top level would miss.

    ``campaign_sweep.csv`` is about the CAMPAIGN and not about one
    polar's sweep, so a move that swept it into ``polars/`` would satisfy
    the assertion above and be wrong.
    """
    workspace = _workspace(tmp_path)
    sweep = workspace.sweep_dir(MATRIX)
    sweep.mkdir(parents=True, exist_ok=True)
    (sweep / "campaign_sweep.csv").write_text("run_id\ncamp/sim_0001\n", encoding="utf-8")
    write_campaign_products(workspace, matrix_stem=MATRIX)
    out = _out(workspace)
    assert (out / "campaign_sweep.csv").is_file(), (
        "the campaign sweep table was moved or removed by the post stage"
    )
    assert not (out / "polars" / "campaign_sweep.csv").exists()


def test_the_products_manifest_names_the_tables_where_they_are(tmp_path):
    """FR-88: a path in ``products.json`` that does not resolve is worse than no path."""
    workspace = _workspace(tmp_path)
    write_campaign_products(workspace, matrix_stem=MATRIX)
    out = _out(workspace)
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    named = sorted(manifest["products"])
    assert named, f"products.json names nothing: {manifest}"
    for relative in named:
        assert (out / relative).is_file(), f"products.json names {relative}, which is not there"
    assert any(name.startswith("polars/") for name in named), (
        f"no polar table is named under polars/: {named}"
    )


# --- FR-86: a provenance file is named by the same convention as everything beside it


def _provenance(out: Path) -> dict[str, str]:
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    return manifest["provenance"]


def test_a_provenance_file_carries_the_point_name_its_script_carries(tmp_path):
    """FR-86. Two conventions sat in one run for one point.

    ``sims/sim_0001/scripts/`` held ``POLAR-0001_M15AL+020BE+000J+100.txt``
    and ``post/matriz/provenance/`` held the run id with its separators
    replaced, so a reader sorting the two directories side by side could
    not line them up, which is the job a naming convention exists to do.
    """
    workspace = _workspace(tmp_path)
    write_campaign_products(workspace, matrix_stem=MATRIX)
    out = _out(workspace)
    written = sorted(path.name for path in (out / "provenance").iterdir())
    assert written == sorted(f"{_point_name(j)}.prov.json" for j, _ in SWEPT), (
        f"the provenance documents are named {written}"
    )
    for relative in _provenance(out).values():
        assert (out / relative).is_file(), f"products.json names {relative}, which is not there"


def test_nothing_renames_a_run(tmp_path):
    """FR-86. The file moves; the identity does not.

    The run id is a good identifier and stays exactly what it was, both
    as the key of the products manifest and as a field INSIDE the
    document. A test that only checked the file name would not see a
    rename that reached the identity.
    """
    workspace = _workspace(tmp_path)
    recorded = [record.run_id for record in workspace.read_manifest()]
    write_campaign_products(workspace, matrix_stem=MATRIX)
    out = _out(workspace)
    index = _provenance(out)
    assert sorted(index) == sorted(recorded), "the products manifest no longer keys on the run id"
    for run_id, relative in index.items():
        document = json.loads((out / relative).read_text(encoding="utf-8"))
        activity = document["activity"][f"pyfs:run/{run_id}"]
        assert activity["pyfs:run_id"] == run_id, (
            f"{relative} records the run as {activity['pyfs:run_id']!r}, not {run_id!r}"
        )


def test_two_records_rendering_one_point_name_do_not_overwrite_each_other(tmp_path):
    """FR-86, the trap under it: the run id was UNIQUE and a point name need not be.

    The default naming template is ``{point}``, which carries no sim id,
    so two simulations of one matrix swept over the same angles render
    the same stem. Naming the document after the point alone would have
    had the second run's provenance overwrite the first's, silently, and
    the manifest would have named one file for two runs.
    """
    workspace = _workspace(tmp_path)
    collected = workspace.sim_dir("0002") / "outputs"
    collected.mkdir(parents=True)
    stem = _point_name(1.0)
    (collected / f"{stem}.txt").write_text(_loads("+0.4308000"), encoding="utf-8")
    twin = workspace.read_manifest()[0].model_copy(
        update={
            "run_id": "camp/sim_0002/a+02.0_b+00.0_j+01.0",
            "sim_id": "0002",
            "script_path": f"scripts/{stem}.txt",
            "outputs": [f"outputs/{stem}.txt"],
        }
    )
    workspace.append_record(twin)
    write_campaign_products(workspace, matrix_stem=MATRIX)
    out = _out(workspace)
    index = _provenance(out)
    assert len(set(index.values())) == len(index), (
        f"two runs share one provenance document: {index}"
    )
    for run_id, relative in index.items():
        document = json.loads((out / relative).read_text(encoding="utf-8"))
        assert f"pyfs:run/{run_id}" in document["activity"], (
            f"{relative} is named for {run_id} and records another run"
        )
    # AND THE FALLBACK IS NARROW, which is the half a uniqueness check
    # alone cannot see: only the two records that CLAIM the contested
    # stem go back to the run id, and the points nothing collides with
    # keep the convention. Falling back for everything would pass the
    # assertion above and undo FR-86 entirely.
    assert index == {
        "camp/sim_0001/a+02.0_b+00.0_j+01.0": (
            "provenance/camp_sim_0001_a+02.0_b+00.0_j+01.0.prov.json"
        ),
        "camp/sim_0002/a+02.0_b+00.0_j+01.0": (
            "provenance/camp_sim_0002_a+02.0_b+00.0_j+01.0.prov.json"
        ),
        "camp/sim_0001/a+02.0_b+00.0_j+01.5": f"provenance/{_point_name(1.5)}.prov.json",
        "camp/sim_0001/a+02.0_b+00.0_j+02.0": f"provenance/{_point_name(2.0)}.prov.json",
    }, f"the fallback did not stop at the contested point: {index}"


# --- FR-85: the polar table's name, and the column that tells its rows apart -------


def test_the_polar_table_takes_the_standard_name_with_sweep_in_the_swept_field(tmp_path):
    """FR-85, first half. One point was written under two conventions.

    Measured in the workspace the author sent back, for one point of one run:
    the script ``POLAR-0001_M15AL+000BE+000J+100.txt`` and the polar table
    ``0001_M15_g01.csv``. The second carries neither the angles the first
    carries nor the advance ratio the run actually swept.
    """
    workspace = _workspace(tmp_path)
    write_campaign_products(workspace, matrix_stem=MATRIX)
    out = _out(workspace)
    written = sorted(path.name for path in (out / "polars").iterdir())
    assert written == [
        "POLAR-0001_M15AL+020BE+000J+sweep_g01.csv",
        "POLAR-0001_M15AL+020BE+000J+sweep_g01.dat",
    ], f"the polar tables are named {written}"


def test_the_polar_table_carries_the_swept_value_and_two_rows_differ_in_it(tmp_path):
    """FR-85, second half, and it is the worse one.

    Measured on the author's ``0001_M15_g01.csv``: the three rows of a
    three-value sweep carried identical ALPHA, BETA, MACH and RE and no
    column naming the swept value, so the only thing distinguishing the
    first row from the third was its position in the file. A table whose
    rows are told apart by order is not a table.
    """
    workspace = _workspace(tmp_path)
    write_campaign_products(workspace, matrix_stem=MATRIX)
    # FOUND BY GLOB AND NOT BY NAME, so this half falsifies on its own
    # assertion rather than on the file name the half above is about.
    columns, rows = read_csv_table(_the_polar_table(_out(workspace)))
    assert "J" in columns, f"the polar table carries no column for the advance ratio: {columns}"
    assert len(rows) == len(SWEPT)
    swept = [row["J"] for row in rows]
    assert len(set(swept)) == len(swept), f"the rows cannot be told apart by J: {swept}"
    told_apart = {column for column in columns if len({row[column] for row in rows}) > 1}
    assert "J" in told_apart, (
        f"only {sorted(told_apart)} differ between rows, and the swept variable is not among them"
    )


def test_a_polar_table_written_under_the_old_name_and_shape_is_still_read(tmp_path):
    """FR-85: a workspace holding tables under the old name is still read.

    Both readers take a PATH and neither parses a name for meaning, which
    is the property that makes the rename safe; and neither requires the
    column that arrived with it. Scored against a CONTROL, the table this
    release writes, so the check cannot pass by refusing to read either.
    """
    old = tmp_path / "0001_M15_g01.csv"
    header = ("POLAR", "DESCRIPTION", "GROUP", "SREF", *COEFFICIENT_COLUMNS)
    old.write_text(
        ",".join(header) + "\n" + ",".join(["0001", "ROTOR", "1", "11.5"] + ["0.0"] * 24) + "\n",
        encoding="utf-8",
    )
    columns, rows = read_csv_table(old)
    assert columns == header and len(rows) == 1, "a table under the old name no longer reads"
    assert "J" not in columns, "the fixture is not the old shape, so it proves nothing"

    workspace = _workspace(tmp_path)
    write_campaign_products(workspace, matrix_stem=MATRIX)
    control = _the_polar_table(_out(workspace))
    assert read_csv_table(control)[1], "the control table did not read either"
    assert read_custom_polar_format(control.with_suffix(".dat")).rows, (
        "the custom format beside it did not read"
    )


# --- FR-87: flow-field samples go to probes, whatever the run type was -------------


def _with_flow_field_samples(tmp_path: Path) -> CampaignWorkspace:
    """The swept polar again, with an unsteady point and a steady point beside it.

    Both cite the same pproc artifact, which is the condition FR-87 names:
    a reader of a finished campaign should not have to know whether a row
    was steady or unsteady to know where the flow-field samples are.
    """
    workspace = _workspace(tmp_path, plots=True)
    collected = workspace.sim_dir("0002") / "outputs"
    collected.mkdir(parents=True)
    stem = "POLAR-0002_M15AL+020BE+000"
    (collected / f"{stem}.txt").write_text(_loads("+0.4308000"), encoding="utf-8")
    (collected / f"{stem}_probes.txt").write_text(
        (FIXTURES / "probe_points_26.120.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    steady = workspace.read_manifest()[0].model_copy(
        update={
            "run_id": "camp/sim_0002/a+02.0",
            "sim_id": "0002",
            "point": {"alpha": 2.0, "beta": 0.0},
            "script_path": f"scripts/{stem}.txt",
            "outputs": [f"outputs/{stem}.txt", f"outputs/{stem}_probes.txt"],
        }
    )
    workspace.append_record(steady)
    return workspace


def test_a_steady_row_and_an_unsteady_row_put_their_samples_in_one_place(tmp_path):
    """FR-87, second claim. ``plots`` named the solver verb, not what the file holds.

    THE GENERICITY IS THE REQUIREMENT and not a side effect: one folder,
    whatever produced it.
    """
    workspace = _with_flow_field_samples(tmp_path)
    write_campaign_products(workspace, matrix_stem=MATRIX)
    out = _out(workspace)
    written = _files_under(out)
    samples = [name for name in written if "plots" in name or "probes" in name]
    assert samples, f"no flow-field samples were written at all: {written}"
    folders = {name.split("/")[0] for name in samples if name.endswith(".csv")}
    assert folders == {"probes"}, (
        f"the flow-field samples of the two run types landed in {sorted(folders)}"
    )
    assert any("_plots.csv" in name for name in samples), "the unsteady row's table is missing"
    assert any("_probes.csv" in name for name in samples), "the steady row's table is missing"


def test_the_fluid_columns_reach_the_table_of_a_row_that_asked_for_them(tmp_path):
    """FR-87, first claim: the forces AND the fluid properties.

    The unsteady plots export carries one column per plot, force and
    fluid alike, and a row whose artifact declares probe parameters
    creates a fluid plot per vertex and parameter. Nothing between the
    export and the table may drop them: a lost quantity is gone until the
    point is run again, which is what makes this the expensive half.
    """
    workspace = _with_flow_field_samples(tmp_path)
    write_campaign_products(workspace, matrix_stem=MATRIX)
    out = _out(workspace)
    # FOUND BY GLOB, so the CONTENT half falsifies on its own assertion
    # and not on the folder name the half above is about.
    unsteady = next(out.rglob(f"{_point_name(1.0)}_plots.csv"))
    columns, rows = read_csv_table(unsteady)
    assert {"CP_FREE1", "VELOCITY1"} <= set(columns), (
        f"the fluid quantities are not in the table: {columns}"
    )
    assert {"CL_MRP_TOTAL", "FX_MRP_TOTAL"} <= set(columns), "the forces are not there either"
    assert rows, "the table has no time step"

    steady = next(out.rglob("POLAR-0002_M15AL+020BE+000_probes.csv"), None)
    assert steady is not None, "the steady row's flow-field samples were not tabled at all"
    columns, rows = read_csv_table(steady)
    assert {"Mach", "vtot", "Cp"} <= set(columns), (
        f"the steady row's flow-field sample carries no fluid quantity: {columns}"
    )
    assert rows, "the steady table has no sample"


def test_the_products_manifest_names_the_samples_under_probes(tmp_path):
    """FR-87: a reader finds them through ``products.json`` or not at all."""
    workspace = _with_flow_field_samples(tmp_path)
    write_campaign_products(workspace, matrix_stem=MATRIX)
    out = _out(workspace)
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    samples = [name for name in manifest["products"] if name.startswith("probes/")]
    assert len(samples) >= 2, f"products.json names {sorted(manifest['products'])}"
    for relative in samples:
        assert (out / relative).is_file()
    assert not any(name.startswith("plots/") for name in manifest["products"]), (
        "products.json still names the folder after the solver verb"
    )
    assert not any(key.startswith("plots/") for key in manifest["skipped"]), (
        "a skip is recorded under a folder that no longer exists"
    )
