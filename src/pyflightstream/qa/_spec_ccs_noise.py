"""The probe catalog, third part: CCS, noise, surface removal and the arity probes.

Pipeline role: the entries of ``PROBE_SPECS`` for the commands the 0.32.0
licensed rounds ran through the release harness and not through
``pyfs-qa probe`` (the CCS lofts, the acoustic chain, ``DELETE_SURFACES``),
for the three commands PFS-2001.05 names, and for the two CCS export
commands whose arity PFS-2003.06 asks (FR-333, FR-334, FR-335). The module
is imported by ``pyflightstream.qa.specs`` and registers into the shared
registry of ``pyflightstream.qa._spec_kit``.

Every assertion is strict only where the instrument is read from a file
the solver wrote and the target is the only command that could have
produced the reading; elsewhere it returns None, which records the
command ``unprobed`` (a probe may never guess). The CCS file the probes
read is synthetic, built here from public shape laws, and states no
dimension of any real geometry.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from pathlib import Path

import pyflightstream._textio as _textio
from pyflightstream._fsm import boundary_names
from pyflightstream.qa._spec_catalog_b import _CREATE_RECT_VSECTION
from pyflightstream.qa._spec_kit import (
    _emit,
    _named_frame,
    _saveas,
    _seq,
    _spec,
)
from pyflightstream.qa.probes import (
    ProbeArtifacts,
    Requires,
    emit_solver_setup,
)
from pyflightstream.script import Script
from pyflightstream.script.helpers import initialize_solver

__all__: list[str] = []

# --- the synthetic CCS file ---------------------------------------------

_CCS_NAME = "ccs3.csv"
_WING, _FUSELAGE, _REVOLUTION = "PYFS_CCS_WING", "PYFS_CCS_FUS", "PYFS_CCS_REV"


def _fmt(value: float) -> str:
    return f"{value + 0.0:.6f}"


def _airfoil(count: int = 7) -> list[tuple[float, float]]:
    """Return a closed symmetric section from a public thickness law."""
    xs = [0.5 * (1.0 - math.cos(math.pi * i / (count - 1))) for i in range(count)]

    def half(x: float) -> float:
        return 0.6 * (0.2969 * math.sqrt(x) - 0.126 * x - 0.3516 * x**2 + 0.2843 * x**3)

    upper = [(x, half(x)) for x in reversed(xs)]
    lower = [(x, -half(x)) for x in xs[1:]]
    return upper + lower


def _wing_lines() -> list[str]:
    lines = [f"Component;{_WING}", "LiftingSurface;true"]
    for y in (0.0, 4.0):
        flat = [f"{_fmt(x)};{_fmt(y)};{_fmt(z)}" for x, z in _airfoil()]
        lines.append("CrossSection;" + ";".join(flat))
    return lines


def _fuselage_lines() -> list[str]:
    lines = [f"Component;{_FUSELAGE}", "LiftingSurface;false"]
    for x in (0.1, 1.0, 2.0):
        radius = 0.5 * math.sin(math.pi * x / 2.1) ** 0.5
        ring = [
            f"{_fmt(x)};{_fmt(radius * math.cos(t))};{_fmt(radius * math.sin(t))}"
            for t in (2.0 * math.pi * k / 8 for k in range(9))
        ]
        lines.append("CrossSection;" + ";".join(ring))
    return lines


def _revolution_lines() -> list[str]:
    profile = [
        f"{_fmt(x)};{_fmt(0.4 * math.sqrt(max(0.0, 1.0 - ((x - 1.5) / 1.5) ** 2)))};0.000000"
        for x in (3.0 * k / 6 for k in range(7))
    ]
    return [
        f"Component;{_REVOLUTION}",
        "LiftingSurface;false",
        "RevolveBody;0.0;0.0;0.0;1.0;0.0;0.0;0.0;360.0",
        "CrossSection;" + ";".join(profile),
    ]


def ccs_probe_text() -> str:
    """Return the three-component synthetic CCS file the CCS probes import."""
    body = ["Aircraft;PYFS_PROBE", "Units;Meter", ""]
    for part in (_wing_lines(), _fuselage_lines(), _revolution_lines()):
        body.extend(part)
        body.append("")
    return "\n".join(body)


def _ccs_file(workdir: Path) -> Path:
    path = workdir / _CCS_NAME
    _textio.write_text(path, ccs_probe_text())
    return path


# --- build callables -----------------------------------------------------


def _ccs_initialize(script: Script, workdir: Path) -> None:
    script.emit("CAD_CREATE_INITIALIZE")


def _ccs_import(component: int) -> Callable[[Script, Path], None]:
    def build(script: Script, workdir: Path) -> None:
        script.emit("CAD_CREATE_IMPORT_CURVE_CCS", "METER", 1, component, _ccs_file(workdir))

    return build


def _ccs_select(script: Script, workdir: Path) -> None:
    script.emit("CAD_CREATE_CURVE_SELECT", -1)


def _ccs_curve(component: int) -> Callable[[Script, Path], None]:
    """Initialize the loft session, import one component's curves, select them."""
    return _seq(_ccs_initialize, _ccs_import(component), _ccs_select)


