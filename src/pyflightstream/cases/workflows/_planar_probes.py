"""Planar probe declaration adapter; no licensed mesh export is launched here."""

from pathlib import Path

from pyflightstream.cases import CampaignConfigError, ProbesSpec, SimCase
from pyflightstream.probes.geometry import apply_geometry_gate, load_surface_mesh, points_inside


def planar_points(case: SimCase, probes: ProbesSpec, native_per_m: float) -> list[list[float]]:
    """Place declared grids and refuse added refinement nodes inside the body."""
    if not probes.grids:
        return []
    source = Path(case.geometry) if case.geometry else None
    if source is not None and source.suffix.lower() == ".fsm":
        source = source.with_suffix(".surface.stl")
        if not source.is_file():
            raise CampaignConfigError(
                f"Planar probes need surface mesh export {source.name}; export the FSM mesh "
                "on the licensed machine before plan. Planning does not launch the solver."
            )
    mesh = None
    if source is not None and source.suffix.lower() in {".stl", ".obj"}:
        mesh = load_surface_mesh(source, require_watertight=False)
        mesh.vertices = mesh.vertices / native_per_m
    points: list[list[float]] = []
    for grid in probes.grids:
        planned = apply_geometry_gate(grid, mesh=mesh, cull=False)
        native = planned.points * native_per_m
        added = native[grid.point_count :]
        if len(added) and source is not None:
            inside = points_inside(added, mesh_path=source)
            if not inside.checked:
                raise CampaignConfigError(
                    f"Planar refinement cannot check added points: {inside.reason}. "
                    "Supply a closed surface mesh and the geometry extra."
                )
            if inside.inside.any():
                raise CampaignConfigError(
                    "Planar refinement adds points inside the body; change the grid or band."
                )
        points.extend(native.tolist())
    return points
