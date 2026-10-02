"""The probe catalog, fourth part: the CCS meshing chapters of the wing, fuselage and revolve.

Pipeline role: the entries of ``PROBE_SPECS`` for the settings, refinement
zones, relaxed trailing edges, control-surface variants and exports of the
three CCS meshing chapters (FR-333, FR-334), written from one table so the
three families read alike. Every entry captures its loft immediately. Undo
probes compare reference, modified, unchanged control and restored lofts;
relaxed trailing edges also compare the saved mesh state (FR-401).

The module is imported by ``pyflightstream.qa.specs`` and registers into the
shared registry of ``pyflightstream.qa._spec_kit``.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._fsm import MeshReadError, mesh_face_counts
from pyflightstream.qa._spec_ccs_noise import (
    _ccs_curve,
    _ccs_select,
    _export_file_effect,
    _export_file_read,
    _export_obj,
    _fuselage_loft,
    _mesh_differs,
    _mesh_read,
    _mesh_signature,
    _revolve_loft,
    _wing_loft,
    ccs_probe_text,
)
from pyflightstream.qa._spec_kit import _emit, _seq, _spec
from pyflightstream.qa.probes import ProbeArtifacts
from pyflightstream.script import Script

__all__: list[str] = []

Build = Callable[[Script, Path], None]


@dataclass(frozen=True)
class _Family:
    """One CCS meshing chapter: its component, its loft and its direction words."""

    name: str
    component: int
    loft: Callable[[str], Build]
    first: str
    second: str


_WING = _Family("WING", 1, _wing_loft, "CHORD", "SPAN")
_FUSELAGE = _Family("FUSELAGE", 2, _fuselage_loft, "AXIAL", "RADIAL")
_REVOLVE = _Family("REVOLVE", 3, _revolve_loft, "AXIAL", "AZIMUTH")


def _capture(
    family: _Family, name: str, filename: str, clear: int = 0, saved: bool = False
) -> Build:
    """Export a loft before changing its definition; clear every surface it made."""

    def build(script: Script, workdir: Path) -> None:
        _ccs_select(script, workdir)
        family.loft(name)(script, workdir)
        _export_obj(1, filename + ".obj")(script, workdir)
        if saved:
            script.emit("SAVEAS", workdir / (filename + ".fsm"))
        delete = (
            "DELETE_SURFACES"
            if "DELETE_SURFACES" in script.registry.for_version(script.version)
            else "SURFACE_DELETE"
        )
        for _ in range(clear):
            script.emit(delete, 1)
        _ccs_select(script, workdir)

    return build


def _reference(family: _Family) -> Build:
    return _seq(_ccs_curve(family.component), _capture(family, "PYFS_REFERENCE", "reference", 1))


def _variant(family: _Family) -> Build:
    return _capture(family, "PYFS_VARIANT", "variant")


def _restored_differs_from_modified(artifacts: ProbeArtifacts) -> bool | None:
    """Judge that the setting changed the mesh and its undoing brought the first mesh back."""
    first = _mesh_signature(artifacts.workdir, "reference.obj")
    modified = _mesh_signature(artifacts.workdir, "variant.obj")
    restored = _mesh_signature(artifacts.workdir, "restored.obj")
    control = _mesh_signature(artifacts.workdir, "control.obj")
    if any(state is None or not state[1] for state in (first, modified, restored, control)):
        return None
    return _restoration(first, modified, control, restored)


def _restoration(first: object, modified: object, control: object, restored: object) -> bool | None:
    """Require the control to preserve a demonstrated modification before judging the undo.

    FR-333 R2 records equal or missing lofts as unprobed. False ("not
    restored") is returned only here, where a valid control differing from the
    reference proves the setup moved the mesh and the restored state still
    equals that control.
    """
    if first == modified or control != modified:
        return None
    return restored == first and restored != control


def _set_chapter(family: _Family, command: str, build: Build, note: str) -> None:
    """Register a setting: the mesh lofted after it differs from the mesh lofted before."""
    _spec(
        command=command,
        build_target=build,
        prelude=_reference(family),
        epilogue=_variant(family),
        assert_effect=_mesh_differs,
        observe=_mesh_read,
        effect_note=note,
    )


def _undo_chapter(
    family: _Family, command: str, build: Build, undo: Build, note: str, *, saved: bool = False
) -> None:
    """Register an undoing command: set, loft, undo, loft; the last loft equals the first."""
    count = 3 if command == "DELETE_CCS_WING_CONTROL_SURFACE" else 1
    initial = _emit(command, family.first) if command.startswith("DEFAULT_") else _seq()
    _spec(
        command=command,
        build_target=undo,
        prelude=_seq(
            _ccs_curve(family.component),
            initial,
            _capture(family, "PYFS_REFERENCE", "reference", 1, saved),
            build,
            _capture(family, "PYFS_MODIFIED", "variant", count, saved),
            _capture(family, "PYFS_CONTROL", "control", count, saved),
        ),
        epilogue=_capture(family, "PYFS_RESTORED", "restored", saved=saved),
        assert_effect=_saved_restored if saved else _restored_differs_from_modified,
        observe=_saved_read if saved else _mesh_read,
        effect_note=note,
    )


def _saved_mesh(workdir: Path, name: str) -> tuple[str, ...] | None:
    """Read only the saved mesh payload, excluding display names and colours.

    The relaxed-TE diagnosis locates its effect in per-face state, not in
    vertex/face counts. Compare that payload against the unchanged control;
    no undocumented row is assigned a guessed meaning.
    """
    path = workdir / f"{name}.fsm"
    try:
        counts = mesh_face_counts(path)
        if counts is None or not counts[0]:
            return None
        lines = path.read_text(encoding="utf-8").splitlines()
        start, end = lines.index("$MESH_START$"), lines.index("$MESH_END$")
        boundaries = int(lines[start + 3])
        payload = lines[start + 4 + 3 * boundaries : end]
        if end <= start or not _complete_saved_payload(payload, counts[0]):
            return None
        return tuple(
            ",".join(_state_token(token) for token in line.split(",") if token.strip())
            for line in payload
        )
    except (OSError, ValueError, IndexError, MeshReadError):
        return None


def _complete_saved_payload(lines: list[str], faces: int) -> bool:
    """Require sized per-face rows, five flag rows and complete vertex coordinates."""
    rows = [[token.strip() for token in line.split(",") if token.strip()] for line in lines]
    flags = next((at for at, row in enumerate(rows[3:], 3) if set(row) <= {"T", "F"}), None)
    if flags is None or len(rows) < flags + 10:
        return False
    if any(len(row) != faces for row in rows[1 : flags + 5]):
        return False
    if any(not set(row) <= {"T", "F"} for row in rows[flags : flags + 5]):
        return False
    if rows[flags + 5] != ["0"] or len(rows[flags + 6]) != 1:
        return False
    points = int(rows[flags + 6][0])
    return points > 0 and all(len(row) == points for row in rows[flags + 7 : flags + 10])


def _state_token(token: str) -> str:
    token = token.strip()
    if token in {"T", "F"}:
        return token
    number = float(token.replace("D", "E"))
    if not math.isfinite(number):
        raise ValueError("saved mesh state contains a non-finite value")
    return str(number + 0.0)


def _saved_restored(artifacts: ProbeArtifacts) -> bool | None:
    names = ("reference", "variant", "control", "restored")
    geometry = [_mesh_signature(artifacts.workdir, name + ".obj") for name in names]
    if any(state is None or not state[1] for state in geometry) or len(set(geometry)) != 1:
        return None
    states = [_saved_mesh(artifacts.workdir, name) for name in names]
    if any(state is None for state in states):
        return None
    return _restoration(*states)


def _saved_read(artifacts: ProbeArtifacts) -> str:
    states = {
        name: _saved_mesh(artifacts.workdir, name)
        for name in ("reference", "variant", "control", "restored")
    }
    return (
        _mesh_read(artifacts)
        + "; saved mesh state: "
        + ", ".join(
            f"{name} {'read' if state is not None else 'unreadable'}"
            for name, state in states.items()
        )
        + f"; control equals modified: {states['control'] == states['variant']}"
        + f"; restored equals reference: {states['restored'] == states['reference']}"
    )


def _wing_zone(script: Script, workdir: Path) -> None:
    """Place a spanwise zone inside the synthetic loft, with a tenth-span margin.

    This command accepts parametric V bounds, not a Cartesian box. Derive
    the physical interval from the same sections the loft imports, then
    map it to V. Forty-seven extra nodes make the interval denser.
    """
    wing = ccs_probe_text().split("Component;", 2)[1]
    span = [
        float(value)
        for line in wing.splitlines()
        if line.startswith("CrossSection;")
        for value in line.split(";")[2::3]
    ]
    low, high = min(span), max(span)
    width = high - low
    margin = 0.1 * width
    start, end = low + margin, high - margin
    script.emit("NEW_CCS_WING_REFINEMENT_ZONE", (start - low) / width, (end - low) / width, 47)


def _family_settings(family: _Family) -> None:
    """Register the settings and zones the three chapters share."""
    name, first, second = family.name, family.first, family.second
    prefix = f"CCS_{name}_MESH"
    if name != "WING":
        _set_chapter(
            family,
            f"{prefix}_SUBDIVISIONS",
            _emit(f"{prefix}_SUBDIVISIONS", first, 30),
            f"a {name.lower()} lofted after 30 {first.lower()} subdivisions has a different mesh",
        )
    _set_chapter(
        family,
        f"{prefix}_GROWTH_SCHEME",
        _emit(f"{prefix}_GROWTH_SCHEME", first, "SUCCESSIVE"),
        f"a {name.lower()} lofted after a successive {first.lower()} growth scheme has a "
        "different mesh",
    )
    _set_chapter(
        family,
        f"{prefix}_GROWTH_RATE",
        _emit(f"{prefix}_GROWTH_RATE", first, 1.2),
        f"a {name.lower()} lofted after a {first.lower()} growth rate of 1.2 has a different mesh",
    )
    _set_chapter(
        family,
        f"{prefix}_PERIODICITY",
        _emit(f"{prefix}_PERIODICITY", second, 2),
        f"a {name.lower()} lofted after a {second.lower()} periodicity of 2 has a different mesh",
    )
    zone = _wing_zone if name == "WING" else _emit(f"NEW_CCS_{name}_REFINEMENT_ZONE", 0.2, 0.6, 12)
    _set_chapter(
        family,
        f"NEW_CCS_{name}_REFINEMENT_ZONE",
        zone,
        f"a {name.lower()} lofted after a refinement zone has a different mesh",
    )
    _undo_chapter(
        family,
        f"DEFAULT_CCS_{name}_MESH_SETTINGS",
        _emit(f"{prefix}_SUBDIVISIONS", first, 30),
        _emit(f"DEFAULT_CCS_{name}_MESH_SETTINGS", first),
        f"after the {first.lower()} subdivisions were changed and the defaults restored, "
        "the loft equals the first loft",
    )
    _undo_chapter(
        family,
        f"DELETE_CCS_{name}_REFINEMENT_ZONES",
        zone,
        _emit(f"DELETE_CCS_{name}_REFINEMENT_ZONES", 1),
        "after a refinement zone was added and deleted, the loft equals the first loft",
    )


def _relaxed_trailing_edges(family: _Family) -> None:
    name = family.name
    relaxed = _emit(f"NEW_CCS_{name}_RELAXED_TE", 0.5, 0.2, 0.8)
    _set_chapter(
        family,
        f"NEW_CCS_{name}_RELAXED_TE",
        relaxed,
        f"a {name.lower()} lofted after a relaxed trailing edge has a different mesh",
    )
    _undo_chapter(
        family,
        f"DELETE_CCS_{name}_RELAXED_TE",
        relaxed,
        _emit(f"DELETE_CCS_{name}_RELAXED_TE", 1),
        "the saved per-face state returns to the reference after relaxed trailing-edge deletion, "
        "while an unchanged control retains the modification and all four geometries agree",
        saved=True,
    )


_CONTROL_SURFACE = _emit(
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
)


def _wing_variants() -> None:
    _set_chapter(
        _WING,
        "NEW_CCS_WING_MORPHING_SURFACE",
        _emit("NEW_CCS_WING_MORPHING_SURFACE", "PYFS_MORPH", 0.5, 0.9, 0.25, 0.25, 0.5, 20.0),
        "a wing lofted after a morphing surface has a different mesh",
    )
    _set_chapter(
        _WING,
        "NEW_CCS_WING_FLAP_COVE",
        _emit("NEW_CCS_WING_FLAP_COVE", "PYFS_COVE", 0.5, 0.9, 0.7, 0.8, "1"),
        "a wing lofted after a flap cove has a different mesh",
    )
    _undo_chapter(
        _WING,
        "DELETE_CCS_WING_CONTROL_SURFACE",
        _CONTROL_SURFACE,
        _emit("DELETE_CCS_WING_CONTROL_SURFACE", 1),
        "after a control surface was added and deleted, the loft equals the first loft",
    )


def _export_wing(script: Script, workdir: Path) -> None:
    script.emit(
        "EXPORT_WING_CCS_FILE",
        "PYFS_WING",
        "TRUE",
        "SHARP",
        "TRUE",
        "C2",
        "C0",
        workdir / "wing_export.csv",
    )


for _family in (_WING, _FUSELAGE, _REVOLVE):
    _family_settings(_family)
for _family in (_FUSELAGE, _REVOLVE):
    _relaxed_trailing_edges(_family)
_wing_variants()
_spec(
    command="EXPORT_WING_CCS_FILE",
    build_target=_export_wing,
    prelude=_seq(_ccs_curve(1), _wing_loft("PYFS_WING")),
    assert_effect=_export_file_effect("wing_export.csv"),
    observe=_export_file_read("wing_export.csv"),
    effect_note=(
        "the CCS file the command names exists and is not empty, written from the six "
        "arguments of the signature heading"
    ),
)
