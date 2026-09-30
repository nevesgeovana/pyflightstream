"""The run records of a workspace: which manifest, its restore and its rebuild.

Pipeline role: the run row, beside the manifest the run stage writes. It is
the 0.32.0 home of three operations on the records of a campaign workspace,
laid down as a contract before the work package that fills it (B1), so the
packages that call it (B2, the sync; B3, the post and collect with
``--runs``) code against fixed signatures:

* :func:`resolve_manifest` names the manifest file a command reads: the
  default ``runs.json``, or another file directly in the workspace root
  (``pyfs-matrix post --runs NAME`` and its siblings). It is implemented.
* :func:`restore` brings a file of the records family back from the
  workspace's ``archive/``: the manifest, the storage record, a matrix's
  products record, the plan receipt or the additional-post record (the
  kinds of :data:`RESTORE_KINDS`). A contract stub until B1 fills it.
* :func:`rebuild` reconstructs run records from the simulation folders under
  ``sims/``. A contract stub until B1 fills it.

Every stub refuses with
:class:`~pyflightstream._errors.ContractNotImplementedError` and the words
"not implemented yet (0.32.0 contract)". A refused manifest name is a
:class:`RunsManifestError`.

The post and the collect of other records (work package B3), at the end of
the module: :func:`manifest_workspace` is the workspace ``post --runs NAME``
and ``collect --runs NAME`` read, :func:`assemble_records` assembles the
records of ``post --from-sims`` in memory from the simulation folders, and
:func:`from_sims_workspace` is the workspace that post reads. Both kinds are
a :class:`ManifestWorkspace`, whose products go to ``post/<matrix>@<label>/``
beside the default ones and never over them.

The module imports the floor, ``cases``, ``results`` and the workspace row;
the collect's assessor is imported where it is called.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from pyflightstream._errors import (
    ContractNotImplementedError,
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream.cases import (
    POINT_AXIS_KEYS,
    POINT_NAME_FIELDS,
    SWEEP_NAME_VALUE,
    classify_outputs,
)
from pyflightstream.cases.matrix import ATTITUDE_KEYS, UNSTATED_CELLS, MatrixRow, read_matrix
from pyflightstream.cases.windows import LAST_REVS_AVG, replan, stated_key
from pyflightstream.results import parse_loads, parse_unsteady_plots
from pyflightstream.workspace import (
    AdditionalRecord,
    CampaignWorkspace,
    RunRecord,
    RunStatus,
    WorkspaceError,
    matrix_files,
)
from pyflightstream.workspace.flight_condition import (
    canonical_condition_defaults,
    resolve_flight_condition,
)
from pyflightstream.workspace.inputs import ReferenceArtifact
from pyflightstream.workspace.matrix import condition_defaults_origin
from pyflightstream.workspace.naming import PointName, datapoint_name_of

#: The manifest a workspace keeps its run records in, and the name
#: :func:`resolve_manifest` returns when no other is named.
DEFAULT_MANIFEST = "runs.json"

#: The file kinds :func:`restore` brings back from ``archive/``.
RESTORE_KINDS = ("runs", "storage", "products", "plan", "additional")

_NOT_YET = "not implemented yet (0.32.0 contract)"


class RunsManifestError(PyflightstreamError, ValueError):
    """A manifest name that does not name a file directly in the workspace root.

    ValueError because the refused thing is the NAME a caller passed, before
    any file is read.
    """


def resolve_manifest(root: str | Path, runs: str | None = None) -> Path:
    """Return the manifest file a command reads in the workspace ``root``.

    Parameters
    ----------
    root : str or Path
        The workspace root, the folder that holds ``runs.json``.
    runs : str, optional
        The manifest's file name. None means ``runs.json``. A name is a file
        directly in ``root``: it must end in ``.json`` and carry no path
        separator, no drive and nothing that leaves the root.

    Returns
    -------
    Path
        ``root / runs``. Whether the file exists is not asked: a command that
        writes a new manifest resolves its name here too.

    Raises
    ------
    RunsManifestError
        When ``runs`` is empty, carries a separator or a drive, does not end in
        ``.json``, has no name before ``.json``, or resolves outside ``root``.
    """
    base = Path(root)
    if runs is None:
        return base / DEFAULT_MANIFEST
    separators = {"/", "\\", os.sep, *([os.altsep] if os.altsep else [])}
    if not runs or any(mark in runs for mark in separators):
        raise RunsManifestError(
            f"the manifest name {runs!r} is not a file name: name a file directly in the "
            f"workspace root {base}, such as runs-rebuilt.json, with no folder in it"
        )
    if not runs.endswith(".json") or runs == ".json":
        raise RunsManifestError(
            f"the manifest name {runs!r} does not end in .json: a manifest is a JSON file "
            f"directly in the workspace root {base}"
        )
    candidate = base / runs
    inside = Path(os.path.abspath(candidate)).parent == Path(os.path.abspath(base))
    if Path(runs).drive or Path(runs).anchor or not inside:
        raise RunsManifestError(
            f"the manifest name {runs!r} resolves outside the workspace root {base}; name a "
            "file directly in it"
        )
    return candidate


def restore(
    root: str | Path,
    kind: str,
    *,
    stamp: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Restore one file of the records family from the workspace's ``archive/``.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    kind : str
        One of :data:`RESTORE_KINDS`.
    stamp : str, optional
        The archive stamp to restore from.
    apply : bool, default False
        Change files; without it the call previews and changes nothing.

    Returns
    -------
    dict
        The record of what was restored, or would be.

    Raises
    ------
    ContractNotImplementedError
        Always, until work package B1 fills this body.
    """
    raise ContractNotImplementedError(f"pyflightstream.run.records.restore: {_NOT_YET}")


