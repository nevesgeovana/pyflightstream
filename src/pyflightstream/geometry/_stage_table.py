"""The stage table of the geometry pipeline: ids, names, checks and where each limit lives.

Pipeline role: pure data of the geometry package. The runner
(:mod:`pyflightstream.workspace._geom_run`) executes stages by id, the ``stages`` verb of
``pyfs-geom`` prints this table, and a stage record names its checks from it. A stage that needs
the geometry kernel is marked, so a run that stops at the last pure stage imports none.
``limit`` is the sentence that says where the check's limit comes from, never a second copy of
the number: the number lives with the stage that measures it.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyflightstream._errors import InputValueError

__all__ = ["STAGE_ROWS", "StageRow", "stage_index", "stage_row"]


@dataclass(frozen=True)
class StageRow:
    """One stage: its id, its name, whether it needs the kernel, and its checks.

    ``checks`` is a tuple of ``(check id, limit)`` pairs; ``limit`` states where the limit is
    taken from.
    """

    stage: str
    name: str
    kernel: bool
    checks: tuple[tuple[str, str], ...]


def _row(stage, name, kernel, *checks):
    return StageRow(stage, name, kernel, tuple(checks))


STAGE_ROWS: tuple[StageRow, ...] = (
    _row("S0", "Definition", False, ("input.valid", "no refused key")),
    _row(
        "S1",
        "Section law",
        False,
        ("section.residual", "acceptance.section_residual"),
        ("section.one_nose_radius", "acceptance"),
        ("section.te_thickness", "acceptance"),
        ("section.inflection", "acceptance"),
    ),
    _row("S2", "Identity report", False, ("identity.listed", "every seed listed")),
    _row(
        "S3",
        "Compatibility",
        False,
        ("compat.common_vector", "identical knots and pins"),
        ("compat.shape_unchanged", "1e-9 of the chord"),
    ),
    _row(
        "S4",
        "Planform or body law",
        False,
        ("law.fewest_stations", "acceptance"),
        ("law.monotonic", "acceptance"),
        ("law.ruled_twist", "acceptance"),
        ("law.region_boundaries", "acceptance"),
    ),
    _row("S5", "Placement", False, ("place.frame", "acceptance")),
    _row(
        "S6",
        "Skin",
        False,
        ("skin.section_exact", "1e-12 m"),
        ("skin.law_residual", "acceptance"),
        ("skin.distance", "acceptance, when an original exists"),
    ),
    _row(
        "S7",
        "Trims and layout",
        False,
        ("trim.closed", "1e-12 in parameter units"),
        ("trim.in_domain", "domain of the skin"),
        ("trim.iso_exact", "axis-aligned"),
        ("trim.partition", "1e-9 relative"),
        ("trim.outer_only", "warning"),
    ),
    _row(
        "S8",
        "Closures",
        False,
        ("closure.rim_shared", "1e-12 m"),
        ("closure.rim_jump", "acceptance"),
        ("closure.base_present", "acceptance"),
        ("closure.no_ridge", "acceptance"),
        ("closure.retracted_identity", "acceptance"),
    ),
    # Sub-steps of S8 for the blend pieces (G6R), each with its own measured checks.
    _row(
        "S8.F1",
        "Fillet build",
        False,
        ("fillet.spine", "every section finds the hosts' intersection"),
        ("closure.tangent_host", "1 deg, geometry._fillet.TANGENT_LIMIT_DEG"),
        ("closure.tangent_wing", "1 deg, geometry._fillet.TANGENT_LIMIT_DEG"),
        ("closure.contact_gap_host", "body tolerance, 1e-4 of its length by default"),
        ("closure.contact_gap_wing", "body tolerance, 1e-4 of its length by default"),
    ),
    _row(
        "S8.F2",
        "Fillet trim by host",
        False,
        ("closure.base_present", "the base runs past both contact lines"),
        ("fillet.host_footprint", "2e-2 relative, geometry._fillet.FOOTPRINT_LIMIT"),
    ),
    _row(
        "S8.F3",
        "Fillet closure",
        False,
        ("closure.free_edges", "the two trailing-edge ends"),
    ),
    _row(
        "S8.B1",
        "Blister build",
        False,
        ("section.residual", "body tolerance, 1e-4 of its length by default"),
        ("continuity.bluff_jump", "1 deg, geometry._blister.SEAM_LIMIT_DEG"),
    ),
    _row(
        "S8.B2",
        "Blister trim by host",
        False,
        ("closure.base_present", "every section enters the host"),
        ("blister.crease_on_host", "1e-9 m"),
        ("trim.closed", "1e-12 in parameter units"),
        ("trim.in_domain", "domain of the base"),
        ("trim.area_removed", "1e-2 relative, geometry._blister.AREA_REMOVED_LIMIT"),
    ),
    _row(
        "S8.B3",
        "Blister closure",
        False,
        ("closure.free_edges", "none: poles at the tips, symmetry plane at the keel"),
    ),
    _row(
        "S9",
        "Continuity",
        False,
        ("continuity.bluff_jump", "1 deg or a declared crease"),
        ("continuity.internal", "reported"),
    ),
    _row(
        "S10",
        "Junctions",
        True,
        ("junction.no_triple_edge", "acceptance"),
        ("junction.no_vertex_inside", "acceptance"),
        ("junction.curve_gap", "acceptance"),
        ("junction.single_curve", "one curve per junction"),
        ("junction.shared_vertex", "acceptance"),
        ("coverage.skin", "acceptance.coverage_fraction"),
    ),
    _row(
        "S11",
        "Export",
        True,
        ("profile.surfaces_only", "no solid entity"),
        ("profile.reader", "reader profile"),
        ("profile.base_shared", "1e-12 m"),
        ("manifest.piece_version", "version of each piece"),
        ("reimport.each_component", "every component reads back"),
        ("area.read_back", "1e-3 relative"),
    ),
    _row(
        "S12",
        "Reader gate",
        False,
        ("gate.conformal", "reader profile"),
        ("gate.te_found", "reader profile"),
    ),
    _row(
        "S13",
        "Round trip",
        True,
        ("roundtrip.same_surface", "equal surface_id"),
        ("roundtrip.identify", "acceptance"),
    ),
)

_BY_ID = {row.stage: row for row in STAGE_ROWS}


def stage_row(stage: str) -> StageRow:
    """Return the row of ``stage``, refusing an id the table does not hold."""
    try:
        return _BY_ID[stage]
    except KeyError:
        raise InputValueError(
            f"stage {stage!r}: unknown; the stages are {', '.join(_BY_ID)}"
        ) from None


def stage_index(stage: str) -> int:
    """Return the position of ``stage`` in the table, refusing an unknown id."""
    return STAGE_ROWS.index(stage_row(stage))
