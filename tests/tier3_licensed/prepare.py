"""Prepare the synthetic geometries of the tier-3 workspace, once, on a
licensed solver.

This is the "GUI once, script everything after" step of
``docs/mesh-inputs.md`` done by script: for each shape ``recipes.SHAPES``
knows, the STL parts are generated, imported with their length units
declared, and saved as a simulation under ``inputs/geometries/``, beside the
boundary sidecar the package writes from the file's own mesh block and a
provenance record naming the generator, the spec and the build. A geometry
already in the library is left alone: redo the step, save a new artifact,
never edit in place.

It is not a matrix row on purpose: a run record is the record of a SOLVE,
judged from the loads table the solve exports, and a preparation exports no
loads, so a preparation row would be recorded FAILED_INCOMPLETE_OUTPUT by
the assessor for the right reason. The script it runs is the same recipe a
row would build (``recipes.prepare_geometry``), so the preparation and the
rows share one source.

The raw meshes of the mesh matrix (``matriz_mesh.fs``) are the second
preparation, ``mesh`` below: two saved simulations of the library exported
to OBJ by the package's own ``export_surface_mesh``, on the build the matrix
runs on.

    python -m tests.tier3_licensed.prepare            # every missing shape
    python -m tests.tier3_licensed.prepare wing body  # named shapes only
    python -m tests.tier3_licensed.prepare mesh       # the OBJ exports, 26.124
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream._fsm import surface_mesh, trailing_edge_midpoints
from pyflightstream.run import LocalExecutor
from pyflightstream.script import Script
from pyflightstream.workspace.inputs import resolve_build, write_inventory
from tests.tier3_licensed import recipes

HERE = Path(__file__).resolve().parent
INPUTS = HERE / "inputs"
LIBRARY = INPUTS / "geometries"
BUILD = "26.120"

#: The file each shape becomes in the library.
FILES = {
    "wing": "10_WING.fsm",
    "halfwing": "11_HALFWING.fsm",
    "body": "20_BODY.fsm",
    "blade": "30_BLADE.fsm",
    "pusher": "40_PUSHER.fsm",
    "twin": "41_TWIN.fsm",
    "wing_phy": "12_WING_PHY.fsm",
    "halfwing_phy": "13_HALFWING_PHY.fsm",
    "blade_phy": "31_BLADE_PHY.fsm",
    "wing_renamed": "14_WING_RENAMED.fsm",
}


#: This machine's installations, gitignored: the committed registry carries
#: placeholders because an installation path is machine configuration, and
#: the package reads this overlay over it for every row (PFS-2031.15).
LOCAL_EXECUTABLES = INPUTS / "executables.local.toml"


def executable(build: str = BUILD) -> Path:
    """The solver of ``build`` on this machine, the way every row resolves it.

    Through the package's own registry reader, so the overlay is read over
    the committed registry with the precedence ``pyfs-matrix`` applies and
    not a second one written here; the local file is named in the refusal
    because it is the one a fresh machine has to write.
    """
    if not LOCAL_EXECUTABLES.is_file():
        raise RuntimeError(
            f"no {LOCAL_EXECUTABLES.name} in the tier-3 inputs/ folder: write one naming this "
            f'machine\'s installation, \'"{build}" = "<path>"\', gitignored like every '
            "machine path; pyfs-matrix reads the same file over inputs/executables.toml"
        )
    return resolve_build(INPUTS, build).fs_exe


def prepare_script(shape: str, output_name: str) -> Script:
    """The preparation script of one shape, through the recipe a row would use."""
    case = types.SimpleNamespace(variables={"SHAPE": shape}, outputs=[output_name])
    script = Script(version=BUILD)
    recipes.prepare_geometry(case, script)
    return script


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(shape: str, *, build: str = BUILD, timeout_s: float = 600.0) -> Path:
    """Generate, import and save one shape into the library; return the file."""
    if shape not in FILES:
        raise ValueError(f"shape {shape!r} names no synthetic shape; one of {', '.join(FILES)}")
    target = LIBRARY / FILES[shape]
    if target.exists():
        return target
    workdir = recipes.GENERATED / f"prep_{shape}"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    script = prepare_script(shape, FILES[shape])
    script_path = workdir / f"prepare_{shape}.txt"
    script_path.write_text(script.render(), encoding="utf-8")
    result = LocalExecutor(executable(build)).run_script(script_path, workdir, timeout_s=timeout_s)
    produced = workdir / FILES[shape]
    if result.timed_out or not produced.is_file():
        raise RuntimeError(
            f"the solver did not save {FILES[shape]} for shape {shape!r}: return code "
            f"{result.return_code}, timed out {result.timed_out}, wall {result.wall_time_s:.0f} s; "
            f"see {workdir}"
        )
    LIBRARY.mkdir(parents=True, exist_ok=True)
    shutil.move(str(produced), str(target))
    sidecar = write_inventory(target, overwrite=True)
    families = [name for name, _ in recipes.SHAPES[shape]()]
    provenance = target.with_name(target.stem + ".provenance.toml")
    provenance.write_text(
        "# Provenance of a SYNTHETIC geometry of the tier-3 workspace (GOAL-012).\n"
        "# Generated from public shape laws by tests.tier3_licensed.recipes and saved\n"
        "# by the solver named below; nothing of the author's went into it.\n"
        f'shape = "{shape}"\n'
        f'generator = "tests.tier3_licensed.recipes.SHAPES[{shape!r}]"\n'
        f"parts = [{', '.join(repr(f) for f in families)}]\n"
        f'wing_spec = "{recipes.WING!r}"\n'
        f'blade_spec = "{recipes.BLADE!r}"\n'
        f"body_radius_m = {recipes.BODY_RADIUS_M}\n"
        f"body_length_m = {recipes.BODY_LENGTH_M}\n"
        f'build = "{build}"\n'
        'executable = "the build named above, installed on the preparing machine; its path '
        'is machine configuration and is not recorded here"\n'
        f'prepared_on = "{_dt.date.today().isoformat()}"\n'
        f'sha256 = "{_sha256(target)}"\n'
        f'sidecar = "{sidecar.name}"\n',
        encoding="utf-8",
    )
    return target


# ------------------------------------------------------------- the raw meshes
#
# THE MESH MATRIX RUNS ONE BODY THREE WAYS: the saved simulation opened, the
# same surface imported from an OBJ with its trailing edge marked by a points
# file, and imported with the edge detected. The OBJ is the saved simulation
# exported by the package's own `pyflightstream.run.export_surface_mesh`, a
# solver run, so it is made here with the other preparations. A mesh file
# never enters Git (invariant 5, the geometry guard of test_house_style), so
# the OBJ is generated and ignored; what is committed is what says how it is
# made and used: its sidecar, its points file and a provenance record, in a
# folder of its own under inputs/geometries/.
#
# A CLONE WITH NO SEAT STILL PLANS THE MATRIX. The plan stages the file and
# checks the points file against its edges, so where no OBJ is on disk the
# offline control writes a STAND-IN from the source's own mesh block
# (`pyflightstream._fsm.surface_mesh`): the same vertices to the last digit,
# the same triangles in the same order. The licensed export replaces it, and
# `mesh_round_trip` measures how far the export is from that block before any
# row runs. Nothing of the rendered scripts depends on which of the two is on
# disk: a script names the file, never its bytes.


@dataclass(frozen=True)
class MeshInput:
    """One raw-mesh geometry of the mesh matrix, made from a saved simulation.

    ``surface`` is the name the stand-in gives the file's one surface, which
    is the name its sidecar's ``boundaries`` states; the sidecar renames it to
    the saved simulation's own name by position, so the solver's name for an
    imported surface does not decide what the loads table calls it.
    ``scale`` multiplies every vertex: 1000 writes the metres of the saved
    simulation as millimetres.
    """

    source: str
    surface: str
    scale: float = 1.0


#: Every raw mesh of the mesh matrix, by the stem its folder, its OBJ and its
#: sidecar share.
MESH_INPUTS: dict[str, MeshInput] = {
    "15_WING_OBJ_TE": MeshInput("10_WING.fsm", "WING_OBJ"),
    "16_WING_OBJ_DET": MeshInput("10_WING.fsm", "WING_OBJ"),
    "17_WING_OBJ_MM": MeshInput("10_WING.fsm", "WING_OBJ", scale=1000.0),
    "32_BLADE_OBJ_TE": MeshInput("30_BLADE.fsm", "BLADE_OBJ"),
    "33_BLADE_OBJ_DET": MeshInput("30_BLADE.fsm", "BLADE_OBJ"),
}

#: The build the mesh matrix runs on and the export is made with: the one
#: build the trailing-edge file route was run on (RPT-061).
MESH_BUILD = "26.124"

#: The machine's record of the licensed export: the build, each export's
#: digest and round trip, each OBJ's digest and points check. Beside the
#: other generated files, never committed: it names this machine's run.
MESH_RECORD = recipes.GENERATED / "mesh_export.json"


def mesh_path(name: str) -> Path:
    """The OBJ of one raw mesh of the mesh matrix, in its own folder."""
    return LIBRARY / name / f"{name}.obj"


def points_path(name: str) -> Path:
    """The trailing-edge points file beside one raw mesh; only the file route has one."""
    return LIBRARY / name / f"{name}.te.txt"


def obj_text(
    vertices: Any, triangles: Any, *, surface: str, scale: float = 1.0, note: str = ""
) -> str:
    """An OBJ of one surface: its vertices scaled, its triangles 1-based, in order."""
    rows = [f"# {note}"] if note else []
    rows.append(f"o {surface}")
    rows += [f"v {x * scale!r} {y * scale!r} {z * scale!r}" for x, y, z in vertices]
    rows += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in triangles]
    return "\n".join(rows) + "\n"


def scaled_obj_text(text: str, scale: float) -> str:
    """An OBJ's text with every vertex line scaled and every other line as written."""
    lines = []
    for line in text.splitlines(keepends=True):
        fields = line.split()
        if fields[:1] == ["v"]:
            ending = line[len(line.rstrip("\r\n")) :]
            values = [float(value) * scale for value in fields[1:4]]
            line = "v " + " ".join(repr(value) for value in values) + ending
        lines.append(line)
    return "".join(lines)


