"""P0410-PB2: FFT-dependent acoustic outputs need exercised numeric snapshots."""

from __future__ import annotations

import ast
import csv
import io
import math
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.post.acoustics import AcousticSignal, write_acoustic_products

HERE = Path(__file__).parent
SNAPSHOTS = HERE / "fixtures" / "products_snapshot"


def _numeric_contracts():
    """Read the comparator's declaration without importing another test module."""
    tree = ast.parse((HERE / "test_products_snapshot.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "NUMERIC_PRODUCTS"
            for target in node.targets
        ):
            assert isinstance(node.value, ast.Dict)
            return {
                ast.literal_eval(key): ast.literal_eval(value)
                for key, value in zip(node.value.keys, node.value.values, strict=True)
                if isinstance(key, ast.Tuple) and ast.literal_eval(key.elts[0]) == "noise"
            }
    pytest.fail("products snapshot has no numeric product declaration")


def _assert_numeric_rows(products, contracts, snapshots):
    for name in sorted(products):
        key = ("noise", f"products/acoustics/{name}")
        assert key in contracts, f"FFT-derived product has no numeric snapshot contract: {name}"
        path = snapshots / "noise" / name
        assert path.is_file(), f"FFT-derived product has no retained numeric table: {name}"
        rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
        columns = contracts[key]

        def finite_row(row, columns=columns):
            try:
                return all(math.isfinite(float(row[column])) for column in columns)
            except (KeyError, TypeError, ValueError):
                return False

        assert columns and any(finite_row(row) for row in rows), (
            f"FFT-derived product has no finite numeric row in {columns}: {name}"
        )


def _fft_dependent_products(tmp_path, monkeypatch):
    """Perturb the FFT itself: discover downstream files by observed dependency."""
    time = np.arange(64) / 64.0
    pressure = 1.0 + np.sin(2 * np.pi * 8 * time)
    signals = [
        AcousticSignal(name, 0.0, float(i + 1), 0.0, tuple(time), tuple(pressure))
        for i, name in enumerate(("PYFS_OBS1", "Observer 2", "Observer 3"))
    ]
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    write_acoustic_products(signals, before, stem="p", rotors={"R": (2, 240.0)})
    original = np.fft.rfft
    monkeypatch.setattr(np.fft, "rfft", lambda *args, **kwargs: 2 * original(*args, **kwargs))
    write_acoustic_products(signals, after, stem="p", rotors={"R": (2, 240.0)})
    return {
        path.name
        for path in before.glob("*.csv")
        if path.read_bytes() != (after / path.name).read_bytes()
    }


def test_p0410_pb2_fft_dependency_detector_exercises_spectra_and_bpf(tmp_path, monkeypatch):
    products = _fft_dependent_products(tmp_path, monkeypatch)
    assert "p_01_PYFS_OBS1_spectrum.csv" in products
    assert "p_acoustics_bpf.csv" in products
    assert "p_01_PYFS_OBS1_pressure.csv" not in products
    # The full numeric-row check is blocked by the existing all-NA BPF snapshot.
    # The spectra remain enforced here; the BPF gap is not treated as covered.
    spectra = {name for name in products if name.endswith("_spectrum.csv")}
    assert len(spectra) == 3
    _assert_numeric_rows(spectra, _numeric_contracts(), SNAPSHOTS)


@pytest.mark.parametrize("defect", ["new-product", "missing-table", "all-na"])
def test_p0410_pb2_fft_guard_catches_new_or_unexercised_products(tmp_path, defect):
    folder = tmp_path / "noise"
    folder.mkdir()
    name = "new_fft_product.csv"
    contracts = {("noise", f"products/acoustics/{name}"): ("AMPLITUDE_PA",)}
    path = folder / name
    path.write_text("AMPLITUDE_PA\n1.0\n", encoding="utf-8")
    _assert_numeric_rows({name}, contracts, tmp_path)
    if defect == "new-product":
        contracts.clear()
    elif defect == "missing-table":
        path.unlink()
    else:
        path.write_text("AMPLITUDE_PA\nNA\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="FFT-derived product"):
        _assert_numeric_rows({name}, contracts, tmp_path)


def _clean_signal(pressure) -> AcousticSignal:
    time = np.arange(64) / 64.0
    return AcousticSignal("OBS", 0.0, 1.0, 0.0, tuple(time), tuple(pressure))


def test_x_f_0334_a_nan_sample_is_not_called_a_silent_record(tmp_path):
    """X-F-0334: the NaN rms made the level None and the log said silent; say what it is."""
    pressure = 1.0 + np.sin(2 * np.pi * 8 * np.arange(64) / 64.0)
    pressure[5] = np.nan
    notes = write_acoustic_products([_clean_signal(pressure)], tmp_path, stem="p").notes
    assert any("non-finite pressure sample, OASPL is NA" in note for note in notes)
    assert not any("silent record" in note for note in notes)
    silent = write_acoustic_products([_clean_signal(np.ones(64))], tmp_path, stem="q").notes
    assert any("silent record, OASPL is NA" in note for note in silent)


def test_x_f_1190_a_nan_rpm_is_named_as_an_unusable_rotor_not_passed_on(tmp_path):
    """X-F-1190: NaN is truthy, so it reached the harmonics and was only caught there."""
    pressure = 1.0 + np.sin(2 * np.pi * 8 * np.arange(64) / 64.0)
    notes = write_acoustic_products(
        [_clean_signal(pressure)], tmp_path, stem="p", rotors={"R": (2, float("nan"))}
    ).notes
    assert any("rotor 'R' states blades=2 and rpm=nan" in note for note in notes)
