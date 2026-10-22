"""What the products stage and the series tables share: the CSV writer and reader, the errors.

A private module below :mod:`pyflightstream.post.products` and
:mod:`pyflightstream.post.series`, so both import downward and neither
imports the other (the architecture lens of REL-0140 found the two
importing each other, one direction hidden inside a function).
:mod:`pyflightstream.post.products` re-exports every public name here,
which is where a reader finds them.

The post's one CSV reader (AD-10), :func:`read_csv_table`, and
the plots-table readers (:func:`plots_table_series` and the step clock it
reads) are defined here too, so :mod:`pyflightstream.post.corrections`, which
:mod:`pyflightstream.post.products` imports, reads a table without importing
that module back. So is the plots history (FR-96) of a continued
point over its whole march (:func:`_march_history`), which the products stage
reads through :func:`_march_records` and :func:`_march_plots_text` and does not
re-export.
"""

from __future__ import annotations

import csv
import math
import re
import weakref
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

import pyflightstream._textio as _textio

# RE-EXPORTED, not used here. `post.products` imports both from this module,
# which is what its own docstring promises a reader, and they are DEFINED in
# `_errors` so callers can catch them without importing the post layer.
from pyflightstream._errors import ProductError as ProductError
from pyflightstream._errors import ProductExistsError as ProductExistsError
from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream._tokens import ADVANCE_RATIO_COLUMN as ADVANCE_RATIO_COLUMN
from pyflightstream._tokens import CONTEXT_COLUMNS as CONTEXT_COLUMNS
from pyflightstream._tokens import FLIGHT_CONDITION_COLUMNS as FLIGHT_CONDITION_COLUMNS
from pyflightstream._tokens import NOT_APPLICABLE as NOT_APPLICABLE

# DEPENDENCIES, NOT RE-EXPORTS (G16): the sections table's first column, and the
# rule every cell is written by. The products take them from the floor themselves.
from pyflightstream._tokens import POLAR_ID_COLUMN, plain_cell
from pyflightstream._tokens import REFERENCE_LENGTH_COLUMNS as REFERENCE_LENGTH_COLUMNS
from pyflightstream.cases import classify_outputs
from pyflightstream.cases.windows import march_end
from pyflightstream.post.axes import blade_azimuth_deg, placed_blade_azimuth_deg
from pyflightstream.post.unsteady import TimestepSeries
from pyflightstream.results import labeled_value, parse_unsteady_plots
from pyflightstream.workspace import CampaignWorkspace, RunRecord
from pyflightstream.workspace.naming import ARCHIVE_DIR, ARCHIVE_STAMP

#: Recorded spellings mapped to product columns. context_row folds case
#: only, so cell keys with units and export-header labels need aliases.
#: Every alias preserves units: ALTFT and ALT are feet, TASmps and VINF
#: are m/s. Unit conversion belongs in point_condition, not an alias.
#: Absolute reynolds is deliberately absent: RE is in millions. Producers
#: must convert absolute Reynolds numbers before passing the RE column.
CONDITION_KEY_ALIASES: dict[str, str] = {
    # The sweep point and the matrix cell, which spell one quantity two ways.
    "advance_ratio": ADVANCE_RATIO_COLUMN,
    "tasmps": "VINF",
    "altft": "ALT",
    # What the loads export REPORTS, which is what the solver says it ran at
    # rather than what the matrix asked for. A product should carry this one:
    # the two differ exactly when something went wrong, which is the case a
    # reader most needs to see.
    "angle_of_attack_deg": "ALPHA",
    "sideslip_deg": "BETA",
    "freestream_velocity_m_s": "VINF",
    "altitude_ft": "ALT",
    # The export's reference velocity, recorded air and directly pinned air
    # keys. Units agree in each pair: m/s, kg/m3, K and Pa s.
    "reference_velocity_m_s": "VREF",
    "density_kg_m3": "RHO",
    "temperature_k": "TEMP",
    "viscosity_pa_s": "MU",
    "rhokgm3": "RHO",
    "tk": "TEMP",
    "mupas": "MU",
}


def context_row(
    condition: Mapping[str, object] | None = None,
    reference: Mapping[str, object] | None = None,
    *,
    columns: Sequence[str] = CONTEXT_COLUMNS,
) -> tuple[object, ...]:
    """Return the values of ``columns``, read from what the run recorded.

    ONE ASSEMBLY FOR EVERY PRODUCT FAMILY, keeping their condition columns
    consistent instead of constructing a separate subset at each call site.

    A key the run did not record is NOT invented and is not left blank: it
    arrives at the funnel as ``None`` and is written as ``NA``, which says the
    column does not apply to that row. That is the third of the three reasons a
    cell can be empty and the only one `NA` stands for -- so a condition the
    solver was never told is visibly absent rather than quietly zero, and a
    zero angle of attack stays a zero.

    The lookup is CASE-INSENSITIVE on purpose: a record writes ``alpha`` and a
    column is ``ALPHA``, and requiring the two to agree makes every caller
    remember a convention that this function can simply apply.

    Parameters
    ----------
    condition : mapping of str to object, optional
        The point's recorded condition.
    reference : mapping of str to object, optional
        The point's recorded reference dimensions.
    columns : sequence of str, optional
        The columns to read, :data:`CONTEXT_COLUMNS` by default.

    Returns
    -------
    tuple of object
        One value per column, looked up without regard to case in the condition and the reference;
        None where the run recorded none.
    """
    folded: dict[str, object] = {}
    for source in (condition or {}, reference or {}):
        for key, value in source.items():
            name = str(key).casefold()
            folded[name] = value
            alias = CONDITION_KEY_ALIASES.get(name)
            if alias is not None:
                # `setdefault` and not assignment: a mapping already carrying
                # the COLUMN's own spelling wins over an alias, so a caller that
                # has done the translation itself is never overwritten by one
                # that happens to carry both spellings.
                folded.setdefault(alias.casefold(), value)
    return tuple(folded.get(name.casefold()) for name in columns)


