"""Tier 1: the 0.32.0 inflow tools of package D.

P0320-INFLOW-FLUCTUATION: the per-probe fluctuation of per-step fields.
P0320-INSTALLED-FRAME: a product table mirrored through y = 0.
P0320-INFLOW-HARMONICS: the blade-view harmonics of a custom inflow.
P0320-FILL-INTERIOR: the probes inside the body take the value of the ray outside it.

Every fixture is synthetic and built from the formulas of the requirement.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-250, FR-251, FR-252, FR-253.

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

import pytest

from pyflightstream._errors import ProductExistsError
from pyflightstream.cases import qsteady
from pyflightstream.post import inflow_tools
from pyflightstream.workspace import WorkspaceError
from pyflightstream.workspace import fields as wfields
from pyflightstream.workspace.cli import main

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- fixtures


def _write_steps(
    folder: Path, count: int, *, amplitude: float = 2.0, start: int = 100
) -> list[Path]:
    """K per-step UNSTRUCTURED fields: vx = 40 + a sin(2 pi k / K) at every probe."""
    paths = []
    for k in range(count):
        path = folder / f"P1_field_01_step_{start + k}.inflow.dat"
        value = 40.0 + amplitude * math.sin(2.0 * math.pi * k / count)
        rows = [(2.0, y, z, value, 1.0, -1.0) for y in (-1.0, 1.0) for z in (-0.5, 0.5)]
        path.write_text("\n".join(" ".join(repr(v) for v in r) for r in rows) + "\n")
        paths.append(path)
    return paths


def _steps(paths: list[Path]) -> list[wfields.StepField]:
    return wfields.read_step_fields([str(p) for p in paths])


# ------------------------------------------------- P0320-INFLOW-FLUCTUATION


def test_p0320_inflow_fluctuation_population_std_of_a_sine(tmp_path):
    """P0320-INFLOW-FLUCTUATION: K steps of v0 + a sin(2 pi k/K) give std a/sqrt(2)."""
    report = wfields.fluctuation_report(_steps(_write_steps(tmp_path, 8, amplitude=2.0)))
    assert len(report.rows) == 4
    for x, _y, _z, sx, sy, sz, mag in report.rows:
        assert x == 2.0
        assert sx == pytest.approx(2.0 / math.sqrt(2.0), rel=1e-12)
        assert sy == 0.0
        assert sz == 0.0
        assert mag == pytest.approx(math.sqrt(sx * sx + sy * sy + sz * sz), rel=1e-12)
    text = wfields.render_fluctuation(report)
    assert text.splitlines()[0] == "x,y,z,std_vx,std_vy,std_vz,std_mag"
    peak, rms = wfields.fluctuation_extent(report)
    assert peak == pytest.approx(math.sqrt(2.0), rel=1e-12)
    assert rms == pytest.approx(math.sqrt(2.0), rel=1e-12)


def test_p0320_inflow_fluctuation_refuses_what_is_not_one_survey(tmp_path):
    """P0320-INFLOW-FLUCTUATION: refuses gaps, moved probes and a single steady file."""
    paths = _write_steps(tmp_path, 4, start=1)
    with pytest.raises(WorkspaceError, match="consecutive"):
        wfields.fluctuation_report(_steps([paths[0], paths[1], paths[3]]))
    with pytest.raises(WorkspaceError, match="no fluctuation"):
        wfields.fluctuation_report(_steps(paths[:1]))
    moved = paths[-1]
    lines = moved.read_text().splitlines()
    lines[0] = lines[0].replace("-1.0 -0.5", "-1.0 -0.4999", 1)
    moved.write_text("\n".join(lines) + "\n")
    with pytest.raises(WorkspaceError, match="not row 1"):
        wfields.fluctuation_report(_steps(paths))


def test_p0320_inflow_fluctuation_folds_into_time_mean_with_provenance(tmp_path, capsys):
    """P0320-INFLOW-FLUCTUATION: --fluctuation writes the sidecar beside the mean, hashed."""
    survey = tmp_path / "post"
    survey.mkdir()
    _write_steps(survey, 8)
    common = [
        "field",
        "time-mean",
        str(survey / "P1_field_01_step_*.inflow.dat"),
        "--last",
        "8",
        "--out",
        "p1_mean",
        "--workspace",
        str(tmp_path),
    ]
    assert main([*common, "--fluctuation"]) == 0
    assert "preview" in capsys.readouterr().out
    assert not (tmp_path / "inputs" / "freestreams").exists()
    assert main([*common, "--fluctuation", "--apply"]) == 0
    folder = tmp_path / "inputs" / "freestreams"
    sidecar = folder / "p1_mean.fluctuation.csv"
    assert sidecar.read_text().splitlines()[0] == "x,y,z,std_vx,std_vy,std_vz,std_mag"
    record = json.loads((folder / "p1_mean.provenance.json").read_text())
    named = {each["file"]: each["sha256"] for each in record["sidecars"]}
    assert set(named) == {"inputs/freestreams/p1_mean.fluctuation.csv"}
    assert len(next(iter(named.values()))) == 64


def test_p0320_inflow_fluctuation_only_refuses_without_last(tmp_path, capsys):
    """P0320-INFLOW-FLUCTUATION: --fluctuation-only without --last is refused, exit 2."""
    _write_steps(tmp_path, 4)
    arguments = [
        "field",
        "time-mean",
        str(tmp_path / "P1_field_01_step_*.inflow.dat"),
        "--fluctuation-only",
        "--out",
        "r",
        "--workspace",
        str(tmp_path),
    ]
    assert main(arguments) == 2
    assert "--last" in capsys.readouterr().err
    assert main([*arguments, "--last", "4", "--vinf", "40"]) == 0
    printed = capsys.readouterr().out
    assert "% of V_inf" in printed
    assert "nothing written" in printed
    assert main([*arguments, "--last", "4", "--apply"]) == 0
    assert (tmp_path / "inputs" / "freestreams" / "r.fluctuation.csv").is_file()
    assert not (tmp_path / "inputs" / "freestreams" / "r.dat").exists()


def test_p0320_inflow_fluctuation_only_refuses_more_steps_than_on_disk(tmp_path, capsys):
    """P0320-INFLOW-FLUCTUATION: fewer steps than --last is a refusal."""
    _write_steps(tmp_path, 3)
    code = main(
        [
            "field",
            "time-mean",
            str(tmp_path / "P1_field_01_step_*.inflow.dat"),
            "--fluctuation-only",
            "--last",
            "5",
            "--out",
            "r",
            "--workspace",
            str(tmp_path),
        ]
    )
    assert code == 2
    assert "fewer than" in capsys.readouterr().err


# ------------------------------------------------ P0320-INSTALLED-FRAME

_TABLE = (
    "FX,FY,MX,MY,MZ,CT,CS,CMN,AZIMUTH\n"
    "1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,30\n"
    "-1.5,-2.5,0,4.5,5.5,6.5,7.5,8.5,350\n"
)


def _rows(path: Path, *, skip: int = 0) -> list[dict[str, str]]:
    return list(csv.DictReader(path.read_text().splitlines()[skip:]))


def test_p0320_installed_frame_flips_the_classified_columns(tmp_path):
    """P0320-INSTALLED-FRAME: FY MX MZ CS CMN negated, FX MY CT kept, azimuth mirrored."""
    table = tmp_path / "loads.csv"
    table.write_text(_TABLE)
    written = inflow_tools.to_installed_frame(table)
    assert written == tmp_path / "loads_installed.csv"
    first, second = _rows(written)
    assert [first[c] for c in ("FX", "MY", "CT")] == ["1.0", "4.0", "6.0"]
    assert [float(first[c]) for c in ("FY", "MX", "MZ", "CS", "CMN")] == [
        -2.0,
        -3.0,
        -5.0,
        -7.0,
        -8.0,
    ]
    assert [float(first["AZIMUTH"]), float(second["AZIMUTH"])] == [330.0, 10.0]
    assert float(second["FY"]) == 2.5
    assert second["MX"] == "0"  # a zero is not written as a negative zero
    report = inflow_tools.installed_frame_columns(["FX", "FY", "AZIMUTH", "CT"])
    assert report.flipped == ("FY",)
    assert report.mapped == ("AZIMUTH",)


def test_p0320_installed_frame_is_an_involution_and_never_overwrites(tmp_path):
    """P0320-INSTALLED-FRAME: twice returns the input; an existing target is refused."""
    table = tmp_path / "loads.csv"
    table.write_text(_TABLE)
    once = inflow_tools.to_installed_frame(table)
    twice = inflow_tools.to_installed_frame(once, out=tmp_path / "back.csv")
    assert _rows(twice) == _rows(table)
    with pytest.raises(ProductExistsError, match="refus"):
        inflow_tools.to_installed_frame(table)


def test_p0320_installed_frame_keeps_the_alias_line_and_flips_named_columns(tmp_path):
    """P0320-INSTALLED-FRAME: the one comma-free alias line is kept; --flip adds columns."""
    table = tmp_path / "rotor.csv"
    table.write_text("ROTOR1 = A B\n" + _TABLE)
    written = inflow_tools.to_installed_frame(table, flip=("fx",))
    assert written.read_text().splitlines()[0] == "ROTOR1 = A B"
    assert float(_rows(written, skip=1)[0]["FX"]) == -1.0
    with pytest.raises(ValueError, match="refus.*NOPE"):
        inflow_tools.to_installed_frame(table, out=tmp_path / "x.csv", flip=("NOPE",))


def test_p0320_installed_frame_classification_has_one_home_the_definitions_page():
    """P0320-INSTALLED-FRAME: the page's table and the code's one list are the same list."""
    page = (ROOT / "docs" / "post-processing-definitions.md").read_text(encoding="utf-8")
    section = page.split("## The installed-frame copy", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(r"^\| `([^`]+)` \| (flip|azimuth|keep) \|", section, flags=re.M)
    assert listed, "the definitions page carries no classification table"
    flip = tuple(name for name, kind in listed if kind == "flip")
    azimuth = tuple(name for name, kind in listed if kind == "azimuth")
    assert flip == inflow_tools.FLIPPED_COLUMNS
    assert azimuth == inflow_tools.AZIMUTH_COLUMNS


# ------------------------------------------------ P0320-INFLOW-HARMONICS

RADIUS = 0.5
OMEGA = 2.0 * math.pi * 20.0


def _plane_grid(profile, half: float = 0.75, steps: int = 31):
    values = [-half + 2.0 * half * i / (steps - 1) for i in range(steps)]
    return [(0.0, y, z, *profile(y, z)) for y in values for z in values]


def _uniform_at_aoa(aoa_deg: float, speed: float = 30.0):
    a = math.radians(aoa_deg)
    return _plane_grid(lambda y, z: (speed * math.cos(a), 0.0, speed * math.sin(a)))


def test_p0320_inflow_harmonics_uniform_field_at_aoa_is_first_harmonic():
    """P0320-INFLOW-HARMONICS: a uniform field at 5 deg is all first harmonic."""
    rows = _uniform_at_aoa(5.0)
    (station,) = inflow_tools.blade_view_harmonics(
        rows,
        hub=(0.0, 0.0, 0.0),
        axis=(1.0, 0.0, 0.0),
        omega_rad_s=OMEGA,
        radii_m=[RADIUS],
        chords_m=[0.1],
    )
    assert station.shares[0] > 0.998
    assert sum(station.shares) == pytest.approx(1.0, abs=1e-9)
    assert station.n95 == 1
    w = math.hypot(30.0 * math.cos(math.radians(5.0)), OMEGA * RADIUS)
    small_angle = math.degrees(
        30.0 * math.cos(math.radians(5.0)) * 30.0 * math.sin(math.radians(5.0)) / w**2
    )
    assert station.dalpha_rms_deg == pytest.approx(small_angle / math.sqrt(2.0), rel=0.02)
    assert station.dalpha_half_ptp_deg == pytest.approx(small_angle, rel=0.02)
    # k_1P = Omega c / (2 mean V_rel), k_eff = n95 k_1P
    assert station.k_1p == pytest.approx(OMEGA * 0.1 / (2.0 * w), rel=0.01)
    assert station.k_eff == pytest.approx(station.k_1p, rel=1e-12)


def test_p0320_inflow_harmonics_n95_agrees_with_the_plan_inflow_fft():
    """P0320-INFLOW-HARMONICS: n95 is the plan's own (one home), not a second estimate."""
    rows = _plane_grid(lambda y, z: (30.0 + 4.0 * y * y - 3.0 * z, 0.0, 2.0 * y))
    kwargs = {"hub": (0.0, 0.0, 0.0), "axis": (1.0, 0.0, 0.0), "omega_rad_s": OMEGA}
    radii = [0.2, 0.4, 0.6]
    ours = inflow_tools.blade_view_harmonics(rows, radii_m=radii, **kwargs)
    theirs = qsteady.blade_inflow_harmonics(rows, radii_m=radii, **kwargs)
    assert tuple(s.n95 for s in ours) == theirs
    assert all(s.k_1p is None and s.k_eff is None for s in ours)


