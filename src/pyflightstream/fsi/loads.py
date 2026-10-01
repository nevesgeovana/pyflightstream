"""Sectional loads parser and elastic-axis moment transfer (WP2, DLV-007).

Pipeline role: per coupling call FlightStream's post-processing script
exports ``FS_SurfaceSection_Loads.txt`` (sectional forces in Newtons
and moments about the quarter chord); this module parses that file
(through :mod:`pyflightstream.results.sectional_loads`, where the parser
is defined since 0.33.0 and which this module re-exports), splits the
flat table into per-blade blocks, and transfers the moments
from the pitch axis to the elastic axis, delivering the aerodynamic
load set the beam solve consumes.

Everything here is anchored on the WP1 dry-run evidence
(reports/RPT-005, fixtures in ``tests/tier1_offline/fixtures/fsi/``):

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
* Blade attribution follows the family-per-blade convention
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
from pyflightstream.fsi.errors import FsiInputError

# The parser of the export and the report it returns are defined in the
# results row since 0.33.0 (AD-10), which removed the cycle between this
# module and results.tables; every name keeps importing from here.
from pyflightstream.results.sectional_loads import (
    EXPECTED_COLUMNS as EXPECTED_COLUMNS,
)
from pyflightstream.results.sectional_loads import (
    SectionalLoadsReport as SectionalLoadsReport,
)
from pyflightstream.results.sectional_loads import SectionBlock as SectionBlock
from pyflightstream.results.sectional_loads import UnitsError as UnitsError
from pyflightstream.results.sectional_loads import (
    parse_sectional_loads as parse_sectional_loads,
)

__all__ = [
    "ElasticAxisLoads",
    "SectionFamily",
    "SectionFamilyMap",
    "cross_check_totals",
    "project_rotor_frame_loads",
    "project_wing_frame_loads",
    "to_elastic_axis",
    "transfer_moment_to_elastic_axis",
]

# Fraction of the blade span the parsed section radii may exceed the
# configured [root, tip] interval before the config is rejected as not
# describing the blade the sections were cut on.
_SPAN_TOLERANCE = 0.01

# Fraction of the blade span that may be left UNCOVERED at each end
# before the resampling would be extrapolating rather than interpolating
# (REV010-008). The two constants bound opposite directions and are
# deliberately different numbers.
#
# This one is calibrated from evidence rather than chosen: a section cut
# puts the outermost section centroids inboard of the geometric ends, so
# some margin is physical and expected.
#
# Measured on the committed WP1 export
# (tests/tier1_offline/fixtures/fsi/FS_SurfaceSection_Loads_call0002.txt, blade_1
# extremes 0.2899 m and 1.813 m) against THE BLADE IT WAS CUT ON, whose
# 11 imported pitch-axis nodes are the committed fixture
# tests/tier1_offline/fixtures/fsi/structural_nodes.csv, root 0.274320 m and tip
# 1.828800 m; RPT-006 Section 2 states the same span as 0.274 to 1.829 m.
# Span 1.554480 m, so the real margins are 1.00% at the root and 1.02%
# at the tip.
#
# 5% accepts that with room and still refuses the case this finding was
# raised for, where sections covering [0.8, 1.2] m of a blade spanning
# [0.25, 1.85] m leave 34% uncovered at the root and 41% at the tip and
# are spread across the whole blade by constant extrapolation.
#
# Corrected 2026-08-03 by the V and V pass, and the correction is the
# instructive part. This comment first reported 2.49% and 2.31% and
# attributed them to "the blade it was cut on". Those numbers are exact
# for the SYNTHETIC test blade [0.25, 1.85] in
# tests/tier1_offline/test_fsi_loads.py:fixture_covering_config, which is deliberately
# wider than the physical one; roughly 60% of each quoted margin was
# that config's outward rounding rather than the section cut. The
# constant is unchanged because 5% clears the real 1.0% by more than it
# cleared the wrong number, but a tolerance justified by a measurement
# of something else is the exact defect class REV-010 was raised about.
_COVERAGE_MARGIN = 0.05


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

    Parameters
    ----------
    moment_pa_nm : numpy.ndarray
        The pitch-axis moment M_PA, positive nose up [N m, or N m / m for a density].
    force_chordwise_n : numpy.ndarray
        The chordwise force F_c [N, or N/m].
    force_normal_n : numpy.ndarray
        The normal force F_n [N, or N/m].
    ea_offset_chordwise_m : numpy.ndarray
        The chordwise offset e_c from the pitch axis to the elastic axis [m].
    ea_offset_normal_m : numpy.ndarray
        The normal offset e_n from the pitch axis to the elastic axis [m].

    Returns
    -------
    numpy.ndarray
        The elastic-axis moment M_EA = M_PA + e_c F_n - e_n F_c, in the unit of ``moment_pa_nm``.
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

    Parameters
    ----------
    fx_n_per_m : numpy.ndarray
        The cut-plane Fx force density [N/m].
    fz_n_per_m : numpy.ndarray
        The cut-plane Fz force density [N/m].
    moment_qc_nm_per_m : numpy.ndarray
        The export's quarter-chord moment density [N m / m], positive about +Z.
    blade_angle_rad : numpy.ndarray
        The local blade angle b [rad].

    Returns
    -------
    tuple of numpy.ndarray
        ``(f_chordwise, f_normal, m_nose_up)``, in N/m, N/m and N m / m.
    """
    fx = np.asarray(fx_n_per_m, dtype=float)
    fz = np.asarray(fz_n_per_m, dtype=float)
    beta = np.asarray(blade_angle_rad, dtype=float)
    chordwise = -fx * np.sin(beta) - fz * np.cos(beta)
    normal = -fx * np.cos(beta) + fz * np.sin(beta)
    return chordwise, normal, -np.asarray(moment_qc_nm_per_m, dtype=float)


