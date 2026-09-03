"""Results into engineering data.

Pipeline role: the top of the pipeline, where parsed solver output
becomes something a report can carry. FOUR inhabitants today, and the
list is what EXISTS rather than what is planned. Two are reached
through this package and two through their own module, which is stated
rather than left to be discovered:

* :mod:`pyflightstream.post.writers` writes flow-visualization exports
  (VTK legacy ASCII and Tecplot ASCII), each beside a settings record
  that lets the file be read alone. Re-exported here;
* :mod:`pyflightstream.post.unsteady` reads a per-timestep field export
  back as an ordered series and averages it over a blade passage.
  Re-exported here;
* :mod:`pyflightstream.post.products` writes the campaign's CSV products,
  the polar table per group, the sections table and the plots table per
  point, from the collected exports and the manifest (PFS-2029.15).
* :mod:`pyflightstream.post.reductions` is the writing seam that keeps
  a reduction from overwriting the file it came from. Re-exported
  here, and it was the one this list omitted while naming the module
  below, which this package does NOT re-export;
* :mod:`pyflightstream.post.settings_table` projects a solver-flag
  snapshot into an all-numeric table, for tools that cannot read
  strings. Imported from its own module, because the projection is
  optional and lossy and a reader should meet its page first.

WHAT THIS LAYER DOES NOT HAVE, said plainly because this docstring
advertised it for three releases and a reader has no other way to find
out. There is no ``ResultArray`` facade: no ``interp_along``, no
``reparametrize``, no ``trim``. FR-20 carries that promise and is
``pending``; AD-06 sends the interpolation half to the sister library.
Sweep assembly is not here either, it is
:mod:`pyflightstream.results.tables`.
"""

from pyflightstream.post.products import (
    ProductError,
    ReferenceValues,
    read_csv_table,
    write_campaign_products,
    write_csv_table,
    write_plots_table,
    write_polar_table,
    write_recorded_polar,
    write_sections_table,
)
from pyflightstream.post.reductions import write_reduction, write_series
from pyflightstream.post.unsteady import (
    FrameAverage,
    TimestepSeries,
    blade_passage_average,
    passage_windows,
    read_timestep_series,
)
from pyflightstream.post.writers import (
    OutputProvenance,
    dataset_to_points,
    settings_records,
    write_tecplot_points,
    write_vtk_points,
)
from pyflightstream.workspace import register_post_stage

__all__ = [
    "FrameAverage",
    "OutputProvenance",
    "ProductError",
    "ReferenceValues",
    "TimestepSeries",
    "blade_passage_average",
    "dataset_to_points",
    "passage_windows",
    "read_timestep_series",
    "settings_records",
    "read_csv_table",
    "write_campaign_products",
    "write_csv_table",
    "write_plots_table",
    "write_polar_table",
    "write_recorded_polar",
    "write_reduction",
    "write_sections_table",
    "write_series",
    "write_tecplot_points",
    "write_vtk_points",
]

# The products are the post stage a campaign leaves after collection
# (PFS-2029.15.03); registered here, below the run layer's reach, so the
# run calls it without importing this layer.
register_post_stage(write_campaign_products)
