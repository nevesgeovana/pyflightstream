"""Tier 1: the noise post product, work package E1 (P0320-NOISE-POST, FR-260 to FR-264).

The fixture ``data/acoustic_signals_probe_a1.txt`` is the export of the licensed
round-1 probe on a tier-3 library geometry (three observers, 16 samples each).
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-261, FR-262, FR-263, FR-290.

from __future__ import annotations

import csv
import math
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream._errors import ProductError
from pyflightstream.cases.acoustics import AcousticSignal
from pyflightstream.post import acoustics
from pyflightstream.post import harmonics as _harmonics
from pyflightstream.post._rotor_products import _acoustic_products

FIXTURE = Path(__file__).parent / "data" / "acoustic_signals_probe_a1.txt"


def _cosine(
    observer: str,
    frequency: float,
    amplitude: float,
    samples: int = 200,
    rate: float = 1000.0,
    mean: float = 0.0,
    pos=(1.0, 0.0, 0.0),
):
    times = tuple(0.05 + n / rate for n in range(samples))
    pressure = tuple(
        mean + amplitude * math.cos(2 * math.pi * frequency * (t - 0.05)) for t in times
    )
    return AcousticSignal(observer, *pos, times, pressure)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_p0320_noise_post_reads_the_real_export_fr_260():
    """P0320-NOISE-POST: the round-1 export is read into one signal per observer."""
    signals = acoustics.read_acoustic_signals(FIXTURE)
    assert [s.observer for s in signals] == ["PYFS_OBS1", "Observer 2", "Observer 3"]
    assert (signals[0].x_m, signals[0].y_m, signals[0].z_m) == (0.0, 10.0, 0.0)
    assert (signals[2].x_m, signals[2].y_m, signals[2].z_m) == (5.0, 0.0, 10.0)
    first = signals[0]
    assert first.time_s[0] == pytest.approx(0.05)
    assert first.pressure_pa[0] == pytest.approx(-0.04860909185659823)
    assert len(first.time_s) == len(first.pressure_pa) > 10


def test_p0320_noise_post_refuses_a_bad_export_fr_260(tmp_path):
    """P0320-NOISE-POST: a file that is not the export is refused naming the line."""
    with pytest.raises(ProductError, match="cannot be read"):
        acoustics.read_acoustic_signals(tmp_path / "missing.txt")
    empty = tmp_path / "empty.txt"
    empty.write_text("\n", encoding="utf-8")
    with pytest.raises(ProductError, match="hold no observer"):
        acoustics.read_acoustic_signals(empty)
    bad = tmp_path / "bad.txt"
    bad.write_text("Observer: a\nPosition: 0,0,0\nColumns: Observer time (sec), PL (Pa)\n1 2\n")
    with pytest.raises(ProductError, match="line 3.*no PO column"):
        acoustics.read_acoustic_signals(bad)
    bad.write_text("Observer: a\nPosition: 0,0,0\nColumns: Observer time (sec), PO (Pa)\n1 x\n")
    with pytest.raises(ProductError, match="line 4.*not numbers"):
        acoustics.read_acoustic_signals(bad)
    bad.write_text("Observer: a\nPosition: 0,0,0\nColumns: Observer time (sec), PO (Pa)\n")
    with pytest.raises(ProductError, match="no samples"):
        acoustics.read_acoustic_signals(bad)


def test_p0320_noise_post_spectrum_of_a_cosine_fr_261():
    """P0320-NOISE-POST: a cosine of amplitude A on a bin reads A; the sampling is stated."""
    signal = _cosine("m", frequency=50.0, amplitude=2.0, mean=0.5)
    spectrum = acoustics.spectrum_of(signal)
    assert spectrum.sample_rate_hz == pytest.approx(1000.0)
    assert spectrum.df_hz == pytest.approx(5.0)
    index = round(50.0 / spectrum.df_hz)
    assert spectrum.frequency_hz[index] == pytest.approx(50.0)
    assert spectrum.amplitude_pa[index] == pytest.approx(2.0)
    assert spectrum.amplitude_pa[0] == pytest.approx(0.5)
    assert max(a for k, a in enumerate(spectrum.amplitude_pa) if k not in (0, index)) < 1e-9
    assert len(spectrum.frequency_hz) == 200 // 2 + 1


def test_p0320_noise_post_refuses_a_nonuniform_time_fr_261():
    """P0320-NOISE-POST: no spectrum from a record whose step is not constant (refuses)."""
    signal = AcousticSignal("m", 0, 0, 0, (0.0, 0.1, 0.5, 0.6), (1.0, 2.0, 3.0, 4.0))
    with pytest.raises(ProductError, match="not uniformly stepped"):
        acoustics.spectrum_of(signal)
    with pytest.raises(ProductError, match="too few"):
        acoustics.spectrum_of(AcousticSignal("m", 0, 0, 0, (0.0,), (1.0,)))


def test_p0320_noise_post_oaspl_fr_262():
    """P0320-NOISE-POST: OASPL is 20 log10(p_rms / 20 uPa); a silent record is NA."""
    signal = _cosine("m", frequency=50.0, amplitude=math.sqrt(2.0) * 2e-5 * 10.0, mean=3.0)
    assert acoustics.oaspl_db(signal) == pytest.approx(20.0 * math.log10(10.0), abs=1e-6)
    silent = AcousticSignal("s", 0, 0, 0, (0.0, 1.0), (0.0, 0.0))
    assert acoustics.oaspl_db(silent) is None
    real = acoustics.read_acoustic_signals(FIXTURE)[0]
    rms = math.sqrt(
        sum((p - sum(real.pressure_pa) / len(real.pressure_pa)) ** 2 for p in real.pressure_pa)
        / len(real.pressure_pa)
    )
    assert acoustics.oaspl_db(real) == pytest.approx(20.0 * math.log10(rms / 20e-6))


def test_p0320_noise_post_blade_passage_harmonics_fr_263():
    """P0320-NOISE-POST: harmonics at n * blades * rpm / 60, NA beyond what the record resolves."""
    # 2 blades at 1500 rpm: 50 Hz; a 50 Hz and a 100 Hz component of the record
    times = tuple(0.05 + n / 1000.0 for n in range(200))
    pressure = tuple(
        2.0 * math.cos(2 * math.pi * 50.0 * (t - 0.05))
        + 0.5 * math.cos(2 * math.pi * 100.0 * (t - 0.05))
        for t in times
    )
    spectrum = acoustics.spectrum_of(AcousticSignal("m", 0, 0, 0, times, pressure))
    rows = acoustics.blade_passage_harmonics(spectrum, blades=2, rpm=1500.0, harmonics=4)
    assert [r[0] for r in rows] == [1, 2, 3, 4]
    assert [r[1] for r in rows] == pytest.approx([50.0, 100.0, 150.0, 200.0])
    assert rows[0][3] == pytest.approx(2.0)
    assert rows[1][3] == pytest.approx(0.5)
    assert rows[2][3] == pytest.approx(0.0, abs=1e-9)
    # above Nyquist (500 Hz): 2 * 3000 rpm / 60 = 100 Hz base, harmonic 6 at 600 Hz
    far = acoustics.blade_passage_harmonics(spectrum, blades=2, rpm=15000.0, harmonics=2)
    assert far[0][1] == pytest.approx(500.0) and far[0][3] is not None
    assert far[1][1] == pytest.approx(1000.0) and far[1][3] is None and far[1][4] is None
    # a record shorter than one period of the harmonic
    slow = acoustics.blade_passage_harmonics(spectrum, blades=1, rpm=6.0, harmonics=1)
    assert slow[0][3] is None
    with pytest.raises(ProductError, match="no blade-passage frequency"):
        acoustics.blade_passage_harmonics(spectrum, blades=0, rpm=100.0)


def _arc(count: int, radius: float = 10.0, centre=(1.0, 2.0, 3.0)):
    return [
        _cosine(
            f"o{i}",
            50.0,
            1.0,
            pos=(
                centre[0],
                centre[1] + radius * math.cos(math.radians(30 * i)),
                centre[2] + radius * math.sin(math.radians(30 * i)),
            ),
        )
        for i in range(count)
    ]


def test_p0320_noise_post_arc_directivity_fr_264():
    """P0320-NOISE-POST: observers on an arc are detected, with centre, radius and angles."""
    fit = acoustics.arc_of(_arc(5))
    assert fit is not None
    assert fit.radius_m == pytest.approx(10.0)
    assert fit.center == pytest.approx((1.0, 2.0, 3.0))
    assert fit.angle_deg == pytest.approx([0.0, 30.0, 60.0, 90.0, 120.0])
    assert acoustics.arc_of(_arc(3)) is None  # three points prove no arc
    scattered = _arc(4)
    scattered[2] = _cosine("x", 50.0, 1.0, pos=(1.0, 2.0, 30.0))
    assert acoustics.arc_of(scattered) is None
    line = [_cosine(f"l{i}", 50.0, 1.0, pos=(float(i), 0.0, 0.0)) for i in range(5)]
    assert acoustics.arc_of(line) is None
    assert acoustics.arc_of(acoustics.read_acoustic_signals(FIXTURE)) is None


def test_p0320_noise_post_writes_the_products_fr_261_to_fr_264(tmp_path):
    """P0320-NOISE-POST: the writer's files, columns and NA lines."""
    signals = _arc(5)
    made = acoustics.write_acoustic_products(
        signals, tmp_path, stem="P1", rotors={"main": (2, 1500.0)}
    )
    names = sorted(p.name for p in made.files)
    assert "P1_00_o0_pressure.csv" not in names and "P1_01_o0_pressure.csv" in names
    assert "P1_05_o4_spectrum.csv" in names
    assert {
        "P1_acoustics_summary.csv",
        "P1_acoustics_bpf.csv",
        "P1_acoustics_directivity.csv",
    } <= set(names)
    summary = _rows(tmp_path / "P1_acoustics_summary.csv")
    assert [r["OBSERVER"] for r in summary] == [f"o{i}" for i in range(5)]
    assert float(summary[0]["SAMPLE_RATE_HZ"]) == pytest.approx(1000.0)
    assert float(summary[0]["OASPL_DB"]) == pytest.approx(
        20 * math.log10(1.0 / math.sqrt(2) / 20e-6)
    )
    bpf = _rows(tmp_path / "P1_acoustics_bpf.csv")
    assert len(bpf) == 5 * 4 and bpf[0]["ROTOR"] == "main"
    assert float(bpf[0]["AMPLITUDE_PA"]) == pytest.approx(1.0)
    directivity = _rows(tmp_path / "P1_acoustics_directivity.csv")
    assert [float(r["ANGLE_DEG"]) for r in directivity] == pytest.approx([0, 30, 60, 90, 120])
    pressure = _rows(tmp_path / "P1_01_o0_pressure.csv")
    assert list(pressure[0]) == ["TIME_S", "PRESSURE_PA"] and len(pressure) == 200
    assert made.notes == []


