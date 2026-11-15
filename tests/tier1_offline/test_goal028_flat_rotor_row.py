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

import re
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


def _rcoef(written, name):
    """The one RCOEF group file of that name the post wrote."""
    return [path for path in written if path.name == name]


def test_the_one_rotor_of_a_flat_row_gets_its_table_at_the_rows_speed(tmp_path):
    _workspace_, written = _flat(tmp_path)
    # 0.58.0: the rotor table is the ROTOR group's RCOEF file, its speed RPM<id> in the run block.
    (table,) = _rcoef(written, "P6002-PUSHER-RCOEF.csv")
    columns, rows = read_csv_table(table)
    assert rows, "the table holds no row"
    assert {float(row["RPM0"]) for row in rows} == {2200.0}


def test_with_two_rotors_nothing_says_whose_speed_it_is_and_the_skip_stays(tmp_path):
    """Neither rotor takes the flat speed: its RPM<id> stays NA in every file."""
    _workspace_, written = _flat(tmp_path, rotors=("PUSHER", "LIFTER"))
    for name in ("P6002-PUSHER-RCOEF.csv", "P6002-LIFTER-RCOEF.csv"):
        (table,) = _rcoef(written, name)
        columns, rows = read_csv_table(table)
        speeds = [column for column in columns if re.fullmatch(r"RPM\d+", column)]
        assert len(speeds) == 2, columns
        assert {row[column] for row in rows for column in speeds} == {"NA"}, name


def test_a_flat_record_stating_no_speed_is_still_the_named_skip(tmp_path):
    _workspace_, written = _flat(tmp_path, rpm=None)
    # No speed is stated, so none is written: RPM0 is NA, never a guessed value.
    (table,) = _rcoef(written, "P6002-PUSHER-RCOEF.csv")
    columns, rows = read_csv_table(table)
    assert rows and {row["RPM0"] for row in rows} == {"NA"}


def test_the_plan_of_a_flat_rotor_row_records_the_speed_it_turned_at(tmp_path):
    """The run half: the speed is on the record, signed, for the table to read."""
    from pyflightstream.cases.workflows import reduction_windows
    from tests.tier1_offline.test_workflows import rotor_case

    case = rotor_case()
    plan = reduction_windows(case)
    assert "rotors" not in plan or not plan["rotors"], "this fixture is the FLAT row"
    assert plan["rpm"] == pytest.approx(float(case.variables["RPM"])), plan.get("rpm")
