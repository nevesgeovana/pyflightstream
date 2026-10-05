"""The post-processing models: what a point exports and what the post reduces (0.34.0).

Pipeline role: describes the pproc artifact. The exports vocabulary names every
file a point can leave and the solver command that writes it
(:data:`EXPORT_KINDS`, :func:`default_outputs`, :func:`classify_outputs`);
:class:`PprocSpec` and its parts declare the sections, the volume section, the
force and fluid plots, the probes, the products and the unsteady reductions a
run asks for. The workflows read it to emit the exports and the post stage
reads it to reduce them.

The cut of AD-16 (0.34.0) moved these models out of the package root, which
re-exports every one of them, so ``pyflightstream.cases.PprocSpec`` and
``pyflightstream.cases.pproc.PprocSpec`` are one class. This module imports
:mod:`pyflightstream.cases.selection` for the family selectors and never the
package root.
"""

from __future__ import annotations

import math
import re
import string
from collections.abc import Mapping, Sequence
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from pyflightstream._deprecations import ROW_EACH_BLADE, refusal_text
from pyflightstream._errors import InputArtifactError
from pyflightstream._expressions import ALLOWED_FUNCTIONS, expression_symbols
from pyflightstream._retired_names import PROBE_SCALE_PROPELLER_RADIUS
from pyflightstream._tokens import REDUCTION_COLUMNS

# The quasi-steady wheel's correction choice (0.31.0), a table of the pproc; its
# module imports only the floor, so the package may import it while it loads.
from pyflightstream.cases.corrections import QsteadyCorrectionSpec
from pyflightstream.cases.selection import EVERY_FAMILY
from pyflightstream.commands import CommandRegistry

__all__ = [
    "DEFAULT_DRIFT_LIMIT_PCT",
    "EXPORT_KINDS",
    "EXPORT_KIND_MEANINGS",
    "EXPORT_KIND_SINCE",
    "OPT_IN_EXPORT_KINDS",
    "PLOT_TYPES",
    "STEADY_ONLY_EXPORT_KINDS",
    "FAMILY_SELECTORS",
    "FLUID_PLOT_PARAMETERS",
    "AXES_PLOT_COMPONENTS",
    "global_frame_plot_declarations",
    "AXES_PLOT_GROUP",
    "ROTOR_PLOT_GROUP_PREFIX",
    "FORCE_PLOT_PARAMETERS",
    "PPROC_FRAMES",
    "PprocSpec",
    "SurfaceTimeAveragingSpec",
    "SectionsSpec",
    "VOLUME_SECTION_KINDS",
    "VOLUME_SECTION_PRISMS",
    "VolumeSectionSpec",
    "PlotsSpec",
    "ProbesSpec",
    "SurfaceProbeSpec",
    "ProductsSpec",
    "ForcePlotGroup",
    "SectionDistribution",
    "ProbeLine",
    "default_outputs",
    "classify_outputs",
]


#: THE EXPORT KINDS A POINT LEAVES (FR-51, PFS-2029.14), in the order the
#: the reference driver wrote them and with the reference suffixes: (kind, suffix, the
#: solver verb, unsteady only). A steady point leaves probe points; an unsteady
#: point leaves plots history in their place. The suffix is
#: what pairs a declared output name with its verb, longest suffix first, so
#: ``x_cp.txt`` is the sections export and never the loads table.
#:
#: NO SUFFIX ENDS WITH ANOTHER KIND'S, except a bare extension. The longest-first
#: rule settles ``_cp.txt`` against ``.txt``, and only that shape: the sections
#: plot is ``_plot_cp_sections.txt`` and not ``_plot_sections_cp.txt``, which
#: would end with the sections kind's ``_cp.txt``, and no plot suffix ends with
#: the unsteady kind's ``_plots.txt``.
#:
#: THE TECPLOT KIND'S VERB IS THE SOLVER'S, AND NO CAMPAIGN EMITS IT (G45 of
#: 0.28.0): the script exports the VTK in its place and the package writes the
#: ``.dat`` from it (:func:`~pyflightstream.cases.workflows.tecplot_source`). The
#: suffix is what the kind is, and it is unchanged.
#:
#: THE SOLVER'S OWN PLOTS (G04 of 0.27.0, RPT-067) are three kinds sharing one
#: verb, ``SAVE_PLOT_TO_FILE``, which saves whichever plot ``SET_PLOT_TYPE``
#: chose; :data:`PLOT_TYPES` names the plot each kind chooses. They sit after
#: every other export and before the log, which is where RPT-067 ran them.
EXPORT_KINDS: tuple[tuple[str, str, str, bool], ...] = (
    ("simulation", ".fsm", "SAVEAS", False),
    ("loads", ".txt", "EXPORT_SOLVER_ANALYSIS_SPREADSHEET", False),
    ("tecplot", ".dat", "EXPORT_SOLVER_ANALYSIS_TECPLOT", False),
    ("vtk", ".vtk", "EXPORT_SOLVER_ANALYSIS_VTK", False),
    ("csv", ".csv", "EXPORT_SOLVER_ANALYSIS_CSV", False),
    (
        "force_distributions",
        "_force_distributions.txt",
        "EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS",
        False,
    ),
    # G05 (0.27.0): the pproc's ONE volume section, in the format its table
    # names. `_vsec` is the only thing telling the file from a surface export
    # of the same extension, so it is claimed first (the longest suffix).
    ("volume_section_vtk", "_vsec.vtk", "EXPORT_VOLUME_SECTION_VTK", False),
    ("volume_section_tecplot", "_vsec.dat", "EXPORT_VOLUME_SECTION_TECPLOT", False),
    ("sections", "_cp.txt", "EXPORT_ALL_SURFACE_SECTIONS", False),
    ("sectional_loads", "_sloads.txt", "EXPORT_SURFACE_SECTIONAL_LOADS", False),
    ("probes", "_probes.txt", "EXPORT_PROBE_POINTS", False),
    ("plots", "_plots.txt", "UNSTEADY_SOLVER_EXPORT_PLOTS", True),
    ("plot_residuals", "_plot_residuals.txt", "SAVE_PLOT_TO_FILE", False),
    ("plot_loads", "_plot_loads.txt", "SAVE_PLOT_TO_FILE", False),
    ("plot_sections_cp", "_plot_cp_sections.txt", "SAVE_PLOT_TO_FILE", False),
    ("log", "_log.txt", "EXPORT_LOG", False),
)

#: The plot each solver-plot kind chooses with ``SET_PLOT_TYPE`` before its
#: ``SAVE_PLOT_TO_FILE`` (RPT-067, 26.124). The file is the plotted SERIES as
#: text: the residual and load histories one row per solver iteration, the
#: section Cp one x/Cp column pair per section. A plot is a display of the
#: solve and never a source of a coefficient: RPT-067's plotted pitching
#: moment is not the exported CMy, so every coefficient keeps coming from the
#: loads export.
PLOT_TYPES: dict[str, str] = {
    "plot_residuals": "RESIDUALS",
    "plot_loads": "LOADS",
    "plot_sections_cp": "SECTIONS_CP",
}

#: THE VOLUME-SECTION KINDS, by the format ``[volume_section]`` names (G05).
#: They are NOT in the default export set and ``[exports]`` cannot name them:
#: a point declares one only because its pproc declares a section, and in the
#: format that section says.
VOLUME_SECTION_KINDS: dict[str, str] = {
    "vtk": "volume_section_vtk",
    "tecplot": "volume_section_tecplot",
}

#: THE RELEASE EACH KIND ENTERED IN, for every kind younger than the first
#: release that wrote run records' outputs this way (0.27.0). A RECORDED output
#: is read as the release that wrote the record read it: a record of an earlier
#: release claims none of these suffixes, so its ``P_vsec.vtk`` is the surface
#: VTK export it was when written, and upgrading the reader does not rewrite
#: what the record says (:func:`classify_outputs`, ``package_version``).
EXPORT_KIND_SINCE: dict[str, tuple[int, int]] = {
    "force_distributions": (0, 27),
    "volume_section_vtk": (0, 27),
    "volume_section_tecplot": (0, 27),
    "plot_residuals": (0, 27),
    "plot_loads": (0, 27),
    "plot_sections_cp": (0, 27),
}


#: An unsteady point samples probes through fluid plots. Section Cp plots
#: are saved once after the march (GOAL-033 T40, 26.124 build 8172026).
STEADY_ONLY_EXPORT_KINDS: frozenset[str] = frozenset({"probes"})

#: FR-417: the probe kinds a ``[[probes]]`` entry may state. ``unsteady`` (the
#: default) samples through fluid plots at every time step; ``normal`` creates
#: probe points after the time march and exports them once.
ProbeKind = Literal["unsteady", "normal"]
PROBE_KINDS: tuple[str, ...] = get_args(ProbeKind)

#: The kinds a pproc must switch ON: every other kind is on unless its
#: ``[exports]`` entry says false. The surface fields and the per-panel force
#: distribution (G10 of 0.27.0) grow with the mesh, so they are asked for
#: where they are wanted.
OPT_IN_EXPORT_KINDS: tuple[str, ...] = ("vtk", "csv", "force_distributions")

#: What each kind an ``[exports]`` table may name leaves, one sentence each,
#: for the generated input glossary ``INPUTS.md`` (G08 of 0.27.0). The command
#: and the run types a kind is written on are read off :data:`EXPORT_KINDS`
#: and the two tuples above, so this states what the file IS and nothing else.
#: The two volume-section kinds are not here: ``[exports]`` cannot name them.
EXPORT_KIND_MEANINGS: dict[str, str] = {
    "simulation": "The point's final saved simulation, its solver state after the solve.",
    "loads": "The loads table, the export every run is judged by.",
    "tecplot": (
        "The surface solution in Tecplot format, written by the package from the VTK "
        "export, preserving panel values in the reference frame; the native nodal "
        "singularity strength is carried only where the pproc sets "
        "singularity_strength = true."
    ),
    "vtk": (
        "The surface solution in VTK format, as the solver writes it; the Tecplot is "
        "written from this same file."
    ),
    "csv": "The surface solution as a CSV table.",
    "force_distributions": ("The per-panel force distribution, saved once at the end of the run."),
    "sections": "The pressure distribution of every surface section the pproc declares.",
    "sectional_loads": "The sectional loads of every surface section the pproc declares.",
    "probes": "The flow quantities at the probe points, after a steady solve.",
    "plots": "The force and fluid plot histories of an unsteady run, one row per time step.",
    "plot_residuals": "The solver's residual history as a text series, one row per iteration.",
    "plot_loads": "The solver's load history as a text series, one row per iteration.",
    "plot_sections_cp": "The section Cp plot as a text series, one x and Cp pair per section.",
    "log": "The solver log, which turns a run into a residual verdict.",
}