def _wing_loft(name: str) -> Callable[[Script, Path], None]:
    return _emit("CAD_CREATE_WING_MESH_FROM_CCS", name, "TRUE", "SHARP", "TRUE", "C2", "C0")


def _fuselage_loft(name: str) -> Callable[[Script, Path], None]:
    return _emit("CAD_CREATE_FUSELAGE_MESH_FROM_CCS", name, "TRUE", "C2", "C2")


def _revolve_loft(name: str) -> Callable[[Script, Path], None]:
    return _emit("CAD_CREATE_REVOLVE_MESH_FROM_CCS", name, 1, "X", 0.0, 360.0, "TRUE", "C2", "C2")


def _export_obj(index: int, filename: str) -> Callable[[Script, Path], None]:
    def build(script: Script, workdir: Path) -> None:
        script.emit("EXPORT_SURFACE_MESH", "OBJ", index, workdir / filename)

    return build


def _ccs_import_file(script: Script, workdir: Path) -> None:
    script.emit(
        "CCS_IMPORT",
        close_component_ends="DISABLE",
        update_properties="DISABLE",
        clear_existing="ENABLE",
        file=_ccs_file(workdir),
    )


# --- effect assertions -----------------------------------------------------


def _name_in_saved(name: str, strict: bool) -> Callable[[ProbeArtifacts], bool | None]:
    """Make an assertion: the saved simulation names a loft (absent is None unless strict)."""

    def check(artifacts: ProbeArtifacts) -> bool | None:
        path = artifacts.workdir / "saved.fsm"
        if not path.is_file():
            return None
        if name.encode("ascii") in path.read_bytes():
            return True
        return False if strict else None

    return check


def _mesh_signature(workdir: Path, filename: str) -> tuple[int, int, int] | None:
    """Return (vertices, faces, hash of both) of an OBJ export, or None when it is absent."""
    path = workdir / filename
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    kept = [line for line in lines if line.startswith(("v ", "f "))]
    vertices = sum(1 for line in kept if line.startswith("v "))
    return vertices, len(kept) - vertices, hash(tuple(kept))


def _meshes_differ(artifacts: ProbeArtifacts, left: str, right: str) -> bool | None:
    """Judge whether two exported lofts differ; equal or absent records unprobed.

    Equal meshes are not broken: the second loft may not have been made at all,
    and a probe may never guess.
    """
    first = _mesh_signature(artifacts.workdir, left)
    second = _mesh_signature(artifacts.workdir, right)
    if first is None or second is None or not first[1] or not second[1]:
        return None
    return True if first != second else None


def _mesh_differs(artifacts: ProbeArtifacts) -> bool | None:
    """Judge whether the variant loft differs from the reference loft."""
    return _meshes_differ(artifacts, "reference.obj", "variant.obj")


def _mesh_read(artifacts: ProbeArtifacts) -> str:
    parts = []
    for name in ("reference.obj", "variant.obj", "restored.obj"):
        sig = _mesh_signature(artifacts.workdir, name)
        if sig is not None:
            parts.append(f"{name[:-4]} {sig[0]} vertices {sig[1]} faces")
    return "; ".join(parts) or "no loft was exported"


def _export_file_effect(name: str) -> Callable[[ProbeArtifacts], bool]:
    """Make an assertion: the export the command names exists and is not empty."""

    def check(artifacts: ProbeArtifacts) -> bool:
        path = artifacts.workdir / name
        return path.is_file() and path.stat().st_size > 0

    return check


