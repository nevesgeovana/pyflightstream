"""Tier 1, 0.31.0 (H1): the per-station harmonic product of a rotor point.

Requirement P0310-HARMONICS. For each rotor point, each blade station and
each sectional load quantity, ``pyfs-matrix post`` fits by least squares

    load(psi) = H0 + A1 cos(psi - PHI1) + A2 cos(2 psi - PHI2)

over every sample of that station, ``psi`` being the sample's blade azimuth
as the written sections table states it, and writes
``sections/<point>_harmonics.csv``. The samples of a quasi-steady WHEEL are
every blade at every clocking; those of an ``unsteady_rotor`` point every
blade at every step of its last complete revolution.

EVERY EXPECTED NUMBER is worked by hand from the definitions: the azimuth of
blade n of a wheel of N blades at clocking i of k is
``(n - 1) 360 / N + sense i (360 / N) / k``, that of blade n of an unsteady
rotor at step t is ``datum + sense t 360 / steps_per_revolution + (n - 1) 360 / N``;
the loads are written from the known harmonics at those azimuths, and the
fit must give the harmonics back. Nothing expected is read off the module
under test.
"""

from __future__ import annotations

import json
import math
import re
import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import ProductError, PyflightstreamWarning
from pyflightstream.cases import PprocSpec
from pyflightstream.cases import qsteady as arithmetic
from pyflightstream.post.axes import placed_blade_azimuth_deg
from pyflightstream.post.harmonics import (
    HARMONICS_COLUMNS,
    HarmonicRotor,
    distinct_azimuths,
    fit_harmonics,
    last_complete_revolution,
    station_harmonics,
)
from pyflightstream.post.products import read_csv_table, write_campaign_products
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_f07_section_distributions import _exports
from tests.tier1_offline.test_post_products import _plots_export

FIXTURES = Path(__file__).parent / "fixtures"
_HEAD = (FIXTURES / "fsi/FS_SurfaceSection_Loads_call0002.txt").read_text()
#: The stations of every blade, in metres from the hub; the rotor's diameter is 2 m.
RADII = (0.3, 0.6, 0.9)
DIAMETER = 2.0

#: The known harmonics of each quantity at station radius r: (H0, A1, PHI1, A2, PHI2).
KNOWN = {
    "Fx": lambda r: (10.0 * r, 2.0 * r, 100.0, 0.5 + r, 250.0),
    "Fz": lambda r: (-3.0, 1.5, 310.0, 0.75, 40.0),
    "Moment": lambda r: (0.2, 0.5, 10.0, 0.25, 190.0),
}


def _load(quantity: str, r: float, psi: float) -> float:
    h0, a1, phi1, a2, phi2 = KNOWN[quantity](r)
    return (
        h0 + a1 * math.cos(math.radians(psi - phi1)) + a2 * math.cos(math.radians(2.0 * psi - phi2))
    )


def _sloads(blocks: list[tuple[float | None, float]]) -> str:
    """A sectional loads export of one block per ``(azimuth, offset scale)``, three stations each.

    ``azimuth`` None writes 999 in every load, a sample the fit must never read.
    """
    numeric = [line for line in _HEAD.splitlines() if re.match(r"\s*[-+]?\d+\.\d+E", line)]
    first = _HEAD.index(numeric[0])
    last = _HEAD.index(numeric[-1]) + len(numeric[-1])
    rows = []
    for psi, scale in blocks:
        for r in RADII:
            loads = (
                (999.0, 999.0, 999.0)
                if psi is None
                else tuple(_load(q, r, psi) for q in ("Fx", "Fz", "Moment"))
            )
            cells = (r * scale, 0.2, 0.0, 0.0, *loads)
            rows.append("     " + ",".join(f"{value: .8E}" for value in cells) + ",")
    text = _HEAD[:first] + "\n".join(rows) + _HEAD[last:]
    return re.sub(r"(Number of Surface Sections:\s*)100", rf"\g<1>{len(rows)}", text)