def default_outputs(
    unsteady: bool,
    exports: Mapping[str, bool] | None = None,
    *,
    has_sections: bool = False,
    normal_probes: bool = False,
) -> list[str]:
    """Return the output names a workflow row gets when it declares none.

    Every kind hangs off ``{name}``, the point's rendered stem, so the
    naming template decides the stem and this list decides the suffixes
    (PFS-2029.19); a steady row leaves out the plots file, and an unsteady row
    leaves out every kind of :data:`STEADY_ONLY_EXPORT_KINDS`: the probe-points
    instant export and the solver's own plots. ``exports`` is
    the pproc artifact's
    ``[exports]`` table (PFS-2029.14.02): a kind set to false is left
    out. Unstated kinds are kept except those of :data:`OPT_IN_EXPORT_KINDS`,
    so an empty table preserves the existing export set, and except the
    section Cp plot, which is on where ``has_sections`` says the pproc declares
    surface sections to plot. The
    artifact cannot set ``loads`` or ``simulation`` to false
    (:class:`PprocSpec` refuses both), so every row naming a run type
    declares its loads table and its final saved simulation. The two
    volume-section kinds are never here: :meth:`PprocSpec.outputs` adds the
    one a declared ``[volume_section]`` names.

    Parameters
    ----------
    unsteady : bool
        Whether the row is unsteady.
    exports : mapping of str to bool, optional
        The pproc artifact's ``[exports]`` table.
    has_sections : bool, optional
        Whether the pproc declares surface sections to plot.
    normal_probes : bool, optional
        Whether an unsteady row samples its pproc's probes as normal probe
        points (FR-417), whose probe-points export it then keeps.

    Returns
    -------
    list of str
        The output names, each ``{name}`` followed by its kind's suffix, in
        the order of :data:`EXPORT_KINDS`.
    """
    chosen = exports or {}

    def wanted(kind: str) -> bool:
        if kind == "plot_sections_cp":
            return chosen.get(kind, has_sections)
        return chosen.get(kind, kind not in OPT_IN_EXPORT_KINDS)

    return [
        f"{{name}}{suffix}"
        for kind, suffix, _, only_unsteady in EXPORT_KINDS
        if (unsteady or not only_unsteady)
        and kind not in VOLUME_SECTION_KINDS.values()
        and not (unsteady and not normal_probes and kind in STEADY_ONLY_EXPORT_KINDS)
        and wanted(kind)
    ]


def classify_outputs(names: Sequence[str], *, package_version: str | None = None) -> dict[str, str]:
    """Map each export kind to the declared output name that carries its suffix.

    Longest suffix first, so ``_cp.txt`` is claimed by the sections kind
    before the loads kind can see a ``.txt``. A kind no name matches is
    absent from the result; a second name matching an already claimed
    kind is left unclassified rather than overwriting the first.

    Parameters
    ----------
    names : sequence of str
        The output names, declared or recorded.
    package_version : str, optional
        The ``package_version`` of the RUN RECORD the names come from. A
        record written by a release before a kind entered
        (:data:`EXPORT_KIND_SINCE`) is read without that kind, as its release
        read it: a 0.26.0 record's ``P_vsec.vtk`` is its surface VTK export,
        not a volume section. None, or a version that states no release,
        reads by the kinds of this release, as a name being declared now is.

    Returns
    -------
    dict of str to str
        Each export kind a name carries, mapped to that name.

    Examples
    --------
    >>> from pyflightstream.cases import classify_outputs
    >>> classify_outputs(["P_vsec.vtk"])
    {'volume_section_vtk': 'P_vsec.vtk'}
    >>> classify_outputs(["P_vsec.vtk"], package_version="0.26.0")
    {'vtk': 'P_vsec.vtk'}
    """
    release = _release_of(package_version)
    known = [
        kind
        for kind in EXPORT_KINDS
        if release is None or EXPORT_KIND_SINCE.get(kind[0], release) <= release
    ]
    by_length = sorted(known, key=lambda kind: -len(kind[1]))
    claimed: dict[str, str] = {}
    for name in names:
        lowered = str(name).lower()
        # G53: retain this nodal source without presenting it as a public product.
        # Older records keep their historical suffix interpretation.
        if (release is None or release >= (0, 29)) and lowered.endswith("_native_tecplot.dat"):
            continue
        # 0.32.0 (E2): an acoustic export or section file is never a surface export.
        if (release is None or release >= (0, 32)) and _is_acoustic_output(name):
            continue
        for kind, suffix, _, _ in by_length:
            if lowered.endswith(suffix) and kind not in claimed:
                claimed[kind] = str(name)
                break
    return claimed


def _is_acoustic_output(name: str) -> bool:
    """Whether an output is an acoustic file (0.32.0), asked of its one home."""
    from pyflightstream.cases.acoustics import is_acoustic_output

    return is_acoustic_output(name)


def _release_of(package_version: str | None) -> tuple[int, int] | None:
    """Return the (major, minor) release a package version string states, or None."""
    if package_version is None:
        return None
    stated = re.match(r"(\d+)\.(\d+)", package_version.strip())
    return (int(stated.group(1)), int(stated.group(2))) if stated else None


#: THE FORCE-PLOT PARAMETERS BY THE SHORT NAME THE REFERENCE PLOT FILES USE, paired
#: with the PARAMETER the command takes and the UNITS it is sampled in
#: (PFS-2029.07.03). The plot's NAME is ``{short}_{group}``, which is how
#: the reference ``CL_MRP_TOTAL`` and ``FX_MRP_TOTAL`` were spelled, and the column
#: the reference PLOTS product carries.
FORCE_PLOT_PARAMETERS: dict[str, tuple[str, str]] = {
    "CL": ("CL", "COEFFICIENTS"),
    "CDI": ("CDI", "COEFFICIENTS"),
    "CDO": ("CDO", "COEFFICIENTS"),
    # The pressure and viscous drag split the 26.125 manual names (FR-423, SRC-753
    # p.359); 26.125 also ran CDI and CDO (RPT-160), and no earlier build has these.
    "CDP": ("CDP", "COEFFICIENTS"),
    "CDV": ("CDV", "COEFFICIENTS"),
    "CD": ("CD", "COEFFICIENTS"),
    "FX": ("FORCE_X", "NEWTONS"),
    "FY": ("FORCE_Y", "NEWTONS"),
    "FZ": ("FORCE_Z", "NEWTONS"),
    "MX": ("MOMENT_X", "NEWTONS"),
    "MY": ("MOMENT_Y", "NEWTONS"),
    "MZ": ("MOMENT_Z", "NEWTONS"),
}

#: The parameters a group plots when it names none: every one but the 26.125 drag
#: split, which a group asks for by name (FR-423), so a group naming no
#: parameter writes on every build the ten plots it always wrote.
DEFAULT_FORCE_PLOTS: tuple[str, ...] = tuple(
    name for name in FORCE_PLOT_PARAMETERS if name not in ("CDP", "CDV")
)

#: The six components an axis rotation needs, as `FORCE_PLOT_PARAMETERS` spells them.
AXES_PLOT_COMPONENTS: tuple[str, ...] = ("FX", "FY", "FZ", "MX", "MY", "MZ")
#: The plot group an unsteady run ADDS when its pproc plots those six for no
#: group in the global MRP frame (0.24.0): every boundary, in the MRP frame. The
#: unsteady polar's axis coefficients are built from it; a rotor's own frame is
#: not the geometry's axes. The plots are named `FX_MRP_TOTAL` and so on.
AXES_PLOT_GROUP = "MRP_TOTAL"
#: The prefix of the plot group an unsteady run ADDS for each rotor it turns
#: (0.24.0): that rotor's own families, general and blades, in the global MRP
#: frame, named `ROTOR_<ALIAS>`. The rotor table of an unsteady point is the
#: window average of that history. A prefix and not the bare alias, because a
#: pproc may name a group of its own after the alias over OTHER families, and an
#: expanding frame names its emissions `<alias>` in the rotor's own axes.
ROTOR_PLOT_GROUP_PREFIX = "ROTOR_"

#: Fluid parameters documented across builds (SRC-003 p.347, SRC-751 p.352).
#: The pproc has no build; the workflow checks the run's command-database enum.
FLUID_PLOT_PARAMETERS = (
    "CP_FREE",
    "CP_REF",
    "MACH",
    "VELOCITY",
    "VX",
    "VY",
    "VZ",
    "STATIC_PRESSURE_RATIO",
    "BL_MOMENTUM_THICKNESS",
    "BL_DISPLACEMENT_THICKNESS",
    "BL_TOTAL_THICKNESS",
    "BL_SHAPE_FACTOR",
    "BL_SKIN_FRICTION",
    "BL_TRANSITION_MARKER",
)

#: The family SELECTORS a pproc entry may write instead of a family name.
#: ``all`` is every boundary (the command's own -1 form); ``airframe`` is
#: every family that is not a blade; ``blades`` is every blade; ``each``
#: expands the entry into one per family the geometry carries, and
#: ``each_blade`` into one per blade, the entry's name carrying
#: ``{family}`` for the expansion. They are what let ONE artifact serve
#: the reference wing-body and isolated-rotor configurations: the
#: reference driver kept
#: one table of sections and plots and filtered it to the components the
#: opened file carried, and the selectors are that filter written down.
FAMILY_SELECTORS = ("all", "airframe", "blades", "each", "each_blade")

#: The frames the package creates itself under a FIXED name, which a pproc
#: entry may cite beside the reference's own ``[[frames]]`` and beside a
#: rotor's frames. MRP is the moment frame the reference creates
#: (PFS-2030.03.02), and BLADE_AXIS the per-blade frame of the multirotor
#: work (PFS-2029.11.03); an entry citing a frame the run did not create is
#: refused at build time naming the frames it did.
#:
#: A ROTOR'S FRAMES ARE NOT HERE, because their names are not fixed: they
#: take the rotor's own alias as their radical (``<ALIAS>_SMRP``,
#: ``<ALIAS>_RMRP``, ``<ALIAS>_RMRP<k>``), which is what a reference
#: declaring several rotors requires. The single ``PROP_MRP`` this tuple
#: carried until 0.15.0 was the last of the one-propulsor assumption:
#: one reference, one rotor, one name that could stand for it.
PPROC_FRAMES = ("MRP", "BLADE_AXIS")

Plane = Literal["XY", "XZ", "YZ"]


def _a_named_frame(value: str) -> str:
    """Refuse a pproc entry's frame that names nothing; WHICH frame is judged at build time."""
    if not value.strip():
        raise ValueError(
            f"frame names one the run creates ({', '.join(PPROC_FRAMES)}, LOCAL_AXIS, "
            "or a rotor's own <ALIAS>_SMRP and <ALIAS>_RMRP) or one the REFERENCE's "
            "[[frames]] table declares; it is empty"
        )
    return value