def _export_file_read(name: str) -> Callable[[ProbeArtifacts], str]:
    """Say what the export file held: its size and its first line, never its numbers."""

    def read(artifacts: ProbeArtifacts) -> str:
        path = artifacts.workdir / name
        if not path.is_file():
            return f"{name} was not written"
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        first = lines[0][:40] if lines else ""
        return (
            f"{name} written, {path.stat().st_size} bytes, {len(lines)} lines, first line {first!r}"
        )

    return read


_INSTRUMENT_FILES = frozenset(
    {
        "probe_script.txt",
        "log_before.txt",
        "log_after.txt",
        "log_final.txt",
        "dump_before.txt",
        "dump_after.txt",
        "state_before.fsm",
        "state_after.fsm",
        "saved.fsm",
        "sheet.txt",
        "listing_at_build.txt",
    }
)


def _record_listing(script: Script, workdir: Path) -> None:
    """Record the directory at build time so a file the solver adds can be told apart."""
    listing = sorted(path.name for path in workdir.iterdir() if path.name != "listing_at_build.txt")
    _textio.write_text(workdir / "listing_at_build.txt", "\n".join(listing))


def _added_files(artifacts: ProbeArtifacts) -> list[str]:
    listing = artifacts.workdir / "listing_at_build.txt"
    known = set(listing.read_text(encoding="utf-8").splitlines()) if listing.is_file() else set()
    return sorted(
        path.name
        for path in artifacts.workdir.iterdir()
        if path.name not in known and path.name not in _INSTRUMENT_FILES
    )


def _a_file_was_added(artifacts: ProbeArtifacts) -> bool | None:
    """Judge whether the solver wrote a file in its folder (lax: the manual names no path)."""
    return True if _added_files(artifacts) else None


def _added_files_read(artifacts: ProbeArtifacts) -> str:
    return f"files added to the working folder: {', '.join(_added_files(artifacts)) or 'none'}"


# --- CCS: the lofts and their preparation (FR-333) ------------------------

_spec(
    command="CCS_IMPORT",
    build_target=_ccs_import_file,
    epilogue=_saveas,
    assert_effect=_name_in_saved(_WING, strict=True),
    effect_note="the saved simulation names the imported wing component",
)
_spec(
    command="CAD_CREATE_INITIALIZE",
    build_target=_ccs_initialize,
    epilogue=_seq(_ccs_import(1), _ccs_select, _wing_loft("PYFS_WING"), _saveas),
    assert_effect=_name_in_saved("PYFS_WING", strict=False),
    effect_note=(
        "the loft that follows the initialization names its wing in the saved simulation; "
        "no instrument reads the initialization itself, so absence records unprobed"
    ),
)
_spec(
    command="CAD_CREATE_IMPORT_CURVE_CCS",
    build_target=_ccs_import(1),
    prelude=_ccs_initialize,
    epilogue=_seq(_ccs_select, _wing_loft("PYFS_WING"), _saveas),
    assert_effect=_name_in_saved("PYFS_WING", strict=False),
    effect_note=(
        "the loft that consumes the imported curves names its wing in the saved simulation"
    ),
)
_spec(
    command="CAD_CREATE_CURVE_SELECT",
    build_target=_ccs_select,
    prelude=_seq(_ccs_initialize, _ccs_import(1)),
    epilogue=_seq(_wing_loft("PYFS_WING"), _saveas),
    assert_effect=_name_in_saved("PYFS_WING", strict=False),
    effect_note=(
        "the loft that consumes the selected curves names its wing in the saved simulation"
    ),
)
_spec(
    command="CAD_CREATE_WING_MESH_FROM_CCS",
    build_target=_wing_loft("PYFS_WING"),
    prelude=_ccs_curve(1),
    epilogue=_saveas,
    assert_effect=_name_in_saved("PYFS_WING", strict=True),
    effect_note="the saved simulation names the lofted wing",
)
_spec(
    command="CAD_CREATE_FUSELAGE_MESH_FROM_CCS",
    build_target=_fuselage_loft("PYFS_FUS"),
    prelude=_ccs_curve(2),
    epilogue=_saveas,
    assert_effect=_name_in_saved("PYFS_FUS", strict=True),
    effect_note="the saved simulation names the lofted fuselage",
)
_spec(
    command="CAD_CREATE_REVOLVE_MESH_FROM_CCS",
    build_target=_revolve_loft("PYFS_REV"),
    prelude=_ccs_curve(3),
    epilogue=_saveas,
    assert_effect=_name_in_saved("PYFS_REV", strict=True),
    effect_note="the saved simulation names the body of revolution",
)