def _layout(blades: int) -> list[dict[str, object]]:
    return [
        {
            "distribution": n,
            "distribution_families": [f"Blade{n}"],
            "families": [f"Blade{n}"],
            "plane": "XZ",
            "frame": f"PROP_RMRP{n}",
            "count": len(RADII),
        }
        for n in range(1, blades + 1)
    ]


def _pproc(blades: int) -> PprocSpec:
    return PprocSpec.model_validate(
        {
            "sections": {
                "count": len(RADII),
                "distributions": [
                    {"families": [f"Blade{n}"], "frame": "LOCAL_AXIS", "planes": ["XZ"]}
                    for n in range(1, blades + 1)
                ],
            },
            "products": {"polars": False, "sections": True},
        }
    )


def _record(**fields: object) -> RunRecord:
    stated: dict[str, object] = dict(
        sim_id="7001",
        point={"alpha": -2.0},
        fs_version_requested="26.124",
        package_version="0.31.0",
        script_sha256="",
        raw_flag=False,
        status=RunStatus.CONVERGED,
        pproc="p001",
        mach=0.2,
        reference={"SREF": 11.5, "CREF": 1.5, "BREF": 20.0},
    )
    stated.update(fields)
    return RunRecord(**stated)  # type: ignore[arg-type]


def _post(workspace: CampaignWorkspace) -> tuple[Path, dict[str, object], list[str]]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        write_campaign_products(workspace)
    out = workspace.root / "post/products"
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    log = (out / "post.log").read_text(encoding="utf-8").splitlines()
    return out, manifest, log


# ------------------------------------------------------------ the wheel --


def _wheel_azimuth(blade: int, blades: int, clocking: int, clockings: int, sign: int) -> float:
    """Blade n of a wheel at clocking i, worked from the definition (not from post.axes)."""
    return ((blade - 1) * 360.0 / blades + sign * clocking * (360.0 / blades) / clockings) % 360.0


def _wheel(
    tmp_path: Path, monkeypatch, *, blades: int, clockings: int, rpm: float
) -> CampaignWorkspace:
    """A recorded wheel point of ``blades`` blades at ``clockings`` clockings, loads known."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    pproc = _pproc(blades)
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: pproc)
    sim = workspace.sim_dir("7001")
    sim.mkdir(parents=True, exist_ok=True)
    loads = _exports()[0]
    sign = 1 if rpm > 0 else -1
    for clocking in range(clockings):
        stem = "DP" if clocking == 0 else f"DP_qs0{clocking}"
        sloads = _sloads(
            [
                (_wheel_azimuth(n, blades, clocking, clockings, sign), 1.0)
                for n in range(1, blades + 1)
            ]
        )
        (sim / f"{stem}.txt").write_text(loads, newline="\n")
        (sim / f"{stem}_sloads.txt").write_text(sloads, newline="\n")
    step = 360.0 / blades / clockings
    quasi = arithmetic.QsteadyRecord(
        case="wheel",
        rotor_alias="PROP",
        blades=blades,
        rpm=rpm,
        shaft_frame_axis="X",
        hub_m=(0.0, 0.0, 0.0),
        axis_vector=(1.0, 0.0, 0.0),
        diameter_m=DIAMETER,
        families_general=(),
        families_blades=tuple(f"Blade{n}" for n in range(1, blades + 1)),
        blade1_azimuth_deg=0.0,
        positions=tuple(
            arithmetic.QsteadyClocking(
                index=i,
                clocking_deg=step * i,
                rotated_deg=sign * step * i,
                loads="DP.txt" if i == 0 else f"DP_qs0{i}.txt",
                section_exports={
                    "sectional_loads": "DP_sloads.txt" if i == 0 else f"DP_qs0{i}_sloads.txt"
                },
            )
            for i in range(clockings)
        ),
        validity=None,
    )
    (sim / "DP_qsteady.json").write_text(quasi.to_text(), encoding="utf-8")
    record = _record(
        run_id="camp/sim_7001/DP",
        point_name="DP",
        sweep_name="DP",
        outputs=["DP.txt", "DP_sloads.txt"],
        recipe="qsteady_rotor",
        sections_layout=_layout(blades),
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    return workspace


def _assert_known(rows: list[dict[str, str]], *, samples: int, distinct: int, tol: float) -> None:
    """Every (quantity, station) row gives back KNOWN, to the tables' printed five decimals."""
    assert len(rows) == len(KNOWN) * len(RADII)
    assert [(row["QUANTITY"], float(row["STATION_R_M"])) for row in rows] == [
        (quantity, r) for quantity in KNOWN for r in RADII
    ]
    for row in rows:
        r = float(row["STATION_R_M"])
        h0, a1, phi1, a2, phi2 = KNOWN[row["QUANTITY"]](r)
        assert row["ROTOR"] == "PROP"
        assert int(row["SAMPLES"]) == samples
        assert int(row["DISTINCT_AZIMUTHS"]) == distinct
        assert float(row["H0"]) == pytest.approx(h0, abs=tol)
        assert float(row["H1_AMP"]) == pytest.approx(a1, abs=tol)
        assert float(row["H1_PHASE_DEG"]) == pytest.approx(phi1, abs=100 * tol)
        assert float(row["H2_AMP"]) == pytest.approx(a2, abs=tol)
        assert float(row["H2_PHASE_DEG"]) == pytest.approx(phi2, abs=100 * tol)
        assert float(row["RESIDUAL_RMS"]) == pytest.approx(0.0, abs=tol)