def _the_radius_is_a_rotors(value: object) -> object:
    """Refuse the 0.14.0 spelling of the probe scale, naming the fix (FR-65).

    It warned and rewrote itself until the instruction of
    2026-09-10: this package has no stable release, so an old word is
    refused with its replacement named rather than carried. See
    :mod:`pyflightstream._retired_names`.
    """
    if value == "propeller_radius":
        raise ValueError(PROBE_SCALE_PROPELLER_RADIUS.message())
    return value


def _check_family_selection(value: object) -> str | list[str]:
    """Accept one word, or a list of words; what a word IS is judged at build time.

    A bare word is one of the five selectors, an alias of the row's setup
    or a family name (the reference p001 of 2026-09-09 writes ``families =
    "Lifters"``), and :func:`select_families` reads it against the row's
    inventory and aliases; a word resolving to nothing is an entry the
    builder skips. The shape refused here is an empty word and an empty
    list.
    """
    if isinstance(value, str):
        if not value.strip():
            raise ValueError(
                "families is a selector word, an alias of the setup, a family name, or a "
                "non-empty list of those; it is empty"
            )
        return value
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        if any(item in ("each", "each_blade") for item in value):
            raise ValueError("'each' and 'each_blade' expand an entry and stand alone")
        if any(not item.strip() for item in value):
            raise ValueError("families lists an empty word")
        return list(value)
    raise ValueError(
        "families is a selector word, an alias of the setup, a family name, or a non-empty "
        "list of those"
    )


class SectionDistribution(BaseModel):
    """One surface-section distribution: families, frame and planes.

    Attributes
    ----------
    families : str or list of str
        What the sections cut: a selector word, an alias, a family name, or a
        list of those.
    frame : str
        The frame the planes belong to: ``MRP``, a frame the reference
        declares, or a rotor's.
    planes : list of {'XY', 'XZ', 'YZ'}
        The planes of that frame the sections lie in, one distribution each.
    count : int, optional
        The number of sections of this entry; unstated, the ``[sections]``
        table's.
    plot_direction : {1, 2}, optional
        The plot direction of this entry; unstated, the ``[sections]`` table's.
    integrate : bool
        Appends the midpoint-strip integrals of the sectional loads to this
        distribution's CSV.
    """

    model_config = ConfigDict(extra="forbid")

    families: Annotated[str | list[str], BeforeValidator(_check_family_selection)]
    frame: str = "MRP"
    planes: list[Plane] = Field(min_length=1)
    #: FR-76, the decision of 2026-09-10. `count` and `plot_direction` may be
    #: stated per entry and fall back to the artifact's; `include_symmetry` may
    #: NOT, and the asymmetry is deliberate, with a reason a reader can check: a plot
    #: direction is a property of the CUT, so two distributions can honestly
    #: want different ones, while symmetry is a property of the CASE and one
    #: artifact whose entries disagreed about it would be describing two cases.
    count: int | None = Field(default=None, ge=1)
    plot_direction: Literal[1, 2] | None = None
    #: Since 0.26.0, append midpoint-strip integrals to this distribution's CSV.
    integrate: bool = False

    _frame_is_named = field_validator("frame")(_a_named_frame)

    @model_validator(mode="after")
    def _the_retired_selector_says_it_in_the_frame(self) -> SectionDistribution:
        """Refuse as the plot group does, because it is the same retirement.

        The ledger promise said `each_blade` is read with a warning until
        0.17.0, and the sections path gave none: a
        distribution is the OTHER consumer of the same selector, and the reference
        `p010.toml` writes one (the interface lens, 2026-09-10). A promise
        kept on one of two paths is a false sentence on the page, not a
        partial one.
        """
        if self.families == "each_blade":
            raise ValueError(
                f"section distribution over {self.planes}: {refusal_text(ROW_EACH_BLADE)}"
            )
        return self


class SectionsSpec(BaseModel):
    """The ``[sections]`` table: NEW_SURFACE_SECTION_DISTRIBUTION per entry and plane.

    Attributes
    ----------
    count : int
        The number of sections of every distribution that states none.
    plot_direction : {1, 2}
        The plot direction of every distribution that states none.
    include_symmetry : bool
        The command's INCLUDE_SYMMETRY argument, one value for the whole
        artifact, because symmetry is a property of the case.
    distributions : list of SectionDistribution
        The distributions, one command per entry and plane.
    """

    model_config = ConfigDict(extra="forbid")

    count: int = Field(default=50, ge=1)
    plot_direction: Literal[1, 2] = 1
    include_symmetry: bool = False
    distributions: list[SectionDistribution] = Field(default_factory=list)


#: THE PRISM-LAYER ARGUMENTS EVERY VOLUME SECTION IS CREATED WITH (G05):
#: ``prisms_type``, ``thickness``, ``layers`` and ``growth_rate``, in the order
#: both create commands take them. They are the values the verified create
#: probes sent (``qa/specs.py``, the volume-section specs, verified on 26.120
#: to 26.124); with ``NONE`` the manual reads no prism layer, and what the other
#: three then mean is the manual's (SRC-003 p.366). A pproc cannot state them:
#: a value no run has sent is not one this package offers.
VOLUME_SECTION_PRISMS: tuple[str, float, int, float] = ("NONE", 0.1, 1, 1.2)

#: The keys each volume-section shape states, and so the keys the other refuses.
_VOLUME_SECTION_SHAPE_KEYS: dict[str, tuple[str, ...]] = {
    "rectangle": ("corners_m", "refinement_layers"),
    "circle": ("radii_m", "points"),
}