def test_p0320_noise_post_na_and_notes_when_the_record_lacks_blades_fr_263(tmp_path):
    """P0320-NOISE-POST: no blades or speed gives NA harmonics and a post-log line."""
    signals = list(acoustics.read_acoustic_signals(FIXTURE))
    made = acoustics.write_acoustic_products(signals, tmp_path, stem="P2")
    assert any("blade-passage harmonics are NA" in note for note in made.notes)
    bpf = _rows(tmp_path / "P2_acoustics_bpf.csv")
    assert len(bpf) == 3 * 4
    assert {r["FREQUENCY_HZ"] for r in bpf} == {"NA"} and {r["AMPLITUDE_PA"] for r in bpf} == {"NA"}
    assert not any(p.name.endswith("directivity.csv") for p in made.files)
    summary = _rows(tmp_path / "P2_acoustics_summary.csv")
    assert float(summary[0]["SAMPLE_RATE_HZ"]) == pytest.approx(1 / 0.009375)
    partial = acoustics.write_acoustic_products(
        signals[:1], tmp_path / "b", stem="P3", rotors={"r": (None, 900.0)}
    )
    assert any("rotor 'r' states blades=None" in note for note in partial.notes)
    ragged = AcousticSignal("rag", 0, 0, 0, (0.0, 0.1, 0.5, 0.6), (1.0, 2.0, 3.0, 4.0))
    made = acoustics.write_acoustic_products(
        [ragged], tmp_path / "c", stem="P4", rotors={"r": (2, 900.0)}
    )
    assert any("not uniformly stepped" in note for note in made.notes)
    assert _rows(tmp_path / "c" / "P4_acoustics_summary.csv")[0]["OASPL_DB"] != "NA"
    assert not any(p.name.endswith("_spectrum.csv") for p in made.files)


