"""Simulation and campaign definitions.

Pipeline role: describes what to run. A :class:`SimCase` (identified
by ``sim_id``) is one solver configuration with its sweep; a
:class:`Campaign` groups cases with the FlightStream version and the
executable path, both required and explicit: nothing is read from
environment variables or guessed (SAD Section 5). Native persistence
is ``campaign.toml``; the pipe-delimited ``matrix.fs`` run matrix
is read unchanged, forever, by the matrix reader
(:mod:`pyflightstream.cases.matrix`, FR-10).

Script recipes are explicitly imported functions satisfying the
:class:`ScriptRecipe` protocol: ``build(case, script) -> None``. The
campaign loop specializes the case per sweep point (filling
:attr:`SimCase.point`) and the recipe translates it into script
emissions, usually through the curated helpers. Recipe references are
``"package.module:function"`` strings, replacing the historical
import-by-number system (PP-7, FR-12).
"""

from __future__ import annotations

import math
import re
import string
import tomllib
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from inspect import Parameter, signature
from pathlib import Path
from typing import Annotated, Literal, NamedTuple, Protocol, runtime_checkable

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

from pyflightstream._atmosphere import ISA
from pyflightstream._deprecations import (
    ROW_AIRFRAME_SELECTOR,
    ROW_BLADES_SELECTOR,
    ROW_EACH_BLADE,
    refusal_text,
)
from pyflightstream._digest import file_sha256, text_sha256
from pyflightstream._errors import (
    InputArtifactError,
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream._expressions import ALLOWED_FUNCTIONS, expression_symbols
from pyflightstream._fsm import names_of
from pyflightstream._retired_names import PROBE_SCALE_PROPELLER_RADIUS, retired_frame
from pyflightstream._tokens import REDUCTION_COLUMNS
from pyflightstream.commands import CommandRegistry, Phase
from pyflightstream.script import Script
from pyflightstream.script.toggles import resolve_toggle
from pyflightstream.versions import resolve

__all__ = [
    "AXIS_UNIT_VECTORS",
    "AliasCycleError",
    "BladeDatum",
    "ROTOR_BLADE_ROTATION_AXIS",
    "RotorBlock",
    "ActuatorBlock",
    "ROTATION_OFFSET_KEY",
    "ROTATION_SWEEP_KEY",
    "Campaign",
    "CampaignConfigError",
    "DerivedFrom",
    "FluidState",
    "EVERY_SURFACE",
    "MeshImport",
    "MeshOperation",
    "RawMeshConditions",
    "ReferenceData",
    "TrailingEdgeMarking",
    "ScriptRecipe",
    "SimCase",
    "SolverSettings",
    "SolverToggle",
    "EXPORT_KINDS",
    "EXPORT_KIND_MEANINGS",
    "EXPORT_KIND_SINCE",
    "InputKey",
    "SOLVER_SETTING_COMMANDS",
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
    "FrameSpec",
    "RAW_PHASES",
    "CustomFlag",
    "RawCommand",
    "PprocSpec",
    "SurfaceTimeAveragingSpec",
    "RESERVED_FRAME_NAMES",
    "SectionsSpec",
    "VOLUME_SECTION_KINDS",
    "VOLUME_SECTION_PRISMS",
    "VolumeSectionSpec",
    "PlotsSpec",
    "ProbesSpec",
    "ProductsSpec",
    "ForcePlotGroup",
    "SectionDistribution",
    "ProbeLine",
    "select_families",
    "select_group_members",
    "resolve_alias",
    "BoundaryAliases",
    "EXPANDING_SELECTORS",
    "default_outputs",
    "classify_outputs",
    "SweepAxis",
    "check_recipe",
    "derived_body_sha256",
    "geometric_sweep_values",
    "load_campaign",
    "multiplied_sweep",
    "NameField",
    "POINT_AXIS_KEYS",
    "PointState",
    "case_at_point",
    "point_state_key",
    "POINT_NAME_FIELDS",
    "SWEEP_NAME_VALUE",
    "name_field",
    "point_name",
    "point_tag",
    "sweep_name",
    "resolve_recipe",
    "stamp_derived_campaign",
]

#: The axes a point tag can name, and therefore the axes a run can be
#: IDENTIFIED by. All three are aerodynamic. Nothing geometric appears
#: here, which is the mechanical half of the reason a geometric sweep is
#: not allowed to multiply with an aerodynamic one; the reasoning is in
#: :func:`multiplied_sweep`.
_TAG_PREFIXES = (("alpha", "a"), ("beta", "b"), ("advance_ratio", "j"))

#: The case variable naming a rigid-body rotation of the geometry held
#: FIXED for the whole case: one angle in degrees, about the axis the
#: recipe or the workflow applies it to. This is the form that composes
#: with an aerodynamic sweep, and it is what a refusal points at.
ROTATION_OFFSET_KEY = "angle_deg"

#: The case variable naming a rotation the study SWEEPS: several angles
#: in degrees, comma separated, in the one string a case variable can
#: hold. A case naming two or more of these AND an aerodynamic sweep of
#: two or more points is refused (:func:`multiplied_sweep`).
ROTATION_SWEEP_KEY = "angle_sweep_deg"


class InputKey(NamedTuple):
    """One key of an input artifact, with what it means (G08 of 0.27.0).

    The registries of keys that are not the fields of a model carry one of
    these per key, beside the key: the matrix columns, the row keys of the run
    types, the reserved keys of a setup preset and the tables of a geometry
    sidecar. The generated input glossary, ``INPUTS.md``, is written from them
    and from the models, whose fields state their meaning in their own
    docstrings. So a key added to one of these registries arrives WITH its
    meaning, and a key that arrives without one fails the glossary's test.

    Attributes
    ----------
    meaning : str
        What the key sets, in one sentence.
    values : str
        Its unit, or the values it takes; empty where the meaning says it.
    command : str
        The solver command it reaches, or several separated by ``", "``;
        empty where it reaches none of its own.
    accepted : str
        Where the key is accepted, for a key whose registry does not say it.
    unscripted : str
        For a key whose VALUE no line of the run's script carries: what takes
        the value instead, or that nothing applies it. The glossary writes it
        after the meaning, behind "No line of the script carries its value",
        so a row cannot read as a solver input the script never states. Empty
        for a key whose value reaches the script.
    """

    meaning: str
    values: str = ""
    command: str = ""
    accepted: str = ""
    unscripted: str = ""


class CampaignConfigError(PyflightstreamError, ValueError):
    """A campaign or case definition cannot be used as written.

    A sweep point that cannot be tagged, a campaign file that does not
    load, a recipe that does not resolve to a callable or whose
    signature the loop cannot call. Distinct from
    :class:`~pyflightstream.cases.matrix.MatrixError`, which is about
    the pipe-delimited run-matrix format specifically.

    Added 2026-08-03 for FR-39, keeping ``ValueError`` as a second base.
    """


@runtime_checkable
class ScriptRecipe(Protocol):
    """A function that turns one case point into script emissions.

    Implementations receive the per-point specialized case (the
    campaign loop fills :attr:`SimCase.point` and stages the geometry)
    and an empty :class:`~pyflightstream.script.Script` bound to the
    campaign's FlightStream version; they emit the whole script,
    usually through the curated helpers. Output files must use paths
    relative to the execution directory, so the collected evidence
    stays inside the managed simulation folder, and must be the names
    the loop rendered into :attr:`SimCase.outputs`: those are the ones
    it collects, and they carry the sweep point.
    """

    def __call__(self, case: SimCase, script: Script) -> None:
        """Emit the complete script for one case point."""
        ...


class SweepAxis(BaseModel):
    """The sweep of one case: which axis varies and its values.

    Attributes
    ----------
    type : str
        The axis that varies: ``alpha`` (angle of attack, deg), ``beta``
        (side slip, deg), ``alpha_beta`` (paired values), ``advance_ratio``
        (rotor advance ratio J, dimensionless), or any FLIGHT_CONDITION key
        of :data:`POINT_AXIS_KEYS` since 0.21.0 (``MACH``, ``REmi``,
        ``ALTFT``, ``RPM``, ``pitch_rate`` and the rest), in the unit its key
        names. A flow variable that varies is RESOLVED PER POINT, and the
        state each point resolved to rides on :attr:`SimCase.point_states`.
    values : list
        Axis values; for ``alpha_beta`` each entry is an
        ``[alpha, beta]`` pair in deg.
    held : dict of str to float
        Coordinates the row HOLDS at every point, in deg, keyed like the
        swept axis and of the free stream, as ``values`` is. Merged into
        every point, so a row that sweeps the incidence at a fixed
        sideslip yields the same coordinates, and therefore the same run
        identity, as the paired sweep that spelled it before 0.15.0.
        ONLY THE TWO ANGLES: an ``ADVANCE_RATIO`` the row holds stays on
        the row, because a point tag has never carried one and putting it
        there would rename every run that has one. Empty for a row that
        holds nothing, and omitted from a written ``campaign.toml`` when
        it is.
    """

    model_config = ConfigDict(extra="forbid")

    #: Every point axis, plus the paired ``alpha_beta`` of the matrices written
    #: before 0.15.0. A member added to POINT_AXIS_KEYS is sweepable the day it
    #: is added, which is what keeps the two from drifting apart.
    type: Literal[
        "alpha",
        "beta",
        "alpha_beta",
        "advance_ratio",
        "MACH",
        "TASmps",
        "REmi",
        "ALTFT",
        "dISA",
        "RHOkgm3",
        "MUPas",
        "ASMPS",
        "TK",
        "PPA",
        "RPM",
        "roll_rate",
        "pitch_rate",
        "yaw_rate",
    ]
    values: list[float] | list[tuple[float, float]]
    #: WHY A HELD COORDINATE IS PART OF THE POINT AND NOT ONLY OF THE ROW,
    #: which the entry above states and does not explain.
    #: THE TAG IS IDENTITY. A row written `AL/BE` over `-4,0,4/0` swept the
    #: incidence and held the sideslip, and its points have been tagged
    #: `a-04.0_b+00.0` in every manifest ever written here. At 0.15.0 the
    #: same row is written `ALPHA:sweep, BETA:0.0` and the held value
    #: reaches the solver off the row; if it did not also reach the POINT,
    #: `pyfs-matrix upgrade` would rename every one of those runs to say
    #: what they always meant, and a resume would re-run them. Seats are
    #: the scarce thing here, so the converter is held to a stronger
    #: promise than lossless content: it does not rename a run.
    #:
    #: Only the two ANGLES are carried, because only they were ever
    #: capable of appearing in a tag as a held value. An advance ratio the
    #: row holds stays on the row, where it was before this release.
    held: dict[str, float] = {}

    @model_validator(mode="after")
    def _held_names_point_axes_the_sweep_does_not(self) -> SweepAxis:
        """Refuse a held coordinate that is not a point axis, or that is the swept one.

        `held` is a channel straight into the point mapping, and the point
        is read whole by more than the tag: a run record and a result
        table both iterate it. So a `campaign.toml` writing
        ``held = {mach = 0.2}`` would put a key nothing declares into
        every record, where `point_tag` ignores it and the table does
        not. The matrix reader can only produce the two angles; this is
        the OTHER door, and it was unguarded (the architecture lens,
        2026-09-10).

        A key equal to the swept axis is refused rather than shadowed.
        The merge order in :meth:`points` lets the sweep win, which keeps
        one behaviour rather than two, but a file stating a variable
        twice has said something it cannot mean and a silent winner is
        how the wrong one gets run.
        """
        axes = {axis for axis, _ in _TAG_PREFIXES}
        for key in self.held:
            if key not in axes:
                raise CampaignConfigError(
                    f"a sweep holds {key!r}, which is not a point axis. A held "
                    f"coordinate joins every point of the sweep and is named in every "
                    f"run_id, so it is one of {', '.join(sorted(axes))}. A quantity the "
                    "case holds and does not vary belongs in its variables."
                )
        if self.type in self.held:
            raise CampaignConfigError(
                f"this sweep varies {self.type} and also HOLDS it at "
                f"{self.held[self.type]!r}: the same variable cannot both vary and be "
                "held. Drop it from held, or sweep the other one."
            )
        return self

    @model_validator(mode="after")
    def _values_match_the_axis_type(self) -> SweepAxis:
        pairs = self.type == "alpha_beta"
        for value in self.values:
            if pairs != isinstance(value, tuple):
                expected = "[alpha, beta] pairs" if pairs else "scalar values"
                raise CampaignConfigError(f"a {self.type} sweep takes {expected}, got {value!r}")
        return self

    @model_validator(mode="after")
    def _points_have_distinct_tags(self) -> SweepAxis:
        """Refuse a sweep whose points cannot be told apart by their names.

        PYFS-003, and since 0.21.0 read on the POINT NAME. A point's name
        writes each axis at the digits of its code (alpha and beta to a tenth
        of a degree, the advance ratio to a hundredth), so alpha 1.01 and 1.04
        both write ``AL+010``. The name ENDS the ``run_id`` and names the
        datapoint folder, so two such points would share one identity.

        What made that expensive was where it surfaced: nothing refused the
        sweep, the pre-flight reported both points READY under one id, and the
        manifest's duplicate rejection only fired when the SECOND point tried
        to record, after the first had run. The refusal belongs at the sweep,
        where it costs nothing. The other variables of a name are the case's
        and the same on every point, so the swept axes alone decide.
        """
        seen: dict[str, dict[str, float]] = {}
        for point in self.points():
            tag = "".join(
                name_field(POINT_AXIS_KEYS[axis], point[axis])
                for axis in POINT_AXIS_KEYS
                if axis in point
            )
            if tag in seen:
                raise CampaignConfigError(
                    f"sweep points {seen[tag]!r} and {point!r} both write {tag!r} in their "
                    "names, so they would share one run_id, one datapoint folder and one set "
                    "of file names. A name writes an angle to a tenth of a degree and an "
                    "advance ratio to a hundredth; separate the values by that much, or split "
                    "them across simulations."
                )
            seen[tag] = point
        return self

    def points(self) -> Iterator[dict[str, float]]:
        """Iterate the sweep as named point coordinates.

        Yields
        ------
        dict of str to float
            One mapping per point, keyed ``alpha``, ``beta``, or
            ``advance_ratio`` (both keys for ``alpha_beta``), plus every
            coordinate in :attr:`held`.
        """
        for value in self.values:
            if self.type == "alpha_beta":
                alpha, beta = value
                point = {"alpha": alpha, "beta": beta}
            else:
                point = {self.type: value}
            # The order is deliberate and it is no longer OBSERVABLE: a
            # `held` key equal to the swept axis is REFUSED by the
            # validator above, so nothing can reach this merge and be
            # shadowed by it. It read "the swept axis wins a key it
            # shares with a held one" until a QA pass pointed out that a
            # silent winner was the whole hazard, and that a mutant
            # reversing the order passed every case (2026-09-10).
            yield {**self.held, **point}


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


#: The kinds only a STEADY point leaves. An unsteady point samples its probes
#: through fluid plots, so it exports no probe points. Of the solver's plots,
#: the residual and the load histories are saved after an unsteady march too,
#: once, at the end of the run (G26 of 0.28.0, RPT-076); the section Cp plot was
#: never run after one, so it stays steady-only, and a pproc stating it true on
#: an unsteady row is refused by the builder.
STEADY_ONLY_EXPORT_KINDS: frozenset[str] = frozenset({"probes", "plot_sections_cp"})

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
    "tecplot": "The surface solution in Tecplot format.",
    "vtk": "The surface solution in VTK format.",
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
        and not (unsteady and kind in STEADY_ONLY_EXPORT_KINDS)
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
        for kind, suffix, _, _ in by_length:
            if lowered.endswith(suffix) and kind not in claimed:
                claimed[kind] = str(name)
                break
    return claimed


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
    "CD": ("CD", "COEFFICIENTS"),
    "FX": ("FORCE_X", "NEWTONS"),
    "FY": ("FORCE_Y", "NEWTONS"),
    "FZ": ("FORCE_Z", "NEWTONS"),
    "MX": ("MOMENT_X", "NEWTONS"),
    "MY": ("MOMENT_Y", "NEWTONS"),
    "MZ": ("MOMENT_Z", "NEWTONS"),
}

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
    """The ``[volume_section]`` table: one flow-field plane a steady point exports (G05).

    The GUI's volume section, declared once in the pproc and cut by every
    point of a steady row after its solve: ``CREATE_NEW_RECTANGLE_VOLUME_SECTION``
    or ``CREATE_NEW_CIRCLE_VOLUME_SECTION`` in the named frame's plane, then
    ``EXPORT_VOLUME_SECTION_VTK`` or ``EXPORT_VOLUME_SECTION_TECPLOT`` to
    ``{name}_vsec.vtk`` or ``{name}_vsec.dat``.

    ONE SECTION PER PPROC. The point's outputs hold one name per export kind,
    so a second plane would need a kind that carries several names; that is a
    later release's.

    Attributes
    ----------
    shape : {'rectangle', 'circle'}
        Which create command cuts the plane.
    frame : str
        The frame the plane lies in: ``MRP``, or a frame the reference's
        ``[[frames]]`` table declares or a rotor carries. A frame the run did
        not create is refused when the script is built.
    plane : {'XY', 'XZ', 'YZ'}
        The frame's plane the section lies in.
    offset_m : float
        The plane's distance from the frame origin along its normal, in
        metres, the simulation's length unit.
    corners_m : tuple of four floats
        Rectangle only: ``x1, y1, x2, y2`` in metres, the two diagonal corners
        the command takes, in the plane. Which in-plane axis each pair runs
        along is the manual's (SRC-003 p.366); the verified probes cut the
        square from -1 to 1 and nothing else.
    refinement_layers : int
        Rectangle only: the command's refinement layer count, 1 unless stated.
        Only 1 has been sent to a solver.
    radii_m : tuple of two floats
        Circle only: the inner and outer radius in metres, ``0 <= r1 < r2``.
    points : tuple of two ints
        Circle only: ``ipts`` radial and ``jpts`` azimuthal segments.
    format : {'vtk', 'tecplot'}
        The export: ``EXPORT_VOLUME_SECTION_VTK`` or
        ``EXPORT_VOLUME_SECTION_TECPLOT``.
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
        own = _VOLUME_SECTION_SHAPE_KEYS[self.shape]
        other = next(shape for shape in _VOLUME_SECTION_SHAPE_KEYS if shape != self.shape)
        stray = [
            key
            for key in _VOLUME_SECTION_SHAPE_KEYS[other]
            if key in self.model_fields_set and getattr(self, key) is not None
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
EXPANDING_FRAMES = {"SMRP": "rotor", "RMRP": "rotor", "LOCAL_AXIS": "blade"}


def global_frame_plot_declarations(pproc: object) -> tuple[ForcePlotGroup, ...]:
    """Read declarations of all six load components in the global MRP frame.

    A ``{family}`` name counts: its emitted groups still measure global loads.
    This reads declarations, not emitted names; post must separately reject
    ambiguous names and cannot infer a template's expansion from its spelling.
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
        all of them.
    groups : list of ForcePlotGroup
        The groups of families, one plot per parameter each.
    """

    model_config = ConfigDict(extra="forbid")

    parameters: list[str] = Field(default_factory=lambda: list(FORCE_PLOT_PARAMETERS))
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


def _a_group_is_one_alias(value):
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


def _probes_are_a_list(value):
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

    @model_validator(mode="after")
    def _points_come_from_one_place(self) -> ProbesSpec:
        """Either the entry draws its own lines, or it cites a file, not both.

        An entry carrying both states the survey twice, and nothing keeps the
        two in agreement. Which one would win is the kind of question a reader
        should never have to ask of a file they wrote.
        """
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
    """

    model_config = ConfigDict(extra="forbid")

    polars: bool = True
    sections: bool = True
    plots: bool = True
    custom_polar_format: bool = False
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


