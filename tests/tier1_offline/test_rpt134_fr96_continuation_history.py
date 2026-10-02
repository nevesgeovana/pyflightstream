"""FR-96 R6 on the plots exports a continuation really wrote on 26.124 (RPT-134).

The fixtures are four plots exports recorded on FlightStream 26.124 (build 8172026), far
field 5, 30_BLADE, 12 steps a revolution: the point's (one revolution, CONVERGED, archived
by the continuation), the continuation 0.34.0 emits ({ADDITIONAL_REVS=1}), the same script
without its INITIALIZE_SOLVER block (the reopened state kept), and the control's (two
revolutions straight). The workspace is the post tests' own unsteady workspace with these
exports in place of its synthetic ones, so the join is the package's, read on real files.

What RPT-134 measured: when the reopened state is kept, the solver's plots export of the
continuation holds the WHOLE march, 24 rows numbered 1 to 24, its first 12 the point's rows
exactly. The continuation 0.34.0 emits re-initialises the reopened solution and re-marches
from step 1, so its export is the point's again; the fix is not in 0.34.0.
"""

from __future__ import annotations

import json
import re
import shutil
import warnings
from pathlib import Path

import numpy as np

from pyflightstream.cases.workflows import (
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    build_script,
)
from pyflightstream.post.products import plots_table_series, write_campaign_products
from pyflightstream.results.loads import parse_unsteady_plots
from pyflightstream.script import Script
from tests.tier1_offline.test_post_products import _unsteady_workspace
from tests.tier1_offline.test_restart_continuation import SAVED, _continuing_case

FIX = Path(__file__).resolve().parent / "fixtures" / "rpt134"
#: The build every recorded export names in its header, and the exports recorded.
BUILD = "8172026"
EXPORTS = ("continuation_plots", "control_plots", "point_plots", "resume_plots")
SOFTWARE = re.compile(r"Software : Flightstream version 26\.1, build #(\d+)")
STAMP = "20261002-120000"
PER_REV = 12
PLAN = {
    "window_stated": True,
    "time_iterations": PER_REV,
    "steps_per_revolution": float(PER_REV),
    "blades": None,
    "time_average": {"windows": [[1, PER_REV]], "window_from": "LAST_REVS_AVG = 1 at run time"},
}
#: The words the post log uses for the shape RPT-134 measured, for both continuation exports:
#: each starts at step 1 and repeats the point's rows there, so it restates the march.
SHAPE_SAID: str | None = "restating the march from step 1"
#: The worst relative difference RPT-134 measured between the resumed continuation's steps
#: 13 to 24 and the control's straight march (4.4e-5, 4 of 24 rows, the last printed digit).
CONTROL_BAND = 5e-5


def _rows(name: str) -> tuple[tuple[str, ...], np.ndarray]:
    report = parse_unsteady_plots((FIX / name).read_text(encoding="latin-1"))
    return tuple(report.columns), np.asarray(report.values, dtype=float)


def _steps(name: str) -> list[int]:
    columns, values = _rows(name)
    return [int(v) for v in values[:, columns.index("Time-step")]]


def _workspace(tmp_path, *, continuation: str | None):
    workspace = _unsteady_workspace(tmp_path, reductions=PLAN)
    outputs = workspace.sim_dir("7001") / "outputs"
    if continuation is None:
        shutil.copyfile(FIX / "point_plots.txt", outputs / "AL-020_plots.txt")
        return workspace
    archive = outputs / "archive" / STAMP
    archive.mkdir(parents=True)
    shutil.move(str(outputs / "AL-020_plots.txt"), archive / "AL-020_plots.txt")
    shutil.copyfile(FIX / "point_plots.txt", archive / "AL-020_plots.txt")
    shutil.copyfile(FIX / continuation, outputs / "AL-020_plots.txt")
    (original,) = workspace.read_manifest()
    workspace.append_record(
        original.model_copy(
            update={
                "run_id": f"camp/sim_7001/r{STAMP}/AL-020",
                "continues": original.run_id,
                "restart": {"form": "ADDITIONAL_REVS", "value": 1.0},
            }
        )
    )
    return workspace


def _posted(workspace):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace, overwrite=True)
    out = workspace.root / "post" / "products"
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    _, series = plots_table_series(out / "probes" / "AL-020_plots.csv")
    said = [str(w.message) for w in caught if "product=plots" in str(w.message)]
    return manifest, series, said


def test_every_recorded_export_names_build_8172026_in_its_header_fr_96():
    """The fixtures are exports of 26.124 build 8172026, read from each file's own header."""
    # Verifies FR-96.
    assert sorted(p.stem for p in FIX.glob("*.txt")) == sorted(EXPORTS)
    builds = {
        name: SOFTWARE.findall((FIX / f"{name}.txt").read_text(encoding="latin-1"))
        for name in EXPORTS
    }
    assert all(found == [BUILD] for found in builds.values()), builds


