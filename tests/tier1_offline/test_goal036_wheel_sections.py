"""Tier 1: a quasi-steady wheel's section distributions at EVERY clocking (0.31.0, G1 and H2).

Until 0.30.0 a ``qsteady_rotor`` wheel solved at k clockings exported its
sections, sectional loads and section Cp at clocking 0 alone; clockings 1 to
k - 1 exported their loads table only. The radial and the azimuthal loads
are required at every position, so each clocking now deletes the previous
clocking's distributions, turns the wheel, initialises, creates them again in
frames turned with the wheel and fixed there, updates them and exports them
under names that carry the clocking; the post tables every clocking, with a
``CLOCKING`` column and each blade's own azimuth.

The solver facts the builder respects are RPT-091's and 24edb353's: a
distribution's cuts are fixed at its creation over the extent of its surfaces
along the plane's normal in the pose they then hold, N cuts at the middles of
N equal intervals. :func:`_cuts` places them by that rule from the rendered
script, so a frame that did not turn with the blades shows as cuts outside
the blade's span.

Every expected value is worked by hand from the fixture and the definitions,
never read off the implementation.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-183.

from __future__ import annotations

import json
import math
import re
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import PprocSpec, SimCase
from pyflightstream.cases import qsteady as arithmetic
from pyflightstream.post import qsteady as post_qsteady
from pyflightstream.post.axes import clocked_blade_azimuth_deg
from pyflightstream.post.products import (
    read_csv_table,
    write_campaign_products,
    write_sections_table,
)
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_f07_section_distributions import _exports
from tests.tier1_offline.test_goal035_l1_defects import _vertices
from tests.tier1_offline.test_goal035_qsteady_rotor import (
    ROTOR,
    _blade_obj,
    _case,
    _lines,
    _with_obj,
)

FIXTURES = Path(__file__).parent / "fixtures"
BLADES = ("Blade1", "Blade2", "Blade3")

# ------------------------------------------------------------- the script --


def _wheel(tmp_path: Path, *, frame: str = "LOCAL_AXIS", sign: int = 1) -> tuple[SimCase, Path]:
    """Three blades from r 0.2 to 1.0 m, three clockings (0, 40, 80 deg), sections exported.

    ``frame`` LOCAL_AXIS cuts each blade in its own frame; ``PROP_SMRP`` cuts
    blade one in the hub frame, the frame 24edb353's test cut it in.
    """
    obj = _blade_obj(tmp_path / "wheel.obj")
    rotor = ROTOR.model_copy(update={"rpm_sign": sign})
    case = _with_obj(_case(rotor=rotor, PASSAGE_POSITIONS="3", ALPHA_POINT=5.0), obj, BLADES)
    families = ["PROP"] if frame == "LOCAL_AXIS" else ["Blade1"]
    pproc = PprocSpec.model_validate(
        {
            "sections": {
                "count": 8,
                "include_symmetry": False,
                "distributions": [{"families": families, "frame": frame, "planes": ["XZ"]}],
            }
        }
    )
    outputs = ["DP.txt", "DP_cp.txt", "DP_sloads.txt", "DP_log.txt"]
    return case.model_copy(update={"pproc": pproc, "outputs": outputs}), obj


def _frames(lines: list[str]) -> dict[int, tuple[tuple[float, ...], ...]]:
    """Every frame the script places by its axes: index to (origin, x, y, z)."""
    placed: dict[int, tuple[tuple[float, ...], ...]] = {}
    for at, line in enumerate(lines):
        if line != "EDIT_COORDINATE_SYSTEM":
            continue
        values = dict(entry.split(" ", 1) for entry in lines[at + 1 : at + 15])
        number = int(values["FRAME"])

        def vector(prefix: str, values: dict[str, str] = values) -> tuple[float, ...]:
            return tuple(float(values[f"{prefix}{c}"]) for c in "XYZ")

        placed[number] = (
            vector("ORIGIN_"),
            vector("VECTOR_X_"),
            vector("VECTOR_Y_"),
            vector("VECTOR_Z_"),
        )
    return placed


def _distributions(lines: list[str]) -> list[tuple[int, int, str, int, int]]:
    """Each distribution: (line, frame, plane, count, surface index)."""
    found = []
    for at, line in enumerate(lines):
        if line != "NEW_SURFACE_SECTION_DISTRIBUTION":
            continue
        block = dict(entry.split(" ", 1) for entry in lines[at + 1 : at + 7])
        found.append(
            (
                at,
                int(block["FRAME"]),
                block["PLANE"],
                int(block["NUM_SECTIONS"]),
                int(lines[at + 7]),
            )
        )
    return found


def _cuts(lines: list[str], obj: Path) -> list[tuple[int, str, list[float]]]:
    """Where the solver cuts each distribution: (the pose it was created in, blade, cuts).

    The pose is the sum of the ROTATE_SURFACE angles before the distribution, a
    right-hand turn about the shaft (x) through the hub at the origin, which is
    how the builder reads ROTATE_SURFACE. The blade's vertices in that pose are
    projected on the normal of the distribution's plane in its frame, from the
    frame's origin, and N cuts sit at the middles of N equal intervals of that
    extent (the rule RPT-091 measured).
    """
    frames = _frames(lines)
    placed = []
    for at, frame, plane, count, surface in _distributions(lines):
        pose = sum(
            float(line.split()[3]) for line in lines[:at] if line.startswith("ROTATE_SURFACE")
        )
        origin, *axes = frames[frame]
        normal = axes[{"YZ": 0, "XZ": 1, "XY": 2}[plane]]
        turn = math.radians(pose)
        family = BLADES[surface - 1]
        extent = []
        for x, y, z in _vertices(obj, family):
            turned = (
                x,
                y * math.cos(turn) - z * math.sin(turn),
                y * math.sin(turn) + z * math.cos(turn),
            )
            extent.append(sum((a - o) * n for a, o, n in zip(turned, origin, normal, strict=True)))
        low, high = min(extent), max(extent)
        step = (high - low) / count
        placed.append((round(pose), family, [low + (k + 0.5) * step for k in range(count)]))
    return placed


def _commands(lines: list[str]) -> list[str]:
    """The first word of every line the script renders as a command, in order."""
    return [line.split(" ", 1)[0] for line in lines if re.fullmatch(r"[A-Z][A-Z_0-9]+( .*)?", line)]


def test_each_clocking_deletes_turns_creates_updates_and_exports_in_that_order(tmp_path):
    """Clockings 1, 2 and then 0: delete, rotate, initialise, create, solve, update, export.

    Clocking 1 is the first to create any distribution, so it has nothing to
    delete; the init phase creates none. Each clocking exports its sections'
    Cp and their sectional loads under its own name, ``_qs<i>`` before the
    kind's suffix; clocking 0 under the point's own.
    """
    # P0310-G1-EVERY-CLOCKING
    # P0310-G1-NO-ACCUMULATION
    case, _ = _wheel(tmp_path)
    lines, _ = _lines(case)
    watched = {
        "DELETE_ALL_SURFACE_SECTIONS": "delete",
        "ROTATE_SURFACE": "rotate",
        "INITIALIZE_SOLVER": "initialise",
        "NEW_SURFACE_SECTION_DISTRIBUTION": "create",
        "START_SOLVER": "solve",
        "UPDATE_ALL_SURFACE_SECTIONS": "update",
        "EXPORT_ALL_SURFACE_SECTIONS": "export Cp",
        "EXPORT_SURFACE_SECTIONAL_LOADS": "export loads",
    }
    events: list[str] = []
    for command in _commands(lines):
        event = watched.get(command)
        if event is not None and (not events or events[-1] != event):
            events.append(event)
    one = ["rotate", "initialise", "create", "solve", "update", "export Cp", "export loads"]
    assert events == ["initialise", *one, "delete", *one, "delete", *one]
    for command, names in (
        ("EXPORT_ALL_SURFACE_SECTIONS", ["DP_qs01_cp.txt", "DP_qs02_cp.txt", "DP_cp.txt"]),
        (
            "EXPORT_SURFACE_SECTIONAL_LOADS",
            ["DP_qs01_sloads.txt", "DP_qs02_sloads.txt", "DP_sloads.txt"],
        ),
        ("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", ["DP_qs01.txt", "DP_qs02.txt", "DP.txt"]),
    ):
        assert [lines[at + 1] for at, line in enumerate(lines) if line == command] == names


def test_no_distribution_outlives_its_clocking(tmp_path):
    """At every solve the solver holds one set of distributions, three (one per blade)."""
    # P0310-G1-NO-ACCUMULATION
    case, _ = _wheel(tmp_path)
    lines, script = _lines(case)
    live, at_each_solve = 0, []
    for command in _commands(lines):
        if command == "DELETE_ALL_SURFACE_SECTIONS":
            live = 0
        elif command == "NEW_SURFACE_SECTION_DISTRIBUTION":
            live += 1
        elif command == "START_SOLVER":
            at_each_solve.append(live)
    assert at_each_solve == [3, 3, 3]
    # The run records one layout, clocking 0's, in the frames the pproc names.
    assert [block["frame"] for block in script.section_blocks] == [
        "PROP_RMRP1",
        "PROP_RMRP2",
        "PROP_RMRP3",
    ]
    assert [block["families"] for block in script.section_blocks] == [[f] for f in BLADES]


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize("frame", ["LOCAL_AXIS", "PROP_SMRP"])
def test_every_clocking_cuts_every_blade_inside_its_span_at_the_same_stations(
    tmp_path, frame, sign
):
    """Eight cuts of a blade spanning 0.2 to 1.0 m sit at 0.25, 0.35, ... 0.95 m at every clocking.

    The blade spans 0.2 to 1.0 m from the shaft at every clocking, and a
    distribution created in a frame turned with the wheel sees that span along
    its normal: the first and last cuts half a spacing, 0.05 m, inside each
    end. Created at 40 deg in a frame that did not turn, blade one's cuts
    would run from 0.2 cos 40 to 1.0 cos 40 along y, 0.18 to 0.73 m: the
    first below the root and the outer quarter of the blade uncut.
    """
    # P0310-G1-CUTS-IN-SPAN
    # P0310-G1-STATIONS-ALIGNED
    case, obj = _wheel(tmp_path, frame=frame, sign=sign)
    lines, _ = _lines(case)
    placed = _cuts(lines, obj)
    poses = sorted({pose for pose, _, _ in placed})
    assert poses == sorted({0, 40 * sign, 80 * sign})
    blades = BLADES if frame == "LOCAL_AXIS" else ("Blade1",)
    assert len(placed) == 3 * len(blades)
    expected = [0.25 + 0.1 * k for k in range(8)]
    for pose, family, cuts in placed:
        assert 0.2 < cuts[0] and cuts[-1] < 1.0, (pose, family, cuts)
        assert cuts == pytest.approx(expected, abs=1e-9), (pose, family)


def test_the_record_names_each_clocking_s_section_exports_as_the_script_writes_them(tmp_path):
    """The point's record is where the post reads each clocking's files: the script's own names."""
    # P0310-G1-EVERY-CLOCKING
    case, _ = _wheel(tmp_path)
    lines, script = _lines(case)
    record = json.loads(script._pending_input_files["DP_qsteady.json"])
    exports = [position["section_exports"] for position in record["positions"]]
    assert exports == [
        {"sections": "DP_cp.txt", "sectional_loads": "DP_sloads.txt"},
        {"sections": "DP_qs01_cp.txt", "sectional_loads": "DP_qs01_sloads.txt"},
        {"sections": "DP_qs02_cp.txt", "sectional_loads": "DP_qs02_sloads.txt"},
    ]
    written = {lines[at + 1] for at, line in enumerate(lines) if line.startswith("EXPORT_")}
    assert {name for entry in exports for name in entry.values()} <= written
    assert (
        arithmetic.position_export_name("DP_sloads.txt", "_sloads.txt", 1) == "DP_qs01_sloads.txt"
    )