#: A second loft of the same curve, with the target between the two lofts.
_SECOND_WING_LOFT = _seq(
    _ccs_select,
    _wing_loft("PYFS_VARIANT"),
    _export_obj(1, "reference.obj"),
    _export_obj(2, "variant.obj"),
)
_REFERENCE_WING = _seq(_ccs_curve(1), _wing_loft("PYFS_REFERENCE"))

_spec(
    command="CCS_WING_MESH_SUBDIVISIONS",
    build_target=_emit("CCS_WING_MESH_SUBDIVISIONS", "CHORD", 30),
    prelude=_REFERENCE_WING,
    epilogue=_SECOND_WING_LOFT,
    assert_effect=_mesh_differs,
    observe=_mesh_read,
    effect_note=(
        "a wing lofted after 30 chordwise subdivisions has a different mesh from "
        "the same wing lofted before them"
    ),
)

# --- the three commands of PFS-2001.05 (FR-334) ---------------------------

_spec(
    command="NEW_CCS_WING_CONTROL_SURFACE",
    build_target=_emit(
        "NEW_CCS_WING_CONTROL_SURFACE",
        "PYFS_AIL",
        0.5,
        0.9,
        0.25,
        0.25,
        0.5,
        20.0,
        1.0,
        "PARAMETRIC",
        "Y",
    ),
    prelude=_REFERENCE_WING,
    epilogue=_SECOND_WING_LOFT,
    assert_effect=_mesh_differs,
    observe=_mesh_read,
    effect_note=(
        "a wing lofted after a gapped control surface has a different mesh from "
        "the same wing lofted before it (the PARAMETRIC form of RPT-097)"
    ),
)


def _surface_section_prelude(script: Script, workdir: Path) -> None:
    _record_listing(script, workdir)
    script.emit("CREATE_NEW_SURFACE_SECTION", 1, "XZ", 0.05, "1", "DISABLE", -1)


_spec(
    command="EXPORT_SURFACE_SECTIONS",
    build_target=_emit("EXPORT_SURFACE_SECTIONS", 1),
    requires=Requires.SOLUTION,
    prelude=_surface_section_prelude,
    assert_effect=_a_file_was_added,
    observe=_added_files_read,
    effect_note=(
        "the solver adds a file to its working folder: the manual states no file name "
        "for the one-section export, so the folder is read, and silence records unprobed"
    ),
    timeout_s=240.0,
)


def _volume_section_export(script: Script, workdir: Path) -> None:
    script.emit("EXPORT_VOLUME_SECTION_VTK", 1, workdir / "vsection.vtk")


def _vsection_file_lax(artifacts: ProbeArtifacts) -> bool | None:
    path = artifacts.workdir / "vsection.vtk"
    return True if path.is_file() and path.stat().st_size > 0 else None


_spec(
    command="VOLUME_SECTION_BOUNDARY_LAYER",
    build_target=_emit("VOLUME_SECTION_BOUNDARY_LAYER", 1, "ENABLE"),
    requires=Requires.SOLUTION,
    prelude=_CREATE_RECT_VSECTION,
    epilogue=_volume_section_export,
    assert_effect=_vsection_file_lax,
    effect_note=(
        "the volume section still exports after the toggle, so the command did not break "
        "the section (the 26.120 manual dropped the command: a build that does not "
        "recognise it records it removed)"
    ),
    timeout_s=240.0,
)

# --- the two CCS export commands of PFS-2003.06 (FR-335) -------------------

