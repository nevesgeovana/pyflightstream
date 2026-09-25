"""The surface averaged over a window by the package, from the per-step exports (G25, 0.28.0).

Pipeline role: the product a pproc's ``[time_averaging]`` asks for. The run
exports the surface as VTK at every step of the window (the per-step export
machinery of ``EXPORT_UNSTEADY_AFTER_ITER``, which ``[time_averaging]`` sets
where the row states no threshold of its own), and this module averages those
exports into ONE surface, written as a Tecplot by the writer the Tecplot of
every point is written with (:func:`pyflightstream.results.write_tecplot_surface`),
and as a VTK too where the pproc asks ``[exports] vtk``.

WHAT THE AVERAGE IS. The same PANEL (the VTK's cell index) across the steps of
the window, each step's values written back in the reference frame first, the
velocity components included (the solver writes them in the analysis loads
frame, as a point, RPT-074); every step weighs the same; nothing is
interpolated. The steps must share one topology (the node and polygon counts and
the nodes around every polygon), or the average is REFUSED by name; a step of
the window that was not exported SKIPS the average by name, never a partial
one. The nodes of the averaged file are those of the window's LAST step: on a
turning rotor the nodes move from step to step and their mean would be a
surface nobody flew. The average itself is :func:`~pyflightstream.post.unsteady.
blade_passage_average`, the package's one averaging routine: the panels are its
samples and the steps its frames.

``SOLVER_TIME_AVERAGING`` is never emitted: it hangs 26.124 (C01). The per-step
instants stay on disk and in ``products.json`` as ``kind: instant``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pyflightstream._digest import file_sha256
from pyflightstream._errors import ProductError
from pyflightstream.post.series import stamped_exports
from pyflightstream.post.unsteady import TimestepSeries, blade_passage_average
from pyflightstream.results import (
    NOT_CARRIED_BY_THE_VTK,
    IncompleteOutputError,
    MalformedOutputError,
    SurfaceFrame,
    VtkSurface,
    read_vtk_surface,
    surface_in_reference,
    write_tecplot_surface,
    write_vtk_surface,
)
from pyflightstream.workspace import RunRecord

__all__ = [
    "SURFACES_DIR",
    "SurfaceAverage",
    "average_surface_exports",
    "write_point_surface_average",
    "write_surface_average",
]

#: The folder under a matrix's products where the averaged surfaces land.
SURFACES_DIR = "surfaces"


@dataclass(frozen=True)
class SurfaceAverage:
    """One surface averaged over a window of per-step exports.

    Attributes
    ----------
    surface : VtkSurface
        The average, in the reference frame: the nodes of the window's last
        step, and each panel's values averaged over the window.
    window : tuple of int
        Inclusive ``(first_step, last_step)`` in solver time steps.
    steps : tuple of int
        The steps averaged, every one of the window.
    inputs : dict of str to str
        Each per-step VTK read, by its path as given, to its sha256.
    frame : SurfaceFrame
        The loads frame the exports were written in and were undone by.
    """

    surface: VtkSurface
    window: tuple[int, int]
    steps: tuple[int, ...]
    inputs: dict[str, str]
    frame: SurfaceFrame


def average_surface_exports(
    exports: Mapping[int, str | Path], *, window: tuple[int, int], frame: SurfaceFrame
) -> SurfaceAverage:
    """Average the per-step VTK surface exports of a window, panel by panel.

    Parameters
    ----------
    exports : mapping of int to path
        Each stamped VTK by the time step it was exported at.
    window : tuple of int
        Inclusive ``(first_step, last_step)``; every step of it must be there.
    frame : SurfaceFrame
        The analysis loads frame the solver wrote the exports in.

    Returns
    -------
    SurfaceAverage
        The average and what it was taken over.

    Raises
    ------
    ProductError
        If a step of the window was not exported (the average is skipped, never
        partial), if an export is not a surface export, or if two steps do not
        share one topology (the average is refused: a panel cannot be followed).
    """
    first, last = int(window[0]), int(window[1])
    steps = list(range(first, last + 1))
    missing = [step for step in steps if step not in exports]
    if missing:
        shown = ", ".join(str(step) for step in missing[:8]) + (", ..." if len(missing) > 8 else "")
        raise ProductError(
            f"{len(missing)} step(s) of the window {first} to {last} were not exported "
            f"(steps {shown}), so the average is skipped: an average of the steps that "
            "were would not be the window's"
        )
    surfaces: list[VtkSurface] = []
    inputs: dict[str, str] = {}
    first_surface: VtkSurface | None = None
    for step in steps:
        path = Path(exports[step])
        try:
            surface = read_vtk_surface(path)
        except (MalformedOutputError, IncompleteOutputError) as error:
            raise ProductError(
                f"step {step}'s export {path.name} is not a surface: {error}"
            ) from error
        if first_surface is None:
            first_surface = surface
        else:
            differs = first_surface.topology_differs(surface)
            if differs is not None:
                raise ProductError(
                    f"step {step}'s export {path.name} has {differs} of step {first}: the "
                    "steps of the window do not share one topology, so a panel cannot be "
                    "followed across them and the average is refused"
                )
            if list(surface.cell_data) != list(first_surface.cell_data):
                raise ProductError(
                    f"step {step}'s export {path.name} carries the variables "
                    f"{list(surface.cell_data)} and step {first}'s carries "
                    f"{list(first_surface.cell_data)}, so the average is refused"
                )
        surfaces.append(surface_in_reference(surface, frame))
        inputs[path.as_posix()] = file_sha256(path)
    names = list(surfaces[0].cell_data)
    series = TimestepSeries(
        steps=np.asarray(steps, dtype=int),
        times_s=None,
        points=surfaces[-1].points,
        fields={name: np.stack([each.cell_data[name] for each in surfaces]) for name in names},
        sources=tuple(Path(exports[step]) for step in steps),
        order_evidence="given",
    )
    average = blade_passage_average(series, window=(first, last))
    newest = surfaces[-1]
    return SurfaceAverage(
        surface=VtkSurface(
            points=newest.points,
            offsets=newest.offsets,
            connectivity=newest.connectivity,
            point_data=dict(newest.point_data),
            cell_data={name: average.fields[name] for name in names},
            title=newest.title,
        ),
        window=(first, last),
        steps=tuple(steps),
        inputs=inputs,
        frame=frame,
    )


def write_surface_average(
    dat: str | Path,
    average: SurfaceAverage,
    *,
    vtk: str | Path | None = None,
    overwrite: bool = False,
) -> list[Path]:
    """Write an averaged surface as Tecplot, and as VTK where asked.

    The Tecplot is written by :func:`~pyflightstream.results.write_tecplot_surface`,
    the writer of every point's Tecplot, and says in its ``DATASETAUXDATA`` what
    it is an average of. The VTK, in the reference frame, is the same surface.

    Returns
    -------
    list of pathlib.Path
        The files written, the Tecplot first.
    """
    first, last = average.window
    auxdata = {
        "AVERAGE_OF": (
            f"{len(average.steps)} per-step VTK surface exports, time steps {first} to "
            f"{last} inclusive, each weighing the same, averaged panel by panel by "
            "pyflightstream"
        ),
        "WINDOW": f"{first} {last}",
        "COORDINATES": f"the nodes of time step {last}, the window's last",
        "TRANSLATION": (
            "every value per panel, cell-centred; the nodes and the velocity "
            "components in the reference frame"
        ),
        "SOURCE_FRAME": f"the analysis loads frame, {average.frame.describe()}",
        "NOT_CARRIED": ", ".join(NOT_CARRIED_BY_THE_VTK)
        + " (the solver's Tecplot carries it and its VTK does not)",
    }
    title = f"FlightStream surface, averaged over time steps {first} to {last} by pyflightstream"
    written = [
        write_tecplot_surface(
            dat, average.surface, title=title, auxdata=auxdata, zone="Average", overwrite=overwrite
        )
    ]
    if vtk is not None:
        written.append(write_vtk_surface(vtk, average.surface, title=title, overwrite=overwrite))
    return written


def write_point_surface_average(
    root: Path,
    *,
    sim_dir: Path,
    record: RunRecord,
    out: Path,
    target: Callable[[Path], Path],
    vtk: bool = False,
    skipped: dict[str, str] | None = None,
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write the time-averaged surface of one point from its per-step exports (G25).

    Nothing for a record whose run stated no ``[time_averaging]``. Otherwise the
    window the RECORD carries is averaged, never one re-read from a pproc edited
    since, from the stamped VTK files where the point ran.

    Parameters
    ----------
    root : Path
        The workspace root, which the inputs are named relative to.
    sim_dir : Path
        The simulation folder.
    record : RunRecord
        The point's record: its ``surface_average_window`` and the translation
        that names its VTK and the loads frame.
    out : Path
        The matrix's products folder; the average lands under ``surfaces/``.
    target : callable
        Called with each file's path before it is written, as every other
        product's is: the products stage passes its archiver.
    vtk : bool
        Write the average as a VTK as well, which ``[exports] vtk`` asks for.
    skipped : dict, optional
        Receives the reason under the product's name where the average is
        skipped or refused.

    Returns
    -------
    tuple
        The files written and their ``products.json`` entries, keyed by the
        path each was written to, relative to ``out``.
    """
    stated = record.surface_average_window
    if stated is None:
        return [], {}
    translation = next(
        (entry for entry in record.surface_translations or [] if isinstance(entry, Mapping)),
        None,
    )
    name = (
        f"{SURFACES_DIR}/{record.point_name or record.run_id.rsplit('/', 1)[-1]}_time_average.dat"
    )
    if translation is None:
        if skipped is not None:
            skipped[name] = (
                "the run recorded no surface written from a VTK, so there is no per-step VTK "
                "and no loads frame to average from"
            )
        return [], {}
    source, dat = Path(str(translation["vtk"])), Path(str(translation["dat"]))
    name = f"{SURFACES_DIR}/{dat.stem}_time_average.dat"
    frame_record = translation.get("frame")
    ran_in = [sim_dir / Path(output).parent for output in record.outputs]
    files = stamped_exports(sim_dir, source.stem, *ran_in).get(("", source.suffix.lstrip(".")), {})
    bounds = stated["iterations"]
    try:
        if not isinstance(frame_record, Mapping):
            raise ProductError("the record states no loads frame for the VTK")
        frame = SurfaceFrame.from_record(frame_record)
        average = average_surface_exports(
            files, window=(int(bounds[0]), int(bounds[1])), frame=frame
        )
    except (ProductError, MalformedOutputError) as error:
        if skipped is not None:
            skipped[name] = str(error)
        return [], {}
    folder = out / SURFACES_DIR
    folder.mkdir(parents=True, exist_ok=True)
    dat_path = target(out / name)
    vtk_path = target(out / f"{SURFACES_DIR}/{dat.stem}_time_average.vtk") if vtk else None
    written = write_surface_average(dat_path, average, vtk=vtk_path, overwrite=True)
    inputs = {
        Path(os.path.relpath(path, root)).as_posix(): digest
        for path, digest in average.inputs.items()
    }
    entry: dict[str, object] = {
        "runs": [record.run_id],
        "kind": "average",
        "window": dict(stated),
        "steps": list(average.steps),
        "inputs": inputs,
        "averaged_by": "pyflightstream",
        "weighting": "uniform",
        "coordinates_step": average.window[1],
        "location": "cell-centred",
        "frame": "reference",
        "not_carried": list(NOT_CARRIED_BY_THE_VTK),
    }
    names: dict[str, dict[str, object]] = {}
    for path, format_name in zip(written, ("tecplot", "vtk"), strict=False):
        key = path.relative_to(out) if path.is_relative_to(out) else path
        names[key.as_posix()] = {**entry, "format": format_name}
    return written, names
