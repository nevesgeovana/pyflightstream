"""``pyfs-qa physics`` and ``pyfs-qa drift`` read the workspace (PFS-2031.17).

Pipeline role: the driver that turns the physics rows of a campaign
workspace into the ``PHY-*`` and ``DRF-*`` evidence reports. It runs the
workspace's physics matrix through the run layer exactly as
``pyfs-matrix run`` does (:func:`run_physics_matrix`), reads the records
back and reduces each case's points with the functions of
:mod:`pyflightstream.qa.physics` (:func:`reduce_physics`), judges them
against the committed references and hands the result to that module's
report writer. ``drift`` is the same matrix run twice, once per solver
build under a registry overlay naming that build's executable, and the
two reductions diffed by :mod:`pyflightstream.qa.drift`
(:func:`drift_from_workspace`).

WHERE THIS MODULE LIVES, which is the decision the design study (66) said
the design settles first. The study feared that a driver reading the
workspace would put the qa layer above the workspace layer and invert the
pipeline's direction, "qa sits below workspace". Measured against the
package's own layer table, ``pyflightstream.overview._CORE_LAYERS``, the
premise is false: ``post | qa`` is the TOP row and ``run | workspace`` the
row under it, ``tests/tier1_offline/test_conventions.py`` asserts that qa
and post share a row, and the qa package already imported the run layer
(``qa.physics``, ``qa.probes``, ``qa.compat``) and the workspace layer
(``qa.cost``, ``qa.cli``) at module level before this module existed. A
driver composing run, workspace and qa therefore belongs in qa, where its
every import points DOWN, and the two homes the study priced were both
worse: a module under ``run/`` importing qa would be the one upward import
in the tree, and a new top-level package above qa would add a row to the
published architecture table for one module. ``tests/tier1_offline/test_qa_matrix.py``
measures the direction: this module imports the run and workspace layers
at module level, and no module of a lower row imports the qa package back.

HOW A ROW NAMES ITS CASE. The row's DESCRIPTION begins with the case id,
``PHY-01_lift_slope_of_the_AR8_NACA0012_wing_polar``, and the package
makes the link from that token to the reduction: a user never writes an
index of rows to cases. PHY-02 is two rows, told apart by the row's
``SYMMETRY`` (the MIRROR row is the half); PHY-06 is its own unsteady row
plus the steady polar of the PHY-01 row at the same angles, which is how
the tier-3 test read it before this module did.

WHAT RUNS AND WHAT IS READ. The run is the run layer's, unchanged: the
assessor is :class:`pyflightstream.run.LoadsAssessor`, the recipe
registry is the workflow table, the HIDDEN column decides the window, and
a recorded point is refused unless ``resume`` is given, in which case the
recorded points are skipped and only new ones run. On a workspace whose
physics matrix already ran under ``pyfs-matrix run``, ``resume`` is what
makes ``pyfs-qa physics`` a reader: nothing executes and the report is the
reduction of what the manifest holds.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Mapping
from pathlib import Path

import pyflightstream
from pyflightstream.cases.matrix import MatrixRow, read_matrix
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.qa.drift import DriftRun, diff_runs
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.physics import (
    PHYSICS_CASES,
    CaseResult,
    PhysicsEnvironmentError,
    PhysicsRun,
    PointResult,
    compare_metrics,
    load_reference,
    phy01_metrics,
    phy02_metrics,
    phy05_metrics,
    phy06_metrics,
)
from pyflightstream.results.tables import parse_run_loads
from pyflightstream.run import CampaignErrors, LoadsAssessor
from pyflightstream.run.matrix import run_matrix
from pyflightstream.versions import resolve
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace.inputs import LOCAL_EXECUTABLES_FILE
from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate, is_portable_name

__all__ = [
    "DEFAULT_MATRIX",
    "case_of_row",
    "drift_from_workspace",
    "physics_build",
    "physics_from_workspace",
    "physics_matrix",
    "point_result",
    "reduce_physics",
    "run_physics_matrix",
]

#: The physics matrix a workspace holds by convention, the tier-3
#: workspace's own name for it.
DEFAULT_MATRIX = "matriz_physics.fs"

#: A row names its case at the head of its DESCRIPTION cell.
_CASE_ID = re.compile(r"^(PHY-\d{2})(?:_|$)")

#: A point the run finished and judged from its loads table.
_TERMINAL_OK = (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER)


def physics_matrix(root: str | Path, matrix: str = DEFAULT_MATRIX) -> Path:
    """Return the physics matrix of a workspace, refusing a name it does not hold.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    matrix : str
        The matrix FILE NAME inside the root, ``matriz_physics.fs`` by
        default. A name and not a path, deliberately: the command reads
        one workspace, and the matrices of a workspace sit at its root
        beside ``inputs/`` (the workspace page), so a path elsewhere would
        name rows that the workspace's manifest cannot record.

    Raises
    ------
    PhysicsEnvironmentError
        When the root holds no matrix of that name; the message lists the
        matrices it does hold, and the parameter that picks another.
    """
    path = Path(root) / matrix
    if path.is_file():
        return path
    held = sorted(candidate.name for candidate in Path(root).glob("*.fs"))
    raise PhysicsEnvironmentError(
        f"the workspace {Path(root)} holds no matrix named {matrix!r}; it holds "
        f"{', '.join(held) if held else 'no matrix at all'}. The physics cases are rows "
        f"of a run matrix at the workspace root, {DEFAULT_MATRIX} by convention; name "
        "another with matrix (CLI: --matrix), or point at the workspace that holds it."
    )


def case_of_row(row: MatrixRow) -> str | None:
    """Return the case id a row names at the head of its DESCRIPTION, or None."""
    match = _CASE_ID.match(row.description)
    return match.group(1) if match else None


def physics_build(matrix: str | Path) -> str:
    """Return the one canonical build every active row of the matrix names.

    A ``PHY`` report is evidence of ONE build, and its stem carries that
    build, so the pre-flight that protects a licensed seat has to know it
    before anything runs. Two builds in one matrix is a comparison, which
    is what ``drift`` is for.

    Raises
    ------
    PhysicsEnvironmentError
        When an active row leaves FS_BUILD empty, or the rows name more
        than one build. The convention of a workspace matrix is that
        every row names its build (PFS-2029.01), so no default is offered.
    """
    rows = read_matrix(matrix)
    silent = [row.pol for row in rows if not row.fs_build.strip()]
    if silent:
        raise PhysicsEnvironmentError(
            f"row(s) {', '.join(silent)} of {Path(matrix).name} leave FS_BUILD empty. A "
            "physics report is evidence of the build it names, so every active row "
            "fills FS_BUILD with a build id of inputs/executables.toml; there is no "
            "default version on this command."
        )
    builds = sorted({row.fs_build.strip() for row in rows})
    if len(builds) != 1:
        raise PhysicsEnvironmentError(
            f"the active rows of {Path(matrix).name} name {len(builds)} builds "
            f"({', '.join(builds)}), and a physics report is evidence of one. Two builds "
            "of one case set is a drift: run pyfs-qa drift with the two executables, or "
            "give every row the same FS_BUILD."
        )
    return resolve(builds[0]).canonical


def _campaign_name(root: Path, name: str | None) -> tuple[str, str]:
    """Return the campaign name and where it came from, the rule ``pyfs-matrix`` applies.

    The name is part of every ``run_id`` in the manifest, so a resumed run
    has to derive it the way the first run did: from the workspace
    directory unless one was given (PFS-2029.03).
    """
    if name is not None:
        return name, "option"
    derived = root.resolve().name
    if not is_portable_name(derived):
        raise PhysicsEnvironmentError(
            f"the workspace directory is named {derived!r}, which is not a legal campaign "
            "name (a plain token: no separators, no whitespace, not empty), and no name "
            "was given; pass name (CLI: --name) to name the campaign yourself."
        )
    return derived, "directory"


def _workspace(root: str | Path) -> CampaignWorkspace:
    """Open the workspace under the author's point-naming convention, as ``pyfs-matrix`` does."""
    return CampaignWorkspace(root, naming=NamingTemplate(point_name=MATRIX_POINT_NAME))