def _write_atomically(target: Path, text: str) -> None:
    """Write through a temporary name, so a concurrent reader sees one file or the other."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, target)


def write_stand_in(name: str) -> Path:
    """Write one raw mesh from its source's saved mesh block; return the OBJ."""
    spec = MESH_INPUTS[name]
    vertices, triangles = surface_mesh(LIBRARY / spec.source)
    note = (
        f"stand-in: the mesh block of {spec.source}, written by tests.tier3_licensed.prepare "
        "where no export is on disk; `prepare mesh` replaces it with the solver's export"
    )
    target = mesh_path(name)
    _write_atomically(
        target, obj_text(vertices, triangles, surface=spec.surface, scale=spec.scale, note=note)
    )
    return target


def ensure_mesh_inputs() -> list[str]:
    """Write the stand-in of every raw mesh with no OBJ on disk; return their names."""
    missing = [name for name in MESH_INPUTS if not mesh_path(name).is_file()]
    for name in missing:
        write_stand_in(name)
    return missing


def points_text(source: str) -> str:
    """The points file of a saved simulation's trailing edge, as committed beside its OBJ.

    The mid-points of the edges its saved mesh block flags as trailing
    (``pyflightstream._fsm.trailing_edge_midpoints``, the reader of RPT-065),
    in the simulation's metres, under the unit line the package's reader
    asks for.
    """
    points = trailing_edge_midpoints(LIBRARY / source)
    return "METER\n" + "".join(f"{x!r},{y!r},{z!r}\n" for x, y, z in points)


