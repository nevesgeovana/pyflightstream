"""The instruments of the 0.40.0 command-gap probes: inputs, builds, readers and judges.

Pipeline role: the support of ``pyflightstream.qa._spec_0400_gap``, which holds the
ordered battery and registers its primary probes. Here are the synthetic inputs
(the qa wing, a box with a known hole and a known degenerate face, a two-sheet
IGES, section and CCS files from public shape laws, the stand-in structural
program), the build callables the probes chain, the readers of what the solver
wrote (saved simulations, OBJ exports, numeric exports, CCS files) and the
judges, lax wherever no run has measured the effect.
"""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np

import pyflightstream._textio as _textio
from pyflightstream._fsm import MESH_MARKER as _MESH_MARKER
from pyflightstream._fsm import (
    boundary_names,
    mesh_face_counts,
    saved_length_unit,
    trailing_edge_midpoints,
)
from pyflightstream.cases.fsi_workspace import aeroelastic_post_script
from pyflightstream.qa._spec_ccs_noise import (
    _ccs_assign,
    _ccs_import,
    _ccs_initialize,
    _ccs_select,
    _wing_loft,
)
from pyflightstream.qa._spec_kit import _emit, _seq
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.geometry import WingSpec, generate_wing_stl, wing_triangles, write_stl
from pyflightstream.qa.probes import ProbeArtifacts
from pyflightstream.script import Script
from pyflightstream.script.helpers import (
    detect_every_boundary,
    initialize_solver,
    render_wake_edge_node_file,
    wake_edge_import_token,
)

__all__: list[str] = []


Build = Callable[[Script, Path], None]


Judge = Callable[[ProbeArtifacts], "bool | None"]


Reading = Callable[[ProbeArtifacts], str]


#: The saved states the harness brackets a target with (``ProbeSpec.save_state``).
_BEFORE, _AFTER = "state_before.fsm", "state_after.fsm"


#: Solved probes march or iterate; a cold licence checkout plus a short solve
#: fits in three minutes on the licensed machine.
_SOLVE_TIMEOUT_S = 180.0


def _faces(path: Path) -> tuple[int, tuple[int, ...] | None] | None:
    if not path.is_file():
        return None
    try:
        return mesh_face_counts(path)
    except (OSError, ValueError, QaEvidenceError):
        return None


def _names(path: Path) -> tuple[str, ...] | None:
    if not path.is_file():
        return None
    try:
        return boundary_names(path)
    except (OSError, ValueError, QaEvidenceError):
        return None


def _state(path: Path) -> str:
    """Read a saved simulation as names with their face counts, or say it is absent."""
    if not path.is_file():
        return f"{path.name} absent"
    names = _names(path)
    faces = _faces(path)
    per = faces[1] if faces else None
    if names and per and len(per) == len(names):
        listed = ", ".join(f"{n}:{c}" for n, c in zip(names, per, strict=True))
    else:
        listed = ", ".join(names or ())
    total = faces[0] if faces else "?"
    return f"{path.name} {len(names or ())} boundaries [{listed}] {total} faces"


def _obj(path: Path) -> tuple[list[tuple[float, float, float]], int] | None:
    """Read an exported OBJ as its vertices and its face count, or None."""
    if not path.is_file():
        return None
    vertices: list[tuple[float, float, float]] = []
    faces = 0
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            words = line.partition("#")[0].split()
            if words[:1] == ["v"] and len(words) >= 4:
                vertices.append((float(words[1]), float(words[2]), float(words[3])))
            elif words[:1] == ["f"]:
                faces += 1
    except ValueError:
        return None
    return vertices, faces


def obj_summary(path: Path) -> str:
    """Name an OBJ export's size, bounding box and centroid azimuth about X."""
    read = _obj(path)
    if read is None or not read[0]:
        return f"{path.name} absent"
    vertices, faces = read
    array = np.asarray(vertices)
    low, high = array.min(axis=0), array.max(axis=0)
    centre = array.mean(axis=0)
    azimuth = math.degrees(math.atan2(float(centre[2]), float(centre[1])))
    box = ",".join(f"{a:.3f}..{b:.3f}" for a, b in zip(low, high, strict=True))
    return (
        f"{path.name} {len(vertices)} vertices {faces} faces box[{box}] "
        f"centroid({centre[0]:.3f},{centre[1]:.3f},{centre[2]:.3f}) azimuth_x {azimuth:.1f} deg"
    )


_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$")


def _rows(path: Path) -> list[list[float]]:
    """Return the all-numeric rows of a text export, split on spaces, commas or semicolons."""
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        tokens = [t for t in re.split(r"[\s,;]+", line.strip()) if t]
        if tokens and all(_NUMBER.match(t) for t in tokens):
            rows.append([float(t) for t in tokens])
    return rows


def _text_head(path: Path, lines: int = 3) -> str:
    if not path.is_file():
        return f"{path.name} absent"
    head = path.read_text(encoding="utf-8", errors="replace").splitlines()[:lines]
    return " | ".join(line.strip()[:80] for line in head)


def _export_summary(path: Path) -> str:
    """Summarise a numeric export: bytes, numeric rows, widths, column ranges, header."""
    if not path.is_file():
        return f"{path.name} absent"
    rows = _rows(path)
    widths = sorted({len(r) for r in rows})
    ranges = ""
    if rows:
        width = min(len(r) for r in rows)
        cols = np.asarray([r[:width] for r in rows])
        ranges = " ranges " + ",".join(
            f"{a:.3g}..{b:.3g}" for a, b in zip(cols.min(axis=0), cols.max(axis=0), strict=True)
        )
    return (
        f"{path.name} {path.stat().st_size} bytes, {len(rows)} numeric rows, widths {widths}"
        f"{ranges}; head: {_text_head(path)}"
    )


def _ccs_sections(path: Path) -> list[list[tuple[float, ...]]]:
    """Return the cross sections of a CCS text file as point lists."""
    if not path.is_file():
        return []
    sections = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().lower().startswith("crosssection"):
            values = [float(t) for t in line.split(";")[1:] if _NUMBER.match(t.strip())]
            sections.append([tuple(values[i : i + 3]) for i in range(0, len(values) - 2, 3)])
    return sections