#: Frame names the package creates itself (PFS-2030.03.02); a setup may
#: not define one of these, because the row's rotation and the pproc
#: definitions resolve them to the package's own frames. The rotor run
#: type also creates each rotor's ``<ALIAS>_SMRP`` and ``BladeAxis<k>``,
#: one per record or blade family, refused by pattern below (the
#: interface lens of REL-0140: a setup defining ROTOR_MRP1 was shadowed).
#: `ROTOR_MRP` LEFT THIS TUPLE AT 0.15.0 with the frame itself. Reserving
#: a name no builder creates refused a setup frame for colliding with
#: nothing, which is a refusal a user cannot act on. A rotor's own frames
#: are protected by the two-sided guard in `workspace.inputs`, which
#: composes `<ALIAS>_SMRP` forward rather than reading a shape backward.
RESERVED_FRAME_NAMES: tuple[str, ...] = ("MRP",)
RESERVED_FRAME_PATTERN = re.compile(r"^BLADEAXIS\d+$")


#: The phases a raw command may be declared before (PFS-2033.01):
#: ``control`` for a line at the head of the script, since a control
#: command may appear anywhere, then the command database's own in the
#: order the script layer enforces, read off the enum rather than
#: restated (the architecture lens of REL-0140).
RAW_PHASES: tuple[str, ...] = (
    Phase.CONTROL.value,
    *(phase.value for phase in Phase if phase is not Phase.CONTROL),
)

#: THE SEAMS A CUSTOM FLAG MAY REACH, three of the seven a raw entry reaches:
#: the ones before the run begins. A command of a later phase is part of the
#: RUN rather than of its setting up, and this package emits those itself.
#:
#: IT LIVES HERE AND NOT IN THE BUILDER. `before` was validated against
#: `RAW_PHASES` while the builder honoured this shorter list, so a flag
#: declared `before = "export"` passed the model, passed the reader, and died
#: later with a sentence about seams: two vocabularies for one field, and the
#: earlier, cheaper refusal was the wrong one (the architecture lens of the
#: 0.15.0 release review).
FLAG_PHASES: tuple[str, ...] = ("control", "geometry", "setup")


class CustomFlag(BaseModel):
    """One solver command a setup exposes to the matrix under a name (PFS-2035.20).

    The design of 2026-09-10: a setup declares the FlightStream
    command and the word a row uses for it, and the row then states the
    VALUE. RAW states a whole line and every row citing that setup emits
    the same one; a flag states the command and lets the row sweep what
    it is set to, which is what makes RAW the escape for a particular
    case rather than the ordinary way to reach a setting.

    Attributes
    ----------
    name : str
        The word a matrix row writes in its VAR_NAMES_VALUES cell. It is
        read case folded, as every other row key is.
    command : str
        The FlightStream command the flag becomes, bare: the row supplies
        the arguments. A line with arguments is refused, because the
        value would then be stated twice and the two could disagree.
    before : str or None
        The phase the command is emitted before. None takes the phase the
        command's own database entry declares, which is the answer for
        every command that has one; state it only to move a CONTROL
        command, whose phase the database leaves open.
    setup : str or None
        The artifact the declaration came from, bound by the workspace
        for the run record and for the refusal.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    command: str
    before: str | None = None
    setup: str | None = None

    @field_validator("name", "command", mode="before")
    @classmethod
    def _stripped(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _a_name_and_a_bare_command(self) -> CustomFlag:
        if not self.name:
            raise ValueError("a flag needs a name, the word a matrix row writes for it")
        if not self.command:
            raise ValueError(
                f"the flag {self.name!r} names no command; write the FlightStream "
                'command it becomes, bare, as command = "SET_WAKE_LENGTH"'
            )
        if len(self.command.split()) > 1:
            raise ValueError(
                f"the flag {self.name!r} states command = {self.command!r}, which carries "
                "arguments. A flag is the command alone and the ROW states the value; a "
                "line with its arguments already in it is a [[raw]] entry, which is what "
                "that table is for."
            )
        if self.before is not None and self.before not in FLAG_PHASES:
            raise ValueError(
                f"the flag {self.name!r} is declared before {self.before!r}, which is not a "
                f"seam a flag reaches; a flag is emitted before one of "
                f"{', '.join(FLAG_PHASES)}, three of the seven a [[raw]] entry reaches. "
                "Leave it out to take the phase the command's own entry declares. A "
                "setting of a later phase is part of the RUN rather than of its setting "
                "up, and a row that needs one states it in the [[raw]] table."
            )
        return self


class RawCommand(BaseModel):
    """One solver command a setup artifact states verbatim (PFS-2033.01).

    The design of 2026-09-09 (design/69): the user writes the command
    line as the solver reads it, arguments included, and names the phase
    it goes before; the builders emit it through the same emitter every
    curated helper uses, so the database's grammar, version, argument
    and phase checks apply to it unchanged. ``setup`` is the artifact
    the entry came from, bound by the workspace for the run record.

    Attributes
    ----------
    command : str
        The command line as the solver reads it, arguments included.
    before : str
        The phase the line is emitted before: ``control`` for a line at the
        head of the script, or one of the command database's phases.
    setup : str or None
        The artifact the entry came from, bound by the workspace.
    source : str or None
        Where the line came from, for the run record and a refusal.
    """

    model_config = ConfigDict(extra="forbid")

    command: str
    before: str
    setup: str | None = None
    #: WHERE THIS LINE CAME FROM, for the run record and for the refusal
    #: (FR-67). A setup's id, the word ``matrix`` for a line written in the
    #: row's own cell, or ``<path>:<line number>`` for a line read out of a
    #: file of the workspace. The last is why this exists at all: a file
    #: carrying a command the build lacks must be refused naming THE FILE
    #: and THE LINE, not the cell that pointed at it, because the cell
    #: holds a path and the mistake is thirty lines away.
    source: str | None = None

    @field_validator("command", mode="before")
    @classmethod
    def _stripped(cls, value: object) -> object:
        # On both construction paths (the QA lens of REL-0140 measured the
        # constructor keeping the padding the validate path stripped).
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _one_line_before_a_known_phase(self) -> RawCommand:
        line = self.command
        if not line:
            raise ValueError("a raw entry needs a command, the line as the solver reads it")
        if "\n" in line or "\r" in line:
            raise ValueError(
                f"the raw command {self.command!r} spans several lines; an entry is one "
                "command line, and a command that is a block is not carried here"
            )
        if self.before not in RAW_PHASES:
            raise ValueError(
                f"the raw command {line!r} is declared before {self.before!r}, which is not a "
                f"phase; write one of {', '.join(RAW_PHASES[1:])}, or control for a line at "
                "the head of the script"
            )
        return self


class FrameSpec(BaseModel):
    """One custom coordinate system the reference's ``[[frames]]`` defines (PFS-2034.01, FR-72).

    The design of 2026-09-09 (design/69): the row's rotation names an
    axis as ``<frame>-<X|Y|Z>``, and the frame is one the setup defined
    here or one the package creates (``MRP``; ``ROTOR_MRP`` on the rotor
    run types). The origin is in the geometry's own frame, the solver's
    reference frame, in the simulation's length unit, and the two axes
    are direction vectors in that frame; the third axis is the right-handed cross product,
    as :func:`pyflightstream.script.helpers.coordinate_frame` computes it.

    Attributes
    ----------
    name : str
        The frame's name, which a row's ``AXIS`` and a pproc entry's
        ``frame`` cite.
    origin : tuple of three floats
        The frame's origin, in the geometry's own frame, in metres.
    x_axis : tuple of three floats
        The direction of the frame's first axis.
    y_axis : tuple of three floats
        The direction of the frame's second axis; the third is their
        right-handed cross product.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    origin: tuple[float, float, float]
    x_axis: tuple[float, float, float] = (1.0, 0.0, 0.0)
    y_axis: tuple[float, float, float] = (0.0, 1.0, 0.0)

    @field_validator("name", mode="before")
    @classmethod
    def _stripped(cls, value: object) -> object:
        # The name the solver shows and a row's AXIS token cites, stored as
        # validated (the architecture lens of REL-0140: " NAC " passed and
        # no token could then resolve it).
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _a_name_of_its_own(self) -> FrameSpec:
        name = self.name
        if not name:
            raise ValueError("a frame needs a name")
        retired = retired_frame(name)
        if retired is not None:
            # REFUSED WHERE IT IS WRITTEN, not only where it is cited. The
            # reserved set lost these spellings with the frames themselves,
            # so a reference could DECLARE `[[frames]] name = "PROP_MRP"`,
            # load clean, and have the citation refused later with a message
            # saying the user's own declared frame was renamed (the interface
            # lens of the 0.15.0 release review).
            raise ValueError(retired.message(wrote=name))
        if name.upper() in RESERVED_FRAME_NAMES or RESERVED_FRAME_PATTERN.match(name.upper()):
            raise ValueError(
                f"the frame name {self.name!r} is one the package creates itself "
                f"({', '.join(RESERVED_FRAME_NAMES)}, and BladeAxis<k> on a rotor "
                "row); choose another name. A rotor's own frames are protected "
                "separately, by the guard that composes <ALIAS>_SMRP forward from the "
                "rotors the reference declares"
            )
        return self


#: How closely a blade datum may lie along the shaft before its azimuth means
#: nothing. It is compared against `|cos(angle between shaft and datum)|`,
#: which is 1 when they are PARALLEL and 0 when they are square, so the
#: number is `cos(5 degrees)` and the refusal fires ABOVE it: a datum within
#: five degrees of the shaft is refused, and a datum at any other angle,
#: however far from square, is accepted.
#:
#: IT WAS `cos(85 degrees)` UNTIL 0.23.0's RELEASE ROUND, which is the
#: complement, and the complement refused every datum more than five degrees
#: from SQUARE -- an ordinary installation at 30 degrees among them. Both
#: datum tests of the day used a datum exactly square or one degree from
#: parallel, and those two verdicts are the same under either reading, so
#: nothing could tell them apart. The message made it worse by printing the
#: angle from the shaft and then saying the datum "nearly lies along" it.
#:
#: The FIVE is a JUDGEMENT rather than a measurement and is written as one;
#: what is not a judgement is that some bound must exist, because an axis that
#: can point anywhere makes "nearly parallel" the ordinary case.
_DATUM_ALIGNMENT_LIMIT = 0.9961946980917455

#: Below this, a vector has no length worth normalising and names no
#: direction. It is a LENGTH tolerance rather than a component one, so a
#: direction stated in millimetres is not refused for being small.
_AXIS_TOLERANCE = 1e-12

#: The unit vector each axis letter has always meant. The letter path resolves
#: through this rather than through a branch, so "Z is (0,0,1)" is a lookup a
#: reader can check instead of a claim.
#:
#: PUBLIC, and a guard made it so. It was `_AXIS_LETTERS` and `cases.workflows`
#: imported it from `cases`, which the layer test refuses: an underscore-private
#: name taken out of a public sibling is a boundary crossed for a helper.
#: Publishing it is the fix the guard names, and it is the honest one -- a
#: reader writing a rotor block needs to know what a letter means.
AXIS_UNIT_VECTORS: dict[str, tuple[float, float, float]] = {
    "X": (1.0, 0.0, 0.0),
    "Y": (0.0, 1.0, 0.0),
    "Z": (0.0, 0.0, 1.0),
}

_AXIS_TOKEN = re.compile(r"^[+-]?[XYZ]$")

#: The axis a blade's azimuth is turned about, as the emitted command names it.
#:
#: IT IS A LETTER AND ALWAYS WILL BE, because the axis it names belongs to the
#: HUB FRAME rather than to the geometry. `ROTATE_COORDINATE_SYSTEM` declares
#: `rotation_axis` as an enum over X, Y, Z, 1, 2 and 3, and the blade frames are
#: turned about the hub -- whose third axis IS the shaft, by construction of
#: :func:`frame_basis_for_shaft`. So the shaft's direction rides on the FRAME
#: and never on this argument, and a rotor installed at any pitch and toe emits
#: the same letter as one installed square.
#:
#: The blade frame builder passed `rotor.axis` straight into that argument until
#: 0.23.0's release round, and `axis` had just been widened to take three
#: components -- so a rotor stating its installation vector emitted a PYTHON
#: TUPLE where the solver expects one letter. Nothing caught it because every
#: test of the item stopped at the basis and none emitted a script.
ROTOR_BLADE_ROTATION_AXIS = "Z"


