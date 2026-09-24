"""The custom free-stream fields of the tier-3 workspace (G15, the licensed probe T14).

Rows 5011 to 5014 of ``matriz_gui.fs`` run the 12_WING_PHY wing under a custom
free stream, each against a CONSTANT control that differs from it in one thing
(``test_freestream.py`` says which). Their two fields are written HERE, from the
wing's own mesh block, so the grid covers the body's YZ extent with a margin
this module states, and ``tests/tier1_offline/test_g15_custom_freestream.py``
holds the committed files to what this module writes.

* ``fs_uniform.txt``: vx = 30 m/s everywhere, the rows' own ``TASmps``, and
  vy = vz = 0, so the field IS the uniform free stream the control solves;
* ``fs_shear.txt``: vx = 30 + 2.5 z m/s, sheared in z about the rows' speed.

Both are the manual's STRUCTURED form: a first line ``Npts Mpts``, then the rows
``x y z vx vy vz``, y the outer index and z the inner, in metres and metres per
second in the global frame, every row at x = 0.

    python -m tests.tier3_licensed.freestreams           # report: extents, grid, files current
    python -m tests.tier3_licensed.freestreams --write   # rewrite the fields and their provenance
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable
from pathlib import Path

from pyflightstream._fsm import surface_mesh

HERE = Path(__file__).resolve().parent
FOLDER = HERE / "inputs" / "freestreams"
WING = HERE / "inputs" / "geometries" / "12_WING_PHY.fsm"

#: The rows' own speed, the ``TASmps`` of rows 5010 to 5014, m/s.
SPEED_M_S = 30.0
#: How far the grid reaches past the body on each side, m: half the wing's span,
#: so the tip vortices and the wake's roll-up stay inside the field.
MARGIN_M = 4.0
#: The grid's spacing in y and in z, m. A linear field is reproduced exactly by
#: any spacing; these keep the file small and its rows readable.
STEP_Y_M = 2.0
STEP_Z_M = 1.0
#: The sheared field's gradient of vx in z, (m/s) per m.
SHEAR_PER_S = 2.5

#: Each field's vx at a height z, m/s, by the stem a row's FREESTREAM names.
FIELDS: dict[str, Callable[[float], float]] = {
    "fs_uniform": lambda z: SPEED_M_S,
    "fs_shear": lambda z: SPEED_M_S + SHEAR_PER_S * z,
}
#: What each field is, for its provenance record.
MEANING = {
    "fs_uniform": "vx = 30 m/s everywhere (the rows' TASmps), vy = vz = 0",
    "fs_shear": "vx = 30 + 2.5 z m/s (sheared in z about the rows' TASmps), vy = vz = 0",
}


def extents(path: Path = WING) -> tuple[float, float, float, float]:
    """The body's (y min, y max, z min, z max), m, from its saved mesh block."""
    vertices, _ = surface_mesh(path)
    ys = [vertex[1] for vertex in vertices]
    zs = [vertex[2] for vertex in vertices]
    return min(ys), max(ys), min(zs), max(zs)


def axis(low: float, high: float, step: float) -> list[float]:
    """The stations from ``low - MARGIN_M`` to ``high + MARGIN_M``, outward to a whole step."""
    start = math.floor((low - MARGIN_M) / step) * step
    stop = math.ceil((high + MARGIN_M) / step) * step
    return [start + index * step for index in range(round((stop - start) / step) + 1)]


def grid() -> tuple[list[float], list[float]]:
    """The field's y and z stations, covering the wing's YZ extent with the margin."""
    ymin, ymax, zmin, zmax = extents()
    return axis(ymin, ymax, STEP_Y_M), axis(zmin, zmax, STEP_Z_M)


def field_text(name: str) -> str:
    """The STRUCTURED file of one field: ``Npts Mpts``, then y outer and z inner."""
    ys, zs = grid()
    speed = FIELDS[name]
    rows = [f"{len(ys)} {len(zs)}"]
    rows += [f"0.0 {y:.1f} {z:.1f} {speed(z):.2f} 0.00 0.00" for y in ys for z in zs]
    return "\n".join(rows) + "\n"


def provenance_text(name: str) -> str:
    """The provenance record beside one field."""
    ymin, ymax, zmin, zmax = extents()
    ys, zs = grid()
    return (
        f"# Provenance of the tier-3 custom free stream {name}.txt, read by the rows of\n"
        f"# matriz_gui.fs stating FREESTREAM: {name} through SET_FREESTREAM CUSTOM STRUCTURED.\n"
        "# Written by tests/tier3_licensed/freestreams.py from the mesh block of\n"
        "# 12_WING_PHY.fsm, in the STRUCTURED form of the 26.124 manual. The package reads\n"
        "# the file against that form at plan and converts nothing: metres and metres per\n"
        "# second, in the global frame.\n"
        'form = "STRUCTURED: Npts Mpts, then Npts x Mpts rows x y z vx vy vz, y outer, z inner"\n'
        f'field = "{MEANING[name]}"\n'
        f"body_y_m = [{ymin!r}, {ymax!r}]\n"
        f"body_z_m = [{zmin!r}, {zmax!r}]\n"
        f"margin_m = {MARGIN_M!r}\n"
        f"grid_y_m = [{ys[0]!r}, {ys[-1]!r}]\n"
        f"grid_z_m = [{zs[0]!r}, {zs[-1]!r}]\n"
        f"points = [{len(ys)}, {len(zs)}]\n"
        "x_m = 0.0\n"
    )


def expected() -> dict[Path, str]:
    """Every file this module writes, by its path, with its text."""
    files: dict[Path, str] = {}
    for name in FIELDS:
        files[FOLDER / f"{name}.txt"] = field_text(name)
        files[FOLDER / f"{name}.provenance.toml"] = provenance_text(name)
    return files


def stale() -> list[str]:
    """The files on disk that differ from what this module writes, by name."""
    return [
        path.name
        for path, text in expected().items()
        if not path.is_file() or path.read_text(encoding="utf-8").replace("\r\n", "\n") != text
    ]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--write" in args:
        FOLDER.mkdir(parents=True, exist_ok=True)
        for path, text in expected().items():
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(HERE).as_posix()}")
        return 0
    ymin, ymax, zmin, zmax = extents()
    ys, zs = grid()
    print(f"12_WING_PHY: y {ymin:g} to {ymax:g} m, z {zmin:g} to {zmax:g} m")
    print(
        f"grid: {len(ys)} y from {ys[0]:g} to {ys[-1]:g}, {len(zs)} z from {zs[0]:g} to {zs[-1]:g}"
    )
    differing = stale()
    print(f"{len(expected()) - len(differing)} of {len(expected())} files current: {differing}")
    return 1 if differing else 0


if __name__ == "__main__":
    raise SystemExit(main())
