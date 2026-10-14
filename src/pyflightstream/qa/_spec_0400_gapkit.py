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
from pathlib import Path

import numpy as np

import pyflightstream._textio as _textio
from pyflightstream.cases.fsi_workspace import aeroelastic_post_script
from pyflightstream.qa._spec_0400_gapbase import (
    _AFTER as _AFTER,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _BEFORE as _BEFORE,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _NUMBER as _NUMBER,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _SOLVE_TIMEOUT_S as _SOLVE_TIMEOUT_S,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _WING as _WING,
)
from pyflightstream.qa._spec_0400_gapbase import (
    Build as Build,
)
from pyflightstream.qa._spec_0400_gapbase import (
    Judge as Judge,
)
from pyflightstream.qa._spec_0400_gapbase import (
    Reading as Reading,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _ccs_sections as _ccs_sections,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _ccs_summary as _ccs_summary,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _export_summary as _export_summary,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _faces as _faces,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _names as _names,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _obj as _obj,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _rows as _rows,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _state as _state,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _states_read as _states_read,
)
from pyflightstream.qa._spec_0400_gapbase import (
    _text_head as _text_head,
)
from pyflightstream.qa._spec_0400_gapbase import (
    obj_summary as obj_summary,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _CCS_WING_CURVES as _CCS_WING_CURVES,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _DEFLECTED as _DEFLECTED,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _MARKS_COUNT as _MARKS_COUNT,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _MARKS_FILE as _MARKS_FILE,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _BlockRows as _BlockRows,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _boundaries_at_least as _boundaries_at_least,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _deflected as _deflected,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _edges_read as _edges_read,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _emit_export_all as _emit_export_all,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _export_format as _export_format,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _face_order_read as _face_order_read,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _file_written as _file_written,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _groups_read as _groups_read,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _import_marks as _import_marks,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _marked_midpoints as _marked_midpoints,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _marks_read as _marks_read,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _marks_reproduced as _marks_reproduced,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _obj_source as _obj_source,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _opened_file as _opened_file,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _reimport_with_marks as _reimport_with_marks,
)
from pyflightstream.qa._spec_0400_gapedges import (
    _write_obj as _write_obj,
)
from pyflightstream.qa._spec_0400_gapedges import (
    edge_count as edge_count,
)
from pyflightstream.qa._spec_0400_gapedges import (
    edges_kept as edges_kept,
)
from pyflightstream.qa._spec_0400_gapedges import (
    mesh_edges as mesh_edges,
)
from pyflightstream.qa._spec_ccs_noise import (
    _ccs_assign,
    _ccs_select,
    _export_obj,
    _wing_loft,
)
from pyflightstream.qa._spec_kit import _emit, _seq
from pyflightstream.qa.geometry import WingSpec, generate_wing_stl, write_stl
from pyflightstream.qa.probes import ProbeArtifacts
from pyflightstream.results.exports import parse_off_body_streamlines
from pyflightstream.script import Script
from pyflightstream.script.helpers import (
    detect_every_boundary,
    initialize_solver,
)

__all__: list[str] = []


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


def file_rows(name: str, minimum: int = 1) -> Judge:
    """Judge by an export holding numeric rows; absent or empty reads unprobed."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        return True if len(_rows(artifacts.workdir / name)) >= minimum else None

    return check


def streamlines_directed(name: str, direction: int) -> Judge:
    """Judge P3-03/04 traces against their x=-1 seed, excluding export counts.

    The direction question and paired runs are recorded in RPT-166. This judge
    applies only to their three-seed wing setup, not to arbitrary flow fields.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        path = artifacts.workdir / name
        if not path.is_file():
            return None
        try:
            report = parse_off_body_streamlines(path.read_text(encoding="utf-8"))
        except ValueError:
            return None
        if report.count != 3:
            return None
        for line in report.streamlines:
            distance = direction * (line.positions[:, 0] + 1.0)
            if (
                line.points < 2
                or not np.isfinite(distance).all()
                or np.any(distance < -1e-6)
                or not np.any(distance > 1e-6)
            ):
                return None
        return True

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
    if len(gone) != len(came):
        return []
    return list(zip(gone, came, strict=True))


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
    first = lines[0][:200] if lines else ""
    folder = artifacts.workdir.resolve()
    for spelling in (str(folder), folder.as_posix()):
        first = first.replace(spelling, "<probe folder>")
    return f"{len(lines)} calls; first: {first}; files at call 1: {seen}"


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
    if script.version.canonical == "26.125":
        # This prelude always imports one constructed wing boundary.
        script.emit("DETECT_TRAILING_EDGES_BY_SURFACE", surfaces=1, surface_indices=[1])
    else:
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


