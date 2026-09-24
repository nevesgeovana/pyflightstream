"""Tier 3: the unsteady actions of PFS-2031.18, run on 26.123 (row 6002, RPT-045).

Row 6002 of ``matriz_actions.fs`` is the ``unsteady`` run type on the tour's
wing with ``EXPORT_UNSTEADY_AFTER_ITER: 4`` over ``TIME_ITERATIONS: 8``. The
run layer wrote the counter program and the empty export script under the
``actions/`` folder of the point's working directory, the run type registered
the COMMAND_LINE action running the program and the SCRIPT action pointing at
the file, and the solver ran both after every time step. What the run left is
what design/67 said it would, and this module reads it back through the record.

WHERE: since 0.27.0 a point run on this machine runs in its own
``sims/sim_6002/datapoints/DP-<point>/``, and its action files and per-step
exports are written there (docs/migrating-to-0.27.0.md section 16, 06a51049).
WHAT: since 0.25.0 an unsteady row samples its probes through fluid plots and
exports no probe points, per step or at the end (F01,
docs/migrating-to-0.25.0.md section 2), so no ``_probes`` file is stamped.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.tier3_licensed.conftest import TERMINAL_OK, line, requested_version

pytestmark = pytest.mark.needs_flightstream

MATRIX = "matriz_actions"
THRESHOLD = 4
STEPS = 8
#: The export kinds the program writes after the threshold, one file per
#: step each, stamped by the solver with the iteration. No ``_probes``: an
#: unsteady row exports no probe points since 0.25.0 (F01).
KINDS = ("", "_cp", "_sloads")


def _record(runs):
    return runs.one(MATRIX, "6002", alpha=2.0)


def _point_dir(runs, workspace):
    """The folder the point ran in: its own datapoint folder since 0.27.0 (06a51049)."""
    return workspace.sim_dir("6002") / "datapoints" / f"DP-{_record(runs).point_name}"


def test_the_row_ran_terminal_and_the_record_keeps_the_count(runs, workspace):
    record = _record(runs)
    assert record.status in TERMINAL_OK, (record.status, record.error)
    assert record.fs_version_requested == requested_version("26.123")
    # The record's cwd names the point's own folder (0.27.0, migration section 16).
    assert record.cwd and Path(record.cwd).parts[-2:] == _point_dir(runs, workspace).parts[-2:]
    assert record.action_program == "actions/pfs_unsteady_actions.py"
    assert record.action_script == "actions/pfs_unsteady_exports.txt"
    assert record.action_count == STEPS
    assert set(record.inputs_sha256) >= {record.action_program, record.action_script}
    # The script file was EMPTY when the record hashed it, before the solver
    # started: the hash of zero bytes.
    assert record.inputs_sha256[record.action_script].startswith("e3b0c44298fc1c149afb")


def test_the_two_actions_were_registered_in_order_before_the_solver(runs):
    script = runs.script(_record(runs))
    texts = script.splitlines()
    first = texts.index(line(script, "SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE"))
    second = texts.index(line(script, "SET_NEW_UNSTEADY_SOLVER_ACTION SCRIPT"))
    init = texts.index("INITIALIZE_SOLVER")
    assert first < second < init
    assert texts[first + 1].endswith('"actions/pfs_unsteady_actions.py"')
    assert texts[second + 1] == "actions/pfs_unsteady_exports.txt"


def test_the_counter_reached_the_step_count_and_the_solver_ran_it_every_step(runs, workspace):
    sim = workspace.sim_dir("6002")
    folder = _point_dir(runs, workspace)
    count = json.loads(
        (folder / "actions" / "pfs_unsteady_actions.count").read_text(encoding="utf-8")
    )
    assert count["count"] == STEPS and count["exporting"] is True, count
    record = _record(runs)
    log = next(o for o in record.outputs if o.endswith("_log.txt"))
    text = (sim / log).read_bytes().decode("utf-8", "replace")
    assert text.count("Executed runtime command:") == STEPS
    assert text.count("Running script file: actions/pfs_unsteady_exports.txt") == STEPS


def test_the_exports_begin_at_the_threshold_and_are_stamped_by_the_solver(runs, workspace):
    folder = _point_dir(runs, workspace)
    stem = _record(runs).script_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    stamped = {}
    for path in folder.iterdir():
        found = re.fullmatch(
            rf"{re.escape(stem)}(_cp|_sloads|_probes)?_iteration=(\d+)\.(txt|dat)", path.name
        )
        if found:
            stamped.setdefault(int(found.group(2)), set()).add(
                (found.group(1) or "", found.group(3))
            )
    assert sorted(stamped) == list(range(THRESHOLD, STEPS + 1)), sorted(stamped)
    for iteration, kinds in stamped.items():
        assert kinds == {
            ("", "txt"),
            ("", "dat"),
            ("_cp", "txt"),
            ("_sloads", "txt"),
        }, (
            iteration,
            kinds,
        )
    assert not any("_probes" in path.name for path in folder.iterdir()), "F01 of 0.25.0"


def test_the_rewritten_script_carries_the_exports_after_the_threshold(runs, workspace):
    text = (_point_dir(runs, workspace) / "actions" / "pfs_unsteady_exports.txt").read_text(
        encoding="utf-8"
    )
    assert text.startswith("UPDATE_ALL_SURFACE_SECTIONS")
    for command in (
        "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
        "EXPORT_SOLVER_ANALYSIS_TECPLOT",
        "EXPORT_ALL_SURFACE_SECTIONS",
        "EXPORT_SURFACE_SECTIONAL_LOADS",
    ):
        assert line(text, command) == command
    # F01 of 0.25.0: an unsteady row neither updates nor exports probe points.
    for command in ("UPDATE_PROBE_POINTS", "EXPORT_PROBE_POINTS"):
        assert command not in text, command


def test_the_stamped_files_of_the_window_table_as_a_series(runs, workspace):
    """PFS-2031.18.01 on the solver's own files: the products stage tables the
    stamped loads and sectional loads of steps 4 to 8 under series/, the step's
    time from the record's clock, the Tecplot and cp files listed by path. The
    probes series is a named skip: the row stamps no probes file (F01 of 0.25.0),
    and a kind with no stamped file is not written (0.24.0)."""
    import csv

    from pyflightstream.post.products import write_campaign_products

    record = _record(runs)
    if not record.export_window:
        pytest.skip(
            "row 6002 was recorded before the run record carried its export window "
            "(0.13.0), so the series has no window to read; rerun the row on the "
            "licensed machine and this test measures the series on the solver's files"
        )
    stem = record.script_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    write_campaign_products(workspace, matrix_stem=MATRIX, overwrite=True)
    series = runs.products(MATRIX) / "series"
    tables = {}
    for kind in ("loads", "sections"):
        path = series / f"{stem}_{kind}_series.csv"
        assert path.is_file(), (
            sorted(p.name for p in series.iterdir()) if series.is_dir() else series
        )
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            tables[kind] = (tuple(reader.fieldnames or ()), list(reader))
    columns, rows = tables["loads"]
    # POL leads every table the post writes since 0.27.0 (G16, migration section 17).
    assert columns[:4] == ("POL", "STEP", "time_s", "azimuth_deg") and "Total_CL" in columns
    assert all(r["POL"] == "6002" for r in rows)
    assert [int(r["STEP"]) for r in rows] == list(range(THRESHOLD, STEPS + 1))
    delta = record.export_window["delta_time_s"]
    assert [float(r["time_s"]) for r in rows] == pytest.approx(
        [s * delta for s in range(THRESHOLD, STEPS + 1)]
    )
    # A cell that does not apply reads NA since 0.23.0, where it was blank.
    assert all(r["azimuth_deg"] == "NA" for r in rows), "row 6002 turns nothing"
    # The wing row defines no section: the sections table is its header.
    assert tables["sections"][1] == []
    assert tables["sections"][0][:3] == ("POL", "STEP", "time_s")
    probes = f"series/{stem}_probes_series.csv"
    assert not (runs.products(MATRIX) / probes).exists()
    index = json.loads((runs.products(MATRIX) / "products.json").read_text(encoding="utf-8"))
    assert probes in index["skipped"], sorted(index["skipped"])
    entry = index["products"][f"series/{stem}_loads_series.csv"]
    assert entry["steps"] == [THRESHOLD, STEPS] and entry["steps_tabled"] == list(
        range(THRESHOLD, STEPS + 1)
    )
    assert len(entry["sections_files"]) == len(entry["tecplot_files"]) == STEPS - THRESHOLD + 1
