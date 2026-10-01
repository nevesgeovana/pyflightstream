"""Sectional loads export parser: ``FS_SurfaceSection_Loads.txt`` (AD-10).

Pipeline role: the results row, beside the other export parsers. It reads
the sectional loads export FlightStream's post-processing script writes
(``EXPORT_SURFACE_SECTIONAL_LOADS``): the labeled header, the SI units the
file must assert, and the table ``Offset, Chord, X_QC, Z_QC, Fx, Fz,
Moment`` of line densities along the span, split into per-family blocks by
the creation-order bookkeeping of the code that made the distributions.

Why it lives here, since 0.33.0. It was defined in
:mod:`pyflightstream.fsi.loads`, the coupling's module, while
:mod:`pyflightstream.results.tables` tabulates the report it returns: the
two modules then imported each other, the one cycle between the results row
and a side branch. The parser is output parsing, which is this row's
subject, so it moved down; :mod:`pyflightstream.fsi.loads` re-exports every
name it had, and the coupling's refusal, :class:`FsiInputError`, is
defined in :mod:`pyflightstream._errors` because two layers now name it.
The results row imports nothing of ``fsi``.

The physics of the file (line densities, the section-plane axes, the blade
attribution) is documented in :mod:`pyflightstream.fsi.loads`, which uses
the parsed report; parsing is anchor-based on the primitives of
:mod:`pyflightstream.results` (FR-16): labels and header rows, never line
offsets, and a missing structural terminator raises instead of returning a
silently shorter table (FR-17).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from pyflightstream._errors import FsiInputError, PyflightstreamError
from pyflightstream.results.core import (
    AnchorNotFoundError,
    IncompleteOutputError,
    delimited_table,
    labeled_value,
    parse_count,
    parse_number,
)

__all__ = [
    "EXPECTED_COLUMNS",
    "FamilyMap",
    "SectionBlock",
    "SectionalLoadsReport",
    "UnitsError",
    "parse_sectional_loads",
]


class _Family(Protocol):
    """One family of a :class:`FamilyMap`: its name and its section count."""

    @property
    def name(self) -> str: ...

    @property
    def count(self) -> int: ...


class FamilyMap(Protocol):
    """What :meth:`SectionalLoadsReport.split` reads of a family map.

    :class:`pyflightstream.fsi.loads.SectionFamilyMap` is the one the
    coupling builds; this row names it by the two things it reads, so it
    imports nothing of ``fsi``.
    """

    @property
    def families(self) -> Sequence[_Family]:
        """The families in creation order, each with its name and section count."""
        ...

    @property
    def total_sections(self) -> int:
        """Sum of the family section counts."""
        ...


_TABLE_ANCHOR = "Offset,"
EXPECTED_COLUMNS = ("Offset", "Chord", "X_QC", "Z_QC", "Fx", "Fz", "Moment")


class UnitsError(PyflightstreamError, ValueError):
    """The export does not carry the asserted SI units (FSI-R03).

    Unit errors in the coupling loop are silent and produce plausible
    wrong answers, so the parser refuses the file instead of scaling:
    the post-processing script must compute the sectional loads with
    ``COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS`` and the solver setup
    must stay in SI.
    """


@dataclass(frozen=True)
class SectionBlock:
    """The rows of one family, split out of the flat export.

    All arrays share the family's section count. The force and moment
    rows are line densities along the span (RPT-006, module
    docstring): the SI assertion fixes the unit basis (Newtons), and
    integrating over the tributary widths recovers the integrated
    loads.

    Attributes
    ----------
    family : str
        Family name from the :class:`SectionFamilyMap`.
    offset_m : numpy.ndarray
        Spanwise section positions [m], the radius from the rotation
        axis along the pitch axis.
    chord_m : numpy.ndarray
        Local chord [m].
    x_qc_m, z_qc_m : numpy.ndarray
        Quarter-chord position in the section plane [m], export axes.
    fx_n_per_m, fz_n_per_m : numpy.ndarray
        Sectional force densities [N/m] along the two in-plane axes of
        the distribution's cut plane, in plane-name order (for the
        blade-frame XY distribution: axial, then in-plane).
    moment_qc_nm_per_m : numpy.ndarray
        Sectional moment density about the quarter chord [N m / m],
        the pitch axis reference (DLV-007 Section 4.3).
    """

    family: str
    offset_m: np.ndarray
    chord_m: np.ndarray
    x_qc_m: np.ndarray
    z_qc_m: np.ndarray
    fx_n_per_m: np.ndarray
    fz_n_per_m: np.ndarray
    moment_qc_nm_per_m: np.ndarray


@dataclass(frozen=True)
class SectionalLoadsReport:
    """Typed content of one ``FS_SurfaceSection_Loads.txt`` export.

    Attributes
    ----------
    angle_of_attack_deg, sideslip_deg : float
        Freestream angles [deg].
    freestream_velocity_m_s : float
        Freestream velocity [m/s]; its label is an SI anchor.
    time_increment_s : float or None
        Unsteady time step [s], when printed.
    solver_mode : str
        ``Steady`` or ``Unsteady`` as printed.
    current_iteration : int
        Solver iteration at export time; advancing values across
        coupling calls are the per-step freshness evidence (RPT-005).
    reference_velocity_m_s, reference_length_m, reference_area_m2 : float or None
        Coefficient normalization references, when printed.
    declared_section_count : int
        Count printed in the header; asserted equal to the table rows.
    force_units, moment_units : str
        Units printed in the footer, asserted SI at parse time.
    columns : tuple of str
        Table column names as printed.
    values : numpy.ndarray
        Full table, shape ``(count, len(columns))``, in printed order.
    """

    angle_of_attack_deg: float
    sideslip_deg: float
    freestream_velocity_m_s: float
    time_increment_s: float | None
    solver_mode: str
    current_iteration: int
    reference_velocity_m_s: float | None
    reference_length_m: float | None
    reference_area_m2: float | None
    declared_section_count: int
    force_units: str
    moment_units: str
    columns: tuple[str, ...]
    values: np.ndarray

    @property
    def count(self) -> int:
        """Number of section rows."""
        return len(self.values)

    @property
    def offset_m(self) -> np.ndarray:
        """Spanwise section positions [m]."""
        return self.values[:, 0]

    @property
    def chord_m(self) -> np.ndarray:
        """Local chords [m]."""
        return self.values[:, 1]

    @property
    def fx_n_per_m(self) -> np.ndarray:
        """Sectional force densities [N/m], first cut-plane axis."""
        return self.values[:, 4]

    @property
    def fz_n_per_m(self) -> np.ndarray:
        """Sectional force densities [N/m], second cut-plane axis."""
        return self.values[:, 5]

    @property
    def moment_qc_nm_per_m(self) -> np.ndarray:
        """Sectional quarter-chord moment densities [N m / m]."""
        return self.values[:, 6]

    def split(self, family_map: FamilyMap) -> dict[str, SectionBlock]:
        """Split the flat table into per-family blocks and cross-check.

        The map's counts partition the rows in creation order; the
        offset and chord discontinuities expected at every block
        boundary are validated, so a map that disagrees with the
        actual creation order fails loudly instead of silently
        attributing sections to the wrong blade (RPT-005 finding 6).

        Parameters
        ----------
        family_map : SectionFamilyMap
            Creation-order bookkeeping from the distribution-creating
            code.

        Returns
        -------
        dict of str to SectionBlock
            Blocks keyed by family name, in creation order.
        """
        if family_map.total_sections != self.count:
            counts = [family.count for family in family_map.families]
            raise FsiInputError(
                f"the family map accounts for {family_map.total_sections} sections "
                f"({counts}) but the export holds {self.count}; the map does not "
                "describe the distributions of this run"
            )
        blocks: dict[str, SectionBlock] = {}
        start = 0
        for family in family_map.families:
            rows = self.values[start : start + family.count]
            blocks[family.name] = SectionBlock(
                family=family.name,
                offset_m=rows[:, 0],
                chord_m=rows[:, 1],
                x_qc_m=rows[:, 2],
                z_qc_m=rows[:, 3],
                fx_n_per_m=rows[:, 4],
                fz_n_per_m=rows[:, 5],
                moment_qc_nm_per_m=rows[:, 6],
            )
            start += family.count
        _validate_block_boundaries(list(blocks.values()))
        return blocks


def _smooth_step(values: np.ndarray, boundary_jump: float, *, directional: bool) -> bool:
    """Judge whether a boundary jump continues a block's march.

    A jump is a smooth continuation when it is within three times the
    block's median absolute step (and marching the same way, for the
    directional offset check). Blocks of one row cannot be judged and
    report not-smooth.
    """
    if len(values) < 2:
        return False
    steps = np.diff(values)
    median_step = float(np.median(np.abs(steps)))
    if abs(boundary_jump) > 3.0 * median_step:
        return False
    if directional:
        march = float(np.median(steps))
        if march != 0.0 and np.sign(boundary_jump) != np.sign(march):
            return False
    return True


def _validate_block_boundaries(blocks: list[SectionBlock]) -> None:
    """Cross-check the family split against the export's geometry.

    Each distribution marches its sections along the span, so inside a
    block the offsets are strictly monotonic, and at a true family
    boundary the offset restarts or the chord jumps (RPT-005 finding
    6). A boundary where both offset and chord continue smoothly means
    the family map disagrees with the creation order.
    """
    for block in blocks:
        steps = np.diff(block.offset_m)
        if len(steps) and not (np.all(steps > 0.0) or np.all(steps < 0.0)):
            raise ValueError(
                f"the offsets of family {block.family!r} are not monotonic along "
                "the span; a section distribution marches root to tip, so a "
                "non-monotonic block means the family map splits the export at "
                "the wrong rows"
            )
    for before, after in zip(blocks, blocks[1:], strict=False):
        offset_jump = float(after.offset_m[0] - before.offset_m[-1])
        chord_jump = float(after.chord_m[0] - before.chord_m[-1])
        offset_smooth = _smooth_step(before.offset_m, offset_jump, directional=True)
        chord_smooth = _smooth_step(before.chord_m, chord_jump, directional=False)
        if offset_smooth and chord_smooth:
            raise ValueError(
                f"families {before.family!r} and {after.family!r} continue smoothly "
                f"across their block boundary (offset jump {offset_jump:.4g} m, "
                f"chord jump {chord_jump:.4g} m); a true family boundary shows an "
                "offset restart or a chord discontinuity, so the family map "
                "disagrees with the creation order of the distributions "
                "(RPT-005 finding 6)"
            )


def _si_labeled_number(text: str, label: str) -> float:
    """Read a unit-carrying labeled value, asserting its SI label."""
    try:
        return parse_number(labeled_value(text, label))
    except AnchorNotFoundError as error:
        raise UnitsError(
            f"the export header does not carry the SI label {label!r}; the "
            "sectional loads parser asserts SI units on the labeled header "
            "(FSI-R03), so a missing unit label means the solver setup is not "
            "in SI or the export format changed"
        ) from error


def parse_sectional_loads(text: str) -> SectionalLoadsReport:
    """Parse one ``FS_SurfaceSection_Loads.txt`` export.

    Parameters
    ----------
    text : str
        Complete file text.

    Returns
    -------
    SectionalLoadsReport
        Typed table plus metadata. The SI assertions (FSI-R03) and the
        structural completeness checks (declared count, closing
        separator, units footer) run here; a file failing any of them
        raises instead of returning less.
    """
    freestream = _si_labeled_number(text, "Freestream velocity (m/s)")
    reference_area = _si_labeled_number(text, "Reference area (m^2)")
    try:
        force_units = labeled_value(text, "Force Units:")
        moment_units = labeled_value(text, "Moment Units:")
    except AnchorNotFoundError as error:
        raise IncompleteOutputError(
            "the sectional loads export has no units footer; the file ends "
            "before the closing block, so the solver stopped before finishing "
            "this export"
        ) from error
    if force_units.strip().lower() != "newtons":
        raise UnitsError(
            f"the export carries forces in {force_units!r}, not Newtons; the "
            "post-processing script must compute the sectional loads with "
            "COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS (FSI-R03), because any "
            "other unit would silently rescale the structural loads"
        )
    if moment_units.strip().lower() != "newton-meter":
        raise UnitsError(
            f"the export carries moments in {moment_units!r}, not Newton-Meter; "
            "a non-SI moment unit would silently rescale the elastic twist "
            "(FSI-R03)"
        )
    header_line = next(
        (line.strip() for line in text.splitlines() if line.strip().startswith(_TABLE_ANCHOR)),
        None,
    )
    if header_line is None:
        raise AnchorNotFoundError(
            f"the sectional loads table header {_TABLE_ANCHOR!r} was not found; "
            "the file is not an EXPORT_SURFACE_SECTIONAL_LOADS output or its "
            "format changed"
        )
    columns = tuple(cell.strip() for cell in header_line.split(",") if cell.strip())
    if columns != EXPECTED_COLUMNS:
        raise FsiInputError(
            f"the sectional loads table names columns {columns}, expected "
            f"{EXPECTED_COLUMNS}; the layout changed and the blade-frame "
            "mapping of the force columns must be re-verified before parsing"
        )
    # REV010-007. This was int(parse_number(...)), the same truncation the
    # results parser had already centralized into parse_count and that this
    # file kept its own copy of: a declared 100.9 became 100 and then passed
    # the 100-row completeness check below, so malformed evidence read as
    # complete evidence. One exact parser, used everywhere counts are read.
    declared = parse_count(
        labeled_value(text, "Number of Surface Sections:"),
        label="Number of Surface Sections",
        minimum=1,
        counts="surface sections",
    )
    rows = delimited_table(text, _TABLE_ANCHOR)
    parsed_rows = [_row_values(row, len(columns)) for row in rows]
    if len(parsed_rows) != declared:
        raise IncompleteOutputError(
            f"the export declares {declared} surface sections but the table "
            f"holds {len(parsed_rows)} rows; the solver stopped mid-write"
        )
    return SectionalLoadsReport(
        angle_of_attack_deg=parse_number(labeled_value(text, "Angle of attack (Deg)")),
        sideslip_deg=parse_number(labeled_value(text, "Side-slip angle (Deg)")),
        freestream_velocity_m_s=freestream,
        time_increment_s=_optional_number(text, "Time increment (sec)"),
        solver_mode=labeled_value(text, "Solver mode:"),
        current_iteration=parse_count(
            labeled_value(text, "Current solver iteration number:"),
            label="Current solver iteration number",
        ),
        reference_velocity_m_s=_optional_number(text, "Reference velocity (m/s)"),
        reference_length_m=_optional_number(text, "Reference length (m)"),
        reference_area_m2=reference_area,
        declared_section_count=declared,
        force_units=force_units,
        moment_units=moment_units,
        columns=columns,
        values=np.asarray(parsed_rows, dtype=float),
    )


def _row_values(row: Sequence[str], width: int) -> list[float]:
    """Return the numbers of one table row, refusing a hole or a wrong width.

    PYFS-009, the sectional-loads half of the same defect as read_fsidisp.
    The old reading dropped EVERY empty cell before counting, which made the
    count check unfalsifiable by a hole: "a,,b,c" left three cells and passed
    as three columns, with every value after the hole shifted one column
    left. Sectional loads are read per blade station, so a shift puts a force
    under a moment's name and the structural solve gets a plausible wrong
    load.

    Exactly ONE trailing empty cell is dropped, and that is the file format
    rather than a concession: the solver terminates every data row with the
    separator (fixture FS_SurfaceSection_Loads_call0002.txt). Interior blanks
    are holes and are refused. Split out of :func:`parse_sectional_loads`
    unchanged in 0.33.0, when the parser moved here (AD-10).
    """
    cells = list(row)
    if cells and not cells[-1].strip():
        cells.pop()
    if len(cells) != width:
        raise FsiInputError(
            f"a sectional loads row holds {len(cells)} values but the header "
            f"names {width} columns; the table layout changed"
        )
    if not all(cell.strip() for cell in cells):
        raise FsiInputError(
            f"a sectional loads row has an empty field ({','.join(cells)!r}), so a "
            "column is missing rather than zero. A blank used to be dropped before "
            "the count, which shifted every value after it one column left"
        )
    return [parse_number(cell) for cell in cells]


def _optional_number(text: str, label: str) -> float | None:
    try:
        return parse_number(labeled_value(text, label))
    except AnchorNotFoundError:
        return None
