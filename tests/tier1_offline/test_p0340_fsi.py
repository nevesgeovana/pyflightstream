"""Tier 1: the FSI items of 0.34.0 (FR-338 to FR-340, PFS-2073.01 to .03).

FR-339 is offline and whole here: the convergence log's signed tip deflection,
a new last column, every earlier column as 0.33.0 wrote it.

FR-338 and FR-340 also owe a licensed run (LQ1, RPT-128). Their marker tests
read the machine-readable field the report carries in its front matter, and
failed until it was committed, so they were held on the package branch
feat/0-34-fsi (df44313d); they entered with RPT-128, in
test_p0340_fsi_rpt128.py. FR-341 (route C, PFS-2073.04)
left 0.34.0 for 0.36.0 by the author decision of 2026-10-01; its offline half
and its RPT-129 test stay on that branch with it.

Each test here was proved by a mutant of the code it holds, reverted and the
file restored (the commit message lists them).
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-339.

from __future__ import annotations

import csv
import io
import math
import re
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.fsi import driver, nodes
from pyflightstream.fsi.config import FsiConfig
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.loads import SectionFamilyMap
from tests.tier1_offline.test_fsi_driver import CALL2, driver_config, run_sequence, stage_run
from tests.tier1_offline.test_fsig_fixed_wing import (
    STATIONS,
    _staged_run,
    _wing_loads_export,
    steady_wing_case,
    wing_config,
)

ROOT = Path(__file__).resolve().parents[2]
FSI_PAGE = ROOT / "docs" / "fsi-workspace.md"

#: The header of fsi_convergence_log.csv as 0.33.0 wrote it, column by column.
V0330_COLUMNS = (
    "call",
    "step",
    "phase",
    "revolutions",
    "solver_iteration",
    "total_normal_force_n",
    "tip_flap_m",
    "tip_twist_deg",
    "inner_solves",
    "twist_residual_rad",
    "twist_tolerance_rad",
    "relaxation",
    "config_sha256",
)


def _log_rows(run_dir: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read the convergence log with the csv module: (header, rows by name)."""
    text = (run_dir / driver.LOG_FILE).read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    reader = csv.DictReader(io.StringIO(body))
    rows = list(reader)
    return list(reader.fieldnames or ()), rows


def _two_blade_loads(iteration: int) -> str:
    """The real export of call 2 with its second family made a second blade at half the load.

    The fixture's first 50 rows are the blade; its last 50 (a non-blade family)
    are replaced by the blade's rows with Fx, Fz and the moment halved, so the
    two blades of a two-blade configuration deflect by different amounts.
    """
    lines = CALL2.splitlines()
    rows = [i for i, line in enumerate(lines) if re.match(r"\s+-?\d\.\d+E[-+]\d+,", line)]
    assert len(rows) == 100, len(rows)
    for blade_row, other_row in zip(rows[:50], rows[50:], strict=True):
        values = [float(v) for v in lines[blade_row].strip().rstrip(",").split(",")]
        values[4:7] = [0.5 * v for v in values[4:7]]
        lines[other_row] = "      " + ", ".join(f"{v:.4E}" for v in values) + ","
    text = "\n".join(lines) + "\n"
    return re.sub(r"(Current solver iteration number:\s+)\d+", rf"\g<1>{iteration}", text)