_spec(
    command="EXPORT_FUSELAGE_CCS_FILE",
    build_target=lambda script, workdir: script.emit(
        "EXPORT_FUSELAGE_CCS_FILE",
        "PYFS_FUS",
        "TRUE",
        "SHARP",
        "TRUE",
        "C2",
        "C2",
        workdir / "fuselage_export.csv",
    ),
    prelude=_seq(_ccs_curve(2), _fuselage_loft("PYFS_FUS")),
    assert_effect=_export_file_effect("fuselage_export.csv"),
    observe=_export_file_read("fuselage_export.csv"),
    effect_note=(
        "the CCS file the command names exists and is not empty, written from the six "
        "arguments of the signature heading"
    ),
)
_spec(
    command="EXPORT_REVOLVE_CCS_FILE",
    build_target=lambda script, workdir: script.emit(
        "EXPORT_REVOLVE_CCS_FILE",
        "PYFS_REV",
        "TRUE",
        "SHARP",
        "TRUE",
        "C2",
        "C2",
        workdir / "revolve_export.csv",
    ),
    prelude=_seq(_ccs_curve(3), _revolve_loft("PYFS_REV")),
    assert_effect=_export_file_effect("revolve_export.csv"),
    observe=_export_file_read("revolve_export.csv"),
    effect_note=(
        "the CCS file the command names exists and is not empty, written from the six "
        "arguments of the signature heading"
    ),
)

# --- DELETE_SURFACES (FR-333) --------------------------------------------


def _one_surface_gone(artifacts: ProbeArtifacts) -> bool | None:
    """Judge whether the inventory after is the one before, less its first name."""
    before = boundary_names(artifacts.workdir / "state_before.fsm")
    after = boundary_names(artifacts.workdir / "state_after.fsm")
    if not before or after is None:
        return None
    return tuple(after) == tuple(before[1:])


def _inventories_read(artifacts: ProbeArtifacts) -> str:
    before = boundary_names(artifacts.workdir / "state_before.fsm")
    after = boundary_names(artifacts.workdir / "state_after.fsm")
    return f"inventory before {before}, after {after}"


_spec(
    command="DELETE_SURFACES",
    build_target=_emit("DELETE_SURFACES", 1),
    requires=Requires.SIM,
    save_state=True,
    assert_effect=_one_surface_gone,
    observe=_inventories_read,
    effect_note=(
        "the saved boundary inventory after the command is the inventory before it "
        "without its first boundary, the rest renumbered"
    ),
)

# --- the acoustic chain (FR-333) -----------------------------------------

_SIGNALS = "signals.txt"
_SECTION = "section"


def _acoustic_motion(script: Script, workdir: Path) -> None:
    """Emit the frame and the rotary motion, setup phase, after the simulation opens."""
    _named_frame("PYFS_ROTOR")(script, workdir)
    script.emit("CREATE_NEW_MOTION", "ROTARY")
    script.emit("SET_MOTION_BOUNDARIES", 1, -1)
    script.emit("SET_MOTION_MOVING_FRAMES", 1, -1)
    script.emit("SET_MOTION_COORDINATE_SYSTEM", 1, 2)
    script.emit("SET_MOTION_ROTOR_AXIS", 1, "X")
    script.emit("SET_MOTION_ROTOR_RPM", 1, 1200.0)


def _acoustic_solver(script: Script, workdir: Path) -> None:
    """Emit the unsteady solver setup, init phase, after every setup command."""
    emit_solver_setup(script)
    script.emit("SET_SOLVER_UNSTEADY", time_iterations=24, delta_time=0.01)


def _observers_file(workdir: Path) -> Path:
    path = workdir / "observers.txt"
    _textio.write_text(path, "2\n0.0,10.0,5.0\n5.0,10.0,0.0\n")
    return path


def _sources(script: Script, workdir: Path) -> None:
    script.emit("ACOUSTIC_SOURCES", "ENABLE")


def _observer(script: Script, workdir: Path) -> None:
    script.emit("CREATE_NEW_ACOUSTIC_OBSERVER", "PYFS_OBS1", 0.0, 10.0, 0.0)


def _observer_import(script: Script, workdir: Path) -> None:
    script.emit("ACOUSTIC_OBSERVERS_IMPORT", _observers_file(workdir))


def _observer_time(script: Script, workdir: Path) -> None:
    script.emit("SET_ACOUSTIC_OBSERVER_TIME", 0.05, 0.2, 16)


def _run(script: Script, workdir: Path) -> None:
    _acoustic_solver(script, workdir)
    initialize_solver(script)
    script.emit("START_SOLVER")


def _compute(script: Script, workdir: Path) -> None:
    script.emit("COMPUTE_ACOUSTIC_SIGNALS")


def _export(script: Script, workdir: Path) -> None:
    script.emit("EXPORT_ACOUSTIC_SIGNALS", workdir / _SIGNALS)