def run_physics_matrix(
    workspace: CampaignWorkspace,
    matrix: str | Path,
    *,
    name: str | None = None,
    resume: bool = False,
) -> list[RunRecord]:
    """Run the physics matrix through the run layer, as ``pyfs-matrix run`` would.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The workspace holding the library the rows resolve against and
        the manifest the records land in.
    matrix : str or Path
        The matrix file, at the workspace root.
    name : str, optional
        The campaign name; the workspace directory's name when left out.
    resume : bool
        Skip the points the manifest already records and run the rest;
        without it a recorded point is refused before anything executes,
        exactly as in :func:`pyflightstream.run.matrix.run_matrix`.

    Returns
    -------
    list of RunRecord
        The records this call executed, in execution order; empty for a
        resumed run over a complete manifest.

    Raises
    ------
    pyflightstream.run.CampaignErrors
        After the loop, when at least one executed point failed. Every
        point is in the manifest by then, so a caller reducing the
        records reports the failed case beside the others rather than
        losing them (:func:`physics_from_workspace` does).
    """
    campaign, name_from = _campaign_name(Path(workspace.root), name)
    return run_matrix(
        matrix,
        workspace,
        name=campaign,
        name_from=name_from,
        recipes={},
        assess=LoadsAssessor(),
        recipe_registry=workflow_registry(),
        resume=resume,
    )


