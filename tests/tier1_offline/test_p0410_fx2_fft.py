"""P0410-FX2: every spectral and harmonic-fit product retains numeric evidence."""

import csv
import io
import math

import numpy as np
import pytest

from tests.tier1_offline import test_products_snapshot as snapshot


def _numeric_rows(contracts, snapshots):
    for (campaign, product), columns in contracts.items():
        path = snapshots / campaign / product.rsplit("/", 1)[-1]
        assert path.is_file(), f"missing FFT table: {campaign}/{product}"
        rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
        assert columns and any(
            all(_finite(row.get(column)) for column in columns) for row in rows
        ), (campaign, product, columns)


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def test_p0410_fx2_every_fft_family_has_numeric_rows():
    _numeric_rows(snapshot.NUMERIC_PRODUCTS, snapshot.SNAPSHOT_DIR)


def _dependency_contracts(campaign, before, after, contracts):
    changed = {name for name in before if name.endswith(".csv") and before[name] != after[name]}
    assert changed, f"the {campaign} detector exercised no numerical dependency"
    for name in changed:
        key = (campaign, name)
        assert key in contracts, f"missing FFT contract: {key}"
        old = list(csv.DictReader(io.StringIO(before[name].decode())))
        new = list(csv.DictReader(io.StringIO(after[name].decode())))
        assert len(old) == len(new)
        for left, right in zip(old, new, strict=True):
            for column in left:
                if left[column] != right[column]:
                    assert column in contracts[key], f"missing FFT column: {key}/{column}"
    return changed


@pytest.mark.parametrize("campaign", ["noise", "unsteady_harmonics", "wheel_harmonics"])
def test_p0410_fx2_dependency_detector_covers_every_fft_family(campaign):
    with pytest.MonkeyPatch.context() as mp:
        before = snapshot.regenerate(campaign, mp)
    original_fft = np.fft.rfft
    original_fit = np.linalg.lstsq

    def changed_fit(*args, **kwargs):
        coefficients, *rest = original_fit(*args, **kwargs)
        offsets = np.arange(1, coefficients.size + 1).reshape(coefficients.shape)
        return (2 * coefficients + offsets, *rest)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(np.fft, "rfft", lambda *a, **k: 2 * original_fft(*a, **k))
        mp.setattr(np.linalg, "lstsq", changed_fit)
        after = snapshot.regenerate(campaign, mp)
    changed = _dependency_contracts(campaign, before, after, snapshot.NUMERIC_PRODUCTS)
    if campaign == "noise":
        assert "products/acoustics/p_acoustics_bpf.csv" in changed
        assert sum(name.endswith("_spectrum.csv") for name in changed) == 3
    else:
        assert any(name.endswith("_harmonics.csv") for name in changed)
        for name in changed:
            key = (campaign, name)
            for column in snapshot.NUMERIC_PRODUCTS[key]:
                missing_column = dict(snapshot.NUMERIC_PRODUCTS)
                missing_column[key] = tuple(c for c in missing_column[key] if c != column)
                with pytest.raises(AssertionError, match="missing FFT column"):
                    _dependency_contracts(campaign, before, after, missing_column)
    _numeric_rows(
        {key: snapshot.NUMERIC_PRODUCTS[key] for key in ((campaign, name) for name in changed)},
        snapshot.SNAPSHOT_DIR,
    )


@pytest.mark.parametrize("defect", ["missing-table", "all-na", "nonfinite"])
def test_p0410_fx2_numeric_detector_refuses_empty_evidence(tmp_path, defect):
    folder = tmp_path / "campaign"
    folder.mkdir()
    path = folder / "fft.csv"
    path.write_text("A\n1.0\n", encoding="utf-8")
    contracts = {("campaign", "products/fft.csv"): ("A",)}
    _numeric_rows(contracts, tmp_path)
    if defect == "missing-table":
        path.unlink()
    else:
        path.write_text("A\n" + ("NA" if defect == "all-na" else "inf") + "\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        _numeric_rows(contracts, tmp_path)


@pytest.mark.parametrize("defect", ["new-product", "uncovered-column"])
def test_p0410_fx2_dependency_detector_refuses_incomplete_contract(defect):
    key = ("campaign", "products/fft.csv")
    before = {key[1]: b"A,B\n1,2\n"}
    after = {key[1]: b"A,B\n2,3\n"}
    contracts = {key: ("A", "B")}
    _dependency_contracts(key[0], before, after, contracts)
    contracts = {} if defect == "new-product" else {key: ("A",)}
    with pytest.raises(AssertionError, match="missing FFT"):
        _dependency_contracts(key[0], before, after, contracts)