def rotor_advance_ratio(speed_m_s: object, rpm: object, diameter_m: object) -> float | None:
    """Return ``J = V / (n D)`` of a rotor at its own speed and diameter, or None.

    THE ONE HOME of the ratio a rotor RAN at (P0320-QS-J): ``J_CLOCK`` of every
    table and the ``J`` of a quasi-steady point's tables read it here. ``n`` is
    in rev/s and its MAGNITUDE, because the hand of the rotation is the rotor's
    and ``RPM_CLOCK`` carries it. None, and not a guess, where an input is
    missing or not a finite number, or where the rotor speed is zero or the
    diameter is not positive. A speed of zero gives ``J = 0``.

    Parameters
    ----------
    speed_m_s : object
        The free-stream speed in m/s; zero gives ``J = 0``.
    rpm : object
        The rotor's speed in rev/min; its sign is left out.
    diameter_m : object
        The rotor's diameter in metres.

    Returns
    -------
    float or None
        ``J``, or None where an input is missing or not finite, the rotor
        speed is zero or the diameter is not positive.
    """
    values = []
    for value in (speed_m_s, rpm, diameter_m):
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        values.append(float(value))
    speed, rate, diameter = values
    if not all(math.isfinite(value) for value in values):
        return None
    if abs(rate) <= 0.0 or diameter <= 0.0:
        return None
    return speed / (abs(rate) / 60.0 * diameter)


#: Columns distinguishing sections rows before their shared condition.
#: AZIMUTH is NA without a rotor, not zero, which is a real rotor angle.
#: STEP names the solver step, or solver iteration on a steady run.
#: FAMILY, PLANE and ROTOR identify the distribution.
_SECTION_IDENTITY_COLUMNS: tuple[str, ...] = ("STEP", "FAMILY", "PLANE", "ROTOR", "AZIMUTH")

#: G16: the polar first, as in every table the post writes.
SECTION_COLUMNS: tuple[str, ...] = (
    POLAR_ID_COLUMN,
    *_SECTION_IDENTITY_COLUMNS,
    *CONTEXT_COLUMNS,
    "Offset",
    "Chord",
    "X_QC",
    "Z_QC",
    "Fx",
    "Fz",
    "Moment",
)

#: The plot-column prefixes that are coefficients, which the solver
#: normalises by its reference velocity and the product by the free stream.
_COEFFICIENT_PLOT_PREFIXES = ("CL_", "CDI_", "CDO_", "CDP_", "CDV_", "CD_")

#: Fixed decimals for cells without a column-specific precision rule.
_DECIMALS = 5

#: Dimensional columns whose small values need significant digits. Include the
#: native plots clock and the physical quantities of sections and probe exports,
#: not only the series clock and viscosity.
_SIGNIFICANT_DIGIT_COLUMNS: frozenset[str] = frozenset(
    {
        "MU",
        "time_s",
        "Time (sec)",
        "Time",
        "ALPHA",
        "BETA",
        "AZIMUTH",
        "AZIMUTH_START",
        "AZIMUTH_END",
        "VINF",
        "VREF",
        "ALT",
        "RHO",
        "TEMP",
        "SREF",
        "CREF",
        "BREF",
        "XMOM",
        "YMOM",
        "ZMOM",
        "X",
        "Y",
        "Z",
        "Offset",
        "Chord",
        "X_QC",
        "Z_QC",
        "Fx",
        "Fz",
        "Moment",
        "Strip_length",
        "Fx_int",
        "Fz_int",
        "My_int",
        "vx",
        "vy",
        "vz",
        "vtot",
        "s_len",
        "momentum_thickness",
        "disp_thick",
        "thickness",
        "STATION_R_M",
        "H0",
        "H1_AMP",
        "H2_AMP",
        "H1_PHASE_DEG",
        "H2_PHASE_DEG",
        "RESIDUAL_RMS",
        "RPM",
        "DIAMETER",
        "THRUST",
        "TORQUE",
        "POWER",
        "BERNOULLI_RESIDUAL",
        "W_M_S",
        "GAMMA_M2_S",
        "DI_N_M",
        "ALPHA_I_DEG",
        "FX",
        "FY",
        "FZ",
        "MX",
        "MY",
        "MZ",
        "VELOCITY",
        "VELOCITY_X",
        "VELOCITY_Y",
        "VELOCITY_Z",
        "VX",
        "VY",
        "VZ",
        "BL_MOMENTUM_THICKNESS",
        "BL_DISPLACEMENT_THICKNESS",
        "BL_TOTAL_THICKNESS",
    }
)
_DIMENSIONAL_PREFIXES = (
    "RPM_",
    "DIAMETER_",
    "THRUST_",
    "TORQUE_",
    "POWER_",
    "FX_",
    "FY_",
    "FZ_",
    "MX_",
    "MY_",
    "MZ_",
)
_SIGNIFICANT_DIGITS = 6

#: Aerodynamic coefficient names, including native and alias-qualified columns.
#: Settings are not coefficients, and a coefficient's drift percentage retains
#: its fixed-decimal format. The pattern excludes physical names such as CREF.
_COEFFICIENT_COLUMN = re.compile(
    r"(?:^|[_ ])(?:C[LDYNRMTPQSFXZ](?:[BWSXYZ]|[IPV0]|[BWS]25)?|CM[XYZ]|"
    r"(?:CR|CM|CN)[BWS]?25|E_T|ETA|ETAW|J)(?:_.*)?$",
    re.IGNORECASE,
)


#: CSV products use NA for a column that does not apply. _cell is the
#: shared funnel for all product families and converts every blank to NA;
#: it cannot distinguish inapplicable values from missing expected ones.
#: Producers therefore own that distinction. Probe position and frame
#: cells also become NA when a record names no probe-position file,
#: preserving readable products despite unavailable position evidence.
#: The printed plan, cost, QA tables and matrix writer share this token;
#: readers still accept the legacy dash. Its definition is in _tokens
#: below all layers, and this module explicitly re-exports it for callers.


