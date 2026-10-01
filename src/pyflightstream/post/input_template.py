"""The input template, ``input_template.md``: one section per kind of input file.

Written at the ROOT of a workspace's ``inputs`` folder since 0.28.0 (G47): one
section per kind of input file a user writes, the files of ``profiles/``
among them, each with a complete example to copy. Every example is a file the
package reads as it stands, which its test holds by writing each one where its
title says and reading it with the reader the run uses; the matrix's header is
the layout's registry, the values a comment lists are read from the registries
that check them, and every key of the glossary's tables is either stated by an
example or named on the page as left out, with the reason.

The sections are one data table, :data:`_TEMPLATE_SECTIONS`, in the page's
order; the page is rendered from it by :func:`input_template_markdown`.

Size exemption: one data table of complete example files, each a literal the suite reads back.
Its length is the examples' own text; a cut would part an example from its section.

Every public name is re-exported, unchanged, by :mod:`pyflightstream.post.guides`,
its path of 0.32.0 (AD-11, since 0.33.0).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import get_args

from pyflightstream._errors import InputArtifactError
from pyflightstream.cases import FLAG_PHASES, RAW_PHASES, ActuatorBlock
from pyflightstream.cases._setup_keys import TEMPLATE_SETTINGS_LEFT_OUT as _SETTINGS_LEFT_OUT
from pyflightstream.cases.corrections import CALIBRATIONS_DIR
from pyflightstream.cases.matrix import COLUMN_MEANINGS
from pyflightstream.cases.workflows import FREESTREAM_DIR, FREESTREAM_FORMS
from pyflightstream.post.glossary import (
    _GENERATED,
    ARTIFACT_HEADINGS,
    INPUT_GLOSSARY_NAME,
    _page_link,
    _write_if_different,
)
from pyflightstream.workspace import REFERENCE_POINTS_FILE
from pyflightstream.workspace.fsi_setup import FSI_TEMPLATE
from pyflightstream.workspace.hpc import HPC_DIR, HPC_FORMATS, WALLTIME_ARITHMETIC
from pyflightstream.workspace.inputs import EXECUTABLES_FILE, LOCAL_EXECUTABLES_FILE
from pyflightstream.workspace.wake_edges import edge_types, length_scale, node_file_units

__all__ = [
    "INPUT_TEMPLATE_NAME",
    "TemplateExample",
    "TemplateSection",
    "input_template_markdown",
    "write_input_template",
    "write_workspace_input_template",
]


# --- the input template, input_template.md (G47 of 0.28.0) --------------------

#: The input template's file name. It is written at the ROOT of a workspace's
#: ``inputs/`` folder, where the files whose format it shows live, and it links
#: the input glossary, which shares this inputs root.
INPUT_TEMPLATE_NAME = "input_template.md"

#: The glossary shares the template's inputs root.
_GLOSSARY_LINK = f"[`{INPUT_GLOSSARY_NAME}`]({INPUT_GLOSSARY_NAME})"


@dataclass(frozen=True)
class TemplateExample:
    """One example file of the input template.

    Attributes
    ----------
    path : str
        Where the file goes, relative to the workspace root; the example
        block's title, so a reader copies it there and the suite writes it
        there before reading it back.
    language : str
        The language of the block's fence: ``toml``, ``text`` or ``csv``.
    text : str
        The file, ending in a newline.
    note : str
        What to know about this file before copying it, above the block.
    """

    path: str
    language: str
    text: str
    note: str = ""


@dataclass(frozen=True)
class TemplateSection:
    """One kind of input file on the input template.

    Attributes
    ----------
    heading : str
        The section's heading; for the five artifacts the glossary covers, the
        glossary's own heading of that artifact.
    intro : str
        What the file is for and where it lives.
    examples : tuple of TemplateExample
        The files the section shows, each complete and valid as it stands.
    after : str
        What the examples do not say by themselves, below them.
    left_out : mapping
        By the glossary's heading of a table, each reason to the keys of that
        table the examples leave out; an empty tuple of keys stands for every
        key of the table. It is written on the page, and the template's test
        holds that every key of every table is shown or named here.
    pages : tuple of (str, str)
        The documentation pages the section links, as (name, title).
    """

    heading: str
    intro: str
    examples: tuple[TemplateExample, ...]
    after: str = ""
    left_out: Mapping[str, Mapping[str, tuple[str, ...]]] = MappingProxyType({})
    pages: tuple[tuple[str, str], ...] = ()


def _in_words(words: Sequence[str], last: str = "or") -> str:
    """Join a closed set of values as a sentence names it: ``a, b or c``."""
    listed = list(words)
    if len(listed) < 2:
        return "".join(listed)
    return f"{', '.join(listed[:-1])} {last} {listed[-1]}"


def _scaled_units() -> tuple[str, ...]:
    """Return the length units a points file may name: the recorded ones with a scale."""
    scaled = []
    for unit in node_file_units():
        try:
            length_scale(unit, "METER")
        except InputArtifactError:
            continue
        scaled.append(unit)
    return tuple(scaled)


#: The run matrix of the template, one mapping per row, by column. A column the
#: layout gains and a row does not state is written ``-``, the matrix's word
#: for "states nothing", so the header is always the layout the reader reads.
_MATRIX_ROWS: tuple[Mapping[str, str], ...] = (
    {
        "POL": "1001",
        "HIDDEN": "1",
        "RUN": "1",
        "AIRCRAFT": "WingBody",
        "CONFIGURATION": "clean",
        "DESCRIPTION": "ALPHA_SWEEP",
        "FLIGHT_CONDITION": "MACH:0.15, REmi:3.1, ALPHA:sweep, BETA:0.0",
        "SWEEP_VALUES": "-2.0,0.0,2.0,4.0",
        "GEOMETRY": "aircraft.fsm",
        "REF": "r001",
        "SET": "s001",
        "PPROC": "p001",
        "SYMMETRY": "NONE",
        "SYMMETRY_LOADS": "-",
        "NCPUS": "8",
        "WALLTIME": "2h",
        "FS_BUILD": "26.124",
        "WORKFLOW": "steady",
        "VAR_NAMES_VALUES": "digits: 6",
    },
    {
        "POL": "1002",
        "HIDDEN": "1",
        "RUN": "1",
        "AIRCRAFT": "WingBody",
        "CONFIGURATION": "disc",
        "DESCRIPTION": "DISC_FROM_A_PROFILE",
        "FLIGHT_CONDITION": "MACH:0.15, REmi:3.1, ALPHA:sweep, BETA:0.0",
        "SWEEP_VALUES": "0.0,4.0",
        "GEOMETRY": "aircraft.fsm",
        "REF": "r001",
        "SET": "s001",
        "PPROC": "p001",
        "SYMMETRY": "NONE",
        "NCPUS": "8",
        "WALLTIME": "2h",
        "FS_BUILD": "26.124",
        "WORKFLOW": "steady",
        "VAR_NAMES_VALUES": "ACTUATOR: DISC / ACTUATOR_RPM: 2400 / PROFILE: prop_thrust",
    },
    {
        "POL": "1003",
        "HIDDEN": "1",
        "RUN": "1",
        "AIRCRAFT": "WingBody",
        "CONFIGURATION": "gust",
        "DESCRIPTION": "CUSTOM_FREE_STREAM",
        "FLIGHT_CONDITION": "MACH:0.15, REmi:3.1, ALPHA:sweep, BETA:0.0",
        "SWEEP_VALUES": "0.0",
        "GEOMETRY": "aircraft.fsm",
        "REF": "r001",
        "SET": "s001",
        "PPROC": "p001",
        "SYMMETRY": "NONE",
        "NCPUS": "8",
        "WALLTIME": "2h",
        "FS_BUILD": "26.124",
        "WORKFLOW": "steady",
        "VAR_NAMES_VALUES": "FREESTREAM: gust",
    },
)


def _matrix_example() -> str:
    """Return the template's run matrix: the layout's header, a dashed line, the rows."""
    columns = list(COLUMN_MEANINGS)
    table = [columns, *([row.get(column, "-") for column in columns] for row in _MATRIX_ROWS)]
    widths = [max(len(line[index]) for line in table) for index in range(len(columns))]
    lines = [
        " | ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip()
        for line in table
    ]
    return "\n".join([lines[0], "-" * len(lines[0]), *lines[1:]]) + "\n"


def _matrix_after() -> str:
    """How the matrix file is laid out, its columns read from the layout's registry."""
    # The glossary's own pointers ("see the table below") point into the
    # glossary, so they are cut here, where no such table follows.
    columns = "\n".join(
        f"{index}. `{name}`: {meaning.meaning}"
        + (f" ({meaning.values.split('; see ')[0]})" if meaning.values else "")
        for index, (name, meaning) in enumerate(COLUMN_MEANINGS.items(), start=1)
    )
    return (
        "The file is a pipe-separated table: the header line names the columns in "
        "exactly this order, a line of dashes may follow it, and then one row per "
        "line. A cell that states nothing holds `-`. The file carries no comment "
        "lines: every line after the header is a row, so a note goes in "
        "`DESCRIPTION`. A row runs only when `RUN` reads 1.\n\n"
        f"{columns}\n\n"
        "`FLIGHT_CONDITION` holds `KEY:value` pairs separated by commas, and exactly "
        "one key carries the word `sweep` where its value would be: that is the "
        "variable the row varies, over the values of `SWEEP_VALUES`, one point "
        "each. `VAR_NAMES_VALUES` holds `KEY: value` pairs separated by ` / `, the "
        "keys the row's run type reads. `REF`, `SET` and `PPROC` name the three "
        "artifacts below by id, and `GEOMETRY` names a file of "
        "`inputs/geometries/` with its extension.\n\n"
        "The first row sweeps the angle of attack, and writes `digits: 6`, a word "
        "the setup below declares as a flag. The second turns the actuator disc "
        "`DISC` of the reference with the radial thrust profile "
        "`inputs/profiles/prop_thrust.txt`, named by its stem. The third flies "
        "through the custom free stream `inputs/freestreams/gust.txt`, also by "
        "its stem, at zero angles, since the field sets the flow's direction."
    )


