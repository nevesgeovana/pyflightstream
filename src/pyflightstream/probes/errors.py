"""Exception types of the probe-survey layer.

Their own module rather than the package ``__init__``, because that
``__init__`` imports the submodules that raise them and a class defined
there would be a circular import. Nothing here imports anything but the
package base, so every probe module can reach it.
"""

from pyflightstream._errors import PyflightstreamError


class ProbeGeometryError(PyflightstreamError, ValueError):
    """Survey geometry that does not describe a measurable arrangement.

    Non-physical radii or stations, an axis specification that cannot be
    walked, a refinement band outside its plane, a position set that does
    not verify against the lattice it claims. Raised by the cylindrical
    lattice, the planar grids and the geometry gate alike, so one
    ``except`` covers the survey-geometry surface.

    Added 2026-08-03 for FR-39, keeping ``ValueError`` as a second base
    so an existing ``except ValueError`` catches what it always did.
    """
