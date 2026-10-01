"""Results into engineering data.

Pipeline role: the top of the pipeline, where parsed solver output
becomes something a report can carry. Public modules and one
private one, and the list is what EXISTS rather than what is planned
(a tier-1 test holds it to the modules on disk).
Each says whether it is reached through this package or through its own
module, which is stated rather than left to be discovered:

* :mod:`pyflightstream.post.diagnostics` renders complete saved post logs as
  Markdown without executing stages or changing products. Its report renderer
  is re-exported here and registered through workspace for lower-layer
  callers; category presentation helpers remain in that module;
* :mod:`pyflightstream.post.probe_fields` exports sampled velocity
  and reusable inflow with explicit units and source provenance. Sampled volume
  uses the same probes/fluid-plots route and writes vertex clouds; native saved
  section indices remain a separate manual API concern. Re-exported here;
* :mod:`pyflightstream.post.field_frames` holds the coordinate and velocity
  transforms the sampled-field and boundary-layer products share, each with
  its native convention stated. Reached through its own module;
* :mod:`pyflightstream.post.boundary_layer` writes the raw VTK boundary-layer
  scalars at recorded surface-section cut points, with the source cell of
  each value. It never averages, interpolates to nodes, guesses a thickness
  unit or builds a wall-normal velocity profile. Reached through its own
  module;
* :mod:`pyflightstream.post.surfaces` averages the per-step surface exports
  of an unsteady window into one surface, the product a pproc's
  ``[time_averaging]`` asks for. Reached through its own module;
* :mod:`pyflightstream.post.section_distributions` tables the sectional
  loads and chordwise Cp, one table per recorded pproc distribution.
  Reached through its own module;
* :mod:`pyflightstream.post.qsteady` tables a quasi-steady rotor's steady
  clockings and their average, and gives its sections the 1P reduced
  frequency of each station (0.30.0). Reached through its own module;
* :mod:`pyflightstream.post.harmonics` fits each blade station's 0P, 1P and 2P
  load around the disc from the written sections (0.31.0). Reached through its
  own module;
* :mod:`pyflightstream.post.corrections` writes a quasi-steady wheel's
  corrected products beside the raw ones and its Theodorsen and Sears
  diagnostic, none of it validated (0.31.0). Reached through its own module;
* :mod:`pyflightstream.post.acoustics` reads a point's acoustic signals
  export into one signal per observer and writes, per observer, the pressure
  against time, the spectrum, the overall sound pressure level and the
  blade-passage harmonics, and the directivity when the observers lie on an
  arc (0.32.0). Reached through its own module;
* :mod:`pyflightstream.post.disc_maps` tables a rotor's sectional load by
  radius and azimuth over the disc, from a quasi-steady wheel's clockings or
  an unsteady rotor's last complete revolution (0.32.0). Reached through its
  own module;
* :mod:`pyflightstream.post.inflow_tools` writes a product table in the
  installed frame and the blade-view harmonics of a custom inflow (0.32.0).
  Reached through its own module;
* :mod:`pyflightstream.post.qsteady_noise` holds the exploratory
  quasi-steady rotor noise model (0.32.0): a blade's load reconstructed
  against azimuth from a quasi-steady wheel's clockings and propagated to an
  observer by a compact loading-noise model, not wired into the post stage.
  Its report writer,
  :func:`pyflightstream.post.qsteady_noise.write_qsteady_noise_report`, is
  left unfilled on purpose and raises
  :class:`pyflightstream._errors.ContractNotImplementedError`. Reached
  through its own module;
* :mod:`pyflightstream.post.custom_polar` and
  :mod:`pyflightstream.post.provenance` hold the custom polar format and the
  PROV-JSON writer that the products entry below names; their existing
  import spellings remain available through :mod:`pyflightstream.post.products`;
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
  per recorded run (PFS-2012.08.01). Its other writers (the polar row, the
  rotor table, the per-blade table, the unsteady polar) and the header of an
  unsteady polar's axes are reached through :mod:`pyflightstream.post.products`
  itself and are not re-exported here.
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
  optional and lossy and a reader should meet its page first;
* :mod:`pyflightstream.post.axes` is the ONE home of the frame conventions:
  the export's frame, the body, stability and wind axes with sideslip, the
  eighteen axis coefficients of a polar row, and where a blade is at a step.
  Reached through its own module, because a reader asking which frame a
  published column is in wants that page and nothing else;
* :mod:`pyflightstream.post.equations` evaluates a pproc's ``[equations]``
  over the averaged columns of an unsteady polar. Reached through its own
  module: the products stage is its caller, and a user writing an equation
  reads the generated ``WRITING-EQUATIONS.md`` first;
* :mod:`pyflightstream.post.guides` writes the generated input guides beside
  a workspace's pproc artifacts: ``VARIABLES.md`` and ``WRITING-EQUATIONS.md``,
  and since 0.27.0 the input glossary ``INPUTS.md``, every key an input
  artifact may state (G08); since 0.28.0 also the input template
  ``input_template.md`` at the root of ``inputs/``, a complete example of
  every kind of input file (G47). Re-exported here. Since 0.33.0 (AD-11) it
  writes the two pproc guides itself and re-exports the other two pages,
  :mod:`pyflightstream.post.glossary`, the input glossary with the parts the
  three pages share, and :mod:`pyflightstream.post.input_template`, the input
  template;
* :mod:`pyflightstream.post._tables` is PRIVATE: the table primitives
  (the condition block, the CSV writer, the column renaming) the product
  modules share, so that no two of them import each other.

WHAT THIS LAYER DOES NOT HAVE, said plainly because this docstring
advertised it for three releases and a reader has no other way to find
out. There is no ``ResultArray`` facade: no ``interp_along``, no
``reparametrize``, no ``trim``. FR-20 carries that promise and is
``pending``; AD-06 sends the interpolation half to the sister library.
Sweep assembly is not here either, it is
:mod:`pyflightstream.results.tables`.
"""

