"""Sectional loads parser and elastic-axis moment transfer (WP2, DLV-007).

Pipeline role: per coupling call FlightStream's post-processing script
exports ``FS_SurfaceSection_Loads.txt`` (sectional forces in Newtons
and moments about the quarter chord); this module parses that file,
splits the flat table into per-blade blocks, and transfers the moments
from the pitch axis to the elastic axis, delivering the aerodynamic
load set the beam solve consumes.

Everything here is anchored on the WP1 dry-run evidence
(reports/RPT-005, fixtures in ``tests/fixtures/fsi/``):

* The file carries the standard labeled FlightStream header; the SI
  assertion (FSI-R03) anchors on the unit-carrying labels
  (``Freestream velocity (m/s)``, ``Reference area (m^2)``) and on the
  ``Force Units`` / ``Moment Units`` footer, which must read Newtons
  and Newton-Meter because the post-processing script computes the
  loads with ``COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS``.
* The data table is ``Offset, Chord, X_QC, Z_QC, Fx, Fz, Moment`` per
  section; the moment is about the quarter chord, the pitch axis
  reference of DLV-007 Section 4.3. The rows are line densities along
  the span: despite the footer naming the computation unit (Newtons
  versus coefficients), integrating the force columns over the
  tributary widths reproduces the integrated axial force of the same
  run to a few percent, while summing them overshoots by the inverse
  width (WP7 near-rigid pilot evidence, RPT-006). Forces are therefore
  [N/m] and moments [N m / m], and the totals cross-check integrates,
  never sums.
* Section-plane axes, on the same pilot evidence: the export ``Fx``
  is the axial (rotor axis) component, invariant under the blade
  rotation and matching the integrated Cx, and ``Fz`` is the in-plane
  component in the rotating blade frame. The mapping onto the
  chordwise/normal axes of :mod:`pyflightstream.fsi.config` therefore
  involves the local blade angle; the deliberate elastic-axis offset
  check of the soft-blade pilot is the planned sign confirmation.
* Blade attribution follows the author's family-per-blade convention
  (RPT-005 finding 6): one geometry family per blade, one section
  distribution per blade boundary, and the flat export concatenates
  the families in creation order. Attribution is therefore bookkeeping
  owned by the code that creates the distributions, serialized as a
  :class:`SectionFamilyMap`; the offset and chord discontinuities at
  the block boundaries are the parser's cross-check.

Unlike the loads spreadsheet, this export's footer carries no version
or build line (observed in the committed fixtures); build traceability
of a coupled run lives in the run manifest (FR-19).

Parsing is anchor-based on the primitives of
:mod:`pyflightstream.results` (FR-16): labels and header rows, never
line offsets, and a missing structural terminator raises instead of
returning a silently shorter table (FR-17).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pyflightstream.fsi.config import FsiConfig, frame_embedding
from pyflightstream.results import (
    AnchorNotFoundError,
    IncompleteOutputError,
    delimited_table,
    labeled_value,
    parse_number,
)

_TABLE_ANCHOR = "Offset,"
EXPECTED_COLUMNS = ("Offset", "Chord", "X_QC", "Z_QC", "Fx", "Fz", "Moment")
# Fraction of the blade span the parsed section radii may exceed the
# configured [root, tip] interval before the config is rejected as not
# describing the blade the sections were cut on.
_SPAN_TOLERANCE = 0.01


class UnitsError(ValueError):
    """The export does not carry the asserted SI units (FSI-R03).

    Unit errors in the coupling loop are silent and produce plausible
    wrong answers, so the parser refuses the file instead of scaling:
    the post-processing script must compute the sectional loads with
    ``COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS`` and the solver setup
    must stay in SI.
    """


class SectionFamily(BaseModel):
    """One section distribution of the flat export, in creation order.

    Attributes
    ----------
    name : str
        Family label, for example the blade name; unique within a map.
    count : int
        Number of sections the distribution creates (its block size in
        the flat export).
    is_blade : bool
        Whether the family is a blade the structural solve consumes;
        non-blade families (a hub, a nacelle) are split and
        cross-checked but never fed to a beam.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    count: int = Field(ge=1)
    is_blade: bool = True


