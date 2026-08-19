"""Flow-visualization writers: probe data to VTK and Tecplot files.

Pipeline role: turns probe positions plus sampled fields into files
ParaView (VTK legacy ASCII polydata) and Tecplot (ASCII POINT zone)
open directly, so any probe survey (planar grid, cylindrical
lattice, or parsed solver export) becomes inspectable flow-vis data.
The writers are deterministic (fixed ``%.9e`` formatting, fixed field
order) so outputs are diffable and goldens are exact, the same policy
as the STL writer of the QA geometry.

Scalars are ``(n,)`` arrays; a ``(n, 3)`` array is written as a
vector field. Field units are whatever the caller sampled; the
writers never rescale.

EVERY FILE CARRIES WHAT PRODUCED IT (PFS-2012.11, her requirement of
2026-08-16). A flow-visualization file used to hold coordinates, field
blocks and a title string, so the settings that produced the numbers had
to be recovered by joining the file back to the campaign's ``runs.json``
through a run identifier the file did not carry either. A file that
needs another file is the opposite of self-contained: separate the two
and the numbers survive while their meaning does not.

Neither format has a place for a sixty-five-flag record, so the record
goes BESIDE the file, named after it, as
``<name>.provenance.json``, and each writer returns the PAIR. The pair
is the deliverable: a data file without its record is half of one, which
is why ``provenance`` is a required keyword rather than an option.

The record is complete rather than tidy. Every flag of
:data:`~pyflightstream.script.solver_setup.FLAG_SPECS` appears, and a
flag nobody has established for that build appears with provenance
``unknown`` and a null value rather than being left out. On a bare
26.120 call that is fifty-seven of sixty-five, which looks like a poor
record and is an honest one: "no evidence exists for this build" and
"this flag does not exist" are different facts, and a reader has to be
able to tell which one the file means (FR-22c, FR-31).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import xarray as xr
from pydantic import BaseModel, ConfigDict

from pyflightstream._errors import PyflightstreamError
from pyflightstream.script.solver_setup import FLAG_SPECS, FlagRecord, SolverSetup

__all__ = [
    "PROVENANCE_SCHEMA",
    "PROVENANCE_SUFFIX",
    "OutputExistsError",
    "OutputProvenance",
    "dataset_to_points",
    "provenance_path",
    "settings_records",
    "write_tecplot_points",
    "write_vtk_points",
]

#: Stamp written into every sidecar. Read it before reading the rest:
#: a reader that finds an unfamiliar stamp knows the layout moved,
#: rather than discovering it a key at a time. It follows the manifest's
#: own convention (``pyfs-manifest/1``).
PROVENANCE_SCHEMA = "pyfs-output-provenance/1"

#: Suffix APPENDED to the output's full name to form its record, so
#: ``probes.vtk`` is described by ``probes.vtk.provenance.json``.
#:
#: Appended rather than substituted, and the reason was measured in this
#: repository's own suite rather than reasoned about: writing the same
#: survey to ``ring.vtk`` and ``ring.dat``, which
#: ``tests/test_post_writers.py`` has done since the far-field ledger
#: landed, gives both files the stem ``ring``. A record named for the
#: STEM would therefore be one file for two different exports, and the
#: second call would either overwrite the first's record or be refused
#: for a collision the caller did nothing wrong to cause. Keeping the
#: data file's own suffix inside the record's name makes the pairing
#: total.
PROVENANCE_SUFFIX = ".provenance.json"


class OutputExistsError(PyflightstreamError, FileExistsError):
    """A flow-visualization file would be overwritten (PFS-2011.02).

    Both writers ended in an unconditional ``write_text``, so a second
    call with the same destination replaced the first silently. That is
    the same class as the campaign defect PYFS-005 records: one point of
    a run overwrote another's output while the record listed both
    complete, which cost licensed solver time and could have published a
    report from one point counted twice.

    ``overwrite=True`` is the only way through and each writer's
    docstring says so.

    It keeps ``FileExistsError`` as its second base for the reason FR-39
    gives for every catalogued class: an existing ``except
    FileExistsError`` around a write catches exactly what it caught
    before, and it is the handler a caller writing a file already has.
    The evidence writers under ``qa`` raise the BUILTIN for the same
    situation, deliberately, because that predates the catalogue's reach;
    a new raise site takes the catalogued type.
    """


class OutputProvenance(BaseModel):
    """Where one post-processing file's numbers came from.

    The minimum a reader needs to say what produced a file, with the
    file in hand and nothing else: which run wrote it, which campaign
    that run belongs to, and the complete solver-flag snapshot of the
    script that ran (:class:`~pyflightstream.script.solver_setup.SolverSetup`).

    The FlightStream version is not a field of its own: it is
    ``setup.fs_version``, the version the per-version defaults in the
    snapshot were resolved against, and a second copy could disagree
    with it.

    Attributes
    ----------
    run_id : str
        Identity of the run, in the campaign's own vocabulary
        (``<campaign>/<sim>/<point>``, as
        :attr:`pyflightstream.workspace.RunRecord.run_id` writes it).
    campaign : str, optional
        Campaign name, when the file belongs to one. None for a
        standalone survey written outside a campaign, which is a real
        case and not a missing value.
    setup : SolverSetup
        The solver-flag snapshot of the script that produced the data.

    Examples
    --------
    >>> from pyflightstream.post import OutputProvenance
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.120")
    >>> setup = helpers.solver_settings(script, velocity=30.0)
    >>> provenance = OutputProvenance(run_id="polar/sim_1/a+00.0", setup=setup)
    >>> provenance.fs_version
    '26.120'
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    campaign: str | None = None
    setup: SolverSetup

    @property
    def fs_version(self) -> str:
        """Canonical FlightStream version the snapshot was resolved against."""
        return self.setup.fs_version