class VolumeSectionSpec(BaseModel):
    """A sampled flow plane, generated from explicit reference-frame probes.

    New runs export samples and post converts them to VTK or Tecplot. Existing
    native section files retain their recorded meaning. Coordinates are meters
    in the declared frame; a frame with unknown placement is refused.

    Attributes
    ----------
    shape : {'rectangle', 'circle'}
        Rectangular or annular sampling domain.
    frame : str
        Frame containing the plane; MRP by default, or explicit REFERENCE.
    plane : {'XY', 'XZ', 'YZ'}
        In-plane coordinate axes, in the written order.
    offset_m : float
        Distance along the remaining positive frame axis, in meters.
    corners_m : tuple of four floats
        Rectangle lower and upper diagonal coordinates u0, v0, u1, v1.
    refinement_layers : int
        Rectangle subdivisions: each extra layer bisects every grid interval.
    radii_m : tuple of two floats
        Circle inner and outer radii in meters.
    points : tuple of two ints
        Rectangle u/v counts (default 25 by 25); circle radial/azimuth counts.
        Rectangle endpoints are included; a circular center is sampled once.
    format : {'vtk', 'tecplot'}
        Post field format, with explicit point topology and SI provenance.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    shape: Literal["rectangle", "circle"]
    frame: str = "MRP"
    plane: Plane
    offset_m: float = 0.0
    corners_m: tuple[float, float, float, float] | None = None
    refinement_layers: int = Field(default=1, ge=1)
    radii_m: tuple[float, float] | None = None
    points: tuple[Annotated[int, Field(ge=1)], Annotated[int, Field(ge=1)]] | None = None
    format: Literal["vtk", "tecplot"] = "vtk"

    _frame_is_named = field_validator("frame")(_a_named_frame)

    @model_validator(mode="after")
    def _each_shape_states_its_own_keys(self) -> VolumeSectionSpec:
        """Refuse a key of the other shape, and a shape missing its own.

        ``refinement_layers`` has a default, so it is judged by whether the
        table STATED it: a circle table writing it names a rectangle's key.
        """
        if self.points is not None and (
            min(self.points) < 2 or (self.shape == "circle" and self.points[1] < 3)
        ):
            raise ValueError("volume grid needs at least 2 samples per axis and 3 around a circle")
        own = _VOLUME_SECTION_SHAPE_KEYS[self.shape]
        other = next(shape for shape in _VOLUME_SECTION_SHAPE_KEYS if shape != self.shape)
        stray = [
            key
            for key in _VOLUME_SECTION_SHAPE_KEYS[other]
            if key != "points" and key in self.model_fields_set and getattr(self, key) is not None
        ]
        if stray:
            raise ValueError(
                f"[volume_section] shape = {self.shape!r} states {', '.join(stray)}, which "
                f"{'is' if len(stray) == 1 else 'are'} a {other}'s; a {self.shape} takes "
                f"{' and '.join(own)}"
            )
        needed = [key for key in own if key != "refinement_layers" and getattr(self, key) is None]
        if needed:
            raise ValueError(
                f"[volume_section] shape = {self.shape!r} needs {' and '.join(needed)}; "
                + (
                    "a rectangle takes corners_m, the two diagonal corners x1, y1, x2, y2 "
                    "in the plane, in metres"
                    if self.shape == "rectangle"
                    else "a circle takes radii_m, the inner and outer radius r1, r2 in "
                    "metres, and points, the ipts radial and jpts azimuthal segments"
                )
            )
        if self.corners_m is not None:
            x1, y1, x2, y2 = self.corners_m
            if x1 == x2 or y1 == y2:
                raise ValueError(
                    f"[volume_section] corners_m = {list(self.corners_m)} enclose no area: "
                    "two diagonal corners differ in both coordinates"
                )
        if self.radii_m is not None:
            inner, outer = self.radii_m
            if not 0.0 <= inner < outer:
                raise ValueError(
                    f"[volume_section] radii_m = {list(self.radii_m)}: the inner radius r1 "
                    "is at least 0 and smaller than the outer r2"
                )
        return self


#: The FRAME KINDS a post-processing entry may cite instead of a frame's
#: name, and what each says the entry is ONE OF (FR-65, the design of
#: 2026-09-10). They are not frames the script creates: they name the
#: ROLE a frame plays for a rotor, and the expansion resolves each to that
#: rotor's own `<ALIAS>_SMRP`, `<ALIAS>_RMRP` or `<ALIAS>_RMRP<k>`.
#:
#: THERE IS NO `expand` KEY, and that is the whole design: a reader who
#: has said which frame a quantity is measured in has already said how
#: many of it there are. `SMRP` and `RMRP` are per ROTOR, because a rotor
#: has one of each; `LOCAL_AXIS` is per BLADE, because a blade has one.
EXPANDING_FRAMES: dict[str, Literal["rotor", "blade"]] = {
    "SMRP": "rotor",
    "RMRP": "rotor",
    "LOCAL_AXIS": "blade",
}


def global_frame_plot_declarations(pproc: object) -> tuple[ForcePlotGroup, ...]:
    """Read declarations of all six load components in the global MRP frame.

    A ``{family}`` name counts: its emitted groups still measure global loads.
    This reads declarations, not emitted names; post must separately reject
    ambiguous names and cannot infer a template's expansion from its spelling.

    Parameters
    ----------
    pproc : PprocSpec or object
        The pproc artifact, or anything carrying its ``plots``.

    Returns
    -------
    tuple of ForcePlotGroup
        The force-plot groups declared in the MRP frame when the plots name
        all of :data:`AXES_PLOT_COMPONENTS`; empty otherwise.
    """
    plots = getattr(pproc, "plots", None)
    if not set(AXES_PLOT_COMPONENTS) <= set(getattr(plots, "parameters", ()) or ()):
        return ()
    return tuple(
        group
        for group in (getattr(plots, "groups", ()) or ())
        if str(getattr(group, "frame", "")).strip().upper() == "MRP"
    )


class ForcePlotGroup(BaseModel):
    """One group of unsteady force plots: a name, a frame and the families summed.

    THE FRAME DECIDES HOW MANY GROUPS THIS ENTRY IS (FR-65). One citing
    `MRP` or a frame the reference declares is ONE group over the whole
    cited set; one citing `SMRP` or `RMRP` is one per ROTOR, in that
    rotor's own frame; one citing `LOCAL_AXIS` is one per BLADE. The
    `each` selector stays beside them, because one group per family in a
    COMMON frame is a reading no frame implies.

    Attributes
    ----------
    name : str
        The group's name, which names its plots ``<parameter>_<name>``; it
        carries ``{family}`` exactly when the entry expands.
    frame : str
        The frame the loads are measured in, which decides how many groups the
        entry is.
    families : str or list of str
        The families summed: a selector word, an alias, a family name, or a
        list of those.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    frame: str = "MRP"
    families: Annotated[str | list[str], BeforeValidator(_check_family_selection)]

    _frame_is_named = field_validator("frame")(_a_named_frame)

    @property
    def emits_per(self) -> Literal["once", "rotor", "blade", "family"]:
        """What this entry is one of: ``once``, ``rotor``, ``blade`` or ``family``.

        The frame is asked first, because it is the statement that cannot
        be a second home for the same fact: a quantity measured in a
        blade's own axes is one per blade whatever the families say.
        """
        kind = EXPANDING_FRAMES.get(self.frame.strip().upper())
        if kind is not None:
            return kind
        if self.families == "each_blade":
            return "blade"
        if self.families == "each":
            return "family"
        return "once"

    @model_validator(mode="after")
    def _the_placeholder_says_what_the_emission_is_about(self) -> ForcePlotGroup:
        """`{family}` is present exactly when there is more than one emission.

        It means WHAT THE EMISSION IS ABOUT rather than what it is named
        after: the rotor's alias on a per-rotor entry, the blade's label
        on a per-blade one, the family on an `each` one.
        """
        if (self.emits_per != "once") != ("{family}" in self.name):
            expands = (
                f"an entry in {self.frame} is one per {self.emits_per}"
                if self.emits_per != "once"
                else f"an entry in {self.frame} is ONE group over the families it names"
            )
            carries = "carries" if self.emits_per != "once" else "carries no"
            raise ValueError(
                f"plot group {self.name!r}: {expands}, so its name {carries} "
                "{family}, which names what each emission is about. The frames that "
                f"expand are {', '.join(sorted(EXPANDING_FRAMES))}, and the selector "
                "'each' expands in a common frame."
            )
        return self

    @model_validator(mode="after")
    def _the_only_field_is_a_bare_family(self) -> ForcePlotGroup:
        """Refuse a plot name whose replacement fields are anything but a bare `{family}`.

        The builder names an emission with `str.format`, so a format spec or a
        conversion (`{family:.0}`, `{family!r}`, a nested spec) can make a name
        print anything, an automatic group's name among them, and the post stage
        would then read another frame's history as the geometry's (release review
        of 0.24.0). No plot name needs more than the bare placeholder.
        """
        fields = [
            (field, spec, conversion)
            for _literal, field, spec, conversion in string.Formatter().parse(self.name)
            if field is not None
        ]
        if any(stated != ("family", "", None) for stated in fields):
            raise ValueError(
                f"plot group {self.name!r}: a plot name may carry only the bare "
                "placeholder {family}, with no format spec and no conversion"
            )
        # A CLOSED ALPHABET, so a name reads back as it was written: the export
        # reader strips whitespace from column names, and a name with a trailing
        # space emitted a history the post stage matched to another group.
        if re.fullmatch(r"(?:[A-Za-z0-9_]|\{family\})+", self.name) is None:
            raise ValueError(
                f"plot group {self.name!r}: a plot name is letters, digits and "
                "underscores, and the bare placeholder {family}; no space and no "
                "other character"
            )
        return self

    @model_validator(mode="after")
    def _a_frame_that_expands_is_not_also_a_selector_that_expands(self) -> ForcePlotGroup:
        """One statement of how many, not two (FR-65).

        The frame decides, so a selector that ALSO decides is a second
        answer to one question. `each` in a rotor frame validated and was
        then refused at build time by a message about families reaching no
        rotor, which describes a different mistake: the model accepted
        what the builder cannot emit (the architecture lens, 2026-09-10).
        """
        if EXPANDING_FRAMES.get(self.frame.strip().upper()) and self.families in (
            "each",
            "each_blade",
        ):
            raise ValueError(
                f"plot group {self.name!r}: the frame {self.frame} already expands, one "
                f"per {self.emits_per}, and families = {self.families!r} expands too, so "
                "the entry states how many it is twice. Name the rotors or the alias "
                f"whose families they own, or 'all' for every rotor; write "
                f"families = 'each' only in a frame that does not expand."
            )
        return self

    @model_validator(mode="after")
    def _the_retired_selector_says_it_in_the_frame(self) -> ForcePlotGroup:
        """`each_blade` said what `LOCAL_AXIS` says, so it is a second home for one fact."""
        if self.families == "each_blade":
            raise ValueError(f"plot group {self.name!r}: {refusal_text(ROW_EACH_BLADE)}")
        return self


class PlotsSpec(BaseModel):
    """The ``[plots]`` table: which parameters, over which groups of families.

    Attributes
    ----------
    parameters : list of str
        The force and moment parameters plotted for every group; unstated,
        all of them but CDP and CDV, the 26.125 drag split, named to be plotted.
    groups : list of ForcePlotGroup
        The groups of families, one plot per parameter each.
    """

    model_config = ConfigDict(extra="forbid")

    parameters: list[str] = Field(default_factory=lambda: list(DEFAULT_FORCE_PLOTS))
    groups: list[ForcePlotGroup] = Field(default_factory=list)

    @field_validator("parameters")
    @classmethod
    def _known_parameters(cls, value: list[str]) -> list[str]:
        unknown = [name for name in value if name not in FORCE_PLOT_PARAMETERS]
        if unknown:
            raise ValueError(
                f"force plot parameter(s) {', '.join(unknown)} are not among "
                f"{', '.join(FORCE_PLOT_PARAMETERS)}"
            )
        return value


def _a_group_is_one_alias(value: object) -> object:
    """Read one alias per group; since 0.26.0 a member list is refused.

    The internal list is the normalized selection iterated by consumers.
    Declare several members under [aliases] in the reference and name that alias.
    """
    if not isinstance(value, Mapping):
        return value
    groups: dict[str, list[int | str]] = {}
    for name, stated in value.items():
        if isinstance(stated, str):
            groups[str(name)] = [stated]
            continue
        if isinstance(stated, list | tuple):
            if len(stated) == 1 and isinstance(stated[0], str):
                replacement = f'{name} = "{stated[0]}"'
            elif not stated:
                replacement = (
                    f'{name} = "{EVERY_FAMILY}" only if no boundary, family or alias '
                    f'named "{EVERY_FAMILY}" exists in the inventory or reference; '
                    "that name takes precedence and selects its own members. Otherwise "
                    "declare every intended boundary under a unique alias in the "
                    f'reference [aliases] and write {name} = "<alias>"'
                )
            else:
                replacement = (
                    f'{name} = "<alias>"; declare the members under [aliases] '
                    "in the reference, using boundary names for positions"
                )
            raise InputArtifactError(
                f"pproc [groups] entry {name!r}: member lists were removed in 0.26.0. "
                f"Write {replacement} instead.",
                kind="pproc",
            )
        return value
    return groups


def _probes_are_a_list(value: object) -> object:
    """Refuse the 0.15.0 `[probes]` table, naming the edit (FR-77).

    A table and an array of tables are one bracket apart in TOML and the
    difference is invisible until something reads it, so the refusal spells out
    what to type. Whoever meets this is holding a workspace that planned
    yesterday, and a message saying only "expected a list" would leave them
    guessing which bracket.
    """
    if isinstance(value, Mapping):
        raise ValueError(
            "`[probes]` is a LIST of tables since 0.16.0, so that one artifact can "
            "probe several frames on one row, as `[[plots.groups]]` and "
            "`[[sections.distributions]]` already do. Write `[[probes]]` instead of "
            "`[probes]`, once per frame you are sampling in; everything inside the "
            "table is unchanged, `frame`, `scale`, `parameters`, `points` and the "
            "`[[probes.lines]]` beneath it."
        )
    return value


class ProbeLine(BaseModel):
    """One line of fluid probes, from one vertex to another, sampled at ``points``.

    Attributes
    ----------
    start : tuple of three floats
        The first vertex, in the entry's frame and scale.
    end : tuple of three floats
        The last vertex, in the entry's frame and scale.
    """

    model_config = ConfigDict(extra="forbid")

    start: tuple[float, float, float]
    end: tuple[float, float, float]


class ProbeRectangle(BaseModel):
    """A rectangular probe plane, given by three of its vertices (FR-79).

    THREE CORNERS AND NOT FOUR. The fourth is determined by the other three,
    and a declaration carrying it lets a reader write one that does not lie in
    their plane, which is a figure nobody can draw and the package would have
    to silently correct or silently accept.

    The grid runs from `origin` toward `along_u` in `points_u` stations and
    toward `along_v` in `points_v`, both ends included, so a 3 by 4 rectangle
    is twelve points and its corners are three of the declared vertices.

    Attributes
    ----------
    origin : tuple of three floats
        The corner the grid starts from.
    along_u : tuple of three floats
        The corner the grid runs toward in its first direction.
    along_v : tuple of three floats
        The corner the grid runs toward in its second direction.
    points_u : int
        The stations from ``origin`` to ``along_u``, both ends included.
    points_v : int
        The stations from ``origin`` to ``along_v``, both ends included.
    """

    model_config = ConfigDict(extra="forbid")

    origin: tuple[float, float, float]
    along_u: tuple[float, float, float]
    along_v: tuple[float, float, float]
    points_u: int = Field(ge=2)
    points_v: int = Field(ge=2)

    @model_validator(mode="after")
    def _the_three_corners_span_a_plane(self) -> ProbeRectangle:
        """Refuse a rectangle whose corners are collinear or coincident."""
        first = [b - a for a, b in zip(self.origin, self.along_u, strict=True)]
        second = [b - a for a, b in zip(self.origin, self.along_v, strict=True)]
        cross = (
            first[1] * second[2] - first[2] * second[1],
            first[2] * second[0] - first[0] * second[2],
            first[0] * second[1] - first[1] * second[0],
        )
        if sum(value * value for value in cross) <= 0.0:
            raise ValueError(
                f"a probe rectangle at {self.origin} spans no plane: its three "
                "corners are collinear or two of them coincide, so there is no "
                "rectangle to grid. `origin`, `along_u` and `along_v` are three "
                "DIFFERENT corners and the fourth follows from them."
            )
        return self


