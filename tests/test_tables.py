"""Tier 1: tabular views of parsed results and the sweep aggregation.

Uses the committed sanitized fixtures for the parsers and a synthetic
manifest built in tmp_path through the public files API; no new large
fixtures are committed.
"""

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import pyflightstream
from pyflightstream.fsi.loads import parse_sectional_loads
from pyflightstream.results import (
    AmbiguousLoadsError,
    LoadsNotFoundError,
    MalformedOutputError,
    parse_loads,
    parse_probe_points,
    parse_residual_history,
    parse_run_loads,
    run_table,
    sweep_table,
    to_csv,
    to_table,
)
from pyflightstream.results import tables as tables_module
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def make_record(run_id="camp/sim_9001/a+02.0", sim_id="9001", **overrides):
    body = dict(
        run_id=run_id,
        sim_id=sim_id,
        point={"alpha": 2.0},
        fs_version_requested="26.120",
        package_version=pyflightstream.__version__,
        script_sha256="0" * 64,
        raw_flag=False,
        status=RunStatus.CONVERGED,
    )
    body.update(overrides)
    return RunRecord(**body)


# --- step 1: per-parser adapters ---------------------------------------


def test_loads_to_dataframe_is_one_row_per_surface_plus_total():
    report = parse_loads(read_fixture("loads_unsteady_26.120.txt"))
    frame = to_table(report)
    assert list(frame["surface"]) == ["Blade1", "Wing", "Tail", "Total"]
    assert list(frame.columns[:4]) == ["surface", "Cx", "Cy", "Cz"]
    assert list(frame.columns[-2:]) == ["force_units", "moment_units"]
    total = frame[frame["surface"] == "Total"].iloc[0]
    assert total["CDi"] == pytest.approx(-0.009075)
    assert set(frame["force_units"]) == {"Coefficients"}
    assert set(frame["moment_units"]) == {"Coefficients"}


def test_residual_history_to_dataframe_keeps_iteration_order():
    history = parse_residual_history(read_fixture("log_residuals_26.120.txt"))
    frame = to_table(history)
    assert list(frame.columns) == ["iteration", "velocity_residual", "pressure_residual"]
    assert frame["iteration"].tolist()[0] == 1
    assert frame["iteration"].tolist()[-1] == 1575
    assert frame["velocity_residual"].iloc[-1] == pytest.approx(9.6e-8)


def test_probe_points_to_dataframe_uses_the_printed_columns():
    report = parse_probe_points(read_fixture("probe_points_26.120.txt"))
    frame = to_table(report)
    assert list(frame.columns) == list(report.columns)
    assert frame.shape == (12, len(report.columns))
    assert frame["X"].iloc[0] == pytest.approx(-0.5)
    assert np.allclose(frame.to_numpy(), report.values)


def test_sectional_loads_to_dataframe_carries_unit_suffixed_columns():
    report = parse_sectional_loads(read_fixture("fsi/FS_SurfaceSection_Loads_call0002.txt"))
    frame = to_table(report)
    assert list(frame.columns) == [
        "offset_m",
        "chord_m",
        "x_qc_m",
        "z_qc_m",
        "fx_n_per_m",
        "fz_n_per_m",
        "moment_qc_nm_per_m",
    ]
    assert frame.shape == (100, 7)
    assert frame["offset_m"].iloc[0] == pytest.approx(0.2899)
    assert frame["moment_qc_nm_per_m"].iloc[0] == pytest.approx(7.696)


def test_sectional_dispatch_without_the_extra_raises_didactically(monkeypatch):
    report = parse_sectional_loads(read_fixture("fsi/FS_SurfaceSection_Loads_call0002.txt"))
    monkeypatch.setattr(tables_module, "_sectional_loads_type", lambda: None)
    with pytest.raises(ImportError, match=r"pip install pyflightstream\[fsi\]"):
        to_table(report)


def test_to_csv_round_trips_through_pandas(tmp_path):
    report = parse_loads(read_fixture("loads_steady_26.120.txt"))
    written = to_csv(report, tmp_path / "loads.csv")
    back = pd.read_csv(written)
    assert back[back["surface"] == "Total"]["CL"].iloc[0] == pytest.approx(0.4308)
    assert back["force_units"].iloc[0] == "Coefficients"