def _cell(value: object) -> str:
    """One CSV cell: floats at five decimals, a blank as ``NA``, everything else as written.

    IT IS DONE HERE because this is the funnel the CSV PRODUCTS pass through --
    the polars, the superfile, the sections, the probes, the campaign reduction
    table, the POINT SERIES and the settings table. A rule applied at each
    writer would need a separate implementation for every product family.

    WHAT DOES NOT PASS THROUGH IT, named rather than left to be discovered:
    `reductions.write_series` and `reductions.write_reduction` render their own
    rows with a bare `csv.writer`, and the probe-positions file in the run stage
    does the same. No `None` reaches any of the three, so none of them writes a
    blank today -- but a NaN would print as `nan` rather than `NA`, and that is
    a gap rather than a decision. The claim here is about the products, not
    about every line of CSV the package emits: an earlier writing of this
    docstring said "every CSV product", and a lens measured the settings table
    doing the exact opposite one module away.

    THIS LIST IS THE AUTHORITY AND EVERY OTHER COPY POINTS AT IT. The closing
    round of FIX-0230 found the change log naming SEVEN products here and this
    docstring naming six, the point series being the one it had dropped --
    `post.series` writes through `write_csv_table` and always did. An
    enumeration that has just been corrected for overclaiming is worth
    re-reading for the opposite, and nobody had.

    NO CELL HOLDS A COMMA OR A DOUBLE QUOTE (G16), which is the second
    rule held here for the same reason as the first: a text cell goes through
    :func:`pyflightstream._tokens.plain_cell`, so a comma is written ``;``, a
    double quote a single one and a line break a space, and the CSV writer has
    nothing to quote. A reader that splits each line on ``,`` then reads every
    row to the header's count. The matrix cells the super content echoes were
    the cells that broke it: ``SWEEP_VALUES`` and ``FLIGHT_CONDITION`` were
    written quoted, commas inside.
    """
    if value is None:
        return NOT_APPLICABLE
    if isinstance(value, float | np.floating):
        number = float(value)
        # NaN and the infinities are values a table cannot state: the NA token.
        return NOT_APPLICABLE if not math.isfinite(number) else f"{number:.{_DECIMALS}f}"
    text = str(value)
    return plain_cell(text) if text.strip() else NOT_APPLICABLE


def _significant_cell(value: object) -> str:
    """Return a cell at six significant digits where that is closer than five decimals."""
    if not isinstance(value, float | np.floating) or not math.isfinite(float(value)):
        return _cell(value)
    number = float(value)
    decimal = f"{number:.{_DECIMALS}f}"
    significant = f"{number:.{_SIGNIFICANT_DIGITS}g}"
    if abs(float(significant) - number) < abs(float(decimal) - number):
        return significant
    return decimal


_TOKEN_REFUSED = re.compile(r'[\s"]')


def _refuse_a_token(what: str, text: str, *, quotes: bool = True) -> None:
    """Refuse a name or title the VTK and Tecplot grammars cannot carry as written."""
    refused = _TOKEN_REFUSED if quotes else re.compile(r"[\r\n]")
    if not text or refused.search(text):
        raise ProductError(
            f"{what} {text!r} cannot be written: a name is not empty and holds no "
            "whitespace or double quote, which the format would read as the end of the "
            "token"
        )