def _before_the_march_trajectory(script: Script, workdir: Path) -> None:
    """Write the trajectory export before the march, a placement the phase order refuses.

    The database phase of the command is export since 0.40.0 (RPT-166 P4-04), so
    the placement the first batch measured, which held the header and no row, is
    appended unvalidated, as :func:`_after_the_march_trajectory` was while the
    recorded phase was setup. The script is flagged raw.
    """
    scratch = Script(script.version, registry=script.registry)
    scratch.declare_existing(motions=script.num_motions)
    scratch.emit("EXPORT_6DOF_TRAJECTORY", 1, workdir / _TRAJECTORY)
    script.raw(scratch.render())


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


# --- the second round (2026-10-12): instruments the first batch showed blind ----------


def _state_still(artifacts: ProbeArtifacts) -> bool | None:
    """Judge a control: the saved boundary list and face count did NOT move.

    A control holds when the command, given nothing to act on, leaves the saved
    simulation as it found it; a moved state is a control that failed.
    """
    before = (_names(artifacts.workdir / _BEFORE), _faces(artifacts.workdir / _BEFORE))
    after = (_names(artifacts.workdir / _AFTER), _faces(artifacts.workdir / _AFTER))
    if None in before or None in after:
        return None
    return before == after


def _selection_took(source: int) -> Judge:
    """Judge a subset selection by the surface made from it (P1-06).

    The first batch read the new surface as an added LAST boundary; the solver
    moves the selected faces out of their surface instead, so a selection that
    took every face of boundary ``source`` empties it and the new surface takes
    its place with its face count. The judge reads the saved file's boundaries
    against the state saved right after the target: some boundary of the saved
    file has exactly the face count of ``source`` and the total did not move.
    Every face of the body in one surface means the subset was ignored.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        state = _faces(artifacts.workdir / _AFTER)
        saved = _faces(artifacts.workdir / "saved.fsm")
        if state is None or saved is None or state[1] is None or saved[1] is None:
            return None
        if len(state[1]) < source or saved[0] != state[0]:
            return None
        if len(saved[1]) == 1 and saved[1][0] == state[0]:
            return False
        names_before = _names(artifacts.workdir / _AFTER) or ()
        names_after = _names(artifacts.workdir / "saved.fsm") or ()
        new = [
            count
            for name, count in zip(names_after, saved[1], strict=False)
            if name not in names_before
        ]
        return True if new and new[-1] == state[1][source - 1] else None

    return check


def _selection_took_all(artifacts: ProbeArtifacts) -> bool | None:
    """Judge the ALL_FACES control: the new surface holds every face of the body."""
    state = _faces(artifacts.workdir / _AFTER)
    saved = _faces(artifacts.workdir / "saved.fsm")
    if state is None or saved is None or saved[1] is None:
        return None
    return True if state[0] in saved[1] else None


#: The wing's node 1 as the P1-10 probe measured it on 26.124 and 26.125: the
#: trailing edge at the tip, (1, -2, 0). Its trailing-edge neighbour at the next
#: station is (1, -1.5, 0). Moved ONTO it, the two faces sharing the edge left the
#: saved simulation before the delete ran (288 to 286 faces on both builds, the
#: second batch), so the node stops 0.1 mm short of it: two sliver faces remain.
_NODE_ONE_NEIGHBOUR = (1.0, -1.5 - 1.0e-4, 0.0)


def _collapsed_edge(script: Script, workdir: Path) -> None:
    """Make sliver faces inside the solver: move node 1 next to its edge neighbour.

    The STL importer drops a zero-area triangle on import (the first batch saved
    12 faces from a 13-triangle box on both builds), so a degenerate face has to
    be made after the import: the faces that share the collapsed edge keep three
    corners of which two coincide.
    """
    _import_wing()(script, workdir)
    script.emit("SELECT_MESH_NODE", 1)
    script.emit("TRANSFORM_SELECTED_NODES", 1, "ABSOLUTE", *_NODE_ONE_NEIGHBOUR)


def _obj_spans(name: str, axis: int, low: float, high: float) -> Judge:
    """Judge an exported surface by its range on ``axis`` covering ``low`` to ``high``."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        read = _obj(artifacts.workdir / name)
        if read is None or not read[0]:
            return None
        values = [v[axis] for v in read[0]]
        return True if min(values) <= low + 1e-3 and max(values) >= high - 1e-3 else None

    return check