def test_p0320_inflow_harmonics_refuses_an_axis_that_is_not_x():
    """P0320-INFLOW-HARMONICS: the profile is a YZ plane, so another axis is refused."""
    with pytest.raises(ValueError, match="refus"):
        inflow_tools.blade_view_harmonics(
            _uniform_at_aoa(5.0),
            hub=(0.0, 0.0, 0.0),
            axis=(0.0, 1.0, 0.0),
            omega_rad_s=OMEGA,
            radii_m=[RADIUS],
        )


def test_p0320_inflow_harmonics_j_map_writes_the_two_tables(tmp_path):
    """P0320-INFLOW-HARMONICS: J through rpm at a fixed V; the two CSVs with their columns."""
    rows = _uniform_at_aoa(5.0)
    diameter = 1.0
    result = inflow_tools.inflow_harmonics_map(
        rows,
        hub=(0.0, 0.0, 0.0),
        axis=(1.0, 0.0, 0.0),
        radii_m=[0.25, 0.4],
        chords_m=[0.1, 0.08],
        diameter_m=diameter,
        v_inf_m_s=30.0,
        advance_ratios=[0.8, 1.2],
        blades=6,
    )
    assert result.suggested_passage_positions == qsteady.suggested_passage_positions(
        max(s.n95 for _j, s in result.stations), 6
    )
    # n = V / (J D): a higher J is a slower rotor, a longer relative-flow angle swing
    (j_low, low), (j_high, high) = result.stations[0], result.stations[2]
    assert (j_low, j_high) == (0.8, 1.2)
    assert low.k_1p > high.k_1p
    full, short = inflow_tools.write_inflow_harmonics(tmp_path, result)
    assert full.name == "inflow_harmonics.csv"
    assert short.name == "inflow_harmonics_J.csv"
    header = full.read_text().splitlines()[0].split(",")
    assert header[:8] == [
        "J",
        "r_over_R",
        "c_over_R",
        "dalpha_rms_deg",
        "dalpha_half_ptp_deg",
        "n95",
        "k_1P",
        "k_eff",
    ]
    assert header[8:] == [f"share_n{i}" for i in range(1, 9)]
    assert short.read_text().splitlines()[0] == "J,r_over_R,n95,k_1P,k_eff,dalpha_rms_deg"
    assert len(full.read_text().splitlines()) == 1 + 4


