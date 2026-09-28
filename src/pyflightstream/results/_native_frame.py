"""The translation's native node match, made in the loads frame the VTK was written in.

Pipeline role: the results layer's private helper for
:func:`pyflightstream.results.surface.translate_vtk_surface`. It is a private
module rather than a private name in :mod:`pyflightstream.results.native_surface`
so that no module imports an underscore-private name out of a public sibling.
"""

from __future__ import annotations

import numpy as np

from pyflightstream.results.native_surface import attach_native_strength
from pyflightstream.results.surface import SurfaceFrame, VtkSurface


def _strength_in_loads_frame(
    surface: VtkSurface, native: VtkSurface, frame: SurfaceFrame
) -> tuple[np.ndarray, dict[str, object]]:
    """Match a native export to a VTK in the LOADS frame the VTK was written in.

    This is the one home of the translation's tolerance rule, which differs
    deliberately from the default of :func:`attach_native_strength` (GOAL-034
    Q8 QA3-2, QA7-2). That default serves a caller holding two surfaces in the
    reference frame and knowing nothing of how either was written, so it allows
    four single-precision epsilons of the coordinates' magnitude. The
    translation knows the VTK was written at single precision in ``frame``, so
    it carries the native into that frame, ``R (p - o)``, and allows each loads
    axis exactly the rounding written along it: half the float32 spacing of the
    written coordinates, plus the double-precision rounding of the carry,
    floored at 1e-6 of the native's diagonal extent. Matching in the reference
    frame instead had to carry the loads rounding through ``|R|``, which for a
    turned frame far from the origin gave every reference axis most of the far
    axis's rounding: 45 degrees and 1e6 away, a native moved 0.02 along loads
    Y, where the VTK rounds by 1e-7, still matched (GOAL-034 Q8 CXQ8R7-1).

    Parameters
    ----------
    surface : VtkSurface
        The VTK as the solver wrote it, in the loads frame.
    native : VtkSurface
        The native export, in the reference frame.
    frame : SurfaceFrame
        The loads frame, as the script placed it.

    Returns
    -------
    numpy.ndarray
        The native strength, one value per node of ``surface`` in its order.
    dict
        The mapping record of :func:`attach_native_strength`, its tolerances
        along the LOADS axes, which ``coordinate_tolerance_frame`` names.
    """
    origin = np.asarray(frame.origin, dtype=float)
    rotation = frame.rotation
    carry = np.abs(rotation)
    in_loads = VtkSurface(
        points=(native.points - origin) @ rotation.T,
        offsets=native.offsets,
        connectivity=native.connectivity,
        point_data=dict(native.point_data),
        title=native.title,
    )
    extent = float(np.linalg.norm(np.ptp(native.points, axis=0)))
    loads_rounding = (
        0.5 * np.abs(np.spacing(surface.points.astype(np.float32))).astype(float)
    ).max(axis=0, initial=0.0)
    arithmetic_rounding = (
        8.0
        * float(np.finfo(float).eps)
        * (
            (np.abs(native.points).max(axis=0, initial=0.0) + np.abs(origin)) @ carry.T
            + np.abs(surface.points).max(axis=0, initial=0.0)
        )
    )
    tolerance = np.maximum(max(1e-10, extent * 1e-6), loads_rounding + arithmetic_rounding)
    matched, mapping = attach_native_strength(surface, in_loads, coordinate_tolerance=tolerance)
    mapping["coordinate_tolerance_frame"] = frame.record()
    return matched.point_data["Singularity_strength"], mapping