def test_the_one_reader_reads_each_clocking_s_section_exports_and_refuses_a_malformed_one(
    tmp_path,
):
    """The typed record carries ``section_exports`` both ways; a malformed one is a refusal."""
    # P0310-G1-EVERY-CLOCKING
    # P0310-A3-RECORD
    case, _ = _wheel(tmp_path)
    _, script = _lines(case)
    text = str(script._pending_input_files["DP_qsteady.json"])
    folder = tmp_path / "read"
    folder.mkdir()
    (folder / "DP_qsteady.json").write_text(text, encoding="utf-8")
    record = arithmetic.read_qsteady_record(folder / "DP.txt")
    assert record.to_text() == text
    assert [dict(position.section_exports or {}) for position in record.positions] == [
        position["section_exports"] for position in json.loads(text)["positions"]
    ]
    assert post_qsteady.clocking_section_export(record.positions[2], "sectional_loads") == (
        "DP_qs02_sloads.txt"
    )
    assert post_qsteady.clocking_section_export(record.positions[2], "plot_sections_cp") is None
    for spoiled in ({"sections": 1}, {"sections": ""}, ["DP_qs01_cp.txt"], None):
        data = json.loads(text)
        data["positions"][1]["section_exports"] = spoiled
        (folder / "DP_qsteady.json").write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(arithmetic.QsteadyRecordError, match="section_exports"):
            arithmetic.read_qsteady_record(folder / "DP.txt")


