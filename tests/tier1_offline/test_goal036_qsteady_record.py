"""Tier 1: the quasi-steady record is one type with one reader and one refusal (0.31.0, A3).

``<point>_qsteady.json`` had no type until 0.31.0: the post's reader raised
``ProductError`` on a record it could not read while the run's returned None on
the same file, and the reader of its rotor alias sat in ``workspace/inputs.py``.
Now :class:`pyflightstream.cases.qsteady.QsteadyRecord` is the record, written
by the builder as its own text and read back by
:func:`pyflightstream.cases.qsteady.read_qsteady_record`, which raises
:class:`pyflightstream.cases.qsteady.QsteadyRecordError` for every failure; the
callers decide: the run judges the log as one solve and says so on the point's
record, the post names each product it leaves out and never raises.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-189.

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Any

import pytest

from pyflightstream import exceptions
from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.cases import qsteady as record_module
from pyflightstream.cases.qsteady import (
    QsteadyRecord,
    QsteadyRecordError,
    read_qsteady_record,
)
from pyflightstream.cases.workflows import QSTEADY_ROTOR
from pyflightstream.run import Assessment, LoadsAssessor, run_campaign
from pyflightstream.run._assessment import _wheel_clockings
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_goal035_l1_defects import _PROP_REFERENCE, _clocked_wheel
from tests.tier1_offline.test_goal035_qsteady_rotor import _case, _lines
from tests.tier1_offline.test_run_campaign import WRITES_LOADS, StubSolver, steady_recipe


def _written(**variables: Any) -> str:
    """The record the builder parks for a quasi-steady row with ``variables``, as text."""
    _, script = _lines(_case(**variables))
    return str(script.pending_input_files["DP_qsteady.json"])


#: A two-clocking wheel, a three-clocking wheel and a sector, each as the builder writes it.
_ROWS = {
    "wheel of two": {"PASSAGE_POSITIONS": "2", "ALPHA_POINT": 5.0},
    "wheel of three": {"PASSAGE_POSITIONS": "3"},
    "sector": {"SYMMETRY": "PERIODIC", "PERIODIC_COPIES": "3"},
}


# ----------------------------------------------------- the type and its reader --


@pytest.mark.parametrize("row", sorted(_ROWS))
def test_the_reader_round_trips_the_writers_record(tmp_path, row):
    """Read back and written again, the builder's record is the same bytes."""
    # P0310-A3-RECORD
    text = _written(**_ROWS[row])
    (tmp_path / "DP_qsteady.json").write_text(text, encoding="utf-8")
    record = read_qsteady_record(tmp_path / "DP.txt")
    assert isinstance(record, QsteadyRecord)
    assert record.to_text() == text
    assert record.as_json() == json.loads(text)
    stated = json.loads(text)
    assert record.rotor_alias == stated["rotor"] == "PROP"
    assert record.case == stated["case"]
    assert [clocking.loads for clocking in record.positions] == [
        entry["loads"] for entry in stated["positions"]
    ]
    # The run type the reader holds the file to is the builder's own name for it.
    assert record.run_type == QSTEADY_ROTOR == record_module.RECORD_RUN_TYPE


def test_the_writer_keeps_the_bytes_it_wrote_before_the_record_had_a_type():
    """The two-clocking wheel's file, key for key and in order, as the 0.30.0 builder wrote it.

    Pinned by a literal and not by the type, which now writes AND reads the
    file, so a round trip alone would move with a reordered key. The plan's
    validity record is the plan's, carried as it is, and taken from the file.
    """
    # P0310-A3-RECORD
    text = _written(PASSAGE_POSITIONS="2", ALPHA_POINT=5.0)
    stated = json.loads(text)
    expected = {
        "schema_version": 1,
        "run_type": "qsteady_rotor",
        "case": "wheel",
        "rotor": "PROP",
        "blades": 3,
        "rpm": 1200.0,
        "shaft_frame_axis": "X",
        "hub_m": [0.0, 0.0, 0.0],
        "axis_vector": [1.0, 0.0, 0.0],
        "diameter_m": 2.0,
        "families_general": [],
        "families_blades": ["Blade1", "Blade2", "Blade3"],
        "blade1_azimuth_deg": 0.0,
        "positions": [
            {"index": 0, "clocking_deg": 0.0, "rotated_deg": 0.0, "loads": "DP.txt"},
            {"index": 1, "clocking_deg": 60.0, "rotated_deg": 60.0, "loads": "DP_qs01.txt"},
        ],
        "validity": stated["validity"],
    }
    assert text == json.dumps(expected, indent=2) + "\n"