class ProbeCircle(BaseModel):
    """A circular probe plane, discretised in polar coordinates (FR-79).

    `points_radial` stations from the centre to the rim INCLUDING both, and
    `points_azimuth` around, so the centre appears once rather than once per
    azimuth: a survey that sampled its own centre eight times would weight it
    eight times in anything that averages the file.

    Attributes
    ----------
    center : tuple of three floats
        The centre of the disk.
    normal : tuple of three floats
        The axis the disk is perpendicular to.
    radius : float
        The disk's radius, in the entry's scale.
    points_radial : int
        The stations from the centre to the rim, both included.
    points_azimuth : int
        The stations around.
    """

    model_config = ConfigDict(extra="forbid")

    center: tuple[float, float, float]
    normal: tuple[float, float, float]
    radius: float = Field(gt=0.0)
    points_radial: int = Field(ge=2)
    points_azimuth: int = Field(ge=3)

    @model_validator(mode="after")
    def _the_normal_is_a_direction(self) -> ProbeCircle:
        """Refuse a zero normal, which names no plane."""
        if sum(value * value for value in self.normal) <= 0.0:
            raise ValueError(
                f"a probe circle at {self.center} states `normal = {self.normal}`, "
                "which is no direction and so names no plane. The normal is the "
                "axis the disk is perpendicular to."
            )
        return self


class ProbesSpec(BaseModel):
    """One ``[[probes]]`` entry: fluid plots along lines, in a frame, per parameter.

    Each line is sampled at ``points`` vertices from ``start`` to ``end``,
    and every vertex gets one UNSTEADY_SOLVER_NEW_FLUID_PLOT per parameter,
    named ``{parameter}{n}`` with n counting vertices across the lines in
    the order written. ``scale`` says what the coordinates are in: metres,
    or ROTOR radii, which is how the nine lines were laid out over the
    disk of whichever rotor the reference named. The word was
    ``propeller_radius`` until 0.15.0 and is REFUSED, naming
    ``rotor_radius``: this release says ROTOR everywhere, because a lifter is not a
    PROPELLER and an aircraft may carry eight of them. The word sweep of
    2026-09-10 rewrote `propeller` here into `rotor` and left the sentence
    arguing against the change it explains (the technical writing lens of
    the 0.15.0 release review).

    Attributes
    ----------
    frame : str
        The frame the lines and planes are laid out in; empty, the rotor's own
        hub frame.
    parameters : list of str
        The fluid parameters sampled at every point.
    points : int
        The vertices each line is sampled at, both ends included.
    scale : {'m', 'rotor_radius'}
        What the coordinates are in: metres, or radii of the row's rotor.
    lines : list of ProbeLine
        Lines of probes, each from one vertex to another.
    rectangles : list of ProbeRectangle
        Rectangular probe planes, each gridded point by point.
    circles : list of ProbeCircle
        Circular probe planes, each gridded in polar coordinates.
    points_file : str, optional
        The name of a points file of ``inputs/profiles/``, cited instead of
        drawing lines and planes.
    kind : {'unsteady', 'normal'}
        How an unsteady row samples the entry: ``unsteady``, one
        fluid plot per point and parameter evaluated at every time step, or
        ``normal``, probe points created after the time march and exported
        once, at the last time step. A steady row accepts either and samples
        probe points.
    """

    model_config = ConfigDict(extra="forbid")

    #: THE FRAME THE LINES ARE LAID OUT IN. Empty means the rotor's own
    #: hub frame, which is what this defaulted to when there was one
    #: package-level rotor frame to name; the builder resolves it, because
    #: the name depends on the row's own rotor. It defaulted to the literal
    #: `ROTOR_MRP` until 0.15.0 removed that frame, which refused every
    #: artifact that had taken the default and told it to edit the
    #: reference (the interface lens of the 0.15.0 release review).
    frame: str = ""
    parameters: list[str] = Field(default_factory=list)
    #: Optional sampled velocity products; each retains source units and topology.
    field_formats: list[Literal["vtk", "tecplot"]] = Field(default_factory=list)
    #: Write a six-column global YZ-plane profile suitable for custom inflow.
    reusable_inflow: bool = False
    points: int = Field(default=25, ge=2)
    scale: Annotated[Literal["m", "rotor_radius"], BeforeValidator(_the_radius_is_a_rotors)] = "m"
    lines: list[ProbeLine] = Field(default_factory=list)
    #: FR-79: a plane is a third and fourth kind of entry beside the line, and
    #: all three emit POINT BY POINT so that one declaration produces one export
    #: whatever the run type.
    rectangles: list[ProbeRectangle] = Field(default_factory=list)
    circles: list[ProbeCircle] = Field(default_factory=list)
    #: FR-80: the name of a points file the USER wrote, under
    #: `inputs/profiles/`, cited instead of `lines`. The entry still
    #: states its `frame` and its `scale`, because a file of numbers says
    #: nothing about where those numbers are measured, and its `parameters`,
    #: because the file says where to sample and not what to sample.
    points_file: str | None = None
    #: THE PACKAGE SETS THIS, A FILE NEVER DOES: the absolute path of
    #: `points_file` under the workspace's `inputs/profiles/`, filled when a
    #: row binds, the way a GEOMETRY stem becomes an absolute path on the case.
    #: On an unsteady row, PLAN reads this file and turns its points into
    #: fluid-plot vertices. On a steady row, the script imports the survey by
    #: this absolute path, since a relative path resolves against the solver's
    #: working directory rather than the submitted point's simulation folder.
    #: Excluded from every dump, so no machine path reaches a record or a plan.
    resolved_points_file: str | None = Field(default=None, exclude=True)
    #: FR-417: how an unsteady row samples this entry. ``unsteady`` (the
    #: default, the 0.36.0 behaviour) is one fluid plot per point and
    #: parameter, a history at every time step; ``normal`` is probe points
    #: created after the time march with the steady commands, updated and
    #: exported once, so they hold the last time step. A steady row samples
    #: probe points whatever the entry states.
    kind: ProbeKind = "unsteady"

    @field_validator("kind", mode="before")
    @classmethod
    def _a_known_probe_kind(cls, value: object) -> object:
        """Refuse a probe kind other than the two, naming both (FR-417 R5)."""
        if value not in PROBE_KINDS:
            raise ValueError(
                f"probe kind {value!r} is not one of {' or '.join(map(repr, PROBE_KINDS))}: "
                'write kind = "unsteady" for a fluid plot per point and parameter, '
                'evaluated at every time step, or kind = "normal" for probe points '
                "sampled once, at the last time step"
            )
        return value

    @model_validator(mode="after")
    def _points_come_from_one_place(self) -> ProbesSpec:
        """Either the entry draws its own lines, or it cites a file, not both.

        An entry carrying both states the survey twice, and nothing keeps the
        two in agreement. Which one would win is the kind of question a reader
        should never have to ask of a file they wrote.
        """
        if len(set(self.field_formats)) != len(self.field_formats):
            raise ValueError("field_formats must not repeat a format")
        if self.field_formats or self.reusable_inflow:
            self.parameters = list(dict.fromkeys([*self.parameters, "VX", "VY", "VZ"]))
        drawn = len(self.lines) + len(self.rectangles) + len(self.circles)
        if self.points_file and drawn:
            raise ValueError(
                f"a probe entry in {self.frame or 'the rotor hub frame'} states both "
                f"`points_file = {self.points_file!r}` and {drawn} shape(s) of its "
                "own, which is the survey written twice with nothing keeping the two "
                "in agreement. State the shapes, or cite the file and delete them."
            )
        if self.points_file and "/" in self.points_file.replace("\\", "/"):
            raise ValueError(
                f"`points_file = {self.points_file!r}` names a path. It is the NAME of "
                "a file under the workspace's `inputs/profiles/`, which is "
                "where a profile lives so that a run never writes over it; a path "
                "would let one artifact reach outside the workspace it belongs to."
            )
        if self.resolved_points_file is not None:
            raise ValueError(
                "`resolved_points_file` is set by the package when a row binds and is "
                "never written in a pproc file; cite the survey with `points_file`."
            )
        return self

    _frame_is_named = field_validator("frame")(_a_named_frame)

    @field_validator("parameters")
    @classmethod
    def _known_parameters(cls, value: list[str]) -> list[str]:
        unknown = [name for name in value if name not in FLUID_PLOT_PARAMETERS]
        if unknown:
            raise ValueError(
                f"fluid plot parameter(s) {', '.join(unknown)} are not among "
                f"{', '.join(FLUID_PLOT_PARAMETERS)}"
            )
        return value


#: The formats a super file can be written in (v0.23.0 item 7), including
#: the custom polar format.
#:
#: IT LIVES HERE AND NOT WITH THE WRITER since the layer guard refused the
#: alternative by name: `ProductsSpec` validates against this list, `cases`
#: may not import `post`, and deferring the import into the validator body
#: does not change its direction. A name two layers need belongs below both.
#: `post.superfile` imports it, so every reader who found it there still
#: does.
#:
#: `csv` is the default because adding a format may not change what an existing
#: workspace writes. THE COLUMN SET IS THE SAME IN BOTH, which is the property
#: that makes this a format rather than a second product: the super file's
#: whole claim is that it carries everything the workspace knows about that
#: simulation, and a format quietly carrying a different SET would break the
#: claim while looking like a formatting option.
#: `legacy_polar` LEFT THIS TUPLE FOR 0.23.0 AND IS BACK IN 0.24.0. That release
#: moved the item out, so a pproc naming the format was refused by name rather
#: than accepted and ignored; the writer stayed, and this release resumes from it.
SUPERFILE_FORMATS: tuple[str, ...] = ("csv", "legacy_polar")

#: The families ``[products] installed_frame`` may name (FR-420): the probes table
#: and the reusable inflow profile. ONE HOME, read by the validator below and by
#: the post stage, so a family cannot be accepted by one and ignored by the other.
INSTALLED_FRAME_FAMILIES: tuple[str, ...] = ("probes", "inflow")