def _ccs_summary(path: Path) -> str:
    sections = _ccs_sections(path)
    if not path.is_file():
        return f"{path.name} absent"
    parts = []
    for points in sections:
        array = np.asarray(points)
        if array.size:
            low, high = array.min(axis=0), array.max(axis=0)
            parts.append(
                f"{len(points)}pts x {low[0]:.3f}..{high[0]:.3f} y {low[1]:.3f}..{high[1]:.3f} "
                f"z {low[2]:.3f}..{high[2]:.3f} first ({array[0][0]:.3f},{array[0][2]:.3f})"
            )
    return f"{path.name} {len(sections)} sections [{'; '.join(parts)}]; head: {_text_head(path, 2)}"


def _faces_moved(direction: str, *, strict: bool, after: str = _AFTER) -> Judge:
    """Judge by the saved face count moving ``up`` or ``down`` across the target.

    Strict only when the caller states that an unmoved count can mean nothing
    but a target that did nothing; a missing state always reads unprobed.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        before = _faces(artifacts.workdir / _BEFORE)
        later = _faces(artifacts.workdir / after)
        if before is None or later is None:
            return None
        moved = later[0] > before[0] if direction == "up" else later[0] < before[0]
        if moved:
            return True
        return False if strict and later[0] == before[0] else None

    return check


def _boundaries_grew(after: str = _AFTER) -> Judge:
    """Judge by the saved boundary list growing; still or absent reads unprobed."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        before = _names(artifacts.workdir / _BEFORE)
        later = _names(artifacts.workdir / after)
        if before is None or later is None:
            return None
        return True if len(later) > len(before) else None

    return check


def _state_or_faces_moved(artifacts: ProbeArtifacts) -> bool | None:
    """Judge by the boundary list or the face count changing; still reads unprobed."""
    before = (_names(artifacts.workdir / _BEFORE), _faces(artifacts.workdir / _BEFORE))
    after = (_names(artifacts.workdir / _AFTER), _faces(artifacts.workdir / _AFTER))
    if None in before or None in after:
        return None
    return True if before != after else None


def _states_read(*extra: str) -> Reading:
    """Read the bracketing states, then each named extra file of the workdir."""

    def read(artifacts: ProbeArtifacts) -> str:
        unit = None
        if (artifacts.workdir / _AFTER).is_file():
            unit = saved_length_unit(artifacts.workdir / _AFTER)
        parts = [_state(artifacts.workdir / _BEFORE), _state(artifacts.workdir / _AFTER)]
        parts.append(f"length unit {unit}")
        for name in extra:
            path = artifacts.workdir / name
            if name.endswith(".obj"):
                parts.append(obj_summary(path))
            elif name.endswith(".fsm"):
                parts.append(_state(path))
            elif name.endswith(".ccs"):
                parts.append(_ccs_summary(path))
            else:
                parts.append(_export_summary(path))
        return "; ".join(parts)

    return read


def file_rows(name: str, minimum: int = 1) -> Judge:
    """Judge by an export holding numeric rows; absent or empty reads unprobed."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        return True if len(_rows(artifacts.workdir / name)) >= minimum else None

    return check


def emptied(name: str) -> Judge:
    """Judge a delete by the export after it: no rows True, rows False, absent unprobed."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        path = artifacts.workdir / name
        if not path.is_file():
            return None
        return len(_rows(path)) == 0

    return check


def _moved_vertices(before: Path, after: Path) -> list[tuple[tuple[float, ...], tuple[float, ...]]]:
    """Pair the vertices that left the mesh with those that arrived (rounded to 1e-6)."""
    first, second = _obj(before), _obj(after)
    if first is None or second is None:
        return []

    def key(v: tuple[float, float, float]) -> tuple[float, ...]:
        return tuple(round(c, 6) for c in v)

    old = {key(v) for v in first[0]}
    new = {key(v) for v in second[0]}
    gone, came = sorted(old - new), sorted(new - old)
    return list(zip(gone, came, strict=False))


def one_vertex_moved(by: tuple[float, float, float] | None) -> Judge:
    """Judge a node transform: exactly one vertex moved (by ``by`` when stated)."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        pairs = _moved_vertices(artifacts.workdir / "before.obj", artifacts.workdir / "after.obj")
        if len(pairs) != 1:
            return None
        if by is None:
            return True
        old, new = pairs[0]
        delta = tuple(n - o for n, o in zip(new, old, strict=True))
        return all(abs(d - b) < 1e-4 for d, b in zip(delta, by, strict=True)) or None

    return check


def _moved_read(artifacts: ProbeArtifacts) -> str:
    pairs = _moved_vertices(artifacts.workdir / "before.obj", artifacts.workdir / "after.obj")
    shown = "; ".join(f"{old} -> {new}" for old, new in pairs[:4])
    return f"{len(pairs)} vertices moved [{shown}]; " + obj_summary(artifacts.workdir / "after.obj")


def _obj_centroid_z(name: str, expected: float) -> Judge:
    """Judge by an exported surface's centroid height: at ``expected`` True, else False."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        read = _obj(artifacts.workdir / name)
        if read is None or not read[0]:
            return None
        z = float(np.mean([v[2] for v in read[0]]))
        return abs(z - expected) < 0.05

    return check


def _obj_range_moved(name: str, axis: int, reference: tuple[float, float]) -> Judge:
    """Judge by an exported surface's range on ``axis`` leaving ``reference``; still unprobed."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        read = _obj(artifacts.workdir / name)
        if read is None or not read[0]:
            return None
        values = [v[axis] for v in read[0]]
        moved = abs(min(values) - reference[0]) > 1e-3 or abs(max(values) - reference[1]) > 1e-3
        return True if moved else None

    return check


def _two_meshes_differ(left: str, right: str) -> Judge:
    """Judge by two exported surfaces differing in face count; equal or absent unprobed."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        a, b = _obj(artifacts.workdir / left), _obj(artifacts.workdir / right)
        if a is None or b is None or not a[1] or not b[1]:
            return None
        return True if a[1] != b[1] else None

    return check


def _primitive_exists(artifacts: ProbeArtifacts) -> bool | None:
    """Judge a primitive: a boundary right after it (a mesh) or after the conversion (a body)."""
    direct = _names(artifacts.workdir / _AFTER)
    converted = _names(artifacts.workdir / "saved.fsm")
    if direct or converted:
        return True
    return None


