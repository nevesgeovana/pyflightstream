"""Pipe-delimited run matrix: the reader and the converter.

Pipeline role: keeps the established run-matrix workflow working
unchanged, forever (BRF-08), and promotes the matrix to a first-class
interface of the file-managed modality (v0.3 decision): reading a
matrix and running it is one call,
:func:`pyflightstream.run.matrix.run_matrix`, with the native
``campaign.toml`` model staying the canonical internal form, so
nothing changes for campaign.toml users. The verified layout is read as
is: POL, AIRCRAFT, DESCRIPTION, RE, MACH, SWEEP_TYPE,
SWEEP_VALUES, REF, SET, ENTRY, FS_SCRIPT, FS_BUILD, HIDDEN, RUN,
WORKFLOW, VAR_NAMES_VALUES. Rows with RUN = 1 are active. SWEEP_TYPE names its
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

WHAT THIS MODULE DOES NOT DO, and where the rest went. The run path
needs the layer ABOVE this one: binding REF, SET, ENTRY and FS_BUILD to
the workspace input library, then planning and executing. Both halves
used to live here and paid for it with imports written inside the
function bodies, which recorded an upward dependency while hiding it
from every module-level reader. They moved on 2026-08-19 (OPS-2007.01,
PFS-2009.05): :class:`pyflightstream.workspace.matrix.ResolvedMatrix`
and :func:`pyflightstream.workspace.matrix.resolve_matrix` do the
binding, and :func:`pyflightstream.run.matrix.plan_matrix` and
:func:`pyflightstream.run.matrix.run_matrix` do the pre-flight and the
execution. Nothing about the format, the flags or the records moved
with them, and the ``pyfs-matrix`` command line kept its name.

THE LAYOUT GREW BY ONE COLUMN on 2026-08-19 and that is a BREAK, taken
deliberately for 0.8.0 (PFS-2025.01, PFS-2025.12). ``WORKFLOW`` names
the workflow type a row asks for. It is a column of its own rather than
a pair inside ``VAR_NAMES_VALUES``, because that cell is where the free
CASE DATA lives and a type competing with it would be indistinguishable
from a user's own key. A file written at the preceding width is not
merely unparsable: :func:`read_matrix` RECOGNISES it and refuses it
naming :func:`upgrade_matrix`, which inserts the one cell and leaves
every other byte of the file alone.

What is left here imports nothing above the cases layer, at any level,
which is what :mod:`tests.test_conventions` now holds it to.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import Campaign, SimCase, SweepAxis

# SAME LAYER, so this is a sideways import and not an upward one: both
# modules are `pyflightstream.cases`, and the layer rule
# (`tests.test_conventions`) is about direction. The reader asks the
# registry which types exist rather than keeping a second list, because a
# second list is how a value gets refused for naming a workflow that was
# registered last week.
from pyflightstream.cases.workflows import workflow_names

__all__ = [
    "LEGACY_WORKFLOW",
    "MatrixError",
    "MatrixRow",
    "convert_matrix",
    "read_matrix",
    "to_campaign",
    "upgrade_matrix",
    "workflow_types",
]

#: The verified layout, in file order. ``WORKFLOW`` sits at index 14, in
#: front of ``VAR_NAMES_VALUES`` rather than after it, and the position
#: is stated rather than appended: ``VAR_NAMES_VALUES`` is the only cell
#: whose content is free and whose width is not fixed by the format, so
#: it stays last and every fixed-width column stays in front of it.
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
    "WORKFLOW",
    "VAR_NAMES_VALUES",
)

#: The width that preceded ``WORKFLOW``, frozen so a file written under
#: it is RECOGNISED and refused with the command that fixes it instead of
#: meeting the generic "this is not a run matrix" message. It is only
#: ever COMPARED: no row is ever read through it, so the reader keeps its
#: single-grammar property and gains no tolerant second path.
_LEGACY_COLUMNS_15 = tuple(name for name in _COLUMNS if name != "WORKFLOW")

#: The workflow every row written before the column existed asks for:
#: the established matrix behaviour, whose builder is the user's own
#: recipe. It is deliberately NOT a registered workflow; it means "no
#: workflow", which is what keeps every matrix written before v0.8.0
#: running exactly as it always ran. Spelled here as well as in
#: :mod:`pyflightstream.cases.workflows` because the two modules meet
#: only through the file format, and neither owns the other's constant.
LEGACY_WORKFLOW = "LEGACY"

_SWEEP_CODES = {"AL": "alpha", "BE": "beta"}

#: The two rotation keys of ``VAR_NAMES_VALUES`` this reader knows about:
#: one fixed offset, one geometric sweep. Their spelling belongs to
#: PFS-2025.14, so both are matched CASE-INSENSITIVELY and neither is
#: interpreted here beyond counting the values a sweep asks for.
_ROTATION_OFFSET_KEY = "angle_deg"
_ROTATION_SWEEP_KEY = "angle_sweep_deg"


class MatrixError(PyflightstreamError, ValueError):
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
    workflow : str
        WORKFLOW column, the workflow type the row asks for; one of
        :data:`WORKFLOW_TYPES`, checked when the row is read.
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
    workflow: str
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


def workflow_types() -> tuple[str, ...]:
    """Every value a ``WORKFLOW`` cell may name.

    :data:`LEGACY_WORKFLOW` first, then the registered workflow names in
    the order :func:`pyflightstream.cases.workflows.workflow_names`
    gives them. It is READ from the registry at call time rather than
    frozen here, so a workflow registered tomorrow is accepted by this
    reader the same day and no second list can disagree with the table.

    Returns
    -------
    tuple of str
        The accepted values, in the order the refusal lists them.

    Examples
    --------
    >>> from pyflightstream.cases.matrix import workflow_types
    >>> workflow_types()[0]
    'LEGACY'
    """
    return (LEGACY_WORKFLOW, *workflow_names())


def _check_workflow(value: str, pol: str) -> str:
    """Refuse a WORKFLOW cell naming no registered workflow type."""
    known = workflow_types()
    if value not in known:
        raise MatrixError(
            f"WORKFLOW value {value!r} of POL {pol} names no known workflow type; the "
            f"registered types are {', '.join(known)}. The column names WHICH "
            "workflow builds the row's script, so an unrecognised value would run the "
            f"wrong one silently; a row that wants the established behaviour, built by "
            f"the recipe its FS_SCRIPT code names, writes {LEGACY_WORKFLOW}."
        )
    return value


def _rotation_values(variables: dict[str, str], key: str) -> list[str] | None:
    """Return the comma-separated values of one rotation key, or None.

    The key is matched case-insensitively: its spelling is PFS-2025.14's
    to settle, and a refusal that fires only for one casing is a refusal
    a user gets past by shouting.
    """
    for name, value in variables.items():
        if name.strip().lower() == key:
            return [token.strip() for token in value.split(",") if token.strip()]
    return None


def _check_one_sweep_per_row(pol: str, sweep: SweepAxis, variables: dict[str, str]) -> None:
    """Refuse a row asking for an aerodynamic AND a geometric sweep.

    The two multiply: a three-point alpha sweep beside a three-angle
    rotation sweep is nine runs the row never asked for, and neither
    axis names the other in the point identifier. The refusal names the
    fixed-offset form, because the user asking for both almost always
    wants one rotation held fixed across an alpha sweep, which is what
    ``angle_deg`` already does.
    """
    rotation = _rotation_values(variables, _ROTATION_SWEEP_KEY)
    if rotation is None or len(rotation) < 2 or len(sweep.values) < 2:
        return
    raise MatrixError(
        f"POL {pol} asks for two sweeps at once: the SWEEP_TYPE {sweep.type} sweep of "
        f"{len(sweep.values)} points and the geometric sweep "
        f"{_ROTATION_SWEEP_KEY}: {','.join(rotation)} of {len(rotation)} angles. The "
        "two would multiply into a grid this row does not name and whose points cannot "
        "be told apart. A rotation held FIXED across an aerodynamic sweep is written "
        f"{_ROTATION_OFFSET_KEY}: <angle>, one value; a sweep OF the rotation is a row "
        "of its own with a single-point SWEEP_VALUES."
    )


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
    if header == _LEGACY_COLUMNS_15:
        raise MatrixError(
            f"{path} carries the {len(_LEGACY_COLUMNS_15)}-column layout that preceded "
            f"the WORKFLOW column, so it is a run matrix written before v0.8.0 rather "
            "than a file this reader cannot recognise. Upgrade it with "
            "pyflightstream.cases.matrix.upgrade_matrix(path, in_place=True), which "
            f"inserts one {LEGACY_WORKFLOW!r} cell per row and leaves every other "
            "byte, separator and line ending of the file exactly as it is."
        )
    if header != _COLUMNS:
        raise MatrixError(
            f"{path} header does not match the verified {len(_COLUMNS)}-column layout; "
            f"expected {', '.join(_COLUMNS)} and found {', '.join(header)}"
        )
    rows: list[MatrixRow] = []
    for row_number, line in enumerate(content[1:], start=1):
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) != len(_COLUMNS):
            raise MatrixError(
                f"data row {row_number} of {path} holds {len(cells)} cells against "
                f"the {len(_COLUMNS)} verified columns: {line.strip()[:60]}..."
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
            workflow=_check_workflow(record["WORKFLOW"], record["POL"]),
            variables=_parse_variables(record["VAR_NAMES_VALUES"]),
        )
        # Every row is checked, active or not: the sweep codes and the
        # variable grammar already are, and a refusal a user only meets
        # after flipping RUN to 1 is a refusal that waited.
        _check_one_sweep_per_row(row.pol, row.sweep, row.variables)
        if row.run == 1 or not active_only:
            rows.append(row)
    return rows


def _peel_terminator(line: bytes) -> tuple[bytes, bytes]:
    """Split one line into its body and its line terminator."""
    for terminator in (b"\r\n", b"\n", b"\r"):
        if line.endswith(terminator):
            return line[: -len(terminator)], terminator
    return line, b""


def _upgraded_bytes(data: bytes, source: str) -> bytes:
    """Insert the WORKFLOW cell into a fifteen-column matrix, byte-wise.

    Works on BYTES and never through :func:`read_matrix`, which replaces
    undecodable bytes, drops the dashed rule and strips every cell: a
    converter built on it would hand back a file the user cannot diff
    against the one they had.
    """
    index = _COLUMNS.index("WORKFLOW")
    last = index == len(_COLUMNS) - 1
    rebuilt: list[bytes] = []
    header_seen = False
    row_number = 0
    for line in data.splitlines(keepends=True):
        body, terminator = _peel_terminator(line)
        if b"|" not in body:
            # The dashed rule, and any blank line. Neither carries a cell,
            # so neither is touched.
            rebuilt.append(line)
            continue
        parts = body.split(b"|")
        if not header_seen:
            header_seen = True
            names = tuple(cell.strip().decode("utf-8", "replace") for cell in parts)
            if names == _COLUMNS:
                return data
            if names != _LEGACY_COLUMNS_15:
                raise MatrixError(
                    f"{source} is not a run matrix at the layout this converter "
                    f"upgrades: its header names {', '.join(names)}, and the "
                    f"{len(_LEGACY_COLUMNS_15)}-column layout that gains the WORKFLOW "
                    f"column names {', '.join(_LEGACY_COLUMNS_15)}."
                )
            cell = _COLUMNS[index].encode("utf-8")
        else:
            row_number += 1
            if len(parts) != len(_LEGACY_COLUMNS_15):
                raise MatrixError(
                    f"data row {row_number} of {source} holds {len(parts)} cells "
                    f"against the {len(_LEGACY_COLUMNS_15)} columns of the layout "
                    "being upgraded, so this converter cannot say which cell the "
                    "WORKFLOW value would sit beside; repair the row first."
                )
            cell = LEGACY_WORKFLOW.encode("utf-8")
        # One leading space always, one trailing space unless the new cell
        # is last: a trailing space at end of line is what the repository's
        # own pre-commit hook strips out from under a committed fixture.
        parts.insert(index, b" " + cell + (b"" if last else b" "))
        rebuilt.append(b"|".join(parts) + terminator)
    if not header_seen:
        raise MatrixError(f"{source} holds no matrix content: no line carries a cell separator")
    return b"".join(rebuilt)


def upgrade_matrix(path: str | Path, *, in_place: bool = False) -> bytes:
    """Add the WORKFLOW column to a matrix written before it existed.

    Every other cell, separator, comment rule and line ending survives
    byte for byte, so the diff a user reviews holds exactly one changed
    thing per line. The value written into each data row is
    :data:`LEGACY_WORKFLOW`, which names the behaviour those rows already
    have; the header receives the column LABEL, so the result is a file
    :func:`read_matrix` accepts rather than one that merely has the right
    number of cells.

    Parameters
    ----------
    path : str or Path
        The matrix to upgrade. It is read as bytes and is not decoded.
    in_place : bool
        Write the upgraded bytes back over ``path``. Keyword-only, and
        False by default, so nothing is rewritten unless it is asked
        for; a caller wanting a different destination writes the
        returned bytes there.

    Returns
    -------
    bytes
        The upgraded file content. A matrix already carrying the column
        is returned unchanged, so running this twice is safe.

    Raises
    ------
    MatrixError
        The header names neither layout, a data row holds the wrong
        number of cells, or no line carries a cell separator.

    Examples
    --------
    >>> from pyflightstream.cases.matrix import upgrade_matrix
    >>> upgrade_matrix("matrix.fs", in_place=True)  # doctest: +SKIP
    """
    target = Path(path)
    upgraded = _upgraded_bytes(target.read_bytes(), str(target))
    if in_place:
        target.write_bytes(upgraded)
    return upgraded


#: Matrix variable naming the files a row's recipe exports, several
#: separated by commas. NOT by the slash: the slash already separates
#: the KEY:VALUE pairs of VAR_NAMES_VALUES, so a slash inside a value
#: splits the variable itself. Comma is what SWEEP_VALUES already uses
#: to separate values within one group.
OUTPUTS_VARIABLE = "OUTPUTS"


def _declared_outputs(row: MatrixRow, *, required: bool = True) -> list[str]:
    """Return the outputs a matrix row declares, refusing a row with none.

    A campaign collects the outputs the case DECLARES: the recipe
    exports ``case.outputs[i]`` and the loop copies exactly those files
    into the run folder. `to_campaign` never set the field, so every
    matrix-driven case carried the empty default, and therefore no
    matrix-driven run has ever collected anything. With the standard
    :class:`~pyflightstream.run.LoadsAssessor`, which is what the README
    and the guides tell a user to pass, the point lands
    ``FAILED_INCOMPLETE_OUTPUT`` with "collected: nothing" AFTER the
    solver has run.

    Measured 2026-08-03 on the author's own research campaign: a
    thirty-minute unsteady run completed, the solver wrote all eight
    expected files into the run folder, and the point was recorded as a
    failure with the files sitting beside it. The physics was fine and
    the bookkeeping threw it away.

    It stayed invisible because the one end-to-end matrix test passes a
    stub assessor that returns CONVERGED without reading a file, so
    nothing in tier 1 ever exercised collection through this path.

    Refusing a row that declares nothing is deliberate, and it is the
    half that matters: a silent empty list spends solver time before
    failing, while a refusal costs nothing and names the remedy.

    Parameters
    ----------
    row : MatrixRow
        One active row.

    Returns
    -------
    list of str
        The declared output file names, in the order written.

    Raises
    ------
    MatrixError
        If the row declares no outputs AND ``required`` is True.
    """
    raw = row.variables.get(OUTPUTS_VARIABLE, "").strip()
    outputs = [part.strip() for part in raw.split(",") if part.strip()]
    if not outputs and not required:
        # Conversion is a translation and spends no solver time, so it
        # carries whatever the row declares, including nothing. FR-10
        # scopes "forever" to the external format, which is the promise
        # about the author's existing files, and FR-11 calls conversion
        # lossless; refusing here broke the one path off the legacy
        # matrix, since every matrix written before this variable
        # existed declares none. The refusal lives on the paths that
        # are about to start a solver (architect and API-designer
        # passes, 2026-08-03).
        return []
    if not outputs:
        raise MatrixError(
            f"POL {row.pol} declares no outputs, so a run of it would collect nothing "
            "and be recorded FAILED_INCOMPLETE_OUTPUT after the solver had already "
            f"spent its time. Add the files the recipe exports to the row's variables "
            f"as {OUTPUTS_VARIABLE}, several separated by commas, for example "
            f"'{OUTPUTS_VARIABLE}: loads_{{point}}.txt, loads_cp_{{point}}.txt'. The "
            "point placeholder is what keeps a swept row's points from "
            "overwriting each other in the one simulation folder they share; "
            "without it the campaign is refused again, later, for that. The "
            "names must be the "
            "ones the recipe passes to its EXPORT commands, which the managed "
            "protocol reads from case.outputs."
        )
    return outputs


def to_campaign(
    path: str | Path,
    *,
    name: str,
    fs_version: str,
    fs_exe: str,
    recipes: Mapping[str, str],
    require_outputs: bool = True,
) -> Campaign:
    """Convert a run matrix into a native :class:`Campaign`.

    Parameters
    ----------
    path : str or Path
        Matrix location; only RUN = 1 rows convert.
    name : str
        Campaign name; the matrix has none, so it is explicit input.
    fs_version : str
        FlightStream version, canonical identifier (26.120); a vendor
        release name works only where it names exactly one registered
        build. The FS_BUILD
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
        ``matrix_fs_script``, ``matrix_fs_build``, ``matrix_hidden``,
        ``matrix_workflow``) so the conversion is lossless (FR-11).
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
            # THE WORKFLOW BELONGS ON THE CASE, as a declared field beside
            # `recipe`, and it is carried here instead because `SimCase` is
            # `extra="forbid"` and adding the field is an edit to
            # `cases/__init__.py`, which this change does not own
            # (PFS-2025.01). The reserved `matrix_` namespace is written by
            # this converter and never by a user's VAR_NAMES_VALUES cell, so
            # the value cannot be shadowed by case data, and the conversion
            # stays lossless (FR-11) meanwhile. When the declared field
            # lands, pass `workflow=row.workflow` and drop this key.
            matrix_workflow=row.workflow,
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
                outputs=_declared_outputs(row, required=require_outputs),
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
    # require_outputs=False: this is the migration tool. A row that
    # declares none converts to a sim that declares none, and the
    # warning below names the rows, so the author's existing matrices
    # keep converting (FR-10, FR-11) and learn what to add.
    campaign = to_campaign(
        path,
        name=name,
        fs_version=fs_version,
        fs_exe=fs_exe,
        recipes=recipes,
        require_outputs=False,
    )
    undeclared = [sim.sim_id for sim in campaign.sims if not sim.outputs]
    if undeclared:
        warnings.warn(
            f"{len(undeclared)} converted sim(s) declare no outputs "
            f"({', '.join(undeclared)}). The conversion is complete and lossless: the "
            f"matrix rows carry no {OUTPUTS_VARIABLE} variable, so the campaign carries "
            "no outputs either. Add them before running, either in the matrix as "
            f"'{OUTPUTS_VARIABLE}: loads_{{point}}.txt' or in the campaign file as "
            "outputs = [...], naming the files the recipe exports. Running a case that "
            "declares none collects nothing and records the point "
            "FAILED_INCOMPLETE_OUTPUT after the solver has already spent its time.",
            UserWarning,
            stacklevel=2,
        )
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
        # FR-11 says the conversion is lossless, and the outputs are part
        # of what the row declares now, so they have to survive it. Before
        # 2026-08-03 there was nothing here to lose: every converted case
        # carried the empty default.
        if sim.outputs:
            lines.append(f"outputs = {_toml_value(list(sim.outputs))}")
        if sim.variables:
            lines.append("[sim.variables]")
            for key, value in sim.variables.items():
                lines.append(f"{_toml_value(key)} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"