def test_to_dataframe_refuses_unknown_inputs_didactically():
    with pytest.raises(TypeError, match="parse_loads"):
        to_table(object())
    with pytest.raises(ValueError, match="empty result list"):
        to_table([])
    with pytest.raises(TypeError, match="to_csv method directly"):
        to_table(pd.DataFrame({"CL": [0.4]}))


# --- the complete column schemas, one literal per table -----------------
#
# OPS-2009.01.03. `RUN_ROW_SCHEMA` below pinned the run row's WHOLE column
# list against a literal; every other table in `results/tables.py` was
# pinned by a fragment (`columns[:4]` and `columns[-2:]` for the loads
# frame), by a per-name lookup (the sweep table), or against the parsed
# report itself (the probe frame, which therefore could not fail). A
# column inserted in the middle of any of them slipped straight past, and
# NFR-19 makes these names a public contract, so it has to be a deliberate
# two-file edit instead.
#
# TWO TABLES ARE DELIBERATELY NOT LISTED HERE, because they already pin
# their complete list where they are tested: `_residual_history_frame`
# (test_residual_history_to_dataframe_keeps_iteration_order) and
# `_sectional_loads_frame`
# (test_sectional_loads_to_dataframe_carries_unit_suffixed_columns). Their
# literals are inline because those tests read the values right beside the
# names; recorded here so a reader does not conclude they were forgotten.
#
# WHY THESE ARE MAPPINGS AND NOT LISTS, while `RUN_ROW_SCHEMA` is a list.
# NFR-19 covers the column NAMES and their units and explicitly NOT their
# order, so what a downstream reader resolves is a LABEL. A literal that
# is a label-to-meaning mapping states exactly the promise, and states the
# unit beside the name where a bare list leaves it to a docstring
# somewhere else. `RUN_ROW_SCHEMA` keeps its ordered form and its own
# comment explaining that order is asserted as a prompt rather than as a
# promise; re-shaping it belongs to the item that owns it, not to this
# one.
#
# NONE OF THESE IS DERIVED from the code under test. A derived expectation
# moves with the code and proves nothing: it would go green on exactly the
# reordering and the silent insertion these exist to catch.

#: `_loads_frame` (results/tables.py): one row per surface plus Total.
LOADS_FRAME_SCHEMA = {
    "surface": "surface name as the solver printed it, plus the row 'Total'",
    "Cx": "force coefficient along x, body frame, units in force_units",
    "Cy": "force coefficient along y, body frame, units in force_units",
    "Cz": "force coefficient along z, body frame, units in force_units",
    "CL": "lift coefficient, wind frame",
    "CDi": "induced drag coefficient, wind frame",
    "CDo": "profile drag coefficient, wind frame",
    "CMx": "moment coefficient about x, units in moment_units",
    "CMy": "moment coefficient about y, units in moment_units",
    "CMz": "moment coefficient about z, units in moment_units",
    "force_units": "what the solver printed as the force normalisation",
    "moment_units": "what the solver printed as the moment normalisation",
}

#: `_probe_points_frame` (results/tables.py). Read the qualifier before
#: reading the floor: these labels are the SOLVER's own printed header,
#: which NFR-19 excludes from the stability promise in as many words, so
#: this literal pins what the committed fixture prints and not a contract
#: this package makes. It is worth pinning anyway, and only for what it
#: does catch: the frame is built with `columns=list(report.columns)`, so
#: the existing test comparing it against `report.columns` cannot fail for
#: any reason at all, and a parser that silently dropped or renamed a
#: column would satisfy it. This one fails.
PROBE_POINTS_FRAME_SCHEMA = {
    "X": "probe x coordinate, simulation length units",
    "Y": "probe y coordinate, simulation length units",
    "Z": "probe z coordinate, simulation length units",
    "Mach": "local Mach number, dimensionless",
    "Cp_ref": "reference pressure coefficient, dimensionless",
    "vx": "velocity component along x",
    "vy": "velocity component along y",
    "vz": "velocity component along z",
    "vtot": "velocity magnitude",
    "Cp": "local pressure coefficient, dimensionless",
    "s_len": "surface arc length from the leading edge",
    "momentum_thickness": "boundary-layer momentum thickness",
    "disp_thick": "boundary-layer displacement thickness",
    "thickness": "boundary-layer thickness",
    "CF": "skin friction coefficient, dimensionless",
    "Transition": "laminar-to-turbulent transition flag",
}