class BladeDatum(BaseModel):
    """Where blade one sits, and the axis its azimuth is measured from (FR-60).

    The decision of 2026-09-10, on the first reading of the use case: an
    azimuth ALONE carries a hidden convention, zero at which axis, that
    two people fill differently and nobody sees. So the datum is written
    beside it: ``{ azimuth_deg = 45.0, zero = "X" }``, the zero being an
    axis letter with an optional sign, refused when it is parallel to the
    axis the rotor turns about, because an angle measured from that axis
    locates nothing.

    Attributes
    ----------
    azimuth_deg : float
        Where blade one is, measured from ``zero`` about the rotor's axis.
    zero : str
        The axis letter the azimuth is measured from, with at most one sign.
    """

    model_config = ConfigDict(extra="forbid")

    azimuth_deg: float = 0.0
    zero: str = "X"

    @field_validator("zero", mode="before")
    @classmethod
    def _an_axis_letter(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        token = value.strip().upper()
        # ONE SIGN AT MOST, and the pattern says so: `lstrip("+-")` strips a
        # RUN, so "+-X" and "-+X" validated and were then stored verbatim,
        # a spelling this package never meant to accept (the interface lens
        # of 2026-09-10).
        if not _AXIS_TOKEN.match(token):
            raise ValueError(
                f"blade1 states zero = {value!r}, which is not an axis; write X, Y or Z, "
                "with at most one leading sign. The sign reverses the direction the "
                "azimuth is measured FROM, not the sense in which it increases"
            )
        return token


class RotorBlock(BaseModel):
    """One rotor, declared as one block of the reference artifact (FR-60).

    The design of 2026-09-10. The block's NAME is an alias over
    everything the rotor owns, the union of :attr:`families_general` and
    :attr:`families_blades` in that order: what a row moves when it cites
    it, and what a group summing the rotor sums.

    THE NAME IS FREE, AND A TRAILING DIGIT IS FINE: the eight lifters of
    a four-a-side aircraft are ``LIFT_L1`` to ``LIFT_R4``. What it may
    not carry is ``_SMRP`` or ``_RMRP``, the radical of the frames the
    package builds from it (the static and rotating moment reference
    points of the rotor), because then a rotor and a frame spell the
    same. PFS-2035.02 said a name ending in a digit is refused, which was
    true of the frame names of 0.14.0 and would refuse the reference study
    under these: the number in ``<ALIAS>_RMRP<k>`` follows ``RMRP``, never
    the alias.

    Attributes
    ----------
    alias : str
        The word a row moves. It is the block's NAME, and this field is a
        restatement of it: a reference file may leave it out and the
        reader fills it in from the name before the block is built;
        stated, it must equal the name, case folded, and a block whose two
        names disagree is refused naming both. Whether the field is worth
        keeping at all is an open question of 2026-09-10.

        IT IS REQUIRED ON THE MODEL even though a file may omit it,
        because everything downstream reads it as the rotor's identity:
        it is the radical of the frames, the word written back into
        MOVING_BC_ALIAS, and what a refusal names. An optional field left
        None built frames called ``None_RMRP1`` rather than refusing, and
        a type check is what found it.
    x_m, y_m, z_m : float
        The hub, in the geometry's own frame.
    axis : str
        The axis it turns about.
    rpm_sign : int
        ``+1`` is the right-hand rule about ``axis``, which is the one
        reading that does not depend on where the reader stands.
    diameter_m : float
        The length an ADVANCE_RATIO resolves against, PER ROTOR: one
        ratio written once in the flight condition gives each rotor a
        speed of its own (FR-63).
    families_general : list of str
        What turns with the rotor and is NOT a blade, the spinner and the
        hub. It has no local axis of its own: its local frame IS the
        rotor's.
    families_blades : list of str
        One entry per blade, in order. THE BLADE COUNT IS THE LENGTH OF
        THIS LIST, so a row states no blade count and a sector mesh
        carrying one blade of four still reduces over four.
    blade1 : BladeDatum
        Where blade one sits, and the axis its azimuth is measured from.
    kind : str
        ``"rotor"``, which is what makes a top-level table of the reference
        a rotor block.
    """

    model_config = ConfigDict(extra="forbid")

    alias: str
    axis: str | tuple[float, float, float] | list[float]
    diameter_m: float = Field(gt=0.0)
    families_blades: list[str]
    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0
    rpm_sign: int = 1
    families_general: list[str] = Field(default_factory=list)
    blade1: BladeDatum = Field(default_factory=BladeDatum)
    kind: str = "rotor"

    @property
    def blade_count(self) -> int:
        """The number of blades, which is the length of :attr:`families_blades`."""
        return len(self.families_blades)

    @property
    def members(self) -> list[str]:
        """Everything the rotor owns, general families first, in the order written."""
        return [*self.families_general, *self.families_blades]

    @property
    def origin(self) -> tuple[float, float, float]:
        """The hub, as the three coordinates a motion is built on."""
        return (self.x_m, self.y_m, self.z_m)

    @field_validator("axis", mode="before")
    @classmethod
    def _an_axis(cls, value: object) -> object:
        """Accept a LETTER or a three-component VECTOR (v0.23.0 item 19).

        The letter keeps its exact meaning: `Z` IS the vector (0, 0, 1), so the
        old spelling is a special case of the new one and every reference
        written before this release asks the solver for exactly what it always
        did. The vector exists because a mesh can arrive with its pitch and toe
        already in it, and a shaft installed at an angle lies on no geometry
        axis at all.
        """
        if isinstance(value, str):
            token = value.strip().upper()
            if token not in ("X", "Y", "Z"):
                # "not an axis" IS THE CONTRACT and the vocabulary test pins it:
                # it is the phrase a user greps for and the one the reference
                # documentation carries. Widening what `axis` accepts may add to
                # the sentence and may not replace it.
                raise ValueError(
                    f"axis = {value!r} is not an axis; write X, Y or Z, or the three "
                    "components of the shaft direction for a rotor installed at an angle"
                )
            return token
        if isinstance(value, (list, tuple)):
            if len(value) != 3:
                raise ValueError(
                    f"axis = {value!r} has {len(value)} components; a direction in space has three"
                )
            try:
                components = tuple(float(component) for component in value)
            except (TypeError, ValueError) as error:
                raise ValueError(f"axis = {value!r} is not three numbers: {error}") from error
            length = math.sqrt(sum(component * component for component in components))
            if length <= _AXIS_TOLERANCE:
                raise ValueError(
                    f"axis = {value!r} has no length, so it names no direction, and a rotor "
                    "turns about a direction"
                )
            return components
        return value

    @property
    def axis_vector(self) -> tuple[float, float, float]:
        """The shaft direction as a UNIT vector, whichever way it was written.

        Every frame the package builds for this rotor is built on this, rather
        than on the geometry's own axes. Until 0.23.0 seven call sites created
        a rotor's frames with `x_axis=(1,0,0)` and `y_axis=(0,1,0)`, which is
        to assume the rotor is installed at zero pitch and zero toe.
        """
        stated = self.axis
        if isinstance(stated, str):
            return AXIS_UNIT_VECTORS[stated]
        components = tuple(float(component) for component in stated)
        length = math.sqrt(sum(component * component for component in components))
        return (components[0] / length, components[1] / length, components[2] / length)

    @field_validator("rpm_sign")
    @classmethod
    def _a_sign(cls, value: int) -> int:
        if value not in (1, -1):
            raise ValueError(
                f"rpm_sign = {value!r} is not a sign; write 1 or -1, where +1 is the "
                "right-hand rule about axis"
            )
        return value

    @model_validator(mode="after")
    def _a_rotor_with_blades_and_a_usable_datum(self) -> RotorBlock:
        if not self.families_blades:
            raise ValueError(
                "families_blades is empty, and the blade count is its length, so this "
                "rotor has no blades; name one mesh family per blade, in order"
            )
        # BY ANGLE AND NOT BY SPELLING since 0.23.0 item 19. This compared two
        # STRINGS, so it caught `axis = Z, zero = Z` and was blind to a shaft
        # at (0, 0.02, 0.9998) with a datum at Z, which is one degree from
        # parallel: an azimuth measured from it locates nothing and it reported
        # a number rather than refusing. A string comparison cannot see
        # "nearly", and once the axis can be any direction, nearly is the
        # ordinary case rather than the exotic one.
        shaft = self.axis_vector
        datum = AXIS_UNIT_VECTORS[self.blade1.zero.lstrip("+-")]
        alignment = abs(sum(a * b for a, b in zip(shaft, datum, strict=True)))
        if alignment > _DATUM_ALIGNMENT_LIMIT:
            degrees = math.degrees(math.acos(min(1.0, alignment)))
            raise ValueError(
                f"blade1 measures its azimuth from {self.blade1.zero}, which is "
                f"{degrees:.2f} degrees from the shaft direction {shaft}. An azimuth "
                "measured from a datum that nearly lies along the shaft locates nothing, "
                "so it is refused rather than reported. Choose a datum square to the disk"
            )
        return self


class ActuatorBlock(BaseModel):
    """One actuator disc, declared as one block of the reference artifact (G06).

    The linearized propeller slipstream the solver models with an actuator
    (SRC-003 pp.185-187). Its GEOMETRY is the configuration's, so it lives in
    the reference beside the rotors and the frames, as a top-level table with
    ``kind = "actuator"`` whose NAME is the disc's name; its LOADING is the
    condition's, so a row states it (``ACTUATOR``, ``ACTUATOR_RPM`` and one of
    ``ACTUATOR_THRUST`` or ``PROFILE``). A reference declaring a disc moves
    nothing on a row that names none.

    Attributes
    ----------
    kind : str
        ``"actuator"``, which is what makes a top-level table of the reference
        an actuator disc.
    frame : str
        The frame the disc's axis belongs to: a name the reference's
        ``[[frames]]`` declares, ``MRP``, or a rotor's frame. The command
        places a disc on a local frame, never on the reference frame, and a
        name the run did not create is refused when the script is built.
    axis : {'X', 'Y', 'Z'}
        The frame's axis the disc turns about.
    offset_m : float
        The disc's position along that axis, from the frame's origin.
    tip_radius_m : float
        The disc's outer radius.
    hub_radius_m : float
        The disc's inner radius, ``0 <= hub < tip``.
    rpm_sign : int
        ``+1`` is the right-hand rule about ``axis``, as a rotor block's; the
        row's ``ACTUATOR_RPM`` is a magnitude and this is its hand.
    blades : int, optional
        The blade count a profile file's distribution is read per; required
        by a row stating ``PROFILE``.
    swirl : float, optional
        The fraction, 0 to 1, of the swirl velocity kept downstream
        (``SET_PROP_ACTUATOR_SWIRL``); unstated, no swirl command is emitted.
    profile_units : str
        The force unit a profile file is written in, as the command database
        spells ``SET_PROP_ACTUATOR_PROFILE``'s ``units_type``.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    kind: Literal["actuator"] = "actuator"
    frame: str
    axis: Literal["X", "Y", "Z"]
    offset_m: float = 0.0
    tip_radius_m: float = Field(gt=0.0)
    hub_radius_m: float = Field(ge=0.0)
    rpm_sign: int = 1
    blades: int | None = Field(default=None, ge=1)
    swirl: float | None = Field(default=None, ge=0.0, le=1.0)
    profile_units: Literal["NEWTONS", "KILO-NEWTONS", "POUND-FORCE", "KILOGRAM-FORCE"] = "NEWTONS"

    @field_validator("frame")
    @classmethod
    def _a_frame_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "frame names the frame the disc's axis belongs to, a name the reference's "
                "[[frames]] declares; it is empty"
            )
        return value

    @field_validator("rpm_sign")
    @classmethod
    def _a_sign(cls, value: int) -> int:
        if value not in (1, -1):
            raise ValueError(
                f"rpm_sign = {value!r} is not a sign; write 1 or -1, where +1 is the "
                "right-hand rule about axis"
            )
        return value

    @model_validator(mode="after")
    def _the_hub_is_inside_the_tip(self) -> ActuatorBlock:
        if self.hub_radius_m >= self.tip_radius_m:
            raise ValueError(
                f"hub_radius_m = {self.hub_radius_m} is not inside tip_radius_m = "
                f"{self.tip_radius_m}: a disc is the annulus between the two"
            )
        return self


def frame_basis_for_shaft(
    shaft: tuple[float, float, float],
    datum: tuple[float, float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return the ``x_axis`` and ``y_axis`` of a frame whose THIRD axis is ``shaft``.

    v0.23.0 item 19. `coordinate_frame` completes a basis with the right-handed
    cross product, so handing it two axes square to the shaft puts the shaft on
    the frame's third axis by construction rather than by arithmetic anyone has
    to check.

    ``x_axis`` is the blade datum PROJECTED INTO THE DISK PLANE. That is what
    makes an azimuth well defined on a tilted rotor: the datum a user names is
    a direction in the geometry, and the angle is measured in the plane the
    blades actually sweep, not in the plane the geometry's axes happen to
    define. On an untilted rotor the projection changes nothing, which is why
    a reference written before this release produces the same frame.

    The caller is responsible for the datum not lying along the shaft;
    `RotorBlock` refuses that by ANGLE before anything reaches here.
    """
    along = sum(a * b for a, b in zip(shaft, datum, strict=True))
    projected = tuple(d - along * s for s, d in zip(shaft, datum, strict=True))
    length = math.sqrt(sum(component * component for component in projected))
    if length <= _AXIS_TOLERANCE:
        raise CampaignConfigError(
            f"the blade datum {datum} lies along the shaft {shaft}, so it projects to "
            "nothing in the disk plane and no azimuth can be measured from it"
        )
    x_axis = tuple(component / length for component in projected)
    y_axis = (
        shaft[1] * x_axis[2] - shaft[2] * x_axis[1],
        shaft[2] * x_axis[0] - shaft[0] * x_axis[2],
        shaft[0] * x_axis[1] - shaft[1] * x_axis[0],
    )
    return x_axis, y_axis


class AliasCycleError(PyflightstreamError, ValueError):
    """An alias resolves through itself, and both sides are named (FR-59).

    The design of 2026-09-10 lets an alias name another alias, resolved to
    the end. That is what makes a cycle possible, so the reader refuses one
    rather than recursing: the message names the alias that closed the ring
    and the member that closed it, because a reader holding only one of the
    two names has to open the file to find the other.
    """


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
        allowed = next(arg.values for arg in entry.args if arg.name == "variables")
        unknown = sorted(set(value) - set(allowed))
        if unknown:
            raise ValueError(f"vtk_variables: unknown variable(s) {', '.join(unknown)}")
        if not value or len(set(value)) != len(value):
            raise ValueError(
                "vtk_variables must be a nonempty list of distinct command variable names"
            )
        return value

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

    def outputs(self, unsteady: bool) -> list[str]:
        """Return the output names a row naming this artifact declares.

        The volume section's file joins a STEADY row's set when the artifact
        declares one (G05); an unsteady row declares none, and its builder
        refuses the artifact.
        """
        names = default_outputs(
            unsteady, self.exports, has_sections=bool(self.sections.distributions)
        )
        if self.volume_section is not None and not unsteady:
            kind = VOLUME_SECTION_KINDS[self.volume_section.format]
            suffix = next(suffix for name, suffix, _, _ in EXPORT_KINDS if name == kind)
            names.append(f"{{name}}{suffix}")
        return names


#: The two selector words this release retires, each to its ledger entry.
#: They are the two that decide what a BLADE is from a pattern over the
#: family name; `all` and `each` guess nothing and stay (the design decision of
#: 2026-09-10).
_SELECTORS_THAT_GUESS = {
    "airframe": ROW_AIRFRAME_SELECTOR,
    "blades": ROW_BLADES_SELECTOR,
}


def warn_a_selector_that_guesses(word: str) -> None:
    """Warn that a families selector deciding what a blade is has retired."""
    # NO PREFIX. The ledger entry already opens with its owner, so
    # prefixing "a families cell" produced "a families cell: families =
    # 'airframe' of a families cell was renamed to ..." (the interface lens
    # of 2026-09-10).
    raise CampaignConfigError(refusal_text(_SELECTORS_THAT_GUESS[word]))


def select_families(
    selection: str | Sequence[str],
    inventory: Sequence[str],
    is_blade: Callable[[str], bool],
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[list[str]]:
    """Expand one families entry over the geometry's inventory, in inventory order.

    Returns a list of family lists, one per emitted entry: a single list
    for a selector or a literal list, one list per family for ``each``
    and ``each_blade``. A family the geometry does not carry is left out,
    as the reference driver filtered its tables to the components it opened; an
    entry that resolves to nothing is an empty result and the caller
    skips it. ``all`` is the empty list standing for the command's own
    every-boundary form, which the caller spells as -1. An ALIAS of the
    row's setup (the design decision of 2026-09-09) is read before the five
    selector words, as the bare string and as a list member, so
    ``airframe`` and ``blades`` are the setup's own where it defines them;
    a bare word that is neither is a family name.
    """
    blades = [name for name in inventory if is_blade(name)]
    if isinstance(selection, str):
        aliased = resolve_alias(selection, inventory, aliases)
        if aliased is not None:
            return [aliased] if aliased else []
        if selection == "all":
            return [[]]
        # THE ALIAS WAS TRIED FIRST, six lines up, so reaching here means
        # the word was read AS A SELECTOR and no alias of that name
        # resolved. That is the only case the retirement is about: a
        # reference that declares `airframe` keeps working unchanged, which
        # is what every one of the reference rows does (the design decision of 2026-09-10).
        if selection == "airframe":
            warn_a_selector_that_guesses(selection)
            chosen = [name for name in inventory if not is_blade(name)]
            return [chosen] if chosen else []
        if selection == "blades":
            warn_a_selector_that_guesses(selection)
            return [blades] if blades else []
        if selection == "each":
            return [[name] for name in inventory]
        if selection == "each_blade":
            return [[name] for name in blades]
        # A bare word outside the five and the aliases is a family (the reference
        # p001 of 2026-09-09); one the inventory lacks is an empty result.
        names = names_of(selection, inventory)
        return [names] if names else []
    chosen: list[str] = []
    for item in selection:
        aliased = resolve_alias(item, inventory, aliases)
        if aliased is not None:
            names = aliased
        elif item == "blades":
            warn_a_selector_that_guesses(item)
            names = blades
        elif item == "airframe":
            warn_a_selector_that_guesses(item)
            names = [name for name in inventory if not is_blade(name)]
        else:
            # A list member resolves as the bare word does, family
            # fallback included (the interface lens of 2026-09-09: the
            # same word selected six blades written alone and nothing
            # written in a list).
            names = names_of(str(item), inventory)
        chosen.extend(name for name in names if name not in chosen)
    return [chosen] if chosen else []


#: The words a ``families`` entry EXPANDS rather than naming a set with,
#: which an alias may not take (the interface lens of 2026-09-09): ``all``
#: is the command's own every-boundary form and the two ``each`` words emit
#: one entry per family. ``airframe`` and ``blades`` name a set and stay
#: shadowable, which is what the design decision asked for.
EXPANDING_SELECTORS = ("all", "each", "each_blade")
#: A boundary-citing cell reads ``g<number>`` as a pproc group, so an alias
#: may not take that spelling.
_GROUP_SPELLING = re.compile(r"^g\d+$")


def _check_aliases(value: dict[str, list[str]]) -> dict[str, list[str]]:
    """Refuse an alias table that names nothing, or takes a word the package reserves.

    One home for the shape, carried by the type rather than spent at the
    artifact's door (the architecture lens of 2026-09-09 measured the
    rule enforced on one of the three models the value crosses).
    """
    for name, members in value.items():
        if not name.strip():
            raise ValueError("an alias needs a name; the [aliases] table holds an empty one")
        if name.strip().casefold() in EXPANDING_SELECTORS:
            raise ValueError(
                f"alias {name!r} takes a word that expands an entry rather than naming a "
                f"set of surfaces ({', '.join(EXPANDING_SELECTORS)}): an alias may shadow "
                "airframe and blades, which name a set, and not these. Choose another name"
            )
        if _GROUP_SPELLING.match(name.strip()):
            raise ValueError(
                f"alias {name!r} is spelled as a pproc group, which a boundary-citing cell "
                f"reads as [groups] entry {name.strip()[1:]!r}; choose a name that is not "
                "g<number>"
            )
        if not members:
            raise ValueError(
                f"alias {name!r} names no member; an alias stands for the boundary names "
                "or families listed after it"
            )
        for member in members:
            if not isinstance(member, str) or not member.strip():
                raise ValueError(
                    f"alias {name!r} lists {member!r}, and a member is a boundary name or a "
                    "family name (a string)"
                )
    return value


#: The boundary aliases a setup preset defines, the design decision of 2026-09-09:
#: a name to the boundary names or families it stands for. The type carries
#: the shape, so the setup artifact, the case and the run record hold one
#: rule between them rather than one validator at the artifact's door.
BoundaryAliases = Annotated[dict[str, list[str]], AfterValidator(_check_aliases)]


def resolve_alias(
    token: str, inventory: Sequence[str], aliases: Mapping[str, Sequence[str]] | None
) -> list[str] | None:
    """Resolve one cited name as an alias of the setup, or None when it is not one.

    The design decision of 2026-09-09: an alias is a name the setup's
    ``[aliases]`` table gives to a list of boundary names or families,
    and it is read wherever a boundary is cited, the exact spelling
    first and case folded second, as a family is. Each member resolves as
    a name does, an exact name of the inventory first and a family (the
    label without its trailing number) second; a member the inventory
    does not carry is ignored, which is how one setup serves a wing-body
    and a rotor. The names come back in member order, each once; an
    alias every member of which is absent resolves to an empty list, and
    the caller says what that means for its key.

    THE DESIGN OF 2026-09-10 ADDED ONE THING and it changes this
    function's contract: a member may be ANOTHER ALIAS, and the reader
    follows it to the end. A member the inventory carries is that
    boundary first, whatever else shares its spelling, so the addition
    cannot change what an existing file resolves to.

    Raises
    ------
    AliasCycleError
        If following the members returns to an alias already on the path,
        naming both sides. A member that names its OWN alias is not a
        ring: it falls back to the FAMILY reading, exactly as it did
        before aliases could nest, so `wing = ["wing"]` gives the wings
        of a mesh that has them and nothing at all of one whose wing was
        renamed.
    """
    if not aliases:
        return None
    key = _alias_key(token, aliases)
    if key is None:
        return None
    return _resolve_alias_key(key, inventory, aliases, seen=())


def _alias_key(token: str, aliases: Mapping[str, Sequence[str]]) -> str | None:
    """Return the alias one token names, the exact spelling first and case folded second."""
    if token in aliases:
        return token
    return next((name for name in aliases if name.casefold() == token.casefold()), None)


def _resolve_alias_key(
    key: str,
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    *,
    seen: tuple[str, ...],
) -> list[str]:
    """Resolve one alias to boundary names, following members that are aliases.

    The design of 2026-09-10 (FR-59): a member may be a mesh family, a
    boundary name, or ANOTHER ALIAS, resolved to the end. A member that
    names an alias already on the path closes a ring, and a ring is
    refused naming BOTH SIDES rather than recursed into, because a reader
    holding one of the two names has to open the file to find the other.
    """
    names: list[str] = []
    path = (*seen, key)
    for member in aliases[key]:
        token = str(member)
        # THE INVENTORY IS ASKED FIRST, and it has to be. A member that
        # names a boundary the mesh carries is that boundary, whatever
        # else shares its spelling; only a member the mesh does not carry
        # is looked up as an alias. Without this order an alias `wing`
        # whose member is the family `Wing` resolves to ITSELF, because
        # an alias is matched case folded, and the reader reports a cycle
        # over a file that has none (measured 2026-09-10 against
        # test_the_refusal_cites_the_word_the_artifact_writes_not_the_alias_members).
        if token in inventory:
            if token not in names:
                names.append(token)
            continue
        nested = _alias_key(token, aliases)
        # A MEMBER THAT NAMES ITS OWN ALIAS IS NOT A RING, it is the
        # 0.14.0 case of an alias resolving to nothing: `wing = ["Wing"]`
        # over a mesh whose wing was renamed matches the alias itself when
        # names are folded, and that file has no ring in it. It falls
        # through to the FAMILY reading, which finds the wings of a mesh
        # that has them and nothing of one whose wing was renamed, which
        # is what it did before aliases could nest. Saying "it resolves to
        # nothing" was the RENAMED case mistaken for the rule, and a
        # technical-writing pass caught it in three places at once
        # (2026-09-10). A ring needs two distinct aliases, and that is what is
        # refused below.
        if nested is not None and nested == key:
            nested = None
        if nested is not None and nested in path:
            raise AliasCycleError(
                f"the alias {key!r} resolves through {token!r}, which resolves back to "
                f"{nested!r}: {' -> '.join(repr(name) for name in (*path, nested))}. An "
                "alias may name another alias, and the reader follows to the end, so a "
                "ring has no end; break it in the reference"
            )
        resolved = (
            _resolve_alias_key(nested, inventory, aliases, seen=path)
            if nested is not None
            else names_of(token, inventory)
        )
        for name in resolved:
            if name not in names:
                names.append(name)
    return names


def alias_members_missing(
    token: str,
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]] | None,
) -> list[tuple[str, str]]:
    """Return the members of one cited alias that NO boundary answers.

    THE OTHER HALF OF THE SENTENCE :func:`resolve_alias` implements. That
    reader IGNORES a member the opened mesh does not carry, which is what
    lets one reference serve a wing-body and an isolated rotor
    (PFS-2035.01). Whether the silence is right is a property of the run
    rather than of the file, so a run may ask to hear about it instead
    (PFS-2035.13), and this function is what it hears: the members, in
    the order the table wrote them, that resolve to nothing at all.

    Each pair is ``(the alias that DECLARES the member, the member)``, and
    the first half is the point: on a nested alias the declaring one is not
    the one the entry cited, and it is the table row the user has to edit.
    A message naming only the cited word sent a reader to the wrong line
    (the interface lens of 2026-09-10).

    A token that names no alias, or an alias every member of which
    resolves, gives an empty list. A RING RAISES, exactly as
    :func:`resolve_alias` does and with the same message: a reporter that
    answered confidently for a file the resolver refuses is a second
    reading of one file (the QA lens of 2026-09-10, measured).
    """
    if not aliases:
        return []
    key = _alias_key(token, aliases)
    if key is None:
        return []
    return _absent_members(key, inventory, aliases, seen=())


