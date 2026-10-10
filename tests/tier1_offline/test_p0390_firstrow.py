"""REF-FIRSTROW (0.39 development): a grid keeps the spanwise width of its row at another component.

Every source is synthetic (tests/p0380_mesh_fixtures.py): the cambered sheet grid
``G`` with its trailing edge, ``T``, a strip of triangles sharing G's tip station
node for node, and ``U``, a strip sharing T's last row. ``T`` is another
component than ``G``, so G's tip station is an interface and the row of cells
next to it is the one whose spanwise width sets how far the last wake filament
shed by G's trailing edge is from ``T``. Each behaviour is run against its
control: the same refinement without ``keep_first_row``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace import refine_mesh
from tests.p0380_mesh_fixtures import open_loop_count, read_mesh, sheet_with_strips, write_source

STRIP = (0.03, 0.04, 0.05, 0.065, 0.08)
GTU = (("T", "tri", STRIP), ("U", "tri", (0.1, 0.1)))


def _toml(factor: float, *, keep: object = True, extra: str = "") -> str:
    lines = ["[families.G]", f"factor = {factor}"]
    if keep is not None:
        lines.append(f"keep_first_row = {str(keep).lower() if isinstance(keep, bool) else keep}")
    return "\n".join(lines) + "\n" + extra


def _level(tmp_path: Path, toml: str, strips=GTU, name: str = "src"):
    mesh = sheet_with_strips(strips)
    src = write_source(tmp_path / name, "wing", mesh, refine_toml=toml)
    return src, refine_mesh(src, overwrite=True, out_dir=tmp_path / f"out_{name}")


def _stations(verts: np.ndarray, faces) -> np.ndarray:
    """Return the sorted spanwise positions (y) of a sheet family's stations."""
    used = sorted({v for f in faces for v in f})
    return np.unique(np.round(verts[used, 1], 9))


def _te_y(path: Path) -> np.ndarray:
    rows = path.read_text(encoding="utf-8").splitlines()[1:]
    return np.sort(np.array([float(r.split(",")[1]) for r in rows if r.strip()]))


@pytest.mark.parametrize("factor", [2.0, 0.5])
def test_the_interface_row_keeps_its_width_and_the_rest_take_the_factor(tmp_path, factor):
    """REF-FIRSTROW: at G's tip (the interface with T) the last row is the source's."""
    mesh = sheet_with_strips(GTU)
    src_y = _stations(mesh.verts, mesh.families["G"])
    _, kept = _level(tmp_path, _toml(factor), name="kept")
    _, plain = _level(tmp_path, _toml(factor, keep=None), name="plain")
    kept_y = _stations(*_family(kept.obj, "G"))
    plain_y = _stations(*_family(plain.obj, "G"))
    first_row = src_y[-1] - src_y[-2]
    assert kept_y[-1] - kept_y[-2] == pytest.approx(first_row, abs=1e-9)
    assert plain_y[-1] - plain_y[-2] != pytest.approx(first_row, abs=1e-6)  # the control moves it
    inner = len(src_y) - 2  # source intervals between station 0 and the kept row
    assert len(kept_y) - 2 == max(1, round(factor * inner))
    assert kept_y[0] == pytest.approx(src_y[0]) and kept_y[-1] == pytest.approx(src_y[-1])
    assert kept.report["G"]["kept_rows"] == ["far station"]
    assert "kept_rows" not in plain.report["G"]


def _family(obj: Path, name: str):
    verts, families = read_mesh(obj)
    return verts, families[name]


def test_the_last_wake_filament_keeps_its_distance_from_the_adjacent_component(tmp_path):
    """REF-FIRSTROW: the trailing-edge mid-point nearest T stays where the source's was."""
    mesh = sheet_with_strips(GTU)
    tip = float(_stations(mesh.verts, mesh.families["G"])[-1])
    src = write_source(tmp_path / "s", "wing", mesh)
    source_gap = tip - _te_y(src.with_suffix(".te.txt"))[-1]
    _, kept = _level(tmp_path, _toml(2.0), name="kept")
    _, plain = _level(tmp_path, _toml(2.0, keep=None), name="plain")
    kept_te = _te_y(next(p for p in kept.files if p.name.endswith(".te.txt")))
    plain_te = _te_y(next(p for p in plain.files if p.name.endswith(".te.txt")))
    assert tip - kept_te[-1] == pytest.approx(source_gap, abs=1e-9)
    # the control: refined spanwise, the last row narrows (by more than half here, the station
    # spacing being clustered toward the tip), so the last filament moves toward T
    assert tip - plain_te[-1] < 0.75 * source_gap


def test_the_level_stays_closed_and_passes_every_gate(tmp_path):
    """REF-FIRSTROW: the unselected neighbour takes the grid's new tip nodes in its band."""
    mesh = sheet_with_strips(GTU)
    _, kept = _level(tmp_path, _toml(2.0))
    verts, families = read_mesh(kept.obj)
    all_faces = [f for fs in families.values() for f in fs]
    source_faces = [f for fs in mesh.families.values() for f in fs]
    assert open_loop_count(all_faces) == open_loop_count(source_faces)
    assert not [g for g in kept.audit.gates if g.verdict == "fail"]


@pytest.mark.parametrize(
    ("toml", "strips", "said"),
    [
        (_toml(2.0, keep='"yes"'), GTU, "is not true or false"),
        (
            _toml(2.0, extra="").replace("factor = 2.0", 'factor = 2.0\nmethod = "remesh"'),
            GTU,
            "is remeshed",
        ),
        (_toml(2.0), (), "no interface row to keep"),
        (_toml(2.0), (("G_tip", "tri", STRIP),), "no interface row to keep"),
        (_toml(2.0, extra='[components]\nWing = ["G", "T"]\n'), GTU, "no interface row to keep"),
    ],
    ids=["not-a-bool", "remesh", "alone", "same-prefix", "same-component"],
)
def test_keep_first_row_that_cannot_be_honoured_is_refused(tmp_path, toml, strips, said):
    """REF-FIRSTROW: each refusal names the family and the key, and nothing is written."""
    mesh = sheet_with_strips(strips)
    src = write_source(tmp_path / "src", "wing", mesh, refine_toml=toml)
    with pytest.raises(InputArtifactError) as caught:
        refine_mesh(src, out_dir=tmp_path / "out")
    text = str(caught.value)
    assert said in text and "keep_first_row" in text and text.endswith("Nothing was written.")
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())
