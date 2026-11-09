"""The pure stages of the geometry pipeline, for the workspace and the command line.

Pipeline role: the one public home of the numerical building blocks that the kernel stages
(:mod:`pyflightstream.workspace.geometry_pipeline`) and the ``geometry`` verbs of the command
line call: the B-spline :class:`Patch`, the generation of the components of a resolved
configuration and their regions, the body and lifting-surface skins and the flat tip cap, the
placement of a wing in the frame of its body, the mesh spacing rules and the mesh checks, the
OBJ writer, the mathematics of reading a lifting surface back from sections, and the record
boundary (schema export, pin verification, configuration writing).

Every name is defined in a private module of this package and re-exported here, so a caller in
another package imports this module and no private path. The functions import no geometry
kernel and no solver; they need numpy and scipy only. The names that matter to a user are the
entry points of :mod:`pyflightstream.workspace.geometry_pipeline` and the configuration
boundary of :mod:`pyflightstream.geometry`; the rest is the contract between the two
packages and may change between releases while the module is provisional.

Examples
--------
>>> from pyflightstream.geometry.stages import Mesh, Patch
>>> Patch.__name__, Mesh.__name__
('Patch', 'Mesh')
"""

from pyflightstream.geometry._bodies import body
from pyflightstream.geometry._boundary import export_schema, unpack, verify_pins, write_config
from pyflightstream.geometry._caps import tip_cap
from pyflightstream.geometry._generation import assembly_regions, generate_components
from pyflightstream.geometry._lifting import lifting_surface
from pyflightstream.geometry._mesh_rules import (
    check_body,
    check_lifting,
    chord_fraction,
    chord_nodes,
    constant,
    count_classes,
    insert_seed,
    load_mesh_controls,
    tip_refinement,
)
from pyflightstream.geometry._mesh_topology import (
    Mesh,
    check_mesh,
    orient_mesh,
    oriented_source_normals,
    repair_inverted,
    write_obj,
)
from pyflightstream.geometry._patch import Patch
from pyflightstream.geometry._placement import wing_in_body_frame
from pyflightstream.geometry._reverse import (
    clean_band,
    closed_contour,
    contour_features,
    cosine,
    fit_section,
    leading_extension,
    reference_planform,
    refine_tip,
)

__all__ = [
    "Mesh",
    "Patch",
    "assembly_regions",
    "body",
    "check_body",
    "check_lifting",
    "check_mesh",
    "chord_fraction",
    "chord_nodes",
    "clean_band",
    "closed_contour",
    "constant",
    "contour_features",
    "cosine",
    "count_classes",
    "export_schema",
    "fit_section",
    "generate_components",
    "insert_seed",
    "leading_extension",
    "lifting_surface",
    "load_mesh_controls",
    "orient_mesh",
    "oriented_source_normals",
    "reference_planform",
    "refine_tip",
    "repair_inverted",
    "tip_cap",
    "tip_refinement",
    "unpack",
    "verify_pins",
    "wing_in_body_frame",
    "write_config",
    "write_obj",
]