# The generated pproc guides. Re-exported here because a module under
# `post` that its package root cannot reach by import is a module a reader
# cannot find, and `tests/tier1_offline/test_results.py` refuses one by name
# unless `_UNREACHABLE_FROM_ITS_PACKAGE_ROOT` records why.
from pathlib import Path

from pyflightstream._deprecations import removed_names_hook
from pyflightstream.post.diagnostics import render_post_diagnostics
from pyflightstream.post.guides import (
    INPUT_GLOSSARY_NAME,
    INPUT_TEMPLATE_NAME,
    PPROC_GUIDE_NAMES,
    write_input_glossary,
    write_input_template,
    write_pproc_guides,
    write_workspace_input_glossary,
    write_workspace_input_template,
    write_workspace_pproc_guides,
)
from pyflightstream.post.probe_fields import write_probe_field
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
from pyflightstream.workspace import (
    register_input_guide,
    register_post_diagnostics,
    register_post_stage,
)

# The polar format's REMOVED names are refused here too, naming the
# replacement, by the one hook both post modules install (AD-10).
__getattr__ = removed_names_hook(__name__)


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
    "render_post_diagnostics",
    "settings_records",
    "read_csv_table",
    "read_custom_polar_format",
    "write_campaign_products",
    "write_csv_table",
    "write_custom_polar_format",
    "write_plots_table",
    "write_polar_table",
    "write_recorded_polar",
    "INPUT_GLOSSARY_NAME",
    "INPUT_TEMPLATE_NAME",
    "PPROC_GUIDE_NAMES",
    "write_input_glossary",
    "write_input_template",
    "write_pproc_guides",
    "write_reduction",
    "write_sections_table",
    "write_point_series",
    "write_probe_field",
    "write_series",
    "write_tecplot_points",
    "write_vtk_points",
]

# The products are the post stage a campaign leaves after collection
# (PFS-2029.15.03); registered here, below the run layer's reach, so the
# run calls it without importing this layer.
register_post_stage(write_campaign_products)
register_post_diagnostics(render_post_diagnostics)
# THE GENERATED PPROC GUIDES reach the workspace init and the plan, which live
# below this layer, through the same kind of registry the post stage uses.
register_input_guide(write_workspace_pproc_guides)
# THE INPUT GLOSSARY (G08 of 0.27.0), beside them and by the same registry.
register_input_guide(write_workspace_input_glossary)
# THE INPUT TEMPLATE (G47 of 0.28.0), at the root of `inputs/`, by the same registry.
register_input_guide(write_workspace_input_template)


def _the_guides_stage(workspace: object, **_options: object) -> list[Path]:
    """Refresh the generated input guides at post; a guide is not a product, so return none."""
    write_workspace_pproc_guides(workspace.inputs_dir)  # type: ignore[attr-defined]
    write_workspace_input_glossary(workspace.inputs_dir)  # type: ignore[attr-defined]
    write_workspace_input_template(workspace.inputs_dir)  # type: ignore[attr-defined]
    return []


register_post_stage(_the_guides_stage)
