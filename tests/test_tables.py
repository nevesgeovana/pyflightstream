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
    DATA_ORIGIN_CODES,
    PROVENANCE_COLUMNS,
    REDUCTION_CODES,
    AmbiguousLoadsError,
    LoadsNotFoundError,
    MalformedOutputError,
    origin_code,
    parse_loads,
    parse_probe_points,
    parse_residual_history,
    parse_run_loads,
    reduction_code,
    run_table,
    sweep_table,
    to_csv,
    to_table,
    write_table,
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
    assert list(frame.columns[-4:]) == [
        "force_units",
        "moment_units",
        "data_origin",
        "reduction",
    ]
    total = frame[frame["surface"] == "Total"].iloc[0]
    assert total["CDi"] == pytest.approx(-0.009075)
    assert set(frame["force_units"]) == {"Coefficients"}
    assert set(frame["moment_units"]) == {"Coefficients"}


def test_residual_history_to_dataframe_keeps_iteration_order():
    history = parse_residual_history(read_fixture("log_residuals_26.120.txt"))
    frame = to_table(history)
    assert list(frame.columns) == [
        "iteration",
        "velocity_residual",
        "pressure_residual",
        "data_origin",
        "reduction",
    ]
    assert frame["iteration"].tolist()[0] == 1
    assert frame["iteration"].tolist()[-1] == 1575
    assert frame["velocity_residual"].iloc[-1] == pytest.approx(9.6e-8)


