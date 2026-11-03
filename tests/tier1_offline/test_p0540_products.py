"""Tier 1: the rotor normal-force slope product (PFS-2186.12, FR-3502 to FR-3504).

Written from the definition on docs/definitions/rotor-coefficients.md ("The normal-force
slope against incidence"): one row per distinct J, the secant between the two rows of
lowest distinct |ALPHA|, NA with a named skip line for one incidence only.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pyflightstream.post._cn_slope import cn_slope_rows

ALIAS = "PUSHER"
COLUMNS = ["POL", "ROTOR", "ALPHA", "BETA", "MACH", "J", f"J_{ALIAS}", f"CN_{ALIAS}"]


def _row(j: str, alpha: str, cn: str, mach: str = "0.2") -> dict[str, str]:
    return {
        "POL": "6001",
        "ROTOR": ALIAS,
        "ALPHA": alpha,
        "BETA": "0",
        "MACH": mach,
        "J": j,
        f"J_{ALIAS}": j,
        f"CN_{ALIAS}": cn,
    }


@pytest.mark.requirement("FR-3502")
def test_p0540_cn_slope_is_the_secant_of_the_two_lowest_distinct_abs_alpha_per_j():
    rows = [
        _row("0.5", "10", "0.50"),
        _row("0.5", "2", "0.10"),
        _row("0.5", "-2", "-0.06"),  # same |ALPHA| as 2: the positive one is kept
        _row("0.5", "5", "0.26"),
        _row("0.8", "0", "0.00", mach="0.3"),
        _row("0.8", "4", "0.20", mach="0.25"),
    ]
    header, body, skipped = cn_slope_rows(COLUMNS, rows, ALIAS)
    assert header[0] == "POL" and header[-6:] == [
        "J",
        "ALPHA_LOW",
        "ALPHA_HIGH",
        "CN_LOW",
        "CN_HIGH",
        "CN_SLOPE_PER_DEG",
    ]
    assert "ALPHA" not in header and header[header.index("J") - 1] == "ROTOR"
    assert len(set(header)) == len(header), "a column name is repeated"
    by_j = {row[-6]: dict(zip(header, row, strict=True)) for row in body}
    assert sorted(by_j) == [0.5, 0.8]
    half = by_j[0.5]
    assert (half["ALPHA_LOW"], half["ALPHA_HIGH"]) == (2.0, 5.0)
    assert half["CN_SLOPE_PER_DEG"] == pytest.approx((0.26 - 0.10) / (5.0 - 2.0))
    assert half["MACH"] == "0.2", "a context column that does not vary keeps its value"
    assert by_j[0.8]["MACH"] == "NA", "a context column that varies reads NA"
    assert by_j[0.8]["CN_SLOPE_PER_DEG"] == pytest.approx(0.20 / 4.0)
    assert skipped == []


@pytest.mark.requirement("FR-3503")
def test_p0540_cn_slope_with_one_incidence_reads_na_and_names_the_skip():
    rows = [_row("0.5", "3", "0.1"), _row("0.9", "0", "0.0"), _row("0.9", "NA", "0.2")]
    header, body, skipped = cn_slope_rows(COLUMNS, rows, ALIAS)
    assert len(body) == 2
    for row in body:
        assert row[header.index("CN_SLOPE_PER_DEG")] == "NA"
        assert row[header.index("ALPHA_LOW")] == "NA"
    assert len(skipped) == 2 and "J=0.5" in skipped[0] and "J=0.9" in skipped[1]


@pytest.mark.requirement("FR-3503")
def test_p0540_cn_slope_of_a_plus_and_minus_pair_says_why_it_is_na():
    """REL-K-011: +2 and -2 are two incidences and one |ALPHA|; the skip line says the second."""
    rows = [_row("0.5", "2", "0.10"), _row("0.5", "-2", "-0.06")]
    header, body, skipped = cn_slope_rows(COLUMNS, rows, ALIAS)
    assert body[0][header.index("CN_SLOPE_PER_DEG")] == "NA"
    assert len(skipped) == 1 and "two distinct |ALPHA|" in skipped[0]
    assert "two incidences" not in skipped[0]


_REFERENCE = "\n".join(
    [
        "area_m2 = 50.0",
        "chord_m = 2.526",
        "span_m = 20.0",
        "",
        f"[rotors.{ALIAS}]",
        f'alias = "{ALIAS}"',
        "x_m = 0.0",
        "y_m = 0.0",
        "z_m = 0.0",
        'axis = "X"',
        "rpm_sign = 1",
        "diameter_m = 1.2",
        'families_blades = ["B"]',
        'blade1 = { azimuth_deg = 0.0, zero = "Y" }',
        "",
    ]
)


@pytest.mark.requirement("FR-3504")
def test_p0540_the_post_writes_the_cn_slope_beside_the_rotor_table_when_asked(tmp_path):
    """The key writes polars/P<sim>-<ALIAS>_cn_slope.csv; off by default it writes nothing."""
    from tests.tier1_offline.test_post_superfile import _post, _workspace

    workspace = _workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r002.toml").write_text(_REFERENCE, encoding="utf-8")
    plain = _post(workspace)
    assert not [p for p in plain if str(p).endswith("_cn_slope.csv")], "off by default"
    for code in ("p001", "p002"):
        pproc = workspace.inputs_dir / "pproc" / f"{code}.toml"
        pproc.write_text(
            pproc.read_text(encoding="utf-8") + "\n[products]\nrotor_cn_slope = true\n",
            encoding="utf-8",
        )
    written = _post(workspace)
    slopes = [Path(p) for p in written if str(p).endswith("_cn_slope.csv")]
    tables = [Path(p) for p in written if str(p).endswith("_rotor.csv")]
    assert slopes and len(slopes) == len(tables)
    slope = slopes[0]
    assert slope.name == tables[0].name.replace("_rotor.csv", "_cn_slope.csv")
    with tables[0].open(encoding="utf-8", newline="") as handle:
        table = list(csv.DictReader(handle))
    with slope.open(encoding="utf-8", newline="") as handle:
        out = list(csv.DictReader(handle))
    assert len(out) == len({float(row[f"J_{ALIAS}"]) for row in table})
    # The value, from the rotor table's own columns and the definition.
    usable = sorted(
        ((float(r["ALPHA"]), float(r[f"CN_{ALIAS}"])) for r in table if r[f"CN_{ALIAS}"] != "NA"),
        key=lambda pair: abs(pair[0]),
    )
    got = out[0]["CN_SLOPE_PER_DEG"]
    if len(usable) >= 2:
        (a0, c0), (a1, c1) = usable[:2]
        assert float(got) == pytest.approx((c1 - c0) / (a1 - a0), rel=1e-4, abs=1e-6)
    else:
        assert got == "NA"
    manifest = json.loads((slope.parents[1] / "products.json").read_text(encoding="utf-8"))
    entry = manifest["products"][f"polars/{slope.name}"]
    assert entry["kind"] == "cn_slope" and entry["rotor"] == ALIAS