def _ccs_moved(name: str, reference: str) -> Judge:
    """Judge a curve operation by the exported CCS differing from the reference export."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        after = _ccs_sections(artifacts.workdir / name)
        before = _ccs_sections(artifacts.workdir / reference)
        if not after or not before:
            return None
        return True if after != before else None

    return check


def _ccs_written(name: str) -> Judge:
    def check(artifacts: ProbeArtifacts) -> bool | None:
        return True if _ccs_sections(artifacts.workdir / name) else None

    return check


def reordered(name: str) -> Judge:
    """Judge the reorder: the exported sections run in increasing y."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        sections = _ccs_sections(artifacts.workdir / name)
        if len(sections) < 2:
            return None
        ys = [float(np.mean([p[1] for p in s])) for s in sections if s]
        return True if ys == sorted(ys) else None

    return check


def _reversed_first_point(name: str, original_first: tuple[float, float]) -> Judge:
    """Judge the reverse: the section no longer starts at the file's first point."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        sections = _ccs_sections(artifacts.workdir / name)
        if not sections or not sections[0]:
            return None
        first = sections[0][0]
        same = abs(first[0] - original_first[0]) < 1e-6 and abs(first[2] - original_first[1]) < 1e-6
        return True if not same else None

    return check


def trajectory_read(name: str) -> Reading:
    """Read a trajectory export: header, first and last rows, and each column's change."""

    def read(artifacts: ProbeArtifacts) -> str:
        path = artifacts.workdir / name
        rows = _rows(path)
        if not rows:
            return _export_summary(path)
        width = min(len(r) for r in rows)
        first, last = rows[0][:width], rows[-1][:width]
        deltas = ",".join(f"{b - a:.4g}" for a, b in zip(first, last, strict=True))
        return f"{_export_summary(path)}; first {first}; last {last}; column changes [{deltas}]"

    return read


def trajectory_moved(name: str) -> Judge:
    """Judge by the trajectory holding two rows and a column other than the first changing."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        rows = _rows(artifacts.workdir / name)
        if len(rows) < 2:
            return None
        width = min(len(r) for r in rows)
        changed = [abs(rows[-1][i] - rows[0][i]) > 1e-9 for i in range(1, width)]
        return True if any(changed) else None

    return check


#: The probe wing: chord 1 m, span 4 m centred on y = 0, coarse.
_WING = WingSpec(naca="0012", chord_m=1.0, span_m=4.0, n_chord=8, n_span=8)


#: A second, coarser wing with a different face count, for selection probes.
_SMALL_WING = WingSpec(naca="0012", chord_m=0.5, span_m=1.0, n_chord=6, n_span=4)


def box_triangles(*, hole: bool, degenerate: bool) -> np.ndarray:
    """Return a unit cube's twelve triangles, minus the top two for a hole, plus a sliver."""
    p = [(x, y, z) for z in (0.0, 1.0) for y in (0.0, 1.0) for x in (0.0, 1.0)]
    quads = [
        (0, 2, 3, 1),  # bottom
        (4, 5, 7, 6),  # top
        (0, 1, 5, 4),  # y = 0
        (2, 6, 7, 3),  # y = 1
        (0, 4, 6, 2),  # x = 0
        (1, 3, 7, 5),  # x = 1
    ]
    triangles = []
    for index, (a, b, c, d) in enumerate(quads):
        if hole and index == 1:
            continue
        triangles.append((p[a], p[b], p[c]))
        triangles.append((p[a], p[c], p[d]))
    if degenerate:
        # Three distinct points on the bottom edge y = 0, z = 0: zero area.
        triangles.append(((0.0, 0.0, 0.0), (0.5, 0.0, 0.0), (1.0, 0.0, 0.0)))
    return np.asarray(triangles, dtype=float)


def _iges_line(text: str, section: str, number: int) -> str:
    return f"{text:<72}{section}{number:>7}"


def iges_two_sheets_text() -> str:
    """Return a two-body IGES file: two flat bilinear patches, a unit sheet and a half sheet.

    Sheet A spans x and y from 0 to 1 at z = 0; sheet B spans 0 to 0.5 at z = 2,
    so which body an operation acted on reads from the converted surface's
    position. Each patch is one rational B-spline surface (entity 128) of degree
    one in both directions, written in the fixed eighty-column layout.
    """
    patches = [
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)],
        [(0.0, 0.0, 2.0), (0.5, 0.0, 2.0), (0.0, 0.5, 2.0), (0.5, 0.5, 2.0)],
    ]
    start = [_iges_line("pyflightstream synthetic two-sheet IGES probe input", "S", 1)]
    global_fields = (
        "1H,,1H;,5HPYFSP,9Hsheet.igs,14Hpyflightstream,3H1.0,32,38,6,308,15,5HPYFSP,"
        "1.0,6,1HM,1,1.0,15H20261012.120000,1.0E-6,10.0,4HPYFS,4HPYFS,11,0,"
        "15H20261012.120000;"
    )
    glob = [
        _iges_line(global_fields[i : i + 72], "G", n + 1)
        for n, i in enumerate(range(0, len(global_fields), 72))
    ]
    parameters: list[str] = []
    directory: list[str] = []
    for index, corners in enumerate(patches):
        de = 2 * index + 1
        values = ["128", "1", "1", "1", "1", "0", "0", "1", "0", "0"]
        values += ["0.0", "0.0", "1.0", "1.0", "0.0", "0.0", "1.0", "1.0"]
        values += ["1.0"] * 4
        for x, y, z in corners:
            values += [f"{x:.4f}", f"{y:.4f}", f"{z:.4f}"]
        values += ["0.0", "1.0", "0.0", "1.0"]
        record = ",".join(values) + ";"
        first = len(parameters) + 1
        chunk = 64
        for i in range(0, len(record), chunk):
            text = f"{record[i : i + chunk]:<64}{de:>8}"
            parameters.append(_iges_line(text, "P", len(parameters) + 1))
        count = len(parameters) - first + 1
        fields1 = ["128", str(first), "0", "0", "0", "0", "0", "0", "00000000"]
        fields2 = ["128", "0", "0", str(count), "0", "", "", "SHEET", str(index + 1)]
        directory.append(_iges_line("".join(f"{f:>8}" for f in fields1), "D", de))
        directory.append(_iges_line("".join(f"{f:>8}" for f in fields2), "D", de + 1))
    counts = f"S{len(start):>7}G{len(glob):>7}D{len(directory):>7}P{len(parameters):>7}"
    terminate = [_iges_line(counts, "T", 1)]
    return "\n".join(start + glob + directory + parameters + terminate) + "\n"