def write_csv_table(
    path: str | Path, columns: Sequence[str], rows: Sequence[Sequence[object]]
) -> Path:
    """Write one CSV table, retaining six significant figures in coefficient columns.

    The header names pass the cells' rule too (G16): no name holds a comma or a
    double quote, so nothing on any line is quoted.

    THE ONE COLUMN-AWARE RULE (PFS-2105.041): a column of
    :data:`_SIGNIFICANT_DIGIT_COLUMNS`, a physical quantity whose values five
    decimals cannot carry, is written at six significant digits wherever that
    states the value more closely than five decimals do. Sea-level viscosity
    was written ``0.00002`` (12 per cent off) and a time step of 2.78e-5 s
    made consecutive rows read ``0.00003, 0.00006, 0.00008``; a value five
    decimals already hold exactly is written as it always was. Dimensional
    force, moment, rotor speed and diameter columns keep this rule when a
    group or rotor alias is appended to their name. Fluid velocity histories
    keep it when a probe number is appended. Unknown columns retain the
    reference precision. Coefficient columns use
    the same six-significant-digit rule; their drift percentages retain five
    decimals. Settings passed as exact text retain their stated form.

    Parameters
    ----------
    path : str or Path
        The table to write.
    columns : sequence of str
        The header names.
    rows : sequence of sequence of object
        The rows, one value per column; None is written as ``NA``.

    Returns
    -------
    Path
        The written table.

    Raises
    ------
    ProductError
        If a row's width differs from the header's.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _textio.atomic_text(target) as handle:
        writer = _textio.csv_writer(handle)
        writer.writerow([plain_cell(str(name)) for name in columns])
        for row in rows:
            if len(row) != len(columns):
                raise ProductError(f"a row has {len(row)} values for {len(columns)} columns")
            writer.writerow(
                [
                    _significant_cell(value)
                    if (
                        name in _SIGNIFICANT_DIGIT_COLUMNS
                        or name.startswith(_DIMENSIONAL_PREFIXES)
                        or (
                            _COEFFICIENT_COLUMN.search(name)
                            and not name.upper().endswith("_DRIFT_PCT")
                        )
                        or re.fullmatch(
                            r"(?:VELOCITY|V[XYZ]|BL_(?:MOMENTUM|DISPLACEMENT|TOTAL)_THICKNESS)\d+",
                            name,
                        )
                    )
                    else _cell(value)
                    for name, value in zip(columns, row, strict=True)
                ]
            )
    return target


def renamed_columns(
    columns: Sequence[str],
    names: Mapping[str, str] | None,
    *,
    printed: Sequence[str],
    where: str,
) -> tuple[str, ...]:
    """Return ``columns`` with the pproc's ``[names]`` dictionary applied.

    ``printed`` is what the plots export prints, which is what a dictionary's
    left side may name. THE WHOLE DICTIONARY APPLIES OR NONE OF IT DOES: half a
    dictionary applied is a file nobody can predict.

    Parameters
    ----------
    columns : sequence of str
        The table's columns.
    names : mapping of str to str, or None
        The pproc's ``[names]`` dictionary, printed name to new name; None or empty leaves the
        columns as they are.
    printed : sequence of str
        The columns the plots export prints.
    where : str
        What the refusal names as the place of the dictionary.

    Returns
    -------
    tuple of str
        The columns, each renamed where the dictionary names it.

    Raises
    ------
    ProductError
        If an entry names a column no plot prints, which must never become a
        column of `NA` nor pass in silence; or gives a column a name the table
        already carries.
    """
    if not names:
        return tuple(columns)
    unknown = [name for name in names if name not in printed]
    if unknown:
        raise ProductError(
            f"{where}: the pproc's [names] table names {', '.join(unknown)}, which no plot "
            f"of this point prints (it prints {', '.join(printed) or 'none'}). A plot column "
            "is <parameter>_<group name>; correct the left side of the entry, or remove "
            "it. No column was renamed."
        )
    held = set(columns)
    clash = [f"{old} -> {new}" for old, new in names.items() if new != old and new in held]
    if clash:
        raise ProductError(
            f"{where}: the pproc's [names] table renames {', '.join(clash)}, and the table "
            "already carries a column of that name. Choose another name. No column was "
            "renamed."
        )
    renamed = tuple(names.get(name, name) for name in columns)
    doubled = sorted({name for name in renamed if renamed.count(name) > 1})
    if doubled:
        raise ProductError(
            f"{where}: the pproc's [names] table gives two columns the name "
            f"{', '.join(doubled)}, and a value would be lost on reading. Choose different "
            "names. No column was renamed."
        )
    return renamed


#: The rotor-table filename suffix and number of lines before its header.
#: Current tables start with the header and carry the alias in ROTOR after
#: POL, so the skip count is zero. Legacy tables with a single-cell alias
#: line before the header can be read by dropping that line.
ROTOR_TABLE_SUFFIX = "_rotor.csv"
ROTOR_TABLE_LEAD_LINES = 0


def section_identity(
    n_rows: int,
    layout: Sequence[Mapping[str, object]] | None,
    rotors: Mapping[str, Mapping[str, object]] | None,
    step: int | None,
    azimuth_deg: float | None,
) -> list[tuple[object, object, object, object]]:
    """Return (FAMILY, PLANE, ROTOR, AZIMUTH) for each row of one sections export.

    A layout whose counts do not add up to the export is NOT applied: a row given
    its neighbour's family is worse than a row given none.

    Parameters
    ----------
    n_rows : int
        The export's number of rows.
    layout : sequence of mapping, or None
        The recorded sections layout, one block per distribution with its ``count``, ``families``
        and ``plane``.
    rotors : mapping of str to mapping, or None
        Rotor alias to its recorded metadata, which says which rotor owns a block and where its
        blade is.
    step : int or None
        The export's time step, for the azimuth at it.
    azimuth_deg : float or None
        The azimuth every row carries where the layout is not applied, in degrees.

    Returns
    -------
    list of tuple
        One ``(FAMILY, PLANE, ROTOR, AZIMUTH)`` per row; None for the first three of every row
        where the layout is missing or its counts do not add up.
    """
    unknown: list[tuple[object, object, object, object]] = [
        (None, None, None, azimuth_deg)
    ] * n_rows
    if not layout:
        return unknown
    counts: list[int] = []
    for block in layout:
        count = block.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            return unknown
        counts.append(count)
    if sum(counts) != n_rows:
        return unknown
    identity: list[tuple[object, object, object, object]] = []
    for block, count in zip(layout, counts, strict=True):
        families = _names_of(block.get("families"))
        alias, azimuth = _rotor_of_the_block(families, rotors, step)
        cell = ("+".join(families) or None, block.get("plane"), alias, azimuth)
        identity.extend([cell] * count)
    return identity


def _names_of(stated: object) -> list[str]:
    """Return a recorded list of names as strings, and nothing for anything else."""
    if isinstance(stated, str) or not isinstance(stated, Sequence):
        return []
    return [str(name) for name in stated]


def _rotor_of_the_block(
    families: Sequence[str],
    rotors: Mapping[str, Mapping[str, object]] | None,
    step: int | None,
) -> tuple[str | None, float | None]:
    """Return the rotor that owns every family of a block, and the azimuth it states.

    A block that cuts the families of ONE blade of the rotor (the rotor's
    ``blade_families``, blade n from 1, each the geometry families that blade
    may state) states THAT blade's azimuth: blade one's, placed by
    :func:`~pyflightstream.post.axes.placed_blade_azimuth_deg`, the one home of
    where blade n sits. Any other block of the rotor (several blades, the
    general families, or a rotor that states no blade grouping) states blade
    one's azimuth, as before.
    """
    for alias, rotor in (rotors or {}).items():
        owned = set(_names_of(rotor.get("families")))
        if not families or not set(families) <= owned:
            continue
        blade_one = blade_azimuth_deg(
            rotor.get("blade1_azimuth_deg"),
            step=step,
            steps_per_revolution=rotor.get("steps_per_revolution"),
            rpm=rotor.get("rpm"),
        )
        return str(alias), _own_blade_azimuth(families, rotor, blade_one)
    return None, None


def _own_blade_azimuth(
    families: Sequence[str], rotor: Mapping[str, object], blade_one_deg: float | None
) -> float | None:
    """Return the azimuth of the ONE blade a block cuts, else blade one's (``blade_one_deg``)."""
    grouped = rotor.get("blade_families")
    if isinstance(grouped, str) or not isinstance(grouped, Sequence):
        return blade_one_deg
    blades = [set(_names_of(members)) for members in grouped]
    cut = [number for number, members in enumerate(blades, start=1) if set(families) <= members]
    if len(cut) != 1:
        return blade_one_deg
    # `blades` is the ROTOR's count where the block states it (a periodic sector
    # carrying two blades of four spaces them a quarter turn apart), the number
    # of blade groups only where the rotor states none.
    stated = rotor.get("blades")
    count = (
        stated if isinstance(stated, int) and not isinstance(stated, bool) and stated > 0 else None
    )
    return placed_blade_azimuth_deg(blade_one_deg, blade=cut[0], blades=count or len(blades))


#: The twenty-four coefficient columns of a polar row, in the order: the
#: point, the body axes, the stability axes, the wind axes, the two drag
#: parts. ``RE`` is the Reynolds number in millions.
COEFFICIENT_COLUMNS: tuple[str, ...] = (
    "ALPHA",
    "BETA",
    "MACH",
    "RE",
    "CDB",
    "CYB",
    "CLB",
    "CRB25",
    "CMB25",
    "CNB25",
    "CDS",
    "CYS",
    "CLS",
    "CRS25",
    "CMS25",
    "CNS25",
    "CDW",
    "CYW",
    "CLW",
    "CRW25",
    "CMW25",
    "CNW25",
    "CD0",
    "CDI",
)

