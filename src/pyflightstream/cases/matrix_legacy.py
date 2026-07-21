"""Reader for the legacy pipe-delimited run matrix (FR-10, FR-11).

Pipeline role: keeps the predecessor run-matrix workflow working
unchanged, forever (BRF-08). The verified 15-column layout is read as
is: POL, AIRCRAFT, DESCRIPTION, RE, MACH, SWEEP_TYPE, SWEEP_VALUES,
REF, SET, ENTRY, FS_SCRIPT, FS_BUILD, HIDDEN, RUN, VAR_NAMES_VALUES.
Rows with RUN = 1 are active. SWEEP_TYPE names its axes separated by
``/`` (verified codes: ``AL`` for alpha, ``BE`` for beta) and
SWEEP_VALUES carries one comma-separated value list per axis, also
``/``-separated; the legacy workflow varies one axis while the other
holds a single value, which broadcasts here. VAR_NAMES_VALUES holds
``/``-separated ``KEY:VALUE`` pairs, values may contain spaces.

The historical 3-digit codes (REF, SET, ENTRY, FS_SCRIPT) were
resolved to files by number at run time; that import-by-number system
is replaced (PP-7, FR-12): :func:`to_campaign` maps the FS_SCRIPT
code to a registered recipe name through an explicit mapping and
preserves all four codes in the case variables, so the conversion is
lossless. :func:`convert_matrix` (FR-11) emits the native
``campaign.toml`` equivalent; RE is stored in millions in the matrix
and converts to an absolute Reynolds number.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pyflightstream.cases import Campaign, SimCase, SweepAxis

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


class LegacyMatrixError(ValueError):
    """A legacy matrix file does not match the verified layout.

    The reader supports exactly the verified format (FR-10); a
    deviation means the file is not a predecessor run matrix or was
    edited beyond what the legacy workflow produced.
    """


@dataclass(frozen=True)
class LegacyRow:
    """One parsed row of the legacy run matrix.

    Attributes
    ----------
    pol : str
        Legacy polar identifier; maps to the native ``sim_id``.
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
        Legacy build column, kept verbatim.
    hidden : bool
        Legacy hidden-mode flag.
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
        raise LegacyMatrixError(
            f"SWEEP_TYPE code(s) {', '.join(unknown)} are not among the verified legacy "
            f"codes ({', '.join(sorted(_SWEEP_CODES))}); extending the mapping needs "
            "evidence from a legacy matrix that uses the code"
        )
    if len(axes) != len(groups):
        raise LegacyMatrixError(
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
            raise LegacyMatrixError(
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
            raise LegacyMatrixError(
                f"variable {pair.strip()!r} is not a KEY:VALUE pair; VAR_NAMES_VALUES "
                "holds '/'-separated KEY:VALUE entries"
            )
        variables[name.strip()] = value.strip()
    return variables


def read_matrix(path: str | Path, active_only: bool = True) -> list[LegacyRow]:
    """Read a legacy ``matriz.fs`` run matrix.

    Parameters
    ----------
    path : str or Path
        Matrix file location.
    active_only : bool
        Keep only rows with RUN = 1, the legacy activity filter;
        False returns every row.

    Returns
    -------
    list of LegacyRow
        Parsed rows in file order.
    """
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    content = [line for line in lines if line.strip() and not set(line.strip()) <= {"-"}]
    if not content:
        raise LegacyMatrixError(f"{path} holds no matrix content")
    header = tuple(cell.strip() for cell in content[0].split("|"))
    if header != _COLUMNS:
        raise LegacyMatrixError(
            f"{path} header does not match the verified 15-column layout; expected "
            f"{', '.join(_COLUMNS)} and found {', '.join(header)}"
        )
    rows: list[LegacyRow] = []
    for line in content[1:]:
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) != len(_COLUMNS):
            raise LegacyMatrixError(
                f"matrix row holds {len(cells)} cells against the 15 verified columns: "
                f"{line.strip()[:60]}..."
            )
        record = dict(zip(_COLUMNS, cells, strict=True))
        row = LegacyRow(
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
    """Convert a legacy matrix into a native :class:`Campaign`.

    Parameters
    ----------
    path : str or Path
        Legacy matrix location; only RUN = 1 rows convert.
    name : str
        Campaign name; the matrix has none, so it is explicit input.
    fs_version : str
        FlightStream version, canonical or alias; the legacy FS_BUILD
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
        Native campaign; the historical codes survive in each case's
        variables (``legacy_ref``, ``legacy_set``, ``legacy_entry``,
        ``legacy_fs_script``, ``legacy_fs_build``, ``legacy_hidden``)
        so the conversion is lossless (FR-11).
    """
    sims = []
    for row in read_matrix(path):
        if row.script_code not in recipes:
            raise LegacyMatrixError(
                f"FS_SCRIPT code {row.script_code!r} of POL {row.pol} has no recipe "
                "mapping; the import-by-number system is replaced by explicit recipe "
                "references, so pass recipes={code: 'package.module:function'}"
            )
        variables: dict[str, str | float | int | bool] = dict(row.variables)
        variables.update(
            legacy_ref=row.ref_code,
            legacy_set=row.set_code,
            legacy_entry=row.entry_code,
            legacy_fs_script=row.script_code,
            legacy_fs_build=row.fs_build,
            legacy_hidden=row.hidden,
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
    """Emit the native ``campaign.toml`` text of a legacy matrix (FR-11).

    Parameters are those of :func:`to_campaign`. The returned text
    loads back through :func:`pyflightstream.cases.load_campaign`, so
    migration is one call and reversible only in the sense that the
    legacy file itself stays untouched and readable forever (FR-10).
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