#: The NACA 0012 section of the use case's ``naca0012.txt``: two columns, x and
#: the out-of-plane coordinate, no header, trailing edge to leading edge and back.
def _naca_points(count: int = 9) -> list[tuple[float, float]]:
    xs = [0.5 * (1.0 - math.cos(math.pi * i / (count - 1))) for i in range(count)]

    def half(x: float) -> float:
        return 0.6 * (0.2969 * math.sqrt(x) - 0.126 * x - 0.3516 * x**2 + 0.2843 * x**3)

    upper = [(x, half(x)) for x in reversed(xs)]
    lower = [(x, -half(x)) for x in xs[1:]]
    return upper + lower


_SECTION_TXT = "naca0012.txt"


_ROOT_3D, _TIP_3D = "root_3d.txt", "tip_3d.txt"


_CURVE_P3D = "section.p3d"


def _section_files(workdir: Path) -> None:
    """Write the 2D section, the 3D root (y = 0) and tip (y = 2) sections and a P3D curve."""
    points = _naca_points()
    _textio.write_text(workdir / _SECTION_TXT, "".join(f"{x:.6f} {z:.6f}\n" for x, z in points))
    _textio.write_text(
        workdir / _ROOT_3D, "".join(f"{x:.6f} 0.000000 {z:.6f}\n" for x, z in points)
    )
    _textio.write_text(
        workdir / _TIP_3D,
        "".join(f"{0.2 + 0.6 * x:.6f} 2.000000 {0.6 * z:.6f}\n" for x, z in points),
    )
    xs = " ".join(f"{x:.6f}" for x, _ in points)
    ys = " ".join("0.000000" for _ in points)
    zs = " ".join(f"{z:.6f}" for _, z in points)
    _textio.write_text(workdir / _CURVE_P3D, f"1\n{len(points)} 1 1\n{xs}\n{ys}\n{zs}\n")


