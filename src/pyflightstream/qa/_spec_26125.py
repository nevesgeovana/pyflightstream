"""The probe catalog, sixth part: the commands the 26.125 manual documents first (FR-423).

Pipeline role: the entries of ``PROBE_SPECS`` for twelve of the thirteen commands the
26.125 edition of the manual (SRC-753) is the first to document, so the probe
campaign of 26.125 judges each of them. No other build carries a row for any
of them, so on every other build these entries never run.

THE JUDGES ARE LAX WHERE NOTHING IS KNOWN YET. A command whose effect lands in
the saved simulation is judged by the saved state MOVING across it, and a state
that does not move records unprobed rather than broken: whether a sweeper
reset, an angle step or a convergence threshold is written into the saved file
at all is what no run has measured, and a setting the file does not carry is
not a command that failed. The two exceptions are measured shapes: the CCS
curve assignment, judged by the loft after it naming its component in the saved
simulation, and the free-surface export, judged by the file it writes.

SET_DIRECT_AEROELASTIC_MESH_MORPHING, the thirteenth, is entered and probed by
item S6 of 0.37.0 (FR-341), which measured it on 26.124 (RPT-154), so it has no
entry here.

The module is imported by ``pyflightstream.qa.specs`` and registers into the
shared registry of ``pyflightstream.qa._spec_kit``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pyflightstream.qa._spec_catalog_b import _SWEEP_AOA_PRELUDE
from pyflightstream.qa._spec_ccs_noise import (
    _ccs_import,
    _ccs_initialize,
    _ccs_select,
    _export_obj,
    _fuselage_loft,
    _mesh_differs,
    _mesh_read,
    _name_in_saved,
    _revolve_loft,
    _wing_loft,
)
from pyflightstream.qa._spec_kit import _emit, _saveas, _seq, _spec
from pyflightstream.qa.probes import ProbeArtifacts, Requires
from pyflightstream.script import Script

__all__: list[str] = []

#: The time steps of the unsteady state the averaging probes set: three, the
#: window of the averaging their first and last.
_UNSTEADY = _emit("SET_SOLVER_UNSTEADY", time_iterations=3, delta_time=0.0123)

#: A predecessor of the averaging command hung 26.124 (C01), so these probes are
#: killed after a minute rather than the default, and a hang costs one minute.
_HANG_GUARD_S = 60.0

#: The free surface every free-surface probe creates first: half a metre above
#: the reference plane, two metres either side of the origin in X, two wide,
#: and a coarse grid (SRC-753 p.338).
_FREE_SURFACE = _emit("CREATE_FREE_SURFACE_TFI_MESH", 0.5, -1.0, 3.0, 2.0, 20, 10)
_FREE_SURFACE_VTK = "free_surface.vtk"


def _state_moved(artifacts: ProbeArtifacts) -> bool | None:
    """Judge a setting by the saved simulation moving across it; still is unprobed.

    True where both saved states exist and differ. Equal states, or a state
    missing, record unprobed: no run has measured whether the file carries the
    setting, so an unmoved file is not evidence that the command failed.
    """
    before = artifacts.saved_before()
    after = artifacts.saved_after()
    if not before or not after:
        return None
    return True if before != after else None


def _free_surface_written(artifacts: ProbeArtifacts) -> bool | None:
    """Judge the free-surface export by the file it names; absent records unprobed."""
    path = artifacts.workdir / _FREE_SURFACE_VTK
    return True if path.is_file() and path.stat().st_size > 0 else None


def _free_surface_export(script: Script, workdir: Path) -> None:
    script.emit("FREE_SURFACE_EXPORT_TYPE", "1", workdir / _FREE_SURFACE_VTK)


def _curves(component: int) -> Callable[[Script, Path], None]:
    """Initialize, import and select one component's curves, with no assignment."""
    return _seq(_ccs_initialize, _ccs_import(component), _ccs_select)


def _blend_loft(name: str) -> Callable[[Script, Path], None]:
    """Loft the probe wing with a blended trailing edge, the geometry the length shapes."""
    return _emit("CAD_CREATE_WING_MESH_FROM_CCS", name, "TRUE", "BLEND", "TRUE", "C2", "C0")


# --- the unsteady solver: the averaging pair (SRC-753 p.360) ---------------------

_spec(
    command="ENABLE_SOLVER_TIME_AVERAGING",
    build_target=_emit("ENABLE_SOLVER_TIME_AVERAGING", 1, 3),
    requires=Requires.SIM,
    prelude=_UNSTEADY,
    save_state=True,
    assert_effect=_state_moved,
    effect_note=(
        "the saved simulation moves across the command under an unsteady state of three "
        "steps; a still file records unprobed. Killed after a minute, since the command "
        "it replaces hung 26.124 (C01)"
    ),
    timeout_s=_HANG_GUARD_S,
)
_spec(
    command="DISABLE_SOLVER_TIME_AVERAGING",
    build_target=_emit("DISABLE_SOLVER_TIME_AVERAGING"),
    requires=Requires.SIM,
    prelude=_seq(_UNSTEADY, _emit("ENABLE_SOLVER_TIME_AVERAGING", 1, 3)),
    save_state=True,
    assert_effect=_state_moved,
    effect_note=(
        "the saved simulation moves across the command after the averaging was enabled; "
        "a still file records unprobed"
    ),
    timeout_s=_HANG_GUARD_S,
)