def _record(listed):
    """A record the way E2 makes it: the export is one of its outputs, named by the suffix."""
    outputs = ["P1.txt", "P1.vtk"] + ([listed] if listed else [])
    return SimpleNamespace(run_id="run-1", outputs=outputs)


def _rotor():
    return {"main": (_harmonics.HarmonicRotor("main", (("a",), ("b",)), None, False), None)}


def test_p0320_noise_post_the_post_stage_hook_fr_264(tmp_path):
    """P0320-NOISE-POST: a record that lists an export gets the products and manifest entries."""
    sim = tmp_path / "sim"
    sim.mkdir()
    (sim / "P1_acoustic_signals.txt").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    out = tmp_path / "post"
    skipped: dict[str, str] = {}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        files, names = _acoustic_products(
            _record("P1_acoustic_signals.txt"),
            sim_dir=sim,
            stem="P1",
            out=out,
            rotors=_rotor(),
            clocks={"main": {"rpm": 1200.0}},
            target=lambda p: p,
            skipped=skipped,
        )
    assert skipped == {} and files
    assert "acoustics/P1_acoustics_summary.csv" in names
    assert names["acoustics/P1_acoustics_summary.csv"]["runs"] == ["run-1"]
    assert all(path.is_file() for path in files)
    bpf = _rows(out / "acoustics" / "P1_acoustics_bpf.csv")
    assert bpf[0]["ROTOR"] == "main" and bpf[0]["FREQUENCY_HZ"] == "40.00000"
    assert not any("blade-passage harmonics are NA" in str(w.message) for w in caught)