# ------------------------------------------------ P0320-FILL-INTERIOR


def _rings():
    rows = []
    for k in range(12):
        psi = math.radians(30.0 * k)
        for r in (0.1, 0.2, 0.3, 0.4, 0.6):
            rows.append((1.0, r * math.cos(psi), r * math.sin(psi), 10.0 * r + k, 0.5 * k, -r))
    return wfields.Field(form="UNSTRUCTURED", rows=tuple(rows))


def test_p0320_fill_interior_takes_the_nearest_value_on_the_same_ray():
    """P0320-FILL-INTERIOR: r < r_body copies the smallest radius at r >= r_body on the ray."""
    field = _rings()
    filled, count = wfields.fill_interior(field, r_body_m=0.38)
    assert count == 12 * 3
    for before, after in zip(field.rows, filled.rows, strict=True):
        assert after[:3] == before[:3]
        r = math.hypot(before[1], before[2])
        if r >= 0.38:
            assert after == before
        else:
            ray = round(math.degrees(math.atan2(before[2], before[1])) / 30.0)
            match = next(
                row
                for row in field.rows
                if abs(math.hypot(row[1], row[2]) - 0.4) < 1e-9
                and abs(round(math.degrees(math.atan2(row[2], row[1])) / 30.0) - ray) < 1e-9
            )
            assert after[3:] == match[3:]