#: The reference block every product row carries in front of its values,
#: so a row is self-describing: which polar, which group, which reference.
_REFERENCE_COLUMNS: tuple[str, ...] = ("SREF", "CREF", "BREF", "XMOM", "YMOM", "ZMOM")


#: A sections table's columns: the point and its condition, then the
#: sectional loads export's own seven columns, in its units.
@dataclass(frozen=True)
class ReferenceValues:
    """The reference block of a product: SREF, CREF, BREF and the moment point.

    The moment point is in the geometry's own coordinate system, the one the
    solver holds the mesh in and reports loads about (the MRP frame the reference
    scripts created sits at this point); the units ride on the field names.
    """

    sref_m2: float
    cref_m: float
    bref_m: float
    xmom_m: float = 0.0
    ymom_m: float = 0.0
    zmom_m: float = 0.0

    @classmethod
    def from_mapping(cls, values: Mapping[str, float]) -> ReferenceValues:
        """Read the block from a mapping keyed by the column names."""
        try:
            return cls(
                sref_m2=float(values["SREF"]),
                cref_m=float(values["CREF"]),
                bref_m=float(values["BREF"]),
                xmom_m=float(values.get("XMOM", 0.0)),
                ymom_m=float(values.get("YMOM", 0.0)),
                zmom_m=float(values.get("ZMOM", 0.0)),
            )
        except KeyError as missing:
            raise ProductError(
                f"the reference block needs {missing.args[0]}; it carries {sorted(values)}"
            ) from missing

    def as_row(self) -> tuple[float, ...]:
        """Return the six values in :data:`_REFERENCE_COLUMNS` order."""
        return (self.sref_m2, self.cref_m, self.bref_m, self.xmom_m, self.ymom_m, self.zmom_m)

    def as_lengths(self) -> dict[str, float]:
        """Return the three reference LENGTHS, keyed by their column names.

        For the product families that carry no moment: a probe sample and a
        reduction window have no moment coefficient, so three columns of moment
        point would be three columns of nothing. The lengths are what a reader
        of those files needs to check a coefficient against.
        """
        return {"SREF": self.sref_m2, "CREF": self.cref_m, "BREF": self.bref_m}

    def as_moment_point(self) -> dict[str, float]:
        """Return the moment point, keyed by its column names.

        For the families that DO carry a moment without carrying the polar's own
        reference block: the unsteady polar and the reductions average the plots'
        `MX_/MY_/MZ_` columns, and a moment states nothing without the point it
        is taken about.
        """
        return {"XMOM": self.xmom_m, "YMOM": self.ymom_m, "ZMOM": self.zmom_m}


def _mach_code(mach: float) -> int:
    """Return the two-digit Mach code of the reference file names: ``round(mach * 100)``."""
    return round(mach * 100)


def polar_file_name(polar: str | int, mach: float, group: str | int) -> str:
    """``<polar>_M<mach code:02d>_g<group:02d>.csv``: one polar table per group.

    THE RECORDED CONVENTION, and the one the reference tooling wrote
    before this package existed. :func:`write_recorded_polar` regenerates
    the recorded tables under it and is compared with what those files name for
    name, which is why it stays. A polar table of a WORKSPACE is named by
    :func:`swept_polar_file_name`, the standard point convention (FR-85).

    Parameters
    ----------
    polar : str or int
        The polar's number.
    mach : float
        The Mach number, written as its two-digit code.
    group : str or int
        The plot group's number, as an int or as the text of one.

    Returns
    -------
    str
        The polar table's file name.

    Raises
    ------
    ProductError
        If ``group`` is a name: the convention states a group by number.
    """
    try:
        number = int(group)
    except (TypeError, ValueError):
        raise ProductError(
            f"the recorded polar file name states a group by NUMBER and {group!r} is a name; "
            "a workspace's polar tables are named by swept_polar_file_name, which carries it"
        ) from None
    return f"{polar}_M{_mach_code(mach):02d}_g{number:02d}.csv"


# --- the post's one CSV reader (AD-10: moved from post.products) ---


def read_csv_table(
    path: str | Path, *, skip: int = 0
) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    """Read one CSV table back: its columns and its rows as mappings of text.

    Values come back as the text written, so a caller decides what is a
    number; a row whose width differs from the header is refused naming
    the line, which is what makes the round trip a proof.

    ``skip`` drops that many lines before the header. Current tables start
    with the header and column `POL` (G16). A legacy rotor table with its
    alias alone on the first line is read with ``skip=1``.

    Parameters
    ----------
    path : str or Path
        The CSV table.
    skip : int, optional
        Lines dropped before the header.

    Returns
    -------
    tuple of (tuple of str, list of dict of str to str)
        The columns and the rows, each a mapping of column to the text written.

    Raises
    ------
    ProductError
        If the file is empty, or a row's width differs from the header's, naming the line.
    """
    target = Path(path)
    with target.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for _ in range(max(0, int(skip))):
            next(reader, None)
        try:
            columns = tuple(next(reader))
        except StopIteration:
            raise ProductError(f"{target} is empty; a table has at least its header") from None
        rows = []
        # THE FILE'S OWN LINE NUMBER: the header is line 1 + skip.
        for number, cells in enumerate(reader, start=2 + max(0, int(skip))):
            if len(cells) != len(columns):
                raise ProductError(
                    f"{target} line {number} carries {len(cells)} values for {len(columns)} columns"
                )
            rows.append(dict(zip(columns, cells, strict=True)))
    return columns, rows


# --- the plots-table readers (AD-10: moved from post.products) ---

#: PFS-2038.04. The column an unsteady plots export states its clock in.
#: Private here, since this module's public names are the ones post.products
#: lists; post.products keeps it as ``PLOTS_STEP_COLUMN`` (AD-10), and
#: the probe table and the probe fields read it from here.
#: The same name `post.superfile` and the probe table already read, and the
#: same rule those two write down: the step a sample came from is not a guess.
_PLOTS_STEP_COLUMN = "Time-step"


