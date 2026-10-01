"""Tier 1: the four FSI items of 0.34.0 (FR-338 to FR-341, PFS-2073.01 to .04).

FR-339 is offline and whole here: the convergence log's signed tip deflection,
a new last column, every earlier column as 0.33.0 wrote it. FR-341's offline
half is here too: arbitrary displacements given to the package through two
loop cycles come back out of the file the solver reads unchanged.

FR-338, FR-340 and FR-341 also owe licensed runs (LQ1 for RPT-128, LQ4 for
RPT-129). Their marker tests read the machine-readable field each report
carries in its front matter and assert the branch it names; until the report
is committed they fail, naming the report and the run that owes it, because a
missing value is a failure by the requirement's own words.

Each test here was proved by a mutant of the code it holds, reverted and the
file restored (the commit message lists them).
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-338, FR-339, FR-340, FR-341.

from __future__ import annotations

import csv
import io
import math
import re
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.cases import fsi_workspace as ws
from pyflightstream.fsi import driver, nodes
from pyflightstream.fsi.config import FixedWing, FsiConfig, PhaseSchedule
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
REPORTS = ROOT / "reports"
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


# --------------------------------------------------------------------------
# FR-341, offline half: arbitrary displacements through two loop cycles.


def test_arbitrary_displacements_survive_two_loop_cycles_in_the_file_the_solver_reads_fr_341(
    tmp_path,
):
    """P0340-FSI-MODAL, FR-341: the package keeps what it is given.

    The truncation test of FR-341 asks whether the solver keeps the
    displacements it is given; its first half is whether the package does.
    Two loop cycles, each handing the driver an arbitrary field (signs and
    magnitudes spread over nine decades, no structural solution behind it),
    and each FSIDisp.txt read back equal to the field to the last bit.
    """
    cfg = stage_run(tmp_path)
    layout = nodes.generate_node_layout(cfg)
    rng = np.random.default_rng(20261001)
    for cycle in (1, 2):
        field = rng.uniform(-1.0, 1.0, (layout.total_nodes, 3)) * 10.0 ** rng.uniform(
            -9.0, 0.0, (layout.total_nodes, 3)
        )
        nodes.write_fsidisp(tmp_path / driver.FROZEN_FILE, field)
        result = driver.coupling_step(tmp_path)
        assert result.call == cycle
        written = nodes.read_fsidisp(
            tmp_path / driver.DISPLACEMENT_FILE, expected_rows=layout.total_nodes
        )
        assert np.array_equal(written, field), (
            f"cycle {cycle}: the file the solver reads differs from the field given, "
            f"largest difference {np.max(np.abs(written - field))!r} m"
        )


# --------------------------------------------------------------------------
# The licensed reports' verdicts (RPT-128, RPT-129).


def _front_matter(number: int, owed_by: str) -> tuple[Path, dict[str, str]]:
    """Return a report and the ``key: value`` fields of its front matter, or fail naming the run."""
    found = sorted(REPORTS.glob(f"RPT-{number}_*.md"))
    if not found:
        pytest.fail(
            f"RPT-{number} is not in reports/: the licensed run {owed_by} owes it, and its "
            "front matter carries the field this requirement's marker test reads"
        )
    lines = found[0].read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in lines[1:]:
        pytest.fail(f"{found[0].name} opens with no front matter between two '---' lines")
    end = lines.index("---", 1)
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip("\"'")
    return found[0], fields


def test_rpt128_states_why_cdo_reads_zero_and_the_tree_holds_its_branch_fr_338():
    """P0340-FSI-CDO, FR-338: `cdo_cause` is `package_order` or `solver`, and its branch holds."""
    report, fields = _front_matter(128, "LQ1")
    cause = fields.get("cdo_cause")
    assert cause in {"package_order", "solver"}, (
        f"{report.name}: cdo_cause is {cause!r}, and FR-338 accepts package_order or solver"
    )
    if cause == "package_order":
        pytest.fail(
            f"{report.name} names the package's order: the corrected export order of the "
            "aeroelastic post, its test with the 0.33.0 order as the control and the parity "
            "entry are owed (FR-338 R2, R4)"
        )
    page = FSI_PAGE.read_text(encoding="utf-8")
    assert "`CDo`" in page and "RPT-128" in page, (
        "FR-338 R3: the FSI page states that CDo reads zero in a coupled run, and why, "
        "citing RPT-128"
    )


def _xz_verdict(moment_ratio: float, force_ratio: float) -> str:
    """FR-340 R2, fixed before the run: confirmed when the moment ratio is as close to 1."""
    return "confirmed" if abs(moment_ratio - 1.0) <= abs(force_ratio - 1.0) else "refuted"


def test_rpt128_xz_moment_verdict_follows_its_two_ratios_and_the_tree_holds_it_fr_340():
    """P0340-FSI-XZ, FR-340: the verdict is recomputed from the two ratios by R2."""
    report, fields = _front_matter(128, "LQ1")
    verdict = fields.get("xz_moment_verdict")
    assert verdict in {"confirmed", "refuted"}, (
        f"{report.name}: xz_moment_verdict is {verdict!r}, and FR-340 accepts confirmed or refuted"
    )
    try:
        moment_ratio = float(fields["xz_moment_ratio"])
        force_ratio = float(fields["xz_force_ratio"])
    except (KeyError, ValueError):
        pytest.fail(f"{report.name} does not state xz_moment_ratio and xz_force_ratio as numbers")
    assert _xz_verdict(moment_ratio, force_ratio) == verdict, (
        f"{report.name}: the ratios {moment_ratio} and {force_ratio} give "
        f"{_xz_verdict(moment_ratio, force_ratio)} by FR-340 R2, not {verdict}"
    )
    if verdict == "refuted":
        pytest.fail(
            f"{report.name} refutes the XZ moment: the warning every coupled run plans with, "
            "naming RPT-128, and its test are owed (FR-340 R4)"
        )
    page = FSI_PAGE.read_text(encoding="utf-8")
    xz = page.split("moment column of an XZ cut", 1)[-1][:1200]
    assert "RPT-128" in xz, "FR-340 R3: the FSI page's XZ reading cites RPT-128"


#: FsiConfig's fields as 0.33.0 defined them: on a failed truncation test none is added.
V0330_CONFIG_FIELDS = (
    "blade_count",
    "omega_rad_per_s",
    "time_increment_s",
    "blade",
    "stiffness_scale_factor",
    "node_offset_chord_fraction",
    "phases",
    "node_map_file",
    "wing",
)


def test_rpt129_states_the_truncation_test_and_the_tree_holds_its_branch_fr_341():
    """P0340-FSI-MODAL, FR-341: `truncation_test` is `pass` or `fail`, and its branch holds."""
    report, fields = _front_matter(129, "LQ4")
    outcome = fields.get("truncation_test")
    assert outcome in {"pass", "fail"}, (
        f"{report.name}: truncation_test is {outcome!r}, and FR-341 accepts pass or fail"
    )
    if outcome == "pass":
        pytest.fail(
            f"{report.name} passes the truncation test: the option of FR-341 R3, its refusals "
            "(R4) and the tests that the existing routes are byte-identical without it are owed"
        )
    assert tuple(FsiConfig.model_fields) == V0330_CONFIG_FIELDS
    assert tuple(FixedWing.model_fields) == (
        "self_weight",
        "gravity_m_per_s2",
        "span_axis",
        "origin_m",
    )
    assert "coupling_relaxation" in PhaseSchedule.model_fields
    assert dict(ws.FSI_WORKFLOW_STATE) == {
        "unsteady_rotor": ws.FSI_ROTOR_IN_DEBUG,
        "steady": None,
        "unsteady": None,
        "qsteady_rotor": None,
    }