def test_p0320_noise_post_the_hook_asks_nothing_of_a_plain_record_and_never_blocks_fr_264(tmp_path):
    """P0320-NOISE-POST: no listing is silent; an unreadable export is skipped with a warning."""
    skipped: dict[str, str] = {}
    quiet = _acoustic_products(
        _record(None),
        sim_dir=tmp_path,
        stem="P1",
        out=tmp_path,
        rotors={},
        clocks={},
        target=lambda p: p,
        skipped=skipped,
    )
    assert quiet == ([], {}) and skipped == {}
    with pytest.warns(Warning, match="acoustics"):
        files, names = _acoustic_products(
            _record("gone_acoustic_signals.txt"),
            sim_dir=tmp_path,
            stem="P1",
            out=tmp_path,
            rotors={},
            clocks={},
            target=lambda p: p,
            skipped=skipped,
        )
    assert (
        (files, names) == ([], {})
        and "acoustics" in skipped
        and "cannot be read" in skipped["acoustics"]
    )


def test_p0320_noise_post_counter_rotation_reads_the_speed_magnitude_fr_263(tmp_path):
    """P0320-NOISE-POST: a negative rpm (opposite rotation) still gives the harmonics."""
    signal = _cosine("m", frequency=50.0, amplitude=2.0)
    spectrum = acoustics.spectrum_of(signal)
    rows = acoustics.blade_passage_harmonics(spectrum, blades=2, rpm=-1500.0, harmonics=1)
    assert rows[0][1] == pytest.approx(50.0) and rows[0][3] == pytest.approx(2.0)
    made = acoustics.write_acoustic_products(
        [signal], tmp_path, stem="P1", rotors={"main": (2, -1500.0)}
    )
    bpf = _rows(tmp_path / "P1_acoustics_bpf.csv")
    assert float(bpf[0]["AMPLITUDE_PA"]) == pytest.approx(2.0)
    assert made.notes == []


