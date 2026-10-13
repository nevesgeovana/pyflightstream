"""PFS-2081.75 / RPT-170: does the order of the geometry-build commands matter?

FR-471 R2 lists SET_SIMULATION_LENGTH_UNITS, the trailing edges, SAVEAS, then
EXPORT_SURFACE_MESH OBJ. ``cases/_geometry_emit.py`` exports the OBJ BEFORE the
units, the trailing edges and SAVEAS. This probe builds one small wing, given
in MILLIMETRES (so the units matter), in both orders, with both ways of marking
the trailing edges (``AUTO_DETECT_TRAILING_EDGES`` and
``IMPORT_WAKE_EDGES_FROM_FILE``), and reads: the OBJ coordinates, the unit head
and the marked trailing-edge mid-points of the saved ``.fsm``, the log's counts.
Order A is the code's (export first), order B the requirement's (export last).
No solve; one hidden solver at a time, free memory checked before each launch.

Usage (licensed, scratch output outside the repository)::

    python geometry_order_probe.py <out_dir> <source_stl_in_metres> [build ...]

Writes ``<out_dir>/<build>/<case>/`` per case and ``<out_dir>/summary.json``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import psutil

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))

from pyflightstream import _fsm  # noqa: E402

# The machine-local folder holding one FlightStream_<build> folder per build.
EXE_ROOT = Path(os.environ.get("PYFS_PROBE_EXE_ROOT", "exe"))
EXES = {
    "26.124": EXE_ROOT / "FlightStream_26124" / "Flightstream_26124.exe",
    "26.125": EXE_ROOT / "FlightStream_26125" / "Flightstream_26125.exe",
}
MIN_FREE_GB = 0.5
LAUNCH_FREE_GB = 2.0


def read_stl(path: Path) -> list[tuple[float, float, float]]:
    """Return the vertices of an ASCII stl in file order."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts[:1] == ["vertex"]:
            out.append((float(parts[1]), float(parts[2]), float(parts[3])))
    return out