#: `sweep_table` (results/tables.py): one row per manifest record. The
#: labels are the run row's, because a sweep row IS a run row; written out
#: rather than spelled as `RUN_ROW_SCHEMA` plus a delta, because a literal
#: that refers to another literal fails the same way a derived one does.
#: The sweep-axis label is the one entry that is not fixed: this campaign
#: sweeps alpha, and a campaign sweeping beta or advance ratio carries
#: that axis's name in its place.
SWEEP_TABLE_SCHEMA = {
    "run_id": "manifest run identity, campaign/sim/point",
    "sim_id": "simulation identity of the case",
    "alpha": "sweep axis of this campaign, deg (see the note above)",
    "fs_version_requested": "canonical FlightStream version the campaign asked for",
    "fs_version_reported": "version the solver printed in its output footer",
    "fs_build": "build number the solver printed",
    "package_version": "pyflightstream version that ran the point",
    "status": "terminal RunStatus of the point",
    "iterations": "solver iterations reached, NaN when unknown",
    "residual": "final solver residual, dimensionless, NaN when unknown",
    "wall_time_s": "elapsed wall time in s, NaN when unrecorded",
    "frame": "reference frame the coefficients are printed in",
    "force_units": "what the solver printed as the force normalisation",
    "moment_units": "what the solver printed as the moment normalisation",
    "Cx": "Total force coefficient along x",
    "Cy": "Total force coefficient along y",
    "Cz": "Total force coefficient along z",
    "CL": "Total lift coefficient",
    "CDi": "Total induced drag coefficient",
    "CDo": "Total profile drag coefficient",
    "CMx": "Total moment coefficient about x",
    "CMy": "Total moment coefficient about y",
    "CMz": "Total moment coefficient about z",
}

_SCHEMA_ADVICE = (
    "SRS NFR-19 makes these names and their units a public contract: "
    "announce the change in the changelog's API surface delta and update "
    "this literal in the same commit. If the literal is red on its first "
    "run against unchanged code, that is a finding to raise rather than a "
    "number to adjust."
)


@pytest.mark.requirement("NFR-19")
def test_loads_frame_exposes_its_complete_column_schema():
    """The loads frame's whole label set, not its first four and last two.

    `test_loads_to_dataframe_is_one_row_per_surface_plus_total` pins
    `columns[:4]` and `columns[-2:]`, so a column inserted anywhere
    between Cz and force_units passes it. Measured on both committed
    fixtures, steady and unsteady, because one table's header is not
    evidence that the other's matches.
    """
    for fixture in ("loads_steady_26.120.txt", "loads_unsteady_26.120.txt"):
        frame = to_table(parse_loads(read_fixture(fixture)))
        assert set(frame.columns) == set(LOADS_FRAME_SCHEMA), (
            f"the loads frame's column labels changed on {fixture}. " + _SCHEMA_ADVICE
        )
        assert len(frame.columns) == len(LOADS_FRAME_SCHEMA), (
            f"the loads frame of {fixture} repeats a column label; the set "
            "comparison above cannot see a duplicate"
        )


@pytest.mark.requirement("NFR-19")
def test_probe_points_frame_exposes_its_complete_column_schema():
    """The probe frame, pinned against a literal instead of against itself.

    `test_probe_points_to_dataframe_uses_the_printed_columns` compares
    `frame.columns` against `report.columns`, and `_probe_points_frame`
    BUILDS the frame with `columns=list(report.columns)`, so that
    assertion is true by construction and cannot fail. What is pinned
    here is the fixture's printed header, which is the solver's and not
    this package's promise (NFR-19 excludes it explicitly); it still
    catches a parser that starts dropping or renaming a column.
    """
    frame = to_table(parse_probe_points(read_fixture("probe_points_26.120.txt")))
    assert set(frame.columns) == set(PROBE_POINTS_FRAME_SCHEMA), (
        "the probe-point frame's column labels changed. These are the SOLVER's "
        "printed names, so a change here is evidence about the export rather "
        "than a decision of this package: check the fixture and the parser "
        "before editing the literal."
    )
    assert len(frame.columns) == len(PROBE_POINTS_FRAME_SCHEMA)