_SETUP_EXAMPLE = """\
# A setup artifact: the solver settings a row's SET column names by id. The id
# is the file name without .toml and begins with s, so this file is s001.
# A key is this package's name for a setting, or the solver's own name for it
# (NITER for iterations, max_parallel_threads for max_threads, ...). A key that
# names no setting, no alias and no reserved key is refused, naming the keys
# that apply. Top-level keys come before the first [table].

iterations = 500                  # solver iterations, a whole number >= 1
convergence = 1e-5                # the residual the solve stops at
boundary_layer = "TURBULENT"      # LAMINAR, TRANSITIONAL or TURBULENT
viscous_coupling = true           # true or false, or "ENABLE" or "DISABLE"
wall_collision_avoidance = true   # the solver's proximity avoidance
farfield_layers = 5               # the far-field layers; state them in every setup

# The solver's stabilization, switched and sized as a pair. The direct form,
# solver_stabilization = <strength>, is the other way to say it; a file states
# one of the two.
stabilization = true
stabilization_strength = 1.0

# The FLUID every row citing this setup inherits: pins that replace what the
# standard atmosphere would supply. A row stating one of them wins, key by key,
# and a row that solves its own density (it states REmi) drops RHOkgm3.
[flight_condition]
RHOkgm3 = 1.225                   # density, kg/m^3
MUPas = 1.789e-5                  # dynamic viscosity, Pa s
ASMPS = 340.29                    # speed of sound, m/s
TK = 288.15                       # static temperature, K
PPA = 101325.0                    # static pressure, Pa

# A solver command line stated verbatim, arguments included, which every row
# citing this setup emits before the phase it names, one of:
# @RAW_PHASES@.
[[raw]]
command = "PRINT s001"
before = "init"

# A solver command this setup exposes to the matrix under a word of your own:
# a row citing this setup writes "digits: 6" in its VAR_NAMES_VALUES cell, and
# the script carries SET_SIGNIFICANT_DIGITS 6. The command is written bare; the
# row states the value. before is optional, one of @FLAG_PHASES@.
[[flags]]
name = "digits"
command = "SET_SIGNIFICANT_DIGITS"
before = "setup"
"""

_PPROC_EXAMPLE = """\
# A post-processing artifact: what a row's PPROC column names by id; the id
# begins with p, so this file is p001. It says what each point defines before
# the solve, which files each point exports, and which products are written
# after the run. Every table is optional. The columns the products write are
# in pproc/VARIABLES.md, and how to write an equation in
# pproc/WRITING-EQUATIONS.md, both beside pproc/INPUTS.md.

# Top-level keys come before the first [table]; written under one, TOML files
# them in that table.
blade_pattern = '^Blade\\d+$'      # a regular expression telling a blade family from the airframe
base_regions = ["Base"]           # boundaries made base regions after the mesh opens;
                                  # a row's BASE_REGIONS wins over it
vtk_variables = ["CP_FREESTREAM", "MACH", "VTOT"]   # what the VTK surface export writes
singularity_strength = false      # true: the Tecplot surface carries the nodal
                                  # Singularity_strength, from a second, native
                                  # Tecplot export per point

# The groups the polar tables are written per: each group's name to ONE alias
# of the reference, or to "all" where no boundary or alias has that name.
[groups]
AIRFRAME = "airframe"
WING = "lifting"

# Which files each point exports; simulation and loads cannot be switched off.
[exports]
simulation = true
loads = true
tecplot = true
vtk = true
csv = false
force_distributions = false       # the per-panel forces
sections = true
sectional_loads = true
probes = true                     # steady rows
plots = true                      # the unsteady run types
plot_residuals = true             # steady rows: the solver's own plots
plot_loads = true
plot_sections_cp = true           # where [[sections.distributions]] declares any
log = true

# Surface sections cut before the solve, one distribution per entry and plane.
[sections]
count = 50                        # sections of every distribution that states none
plot_direction = 1                # 1 or 2
include_symmetry = false

[[sections.distributions]]
families = "lifting"              # an alias, a family name, or a list of them
frame = "MRP"                     # MRP, a frame of the reference, or a rotor's
planes = ["XZ"]                   # XY, XZ or YZ, one distribution each
count = 40                        # this entry's own count
plot_direction = 1
integrate = true                  # append the strip integrals of the sectional loads

# One flow-field plane each point of a steady row cuts after its solve. A
# rectangle is shown; a circle states shape = "circle", radii_m = [r1, r2] and
# points = [ipts, jpts] in place of corners_m and refinement_layers.
[volume_section]
shape = "rectangle"
frame = "MRP"
plane = "XZ"
offset_m = 0.0                    # along the plane's normal, from the frame's origin
corners_m = [-1.0, -1.0, 1.0, 1.0]   # x1, y1, x2, y2, two diagonal corners in the plane
refinement_layers = 1
format = "vtk"                    # vtk or tecplot

# The unsteady force plots: which parameters, over which groups of families.
[plots]
parameters = ["CL", "CD", "FX", "FZ", "MY"]

[[plots.groups]]
name = "WING"
frame = "MRP"
families = "lifting"

# Fluid probes, one entry per frame sampled: lines, rectangles and circles of
# points, laid out in the entry's frame in the entry's scale ... An unsteady
# row samples the parameters listed; a steady row exports its fixed set of
# variables, the list only switching the entry on, and says so in a warning.
[[probes]]
frame = "MRP"
parameters = ["VX", "VY", "VZ", "CP_FREE"]
points = 11                       # points per line, both ends included
scale = "m"                       # m, or rotor_radius
field_formats = []               # opt in with ["vtk", "tecplot"]
reusable_inflow = false           # requires a global YZ plane and proved SI vectors

[[probes.lines]]
start = [2.0, -1.0, 0.0]
end = [2.0, 1.0, 0.0]

[[probes.rectangles]]
origin = [3.0, -1.0, -0.5]        # three corners; the fourth follows from them
along_u = [3.0, 1.0, -0.5]
along_v = [3.0, -1.0, 0.5]
points_u = 5
points_v = 3

[[probes.circles]]
center = [3.0, 0.0, 0.0]
normal = [1.0, 0.0, 0.0]
radius = 0.5
points_radial = 3                 # from the centre to the rim, both included
points_azimuth = 8

# ... or a points file of inputs/profiles/, named without a folder, in place
# of drawing them.
[[probes]]
parameters = ["VX", "VY", "VZ"]
points_file = "wake_survey.csv"

# The phase-locked reduction of an unsteady rotor row: generated when the row
# turns at least min_revolutions, averaged over the last revolutions.
[phase_locked]
min_revolutions = 4.0
last_revolutions_avg = 2.0

# A coefficient the post stage derives into the unsteady polar, about ONE
# alias: this one is the column CX_airframe.
[equations.CX]
expression = "FX / (0.5 * RHO * VINF**2 * SREF)"
meshes_alias = "airframe"
frame = "MRP"

# What your own symbols mean, listed in pproc/VARIABLES.md beside the package's.
[glossary]
CX = "-. The axial force coefficient of the airframe, in the MRP frame"

# A plot column of the unsteady polar renamed for a downstream tool.
[names]
CL_WING = "CL_W"

# Which products are written after the run.
[products]
polars = true
sections = true
plots = true
custom_polar_format = false
# Raw native integral quantities at declared cuts, with source-cell provenance.
boundary_layer_integrals = false
# Distinct velocity profile; unavailable builds are refused explicitly.
boundary_layer_velocity_profile = false
superfile_format = "csv"
"""