class ProductsSpec(BaseModel):
    """The ``[products]`` table: which post-processed CSV tables the campaign writes.

    ``polars``: one table per group of ``[groups]``, the coefficients of the
    group per point; ``sections``: one table per point from its sectional
    loads export; ``plots``: one table per unsteady point from its plots
    export. All CSV, one header line and one row per record.

    ``custom_polar_format``: beside every polar table, the same rows in the
    fixed-width text format the existing tooling opens
    (PFS-2014.01.01), ``<polar>_M<mach code>_g<group>.dat``. Off by
    default, since it is a second serialization of the polar table for
    one reader.

    Attributes
    ----------
    polars : bool
        Writes one polar table per group of ``[groups]``, the group's
        coefficients per point.
    sections : bool
        Writes one sections table per point, from its sectional loads export.
    plots : bool
        Writes one plots table per unsteady point, from its plots export.
    custom_polar_format : bool
        Writes, beside every polar table, the same rows in the fixed-width
        custom polar format.
    superfile_format : str
        The format the super file is written in.
    settings_codebook : bool
        Writes, per matrix, the all-numeric settings table of every recorded
        point and its codebook under ``settings/`` (FR-419). On by default.
    installed_frame : list of str
        The families of table copied mirrored through y = 0 beside their
        source, from ``{"probes", "inflow"}`` (FR-420). Empty by default.
    """

    model_config = ConfigDict(extra="forbid")

    polars: bool = True
    sections: bool = True
    plots: bool = True
    custom_polar_format: bool = False
    #: Raw VTK boundary-layer integral quantities and markers at recorded section cuts.
    #: Retains original cell association; this does not request a velocity profile.
    boundary_layer_integrals: bool = False
    #: A separate wall-normal velocity profile request. Unavailable until a build
    #: proves unattended EXPORT_BL_VELOCITY_PROFILE execution (RPT-027/RPT-075).
    boundary_layer_velocity_profile: bool = False
    #: FR-419: the numeric settings table of the campaign and its legend. ON by
    #: default (the owner's decision of 2026-10-05); ``false`` turns it off and
    #: writes what 0.36.0 wrote.
    settings_codebook: bool = True
    #: FR-420: the families whose tables are also written mirrored through y = 0.
    #: The accepted names are :data:`INSTALLED_FRAME_FAMILIES`, refused where the
    #: pproc is read.
    installed_frame: list[str] = Field(default_factory=list)

    @field_validator("installed_frame")
    @classmethod
    def _a_family_the_post_mirrors(cls, value: list[str]) -> list[str]:
        """Refuse a family the post does not mirror, naming the accepted ones."""
        unknown = [name for name in value if name not in INSTALLED_FRAME_FAMILIES]
        if unknown:
            raise ValueError(
                f"installed_frame names {', '.join(map(repr, unknown))}, which the post does "
                f"not mirror; the accepted families are {', '.join(INSTALLED_FRAME_FAMILIES)}"
            )
        return value

    @field_validator("boundary_layer_velocity_profile")
    @classmethod
    def _profile_requires_an_unattended_native_route(cls, value: bool) -> bool:
        if value:
            raise ValueError(
                "boundary_layer_velocity_profile is unavailable: EXPORT_BL_VELOCITY_PROFILE "
                "is interactive on 26.122 (RPT-027) and stalls on 26.124 (RPT-075); "
                "no supported build has a proved unattended route. Integrals are a "
                "separate request and never substitute for the velocity profile."
            )
        return value

    #: Item 7. Which FORMAT the super file is written in: `csv` as before, or
    #: `legacy_polar`, the fixed-width form the existing tooling opens. The
    #: writer took this argument from the first commit of 0.23.0 and the ONE
    #: production call omitted it, so every campaign got `csv` and the second
    #: format was a constant nobody could select.
    #:
    #: A FIELD AND NOT A FLAG, because `custom_polar_format` beside it is
    #: already a `[products]` key: a user choosing how their products are written
    #: should find both choices in one table rather than one here and one on a
    #: command line.
    #:
    #: The DEFAULT MAY NOT MOVE. It is the existing file format, so adding
    #: this changes nothing about an existing workspace.
    superfile_format: str = "csv"

    @field_validator("superfile_format")
    @classmethod
    def _a_format_the_package_offers(cls, value: str) -> str:
        """Refuse an unknown format where the pproc is READ.

        The writer already refuses one, naming the formats that exist -- and it
        fires after a campaign has been planned and a seat possibly spent. A
        typo in a TOML file is a typo the loader can see, so it is seen here.

        The list is the one the writer uses, which is why it lives in this
        module rather than with the writer: a third format cannot be offered
        by one and refused by the other.
        """
        if value not in SUPERFILE_FORMATS:
            raise ValueError(
                f"the super file format {value!r} is not one this package writes; "
                f"the formats that exist are {', '.join(SUPERFILE_FORMATS)}"
            )
        return value


#: The drift limit of a pproc that declares no ``[per_revolution]`` table, in
#: per cent. ONE HOME (0.31.0 release review): the pproc model's default below
#: and the post's fallback (``pyflightstream.post.products``, which imports it
#: from here) read this one constant, so the two cannot disagree.
DEFAULT_DRIFT_LIMIT_PCT = 1.0


class PerRevolutionSpec(BaseModel):
    """The ``[per_revolution]`` table: how far one revolution may differ from the last.

    ``drift_limit_pct`` is the per-revolution product's declared threshold, in
    per cent. The product ``probes/<point>_per_revolution_<ALIAS>.csv`` states the
    drift of every plotted column's mean from the previous revolution. When the
    LAST revolution's change of a force or moment column exceeds this limit in per
    cent of its scale (the largest previous mean of its kind in its group: thrust
    for an in-plane force, torque for an in-plane moment), ``post.log`` gets a
    WARNING line; it never blocks a product (FR-180).

    Absent, the limit is 1.0 per cent (:data:`DEFAULT_DRIFT_LIMIT_PCT`). The
    table is optional and read again by ``pyfs-matrix post``, so declaring or
    editing it needs no new run.

    Examples
    --------
    >>> PerRevolutionSpec().drift_limit_pct
    1.0
    >>> PerRevolutionSpec(drift_limit_pct=0.25).drift_limit_pct
    0.25
    """

    model_config = ConfigDict(extra="forbid")

    #: The change, in per cent of a force or moment column's scale, above which
    #: its last revolution is warned about. Positive.
    drift_limit_pct: float = Field(default=DEFAULT_DRIFT_LIMIT_PCT, gt=0.0)


class PhaseLockedSpec(BaseModel):
    """The ``[phase_locked]`` table: when the reduction exists, and over how much.

    ``min_revolutions`` is the minimum TOTAL revolutions the matrix row must
    turn for the reduction to be generated, and the comparison is AT LEAST:
    equal generates it. What is compared is what the row states, the whole run
    of THAT rotor, and never the length of the exported window.

    ``last_revolutions_avg`` is how many of the last revolutions enter the mean
    at each azimuth. It may not exceed ``min_revolutions``: a reduction may not
    average over more history than it required in order to exist.

    NOT REACHING THE MINIMUM NEVER REFUSES ANOTHER PRODUCT. This is a gate on
    one reduction: a short run loses the phase-locked table, named as a skip in
    ``products.json`` with the two numbers, and keeps its polar, its per-blade
    table and everything else.

    Examples
    --------
    >>> gate = PhaseLockedSpec(min_revolutions=4.0, last_revolutions_avg=2.0)
    >>> gate.generated_for(revolutions=4.0), gate.generated_for(revolutions=3.9)
    (True, False)
    """

    model_config = ConfigDict(extra="forbid")

    #: Total revolutions the matrix must specify before this is generated.
    min_revolutions: float = Field(gt=0.0)
    #: How many of the LAST revolutions the average uses.
    last_revolutions_avg: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _averages_no_more_than_it_required(self) -> PhaseLockedSpec:
        if self.last_revolutions_avg > self.min_revolutions:
            raise ValueError(
                f"phase_locked averages over {self.last_revolutions_avg} revolutions but "
                f"is only generated from {self.min_revolutions}, so it would average over "
                "more history than it required to exist. Raise min_revolutions, or "
                "average over fewer"
            )
        return self

    def generated_for(self, *, revolutions: float) -> bool:
        """Whether a run of ``revolutions`` turns gets a phase-locked reduction.

        AT LEAST, not more than: equality meets the minimum, and the
        boundary is the whole content of the rule, so it is one comparison with
        its own name rather than an inline `>=` at each call site.
        """
        return float(revolutions) >= self.min_revolutions


class EquationSpec(BaseModel):
    """One entry of ``[equations]``: a coefficient the post stage derives.

    AN EQUATION POINTS AT AN ALIAS AND NEVER AT A MESH FAMILY. The alias is
    what gives the derived coefficient a name that says which body it is
    about, so every derived column is ``<NAME>_<alias>``; a family list would
    give it nothing to be called, and ``families`` is refused as an unknown key.

    ``frame`` rides beside it because an axis matters: the same expression over
    the plots of two frames is two different coefficients. It is optional, and
    it steers which plotted column a symbol finds (see
    :func:`pyflightstream.post.equations.resolve_symbol`).

    The expression is arithmetic over the columns the unsteady polar's row
    already holds: numbers, names, ``+ - * / **``, unary minus, parentheses and
    the functions ``abs, sqrt, sin, cos, tan, radians, degrees, min, max``. It
    is checked when the pproc is read, so a construct outside that set is
    refused at load and never at the end of a campaign.

    Attributes
    ----------
    expression : str
        The arithmetic, over the columns the unsteady polar's row holds.
    meshes_alias : str
        The alias the coefficient is about, and the suffix of its column
        ``<NAME>_<alias>``; never a family list.
    frame : str, optional
        The frame whose plotted columns a symbol finds first.

    Examples
    --------
    >>> spec = EquationSpec(expression="FX / (0.5 * RHO * VINF**2 * SREF)", meshes_alias="PUSHER")
    >>> spec.symbols()
    ['FX', 'RHO', 'VINF', 'SREF']
    """

    model_config = ConfigDict(extra="forbid")

    #: The arithmetic, in the variables the glossary names.
    expression: str
    #: WHICH BODY. An alias, never a family list.
    meshes_alias: str
    #: WHICH AXES. Optional, because an expression of scalars needs none.
    frame: str | None = None

    @field_validator("expression", "meshes_alias")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        token = value.strip()
        if not token:
            raise ValueError(
                "an equation needs both an expression and the alias it is about; the "
                "alias is what every derived coefficient carries as its `_<alias>` suffix"
            )
        return token

    @field_validator("expression")
    @classmethod
    def _an_expression_this_package_evaluates(cls, value: str) -> str:
        """Refuse at LOAD what the evaluator would refuse at post."""
        try:
            expression_symbols(value)
        except InputArtifactError as refused:
            raise ValueError(str(refused)) from refused
        return value

    def symbols(self) -> list[str]:
        """Return the names the expression reads, in order, functions left out."""
        return expression_symbols(self.expression)