def _section_ccs_text(points: list[tuple[float, float, float]]) -> str:
    """Return a one-component CCS file holding one cross section."""
    flat = ";".join(f"{x:.6f};{y:.6f};{z:.6f}" for x, y, z in points)
    lines = ["Aircraft;PYFS_GAP", "Units;Meter", "", "Component;PYFS_SECTION"]
    lines += ["LiftingSurface;true", f"CrossSection;{flat}"]
    return "\n".join(lines) + "\n"


def _ccs_section_name(name: str) -> str:
    return Path(name).with_suffix(".csv").name


def _section_ccs_files(workdir: Path) -> None:
    """Write each section file of :func:`_section_files` again as a one-section CCS file.

    The CAD Create curve probes import their sections through the CCS curve
    route, verified on both builds by the CCS lofts, because the text route
    (CAD_CREATE_IMPORT_CURVE_TXT) aborts the script on 26.124 (P2-14) and so
    could not set a curve probe up.
    """
    points = _naca_points()
    sections = {
        _SECTION_TXT: [(x, 0.0, z) for x, z in points],
        _ROOT_3D: [(x, 0.0, z) for x, z in points],
        _TIP_3D: [(0.2 + 0.6 * x, 2.0, 0.6 * z) for x, z in points],
    }
    for name, section in sections.items():
        _textio.write_text(workdir / _ccs_section_name(name), _section_ccs_text(section))


def _cad_session_ccs(*files: str, select: bool = True) -> Build:
    """Open the CAD Create session and import the sections through the CCS curve route."""

    def build(script: Script, workdir: Path) -> None:
        _section_files(workdir)
        _section_ccs_files(workdir)
        script.emit("NEW_SIMULATION")
        script.emit("CAD_CREATE_INITIALIZE")
        for name in files:
            script.emit(
                "CAD_CREATE_IMPORT_CURVE_CCS", "METER", 1, 1, workdir / _ccs_section_name(name)
            )
        if select:
            script.emit("CAD_CREATE_CURVE_SELECT", -1)

    return build


def _import_txt_as(layout: str) -> Build:
    """Import the 2D section written in another text layout (the P2-14 file-format probes).

    ``comma`` separates the two columns with a comma; ``count`` opens the file
    with a line holding the point count. Only the file moves; the command line
    is the one P2-14 emits.
    """

    def build(script: Script, workdir: Path) -> None:
        _section_files(workdir)
        points = _naca_points()
        if layout == "comma":
            body = "".join(f"{x:.6f},{z:.6f}\n" for x, z in points)
        else:
            body = f"{len(points)}\n" + "".join(f"{x:.6f} {z:.6f}\n" for x, z in points)
        path = workdir / f"naca0012_{layout}.txt"
        _textio.write_text(path, body)
        script.emit("CAD_CREATE_IMPORT_CURVE_TXT", "METER", "2D", 1, "XZ", path)

    return build