# ------------------------------------------------------------- the azimuth --


@pytest.mark.parametrize(
    ("blade", "clocking", "rpm", "expected"),
    [
        (1, 0, 1200.0, 10.0),  # blade one at its datum
        (2, 0, 1200.0, 130.0),  # a third of a turn on
        (3, 2, 1200.0, 10.0 + 240.0 + 80.0),  # clocking 2 of 3 turns 2 * 40 deg
        (2, 1, -1200.0, 10.0 + 120.0 - 40.0),  # a left-hand wheel turns backwards
        (1, 2, -1200.0, 10.0 - 80.0 + 360.0),  # wrapped to one turn
    ],
)
def test_a_blade_of_a_clocked_wheel_is_its_place_plus_the_clocking_in_the_sense_of_rotation(
    blade, clocking, rpm, expected
):
    """psi = datum + (n - 1) 360 / N + sign(rpm) i (360 / N) / k, three blades, three clockings."""
    # P0310-H2-BLADE-AZIMUTH
    got = clocked_blade_azimuth_deg(
        10.0, blade=blade, blades=3, clocking=clocking, positions=3, rpm=rpm
    )
    assert got == pytest.approx(expected, abs=1e-9)


def test_a_clocked_azimuth_that_is_not_stated_is_none_and_never_a_zero():
    # P0310-H2-BLADE-AZIMUTH
    for stated in (
        {"blade": 4},
        {"blade": 0},
        {"blades": 0},
        {"positions": None},
        {"clocking": 1.5},
        {"rpm": 0.0},
        {"blade": True},
    ):
        arguments = {"blade": 1, "blades": 3, "clocking": 1, "positions": 3, "rpm": 1.0, **stated}
        assert clocked_blade_azimuth_deg(10.0, **arguments) is None, stated