def test_probe_points_to_dataframe_uses_the_printed_columns():
    report = parse_probe_points(read_fixture("probe_points_26.120.txt"))
    frame = to_table(report)
    assert list(frame.columns) == [*report.columns, *PROVENANCE_COLUMNS]
    assert frame.shape == (12, len(report.columns) + len(PROVENANCE_COLUMNS))
    assert frame["X"].iloc[0] == pytest.approx(-0.5)
    assert np.allclose(frame[list(report.columns)].to_numpy(), report.values)


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
        "data_origin",
        "reduction",
    ]
    assert frame.shape == (100, 9)
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
# WHY THESE ARE MAPPINGS AND NOT LISTS. NFR-19 covers the column NAMES and
# their units and explicitly NOT their order, so what a downstream reader
# resolves is a LABEL. A literal that is a label-to-meaning mapping states
# exactly the promise, and states the unit beside the name where a bare list
# leaves it to a docstring somewhere else.
#
# `RUN_ROW_SCHEMA` was the one exception, an ordered list compared with
# `==`, and this paragraph used to say re-shaping it belonged to the item
# that owned it. PFS-2014.05 was that item: adding a column is not a
# breaking change under the author's convention of 2026-08-17, and the
# ordered form made the addition fail an assertion whose own message told
# the reader to check the changelog. All four are mappings now.
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
    "data_origin": "raw off the run or reduced by post-processing (PFS-2014.05)",
    "reduction": "which reduction produced the numbers, none where nothing did",
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
    # NOT the solver's: these two are this package's own promise, added to
    # every table it writes by PFS-2014.05, which is why the qualifier
    # above about printed headers does not reach them.
    "data_origin": "raw off the run or reduced by post-processing (PFS-2014.05)",
    "reduction": "which reduction produced the numbers, none for a point sample",
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
    "data_origin": "raw off the run or reduced by post-processing (PFS-2014.05)",
    "reduction": "none on a steady point, time_average on an unsteady one",
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
#: IT WAS AN ORDERED LIST COMPARED WITH `==` until 2026-08-19, and that
#: contradicted the author's own convention of 2026-08-17: an output has no
#: fixed column order, a reader resolves a column by its LABEL, and adding a
#: column is therefore not a breaking change. The ordered form made this
#: assertion fail on the addition PFS-2014.05 announced in the changelog,
#: which is the false alarm the convention exists to prevent, and it was the
#: only one of the four schema literals in this file still shaped that way.
#: It is a label-to-meaning mapping now, like its three siblings, with the
#: duplicate check the set comparison cannot make by itself.
RUN_ROW_SCHEMA = {
    "run_id": "manifest run identity, campaign/sim/point",
    "sim_id": "simulation identity of the case",
    "data_origin": "raw off the run or reduced by post-processing (PFS-2014.05)",
    "reduction": "none on a steady point, time_average on an unsteady one",
    "alpha": "sweep axis of this fixture, deg (see the docstring below)",
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


def test_run_table_exposes_the_documented_column_schema():
    """NFR-19: the run row's full column set is the public contract.

    `alpha` is the sweep-axis column of this fixture; a case swept on another
    axis carries that axis's name instead, which is why the sweep axis sits
    between the identity block and the version block rather than at the end.

    The LABELS are the promise and their order is not (NFR-19 says so, and
    the author restated it on 2026-08-17), so the comparison is on the set
    with a length check beside it: the set alone cannot see a label emitted
    twice.
    """
    loads = parse_loads(read_fixture("loads_steady_26.120.txt"))
    record = make_record(
        iterations=312, residual=3.2e-6, wall_time_s=41.5, outputs=["raw/loads.txt"]
    )
    columns = list(run_table(record, loads=loads).columns)
    assert set(columns) == set(RUN_ROW_SCHEMA), (
        "the run-row column schema changed. SRS NFR-19 makes these names a "
        "public contract: announce the change in the changelog's API surface "
        "delta and update this literal in the same commit."
    )
    assert len(columns) == len(RUN_ROW_SCHEMA), (
        f"the run row repeats a column label ({columns}); the set comparison "
        "above cannot see a duplicate"
    )


def test_run_table_joins_identity_conditions_and_total_coefficients():
    loads = parse_loads(read_fixture("loads_steady_26.120.txt"))
    record = make_record(
        iterations=312, residual=3.2e-6, wall_time_s=41.5, outputs=["raw/loads.txt"]
    )
    frame = run_table(record, loads=loads)
    assert frame.shape[0] == 1
    row = frame.iloc[0]
    assert list(frame.columns[:5]) == [
        "run_id",
        "sim_id",
        "data_origin",
        "reduction",
        "alpha",
    ]
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


# --- PFS-2014.05: every row says what produced its numbers ----------------
#
# Her requirement of 2026-08-16, and the sweep is the case she named. One
# table, two provenances per row: a steady point's coefficients are a direct
# integration, an unsteady point's are the solver's own time average, and
# both are printed under CL and CDi. A reader who cannot tell them apart
# compares them and reads a method difference as physics.
#
# THE VOCABULARY IS THE AUTHOR'S CALL and these tests pin the lane default
# rather than her ruling, which is still owed: two origin tokens, three
# reduction tokens, a failed row saying `unknown` rather than `none`, and an
# unsteady solver export counting as `raw` because the solver did the
# averaging and the reduction token is what names it.


@pytest.mark.requirement("NFR-19")
def test_a_mixed_sweep_traces_every_row_without_another_file(tmp_path):
    """The falsifying test of PFS-2014.05, read back off the written file.

    Asserted against the csv rather than against the DataFrame, because
    the acceptance is about a FILE: the identifier has to survive being
    written and read back, which is exactly what an empty cell would not
    do (it returns as NaN).

    The fixture campaign is already mixed: a converged steady point, an
    iteration-limited unsteady point, and a failed point with no loads
    export at all.
    """
    frame = sweep_table(build_sweep_workspace(tmp_path))
    written = write_table(frame, tmp_path / "sweep.csv")
    back = pd.read_csv(written)
    traced = list(zip(back["data_origin"], back["reduction"], strict=True))
    assert traced == [("raw", "none"), ("raw", "time_average"), ("raw", "unknown")], (
        "a mixed sweep must let every row be traced to raw or reduced with no "
        f"other file open; the written csv says {traced}"
    )
    assert back["status"].tolist() == [
        "CONVERGED",
        "COMPLETED_MAX_ITER",
        "FAILED_EXECUTION",
    ]
    # And the identifier is genuinely PER ROW here: a header field could not
    # have carried these three answers.
    assert back["reduction"].nunique() == 3


def test_every_written_table_says_what_produced_its_numbers(tmp_path):
    """The four single-result tables, not only the sweep.

    The acceptance is "every file the package writes", and a constant
    column on a single-provenance file is what makes the promise total:
    "this one happens to be uniform, so it needs no column" is how a file
    ends up needing a second file.
    """
    cases = {
        "loads_steady": (parse_loads(read_fixture("loads_steady_26.120.txt")), "none"),
        "loads_unsteady": (
            parse_loads(read_fixture("loads_unsteady_26.120.txt")),
            "time_average",
        ),
        "probes": (parse_probe_points(read_fixture("probe_points_26.120.txt")), "none"),
        "residuals": (parse_residual_history(read_fixture("log_residuals_26.120.txt")), "none"),
        # The committed sectional fixture prints `Solver mode: Unsteady`,
        # so its reduction is read off the file rather than assumed: this
        # is the one non-sweep table whose token is not a constant of the
        # kind of file it is.
        "sectional": (
            parse_sectional_loads(read_fixture("fsi/FS_SurfaceSection_Loads_call0002.txt")),
            "time_average",
        ),
    }
    for name, (result, expected_reduction) in cases.items():
        back = pd.read_csv(to_csv(result, tmp_path / f"{name}.csv"))
        assert set(back["data_origin"]) == {"raw"}, f"{name} lost its data_origin"
        assert set(back["reduction"]) == {expected_reduction}, (
            f"{name} says reduction {set(back['reduction'])}, expected {expected_reduction!r}"
        )


def test_write_table_refuses_a_table_that_cannot_say_what_it_is(tmp_path):
    """Absence is refused; MULTIPLICITY is not, and that is the whole design.

    An earlier plan refused a frame holding more than one distinct
    (data_origin, reduction) pair, which would have refused the mixed
    sweep this item exists to make writable.
    """
    mixed = pd.DataFrame(
        {
            "CL": [0.4, 0.5],
            "data_origin": ["raw", "raw"],
            "reduction": ["none", "time_average"],
        }
    )
    assert write_table(mixed, tmp_path / "mixed.csv").is_file()

    for frame, expected in (
        (pd.DataFrame({"CL": [0.4]}), "no data_origin"),
        (pd.DataFrame({"CL": [0.4], "data_origin": ["raw"]}), "no reduction"),
        (
            pd.DataFrame({"CL": [0.4], "data_origin": ["raw"], "reduction": [""]}),
            "does not publish",
        ),
        (
            pd.DataFrame({"CL": [0.4], "data_origin": ["RAW"], "reduction": ["none"]}),
            "does not publish",
        ),
        (
            pd.DataFrame({"CL": [0.4], "data_origin": ["reduced"], "reduction": ["none"]}),
            "name no reduction",
        ),
    ):
        with pytest.raises(MalformedOutputError, match=expected):
            write_table(frame, tmp_path / "refused.csv")


def test_write_table_can_be_told_not_to_replace_a_file(tmp_path):
    """The default stays what this module always did; the refusal is opt-in."""
    frame = pd.DataFrame({"CL": [0.4], "data_origin": ["raw"], "reduction": ["none"]})
    target = tmp_path / "polar.csv"
    write_table(frame, target)
    assert write_table(frame, target).is_file()  # overwrite=True by default
    with pytest.raises(MalformedOutputError, match="already exists"):
        write_table(frame, target, overwrite=False)


def test_the_published_codes_are_integers_and_append_only():
    """The numeric-only form carries codes, and a code never moves.

    Pinned as literals rather than read off the mapping: a test that
    reads the value it is checking cannot fail, and what this guards is
    precisely that a published integer keeps its meaning for a file
    written before the change.
    """
    assert DATA_ORIGIN_CODES == {"raw": 0, "reduced": 1}
    assert REDUCTION_CODES == {"none": 0, "time_average": 1, "unknown": 2}
    assert (origin_code("raw"), origin_code("reduced")) == (0, 1)
    assert reduction_code("time_average") == 1
    for call, token in ((origin_code, "time_average"), (reduction_code, "raw")):
        with pytest.raises(MalformedOutputError, match="does not publish|is not a"):
            call(token)


# --- PFS-2014.03: a sweep that yielded nothing still leaves a table -------


def test_sweep_table_can_return_the_rows_it_has_when_no_run_yielded_loads(tmp_path):
    """The half of PFS-2014.03 that lives in this layer.

    `run_campaign` is to write the sweep csv before it raises
    `CampaignErrors`, so a campaign with failed points still leaves a
    file a colleague can open. That is impossible while `sweep_table`
    raises on the same condition: catching the refusal leaves nothing to
    write, since the rows are assembled inside the call.

    The empty-manifest refusal is deliberately NOT relaxed by the
    keyword: `run_campaign` appends one record per executed point, so an
    empty manifest cannot reach this call and a table with no rows says
    nothing about anything.
    """
    workspace = build_sweep_workspace(tmp_path)
    with pytest.raises(LoadsNotFoundError):
        sweep_table(workspace, loads_file="polar.txt")

    with pytest.warns(UserWarning, match="successful runs yielded a coefficient"):
        frame = sweep_table(workspace, loads_file="polar.txt", require_loads=False)
    assert frame.shape[0] == 3, "the rows already assembled must come back"
    assert "CL" not in frame.columns, "no run yielded coefficients, so there is no CL"
    assert frame["run_id"].tolist() == [
        "camp/sim_9001/a+02.0",
        "camp/sim_9001/a+00.0",
        "camp/sim_9001/a+04.0",
    ]
    # And it is still a writable table: the provenance columns are what
    # `run_campaign` will hand to `write_table`.
    assert set(frame["reduction"]) == {"unknown"}
    assert write_table(frame, tmp_path / "sweep.csv").is_file()

    with pytest.raises(MalformedOutputError, match="no manifest records"):
        sweep_table(CampaignWorkspace(tmp_path / "empty"), require_loads=False)


# --- PFS-2014.02: a parser is only half of a conversion -------------------
#
# The acceptance's first sentence asks for a parser AND a tabular
# conversion for every export in the DEFAULT set. `EXPORT_CONVERSIONS`
# records the parser and nothing recorded the other half, so
# `parse_unsteady_plots` shipped in wave one of this lane with no
# `to_table` branch behind it: FR-32 ("every parser result converts to a
# tidy table and to csv") was false for that export while reading
# implemented, and the classification called it `parsed`.
#
# The walk below is over the classification rather than over a list
# written here, so a fifth `parsed` verdict fails until it has both
# halves. What is written here is the FIXTURE per export, and it is
# required rather than optional: an export whose fixture is missing would
# otherwise be skipped, and a walk that skips is a walk that reports green
# over the thing it was built to measure.

#: One committed export per ``parsed`` verdict of
#: :data:`~pyflightstream.results.EXPORT_CONVERSIONS`.
PARSED_EXPORT_FIXTURES = {
    "EXPORT_SOLVER_ANALYSIS_SPREADSHEET": "loads_steady_26.120.txt",
    "EXPORT_PROBE_POINTS": "probe_points_26.120.txt",
    "UNSTEADY_SOLVER_EXPORT_PLOTS": "unsteady_plots_26.120.txt",
    "EXPORT_SURFACE_SECTIONAL_LOADS": "fsi/FS_SurfaceSection_Loads_call0002.txt",
}


@pytest.mark.requirement("FR-32")
def test_every_parsed_export_converts_to_a_tidy_table(tmp_path):
    """Every export classified ``parsed`` reads AND tabulates (PFS-2014.02).

    Both halves in one walk, because they fail independently: a parser
    can land without a :func:`to_table` branch (which is exactly what
    happened to the unsteady plot export) and a dispatch branch can rot
    without the parser noticing.

    The population is asserted before the verdict, twice over: the
    classification must name at least the four exports it named when
    this guard was written, and every one of them must have been walked.
    A walk that resolves nothing satisfies "no failures" perfectly.
    """
    import importlib

    from pyflightstream.results import EXPORT_CONVERSIONS, EXPORT_PARSED

    parsed = sorted(
        command for command, entry in EXPORT_CONVERSIONS.items() if entry.verdict == EXPORT_PARSED
    )
    assert len(parsed) >= 4, (
        f"the classification names {len(parsed)} parsed export(s); four had parsers "
        "when this guard was written and a verdict is only ever added"
    )
    assert set(parsed) <= set(PARSED_EXPORT_FIXTURES), (
        "a parsed export has no committed fixture here, so this walk would skip it: "
        f"{sorted(set(parsed) - set(PARSED_EXPORT_FIXTURES))}. Commit one export of "
        "that command and name it, or the guard measures the exports it already knew"
    )

    walked: list[str] = []
    failures: list[str] = []
    for command in parsed:
        entry = EXPORT_CONVERSIONS[command]
        assert entry.parser, f"{command} is classified parsed and names no parser"
        module_name, _, attribute = entry.parser.rpartition(".")
        parser = getattr(importlib.import_module(module_name), attribute)
        report = parser(read_fixture(PARSED_EXPORT_FIXTURES[command]))
        walked.append(command)
        try:
            frame = to_table(report)
        except Exception as error:  # noqa: BLE001 - the verdict is the message
            failures.append(f"{command}: to_table raised {type(error).__name__}: {error}")
            continue
        if frame.empty:
            failures.append(f"{command}: to_table returned an empty table")
            continue
        missing = [name for name in PROVENANCE_COLUMNS if name not in frame.columns]
        if missing:
            failures.append(f"{command}: the table carries no {missing} column")
            continue
        write_table(frame, tmp_path / f"{command.lower()}.csv")

    assert walked == parsed, (
        f"the walk covered {walked} of {parsed}; a parsed export that is never "
        "converted here is a default-set export nobody measured"
    )
    assert not failures, (
        "an export classified `parsed` cannot be turned into a tidy table, so it has "
        "a parser and no conversion and FR-32 is false for it:\n  " + "\n  ".join(failures)
    )


def test_the_unsteady_plot_export_tabulates_under_its_printed_labels():
    """One row per time step, one column per plot, plus the provenance.

    THE COLUMN LABELS ARE THE SOLVER'S and the order is data rather than
    a contract (her convention of 2026-08-17): the set of plots is
    whatever the run defined, so this pins the label SET and the row
    count, never a position. What this package promises about the frame
    is the two provenance columns and that nothing else is added.

    ``reduction`` is ``none`` and not ``time_average``, and the
    difference is physical rather than bookkeeping: this export is the
    per-time-step history itself, so no window was averaged to produce a
    row. A time average OF this history would be ``time_average``.
    """
    from pyflightstream.results import parse_unsteady_plots

    report = parse_unsteady_plots(read_fixture("unsteady_plots_26.120.txt"))
    frame = to_table(report)
    assert set(frame.columns) == set(report.columns) | set(PROVENANCE_COLUMNS)
    assert len(frame.columns) == len(report.columns) + len(PROVENANCE_COLUMNS), (
        "a plot column collided with a provenance column and one of them was lost"
    )
    assert len(frame) == report.steps == 5
    assert frame["CL"].iloc[0] == pytest.approx(2.35e-3)
    assert frame["Time (sec)"].tolist() == pytest.approx([0.0, 0.004, 0.008, 0.012, 0.016])
    assert set(frame["data_origin"]) == {"raw"}
    assert set(frame["reduction"]) == {"none"}


def test_a_plot_named_like_a_provenance_column_is_refused_not_overwritten():
    """The one way this export can silently lose a column of numbers.

    Plot names are the user's own, so nothing stops a run defining a plot
    called ``reduction``. Stamping the provenance would then overwrite a
    column of physical numbers with a constant token, and the frame would
    still write, still carry both provenance columns and still look
    right. Refused by name instead.
    """
    from pyflightstream.results import UnsteadyPlotsReport

    report = UnsteadyPlotsReport(
        columns=("Time (sec)", "reduction"),
        values=np.array([[0.0, 1.0], [0.004, 2.0]]),
    )
    with pytest.raises(MalformedOutputError, match="reduction"):
        to_table(report)


# --- OPS-2009.01.08: the refusal a caller can catch by class -------------


@pytest.mark.requirement("FR-39")
def test_to_table_refuses_an_unsupported_result_through_the_catalog():
    """`except TypeError` still catches it and `except PyflightstreamError` now does.

    Written against the CATALOG rather than against the new class name,
    so it fails on the assertion and not on an import: on the base
    `to_table` raises the bare builtin, which is a `TypeError` that is
    not a `PyflightstreamError` and whose name is in no catalog.

    Both arms of the refusal are exercised, because they are two raises
    in one definition and the FR-39 ratchet counts them separately.
    """
    from pyflightstream import exceptions
    from pyflightstream._errors import PyflightstreamError

    checked = 0
    for result in (object(), pd.DataFrame({"CL": [0.4]})):
        try:
            to_table(result)
        except TypeError as error:
            caught: TypeError = error
        else:  # pragma: no cover - a silent success would be a worse defect
            pytest.fail(f"to_table({type(result).__name__}) returned instead of refusing")
        checked += 1
        assert isinstance(caught, PyflightstreamError), (
            f"to_table raised a bare {type(caught).__name__} for "
            f"{type(result).__name__}, so `except PyflightstreamError` misses it and "
            "FR-39's first clause is false here. Raise a catalogued class keeping "
            "TypeError as its second base"
        )
        assert type(caught).__name__ in exceptions.__all__, (
            f"{type(caught).__name__} is not in pyflightstream.exceptions.__all__, so "
            "a caller cannot import the class it is told to catch"
        )
    assert checked == 2, f"only {checked} refusal arm(s) were exercised, expected 2"