def settings_records(setup: SolverSetup) -> list[FlagRecord]:
    """Return one record per snapshot flag, in ``FLAG_SPECS`` order.

    Completeness is enforced here rather than trusted: a snapshot that
    carries fewer flags than the library knows about is completed with
    ``unknown`` records, so the written file names every flag. Silence
    about a flag is the one thing this record may not do, because a
    reader cannot distinguish silence from absence.

    A flag the snapshot carries and ``FLAG_SPECS`` does not know about is
    appended after the known set rather than dropped: it means the
    snapshot was written by a newer library, and dropping it would make
    this reader the thing that lost the fact.

    Parameters
    ----------
    setup : SolverSetup
        The snapshot to render.

    Returns
    -------
    list of FlagRecord
        One record per flag, known flags first in emission order.
    """
    known = [spec.command for spec in FLAG_SPECS]
    records = [
        setup.flags.get(command)
        or FlagRecord(command=command, family="unknown", provenance="unknown")
        for command in known
    ]
    seen = set(known)
    records += [record for command, record in setup.flags.items() if command not in seen]
    return records


def provenance_path(destination: str | Path) -> Path:
    """Return the settings record that describes ``destination``.

    Parameters
    ----------
    destination : str or pathlib.Path
        A file one of this module's writers wrote or will write.

    Returns
    -------
    pathlib.Path
        The record beside it, its full name plus
        :data:`PROVENANCE_SUFFIX`.

    Examples
    --------
    >>> from pyflightstream.post.writers import provenance_path
    >>> provenance_path("survey/ring.vtk").name
    'ring.vtk.provenance.json'
    """
    destination = Path(destination)
    return destination.with_name(destination.name + PROVENANCE_SUFFIX)