# ------------------------------------------------------------- the post --

#: The sectional loads export of the three blades, two stations each, at r
#: 0.25 and 0.75 m with a chord of 0.2 m; ``Fx`` is ``fx`` plus the blade's
#: number, so every block and every clocking is told apart.
_HEAD = (FIXTURES / "fsi/FS_SurfaceSection_Loads_call0002.txt").read_text()


def _sloads(fx: float, offsets: tuple[float, float] = (0.25, 0.75)) -> str:
    numeric = [line for line in _HEAD.splitlines() if re.match(r"\s*[-+]?\d+\.\d+E", line)]
    first = _HEAD.index(numeric[0])
    last = _HEAD.index(numeric[-1]) + len(numeric[-1])
    rows = [
        f"      {r:.4E}, {0.2:.4E}, {0.0:.4E}, {0.0:.4E}, {fx + blade:.4E}, {1.0:.4E}, {0.0:.4E},"
        for blade in (1, 2, 3)
        for r in offsets
    ]
    text = _HEAD[:first] + "\n".join(rows) + _HEAD[last:]
    return re.sub(r"(Number of Surface Sections:\s*)100", r"\g<1>6", text)


_LAYOUT = [
    {"distribution": 1, "families": [blade], "plane": "XZ", "frame": f"PROP_RMRP{n}", "count": 2}
    for n, blade in enumerate(BLADES, start=1)
]