def _wing_call(tmp_path: Path, cfg: FsiConfig, fz_n_per_m: float) -> tuple[Path, float]:
    """One steady fixed-wing call; returns the run folder and the tip z the package wrote."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    run_dir = _staged_run(tmp_path, steady_wing_case, cfg)
    (run_dir / driver.LOADS_FILE).write_text(
        _wing_loads_export(60, unsteady=False, fz_n_per_m=fz_n_per_m)
    )
    driver.coupling_step(run_dir)
    layout = nodes.load_node_map(run_dir / cfg.node_map_file)
    written = nodes.read_fsidisp(run_dir / driver.DISPLACEMENT_FILE)
    return run_dir, float(written[layout.row_index(0, STATIONS - 1, "elastic_axis")][2])


# --------------------------------------------------------------------------
# FR-339: the signed tip deflection, a new last column.


@pytest.mark.parametrize(
    "case, cfg, fz_n_per_m, sign",
    [
        ("lift_bends_up", wing_config(self_weight=False), 50.0, 1.0),
        ("weight_bends_down", wing_config(), 0.0, -1.0),
    ],
    ids=["positive", "negative"],
)
def test_the_last_column_is_the_signed_tip_deflection_of_the_displacement_file_fr_339(
    tmp_path, case, cfg, fz_n_per_m, sign
):
    """P0340-FSI-TIP-SIGN, FR-339 R1: the sign the displacement file carries.

    Lift alone bends the wing toward the suction side (+z, positive); its own
    weight alone bends it down (negative). The test reads the tip node of the
    FSIDisp.txt the call wrote and the log's last column, both with their sign.
    """
    run_dir, tip_z = _wing_call(tmp_path / case, cfg, fz_n_per_m)
    header, rows = _log_rows(run_dir)
    assert header[-1] == "tip_flap_signed_m"
    signed = float(rows[-1]["tip_flap_signed_m"])
    assert math.copysign(1.0, tip_z) == sign
    assert math.copysign(1.0, signed) == sign, (
        f"the log says {signed} m and the displacement file's tip moved {tip_z} m"
    )
    # The written displacement is the relaxed one, d = lambda * d_calc from rest.
    assert signed * cfg.phases.coupling_relaxation == pytest.approx(tip_z, rel=1e-6)
    # FR-339 R2: the magnitude column keeps its value, the absolute of the same number.
    assert rows[-1]["tip_flap_m"] == f"{abs(signed):.6e}"


def test_every_earlier_column_keeps_its_name_position_and_value_fr_339(tmp_path):
    """P0340-FSI-TIP-SIGN, FR-339 R2: 0.33.0's thirteen columns, then the new one.

    The rotor route through every phase (wake development, averaging,
    convergence, recording) and a frozen replay: the header is 0.33.0's plus
    exactly one last column, and on every solved row the magnitude columns are
    the largest magnitude over the blades, as 0.33.0 computed them, while the
    signed one carries that blade's sign. A row with no solve leaves it empty
    or zero as the other tip columns do.
    """
    stage_run(tmp_path)
    results = run_sequence(tmp_path, 11)
    header, rows = _log_rows(tmp_path)
    assert tuple(header) == (*V0330_COLUMNS, "tip_flap_signed_m")
    assert len(rows) == len(results)
    for result, row in zip(results, rows, strict=True):
        if result.solutions is None:
            assert row["tip_flap_m"] == f"{0.0:.6e}"
            assert float(row["tip_flap_signed_m"]) == 0.0
            continue
        tips = [sol.flap_deflection_m[-1] for sol in result.solutions]
        twists = [math.degrees(sol.elastic_twist_rad[-1]) for sol in result.solutions]
        assert row["tip_flap_m"] == f"{max(abs(v) for v in tips):.6e}"
        assert row["tip_twist_deg"] == f"{max(abs(v) for v in twists):.6e}"
        assert row["tip_flap_signed_m"] == f"{max(tips, key=abs):.6e}"
        assert row["config_sha256"] and row["relaxation"]

    # Two blades whose tips differ: the magnitude columns are the larger one's
    # and the signed column is that same blade's, never the other's.
    two_dir = tmp_path / "two_blades"
    stage_run(two_dir, driver_config().model_copy(update={"blade_count": 2}))
    (two_dir / driver.FAMILY_MAP_FILE).write_text(
        SectionFamilyMap.uniform(blade_count=2, sections_per_blade=50).model_dump_json(indent=2)
        + "\n",
        encoding="utf-8",
    )
    solved = []
    for call in range(4):
        (two_dir / driver.LOADS_FILE).write_text(
            _two_blade_loads(100 + 40 * call), encoding="utf-8"
        )
        result = driver.coupling_step(two_dir)
        if result.solutions is not None:
            solved.append(result)
    _, rows = _log_rows(two_dir)
    assert solved, "no call of the two-blade run solved"
    for result, row in zip(solved, rows[-len(solved) :], strict=True):
        tips = [sol.flap_deflection_m[-1] for sol in result.solutions]
        assert abs(abs(tips[0]) - abs(tips[1])) > 1e-9, f"the two tips do not differ: {tips}"
        assert row["tip_flap_m"] == f"{max(abs(v) for v in tips):.6e}"
        assert row["tip_flap_signed_m"] == f"{max(tips, key=abs):.6e}"

    frozen_dir = tmp_path / "frozen"
    cfg = stage_run(frozen_dir)
    layout = nodes.generate_node_layout(cfg)
    nodes.write_fsidisp(frozen_dir / driver.FROZEN_FILE, np.zeros((layout.total_nodes, 3)))
    driver.coupling_step(frozen_dir)
    header, rows = _log_rows(frozen_dir)
    assert tuple(header) == (*V0330_COLUMNS, "tip_flap_signed_m")
    assert rows[0]["phase"] == "frozen"
    assert rows[0]["tip_flap_m"] == rows[0]["tip_flap_signed_m"] == ""


def _call2_scaled(iteration: int, factor: float, *, steady: bool = False) -> str:
    """The real export of call 2 with every section's Fx, Fz and moment times ``factor``.

    ``factor = -1`` reverses the loads, so a blade the fixture bends toward
    the suction side bends away from it; ``steady`` drops the time increment,
    as a steady (quasi-steady sector) export carries none.
    """
    lines = CALL2.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"\s+-?\d\.\d+E[-+]\d+,", line):
            values = [float(v) for v in line.strip().rstrip(",").split(",")]
            values[4:7] = [factor * v for v in values[4:7]]
            lines[i] = "      " + ", ".join(f"{v:.4E}" for v in values) + ","
    text = "\n".join(lines) + "\n"
    if steady:
        text = text.replace("     Time increment (sec)                        .004\n", "")
        assert "Time increment" not in text
    return re.sub(r"(Current solver iteration number:\s+)\d+", rf"\g<1>{iteration}", text)


def _assert_signed_row(row: dict[str, str], tips: list[float], sign: float) -> None:
    """The signed column carries the largest blade's tip with its sign; the magnitude its abs."""
    largest = max(tips, key=abs)
    assert math.copysign(1.0, largest) == sign, f"the solved tips {tips} do not have sign {sign}"
    assert row["tip_flap_signed_m"] == f"{largest:.6e}"
    assert row["tip_flap_m"] == f"{abs(largest):.6e}"
    assert math.copysign(1.0, float(row["tip_flap_signed_m"])) == sign


