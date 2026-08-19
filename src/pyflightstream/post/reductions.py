"""The writing seam of a reduction, and the file rule it holds.

Pipeline role: the only place in the package where a reduction of an
unsteady series becomes a file. It exists as its own module because the
rule it enforces is a rule about DESTINATIONS, and the average itself
(:func:`pyflightstream.post.unsteady.blade_passage_average`) is pure and
has none.

HER FILE RULE, 2026-08-16, absorbed from PFS-2015.03 into PFS-2015.01:

* a reduction NEVER overwrites the file it came from;
* the time series keeps its own dedicated file.

Both are enforced HERE rather than in a workflow, and that placement is
the whole point of the rule as she stated it: it holds however the
reduction is reached, so a caller who bypasses the workflow and calls
this layer directly cannot obtain an average with no history beside it.
A rule that only a workflow keeps is a rule with a documented way round
it.

Three refusals, and they are deliberately of two different types
because they are two different failures. Writing onto a file that was
READ, and writing a reduction with no series beside it, are file
management refusing to destroy evidence, which is
:class:`~pyflightstream.workspace.WorkspaceError`. Writing onto a file
that already exists is the silent-overwrite class PYFS-005 records,
which is :class:`~pyflightstream.post.writers.OutputExistsError` and
takes the same ``overwrite=True`` way through as the flow-visualization
writers.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from pyflightstream.post.unsteady import FrameAverage, TimestepSeries
from pyflightstream.post.writers import OutputExistsError
from pyflightstream.workspace import WorkspaceError

__all__ = ["write_reduction", "write_series"]


def _refuse_existing(destination: Path, overwrite: bool) -> None:
    """Refuse a destination that already exists (PFS-2011.02)."""
    if destination.exists() and not overwrite:
        raise OutputExistsError(
            f"{destination} already exists. Pass overwrite=True to replace it "
            "deliberately, or write under a name that carries the window: a reduction "
            "that silently replaced another is the shape PYFS-005 records, one point of "
            "a run overwriting another's output while the record listed both complete."
        )


def _refuse_a_source(destination: Path, sources: tuple[Path, ...]) -> None:
    """Refuse a destination that is one of the files the series read."""
    resolved = destination.resolve()
    clash = [source for source in sources if Path(source).resolve() == resolved]
    if clash:
        raise WorkspaceError(
            f"{destination} is a file this reduction was READ from, so writing it would "
            "replace the history with its own summary. A reduction never overwrites the "
            "file it came from (author's rule of 2026-08-16): write the average under a "
            "name of its own, beside the series."
        )


def write_series(
    path: str | Path,
    series: TimestepSeries,
    *,
    overwrite: bool = False,
) -> Path:
    """Write the time series to its own dedicated file.

    One row per exported frame: the solver step, the solution time in
    seconds where the frames carried one, and one column per sample of
    each field. The history is what makes an average auditable, so it
    gets a file rather than a section of one.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination CSV file. Its parent is created if absent.
    series : TimestepSeries
        The read-back frames.
    overwrite : bool, keyword-only
        Replace an existing destination. Default False.

    Returns
    -------
    pathlib.Path
        The written file.

    Raises
    ------
    OutputExistsError
        If the destination exists and ``overwrite`` is False.
    WorkspaceError
        If the destination is one of the frame files the series was
        read from.
    """
    destination = Path(path)
    _refuse_a_source(destination.parent / destination.name, series.sources)
    _refuse_existing(destination, overwrite)
    destination.parent.mkdir(parents=True, exist_ok=True)

    names = sorted(series.fields)
    header = ["step"]
    if series.times_s is not None:
        header.append("time_s")
    columns: list[np.ndarray] = []
    for name in names:
        values = series.fields[name]
        if values.ndim == 2:
            for sample in range(values.shape[1]):
                header.append(f"{name}_{sample}")
                columns.append(values[:, sample])
        else:
            for sample in range(values.shape[1]):
                for axis, letter in enumerate("xyz"):
                    header.append(f"{name}_{sample}_{letter}")
                    columns.append(values[:, sample, axis])

    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for index in range(series.n_frames):
            row: list[object] = [int(series.steps[index])]
            if series.times_s is not None:
                row.append(float(series.times_s[index]))
            row += [float(column[index]) for column in columns]
            writer.writerow(row)
    return destination


def write_reduction(
    path: str | Path,
    average: FrameAverage,
    *,
    series_file: str | Path,
    sources: tuple[Path, ...] | list[Path] | None = None,
    overwrite: bool = False,
) -> Path:
    """Write a reduction, refusing every way it could lose its history.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination CSV file, holding one row per field and sample:
        ``field,probe,mean``.
    average : FrameAverage
        The reduction, from
        :func:`pyflightstream.post.unsteady.blade_passage_average`.
    series_file : str or pathlib.Path, keyword-only
        The time series this reduction came from, written by
        :func:`write_series`. It must exist and sit in the same folder
        as the destination, because "beside it" is what makes the pair
        findable by someone holding only the folder.
    sources : sequence of pathlib.Path, optional
        Extra files this reduction was read from, on top of the frames
        the average already carries. Both sets are refused as
        destinations.
    overwrite : bool, keyword-only
        Replace an existing destination. Default False.

    Returns
    -------
    pathlib.Path
        The written file.

    Raises
    ------
    WorkspaceError
        If the destination is a file the reduction was read from, or if
        the series file is missing or is not beside the destination.
    OutputExistsError
        If the destination exists and ``overwrite`` is False.
    """
    destination = Path(path)
    series_path = Path(series_file)
    read = tuple(average.sources) + tuple(Path(item) for item in (sources or ())) + (series_path,)

    _refuse_a_source(destination, read)

    if not series_path.is_file():
        raise WorkspaceError(
            f"{series_path} does not exist, so this average would be written with no "
            "history beside it. The time series keeps its own dedicated file (author's "
            "rule of 2026-08-16): write it with write_series first, then the reduction."
        )
    if series_path.resolve().parent != destination.resolve().parent:
        raise WorkspaceError(
            f"{series_path} is not beside {destination}: the series sits in "
            f"{series_path.resolve().parent} and the reduction would go to "
            f"{destination.resolve().parent}. An average found without its history is an "
            "average nobody can audit, so the two live in one folder."
        )

    _refuse_existing(destination, overwrite)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["field", "probe", "mean"])
        for name in sorted(average.fields):
            values = average.fields[name]
            if values.ndim == 1:
                for probe, value in enumerate(values):
                    writer.writerow([name, probe, float(value)])
            else:
                for probe, vector in enumerate(values):
                    for axis, letter in enumerate("xyz"):
                        writer.writerow([f"{name}_{letter}", probe, float(vector[axis])])
    return destination