def fsi_standin_source() -> str:
    """Return the stand-in structural program: it logs each call and answers with zeros.

    Called by the solver at a coupling step, it records the time, its working
    directory and its arguments in ``fsi_standin_calls.log`` (in the working
    directory and beside itself), archives the text files it finds there with a
    listing into ``fsi_standin_calls/call_NNNN``, and writes ``FSIDisp.txt`` with
    one zero displacement per line of ``fsi_nodes.txt`` when that node file is in
    the working directory (the comma-separated format of the package's dummy
    step). It computes nothing.
    """
    return '''"""Stand-in structural program of the gap probes: logs, answers zeros."""
import datetime
import os
import shutil
import sys
from pathlib import Path


def main():
    here = Path(os.getcwd())
    stamp = datetime.datetime.now().isoformat(timespec="milliseconds")
    calls = here / "fsi_standin_calls"
    calls.mkdir(exist_ok=True)
    number = 1 + len(list(calls.glob("call_*")))
    archive = calls / f"call_{number:04d}"
    archive.mkdir()
    files = sorted(p for p in here.iterdir() if p.is_file())
    for path in files:
        small = path.stat().st_size < 5000000
        own = path.name.startswith("fsi_standin")
        if small and path.suffix.lower() in (".txt", ".csv", ".dat") and not own:
            shutil.copy2(path, archive / path.name)
    listing = "".join(f"{p.name}\\t{p.stat().st_size}\\n" for p in files)
    (archive / "directory_listing.txt").write_text(listing, encoding="utf-8")
    nodes = here / "fsi_nodes.txt"
    if nodes.is_file():
        count = sum(1 for line in nodes.read_text(encoding="utf-8").splitlines() if line.strip())
        zero = "0.000000000000e+00,0.000000000000e+00,0.000000000000e+00"
        (here / "FSIDisp.txt").write_text("\\n".join([zero] * count) + "\\n", encoding="utf-8")
    line = f"{stamp} call {number} cwd {here} argv {sys.argv[1:]}\\n"
    targets = {here, Path(sys.argv[0]).resolve().parent}
    for folder in targets:
        try:
            with open(folder / "fsi_standin_calls.log", "a", encoding="utf-8") as log:
                log.write(line)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


_STANDIN_PY = "fsi_standin.py"


_STANDIN_LOG = "fsi_standin_calls.log"


_NODES = "fsi_nodes.txt"


def _windowless_python() -> Path:
    """Return the windowless interpreter beside this one, or this one where none exists."""
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return candidate if candidate.is_file() else Path(sys.executable)


def _write_standin(workdir: Path) -> Path:
    path = workdir / _STANDIN_PY
    _textio.write_text(path, fsi_standin_source())
    # The wing's quarter chord line, nine nodes along the span, X,Y,Z per line.
    nodes = "".join(f"0.250000,{-2.0 + 0.5 * i:.6f},0.000000\n" for i in range(9))
    _textio.write_text(workdir / _NODES, nodes)
    return path


def _calls_read(artifacts: ProbeArtifacts) -> str:
    log = artifacts.workdir / _STANDIN_LOG
    if not log.is_file():
        return "the stand-in was not called (no call log in the probe folder)"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    listing = artifacts.workdir / "fsi_standin_calls" / "call_0001" / "directory_listing.txt"
    seen = (
        listing.read_text(encoding="utf-8", errors="replace").replace("\n", ", ")[:400]
        if listing.is_file()
        else "no listing"
    )
    return f"{len(lines)} calls; first: {lines[0][:200] if lines else ''}; files at call 1: {seen}"


def _called(artifacts: ProbeArtifacts) -> bool | None:
    log = artifacts.workdir / _STANDIN_LOG
    return True if log.is_file() and log.stat().st_size > 0 else None


def _wing_file(
    workdir: Path,
    name: str = "Wing",
    spec: WingSpec = _WING,
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    half: bool = False,
) -> Path:
    return generate_wing_stl(
        spec, workdir / f"{name.lower()}.stl", half=half, translation_m=translation, name=name
    )


def _import_wing(
    name: str = "Wing",
    spec: WingSpec = _WING,
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    *,
    new: bool = True,
    half: bool = False,
) -> Build:
    """Open a new simulation (unless ``new`` is False) and import one synthetic wing in metres."""

    def build(script: Script, workdir: Path) -> None:
        path = _wing_file(workdir, name, spec, translation, half)
        if new:
            script.emit("NEW_SIMULATION")
        script.emit("IMPORT", "METER", "STL", path, clear=new)

    return build


def _import_box(*, hole: bool, degenerate: bool) -> Build:
    def build(script: Script, workdir: Path) -> None:
        path = write_stl(
            box_triangles(hole=hole, degenerate=degenerate), workdir / "box.stl", name="Box"
        )
        script.emit("NEW_SIMULATION")
        script.emit("IMPORT", "METER", "STL", path, clear=True)

    return build


def _export(surface: int, filename: str) -> Build:
    def build(script: Script, workdir: Path) -> None:
        script.emit("EXPORT_SURFACE_MESH", "OBJ", surface, workdir / filename)

    return build


def _exports(count: int, stem: str = "surface") -> Build:
    return _seq(*(_export(i, f"{stem}_{i}.obj") for i in range(1, count + 1)))


def _save(filename: str) -> Build:
    def build(script: Script, workdir: Path) -> None:
        script.emit("SAVEAS", workdir / filename)

    return build


def _threshold(
    minimum: float, maximum: float, *, subset: str = "ALL_FACES", axis: str = "X"
) -> Build:
    return _emit(
        "SURFACE_SELECT_BY_THRESHOLD",
        frame=1,
        threshold=axis,
        min_value=minimum,
        max_value=maximum,
        range="ABOVE_MIN_BELOW_MAX",
        subset=subset,
    )


def _iges_import(script: Script, workdir: Path) -> None:
    path = workdir / "two_sheets.igs"
    _textio.write_text(path, iges_two_sheets_text())
    script.emit("NEW_SIMULATION")
    script.emit("IMPORT_CAD", "MEDIUM", "TRUE", 20, path)


def _convert(body: int) -> Build:
    return _emit("CONVERT_CAD_TO_MESH", body)


def _cad_session(*files: str, select: bool = True) -> Build:
    """Open the CAD Create session on a new simulation and import section files."""

    def build(script: Script, workdir: Path) -> None:
        _section_files(workdir)
        script.emit("NEW_SIMULATION")
        script.emit("CAD_CREATE_INITIALIZE")
        for name in files:
            dimensions = "2D" if name == _SECTION_TXT else "3D"
            script.emit("CAD_CREATE_IMPORT_CURVE_TXT", "METER", dimensions, 1, "XZ", workdir / name)
        if select:
            script.emit("CAD_CREATE_CURVE_SELECT", -1)

    return build


def _export_ccs(filename: str) -> Build:
    def build(script: Script, workdir: Path) -> None:
        script.emit("CAD_CREATE_CURVE_EXPORT_CCS", workdir / filename)

    return build


def _flow(*, steady: bool, velocity: float = 30.0, steps: int = 20, dt: float = 0.02) -> Build:
    """Emit the free stream, the references and the solver mode (steady or unsteady)."""

    def build(script: Script, workdir: Path) -> None:
        script.emit("SET_FREESTREAM", "CONSTANT")
        script.allow_broken(
            "AIR_ALTITUDE",
            reason=(
                "gap probe prelude sets sea level, and the recorded METERS-as-FEET "
                "defect cannot change an altitude of zero"
            ),
        )
        script.emit("AIR_ALTITUDE", 0.0, "METERS")
        script.emit("SOLVER_SET_VELOCITY", velocity)
        script.emit("SOLVER_SET_REF_VELOCITY", velocity)
        script.emit("SOLVER_SET_REF_AREA", 4.0)
        script.emit("SOLVER_SET_REF_LENGTH", 1.0)
        if steady:
            script.emit("SOLVER_SET_ITERATIONS", 20)
            script.emit("SET_SOLVER_STEADY")
        else:
            script.emit("SET_SOLVER_UNSTEADY", time_iterations=steps, delta_time=dt)

    return build


def _units_and_edges(script: Script, workdir: Path) -> None:
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    detect_every_boundary(script, "trailing_edges")


def _start(symmetry: str = "NONE") -> Build:
    def build(script: Script, workdir: Path) -> None:
        initialize_solver(script, symmetry=symmetry)
        script.emit("START_SOLVER")

    return build


def _solved_wing(aoa: float = 4.0) -> Build:
    """Build a steady solved point on the probe wing, ready for analysis-phase targets."""
    return _seq(
        _import_wing(),
        _units_and_edges,
        _flow(steady=True),
        _emit("SOLVER_SET_AOA", aoa),
        _start(),
    )


def _seed_line(script: Script, workdir: Path) -> None:
    """Three seeds on a vertical line one chord ahead of the wing, off the span centre."""
    script.emit(
        "NEW_STREAMLINE_DISTRIBUTION",
        position_1_x=-1.0,
        position_1_y=0.5,
        position_1_z=-0.2,
        position_2_x=-1.0,
        position_2_y=0.5,
        position_2_z=0.2,
        subdivisions=3,
    )


def _offbody_export(filename: str = "offbody.txt") -> Build:
    def build(script: Script, workdir: Path) -> None:
        script.emit("GENERATE_ALL_OFF_BODY_STREAMLINES")
        script.emit("EXPORT_ALL_OFF_BODY_STREAMLINES", workdir / filename)

    return build


def _offbody_file(filename: str) -> Build:
    """Export the off-body lines, addressed absolutely like every probe file."""

    def build(script: Script, workdir: Path) -> None:
        script.emit("EXPORT_ALL_OFF_BODY_STREAMLINES", workdir / filename)

    return build


def _surface_export(filename: str = "surface_lines.txt") -> Build:
    def build(script: Script, workdir: Path) -> None:
        script.emit("EXPORT_ALL_SURFACE_STREAMLINES", workdir / filename)

    return build


def _motion(kind: str) -> Build:
    """Create one motion of ``kind`` on every boundary, about a frame at the quarter chord."""

    def build(script: Script, workdir: Path) -> None:
        script.emit("CREATE_NEW_COORDINATE_SYSTEM")
        script.emit(
            "EDIT_COORDINATE_SYSTEM",
            frame=2,
            name="PYFS_GAP_CG",
            origin_x=0.25,
            origin_y=0.0,
            origin_z=0.0,
            vector_x_x=1.0,
            vector_x_y=0.0,
            vector_x_z=0.0,
            vector_y_x=0.0,
            vector_y_y=1.0,
            vector_y_z=0.0,
            vector_z_x=0.0,
            vector_z_y=0.0,
            vector_z_z=1.0,
        )
        script.emit("CREATE_NEW_MOTION", kind)
        script.emit("SET_MOTION_BOUNDARIES", 1, -1)
        script.emit("SET_MOTION_COORDINATE_SYSTEM", 1, 2)

    return build


_TRAJECTORY = "trajectory.txt"


_ALL_FREE = ("U ENABLE", "V ENABLE", "W ENABLE", "P ENABLE", "Q ENABLE", "R ENABLE")


_PITCH_ONLY = ("U DISABLE", "V DISABLE", "W DISABLE", "P DISABLE", "Q ENABLE", "R DISABLE")


def _sixdof_body(
    *,
    mass: bool = True,
    gravity: bool = False,
    active: tuple[str, ...] | None = _ALL_FREE,
    half: bool = False,
) -> Build:
    """Put the wing on a 6DOF motion with its mass, gravity and freedoms (the P4 prelude)."""

    def build(script: Script, workdir: Path) -> None:
        _import_wing(half=half)(script, workdir)
        _units_and_edges(script, workdir)
        _motion("6DOF")(script, workdir)
        if mass:
            script.emit("SET_MOTION_MASS_PROPERTIES", 1, 100.0, 10.0, 10.0, 10.0, 0.0, 0.0, 0.0)
        if gravity:
            script.emit("SET_MOTION_GRAVITY", 1, 0.0, 0.0, -9.81)
        if active is not None:
            script.emit("SET_MOTION_6DOF_ACTIVE_VARIABLES", 1, list(active))

    return build


def _trajectory_export(script: Script, workdir: Path) -> None:
    script.emit("EXPORT_6DOF_TRAJECTORY", 1, workdir / _TRAJECTORY)


def _march(*, symmetry: str = "NONE", steps: int = 20) -> Build:
    """March slowly, one metre per second, so gravity and the stated loads dominate."""
    return _seq(_flow(steady=False, velocity=1.0, steps=steps, dt=0.02), _start(symmetry))


def _trajectory_then_march(symmetry: str = "NONE") -> Build:
    return _seq(_trajectory_export, _march(symmetry=symmetry))


def _after_the_march_trajectory(script: Script, workdir: Path) -> None:
    """Write the trajectory export after the march, a placement the phase order refuses.

    The line is rendered by a validated emission on a scratch script of the same
    build, then appended unvalidated, so its grammar is the database's while its
    position is the one the probe measures (P4 probe 4). The script is flagged
    raw, which is why this probe stays in the battery and out of ``PROBE_SPECS``.
    """
    scratch = Script(script.version, registry=script.registry)
    scratch.declare_existing(motions=script.num_motions)
    scratch.emit("EXPORT_6DOF_TRAJECTORY", 1, workdir / _TRAJECTORY)
    script.raw(scratch.render())


def _write_standin_build(script: Script, workdir: Path) -> None:
    _write_standin(workdir)


def _not_called(artifacts: ProbeArtifacts) -> bool | None:
    if artifacts.log_final() is None:
        return None
    return not (artifacts.workdir / _STANDIN_LOG).is_file()


def _saved_names_file(name: str) -> Judge:
    """Judge by the executable's file name entering the saved simulation; absent unprobed."""
    token = name.encode("ascii", errors="ignore")

    def check(artifacts: ProbeArtifacts) -> bool | None:
        before = artifacts.workdir / _BEFORE
        after = artifacts.workdir / _AFTER
        if not before.is_file() or not after.is_file():
            return None
        gained = token in after.read_bytes() and token not in before.read_bytes()
        return True if gained else None

    return check


def _seq_read(*readers: Reading) -> Reading:
    def read(artifacts: ProbeArtifacts) -> str:
        return "; ".join(reader(artifacts) for reader in readers)

    return read


def _new_surface_matches(source: int) -> Judge:
    """Judge by the last boundary of saved.fsm having the face count of boundary ``source``."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        faces = _faces(artifacts.workdir / "saved.fsm")
        if faces is None or faces[1] is None or len(faces[1]) <= source:
            return None
        return True if faces[1][-1] == faces[1][source - 1] else None

    return check


def _only_sheet_a(artifacts: ProbeArtifacts) -> bool | None:
    names = _names(artifacts.workdir / "saved.fsm")
    if not names:
        return None
    if len(names) >= 2:
        return False
    read = _obj(artifacts.workdir / "surface_1.obj")
    if read is None or not read[0]:
        return None
    return abs(float(np.mean([v[2] for v in read[0]]))) < 0.05 or None


def _import_txt(name: str) -> Build:
    def build(script: Script, workdir: Path) -> None:
        dimensions = "2D" if name == _SECTION_TXT else "3D"
        script.emit("CAD_CREATE_IMPORT_CURVE_TXT", "METER", dimensions, 1, "XZ", workdir / name)

    return build


def _import_p3d(script: Script, workdir: Path) -> None:
    script.emit("CAD_CREATE_IMPORT_CURVE_P3D", "METER", "FALSE", 1, 1, workdir / _CURVE_P3D)


def _read_back_and_loft(filename: str) -> Build:
    def build(script: Script, workdir: Path) -> None:
        script.emit("CAD_CREATE_INITIALIZE")
        script.emit("CAD_CREATE_IMPORT_CURVE_CCS", "METER", 1, 1, workdir / filename)
        _ccs_select(script, workdir)
        _ccs_assign(1)(script, workdir)
        _wing_loft("PYFS_LOFTED")(script, workdir)

    return build


def _custom_force(script: Script, workdir: Path) -> None:
    path = workdir / "pulse_force.txt"
    _textio.write_text(path, "0.000 0.0\n0.010 0.0\n0.015 -20.0\n0.020 0.0\n1.000 0.0\n")
    script.emit("CREATE_NEW_6DOF_CUSTOM_FORCE", 1, "FORCE_VS_TIME", path)


def _write_post(script: Script, workdir: Path) -> None:
    """Write the package's aeroelastic post-processing script and name it to the solver.

    The script is the one the fixed-wing FSI route stages (the sectional loads
    exported as the file the PyNite beam reads), so the stand-in sees the file
    exchange the package already uses.
    """
    path = workdir / "fsi_post.txt"
    _textio.write_text(path, aeroelastic_post_script(script.version))
    script.emit("SET_AEROELASTIC_POST_PROCESSING_SCRIPT", path)


def _sections_then_start(script: Script, workdir: Path) -> None:
    initialize_solver(script)
    script.emit(
        "NEW_SURFACE_SECTION_DISTRIBUTION",
        frame=1,
        plane="XZ",
        num_sections=8,
        plot_direction="1",
        surfaces=-1,
    )
    script.emit("START_SOLVER")


def _pod_ccs_text(direction: int) -> str:
    """Return a one-component CCS fuselage pod whose Relaxed_TE line sheds in ``direction``."""
    lines = ["Aircraft;PYFS_GAP", "Units;Meter", "", "Component;PYFS_POD", "LiftingSurface;false"]
    lines.append(f"Relaxed_TE;0.5;0.2;0.8;{direction}")
    for x, radius in ((0.1, 0.19), (1.0, 0.5), (2.0, 0.19)):
        ring = []
        for k in range(9):
            angle = 2.0 * math.pi * k / 8
            ring.append(f"{x:.6f};{radius * math.cos(angle):.6f};{radius * math.sin(angle):.6f}")
        lines.append("CrossSection;" + ";".join(ring))
    return "\n".join(lines) + "\n"


def _pod_import(direction: int) -> Build:
    def build(script: Script, workdir: Path) -> None:
        path = workdir / "pod_relaxed.csv"
        _textio.write_text(path, _pod_ccs_text(direction))
        script.emit("NEW_SIMULATION")
        script.emit(
            "CCS_IMPORT",
            close_component_ends="DISABLE",
            update_properties="DISABLE",
            clear_existing="ENABLE",
            file=path,
        )

    return build


def mesh_edges(path: Path) -> dict[str, object]:
    """Read a saved mesh block's face shapes and the edges its slot rows mark, quads included.

    The package's reader (``pyflightstream._fsm``) reads triangles only, measured
    on the solver's saves (RPT-065): three vertex-index rows, then per-face rows
    up to five T/F rows, the second to fourth of which flag the edges (1,2),
    (2,3) and (3,1). A loft may save quadrilaterals, whose layout no run has
    measured, and a reader that refuses them would leave a loft's edges
    unprobed for a reason that is not the loft's. So this probe reader carries
    the stated hypothesis for a block whose faces have up to K corners: K
    vertex-index rows, then the T/F rows, of which rows 2 to K+1 flag the edges
    (i, i+1) of each face, wrapping on the face's own corner count. Whatever it
    finds is reported with the face shapes and the T/F row count, so the
    reading shows when the hypothesis did not hold; the format becomes the
    package reader's once a run has measured it.
    """
    result: dict[str, object] = {"edges": None}
    if not path.is_file():
        result["error"] = f"{path.name} absent"
        return result
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = next(i for i, line in enumerate(lines) if line.strip() == _MESH_MARKER) + 1
        rows = _BlockRows(lines[start:])
        rows.skip(2)
        rows.skip(3 * int(rows.next_line()))
        faces = int(rows.next_line())
        rows.tokens()
        corners = [int(t) for t in rows.tokens()]
        result["face_shapes"] = {str(k): corners.count(k) for k in sorted(set(corners))}
        slots = [
            [int(t) - 1 if t.lstrip("-").isdigit() else -1 for t in rows.tokens()]
            for _ in range(max(corners))
        ]
        flags, after = rows.flag_rows(faces)
        result["flag_rows"] = len(flags)
        if after != ["0"]:
            result["error"] = f"the line after the T/F rows reads {after[:3]}"
            return result
        rows.next_line()
        axes = [[float(t) for t in rows.tokens()] for _ in range(3)]
        vertices = list(zip(*axes, strict=True))
        result["edges"] = len(_marked_midpoints(vertices, corners, slots, flags))
    except (StopIteration, ValueError, IndexError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    return result


class _BlockRows:
    """Step through the rows of a mesh block, comma-separated tokens per row."""

    def __init__(self, lines: list[str]) -> None:
        self._rows = iter(lines)

    def next_line(self) -> str:
        return next(self._rows).strip()

    def skip(self, count: int) -> None:
        for _ in range(count):
            next(self._rows)

    def tokens(self) -> list[str]:
        return [t.strip() for t in next(self._rows).split(",") if t.strip()]

    def flag_rows(self, faces: int) -> tuple[list[list[bool]], list[str]]:
        """Skip the per-face number rows, read the T/F rows, and return the row after them."""
        flags: list[list[bool]] = []
        while True:
            row = self.tokens()
            if row and set(row) <= {"T", "F"} and len(row) == faces:
                flags.append([t == "T" for t in row])
            elif flags:
                return flags, row


def _marked_midpoints(
    vertices: list[tuple[float, ...]],
    corners: list[int],
    slots: list[list[int]],
    flags: list[list[bool]],
) -> set[tuple[float, ...]]:
    """Return the mid-points of the edges T/F rows 2 to K+1 flag, edge (i, i+1) per face."""
    found: set[tuple[float, ...]] = set()
    for edge_row in range(1, min(len(slots) + 1, len(flags))):
        slot = edge_row - 1
        for face, flagged in enumerate(flags[edge_row]):
            n = corners[face]
            if flagged and slot < n:
                a = vertices[slots[slot][face]]
                b = vertices[slots[(slot + 1) % n][face]]
                found.add(tuple(round((p + q) / 2, 9) for p, q in zip(a, b, strict=True)))
    return found


def edge_count(path: Path) -> int | None:
    """Count the trailing edges a saved simulation marks, or None when it cannot be read."""
    if not path.is_file():
        return None
    try:
        return len(trailing_edge_midpoints(path))
    except (OSError, ValueError, QaEvidenceError):
        found = mesh_edges(path).get("edges")
        return found if isinstance(found, int) else None


def edges_kept(name: str) -> Judge:
    """Judge a loft asked to mark its trailing edges: marked True, none False, unreadable None.

    Strict on a read file, triangles or quadrilaterals alike (:func:`mesh_edges`):
    a loft told to mark its trailing edges that saves none did not do what it was
    asked. Only a block neither reader can read records unprobed.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        found = edge_count(artifacts.workdir / name)
        if found is None:
            return None
        return found > 0

    return check


def _edges_read(name: str, *extra: str) -> Reading:
    states = _states_read(name, *extra)

    def read(artifacts: ProbeArtifacts) -> str:
        path = artifacts.workdir / name
        found = edge_count(path)
        shape = mesh_edges(path)
        shown = {k: v for k, v in shape.items() if k != "edges"}
        return f"{name} marks {found} trailing edges, block {shown}; " + states(artifacts)

    return read


def _boundaries_at_least(name: str, count: int) -> Judge:
    def check(artifacts: ProbeArtifacts) -> bool | None:
        names = _names(artifacts.workdir / name)
        return True if names and len(names) >= count else None

    return check


def _file_written(name: str) -> Judge:
    def check(artifacts: ProbeArtifacts) -> bool | None:
        path = artifacts.workdir / name
        return True if path.is_file() and path.stat().st_size > 0 else None

    return check


def _deflected(angle: float) -> Build:
    """Emit the reopen probes' control surface in the ten-argument PARAMETRIC form."""
    return _emit(
        "NEW_CCS_WING_CONTROL_SURFACE",
        "PYFS_AIL",
        0.5,
        0.9,
        0.25,
        0.25,
        0.5,
        angle,
        1.0,
        "PARAMETRIC",
        "Y",
    )


_DEFLECTED = _deflected(20.0)


_CCS_WING_CURVES = _seq(_ccs_initialize, _ccs_import(1), _ccs_select, _ccs_assign(1))


def _opened_file(script: Script) -> Path | None:
    """Return the simulation file the script's tier prelude opened, read off its OPEN line."""
    lines = script.render().splitlines()
    for index, line in enumerate(lines):
        words = line.split(maxsplit=1)
        if words[:1] == ["OPEN"]:
            if len(words) == 2:
                return Path(words[1].strip())
            if index + 1 < len(lines) and lines[index + 1].strip():
                return Path(lines[index + 1].strip())
    return None


_MARKS_FILE = "source_marks.txt"


_MARKS_COUNT = "source_marks_count.txt"


def _reimport_with_marks(obj_name: str, edge_type: str) -> Build:
    """Open nothing new but the source's OBJ, and write the points file of the source's marks.

    The tier prelude opened the source probe's ``saved.fsm``; its marked edges
    (read here, at build time, from that file) become the points file, and the
    OBJ the source exported beside it is imported into a new simulation in
    metres. The count is kept in the probe folder for the judge.
    """

    def build(script: Script, workdir: Path) -> None:
        source = _opened_file(script)
        midpoints: tuple[tuple[float, float, float], ...] = ()
        if source is not None and source.is_file():
            try:
                midpoints = trailing_edge_midpoints(source)
            except (OSError, ValueError):
                midpoints = ()
        _textio.write_text(workdir / _MARKS_FILE, render_wake_edge_node_file(midpoints))
        _textio.write_text(workdir / _MARKS_COUNT, f"{len(midpoints)}\n")
        obj = (source.parent if source is not None else workdir) / obj_name
        script.emit("NEW_SIMULATION")
        script.emit("IMPORT", "METER", "OBJ", obj, clear=True)
        script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")

    return build


def _import_marks(edge_type: str) -> Build:
    def build(script: Script, workdir: Path) -> None:
        token = wake_edge_import_token(script, "METER")
        script.emit("IMPORT_WAKE_EDGES_FROM_FILE", edge_type, 0.0001, token, workdir / _MARKS_FILE)

    return build


def _marks_reproduced(artifacts: ProbeArtifacts) -> bool | None:
    """Judge the points-file route: the saved marks number what the source marked."""
    count_file = artifacts.workdir / _MARKS_COUNT
    if not count_file.is_file():
        return None
    expected = int(count_file.read_text(encoding="utf-8").strip() or 0)
    found = edge_count(artifacts.workdir / "saved.fsm")
    if not expected or found is None:
        return None
    return True if found == expected else None


def _marks_read(artifacts: ProbeArtifacts) -> str:
    count_file = artifacts.workdir / _MARKS_COUNT
    expected = count_file.read_text(encoding="utf-8").strip() if count_file.is_file() else "?"
    return f"source marked {expected}; " + _edges_read("saved.fsm")(artifacts)


def _write_obj(triangles: np.ndarray, path: Path, scale: float = 1.0) -> Path:
    """Write triangles as an OBJ, vertices shared, faces in the given order."""
    index: dict[tuple[float, ...], int] = {}
    faces = []
    for triangle in triangles:
        face = []
        for corner in triangle:
            key = tuple(round(float(c) * scale, 9) for c in corner)
            face.append(index.setdefault(key, len(index) + 1))
        faces.append(face)
    body = ["# pyflightstream synthetic probe body"]
    body += [f"v {x:.9g} {y:.9g} {z:.9g}" for (x, y, z) in index]
    body += ["f " + " ".join(str(i) for i in face) for face in faces]
    _textio.write_text(path, "\n".join(body) + "\n")
    return path


def _obj_source(name: str, *, scale: float = 1.0, reverse: bool = False) -> Build:
    def build(script: Script, workdir: Path) -> None:
        triangles = wing_triangles(_WING)
        if reverse:
            triangles = triangles[::-1]
        units = "MILLIMETER" if scale != 1.0 else "METER"
        path = _write_obj(triangles, workdir / name, scale)
        script.emit("NEW_SIMULATION")
        script.emit("IMPORT", units, "OBJ", path, clear=True)

    return build


def _face_order_read(source: str, exported: str) -> Reading:
    """Compare the face sequence of an exported OBJ with its source, as corner sets."""

    def faces(path: Path) -> list[frozenset[tuple[float, ...]]] | None:
        if not path.is_file():
            return None
        vertices: list[tuple[float, ...]] = []
        out: list[frozenset[tuple[float, ...]]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            words = line.split()
            if words[:1] == ["v"]:
                vertices.append(tuple(round(float(w), 5) for w in words[1:4]))
            elif words[:1] == ["f"]:
                out.append(frozenset(vertices[int(w.split("/")[0]) - 1] for w in words[1:]))
        return out

    def read(artifacts: ProbeArtifacts) -> str:
        a, b = faces(artifacts.workdir / source), faces(artifacts.workdir / exported)
        if a is None or b is None:
            return f"{source} or {exported} absent"
        same = sum(1 for x, y in zip(a, b, strict=False) if x == y)
        first = next((i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), None)
        return (
            f"source {len(a)} faces, export {len(b)} faces, {same} at the same position, "
            f"first difference at face {first}, same set {set(a) == set(b)}"
        )

    return read


def _groups_read(name: str) -> Reading:
    def read(artifacts: ProbeArtifacts) -> str:
        path = artifacts.workdir / name
        if not path.is_file():
            return f"{name} absent; " + _state(artifacts.workdir / "saved.fsm")
        groups = [
            line.strip()
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line[:2] in ("o ", "g ")
        ]
        return f"{name} groups {groups[:12]}; " + _state(artifacts.workdir / "saved.fsm")

    return read


def _emit_export_all(name: str) -> Build:
    def build(script: Script, workdir: Path) -> None:
        script.emit("EXPORT_SURFACE_MESH", "OBJ", -1, workdir / name)

    return build


def _export_format(fmt: str) -> Build:
    def build(script: Script, workdir: Path) -> None:
        script.emit("EXPORT_SURFACE_MESH", fmt, 1, workdir / f"wing.{fmt.lower()}")

    return build
