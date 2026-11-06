"""P0560-WHEEL: wake terminations carried by sector-to-wheel and marked across a merge.

Pipeline role: tier-1 oracle of PFS-2195 (FR-3720, FR-3721). The sector is the synthetic one of
``test_p0540_wheel``, with its blade base and nacelle base merged into their parents and one
explicit wake-termination node at the tip end of a rim. The node expected in the wheel is that
tip point turned by each copy's angle, computed here, not read from the code under test.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace import plan_mark_boundaries
from pyflightstream.workspace._wheel import sector_to_wheel
from tests.tier1_offline.test_p0540_wheel import (
    Built,
    _write_points,
    build_sector,
    read_wheel,
    turn,
)

COPIES = 6
RIM = '[trailing_edges.TE_a]\nfile = "sector.TE_a.te.txt"\ntype = "STANDARD"\n'


def terminated_sector(folder: Path, build: str = "26.125") -> tuple[Built, np.ndarray]:
    """Write the merged sector with one explicit termination node; return it and that node."""
    built = build_sector(folder, copies=COPIES, separate_base=True)
    _, tip = built.rims["TE_a"][-1]
    point = built.verts[tip]
    _write_points(folder / "sector.TE_a.wake.te.txt", [point])
    sidecar = folder / "sector.obj.boundaries.toml"
    text = sidecar.read_text(encoding="utf-8")
    assert text.count(RIM) == 1 and text.count('fs_build = "26.124"') == 1
    text = text.replace(RIM, RIM + 'wake_termination_nodes = "sector.TE_a.wake.te.txt"\n')
    sidecar.write_text(text.replace('"26.124"', f'"{build}"'), encoding="utf-8")
    return built, point


def wheel_of(built: Built, out: Path, **options):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sector_to_wheel(
            built.obj, copies=COPIES, blades=["Blade1"], axis="x", out=out, **options
        )


@pytest.mark.requirement("FR-3720")
@pytest.mark.parametrize("build", ["26.124", "26.125"])
def test_p0560_a_wheel_with_explicit_terminations_across_a_merge_passes_the_preview(
    tmp_path: Path, build: str
) -> None:
    built, point = terminated_sector(tmp_path, build)
    wheel = tmp_path / "wheel.obj"
    wheel_of(built, wheel)
    side = (tmp_path / "wheel.obj.boundaries.toml").read_text(encoding="utf-8")
    assert side.count("wake_termination_nodes") == COPIES and side.count("merge_into") == 7

    plan = plan_mark_boundaries(wheel)

    verts, _ = read_wheel(wheel)
    labels = [f"TE_a_{k + 1}" for k in range(COPIES)]
    assert sorted(plan.nodes) == labels
    for k, label in enumerate(labels):
        expected = turn(point[None, :], np.array([1.0, 0.0, 0.0]), np.zeros(3), 60.0 * k)[0]
        (node,) = plan.nodes[label]
        assert np.allclose(verts[node - 1], expected, atol=1e-9), label
    lines = plan.script.splitlines()
    marks = [i for i, line in enumerate(lines) if line == "MARK_WAKE_TERMINATION_NODES"]
    combines = [i for i, line in enumerate(lines) if line.startswith("SURFACE_COMBINE")]
    assert len(marks) == COPIES and len(combines) == 7
    assert max(marks) < min(combines)


@pytest.mark.requirement("FR-3721")
@pytest.mark.parametrize("build", ["26.126", "26.127"])
def test_p0560_explicit_terminations_across_a_merge_on_an_unmeasured_build_name_the_evidence(
    tmp_path: Path, build: str
) -> None:
    built, _ = terminated_sector(tmp_path, build)
    wheel = tmp_path / "wheel.obj"
    wheel_of(built, wheel)
    with pytest.raises(InputArtifactError) as caught:
        plan_mark_boundaries(wheel)
    words = str(caught.value)
    assert build in words and "26.124" in words and "26.125" in words
    assert "CMP-26125_2026-10-26_marking" in words