# --- step 2: run-level merge -------------------------------------------


#: The complete run-row column schema, written out rather than derived from
#: `_RUN_IDENTITY_COLUMNS` / `_RUN_OUTCOME_COLUMNS`. Deriving it would move
#: with the code and prove nothing. SRS NFR-19 promises that these names and
#: their units are a public contract and that a change to them is ANNOUNCED;
#: the other tests in this module pin fragments and per-name lookups, which
#: catch a rename but not a column silently ADDED in the middle. This literal
#: makes any schema change a deliberate two-file edit, which is what
#: "announced" has to mean mechanically.
#:
#: Order is NOT part of the promise (NFR-19 says so explicitly). It is
#: asserted here anyway because a list comparison is the readable form, and a
#: pure reorder failing this test is the intended prompt to check the
#: changelog, not a defect claim.
RUN_ROW_SCHEMA = [
    "run_id",
    "sim_id",
    "alpha",
    "fs_version_requested",
    "fs_version_reported",
    "fs_build",
    "package_version",
    "status",
    "iterations",
    "residual",
    "wall_time_s",
    "frame",
    "force_units",
    "moment_units",
    "Cx",
    "Cy",
    "Cz",
    "CL",
    "CDi",
    "CDo",
    "CMx",
    "CMy",
    "CMz",
]


def test_run_table_exposes_the_documented_column_schema():
    """NFR-19: the run row's full column set is the public contract.

    `alpha` is the sweep-axis column of this fixture; a case swept on another
    axis carries that axis's name instead, which is why the sweep axis sits
    between the identity block and the version block rather than at the end.
    """
    loads = parse_loads(read_fixture("loads_steady_26.120.txt"))
    record = make_record(
        iterations=312, residual=3.2e-6, wall_time_s=41.5, outputs=["raw/loads.txt"]
    )
    assert list(run_table(record, loads=loads).columns) == RUN_ROW_SCHEMA, (
        "the run-row column schema changed. SRS NFR-19 makes these names a "
        "public contract: announce the change in the changelog's API surface "
        "delta and update this list in the same commit."
    )


def test_run_table_joins_identity_conditions_and_total_coefficients():
    loads = parse_loads(read_fixture("loads_steady_26.120.txt"))
    record = make_record(
        iterations=312, residual=3.2e-6, wall_time_s=41.5, outputs=["raw/loads.txt"]
    )
    frame = run_table(record, loads=loads)
    assert frame.shape[0] == 1
    row = frame.iloc[0]
    assert list(frame.columns[:3]) == ["run_id", "sim_id", "alpha"]
    assert row["run_id"] == "camp/sim_9001/a+02.0"
    assert row["alpha"] == 2.0
    assert row["fs_version_requested"] == "26.120"
    assert row["status"] == "CONVERGED"
    assert row["iterations"] == 312
    assert row["wall_time_s"] == pytest.approx(41.5)
    assert row["frame"] == "Reference"
    assert row["force_units"] == "Coefficients"
    assert row["CL"] == pytest.approx(0.4308)
    assert row["CMy"] == pytest.approx(-0.0912)


def test_run_table_without_loads_keeps_identity_and_nan_outcome():
    record = make_record(status=RunStatus.FAILED_EXECUTION, error="timed out")
    frame = run_table(record)
    row = frame.iloc[0]
    assert row["status"] == "FAILED_EXECUTION"
    assert math.isnan(row["iterations"])
    assert "CL" not in frame.columns


def test_run_table_refuses_colliding_sweep_axis_names():
    loads = parse_loads(read_fixture("loads_steady_26.120.txt"))
    with pytest.raises(ValueError, match="collides"):
        run_table(make_record(point={"status": 1.0}))
    with pytest.raises(ValueError, match="collides"):
        run_table(make_record(point={"CL": 1.0}), loads=loads)


# --- step 3: sweep aggregation through the manifest --------------------