@pytest.mark.parametrize("rpm", [1200.0, -1200.0])
def test_a_wheel_of_six_blades_at_two_clockings_gives_back_its_harmonics(
    tmp_path, monkeypatch, rpm
):
    """N = 6, k = 2: twelve samples at twelve azimuths, 30 deg apart, per station.

    On a left-hand wheel (negative rpm) clocking 1 turns the wheel -30 deg,
    so blade one is at 330 deg; the loads are written at the azimuth the
    AZIMUTH column states, and the phases come back in that same convention.
    """
    # P0310-HARMONICS
    workspace = _wheel(tmp_path, monkeypatch, blades=6, clockings=2, rpm=rpm)
    out, manifest, _ = _post(workspace)
    sign = 1 if rpm > 0 else -1
    # THE AZIMUTH COLUMN THE FIT READS is the one worked by hand above.
    _, sections = read_csv_table(out / "sections" / "DP_sections.csv")
    for row in sections:
        blade, clocking = int(row["FAMILY"].removeprefix("Blade")), int(row["CLOCKING"])
        assert float(row["AZIMUTH"]) == pytest.approx(
            _wheel_azimuth(blade, 6, clocking, 2, sign), abs=1e-9
        )
    columns, rows = read_csv_table(out / "sections" / "DP_harmonics.csv")
    assert tuple(columns) == HARMONICS_COLUMNS
    assert columns[0] == "POL" and columns[1] == "ALPHA"
    assert {row["POL"] for row in rows} == {"7001"}
    assert {row["MACH"] for row in rows} == {"0.20000"}
    _assert_known(rows, samples=12, distinct=12, tol=1e-4)
    for row in rows:
        assert float(row["R_OVER_R"]) == pytest.approx(float(row["STATION_R_M"]) / 1.0)
    entry = manifest["products"]["sections/DP_harmonics.csv"]
    assert entry["kind"] == "harmonics"
    assert entry["source"] == "wheel clockings"
    assert entry["samples"] == 12
    assert entry["runs"] == ["camp/sim_7001/DP"]


def test_a_left_hand_wheel_s_phase_is_the_azimuth_its_table_states(tmp_path, monkeypatch):
    """A 1P load peaking where AZIMUTH reads 100 deg reads PHI1 = 100 on either hand.

    Blade one of the left-hand wheel sits at 330 deg at clocking 1, not at
    30 deg; a fit that turned the clocking the right-hand way would pair
    each load with another blade's azimuth and give another phase.
    """
    # P0310-HARMONICS
    workspace = _wheel(tmp_path, monkeypatch, blades=6, clockings=2, rpm=-1200.0)
    out, _, _ = _post(workspace)
    _, sections = read_csv_table(out / "sections" / "DP_sections.csv")
    blade_one = [row for row in sections if row["FAMILY"] == "Blade1"]
    assert sorted({float(row["AZIMUTH"]) for row in blade_one}) == [0.0, 330.0]
    _, rows = read_csv_table(out / "sections" / "DP_harmonics.csv")
    fx = [row for row in rows if row["QUANTITY"] == "Fx"]
    assert [float(row["H1_PHASE_DEG"]) for row in fx] == pytest.approx([100.0] * 3, abs=0.01)


