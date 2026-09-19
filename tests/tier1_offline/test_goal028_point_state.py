"""A run record describes the state of ITS OWN point (STATE-SNAPSHOT, CC-01).

THE DEFECT, as the owner would meet it. A row sweeps the Mach number at a held
Reynolds number. Every point gets its own script with its own velocity and
density, which 0.21.0 measured. The RECORD of each point did not: it was written
from the simulation-level case, so both records carried the FIRST point's Mach,
velocity and density. Downstream, the post stage wrote that Mach into every row
of the polar and the rotor table divided by another point's density.

The expected values are the ones the SCRIPT of each point carries, read off the
emitted script, never off the record writer.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run.matrix import run_matrix
from tests.tier1_offline.test_goal024_point_name import RECIPES, _matrix
from tests.tier1_offline.test_goal024_sweep_any_variable import _every_value
from tests.tier1_offline.test_matrix_run import WRITES_EVERY_EXPORT, CountingStub, converged


@pytest.fixture
def swept(tmp_path):
    workspace, matrix = _matrix(
        tmp_path, condition="MACH:sweep, REmi:2.3, ALPHA:0.0", values="0.1,0.3"
    )
    run_matrix(
        matrix,
        workspace,
        name="swept",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=converged,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    return workspace


def _script_state(workspace, stem: str) -> tuple[float, float]:
    text = (workspace.sim_dir("3207") / "scripts" / f"{stem}.txt").read_text(encoding="utf-8")
    return (
        float(_every_value(text, "SOLVER_SET_VELOCITY")[0]),
        float(_every_value(text, "DENSITY")[0]),
    )


def test_each_record_carries_the_state_its_own_script_was_given(swept):
    records = {record.point_name: record for record in swept.read_manifest()}
    assert sorted(records) == ["M100RE230AL+000", "M300RE230AL+000"], sorted(records)
    for name, mach in (("M100RE230AL+000", 0.1), ("M300RE230AL+000", 0.3)):
        record = records[name]
        velocity, density = _script_state(swept, f"P3207-{name}")
        assert record.mach == pytest.approx(mach), (name, record.mach)
        assert record.flight_condition["MACH"] == pytest.approx(mach), record.flight_condition
        assert record.velocity_requested_m_s == pytest.approx(velocity, rel=1e-4), name
        assert record.density_kg_m3 == pytest.approx(density, rel=1e-4), (
            f"{name}: the record states density {record.density_kg_m3} and its own script "
            f"was given {density}"
        )


def test_the_two_records_differ_which_is_what_a_sim_level_snapshot_cannot_do(swept):
    slow, fast = sorted(swept.read_manifest(), key=lambda record: record.point["MACH"])
    assert fast.mach > slow.mach * 2.5
    assert fast.velocity_requested_m_s > slow.velocity_requested_m_s * 2.5
    assert slow.density_kg_m3 > fast.density_kg_m3 * 2.5


# ------------------------------------------------ records ALREADY written wrong


def _as_0_23_0_wrote_them(workspace) -> None:
    """Give every record the FIRST point's state, which is what 0.23.0 recorded.

    The point mapping and the row's cell are left alone: they are what a record
    written before this release still states truthfully, and they are all the
    post stage has to re-resolve the point from.
    """
    import json

    path = workspace.root / "runs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    runs = data["runs"] if isinstance(data, dict) else data
    first = min(runs, key=lambda run: run["point"]["MACH"])
    for run in runs:
        for key in ("mach", "velocity_requested_m_s", "density_kg_m3", "flight_condition"):
            run[key] = first[key]
    path.write_text(json.dumps(data), encoding="utf-8")


def test_the_post_stage_re_resolves_a_point_a_record_describes_wrongly(swept):
    """No re-run and no rewritten record: the polar still states each row's own Mach."""
    import warnings

    from pyflightstream.post.products import read_csv_table, write_campaign_products
    from tests.tier1_offline.test_post_products import loads_stating

    # The stub executor leaves placeholders; a real loads export per point is
    # what the post stage reads. It states no Mach, so one text serves both.
    for record in swept.read_manifest():
        loads = next(o for o in record.outputs if o.endswith(f"{record.point_name}.txt"))
        # ...divided by the reference THIS workspace states, as a real export is.
        reference = record.reference
        text = loads_stating(area_m2=reference["SREF"], chord_m=reference["CREF"])
        (swept.sim_dir("3207") / loads).write_text(text, encoding="utf-8")
    # And a group that selects the surfaces that export carries: one that selects
    # nothing is a named skip, not a polar of zeros.
    (swept.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = ["W", "B"]\n', encoding="utf-8"
    )
    _as_0_23_0_wrote_them(swept)
    before = (swept.root / "runs.json").read_bytes()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        stem = swept.read_manifest()[0].matrix_stem
        written = write_campaign_products(swept, matrix_stem=stem, overwrite=True)
    assert (swept.root / "runs.json").read_bytes() == before, "a record is never rewritten"

    polars = [path for path in written if path.parent.name == "polars" and path.suffix == ".csv"]
    assert polars, [str(path) for path in written]
    _columns, rows = read_csv_table(polars[0])
    assert [float(row["MACH"]) for row in rows] == pytest.approx([0.1, 0.3]), (
        "the Mach 0.3 run is published as Mach 0.1: every row took the first record's Mach"
    )
    said = [str(w.message) for w in caught if "M300RE230AL+000" in str(w.message)]
    assert said and "0.3" in said[0] and "0.1" in said[0], [str(w.message) for w in caught]