_SURFACE_PROBE_EXAMPLE = """\
# Select this artifact only for an unsteady row. Coordinates are local metres.
# This native surface history is separate from off-body fluid probes.
[[surface_probes]]
name = "upper_cp"
parameter = "CP_FREE"
frame = "REFERENCE"
point_m = [0.25, 0.1, 0.02]

[[surface_probes]]
name = "upper_speed"
parameter = "VELOCITY"
frame = "REFERENCE"
point_m = [0.25, 0.1, 0.02]

[products]
plots = true
"""


_REFERENCE_EXAMPLE = """\
# A reference artifact: what a row's REF column names by id; the id begins
# with r, so this file is r001. The lengths the coefficients are divided by,
# the moment point, the frames, your names for groups of boundaries, and one
# block per rotor, actuator disc and named point. Lengths are in metres, in
# the geometry's own frame.

area_m2 = 8.0                     # S_ref, m^2
chord_m = 1.0                     # c_ref, m
span_m = 8.0                      # b_ref, m
rotor_diameter_m = 1.2            # D, m: what an ADVANCE_RATIO and C_T divide by

[moment_point]                    # the moment reference point
x_m = 0.25
y_m = 0.0
z_m = 0.0

[body_axes]                       # the mesh axis each body rate turns about
roll = "X"
pitch = "Y"
yaw = "Z"

# Your own names for groups of boundaries, read wherever a boundary is cited:
# a pproc group, a families entry, a row's rotation. A member may be another
# alias, and a member the opened mesh does not carry is left out.
[aliases]
airframe = ["Wing", "Body", "Base"]
lifting = ["Wing"]

# The recorded rotor; its position is the one field a builder reads.
[rotor]
radius_m = 0.6                    # optional; half of rotor_diameter_m when stated
hub_radius_m = 0.1
n_blades = 3                      # the blade count of the mesh a row opens
pitch_deg = 0.0                   # recorded
toe_deg = 0.0                     # recorded

[rotor.position]
x_m = -0.5
y_m = 0.0
z_m = 0.0

# Custom coordinate systems, in the order written: origin in metres, two axis
# directions, the third their right-handed cross product. A row's AXIS and a
# pproc entry's frame cite them by name.
[[frames]]
name = "DISC_HUB"
origin = [0.4, 3.0, 0.0]
x_axis = [1.0, 0.0, 0.0]
y_axis = [0.0, 1.0, 0.0]

# One block per rotor: a top-level table with kind = "rotor". Its name is the
# word a row moves, and an alias over everything the rotor owns.
[PROP]
kind = "rotor"
alias = "PROP"                    # optional; equal to the block's name
axis = "X"                        # X, Y or Z, or the shaft direction [x, y, z]
diameter_m = 1.2
x_m = -0.5
y_m = 0.0
z_m = 0.0
rpm_sign = 1                      # +1 is the right-hand rule about axis
families_general = ["Spinner"]    # what turns with the rotor and is not a blade
families_blades = ["Blade1", "Blade2", "Blade3"]   # one per blade, in order

[PROP.blade1]                     # where blade one is, and what its azimuth is measured from
azimuth_deg = 0.0
zero = "Y"                        # an axis letter, with at most one sign

# One block per actuator disc: a top-level table with kind = "actuator". A
# row's ACTUATOR names it; a disc no row names emits nothing.
[DISC]
kind = "actuator"
frame = "DISC_HUB"                # a frame of [[frames]], MRP, or a rotor's frame
axis = "X"                        # the frame's axis the disc turns about
offset_m = 0.0                    # along that axis, from the frame's origin
tip_radius_m = 0.5
hub_radius_m = 0.1
rpm_sign = 1
blades = 3                        # required by a row stating PROFILE
swirl = 0.5                       # the fraction of the swirl kept, 0 to 1
profile_units = "NEWTONS"         # @PROFILE_UNITS@
thrust_units = "NEWTONS"          # ACTUATOR_THRUST: NEWTONS, POUNDS or COEFFICIENT
wake_type = "RIGID"               # explicit wake model; RELAXED is the other choice

# A named point: a top-level table with any other kind (rotor or airframe).
# It is read and kept; a row that names a point finds it in
# inputs/reference_points.toml.
[ARP]
kind = "airframe"
x_m = 0.25
y_m = 0.0
z_m = 0.0
"""

_REFERENCE_POINTS_EXAMPLE = """\
# The named reference points of this workspace, one table per name: ARP is the
# airframe point, and a rotor point is ERP with one propulsor or ERP1 to ERPn
# with more. A row's ROTOR_ORIGIN may name a rotor point instead of stating
# coordinates. The coordinates are metres in the geometry's own frame.

[ARP]
x_m = 0.25
y_m = 0.0
z_m = 0.0

[ERP1]
kind = "rotor"                    # rotor or airframe; unstated, the name decides
x_m = -0.5
y_m = 0.0
z_m = 0.0
"""

_INVENTORY_EXAMPLE = """\
# The boundary inventory of aircraft.fsm, as `pyfs-matrix inventory` writes it
# from the file's own mesh block: the solver's order, the name at position i
# being boundary i. A run whose sidecar disagrees with the file is refused
# before the solver starts; rewrite it from the file with
# `pyfs-matrix inventory inputs/geometries/aircraft/aircraft.fsm --overwrite`.
file = "aircraft.fsm"
boundaries = [
    "Wing",
    "Body",
    "Base",
    "Spinner",
    "Blade1",
    "Blade2",
    "Blade3",
]
"""

