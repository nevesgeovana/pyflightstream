"""A record written with NO stated window is averaged over the one it defaulted to (MC-02).

The post half of the owner's answer. A new row is refused at plan; a record she
ALREADY HOLDS is never refused at post. 0.23.0 sent such a point down the STEADY
route: group polars read off the LAST TIME STEP under the steady names, beside a
time average over a window the run had defaulted, with nothing in either file
saying which was an instant and which an average. The definitions page says the
polar of an unsteady point ALWAYS comes from the plots, time-averaged.

So the point gets its `_uns_avg` table over the window its own record carries
(`window_stated: False`: the last revolution with a rotor, the whole run
without), the stage SAYS which window that was, and no last-step polar is written
under a steady name.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from pyflightstream.post.products import read_csv_table, write_campaign_products
from tests.tier1_offline.test_post_products import _products_manifest, _unsteady_workspace

#: As `reduction_windows` writes it for a rotorless row that states no key: the
#: whole run, and the flag that says the ROW did not state it.
DEFAULTED = {
    "window_stated": False,
    "time_iterations": 8,
    "steps_per_revolution": None,
    "blades": None,
    "time_average": {
        "windows": [[1, 8]],
        "window_from": "the whole run: nothing shorter is stated",
    },
}


def _posted(tmp_path):
    workspace = _unsteady_workspace(tmp_path, reductions=DEFAULTED, recipe="unsteady")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        written = [Path(path) for path in write_campaign_products(workspace)]
    return workspace, written, [str(w.message) for w in caught]


def test_the_point_gets_its_average_over_the_window_its_record_defaulted_to(tmp_path):
    _workspace_, written, _said = _posted(tmp_path)
    (table,) = [path for path in written if path.name.endswith("_uns_avg.csv")]
    _columns, rows = read_csv_table(table)
    assert [(row["FIRST_STEP"], row["LAST_STEP"], row["STEPS"]) for row in rows] == [
        ("1", "8", "8")
    ]


def test_the_stage_says_which_window_it_used_and_how_to_choose_another(tmp_path):
    _workspace_, _written, said = _posted(tmp_path)
    about = [message for message in said if "states no" in message and "AL-020" in message]
    assert len(about) == 1, said
    assert "1 to 8" in about[0] and "LAST_ITERS_AVG" in about[0], about[0]


def test_no_last_step_polar_is_written_under_a_steady_name(tmp_path):
    workspace, written, _said = _posted(tmp_path)
    steady_named = [
        path.name for path in written if path.parent.name == "polars" and "_g01" in path.name
    ]
    assert steady_named == [], steady_named
    assert all("_g01" not in key for key in _products_manifest(workspace)["products"])


def test_a_window_from_a_retired_key_is_said_as_that_and_not_as_a_default(tmp_path):
    """A row with a deprecated WINDOW_* key did state a window; the run did not default.

    Found reading the code for the architecture document of 0.24.0: the warning
    called every unstated window "the window the run defaulted to", including one a
    retired key of the row had chosen. It names where the window came from.
    """
    retired = {
        **DEFAULTED,
        "time_average": {
            "windows": [[5, 8]],
            "window_from": "the retired WINDOW_STEPS of the row: 4 steps",
        },
    }
    workspace = _unsteady_workspace(tmp_path, reductions=retired, recipe="unsteady")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        write_campaign_products(workspace)
    about = [str(w.message) for w in caught if "states no" in str(w.message)]
    assert len(about) == 1, [str(w.message) for w in caught]
    assert "WINDOW_STEPS" in about[0] and "5 to 8" in about[0], about[0]
    assert "defaulted" not in about[0], about[0]