def test_p0320_fill_interior_refuses_a_ray_with_no_point_outside_the_body():
    """P0320-FILL-INTERIOR: an interior probe with no partner on its ray is refused."""
    rows = tuple(_rings().rows) + (
        (1.0, 0.05 * math.cos(0.4), 0.05 * math.sin(0.4), 1.0, 1.0, 1.0),
    )
    with pytest.raises(WorkspaceError, match="no point at r >= 0.38"):
        wfields.fill_interior(wfields.Field(form="UNSTRUCTURED", rows=rows), r_body_m=0.38)
    with pytest.raises(WorkspaceError, match="r_body"):
        wfields.fill_interior(_rings(), r_body_m=0.0)


def test_p0320_fill_interior_cli_previews_then_applies_with_provenance(tmp_path, capsys):
    """P0320-FILL-INTERIOR: preview by default, --apply writes the field and its record."""
    source = tmp_path / "in.dat"
    source.write_text(wfields.render_field(_rings()))
    arguments = [
        "field",
        "fill-interior",
        str(source),
        "--r-body",
        "0.38",
        "--out",
        "filled",
        "--workspace",
        str(tmp_path),
    ]
    assert main(arguments) == 0
    printed = capsys.readouterr().out
    assert "36 points replaced" in printed
    assert "nothing written" in printed
    assert not (tmp_path / "inputs").exists()
    assert main([*arguments, "--apply"]) == 0
    folder = tmp_path / "inputs" / "freestreams"
    record = json.loads((folder / "filled.provenance.json").read_text())
    assert record["operation"] == "fill-interior"
    assert record["parameters"]["r_body_m"] == 0.38
    assert record["parameters"]["replaced"] == 36
    assert (folder / "filled.dat").is_file()
    assert main([*arguments, "--apply"]) == 2  # never overwrites unasked
    assert "exists" in capsys.readouterr().err