def _stated_steps(columns: Sequence[str], values: np.ndarray, n_rows: int) -> np.ndarray:
    """Return the exported clock where the table states one, the ordinal otherwise."""
    if _PLOTS_STEP_COLUMN not in columns or not n_rows:
        return np.arange(1, n_rows + 1, dtype=int)
    return _read_step_clock(values[:, list(columns).index(_PLOTS_STEP_COLUMN)])


def _read_step_clock(cells: Sequence[object] | np.ndarray) -> np.ndarray:
    """Return the steps a plots table's ``Time-step`` cells state, the ordinal where they cannot.

    THE ONE READER OF THAT CLOCK (AD-10): the reductions, the probe table and
    the probe fields read it through here, so a row's step is the same number
    in every product. A cell that is not a finite whole number, or a clock
    that is not strictly increasing, gives the WHOLE table its ordinal, never
    a mix of stated and ordinal steps.

    Parameters
    ----------
    cells : sequence
        The column's cells, as text or numbers, in table order.

    Returns
    -------
    numpy.ndarray
        One whole step per cell.
    """
    n_rows = len(cells)
    ordinal = np.arange(1, n_rows + 1, dtype=int)
    try:
        read = [float(cell) for cell in cells]  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ordinal
    stated = np.asarray(read, dtype=float)
    if not n_rows or not bool(np.all(np.isfinite(stated))):
        return ordinal
    whole = np.rint(stated)
    if not bool(np.all(np.abs(stated - whole) < 1e-9)):
        # A fractional clock is a time and not a step; the windows a
        # reduction states are whole steps, so the ordinal is what is left.
        return ordinal
    steps = whole.astype(int)
    if n_rows > 1 and not bool(np.all(np.diff(steps) > 0)):
        # Duplicated or out of order. Selecting a window by value would
        # then pick rows the window did not name, which is worse than the
        # ordinal it has always used.
        return ordinal
    return steps


def _plotted_number(text: str | None) -> float:
    """Read one plots-table cell as a number, its `NA` or blank as NaN."""
    cell = (text or "").strip()
    # The historical dash is a reader's NA too (the token's own definition).
    return math.nan if cell in ("", NOT_APPLICABLE, "-") else float(cell)


def plots_table_series(path: str | Path) -> tuple[tuple[str, ...], TimestepSeries]:
    """Read a written plots table back as the series its reductions are taken over.

    THE TABLE'S OWN CLOCK WHEN IT STATES ONE (PFS-2038.04, GEO-039-F05).
    The export writes one row per time step (the manual's paraphrase in the
    database entry for ``UNSTEADY_SOLVER_EXPORT_PLOTS``) and states the step
    it wrote in a ``Time-step`` column; the step axis is that column, so a
    window's ``FIRST_STEP`` and ``LAST_STEP`` mean what the file means,
    including an offset or sparse clock.

    Use row ordinals only where the table states no step clock.

    THE ORDINAL REMAINS THE FALLBACK, for a table that states no such
    column and for one whose column is not a strictly increasing whole
    number: a product is better than a refusal there, and the review's
    coverage validation, which would refuse windows that work today, is
    deliberately not taken. The column is still carried as a FIELD as well,
    so no existing product loses a value.

    Every column is one field of one sample, since the plots table samples
    no position; the sample position is the origin, which stands for the
    configuration the plot was defined over.

    Read from the WRITTEN table rather than from the export in memory, so a
    reduction is of the file a user holds and can be recomputed from it.

    `POL` IS NOT A PLOTTED QUANTITY (G16). The table opens with the
    polar its point belongs to, which says which polar the file is OF and is
    no field of any sample: it is left out of the columns and of the series,
    so no reduction averages it and no reduction states it twice. A table
    with no such column needs no exclusion.

    Parameters
    ----------
    path : str or Path
        A plots table the post wrote.

    Returns
    -------
    tuple
        The table's plotted columns, in its order, and the series.

    Raises
    ------
    ProductError
        If the table holds a header and no rows.
    """
    header, rows = read_csv_table(path)
    columns = tuple(name for name in header if name != POLAR_ID_COLUMN)
    if not rows:
        raise ProductError(f"{path} holds a header and no rows; a plots table has a time step")
    # `NA` (or blank) READS BACK AS NaN. The table writes a NaN the export
    # carried as `NA`, and `float` refused the table's own token, so a table
    # holding one could not be read at all; the window's average decides
    # whether the NaN matters.
    values = np.asarray(
        [[_plotted_number(row[name]) for name in columns] for row in rows], dtype=float
    )
    return columns, TimestepSeries(
        steps=_stated_steps(columns, values, len(rows)),
        times_s=None,
        points=np.zeros((1, 3)),
        fields={name: values[:, index][:, None] for index, name in enumerate(columns)},
        sources=(Path(path),),
    )


# --- the whole march of a continued point (FR-96) ---------------------
#
# A continuation reopens the saved simulation of the run it continues and
# marches on; that run's outputs are archived under the datapoint's
# ``archive/<stamp>/``, the stamp being the one the continuation's run id
# carries (``<campaign>/sim_<id>/r<stamp>/<point>``). RPT-134 measured one shape on
# 26.124: a continuation that clears the reopened state marches again from step 1,
# so its export restates the march it continues. The other shape, an export of the
# continuation's own steps only, is not on record, so the post reads both by their
# step numbers and says which it met.

#: The run types that march in time; only their records are continued.
_MARCHING = ("unsteady", "unsteady_rotor")
#: The banner labels a plots export scales its coefficients by; two exports
#: are one history only when they state the same two.
_SCALE_LABELS = ("Freestream velocity (m/s)", "Reference velocity (m/s)")
_TIME_COLUMNS = ("Time (sec)", "Time")
_RULE = re.compile(r"^-{4,}$")


@dataclass(frozen=True)
class _PlotsExport:
    """One plots export split into its banner, its rows and what follows them."""

    head: list[str]
    rows: list[str]
    tail: list[str]
    columns: tuple[str, ...]
    values: np.ndarray
    steps: np.ndarray
    scale: tuple[str | None, ...]