_RAW_MESH_SIDECAR_EXAMPLE = """\
# The sidecar of a raw mesh, wing_raw.obj. An OBJ's boundaries are its groups
# that hold a face, in the order of the file: when no sidecar stands beside it,
# the plan writes this list from them, and the tables below go beneath it. An
# STL names no group, so its list is written by hand. A mesh file carries no
# length unit, so the [import] table is always written by hand.
file = "wing_raw.obj"
boundaries = ["naca"]             # the file's surfaces, in the file's order

[import]
units = "MILLIMETER"              # the unit the mesh file is written in; never assumed

# The operations applied right after the import, in the order written, each
# naming the surface it acts on by the file's name or an earlier rename's.
# A rename is shown; the others are
#   op = "scale",     factors = [fx, fy, fz]        (each above zero)
#   op = "translate", vector = [x, y, z]            (in the [import] unit)
#   op = "rotate",    axis = "Z", angle_deg = 90.0
#   op = "mirror",    surface = "<name>", plane = "XZ"
# A scale, a translation and a rotation take surface = "all" by default. A
# trailing-edge points file names edges of the file as written, so a mesh
# whose edges come from one takes no operation but a rename.
[[import.operations]]
op = "rename"
surface = "naca"
to = "Wing"

# The trailing edges, marked from a points file beside this sidecar (the file
# below). The other route is the solver's detection, in place of these three
# keys: detect = "auto", or detect = { surfaces = ["Wing"], sweep_angle = 60.0 }.
[trailing_edges]
file = "wing_raw.te.txt"
type = "STANDARD"                 # @EDGE_TYPES@
tolerance = 0.0001                # m: how close an edge's mid-point is to a point of the file

[wake_termination]                # only when written
detect = "auto"                   # or { surfaces = ["Wing"] }

[base_regions]                    # only when written
detect = "auto"
"""

_DUCT_SIDECAR_EXAMPLE = """\
# Synthetic duct with outward-facing inlet and outlet faces.
file = "duct.obj"
boundaries = ["Inlet", "Outlet", "Wall"]
[import]
units = "METER"
[trailing_edges]
none = true
[ports]
feed = "Inlet"
exit = "Outlet"
"""

_TRAILING_EDGE_POINTS_EXAMPLE = """\
MILLIMETER
1000.0,0.0,0.0
1000.0,2000.0,0.0
1000.0,4000.0,0.0
"""

_PROVENANCE_EXAMPLE = """\
# Where aircraft.fsm came from. The package reads no key of this file: it
# keeps the record beside its geometry, leaves it out of what a GEOMETRY cell
# can name, and moves it with the geometry. Write what a reader needs to trust
# or rebuild the mesh; these keys are a suggestion.
source = "exported from the CAD model, revision C"
prepared_with = "FlightStream 26.124"
prepared_on = "2026-01-15"
units = "METER"
sha256 = "the SHA-256 of aircraft.fsm, as `certutil -hashfile` or `sha256sum` prints it"
sidecar = "aircraft.boundaries.toml"
"""

_ACTUATOR_PROFILE_EXAMPLE = """\
0.2,0.0
0.3,84.2
0.4,110.3
0.5,123.3
0.6,127.3
0.7,123.3
0.8,110.3
0.9,84.2
1.0,0.0
"""

_PROBE_SURVEY_EXAMPLE = """\
3
2.0,-1.0,0.0,1
2.0,0.0,0.0,1
2.0,1.0,0.0,1
"""

_FREESTREAM_EXAMPLE = """\
3 3
-2.0 -5.0 -1.0 50.0 0.0 0.0
-2.0 -5.0 0.0 50.0 0.0 0.0
-2.0 -5.0 1.0 50.0 0.0 0.0
-2.0 0.0 -1.0 50.0 0.0 1.5
-2.0 0.0 0.0 50.0 0.0 1.5
-2.0 0.0 1.0 50.0 0.0 1.5
-2.0 5.0 -1.0 50.0 0.0 0.0
-2.0 5.0 0.0 50.0 0.0 0.0
-2.0 5.0 1.0 50.0 0.0 0.0
"""

#: 0.31.0 (P0310-CAL-SCHEMA): a quasi-steady wheel's calibration table, route 4,
#: two rows of one component over J; every number is a placeholder, and no
#: route is validated.
_CALIBRATION_EXAMPLE = """\
# A calibration table (route 4) a pproc's [qsteady_correction] names by its id.
# NOT VALIDATED: the numbers below are placeholders, not a recommendation.
route = "table"
description = "a discrepancy surface over J, constant in ALPHA and K_1P"

[[rows]]
COMPONENT = "THRUST"
J = 0.5
ALPHA = 0.0
K_1P = 0.05
OFFSET_0P = 0.0
GAIN_0P = 1.0
GAIN_1P = 1.0
PHASE_1P_DEG = 0.0

[[rows]]
COMPONENT = "THRUST"
J = 0.7
ALPHA = 0.0
K_1P = 0.05
OFFSET_0P = 0.0
GAIN_0P = 1.0
GAIN_1P = 1.0
PHASE_1P_DEG = 0.0
"""

_HPC_EXAMPLE = """\
# The profile of the cluster this workspace may be opened on. No row cites it:
# a run on Linux with one profile here submits each point to the scheduler
# instead of running it. One profile per workspace; several are refused.

application_id = "flightstream"   # the scheduler's own name for the application; required

# What {walltime} carries, @WALLTIME_ARITHMETIC@: wall is the row's WALLTIME as
# written (4h), seconds the whole clock in seconds (14400).
walltime_arithmetic = "wall"

# The descriptor file written in each point's folder, and its fields: the keys
# this scheduler expects, each a text in which {name} is replaced by the
# point's value of that name: sim, point, fs_build, fs_build_alias, ncpus,
# walltime, walltime_s, walltime_written, application_id, script_path or
# work_dir. A name the point cannot supply is refused, never written empty.
[descriptor]
format = "yaml"                   # @HPC_FORMATS@
name = "submit.yaml"              # a plain file name

[descriptor.fields]
ApplicationId = "{application_id}"
job_name = "FTS{sim}"
master_file = "{script_path}"
workdir = "{work_dir}"
ncpus = "{ncpus}"
walltime = "{walltime}"
version = "{fs_build_alias}"

# The submission, argument by argument, never one string through a shell;
# {descriptor_path} is the descriptor just written.
[submit]
command = ["esub", "{descriptor_path}"]

# Values the profile keeps beside its fields. A descriptor carries only what
# [descriptor.fields] writes.
[defaults]
walltime = 28800

# What this scheduler calls each build a row names, keyed by the canonical
# build: several builds may share one scheduler name. {fs_build_alias} writes it.
[builds]
"26.124" = "26.1"

# The solver's log: export_log = false on a machine that aborts at EXPORT_LOG,
# the log it writes itself, and the files its scheduler writes when a job ends.
[log]
export_log = true
native_log = "FTS{sim}.l*"
job_end_files = ["FTS{sim}.o*", "FTS{sim}.e*"]
"""

_EXECUTABLES_EXAMPLE = """\
# The build registry: what each build id of a row's FS_BUILD cell means on
# this workspace, one entry per build. A path may be a placeholder in a
# workspace kept in version control, with this machine's real path in
# executables.local.toml beside this file.

# A bare path declares no version: the rows on this build are emitted under
# the campaign's default version.
"26.120" = "C:/path/to/FlightStream_26120/FlightStream.exe"

# A table declares the version the build's scripts are emitted under, which
# lets one matrix send rows to several builds. The version is a string.
"26.124" = { path = "C:/path/to/FlightStream_26124/FlightStream.exe", version = "26.124" }
"""

_LOCAL_EXECUTABLES_EXAMPLE = """\
# This machine's paths for the builds executables.toml declares, read over it.
# Keep this file out of version control. A bare path keeps the version the
# registry declares; a table replaces the entry. A build the registry does not
# declare is refused.
"26.124" = "C:/path/to/this/machine/FlightStream.exe"
"""


def _filled(text: str) -> str:
    """Fill the value lists an example's comments name, from the code that reads them."""
    values = {
        "@RAW_PHASES@": _in_words(RAW_PHASES),
        "@FLAG_PHASES@": _in_words(FLAG_PHASES),
        "@PROFILE_UNITS@": _in_words(
            get_args(ActuatorBlock.model_fields["profile_units"].annotation)
        ),
        "@EDGE_TYPES@": _in_words(edge_types()),
        "@WALLTIME_ARITHMETIC@": _in_words(sorted(WALLTIME_ARITHMETIC)),
        "@HPC_FORMATS@": _in_words(HPC_FORMATS),
    }
    for token, value in values.items():
        text = text.replace(token, value)
    return text