# ------------------------------------------------ review round (package d reviewer)


def test_p0320_installed_frame_single_column_table_is_a_table_not_an_alias(tmp_path):
    """P0320-INSTALLED-FRAME: a one-column table has no comma, but its header is not an alias."""
    table = tmp_path / "one.csv"
    table.write_text("FY\n5\n-2\n")
    written = inflow_tools.to_installed_frame(table)
    assert written.read_text() == "FY\n-5\n2\n"


def test_p0320_installed_frame_classification_by_behavior_not_only_by_page(tmp_path):
    """P0320-INSTALLED-FRAME: every family flips as stated; a longer name does not match."""
    header = (
        "fy,FY_BLADE1,CNB1,CYAW,CRR,CNB2,CMX,TORQUE,RPM,BETA,FYZ,FX,MY,CT,azimuth_deg,AZIMUTH_END"
    )
    table = tmp_path / "many.csv"
    table.write_text(header + "\n" + ",".join(["2"] * 15) + ",90\n")
    (row,) = _rows(inflow_tools.to_installed_frame(table))
    flipped = {k for k, v in row.items() if v == "-2"}
    assert flipped == {
        "fy",
        "FY_BLADE1",
        "CNB1",
        "CYAW",
        "CRR",
        "CNB2",
        "CMX",
        "TORQUE",
        "RPM",
        "BETA",
    }
    assert row["FYZ"] == row["FX"] == row["MY"] == row["CT"] == "2"
    assert row["AZIMUTH_END"] == "270"