def scaled_stl(source: Path, target: Path, factor: float) -> None:
    """Write the stl scaled by ``factor`` (metres to millimetres)."""
    lines = []
    for line in source.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts[:1] == ["vertex"]:
            x, y, z = (float(v) * factor for v in parts[1:4])
            line = f"      vertex {x:.9e} {y:.9e} {z:.9e}"
        lines.append(line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def trailing_midpoints_mm(stl_mm: Path) -> list[tuple[float, float, float]]:
    """Mid-points of the edges lying on the maximum-x line of the source (millimetres)."""
    vertices = read_stl(stl_mm)
    xmax = max(v[0] for v in vertices)
    edges = set()
    for i in range(0, len(vertices), 3):
        tri = vertices[i : i + 3]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            p, q = tri[a], tri[b]
            if abs(p[0] - xmax) < 1e-6 and abs(q[0] - xmax) < 1e-6:
                edges.add(tuple(sorted((p, q))))
    return sorted(
        tuple((p[k] + q[k]) / 2 for k in range(3))
        for p, q in edges  # type: ignore[misc]
    )


def script_text(case: str, work: Path, stl_mm: Path, nodes: Path) -> str:
    """Return the build script of one case; case is ``<order>-<route>``."""
    order, route = case.split("-")
    w = str(work).replace("/", "\\")
    export = f"EXPORT_SURFACE_MESH OBJ -1\n{w}\\wing.obj\n\n"
    if route == "detect":
        marking = "AUTO_DETECT_TRAILING_EDGES\n\n"
    else:
        nodes_path = str(nodes).replace("/", chr(92))
        marking = f"IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER\n{nodes_path}\n\n"
    head = f"NEW_SIMULATION\nIMPORT\nUNITS MILLIMETER\nFILE_TYPE STL\nFILE {stl_mm}\nCLEAR\n\n"
    units = "SET_SIMULATION_LENGTH_UNITS METER\n\n"
    save = f"SAVEAS\n{w}\\wing.fsm\n\n"
    log = f"EXPORT_LOG\n{w}\\log.txt\n\nCLOSE_FLIGHTSTREAM\n"
    if order == "C":
        body = units.replace("METER", "MILLIMETER") + marking + save + export
    elif order == "A":
        body = export + units + marking + save
    else:
        body = units + marking + save + export
    return head + body + "\n" + log


def obj_bounds(path: Path) -> dict[str, object]:
    """Return the vertex count and the coordinate extent of an OBJ."""
    xs = [[], [], []]
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("v "):
            for k, v in enumerate(line.split()[1:4]):
                xs[k].append(float(v))
    return {
        "vertices": len(xs[0]),
        "min": [min(c) for c in xs],
        "max": [max(c) for c in xs],
    }


def log_lines(path: Path) -> list[str]:
    """Return the log's lines that speak of edges, units or scale."""
    raw = path.read_bytes()
    text = (
        raw.decode("utf-16-le", errors="replace")
        if raw[1:2] == b"\x00"
        else raw.decode("utf-8", "replace")
    )
    text = text.replace("\x00", "")
    keep = re.compile(r"trailing|wake edge|unit|scale|import", re.IGNORECASE)
    return [ln.strip() for ln in text.splitlines() if keep.search(ln)]


def wait_for_memory() -> float:
    """Return free GB; refuse to launch below the launch floor."""
    free = psutil.virtual_memory().available / 2**30
    if free < LAUNCH_FREE_GB:
        raise SystemExit(f"free memory {free:.2f} GB below the launch floor {LAUNCH_FREE_GB} GB")
    return free


def run_case(build: str, case: str, out: Path, stl_mm: Path, nodes: Path) -> dict[str, object]:
    """Run one case on one build and return what was read."""
    work = out / build / case
    work.mkdir(parents=True, exist_ok=True)
    script = work / "probe_script.txt"
    script.write_text(script_text(case, work, stl_mm, nodes), encoding="utf-8")
    wait_for_memory()
    subprocess.run(
        [str(EXES[build]), "-hidden", "-script", str(script)],
        cwd=work,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=150,
    )
    result: dict[str, object] = {"case": case, "build": build}
    obj, fsm, log = work / "wing.obj", work / "wing.fsm", work / "log.txt"
    result["obj"] = obj_bounds(obj) if obj.exists() else None
    if fsm.exists():
        result["fsm_bytes"] = fsm.stat().st_size
        result["fsm_unit_head"] = _fsm.saved_length_unit(fsm)
        mids = _fsm.trailing_edge_midpoints(fsm)
        result["te_count"] = len(mids)
        result["te_x_range"] = [min(m[0] for m in mids), max(m[0] for m in mids)] if mids else None
        result["te_y_range"] = [min(m[1] for m in mids), max(m[1] for m in mids)] if mids else None
    else:
        result["fsm_bytes"] = None
    result["log"] = log_lines(log) if log.exists() else None
    return result


def main() -> None:
    """Run the cases on each build named, one solver at a time.

    Case C states MILLIMETER and exports last.
    """
    out = Path(sys.argv[1])
    source = Path(sys.argv[2])
    builds = sys.argv[3:] or list(EXES)
    out.mkdir(parents=True, exist_ok=True)
    stl_mm = out / "wing_mm.stl"
    scaled_stl(source, stl_mm, 1000.0)
    mids = trailing_midpoints_mm(stl_mm)
    nodes = out / "wing_te_nodes.txt"
    # The solver reads the node file in the simulation's unit (METER by then).
    nodes.write_text(
        "\n".join(f"{x / 1000:.9f},{y / 1000:.9f},{z / 1000:.9f}" for x, y, z in mids) + "\n"
    )
    results = []
    for build in builds:
        for case in ("A-detect", "B-detect", "A-file", "B-file", "C-detect"):
            results.append(run_case(build, case, out, stl_mm, nodes))
            (out / "summary.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