#: The reason a key of a table is left out of every example because the
#: example shows the table's other form, and the comment beside it shows this.
_IN_THE_COMMENT = "the other form, shown in the comment above its table"


def _page(name: str, title: str) -> tuple[str, str]:
    """Return a documentation page the template links: ``docs/<name>.md`` and its title."""
    return (name, title)


#: The setup tables the input template's example leaves out, each with the
#: reason and its keys: the separation models, whose assignment is
#: scenario-specific, and the per-step actions of FR-319.
_SETUP_TABLES_LEFT_OUT: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "`[bulk_separation]`": MappingProxyType(
        {
            "scenario-specific assignment; select surfaces explicitly": (
                "name",
                "separation_type",
                "diameter",
                "boundaries",
            )
        }
    ),
    "`[[airfoil_separation]]`": MappingProxyType(
        {
            "scenario-specific assignment; select surfaces explicitly": (
                "name",
                "valarezo_criterion",
                "boundaries",
            )
        }
    ),
    "`[[axial_vortex_separation]]`": MappingProxyType(
        {
            "scenario-specific assignment; select surfaces explicitly": (
                "name",
                "diameter",
                "frame",
                "body_axis",
                "sharp_nose_vortices",
                "boundaries",
            )
        }
    ),
    "`[[cylindrical_bulk_separation]]`": MappingProxyType(
        {
            "scenario-specific assignment; select surfaces explicitly": (
                "name",
                "diameter",
                "boundaries",
            )
        }
    ),
    "`[[stratford_bulk_separation]]`": MappingProxyType(
        {
            "scenario-specific assignment; select surfaces explicitly": (
                "name",
                "boundaries",
            )
        }
    ),
    "`[[unsteady_solver_actions]]`": MappingProxyType(
        {
            "optional, a marching row's per-step actions": (
                "type",
                "name",
                "filename",
            )
        }
    ),
}