def rebuild(
    root: str | Path,
    *,
    out: str | None = None,
    all_sims: bool = False,
    sims: Sequence[str] | None = None,
    build_alias: Mapping[str, str] | None = None,
    matrix: str | Path | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Rebuild run records from the simulation folders under ``sims/``.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    out : str, optional
        The manifest file the rebuilt records go to, a name
        :func:`resolve_manifest` accepts.
    all_sims : bool, default False
        Rebuild every simulation folder on disk, recorded or not.
    sims : sequence of str, optional
        The simulation ids to rebuild.
    build_alias : mapping of str to str, optional
        The scheduler name of a solver build, keyed by the build.
    matrix : str or Path, optional
        The matrix revision the simulations ran from.
    apply : bool, default False
        Write files; without it the call previews and writes nothing.

    Returns
    -------
    dict
        The record of what was rebuilt, or would be.

    Raises
    ------
    ContractNotImplementedError
        Always, until work package B1 fills this body.
    """
    raise ContractNotImplementedError(f"pyflightstream.run.records.rebuild: {_NOT_YET}")


# ---------------------------------------------------------------------------
# 0.32.0, work package B3: the post and the collect of other records.

#: What sets the products folder of a post of other records apart from the
#: default one: ``post/<matrix>@<label>/`` beside ``post/<matrix>/``.
APART_MARK = "@"

#: The label of the products folder of ``post --from-sims``: ``post/<matrix>@sims/``.
FROM_SIMS_LABEL = "sims"

#: The note every record assembled from the simulation folders carries in its
#: ``warnings``, which the post writes into its log beside the point.
ASSEMBLED_NOTE = (
    "assembled from the simulation folder by pyfs-matrix post --from-sims: no run "
    "record and no script was compared, so the matrix row, its reference and its "
    "setup state what the point was asked, and its exports what it reported"
)

#: The two angles a loads export reports, by the sweep axis that names them.
_REPORTED_ANGLES = ("alpha", "beta")

#: Half the last printed digit of an angle in a loads export (three decimals).
_ANGLE_TOLERANCE_DEG = 5e-4 + 1e-9

#: The folders under a simulation folder that hold no export of a point: the
#: archives, the scripts and the staged link to the input library.
_NOT_EXPORT_FOLDERS = frozenset({"archive", "scripts", "inputs"})

#: The column of a plots export that counts the solver's time steps.
_CLOCK_COLUMN = "Time-step"


class ManifestWorkspace(CampaignWorkspace):
    """A workspace whose run records are not runs.json, and whose products stand apart.

    Built by :func:`manifest_workspace` for a named manifest, which it reads
    and whose three writers (``append_record``, ``complete_submitted_record``,
    ``supersede_records``) it writes under that manifest's own lock, and by
    :func:`from_sims_workspace` for records assembled in memory, which no
    writer may write. Either way the products and the post's reports land in
    ``post/<matrix>@<label>/`` (:meth:`products_dir`, :meth:`reports_root`),
    so the default products are never overwritten and the two posts can be
    compared.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    label : str
        What follows :data:`APART_MARK` in the products folder's name.
    manifest : Path, optional
        The named manifest, a file directly in ``root``.
    assembled : sequence of RunRecord, optional
        Records assembled in memory; given, no manifest is read or written.
    refusals : mapping of str to str, optional
        What could not be assembled, by where it is, with the reason. Each is
        warned once, at the first :meth:`read_manifest`, so the post that reads
        the records writes it into its log.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        label: str,
        manifest: Path | None = None,
        assembled: Sequence[RunRecord] | None = None,
        refusals: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(root)
        self.label = label
        self._manifest = None if manifest is None else self.root / Path(manifest).name
        self._assembled = None if assembled is None else list(assembled)
        self.refusals = dict(refusals or {})
        self._announced = False

    @property
    def manifest_path(self) -> Path:
        """The named manifest; for assembled records, the ``sims/`` folder they came from."""
        if self._manifest is not None:
            return self._manifest
        return self.root / "sims"

    @property
    def assembled(self) -> list[RunRecord] | None:
        """The records assembled in memory, without announcing a refusal; None for a manifest."""
        return None if self._assembled is None else list(self._assembled)

    def products_dir(self, matrix_stem: str | None) -> Path:
        """Where these records' products land: ``post/<matrix>@<label>/``."""
        return self.root / "post" / f"{matrix_stem or 'products'}{APART_MARK}{self.label}"

    def reports_root(self, matrix_stem: str | None) -> Path:
        """Keep the post's measurement reports inside the apart folder, never ``reports/``."""
        return self.products_dir(matrix_stem)

    def read_raw_manifest(self) -> list[dict]:
        """Read the named manifest as written, or give each assembled record as JSON."""
        if self._assembled is None:
            return super().read_raw_manifest()
        return [record.model_dump(mode="json") for record in self._assembled]

    def read_manifest(self) -> list[RunRecord]:
        """Read the named manifest, or give the assembled records, warning each refusal once."""
        if self._assembled is None:
            return super().read_manifest()
        if not self._announced:
            self._announced = True
            for where, reason in self.refusals.items():
                warn(
                    f"{where}: the record was refused, and nothing was assumed in its place: "
                    f"{reason}",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
        return list(self._assembled)

    def read_additional(self) -> list[AdditionalRecord]:
        """Read the additional post's extractions; none belongs to assembled records."""
        if self._assembled is None:
            return super().read_additional()
        return []

    def _refuse_a_write(self) -> None:
        if self._assembled is not None:
            raise WorkspaceError(
                "records assembled from the simulation folders by --from-sims are never "
                f"written: they live in memory for one post of {self.root}"
            )

    def append_record(self, record: RunRecord) -> None:
        """Append to the named manifest; refused for assembled records."""
        self._refuse_a_write()
        super().append_record(record)

    def complete_submitted_record(self, record: RunRecord) -> None:
        """Complete a record of the named manifest; refused for assembled records."""
        self._refuse_a_write()
        super().complete_submitted_record(record)

    def supersede_records(self, *args: Any, **kwargs: Any) -> Path | None:
        """Supersede records of the named manifest; refused for assembled records."""
        self._refuse_a_write()
        return super().supersede_records(*args, **kwargs)


def manifest_workspace(root: str | Path, runs: str | None = None) -> CampaignWorkspace:
    """Return the workspace ``post --runs NAME`` and ``collect --runs NAME`` read.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    runs : str, optional
        The manifest's file name, as :func:`resolve_manifest` takes it. None,
        or ``runs.json``, is the default workspace, unchanged.

    Returns
    -------
    CampaignWorkspace
        The plain workspace for runs.json; otherwise a
        :class:`ManifestWorkspace` labelled with the manifest's stem, whose
        products land in ``post/<matrix>@<stem>/``.

    Raises
    ------
    RunsManifestError
        For a name :func:`resolve_manifest` refuses, for a manifest that is not
        in the root, and for ``sims.json``, whose folder would be the one of
        ``post --from-sims``.
    """
    path = resolve_manifest(root, runs)
    if path == resolve_manifest(root):
        return CampaignWorkspace(root)
    if path.stem == FROM_SIMS_LABEL:
        raise RunsManifestError(
            f"the manifest name {runs!r} would post into post/<matrix>{APART_MARK}"
            f"{FROM_SIMS_LABEL}/, the folder of post --from-sims; rename the manifest"
        )
    if not path.is_file():
        raise RunsManifestError(
            f"the manifest {path.name} is not in the workspace root {Path(root)}; name a "
            "manifest that is there (a named manifest is never read as an empty one)"
        )
    return ManifestWorkspace(root, label=path.stem, manifest=path)


def from_sims_workspace(
    root: str | Path, matrix_stem: str, *, steps_per_revolution: float | None = None
) -> ManifestWorkspace:
    """Return the workspace ``post MATRIX --from-sims`` reads: records assembled in memory.

    See :func:`assemble_records` for what is assembled and what is refused.
    The products land in ``post/<matrix>@sims/``.
    """
    assembled, refusals = assemble_records(
        root, matrix_stem, steps_per_revolution=steps_per_revolution
    )
    return ManifestWorkspace(root, label=FROM_SIMS_LABEL, assembled=assembled, refusals=refusals)


def assemble_records(
    root: str | Path, matrix_stem: str, *, steps_per_revolution: float | None = None
) -> tuple[list[RunRecord], dict[str, str]]:
    """Assemble in memory the run records of a matrix from its simulation folders.

    For points run outside this package there is no runs.json and no script
    to compare, so a record is assembled from what the workspace states: the
    matrix row (its sweep, its flight condition, its pproc, its window), the
    reference and the setup it names, and each point's exports under
    ``sims/sim_<POL>/``. One point is one loads export (a ``.txt`` no longer
    export suffix claims), anywhere under the simulation folder but its
    ``archive``, ``scripts`` and ``inputs`` folders; the point's other exports
    are the files beside it whose names extend its stem. Its name is its
    ``DP-<name>`` folder's, else the export's stem. Its status is the one the
    collect's assessor gives the exports.

    What a record would carry and cannot be recovered is REFUSED by name,
    never guessed, and that point (or that row) is left out:

    * the aliases and the reference block, when the row's reference does not
      resolve;
    * the flight condition, when the row and its setup's pins do not resolve;
    * the point of the sweep, when the angles the export reports are no value
      of the row's sweep, or when the row sweeps anything but an angle over
      more than one value;
    * the averaging window of a point with a time history, when the row states
      neither ``LAST_REVS_AVG`` nor ``LAST_ITERS_AVG``;
    * the steps per revolution, when the window is in revolutions and
      ``steps_per_revolution`` does not state them.

    A record assembled here carries no rotor block, so the rotor tables and the
    per-rotor reductions of such a point are the post's own named skips.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    matrix_stem : str
        The matrix, found at the root or under ``inputs/matrices/``.
    steps_per_revolution : float, optional
        The solver steps of one revolution, for a window in revolutions.

    Returns
    -------
    tuple
        The assembled records, and each refusal by where it is
        (``sims/sim_<POL>`` or the export's path) with its reason.

    Raises
    ------
    WorkspaceError
        When the matrix is in neither home, or ``steps_per_revolution`` is not
        a positive number.
    """
    import pyflightstream

    workspace = CampaignWorkspace(root)
    if steps_per_revolution is not None and not steps_per_revolution > 0:
        raise WorkspaceError(
            f"--steps-per-revolution {steps_per_revolution:g} is not a positive number of "
            "solver steps"
        )
    matrix = _the_matrix(workspace.root, matrix_stem)
    assembled: list[RunRecord] = []
    refusals: dict[str, str] = {}
    for row in read_matrix(matrix, active_only=False):
        sim_dir = workspace.root / "sims" / f"sim_{row.pol}"
        if not sim_dir.is_dir():
            continue
        where = f"sims/sim_{row.pol}"
        try:
            reference, pins, origin = _row_inputs(workspace, row)
        except (PyflightstreamError, OSError, ValueError) as error:
            refusals[where] = str(error)
            continue
        by_point: dict[str, list[tuple[str, RunRecord]]] = {}
        for loads in _loads_exports(sim_dir):
            export = f"{where}/{loads.relative_to(sim_dir).as_posix()}"
            try:
                record = _assembled_record(
                    workspace,
                    row,
                    matrix_stem,
                    sim_dir,
                    loads,
                    reference=reference,
                    pins=pins,
                    origin=origin,
                    steps_per_revolution=steps_per_revolution,
                    version=pyflightstream.__version__,
                )
            except (PyflightstreamError, OSError, ValueError) as error:
                refusals[export] = str(error)
                continue
            by_point.setdefault(repr(sorted(record.point.items())), []).append((export, record))
        for pairs in by_point.values():
            if len(pairs) == 1:
                assembled.append(pairs[0][1])
                continue
            # TWO EXPORTS AT ONE POINT COST BOTH, never a choice between them.
            names = ", ".join(export for export, _ in pairs)
            for export, record in pairs:
                refusals[export] = (
                    f"the point of the sweep: {names} report one point of row POL {row.pol}'s "
                    f"sweep, {dict(record.point)}; a point is one export, so none is chosen"
                )
        if not by_point and not any(name.startswith(f"{where}/") for name in refusals):
            refusals[where] = (
                "the simulation folder holds no loads export, so no point of it can be assembled"
            )
    return assembled, refusals


def _the_matrix(root: Path, matrix_stem: str) -> Path:
    """Return the one matrix file of ``matrix_stem`` among the workspace's matrix homes."""
    stem = Path(matrix_stem).stem
    found = [path for path in matrix_files(root) if path.stem == stem]
    if not found:
        raise WorkspaceError(
            f"the matrix {stem!r} is neither at the root of {root} nor under "
            "inputs/matrices/; post --from-sims reads its rows to assemble the records"
        )
    distinct = {path.read_bytes() for path in found}
    if len(distinct) > 1:
        raise WorkspaceError(
            f"the matrix {stem!r} is at {found[0]} and at {found[1]} with different bytes; "
            "keep one, since the records would depend on which was read"
        )
    return found[0]


def _row_inputs(
    workspace: CampaignWorkspace, row: MatrixRow
) -> tuple[ReferenceArtifact, dict[str, float], str]:
    """Return the reference, the setup's flight-condition pins and their origin, for a row."""
    try:
        reference = workspace.resolve_reference(row.ref_code)
    except (PyflightstreamError, OSError, ValueError) as error:
        raise WorkspaceError(
            f"the aliases and the reference block: row POL {row.pol} names the reference "
            f"{row.ref_code!r}, which does not resolve ({error}); a record carries both "
            "from it, so nothing is assumed in their place"
        ) from error
    origin = condition_defaults_origin(row.set_code)
    if row.set_code in UNSTATED_CELLS:
        return reference, {}, origin
    try:
        table = workspace.resolve_setup(row.set_code).settings.get("flight_condition") or {}
        if not isinstance(table, Mapping) or any(
            isinstance(value, bool) or not isinstance(value, int | float)
            for value in table.values()
        ):
            raise WorkspaceError(
                f"{origin} states [flight_condition] as {table!r}, and its pins are numbers"
            )
        pins = canonical_condition_defaults(
            {str(key): float(value) for key, value in table.items()}, origin
        )
    except (PyflightstreamError, OSError, ValueError) as error:
        raise WorkspaceError(
            f"the flight condition: row POL {row.pol} names the setup {row.set_code!r}, whose "
            f"pins cannot be read ({error})"
        ) from error
    return reference, pins, origin


def _loads_exports(sim_dir: Path) -> Iterator[Path]:
    """Every loads export under a simulation folder, in path order."""
    found: list[Path] = []
    for folder, children, files in os.walk(sim_dir):
        children[:] = sorted(
            name
            for name in children
            if name.casefold() not in _NOT_EXPORT_FOLDERS
            and not os.path.isjunction(os.path.join(folder, name))
            and not os.path.islink(os.path.join(folder, name))
        )
        for name in files:
            if classify_outputs([name]) == {"loads": name}:
                found.append(Path(folder) / name)
    yield from sorted(found)


def _companions(loads: Path) -> list[Path]:
    """Return the exports beside a loads export whose names extend its stem, in order."""
    prefix = f"{loads.stem}_"
    return sorted(
        path
        for path in loads.parent.iterdir()
        if path.is_file()
        and path.name.startswith(prefix)
        and classify_outputs([path.name]) not in ({}, {"loads": path.name})
    )


def _swept_name(row: MatrixRow) -> str:
    """Name the row's sweep as the package does: each swept field ``<code>+sweep``."""
    axes = _REPORTED_ANGLES if row.sweep.type == "alpha_beta" else (row.sweep.type,)
    codes = []
    for axis in axes:
        field = POINT_NAME_FIELDS.get(POINT_AXIS_KEYS.get(axis, axis))
        codes.append(f"{field.code if field is not None else axis}{SWEEP_NAME_VALUE}")
    return "".join(codes)


def _the_point(row: MatrixRow, export: str, alpha: float, beta: float) -> dict[str, float]:
    """Return the point of the row's sweep an export reports, or refuse naming why."""
    points = [dict(point) for point in row.sweep.points()]
    reported = {"alpha": alpha, "beta": beta}
    fitting = [
        point
        for point in points
        if all(
            abs(float(point[axis]) - reported[axis]) <= _ANGLE_TOLERANCE_DEG
            for axis in _REPORTED_ANGLES
            if axis in point
        )
    ]
    if len(fitting) == 1:
        return fitting[0]
    values = ", ".join(f"{value}" for value in row.sweep.values)
    if not fitting:
        raise WorkspaceError(
            f"the point of the sweep: {export} reports alpha {alpha:g} and beta {beta:g}, "
            f"and no point of row POL {row.pol}'s sweep ({row.sweep.type}: {values}) is at "
            "those angles, so the point it was asked as cannot be named"
        )
    raise WorkspaceError(
        f"the point of the sweep: row POL {row.pol} sweeps {row.sweep.type} over {values}, "
        f"{len(fitting)} of its points are at the angles {export} reports, and the export "
        "does not state its swept value; split the row, one value each"
    )


def _assembled_record(
    workspace: CampaignWorkspace,
    row: MatrixRow,
    matrix_stem: str,
    sim_dir: Path,
    loads: Path,
    *,
    reference: ReferenceArtifact,
    pins: Mapping[str, float],
    origin: str,
    steps_per_revolution: float | None,
    version: str,
) -> RunRecord:
    """Assemble the record of one point from its loads export, or refuse it by name."""
    from pyflightstream.run.collect import assessment_of_collected

    export = f"sims/sim_{row.pol}/{loads.relative_to(sim_dir).as_posix()}"
    try:
        report = parse_loads(loads.read_text(encoding="utf-8"))
    except (PyflightstreamError, ValueError) as error:
        raise WorkspaceError(
            f"the loads export: {export} cannot be read as one ({error})"
        ) from error
    point = _the_point(row, export, report.angle_of_attack_deg, report.sideslip_deg)
    stem = datapoint_name_of(loads.parent.name)
    name = stem if stem is not None else PointName(loads.stem)
    cell = dict(row.flight_condition)
    swept = POINT_AXIS_KEYS.get(row.sweep.type)
    if swept is not None and swept not in ATTITUDE_KEYS and row.sweep.type in point:
        cell[swept] = float(point[row.sweep.type])
    try:
        resolved = resolve_flight_condition(
            cell,
            pol=row.pol,
            reference_length_m=reference.chord_m,
            defaults=pins or None,
            defaults_origin=origin,
        )
    except PyflightstreamError as error:
        raise WorkspaceError(
            f"the flight condition of row POL {row.pol} cannot be resolved from the row and "
            f"its setup ({error})"
        ) from error
    companions = _companions(loads)
    moment = reference.moment_point
    record = RunRecord(
        run_id=f"{workspace.root.name}/sim_{row.pol}/{name}",
        sim_id=row.pol,
        point=point,
        point_name=str(name),
        sweep_name=_swept_name(row),
        matrix_stem=matrix_stem,
        fs_version_requested=row.fs_build if row.fs_build not in UNSTATED_CELLS else "unstated",
        velocity_requested_m_s=resolved.velocity_m_per_s,
        flight_condition=cell,
        flight_condition_defaults=dict(resolved.defaulted),
        flight_condition_defaults_from=origin if resolved.defaulted else "",
        density_kg_m3=resolved.density_kg_m3,
        temperature_k=resolved.temperature_k,
        viscosity_pa_s=resolved.viscosity_pa_s,
        density_source=resolved.density_source,
        reference_length_m=reference.chord_m,
        package_version=version,
        script_sha256="",
        raw_flag=False,
        pproc=row.pproc_code if row.pproc_code not in UNSTATED_CELLS else None,
        recipe=row.workflow,
        description=row.description,
        mach=resolved.mach,
        reference={
            "SREF": reference.area_m2,
            "CREF": reference.chord_m,
            "BREF": reference.span_m,
            "XMOM": moment.x_m,
            "YMOM": moment.y_m,
            "ZMOM": moment.z_m,
        },
        aliases={alias: list(members) for alias, members in reference.aliases.items()},
        motions=[dict(motion) for motion in row.motions],
        reductions=_reductions(row, export, companions, steps_per_revolution),
        outputs=[path.relative_to(sim_dir).as_posix() for path in (loads, *companions)],
        status=RunStatus.SUBMITTED,
        warnings=[ASSEMBLED_NOTE],
    )
    try:
        judged = assessment_of_collected(record, sim_dir)
    except (PyflightstreamError, OSError, ValueError) as error:
        raise WorkspaceError(
            f"the status: the collect's assessor cannot judge {export} ({error})"
        ) from error
    return record.model_copy(
        update={
            "status": judged.status,
            "iterations": judged.iterations,
            "residual": judged.residual,
            "error": judged.error,
            "fs_version_reported": judged.fs_version_reported,
            "fs_build": judged.fs_build,
            "log_file_used": judged.log_file_used,
        }
    )


def _reductions(
    row: MatrixRow,
    export: str,
    companions: Sequence[Path],
    steps_per_revolution: float | None,
) -> dict[str, object] | None:
    """Return the reductions plan of a point with a time history, cut from the row."""
    plots = next((path for path in companions if classify_outputs([path.name]).get("plots")), None)
    stated = stated_key(row.variables)
    if plots is None:
        if stated is None:
            return None
        raise WorkspaceError(
            f"the time history: row POL {row.pol} states {stated[0]} = {stated[1]:g}, and "
            f"{export} has no plots export beside it ({Path(export).stem}_plots.txt) to "
            "average over"
        )
    if stated is None:
        raise WorkspaceError(
            f"the averaging window: {export} has a time history, and row POL {row.pol} states "
            "neither LAST_REVS_AVG nor LAST_ITERS_AVG (or states both); the window a record "
            "carries is never assumed, so state one in the row"
        )
    if stated[0] == LAST_REVS_AVG and steps_per_revolution is None:
        raise WorkspaceError(
            f"the steps per revolution: row POL {row.pol} states LAST_REVS_AVG = "
            f"{stated[1]:g}, a window counted in revolutions, and nothing states how many "
            "solver steps one revolution of this run is; pass --steps-per-revolution N"
        )
    try:
        history = parse_unsteady_plots(plots.read_text(encoding="utf-8"))
        clock = history.series(_CLOCK_COLUMN)
    except (PyflightstreamError, ValueError) as error:
        raise WorkspaceError(
            f"the time history: {plots.name} cannot be read for its {_CLOCK_COLUMN} column "
            f"({error})"
        ) from error
    if not len(clock):
        raise WorkspaceError(f"the time history: {plots.name} holds no time step")
    plan: dict[str, object] = {
        "time_iterations": int(round(float(max(clock)))),
        "steps_per_revolution": steps_per_revolution,
        "blades": None,
    }
    cut = replan(plan, row.variables)
    if cut is None:
        raise WorkspaceError(
            f"the averaging window: row POL {row.pol} states {stated[0]} = {stated[1]:g}, "
            f"and no window of the {plan['time_iterations']} steps of {plots.name} can be "
            "cut from it"
        )
    return cut