@pytest.mark.parametrize("sign", [1.0, -1.0], ids=["positive", "negative"])
def test_the_rotor_routes_write_the_tip_with_its_sign_fr_339(tmp_path, sign):
    """P0340-FSI-TIP-SIGN, FR-339 R1 on the two rotor routes, both signs.

    The unsteady rotor through every phase and the quasi-steady sector, each
    fed the real export of call 2 as recorded (the blade bends toward the
    suction side) and with its loads reversed (it bends away). On every
    solved row the signed column is the tip of the solution with its sign,
    and the magnitude column its absolute value.
    """
    rotor = tmp_path / "rotor"
    stage_run(rotor)
    solved = 0
    for call in range(11):
        (rotor / driver.LOADS_FILE).write_text(
            _call2_scaled(100 + 40 * call, sign), encoding="utf-8"
        )
        result = driver.coupling_step(rotor)
        _, rows = _log_rows(rotor)
        assert rows[-1]["phase"] == str(result.phase)
        if result.solutions is not None:
            solved += 1
            _assert_signed_row(
                rows[-1], [sol.flap_deflection_m[-1] for sol in result.solutions], sign
            )
    assert solved >= 3, f"only {solved} calls of the rotor run solved"

    sector = tmp_path / "sector"
    stage_run(sector)
    (sector / driver.QUASI_STEADY_ROTOR_FILE).write_text("marker\n", encoding="utf-8")
    for call in range(2):
        (sector / driver.LOADS_FILE).write_text(
            _call2_scaled(100 + 40 * call, sign, steady=True), encoding="utf-8"
        )
        result = driver.coupling_step(sector)
        assert result.phase == driver.QUASI_STEADY_ROTOR_PHASE
        assert result.solutions is not None
        _, rows = _log_rows(sector)
        assert rows[-1]["phase"] == driver.QUASI_STEADY_ROTOR_PHASE
        _assert_signed_row(rows[-1], [sol.flap_deflection_m[-1] for sol in result.solutions], sign)