def _absent_members(
    key: str,
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    *,
    seen: tuple[str, ...],
) -> list[tuple[str, str]]:
    """Walk one alias the way the resolver does, collecting what answers nothing."""
    absent: list[tuple[str, str]] = []
    path = (*seen, key)
    for member in aliases[key]:
        token = str(member)
        # THE SAME FOUR READINGS IN THE SAME ORDER as `_resolve_alias_key`,
        # the ring included, deliberately: a reporter that resolves a
        # member differently from the resolver reports members that resolve
        # and misses ones that do not, which is worse than staying silent.
        if token in inventory:
            continue
        nested = _alias_key(token, aliases)
        if nested is not None and nested == key:
            nested = None
        if nested is not None and nested in path:
            raise AliasCycleError(
                f"the alias {key!r} resolves through {token!r}, which resolves back to "
                f"{nested!r}: {' -> '.join(repr(name) for name in (*path, nested))}. An "
                "alias may name another alias, and the reader follows to the end, so a "
                "ring has no end; break it in the reference"
            )
        if nested is not None:
            for pair in _absent_members(nested, inventory, aliases, seen=path):
                if pair not in absent:
                    absent.append(pair)
        elif not names_of(token, inventory) and (key, token) not in absent:
            absent.append((key, token))
    return absent


#: The one alias that means every family the geometry carries, in a `[groups]` entry
#: as in a `families` selector.
EVERY_FAMILY = "all"


def select_group_members(
    members: Sequence[int | str],
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[str]:
    """Resolve one ``[groups]`` entry's members against an inventory, in member order.

    The design decisions of 2026-09-09 (PFS-2005.02). An EMPTY group is every
    name of the inventory. Otherwise each member is, tried in this order,
    an exact name of the inventory; an ALIAS of the row's setup
    (:func:`resolve_alias`), so ``airframe`` and ``blades`` are whatever
    the setup says and nothing is hardcoded; or a FAMILY, the label
    without its trailing number, selecting every member of it the
    inventory carries (``Blade`` is ``Blade1`` to ``Blade6``). A member
    resolving to nothing is left out, which is how one artifact serves a
    wing-body and an isolated rotor; a POSITION is not a name and is left
    to the caller, which is the motion path that has an index to give it.
    The inventory is whatever the caller judges by: the boundary labels
    of the opened file on the script path, the surface rows of the loads
    table at products time.
    """
    if not members:
        return list(inventory)
    chosen: list[str] = []
    for member in members:
        if isinstance(member, int):
            continue
        token = str(member)
        names = [token] if token in inventory else resolve_alias(token, inventory, aliases)
        if names is None:
            names = names_of(token, inventory)
        if not names and token == EVERY_FAMILY:
            # THE WORD THE DEPRECATION TELLS AN EMPTY GROUP'S OWNER TO WRITE (0.24.0).
            # A group is ONE alias as a string, an empty list was every family, and
            # its replacement is `"all"`; it selected nothing, so following the
            # package's own advice cost the polar of the whole configuration. An
            # alias, a boundary or a family of that name is tried first and wins.
            names = list(inventory)
        elif names and token == EVERY_FAMILY:
            # AND WHEN ONE DOES WIN, IT IS SAID (release review of 0.24.0, API-B9): a
            # geometry with a surface or a family called `all` turns the word that
            # means every surface into that one surface, and a polar of one surface
            # under the configuration's group name is a number nobody asked for.
            warn(
                f'the group member "{EVERY_FAMILY}" selected {names}, a surface, family '
                "or alias of that name, and NOT every surface of the geometry. Rename "
                f'that surface, or name the group\'s members, if "{EVERY_FAMILY}" meant '
                "all of them.",
                PyflightstreamWarning,
                stacklevel=2,
            )
        chosen.extend(name for name in names if name not in chosen)
    return chosen


@dataclass(frozen=True)
class NameField:
    """How one flight-condition variable is written in a point name (0.21.0).

    ``code`` then the value times ``scale``, rounded, zero-padded to
    ``width`` characters; a signed field counts its sign in the width.

    ``magnitude`` writes the field WITHOUT its sign whatever sign the value
    carries. It lives here, beside ``signed``, because it is the same kind of
    fact about the same field, and a reader adding a variable reads this
    dataclass and the table below. Held in a second table keyed by the same
    keys, it had to be remembered at each call site and was remembered at one of
    three: the sweep name and the duplicate-identity guard were writing the sign
    the point name had just dropped (the architect lens, FIX-0220).
    """

    code: str
    scale: float
    width: int
    signed: bool
    magnitude: bool = False


#: THE POINT NAME'S CODE TABLE (SCOPE-0210 section 1),
#: keyed by the canonical FLIGHT_CONDITION key. Codes differ in LETTERS and never
#: only in case, because a Windows file name does not distinguish case.
POINT_NAME_FIELDS: dict[str, NameField] = {
    "MACH": NameField("M", 1000.0, 3, False),
    "TASmps": NameField("V", 10.0, 4, False),
    "REmi": NameField("RE", 100.0, 3, False),
    "ALTFT": NameField("ALT", 1.0, 5, False),
    "dISA": NameField("DT", 10.0, 4, True),
    "RHOkgm3": NameField("RHO", 10000.0, 5, False),
    "MUPas": NameField("MU", 1e9, 5, False),
    "ASMPS": NameField("A", 10.0, 4, False),
    "TK": NameField("T", 10.0, 4, False),
    "PPA": NameField("PS", 1.0, 6, False),
    "ALPHA": NameField("AL", 10.0, 4, True),
    "BETA": NameField("BE", 10.0, 4, True),
    "ADVANCE_RATIO": NameField("J", 100.0, 4, True),
    # A MAGNITUDE, AND THEREFORE UNSIGNED. The hand of a rotation is the
    # reference rotor's and never the point's, so a folder named `RPM-0473`
    # would be naming a property of the ROTOR in the identity of a POINT, and
    # two runs of one speed in opposite directions would get two names for one
    # operating point.
    #
    # THE SIGN IS NOT DECORATION, IT IS A DIGIT. Written signed, the `+` could
    # never be a `-` and it cost the fifth character: 10000 rev/min wrote
    # `RPM+10000`, EIGHT characters where every other name is seven, so the
    # fixed-width scheme broke silently on any rotor past 9999. Unsigned, the
    # same width reaches 99999 and every name is the same length.
    "RPM": NameField("RPM", 1.0, 5, False, magnitude=True),
    "roll_rate": NameField("P", 10.0, 4, True),
    "pitch_rate": NameField("Q", 10.0, 4, True),
    "yaw_rate": NameField("R", 10.0, 4, True),
}

#: The point axes, by the name a sweep point uses, and the FLIGHT_CONDITION key
#: each one is. THE THREE HISTORICAL AXES KEEP THEIR LOWER-CASE NAMES, which
#: every manifest, product table and point mapping ever written here carries;
#: the variables that became sweepable at 0.21.0 are named by their cell key,
#: so a reader of a row and a reader of a point read one vocabulary.
#:
#: THE ORDER IS THE NAME'S FALLBACK ORDER, used by a case with no cell: the
#: flow keys, then the angles, then the rotor and the rates, which is the order
#: the reference matrices declare them in.
POINT_AXIS_KEYS: dict[str, str] = {
    "MACH": "MACH",
    "TASmps": "TASmps",
    "REmi": "REmi",
    "ALTFT": "ALTFT",
    "dISA": "dISA",
    "RHOkgm3": "RHOkgm3",
    "MUPas": "MUPas",
    "ASMPS": "ASMPS",
    "TK": "TK",
    "PPA": "PPA",
    "alpha": "ALPHA",
    "beta": "BETA",
    "advance_ratio": "ADVANCE_RATIO",
    "RPM": "RPM",
    "roll_rate": "roll_rate",
    "pitch_rate": "pitch_rate",
    "yaw_rate": "yaw_rate",
}

#: What a swept field carries in place of its value in a name about a whole
#: sweep (a one-job script, a superfile): ``AL+sweep``.
SWEEP_NAME_VALUE = "+sweep"


def name_field(key: str, value: float) -> str:
    """Write one variable the way a point name carries it, for example ``M144`` or ``AL-020``.

    Raises
    ------
    CampaignConfigError
        If the key has no code, or an unsigned variable is negative.
    """
    field = POINT_NAME_FIELDS.get(key)
    if field is None:
        raise CampaignConfigError(
            f"{key!r} has no code in the point name, so a point declaring it cannot be "
            f"named; the codes are for {', '.join(POINT_NAME_FIELDS)}."
        )
    # A MAGNITUDE FIELD REFUSES A SIGN RATHER THAN ABSORBING ONE, and the
    # difference is a whole defect. Absorbing it is silent, and silence is what
    # this rule exists to end: a swept `RPM` over `600, -600` had its two points
    # named identically, so the user met a FILE NAME COLLISION instead of the
    # sentence that says where the hand belongs, on a row whose scalar form
    # refuses correctly (the qa lens, FIX-0220).
    #
    # It is checked HERE, in the one funnel every name goes through, because
    # three call sites write a field through this function -- the point name,
    # the sweep name and the guard that refuses two points sharing one name --
    # and a rule applied at one of them made those three disagree.
    if field.magnitude and float(value) < 0.0:
        raise CampaignConfigError(
            f"{key} is {value!r}, and a row's rotor speed is a MAGNITUDE: it says how "
            "fast, not which way. The hand of the rotation is the rotor's, declared "
            "once in the reference beside its axis and its origin. Write the speed "
            "positive and set 'rpm_sign' there; on a row that names no rotor block, "
            "write 'RPM_SIGN: -1' beside the speed."
        )
    number = round(float(value) * field.scale)
    if field.signed:
        return f"{field.code}{number:+0{field.width}d}"
    if number < 0:
        raise CampaignConfigError(
            f"{key} is {value!r}, and a point name writes {key} without a sign, so the "
            f"point name cannot carry a negative {key}. The flight condition itself can "
            "hold one; it is the name of the point that has no place for the sign."
        )
    return f"{field.code}{number:0{field.width}d}"


def _name_order(case: SimCase, point: Mapping[str, float]) -> list[str]:
    """Return the declared FLIGHT_CONDITION keys in row order, or a cell-less case's fallback."""
    order = list(case.condition_order)
    if not order:
        if case.mach is not None:
            order.append("MACH")
        order.extend(POINT_AXIS_KEYS[axis] for axis in POINT_AXIS_KEYS if axis in point)
    # A point axis the order does not state still names the point, at the end:
    # two points of one case must never share a name for want of a key.
    order.extend(
        POINT_AXIS_KEYS[axis]
        for axis in POINT_AXIS_KEYS
        if axis in point and POINT_AXIS_KEYS[axis] not in order
    )
    return order


def _as_a_number(case: SimCase, key: str, stated: object, where: str) -> float:
    """Return ``stated`` as a number, or raise the refusal this path promises.

    ONE conversion for all four places a declared variable's value can come
    from, so a fifth cannot be added past the refusal. The first writing wrapped
    the `variables` branch alone and left the other three raising a bare
    `ValueError` out of `float()` -- including `flight_condition`, which is where
    a MATRIX CELL's value lands and is the branch the requirement is about
    (measured by the closing round, 2026-09-16: a cell stating `MACH: fast` gave
    `could not convert string to float: 'fast'`).
    """
    try:
        return float(stated)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} in its flight condition and states "
            f"{stated!r} for it in {where}, which is not a number, so the point cannot "
            "be named."
        ) from None


def _name_value(case: SimCase, point: Mapping[str, float], key: str) -> float:
    for axis, axis_key in POINT_AXIS_KEYS.items():
        if key == axis_key and axis in point:
            return _as_a_number(case, key, point[axis], "this point")
    if key in case.flight_condition:
        return _as_a_number(case, key, case.flight_condition[key], "its FLIGHT_CONDITION")
    if key == "MACH" and case.mach is not None:
        return _as_a_number(case, key, case.mach, "its Mach number")
    if key in case.variables:
        return _as_a_number(case, key, case.variables[key], "its variables")
    raise CampaignConfigError(
        f"case {case.sim_id!r} declares {key} in its flight condition and this point carries "
        f"no value for it, so the point cannot be named."
    )


def point_name(case: SimCase, point: Mapping[str, float]) -> str:
    """Return the name of one point of a case: its identity, folder and file stem (0.21.0).

    Every variable the row's FLIGHT_CONDITION declares, in the order the row
    declares them, written as :data:`POINT_NAME_FIELDS` says, with the point's
    own value for a swept one: ``M144RE438AL+000BE+000J+080``. A case with no
    cell (authored in Python) is named by its Mach number when it has one and
    then by the axes of its point. It ends the ``run_id``, names the datapoint
    folder ``DP-<name>`` and is the stem of every file ``P<POL>-<name>``.

    Raises
    ------
    CampaignConfigError
        If a declared variable has no value on this point or no code.
    """
    return "".join(
        name_field(key, _name_value(case, point, key)) for key in _name_order(case, point)
    )


def sweep_name(case: SimCase) -> str:
    """Return the name of a case's whole sweep, each swept field written ``<code>+sweep``."""
    swept = {POINT_AXIS_KEYS[axis] for axis in _swept_axes(case.sweep)}
    first = next(case.sweep.points(), {})
    parts = []
    for key in _name_order(case, first):
        if key in swept:
            parts.append(f"{POINT_NAME_FIELDS[key].code}{SWEEP_NAME_VALUE}")
        else:
            parts.append(name_field(key, _name_value(case, first, key)))
    return "".join(parts)


def _swept_axes(sweep: SweepAxis) -> tuple[str, ...]:
    return ("alpha", "beta") if sweep.type == "alpha_beta" else (sweep.type,)


def point_tag(point: dict[str, float]) -> str:
    """Return the 0.20.x file-name tag of one sweep point.

    The tag encodes the point coordinates in a fixed axis order with
    signed fixed-width values, for example ``a+02.0_b+00.0``. Until 0.20.x it
    named the generated script and ended the ``run_id``; SINCE 0.21.0 NEITHER
    IS TRUE, and :func:`point_name` is both. This is kept for the two readers
    of a recorded workspace: `pyfs-matrix rename`, which maps a 0.20 record to
    its new name with it, and anything reading a manifest written before the
    rename.

    Parameters
    ----------
    point : dict of str to float
        Point coordinates as produced by :meth:`SweepAxis.points`.
    """
    parts = [f"{prefix}{point[axis]:+05.1f}" for axis, prefix in _TAG_PREFIXES if axis in point]
    if not parts:
        raise CampaignConfigError(f"point {point!r} has no known axis (alpha, beta, advance_ratio)")
    return "_".join(parts)


def geometric_sweep_values(variables: Mapping[str, object]) -> list[str]:
    """Return the angles a case's geometric sweep variable declares.

    The variable is :data:`ROTATION_SWEEP_KEY`, and its values are
    comma separated because a case variable holds one scalar or one
    string and never a list. Values are returned as written, in degrees,
    without being converted: this function counts how many angles were
    asked for, and whether each is a number is the recipe's or the
    workflow's refusal to make, naming the key the user typed.

    The key is matched CASE-INSENSITIVELY. Its spelling is settled
    elsewhere, and a limit that fires only for one casing is a limit a
    user gets past by shouting.

    EVERY matching key is read and their values are POOLED, rather than
    the first match winning. Two keys differing only in case are two
    distinct entries in a variables mapping, so a first-match rule let a
    one-angle ``angle_sweep_deg`` stand in front of a three-angle
    ``ANGLE_SWEEP_DEG`` and carry the whole declaration past the limit.
    Pooling closes that and is right on its own terms besides: two keys
    naming one rotation is an ambiguity, and counting both is what makes
    the ambiguous case meet a refusal rather than a coin toss.

    Parameters
    ----------
    variables : mapping of str to object
        A case's free variables, as :attr:`SimCase.variables` holds them
        or as the run matrix reader parsed its ``VAR_NAMES_VALUES`` cell.

    Returns
    -------
    list of str
        The declared angles in degrees, in the order written, pooled
        across every key that spells :data:`ROTATION_SWEEP_KEY` in any
        casing. Empty when no such key is present or all of them hold
        nothing but separators, which are the same fact here: no
        geometric sweep was asked for.

    Examples
    --------
    >>> geometric_sweep_values({"angle_sweep_deg": "0.0,5.0,10.0"})
    ['0.0', '5.0', '10.0']
    >>> geometric_sweep_values({"angle_sweep_deg": "5.0", "ANGLE_SWEEP_DEG": "7.5"})
    ['5.0', '7.5']
    >>> geometric_sweep_values({"CONFIG": "NSX"})
    []
    """
    angles: list[str] = []
    for name, value in variables.items():
        if name.strip().lower() == ROTATION_SWEEP_KEY:
            angles += [token.strip() for token in str(value).split(",") if token.strip()]
    return angles