def test_the_solve_order_is_the_builders_clocking_zero_last(tmp_path):
    """Clockings 1 to k - 1 first, then 0, as ``_build_qsteady_rotor`` solves them."""
    # P0310-A3-RECORD
    (tmp_path / "DP_qsteady.json").write_text(_written(PASSAGE_POSITIONS="3"), encoding="utf-8")
    record = read_qsteady_record(tmp_path / "DP.txt")
    assert [clocking.index for clocking in record.solve_order()] == [1, 2, 0]


def _spoiled(key: str, value: object) -> str:
    """The builder's two-clocking record with ``key`` set to ``value`` (or removed)."""
    data = json.loads(_written(PASSAGE_POSITIONS="2"))
    if value is _REMOVED:
        del data[key]
    else:
        data[key] = value
    return json.dumps(data)


_REMOVED = object()


def _refusals() -> dict[str, str | None]:
    """Every shape of a record the reader must refuse, as the file's text (None: no file)."""
    clockings = json.loads(_written(PASSAGE_POSITIONS="2"))
    clockings["positions"].reverse()
    stray = json.loads(_written(PASSAGE_POSITIONS="2"))
    stray["positions"][0]["phase_deg"] = 0.0
    return {
        "missing": None,
        "not json": '{"schema_version": 1, "run_type": ',
        "not utf-8": "\udcff",
        "an array": "[1, 2]",
        "schema 2": _spoiled("schema_version", 2),
        "schema true": _spoiled("schema_version", True),
        "no schema": _spoiled("schema_version", _REMOVED),
        "an unknown key": _spoiled("extra", 1),
        "a missing key": _spoiled("diameter_m", _REMOVED),
        "another run type": _spoiled("run_type", "steady"),
        "another case": _spoiled("case", "hub"),
        "no rotor alias": _spoiled("rotor", ""),
        "a speed that is a flag": _spoiled("rpm", True),
        "a hub of two numbers": _spoiled("hub_m", [0.0, 0.0]),
        "no clocking": _spoiled("positions", []),
        "clockings out of order": json.dumps(clockings),
        "a clocking with a stray key": json.dumps(stray),
        "a validity that is a list": _spoiled("validity", []),
    }


@pytest.mark.parametrize("shape", sorted(_refusals()))
def test_a_missing_corrupt_or_unknown_record_is_one_refusal(tmp_path, shape):
    """Every failure is QsteadyRecordError, catalogued, naming the file."""
    # P0310-A3-RECORD
    text = _refusals()[shape]
    path = tmp_path / "DP_qsteady.json"
    if text == "\udcff":
        path.write_bytes(b'{"schema_version": 1, "run_type": "\xff"}')
    elif text is not None:
        path.write_text(text, encoding="utf-8")
    with pytest.raises(QsteadyRecordError, match="the quasi-steady record") as caught:
        read_qsteady_record(tmp_path / "DP.txt")
    assert "DP_qsteady.json" in str(caught.value)
    assert isinstance(caught.value, PyflightstreamError) and isinstance(caught.value, ValueError)
    assert exceptions.QsteadyRecordError is QsteadyRecordError


def test_the_rotor_alias_reader_lives_beside_the_record():
    """One reader of the record's ``rotor`` key, in cases/qsteady.py; none left in workspace."""
    # P0310-A3-RECORD
    import pyflightstream.workspace.inputs as inputs

    assert record_module.qsteady_record_rotor_alias({"rotor": "PROP"}) == "PROP"
    assert not hasattr(inputs, "qsteady_record_rotor_alias")
    with pytest.raises(QsteadyRecordError, match="names no rotor alias"):
        record_module.qsteady_record_rotor_alias({})


# ------------------------------------------------------------- the run decides --


def test_the_run_judges_the_log_as_one_solve_and_warns_when_the_record_cannot_be_read(tmp_path):
    """A wheel of two clockings whose record is spoiled: no clocking verdicts, one warning.

    With its record, the same point is judged clocking by clocking and warns of
    nothing; without it, its one log of two solves is judged as one solve, as
    before 0.31.0, and the assessment now says so for the point's record.
    """
    # P0310-A3-RECORD
    case, sim = _clocked_wheel(tmp_path / "whole", (2.0e-6, 3.0e-6))
    whole = LoadsAssessor()(case, None, sim)
    assert whole.clocking_verdicts is not None and whole.warnings is None

    case, sim = _clocked_wheel(tmp_path / "spoiled", (2.0e-6, 3.0e-6))
    (sim / "outputs" / "DP_qsteady.json").write_text(_spoiled("schema_version", 2))
    spoiled = LoadsAssessor()(case, None, sim)
    assert spoiled.clocking_verdicts is None
    assert spoiled.warnings is not None and len(spoiled.warnings) == 1
    (line,) = spoiled.warnings
    assert "DP_qsteady.json" in line and "is of schema 2" in line
    assert "judged as one solve" in line