def point_result(workspace: CampaignWorkspace, record: RunRecord) -> PointResult:
    """One recorded point as the reduction functions read it.

    The loads table is resolved through the manifest and cross-checked
    against the point (:func:`pyflightstream.results.tables.parse_run_loads`),
    the label is the row and the point (``sim_5001/a+04.0``), and the
    convergence word is the record's own status, which the run layer
    judged with the log when one was exported. This is the ``_point`` of
    the tier-3 physics test, moved into the package so the driver and
    the test read a record the same way.
    """
    report = parse_run_loads(workspace, record)
    return PointResult(
        alpha_deg=float(record.point.get("alpha", 0.0)),
        total=dict(report.total),
        iterations=report.current_iteration,
        converged=record.status is RunStatus.CONVERGED,
        label=f"sim_{record.sim_id}/{record.run_id.rsplit('/', 1)[-1]}",
    )


def _records_by_row(workspace: CampaignWorkspace, stem: str) -> dict[str, list[RunRecord]]:
    """Return the manifest's records of one matrix by POL, the latest per point winning."""
    latest: dict[str, dict[str, RunRecord]] = {}
    for record in workspace.read_manifest():
        if record.matrix_stem == stem:
            latest.setdefault(record.sim_id, {})[record.run_id] = record
    return {pol: list(points.values()) for pol, points in latest.items()}


def _points_of_row(
    workspace: CampaignWorkspace, row: MatrixRow, records: list[RunRecord]
) -> list[PointResult]:
    """Every point of one row as a :class:`PointResult`, sorted by angle of attack.

    Raises
    ------
    QaEvidenceError
        When the row has no record or a record is not a finished, judged
        point; the message names the row, the point and its status, and
        becomes the case's ``error`` field. The catalogued class rather
        than a bare ``RuntimeError`` (FR-39): the records are evidence
        and this is what the evidence cannot support.
    """
    if not records:
        raise QaEvidenceError(
            f"row {row.pol} ({row.description}) has no record in the manifest; run the "
            "matrix first, or resume a run that skipped it"
        )
    unfinished = [
        f"{record.run_id}: {record.status.value}" + (f" ({record.error})" if record.error else "")
        for record in records
        if record.status not in _TERMINAL_OK
    ]
    if unfinished:
        raise QaEvidenceError(
            f"row {row.pol} has {len(unfinished)} point(s) the run did not finish: "
            + "; ".join(unfinished)
        )
    return sorted((point_result(workspace, record) for record in records), key=_by_angle)


def _by_angle(point: PointResult) -> float:
    return point.alpha_deg


def _geometry_of(rows: list[MatrixRow], matrix: Path) -> str:
    """Return the one-line geometry statement of a case: which rows built it, from what."""
    parts = []
    for row in rows:
        geometry = row.variables.get("GEOMETRY", "the solver's open simulation")
        symmetry = row.variables.get("SYMMETRY", "NONE")
        parts.append(
            f"row {row.pol} of {matrix.name}, {row.workflow} workflow over {geometry} "
            f"under SYMMETRY {symmetry}"
        )
    return "; ".join(parts)


