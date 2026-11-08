"""Parametric geometry: component records, configuration, sections and lifting surfaces.

Pipeline role: pure numerical layer below the workspace. It describes
aircraft components by a few parameters and rebuilds their skin as B-spline
patches, with no geometry kernel, no solver and no import from the run, post
or workspace layers. Stages that need a kernel (IGES writing, meshing) live in
the workspace and import the types defined here.

The public names are :class:`ComponentRecord` (the parameter contract),
:class:`Patch` (the exchange type between stages), and
:func:`load_config`, :func:`resolve_config` and :func:`write_config`
(the TOML input boundary).

Examples
--------
>>> from pyflightstream.geometry import resolve_config
>>> resolved = resolve_config({"type": "lifting_surface"})
>>> resolved["components"]["COMPONENT"]["type"]["source"]
'given'
"""

from pyflightstream.geometry.component import ComponentRecord
from pyflightstream.geometry.config import load_config, resolve_config, write_config
from pyflightstream.geometry.patch import Patch

__all__ = ["ComponentRecord", "Patch", "load_config", "resolve_config", "write_config"]