def _record(rpm: float) -> arithmetic.QsteadyRecord:
    """The point's record: three blades at ``rpm``, three clockings of 40 deg."""
    sign = 1.0 if rpm >= 0.0 else -1.0
    return arithmetic.QsteadyRecord(
        case="wheel",
        rotor_alias="PROP",
        blades=3,
        rpm=rpm,
        shaft_frame_axis="X",
        hub_m=(0.0, 0.0, 0.0),
        axis_vector=(1.0, 0.0, 0.0),
        diameter_m=3.0,
        families_general=(),
        families_blades=BLADES,
        blade1_azimuth_deg=0.0,
        positions=tuple(
            arithmetic.QsteadyClocking(
                index=i,
                clocking_deg=40.0 * i,
                rotated_deg=sign * 40.0 * i,
                loads="DP.txt" if i == 0 else f"DP_qs0{i}.txt",
                section_exports={
                    "sectional_loads": "DP_sloads.txt" if i == 0 else f"DP_qs0{i}_sloads.txt"
                },
            )
            for i in range(3)
        ),
        validity=None,
    )


def _tabled(path: Path, text: str) -> Path | None:
    return write_sections_table(path, text, mach=0.1, layout=_LAYOUT, pol="9001")


def _posted(
    tmp_path: Path,
    rpm: float,
    offsets: tuple[float, float] = (0.25, 0.75),
    **shifted: tuple[float, float],
) -> tuple:
    folder = tmp_path / "point"
    folder.mkdir()
    for i in (1, 2):
        (folder / f"DP_qs0{i}_sloads.txt").write_text(
            _sloads(10.0 * i, shifted.get(f"c{i}", offsets)), encoding="utf-8"
        )
    table = _tabled(tmp_path / "DP_sections.csv", _sloads(0.0, offsets))
    assert table is not None
    clocked = post_qsteady.add_clockings_to_sections(table, _record(rpm), folder, tabled=_tabled)
    columns, rows = read_csv_table(table)
    return clocked, list(columns), rows


@pytest.mark.parametrize(
    ("rpm", "azimuths"),
    [
        (1200.0, {0: (0, 120, 240), 1: (40, 160, 280), 2: (80, 200, 320)}),
        (-1200.0, {0: (0, 120, 240), 1: (320, 80, 200), 2: (280, 40, 160)}),
    ],
)
def test_a_wheel_s_sections_table_holds_every_clocking_with_each_blade_s_azimuth(
    tmp_path, rpm, azimuths
):
    """Three clockings of three blades: 18 rows, each with its clocking and its blade's azimuth.

    Blade n sits (n - 1) 120 deg from blade one and clocking i turns the wheel
    by 40 i deg in the sense of rotation, so on a right-hand wheel blade two
    is at 160 deg at clocking 1, and on a left-hand one at 80 deg.
    """
    # P0310-G1-EVERY-CLOCKING
    # P0310-H2-BLADE-AZIMUTH
    # P0310-G1-STATIONS-ALIGNED
    clocked, columns, rows = _posted(tmp_path, rpm)
    assert clocked.missing == {} and clocked.misaligned == []
    assert columns[-1] == "CLOCKING"
    assert len(rows) == 18
    assert [int(row["CLOCKING"]) for row in rows] == [0] * 6 + [1] * 6 + [2] * 6
    for row in rows:
        clocking, blade = int(row["CLOCKING"]), BLADES.index(row["FAMILY"])
        assert float(row["AZIMUTH"]) == pytest.approx(azimuths[clocking][blade])
        assert row["ROTOR"] == "PROP"
        # Each clocking's rows are its own export's: Fx is 10 i plus the blade's number.
        assert float(row["Fx"]) == pytest.approx(10.0 * clocking + blade + 1)
    stations = {
        clocking: [
            (row["FAMILY"], row["Offset"]) for row in rows if int(row["CLOCKING"]) == clocking
        ]
        for clocking in (0, 1, 2)
    }
    assert stations[0] == stations[1] == stations[2]
    assert stations[0] == [(blade, r) for blade in BLADES for r in ("0.25000", "0.75000")]