def _reduce_case(
    case_id: str,
    rows: list[MatrixRow],
    workspace: CampaignWorkspace,
    by_row: dict[str, list[RunRecord]],
    steady_rows: list[MatrixRow],
    matrix: Path,
) -> tuple[tuple[PointResult, ...], dict[str, float]]:
    """Reduce one case from its rows' records: the points shown and the metrics judged.

    Each branch states which rows feed which reduction, which is the one
    thing the retired script builders said and the matrix does not.
    """
    if case_id == "PHY-01":
        (row,) = rows
        points = _points_of_row(workspace, row, by_row.get(row.pol, []))
        return tuple(points), phy01_metrics(points)
    if case_id == "PHY-02":
        halves = [row for row in rows if row.variables.get("SYMMETRY", "").upper() == "MIRROR"]
        fulls = [row for row in rows if row not in halves]
        if len(halves) != 1 or len(fulls) != 1:
            raise QaEvidenceError(
                f"PHY-02 is one full-span row and one row under SYMMETRY MIRROR; the matrix "
                f"names {len(fulls)} full and {len(halves)} mirrored row(s) for it"
            )
        (full,) = _points_of_row(workspace, fulls[0], by_row.get(fulls[0].pol, []))
        (half,) = _points_of_row(workspace, halves[0], by_row.get(halves[0].pol, []))
        return (full, half), phy02_metrics(full, half)
    if case_id == "PHY-05":
        (row,) = rows
        (point,) = _points_of_row(workspace, row, by_row.get(row.pol, []))
        return (point,), phy05_metrics(point)
    if case_id == "PHY-06":
        (row,) = rows
        if len(steady_rows) != 1:
            raise QaEvidenceError(
                "PHY-06 judges the unsteady march against the steady polar of the PHY-01 "
                f"row, and the matrix names {len(steady_rows)} PHY-01 row(s)"
            )
        steady = _points_of_row(workspace, steady_rows[0], by_row.get(steady_rows[0].pol, []))
        unsteady = _points_of_row(workspace, row, by_row.get(row.pol, []))
        return (*steady, *unsteady), phy06_metrics(steady, unsteady)
    raise QaEvidenceError(f"{case_id} has no reduction in {__name__}")


def _one_row_each(case_id: str, rows: list[MatrixRow]) -> None:
    if case_id != "PHY-02" and len(rows) != 1:
        raise QaEvidenceError(
            f"{case_id} is one row of the matrix and {len(rows)} rows name it: "
            f"{', '.join(row.pol for row in rows)}"
        )