def _provenance_payload(provenance: OutputProvenance, destination: Path) -> str:
    """Render the sidecar text for one written file."""
    payload = {
        "provenance_schema": PROVENANCE_SCHEMA,
        "describes": destination.name,
        "run_id": provenance.run_id,
        "campaign": provenance.campaign,
        "fs_version": provenance.fs_version,
        "flags": [record.model_dump(mode="json") for record in settings_records(provenance.setup)],
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def _refuse_existing(destination: Path, overwrite: bool) -> None:
    """Refuse a destination that already exists (PFS-2011.02)."""
    if destination.exists() and not overwrite:
        raise OutputExistsError(
            f"{destination} already exists. This writer replaced it silently until "
            "2026-08-19, which is the shape PYFS-005 records: one point of a run "
            "overwrote another's output while the run record listed both complete. "
            "Pass overwrite=True to replace it deliberately, or write under a name "
            "that carries the point."
        )


def _write_pair(
    destination: Path,
    text: str,
    provenance: OutputProvenance,
    *,
    overwrite: bool,
) -> tuple[Path, Path]:
    """Write the data file and its settings record, or neither.

    Both destinations are tested BEFORE either is written, so a refusal
    never leaves half a pair behind: a data file whose record belongs to
    a different run is worse than no file at all.
    """
    record = provenance_path(destination)
    _refuse_existing(destination, overwrite)
    _refuse_existing(record, overwrite)
    destination.write_text(text, encoding="utf-8")
    record.write_text(_provenance_payload(provenance, destination), encoding="utf-8")
    return destination, record


def _fmt(value: float) -> str:
    return f"{value:.9e}"


def _checked(points: np.ndarray, fields: Mapping[str, np.ndarray] | None):
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(f"points must have shape (n, 3), got {points.shape}")
    checked: dict[str, np.ndarray] = {}
    for name, values in (fields or {}).items():
        array = np.asarray(values, dtype=float)
        if array.shape not in ((len(points),), (len(points), 3)):
            raise ValueError(
                f"field {name!r} has shape {array.shape}; it must hold one scalar "
                f"or one 3-vector per probe ({len(points)} probes)"
            )
        checked[name] = array
    return points, checked


def write_vtk_points(
    path: str | Path,
    points: np.ndarray,
    fields: Mapping[str, np.ndarray] | None = None,
    *,
    provenance: OutputProvenance,
    title: str = "pyflightstream probe data",
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Write probe data as a VTK legacy ASCII polydata file.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination ``.vtk`` file.
    points : numpy.ndarray
        Probe positions, shape ``(n, 3)``, reference frame.
    fields : mapping of str to numpy.ndarray, optional
        Per-probe data: ``(n,)`` scalars or ``(n, 3)`` vectors,
        written in the mapping's order.
    provenance : OutputProvenance, keyword-only
        Run identity and the solver-flag snapshot that produced the
        numbers. REQUIRED, and required rather than defaulted for the
        reason PFS-2012.11 gives: an optional record is absent exactly
        where it matters, on the run nobody thought about while writing
        the call. It is written beside the output as
        ``<name>.provenance.json``, because neither this format nor the
        Tecplot one can carry sixty-five flags inline.
    title : str
        VTK header title line.
    overwrite : bool, keyword-only
        Replace an existing destination. Default False, and the default
        is the point: this writer ended in an unconditional
        ``write_text``, so a second call with the same path replaced the
        first silently. It covers the record as well as the data file.

    Returns
    -------
    tuple of pathlib.Path
        ``(output, record)``: the written data file and the settings
        record beside it. The pair is the deliverable, so both are
        returned; a caller wanting only the first should say so by name.

    Raises
    ------
    OutputExistsError
        If either the destination or its record exists and
        ``overwrite`` is False. It keeps ``FileExistsError`` as a base,
        so an existing handler around the call catches what it always
        did. Neither file is written when either is refused.
    ValueError
        If ``points`` is not ``(n, 3)``, or a field's shape does not
        match the probe count.

    Examples
    --------
    >>> import numpy as np
    >>> from pyflightstream.post import OutputProvenance, write_vtk_points
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.120")
    >>> setup = helpers.solver_settings(script, velocity=30.0)
    >>> points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    >>> import tempfile, pathlib
    >>> folder = pathlib.Path(tempfile.mkdtemp())
    >>> output, record = write_vtk_points(
    ...     folder / "probes.vtk",
    ...     points,
    ...     {"cp": np.array([1.0, -0.5])},
    ...     provenance=OutputProvenance(run_id="polar/sim_1/a+00.0", setup=setup),
    ... )
    >>> record.name
    'probes.vtk.provenance.json'
    """
    points, checked = _checked(points, fields)
    n = len(points)
    lines = [
        "# vtk DataFile Version 3.0",
        title,
        "ASCII",
        "DATASET POLYDATA",
        f"POINTS {n} float",
    ]
    lines += [" ".join(_fmt(c) for c in row) for row in points]
    lines.append(f"VERTICES {n} {2 * n}")
    lines += [f"1 {i}" for i in range(n)]
    if checked:
        lines.append(f"POINT_DATA {n}")
        for name, array in checked.items():
            if array.ndim == 1:
                lines.append(f"SCALARS {name} float 1")
                lines.append("LOOKUP_TABLE default")
                lines += [_fmt(value) for value in array]
            else:
                lines.append(f"VECTORS {name} float")
                lines += [" ".join(_fmt(c) for c in row) for row in array]
    return _write_pair(Path(path), "\n".join(lines) + "\n", provenance, overwrite=overwrite)


def write_tecplot_points(
    path: str | Path,
    points: np.ndarray,
    fields: Mapping[str, np.ndarray] | None = None,
    *,
    provenance: OutputProvenance,
    title: str = "pyflightstream probe data",
    zone: str = "probes",
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Write probe data as a Tecplot ASCII ordered POINT zone.

    Vector fields expand into three variables with ``_x``/``_y``/``_z``
    suffixes, following the Cartesian axis naming of the writers'
    coordinate columns.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination ``.dat`` file.
    points : numpy.ndarray
        Probe positions, shape ``(n, 3)``, reference frame.
    fields : mapping of str to numpy.ndarray, optional
        Per-probe data: ``(n,)`` scalars or ``(n, 3)`` vectors.
    provenance : OutputProvenance, keyword-only
        Run identity and the solver-flag snapshot that produced the
        numbers, written beside the output as
        ``<name>.provenance.json``. REQUIRED, for the reason its sibling
        gives: the TITLE record is one string and the settings record is
        sixty-five flags with their citations, so it cannot go inline.
    title : str
        TITLE record.
    zone : str
        Zone name.
    overwrite : bool, keyword-only
        Replace an existing destination. Default False, for the same
        reason as its sibling: this writer also ended in an
        unconditional ``write_text``, so a second call with the same
        path replaced the first silently. It covers the record too.

    Returns
    -------
    tuple of pathlib.Path
        ``(output, record)``: the written data file and the settings
        record beside it.

    Raises
    ------
    OutputExistsError
        If either the destination or its record exists and
        ``overwrite`` is False. Neither file is written when either is
        refused.
    ValueError
        If ``points`` is not ``(n, 3)``, or a field's shape does not
        match the probe count.
    """
    points, checked = _checked(points, fields)
    columns: list[tuple[str, np.ndarray]] = [
        ("X", points[:, 0]),
        ("Y", points[:, 1]),
        ("Z", points[:, 2]),
    ]
    for name, array in checked.items():
        if array.ndim == 1:
            columns.append((name, array))
        else:
            for axis, component in zip("xyz", array.T, strict=True):
                columns.append((f"{name}_{axis}", component))
    lines = [
        f'TITLE = "{title}"',
        "VARIABLES = " + " ".join(f'"{name}"' for name, _ in columns),
        f'ZONE T="{zone}" I={len(points)} ZONETYPE=ORDERED DATAPACKING=POINT',
    ]
    table = np.column_stack([values for _, values in columns])
    lines += [" ".join(_fmt(value) for value in row) for row in table]
    return _write_pair(Path(path), "\n".join(lines) + "\n", provenance, overwrite=overwrite)


def dataset_to_points(ds: xr.Dataset) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Flatten a far-field ledger dataset into writer inputs.

    Rebuilds Cartesian positions from the survey coordinates
    (``x = station R``, ``y = r sin(psi) R``, ``z = r cos(psi) R``,
    the convention of :mod:`pyflightstream.probes`) and flattens every
    ``(station, r, psi)`` data variable in the dataset's order, so a
    ledger dataset drops straight into :func:`write_vtk_points` or
    :func:`write_tecplot_points`.

    Parameters
    ----------
    ds : xarray.Dataset
        Ledger dataset with dims ``(station, r, psi)`` and the
        ``tip_radius`` attribute, as built by
        :func:`pyflightstream.farfield.lattice_dataset`.

    Returns
    -------
    tuple
        ``(points, fields)``: positions ``(n, 3)`` in simulation
        length units and the flattened scalar fields.
    """
    tip = float(ds.attrs["tip_radius"])
    station = np.asarray(ds.coords["station"])
    r = np.asarray(ds.coords["r"])
    psi = np.asarray(ds.coords["psi"])
    x, rr, pp = np.meshgrid(station, r, psi, indexing="ij")
    points = np.column_stack(
        [
            (x * tip).ravel(),
            (rr * np.sin(pp) * tip).ravel(),
            (rr * np.cos(pp) * tip).ravel(),
        ]
    )
    fields = {}
    for name, variable in ds.data_vars.items():
        if variable.dims == ("station", "r", "psi"):
            fields[name] = np.asarray(variable).ravel()
    return points, fields