def test_a_run_resumed_on_a_0330_log_is_refused_before_it_writes_fr_339(tmp_path):
    """P0340-FSI-TIP-SIGN, FR-339 R1 and R2: one log, one layout.

    A run whose log 0.33.0 started (thirteen columns) and which this release
    resumes would append rows of fourteen under that header. The call is
    refused, naming the file, before it writes the displacement file, the
    log or the state; with the old log moved aside the same call resumes and
    starts a log under this release's header.
    """
    stage_run(tmp_path)
    run_sequence(tmp_path, 2)
    log = tmp_path / driver.LOG_FILE
    text = log.read_text(encoding="utf-8").replace(",tip_flap_signed_m\n", "\n", 1)
    assert ",".join(V0330_COLUMNS) + "\n" in text
    log.write_text(text, encoding="utf-8")
    (tmp_path / driver.LOADS_FILE).write_text(_call2_scaled(300, 1.0), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    with pytest.raises(FsiInputError, match=r"fsi_convergence_log\.csv was started under"):
        driver.coupling_step(tmp_path)
    after = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    assert after == before, "the refused call wrote into the run folder"

    log.rename(tmp_path / "fsi_convergence_log_0330.csv")
    result = driver.coupling_step(tmp_path)
    header, rows = _log_rows(tmp_path)
    assert tuple(header) == (*V0330_COLUMNS, "tip_flap_signed_m")
    assert [int(row["call"]) for row in rows] == [result.call] == [3]


def test_a_reader_of_a_0330_log_keeps_reading_it_fr_339(tmp_path):
    """P0340-FSI-TIP-SIGN, FR-339 R3, and the FSI page states the convention (R1).

    A reader that takes the columns by name reads a 0.33.0 log, which lacks
    the new column, and a 0.34.0 log alike; the FSI page names the column and
    its sign.
    """
    old = tmp_path / "old"
    old.mkdir()
    (old / driver.LOG_FILE).write_text(
        "# pyflightstream FSI convergence log (FSI-R09, FSI-R15)\n"
        + ",".join(V0330_COLUMNS)
        + "\n1,1,fixed_wing,,60,200.000000,1.270541e-02,0.000000e+00,1,,,0.400,abc\n",
        encoding="utf-8",
    )
    run_dir, _ = _wing_call(tmp_path / "new", wing_config(), 0.0)
    for folder in (old, run_dir):
        _, rows = _log_rows(folder)
        assert rows and all("tip_flap_m" in row for row in rows)
        assert float(rows[0]["tip_flap_m"]) > 0.0
    page = FSI_PAGE.read_text(encoding="utf-8")
    assert "`tip_flap_signed_m`" in page
    assert "suction side" in page.split("`tip_flap_signed_m`", 1)[1][:600]
