"""The read-back verdict of a wake-edge marking: every declared point marked in the saved file.

Pipeline role: workspace layer, private. The marking pass (geometry mark-boundaries) and the
campaign's wake-edge collection compare the trailing edges a saved simulation holds with the
mid-points every declared file names, in physical metres, and say which files lost edges and
what the builds' probes say a lost edge means. Re-exported by
:mod:`pyflightstream.workspace.wake_edges`, whose public name it keeps.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy

from pyflightstream._fsm import MeshReadError, saved_mesh_coordinate_unit, trailing_edge_midpoints
from pyflightstream._lengths import scale
from pyflightstream.workspace.manifest import RunStatus

__all__ = ["SECOND_IMPORT_ADDS_A_GROUP", "saved_wake_edge_verdict"]

#: Builds whose marking probe imported a second wake-edge file and saved both groups, the first
#: kept (the IMPORT_WAKE_EDGES_FROM_FILE observation, groups ["Rim", "Rim"], of each report).
SECOND_IMPORT_ADDS_A_GROUP: dict[str, str] = {
    "26.124": "reports/compat/CMP-26124_2026-10-26_marking.yaml",
    "26.125": "reports/compat/CMP-26125_2026-10-26_marking.yaml",
    "26.127": "reports/compat/CMP-26127_2026-11-06_marking.yaml",
}


def saved_wake_edge_verdict(sets, folder: Path, collected: Sequence[str], build: str):
    """Compare the marked saved mesh with every declared set in physical metres.

    Parameters
    ----------
    sets : sequence of mappings
        Declared edge points, tolerances and source files.
    folder : Path
        Folder containing the collected saved simulation.
    collected : sequence of str
        Collected output names, including exactly one saved simulation.
    build : str
        Solver build associated with the marking pass.

    Returns
    -------
    tuple or None
        Failure status and diagnosis, or None when every declared point is marked.
    """
    saves = [folder / name for name in collected if Path(name).suffix.lower() == ".fsm"]
    if len(saves) != 1:
        return (
            RunStatus.FAILED_INCOMPLETE_OUTPUT,
            "multiple wake-edge imports are checked on the saved simulation, and the run "
            f"collected {len(saves)} .fsm files; list exactly one saved simulation (.fsm) "
            "among the row's outputs",
        )
    try:
        unit = saved_mesh_coordinate_unit(saves[0])
        factor = None if unit is None else scale(unit, "METER")
        if factor is None:
            raise MeshReadError("saved mesh coordinate unit is unknown")
        marked = (
            numpy.asarray(trailing_edge_midpoints(saves[0]), dtype=float).reshape(-1, 3) * factor
        )
    except (OSError, ValueError, MeshReadError) as exc:
        return RunStatus.FAILED_INCOMPLETE_OUTPUT, f"cannot check saved trailing-edge sets: {exc}"
    missing, present, total = [], 0, 0
    for entry in sets:
        found = 0
        for point in entry["points_m"]:
            found += bool(
                len(marked)
                and numpy.any(numpy.linalg.norm(marked - point, axis=1) <= entry["tolerance"])
            )
        total += len(entry["points_m"])
        present += found
        if found < len(entry["points_m"]):
            missing.append(entry["file"])
    if missing:
        return RunStatus.FAILED_SCRIPT, _missing_words(missing, present, total, build)
    return None


def _missing_words(missing: list[str], present: int, total: int, build: str) -> str:
    """Name the files that lost edges, and what the build's probes say a lost edge means."""
    head = (
        f"the saved simulation marks {present} of {total} trailing-edge points; the edges of "
        f"{', '.join(missing)} are missing"
    )
    report = SECOND_IMPORT_ADDS_A_GROUP.get(_canonical_build(build) or "")
    if report is None:
        return (
            f"{head}, which is what a second wake-edge import replacing the first would "
            f"leave (unmeasured on {build}, PFS-2149.01)"
        )
    return (
        f"{head}. On FlightStream {build} a second wake-edge import adds a group and keeps "
        f"the first ({report}), so the solver did not keep those edges: compare the edges "
        "the solver log reports imported with the file, and look for an edge two "
        "declarations name or, on 26.127, an import before the first CREATE_NEW_BASE_REGION"
    )


def _canonical_build(build: str) -> str | None:
    """Return the registered build ``build`` names, or None where it names none or several."""
    from pyflightstream.versions import AmbiguousVersionAliasError, UnknownVersionError, resolve

    try:
        return resolve(build).canonical
    except (AmbiguousVersionAliasError, UnknownVersionError):
        return None