def test_a_clocking_cut_elsewhere_is_said_and_a_missing_one_is_named(tmp_path):
    """Clocking 2 cut at 0.30 and 0.80 m is kept and said; a clocking with no export is named."""
    # P0310-G1-STATIONS-ALIGNED
    clocked, _, rows = _posted(tmp_path, 1200.0, c2=(0.30, 0.80))
    assert clocked.missing == {}
    assert len(clocked.misaligned) == 1 and "clocking 2" in clocked.misaligned[0]
    assert {int(row["CLOCKING"]) for row in rows} == {0, 1, 2}
    (tmp_path / "point" / "DP_qs01_sloads.txt").unlink()
    table = _tabled(tmp_path / "again.csv", _sloads(0.0))
    assert table is not None
    again = post_qsteady.add_clockings_to_sections(
        table, _record(1200.0), tmp_path / "point", tabled=_tabled
    )
    assert list(again.missing) == [1] and "DP_qs01_sloads.txt" in again.missing[1]
    _, kept = read_csv_table(table)
    assert {int(row["CLOCKING"]) for row in kept} == {0, 2}


def test_the_validity_of_a_clocked_wheel_is_its_point_s_own_solve(tmp_path):
    """k and the shares are read over clocking 0's stations of blade one, never three times over.

    Two stations of blade one, r 0.25 and 1.2 m, chord 0.2 m, at 1200 rev/min
    and 30 m/s: k = 0.2 Omega / (2 sqrt(30^2 + (Omega r)^2)), 0.2872 and
    0.0817, so only the inner one is above 0.1. Each stands for a strip of
    0.475 m (to the midpoint, 0.725 m) and carries Fx = 1 N/m at clocking 0,
    so the thrust share above 0.1 is 50 %. Clockings 1 and 2 carry 11 and 21
    N/m at the same stations; counting them would give another share.
    """
    # P0310-G1-EVERY-CLOCKING
    _posted(tmp_path, 1200.0, offsets=(0.25, 1.2))
    table = tmp_path / "DP_sections.csv"
    validity = post_qsteady.add_reduced_frequency_to_sections(
        table, _record(1200.0), velocity_m_per_s=30.0
    )
    assert validity is not None
    omega = 1200.0 * 2.0 * math.pi / 60.0
    k = [omega * 0.2 / (2.0 * math.hypot(30.0, omega * r)) for r in (0.25, 1.2)]
    assert k[0] > 0.1 > k[1]
    assert validity.values["K_1P_MIN"] == pytest.approx(k[1], abs=1e-6)
    assert validity.values["K_1P_MAX"] == pytest.approx(k[0], abs=1e-6)
    assert validity.values["SPAN_PCT_K_GT_0_1"] == pytest.approx(50.0)
    assert validity.values["THRUST_PCT_K_GT_0_1"] == pytest.approx(50.0)
    _, rows = read_csv_table(table)
    assert len(rows) == 18 and all(row["K_1P"] != "NA" for row in rows)


# ------------------------------------------------------ the campaign's post --