def test_a_harmonic_short_of_azimuths_is_na_and_said_once(tmp_path, monkeypatch):
    """N = 2, k = 2 holds four distinct azimuths: 1P is fitted, 2P is NA, said once in post.log."""
    # P0310-HARMONICS
    workspace = _wheel(tmp_path, monkeypatch, blades=2, clockings=2, rpm=1200.0)
    out, _, log = _post(workspace)
    _, rows = read_csv_table(out / "sections" / "DP_harmonics.csv")
    assert len(rows) == len(KNOWN) * len(RADII)
    for row in rows:
        assert int(row["SAMPLES"]) == 4 and int(row["DISTINCT_AZIMUTHS"]) == 4
        assert row["H1_AMP"] != "NA" and row["H1_PHASE_DEG"] != "NA"
        assert row["H2_AMP"] == "NA" and row["H2_PHASE_DEG"] == "NA"
    said = [line for line in log if "DP_harmonics.csv" in line and "harmonic is NA" in line]
    assert len(said) == 1, said
    assert said[0].startswith("WARNING point=DP product=sections/DP_harmonics.csv:")
    assert "2P harmonic is NA in 9 row(s)" in said[0] and "needs 5" in said[0]


# ------------------------------------------------------ an unsteady rotor --

#: Steps per revolution, the datum of blade one, and the stamped window 1 to 14:
#: revolutions 1-6 and 7-12 are complete, 13-14 is not, so the fit reads 7-12.
PER_REVOLUTION = 6
DATUM = 20.0
LAST = 14


def _unsteady_azimuth(blade: int, blades: int, step: int, sign: int) -> float:
    """Blade n of an unsteady rotor at step t, worked from the definition."""
    return (DATUM + sign * step * 360.0 / PER_REVOLUTION + (blade - 1) * 360.0 / blades) % 360.0


def _unsteady(tmp_path: Path, monkeypatch, *, blades: int, rpm: float) -> CampaignWorkspace:
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    pproc = _pproc(blades)
    monkeypatch.setattr(CampaignWorkspace, "resolve_pproc", lambda self, key: pproc)
    sim = workspace.sim_dir("7001")
    sim.mkdir(parents=True, exist_ok=True)
    sign = 1 if rpm > 0 else -1
    (sim / "AL-020.txt").write_text(_exports()[0], newline="\n")
    (sim / "AL-020_plots.txt").write_text(_plots_export(LAST), encoding="utf-8")
    for step in range(1, LAST + 1):
        inside = 7 <= step <= 12
        text = _sloads(
            [
                (_unsteady_azimuth(n, blades, step, sign) if inside else None, 1.0)
                for n in range(1, blades + 1)
            ]
        )
        (sim / f"AL-020_sloads_iteration={step}.txt").write_text(text, newline="\n")
    (sim / "AL-020_sloads.txt").write_text(
        (sim / f"AL-020_sloads_iteration={LAST}.txt").read_text(), newline="\n"
    )
    rotor = {
        "blades": blades,
        "rpm": rpm,
        "blade1_azimuth_deg": DATUM,
        "blade_families": [f"Blade{n}" for n in range(1, blades + 1)],
        "steps_per_revolution": float(PER_REVOLUTION),
        "phase_locked": {"skipped": "not under test"},
        "per_blade": {"skipped": "not under test"},
    }
    record = _record(
        run_id="camp/sim_7001/AL-020",
        point_name="AL-020",
        sweep_name="AL-020",
        outputs=["AL-020.txt", "AL-020_plots.txt", "AL-020_sloads.txt"],
        recipe="unsteady_rotor",
        sections_layout=_layout(blades),
        export_window={"first_step": 1, "time_iterations": LAST, "delta_time_s": 0.01},
        reductions={
            "window_stated": True,
            "time_iterations": LAST,
            "steps_per_revolution": float(PER_REVOLUTION),
            "blades": None,
            "time_average": {"windows": [[1, LAST]], "window_from": "the whole run"},
            "phase_locked": {"skipped": "the row names its rotors"},
            "per_blade": {"skipped": "the row names its rotors"},
            "rotors": {"PROP": rotor},
        },
    )
    monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
    return workspace