def multiplied_sweep(sweep: SweepAxis, variables: Mapping[str, object]) -> list[str]:
    """Return the geometric angles that would MULTIPLY with the sweep.

    This is the single owner of the one-sweep-per-case limit, called from
    both places a case can be declared: the ``campaign.toml`` model
    (:class:`SimCase`) and the run matrix reader
    (:func:`pyflightstream.cases.matrix.read_matrix`). Two owners would
    be two rules, and the drift would be discovered by a user whose
    hand-written campaign ran what the matrix refuses.

    THE DECISION IT ENFORCES (design note DD-28): a geometric sweep does
    NOT multiply with
    the aerodynamic one. A case carries one aerodynamic sweep and at most
    one FIXED geometric offset (:data:`ROTATION_OFFSET_KEY`); a study OF
    the geometry is one case per geometry, each with its own ``sim_id``.
    Multiplication was rejected on identity rather than on taste. A run
    is identified by :func:`point_tag`, whose axes are
    :data:`_TAG_PREFIXES`, and none of the three is geometric, so the
    three angles of a rotation sweep crossed with an eleven point alpha
    sweep are thirty three runs wearing eleven identities: each group of
    three renders one tag, one ``run_id`` and one set of output file
    names. That is exactly the collision
    :meth:`SweepAxis._points_have_distinct_tags` already refuses within
    one axis, and it is not made safe by arriving from a second axis. The
    same collapse reaches the evidence:
    :class:`pyflightstream.qa.cost.PointKey` keys a cost row by
    ``sim_id`` and the recorded point, so three geometries under one
    ``sim_id`` average into one cell and the geometry that got slower
    cannot be seen.

    Parameters
    ----------
    sweep : SweepAxis
        The case's aerodynamic sweep.
    variables : mapping of str to object
        The case's free variables.

    Returns
    -------
    list of str
        The geometric angles in degrees when BOTH sweeps carry two or
        more values, which is the multiplying shape. Empty otherwise, so
        a fixed offset beside a sweep, a rotation sweep on a single point
        case, and a case with no geometric variable at all all pass: each
        of those is one sweep, and one sweep is what a case may have.

    Examples
    --------
    >>> sweep = SweepAxis(type="alpha", values=[0.0, 2.0, 4.0])
    >>> multiplied_sweep(sweep, {"angle_sweep_deg": "0.0,5.0"})
    ['0.0', '5.0']
    >>> multiplied_sweep(sweep, {"angle_deg": "5.0"})
    []
    """
    angles = geometric_sweep_values(variables)
    if len(angles) < 2 or len(sweep.values) < 2:
        return []
    return angles


class ReferenceData(BaseModel):
    """Reference quantities for coefficient normalization.

    Attributes
    ----------
    area : float
        Reference area S_ref in simulation length units squared.
    length : float
        Reference length L_ref in simulation length units.
    velocity : float, optional
        Reference velocity in m/s; None lets the recipe default it to
        the free-stream velocity (steady runs) or a characteristic
        velocity such as the rotor tip speed (SRC-003 p.201).
    rotor_diameter : float, optional
        Rotor diameter D in simulation length units, carried from
        the reference artifact's ``rotor_diameter_m``. It is the
        length an advance ratio is a ratio AGAINST: a row stating
        ``ADVANCE_RATIO`` resolves its rotor speed as
        ``n = V / (J D)``, so without this the ratio names no speed.
        None for a configuration with no rotor.
    """

    # PYFS-016. A reference area or length of zero divides every
    # coefficient by zero; a negative one flips the sign of every
    # coefficient in the report while the run looks healthy; an
    # infinite one drives them all to zero. All three were measured
    # accepted at HEAD. These are DIVISORS of the published numbers,
    # which is why the bound is a refusal rather than a warning.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    area: float = Field(gt=0.0)
    length: float = Field(gt=0.0)
    velocity: float | None = Field(default=None, gt=0.0)
    rotor_diameter: float | None = Field(default=None, gt=0.0)
    #: The reference span, which the polar products scale the rolling and
    #: yawing moments to (PFS-2029.15); None keeps a case built without it.
    span_m: float | None = Field(default=None, gt=0.0)
    #: The moment reference point (x, y, z) in simulation length units,
    #: carried from the reference artifact's ``[moment_point]``. A builder
    #: creates a coordinate system named MRP there and makes it the
    #: analysis loads frame, so moments are reported about it
    #: (PFS-2030.03.02). None for an authored case that states none, which
    #: leaves the solver's reference frame as the loads frame, as before.
    moment_point_m: tuple[float, float, float] | None = None
    #: The rotor position (x, y, z) in simulation length units, from
    #: the reference artifact's ``[rotor.position]``. The two unsteady
    #: run types create a coordinate system named ROTOR_MRP there, which is
    #: the frame the reference probe lines and rotor plots are defined in,
    #: and the rotor run turns about it. None when the reference declares
    #: no rotor.
    rotor_position_m: tuple[float, float, float] | None = None
    #: WHICH MODEL AXIS EACH BODY RATE TURNS ABOUT (0.21.0), from the
    #: reference artifact's ``[body_axes]`` table: ``roll``, ``pitch`` and
    #: ``yaw`` to ``X``, ``Y`` or ``Z``. A mesh is built in whatever
    #: orientation its author chose, and a rotating free stream has to be
    #: given an AXIS of a frame, so the row cannot state one without the
    #: reference saying which axis is which. Empty for a reference that
    #: declares none, and a row stating a rate against such a reference is
    #: refused by name rather than guessed for.
    body_axes: dict[str, str] = Field(default_factory=dict)

    @field_validator("body_axes")
    @classmethod
    def _axes_are_three_named_axes(cls, value: dict[str, str]) -> dict[str, str]:
        """Refuse a table that names something other than one axis per rate."""
        axes = {key.strip().lower(): str(item).strip().upper() for key, item in value.items()}
        unknown = sorted(set(axes) - {"roll", "pitch", "yaw"})
        if unknown:
            raise ValueError(
                f"body_axes names {', '.join(unknown)}, and a body rate is one of roll, "
                "pitch or yaw. Write one axis for each rate the model can be given."
            )
        wrong = sorted(key for key, item in axes.items() if item not in {"X", "Y", "Z"})
        if wrong:
            raise ValueError(
                f"body_axes gives {', '.join(wrong)} an axis that is not X, Y or Z. An "
                "axis of a coordinate system is one of those three."
            )
        if len(set(axes.values())) != len(axes):
            raise ValueError(
                f"body_axes writes one axis twice ({axes}), and two body rates cannot turn "
                "about the same axis of one frame."
            )
        return axes


def _resolve_settings_toggle(value: object) -> object:
    """Resolve a settings toggle in either vocabulary, before validation.

    Runs ahead of pydantic's bool parsing, and resolves every value
    itself rather than only strings, so the settings field and the
    helper keyword it mirrors accept exactly the same thing: True and
    False, and the solver's own ENABLE and DISABLE. Pydantic's lax
    coercions (``"yes"``, ``"on"``, ``1``) are deliberately not
    accepted here, because a settings file that says ``1`` for a flag
    the solver writes as a word is more likely a mistake than an
    intent. The refusal is a ValueError, which pydantic reports as a
    ValidationError naming the field, so the message survives.
    """
    if value is None:
        return value
    return resolve_toggle(value, context="a solver settings toggle")


#: Settings toggle: a bool, or the solver's own ENABLE and DISABLE.
SolverToggle = Annotated[bool, BeforeValidator(_resolve_settings_toggle)]


class SolverSettings(BaseModel):
    """Solver runtime settings of one case.

    Field names match the keyword arguments of
    :func:`pyflightstream.script.helpers.solver_settings`, so recipes
    can forward them directly.

    Attributes
    ----------
    iterations : int
        Solver iteration limit.
    convergence : float
        Residual threshold declaring convergence (SRC-003 p.200).
    forced_iterations : bool, optional
        Run the full iteration count regardless of convergence. The
        solver's own words are accepted too (see below).
    boundary_layer : str, optional
        The boundary layer model: ``LAMINAR``, ``TRANSITIONAL``, or
        ``TURBULENT``.
    viscous_coupling : bool, optional
        Couple the boundary layer model to the potential solution.
        The solver's own words are accepted too (see below).
    max_threads : int, optional
        Parallel core count; a row's ``NCPUS`` column wins over it.
    timeout_s : float, optional
        Wall-clock limit for one point's solver process; enforced by
        the executor, not by FlightStream.
    walltime_margin_s : float, optional
        How much of a row's ``WALLTIME`` to leave for the exports, in
        seconds; twenty minutes when unstated. It emits nothing.
    solver_model : str, optional
        The flow model the solver is initialized with, ``INCOMPRESSIBLE``,
        ``SUBSONIC_PRANDTL_GLAUERT``, ``TRANSONIC_FIELD_PANEL``,
        ``TANGENT_CONE`` or ``MODIFIED_NEWTONIAN``; an argument of
        ``INITIALIZE_SOLVER``. None leaves the emitter's own default, which
        is ``INCOMPRESSIBLE``.
    wall_collision_avoidance : bool, optional
        The wall-collision avoidance argument of ``INITIALIZE_SOLVER``, the
        other one a preset states.
    convergence_iterations : int, optional
        Iterations the residual must hold under the threshold before
        the solver calls the run converged.
    minimum_cp : float, optional
        Floor applied to the pressure coefficient.
    farfield_layers : int, optional
        Farfield layer count.
    mesh_induced_wake_velocity : bool, optional
        Switches the solver's mesh-induced wake velocity. This toggle
        and the four below it are advanced settings, and the solver's
        own ENABLE and DISABLE are read as well as Python booleans.
    unsteady_pressure_and_kutta : bool, optional
        Switches the unsteady Bernoulli and Kutta terms of the unsteady
        solver.
    wake_on_wake_induction : bool, optional
        Switches the wake-on-wake induced velocity computation.
    additional_wake_relaxation : bool, optional
        Asks for one additional wake relaxation iteration.
    reynolds_averaged_drag : bool, optional
        Switches the Reynolds-averaged (flat plate) boundary layer
        calculations.
    solver_stabilization : float, optional
        Stabilization strength. A preset that gates it with a separate
        ENABLE/DISABLE key resolves the pair before it arrives here:
        disabled means None, not zero.
    laminar_separation : bool, optional
        Switches laminar boundary layer separation.
    kutta_joukowski_lift : bool, optional
        Computes the inviscid lift by the Kutta-Joukowski theorem, from
        the bound circulation, instead of integrating the surface
        pressure.
    aeroelastic_rbf_type : str, optional
        The radial basis function of the aeroelastic mesh morphing.
    print_rotor_induced_velocities : bool, optional
        Prints the rotor-induced velocities to the log at every time
        step of an unsteady run.
    adaptive_field_grid_refinement : bool, optional
        Refines the field-source grid where the solution needs it; the
        manual marks it transonic only.
    rotor_induced_velocity_blending : float, optional
        Blending factor for wake stabilization, dimensionless, between
        0 and 1.
    wake_numerical_relaxation : float, optional
        Relaxation factor applied to the wake between iterations,
        dimensionless, between 0 and 1.
    wake_relaxation : bool, optional
        Relaxes the wake geometry between solver iterations.
    wake_decay_constant_per_m : float, optional
        Rate at which wake vorticity decays with distance, per metre.
    wake_streamwise_agglomeration : bool, optional
        Agglomerates wake filament edges along the streamwise direction,
        so the solver carries fewer wake elements.
    jet_wake_decay_normalized_length : float, optional
        Distance at which a jet wake decays to a tenth of its strength,
        in jet wake diameters.
    jet_wake_filaments_grid_induction : bool, optional
        Whether the jet wake filaments induce velocity on the mesh.
    adverse_gradient_boundary_layer : bool, optional
        Switches the adverse-pressure-gradient treatment of the
        boundary-layer model.
    vortex_ring_normalization : bool, optional
        Normalizes the vortex-ring strengths on the wake panels.
    wake_termination_revolutions : float, optional
        Wake termination stated in revolutions, negative counting
        backwards from the end of the run. Converted to time steps by
        the rotor builder, which is the only layer that knows how many
        steps a revolution is.
    wake_termination_steps : int, optional
        Wake termination stated in time steps, negative counting
        backwards from the end of the run, for a run type with a clock
        and no rotor.
    symmetry_loads : bool, optional
        Whether the reported loads are the meshed half's or sector's or
        the whole model's; a row's ``SYMMETRY_LOADS`` column wins over it.
    significant_digits : int, optional
        How many decimals the solver prints in every export.
    reference_velocity_m_per_s : float, optional
        The velocity the coefficients are normalised on, in m/s; unstated,
        the free-stream velocity.
    vorticity_drag_families : list of str, optional
        The families whose induced drag comes from vorticity integration,
        by family name.
    axial_separation_families : list of str, optional
        The families on the axial flow separation list, by family name.
    load_solver_initialization : bool, optional
        Whether ``OPEN`` loads the solver initialization a saved
        simulation carries; unstated, it does not.
    analysis_families : list of str, optional
        The families that enter the loads, by family name; every other
        boundary leaves the analysis.
    load_units : str, optional
        The unit the loads table prints its forces and moments in.
    inviscid_loads : bool, optional
        Reports the loads and moments without their viscous part.
    vorticity_lift_model : bool, optional
        Computes the lift from the vorticity field rather than from the
        integrated surface pressure.
    unsteady_viscous_coupling_iteration : int, optional
        The time step at which an unsteady run switches the viscous
        coupling on.

    Notes
    -----
    The toggles accept the solver's own vocabulary as well as Python
    booleans: ``viscous_coupling = 'DISABLE'`` in a settings file means
    False, the same as ``viscous_coupling = false``. A settings preset
    carried over from the solver speaks ENABLE and DISABLE, and a
    preset is often mixed (one flag in each vocabulary), so the model
    reads both and stores the bool
    (:func:`pyflightstream.script.toggles.resolve_toggle`). Any other
    string is refused by name.
    """

    # PYFS-016. Every bound below was measured ACCEPTED before it was
    # written: zero and negative iterations, a zero and a negative
    # timeout, a zero and a NaN convergence threshold, zero threads.
    # None of those describes a run that can happen, and the NaN
    # threshold is the one that does not even fail loudly: it compares
    # false against every residual, so the solver burns its whole
    # iteration budget and the run is recorded as having met a target
    # it never met.
    #
    # allow_inf_nan=False stops the NaN and infinity half; the
    # per-field bounds stop the zero and negative half. Both are
    # needed, because a numeric constraint does not reject NaN on its
    # own: every comparison against NaN is false, so ge and gt pass it.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    iterations: int = Field(default=500, ge=1)
    convergence: float = Field(default=1e-5, gt=0.0)
    forced_iterations: SolverToggle | None = None
    boundary_layer: str | None = None
    viscous_coupling: SolverToggle | None = None
    max_threads: int | None = Field(default=None, ge=1)
    timeout_s: float | None = Field(default=None, gt=0.0)
    #: FR-98: how much of a row's WALLTIME to leave for the exports, in
    #: seconds. Twenty minutes when a setup states none.
    #:
    #: IT IS THE SETUP'S AND NOT THE ROW'S, because how long the exports
    #: take is the same question on every platform and does not vary with
    #: the row, while a wall clock does. This model FORBIDS EXTRAS, so
    #: until the field existed a setup stating it was REFUSED by name and
    #: every run was locked to the default: a documented override nobody
    #: could exercise, which is a claim the tree did not do. Found by the
    #: independent Codex review of `main`, 2026-09-13 (GEO-047-C09).
    #:
    #: IT EMITS NOTHING, which is the one field of this block that does
    #: not, and the reason is stated rather than left as an exception: it
    #: is read by the wall-clock program the run stage writes beside the
    #: script, not by a solver command.
    walltime_margin_s: float | None = Field(default=None, gt=0.0)

    # --- the settings a preset carries and nothing used to read ------
    #
    # EVERY FIELD BELOW HAS AN EMITTER, and that is the rule this block
    # is held to rather than a coincidence of the first version. Ten of
    # them are keyword arguments of
    # `pyflightstream.script.helpers.solver_settings` and two are
    # arguments of `initialize_solver`; a setting a preset can state and
    # no helper can emit does NOT get a field here, because a field
    # whose value never reaches a script is a promise the file cannot
    # keep. Those stay declared as recorded-only in the preset resolver,
    # where the reason is written beside the key.
    #
    # They are all optional and all default to None, which is what keeps
    # every campaign written before this release emitting exactly the
    # lines it emitted before: a setting nobody states is a setting
    # nobody emits, and the solver's own default stands.
    solver_model: str | None = None
    wall_collision_avoidance: SolverToggle | None = None
    convergence_iterations: int | None = Field(default=None, ge=1)
    minimum_cp: float | None = None
    farfield_layers: int | None = Field(default=None, ge=1)
    mesh_induced_wake_velocity: SolverToggle | None = None
    unsteady_pressure_and_kutta: SolverToggle | None = None
    wake_on_wake_induction: SolverToggle | None = None
    additional_wake_relaxation: SolverToggle | None = None
    reynolds_averaged_drag: SolverToggle | None = None
    solver_stabilization: float | None = Field(default=None, ge=0.0)
    #: Optional advanced settings, using the existing solver helper keywords.
    #: None emits nothing; the command database validates each stated value
    #: against the run's build before emission.
    laminar_separation: SolverToggle | None = None
    kutta_joukowski_lift: SolverToggle | None = None
    aeroelastic_rbf_type: str | None = None
    print_rotor_induced_velocities: SolverToggle | None = None
    adaptive_field_grid_refinement: SolverToggle | None = None
    rotor_induced_velocity_blending: float | None = None
    wake_numerical_relaxation: float | None = None
    wake_relaxation: SolverToggle | None = None
    wake_decay_constant_per_m: float | None = None
    wake_streamwise_agglomeration: SolverToggle | None = None
    jet_wake_decay_normalized_length: float | None = None
    jet_wake_filaments_grid_induction: SolverToggle | None = None
    adverse_gradient_boundary_layer: SolverToggle | None = None
    vortex_ring_normalization: SolverToggle | None = None
    #: Wake termination stated in REVOLUTIONS, which is the unit a rotor
    #: preset writes it in, and negative counting backwards from the end
    #: of the run. The emitter takes time STEPS, and the conversion needs
    #: the steps per revolution, which only the case's own clock knows;
    #: it is therefore done by the rotor builder and never here.
    wake_termination_revolutions: float | None = None
    #: Wake termination stated in time STEPS, the emitter's own unit, for a
    #: run type that has a clock and no rotor (PFS-2030.03.04): a
    #: revolution has no length there, so the revolutions key above is
    #: refused on it and this one is the way to say it. Negative counts
    #: backwards from the end of the run, as the solver reads it.
    wake_termination_steps: int | None = None
    #: The four settings the reference scripts state and 0.10.1 did not
    #: (FR-54, PFS-2030.03.*). Each is None unless a preset states it, so a
    #: preset that says nothing emits nothing and every earlier golden holds.
    #: symmetry_loads reaches SET_ANALYSIS_SYMMETRY_LOADS AS STATED, the reference
    #: decision of 2026-09-02 (PFS-2028.05); an absent key stays silent.
    symmetry_loads: SolverToggle | None = None
    #: SET_SIGNIFICANT_DIGITS: how many decimals the solver prints in every
    #: export. The reference scripts state 7; the solver's own default prints 4.
    significant_digits: int | None = Field(default=None, ge=1)
    #: SOLVER_SET_REF_VELOCITY in m/s. None means the builders state the
    #: freestream velocity, which is what the coefficients are normalised
    #: on unless a preset says otherwise (PFS-2030.03.01).
    reference_velocity_m_per_s: float | None = Field(default=None, gt=0.0)
    #: SET_VORTICITY_DRAG_BOUNDARIES written as FAMILY NAMES; the builder
    #: resolves them through the opened geometry's inventory and leaves out
    #: the families the geometry does not carry, as the reference driver did
    #: (PFS-2030.03.03). An empty result is refused.
    vorticity_drag_families: list[str] | None = None
    #: SET_AXIAL_SEPARATION_BOUNDARIES written as FAMILY NAMES, resolved by the
    #: same rule as :attr:`vorticity_drag_families` and through the same
    #: function.
    #:
    #: IT WAS REACHABLE ONLY AS A HELPER KEYWORD NOBODY PASSED. `solver_settings`
    #: has taken `axial_separation_boundaries` since the helper was written and
    #: the campaign path never stated it, so no preset could ask for it: the
    #: API-only shape this release exists to catch, one level below the products.
    #:
    #: THE BUILD GUARD DECIDES WHETHER IT MAY RUN. The command is documented to
    #: 26.100 and no further, and RPT-018 measured it reported deprecated and
    #: then REFUSED by the 26.101 and 26.121 solvers. A row naming this key on a
    #: later build is refused where every unavailable command is refused, naming
    #: the build -- which is better than emitting a line the solver rejects
    #: mid-run, after the seat is spent.
    axial_separation_families: list[str] | None = None
    #: The LOAD_SOLVER_INITIALIZATION argument of OPEN. None means DISABLE,
    #: which is what the reference scripts wrote on every open: a saved simulation
    #: may carry an initialised solver, and loading it would start the run
    #: from a state the row never declared (PFS-2030.03.01).
    load_solver_initialization: SolverToggle | None = None
    #: THE SELECTIONS OF THE LOADS ANALYSIS (G09 of 0.27.0), analysis-phase
    #: commands the builders emit after ``START_SOLVER`` and before the exports,
    #: on a STEADY row only: set after the solve starts, a march's per-step
    #: exports would not see them (the shape RPT-064 measured for the loads
    #: frame), so a row of an unsteady run type stating one is refused. None
    #: emits nothing.
    #:
    #: SET_SOLVER_ANALYSIS_BOUNDARIES written as FAMILY NAMES, resolved like
    #: :attr:`vorticity_drag_families`: the boundaries that enter the loads, every
    #: other one leaving the analysis (SRC-003 p.351). A family the geometry does
    #: not carry is left out, and a list that resolves to none is refused.
    analysis_families: list[str] | None = None
    #: SET_LOADS_AND_MOMENTS_UNITS: the unit the loads table prints, one of the
    #: tokens the command takes on the row's build. The polar and every product
    #: read coefficients, so a point exported in another unit writes no product.
    load_units: str | None = None
    #: SET_INVISCID_LOADS: the loads and moments without their viscous part.
    inviscid_loads: SolverToggle | None = None
    #: SET_VORTICITY_LIFT_MODEL (G14 of 0.27.0): lift from the vorticity field
    #: rather than from the integrated surface pressure, stated before the
    #: solver is initialised on every run type. None emits nothing. The command
    #: database decides the builds: 26.124 answers the name as an unrecognized
    #: command (RPT-068), so a row on it is refused at plan.
    vorticity_lift_model: SolverToggle | None = None
    #: SET_UNSTEADY_VISCOUS_COUPLING_ITERATION (G14 of 0.27.0): the time step at
    #: which an unsteady run switches the viscous coupling on, stated before the
    #: solver is initialised. The unsteady run types only; documented by the
    #: 25.000, 25.100 and 26.000 editions alone, so the database refuses it on
    #: every later build, naming the build.
    unsteady_viscous_coupling_iteration: int | None = Field(default=None, ge=1)

    @field_validator("load_units")
    @classmethod
    def _a_unit_the_command_takes(cls, value: str | None) -> str | None:
        # Read from the command database, as the VTK variables are, so the list
        # a refusal prints is the one the emitter would enforce.
        if value is None:
            return None
        entry = CommandRegistry.load().commands["SET_LOADS_AND_MOMENTS_UNITS"]
        allowed = [str(token) for token in entry.args[0].values or ()]
        for token in allowed:
            if token.upper() == str(value).strip().upper():
                return token
        raise ValueError(
            f"load_units = {value!r} is not one of {', '.join(allowed)} "
            f"(SET_LOADS_AND_MOMENTS_UNITS, {entry.citation})"
        )


