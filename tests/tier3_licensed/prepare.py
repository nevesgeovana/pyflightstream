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

    python -m tests.tier3_licensed.prepare            # every missing shape
    python -m tests.tier3_licensed.prepare wing body  # named shapes only
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import shutil
import sys
import types
from pathlib import Path

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


def main(argv: list[str] | None = None) -> int:
    shapes = (argv if argv is not None else sys.argv[1:]) or list(FILES)
    for shape in shapes:
        target = prepare(shape)
        print(f"{shape:9} -> {target.relative_to(HERE).as_posix()} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