@pytest.mark.parametrize("rpm", [1200.0, -1200.0])
def test_an_unsteady_rotor_s_last_revolution_gives_back_its_harmonics(tmp_path, monkeypatch, rpm):
    """Three blades over steps 7 to 12: eighteen samples at six azimuths per station.

    The series states each block's own blade's azimuth (P0310-H2-BLADE-AZIMUTH),
    blade n (n - 1) 120 deg ahead of blade one. Every step outside the last complete revolution
    carries 999 in every load, so a fit that read one would not give back
    the harmonics.
    """
    # P0310-HARMONICS
    workspace = _unsteady(tmp_path, monkeypatch, blades=3, rpm=rpm)
    out, manifest, _ = _post(workspace)
    sign = 1 if rpm > 0 else -1
    _, series = read_csv_table(out / "series" / "AL-020_sections_series.csv")
    for row in series:
        # THE SERIES' AZIMUTH is the block's own blade's, worked by hand.
        blade = int(row["FAMILY"].removeprefix("Blade"))
        assert float(row["AZIMUTH"]) == pytest.approx(
            _unsteady_azimuth(blade, 3, int(row["STEP"]), sign), abs=1e-9
        )
    columns, rows = read_csv_table(out / "sections" / "AL-020_harmonics.csv")
    assert tuple(columns) == HARMONICS_COLUMNS
    _assert_known(rows, samples=18, distinct=6, tol=1e-4)
    # NO REFERENCE TO ASK FOR THE ROTOR'S DIAMETER: r / R is not applicable.
    assert {row["R_OVER_R"] for row in rows} == {"NA"}
    entry = manifest["products"]["sections/AL-020_harmonics.csv"]
    assert entry["kind"] == "harmonics"
    assert entry["source"] == "unsteady last revolution"
    assert entry["samples"] == 18
    assert entry["revolution"] == {"PROP": [7, 12]}


def test_an_unsteady_rotor_short_of_one_revolution_is_named(tmp_path, monkeypatch):
    """At 20 steps per revolution the 14 stamped steps hold no complete revolution: named."""
    # P0310-HARMONICS
    workspace = _unsteady(tmp_path, monkeypatch, blades=3, rpm=1200.0)
    record = workspace.read_manifest()[0]
    record.reductions["rotors"]["PROP"]["steps_per_revolution"] = 20.0  # type: ignore[index]
    out, manifest, log = _post(workspace)
    assert not (out / "sections" / "AL-020_harmonics.csv").exists()
    reason = manifest["skipped"]["sections/AL-020_harmonics.csv#rotor=PROP"]
    assert "not one complete revolution" in reason and "20 steps per revolution" in reason
    assert any("AL-020_harmonics.csv" in line and "complete revolution" in line for line in log)


def test_an_unsteady_rotor_with_no_sections_series_is_named(tmp_path, monkeypatch):
    """No per-step sectional loads, so no series: the harmonics are a named skip.

    Seen on a licensed run: the product was absent and neither products.json
    nor post.log said so (invariant 2).
    """
    # P0310-HARMONICS
    workspace = _unsteady(tmp_path, monkeypatch, blades=3, rpm=1200.0)
    for path in workspace.sim_dir("7001").glob("AL-020_sloads_iteration=*.txt"):
        path.unlink()
    out, manifest, log = _post(workspace)
    assert not (out / "series" / "AL-020_sections_series.csv").exists()
    assert not (out / "sections" / "AL-020_harmonics.csv").exists()
    reason = manifest["skipped"]["sections/AL-020_harmonics.csv"]
    assert "no sections series" in reason and "AL-020_sections_series.csv" in reason
    assert any("AL-020_harmonics.csv" in line and "no sections series" in line for line in log)