#: The solver command each :class:`SolverSettings` field reaches, for the
#: generated input glossary ``INPUTS.md`` (G08 of 0.27.0), which reads the
#: builds a setting is accepted on off the command's own evidence. A field
#: absent here reaches no command: ``timeout_s`` is the executor's and
#: ``walltime_margin_s`` the wall-clock program's. Written out rather than
#: matched by name against the helper's flags, because two fields share a
#: helper keyword's name and reach another command: ``solver_model`` and
#: ``wall_collision_avoidance`` are arguments of ``INITIALIZE_SOLVER``.
SOLVER_SETTING_COMMANDS: dict[str, str] = {
    "iterations": "SOLVER_SET_ITERATIONS",
    "convergence": "SOLVER_SET_CONVERGENCE",
    "forced_iterations": "SOLVER_SET_FORCED_ITERATIONS",
    "boundary_layer": "SET_BOUNDARY_LAYER_TYPE",
    "viscous_coupling": "SET_SOLVER_VISCOUS_COUPLING",
    "max_threads": "SET_MAX_PARALLEL_THREADS",
    "solver_model": "INITIALIZE_SOLVER",
    "wall_collision_avoidance": "INITIALIZE_SOLVER",
    "convergence_iterations": "SET_SOLVER_CONVERGENCE_ITERATIONS",
    "minimum_cp": "SOLVER_MINIMUM_CP",
    "farfield_layers": "SOLVER_SET_FARFIELD_LAYERS",
    "mesh_induced_wake_velocity": "SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY",
    "unsteady_pressure_and_kutta": "SOLVER_UNSTEADY_PRESSURE_AND_KUTTA",
    "wake_on_wake_induction": "SET_WAKE_ON_WAKE_INDUCTION",
    "additional_wake_relaxation": "ADDITIONAL_WAKE_RELAXATION_ITERATION",
    "reynolds_averaged_drag": "REYNOLDS_AVERAGED_DRAG_FORCES",
    "solver_stabilization": "SOLVER_STABILIZATION",
    "laminar_separation": "LAMINAR_SEPARATION",
    "kutta_joukowski_lift": "KUTTA_JOUKOWSKI_LIFT_FORCES",
    "aeroelastic_rbf_type": "AEROELASTIC_RBF_TYPE",
    "print_rotor_induced_velocities": "PRINT_ROTOR_INDUCED_VELOCITIES",
    "adaptive_field_grid_refinement": "SET_ADAPTIVE_FIELD_GRID_REFINEMENT",
    "rotor_induced_velocity_blending": "ROTOR_INDUCED_VELOCITY_BLENDING",
    "wake_numerical_relaxation": "SET_WAKE_NUMERICAL_RELAXATION",
    "wake_relaxation": "SET_WAKE_RELAXATION",
    "wake_decay_constant_per_m": "SET_WAKE_DECAY_CONSTANT",
    "wake_streamwise_agglomeration": "SET_WAKE_STREAMWISE_AGGLOMERATION",
    "jet_wake_decay_normalized_length": "SET_JET_WAKE_DECAY_NORMALIZED_LENGTH",
    "jet_wake_filaments_grid_induction": "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION",
    "adverse_gradient_boundary_layer": "SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER",
    "vortex_ring_normalization": "SOLVER_VORTEX_RING_NORMALIZATION",
    "wake_termination_revolutions": "SET_WAKE_TERMINATION_TIME_STEPS",
    "wake_termination_steps": "SET_WAKE_TERMINATION_TIME_STEPS",
    "symmetry_loads": "SET_ANALYSIS_SYMMETRY_LOADS",
    "significant_digits": "SET_SIGNIFICANT_DIGITS",
    "reference_velocity_m_per_s": "SOLVER_SET_REF_VELOCITY",
    "vorticity_drag_families": "SET_VORTICITY_DRAG_BOUNDARIES",
    "axial_separation_families": "SET_AXIAL_SEPARATION_BOUNDARIES",
    "load_solver_initialization": "OPEN",
    "analysis_families": "SET_SOLVER_ANALYSIS_BOUNDARIES",
    "load_units": "SET_LOADS_AND_MOMENTS_UNITS",
    "inviscid_loads": "SET_INVISCID_LOADS",
    "vorticity_lift_model": "SET_VORTICITY_LIFT_MODEL",
    "unsteady_viscous_coupling_iteration": "SET_UNSTEADY_VISCOUS_COUPLING_ITERATION",
}


class FluidState(BaseModel):
    """The resolved air state a case runs at (PFS-2027.05, PFS-2025.02.05).

    Every field carries its unit in its name. It is the OUTPUT of
    resolving a flight condition, and it rides on the case so that a
    builder can emit it: the resolver lives in the workspace layer,
    which a builder cannot import, so the value travels rather than the
    computation.

    ``source`` records WHICH branch produced the density, and it is not
    decoration. A density solved to meet a Reynolds number is not a
    point in any atmosphere, deliberately, and this field is what stops
    a later reader treating it as an altitude and "fixing" it into one.

    THIS IS THE RESOLVED STATE WITHOUT ITS INPUTS, and the distinction
    matters for one claim. PFS-2027.05 says a reader can RECOMPUTE the
    resolution rather than trust it; that is true of
    ``ResolvedMatrix.conditions``, which carries the condition as
    written, the altitude and the ISA deviation, and it is NOT true of
    this object, which carries none of the three. A release review found
    the recompute claim attached to the object that cannot satisfy it.
    Concretely: a ``FluidState`` cannot tell sea level at ISA+15 from an
    altitude that happens to give the same temperature. Read the
    resolved condition when the inputs matter; read this when the state
    does.
    """

    model_config = ConfigDict(extra="forbid")

    velocity_m_per_s: float
    density_kg_m3: float
    pressure_pa: float
    temperature_k: float
    viscosity_pa_s: float
    sonic_velocity_m_per_s: float
    #: The ratio of specific heats, dimensionless. Carried BESIDE the
    #: sonic velocity rather than instead of it, because the solver
    #: editions state the same physical fact two ways: the three
    #: pre-26.100 builds take a sonic velocity and the later ones take
    #: this ratio. A case that travels between builds needs both.
    #:
    #: The default is the FLOOR CONSTANT and not a literal 1.4. It read
    #: ``= 1.4`` until a release review pointed out that
    #: :class:`~pyflightstream.workspace.flight_condition.ResolvedCondition`
    #: carries a comment forbidding exactly that, in the same words for
    #: the same reason: a second literal lets the two drift the moment
    #: the floor constant moves, and the two builds would then solve
    #: different gases from one case. The resolver always supplies this
    #: value, so the default is reached only by an AUTHORED campaign,
    #: which is precisely the path with no resolver to keep it honest.
    heat_capacity_ratio: float = ISA.heat_capacity_ratio
    #: WHICH branch produced the density: ``"atmosphere"`` or
    #: ``"solved-from-reynolds"``. Required, with no default, and that
    #: is deliberate. It defaulted to ``"atmosphere"`` until a release
    #: review observed that a provenance marker defaulting to one of its
    #: two real values makes an unset state ASSERT a branch rather than
    #: record that nothing established one, on the one field whose whole
    #: job is to stop an unearned claim about provenance.
    source: str
    #: The length a stated Reynolds number was measured against, in
    #: metres. None when no Reynolds number was stated.
    reference_length_m: float | None = None


class PointState(BaseModel):
    """The flow state ONE point of a swept flight condition resolved to (0.21.0).

    A row that sweeps a flow variable -- `MACH:sweep`, `REmi:sweep`, an
    altitude -- states a DIFFERENT condition at every point, and the condition
    is resolved where the reference length lives, one layer above this one. So
    each point's resolved state travels here, keyed by the point, and
    :func:`case_at_point` puts it on the case the builder is handed. A row that
    sweeps an angle or a ratio resolves once and carries none of these.

    Attributes
    ----------
    mach, velocity, reynolds : float or None
        The three the case has fields for, at this point.
    fluid : FluidState or None
        The whole resolved state, which is what a builder emits.
    flight_condition : dict
        The condition as stated for this point: the row's cell with the swept
        key at this point's value.
    flight_condition_defaults : dict
        The pins the setup supplied at this point.
    flight_condition_defaults_from : str
        Where those pins came from, in words a reader can act on.
    """

    model_config = ConfigDict(extra="forbid")

    mach: float | None = None
    velocity: float | None = None
    reynolds: float | None = None
    fluid: FluidState | None = None
    flight_condition: dict[str, float] = Field(default_factory=dict)
    flight_condition_defaults: dict[str, float] = Field(default_factory=dict)
    flight_condition_defaults_from: str = ""


def point_state_key(point: Mapping[str, float]) -> str:
    """Return the key one point's resolved state is filed under.

    The point itself, written to ten significant figures per axis and sorted,
    so the same point read from a matrix, a plan or a record finds its state.
    """
    return "|".join(f"{axis}={float(value):.10g}" for axis, value in sorted(point.items()))


def case_at_point(case: SimCase, point: Mapping[str, float], **update: object) -> SimCase:
    """Return the case AT one point of its sweep, resolved state included.

    Every point of a run passes through here: the point rides on the case, and
    when the row swept a flow variable the state that point resolved to
    replaces the row's. Without it a MACH sweep would emit the first point's
    Mach number on every point of the row, which is the defect that makes the
    feature a lie rather than a limitation.
    """
    fields: dict[str, object] = {"point": dict(point), **update}
    state = case.point_states.get(point_state_key(point))
    if state is not None:
        for name in ("mach", "velocity", "reynolds", "fluid"):
            fields[name] = getattr(state, name)
        if state.flight_condition:
            fields["flight_condition"] = dict(state.flight_condition)
        fields["flight_condition_defaults"] = dict(state.flight_condition_defaults)
        fields["flight_condition_defaults_from"] = state.flight_condition_defaults_from
    return case.model_copy(update=fields)


#: The word a mesh operation's ``surface`` takes for every surface of the file.
EVERY_SURFACE = "all"

#: The keys each mesh operation of an import states besides ``op`` and
#: ``surface`` (G03), and the only ones it may state.
_MESH_OPERATION_KEYS: Mapping[str, tuple[str, ...]] = {
    "scale": ("factors",),
    "rename": ("to",),
    "mirror": ("plane",),
    "translate": ("vector",),
    "rotate": ("axis", "angle_deg"),
}


