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

The 0.29 workflow keeps unit conversion at the command boundary. Physical
metre-labelled inputs and explicitly SI reference normalizations use the
shared :mod:`pyflightstream._lengths` floor; the direct Python reference
API retains its native-unit default. Saved FSM units are decoded only for
measured METER/MILLIMETER heads. CAD conversion extends the existing mesh
import route, and unproved formats remain named refusals.

Custom inflow preserves the user's physical orientation. An explicit SI
declaration prepares a separate solver-unit file with source and effective
hashes; an undeclared file keeps its bytes. The final emitted transforms
and rotor sweep feed conservative spatial bounds, not a guarantee of
interpolation support inside an unstructured field. These controls do not
automatically rotate a field or accept a nonzero incidence beside it.

The 0.30 quasi-steady rotor (the ``qsteady_rotor`` run type of
:mod:`pyflightstream.cases.workflows`) keeps its own arithmetic in
:mod:`pyflightstream.cases.qsteady`: the clockings of a wheel, the 1P
reduced frequency and its validity figures, and the harmonic content of a
custom inflow as one blade meets it. The plan and the post both read it.
The 0.31 correction routes of a wheel, the pproc's ``[qsteady_correction]``
table and the calibration file it names, are
:mod:`pyflightstream.cases.corrections`, which the plan validates and the
post applies; none of them is validated.
:mod:`pyflightstream.cases.fsi_workspace` states which workflows may couple
and wires the fixed-wing and quasi-steady sector routes.

The 0.32 modules of this layer: :mod:`pyflightstream.cases.acoustics` emits
the solver's acoustic sources, observers and signals export on an unsteady
row and states the contract of the export the post stage reads;
:mod:`pyflightstream.cases.ccs_wing`, :mod:`pyflightstream.cases.ccs_fuselage`
and :mod:`pyflightstream.cases.ccs_revolution` have the solver make a mesh of
a row's CCS file, by the curve route or the file route, with the vocabulary of
the sidecar's ``[import.ccs]`` table in the private ``cases._ccs``; and
:mod:`pyflightstream.cases.setup_surfaces` removes the surfaces a setup names,
renumbering the inventory as the solver does, and emits the slipstream wake
stabilization of each rotor motion.

The 0.33 layout of this layer: :mod:`pyflightstream.cases.workflows` is a
package. Its root keeps every public name and nothing else, and its private
modules import one another only in a declared order, from the extraction
script of a saved simulation and the run-type registry at the top, through
the builders of each run type, the script skeleton, the post-processing,
probe, clock, export, reduction, free-stream, settings, frame, geometry,
name, timing, motion and actuator emission, down to the typed readers of a
row's keys, the conventions and the row vocabulary at the bottom. The
run-type table is one object created empty below the builders and filled by
the registry when the package is imported. A new run type is a builder
module and one registry entry; a row key is registered in the vocabulary and
read by the row readers. Four private modules carry the 0.33 features of
this layer: ``cases._setup_keys`` (the setup keys of a preset and the
command each reaches), ``cases._setup_link`` (the analysis settings of a
setup: the loads selections, the moments model and its rotor link, the
unsteady solver actions), ``cases._skipped_families`` (each family a row's
geometry does not carry, named once per matrix at plan) and
``cases._unsteady_actions`` (the step counter and the per-step actions every
unsteady march registers). The unit that names no length has one home, the
floor :mod:`pyflightstream._lengths`, and the flag phases one home, this
package.

The 0.34 layout of this root (AD-16): the models it held moved to six public
modules, and the root re-exports every name it exported, so each moved name
has two paths that are one object. :mod:`pyflightstream.cases.pproc` holds the
exports vocabulary and the post-processing artifact;
:mod:`pyflightstream.cases.reference_blocks` the rotor, actuator and blade
blocks of a reference and the two errors of a case definition;
:mod:`pyflightstream.cases.settings` the solver settings, the flight-condition
state and the reference data; :mod:`pyflightstream.cases.mesh` the mesh import
and the mesh-side boundary models; :mod:`pyflightstream.cases.naming` the point
and sweep names; :mod:`pyflightstream.cases.selection` the family and alias
selection. None of the six imports this root, so the root keeps the input keys,
the recipes, the sweep, the flags and raw commands, the frames, the case and
the campaign, and a field a release adds to a model lands in the model's own
module.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable, Iterator, Mapping
from importlib import import_module
from inspect import Parameter, signature
from pathlib import Path
from typing import Any, Literal, NamedTuple, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

from pyflightstream._digest import file_sha256, text_sha256
from pyflightstream._retired_names import retired_frame

