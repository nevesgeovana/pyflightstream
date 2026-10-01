"""The probe catalog, fourth part: the CCS meshing chapters of the wing, fuselage and revolve.

Pipeline role: the entries of ``PROBE_SPECS`` for the settings, refinement
zones, relaxed trailing edges, control-surface variants and exports of the
three CCS meshing chapters (FR-333, FR-334), written from one table so the
three families read alike. Every entry lofts the same synthetic curve twice
or three times, the target between the lofts, exports each loft as OBJ and
compares the meshes: a setting that changes the mesh is verified, a deletion
that restores the first mesh is verified, and silence records unprobed.

The module is imported by ``pyflightstream.qa.specs`` and registers into the
shared registry of ``pyflightstream.qa._spec_kit``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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


def _reference(family: _Family) -> Build:
    return _seq(_ccs_curve(family.component), family.loft("PYFS_REFERENCE"))


def _variant(family: _Family) -> Build:
    return _seq(
        _ccs_select,
        family.loft("PYFS_VARIANT"),
        _export_obj(1, "reference.obj"),
        _export_obj(2, "variant.obj"),
    )


def _restored_differs_from_modified(artifacts: ProbeArtifacts) -> bool | None:
    """Judge that the setting changed the mesh and its undoing brought the first mesh back."""
    first = _mesh_signature(artifacts.workdir, "reference.obj")
    modified = _mesh_signature(artifacts.workdir, "variant.obj")
    restored = _mesh_signature(artifacts.workdir, "restored.obj")
    if first is None or modified is None or restored is None or not first[1] or not restored[1]:
        return None
    if first == modified:
        return None
    return True if restored == first else None


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


def _undo_chapter(family: _Family, command: str, build: Build, undo: Build, note: str) -> None:
    """Register an undoing command: set, loft, undo, loft; the last loft equals the first."""
    _spec(
        command=command,
        build_target=undo,
        prelude=_seq(_reference(family), build, _ccs_select, family.loft("PYFS_MODIFIED")),
        epilogue=_seq(
            _ccs_select,
            family.loft("PYFS_RESTORED"),
            _export_obj(1, "reference.obj"),
            _export_obj(2, "variant.obj"),
            _export_obj(3, "restored.obj"),
        ),
        assert_effect=_restored_differs_from_modified,
        observe=_mesh_read,
        effect_note=note,
    )


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
    zone = (
        _emit("NEW_CCS_WING_REFINEMENT_ZONE", 0.2, 0.6, 12)
        if name == "WING"
        else _emit(f"NEW_CCS_{name}_REFINEMENT_ZONE", 0.2, 0.6, 12)
    )
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
        "after a relaxed trailing edge was added and deleted, the loft equals the first loft",
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
