"""Pipe-delimited run matrix: reader, converter, and run entry.

Pipeline role: keeps the established run-matrix workflow working
unchanged, forever (BRF-08), and promotes the matrix to a first-class
interface of the file-managed modality (v0.3 decision): reading a
matrix and running it is one call, :func:`run_matrix`, with the native
``campaign.toml`` model staying the canonical internal form, so
nothing changes for campaign.toml users. The verified 15-column layout
is read as is: POL, AIRCRAFT, DESCRIPTION, RE, MACH, SWEEP_TYPE,
SWEEP_VALUES, REF, SET, ENTRY, FS_SCRIPT, FS_BUILD, HIDDEN, RUN,
VAR_NAMES_VALUES. Rows with RUN = 1 are active. SWEEP_TYPE names its
axes separated by ``/`` (verified codes: ``AL`` for alpha, ``BE`` for
beta) and SWEEP_VALUES carries one comma-separated value list per
axis, also ``/``-separated; the matrix workflow varies one axis while
the other holds a single value, which broadcasts here.
VAR_NAMES_VALUES holds ``/``-separated ``KEY:VALUE`` pairs; values may
contain spaces and escaped newlines (a literal backslash-n sequence),
which are preserved verbatim.

The historical 3-digit codes (REF, SET, ENTRY, FS_SCRIPT) were
resolved to files by number at run time; that import-by-number system
is replaced (PP-7, FR-12): :func:`to_campaign` maps the FS_SCRIPT
code to a registered recipe name through an explicit mapping and
preserves all four codes in the case variables, so the conversion is
lossless. :func:`convert_matrix` (FR-11) emits the native
``campaign.toml`` equivalent; RE is stored in millions in the matrix
and converts to an absolute Reynolds number.

On the run path, :func:`resolve_matrix` binds the reference columns
against the workspace input library
(:mod:`pyflightstream.workspace.inputs`): REF to a reference-data
artifact, SET to a solver-setup preset, ENTRY to named boundary
groups, and FS_BUILD to an executable through the build registry (an
explicit override path is the only way to run the MANUAL
mode). Plain conversion never needs the library; resolution applies
only when the matrix is planned or run. The run entries compose the
execution layer (:func:`pyflightstream.run.plan_campaign` and
:func:`pyflightstream.run.run_campaign`) and import it inside the
functions, so the cases layer keeps no module-level upward dependency.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from pyflightstream.cases import (
    Campaign,
    ReferenceData,
    ScriptRecipe,
    SimCase,
    SolverSettings,
    SweepAxis,
)

if TYPE_CHECKING:  # upper-layer types, imported only for annotations
    from pyflightstream.run import CampaignPlan, Executor, OutcomeAssessor
    from pyflightstream.workspace import (
        CampaignWorkspace,
        GroupsArtifact,
        ReferenceArtifact,
        RunRecord,
        SetupArtifact,
    )

__all__ = [
    "MatrixError",
    "MatrixRow",
    "ResolvedMatrix",
    "convert_matrix",
    "plan_matrix",
    "read_matrix",
    "resolve_matrix",
    "run_matrix",
    "to_campaign",
]

_COLUMNS = (
    "POL",
    "AIRCRAFT",
    "DESCRIPTION",
    "RE",
    "MACH",
    "SWEEP_TYPE",
    "SWEEP_VALUES",
    "REF",
    "SET",
    "ENTRY",
    "FS_SCRIPT",
    "FS_BUILD",
    "HIDDEN",
    "RUN",
    "VAR_NAMES_VALUES",
)
_SWEEP_CODES = {"AL": "alpha", "BE": "beta"}


class MatrixError(ValueError):
    """A run-matrix file does not match the verified layout.

    The reader supports exactly the verified format (FR-10); a
    deviation means the file is not a run matrix or was edited
    beyond what the matrix workflow produces.
    """


@dataclass(frozen=True)
class MatrixRow:
    """One parsed row of the run matrix.

    Attributes
    ----------
    pol : str
        Polar identifier (POL column); maps to the native ``sim_id``.
    aircraft, description : str
        Configuration name and free text.
    re_millions : float
        Reynolds number in millions, as stored in the matrix.
    mach : float
        Mach number.
    sweep : SweepAxis
        The sweep, already in native form.
    ref_code, set_code, entry_code, script_code : str
        The historical 3-digit codes (REF, SET, ENTRY, FS_SCRIPT).
    fs_build : str
        FS_BUILD column, kept verbatim.
    hidden : bool
        HIDDEN column, the windowless-run flag.
    run : int
        Activity flag; rows with 1 are active.
    variables : dict
        The KEY:VALUE variables, values kept as strings.
    """

    pol: str
    aircraft: str
    description: str
    re_millions: float
    mach: float
    sweep: SweepAxis
    ref_code: str
    set_code: str
    entry_code: str
    script_code: str
    fs_build: str
    hidden: bool
    run: int
    variables: dict[str, str]


def _parse_sweep(sweep_type: str, sweep_values: str) -> SweepAxis:
    axes = [token.strip() for token in sweep_type.split("/")]
    groups = [token.strip() for token in sweep_values.split("/")]
    unknown = [axis for axis in axes if axis not in _SWEEP_CODES]
    if unknown:
        raise MatrixError(
            f"SWEEP_TYPE code(s) {', '.join(unknown)} are not among the verified "
            f"codes ({', '.join(sorted(_SWEEP_CODES))}); extending the mapping needs "
            "evidence from a matrix that uses the code"
        )
    if len(axes) != len(groups):
        raise MatrixError(
            f"SWEEP_TYPE names {len(axes)} axes but SWEEP_VALUES holds {len(groups)} "
            "value groups; each axis takes one '/'-separated group"
        )
    values = {
        _SWEEP_CODES[axis]: [float(token) for token in group.split(",")]
        for axis, group in zip(axes, groups, strict=True)
    }
    if set(values) == {"alpha", "beta"}:
        alpha, beta = values["alpha"], values["beta"]
        if len(alpha) > 1 and len(beta) == 1:
            beta = beta * len(alpha)
        elif len(beta) > 1 and len(alpha) == 1:
            alpha = alpha * len(beta)
        elif len(alpha) != len(beta):
            raise MatrixError(
                "an AL/BE sweep varies one axis while the other holds a single "
                f"value; got {len(alpha)} alpha and {len(beta)} beta values"
            )
        return SweepAxis(
            type="alpha_beta", values=[list(pair) for pair in zip(alpha, beta, strict=True)]
        )
    axis_name, axis_values = next(iter(values.items()))
    return SweepAxis(type=axis_name, values=axis_values)


def _parse_variables(cell: str) -> dict[str, str]:
    variables: dict[str, str] = {}
    if not cell.strip():
        return variables
    for pair in cell.split("/"):
        name, separator, value = pair.partition(":")
        if not separator:
            raise MatrixError(
                f"variable {pair.strip()!r} is not a KEY:VALUE pair; VAR_NAMES_VALUES "
                "holds '/'-separated KEY:VALUE entries"
            )
        variables[name.strip()] = value.strip()
    return variables


def read_matrix(path: str | Path, *, active_only: bool = True) -> list[MatrixRow]:
    """Read a pipe-delimited ``matrix.fs`` run matrix.

    Parameters
    ----------
    path : str or Path
        Matrix file location.
    active_only : bool
        Keep only rows with RUN = 1, the matrix activity filter;
        False returns every row. Keyword-only, so a bare boolean
        never hides in the call.

    Returns
    -------
    list of MatrixRow
        Parsed rows in file order.
    """
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    content = [line for line in lines if line.strip() and not set(line.strip()) <= {"-"}]
    if not content:
        raise MatrixError(f"{path} holds no matrix content")
    header = tuple(cell.strip() for cell in content[0].split("|"))
    if header != _COLUMNS:
        raise MatrixError(
            f"{path} header does not match the verified 15-column layout; expected "
            f"{', '.join(_COLUMNS)} and found {', '.join(header)}"
        )
    rows: list[MatrixRow] = []
    for row_number, line in enumerate(content[1:], start=1):
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) != len(_COLUMNS):
            raise MatrixError(
                f"data row {row_number} of {path} holds {len(cells)} cells against "
                f"the 15 verified columns: {line.strip()[:60]}..."
            )
        record = dict(zip(_COLUMNS, cells, strict=True))
        row = MatrixRow(
            pol=record["POL"],
            aircraft=record["AIRCRAFT"],
            description=record["DESCRIPTION"],
            re_millions=float(record["RE"]),
            mach=float(record["MACH"]),
            sweep=_parse_sweep(record["SWEEP_TYPE"], record["SWEEP_VALUES"]),
            ref_code=record["REF"],
            set_code=record["SET"],
            entry_code=record["ENTRY"],
            script_code=record["FS_SCRIPT"],
            fs_build=record["FS_BUILD"],
            hidden=record["HIDDEN"] == "1",
            run=int(record["RUN"]),
            variables=_parse_variables(record["VAR_NAMES_VALUES"]),
        )
        if row.run == 1 or not active_only:
            rows.append(row)
    return rows


def to_campaign(
    path: str | Path,
    *,
    name: str,
    fs_version: str,
    fs_exe: str,
    recipes: Mapping[str, str],
) -> Campaign:
    """Convert a run matrix into a native :class:`Campaign`.

    Parameters
    ----------
    path : str or Path
        Matrix location; only RUN = 1 rows convert.
    name : str
        Campaign name; the matrix has none, so it is explicit input.
    fs_version : str
        FlightStream version, canonical or alias; the FS_BUILD
        column does not identify one, so it is explicit input.
    fs_exe : str
        Explicit executable path (never guessed, SAD Section 5).
    recipes : mapping of str to str
        FS_SCRIPT code to recipe reference (``module:function`` or a
        name registered with the campaign loop); replaces the
        import-by-number system (PP-7, FR-12).

    Returns
    -------
    Campaign
        Native campaign; the matrix codes survive in each case's
        variables (``matrix_ref``, ``matrix_set``, ``matrix_entry``,
        ``matrix_fs_script``, ``matrix_fs_build``, ``matrix_hidden``)
        so the conversion is lossless (FR-11).
    """
    sims = []
    for row in read_matrix(path):
        if row.script_code not in recipes:
            raise MatrixError(
                f"FS_SCRIPT code {row.script_code!r} of POL {row.pol} has no recipe "
                "mapping; the import-by-number system is replaced by explicit recipe "
                "references: map the code with recipes={code: 'package.module:function'} "
                "in Python, or --recipe CODE=package.module:function on the pyfs-matrix "
                "command line"
            )
        variables: dict[str, str | float | int | bool] = dict(row.variables)
        variables.update(
            matrix_ref=row.ref_code,
            matrix_set=row.set_code,
            matrix_entry=row.entry_code,
            matrix_fs_script=row.script_code,
            matrix_fs_build=row.fs_build,
            matrix_hidden=row.hidden,
        )
        sims.append(
            SimCase(
                sim_id=row.pol,
                aircraft=row.aircraft,
                description=row.description,
                reynolds=row.re_millions * 1e6,
                mach=row.mach,
                sweep=row.sweep,
                recipe=recipes[row.script_code],
                variables=variables,
            )
        )
    return Campaign(name=name, fs_version=fs_version, fs_exe=fs_exe, sims=sims)


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def convert_matrix(
    path: str | Path,
    *,
    name: str,
    fs_version: str,
    fs_exe: str,
    recipes: Mapping[str, str],
) -> str:
    """Emit the native ``campaign.toml`` text of a run matrix (FR-11).

    Parameters are those of :func:`to_campaign`. The returned text
    loads back through :func:`pyflightstream.cases.load_campaign`, so
    migration is one call and reversible only in the sense that the
    matrix file itself stays untouched and readable forever (FR-10).
    """
    campaign = to_campaign(path, name=name, fs_version=fs_version, fs_exe=fs_exe, recipes=recipes)
    lines = [
        "[campaign]",
        f"name = {_toml_value(campaign.name)}",
        f"fs_version = {_toml_value(campaign.fs_version)}",
        f"fs_exe = {_toml_value(campaign.fs_exe)}",
    ]
    for sim in campaign.sims:
        lines += [
            "",
            "[[sim]]",
            f"sim_id = {_toml_value(sim.sim_id)}",
            f"aircraft = {_toml_value(sim.aircraft)}",
        ]
        if sim.description:
            lines.append(f"description = {_toml_value(sim.description)}")
        if sim.reynolds is not None:
            lines.append(f"reynolds = {_toml_value(sim.reynolds)}")
        if sim.mach is not None:
            lines.append(f"mach = {_toml_value(sim.mach)}")
        plain_values = [
            list(value) if isinstance(value, tuple) else value for value in sim.sweep.values
        ]
        lines.append(
            f"sweep = {{type = {_toml_value(sim.sweep.type)}, "
            f"values = {_toml_value(plain_values)}}}"
        )
        lines.append(f"recipe = {_toml_value(sim.recipe)}")
        if sim.variables:
            lines.append("[sim.variables]")
            for key, value in sim.variables.items():
                lines.append(f"{_toml_value(key)} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# First-class run path: matrix codes resolved against the workspace
# input library, then planned and executed through the canonical
# campaign form (v0.3 decision 3).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedMatrix:
    """A matrix bound to a workspace input library, ready to plan or run.

    Attributes
    ----------
    campaign : Campaign
        The canonical campaign form, with the resolved reference data
        applied to each case (``reference``) and the solver preset
        applied to each case's runtime settings (``solver``); the
        historical codes stay in the case variables, so nothing of the
        matrix is lost.
    references : dict of str to ReferenceArtifact
        Resolved reference-data artifacts, keyed by REF code.
    setups : dict of str to SetupArtifact
        Resolved solver-setup presets, keyed by SET code; the raw
        preset table is kept verbatim for consumers beyond the runtime
        subset (see :func:`resolve_matrix`).
    groups : dict of str to GroupsArtifact
        Resolved named boundary groups, keyed by ENTRY code; members
        are boundary labels or indices, verbatim, for the script layer
        and the post-processing aggregation.
    fs_exe : Path
        The executable selected through the FS_BUILD column (registry
        mode) or the explicit override; existence is checked by the
        executor at construction, not here.
    """

    campaign: Campaign
    references: dict[str, ReferenceArtifact] = field(default_factory=dict)
    setups: dict[str, SetupArtifact] = field(default_factory=dict)
    groups: dict[str, GroupsArtifact] = field(default_factory=dict)
    fs_exe: Path = Path()


def _resolve_build(
    rows: list[MatrixRow],
    workspace: CampaignWorkspace,
    override: str | Path | None,
    path: str | Path,
) -> Path:
    """Select the executable from the FS_BUILD column or the override.

    The explicit override always wins (it is the only way to run the
    MANUAL mode); registry mode requires the active rows to
    agree on a single build id, because a campaign binds to exactly
    one FlightStream installation.
    """
    from pyflightstream.workspace import InputArtifactError

    if override is not None:
        return Path(override)
    builds = sorted({row.fs_build for row in rows})
    if len(builds) > 1:
        raise MatrixError(
            f"the active rows of {path} name {len(builds)} FS_BUILD values "
            f"({', '.join(builds)}), but a campaign binds to exactly one FlightStream "
            "installation; run the matrix once per build, or pass the explicit fs_exe "
            "override to force a single executable"
        )
    build = builds[0]
    if build.upper() == "MANUAL":
        raise MatrixError(
            "FS_BUILD is MANUAL, the explicit-path mode: pass fs_exe=... "
            "(the explicit override path). MANUAL never reads the build registry, "
            "and the executable is never guessed"
        )
    try:
        return workspace.resolve_executable(build)
    except InputArtifactError as error:
        raise InputArtifactError(
            f"the FS_BUILD column of {path} names build {build!r}, which the "
            "workspace build registry cannot resolve; register it in "
            "inputs/executables.toml, or pass the explicit fs_exe override. "
            f"{error}"
        ) from error


def _resolve_code(workspace: CampaignWorkspace, kind: str, code: str, pol: str):
    """Resolve one REF/SET/ENTRY code, naming the row and the target file."""
    from pyflightstream.workspace import InputArtifactError

    column, subdir, resolver = {
        "reference": ("REF", "references", workspace.resolve_reference),
        "setup": ("SET", "setups", workspace.resolve_setup),
        "group": ("ENTRY", "groups", workspace.resolve_group),
    }[kind]
    try:
        return resolver(code)
    except InputArtifactError as error:
        raise InputArtifactError(
            f"matrix row POL {pol}: the {column} column names {kind} {code!r}, which "
            "the workspace input library cannot resolve; put the artifact at "
            f"inputs/{subdir}/{code}.toml (or fix the matrix code). {error}"
        ) from error


def _solver_from_setup(setup: SetupArtifact, set_code: str) -> SolverSettings:
    """Map the runtime subset of one preset onto the case solver settings.

    Preset keys that name :class:`~pyflightstream.cases.SolverSettings`
    fields apply; the remaining keys stay verbatim in the artifact (a
    warning lists them), awaiting the formal solver-setup model that
    will consume the full table.
    """
    from pyflightstream.workspace import InputArtifactError

    known = set(SolverSettings.model_fields)
    matched = {key: value for key, value in setup.settings.items() if key in known}
    unmatched = sorted(key for key in setup.settings if key not in known)
    if unmatched:
        warnings.warn(
            f"setup preset {set_code!r}: key(s) {', '.join(unmatched)} do not map to "
            "the case solver settings yet and were left to the preset artifact "
            "verbatim; the formal solver-setup model will consume the full table",
            stacklevel=2,
        )
    try:
        return SolverSettings(**matched)
    except ValidationError as error:
        raise InputArtifactError(
            f"setup preset {set_code!r} does not fit the case solver settings: {error}"
        ) from error


def resolve_matrix(
    path: str | Path,
    workspace: CampaignWorkspace,
    *,
    name: str,
    fs_version: str,
    recipes: Mapping[str, str],
    fs_exe: str | Path | None = None,
) -> ResolvedMatrix:
    """Bind a run matrix to the workspace input library.

    The matrix converts through the canonical campaign form
    (:func:`to_campaign`) and its reference columns resolve against
    the library under ``inputs/``: REF to reference data (applied to
    each case's ``reference``), SET to a solver preset (its runtime
    subset applied to each case's ``solver``), ENTRY to named boundary
    groups (returned verbatim), and FS_BUILD to an executable through
    the build registry. A missing artifact fails with a didactic error
    naming the row, the missing id, and the ``inputs/`` file to create;
    plain conversion (:func:`convert_matrix`) never needs the library.

    Parameters
    ----------
    path : str or Path
        Matrix location; only RUN = 1 rows resolve.
    workspace : CampaignWorkspace
        The managed campaign root carrying the input library.
    name : str
        Campaign name; the matrix has none, so it is explicit input.
    fs_version : str
        FlightStream version, canonical or alias; the FS_BUILD column
        selects an executable, not a command-database version, so the
        version stays explicit input.
    recipes : mapping of str to str
        FS_SCRIPT code to recipe reference, as in :func:`to_campaign`.
    fs_exe : str or Path, optional
        Explicit executable override; it always wins over the build
        registry and is the only way to run the MANUAL mode.

    Returns
    -------
    ResolvedMatrix
        The campaign with resolved artifacts applied, the artifacts
        themselves keyed by their codes, and the selected executable.

    Raises
    ------
    MatrixError
        Layout deviations, no active row, mixed FS_BUILD values, or
        MANUAL mode without the explicit override.
    pyflightstream.workspace.InputArtifactError
        A code the library cannot resolve, or a preset that does not
        fit the case solver settings.
    """
    rows = read_matrix(path)
    if not rows:
        raise MatrixError(f"{path} has no active rows (RUN = 1); nothing to resolve or run")
    exe = _resolve_build(rows, workspace, override=fs_exe, path=path)
    campaign = to_campaign(path, name=name, fs_version=fs_version, fs_exe=str(exe), recipes=recipes)
    references: dict[str, ReferenceArtifact] = {}
    setups: dict[str, SetupArtifact] = {}
    groups: dict[str, GroupsArtifact] = {}
    solvers: dict[str, SolverSettings] = {}
    for row in rows:
        if row.ref_code not in references:
            references[row.ref_code] = _resolve_code(workspace, "reference", row.ref_code, row.pol)
        if row.set_code not in setups:
            setups[row.set_code] = _resolve_code(workspace, "setup", row.set_code, row.pol)
            solvers[row.set_code] = _solver_from_setup(setups[row.set_code], row.set_code)
        if row.entry_code not in groups:
            groups[row.entry_code] = _resolve_code(workspace, "group", row.entry_code, row.pol)
    sims: list[SimCase] = []
    for case, row in zip(campaign.sims, rows, strict=True):
        reference = references[row.ref_code]
        sims.append(
            case.model_copy(
                update={
                    "reference": ReferenceData(area=reference.area_m2, length=reference.chord_m),
                    "solver": solvers[row.set_code],
                }
            )
        )
    return ResolvedMatrix(
        campaign=campaign.model_copy(update={"sims": sims}),
        references=references,
        setups=setups,
        groups=groups,
        fs_exe=exe,
    )


def plan_matrix(
    path: str | Path,
    workspace: CampaignWorkspace,
    *,
    name: str,
    fs_version: str,
    recipes: Mapping[str, str],
    fs_exe: str | Path | None = None,
    recipe_registry: dict[str, ScriptRecipe] | None = None,
    write_plan: bool = True,
) -> CampaignPlan:
    """Pre-flight a run matrix without executing anything.

    Resolution (:func:`resolve_matrix`) plus the campaign pre-flight
    (:func:`pyflightstream.run.plan_campaign`): every recipe resolves,
    every script builds in dry run, and points already in the manifest
    are marked ALREADY_RECORDED, exactly what
    ``run_matrix(..., resume=True)`` would skip.

    Parameters
    ----------
    path, workspace, name, fs_version, recipes, fs_exe
        As in :func:`resolve_matrix`.
    recipe_registry : dict of str to ScriptRecipe, optional
        Named recipe registry (name to callable) consulted before
        treating a recipe reference as ``module:function``, forwarded
        to the campaign pre-flight.
    write_plan : bool
        Write the JSON summary as ``plan.json`` in the campaign root
        (default True), as in the campaign pre-flight.

    Returns
    -------
    pyflightstream.run.CampaignPlan
        One status per matrix point; inspect ``blocked`` before
        running, or print ``summary()``.
    """
    from pyflightstream.run import plan_campaign

    resolved = resolve_matrix(
        path, workspace, name=name, fs_version=fs_version, recipes=recipes, fs_exe=fs_exe
    )
    return plan_campaign(
        resolved.campaign, workspace, recipes=recipe_registry, write_plan=write_plan
    )


def run_matrix(
    path: str | Path,
    workspace: CampaignWorkspace,
    *,
    name: str,
    fs_version: str,
    recipes: Mapping[str, str],
    assess: OutcomeAssessor,
    fs_exe: str | Path | None = None,
    executor: Executor | None = None,
    recipe_registry: dict[str, ScriptRecipe] | None = None,
    resume: bool = False,
    hidden: bool = True,
) -> list[RunRecord]:
    """Read a run matrix and run it: the one-call first-class entry.

    In order: the matrix converts through the canonical campaign form,
    its codes resolve against the workspace input library
    (:func:`resolve_matrix`), the whole campaign pre-flights in dry
    run, and only then the points execute through
    :func:`pyflightstream.run.run_campaign`, landing one manifest
    record per point. A blocked pre-flight refuses to execute at all,
    so a broken recipe or missing artifact costs no solver time.

    Parameters
    ----------
    path, workspace, name, fs_version, recipes, fs_exe
        As in :func:`resolve_matrix`; the executable comes from the
        FS_BUILD column through the build registry, or from the
        explicit ``fs_exe`` override (mandatory for MANUAL rows).
    assess : pyflightstream.run.OutcomeAssessor
        Solver-quality judgment, for example
        :class:`pyflightstream.run.LoadsAssessor`; required because
        the loop refuses to invent convergence evidence.
    executor : pyflightstream.run.Executor, optional
        Replacement executor; by default a
        :class:`pyflightstream.run.LocalExecutor` is built from the
        resolved executable.
    recipe_registry : dict of str to ScriptRecipe, optional
        Named recipe registry (name to callable), forwarded to the
        pre-flight and the campaign loop.
    resume : bool
        With True, points already in the manifest are skipped, so a
        grown matrix re-runs only its new points; with False (the
        default) an already-recorded point raises before anything
        executes, as in :func:`pyflightstream.run.run_campaign`.
    hidden : bool
        Windowless solver runs (default True); forwarded to the
        default executor only.

    Returns
    -------
    list of pyflightstream.workspace.RunRecord
        The records executed by this call, in execution order.

    Raises
    ------
    MatrixError
        Layout or build-selection problems, or a blocked pre-flight
        (the message carries the plan summary; nothing was executed).
    pyflightstream.run.CampaignErrors
        After the loop, when at least one executed point failed.
    """
    from pyflightstream.run import LocalExecutor, plan_campaign, run_campaign

    resolved = resolve_matrix(
        path, workspace, name=name, fs_version=fs_version, recipes=recipes, fs_exe=fs_exe
    )
    plan = plan_campaign(resolved.campaign, workspace, recipes=recipe_registry)
    if plan.blocked:
        raise MatrixError(
            f"pre-flight blocked {len(plan.blocked)} matrix point(s); nothing was "
            f"executed:\n{plan.summary()}"
        )
    if executor is None:
        executor = LocalExecutor(resolved.fs_exe, hidden=hidden)
    return run_campaign(
        resolved.campaign,
        executor,
        workspace,
        assess=assess,
        recipes=recipe_registry,
        resume=resume,
    )
