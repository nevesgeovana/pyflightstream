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
  point, from the collected exports and the manifest (PFS-2029.15); the
  custom polar format beside the polar table when asked (PFS-2014.01.01), its
  writer and reader re-exported here; and a PROV-JSON provenance document
  per recorded run (PFS-2012.08.01).
* :mod:`pyflightstream.post.superfile` writes the SUPERFILE of each polar
  and group beside the polar table (FR-89), one row per converged point
  whose column set is a superset of everything the workspace knows about
  that simulation, and the measurement of what it wrote under
  ``reports/``. Reached through its own module rather than re-exported
  here: everything it offers is called by the products stage, and a
  reader wanting it wants its page;
* :mod:`pyflightstream.post.series` tables the stamped per-step exports
  of a windowed unsteady point, one table per export kind under the
  matrix's ``series/`` (PFS-2031.18.01); its ``write_point_series`` is
  re-exported here. It is not :func:`write_series` below, which writes the
  plots export's own history for the reductions;
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
    CustomPolarTable,
    ProductError,
    ProductExistsError,
    ReferenceValues,
    read_csv_table,
    read_custom_polar_format,
    write_campaign_products,
    write_csv_table,
    write_custom_polar_format,
    write_plots_table,
    write_polar_table,
    write_recorded_polar,
    write_sections_table,
)
from pyflightstream.post.reductions import write_reduction, write_series
from pyflightstream.post.series import write_point_series
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


def __getattr__(name: str) -> object:
    """Serve the polar format's former names here too, warning from the ledger.

    Those names were spelled with a possessive prefix before 0.14.0 and are
    spelled ``custom`` now; the old ones are read until 0.16.0.

    The package warns itself rather than routing through the products
    shim: a from-import asks the package twice (``hasattr`` before the
    import opcode's own lookup), and routing warned twice for it.
    """
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "FrameAverage",
    "CustomPolarTable",
    "OutputProvenance",
    "ProductError",
    "ProductExistsError",
    "ReferenceValues",
    "TimestepSeries",
    "blade_passage_average",
    "dataset_to_points",
    "passage_windows",
    "read_timestep_series",
    "settings_records",
    "read_csv_table",
    "read_custom_polar_format",
    "write_campaign_products",
    "write_csv_table",
    "write_custom_polar_format",
    "write_plots_table",
    "write_polar_table",
    "write_recorded_polar",
    "write_reduction",
    "write_sections_table",
    "write_point_series",
    "write_series",
    "write_tecplot_points",
    "write_vtk_points",
]

# The products are the post stage a campaign leaves after collection
# (PFS-2029.15.03); registered here, below the run layer's reach, so the
# run calls it without importing this layer.
register_post_stage(write_campaign_products)