def _campaign(tmp_path: Path, monkeypatch) -> tuple[CampaignWorkspace, Path]:
    """A recorded wheel point of two blades at three clockings, 60 deg apart, posted.

    The recorded exports of test_f07: two sectional stations and two Cp
    sections, one per blade (blade one's at the first, blade two's at the
    second). Clocking i's sectional loads print blade one's Fx as -44.13 - i N.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    pproc = PprocSpec.model_validate(
        {
            "sections": {
                "count": 1,
                "distributions": [
                    {"families": [blade], "frame": "LOCAL_AXIS", "planes": ["XZ"]}
                    for blade in ("Blade1", "Blade2")
                ],
            },
            "products": {"polars": False, "sections": True},
        }
    )
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: pproc)
    sim = workspace.sim_dir("7001")
    sim.mkdir(parents=True, exist_ok=True)
    loads, sloads, cp = _exports()
    outputs = []
    for clocking in range(3):
        stem = "DP" if clocking == 0 else f"DP_qs0{clocking}"
        shifted = sloads.replace("-0.4413E+02", f"-0.{4413 + 100 * clocking}E+02")
        for suffix, text in (("", loads), ("_sloads", shifted), ("_cp", cp)):
            (sim / f"{stem}{suffix}.txt").write_text(text, newline="\n")
            if clocking == 0:
                outputs.append(f"{stem}{suffix}.txt")
    # The record as the builder writes it: the typed record's own text, which
    # the post's one reader reads back.
    quasi = arithmetic.QsteadyRecord(
        case="wheel",
        rotor_alias="PROP",
        blades=2,
        rpm=1200.0,
        shaft_frame_axis="X",
        hub_m=(0.0, 0.0, 0.0),
        axis_vector=(1.0, 0.0, 0.0),
        diameter_m=2.0,
        families_general=(),
        families_blades=("Blade1", "Blade2"),
        blade1_azimuth_deg=0.0,
        positions=tuple(
            arithmetic.QsteadyClocking(
                index=i,
                clocking_deg=60.0 * i,
                rotated_deg=60.0 * i,
                loads="DP.txt" if i == 0 else f"DP_qs0{i}.txt",
                section_exports={
                    kind: ("DP" if i == 0 else f"DP_qs0{i}") + suffix
                    for kind, suffix in (
                        ("sections", "_cp.txt"),
                        ("sectional_loads", "_sloads.txt"),
                    )
                },
            )
            for i in range(3)
        ),
        validity=None,
    )
    (sim / "DP_qsteady.json").write_text(quasi.to_text(), encoding="utf-8")
    blocks = [
        {
            "distribution": k,
            "distribution_families": [blade],
            "families": [blade],
            "plane": "XZ",
            "frame": f"PROP_RMRP{k}",
            "count": 1,
        }
        for k, blade in ((1, "Blade1"), (2, "Blade2"))
    ]
    record = RunRecord(
        run_id="camp/sim_7001/DP",
        sim_id="7001",
        point_name="DP",
        sweep_name="DP",
        point={"alpha": -2.0},
        fs_version_requested="26.124",
        package_version="0.31.0",
        script_sha256="",
        raw_flag=False,
        status=RunStatus.CONVERGED,
        outputs=outputs,
        pproc="p001",
        recipe="qsteady_rotor",
        mach=0.2,
        reference={"SREF": 11.5, "CREF": 1.5, "BREF": 20.0},
        sections_layout=blocks,
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        write_campaign_products(workspace)
    return workspace, workspace.root / "post/products"


def test_the_campaign_post_tables_every_clocking_in_both_section_products(tmp_path, monkeypatch):
    """The sections table and each distribution's sectional loads and Cp hold the three clockings.

    Two blades, three clockings: theta_i = i * 180 / 3 = 60 i deg, so blade
    one is at 0, 60 and 120 deg and blade two at 180, 240 and 300 deg.
    """
    # P0310-G1-EVERY-CLOCKING
    # P0310-H2-BLADE-AZIMUTH
    _, out = _campaign(tmp_path, monkeypatch)
    azimuth = {("Blade1", 0): 0, ("Blade1", 1): 60, ("Blade1", 2): 120}
    azimuth |= {("Blade2", 0): 180, ("Blade2", 1): 240, ("Blade2", 2): 300}
    columns, rows = read_csv_table(out / "sections" / "DP_sections.csv")
    assert "CLOCKING" in columns
    assert [(row["FAMILY"], int(row["CLOCKING"])) for row in rows] == [
        (blade, clocking) for clocking in range(3) for blade in ("Blade1", "Blade2")
    ]
    for row in rows:
        assert float(row["AZIMUTH"]) == pytest.approx(azimuth[row["FAMILY"], int(row["CLOCKING"])])
    blade_one = [float(row["Fx"]) for row in rows if row["FAMILY"] == "Blade1"]
    assert blade_one == pytest.approx([-44.13, -45.13, -46.13])
    for kind in ("sloads", "cp"):
        for blade in ("Blade1", "Blade2"):
            columns, rows = read_csv_table(out / "sections" / f"DP_{kind}_{blade}.csv")
            assert "CLOCKING" in columns, (kind, blade)
            clockings = sorted({int(row["CLOCKING"]) for row in rows})
            assert clockings == [0, 1, 2], (kind, blade)
            for row in rows:
                assert row["FAMILY"] == blade and row["ROTOR"] == "PROP"
                assert float(row["AZIMUTH"]) == pytest.approx(azimuth[blade, int(row["CLOCKING"])])
    _, loads = read_csv_table(out / "sections" / "DP_sloads_Blade1.csv")
    assert [float(row["Fx"]) for row in loads] == pytest.approx([-44.13, -45.13, -46.13])