@dataclass(frozen=True)
class _MarchHistory:
    """The plots history of a continued point over its whole march (FR-96).

    Attributes
    ----------
    text : str
        The export the plots table is written from: the continuation's banner
        and footer around the rows of every run of the chain, in step order.
    last_step : int
        The last step the history holds, where the averaging window ends.
    said : str
        What the post log states about how the history was put together.
    idle : tuple of str
        One warning per run of the chain whose export adds no time step to the
        march it continues (FR-800), naming both runs; empty where every
        continuation marched on.
    """

    text: str
    last_step: int
    said: str
    idle: tuple[str, ...] = ()


def _plots_export(path: Path) -> _PlotsExport | None:
    """Read one plots export as rows of text and numbers, or None where it cannot be.

    The rows are found as :func:`~pyflightstream.results.parse_unsteady_plots`
    finds them: the header is the first line carrying a comma, then every
    line that is neither blank nor a dashed rule, until the rule that closes
    the table.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        report = parse_unsteady_plots(text)
    except (OSError, PyflightstreamError):
        return None
    scale = tuple(_printed(text, label) for label in _SCALE_LABELS)
    lines = text.split("\n")
    header = next(index for index, line in enumerate(lines) if "," in line)
    at: list[int] = []
    for index in range(header + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped and _RULE.match(stripped):
            if at:
                break
        elif stripped:
            at.append(index)
    values = np.asarray(report.values, dtype=float)
    if len(at) != len(values):
        return None
    return _PlotsExport(
        head=lines[: at[0]],
        rows=[lines[index] for index in at],
        tail=lines[at[-1] + 1 :],
        columns=tuple(report.columns),
        values=values,
        steps=_stated_steps(report.columns, values, len(at)),
        scale=scale,
    )


def _printed(text: str, label: str) -> str | None:
    """Return the value a banner prints after ``label``, or None where it prints none."""
    try:
        return labeled_value(text, label)
    except (PyflightstreamError, ValueError):
        return None


def _renumbered(export: _PlotsExport, by_step: int, by_time: float) -> list[str]:
    """Return the export's rows with the step and the time moved on by the given amounts."""
    columns = export.columns
    moved = {_PLOTS_STEP_COLUMN: float(by_step)} if _PLOTS_STEP_COLUMN in columns else {}
    moved.update({name: by_time for name in _TIME_COLUMNS if name in columns})
    rows = []
    for row, values in zip(export.rows, export.values, strict=True):
        cells = row.strip().split(",")
        for name, by in moved.items():
            index = columns.index(name)
            cells[index] = f"{values[index] + by:.10G}"
        rows.append(",".join(cells))
    return rows


_History = tuple[list[str], np.ndarray, np.ndarray]


def _join(before: _History, after: _PlotsExport) -> tuple[_History, str] | None:
    """Join a history and the export of the run that continued it, at an exact seam.

    The rule, by step number: an export whose first step comes after the
    history's last continues the numbering and is appended; one that starts
    inside the history and repeats its rows there restates the march and is
    taken from where it starts; one that starts again at step 1 with rows of
    its own restarted the count and is numbered on from the history's last
    step, its time too. Anything else is not joined (None): a seam that
    cannot be placed exactly is not a history.
    """
    rows, values, steps = before
    last, first = int(steps[-1]), int(after.steps[0])
    if first > last + 1:
        return None  # steps are missing at the seam: no step may be missing there
    if first > last:
        stacked = np.vstack([values, after.values])
        return (rows + after.rows, stacked, np.concatenate([steps, after.steps])), (
            f"numbered on from step {first}"
        )
    where = {int(step): index for index, step in enumerate(steps)}
    shared = [
        (index, where.get(int(step))) for index, step in enumerate(after.steps) if step <= last
    ]
    if all(
        mine is not None
        and np.allclose(after.values[index], values[mine], rtol=1e-6, atol=1e-12, equal_nan=True)
        for index, mine in shared
    ):
        keep = int(np.searchsorted(steps, first))
        # A restatement that ends before the history does leaves the later
        # steps in place: they are the march's, and so is its end.
        rest = int(np.searchsorted(steps, int(after.steps[-1]), side="right"))
        stacked = np.vstack([values[:keep], after.values, values[rest:]])
        return (
            rows[:keep] + after.rows + rows[rest:],
            stacked,
            np.concatenate([steps[:keep], after.steps, steps[rest:]]),
        ), f"restating the march from step {first}"
    if first != 1:
        return None
    columns = list(after.columns)
    time = next((columns.index(name) for name in _TIME_COLUMNS if name in columns), None)
    by_time = 0.0
    if time is not None and after.values[0, time] <= values[-1, time]:
        by_time = float(values[-1, time])
    moved = after.values.copy()
    if _PLOTS_STEP_COLUMN in columns:
        moved[:, columns.index(_PLOTS_STEP_COLUMN)] += last
    if time is not None:
        moved[:, time] += by_time
    stacked = np.vstack([values, moved])
    return (
        rows + _renumbered(after, last, by_time),
        stacked,
        np.concatenate([steps, after.steps + last]),
    ), (f"counting again from 1, numbered on from step {last + 1}")


def _plots_output(record: RunRecord | None) -> str | None:
    """Return the recorded output of a run that is its plots export, or None."""
    outputs = [str(name) for name in (record.outputs if record is not None else ())]
    name = classify_outputs([Path(output).name for output in outputs]).get("plots")
    return next((output for output in outputs if Path(output).name == name), None)


def _stamp_of(run_id: str) -> str | None:
    """Return the archive stamp a continuation's run id carries, or None."""
    parts = run_id.rsplit("/", 2)
    stamp = parts[-2][1:].split(".")[0] if len(parts) == 3 and parts[-2][:1] == "r" else ""
    try:
        datetime.strptime(stamp, ARCHIVE_STAMP)
    except ValueError:
        return None
    return stamp