def test_a_missing_record_warns_only_where_the_point_is_quasi_steady(tmp_path):
    """No record beside a qsteady point is said; beside any other point there is nothing to say."""
    # P0310-A3-RECORD
    loads = tmp_path / "DP.txt"
    clockings, said = _wheel_clockings(loads, quasi_steady=True)
    assert clockings is None and said is not None and "is not on disk" in said
    assert _wheel_clockings(loads, quasi_steady=False) == (None, None)
    assert _wheel_clockings(loads, quasi_steady=None) == (None, None)
    (tmp_path / "DP_qsteady.json").write_text("not json", encoding="utf-8")
    assert _wheel_clockings(loads, quasi_steady=False) == (None, None)
    clockings, said = _wheel_clockings(loads, quasi_steady=None)
    assert clockings is None and said is not None and "cannot be read" in said


def test_the_point_record_carries_what_the_judgment_did_without(tmp_path):
    """The assessment's warning reaches the point's RunRecord ``warnings``, and is warned."""
    # P0310-A3-RECORD
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    campaign = Campaign(
        name="camp",
        fs_version="26.120",
        fs_exe=sys.executable,
        sims=[
            SimCase(
                sim_id="9001",
                aircraft="TestWing",
                velocity=30.0,
                geometry=str(geometry),
                sweep=SweepAxis(type="alpha", values=[0.0]),
                recipe="steady",
                outputs=["loads_{point}.txt"],
            )
        ],
    )
    said = "the quasi-steady record DP_qsteady.json is of schema 2; judged as one solve"

    def judged(case, execution, sim_dir):
        return Assessment(status=RunStatus.CONVERGED, iterations=1, warnings=[said])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        (record,) = run_campaign(
            campaign,
            StubSolver(WRITES_LOADS),
            CampaignWorkspace(tmp_path / "camp"),
            assess=judged,
            recipes={"steady": steady_recipe},
        )
    assert said in record.warnings
    assert any(said in str(warning.message) for warning in caught)


# ------------------------------------------------------------ the post decides --


def _posted_with(tmp_path: Path, text: str | None) -> tuple[dict, Path]:
    """Polar 6001 re-recorded as a quasi-steady wheel whose record file holds ``text``.

    ``None`` leaves no record at all. The post runs to its end either way.
    """
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r001.toml").write_text(
        _PROP_REFERENCE, encoding="utf-8"
    )
    records = workspace.read_manifest()
    (workspace.root / "runs.json").unlink()
    for record in records:
        if record.sim_id == "6001":
            loads = workspace.sim_dir("6001") / record.outputs[0]
            if text is not None:
                loads.with_name(loads.stem + "_qsteady.json").write_text(text, encoding="utf-8")
            record = record.model_copy(update={"recipe": QSTEADY_ROTOR})
        workspace.append_record(RunRecord(**record.model_dump()))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _post(workspace)
    (manifest,) = workspace.root.rglob("products.json")
    return json.loads(manifest.read_text(encoding="utf-8")), manifest.parent


@pytest.mark.parametrize(
    ("shape", "says"),
    [
        ("missing", "is not on disk"),
        ("corrupt", "cannot be read"),
        ("schema 2", "is of schema 2"),
    ],
)
def test_the_post_names_each_product_the_record_costs_and_never_raises(tmp_path, shape, says):
    """products.json skips the rotor table and the clockings tables by name; post.log warns."""
    # P0310-A3-RECORD
    text = {"missing": None, "corrupt": "{not json", "schema 2": _spoiled("schema_version", 2)}
    products, folder = _posted_with(tmp_path, text[shape])
    skipped = products["skipped"]
    naming = {name: reason for name, reason in skipped.items() if says in reason}
    assert any(name.endswith("_qs_positions.csv") for name in naming), skipped
    assert any(name.endswith("PROP_rotor.csv") for name in naming), skipped
    assert not any(name.endswith("_qs_positions.csv") for name in products["products"])
    log = (folder / products["log"]).read_text(encoding="utf-8")
    assert any(
        line.startswith("WARNING") and says in line and "_qsteady.json" in line
        for line in log.splitlines()
    ), log