def _loft_exported(name: str, index: int, filename: str) -> Build:
    """Loft the selected curves, then export that loft at once (P2-07 to P2-09).

    The first batch exported both lofts after the second one, and on 26.125
    (every setting) and on 26.124 (the merge tolerance) both exports came back
    empty although each loft printed its length; exporting each loft right
    after it is made keeps the reading of the reference independent of what the
    second loft does to it.
    """
    return _seq(_wing_loft(name), _export_obj(index, filename))


def _streamline_table(name: str) -> Judge:
    """Judge a surface streamline export by the table it writes, rows or none.

    No script command seeds an on-body streamline (the manual, p.263: each one
    starts from a click on the surface; p.382 lists only generate, delete and
    export), so a batch run exports the table with zero lines. The file and its
    count line are still written by the export alone.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        path = artifacts.workdir / name
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
        return True if "Number of Surface Streamlines" in text else None

    return check


_SURFACE_LINE_COUNT = re.compile(r"Number of Surface Streamlines:\s*(\d+)")


def _surface_lines_deleted(name: str) -> Judge:
    """Judge the on-body streamline delete by the count line of the export after it.

    The first batch read zero lines after the delete as verified, although no
    line existed to delete: no script command seeds an on-body streamline, so
    the generation before the delete made none (P3-05 counts 0 on both builds),
    and a control export before the delete cannot precede it, the phase order
    putting every export last. Lines left after the delete break it; no line
    left cannot tell a delete from a delete of nothing and records unprobed.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        path = artifacts.workdir / name
        if not path.is_file():
            return None
        found = _SURFACE_LINE_COUNT.search(path.read_text(encoding="utf-8", errors="replace"))
        if found is None:
            return None
        return False if int(found.group(1)) > 0 else None

    return check


def _march_then_trajectory(*, symmetry: str = "NONE") -> Build:
    """March, then export the trajectory (P4).

    The first batch exported before the march, the phase the database records,
    and the file held the header and no row on both builds (P4-04 on 26.124 and
    26.125: 470 bytes, zero numeric rows, after a 20-step march), while the
    export placed after the march held the rows (P4-04m). So every P4 probe
    reads the after-the-march export.
    """
    return _seq(_march(symmetry=symmetry), _after_the_march_trajectory)


#: The trajectory columns the solver writes (x, y, z, u, v, w, p, q, r, phi,
#: theta, psi, then the forces and moments), measured on both builds.
_Z, _THETA = 2, 10