def _chain(
    sim_dir: Path,
    record: RunRecord,
    output: str,
    end: _PlotsExport,
    manifest: Mapping[str, RunRecord],
) -> tuple[list[tuple[str, _PlotsExport]], str]:
    """Return the exports of the runs ``record`` continues, oldest first, and what was not found."""
    chain: list[tuple[str, _PlotsExport]] = []
    later = record
    while later.continues and len(chain) < len(manifest):
        earlier, stamp = manifest.get(later.continues), _stamp_of(later.run_id)
        name = Path(_plots_output(earlier) or output).name
        path = (sim_dir / output).parent / ARCHIVE_DIR / str(stamp) / name
        found = _plots_export(path) if stamp else None
        alike = found is not None and (found.scale, found.columns) == (end.scale, end.columns)
        if earlier is None or found is None or not alike:
            # A chain with an older run missing is no chain: the table then holds
            # the continuation's own export, as the definition states.
            return [], f"the history of {later.continues!r} is not readable at {path}"
        chain.insert(0, (str(later.continues), found))
        later = earlier
    return chain, ""


def _march_history(
    sim_dir: Path, record: RunRecord, manifest: Mapping[str, RunRecord]
) -> _MarchHistory | None:
    """Return the plots history of a continued point over its whole march, or None.

    None where the record continues nothing, is not a march, or has no
    readable plots export. Otherwise the chain of runs it continues is walked
    through ``continues`` in ``manifest`` (run id to record), each run's
    export read from the archive the next one moved it into, and the exports
    joined by :func:`_join`. A run of the chain whose export is not found, or
    cannot be joined, ends the walk there: the history then begins after it,
    and ``said`` names the file and what posting again after restoring it
    gives. The averaging window ends at the history's last step.
    """
    output = _plots_output(record)
    if not record.continues or record.recipe not in _MARCHING or output is None:
        return None
    end = _plots_export(sim_dir / output)
    if end is None:
        return None
    chain, missing = _chain(sim_dir, record, output, end, manifest)
    history: _History | None = None
    told: list[str] = []
    idle: list[str] = []
    before = ""
    for run_id, export in [*chain, (record.run_id, end)]:
        joined = _join(history, export) if history is not None else None
        if history is None or joined is None:
            if history is not None:
                missing = f"the export of {run_id!r} cannot be joined to the run before it"
                # No partial chain: the table holds the continuation's own export.
                export, run_id, idle = end, record.run_id, []
            history = (export.rows, export.values, export.steps)
            told = [f"{run_id!r} steps {int(export.steps[0])} to {int(export.steps[-1])}"]
            before = run_id
            if joined is None and run_id == record.run_id:
                break
            continue
        reached = int(history[2][-1])
        history, how = joined
        told.append(f"{run_id!r} {how} to step {int(history[2][-1])}")
        if int(history[2][-1]) <= reached:
            idle.append(_adds_no_step(run_id, before, reached))
        before = run_id
    rows, _, steps = history if history is not None else (end.rows, end.values, end.steps)
    said = (
        f"point={record.run_id} product=plots: this run continues {record.continues!r}, and "
        f"its plots table is the march as joined here: {'; '.join(told)}. "
        + (
            f"Not joined: {missing}, so the steps before it are not in the table; restore that "
            "file and post again to average over the whole march. "
            if missing
            else ""
        )
        + f"The averaging window ends at step {int(steps[-1])}, the last step the table holds."
    )
    text = "\n".join([*end.head, *rows, *end.tail])
    return _MarchHistory(text, int(steps[-1]), said, tuple(idle))


def _adds_no_step(run_id: str, continued: str, reached: int) -> str:
    """Return the warning for a continuation whose export adds no time step (FR-800).

    The shape RPT-134 measured on 26.124:
    the solver cleared the reopened state and marched again from step 1, so the
    export restates the march it continues and ends where that march ended. The
    table is still posted, as the march stands; the warning names the two runs.
    """
    return (
        f"point={run_id} product=plots: this continuation of {continued!r} adds no time "
        f"step to its march: {continued!r} had reached step {reached} and the "
        f"continuation's plots export ends there or before, so no continued step is in the "
        "table. A continuation that clears the reopened state marches again from step 1 "
        "(RPT-134); the table is posted as the march stands."
    )


#: The marches :func:`_march_records` computed in the current post, by run id,
#: for :func:`_march_plots_text` to take: each march is joined once per record.
_MARCHES: weakref.WeakKeyDictionary[CampaignWorkspace, dict[str, _MarchHistory | None]] = (
    weakref.WeakKeyDictionary()
)


def _march_records(workspace: CampaignWorkspace, records: Sequence[RunRecord]) -> list[RunRecord]:
    """Return ``records`` with each continuation's windows ending at its march's last step.

    FR-96: a continuation records the row's clock, so its windows end
    at the last step of the run it continues; they are moved, keeping their
    lengths, to end at the last step of the whole march (:func:`_march_history`,
    :func:`~pyflightstream.cases.windows.march_end`). Every other record is
    returned as it is, and no record is rewritten.
    """
    if not any(record.continues for record in records):
        return list(records)
    manifest = {record.run_id: record for record in workspace.read_manifest()}
    moved = []
    held = _MARCHES.setdefault(workspace, {})
    held.clear()  # a march is computed once per post: every post begins here
    for record in records:
        march = _march_history(workspace.sim_dir(record.sim_id), record, manifest)
        held[record.run_id] = march
        plan = march_end(record.reductions, last_step=march.last_step) if march else None
        moved.append(record.model_copy(update={"reductions": plan}) if plan else record)
    return moved


def _march_plots_text(workspace: CampaignWorkspace, record: RunRecord | None, path: Path) -> str:
    """Return the plots export a point's table is written from: the whole march, continued.

    A point that continues nothing reads its own export. A
    continuation reads :func:`_march_history`, and the post log says how it was
    put together and where the averaging window ends.
    """
    if record is not None and record.continues:
        held = _MARCHES.get(workspace, {})
        if record.run_id in held:
            march = held.pop(record.run_id)  # computed by _march_records, once for both
        else:
            manifest = {entry.run_id: entry for entry in workspace.read_manifest()}
            march = _march_history(workspace.sim_dir(record.sim_id), record, manifest)
        if march is not None:
            warn(march.said, PyflightstreamWarning, stacklevel=2)
            for idle in march.idle:
                warn(idle, PyflightstreamWarning, stacklevel=2)
            return march.text
    return path.read_text(encoding="utf-8", errors="replace")