class SectionFamilyMap(BaseModel):
    """Creation-order bookkeeping of the section distributions.

    The flat loads export concatenates the per-boundary families in
    creation order (RPT-005 finding 6), so the code that creates the
    distributions is the single source of truth for attribution. That
    code emits this map; the parser only splits and cross-checks.

    Attributes
    ----------
    families : list of SectionFamily
        Families in creation order.
    """

    model_config = ConfigDict(extra="forbid")

    families: list[SectionFamily] = Field(min_length=1)

    @field_validator("families")
    @classmethod
    def _unique_names(cls, families: list[SectionFamily]) -> list[SectionFamily]:
        """Attribution by name requires unique family names."""
        names = [family.name for family in families]
        if len(set(names)) != len(names):
            raise ValueError(
                "family names must be unique; a duplicated name makes the "
                f"per-blade attribution ambiguous (got {names})"
            )
        return families

    @classmethod
    def uniform(cls, blade_count: int, sections_per_blade: int) -> SectionFamilyMap:
        """Build the map of identical per-blade distributions.

        Parameters
        ----------
        blade_count : int
            Number of blades, one family each, created in blade order.
        sections_per_blade : int
            Sections of every distribution.
        """
        return cls(
            families=[
                SectionFamily(name=f"blade_{i + 1}", count=sections_per_blade)
                for i in range(blade_count)
            ]
        )

    @property
    def total_sections(self) -> int:
        """Sum of the family block sizes."""
        return sum(family.count for family in self.families)


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

    def split(self, family_map: SectionFamilyMap) -> dict[str, SectionBlock]:
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
            raise ValueError(
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
        raise ValueError(
            f"the sectional loads table names columns {columns}, expected "
            f"{EXPECTED_COLUMNS}; the layout changed and the blade-frame "
            "mapping of the force columns must be re-verified before parsing"
        )
    declared = int(parse_number(labeled_value(text, "Number of Surface Sections:")))
    rows = delimited_table(text, _TABLE_ANCHOR)
    parsed_rows: list[list[float]] = []
    for row in rows:
        cells = [cell for cell in row if cell]
        if len(cells) != len(columns):
            raise ValueError(
                f"a sectional loads row holds {len(cells)} values but the header "
                f"names {len(columns)} columns; the table layout changed"
            )
        parsed_rows.append([parse_number(cell) for cell in cells])
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
        current_iteration=int(
            parse_number(labeled_value(text, "Current solver iteration number:"))
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


def _optional_number(text: str, label: str) -> float | None:
    try:
        return parse_number(labeled_value(text, label))
    except AnchorNotFoundError:
        return None


def transfer_moment_to_elastic_axis(
    moment_pa_nm: np.ndarray,
    force_chordwise_n: np.ndarray,
    force_normal_n: np.ndarray,
    ea_offset_chordwise_m: np.ndarray,
    ea_offset_normal_m: np.ndarray,
) -> np.ndarray:
    """Transfer a sectional pitch-axis moment to the elastic axis.

    M_EA = M_PA + e_c F_n - e_n F_c: the spanwise component of
    M_PA + e x F for the section-plane offset e = (e_c, e_n) from the
    pitch axis to the elastic axis and the section force
    F = (F_c, F_n), in the right-handed blade triad of
    :mod:`pyflightstream.fsi.config` (chordwise toward the leading
    edge, normal completing the triad, moments positive nose up about
    the spanwise axis). All inputs broadcast. The identity holds per
    unit span exactly as for totals, so it applies unchanged to the
    line densities of the sectional export (forces in N/m, moments in
    N m / m, offsets in m).

    Source: DLV-007 Section 4.3 (FSI-R04); pitch-axis moment reference
    confirmed by the WP1 dry run (reports/RPT-005 finding 4).
    """
    return (
        np.asarray(moment_pa_nm, dtype=float)
        + np.asarray(ea_offset_chordwise_m, dtype=float) * np.asarray(force_normal_n, dtype=float)
        - np.asarray(ea_offset_normal_m, dtype=float) * np.asarray(force_chordwise_n, dtype=float)
    )


def project_rotor_frame_loads(
    fx_n_per_m: np.ndarray,
    fz_n_per_m: np.ndarray,
    moment_qc_nm_per_m: np.ndarray,
    blade_angle_rad: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project cut-plane load densities onto the section axes (rotor frame).

    f_chordwise = -Fx sin b - Fz cos b (toward the leading edge),
    f_normal = -Fx cos b + Fz sin b (toward the suction side), and
    m_nose_up = -Moment. In the rotor import frame (X axial, Y
    in-plane, Z span; RPT-006 finding 3) the section chordwise and
    suction directions at local blade angle b are (-sin b, -cos b) and
    (-cos b, sin b); nose-up is the rotation about -Z for this
    geometry, and the export's moment column is positive about +Z,
    physically nose-down (the dry-run fixture's +7 to +13 N m/m match
    the nose-down |Cm| q c^2 of the cambered generic section). The
    sign is corroborated by the soft-blade pilot response (RPT-007).
    Inputs broadcast; densities in N/m and N m / m, angles in rad.

    Source: rigid-section geometry of the rotor-frame embedding
    (RPT-006 finding 3); load assembly of DLV-007 Section 4.2.
    """
    fx = np.asarray(fx_n_per_m, dtype=float)
    fz = np.asarray(fz_n_per_m, dtype=float)
    beta = np.asarray(blade_angle_rad, dtype=float)
    chordwise = -fx * np.sin(beta) - fz * np.cos(beta)
    normal = -fx * np.cos(beta) + fz * np.sin(beta)
    return chordwise, normal, -np.asarray(moment_qc_nm_per_m, dtype=float)


@dataclass(frozen=True)
class ElasticAxisLoads:
    """Per-section aerodynamic load densities of one blade, about its EA.

    All arrays share the block's section count and are line densities
    along the span (RPT-006), ready for the beam's distributed-load
    interface; the tributary widths integrate them back to totals.

    Attributes
    ----------
    radius_m : numpy.ndarray
        Section radii [m] from the rotation axis along the pitch axis.
    chord_m : numpy.ndarray
        Local chords [m].
    force_chordwise_n_per_m : numpy.ndarray
        Chordwise force densities [N/m] (export Fx column; see
        :func:`to_elastic_axis` for the axes caveat).
    force_normal_n_per_m : numpy.ndarray
        Normal (flap-direction) force densities [N/m] (export Fz).
    moment_pa_nm_per_m : numpy.ndarray
        Moment densities about the pitch axis [N m / m], as exported.
    moment_ea_nm_per_m : numpy.ndarray
        Moment densities about the elastic axis [N m / m] (FSI-R04).
    ea_offset_chordwise_m, ea_offset_normal_m : numpy.ndarray
        Interpolated elastic-axis offsets e(r) [m] used in the
        transfer.
    tributary_width_m : numpy.ndarray
        Spanwise width [m] of each section's midpoint strip;
        integrates the densities back to totals for cross-checks.
    """

    radius_m: np.ndarray
    chord_m: np.ndarray
    force_chordwise_n_per_m: np.ndarray
    force_normal_n_per_m: np.ndarray
    moment_pa_nm_per_m: np.ndarray
    moment_ea_nm_per_m: np.ndarray
    ea_offset_chordwise_m: np.ndarray
    ea_offset_normal_m: np.ndarray
    tributary_width_m: np.ndarray

    @property
    def flap_load_n_per_m(self) -> np.ndarray:
        """Normal force densities [N/m] at the section radii."""
        return self.force_normal_n_per_m

    @property
    def torsion_moment_nm_per_m(self) -> np.ndarray:
        """Elastic-axis moment densities [N m / m] at the section radii."""
        return self.moment_ea_nm_per_m


def _tributary_widths(radii: np.ndarray) -> np.ndarray:
    """Midpoint strip widths of sorted section radii (sum = span covered)."""
    edges = np.concatenate(([radii[0]], 0.5 * (radii[1:] + radii[:-1]), [radii[-1]]))
    return np.diff(edges)


def to_elastic_axis(block: SectionBlock, cfg: FsiConfig) -> ElasticAxisLoads:
    """Transfer one blade block to elastic-axis load densities (FSI-R04).

    The elastic-axis offsets e(r) come from the configuration,
    interpolated linearly at the section radii, so refining the
    elastic axis estimate never touches the FlightStream setup
    (DLV-007 Section 4.3).

    Axes (RPT-006 finding 3): the export columns are the cut-plane
    axes. At Omega zero (``section_frame`` embedding, the wing case)
    they are the section chordwise/normal axes and pass through
    unchanged. On a spinning blade (``rotor_frame``) they are the
    axial and in-plane axes, so the loads are projected onto the
    section axes with the local blade angle interpolated from the
    geometric pitch distribution
    (:func:`project_rotor_frame_loads`); the embedding rule is shared
    with the node generator through
    :func:`pyflightstream.fsi.config.frame_embedding`, so loads and
    displacements always live in the same triad.

    Parameters
    ----------
    block : SectionBlock
        One blade family from :meth:`SectionalLoadsReport.split`.
    cfg : FsiConfig
        Configuration whose blade the sections were cut on.

    Returns
    -------
    ElasticAxisLoads
        Load densities about the elastic axis at the section radii,
        in section components.
    """
    stations = np.asarray(cfg.blade.station_radii_m, dtype=float)
    radii = block.offset_m
    span = stations[-1] - stations[0]
    tolerance = _SPAN_TOLERANCE * span
    if radii.min() < stations[0] - tolerance or radii.max() > stations[-1] + tolerance:
        raise ValueError(
            f"the sections of family {block.family!r} span "
            f"[{radii.min():.4g}, {radii.max():.4g}] m but the configured blade "
            f"spans [{stations[0]:.4g}, {stations[-1]:.4g}] m; this configuration "
            "does not describe the blade these sections were cut on"
        )
    e_chordwise = np.interp(radii, stations, cfg.blade.elastic_axis_offset_chordwise_m)
    e_normal = np.interp(radii, stations, cfg.blade.elastic_axis_offset_normal_m)
    ascending = radii if radii[0] <= radii[-1] else radii[::-1]
    widths = _tributary_widths(ascending)
    if radii[0] > radii[-1]:
        widths = widths[::-1]
    if frame_embedding(cfg) == "rotor_frame":
        beta = np.radians(np.interp(radii, stations, cfg.blade.geometric_pitch_deg))
        chordwise, normal, moment_pa = project_rotor_frame_loads(
            block.fx_n_per_m, block.fz_n_per_m, block.moment_qc_nm_per_m, beta
        )
    else:
        chordwise, normal = block.fx_n_per_m, block.fz_n_per_m
        moment_pa = block.moment_qc_nm_per_m
    return ElasticAxisLoads(
        radius_m=radii,
        chord_m=block.chord_m,
        force_chordwise_n_per_m=chordwise,
        force_normal_n_per_m=normal,
        moment_pa_nm_per_m=moment_pa,
        moment_ea_nm_per_m=transfer_moment_to_elastic_axis(
            moment_pa, chordwise, normal, e_chordwise, e_normal
        ),
        ea_offset_chordwise_m=e_chordwise,
        ea_offset_normal_m=e_normal,
        tributary_width_m=widths,
    )


def cross_check_totals(
    block: SectionBlock,
    integrated_fx_n: float,
    integrated_fz_n: float,
    rel_tol: float = 0.05,
) -> dict[str, float]:
    """Cross-check a block's integrated densities against total forces.

    The force densities integrated over the tributary widths must
    reproduce the loads FlightStream reports for the same boundary in
    the same run, in Newtons and in a comparable frame component
    (RPT-006: the axial component is the frame-invariant one for a
    rotating blade); a disagreement beyond ``rel_tol`` means the
    sections do not cover the boundary, the attribution is wrong, or
    the per-span unit finding no longer holds, and raises instead of
    letting a mis-scaled load set into the structural solve.

    Parameters
    ----------
    block : SectionBlock
        One family block.
    integrated_fx_n, integrated_fz_n : float
        Integrated forces [N] of the matching boundary from the same
        run, in the components matching the export axes.
    rel_tol : float
        Allowed relative disagreement, on the larger of the compared
        magnitudes; the default reflects the few-percent closure of
        the pilot evidence (tip and root strips, frame effects).

    Returns
    -------
    dict of str to float
        Relative deltas per component (``"fx"``, ``"fz"``).
    """
    ascending = np.sort(block.offset_m)
    widths = _tributary_widths(ascending)
    order = np.argsort(block.offset_m)
    deltas: dict[str, float] = {}
    for name, density, integrated in (
        ("fx", block.fx_n_per_m, integrated_fx_n),
        ("fz", block.fz_n_per_m, integrated_fz_n),
    ):
        total = float((density[order] * widths).sum())
        scale = max(abs(total), abs(integrated), 1e-9)
        deltas[name] = abs(total - integrated) / scale
        if deltas[name] > rel_tol:
            raise ValueError(
                f"the sectional {name.upper()} of family {block.family!r} "
                f"integrates to {total:.6g} N but the integrated export reports "
                f"{integrated:.6g} N ({deltas[name]:.2%} apart, tolerance "
                f"{rel_tol:.2%}); the sections do not cover the boundary, the "
                "attribution is wrong, or the per-span unit finding (RPT-006) "
                "no longer holds"
            )
    return deltas