def test_p0320_noise_post_nyquist_bin_and_odd_count_fr_261():
    """P0320-NOISE-POST: the Nyquist bin of an even count and the last bin of an odd count."""
    even = _cosine("e", frequency=500.0, amplitude=1.5, samples=200)
    spectrum = acoustics.spectrum_of(even)
    assert spectrum.frequency_hz[-1] == pytest.approx(500.0)
    assert spectrum.amplitude_pa[-1] == pytest.approx(1.5)
    odd = _cosine("o", frequency=50.0, amplitude=2.0, samples=201, rate=1005.0)
    spectrum = acoustics.spectrum_of(odd)
    assert len(spectrum.frequency_hz) == 101
    assert spectrum.amplitude_pa[10] == pytest.approx(2.0)
    assert spectrum.amplitude_pa[-1] < 1e-9


def test_p0320_noise_post_arc_angle_direction_follows_the_second_observer_fr_264():
    """P0320-NOISE-POST: angles increase toward observer 2 whichever way the arc is walked."""
    forward = _arc(5)
    orders = (forward, forward[::-1], [forward[2], forward[3], forward[1], forward[0], forward[4]])
    for signals in orders:
        fit = acoustics.arc_of(signals)
        assert fit is not None
        assert fit.angle_deg[0] == pytest.approx(0.0)
        assert fit.angle_deg[1] == pytest.approx(
            30.0 * abs(int(signals[1].observer[1:]) - int(signals[0].observer[1:]))
        )


def test_p0320_noise_post_an_unwritable_product_never_blocks_the_post_fr_264(tmp_path):
    """P0320-NOISE-POST: a write that fails is skipped with a warning, not raised."""
    sim = tmp_path / "sim"
    sim.mkdir()
    (sim / "e_acoustic_signals.txt").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    blocker = tmp_path / "post"
    blocker.write_text("a file where the products folder should be", encoding="utf-8")
    skipped: dict[str, str] = {}
    with pytest.warns(Warning, match="acoustics"):
        files, names = _acoustic_products(
            _record("e_acoustic_signals.txt"),
            sim_dir=sim,
            stem="P1",
            out=blocker,
            rotors={},
            clocks={},
            target=lambda p: p,
            skipped=skipped,
        )
    assert (files, names) == ([], {}) and "acoustics" in skipped


def _unsteady_rotor_workspace(tmp_path, *, listed: bool):
    """A workspace with one unsteady_rotor point whose record lists (or not) the E2 export."""
    from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    outputs = ["p.txt", "p.vtk"] + (["p_acoustic_signals.txt"] if listed else [])
    record = RunRecord(
        run_id="camp/sim_7010/AL+000",
        sim_id="7010",
        point_name="AL+000",
        fs_version_requested="26.124",
        status=RunStatus.CONVERGED,
        recipe="unsteady_rotor",
        outputs=outputs,
        package_version="0.32.0",
        script_sha256="",
        raw_flag=False,
    )
    sim = workspace.sim_dir(record.sim_id)
    sim.mkdir(parents=True, exist_ok=True)
    (sim / "p.txt").write_text("native export", encoding="utf-8")
    (sim / "p_acoustic_signals.txt").write_text(FIXTURE.read_text(encoding="utf-8"), "utf-8")
    workspace.append_record(record)
    return workspace


def test_p0320_noise_post_the_record_lists_the_export_as_an_output_fr_290(tmp_path):
    """P0320-NOISE-POST, P0320-NOISE-COLLECT: end to end, the export E2 records among the
    outputs of an unsteady_rotor point reaches write_campaign_products, and the noise
    product files and their manifest entries appear; a record that does not list it
    asks for no acoustics. Reverting the reader to a field RunRecord lacks fails this."""
    import json

    from pyflightstream.post.products import write_campaign_products

    workspace = _unsteady_rotor_workspace(tmp_path, listed=True)
    write_campaign_products(workspace, overwrite=True)
    out = workspace.products_dir(None)
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    noise = {k: v for k, v in manifest["products"].items() if v.get("kind") == "acoustics"}
    assert "acoustics/p_acoustics_summary.csv" in noise, sorted(manifest["products"])
    assert (out / "acoustics" / "p_acoustics_summary.csv").is_file()
    assert all((out / name).is_file() for name in noise)

    quiet = _unsteady_rotor_workspace(tmp_path / "q", listed=False)
    write_campaign_products(quiet, overwrite=True)
    assert not (quiet.products_dir(None) / "acoustics").exists()