# ------------------------------------------------------------ the fit --


def test_the_fit_gives_back_known_harmonics_exactly():
    """Twelve azimuths 30 deg apart (a wheel of 6 blades at 2 clockings), exact to rounding."""
    # P0310-HARMONICS
    azimuths = [30.0 * i for i in range(12)]
    for quantity in KNOWN:
        h0, a1, phi1, a2, phi2 = KNOWN[quantity](0.6)
        fit = fit_harmonics(azimuths, [_load(quantity, 0.6, psi) for psi in azimuths])
        assert (fit.samples, fit.distinct) == (12, 12)
        assert fit.h0 == pytest.approx(h0, rel=1e-12, abs=1e-12)
        assert fit.h1_amp == pytest.approx(a1, rel=1e-12)
        assert fit.h1_phase_deg == pytest.approx(phi1, rel=1e-12)
        assert fit.h2_amp == pytest.approx(a2, rel=1e-12)
        assert fit.h2_phase_deg == pytest.approx(phi2, rel=1e-12)
        assert fit.residual_rms == pytest.approx(0.0, abs=1e-12)


def test_the_na_rules_follow_the_distinct_azimuths():
    """1P needs three distinct azimuths and 2P five; 0 and 360 deg are one azimuth."""
    # P0310-HARMONICS
    assert distinct_azimuths([0.0, 360.0, 180.0]) == 2
    assert distinct_azimuths([0.0, 359.9999999, 120.0]) == 2
    two = fit_harmonics([0.0, 360.0, 180.0, 180.0], [1.0, 3.0, 5.0, 7.0])
    assert two.distinct == 2 and two.h1_amp is None and two.h2_amp is None
    assert two.h0 == pytest.approx(4.0)
    assert two.residual_rms == pytest.approx(math.sqrt(5.0))
    three = fit_harmonics([0.0, 120.0, 240.0], [3.0, 0.0, 0.0])
    assert three.h1_amp == pytest.approx(2.0) and three.h1_phase_deg == pytest.approx(0.0)
    assert three.h2_amp is None
    four = fit_harmonics([0.0, 90.0, 180.0, 270.0], [1.0, 2.0, 3.0, 4.0])
    assert four.h1_amp is not None and four.h2_amp is None and four.h2_phase_deg is None
    five = fit_harmonics([0.0, 72.0, 144.0, 216.0, 288.0], [1.0, 2.0, 3.0, 4.0, 5.0])
    assert five.h2_amp is not None and five.residual_rms == pytest.approx(0.0, abs=1e-12)


def test_a_fit_without_one_value_per_azimuth_raises_the_catalogued_error():
    """The refusal is a ProductError, which is still a ValueError (FR-39)."""
    # P0310-HARMONICS
    with pytest.raises(ProductError, match="one value per azimuth"):
        fit_harmonics([0.0, 120.0], [1.0])
    with pytest.raises(ValueError, match="at least one sample"):
        fit_harmonics([], [])


def test_the_last_complete_revolution_is_counted_from_the_first_step():
    # P0310-HARMONICS
    assert last_complete_revolution(1, 14, 6.0) == (7, 12)
    assert last_complete_revolution(1, 12, 6.0) == (7, 12)
    assert last_complete_revolution(3, 13, 4.0) == (7, 10)
    assert last_complete_revolution(3, 14, 4.0) == (11, 14)
    assert last_complete_revolution(1, 5, 6.0) is None


def test_a_blade_is_placed_ahead_of_blade_one_whatever_the_sense():
    """Blade n of N sits (n - 1) 360 / N deg ahead of blade one, wrapped."""
    # P0310-HARMONICS
    assert placed_blade_azimuth_deg(300.0, blade=1, blades=3) == pytest.approx(300.0)
    assert placed_blade_azimuth_deg(300.0, blade=2, blades=3) == pytest.approx(60.0)
    assert placed_blade_azimuth_deg(300.0, blade=3, blades=3) == pytest.approx(180.0)
    assert placed_blade_azimuth_deg(300.0, blade=0, blades=3) is None
    assert placed_blade_azimuth_deg(None, blade=1, blades=3) is None