def collect_text(workspace, sim_id, tmp_path, name, text):
    """Collect one output through the public files API and return it."""
    produced = tmp_path / name
    produced.write_text(text, encoding="utf-8")
    return workspace.collect_outputs(sim_id, [produced])


def build_sweep_workspace(tmp_path):
    """Synthetic three-run manifest: two runs with loads, one failed."""
    workspace = CampaignWorkspace(tmp_path / "camp")
    outputs_a = collect_text(
        workspace, "9001", tmp_path, "loads_a0.txt", read_fixture("loads_steady_26.120.txt")
    )
    workspace.append_record(
        make_record(
            run_id="camp/sim_9001/a+02.0",
            point={"alpha": 2.0},
            iterations=312,
            outputs=outputs_a,
        )
    )
    outputs_b = collect_text(
        workspace, "9001", tmp_path, "loads_a1.txt", read_fixture("loads_unsteady_26.120.txt")
    )
    workspace.append_record(
        make_record(
            run_id="camp/sim_9001/a+00.0",
            point={"alpha": 0.0},
            status=RunStatus.COMPLETED_MAX_ITER,
            iterations=1575,
            outputs=outputs_b,
        )
    )
    workspace.append_record(
        make_record(
            run_id="camp/sim_9001/a+04.0",
            point={"alpha": 4.0},
            status=RunStatus.FAILED_EXECUTION,
            error="solver crashed",
        )
    )
    return workspace


def test_sweep_table_builds_one_row_per_manifest_record(tmp_path):
    workspace = build_sweep_workspace(tmp_path)
    frame = sweep_table(workspace)
    assert frame.shape[0] == 3
    assert frame["alpha"].tolist() == [2.0, 0.0, 4.0]
    assert frame["CL"].iloc[0] == pytest.approx(0.4308)
    assert frame["CL"].iloc[1] == pytest.approx(0.00166)
    assert math.isnan(frame["CL"].iloc[2])
    assert frame["status"].tolist() == ["CONVERGED", "COMPLETED_MAX_ITER", "FAILED_EXECUTION"]
    # A second workspace over the same root reads the same manifest. This
    # used to be written as `sweep_table(tmp_path / "camp")`, a bare root
    # path the function coerced for itself; the coercion is gone (see
    # test_a_bare_root_path_is_refused_with_the_call_that_replaces_it).
    again = sweep_table(CampaignWorkspace(tmp_path / "camp"))
    assert again["run_id"].tolist() == frame["run_id"].tolist()
    # The final csv is one DataFrame.to_csv away.
    frame.to_csv(tmp_path / "sweep.csv", index=False)
    back = pd.read_csv(tmp_path / "sweep.csv")
    assert back.shape[0] == 3


@pytest.mark.requirement("NFR-19")
def test_sweep_table_exposes_its_complete_column_schema(tmp_path):
    """The sweep table's whole label set, not the three names read by name.

    `test_sweep_table_builds_one_row_per_manifest_record` reads alpha, CL
    and status by name, which catches a rename of those three and nothing
    else: a column added, removed or renamed anywhere else passes it. This
    campaign holds one converged run, one iteration-limited run and one
    failed run, so the union of the row shapes is exercised rather than
    the happy one alone.
    """
    frame = sweep_table(build_sweep_workspace(tmp_path))
    assert set(frame.columns) == set(SWEEP_TABLE_SCHEMA), (
        "the sweep table's column labels changed. " + _SCHEMA_ADVICE
    )
    assert len(frame.columns) == len(SWEEP_TABLE_SCHEMA)
    # The failed run has no coefficients and must still carry the columns,
    # as NaN, or the table would stop accounting for every executed point
    # and a downstream reader would meet a ragged frame.
    failed = frame[frame["status"] == "FAILED_EXECUTION"].iloc[0]
    assert math.isnan(failed["CL"]) and math.isnan(failed["CDi"])


def test_sweep_table_refuses_an_empty_manifest(tmp_path):
    with pytest.raises(ValueError, match="no manifest records"):
        sweep_table(CampaignWorkspace(tmp_path))


