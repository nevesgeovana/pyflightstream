"""The pproc example of the field tables, and what it leaves out, for the input template.

The streamlines table (FR-460), the survey lattice of ``[[probes]]`` and the far-field
table (FR-454) are the pproc tables of the field products. They live in their own
example, ``inputs/pproc/p003.toml``, so the first example stays the one a row of any
run type can name, and the template module keeps to its size.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

_FIELD_EXAMPLE: Final = """\
# Traced streamlines, a survey lattice of probe points, and the far-field
# analyses that read them. Lengths are metres unless a key says r/R or BREF.
[streamlines]
surface = true                    # surface friction lines, and their export
direction = "downstream"          # every off-body line: downstream or upstream
length_m = 6.0                    # how far every off-body line goes
vtk = true                        # the package VTK polyline product

[[streamlines.lines]]
frame = "MRP"
start = [-0.5, 1.9, -0.1]
end = [-0.5, 1.9, 0.1]
count = 20                        # streamlines, evenly from start to end
scale = "m"                       # m, or rotor_radius

[[streamlines.tubes]]
frame = "MRP"
axis = "X"                        # X, Y or Z of that frame
origin = [-0.3, 0.0, 0.0]
radius = 0.9
radial = 4
circular = 12                     # radial * circular streamlines
scale = "m"

# A survey lattice: rings of points on annular planes about the axis of a frame.
[[probes]]
frame = "MRP"
parameters = ["VX", "VY", "VZ"]
kind = "normal"

[[probes.lattices]]
frame = "MRP"
tip_radius_m = 1.0                # r/R below is a fraction of this
stations = [-1.0, 0.0, 1.0]       # x/R of the planes, strictly increasing
n_r = 4                           # rings of every plane
r_inner = 0.1
r_outer = 1.2
n_psi = 16                        # points of every ring
lateral_radius = 1.4              # the closure cylinder
lateral_stations = [-1.0, 1.0]
hub_width = 0.05
tip_width = 0.05

# The far field: which families, and the analyses over them.
[farfield]
families = "lifting"

[farfield.trefftz]
variant = ["sections", "wake", "plane"]
stations = 80                     # per side, when the plan adds a distribution
distance_bref = 0.25              # plane behind the families, in BREF
half_width_bref = 0.75
half_height_bref = 0.5
spacing_bref = 0.01

[farfield.ledgers]                # the lattice may be stated here instead
frame = "MRP"
tip_radius_m = 1.0
stations = [-1.0, 1.0]
n_r = 4
r_inner = 0.1
r_outer = 1.2
n_psi = 16
lateral_radius = 1.4
lateral_stations = [-1.0, 1.0]
hub_width = 0.05
tip_width = 0.05
balances = ["mass", "axial", "transverse", "torque", "in_plane_moment", "crossflow_energy"]
m_max = 6                         # highest azimuthal order stored
"""

_A_ROTOR_PLACES_IT: Final = (
    "the alternative to frame and tip_radius_m, which it refuses beside it: a rotor of "
    "the reference places the lattice by its own hub frame and radius"
)

_FIELD_LEFT_OUT: Final = MappingProxyType(
    {
        "`[streamlines]`": MappingProxyType(
            {
                "the alternative to length_m, which it refuses beside it; the line runs "
                "until it leaves the domain": ("unrestricted",),
            }
        ),
        "`[[probes.lattices]]`": MappingProxyType({_A_ROTOR_PLACES_IT: ("rotor",)}),
        "`[farfield.trefftz]`": MappingProxyType(
            {
                "a rotor lattice's station x/R, read only where the survey is a rotor's; "
                "unstated, the last station": ("station",),
            }
        ),
        "`[farfield.ledgers]`": MappingProxyType({_A_ROTOR_PLACES_IT: ("rotor",)}),
    }
)


def field_example() -> str:
    """Return the text of the ``inputs/pproc/p003.toml`` example of the template."""
    return _FIELD_EXAMPLE


def field_left_out() -> Mapping[str, Mapping[str, tuple[str, ...]]]:
    """Return the keys of the field tables the example leaves out, by table, with the reason."""
    return _FIELD_LEFT_OUT
