"""Results into engineering data.

Pipeline role: assembles parsed results into sweep tables and labeled
arrays, applies axis transformations, performs blade-passage averaging
for unsteady runs, and writes flow-visualization exports. Implemented
incrementally: the probe-data writers (VTK legacy ASCII and Tecplot
ASCII, :mod:`pyflightstream.post.writers`) are the first inhabitants;
the ``ResultArray`` facade (``interp_along``, ``reparametrize``,
``trim``) stays planned.
"""

from pyflightstream.post.writers import (
    dataset_to_points,
    write_tecplot_points,
    write_vtk_points,
)

__all__ = ["write_vtk_points", "write_tecplot_points", "dataset_to_points"]
