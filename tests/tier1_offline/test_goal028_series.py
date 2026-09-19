"""The series tables say which step, which probe, which surface and at what condition.

THE DEFECTS (scope 4d, S6 of the drafts: NL-02, RI-06, NL-05, RI-04, MT-06).

- The solver step was spelled `step` here, `ITERATION` in the sections table and
  `STEP` in the probe table. ONE name, `STEP`, as answered on 2026-09-18.
- The probes series carried one row per step and probe and NO column saying which
  probe: twelve rows of one step were told apart by their order (RI-06).
- No series row stated the condition it was flown at (NL-05); every other product
  of the point does.
- The sections series concatenated every distribution with no identity, exactly as
  the sections table did (RI-04).
- A SUBMITTED point runs in `datapoints/DP-<tag>/` and the solver stamps its
  per-step exports there. The writer scanned the simulation folder's top level
  only, found nothing, and wrote three HEADER-ONLY tables the manifest recorded as
  written, with `steps_tabled: []` and no skip (MT-06).

THE USAGE, as a reader meets it:

    STEP,time_s,azimuth_deg,PROBE,ALPHA,BETA,MACH,...,X,Y,Z,...
    3,0.03000,90.00000,1,-2.00000,...
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_post_products import (  # noqa: E402
    LOADS,
    PROBES,
    SLOADS,
    _products_manifest,
    _series,
    _windowed_workspace,
)

from pyflightstream.post._tables import CONTEXT_COLUMNS  # noqa: E402
from pyflightstream.post.products import NOT_APPLICABLE, write_campaign_products  # noqa: E402

WINDOW = {
    "stated_form": "iterations",
    "stated_value": 3.0,
    "first_step": 3,
    "time_iterations": 5,
    "delta_time_s": 0.01,
    "step_deg": 30.0,
}


def test_every_series_spells_the_step_in_capitals_and_states_the_condition(tmp_path):
    workspace = _windowed_workspace(tmp_path, window=WINDOW)
    write_campaign_products(workspace)
    for name in ("loads", "sections", "probes"):
        columns, rows = _series(workspace, f"AL-020_{name}_series.csv")
        assert columns[0] == "STEP" and "step" not in columns, (name, columns[:4])
        at = columns.index("ALPHA")
        assert tuple(columns[at : at + len(CONTEXT_COLUMNS)]) == CONTEXT_COLUMNS, (name, columns)
        # The record states Mach 0.2 and SREF 50; the loads export states alpha.
        assert rows[0]["MACH"] == "0.20000", (name, rows[0])
        assert rows[0]["SREF"] == "50.00000", (name, rows[0])


def test_a_probes_series_row_says_which_probe_it_is(tmp_path):
    workspace = _windowed_workspace(tmp_path, window=WINDOW)
    write_campaign_products(workspace)
    columns, rows = _series(workspace, "AL-020_probes_series.csv")
    assert "PROBE" in columns and columns.index("PROBE") < columns.index("ALPHA"), columns
    of_step_three = [int(r["PROBE"]) for r in rows if r["STEP"] == "3"]
    assert of_step_three == list(range(1, 13)), "the fixture exports twelve probes, in order"


def _with_layout(workspace, layout, reductions):
    from pyflightstream.workspace import RunRecord

    (record,) = workspace.read_manifest()
    updated = record.model_copy(update={"sections_layout": layout, "reductions": reductions})
    (workspace.root / "runs.json").unlink()
    workspace.append_record(RunRecord(**updated.model_dump()))


def test_a_sections_series_row_says_which_distribution_it_belongs_to(tmp_path):
    workspace = _windowed_workspace(tmp_path, window=WINDOW)
    _with_layout(
        workspace,
        [
            {"families": ["W"], "plane": "XZ", "count": 1, "frame": ""},
            {"families": ["B"], "plane": "XY", "count": 1, "frame": "B1"},
        ],
        None,
    )
    write_campaign_products(workspace)
    columns, rows = _series(workspace, "AL-020_sections_series.csv")
    assert columns[:6] == ["STEP", "time_s", "FAMILY", "PLANE", "ROTOR", "AZIMUTH"], columns[:7]
    assert [(r["STEP"], r["FAMILY"], r["PLANE"]) for r in rows[:2]] == [
        ("3", "W", "XZ"),
        ("3", "B", "XY"),
    ]
    # No reference in this workspace names a rotor, so no block has one.
    assert {r["ROTOR"] for r in rows} == {NOT_APPLICABLE}
    assert {r["AZIMUTH"] for r in rows} == {NOT_APPLICABLE}


def _submitted_workspace(tmp_path, kinds=("", "_sloads", "_probes")):
    """The layout a SUBMITTED point leaves: everything under its datapoint folder."""
    from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = ["W", "B"]\n', encoding="utf-8"
    )
    folder = workspace.sim_dir("7001") / "datapoints" / "DP-AL-020"
    folder.mkdir(parents=True)
    (folder / "AL-020.txt").write_text(LOADS, encoding="utf-8")
    texts = {"": LOADS, "_sloads": SLOADS, "_probes": PROBES}
    for step in (3, 4, 5):
        for kind in kinds:
            (folder / f"AL-020{kind}_iteration={step}.txt").write_text(
                texts[kind], encoding="utf-8"
            )
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_7001/AL-020",
            point_name="AL-020",
            sweep_name="AL-020",
            sim_id="7001",
            point={"alpha": -2.0},
            fs_version_requested="26.123",
            package_version="0.24.0.dev0",
            script_sha256="",
            raw_flag=False,
            status=RunStatus.CONVERGED,
            outputs=["datapoints/DP-AL-020/AL-020.txt"],
            pproc="p001",
            recipe="unsteady_rotor",
            description="ROTOR_UNSTEADY",
            mach=0.2,
            reference={"SREF": 50.0, "CREF": 2.526, "BREF": 20.0},
            export_window=WINDOW,
            action_count=5,
        )
    )
    return workspace


def test_the_stamped_exports_of_a_submitted_point_are_found_in_its_datapoint_folder(tmp_path):
    workspace = _submitted_workspace(tmp_path)
    write_campaign_products(workspace)
    _columns, rows = _series(workspace, "AL-020_loads_series.csv")
    assert [int(r["STEP"]) for r in rows] == [3, 4, 5]
    entry = _products_manifest(workspace)["products"]["series/AL-020_loads_series.csv"]
    assert entry["steps_tabled"] == [3, 4, 5], entry


def test_a_kind_with_no_stamped_file_is_a_named_skip_and_never_a_header_only_table(tmp_path):
    workspace = _submitted_workspace(tmp_path, kinds=("",))
    with pytest.warns(Warning):
        write_campaign_products(workspace)
    series = workspace.root / "post" / "products" / "series"
    assert (series / "AL-020_loads_series.csv").is_file()
    assert not (series / "AL-020_probes_series.csv").exists(), "a table of a header and no row"
    manifest = _products_manifest(workspace)
    assert "series/AL-020_probes_series.csv" not in manifest["products"]
    reason = manifest["skipped"]["series/AL-020_probes_series.csv"]
    assert "AL-020_probes_iteration=" in reason and "DP-AL-020" in reason, reason
