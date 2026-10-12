"""Probe geometry, the one home: survey lattices, planar grids, layouts and emission.

Pipeline role: the only place where probe positions are computed (FR-459). A
facade over :mod:`.lattice` (the cylindrical survey lattice of the far-field
extraction, DLV-006 Sec. 2), :mod:`.layouts` (the line, rectangle and circle
layouts of a ``[[probes]]`` entry, the lattice shape and the far-field plane),
:mod:`.planar` (the planar probe planner's types) and :mod:`.geometry` (the
geometry gate and the inside-the-body check); the script lines and the import
csv that create and export probes are :mod:`.layouts`' too.
"""

from __future__ import annotations

from pyflightstream.probes.errors import ProbeGeometryError
from pyflightstream.probes.lattice import ProbeLattice, build_lattice
from pyflightstream.probes.layouts import (
    circle_points,
    emit_probe_export,
    emit_probe_import,
    emit_probe_points,
    farfield_plane,
    lattice_points,
    line_points,
    rectangle_points,
    write_points_csv,
    write_probe_csv,
)
from pyflightstream.probes.planar import (
    AxisSpec,
    FrameDefinition,
    GeometryGateReport,
    PlanarProbeGrid,
    PlannedProbes,
    RefinementBand,
)

__all__ = [
    "ProbeGeometryError",
    "ProbeLattice",
    "build_lattice",
    "emit_probe_points",
    "emit_probe_import",
    "emit_probe_export",
    "write_probe_csv",
    "write_points_csv",
    "FrameDefinition",
    "AxisSpec",
    "RefinementBand",
    "PlanarProbeGrid",
    "GeometryGateReport",
    "PlannedProbes",
    "circle_points",
    "farfield_plane",
    "lattice_points",
    "line_points",
    "rectangle_points",
]