def reduce_physics(
    workspace: CampaignWorkspace,
    matrix: str | Path,
    *,
    references_dir: str | Path | None = None,
    source: str | None = None,
) -> PhysicsRun:
    """Reduce the recorded rows of the physics matrix into a judged physics run.

    Reads the manifest, takes the records of this matrix, groups them by
    row, maps each row to the case its DESCRIPTION names, reduces the
    case's points with the qa functions and judges the metrics against
    the committed references. A case whose rows did not all finish, or
    whose rows do not fit its reduction, is reported with its ``error``
    rather than raised, so one broken case cannot hide the others'
    evidence, which is what the hand-built run did too.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The workspace whose manifest holds the records.
    matrix : str or Path
        The matrix file; its stem selects the records and its rows name
        the cases.
    references_dir : str or Path, optional
        Alternative reference directory, used by tests.
    source : str, optional
        The sentence the report prints as its source; derived from the
        matrix and the workspace directory when left out.

    Returns
    -------
    PhysicsRun
        One :class:`CaseResult` per case the rows name, in registry order.

    Raises
    ------
    PhysicsEnvironmentError
        When a row names a case the registry does not know, when the
        manifest holds no record of this matrix, or when the records name
        more than one solver version (a physics report is evidence of
        one build; two is a drift).
    """
    path = Path(matrix)
    rows = read_matrix(path)
    by_case: dict[str, list[MatrixRow]] = {}
    for row in rows:
        case_id = case_of_row(row)
        if case_id is None:
            continue
        if case_id not in PHYSICS_CASES:
            raise PhysicsEnvironmentError(
                f"row {row.pol} of {path.name} names case {case_id}, which the registry "
                f"does not know; registered: {', '.join(PHYSICS_CASES)}. A row names its "
                "case at the head of DESCRIPTION, and the reduction is the registry's."
            )
        by_case.setdefault(case_id, []).append(row)
    by_row = _records_by_row(workspace, path.stem)
    if not by_row:
        raise PhysicsEnvironmentError(
            f"the manifest {workspace.manifest_path} holds no record of {path.name}; "
            "run the matrix first (pyfs-qa physics runs it, and pyfs-matrix run does)."
        )
    records = [record for points in by_row.values() for record in points]
    versions = sorted({record.fs_version_requested for record in records})
    if len(versions) != 1:
        raise PhysicsEnvironmentError(
            f"the records of {path.name} name {len(versions)} solver versions "
            f"({', '.join(versions)}), and a physics report is evidence of one build; two "
            "builds of one case set is a drift (pyfs-qa drift)."
        )
    results: list[CaseResult] = []
    steady_rows = by_case.get("PHY-01", [])
    for case_id, case in PHYSICS_CASES.items():
        case_rows = by_case.get(case_id)
        if not case_rows:
            continue
        # PHY-06 reads the PHY-01 row as its steady polar, so its
        # statement names both rows.
        geometry = _geometry_of(case_rows + (steady_rows if case_id == "PHY-06" else []), path)
        try:
            _one_row_each(case_id, case_rows)
            points, metrics = _reduce_case(case_id, case_rows, workspace, by_row, steady_rows, path)
        except QaEvidenceError as error:
            results.append(
                CaseResult(case_id=case_id, title=case.title, geometry=geometry, error=str(error))
            )
            continue
        reference = load_reference(case_id, references_dir)
        results.append(
            CaseResult(
                case_id=case_id,
                title=case.title,
                geometry=geometry,
                points=points,
                metrics=metrics,
                verdicts=compare_metrics(metrics, reference),
                reference=reference,
            )
        )
    identity: list[str] = []
    for record in records:
        if record.fs_version_reported is None:
            continue
        line = f"Flightstream version {record.fs_version_reported}, build {record.fs_build}"
        if line not in identity:
            identity.append(line)
    executables = sorted({Path(record.fs_exe).name for record in records if record.fs_exe})
    digests = sorted({record.fs_exe_sha256 for record in records if record.fs_exe_sha256})
    return PhysicsRun(
        version=versions[0],
        fs_exe_name=", ".join(executables) or "not recorded",
        package_version=pyflightstream.__version__,
        results=tuple(results),
        solver_identity=tuple(identity),
        fs_exe_sha256=", ".join(digests) or None,
        # How the solver was called, read off the first record that carries
        # it (PFS-2012.04); None for records written before the field.
        executor=next((record.executor for record in records if record.executor), None),
        source=source or f"{path.name} in workspace {Path(workspace.root).name}",
    )


def physics_from_workspace(
    root: str | Path,
    *,
    matrix: str = DEFAULT_MATRIX,
    name: str | None = None,
    resume: bool = False,
    references_dir: str | Path | None = None,
) -> PhysicsRun:
    """Run the workspace's physics matrix and reduce it: what ``pyfs-qa physics`` does.

    Parameters
    ----------
    root : str or Path
        The workspace root, holding ``inputs/`` and the matrix.
    matrix : str
        The matrix file name at the root, ``matriz_physics.fs`` by default.
    name : str, optional
        The campaign name; the directory's name when left out.
    resume : bool
        Skip the points the manifest already records. On a workspace
        whose matrix already ran, this is what makes the command a
        reader that spends no seat.
    references_dir : str or Path, optional
        Alternative reference directory, used by tests.

    Returns
    -------
    PhysicsRun
        The judged run. A point that failed leaves its case reported
        with an error rather than aborting the report: the run layer
        raises :class:`~pyflightstream.run.CampaignErrors` after the
        loop, and every point is in the manifest by then.

    Raises
    ------
    PhysicsEnvironmentError
        The refusals of :func:`physics_matrix`, :func:`physics_build`
        and :func:`reduce_physics`.
    pyflightstream.cases.matrix.MatrixError, pyflightstream.workspace.InputArtifactError
        The run layer's own refusals, before anything executes: a blocked
        pre-flight, a recorded point without ``resume``, a code the
        library cannot resolve.

    Examples
    --------
    The tier-3 workspace after its physics matrix ran on the licensed
    machine, reduced without a second seat:

    >>> from pyflightstream.qa.matrix import physics_from_workspace
    >>> run = physics_from_workspace("tests/tier3_licensed", resume=True)  # doctest: +SKIP
    >>> run.verdict_counts()["fail"]                                       # doctest: +SKIP
    0
    """
    path = physics_matrix(root, matrix)
    physics_build(path)
    workspace = _workspace(root)
    try:
        run_physics_matrix(workspace, path, name=name, resume=resume)
    except CampaignErrors:
        # Every point is recorded by now; the failed rows reach the
        # report as cases with an error beside the cases that finished.
        pass
    return reduce_physics(workspace, path, references_dir=references_dir)


