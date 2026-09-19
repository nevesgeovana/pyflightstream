"""The axes module against the SOLVER'S OWN NUMBERS, over every recorded export.

The second oracle, and the one a derivation cannot argue with. A loads export
prints the total force as ``(Cx, Cy, Cz)`` in its own frame and, separately, the
drag it measured along the free stream, ``CDi + CDo``. So for any export

    CDW = wind_force_coefficients((Cx, Cy, Cz), alpha, beta)[0]  ==  CDi + CDo

and a rotation with one wrong sign misses it by a hundred thousand times the
printed precision. 0.23.0's ``_free_stream`` gave -0.01058 where the export of
alpha 4, beta 2 states +0.03578.

THE FIXTURE is the Total row of each export under ``tests/tier3_licensed/sims``,
as printed, extracted by ``scripts/extract_recorded_total_rows.py``. Those
exports are machine output and are not tracked, so the table is what CI reads;
where the live exports exist the last test refuses a fixture that disagrees with
them, so the table cannot be edited into agreement with an implementation.

THE TOLERANCE IS THE PRINTED PRECISION, not a constant. Four printed numbers
enter the identity, each rounded to the last digit the export prints, so the
identity can close no better than two units of that digit: 2e-7 on an export
printing seven decimals, 2e-4 on one printing four.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import math
import os
from pathlib import Path

import numpy as np
import pytest

from pyflightstream.post import axes

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("fixtures") / "recorded_total_rows.csv"
SIMS = Path(os.environ.get("PYFLIGHTSTREAM_RECORDED_SIMS", ROOT / "tests/tier3_licensed/sims"))
EXTRACTOR = ROOT / "scripts" / "extract_recorded_total_rows.py"


def _rows() -> list[dict[str, str]]:
    with FIXTURE.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _decimals(printed: str) -> int:
    return len(printed.split(".")[1]) if "." in printed else 0


ROWS = _rows()
ANGLED = [row for row in ROWS if float(row["alpha_deg"]) != 0.0 or float(row["beta_deg"]) != 0.0]


def test_the_fixture_holds_exports_under_sideslip_and_under_both_angles():
    assert len(ANGLED) >= 25
    assert any(float(r["beta_deg"]) != 0.0 and float(r["alpha_deg"]) == 0.0 for r in ANGLED)
    assert any(float(r["beta_deg"]) != 0.0 and float(r["alpha_deg"]) != 0.0 for r in ANGLED)


@pytest.mark.parametrize("row", ANGLED, ids=[row["export"] for row in ANGLED])
def test_the_wind_axis_drag_is_the_drag_the_export_states(row):
    force = np.array([float(row[name]) for name in ("Cx", "Cy", "Cz")])
    stated = float(row["CDi"]) + float(row["CDo"])
    digits = min(_decimals(row[name]) for name in ("Cx", "Cz", "CDi", "CDo"))
    tolerance = 2.0 * 10.0 ** (-digits)
    cdw, _cyw, _clw = axes.wind_force_coefficients(
        force, float(row["alpha_deg"]), float(row["beta_deg"])
    )
    assert math.isclose(cdw, stated, abs_tol=tolerance), (
        f"{row['export']}: CDW {cdw:+.8f} against the export's CDi + CDo {stated:+.8f}, "
        f"at alpha {row['alpha_deg']} beta {row['beta_deg']}, tolerance {tolerance:g}"
    )


def test_the_identity_discriminates_the_solver_vector_from_the_aiaa_one():
    """The control for the test above: it must be ABLE to refuse a near miss.

    At alpha 4, beta 2 the AIAA vector ``(ca cb, -sb, sa cb)`` differs from the
    solver's ``(ca cb, -ca sb, sa)`` only at second order, and the recorded
    export still tells them apart by a factor of two hundred.
    """
    row = next(r for r in ANGLED if r["export"].endswith("POLAR-1004_M10AL+040BE+020.txt"))
    a, b = math.radians(4.0), math.radians(2.0)
    force = np.array([float(row[name]) for name in ("Cx", "Cy", "Cz")])
    stated = float(row["CDi"]) + float(row["CDo"])
    aiaa = np.array([math.cos(a) * math.cos(b), -math.sin(b), math.sin(a) * math.cos(b)])
    assert abs(float(force @ aiaa) - stated) > 1e-5
    assert abs(axes.wind_force_coefficients(force, 4.0, 2.0)[0] - stated) < 2e-7


@pytest.mark.skipif(
    not SIMS.is_dir(),
    reason="the recorded exports are machine output and live on the licensed machine only",
)
def test_the_fixture_is_the_live_exports_as_printed():
    spec = importlib.util.spec_from_file_location("extract_recorded_total_rows", EXTRACTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    live = {row["export"]: row for row in module.rows()}
    for row in ROWS:
        relative = Path(row["export"])
        path = SIMS / relative.parent / "raw" / relative.name
        if path.is_file():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row.get("sha256"), (
                f"{row['export']}: live export bytes differ from the recorded sha256"
            )
        if row["export"] in live:
            assert row == live[row["export"]], f"{row['export']} was edited in the fixture"


def test_every_recorded_export_has_a_sha256_witness():
    import re

    assert ROWS, "the recorded export fixture must not be empty"
    assert all(re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")) for row in ROWS), (
        "every recorded Total row needs a sha256 witness"
    )


@pytest.mark.parametrize(
    "old,new",
    [(b"Original heading", b"Replaced heading"), (b"Angle of attack (Deg)", b"Unknown heading")],
    ids=["same-values", "no-longer-selected"],
)
def test_replacing_export_bytes_with_the_same_total_row_is_refused(tmp_path, monkeypatch, old, new):
    # Only the non-tabular heading changes; all printed values stay identical.
    path = tmp_path / "sim_1/raw/loads.txt"
    path.parent.mkdir(parents=True)
    original = (
        b"Original heading\r\nAngle of attack (Deg) 4\r\nSide-slip angle (Deg) 2\r\n"
        b"Surface, Cx, Cy, Cz, CL, CDi, CDo\r\nTotal, 1, 2, 3, 4, 5, 6\r\n"
    )
    path.write_bytes(original)
    monkeypatch.setenv("PYFLIGHTSTREAM_RECORDED_SIMS", str(tmp_path))
    spec = importlib.util.spec_from_file_location("extract_recorded_total_rows", EXTRACTOR)
    assert spec is not None and spec.loader is not None
    extractor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extractor)
    before = extractor.rows()
    monkeypatch.setitem(globals(), "ROWS", before)
    monkeypatch.setitem(globals(), "SIMS", tmp_path)
    test_the_fixture_is_the_live_exports_as_printed()
    replacement = original.replace(old, new)
    path.write_bytes(replacement)
    assert extractor.total_row(original.decode()) == extractor.total_row(replacement.decode())
    with pytest.raises(AssertionError, match="sim_1/loads.txt"):
        test_the_fixture_is_the_live_exports_as_printed()


def test_extractor_hashes_exact_bytes_before_newline_normalization(tmp_path, monkeypatch):
    path = tmp_path / "sim_1/raw/loads.txt"
    path.parent.mkdir(parents=True)
    payload = (
        b"Angle of attack (Deg) 4\r\nSide-slip angle (Deg) 2\r\n"
        b"Surface, Cx, Cy, Cz, CL, CDi, CDo\r\nTotal, 1, 2, 3, 4, 5, 6\r\n"
    )
    path.write_bytes(payload)
    monkeypatch.setenv("PYFLIGHTSTREAM_RECORDED_SIMS", str(tmp_path))
    spec = importlib.util.spec_from_file_location("extract_recorded_total_rows", EXTRACTOR)
    assert spec is not None and spec.loader is not None
    extractor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extractor)
    assert extractor.rows()[0].get("sha256") == hashlib.sha256(payload).hexdigest(), (
        "sha256 must witness the original export bytes"
    )
    assert (
        hashlib.sha256(payload).digest() != hashlib.sha256(payload.replace(b"\r\n", b"\n")).digest()
    )
