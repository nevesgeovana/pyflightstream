"""A row that states its one rotor with flat keys gets that rotor's table (debt item 5.1).

THE DEFECT. A matrix row stating `RPM` and `ROTOR_AXIS` and no `MOTIONS` list plans
no per-rotor block, and the rotor table read the rotor's speed from that block
alone. 0.23.0 made the absence a named skip; the table was still not written, though
the package already knew the speed: it is what `steps_per_revolution` was computed
from.

THE REACH, and it is bounded: the row's reference declares EXACTLY ONE rotor, so the
flat speed can only be that rotor's. With two, nothing says whose it is, and the skip
stays.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream.post.products import read_csv_table
from pyflightstream.workspace import RunRecord
from tests.tier1_offline.test_post_superfile import _post, _workspace

ROTOR = """
[rotors.{alias}]
alias = "{alias}"
x_m = 0.0
y_m = 0.0
z_m = 0.0
axis = "X"
rpm_sign = 1
diameter_m = 2.0
families_blades = ["B"]
blade1 = {{ azimuth_deg = 0.0, zero = "Y" }}
"""


def _flat(tmp_path, *, rotors=("PUSHER",), rpm: float | None = 2200.0):
    """The recorded campaign, its unsteady record rewritten as a FLAT row leaves it."""
    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(
        "area_m2 = 50.0\nchord_m = 2.526\nspan_m = 20.0\n"
        + "".join(ROTOR.format(alias=alias) for alias in rotors),
        encoding="utf-8",
    )
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.reductions:
            plan = {k: v for k, v in record.reductions.items() if k != "rotors"}
            if rpm is not None:
                plan["rpm"] = rpm
            record = record.model_copy(update={"reductions": plan})
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        written = [Path(path) for path in _post(workspace)]
    return workspace, written


def test_the_one_rotor_of_a_flat_row_gets_its_table_at_the_rows_speed(tmp_path):
    _workspace_, written = _flat(tmp_path)
    (table,) = [path for path in written if path.name.endswith("-PUSHER_rotor.csv")]
    columns, rows = read_csv_table(table, skip=1)
    assert rows, "the table holds no row"
    assert {float(row["RPM_PUSHER"]) for row in rows} == {2200.0}


def test_with_two_rotors_nothing_says_whose_speed_it_is_and_the_skip_stays(tmp_path):
    import json

    workspace, written = _flat(tmp_path, rotors=("PUSHER", "LIFTER"))
    assert not [path for path in written if path.name.endswith("_rotor.csv")]
    (manifest,) = workspace.root.rglob("products.json")
    skipped = json.loads(manifest.read_text(encoding="utf-8"))["skipped"]
    assert any(key.endswith("-PUSHER_rotor.csv") for key in skipped), sorted(skipped)


def test_a_flat_record_stating_no_speed_is_still_the_named_skip(tmp_path):
    workspace, written = _flat(tmp_path, rpm=None)
    assert not [path for path in written if path.name.endswith("_rotor.csv")]


def test_the_plan_of_a_flat_rotor_row_records_the_speed_it_turned_at(tmp_path):
    """The run half: the speed is on the record, signed, for the table to read."""
    from pyflightstream.cases.workflows import reduction_windows
    from tests.tier1_offline.test_workflows import rotor_case

    case = rotor_case()
    plan = reduction_windows(case)
    assert "rotors" not in plan or not plan["rotors"], "this fixture is the FLAT row"
    assert plan["rpm"] == pytest.approx(float(case.variables["RPM"])), plan.get("rpm")