class MeshOperation(BaseModel):
    """One mesh operation applied right after a raw mesh is imported (G03).

    Declared in the geometry's sidecar, beside the unit, as one
    ``[[import.operations]]`` table each, and applied in the order written,
    in the reference frame:

    * ``scale``: ``factors = [fx, fy, fz]``, each greater than zero;
    * ``rename``: ``surface`` and ``to``, the new name;
    * ``mirror``: ``surface`` and ``plane`` (``YZ``, ``XZ`` or ``XY``); the
      mirrored copy joins its source, so the surface count is unchanged;
    * ``translate``: ``vector = [x, y, z]``, in the ``[import]`` unit;
    * ``rotate``: ``axis`` (``X``, ``Y`` or ``Z``) and ``angle_deg``.

    ``surface`` names the surface acted on by the name the file gives it,
    or by a name an earlier rename gave; never by position. It is
    :data:`EVERY_SURFACE` by default, which ``rename`` and ``mirror`` do not
    take: each acts on one named surface.

    Attributes
    ----------
    op : {'scale', 'rename', 'mirror', 'translate', 'rotate'}
        Which operation, and so which of the keys below it states.
    surface : str
        The surface acted on, by the file's name or an earlier rename's;
        ``"all"`` for every surface, which a rename and a mirror do not take.
    factors : tuple of three floats, optional
        A scale's factor along each axis, each greater than zero.
    vector : tuple of three floats, optional
        A translation's vector, in the ``[import]`` unit.
    axis : {'X', 'Y', 'Z'}, optional
        The axis a rotation turns about.
    angle_deg : float, optional
        The angle of a rotation, in degrees.
    plane : {'YZ', 'XZ', 'XY'}, optional
        The plane a mirror reflects in; the copy joins its source.
    to : str, optional
        A rename's new name, one word.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["scale", "rename", "mirror", "translate", "rotate"]
    surface: str = EVERY_SURFACE
    factors: tuple[float, float, float] | None = None
    vector: tuple[float, float, float] | None = None
    axis: Literal["X", "Y", "Z"] | None = None
    angle_deg: float | None = None
    plane: Literal["YZ", "XZ", "XY"] | None = None
    to: str | None = None

    @field_validator("surface", "to", mode="before")
    @classmethod
    def _stripped(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _its_own_keys_and_sound_values(self) -> MeshOperation:
        own = _MESH_OPERATION_KEYS[self.op]
        every = {key for keys in _MESH_OPERATION_KEYS.values() for key in keys}
        missing = [key for key in own if getattr(self, key) is None]
        if missing:
            raise ValueError(
                f"a {self.op} states {' and '.join(own)}; {', '.join(missing)} is not stated"
            )
        foreign = sorted(key for key in every - set(own) if getattr(self, key) is not None)
        if foreign:
            raise ValueError(
                f"a {self.op} does not read {', '.join(foreign)}; it states "
                f"{' and '.join(own)} and, optionally, surface"
            )
        if not self.surface:
            raise ValueError(
                f'surface is empty; name a surface of the file, or write "{EVERY_SURFACE}"'
            )
        if self.op in ("rename", "mirror") and self.surface == EVERY_SURFACE:
            raise ValueError(
                f'a {self.op} names the surface it acts on, as surface = "<a name of the '
                'file>"; it has no every-surface form'
            )
        numbers = [*(self.factors or ()), *(self.vector or ())]
        if self.angle_deg is not None:
            numbers.append(self.angle_deg)
        if not all(math.isfinite(number) for number in numbers):
            raise ValueError(f"a {self.op} states a value that is not a finite number")
        if self.factors is not None and min(self.factors) <= 0:
            raise ValueError(
                f"each scale factor must be greater than zero, the manual's rule; "
                f"got {list(self.factors)}"
            )
        if self.to is not None and (not self.to or any(char.isspace() for char in self.to)):
            raise ValueError(
                f"to = {self.to!r} is not a surface name the solver reads as one word; "
                "write a name with no spaces"
            )
        if self.to == EVERY_SURFACE:
            raise ValueError(
                f'to = "{EVERY_SURFACE}" would name a surface with the word for every surface'
            )
        return self


class MeshImport(BaseModel):
    """How a raw mesh is imported: the ``[import]`` table of its sidecar (G01).

    A raw mesh (``.obj``, ``.stl``) carries no length unit, so the file
    that names its boundaries, ``<stem>.boundaries.toml`` beside it,
    states the unit it is written in, and a workflow row naming the mesh
    is refused without it rather than imported under an assumed one.

    ``units`` goes to ``IMPORT`` and nowhere else. The simulation's own
    length unit is always metres, because every length the reference and
    the row state is in metres; the builder sets it after the import
    (:data:`pyflightstream.cases.workflows.SIMULATION_LENGTH_UNIT`). The
    value is only normalised here: which spellings a build takes is read
    from the command database by the builder, per build.

    ``operations`` are the mesh operations applied right after the import,
    in the order written (G03, :class:`MeshOperation`); empty when the
    table declares none.

    Attributes
    ----------
    units : str
        The length unit the mesh file is written in; never assumed.
    operations : tuple of MeshOperation
        The mesh operations applied right after the import, in the order
        written.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    units: str
    operations: tuple[MeshOperation, ...] = ()

    @field_validator("units", mode="before")
    @classmethod
    def _one_word_in_capitals(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        spelled = value.strip().upper()
        if not spelled:
            raise ValueError(
                "`units` is empty; write the length unit the mesh file is written in, "
                'as units = "MILLIMETER"'
            )
        return spelled

    @property
    def moving_operations(self) -> tuple[MeshOperation, ...]:
        """The operations that move, scale or copy the body: every one but ``rename``.

        A trailing-edge points file names edges of the mesh as the FILE
        holds it, and is checked against that file; one of these would
        carry the body's edges away from the points (G02).
        """
        return tuple(operation for operation in self.operations if operation.op != "rename")

    def names_after_renames(self, names: Sequence[str]) -> tuple[str, ...]:
        """Return the boundary names as this import's renames leave them, in order.

        The inventory a row cites for a raw mesh is the sidecar's
        ``boundaries`` as the ``rename`` operations leave them (G03), which
        is what the builder declares. This applies them and judges nothing:
        a rename whose surface is absent at its step, or carried twice, is
        passed over here and refused by the builder.
        """
        renamed = list(names)
        for operation in self.operations:
            if operation.op != "rename" or operation.to is None:
                continue
            found = [index for index, name in enumerate(renamed) if name == operation.surface]
            if len(found) == 1:
                renamed[found[0]] = operation.to
        return tuple(renamed)


#: The ``[trailing_edges]`` routes a raw mesh's sidecar may take (G02): a
#: file of edge mid-points, the default, or detection, applied only when
#: written.
TrailingEdgeRoute = Literal["file", "detect"]


class TrailingEdgeMarking(BaseModel):
    """How a raw mesh's trailing edges are marked: its sidecar's ``[trailing_edges]`` (G02).

    A raw mesh carries no trailing edge, and without one the solver makes
    no wake and runs and answers anyway, so a raw mesh declares one.

    ``route = "file"`` is the default route. ``points_m`` are the mid-points
    of the trailing-edge mesh edges, in metres, the simulation's length unit, read
    from the points file the table names and checked against the mesh when
    the row is bound (:mod:`pyflightstream.workspace.wake_edges`); the
    builder writes them as the solver's node file and imports it with
    ``IMPORT_WAKE_EDGES_FROM_FILE``, giving every edge ``edge_type`` and
    matching within ``tolerance``. ``points_file`` is where they were read
    from, for a refusal to name; it is kept out of every dump, since it is
    a path on one machine.

    ``route = "detect"`` marks by the solver's detection:
    ``detect_surfaces`` names the surfaces to detect on, by the sidecar's
    names, and is empty for every surface; ``sweep_angle_deg`` is set
    before the detection when stated. Detection gives every edge the
    STANDARD type and reads no tolerance.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    route: TrailingEdgeRoute
    edge_type: str = "STANDARD"
    tolerance: float = 0.0001
    points_m: tuple[tuple[float, float, float], ...] = ()
    points_file: str | None = Field(default=None, exclude=True)
    detect_surfaces: tuple[str, ...] = ()
    sweep_angle_deg: float | None = None

    @field_validator("edge_type", mode="before")
    @classmethod
    def _one_word_in_capitals(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _one_route_and_sound_values(self) -> TrailingEdgeMarking:
        if not math.isfinite(self.tolerance) or self.tolerance <= 0.0:
            raise ValueError(
                f"tolerance = {self.tolerance!r}; it is the distance, in the simulation's "
                "length unit, within which an edge's mid-point counts as a point of the "
                "file, and it must be positive and finite"
            )
        if self.route == "file":
            if self.detect_surfaces or self.sweep_angle_deg is not None:
                raise ValueError("the file route takes no detection surfaces and no sweep angle")
            return self
        if self.points_m or self.points_file is not None:
            raise ValueError("the detect route reads no points file")
        if not all(name.strip() for name in self.detect_surfaces):
            raise ValueError("a detection surface is named by an empty string")
        if self.sweep_angle_deg is not None and not math.isfinite(self.sweep_angle_deg):
            raise ValueError(f"sweep_angle = {self.sweep_angle_deg!r} is not a finite number")
        return self


class RawMeshConditions(BaseModel):
    """The boundary conditions a raw mesh's sidecar declares (G02, Q1 of 0.27.0).

    ``trailing_edges`` is required of every raw mesh a workflow imports,
    and the builder refuses one without it. ``wake_termination`` detects
    wake-termination nodes, ``"auto"`` over every surface or by the
    surfaces named; ``base_regions = "auto"`` detects base regions over
    the whole mesh. Both are None unless written.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    trailing_edges: TrailingEdgeMarking | None = None
    wake_termination: Literal["auto"] | tuple[str, ...] | None = None
    base_regions: Literal["auto"] | None = None


class SimCase(BaseModel):
    """One solver configuration with its sweep (SAD Section 5).

    Attributes
    ----------
    sim_id : str
        Case identity; also names the managed folder
        ``sims/sim_<sim_id>``.
    aircraft : str
        Aircraft or configuration name.
    description : str
        Free-text description.
    reynolds : float, optional
        Chord Reynolds number of the condition.
    mach : float, optional
        Free-stream Mach number.
    velocity : float, optional
        Free-stream velocity in m/s.
    freestream_profile : str, optional
        The ABSOLUTE path of a custom free-stream file (G15 of 0.27.0): a
        velocity field over the YZ plane of the global frame, in metres and
        metres per second, which the run writes as ``SET_FREESTREAM CUSTOM``
        in place of ``CONSTANT``. A ``.txt`` is the manual's STRUCTURED form
        and a ``.dat`` its UNSTRUCTURED form. A matrix row states
        ``FREESTREAM: <stem>`` and the workspace resolves it here against
        ``inputs/freestreams/`` when the row binds; a case built in Python
        sets it directly. None, the default, is the uniform free stream. The
        field sets the flow's direction, since ``SOLVER_SET_AOA`` does not
        turn it (measured on 26.124), so the case's angle of attack and
        sideslip are 0 and its builder refuses any other.
    geometry : str, optional
        Path of the geometry or simulation file the recipe opens or
        imports (an ``.fsm`` for OPEN, a mesh file for IMPORT); the
        campaign loop stages
        it into ``inputs/`` and rewrites this field to the staged
        copy, so recipes OPEN exactly what the manifest hashed.
    sweep : SweepAxis
        The sweep of this case.
    flight_condition_defaults : dict, optional
        The pins the row's setup artifact supplied for keys the row did
        not state (PFS-2030.08). Beside ``flight_condition`` rather than
        merged into it, so the row stays as written and the record still
        says what the resolution used.
    flight_condition_defaults_from : str, optional
        Which setup supplied them, id and path.
    flight_condition : dict, optional
        The FLIGHT_CONDITION cell of the row this case came from, as
        WRITTEN: canonical key to value, in the units the keys name
        (PFS-2027.01). Empty when the case states none.

        It travels on the case UNINTERPRETED, and that is the layering
        rather than laziness. Turning a constraint set into a flow state
        needs the reference LENGTH, which lives in the reference
        artifact, and binding that artifact is workspace work one layer
        above this one. So this layer carries the constraints verbatim
        and :func:`pyflightstream.workspace.flight_condition.resolve_flight_condition`
        turns them into ``velocity``, ``density``, ``mach`` and
        ``reynolds``. Keeping the inputs here beside the resolved values
        is also what lets a reader recompute the resolution rather than
        trust it (PFS-2027.05).
    fluid : FluidState, optional
        The RESOLVED air state, where a flight condition was resolved
        into one. Absent on a case whose row stated none and on every
        hand-written campaign that does not set it, which is what keeps
        such a case rendering exactly what it always rendered.
    reference : ReferenceData, optional
        Coefficient normalization references.
    solver : SolverSettings
        Runtime settings; defaults apply when omitted.
    recipe : str
        Script recipe reference, ``"package.module:function"``, or a
        name registered with the campaign loop.
    variables : dict
        Free per-case variables for the recipe (strings, numbers, or
        booleans), for example a symmetry declaration.
    outputs : list of str
        Output files the recipe's script exports, relative to the
        execution directory; the loop collects them into that point's own
        ``datapoints/DP-<point>/`` and
        a missing one marks the point FAILED_INCOMPLETE_OUTPUT. Names
        may carry the naming placeholders, and the loop renders them
        for the point being built before the recipe runs, so a recipe
        exports ``case.outputs[i]`` rather than a literal. Every point
        of a case runs in one folder, so a case whose points would
        render the same output name is blocked before it runs.
    point : dict of str to float
        The current sweep point; filled by the campaign loop before
        the recipe builds, empty on the authored case.
    fs_build : str, optional
        Solver build this case runs on, named as a key of the ``builds``
        mapping :func:`pyflightstream.run.run_campaign` takes. None, the
        default, means the campaign's own ``fs_exe`` and ``fs_version``,
        which is what every campaign written before v0.8.0 says and what
        a single-installation campaign keeps saying.

        It exists because a campaign declares ONE installation while a
        study across two solver builds is a real question, and until
        this field there was no way to state one at all: the run matrix
        refused a second FS_BUILD value outright. The build id is
        indirect on purpose. Putting the executable path here would put
        a machine path in every stored ``campaign.toml``, and the point
        of the id is that the same campaign file runs on a second
        machine whose installations sit elsewhere.
    """

    model_config = ConfigDict(extra="forbid")

    sim_id: str
    aircraft: str
    description: str = ""
    reynolds: float | None = None
    mach: float | None = None
    velocity: float | None = None
    #: THE FREE STREAM'S OWN FILE (G15), beside the free-stream state whose
    #: uniformity it replaces: read where it lives, hashed into the run
    #: record's ``inputs_sha256``, never copied beside the mesh. None for every
    #: case written before 0.27.0, which renders exactly what it rendered.
    freestream_profile: str | None = None
    geometry: str | None = None
    sweep: SweepAxis
    flight_condition: dict[str, float] = Field(default_factory=dict)
    #: 0.21.0: the canonical keys of the row's FLIGHT_CONDITION cell IN THE ORDER
    #: THE ROW WROTE THEM, the swept key included. The point name is written in
    #: this order (:func:`point_name`). Empty for a case authored without a cell.
    condition_order: list[str] = Field(default_factory=list)
    #: The flight-condition pins the row's SETUP artifact supplied, with the
    #: values used, for the keys the row did not state (PFS-2030.08). Written
    #: by the workspace resolver and never by the matrix reader: a matrix
    #: converted without a workspace has no setup to read, and leaves it
    #: empty. Empty also means "the row stated everything it resolved
    #: against", which is every case written before 0.12.0.
    flight_condition_defaults: dict[str, float] = Field(default_factory=dict)
    #: WHERE those defaults came from, as the workspace named it, for
    #: example ``"setup 's001' (inputs/setups/s001.toml)"``. Empty when the
    #: row inherited nothing. Without it the record states four numbers
    #: and cannot name the file that supplied them.
    flight_condition_defaults_from: str = ""
    fluid: FluidState | None = None
    reference: ReferenceData | None = None
    solver: SolverSettings = Field(default_factory=SolverSettings)
    recipe: str
    #: The row's own keys, and TWO THINGS THE RESOLVER WRITES beside them:
    #: a flat `ROTOR_ORIGIN` bound to a named reference point, and the
    #: invocation's `IGNORE_MISSING_FAMILIES` choice (PFS-2035.13). So this
    #: is no longer purely what the cell said, which a reader of this model
    #: alone would otherwise conclude; its neighbour
    #: `flight_condition_defaults` documents the same kind of provenance.
    variables: dict[str, str | float | int | bool] = Field(default_factory=dict)
    #: The rotor motions a row's ``MOTIONS`` list states (PFS-2029.11),
    #: one record each in cell order; empty for a row stating one rotor
    #: flat, which is every row written before 0.11.0.
    motions: list[dict[str, str]] = Field(default_factory=list)
    #: The rotations of the opened mesh a row's ``ROTATE`` list states
    #: (PFS-2034.02), one record each in cell order, applied in that order
    #: after every frame exists and before any motion; empty for a row
    #: stating none, which is every row written before 0.14.0.
    rotations: list[dict[str, str]] = Field(default_factory=list)
    #: The translations of the opened mesh a row's ``TRANSLATE`` list states
    #: (FR-100, PFS-2034.06), one record each in cell order, applied in that
    #: order after every frame exists and before every rotation: DISTANCE in
    #: metres along one axis of the named frame. Empty for a row stating none,
    #: which is every row written before 0.19.0.
    translations: list[dict[str, str]] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    #: The post-processing specification the row's PPROC cell named, bound
    #: by the workspace (PFS-2029.07); None for a case built without one,
    #: which emits the default export set and no sections, plots or probes.
    pproc: PprocSpec | None = None
    pproc_id: str | None = None
    #: The custom coordinate systems the row's setup defines (PFS-2034.01),
    #: created after the package's own frames in the order written; empty
    #: for a setup that defines none, which is every setup written before
    #: 0.14.0.
    frames: list[FrameSpec] = Field(default_factory=list)
    #: The solver commands the row's setup states verbatim (PFS-2033.01),
    #: each emitted before the phase it names, in the order written; empty
    #: for a setup stating none.
    raw_commands: list[RawCommand] = Field(default_factory=list)
    #: The custom flags the row's setup declares (PFS-2035.20), each a
    #: FlightStream command the row may set by name. Bound by the
    #: workspace from the setup artifact, as the raw commands are.
    flags: list[CustomFlag] = Field(default_factory=list)
    #: The boundary aliases the row's REFERENCE declares (FR-59, the reference
    #: design of 2026-09-10; the setup's until 0.14.0), a name to the
    #: boundary names, families or other aliases it stands for; read by
    #: every builder that resolves a cited boundary and carried on the
    #: record for the products stage. Empty for a configuration defining
    #: none, which is every one written before 0.14.0.
    aliases: BoundaryAliases = Field(default_factory=dict)
    #: The rotors the row's reference declares (FR-60), keyed by the word
    #: a motion record cites. A record naming one takes its hub, axis,
    #: sign, blades and diameter from it and states none of them itself,
    #: which is what lets a row state nine rotors without repeating nine
    #: hubs. Empty for a configuration with no rotor block, which is
    #: every one written before 0.15.0.
    rotors: dict[str, RotorBlock] = Field(default_factory=dict)
    #: The actuator discs the row's reference declares (G06), keyed by the
    #: block's name, which is what a row's ``ACTUATOR`` names. Empty for a
    #: configuration declaring none, which is every one written before 0.27.0;
    #: a disc declared and not named by the row emits nothing.
    actuators: dict[str, ActuatorBlock] = Field(default_factory=dict)
    #: The ABSOLUTE path of the file a row's ``PROFILE`` names under the
    #: workspace's ``inputs/profiles/`` (G06), resolved and checked when the
    #: row binds. The solver never reads it: the builder reads its rows into
    #: the run's own copy, in the one form 26.124 reads, which the run writes
    #: where the point runs and hashes into the record's ``inputs_sha256``.
    #: None for a row stating no profile.
    actuator_profile: str | None = None
    #: The boundary order a sidecar beside the geometry states
    #: (PFS-2029.06.03), bound by the workspace; the builder refuses the
    #: run when the file's own mesh block disagrees with it.
    inventory: tuple[str, ...] | None = None
    #: Where the boundary inventory came from: ``sidecar``, ``mesh_block``
    #: or None when the geometry declares none.
    inventory_source: str | None = None
    #: The ``[import]`` table of the sidecar beside a raw mesh (G01), bound
    #: by the workspace: the length unit the file is written in. None for a
    #: geometry whose sidecar states no such table, which is every saved
    #: simulation; the builder refuses a raw mesh without one, and a saved
    #: simulation with one.
    mesh_import: MeshImport | None = None
    #: The ``[trailing_edges]``, ``[wake_termination]`` and ``[base_regions]``
    #: tables of the same sidecar (G02), bound by the workspace, a file
    #: route's points read and checked against the mesh. None for a sidecar
    #: stating none of the three; the builder refuses a raw mesh without a
    #: trailing edge, and a saved simulation with any of them.
    raw_mesh_conditions: RawMeshConditions | None = None
    point: dict[str, float] = Field(default_factory=dict)
    #: The state each point of a SWEPT FLOW VARIABLE resolved to, keyed by
    #: :func:`point_state_key` (0.21.0). Empty on every row that sweeps an
    #: angle or a ratio, which resolve once for the whole row.
    point_states: dict[str, PointState] = Field(default_factory=dict)
    fs_build: str | None = None

    @model_validator(mode="after")
    def _one_sweep_per_case(self) -> SimCase:
        """Refuse a case asking for an aerodynamic AND a geometric sweep.

        The limit is stated at DECLARATION, which is the moment this
        validator runs: constructing the case in Python, or loading the
        ``campaign.toml`` that holds it. Nothing is resolved yet, no
        workspace is opened and no solver is started, so a user meets the
        limit before spending anything on it. The run matrix reader
        carries the same refusal at its own declaration moment, in its
        own vocabulary; both call :func:`multiplied_sweep`, which is
        where the decision and its reasoning live.

        The refusal names the fixed-offset form, because the user asking
        for both almost always wants one rotation held fixed across an
        aerodynamic sweep, which is what
        :data:`ROTATION_OFFSET_KEY` already does and costs one campaign
        rather than N.
        """
        angles = multiplied_sweep(self.sweep, self.variables)
        if not angles:
            return self
        raise CampaignConfigError(
            f"case {self.sim_id} asks for two sweeps at once: the {self.sweep.type} "
            f"sweep of {len(self.sweep.values)} points and the geometric sweep "
            f"{ROTATION_SWEEP_KEY}: {','.join(angles)} of {len(angles)} angles. The "
            f"two would multiply into {len(self.sweep.values) * len(angles)} runs the "
            "case does not name, and the points cannot be told apart: a run is "
            "identified by its aerodynamic point alone, so every geometry would "
            "produce the same run_id and the same output file names. A rotation held "
            f"FIXED across an aerodynamic sweep is written {ROTATION_OFFSET_KEY} = "
            "<angle>, one value; a sweep OF the geometry is one case per geometry, "
            "each with its own sim_id and its own single-valued angle."
        )


#: Key of the marker's own digest, the one line the canonical form
#: below drops. It is a bare TOML key, never a quoted one: every case
#: variable is emitted quoted (``"content_sha256" = ...``), so a case
#: variable spelled the same way cannot be mistaken for the marker and
#: cannot hide an edit made anywhere else in the file.
_CONTENT_DIGEST_KEY = "content_sha256"


class DerivedFrom(BaseModel):
    """Where a generated ``campaign.toml`` came from, recorded in itself.

    A campaign the package wrote is otherwise byte-indistinguishable
    from one a user authored, and will be edited by someone who believes
    it is input. This marker is what makes the rule enforceable rather
    than conventional, and it lives IN the file rather than beside it
    because a file gets copied out of its folder.

    Attributes
    ----------
    matrix : str
        The run-matrix path exactly as it was given to the conversion.
        Relative paths resolve against the campaign file's own folder
        when the marker is checked.
    matrix_sha256 : str
        sha256 of the matrix file's bytes at the moment of conversion,
        so a matrix edited afterwards makes the campaign stale.
    generated_at : str
        When the campaign was written, UTC, ISO 8601, ending in ``Z``.
        Presentation only: nothing in the package compares it.
    content_sha256 : str
        sha256 of this campaign's own canonical body
        (:func:`derived_body_sha256`), so an edit to ANY other line of
        the file is refused at load. The digest is a tamper check over
        the file text, not a same-inputs digest: it deliberately covers
        the executable path and the generation moment, because editing
        either is exactly what it exists to catch.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    matrix: str
    matrix_sha256: str
    generated_at: str
    content_sha256: str


def derived_body_sha256(text: str) -> str:
    r"""Return the digest of a campaign text's canonical body.

    The canonical form is stated here because the digest is compared
    against a value written into a file on another day, possibly on
    another platform:

    * the line carrying the marker's own digest is DROPPED, so the
      digest can be written into the very text it describes;
    * the text is split with ``splitlines()``, which drops the line
      TERMINATOR, so a file written through ``open(..., "w")`` on
      Windows, where every newline becomes CRLF on disk, still matches
      the digest taken before it was written;
    * every line is then right-stripped and trailing blank lines go, so
      trailing whitespace, which no reader can see and several editors
      add or remove on save, is not a reason to refuse a campaign;
    * the surviving lines join on ``\n`` and hash as UTF-8.

    The two middle rules are stated apart because they are different
    rules with different causes, and a mutation run on 2026-08-19 showed
    the second doing none of the work the first does: with the strip
    removed, a CRLF file still matched.

    Parameters
    ----------
    text : str
        The whole decoded ``campaign.toml`` text.

    Returns
    -------
    str
        Lowercase hexadecimal sha256, through
        :func:`pyflightstream._digest.text_sha256`, which is the single
        owner of the algorithm.

    Examples
    --------
    >>> derived_body_sha256("[campaign]\nname = 'a'\n") == derived_body_sha256(
    ...     "[campaign]\r\nname = 'a'\r\n\r\n"
    ... )
    True
    """
    lines = [
        line.rstrip()
        for line in text.splitlines()
        if not line.strip().startswith(_CONTENT_DIGEST_KEY)
    ]
    while lines and not lines[-1]:
        lines.pop()
    return text_sha256("\n".join(lines))


def stamp_derived_campaign(
    text: str,
    matrix: str | Path,
    *,
    generated_at: str | None = None,
) -> str:
    """Mark a generated ``campaign.toml`` text as derived from a matrix.

    The ``[campaign.derived_from]`` table is inserted immediately after
    the ``[campaign]`` scalars, which is where TOML requires a sub-table
    of a table to go, and the content digest is computed over everything
    else, so the returned text describes itself.

    Parameters
    ----------
    text : str
        The campaign text as generated, for example by
        :func:`pyflightstream.cases.matrix.convert_matrix`.
    matrix : str or Path
        The matrix the text was converted from. It is read here, to be
        hashed, and recorded verbatim as the marker's ``matrix``.
    generated_at : str, optional
        Override for the recorded moment; the default is now, in UTC,
        ISO 8601 to the second. Present so a caller that needs a
        byte-reproducible output can ask for one.

    Returns
    -------
    str
        The same campaign text with the marker table in it.

    Examples
    --------
    >>> from pathlib import Path
    >>> stamped = stamp_derived_campaign(   # doctest: +SKIP
    ...     convert_matrix("matrix.fs", name="wing", fs_version="26.120",
    ...                    fs_exe="FlightStream.exe", recipes={"003": "r:build"}),
    ...     "matrix.fs",
    ... )
    >>> Path("campaign.toml").write_text(stamped, encoding="utf-8")  # doctest: +SKIP
    """
    moment = generated_at or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    table = [
        "[campaign.derived_from]",
        f'matrix = "{matrix}"',
        f'matrix_sha256 = "{file_sha256(matrix)}"',
        f'generated_at = "{moment}"',
    ]
    lines = text.splitlines()
    insert_at = len(lines)
    for index, line in enumerate(lines):
        if line.strip() == "[campaign]":
            for after in range(index + 1, len(lines)):
                if lines[after].lstrip().startswith("["):
                    insert_at = after
                    break
            break
    else:
        raise CampaignConfigError(
            "the text to stamp has no [campaign] table, so there is nowhere to "
            "record where it was derived from; stamp the output of a campaign "
            "generator, not an arbitrary file"
        )
    head = lines[:insert_at]
    while head and not head[-1].strip():
        head.pop()
    tail = lines[insert_at:]
    # The digest is taken over the text WITHOUT its own line, which is
    # exactly what `derived_body_sha256` drops, so the value written here
    # is the value a reader recomputes from the finished file.
    unstamped = head + [""] + table + [""] + tail
    digest = derived_body_sha256("\n".join(unstamped))
    stamped = head + [""] + table + [f'{_CONTENT_DIGEST_KEY} = "{digest}"', ""] + tail
    return "\n".join(stamped).rstrip("\n") + "\n"


class Campaign(BaseModel):
    """A named group of cases bound to one FlightStream installation.

    Attributes
    ----------
    name : str
        Campaign name; prefixes every ``run_id``.
    fs_version : str
        FlightStream version, canonical identifier (26.120); a vendor
        release name works only where it names exactly one registered
        build. Validated against the registered versions at load time
        and STORED canonical (PFS-2009.04): a name accepted today is
        resolved today, so what the model holds, and what a converted
        matrix writes, is the build and never the name.
    fs_exe : str
        Explicit path of the FlightStream executable; existence is
        checked by the executor at construction, not here, so a
        campaign file can be authored away from the licensed machine.
    sims : list of SimCase
        The cases of the campaign.
    derived_from : DerivedFrom, optional
        Present only on a campaign the package GENERATED, naming the
        matrix it came from and digesting both files. None means nobody
        generated this campaign, which is the ordinary case and is not a
        lesser one: an authored campaign is the source of its study and
        the package says nothing about it.
    matrix_stem : str, optional
        The stem of the run matrix this campaign was converted from, for
        example ``"matriz_setup"`` for ``matriz_setup.fs``, and None for
        a campaign authored in Python or loaded from a file. It is the
        identity under which the matrix keeps its own products in a
        workspace that holds several: the plan, the sweep table and the
        product tables of a matrix land under ``post/<matrix>/`` and
        every run record says which matrix it came from (PFS-2031.04).
        Distinct from ``name``, which is the campaign name every run id
        carries and which a whole workspace usually shares, and from
        ``DerivedFrom.matrix``, which is the path the conversion read; the
        word ``stem`` is in the name so the two are not one word on the
        ``campaign.toml`` surface (the design decision of 2026-09-08).

    Notes
    -----
    :attr:`source_path` is knowledge rather than a field. It is set only
    by :func:`load_campaign`, so a campaign file cannot declare a source
    it did not come from, and the ``campaign.toml`` surface is untouched
    by it.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    fs_version: str
    fs_exe: str
    sims: list[SimCase]
    derived_from: DerivedFrom | None = None
    matrix_stem: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _take_the_earlier_name_of_the_matrix_stem(cls, data: object) -> object:
        """Read a campaign file written under the field's one-day name, ``matrix``."""
        if isinstance(data, dict) and "matrix" in data and "matrix_stem" not in data:
            data = {**data, "matrix_stem": data["matrix"]}
            del data["matrix"]
        return data

    #: The file this campaign was loaded from, or None for one built in
    #: Python. Private so it cannot be set from a file; read through
    #: :attr:`source_path`.
    _source_path: str | None = PrivateAttr(default=None)

    @property
    def source_path(self) -> str | None:
        """The campaign file this was loaded from, or None.

        Returns
        -------
        str or None
            The path :func:`load_campaign` was given, as given. None
            means the campaign was built in Python and no file is its
            source.
        """
        return self._source_path

    @property
    def is_derived(self) -> bool:
        """Whether the package generated this campaign from a matrix.

        Returns
        -------
        bool
            True when the file carries the ``[campaign.derived_from]``
            marker. False means it is an authored campaign, which is the
            source of its own study; ask this rather than sniffing keys.
        """
        return self.derived_from is not None

    @field_validator("fs_version")
    @classmethod
    def _version_is_registered(cls, value: str) -> str:
        """Resolve the version and KEEP the answer (PFS-2009.04).

        Until 0.13.0 this resolved for the side effect and returned the
        string as written, so a campaign built from a vendor name stored
        the name. ``26.1`` named one build until 2026-08-04 and two
        after it, and a campaign.toml holding it was refused on a
        machine where nothing changed but the installed package, in a
        file its owner never edited. The model holds the canonical
        identifier; the alias is accepted at the door and goes no
        further, so a converted matrix writes the build and not the
        name, and ``pyfs-matrix plan`` reads the same build on the day a
        second build claims the alias.
        """
        return resolve(value).canonical

    @model_validator(mode="after")
    def _sim_ids_are_distinct(self) -> Campaign:
        """Refuse two cases claiming the same ``sim_id``.

        PYFS-003, second half. ``sim_id`` selects the simulation folder AND
        sits in the middle of every ``run_id``, so two cases sharing one
        would stage into the same ``inputs/``, write into the same
        ``scripts/``, collect into the same ``datapoints/``, and produce colliding
        identities for any points whose tags agree. The model accepted it
        without complaint and the pre-flight reported both as READY.

        Checked here rather than in the workspace because it is a property
        of the campaign as declared, knowable with no filesystem at all.
        """
        seen: set[str] = set()
        duplicated: set[str] = set()
        for case in self.sims:
            if case.sim_id in seen:
                duplicated.add(case.sim_id)
            seen.add(case.sim_id)
        if duplicated:
            raise CampaignConfigError(
                f"campaign {self.name!r} declares more than one case with sim_id "
                f"{', '.join(repr(sim) for sim in sorted(duplicated))}. The sim_id names the "
                "simulation folder and sits inside every run_id, so the cases would "
                "share one staging area, one script folder and one output folder. "
                "Give each case its own sim_id."
            )
        return self


def _refuse_an_edited_derived_campaign(campaign: Campaign, path: str | Path, text: str) -> None:
    """Refuse a generated campaign whose file no longer matches its digests.

    Nothing is re-derived here, and that is the whole design. Rebuilding
    the campaign from the matrix would be seeded from the file under
    test: ``name``, ``fs_version``, ``fs_exe`` and each case's ``recipe``
    are handed TO the conversion rather than read from the matrix, so a
    re-derivation would find them equal by construction and an edited
    ``fs_exe``, which is what a user on a second machine actually edits,
    would load in silence. Comparing the file against digests taken when
    it was written covers every field the same way.

    Two comparisons, and the second is deliberately skippable. The
    content digest always applies. The matrix digest applies only where
    the recorded matrix is readable, because the marker exists to
    survive the campaign being copied out of its folder, and a refusal
    on an absent matrix would make the marker the reason a perfectly
    good campaign stops loading.
    """
    marker = campaign.derived_from
    if marker is None:  # pragma: no cover - callers check first
        return
    remedy = (
        f"{path} was GENERATED from {marker.matrix} and has been edited since. Edit "
        f"{marker.matrix} instead and convert it again (pyfs-matrix convert), so the "
        "matrix and the campaign cannot disagree about what the study is. To take "
        "ownership of this file instead, delete its [campaign.derived_from] table: "
        "it then loads as an authored campaign, which is a supported source."
    )
    if derived_body_sha256(text) != marker.content_sha256:
        raise CampaignConfigError(remedy)
    matrix_path = Path(marker.matrix)
    if not matrix_path.is_absolute():
        matrix_path = Path(path).parent / matrix_path
    if matrix_path.is_file() and file_sha256(matrix_path) != marker.matrix_sha256:
        raise CampaignConfigError(
            f"{path} was generated from {marker.matrix}, and that matrix has changed "
            "since; the campaign no longer describes the study the matrix states. "
            "Convert the matrix again (pyfs-matrix convert) rather than running a "
            "campaign whose source has moved on."
        )


def load_campaign(path: str | Path) -> Campaign:
    """Load and validate a ``campaign.toml`` file.

    The file holds one ``[campaign]`` table (name, fs_version,
    fs_exe) and one ``[[sim]]`` array entry per case, as in SAD
    Section 5.

    A file the package GENERATED carries a ``[campaign.derived_from]``
    table naming its matrix, and is refused here when it has been edited
    since; a file a user authored carries no such table, loads exactly as
    it always did, and is recorded as the source of its own study. The
    refusal fires only on the marker's presence, which is what keeps
    every hand-written campaign in existence loading.

    Parameters
    ----------
    path : str or Path
        Location of the TOML file.

    Returns
    -------
    Campaign
        Validated campaign; version aliases are checked against the
        registered versions immediately, so a typo fails at load
        time, not at the first point. Its :attr:`Campaign.source_path`
        is this file and :attr:`Campaign.is_derived` says which kind it
        is.

    Raises
    ------
    CampaignConfigError
        No ``[campaign]`` table; or a generated campaign that has been
        edited, or whose matrix has changed since the conversion.

    Examples
    --------
    >>> campaign = load_campaign("campaign.toml")   # doctest: +SKIP
    >>> campaign.is_derived                         # doctest: +SKIP
    False
    >>> campaign.source_path                        # doctest: +SKIP
    'campaign.toml'
    """
    text = Path(path).read_text(encoding="utf-8")
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    if "campaign" not in data:
        raise CampaignConfigError(
            f"{path} has no [campaign] table; campaign.toml needs [campaign] with "
            "name, fs_version, and fs_exe, plus one [[sim]] entry per case"
        )
    campaign = Campaign(**data["campaign"], sims=data.get("sim", []))
    campaign._source_path = str(path)
    if campaign.derived_from is not None:
        _refuse_an_edited_derived_campaign(campaign, path, text)
    return campaign


def resolve_recipe(reference: str) -> Callable[[SimCase, Script], None]:
    """Import the recipe function a reference string names.

    Parameters
    ----------
    reference : str
        ``"package.module:function"``; the module must be importable
        and the attribute callable. Explicit references replace the
        historical import-by-number system (PP-7, FR-12).

    Returns
    -------
    callable
        The recipe function, satisfying :class:`ScriptRecipe`.
    """
    module_name, separator, function_name = reference.partition(":")
    if not separator or not module_name or not function_name:
        raise CampaignConfigError(
            f"recipe reference {reference!r} is not of the form 'package.module:function'"
        )
    try:
        module = import_module(module_name)
    except ImportError as error:
        raise CampaignConfigError(
            f"recipe module {module_name!r} cannot be imported: {error}. Recipes are "
            "explicitly imported functions; check the module path and the environment."
        ) from error
    recipe = getattr(module, function_name, None)
    if not callable(recipe):
        raise CampaignConfigError(
            f"recipe {reference!r} does not name a callable in {module_name!r}; found {recipe!r}"
        )
    check_recipe(reference, recipe)
    return recipe


def check_recipe(reference: str, recipe: Callable) -> None:
    """Refuse a callable the campaign loop could not call.

    The loose form of a script builder, ``build(workdir) -> Script``,
    is what everyone arriving from a driver script has; called by the
    loop it raises a bare TypeError once per point, after the pre-flight
    has already accepted the campaign. Refusing at resolution names the
    protocol and the signature found, once, before anything runs.
    Callables whose signature cannot be read (builtins, C extensions)
    pass: the library does not refuse what it cannot inspect.
    """
    try:
        parameters = signature(recipe).parameters.values()
    except (TypeError, ValueError):
        return
    positional = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD, Parameter.VAR_POSITIONAL)
    ]
    if any(parameter.kind is Parameter.VAR_POSITIONAL for parameter in positional):
        return
    required = [parameter for parameter in positional if parameter.default is Parameter.empty]
    unfillable = [
        parameter.name
        for parameter in parameters
        if parameter.kind is Parameter.KEYWORD_ONLY and parameter.default is Parameter.empty
    ]
    if len(positional) >= 2 and len(required) <= 2 and not unfillable:
        return
    found = ", ".join(parameter.name for parameter in parameters) or "no arguments"
    raise CampaignConfigError(
        f"recipe {reference!r} does not satisfy the ScriptRecipe protocol: the campaign "
        f"loop calls build(case, script) -> None, and this one takes ({found}). A loose "
        "builder that creates and returns its own Script emits into a script the loop "
        "never sees; take the case and the script it hands you, and return None."
    )