def read_obj(path: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """The vertices, triangles (0-based) and object or group names an OBJ writes.

    Read line by line rather than through the mesh reader, which merges and
    may reorder what it loads: the round trip is a question about the file.
    A polygon is split into a fan; ``a/b/c`` references keep their vertex.
    """
    vertices: list[list[float]] = []
    faces: list[tuple[int, int, int]] = []
    names: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "v":
            vertices.append([float(value) for value in fields[1:4]])
        elif fields[0] == "f":
            refs = [int(field.split("/")[0]) for field in fields[1:]]
            refs = [ref - 1 if ref > 0 else len(vertices) + ref for ref in refs]
            faces += [(refs[0], refs[k], refs[k + 1]) for k in range(1, len(refs) - 1)]
        elif fields[0] in ("o", "g"):
            names.append(" ".join(fields[1:]))
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=int), names


def _nearest(points: np.ndarray, candidates: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gaps = np.linalg.norm(points[:, None, :] - candidates[None, :, :], axis=2)
    chosen = gaps.argmin(axis=1)
    return chosen, gaps[np.arange(len(points)), chosen]


def _turned(face: tuple[int, ...]) -> tuple[int, ...]:
    """A triangle turned to start at its smallest index, its orientation kept."""
    start = face.index(min(face))
    return face[start:] + face[:start]


def mesh_round_trip(source: Path, obj: Path, *, scale: float = 1.0) -> dict[str, Any]:
    """How far an OBJ of a saved simulation is from that simulation's own mesh block.

    Each OBJ vertex is matched to its nearest block vertex (the block scaled
    by ``scale``), and each OBJ triangle is read through that match: the
    same triangles in the same order, the same set with the same
    orientation, or the same set in any orientation.
    """
    block_vertices, block_faces = surface_mesh(source)
    block = np.asarray(block_vertices, dtype=float) * scale
    faces = [tuple(face) for face in block_faces]
    vertices, triangles, names = read_obj(obj)
    matched, distance = _nearest(vertices, block)
    _, back = _nearest(block, vertices)
    mapped = [tuple(int(matched[i]) for i in face) for face in triangles.tolist()]
    return {
        "vertices": [len(block), len(vertices)],
        "faces": [len(faces), len(mapped)],
        "max_vertex_distance": float(max(distance.max(), back.max())),
        "vertices_matched_one_to_one": len(set(matched.tolist())) == len(block) == len(vertices),
        "faces_in_the_same_order": mapped == faces,
        "faces_same_set_same_orientation": {_turned(f) for f in mapped}
        == {_turned(f) for f in faces},
        "faces_same_set": {tuple(sorted(f)) for f in mapped} == {tuple(sorted(f)) for f in faces},
        "surface_names": names,
    }


def check_points(name: str, obj: Path | None = None) -> dict[str, Any]:
    """Run a raw mesh's points file through the check the plan runs (T05)."""
    from pyflightstream.workspace.inputs import read_mesh_import
    from pyflightstream.workspace.wake_edges import (
        matched_trailing_edge_points,
        read_trailing_edge_points,
    )

    sidecar = LIBRARY / name / f"{name}.boundaries.toml"
    spec = read_mesh_import(sidecar)
    assert spec is not None, f"{sidecar.name} states no [import] table"
    read = read_trailing_edge_points(points_path(name))
    checked = matched_trailing_edge_points(
        read.points,
        points_unit=read.unit,
        mesh=obj or mesh_path(name),
        mesh_unit=spec.units,
        simulation_unit="METER",
        source=points_path(name).name,
        lines=read.lines,
    )
    return {"points": len(checked), "unit": read.unit, "mesh_unit": spec.units}


def export_mesh_inputs(build: str = MESH_BUILD, *, timeout_s: float = 600.0) -> dict[str, Any]:
    """Export each source to OBJ on the licensed solver and install every raw mesh.

    One solver run per source (two), one at a time: ``export_surface_mesh``
    opens the saved simulation, exports every surface to OBJ and closes. A
    METER mesh is the export's own bytes; the MILLIMETER one is the export
    with every vertex line scaled. Each export is measured against its
    source's mesh block, each points file is checked against the OBJ it will
    run with, and the whole is recorded in ``_generated/mesh_export.json``.
    A failed export stops here with the stand-in left in place, so the
    matrix never runs against a file nobody measured.
    """
    from pyflightstream.run import export_surface_mesh

    solver = executable(build)
    record: dict[str, Any] = {
        "build": build,
        "executable_sha256": _sha256(Path(solver)),
        "prepared_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "sources": {},
        "inputs": {},
    }
    exported: dict[str, Path] = {}
    for source in sorted({spec.source for spec in MESH_INPUTS.values()}):
        workdir = recipes.GENERATED / f"export_{Path(source).stem}"
        if workdir.exists():
            shutil.rmtree(workdir)
        obj = export_surface_mesh(
            LIBRARY / source,
            workdir,
            version=build,
            fs_exe=solver,
            file_type="OBJ",
            surface=-1,
            timeout_s=timeout_s,
        )
        exported[source] = obj
        record["sources"][source] = {
            "source_sha256": _sha256(LIBRARY / source),
            "export": obj.name,
            "export_sha256": _sha256(obj),
            "round_trip": mesh_round_trip(LIBRARY / source, obj),
        }
    for name, spec in MESH_INPUTS.items():
        target = mesh_path(name)
        if spec.scale == 1.0:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(exported[spec.source], target)
        else:
            text = exported[spec.source].read_text(encoding="utf-8")
            _write_atomically(target, scaled_obj_text(text, spec.scale))
        entry: dict[str, Any] = {
            "source": spec.source,
            "scale": spec.scale,
            "sha256": _sha256(target),
            "round_trip": mesh_round_trip(LIBRARY / spec.source, target, scale=spec.scale),
        }
        if points_path(name).is_file():
            entry["points_check"] = check_points(name)
        record["inputs"][name] = entry
    MESH_RECORD.parent.mkdir(parents=True, exist_ok=True)
    MESH_RECORD.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    shapes = (argv if argv is not None else sys.argv[1:]) or list(FILES)
    if shapes == ["mesh"]:
        record = export_mesh_inputs()
        print(json.dumps(record, indent=2))
        print(f"recorded in {MESH_RECORD.relative_to(HERE).as_posix()}")
        return 0
    for shape in shapes:
        target = prepare(shape)
        print(f"{shape:9} -> {target.relative_to(HERE).as_posix()} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