def project_wing_frame_loads(
    fx_n_per_m: np.ndarray,
    fz_n_per_m: np.ndarray,
    moment_qc_nm_per_m: np.ndarray,
    section_pitch_rad: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project a wing's XZ-cut load densities onto its section axes (FSI-G).

    f_chordwise = -Fx cos b + Fz sin b (toward the leading edge),
    f_normal = Fx sin b + Fz cos b (toward the suction side), and
    m_nose_up = +Moment. The cut is the reference XZ plane in a frame with
    the reference axes (x aft, y right, z up; the wiring refuses any other),
    so ``Fx`` and ``Fz`` are the x and z force densities, and the section
    axes at nose-up pitch b are (-cos b, sin b) and (sin b, cos b) in (x, z)
    (:func:`pyflightstream.fsi.nodes.station_triads`). The moment column is
    read as positive about +y, the axis the XZ plane leaves out, as the
    rotor's XY cut is read about +z; +y turns the leading edge up on either
    wing, so it is nose up. THAT SIGN IS THE ONE READING HERE NOT YET
    CORROBORATED ON THIS CUT: the rotor's was, by the soft-blade pilot
    (RPT-007); the wing's agrees in sign at the integral on 26.124 and
    not in magnitude (+7.49 against +17.13 N m, 44 %, RPT-092).
    Inputs broadcast; densities in N/m and N m / m, angles in rad.

    Source: rigid-section geometry of the wing-frame embedding; the moment
    convention by analogy with :func:`project_rotor_frame_loads`.

    Parameters
    ----------
    fx_n_per_m : numpy.ndarray
        The x force density of the XZ cut [N/m].
    fz_n_per_m : numpy.ndarray
        The z force density of the XZ cut [N/m].
    moment_qc_nm_per_m : numpy.ndarray
        The export's quarter-chord moment density [N m / m], read as positive about +y.
    section_pitch_rad : numpy.ndarray
        The section's nose-up pitch b [rad].

    Returns
    -------
    tuple of numpy.ndarray
        ``(f_chordwise, f_normal, m_nose_up)``, in N/m, N/m and N m / m.
    """
    fx = np.asarray(fx_n_per_m, dtype=float)
    fz = np.asarray(fz_n_per_m, dtype=float)
    beta = np.asarray(section_pitch_rad, dtype=float)
    chordwise = -fx * np.cos(beta) + fz * np.sin(beta)
    normal = fx * np.sin(beta) + fz * np.cos(beta)
    return chordwise, normal, np.asarray(moment_qc_nm_per_m, dtype=float)


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

    Raises
    ------
    FsiInputError
        If the family's sections span a range other than the configured blade's, or cover too
        little of it.
    """
    stations = np.asarray(cfg.blade.station_radii_m, dtype=float)
    embedding = frame_embedding(cfg)
    # FSI-G: a wing's sections are cut on the reference XZ plane, so the
    # export's Offset is the y coordinate from the cut frame's origin, which
    # the wiring holds at the wing's own origin; a left wing's span runs
    # along -y and its stations are distances, so the sign is undone here.
    radii = (
        block.offset_m * cfg.wing.span_sign
        if embedding == "wing_frame" and cfg.wing is not None
        else block.offset_m
    )
    span = stations[-1] - stations[0]
    tolerance = _SPAN_TOLERANCE * span
    if radii.min() < stations[0] - tolerance or radii.max() > stations[-1] + tolerance:
        raise FsiInputError(
            f"the sections of family {block.family!r} span "
            f"[{radii.min():.4g}, {radii.max():.4g}] m but the configured blade "
            f"spans [{stations[0]:.4g}, {stations[-1]:.4g}] m; this configuration "
            "does not describe the blade these sections were cut on"
        )
    # REV010-008, the other side of the same interval. The check above
    # refuses sections that reach BEYOND the blade and said nothing about
    # sections that cover only part of it. Downstream, _blade_densities
    # resamples with numpy.interp, whose default is constant endpoint
    # extrapolation, so sections covering [0.8, 1.2] m were spread across a
    # blade spanning [0.25, 1.85] m: loads [10, 20] became
    # [10, 10, 16.25, 20, 20] and the structural model received an applied
    # load over a domain the evidence never covered. The logged total,
    # meanwhile, integrates only the covered interval, so the two describe
    # different fields.
    #
    # The same named tolerance bounds both directions. Constant
    # extrapolation is legitimate for the small root and tip margins a
    # section cut does not reach, which is what the resampler's docstring
    # already claimed; this is what makes the claim true.
    margin = _COVERAGE_MARGIN * span
    if radii.min() > stations[0] + margin or radii.max() < stations[-1] - margin:
        covered = (radii.max() - radii.min()) / span
        raise FsiInputError(
            f"the sections of family {block.family!r} cover "
            f"[{radii.min():.4g}, {radii.max():.4g}] m, which is {covered:.1%} of the "
            f"configured blade span [{stations[0]:.4g}, {stations[-1]:.4g}] m. The "
            "uncovered root or tip would be filled by constant extrapolation from "
            "the nearest section, so the structural model would receive an applied "
            "load over a domain these loads never measured, while the logged "
            "integral covers only the measured interval: the two would describe "
            "different fields. Export sections over the whole blade, or configure "
            "the blade these sections were cut on (the margin allowed at each end "
            f"is {_COVERAGE_MARGIN:.0%} of span)"
        )
    e_chordwise = np.interp(radii, stations, cfg.blade.elastic_axis_offset_chordwise_m)
    e_normal = np.interp(radii, stations, cfg.blade.elastic_axis_offset_normal_m)
    ascending = radii if radii[0] <= radii[-1] else radii[::-1]
    widths = _tributary_widths(ascending)
    if radii[0] > radii[-1]:
        widths = widths[::-1]
    if embedding == "rotor_frame":
        beta = np.radians(np.interp(radii, stations, cfg.blade.geometric_pitch_deg))
        chordwise, normal, moment_pa = project_rotor_frame_loads(
            block.fx_n_per_m, block.fz_n_per_m, block.moment_qc_nm_per_m, beta
        )
    elif embedding == "wing_frame":
        beta = np.radians(np.interp(radii, stations, cfg.blade.geometric_pitch_deg))
        chordwise, normal, moment_pa = project_wing_frame_loads(
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

    Raises
    ------
    FsiInputError
        If a component's integrated density disagrees with the export's total beyond ``rel_tol``.
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
            raise FsiInputError(
                f"the sectional {name.upper()} of family {block.family!r} "
                f"integrates to {total:.6g} N but the integrated export reports "
                f"{integrated:.6g} N ({deltas[name]:.2%} apart, tolerance "
                f"{rel_tol:.2%}); the sections do not cover the boundary, the "
                "attribution is wrong, or the per-span unit finding (RPT-006) "
                "no longer holds"
            )
    return deltas