def _rows(offsets: dict[tuple[int, int], float] | None = None, counts: int = 3):
    """A wheel table of two blades at three clockings of 60 deg; Fx = 5 + cos(psi - 45)."""
    offsets = offsets or {}
    columns = ("POL", "FAMILY", "PLANE", "ROTOR", "AZIMUTH", "ALPHA", "Offset", "Fx", "CLOCKING")
    rows = []
    for clocking in range(3):
        for blade in (1, 2):
            psi = (blade - 1) * 180.0 + clocking * 60.0
            stations = RADII if (clocking, blade) != (2, 2) else RADII[:counts]
            for j, r in enumerate(stations, start=1):
                radius = r + offsets.get((clocking, blade), 0.0) * (j == 2)
                rows.append(
                    {
                        "POL": "1",
                        "FAMILY": f"Blade{blade}",
                        "PLANE": "XZ",
                        "ROTOR": "PROP",
                        "AZIMUTH": f"{psi:.5f}",
                        "ALPHA": "0.0",
                        "Offset": f"{radius:.7f}",
                        "Fx": f"{5.0 + math.cos(math.radians(psi - 45.0)):.9f}",
                        "CLOCKING": str(clocking),
                    }
                )
    return columns, rows


ROTOR = HarmonicRotor(
    alias="PROP", blades=(("Blade1",), ("Blade2",)), diameter_m=2.0, azimuth_is_blade_one=False
)


def test_a_station_off_its_radius_is_a_named_skip_and_the_others_are_fitted():
    """Station 2 of blade two at clocking 1 sits 1e-5 m out (1e-5 of 0.9 m > 1e-6): named."""
    # P0310-HARMONICS
    columns, rows = _rows({(1, 2): 1e-5})
    result = station_harmonics(columns, rows, {"PROP": ROTOR}, sample_column="CLOCKING")
    assert list(result.skipped) == ["#rotor=PROP#station=2"]
    assert "station 2" in result.skipped["#rotor=PROP#station=2"]
    assert [(quantity, radius) for _, quantity, radius, _, _ in result.rows] == [
        ("Fx", 0.3),
        ("Fx", 0.9),
    ]
    fit = result.rows[0][4]
    assert (fit.samples, fit.distinct) == (6, 6)
    assert fit.h1_amp == pytest.approx(1.0, abs=1e-8)
    assert fit.h1_phase_deg == pytest.approx(45.0, abs=1e-6)
    # WITHIN THE TOLERANCE, 1e-7 m on 0.9 m, the station is matched.
    columns, rows = _rows({(1, 2): 1e-7})
    close = station_harmonics(columns, rows, {"PROP": ROTOR}, sample_column="CLOCKING")
    assert close.skipped == {} and len(close.rows) == 3


def test_blocks_of_other_station_counts_skip_the_rotor_by_name():
    # P0310-HARMONICS
    columns, rows = _rows(counts=2)
    result = station_harmonics(columns, rows, {"PROP": ROTOR}, sample_column="CLOCKING")
    assert result.rows == []
    assert "#rotor=PROP" in result.skipped and "[2, 3]" in result.skipped["#rotor=PROP"]


def test_the_na_note_is_one_per_rotor_and_harmonic():
    """Two clockings of two blades at 0 and 180 deg: two azimuths, both harmonics NA, two notes."""
    # P0310-HARMONICS
    columns, rows = _rows()
    kept = [row for row in rows if row["CLOCKING"] == "0"]
    result = station_harmonics(columns, kept, {"PROP": ROTOR}, sample_column="CLOCKING")
    assert len(result.rows) == 3
    assert all(fit.h1_amp is None and fit.h2_amp is None for *_, fit in result.rows)
    assert len(result.notes) == 2
    assert "1P harmonic is NA in 3 row(s)" in result.notes[0]
    assert "2P harmonic is NA in 3 row(s)" in result.notes[1]