def test_the_resumed_export_holds_the_whole_march_numbered_1_to_24_fr_96():
    """RPT-134's answer: the whole march, numbered on from 1; its first 12 rows the point's own."""
    # Verifies FR-96.
    assert _steps("resume_plots.txt") == list(range(1, 2 * PER_REV + 1))
    columns, resumed = _rows("resume_plots.txt")
    point_columns, point = _rows("point_plots.txt")
    assert columns == point_columns
    assert np.array_equal(resumed[:PER_REV], point), "the first revolution is not the point's"
    assert not np.array_equal(resumed[PER_REV:], resumed[:PER_REV]), (
        "the second revolution re-marched the first"
    )


def test_the_resumed_march_is_the_unbroken_march_within_its_printed_digits_fr_96():
    """Context, not the requirement: steps 13 to 24 against the control's straight 24 steps."""
    # Verifies FR-96.
    _, resumed = _rows("resume_plots.txt")
    _, straight = _rows("control_plots.txt")
    assert resumed.shape == straight.shape
    scale = np.maximum(np.abs(straight), 1e-30)
    worst = float(np.max(np.abs(resumed - straight) / scale))
    assert 0.0 < worst < CONTROL_BAND, worst
    assert np.array_equal(resumed[:PER_REV], straight[:PER_REV])


def test_the_resumed_continuation_joins_into_every_step_once_fr_96(tmp_path):
    """The real resumed export: steps 1 to 24 once each, the window the march's last revolution."""
    # Verifies FR-96.
    manifest, series, said = _posted(_workspace(tmp_path, continuation="resume_plots.txt"))
    assert list(series.steps) == list(range(1, 2 * PER_REV + 1)), list(series.steps)
    entry = manifest["products"]["probes/AL-020_time_average.csv"]
    assert entry["windows"] == [[PER_REV + 1, 2 * PER_REV]], entry
    assert len(said) == 1 and SHAPE_SAID in said[0], said


def test_the_joined_history_ends_where_the_unbroken_march_ends_fr_96(tmp_path):
    """Context, not the requirement: as many joined steps as the control's straight march."""
    # Verifies FR-96.
    _, series, _ = _posted(_workspace(tmp_path, continuation="resume_plots.txt"))
    assert len(series.steps) == len(_steps("control_plots.txt")) == 2 * PER_REV


def test_the_0340_continuation_re_marched_and_posts_one_revolution_fr_96(tmp_path):
    """The continuation 0.34.0 emits: its export IS the point's, and the post says so."""
    # Verifies FR-96.
    _, continued = _rows("continuation_plots.txt")
    _, point = _rows("point_plots.txt")
    assert np.array_equal(continued, point), "the 0.34.0 continuation did not re-march the point"
    manifest, series, said = _posted(_workspace(tmp_path, continuation="continuation_plots.txt"))
    assert list(series.steps) == list(range(1, PER_REV + 1)), list(series.steps)
    assert manifest["products"]["probes/AL-020_time_average.csv"]["windows"] == [[1, PER_REV]]
    assert len(said) == 1 and f"{SHAPE_SAID} to step {PER_REV}" in said[0], said


def test_the_recorded_point_alone_posts_its_own_revolution_control_fr_96(tmp_path):
    """The control: the point's own export, continuing nothing, posts steps 1 to 12 as before."""
    # Verifies FR-96.
    manifest, series, said = _posted(_workspace(tmp_path, continuation=None))
    assert list(series.steps) == list(range(1, PER_REV + 1)) and said == []
    assert manifest["products"]["probes/AL-020_time_average.csv"]["windows"] == [[1, PER_REV]]


def test_the_package_still_initialises_the_reopened_state_as_rpt_134_measured_fr_96():
    """The 0.34.0 continuation emits INITIALIZE_SOLVER between OPEN and START_SOLVER.

    On 26.124 that block clears the reopened solution and the march restarts at step 1
    (RPT-134). When a later release stops emitting it on a continuation, this test moves
    with it and RPT-134's resume arm is its evidence; until then it pins what was measured.
    """
    # Verifies FR-96.
    case = _continuing_case(
        "{ADDITIONAL_ITERS=12}",
        **{RESTART_FROM_VARIABLE: SAVED, RESTART_ITERATIONS_VARIABLE: "12"},
    )
    script = Script("26.124")
    build_script(case, script)
    lines = script.render().splitlines()
    assert lines.index("OPEN") < lines.index("INITIALIZE_SOLVER") < lines.index("START_SOLVER")