# --- the sweeper and the stability toolbox (SRC-753 pp.372, 384) -----------------

_spec(
    command="RESET_SOLVER_SWEEPER",
    build_target=_emit("RESET_SOLVER_SWEEPER"),
    requires=Requires.SOLVER,
    prelude=_SWEEP_AOA_PRELUDE,
    save_state=True,
    assert_effect=_state_moved,
    effect_note=(
        "the saved simulation moves across the reset of a configured angle sweep; a still "
        "file records unprobed"
    ),
)
_spec(
    command="STABILITY_TOOLBOX_ANGLE_INCREMENT",
    build_target=_emit("STABILITY_TOOLBOX_ANGLE_INCREMENT", 2.5),
    requires=Requires.SIM,
    save_state=True,
    assert_effect=_state_moved,
    effect_note="the saved simulation moves across the angle step; a still file records unprobed",
)

# --- the aeroelastic coupling toolbox (SRC-753 p.390) ----------------------------

_spec(
    command="SET_AEROELASTIC_CONVERGENCE_THRESHOLD",
    build_target=_emit("SET_AEROELASTIC_CONVERGENCE_THRESHOLD", 1e-5),
    requires=Requires.SIM,
    save_state=True,
    assert_effect=_state_moved,
    effect_note=(
        "the saved simulation moves across a threshold a hundred times below the "
        "documented default; a still file records unprobed"
    ),
)

# --- free surfaces (SRC-753 p.338) ----------------------------------------------

_spec(
    command="CREATE_FREE_SURFACE_TFI_MESH",
    build_target=_FREE_SURFACE,
    requires=Requires.SIM,
    save_state=True,
    assert_effect=_state_moved,
    effect_note="the saved simulation gains the free-surface mesh; a still file records unprobed",
)
_spec(
    command="FREE_SURFACE_EXPORT_TYPE",
    build_target=_free_surface_export,
    requires=Requires.SIM,
    prelude=_FREE_SURFACE,
    preconditions=("CREATE_FREE_SURFACE_TFI_MESH",),
    assert_effect=_free_surface_written,
    effect_note="the export writes the VTK file it names; no file records unprobed",
)
_spec(
    command="DELETE_FREE_SURFACE",
    build_target=_emit("DELETE_FREE_SURFACE"),
    requires=Requires.SIM,
    prelude=_FREE_SURFACE,
    preconditions=("CREATE_FREE_SURFACE_TFI_MESH",),
    save_state=True,
    assert_effect=_state_moved,
    effect_note=(
        "the saved simulation moves when the free surface created before it is deleted; "
        "a still file records unprobed"
    ),
)

# --- the CCS chapters (SRC-753 pp.298, 307, 311, 314) ------------------------------

_spec(
    command="ASSIGN_SELECTED_CURVES_TO_CCS_WING",
    build_target=_emit("ASSIGN_SELECTED_CURVES_TO_CCS_WING"),
    prelude=_curves(1),
    epilogue=_seq(_wing_loft("PYFS_WING"), _saveas),
    assert_effect=_name_in_saved("PYFS_WING", strict=False),
    effect_note="the loft after the assignment names its wing in the saved simulation",
)
_spec(
    command="ASSIGN_SELECTED_CURVES_TO_CCS_FUSELAGE",
    build_target=_emit("ASSIGN_SELECTED_CURVES_TO_CCS_FUSELAGE"),
    prelude=_curves(2),
    epilogue=_seq(_fuselage_loft("PYFS_FUS"), _saveas),
    assert_effect=_name_in_saved("PYFS_FUS", strict=False),
    effect_note="the loft after the assignment names its fuselage in the saved simulation",
)
_spec(
    command="ASSIGN_SELECTED_CURVES_TO_CCS_REVOLVE_BODY",
    build_target=_emit("ASSIGN_SELECTED_CURVES_TO_CCS_REVOLVE_BODY"),
    prelude=_curves(3),
    epilogue=_seq(_revolve_loft("PYFS_REV"), _saveas),
    assert_effect=_name_in_saved("PYFS_REV", strict=False),
    effect_note="the loft after the assignment names its revolved body in the saved simulation",
)
_spec(
    command="SET_CCS_TE_BLEND_LENGTH",
    build_target=_emit("SET_CCS_TE_BLEND_LENGTH", 40.0),
    prelude=_seq(_curves(1), _blend_loft("PYFS_REFERENCE")),
    epilogue=_seq(
        _ccs_select,
        _blend_loft("PYFS_VARIANT"),
        _export_obj(1, "reference.obj"),
        _export_obj(2, "variant.obj"),
    ),
    assert_effect=_mesh_differs,
    observe=_mesh_read,
    effect_note=(
        "a blended-edge wing lofted after a 40 per cent blend length has a different mesh "
        "from the same wing lofted before it at the default 10"
    ),
)
