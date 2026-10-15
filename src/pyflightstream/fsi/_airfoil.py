"""Shared analytic airfoil contour used by geometry and structural inputs."""

import numpy as np


def naca4_contour(naca: str, n_chord: int) -> np.ndarray:
    """Return the closed NACA 4-digit section contour in unit-chord axes.

    The analytic thickness polynomial uses the closed-trailing-edge
    variant (last coefficient -0.1036), so the surface can be meshed
    watertight. Chordwise stations are cosine spaced, clustering points
    at the leading and trailing edges.

    Parameters
    ----------
    naca : str
        Four-digit designation, for example ``"2412"``.
    n_chord : int
        Panels per side; the contour has ``2 * n_chord + 1`` points.

    Returns
    -------
    numpy.ndarray
        Shape ``(2 * n_chord + 1, 2)`` array of (x/c, z/c) points,
        traversing the lower surface from the trailing edge to the
        leading edge and the upper surface back; first and last point
        are both the trailing edge, so the polygon is closed.

    Examples
    --------
    >>> contour = naca4_contour("0012", 21)
    >>> contour.shape, float(contour[0, 0])
    ((43, 2), 1.0)
    """
    m = int(naca[0]) / 100.0
    p = int(naca[1]) / 10.0
    t = int(naca[2:]) / 100.0
    beta = np.linspace(0.0, np.pi, n_chord + 1)
    x = 0.5 * (1.0 - np.cos(beta))  # 0 (leading edge) to 1 (trailing edge)
    half_thickness = (
        5.0 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4)
    )
    camber = np.zeros_like(x)
    slope = np.zeros_like(x)
    if m > 0.0:
        front = x < p
        camber[front] = m / p**2 * (2.0 * p * x[front] - x[front] ** 2)
        slope[front] = 2.0 * m / p**2 * (p - x[front])
        rear = ~front
        camber[rear] = m / (1.0 - p) ** 2 * (1.0 - 2.0 * p + 2.0 * p * x[rear] - x[rear] ** 2)
        slope[rear] = 2.0 * m / (1.0 - p) ** 2 * (p - x[rear])
    theta = np.arctan(slope)
    upper = np.column_stack(
        (x - half_thickness * np.sin(theta), camber + half_thickness * np.cos(theta))
    )
    lower = np.column_stack(
        (x + half_thickness * np.sin(theta), camber - half_thickness * np.cos(theta))
    )
    return np.vstack((lower[::-1], upper[1:]))