#: The sections of the input template, in the page's order: one per kind of
#: input file a user writes. The five artifacts the input glossary covers are
#: headed as it heads them, so a reader moving between the two pages meets one
#: name for each. A data table, evaluated once, since every value it reads is
#: a registry fixed at import.
_TEMPLATE_SECTIONS: tuple[TemplateSection, ...] = (
    TemplateSection(
        heading="The existing beam configuration, `inputs/fsi/f001.toml`",
        intro=(
            "A row selects this structural input with `FSI: f001` in VAR_NAMES_VALUES. "
            "Calculated mode integrates homogeneous solid contours using the established "
            "material dataset; supplied mode accepts the complete config.blade distributions. "
            "Dimensionless calibration defaults to unity; an explicit matrix factor replaces "
            "the file factor once."
        ),
        examples=(TemplateExample("inputs/fsi/f001.toml", "toml", FSI_TEMPLATE),),
        after=(
            "The run stages and hashes effective config.json, fsi-provenance.json and the "
            "original input per point. The existing coupling executable, node map and "
            "section-load setup remain explicit. No new section or coupled-physics "
            "validation is implied. See docs/fsi-workspace.md."
        ),
        pages=(_page("fsi-workspace", "FSI workspace inputs"),),
    ),
    TemplateSection(
        heading="Optional matrix folder, `inputs/matrices/<name>.fs`",
        intro=(
            "The Excel workbook supports matrices at the workspace root or in this folder. "
            "Every MATRIX filename is unique across those locations; new Excel-authored "
            "files use this folder."
        ),
        examples=(
            TemplateExample(
                "inputs/matrices/excel_campaign.fs",
                "text",
                _matrix_example()
                .replace("1001", "8001")
                .replace("1002", "8002")
                .replace("1003", "8003"),
            ),
        ),
        after=(
            "The optional macro-free workbook uses Runs and an editable Dictionary. "
            "Read and Write each require Preview followed by Apply or Cancel; neither "
            "runs a solver. See docs/excel-matrices.md."
        ),
        pages=(_page("excel-matrices", "Optional Excel matrix workbook"),),
    ),
    TemplateSection(
        heading="Storage recipe, `inputs/management/m<id>.toml`",
        intro=(
            "Optional: what `pyfs-matrix free-space m001 --workspace . --apply` runs. "
            "Up to four tables, each a list of steps run in this order."
        ),
        examples=(
            TemplateExample(
                "inputs/management/m001.toml",
                "toml",
                (
                    "[[prune_step_exports]]\n"
                    'sims = "all"\n'
                    "\n"
                    "[[compact_sims]]\n"
                    'sims = "all"\n'
                    'status = ["CONVERGED"]\n'
                    "\n"
                    "[[delete_extensions]]\n"
                    'extensions = [".vtk"]\n'
                    "\n"
                    "[[post_archives]]\n"
                    'action = "delete"\n'
                    "keep_latest = 1\n"
                ),
            ),
        ),
        after=(
            "`[[prune_step_exports]]` deletes the per-step exports of an unsteady "
            "point but the last step of each export; a later `post` refuses a product "
            "that needs a deleted step and names it. "
            "`[[compact_sims]]` zips a converged simulation folder to "
            "`sims/sim_<id>.zip`, restored automatically the next time `post`, "
            "`collect` or a continuation reads it. `[[delete_extensions]]` deletes "
            "files of the named extension under `sims/`; `.fsm`, scripts and logs "
            "are never deleted regardless. `[[post_archives]]` compacts or deletes "
            "the `post/<matrix>/archive/<stamp>/` folders a superseded product "
            "left, keeping the newest `keep_latest` of each matrix regardless of "
            "age. See docs/storage-and-sync.md."
        ),
        pages=(_page("storage-and-sync", "Storage and sync"),),
    ),
    TemplateSection(
        heading=ARTIFACT_HEADINGS["matrix"],
        intro=(
            "What to run: one row per simulation, each naming its flight condition, "
            "its sweep, its geometry and, by id, the three artifacts below. The "
            "matrix lives in the workspace ROOT, beside `inputs/`, under a name "
            "of your own ending in `.fs`; `pyfs-matrix plan <file> --workspace .` "
            "checks it without running anything, and `pyfs-matrix run` runs it."
        ),
        examples=(TemplateExample("campaign.fs", "text", _matrix_example()),),
        after=_matrix_after(),
        left_out=MappingProxyType(
            {
                "The `FLIGHT_CONDITION` cell": MappingProxyType(
                    {"a closed vocabulary, on the flight-conditions page": ()}
                ),
                "The row keys, by run type": MappingProxyType(
                    {"the vocabulary of every run type, with the run types that read each": ()}
                ),
            }
        ),
        pages=(
            _page("workspace-and-workflows", "The workspace and the workflow"),
            _page("flight-conditions", "Flight conditions"),
        ),
    ),
    TemplateSection(
        heading=ARTIFACT_HEADINGS["setup"],
        intro=(
            "The solver settings of a condition, shared by every row whose `SET` "
            "names it. One file per setup in `inputs/setups/`, named by its id."
        ),
        examples=(
            TemplateExample("inputs/setups/s001.toml", "toml", _filled(_SETUP_EXAMPLE)),
            TemplateExample(
                "inputs/setups/s020.toml",
                "toml",
                'farfield_layers = 5\n[[ports]]\nport = "feed"\nkind = "inlet"\n'
                'velocity_variable = "FEED_VELOCITY"\n'
                '# profile_variable = "FEED_PROFILE" # optional MATRIX filename\n'
                '[[ports]]\nport = "exit"\nkind = "outlet"\n'
                'velocity_variable = "EXIT_VELOCITY"\n',
                note=("Pair with the duct sidecar; MATRIX states FEED_VELOCITY and EXIT_VELOCITY."),
            ),
        ),
        after=(
            "A key the package keeps in the file and sends nowhere is warned "
            "about, naming the key and why, every time the setup is read; "
            '`recorded_only = ["my_setting"]` declares one of your own that way.'
        ),
        left_out=MappingProxyType(
            {
                "Solver settings": MappingProxyType(
                    {
                        "optional; unstated, each keeps the default INPUTS.md gives": (
                            _SETTINGS_LEFT_OUT
                        ),
                        "the direct form of the stabilization pair the example states": (
                            "solver_stabilization",
                        ),
                    }
                ),
                "`[[ports]]`": MappingProxyType(
                    {
                        "optional MATRIX profile and explicit remesh": (
                            "profile_variable",
                            "remesh",
                        ),
                    }
                ),
                "`[ports.remesh]`": MappingProxyType(
                    {
                        "optional radial remeshing before profile assignment": (
                            "inner_radius_m",
                            "radial_faces",
                            "growth_scheme",
                            "growth_rate",
                        ),
                    }
                ),
                **_SETUP_TABLES_LEFT_OUT,
                "`[[actuator_operations]]`": MappingProxyType(
                    {
                        "explicit actions require actual saved or created actuator names": (
                            "op",
                            "actuator",
                            "name",
                        )
                    }
                ),
                "`[[base_region_operations]]`": MappingProxyType(
                    {
                        "explicit ordered actions depend on existing base-region state": (
                            "operation",
                            "boundary",
                            "index",
                            "model",
                            "cp",
                            "mesh",
                        )
                    }
                ),
                "`[base_region_operations.mesh]`": MappingProxyType(
                    {
                        "radial mesh parameters apply to a remesh action only": (
                            "inner_radius_m",
                            "radial_faces",
                            "growth_scheme",
                            "growth_rate",
                        )
                    }
                ),
                "The solver's own names, read as aliases": MappingProxyType(
                    {"the solver's own spellings of the settings; either is read": ()}
                ),
                "Recorded, and emitting nothing": MappingProxyType(
                    {"kept in the file and sent nowhere, each warned about": ()}
                ),
                "Tables and reserved keys": MappingProxyType(
                    {
                        "names keys of your own to keep and send nowhere, each warned about": (
                            "recorded_only",
                        ),
                    }
                ),
            }
        ),
        pages=(
            _page("settings-codebook", "The settings codebook"),
            _page("flight-conditions", "Flight conditions"),
        ),
    ),
    TemplateSection(
        heading=ARTIFACT_HEADINGS["pproc"],
        intro=(
            "What each point defines before the solve, exports after it, and "
            "which products the campaign writes, shared by every row whose "
            "`PPROC` names it. One file per artifact in `inputs/pproc/`, beside "
            "the three generated guides."
        ),
        examples=(
            TemplateExample("inputs/pproc/p001.toml", "toml", _PPROC_EXAMPLE),
            TemplateExample("inputs/pproc/p002.toml", "toml", _SURFACE_PROBE_EXAMPLE),
        ),
        after=(
            "Some tables belong to one kind of run. The unsteady force plots, the "
            "phase-locked table and the equations serve the unsteady run types, "
            "and a steady row passes them over. Volume sampling supports both run "
            "types. Unsteady section Cp describes the final instant, not a time "
            "average. The residual and load plots are saved on both. "
            "The separate p002 example records native surface properties during an "
            "unsteady march, using SURFACE_<name> plot columns. A steady row refuses it. "
            "Every table is read and checked when the file is, so a mistake in one "
            "is refused on any row."
        ),
        left_out=MappingProxyType(
            {
                "The tables and top-level keys": MappingProxyType(
                    {
                        "an unsteady row's surface average, which a steady row refuses; "
                        "INPUTS.md names the builds": ("time_averaging",),
                        "an unsteady rotor's drift limit, 1 per cent where the table is absent": (
                            "per_revolution",
                        ),
                        "a quasi-steady wheel's correction route, off where the table "
                        "is absent; its calibration file has a section of its own": (
                            "qsteady_correction",
                        ),
                    }
                ),
                "`[per_revolution]`": MappingProxyType(
                    {"the table is left out, for the reason above": ("drift_limit_pct",)}
                ),
                "`[qsteady_correction]`": MappingProxyType(
                    {
                        "the table is left out, for the reason above": (
                            "route",
                            "file",
                            "diagnostic",
                        ),
                    }
                ),
                "`[time_averaging]`": MappingProxyType(
                    {
                        "the table is left out, for the reason above": (
                            "last_revs",
                            "last_iters",
                        ),
                    }
                ),
                "`[volume_section]`": MappingProxyType(
                    {"a circle's keys, " + _IN_THE_COMMENT: ("radii_m", "points")}
                ),
            }
        ),
        pages=(
            _page("post-processing-definitions", "The post-processing definitions"),
            _page("workspace-and-workflows", "The workspace and the workflow"),
        ),
    ),
    TemplateSection(
        heading=ARTIFACT_HEADINGS["reference"],
        intro=(
            "What a configuration IS, shared by every row whose `REF` names it: "
            "the reference lengths, the moment point, the frames, your aliases, "
            "and one block per rotor, actuator disc and named point. One file "
            "per reference in `inputs/references/`."
        ),
        examples=(
            TemplateExample("inputs/references/r001.toml", "toml", _filled(_REFERENCE_EXAMPLE)),
        ),
        after=(
            "A block is told apart by its `kind`, so its NAME is yours: the word "
            "a row moves or names. A name may be no other block's, alias's or "
            "frame's, and a rotor's name may not carry `_SMRP` or `_RMRP`, the "
            "frames the package builds for it."
        ),
        left_out=MappingProxyType(
            {
                table: MappingProxyType(
                    {"the kind a named point states, which says nothing of this one": ("kind",)}
                )
                for table in ("`[moment_point]`", "`[rotor.position]`")
            }
        ),
        pages=(
            _page("workspace-and-workflows", "The workspace and the workflow"),
            _page("mesh-inputs", "Mesh inputs"),
        ),
    ),
    TemplateSection(
        heading="The named reference points, `inputs/reference_points.toml`",
        intro=(
            "Optional, one per workspace: the points a row may name instead of "
            "writing coordinates, written once for the whole campaign."
        ),
        examples=(
            TemplateExample(f"inputs/{REFERENCE_POINTS_FILE}", "toml", _REFERENCE_POINTS_EXAMPLE),
        ),
        after=(
            "A name outside the convention is refused, and a rotor motion may "
            "turn only about a rotor point. Every key a point takes is in the "
            f"example; {_GLOSSARY_LINK} lists the keys of the files a row cites."
        ),
        pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
    ),
    TemplateSection(
        heading=ARTIFACT_HEADINGS["geometry"],
        intro=(
            "The file beside a geometry that names its boundaries, "
            "`<stem>.boundaries.toml`. A geometry sits in `inputs/geometries/` "
            "directly, or in a folder named by its stem with everything that "
            "belongs to it, which is the layout the examples use; a row's "
            "`GEOMETRY` names the file the same way in both. A saved simulation "
            "(`.fsm`) gets its sidecar from `pyfs-matrix inventory`. An OBJ with no "
            "sidecar gets one from the plan, its `boundaries` read from the OBJ's "
            "groups, and an STL's is written by hand; beside a raw mesh, you add how "
            "it is imported and where its trailing edges are."
        ),
        examples=(
            TemplateExample(
                "inputs/geometries/aircraft/aircraft.boundaries.toml",
                "toml",
                _INVENTORY_EXAMPLE,
                note="Beside a saved simulation, `aircraft.fsm`:",
            ),
            TemplateExample(
                "inputs/geometries/wing_raw/wing_raw.boundaries.toml",
                "toml",
                _filled(_RAW_MESH_SIDECAR_EXAMPLE),
                note="Beside a raw mesh, `wing_raw.obj`:",
            ),
            TemplateExample(
                "inputs/geometries/wing_cad/wing_cad.boundaries.toml",
                "toml",
                (
                    'file = "wing_cad.igs"\n'
                    'boundaries = ["Wing"]\n'
                    "\n"
                    "[import]\n"
                    'units = "FILE"\n'
                    "\n"
                    "[import.cad]\n"
                    'tessellation_density = "MEDIUM"\n'
                    "unreferenced_patches = true\n"
                    "num_curvature = 80\n"
                    "body_index = -1\n"
                    "\n"
                    "[trailing_edges]\n"
                    'detect = "auto"\n'
                ),
                note="CAD conversion: inspect source dimensions and converted boundaries:",
            ),
            TemplateExample(
                "inputs/geometries/duct/duct.boundaries.toml",
                "toml",
                _DUCT_SIDECAR_EXAMPLE,
                note="Uniform normal-velocity ports on a synthetic closed duct:",
            ),
        ),
        left_out=MappingProxyType(
            {
                "`[[import.operations]]`": MappingProxyType(
                    {
                        "the keys of the other operations, shown in the comment": (
                            "factors",
                            "vector",
                            "axis",
                            "angle_deg",
                            "plane",
                        ),
                    }
                ),
                "`detect = { ... }` of `[trailing_edges]`": MappingProxyType(
                    {_IN_THE_COMMENT: ("surfaces", "sweep_angle")}
                ),
                # 0.32.0 (package C): beside a CCS file only, which the
                # CCS geometry page shows with every key.
                "`[import]`": MappingProxyType(
                    {"beside a CCS file only, shown on the CCS geometry page": ("ccs",)}
                ),
                "`[import.ccs]`": MappingProxyType(
                    {"the table is left out, for the reason above": ()}
                ),
                "`[import.ccs.subdivisions]`": MappingProxyType(
                    {"the table is left out, for the reason above": ()}
                ),
                "`[[import.ccs.control_surfaces]]`": MappingProxyType(
                    {"the table is left out, for the reason above": ()}
                ),
            }
        ),
        pages=(
            _page("mesh-inputs", "Mesh inputs"),
            _page("ccs-geometry", "CCS geometry"),
            _page("workspace-and-workflows", "The workspace and the workflow"),
        ),
    ),
    TemplateSection(
        heading="The trailing-edge points file, beside a raw mesh's sidecar",
        intro=(
            "The mid-point of every trailing-edge edge of a raw mesh, named by "
            "the `file` key of the sidecar's `[trailing_edges]` table and kept "
            "beside the sidecar. It holds no comment: the first line names the "
            "length unit of the points, one of "
            f"{_in_words(_scaled_units())}, and every later line is one point, "
            "`x,y,z`, three numbers separated by commas. The unit is what lets "
            "the run convert the points to the simulation's metres; each point "
            "is matched to an edge of the mesh within the sidecar's `tolerance`."
        ),
        examples=(
            TemplateExample(
                "inputs/geometries/wing_raw/wing_raw.te.txt",
                "text",
                _TRAILING_EDGE_POINTS_EXAMPLE,
            ),
        ),
        after=(
            f"It has no keys of its own; the sidecar's are in {_GLOSSARY_LINK}. "
            "`pyflightstream.workspace.wake_edges.write_trailing_edge_points` "
            "writes one from a list of points."
        ),
        pages=(_page("mesh-inputs", "Mesh inputs"),),
    ),
    TemplateSection(
        heading="The provenance record, `<stem>.provenance.toml` beside a geometry",
        intro=(
            "Optional: where a geometry came from, kept beside it as TOML. The "
            "package reads no key of it, so the keys are yours; it keeps the "
            "record out of what a `GEOMETRY` cell can name and moves it with its "
            "geometry (`pyfs-workspace migrate-geometries`)."
        ),
        examples=(
            TemplateExample(
                "inputs/geometries/aircraft/aircraft.provenance.toml",
                "toml",
                _PROVENANCE_EXAMPLE,
            ),
        ),
        after=f"No key of it is read, so none is in {_GLOSSARY_LINK}.",
        pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
    ),
    TemplateSection(
        heading="The actuator radial thrust profile, `inputs/profiles/<stem>.<ext>`",
        intro=(
            "The load of an actuator disc along its radius, for a row that names "
            "a disc and states `PROFILE: <stem>`, the file's name without its "
            "extension. One row per radial station, `r,F`: the station as a "
            "fraction of the tip radius, and the sectional thrust per unit span of "
            "ONE blade, in the force unit the disc block's `profile_units` names. "
            "The numbers pass to the solver as written. No header, no count "
            "and no comment: the solver reads every line as a point, so the file "
            "holds the rows and nothing else, at least two of them. The disc's "
            "`blades` says how many blades the distribution is per."
        ),
        examples=(
            TemplateExample("inputs/profiles/prop_thrust.txt", "text", _ACTUATOR_PROFILE_EXAMPLE),
        ),
        after=(
            "The file stays as your editor saved it: the run writes the copy the "
            "solver reads, with no final newline and no blank line, where the "
            f"point runs. The disc's keys are in {_GLOSSARY_LINK}, under the "
            "reference's actuator block, and the row's under the row keys."
        ),
        pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
    ),
    TemplateSection(
        heading="The probe survey, `inputs/profiles/<name>`",
        intro=(
            "Points to sample the flow at, for a pproc `[[probes]]` entry that "
            'states `points_file = "<name>"`, the file\'s name with its '
            "extension, instead of drawing lines and planes. The first line is "
            "the count of points; every later line is one point, `X,Y,Z,TYPE`, "
            "TYPE 0 for a point on the surface and 1 for one in the volume. No "
            "comment and no header."
        ),
        examples=(
            TemplateExample("inputs/profiles/wake_survey.csv", "csv", _PROBE_SURVEY_EXAMPLE),
        ),
        after=(
            "On a steady row the script imports the file where it lives, its "
            "coordinates in metres in the reference frame; on an unsteady row "
            "the plan reads it and places each point in the entry's `frame` and "
            f"`scale`. The entry's keys are in {_GLOSSARY_LINK}, under "
            "`[[probes]]`."
        ),
        pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
    ),
    TemplateSection(
        heading=f"The custom free stream, `inputs/{FREESTREAM_DIR}/<stem>.txt`",
        intro=(
            "A velocity field over the YZ plane of the global frame, for a row "
            "stating `FREESTREAM: <stem>`, which the run writes in place of the "
            "constant free stream. The extension is the form: "
            + _in_words(
                [f"`{suffix}` is {form}" for suffix, form in FREESTREAM_FORMS.items()],
                "and",
            )
            + ". The STRUCTURED form is shown: a first line `Npts Mpts`, two "
            "positive integers, then Npts x Mpts rows `x y z vx vy vz`, the first "
            "index outer and the second inner. This example is in metres and metres "
            "per second: state `FREESTREAM_UNITS: SI` to prepare a native-unit copy. "
            "`NATIVE` preserves already-native bytes; omission preserves legacy bytes. "
            "Every row states the same x, and the rows state at least two "
            "distinct y and two distinct z. The UNSTRUCTURED form is the rows "
            "alone, one per vertex, with no first line. No comment in either."
        ),
        examples=(
            TemplateExample(f"inputs/{FREESTREAM_DIR}/gust.txt", "text", _FREESTREAM_EXAMPLE),
        ),
        after=(
            "The field sets the flow's direction, so a row flying through one "
            "states zero angles of attack and sideslip, and no body rate: write an "
            "incidence into vy and vz. The body is then loaded as at that incidence, "
            "and the loads export prints CL and CDi in the axes of the zero angle the "
            "row states, so read the body forces Cx, Cy and Cz, or turn CL and CDi by "
            "the field's incidence. Make the grid reach past the body: beyond it the "
            "solver does not extend the field, and the plan warns when the body "
            "reaches outside a conservative transformed-body and rotary-sweep envelope. "
            "Grid-bounds containment alone does not certify interior interpolation. "
            "Source/effective hashes bind an explicitly converted copy. "
            "Both forms were run on FlightStream 26.124 "
            f"(RPT-071, RPT-077, RPT-082). The row key is in {_GLOSSARY_LINK}, under the row "
            "keys."
        ),
        pages=(_page("gui-to-pyfs", "From the GUI to pyfs"),),
    ),
    TemplateSection(
        heading=f"The quasi-steady wheel calibration, `inputs/{CALIBRATIONS_DIR}/<id>.toml`",
        intro=(
            "Optional (0.31.0): the calibration a pproc's `[qsteady_correction]` "
            'table names by its id, `file = "<id>"`, for a `qsteady_rotor` wheel. '
            "The post writes each corrected product beside its raw file, "
            "`<name>_corrected.csv`, and never over it; no route is validated. "
            "`route` is `table` (a surface you fitted) or `sector_offset` (a 0P "
            "offset from an axial unsteady sector run, which the file names in "
            "`source_run_id`). Each `[[rows]]` names a `COMPONENT`, its place on "
            "the axes `J`, `ALPHA` and `K_1P`, and `OFFSET_0P`, `GAIN_0P`, `GAIN_1P` "
            "and `PHASE_1P_DEG`; the rows of one component form a grid over the "
            "axes that vary."
        ),
        examples=(
            TemplateExample(f"inputs/{CALIBRATIONS_DIR}/c001.toml", "toml", _CALIBRATION_EXAMPLE),
        ),
        after=(
            "Inside the grid the coefficients are interpolated multilinearly; a point "
            "outside it is never extrapolated, and is named in `products.json` and "
            "`post.log`. The plan reads the file a row's pproc names and refuses it "
            "naming the line; the post reads it again, so a route is chosen or "
            "changed with no new run."
        ),
        pages=(_page("qsteady-corrections", "Quasi-steady wheel corrections"),),
    ),
    TemplateSection(
        heading=f"The HPC profile, `inputs/{HPC_DIR}/<name>.toml`",
        intro=(
            "How the cluster this workspace may be opened on is asked to run a "
            "job: the descriptor file it reads, the command that submits it, and "
            "what it calls each build. Optional, and at most one per workspace."
        ),
        examples=(TemplateExample(f"inputs/{HPC_DIR}/h001.toml", "toml", _filled(_HPC_EXAMPLE)),),
        after=(
            "A key the package does not read is refused, naming it, and so is "
            "`export_log` or `native_log` written under any table but `[log]`. "
            f"Every key a profile takes is in the example; {_GLOSSARY_LINK} lists "
            "the keys of the files a row cites."
        ),
        pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
    ),
    TemplateSection(
        heading=f"The build registry, `inputs/{EXECUTABLES_FILE}`",
        intro=(
            "What each build id a row's `FS_BUILD` names means: the solver's "
            "executable and, optionally, the version its scripts are emitted "
            "under. `pyfs-workspace init` writes a commented one; replace it with "
            "entries like these."
        ),
        examples=(TemplateExample(f"inputs/{EXECUTABLES_FILE}", "toml", _EXECUTABLES_EXAMPLE),),
        after=(
            "An entry is a path, or a table of `path` and `version` and nothing "
            "else; any other key is refused, naming it. Every key an entry takes "
            f"is in the example; {_GLOSSARY_LINK} lists the keys of the files a "
            "row cites."
        ),
        pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
    ),
    TemplateSection(
        heading=f"This machine's paths, `inputs/{LOCAL_EXECUTABLES_FILE}`",
        intro=(
            "Optional: the real paths of the builds on this machine, for a "
            "workspace whose registry keeps placeholders because it is in version "
            "control. Read over the registry; keep it out of version control."
        ),
        examples=(
            TemplateExample(f"inputs/{LOCAL_EXECUTABLES_FILE}", "toml", _LOCAL_EXECUTABLES_EXAMPLE),
        ),
        after=(
            f"Its entries take the registry's shapes; {_GLOSSARY_LINK} lists the "
            "keys of the files a row cites."
        ),
        pages=(_page("workspace-and-workflows", "The workspace and the workflow"),),
    ),
)