def _section(script: Script, workdir: Path) -> None:
    folder = workdir / _SECTION
    folder.mkdir(exist_ok=True)
    script.emit(
        "CREATE_ACOUSTIC_SECTION",
        frame=1,
        plane="YZ",
        offset=0.0,
        radial_observers=2,
        azimuth_observers=4,
        inner_radius=5.0,
        outer_radius=10.0,
        storage_path=folder,
    )


_SETUP_STEPS = {
    "ACOUSTIC_SOURCES": _sources,
    "CREATE_NEW_ACOUSTIC_OBSERVER": _observer,
    "ACOUSTIC_OBSERVERS_IMPORT": _observer_import,
    "SET_ACOUSTIC_OBSERVER_TIME": _observer_time,
}
_ANALYSIS_STEPS = {
    "COMPUTE_ACOUSTIC_SIGNALS": _compute,
    "EXPORT_ACOUSTIC_SIGNALS": _export,
    "CREATE_ACOUSTIC_SECTION": _section,
}


def _signal_blocks(artifacts: ProbeArtifacts) -> list[tuple[str, list[list[float]]]] | None:
    """Parse the exported signals file into (observer name, data rows); None when absent."""
    path = artifacts.workdir / _SIGNALS
    if not path.is_file():
        return None
    blocks: list[tuple[str, list[list[float]]]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if text.startswith("Observer:"):
            blocks.append((text.split(":", 1)[1].strip(), []))
        elif blocks and re.match(r"^[-+0-9.]", text):
            try:
                blocks[-1][1].append([float(token) for token in text.split()])
            except ValueError:
                continue
    return blocks


def _signals_read(artifacts: ProbeArtifacts) -> str:
    blocks = _signal_blocks(artifacts)
    if blocks is None:
        return f"{_SIGNALS} was not written"
    rows = [len(data) for _, data in blocks]
    nonzero = sum(1 for _, data in blocks for row in data for value in row[1:] if value != 0.0)
    return (
        f"{len(blocks)} observer blocks, rows per block {rows}, {nonzero} nonzero pressure values"
    )


def _sources_effect(artifacts: ProbeArtifacts) -> bool | None:
    blocks = _signal_blocks(artifacts)
    if not blocks:
        return None
    nonzero = any(value != 0.0 for _, data in blocks for row in data for value in row[1:])
    return True if nonzero else None


def _observer_effect(artifacts: ProbeArtifacts) -> bool | None:
    blocks = _signal_blocks(artifacts)
    if not blocks:
        return None
    return "PYFS_OBS1" in [name for name, _ in blocks]


def _import_effect(artifacts: ProbeArtifacts) -> bool | None:
    blocks = _signal_blocks(artifacts)
    if not blocks:
        return None
    imported = [name for name, _ in blocks if re.fullmatch(r"Observer \d+", name)]
    return len(imported) >= 2


def _time_effect(artifacts: ProbeArtifacts) -> bool | None:
    blocks = _signal_blocks(artifacts)
    if not blocks or not all(data for _, data in blocks):
        return None
    sixteen = all(len(data) == 16 for _, data in blocks)
    starts = all(abs(data[0][0] - 0.05) < 1e-6 for _, data in blocks)
    return sixteen and starts


def _compute_effect(artifacts: ProbeArtifacts) -> bool | None:
    blocks = _signal_blocks(artifacts)
    if not blocks:
        return None
    return True if any(data for _, data in blocks) else None


def _export_effect(artifacts: ProbeArtifacts) -> bool:
    blocks = _signal_blocks(artifacts)
    return bool(blocks)


def _section_effect(artifacts: ProbeArtifacts) -> bool | None:
    folder = artifacts.workdir / _SECTION
    files = [path for path in folder.rglob("*") if path.is_file()] if folder.is_dir() else []
    return True if files else None


def _section_read(artifacts: ProbeArtifacts) -> str:
    folder = artifacts.workdir / _SECTION
    count = sum(1 for path in folder.rglob("*") if path.is_file()) if folder.is_dir() else 0
    return f"{count} files in the section storage folder"


def _chain_spec(
    command: str,
    effect: Callable[[ProbeArtifacts], bool | None],
    note: str,
    read: Callable[[ProbeArtifacts], str] = _signals_read,
) -> None:
    """Register one probe of the chain: the target in its place, the rest around it.

    Setup commands run before the solver initializes, so the ones ahead of the
    target go in the prelude and the ones after it in the epilogue; an analysis
    command needs the solution first, so the whole setup and the run go in the
    prelude and only the analysis commands after the target follow it.
    """
    setup = list(_SETUP_STEPS.items())
    analysis = list(_ANALYSIS_STEPS.items())
    epilogue: Callable[[Script, Path], None] | None
    if command in _SETUP_STEPS:
        at = [name for name, _ in setup].index(command)
        before = [step for _, step in setup[:at]]
        after = [step for _, step in setup[at + 1 :]]
        prelude = _seq(_acoustic_motion, *before)
        epilogue = _seq(*after, _run, _compute, _export)
        target = _SETUP_STEPS[command]
    else:
        at = [name for name, _ in analysis].index(command)
        before = [step for _, step in analysis[:at] if step is not _section]
        prelude = _seq(_acoustic_motion, *(step for _, step in setup), _run, *before)
        rest = [step for _, step in analysis[at + 1 :] if step is not _section]
        epilogue = _seq(*rest) if rest else None
        target = _ANALYSIS_STEPS[command]
    _spec(
        command=command,
        build_target=target,
        requires=Requires.SIM,
        prelude=prelude,
        epilogue=epilogue,
        assert_effect=effect,
        observe=read,
        effect_note=note,
        timeout_s=240.0,
    )


_chain_spec(
    "ACOUSTIC_SOURCES",
    _sources_effect,
    "the signals exported after a marched rotor carry nonzero pressures with the sources enabled",
)
_chain_spec(
    "CREATE_NEW_ACOUSTIC_OBSERVER",
    _observer_effect,
    "the signals file holds an observer block named for the observer created",
)
_chain_spec(
    "ACOUSTIC_OBSERVERS_IMPORT",
    _import_effect,
    "the signals file holds the two observers read from the observer file, named by index",
)
_chain_spec(
    "SET_ACOUSTIC_OBSERVER_TIME",
    _time_effect,
    "every observer block of the signals file has 16 rows and starts at the requested time",
)
_chain_spec(
    "COMPUTE_ACOUSTIC_SIGNALS",
    _compute_effect,
    "the signals exported after the computation carry data rows",
)
_chain_spec(
    "EXPORT_ACOUSTIC_SIGNALS",
    _export_effect,
    "the signals file the command names exists and holds observer blocks",
)
_chain_spec(
    "CREATE_ACOUSTIC_SECTION",
    _section_effect,
    "the section's storage folder holds files after the section is created on a computed solution",
    read=_section_read,
)


# --- the two observer deletions (the acoustic chapter is probed whole) -----------


def _second_observer(script: Script, workdir: Path) -> None:
    script.emit("CREATE_NEW_ACOUSTIC_OBSERVER", "PYFS_OBS2", 5.0, 10.0, 0.0)


_TWO_OBSERVERS = _seq(_acoustic_motion, _observer, _second_observer, _observer_time)


def _one_observer_gone(artifacts: ProbeArtifacts) -> bool | None:
    blocks = _signal_blocks(artifacts)
    if not blocks:
        return None
    names = {name for name, _ in blocks}
    survivors = names & {"PYFS_OBS1", "PYFS_OBS2"}
    if len(survivors) == 1:
        return True
    return False if len(survivors) == 2 else None


def _no_observer_left(artifacts: ProbeArtifacts) -> bool | None:
    blocks = _signal_blocks(artifacts)
    if blocks is None:
        return None
    return not blocks


_spec(
    command="DELETE_ACOUSTIC_OBSERVER",
    build_target=_emit("DELETE_ACOUSTIC_OBSERVER", 1),
    requires=Requires.SIM,
    prelude=_TWO_OBSERVERS,
    epilogue=_seq(_run, _compute, _export),
    assert_effect=_one_observer_gone,
    observe=_signals_read,
    effect_note=(
        "of the two observers created, exactly one is left in the signals file "
        "(the manual counts the index in the application's own tree)"
    ),
    timeout_s=240.0,
)
_spec(
    command="DELETE_ALL_ACOUSTIC_OBSERVERS",
    build_target=_emit("DELETE_ALL_ACOUSTIC_OBSERVERS"),
    requires=Requires.SIM,
    prelude=_TWO_OBSERVERS,
    epilogue=_seq(_run, _compute, _export),
    assert_effect=_no_observer_left,
    observe=_signals_read,
    effect_note="the signals file holds no observer block after both observers were deleted",
    timeout_s=240.0,
)
