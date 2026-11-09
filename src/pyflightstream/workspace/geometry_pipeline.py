"""The geometry pipeline of a parametric aircraft: generate, check, mesh and identify.

Pipeline role: the public entry points of the stages that need the geometry kernel, behind the
optional ``gmsh`` extra. :func:`generate_iges` writes the exposed skin of a parametric
configuration (:func:`pyflightstream.geometry.load_config`) as a named IGES file, one NAME per
component; :func:`check_against_original` measures a rebuilt surface against an original under a
named deviation profile; :func:`mesh_generated` meshes a configuration into an all-quad surface
mesh with its acceptance checks; and :func:`identify_lifting_surface` reads the planform and the
sections of a lifting surface back from an original IGES, in the form a configuration takes
(:class:`LiftingIdentification`). The pure parameter contract
(:class:`~pyflightstream.geometry.ComponentRecord`) and the TOML input boundary live in
:mod:`pyflightstream.geometry` and import no kernel.

Each function refuses with the install command (``pip install pyflightstream[gmsh]``) when the
extra is missing. The command line is ``pyfs-workspace geometry generate | identify | check |
mesh-generated | schema``.

Examples
--------
>>> from pyflightstream.workspace.geometry_pipeline import __all__
>>> sorted(__all__)[:2]
['GeneratedMesh', 'LiftingIdentification']
"""

from pyflightstream.workspace._geometry_check import check_against_original
from pyflightstream.workspace._geometry_generate import generate_iges
from pyflightstream.workspace._geometry_mesh import GeneratedMesh, mesh_generated
from pyflightstream.workspace._geometry_reverse import (
    LiftingIdentification,
    identify_lifting_surface,
)

__all__ = [
    "GeneratedMesh",
    "LiftingIdentification",
    "check_against_original",
    "generate_iges",
    "identify_lifting_surface",
    "mesh_generated",
]