def _overlay_line(build_id: str, fs_exe: str | Path, version: str) -> str:
    return f'"{build_id}" = {{ path = "{Path(fs_exe).as_posix()}", version = "{version}" }}\n'


def drift_from_workspace(
    root: str | Path,
    version_a: str,
    version_b: str,
    *,
    fs_exes: Mapping[str, str | Path],
    workroot: str | Path,
    matrix: str = DEFAULT_MATRIX,
    name: str | None = None,
    references_dir: str | Path | None = None,
) -> DriftRun:
    """Run the physics matrix on two builds and diff the two reductions.

    Each side is a workspace of its own under ``workroot``, ``a_<build>``
    and ``b_<build>``: a copy of the workspace's ``inputs/`` library and
    the matrix, plus an ``inputs/executables.local.toml`` overlay sending
    every build id the rows name to that side's executable and version.
    So the rows are the same bytes on both sides, the two manifests and
    the two sweep tables are kept apart, and the run layer records each
    side against the executable it actually ran. The reductions are then
    diffed with the case bands centered on side A
    (:func:`pyflightstream.qa.drift.diff_runs`).

    Parameters
    ----------
    root : str or Path
        The workspace whose library and matrix both sides copy.
    version_a, version_b : str
        Baseline and compared versions; the same version twice is the
        degenerate self-comparison that proves the machinery.
    fs_exes : mapping of str to path
        The executable per canonical version, never guessed.
    workroot : str or Path
        Where the two side workspaces are made; each must not exist yet,
        because a drift is two fresh runs and a side that exists holds a
        manifest the run would refuse point by point.
    matrix : str
        The matrix file name at the root.
    name : str, optional
        The campaign name of both sides; the workspace directory's name
        when left out, as for the physics run.
    references_dir : str or Path, optional
        Alternative reference directory, used by tests; the diff itself
        needs no reference.

    Raises
    ------
    PhysicsEnvironmentError
        A missing matrix, a version with no executable, or a side root
        that already exists.
    """
    path = physics_matrix(root, matrix)
    canonical_a = resolve(version_a).canonical
    canonical_b = resolve(version_b).canonical
    builds = sorted({row.fs_build.strip() for row in read_matrix(path) if row.fs_build.strip()})
    runs: list[PhysicsRun] = []
    for side, canonical in (("a", canonical_a), ("b", canonical_b)):
        exe = fs_exes.get(canonical)
        if exe is None:
            raise PhysicsEnvironmentError(
                f"no executable given for {canonical}; fs_exes maps each version to its "
                "fs_exe (CLI: --fs-exe), written VERSION=PATH, one per version and never "
                "guessed."
            )
        side_root = Path(workroot) / f"{side}_{canonical.replace('.', '')}"
        if side_root.exists():
            raise PhysicsEnvironmentError(
                f"{side_root} already exists, and a drift is two fresh runs of the matrix; "
                "remove it or choose another workroot (CLI: --workroot)."
            )
        shutil.copytree(
            Path(root) / "inputs",
            side_root / "inputs",
            ignore=shutil.ignore_patterns("*.local.toml"),
        )
        shutil.copy(path, side_root / path.name)
        (side_root / "inputs" / LOCAL_EXECUTABLES_FILE).write_text(
            f"# Written by pyfs-qa drift: side {side} runs every build the rows name on "
            f"FlightStream {canonical}.\n"
            + "".join(_overlay_line(build, exe, canonical) for build in builds),
            encoding="utf-8",
        )
        workspace = _workspace(side_root)
        try:
            run_physics_matrix(workspace, side_root / path.name, name=name)
        except CampaignErrors:
            pass
        runs.append(
            reduce_physics(
                workspace,
                side_root / path.name,
                references_dir=references_dir,
                source=f"{path.name} in workspace {Path(root).name}, side {side} under "
                f"{side_root.name}",
            )
        )
    run_a, run_b = runs
    return diff_runs(run_a, run_b)