_TEMPLATE_INTRO = (
    "One section per kind of input file you write, each with what the file is "
    "for, where it lives, and a complete example to copy. Copy an example to the "
    "path its block's title names, relative to the workspace root, and edit the "
    "values: every example is a file the package reads as it stands, and the "
    "test suite writes each one where its title says and reads it with the "
    "function the run reads it with. The examples cite each other, so the matrix "
    "runs against the setup, the pproc, the reference, the geometry, the profile "
    "and the free stream shown here. What every key of the matrix row, the "
    f"setup, the pproc, the reference and the geometry sidecar sets, with its "
    f"unit and its values, is in the input glossary, {_GLOSSARY_LINK}; a key an "
    "example leaves out is named under it, with the reason."
)


def _left_out_lines(section: TemplateSection) -> list[str]:
    if not section.left_out:
        return []
    lines = [
        "**Left out of the example.** Each is a key this file may state; what it sets, "
        f"its unit and its values are in {_GLOSSARY_LINK}, under the table named.",
        "",
    ]
    for table, reasons in section.left_out.items():
        for reason, keys in reasons.items():
            named = "every key" if not keys else ", ".join(f"`{key}`" for key in keys)
            lines.append(f"- **{table}** ({reason}): {named}.")
    lines.append("")
    return lines