class SurfaceTimeAveragingSpec(BaseModel):
    """The last iterations or revolutions used for solver surface averaging.

    Attributes
    ----------
    last_revs : float, optional
        Averages the surface exports over the last revolutions of the rotor
        clock.
    last_iters : int, optional
        Averages the surface exports over the last time iterations; a table
        states exactly one of the two.
    """

    model_config = ConfigDict(extra="forbid")

    last_revs: float | None = Field(default=None, gt=0, strict=True, allow_inf_nan=False)
    last_iters: int | None = Field(default=None, gt=0, strict=True)

    @model_validator(mode="after")
    def _one_window(self) -> SurfaceTimeAveragingSpec:
        if (self.last_revs is None) == (self.last_iters is None):
            raise ValueError("[time_averaging] requires exactly one of last_revs or last_iters")
        return self


class SurfaceProbeSpec(BaseModel):
    """One surface property recorded at a named-frame point during an unsteady march."""

    model_config = ConfigDict(extra="forbid")

    #: Stable user identity; the native plot is named SURFACE_<name>.
    name: str
    #: Exact native surface property, including Cp and boundary-layer integrals.
    parameter: str
    #: Named coordinate system containing the point, resolved before initialization.
    frame: str = "REFERENCE"
    #: Local physical coordinates in metres, converted to the command's length unit.
    point_m: tuple[float, float, float]

    @field_validator("name")
    @classmethod
    def _identifier(cls, value: str) -> str:
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value) is None:
            raise ValueError(
                "surface probe name must start with a letter and use letters, digits or _"
            )
        return value

    @field_validator("parameter")
    @classmethod
    def _parameter(cls, value: str) -> str:
        entry = CommandRegistry.load().commands["NEW_UNSTEADY_SOLVER_SURFACE_PROBE"]
        allowed = next(arg.values for arg in entry.args if arg.name == "parameter") or ()
        if value not in allowed:
            raise ValueError(
                f"surface probe parameter {value!r} must be one of {', '.join(allowed)}"
            )
        return value

    @field_validator("point_m")
    @classmethod
    def _finite_point(cls, value: tuple[float, float, float]) -> tuple[float, float, float]:
        if not all(math.isfinite(component) for component in value):
            raise ValueError("surface probe point_m must contain three finite coordinates")
        return value

    _frame_is_named = field_validator("frame")(_a_named_frame)