# The setup keys' command table and the tables FR-319 added; its module imports
# only pydantic and the command database, so the package may import it while it loads.
from pyflightstream.cases._setup_keys import SOLVER_SETTING_COMMANDS
from pyflightstream.cases.mesh import (
    EVERY_SURFACE,
    BaseRegionOperation,
    CadImportOptions,
    MeshImport,
    MeshOperation,
    RawMeshConditions,
    TrailingEdgeMarking,
)
from pyflightstream.cases.mesh import PortBoundary as PortBoundary
from pyflightstream.cases.mesh import RadialBoundaryMesh as RadialBoundaryMesh
from pyflightstream.cases.mesh import TrailingEdgeRoute as TrailingEdgeRoute
from pyflightstream.cases.naming import (
    POINT_AXIS_KEYS,
    POINT_NAME_FIELDS,
    ROTATION_OFFSET_KEY,
    ROTATION_SWEEP_KEY,
    SWEEP_NAME_VALUE,
    TAG_AXES,
    NameField,
    geometric_sweep_values,
    multiplied_sweep,
    name_field,
    point_name,
    point_tag,
    sweep_name,
)
from pyflightstream.cases.pproc import (
    AXES_PLOT_COMPONENTS,
    AXES_PLOT_GROUP,
    DEFAULT_DRIFT_LIMIT_PCT,
    EXPORT_KIND_MEANINGS,
    EXPORT_KIND_SINCE,
    EXPORT_KINDS,
    FAMILY_SELECTORS,
    FLUID_PLOT_PARAMETERS,
    FORCE_PLOT_PARAMETERS,
    OPT_IN_EXPORT_KINDS,
    PLOT_TYPES,
    PPROC_FRAMES,
    ROTOR_PLOT_GROUP_PREFIX,
    STEADY_ONLY_EXPORT_KINDS,
    VOLUME_SECTION_KINDS,
    VOLUME_SECTION_PRISMS,
    ForcePlotGroup,
    PlotsSpec,
    PprocSpec,
    ProbeLine,
    ProbesSpec,
    ProductsSpec,
    SectionDistribution,
    SectionsSpec,
    SurfaceProbeSpec,
    SurfaceTimeAveragingSpec,
    VolumeSectionSpec,
    classify_outputs,
    default_outputs,
    global_frame_plot_declarations,
)
from pyflightstream.cases.pproc import EXPANDING_FRAMES as EXPANDING_FRAMES
from pyflightstream.cases.pproc import SUPERFILE_FORMATS as SUPERFILE_FORMATS
from pyflightstream.cases.pproc import EquationSpec as EquationSpec
from pyflightstream.cases.pproc import PerRevolutionSpec as PerRevolutionSpec
from pyflightstream.cases.pproc import PhaseLockedSpec as PhaseLockedSpec
from pyflightstream.cases.pproc import Plane as Plane
from pyflightstream.cases.pproc import ProbeCircle as ProbeCircle
from pyflightstream.cases.pproc import ProbeRectangle as ProbeRectangle
from pyflightstream.cases.reference_blocks import (
    AXIS_UNIT_VECTORS,
    ROTOR_BLADE_ROTATION_AXIS,
    ActuatorBlock,
    AliasCycleError,
    BladeDatum,
    CampaignConfigError,
    RotorBlock,
)
from pyflightstream.cases.reference_blocks import ActuatorOperation as ActuatorOperation
from pyflightstream.cases.reference_blocks import frame_basis_for_shaft as frame_basis_for_shaft
from pyflightstream.cases.selection import EVERY_FAMILY as EVERY_FAMILY
from pyflightstream.cases.selection import (
    EXPANDING_SELECTORS,
    BoundaryAliases,
    resolve_alias,
    select_families,
    select_group_members,
)
from pyflightstream.cases.selection import alias_members_missing as alias_members_missing
from pyflightstream.cases.selection import (
    warn_a_selector_that_guesses as warn_a_selector_that_guesses,
)
from pyflightstream.cases.settings import (
    FluidState,
    PointState,
    ReferenceData,
    SolverSettings,
    SolverToggle,
    point_state_key,
)
from pyflightstream.commands import Phase
from pyflightstream.fsi.config import FsiConfig
from pyflightstream.script import Script
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
    "DEFAULT_DRIFT_LIMIT_PCT",
    "DerivedFrom",
    "FluidState",
    "EVERY_SURFACE",
    "CadImportOptions",
    "MeshImport",
    "MeshOperation",
    "RawMeshConditions",
    "ReferenceData",
    "TrailingEdgeMarking",
    "ScriptRecipe",
    "SimCase",
    "BaseRegionOperation",
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
    "SurfaceProbeSpec",
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
]


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
        axes = set(TAG_AXES)
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
    reference frame, in metres, and the two axes
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
    #: record's ``inputs_sha256``. An explicit SI declaration additionally
    #: prepares and hashes a separate solver copy. None for every
    #: case written before 0.27.0, which renders exactly what it rendered.
    freestream_profile: str | None = None
    #: Explicit custom-file units: SI means m and m/s; NATIVE means current
    #: simulation length units per second. Omitted preserves legacy bytes.
    freestream_units: Literal["SI", "NATIVE"] | None = None
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
    fsi: FsiConfig | None = None
    fsi_provenance: dict[str, Any] = Field(default_factory=dict)
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
    #: Profiles named by individual ACTUATOR records, resolved by library stem.
    actuator_profiles: dict[str, str] = Field(default_factory=dict)
    #: The ABSOLUTE path of the file a row's ``ACOUSTIC_OBSERVERS_FILE`` names
    #: under the workspace's ``inputs/acoustics/`` (0.32.0, FR-266), resolved and
    #: checked when the row binds; the builder parks the point's own copy, which
    #: the run writes and hashes. None for a row stating no such file.
    acoustic_observers_file: str | None = None
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
    #: The setup keys the matrix row stated over its preset, as written in the
    #: cell (FR-316); :attr:`solver` already carries their effective values.
    setup_from_row: dict[str, str] = Field(default_factory=dict)

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