def _pitch_only(name: str) -> Judge:
    """Judge pitch-only freedoms: theta moves while z stays, under gravity."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        rows = _rows(artifacts.workdir / name)
        if len(rows) < 2 or min(len(r) for r in rows) <= _THETA:
            return None
        z_moved = abs(rows[-1][_Z] - rows[0][_Z]) > 1e-6
        theta_moved = abs(rows[-1][_THETA] - rows[0][_THETA]) > 1e-6
        if z_moved:
            return False
        return True if theta_moved else None

    return check


def _pitch_kick(script: Script, workdir: Path) -> None:
    """Start the body with a pitch rate, the excitation that needs no force command.

    The first batch excited P4-03 and P4-11 with CREATE_NEW_6DOF_EXTERNAL_FORCE,
    which aborts the script on both builds (P4-06); an initial pitch rate excites
    the pitch freedom with a command each build carries.
    """
    script.emit("SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY", 1, 0.0, 10.0, 0.0)


def _nodes_only(script: Script, workdir: Path) -> None:
    """Name the structural node file on the motion, the stand-in written beside it."""
    _write_standin(workdir)
    script.emit("SET_MOTION_FSI_STRUCTURAL_NODES", 1, workdir / _NODES)


def _aero_frame(script: Script, workdir: Path) -> None:
    """Create frame 2 at the origin, the frame the aeroelastic coupling is assigned.

    The manual refuses the reference frame there (p.388: "Set value to 1
    (reference) will throw an error"), and the first batch's route B prelude,
    which assigned frame 1 with no frame created, stopped on "No user-defined
    coordinate systems available to assign as aeroelastic frames" (26.124).
    """
    script.emit("CREATE_NEW_COORDINATE_SYSTEM")
    script.emit(
        "EDIT_COORDINATE_SYSTEM",
        frame=2,
        name="PYFS_GAP_AERO",
        origin_x=0.0,
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


def _sections_in_frame_then_start(frame: int) -> Build:
    """Initialise, cut the sectional loads in ``frame``, start (the route B epilogue)."""

    def build(script: Script, workdir: Path) -> None:
        initialize_solver(script)
        script.emit(
            "NEW_SURFACE_SECTION_DISTRIBUTION",
            frame=frame,
            plane="XZ",
            num_sections=8,
            plot_direction="1",
            # The block stopped the script at its closing line without this
            # keyword, in frame 2 and in frame 1 alike (third batch, both
            # builds); the package's own section emission states it.
            include_symmetry="DISABLE",
            surfaces=-1,
        )
        script.emit("START_SOLVER")

    return build


def _nothing_converted(name: str) -> Judge:
    """Judge a CAD body delete by the conversion of every body after it making nothing.

    The two-sheet IGES imports as ONE CAD body: converting every body without a
    delete makes one surface spanning both sheets (P2-05c, both builds). So
    deleting body 1 deletes both sheets, and the conversion after it has nothing
    to make; a surface after the delete means the delete removed nothing.
    """

    def check(artifacts: ProbeArtifacts) -> bool | None:
        names = _names(artifacts.workdir / name)
        if names is None:
            return None
        return len(names) == 0

    return check


# --- the declined surface of 26.125 (PFS-2085.021) -------------------------------------


def _wing_and_sphere(script: Script, workdir: Path) -> None:
    """Import the probe wing (trailing edges marked) and mesh a sphere beside it (none).

    The sphere is the solver's own (CAD_CREATE_SPHERE then the conversion, P2-11
    verified on both builds), out of the wing's wake: a hand-written STL sphere,
    behind the wing and then beside it, sent the solve to "Solver divergence
    detected!" at iteration 3 on both builds (third and fourth batches).
    """
    _import_wing()(script, workdir)
    script.emit("CAD_CREATE_SPHERE", 1, 0.5, 4.0, 0.0, 0.3)
    script.emit("CONVERT_CAD_TO_MESH", -1)
    _units_and_edges(script, workdir)


_DECLINED_LOADS = "loads.txt"


def _surface_drag(artifacts: ProbeArtifacts) -> dict[str, dict[str, float]] | None:
    from pyflightstream.results.loads import parse_loads

    path = artifacts.workdir / _DECLINED_LOADS
    if not path.is_file():
        return None
    try:
        return dict(parse_loads(path.read_text(encoding="utf-8", errors="replace")).surfaces)
    except (ValueError, KeyError):
        return None


def _sphere_row_read(artifacts: ProbeArtifacts) -> bool | None:
    """Judge the instrument: the loads export holds the sphere's row.

    The question is a reading, not a yes or no: what the sphere's drag columns
    print with the sphere on the vorticity list (D-01) against off it (D-01c).
    """
    surfaces = _surface_drag(artifacts)
    if not surfaces:
        return None
    # A diverged solve still exports its table (the third batch printed a wing Cx
    # of 4.3e11): a reading is kept only from a table whose numbers are a solution.
    if any(abs(value) > 10.0 for columns in surfaces.values() for value in columns.values()):
        return None
    return True if any(name.lower().startswith("sphere") for name in surfaces) else None


def _drag_read(artifacts: ProbeArtifacts) -> str:
    surfaces = _surface_drag(artifacts)
    if surfaces is None:
        return f"{_DECLINED_LOADS} absent or unreadable"
    shown = []
    for name, columns in surfaces.items():
        values = ", ".join(
            f"{key} {columns[key]:.7g}"
            for key in ("Cx", "CL", "CDi", "CDo", "CDp", "CDv")
            if key in columns
        )
        shown.append(f"{name}: {values}")
    return "; ".join(shown)


def _declined_export(script: Script, workdir: Path) -> None:
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", workdir / _DECLINED_LOADS)