class PprocSpec(BaseModel):
    """The post-processing specification a matrix row's PPROC cell names.

    PFS-2029.07.01, the design decision of 2026-09-02: the groups artifact IS the
    home of post-processing and is renamed pproc. Twelve tables. ``groups``
    is exactly what the groups file held, a number to the families it
    aggregates, and the polar tables are written per group of it; a
    member is resolved by :func:`select_group_members`, and an empty
    group is every family (the design decision of 2026-09-09); ``exports`` says which of
    the export kinds a point writes, with VTK and CSV opt-in and the
    existing kinds enabled unless set to false (since 0.27.0 the per-panel
    ``force_distributions`` is opt-in too, and a steady point
    also saves the solver's residual and load plots, and its section Cp plot
    where ``sections`` declares any: ``plot_residuals``, ``plot_loads`` and
    ``plot_sections_cp``); ``sections``, ``plots`` and
    ``probes`` are the solver definitions the builders emit before the solver runs; ``products``
    says which post-processed files are written after it. Since 0.24.0
    ``phase_locked`` gates and shapes the phase-locked reduction, ``equations``
    adds derived columns to the unsteady polar, ``glossary`` says what the
    user's own symbols mean, and ``names`` renames the unsteady polar's plot
    columns for a downstream tool. The four ship together, because the model
    forbids unknown keys and an artifact written for one of them is refused by
    an install that lacks it. ``time_averaging`` asks for time-averaged
    surfaces, and since 0.27.0 ``volume_section`` declares the one flow-field
    plane a steady point cuts and exports (G05).

    Attributes
    ----------
    groups : dict of str to str
        The groups the polar tables are written per, each naming ONE alias of
        the reference.
    phase_locked : PhaseLockedSpec, optional
        When the phase-locked reduction is generated, and over how many
        revolutions; absent, it is the series of blade passages.
    per_revolution : PerRevolutionSpec, optional
        The drift limit, in per cent, of the per-revolution product; absent, 1.
    qsteady_correction : QsteadyCorrectionSpec, optional
        The correction route and the diagnostic of a quasi-steady wheel's post;
        absent, none. Every route is off by default and not validated.
    equations : dict of str to EquationSpec
        Coefficients the post stage derives into the unsteady polar, keyed by
        the derived coefficient's name.
    glossary : dict of str to str
        What each of the user's own symbols means, listed in ``VARIABLES.md``
        beside the package's definitions.
    names : dict of str to str
        Renames a plot column of the unsteady polar and of the reductions, from
        the name the export prints to the one a reader's tool expects.
    exports : dict of str to bool
        Which of the export kinds a point writes.
    time_averaging : SurfaceTimeAveragingSpec, optional
        Asks the solver for surface exports averaged over the last iterations
        or revolutions of the run.
    vtk_variables : list of str, optional
        The variables the VTK surface export writes.
    singularity_strength : bool
        Whether the Tecplot surface carries the nodal ``Singularity_strength``
        from a native Tecplot export beside the VTK; False, the default, exports
        no native Tecplot and the surface declares the strength not carried.
    sections : SectionsSpec
        The surface-section distributions the script declares before the
        solve.
    volume_section : VolumeSectionSpec, optional
        The one flow-field plane each point of a steady row cuts after its
        solve and exports.
    plots : PlotsSpec
        The unsteady force plots: which parameters, over which groups of
        families.
    probes : list of ProbesSpec
        The fluid probe entries, one per frame sampled.
    products : ProductsSpec
        Which post-processed tables the campaign writes.
    blade_pattern : str
        How a blade family is told from the airframe: a regular expression
        over the family name.
    base_regions : list of str
        The boundaries that become base regions, detected after ``OPEN``; a
        row's ``BASE_REGIONS`` wins over it.
    """

    model_config = ConfigDict(extra="forbid")

    #: ONE ALIAS PER GROUP, written as a string since 0.24.0; held as a list of
    #: members because that is what every reader of it iterates. The list form
    #: is refused since 0.26.0; write one alias as a string.
    groups: Annotated[dict[str, list[int | str]], BeforeValidator(_a_group_is_one_alias)] = Field(
        default_factory=dict
    )
    #: ``[phase_locked]``, OPTIONAL. Absent, the phase-locked reduction is the
    #: passage series it has always been and nothing gates it. Declared, it is
    #: generated when the matrix row turns AT LEAST ``min_revolutions``, as the
    #: mean at each azimuth over the last ``last_revolutions_avg`` revolutions;
    #: a shorter run loses this reduction and nothing else.
    phase_locked: PhaseLockedSpec | None = None
    #: ``[per_revolution]``, OPTIONAL (0.31.0): the drift limit, in per cent, above
    #: which the last revolution of a force or moment column is warned about in
    #: ``post.log``. The product itself is written for every unsteady rotor point
    #: whatever this table says; absent, the limit is 1 per cent.
    per_revolution: PerRevolutionSpec | None = None
    #: ``[qsteady_correction]``, OPTIONAL (0.31.0): the correction route a
    #: quasi-steady wheel's post applies, beside the raw products and never over
    #: them, and the diagnostic it writes; absent, no route and no diagnostic.
    #: No route is validated (:mod:`pyflightstream.cases.corrections`).
    qsteady_correction: QsteadyCorrectionSpec | None = None
    #: ``[equations]``, keyed by the derived coefficient's own name; the value
    #: says what it is and which alias it is about. The post stage evaluates
    #: them, in :meth:`equation_order`, into the unsteady polar.
    equations: dict[str, EquationSpec] = Field(default_factory=dict)
    #: ``[glossary]``: what each symbol means, extensible by the user. The
    #: generated ``VARIABLES.md`` lists it beside the package's own.
    glossary: dict[str, str] = Field(default_factory=dict)
    #: ``[names]``: the dictionary from a plot column as the export prints it to
    #: the name a reader's tool expects (0.24.0). It renames columns of the
    #: unsteady polar and of the reductions and nothing else; absent, every name
    #: passes through as printed.
    names: dict[str, str] = Field(default_factory=dict)
    exports: dict[str, bool] = Field(default_factory=dict)
    time_averaging: SurfaceTimeAveragingSpec | None = None
    vtk_variables: list[str] | None = None

    @field_validator("vtk_variables")
    @classmethod
    def _known_vtk_variables(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        entry = CommandRegistry.load().commands["SET_VTK_EXPORT_VARIABLES"]
        allowed = next(arg.values for arg in entry.args if arg.name == "variables") or ()
        unknown = sorted(set(value) - set(allowed))
        if unknown:
            raise ValueError(f"vtk_variables: unknown variable(s) {', '.join(unknown)}")
        if not value or len(set(value)) != len(value):
            raise ValueError(
                "vtk_variables must be a nonempty list of distinct command variable names"
            )
        return value

    #: 0.30.0 (SS1): whether a point's Tecplot surface carries the nodal
    #: ``Singularity_strength``. The VTK does not hold it, so carrying it costs
    #: a second, native Tecplot export per point and per exported step
    #: (``<name>_native_tecplot.dat``). OFF by default: the script exports the
    #: VTK alone, and the ``.dat`` carries every VTK variable and declares
    #: ``Singularity_strength`` not carried. True exports the native file and
    #: carries it, exactly as 0.29.0 did. A bool, and nothing a bool is read
    #: from: ``"true"`` or ``1`` is refused.
    singularity_strength: bool = Field(default=False, strict=True)

    sections: SectionsSpec = Field(default_factory=SectionsSpec)
    #: G05 (0.27.0): ONE flow-field plane each point of a STEADY row cuts after
    #: its solve and exports to ``{name}_vsec.vtk`` or ``{name}_vsec.dat``.
    #: Absent, the default, nothing is cut, declared or exported. An unsteady
    #: row naming an artifact that declares it is refused by its builder.
    volume_section: VolumeSectionSpec | None = None
    plots: PlotsSpec = Field(default_factory=PlotsSpec)
    #: FR-77: a LIST, so one artifact probes several frames on one row. It was
    #: a single table until 0.16.0 and a `[probes]` written that way is refused
    #: by `_probes_are_a_list` below, naming the edit.
    probes: Annotated[list[ProbesSpec], BeforeValidator(_probes_are_a_list)] = Field(
        default_factory=list
    )
    #: Native surface-property histories, separate from fluid samples and field products.
    surface_probes: list[SurfaceProbeSpec] = Field(default_factory=list)

    @field_validator("surface_probes")
    @classmethod
    def _unique_surface_probe_names(cls, value: list[SurfaceProbeSpec]) -> list[SurfaceProbeSpec]:
        names = [probe.name for probe in value]
        if len(set(names)) != len(names):
            raise ValueError("surface probe names must be unique within one pproc artifact")
        return value

    products: ProductsSpec = Field(default_factory=ProductsSpec)
    #: How a blade family is told from the airframe: a regular expression
    #: over the family name. The reference ones were Blade1 to Blade6.
    blade_pattern: str = r"^Blade\d+$"
    #: The boundaries that BECOME base regions (PFS-2029.10, RPT-066): one
    #: DETECT_BASE_REGIONS_BY_SURFACE per boundary of those families, after
    #: OPEN. A body's flat base, never the body carrying it, which the
    #: command marks nothing on, silently. Empty, the default, emits
    #: nothing; a row's BASE_REGIONS key overrides the artifact.
    base_regions: list[str] = Field(default_factory=list)

    def group_alias(self, name: str) -> str | None:
        """Return the ONE alias group ``name`` names, or None where it names several."""
        members = self.groups.get(name)
        if members is None or len(members) != 1 or not isinstance(members[0], str):
            return None
        return members[0]

    def equation_order(self) -> list[str]:
        """Return the order the equations must be evaluated in.

        An equation may name another equation, and the user writes them in a
        TOML table, which has no order anyone may rely on. So chaining is a
        feature only if the package can say WHICH ORDER, and an order exists
        only if a cycle is refused, because a cycle has none.

        A symbol the table does not define is a BASE VARIABLE and not a missing
        dependency. That direction matters more than it looks: the generated
        guide's own worked example is ``expression = "CT * 2"``, and treating
        every unknown symbol as unresolved would refuse the first equation any
        user writes.

        The expression is PARSED rather than searched, so ``CT`` inside
        ``CTX_WIND`` is not read as a reference to ``CT``. A substring reader
        invents dependencies and then invents cycles out of pairs that have
        none.

        Returns
        -------
        list of str
            Every equation name exactly once, each after every equation its
            expression names. Ties keep declaration order, so the answer is
            stable across runs and a diff of two products is about the numbers.

        Raises
        ------
        InputArtifactError
            When the equations are circular, naming the members of the cycle.
            "Circular" alone would send the user back to a TOML table to find
            the loop by eye.
        """
        names = list(self.equations)
        # A self-reference is kept rather than filtered out, so `A = A + 1`
        # can never be placed and reads as the cycle of one that it is. A
        # filter here would make it order cleanly and compute nothing.
        depends = {
            name: [token for token in spec.symbols() if token in self.equations]
            for name, spec in self.equations.items()
        }

        order: list[str] = []
        placed: set[str] = set()
        while len(order) < len(names):
            ready = [
                name
                for name in names
                if name not in placed and all(dep in placed for dep in depends[name])
            ]
            if not ready:
                stuck = sorted(name for name in names if name not in placed)
                raise InputArtifactError(
                    f"the equations {', '.join(stuck)} are circular: each waits on "
                    f"another in the set, so there is no order to evaluate them in. "
                    f"An equation may name another equation, but the chain has to end "
                    f"at variables the products already carry."
                )
            order.extend(ready)
            placed.update(ready)
        return order

    @model_validator(mode="after")
    def _the_equations_can_be_ordered(self) -> PprocSpec:
        """Refuse a circular chain when the pproc is READ, not when it is asked.

        `equation_order()` is public because a caller may want the order, but a
        refusal that only fires when someone remembers to ask is not a check.
        The information is available the moment the artifact is validated, and
        an engineer writing a TOML file should not have to open an interpreter
        to learn that the file is not well formed.

        The refusal is re-raised as a `ValueError` so it arrives as pydantic's
        own validation error, carrying the field and the artifact path that the
        loader adds, rather than escaping the model layer as something a caller
        of `PprocSpec(...)` would not think to catch.
        """
        try:
            self.equation_order()
        except InputArtifactError as circular:
            raise ValueError(str(circular)) from circular
        return self

    @field_validator("names")
    @classmethod
    def _one_readers_name_per_export_name(cls, value: dict[str, str]) -> dict[str, str]:
        """Refuse a dictionary two entries of which name one column, or a name not one word.

        Two plot columns renamed to one name would be two columns under one
        heading, and a reader taking a column by name would get whichever came
        last. A name holding a comma or a space is not a CSV heading a tool can
        ask for. Both are visible the moment the artifact is read.
        """
        taken: dict[str, str] = {}
        for printed, wanted in value.items():
            if wanted in REDUCTION_COLUMNS:
                raise ValueError(
                    f"[names] reduction column {printed!r} cannot be named {wanted!r}: "
                    f"{wanted} is a reserved context or identity column of the product"
                )
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-]*", str(wanted)):
                raise ValueError(
                    f"[names] {printed} = {wanted!r}: the name a column is given is one "
                    "word of letters, digits, underscores, dots and hyphens, starting with "
                    "a letter or an underscore, because it becomes a CSV heading"
                )
            if wanted in taken:
                raise ValueError(
                    f"[names] gives {taken[wanted]} and {printed} the one name {wanted!r}, "
                    "which would put two columns under one heading; give each its own"
                )
            taken[wanted] = printed
        return value

    @field_validator("equations")
    @classmethod
    def _an_equation_name_is_a_symbol(
        cls, value: dict[str, EquationSpec]
    ) -> dict[str, EquationSpec]:
        """Refuse a name no expression could write: it is how another equation uses this one.

        So it is one identifier, and it is none of the functions an expression
        may call: ``[equations.sqrt]`` would make ``sqrt(x)`` ambiguous, and
        ``[equations."C T"]`` could never be named by anything.
        """
        for name in value:
            if not name.isidentifier() or name in ALLOWED_FUNCTIONS:
                raise ValueError(
                    f"[equations.{name}]: an equation's name becomes the column "
                    f"{name}_<alias> and the symbol other expressions use, so it is letters, "
                    "digits and underscores, not starting with a digit, and not one of the "
                    f"functions {', '.join(ALLOWED_FUNCTIONS)}. Rename the entry."
                )
        return value

    @field_validator("exports")
    @classmethod
    def _known_export_kinds(cls, value: dict[str, bool]) -> dict[str, bool]:
        volume = sorted(set(value) & set(VOLUME_SECTION_KINDS.values()))
        if volume:
            raise ValueError(
                f"[exports] names {', '.join(volume)}: the volume section export is declared "
                "by [volume_section] format, not by [exports]; a point exports the one "
                "section its pproc declares, in the format that table names"
            )
        kinds = [
            kind for kind, _, _, _ in EXPORT_KINDS if kind not in VOLUME_SECTION_KINDS.values()
        ]
        unknown = sorted(set(value) - set(kinds))
        if unknown:
            raise ValueError(
                f"export kind(s) {', '.join(unknown)} are not among the export kinds a point "
                f"leaves: {', '.join(kinds)}"
            )
        if not value.get("loads", True):
            raise ValueError(
                "the loads table cannot be deselected: it is the export this package "
                "judges a run by"
            )
        # G11 (0.27.0): a point's final state is a guarantee, not a choice.
        # `false` here was the one route by which a row naming a run type left
        # no .fsm, and nothing said so.
        if not value.get("simulation", True):
            raise ValueError(
                "the saved simulation cannot be deselected: every point of a row naming a "
                "run type leaves its final .fsm in datapoints/DP-<point>/, hashed in its run "
                "record; remove 'simulation = false'"
            )
        return value

    @model_validator(mode="after")
    def _a_sections_plot_needs_sections(self) -> PprocSpec:
        # G04 (0.27.0): the section Cp plot is on by default only where the
        # artifact declares sections; an explicit true without them would save
        # the plot of no section, so it is refused naming the table it needs.
        if self.exports.get("plot_sections_cp") and not self.sections.distributions:
            raise ValueError(
                "[exports] plot_sections_cp = true and the artifact declares no "
                "[[sections.distributions]], so the solver would save the Cp plot of no "
                "section. Declare the sections to plot, or remove the key: the plot is "
                "saved by default wherever sections are declared"
            )
        return self

    @field_validator("blade_pattern")
    @classmethod
    def _compiles(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as error:
            raise ValueError(
                f"blade_pattern {value!r} is not a regular expression: {error}"
            ) from error
        return value

    def is_blade(self, family: str) -> bool:
        """Whether one family name is a blade by this artifact's pattern."""
        return re.match(self.blade_pattern, family) is not None

    @model_validator(mode="after")
    def _boundary_layer_sections_are_declared(self) -> PprocSpec:
        if self.products.boundary_layer_integrals and not self.sections.distributions:
            raise ValueError("boundary_layer_integrals requires declared sections.distributions")
        return self

    def outputs(self, unsteady: bool) -> list[str]:
        """Return the output names a row naming this artifact declares.

        The volume section's file joins a STEADY row's set when the artifact
        declares one (G05); an unsteady row declares none, and its builder
        refuses the artifact.
        """
        normal = unsteady and self.samples_normal_probes()
        names = default_outputs(
            unsteady,
            self.exports,
            has_sections=bool(self.sections.distributions),
            normal_probes=normal,
        )
        if self.products.boundary_layer_integrals:
            # Requested products require their native source exports, as fields do.
            for source in ("{name}.vtk", "{name}_cp.txt"):
                if source not in names:
                    names.append(source)
        if (
            (unsteady and self.surface_probes)
            or self.volume_section is not None
            or any(entry.field_formats or entry.reusable_inflow for entry in self.probes)
        ):
            # FR-418: a NORMAL entry's field is read from the probe-points
            # export on an unsteady row too, not from the plots history.
            source = "{name}_plots.txt" if unsteady and not normal else "{name}_probes.txt"
            if source not in names:
                names.append(source)
        return names

    def samples_normal_probes(self) -> bool:
        """Whether an unsteady row samples this artifact's probes as NORMAL probe points.

        True when the artifact declares at least one ``[[probes]]`` entry and
        every entry states ``kind = "normal"`` (FR-417); an entry that states no
        kind is ``unsteady``. A mixture is refused by the unsteady builders,
        naming the entries of each kind; a steady row samples probe points
        whatever this says.

        Returns
        -------
        bool
            Whether the entries are all normal probes.
        """
        return bool(self.probes) and all(entry.kind == "normal" for entry in self.probes)
