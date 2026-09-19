"""The campaign's drag check judges every export against the digits IT prints.

`scripts/measure_campaign_coherence.py` is the instrument of the licensed
evidence. Its drag check took ONE band for the whole workspace, the loosest
export's, so a four-decimal export beside a seven-decimal one let the 0.23.0
sign defect read `coherent` (release review of 0.24.0, VV-V1).

The fixture is two exports built from the convention: the free stream is
`(cos a cos b, -cos a sin b, sin a)` in the export's frame, and the export's
`CDi + CDo` is the projection of its force on it. The DEFECT export states the
projection with the y term's sign flipped, which at beta 4 and `Cy = -0.0004864`
moves it by `2 |Cy sin b|`, about 6.8e-5.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "measure_campaign_coherence.py"


def _instrument():
    spec = importlib.util.spec_from_file_location("measure_campaign_coherence", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _export(path: Path, alpha, beta, force, drag, decimals) -> None:
    cx, cy, cz = force
    cdi = round(drag / 4.0, decimals)
    cdo = round(drag - cdi, decimals)
    cells = ", ".join(f"{value:+.{decimals}f}" for value in (cx, cy, cz, 0.1, cdi, cdo))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Solver mode:                                Steady\n"
        f"Angle of attack (Deg)                       {alpha:.{decimals}f}\n"
        f"Side-slip angle (Deg)                       {beta:.{decimals}f}\n"
        "Surface, Cx, Cy, Cz, CL, CDi, CDo\n"
        f"Total, {cells}\n",
        encoding="utf-8",
    )


def _projection(alpha, beta, force, flip_y=False) -> float:
    a, b = math.radians(alpha), math.radians(beta)
    y = math.cos(a) * math.sin(b) * (1.0 if flip_y else -1.0)
    return force[0] * math.cos(a) * math.cos(b) + force[1] * y + force[2] * math.sin(a)


def _workspace(tmp_path: Path, *, flip_y: bool, row_gap: float = 0.0) -> tuple[Path, Path]:
    sideslip = (0.0221000, -0.0004864, 0.0040000)
    _export(
        tmp_path / "sims" / "sim_1003" / "datapoints" / "B" / "loads.txt",
        0.0,
        4.0,
        sideslip,
        _projection(0.0, 4.0, sideslip, flip_y=flip_y),
        decimals=7,
    )
    four = (0.0200, 0.0000, 0.1000)
    _export(
        tmp_path / "sims" / "sim_5001" / "datapoints" / "A" / "loads.txt",
        2.0,
        0.0,
        four,
        _projection(2.0, 0.0, four),
        decimals=4,
    )
    out = tmp_path / "out"
    (out / "polars").mkdir(parents=True)
    (out / "polars" / "P5001_x.csv").write_text(
        f"ALPHA,BETA,CDW,CD0,CDI\n2.0,0.0,{0.02350 + row_gap:.5f},0.02000,0.00350\n",
        encoding="utf-8",
    )
    return tmp_path, out


def test_a_campaign_whose_exports_close_on_their_own_digits_is_coherent(tmp_path):
    workspace, out = _workspace(tmp_path, flip_y=False)
    result = _instrument().steady_drag(workspace, out)
    assert len(result["measured"]["exports"]) == 2, result["measured"]["exports"]
    assert result["verdict"] == "coherent", result["measured"]


def test_a_sign_defect_on_a_seven_decimal_export_is_not_hidden_by_a_four_decimal_one(tmp_path):
    workspace, out = _workspace(tmp_path, flip_y=True)
    result = _instrument().steady_drag(workspace, out)
    assert result["verdict"] == "INCOHERENT", result["measured"]
    assert result["measured"]["worst_ratio_at"] == "loads.txt"
    assert result["measured"]["worst_ratio"] > 100.0, result["measured"]["worst_ratio"]
    # The gap itself is the signature, 2 |Cy sin b|, well under the four-decimal band.
    gap = max(row["gap"] for row in result["measured"]["exports"])
    assert abs(gap - 2 * 0.0004864 * math.sin(math.radians(4.0))) < 2e-7


# --- A POLAR ROW IS NO MORE PRECISE THAN THE EXPORT IT WAS COMPUTED FROM ----------
#
# Found by the campaign's own dry run: a polar row's CDW is the projection of the
# export's (Cx, Cy, Cz) and its CD0, CDI are the export's CDo, CDi, so a row
# computed from a four-decimal export carries that export's rounding. Judging the
# row against its own five decimals alone called a coherent row incoherent.


def test_a_row_is_judged_with_the_digits_of_the_export_it_came_from(tmp_path):
    # 4e-5 off: outside the row's own 1.5e-5, inside its four-decimal export's band.
    workspace, out = _workspace(tmp_path, flip_y=False, row_gap=4.0e-5)
    result = _instrument().steady_drag(workspace, out)
    assert result["verdict"] == "coherent", result["measured"]


def test_a_row_off_by_more_than_its_export_and_its_own_digits_is_still_refused(tmp_path):
    # THE CONTROL: 5e-4 is more than any rounding of either file explains.
    workspace, out = _workspace(tmp_path, flip_y=False, row_gap=5.0e-4)
    result = _instrument().steady_drag(workspace, out)
    assert result["verdict"] == "INCOHERENT", result["measured"]
    assert result["measured"]["worst_ratio_at"].startswith("P5001_x.csv")