def input_template_markdown() -> str:
    """Return the input template, ``input_template.md``, as Markdown.

    One section per kind of input file a user writes, each with what the file
    is for, where it lives and a complete example: the run matrix, the setup,
    the pproc, the reference, the named points, the geometry sidecar and the
    trailing-edge points file beside it, the provenance record, the actuator
    profile and the probe survey of ``profiles/``, the custom free stream, the
    HPC profile and the build registry with its overlay. Each example is a
    file the package reads as it stands, and the keys an example leaves out are
    named with the reason. Generated on every call.

    Examples
    --------
    >>> text = input_template_markdown()
    >>> text.splitlines()[0]
    '# Input templates'
    >>> 'title="inputs/setups/s001.toml"' in text
    True
    """
    sections = _TEMPLATE_SECTIONS
    lines = ["# Input templates", "", _GENERATED, "", _TEMPLATE_INTRO, "", "Sections:", ""]
    lines += [f"- {section.heading}" for section in sections]
    for section in sections:
        lines += ["", f"## {section.heading}", "", section.intro, ""]
        for example in section.examples:
            if example.note:
                lines += [example.note, ""]
            lines.append(f'```{example.language} title="{example.path}"')
            lines += [example.text.rstrip("\n"), "```", ""]
        if section.after:
            lines += [section.after, ""]
        lines += _left_out_lines(section)
        links = [_GLOSSARY_LINK] + [_page_link(name, title) for name, title in section.pages]
        lines += [f"Read more: {'; '.join(links)}."]
    lines.append("")
    return "\n".join(lines)


def write_input_template(folder: str | Path, *, changed: list[Path] | None = None) -> Path:
    """Write the input template, ``input_template.md``, into ``folder``; return its path.

    Rewritten only when its content would change, so the call is idempotent
    and leaves a versioned workspace clean.

    Parameters
    ----------
    folder : str or pathlib.Path
        Where to write it: the ``inputs`` folder of a workspace. Created if it
        is not there.
    changed : list, optional
        Receives the page when this call actually wrote it.

    Returns
    -------
    pathlib.Path
        The page, written or not.

    Examples
    --------
    >>> import tempfile
    >>> folder = tempfile.mkdtemp()
    >>> first: list = []
    >>> write_input_template(folder, changed=first).name
    'input_template.md'
    >>> again: list = []
    >>> _ = write_input_template(folder, changed=again)
    >>> len(first), len(again)
    (1, 0)
    """
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    page = target / INPUT_TEMPLATE_NAME
    if _write_if_different(page, input_template_markdown()) and changed is not None:
        changed.append(page)
    return page


def write_workspace_input_template(inputs_dir: str | Path) -> list[Path]:
    """Write ``input_template.md`` at the root of ``inputs_dir``; return it if it CHANGED.

    The input-guide writer this package registers with
    :func:`pyflightstream.workspace.register_input_guide` beside the glossary,
    which is how ``pyfs-workspace init``, ``pyfs-matrix plan`` and
    ``pyfs-matrix post`` reach it.
    """
    changed: list[Path] = []
    write_input_template(inputs_dir, changed=changed)
    return changed
