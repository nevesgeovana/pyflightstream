"""One rotor campaign, posted once, states ONE clock in every product that carries it.

THIS IS THE SECOND HALF OF `reports/RPT-056`, which stayed registered after the first half
closed. `J_CLOCK` and `RPM_CLOCK` say what the clock rotor ran at: the speed the record kept and
the advance ratio that speed implies against the point's own free stream and the rotor's
diameter. Unit cases prove `clock_rotor_facts` and `point_condition`; nothing committed read the
two columns OUT OF the products and compared them.

THE DEFECT THIS GUARDS. The rotor table and the per-step series once read `NA` in both columns
while the polar beside them carried values: each family builds its condition itself, and a
caller that forgets `clock=` writes a correct-looking file with the columns empty. The QA lens
measured on 2026-09-22 that deleting `clock=` from both repaired callers left 35 targeted tests
green, so the drift could return unnoticed.

THE CAMPAIGN is the rotor variant of the freeze fixture: a reference declaring rotor `PUSHER`
with `diameter_m = 2.0`, a record whose plan turned it at 2200 rev/min, a matrix row naming it
as `CLOCK_MOTION`, and three stamped loads exports so the per-step series exists beside the
polar and the rotor table.

THE NUMBERS. The export states a free stream of 68.058 m/s, so
`J = V / (n D) = 68.058 / (2200 / 60 * 2.0) = 0.92806` at the products' five decimals.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from pyflightstream.post.products import NOT_APPLICABLE, write_campaign_products
from tests.tier1_offline.test_b01_frozen_solve import _post_workspace
from tests.tier1_offline.test_goal028_series import WINDOW
from tests.tier1_offline.test_post_products import LOADS

#: The three families RPT-056 names, as the products stage writes them for this campaign.
POLAR = "polars/P7001_AL-020_uns_avg.csv"
ROTOR_TABLE = "polars/P7001-PUSHER_rotor.csv"
SERIES = "series/AL-020_loads_series.csv"

#: What the clock rotor ran at, as every product prints it.
J_CLOCK = "0.92806"
RPM_CLOCK = "2200.00000"


def _posted_rotor_campaign(tmp_path, clock_motion: str = "PUSHER") -> Path:
    """Post one rotor campaign once and return its products folder.

    ``clock_motion`` is how the matrix row spells the clock rotor; the
    reference declares it as ``PUSHER``.
    """
    workspace = _post_workspace(tmp_path, 2411, (60, 61), rotor=True)
    matrix = workspace.root / "products.fs"
    text = matrix.read_text(encoding="utf-8")
    # The rewrite must land, or the second test would post the first one's campaign.
    assert text.count("CLOCK_MOTION: PUSHER") == 1, "the fixture row no longer names its clock"
    matrix.write_text(
        text.replace("CLOCK_MOTION: PUSHER", f"CLOCK_MOTION: {clock_motion}"), encoding="utf-8"
    )
    # THE PER-STEP SERIES needs the stamped exports a submitted point leaves in its
    # datapoint folder, and a record whose export window names their steps.
    folder = workspace.sim_dir("7001") / "datapoints" / "DP-AL-020"
    for step in range(int(WINDOW["first_step"]), int(WINDOW["time_iterations"]) + 1):
        (folder / f"AL-020_iteration={step}.txt").write_text(
            LOADS.replace("Steady", "Unsteady"), encoding="utf-8"
        )
    runs = workspace.root / "runs.json"
    recorded = json.loads(runs.read_text(encoding="utf-8"))
    recorded[0]["export_window"] = dict(WINDOW)
    runs.write_text(json.dumps(recorded, indent=1), encoding="utf-8")
    write_campaign_products(workspace, matrix_stem="products")
    return workspace.root / "post" / "products"


def _clocks(products: Path) -> dict[str, set[tuple[str, str]]]:
    """Return what every CSV carrying the clock columns states in them, by file.

    The header is the first row, or the second where the first is a title, as
    the rotor table's is. EVERY DATA ROW is read, not only the first: the
    series has one row per step, and a step that lost its clock is the same
    drift as a family that did.
    """
    found: dict[str, set[tuple[str, str]]] = {}
    for path in sorted(products.rglob("*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle))
        at = next((i for i, row in enumerate(rows[:2]) if "J_CLOCK" in row), None)
        if at is None:
            continue
        header = rows[at]
        j, rpm = header.index("J_CLOCK"), header.index("RPM_CLOCK")
        name = path.relative_to(products).as_posix()
        found[name] = {(row[j], row[rpm]) for row in rows[at + 1 :]}
    return found


def _assert_one_clock(products: Path) -> None:
    """The three named families are present, and every product states the polar's clock."""
    clocks = _clocks(products)
    for name in (POLAR, ROTOR_TABLE, SERIES):
        assert name in clocks, (name, sorted(clocks))
    (stated,) = clocks[POLAR]
    assert NOT_APPLICABLE not in stated, f"the polar states no clock: {stated}"
    assert stated == (J_CLOCK, RPM_CLOCK), stated
    disagreeing = {name: values for name, values in clocks.items() if values != {stated}}
    assert not disagreeing, f"the polar states {stated}; these state otherwise: {disagreeing}"


def test_the_polar_the_rotor_table_and_the_series_state_one_clock(tmp_path):
    """RPT-056: the polar, the rotor table and the per-step series agree, and none reads NA."""
    _assert_one_clock(_posted_rotor_campaign(tmp_path))


def test_a_clock_named_in_another_case_states_the_same_clock(tmp_path):
    """The row names its clock as `pusher`; the reference declares `PUSHER`.

    The planner folds the case of `CLOCK_MOTION`, so the products fold it too:
    the diameter is found under the reference's own spelling, and the ratio is
    the same in every product rather than `NA` in all of them.
    """
    _assert_one_clock(_posted_rotor_campaign(tmp_path, clock_motion="pusher"))
