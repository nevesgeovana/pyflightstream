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
import shutil
import sys
import types
from pathlib import Path
from typing import Any

from pyflightstream.run import LocalExecutor
from pyflightstream.script import Script
from pyflightstream.workspace.inputs import resolve_build, write_inventory
from tests.support_tier3 import HERE as HERE
from tests.support_tier3 import (
    INPUTS as INPUTS,
)
from tests.support_tier3 import (
    LIBRARY as LIBRARY,
)
from tests.support_tier3 import (
    MESH_INPUTS as MESH_INPUTS,
)
from tests.support_tier3 import (
    MeshInput as MeshInput,
)
from tests.support_tier3 import (
    _nearest as _nearest,
)
from tests.support_tier3 import (
    _turned as _turned,
)
from tests.support_tier3 import (
    _write_atomically as _write_atomically,
)
from tests.support_tier3 import (
    check_points as check_points,
)
from tests.support_tier3 import (
    ensure_mesh_inputs as ensure_mesh_inputs,
)
from tests.support_tier3 import (
    mesh_path as mesh_path,
)
from tests.support_tier3 import (
    mesh_round_trip as mesh_round_trip,
)
from tests.support_tier3 import (
    obj_text as obj_text,
)
from tests.support_tier3 import (
    points_path as points_path,
)
from tests.support_tier3 import (
    points_text as points_text,
)
from tests.support_tier3 import (
    read_obj as read_obj,
)
from tests.support_tier3 import surface_mesh as surface_mesh
from tests.support_tier3 import trailing_edge_midpoints as trailing_edge_midpoints
from tests.support_tier3 import (
    write_stand_in as write_stand_in,
)
from tests.tier3_licensed import recipes

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


#: Every raw mesh of the mesh matrix, by the stem its folder, its OBJ and its
#: sidecar share.

#: The build the mesh matrix runs on and the export is made with: the one
#: build the trailing-edge file route was run on (RPT-061).
MESH_BUILD = "26.124"

#: The machine's record of the licensed export: the build, each export's
#: digest and round trip, each OBJ's digest and points check. Beside the
#: other generated files, never committed: it names this machine's run.
MESH_RECORD = recipes.GENERATED / "mesh_export.json"


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