def test_p0320_inflow_harmonics_k_eff_is_n95_times_k_1p_and_sense_keeps_the_size():
    """P0320-INFLOW-HARMONICS: with n95 above 1 k_eff = n95 k_1P; the J map takes either hand."""
    rows = _plane_grid(lambda y, z: (30.0 + 40.0 * y * y - 30.0 * z * z, 0.0, 12.0 * y * z))
    kwargs = {"hub": (0.0, 0.0, 0.0), "axis": (1.0, 0.0, 0.0), "omega_rad_s": OMEGA}
    stations = inflow_tools.blade_view_harmonics(
        rows, radii_m=[0.3, 0.6], chords_m=[0.1, 0.1], **kwargs
    )
    assert max(s.n95 for s in stations) > 1
    for s in stations:
        assert s.k_eff == pytest.approx(s.n95 * s.k_1p, rel=1e-12)
    common = {
        "hub": (0.0, 0.0, 0.0),
        "axis": (1.0, 0.0, 0.0),
        "radii_m": [0.3],
        "chords_m": [0.1],
        "diameter_m": 1.0,
        "v_inf_m_s": 30.0,
        "advance_ratios": [1.0],
        "blades": 6,
    }
    right = inflow_tools.inflow_harmonics_map(rows, sense=1, **common).stations[0][1]
    left = inflow_tools.inflow_harmonics_map(rows, sense=-1, **common).stations[0][1]
    omega = 2.0 * math.pi * 30.0
    assert right.k_1p == pytest.approx(left.k_1p, rel=1e-9)
    assert right.k_1p > 0.0
    w = math.hypot(30.0, omega * 0.3)
    assert right.k_1p == pytest.approx(omega * 0.1 / (2.0 * w), rel=0.1)
    assert left.n95 >= 1


def test_p0320_inflow_harmonics_refuses_wrong_chords_advance_ratio_and_sense():
    """P0320-INFLOW-HARMONICS: a chord count, a non-positive J and a sense of 2 are refused."""
    rows = _uniform_at_aoa(5.0)
    kwargs = {"hub": (0.0, 0.0, 0.0), "axis": (1.0, 0.0, 0.0)}
    with pytest.raises(ValueError, match="refus.*chords"):
        inflow_tools.blade_view_harmonics(
            rows, omega_rad_s=OMEGA, radii_m=[0.2, 0.3], chords_m=[0.1], **kwargs
        )
    common = {"radii_m": [0.3], "diameter_m": 1.0, "v_inf_m_s": 30.0, "blades": 6, **kwargs}
    with pytest.raises(ValueError, match="refus.*advance ratio"):
        inflow_tools.inflow_harmonics_map(rows, advance_ratios=[1.0, 0.0], **common)
    with pytest.raises(ValueError, match="refus.*sense"):
        inflow_tools.inflow_harmonics_map(rows, advance_ratios=[1.0], sense=2, **common)


def test_p0320_inflow_harmonics_shares_use_the_amplitude_floor_of_n95():
    """P0320-INFLOW-HARMONICS: a harmonic under 0.001 degree is in neither n95 nor the shares."""
    kwargs = {
        "hub": (0.0, 0.0, 0.0),
        "axis": (1.0, 0.0, 0.0),
        "omega_rad_s": OMEGA,
        "radii_m": [RADIUS],
    }
    quiet = _plane_grid(lambda y, z: (30.0 + 1e-4 * (y * y - z * z), 0.0, 0.0))
    (below,) = inflow_tools.blade_view_harmonics(quiet, **kwargs)
    assert below.n95 == 0
    assert below.shares == (0.0,) * 8
    loud = _plane_grid(lambda y, z: (30.0 + 1.0 * (y * y - z * z), 0.0, 0.0))
    (above,) = inflow_tools.blade_view_harmonics(loud, **kwargs)
    assert above.n95 == 2
    assert above.shares[1] > 0.99


def test_p0320_inflow_fluctuation_sidecar_hash_is_the_file_and_it_is_never_overwritten(tmp_path):
    """P0320-INFLOW-FLUCTUATION: the recorded sha256 is the file's; a stale sidecar is refused."""
    import hashlib

    survey = tmp_path / "post"
    survey.mkdir()
    _write_steps(survey, 8)
    arguments = [
        "field",
        "time-mean",
        str(survey / "P1_field_01_step_*.inflow.dat"),
        "--last",
        "8",
        "--out",
        "p1_mean",
        "--workspace",
        str(tmp_path),
        "--fluctuation",
        "--apply",
    ]
    assert main(arguments) == 0
    folder = tmp_path / "inputs" / "freestreams"
    record = json.loads((folder / "p1_mean.provenance.json").read_text())
    digest = hashlib.sha256((folder / "p1_mean.fluctuation.csv").read_bytes()).hexdigest()
    assert [each["sha256"] for each in record["sidecars"]] == [digest]
    (folder / "p1_mean.dat").unlink()
    (folder / "p1_mean.provenance.json").unlink()
    assert main(arguments) == 2
    assert (folder / "p1_mean.fluctuation.csv").read_bytes()