def test_a_bare_root_path_is_refused_with_the_call_that_replaces_it():
    """OPS-2009.02.05: the DELETE branch, and what a caller now reads.

    Both entry points took a `CampaignWorkspace` OR its root path until
    v0.8.0, and building the workspace from a path is what made this
    layer import the layer above it. The import was deferred into the
    helper's body, which changed nothing about the direction and only
    hid it from a module-level reader, so the convenience went rather
    than being blessed as AD-01's one exception.

    The break is deliberate and the refusal has to carry the remedy, or
    a user meets an AttributeError from inside a private helper instead.
    Asserted on the CONTENT of the message rather than on its type
    alone: the type says "wrong", the sentence says what to write.
    """
    for call, name in (
        (lambda root: sweep_table(root), "sweep_table"),
        (lambda root: parse_run_loads(root, "camp/sim_9001/a+02.0"), "parse_run_loads"),
    ):
        with pytest.raises(MalformedOutputError) as caught:
            call(Path("some/campaign/root"))
        message = str(caught.value)
        assert name in message
        assert "CampaignWorkspace" in message, (
            "the refusal must name the class the caller has to construct"
        )
        assert "from pyflightstream.workspace import CampaignWorkspace" in message, (
            "the refusal must carry the import line, since the remedy is one "
            "import and one call and a message that omits it teaches nothing"
        )
    # And it stays catchable as a ValueError, which is what the catalogue
    # promises for every class it holds: code written before this release
    # that wrapped these calls in `except ValueError` still catches.
    with pytest.raises(ValueError):
        sweep_table(Path("some/campaign/root"))


def test_sweep_table_flags_a_wrong_loads_file_name(tmp_path):
    workspace = build_sweep_workspace(tmp_path)
    with pytest.raises(LoadsNotFoundError, match="no collected output is named"):
        sweep_table(workspace, loads_file="polar.txt")


def test_parse_run_loads_resolves_by_run_id(tmp_path):
    workspace = build_sweep_workspace(tmp_path)
    report = parse_run_loads(workspace, "camp/sim_9001/a+02.0")
    assert report.angle_of_attack_deg == 2.0
    with pytest.raises(ValueError, match="identity authority"):
        parse_run_loads(workspace, "camp/sim_9001/a+99.0")


def test_parse_run_loads_for_a_failed_point_is_a_loads_not_found(tmp_path):
    workspace = build_sweep_workspace(tmp_path)
    with pytest.raises(LoadsNotFoundError, match="no collected outputs"):
        parse_run_loads(workspace, "camp/sim_9001/a+04.0")


def test_parse_run_loads_refuses_ambiguity_until_named(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    outputs = collect_text(
        workspace, "9001", tmp_path, "first.txt", read_fixture("loads_steady_26.120.txt")
    ) + collect_text(
        workspace, "9001", tmp_path, "second.txt", read_fixture("loads_steady_26.120.txt")
    )
    record = make_record(outputs=outputs)
    with pytest.raises(AmbiguousLoadsError, match="loads_file"):
        parse_run_loads(workspace, record)
    report = parse_run_loads(workspace, record, loads_file="second.txt")
    assert report.total["CL"] == pytest.approx(0.4308)
    with pytest.raises(LoadsNotFoundError, match="no collected output named"):
        parse_run_loads(workspace, record, loads_file="third.txt")


def test_parse_run_loads_refuses_an_overwritten_export(tmp_path):
    # The record claims alpha +4.0 but the collected spreadsheet prints
    # alpha +2.0: the same named export of a later point overwrote it.
    workspace = CampaignWorkspace(tmp_path / "camp")
    outputs = collect_text(
        workspace, "9001", tmp_path, "loads.txt", read_fixture("loads_steady_26.120.txt")
    )
    record = make_record(run_id="camp/sim_9001/a+04.0", point={"alpha": 4.0}, outputs=outputs)
    with pytest.raises(ValueError, match="not the evidence of this run"):
        parse_run_loads(workspace, record)


def test_parse_run_loads_names_a_missing_file_on_disk(tmp_path):
    workspace = CampaignWorkspace(tmp_path / "camp")
    workspace.create_sim("9001")
    record = make_record(outputs=["raw/gone.txt"])
    with pytest.raises(FileNotFoundError, match="archived or"):
        parse_run_loads(workspace, record)
