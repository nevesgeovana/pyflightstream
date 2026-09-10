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

import re
import tomllib
import warnings
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from importlib import import_module
from inspect import Parameter, signature
from pathlib import Path
from typing import Annotated, Literal, Protocol, runtime_checkable

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
    PPROC_HER_POLAR_FORMAT,
    ROW_AIRFRAME_SELECTOR,
    ROW_BLADES_SELECTOR,
    ROW_EACH_BLADE,
    refusal_text,
)
from pyflightstream._digest import file_sha256, text_sha256
from pyflightstream._errors import PyflightstreamDeprecationWarning, PyflightstreamError
from pyflightstream._fsm import names_of
from pyflightstream._retired_names import PROBE_SCALE_PROPELLER_RADIUS
from pyflightstream.commands import Phase
from pyflightstream.script import Script
from pyflightstream.script.toggles import resolve_toggle
from pyflightstream.versions import resolve

__all__ = [
    "AliasCycleError",
    "BladeDatum",
    "RotorBlock",
    "ROTATION_OFFSET_KEY",
    "ROTATION_SWEEP_KEY",
    "Campaign",
    "CampaignConfigError",
    "DerivedFrom",
    "FluidState",
    "ReferenceData",
    "ScriptRecipe",
    "SimCase",
    "SolverSettings",
    "SolverToggle",
    "EXPORT_KINDS",
    "FAMILY_SELECTORS",
    "FLUID_PLOT_PARAMETERS",
    "FORCE_PLOT_PARAMETERS",
    "PPROC_FRAMES",
    "FrameSpec",
    "RAW_PHASES",
    "RawCommand",
    "PprocSpec",
    "RESERVED_FRAME_NAMES",
    "SectionsSpec",
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
    "point_tag",
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
        ``alpha`` (angle of attack, deg), ``beta`` (side slip, deg),
        ``alpha_beta`` (paired values), or ``advance_ratio``
        (rotor advance ratio J, dimensionless).
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

    type: Literal["alpha", "beta", "alpha_beta", "advance_ratio"]
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
        """Refuse a sweep whose points cannot be told apart by run_id.

        PYFS-003. ``point_tag`` formats at one decimal, so alpha 1.01 and
        1.04 both render ``a+01.0``. The tag ENDS the ``run_id``, so two
        points of one case then shared one manifest identity.

        What made that expensive was where it surfaced. Nothing refused the
        sweep, the pre-flight reported both points READY under the same id,
        and the manifest's duplicate rejection only fired when the SECOND
        point tried to record. By then the first had executed, written its
        script and appended its record, so the campaign was left
        half-executed with a manifest that looks complete for the id it
        holds. The refusal belongs at the sweep, where it costs nothing.

        Widening the tag was the other option and is not taken: the tag is
        IDENTITY, it ends every ``run_id`` already in every existing
        manifest, and any fixed precision collides at some spacing anyway.
        Refusing the ambiguous sweep is exact; a wider tag would only move
        the collision.
        """
        seen: dict[str, dict[str, float]] = {}
        for point in self.points():
            tag = point_tag(point)
            if tag in seen:
                raise CampaignConfigError(
                    f"sweep points {seen[tag]!r} and {point!r} both tag as {tag!r}, "
                    "so they would share one run_id and one set of file names. "
                    "Point tags are fixed at one decimal because they are run "
                    "IDENTITY and appear in every existing manifest. Separate the "
                    "values by at least 0.1, or split them across simulations."
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
#: author's own driver wrote them and with the author's suffixes: (kind, suffix, the
#: solver verb, unsteady only). A steady point leaves seven, an unsteady point
#: eight, the plots file being the one only a time loop produces. The suffix is
#: what pairs a declared output name with its verb, longest suffix first, so
#: ``x_cp.txt`` is the sections export and never the loads table.
EXPORT_KINDS: tuple[tuple[str, str, str, bool], ...] = (
    ("simulation", ".fsm", "SAVEAS", False),
    ("loads", ".txt", "EXPORT_SOLVER_ANALYSIS_SPREADSHEET", False),
    ("tecplot", ".dat", "EXPORT_SOLVER_ANALYSIS_TECPLOT", False),
    ("sections", "_cp.txt", "EXPORT_ALL_SURFACE_SECTIONS", False),
    ("sectional_loads", "_sloads.txt", "EXPORT_SURFACE_SECTIONAL_LOADS", False),
    ("probes", "_probes.txt", "EXPORT_PROBE_POINTS", False),
    ("plots", "_plots.txt", "UNSTEADY_SOLVER_EXPORT_PLOTS", True),
    ("log", "_log.txt", "EXPORT_LOG", False),
)


def default_outputs(unsteady: bool, exports: Mapping[str, bool] | None = None) -> list[str]:
    """Return the output names a workflow row gets when it declares none.

    Every kind hangs off ``{name}``, the point's rendered stem, so the
    naming template decides the stem and this list decides the suffixes
    (PFS-2029.19); a steady row leaves out the plots file. ``exports`` is
    the pproc artifact's
    ``[exports]`` table (PFS-2029.14.02): a kind set to false is left
    out, a kind the table does not name is kept, so an empty table is
    the whole set, as the author's driver's ``files_to_save`` defaulted.
    """
    chosen = exports or {}
    return [
        f"{{name}}{suffix}"
        for kind, suffix, _, only_unsteady in EXPORT_KINDS
        if (unsteady or not only_unsteady) and chosen.get(kind, True)
    ]


def classify_outputs(names: Sequence[str]) -> dict[str, str]:
    """Map each export kind to the declared output name that carries its suffix.

    Longest suffix first, so ``_cp.txt`` is claimed by the sections kind
    before the loads kind can see a ``.txt``. A kind no name matches is
    absent from the result; a second name matching an already claimed
    kind is left unclassified rather than overwriting the first.
    """
    by_length = sorted(EXPORT_KINDS, key=lambda kind: -len(kind[1]))
    claimed: dict[str, str] = {}
    for name in names:
        lowered = str(name).lower()
        for kind, suffix, _, _ in by_length:
            if lowered.endswith(suffix) and kind not in claimed:
                claimed[kind] = str(name)
                break
    return claimed


#: THE FORCE-PLOT PARAMETERS BY THE SHORT NAME THE AUTHOR'S PLOT FILES USE, paired
#: with the PARAMETER the command takes and the UNITS it is sampled in
#: (PFS-2029.07.03). The plot's NAME is ``{short}_{group}``, which is how
#: the author's ``CL_MRP_TOTAL`` and ``FX_MRP_TOTAL`` were spelled, and the column
#: the author's PLOTS product carries.
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

#: The fluid parameters an unsteady fluid plot can sample, the command's
#: own enumeration (SRC-003 p.347).
FLUID_PLOT_PARAMETERS = (
    "CP_FREE",
    "CP_REF",
    "MACH",
    "VELOCITY",
    "VX",
    "VY",
    "VZ",
    "STATIC_PRESSURE_RATIO",
)

#: The family SELECTORS a pproc entry may write instead of a family name.
#: ``all`` is every boundary (the command's own -1 form); ``airframe`` is
#: every family that is not a blade; ``blades`` is every blade; ``each``
#: expands the entry into one per family the geometry carries, and
#: ``each_blade`` into one per blade, the entry's name carrying
#: ``{family}`` for the expansion. They are what let ONE artifact serve
#: the author's wing-body and the author's isolated-rotor configurations: the author's driver kept
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
            f"frame names one the run creates ({', '.join(PPROC_FRAMES)}, a rotor's "
            "ROTOR_MRP<k> or RotorAxis<k>) or one the setup's [[frames]] table defines; "
            "it is empty"
        )
    return value


def _the_radius_is_a_rotors(value: object) -> object:
    """Refuse the 0.14.0 spelling of the probe scale, naming the fix (FR-65).

    It warned and rewrote itself until the author's instruction of
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
    or a family name (the author's p001 of 2026-09-09 writes ``families =
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
    """One surface-section distribution: families, frame and planes."""

    model_config = ConfigDict(extra="forbid")

    families: Annotated[str | list[str], BeforeValidator(_check_family_selection)]
    frame: str = "MRP"
    planes: list[Plane] = Field(min_length=1)

    _frame_is_named = field_validator("frame")(_a_named_frame)

    @model_validator(mode="after")
    def _the_retired_selector_says_it_in_the_frame(self) -> SectionDistribution:
        """Warn as the plot group does, because it is the same retirement.

        The ledger promise and the changelog both say `each_blade` is read
        with a warning until 0.17.0, and the sections path gave none: a
        distribution is the OTHER consumer of the same selector, and the author's own
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
    """The ``[sections]`` table: NEW_SURFACE_SECTION_DISTRIBUTION per entry and plane."""

    model_config = ConfigDict(extra="forbid")

    count: int = Field(default=50, ge=1)
    plot_direction: Literal[1, 2] = 1
    include_symmetry: bool = False
    distributions: list[SectionDistribution] = Field(default_factory=list)


#: The FRAME KINDS a post-processing entry may cite instead of a frame's
#: name, and what each says the entry is ONE OF (FR-65, the author's design of
#: 2026-09-10). They are not frames the script creates: they name the
#: ROLE a frame plays for a rotor, and the expansion resolves each to that
#: rotor's own `<ALIAS>_SMRP`, `<ALIAS>_RMRP` or `<ALIAS>_RMRP<k>`.
#:
#: THERE IS NO `expand` KEY, and that is the whole design: a reader who
#: has said which frame a quantity is measured in has already said how
#: many of it there are. `SMRP` and `RMRP` are per ROTOR, because a rotor
#: has one of each; `LOCAL_AXIS` is per BLADE, because a blade has one.
EXPANDING_FRAMES = {"SMRP": "rotor", "RMRP": "rotor", "LOCAL_AXIS": "blade"}


class ForcePlotGroup(BaseModel):
    """One group of unsteady force plots: a name, a frame and the families summed.

    THE FRAME DECIDES HOW MANY GROUPS THIS ENTRY IS (FR-65). One citing
    `MRP` or a frame the reference declares is ONE group over the whole
    cited set; one citing `SMRP` or `RMRP` is one per ROTOR, in that
    rotor's own frame; one citing `LOCAL_AXIS` is one per BLADE. The
    `each` selector stays beside them, because one group per family in a
    COMMON frame is a reading no frame implies.
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
    """The ``[plots]`` table: which parameters, over which groups of families."""

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


class ProbeLine(BaseModel):
    """One line of fluid probes, from one vertex to another, sampled at ``points``."""

    model_config = ConfigDict(extra="forbid")

    start: tuple[float, float, float]
    end: tuple[float, float, float]


class ProbesSpec(BaseModel):
    """The ``[probes]`` table: fluid plots along lines, in a frame, per parameter.

    Each line is sampled at ``points`` vertices from ``start`` to ``end``,
    and every vertex gets one UNSTEADY_SOLVER_NEW_FLUID_PLOT per parameter,
    named ``{parameter}{n}`` with n counting vertices across the lines in
    the order written. ``scale`` says what the coordinates are in: metres,
    or ROTOR radii, which is how the author's nine lines were laid out over the
    disk of whichever rotor the reference named. The word was
    ``propeller_radius`` until 0.15.0 and is read with a warning until
    0.17.0: this release says ROTOR everywhere, because a lifter is not a
    rotor and the author's aircraft has eight of them.
    """

    model_config = ConfigDict(extra="forbid")

    frame: str = "ROTOR_MRP"
    parameters: list[str] = Field(default_factory=list)
    points: int = Field(default=25, ge=2)
    scale: Annotated[Literal["m", "rotor_radius"], BeforeValidator(_the_radius_is_a_rotors)] = "m"
    lines: list[ProbeLine] = Field(default_factory=list)

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


class ProductsSpec(BaseModel):
    """The ``[products]`` table: which post-processed CSV tables the campaign writes.

    ``polars``: one table per group of ``[groups]``, the coefficients of the
    group per point; ``sections``: one table per point from its sectional
    loads export; ``plots``: one table per unsteady point from its plots
    export. All CSV, one header line and one row per record.

    ``custom_polar_format``: beside every polar table, the same rows in the
    fixed-width text format the author's existing tooling opens
    (PFS-2014.01.01), ``<polar>_M<mach code>_g<group>.dat``. Off by
    default, since it is a second serialization of the polar table for
    one reader.
    """

    model_config = ConfigDict(extra="forbid")

    polars: bool = True
    sections: bool = True
    plots: bool = True
    custom_polar_format: bool = False

    @model_validator(mode="before")
    @classmethod
    def _the_former_name_of_the_custom_format(cls, data: object) -> object:
        """Read ``her_polar_format``, the key's name until 0.14.0, warning from the ledger."""
        if isinstance(data, dict) and "her_polar_format" in data:
            if "custom_polar_format" in data:
                raise ValueError(
                    "the [products] table states her_polar_format and custom_polar_format "
                    "both; they are one key, and custom_polar_format is its name"
                )
            warnings.warn(
                PPROC_HER_POLAR_FORMAT.message(), PyflightstreamDeprecationWarning, stacklevel=2
            )
            data = {**data, "custom_polar_format": data["her_polar_format"]}
            del data["her_polar_format"]
        return data


#: Frame names the package creates itself (PFS-2030.03.02); a setup may
#: not define one of these, because the row's rotation and the pproc
#: definitions resolve them to the package's own frames. The rotor run
#: type also creates ``ROTOR_MRP<k>``, ``RotorAxis<k>`` and ``BladeAxis<k>``,
#: one per record or blade family, refused by pattern below (the
#: interface lens of REL-0140: a setup defining ROTOR_MRP1 was shadowed).
RESERVED_FRAME_NAMES: tuple[str, ...] = ("MRP", "ROTOR_MRP")
RESERVED_FRAME_PATTERN = re.compile(r"^(ROTOR_MRP|ROTORAXIS|BLADEAXIS)\d+$")


#: The phases a raw command may be declared before (PFS-2033.01):
#: ``control`` for a line at the head of the script, since a control
#: command may appear anywhere, then the command database's own in the
#: order the script layer enforces, read off the enum rather than
#: restated (the architecture lens of REL-0140).
RAW_PHASES: tuple[str, ...] = (
    Phase.CONTROL.value,
    *(phase.value for phase in Phase if phase is not Phase.CONTROL),
)


class RawCommand(BaseModel):
    """One solver command a setup artifact states verbatim (PFS-2033.01).

    The author's design of 2026-09-09 (design/69): the user writes the command
    line as the solver reads it, arguments included, and names the phase
    it goes before; the builders emit it through the same emitter every
    curated helper uses, so the database's grammar, version, argument
    and phase checks apply to it unchanged. ``setup`` is the artifact
    the entry came from, bound by the workspace for the run record.
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
    """One custom coordinate system a setup artifact defines (PFS-2034.01).

    The author's design of 2026-09-09 (design/69): the row's rotation names an
    axis as ``<frame>-<X|Y|Z>``, and the frame is one the setup defined
    here or one the package creates (``MRP``; ``ROTOR_MRP`` on the rotor
    run types). The origin is in the geometry's own frame, the solver's
    reference frame, in the simulation's length unit, and the two axes
    are direction vectors in that frame; the third axis is the right-handed cross product,
    as :func:`pyflightstream.script.helpers.coordinate_frame` computes it.
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
        if name.upper() in RESERVED_FRAME_NAMES or RESERVED_FRAME_PATTERN.match(name.upper()):
            raise ValueError(
                f"the frame name {self.name!r} is one the package creates itself "
                f"({', '.join(RESERVED_FRAME_NAMES)}, and ROTOR_MRP<k>, RotorAxis<k> and "
                "BladeAxis<k> on a rotor row); choose another name"
            )
        return self


#: An axis letter with at most one leading sign, which is exactly what a
#: blade datum may be written as. It sits with its only user rather than
#: among the frame names, where an earlier edit put it between a doc
#: comment and the constants that comment describes (the technical
#: writing lens and the architecture lens, independently, 2026-09-10).
_AXIS_TOKEN = re.compile(r"^[+-]?[XYZ]$")


class BladeDatum(BaseModel):
    """Where blade one sits, and the axis its azimuth is measured from (FR-60).

    The author's answer of 2026-09-10, on the first reading of the use case: an
    azimuth ALONE carries a hidden convention, zero at which axis, that
    two people fill differently and nobody sees. So the datum is written
    beside it: ``{ azimuth_deg = 45.0, zero = "X" }``, the zero being an
    axis letter with an optional sign, refused when it is parallel to the
    axis the rotor turns about, because an angle measured from that axis
    locates nothing.
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

    The author's design of 2026-09-10. The block's NAME is an alias over
    everything the rotor owns, the union of :attr:`families_general` and
    :attr:`families_blades` in that order: what a row moves when it cites
    it, and what a group summing the rotor sums.

    THE NAME IS FREE, AND A TRAILING DIGIT IS FINE: the eight lifters of
    a four-a-side aircraft are ``LIFT_L1`` to ``LIFT_R4``. What it may
    not carry is ``_SMRP`` or ``_RMRP``, the radical of the frames the
    package builds from it (the static and rotating moment reference
    points of the rotor), because then a rotor and a frame spell the
    same. PFS-2035.02 said a name ending in a digit is refused, which was
    true of the frame names of 0.14.0 and would refuse the author's own study
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
        keeping at all is the author's open question of 2026-09-10.

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
    """

    model_config = ConfigDict(extra="forbid")

    alias: str
    axis: str
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
        if not isinstance(value, str):
            return value
        token = value.strip().upper()
        if token not in ("X", "Y", "Z"):
            raise ValueError(f"axis = {value!r} is not an axis; write X, Y or Z")
        return token

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
        if self.blade1.zero.lstrip("+-") == self.axis:
            raise ValueError(
                f"blade1 measures its azimuth from {self.blade1.zero}, which is parallel to "
                f"axis = {self.axis}, the axis the rotor turns about; an angle measured from "
                "that axis locates nothing. Choose one of the other two axes"
            )
        return self


class AliasCycleError(PyflightstreamError, ValueError):
    """An alias resolves through itself, and both sides are named (FR-59).

    The author's design of 2026-09-10 lets an alias name another alias, resolved to
    the end. That is what makes a cycle possible, so the reader refuses one
    rather than recursing: the message names the alias that closed the ring
    and the member that closed it, because a reader holding only one of the
    two names has to open the file to find the other.
    """


class PprocSpec(BaseModel):
    """The post-processing specification a matrix row's PPROC cell names.

    PFS-2029.07.01, the author's decision of 2026-09-02: the groups artifact IS the
    home of post-processing and is renamed pproc. Six tables. ``groups``
    is exactly what the groups file held, a number to the families it
    aggregates, and the polar tables are written per group of it; a
    member is resolved by :func:`select_group_members`, and an empty
    group is every family (the author's decision of 2026-09-09); ``exports`` says which of
    the eight export kinds a point writes, all of them unless a kind is
    set to false; ``sections``, ``plots`` and ``probes`` are the solver
    definitions the builders emit before the solver runs; ``products``
    says which post-processed files are written after it.
    """

    model_config = ConfigDict(extra="forbid")

    groups: dict[str, list[int | str]] = Field(default_factory=dict)
    exports: dict[str, bool] = Field(default_factory=dict)
    sections: SectionsSpec = Field(default_factory=SectionsSpec)
    plots: PlotsSpec = Field(default_factory=PlotsSpec)
    probes: ProbesSpec = Field(default_factory=ProbesSpec)
    products: ProductsSpec = Field(default_factory=ProductsSpec)
    #: How a blade family is told from the airframe: a regular expression
    #: over the family name. The author's were Blade1 to Blade6.
    blade_pattern: str = r"^Blade\d+$"
    #: The mesh families the base-region autodetect is allowed to consider
    #: (PFS-2029.10): one DETECT_BASE_REGIONS_BY_SURFACE per boundary of
    #: those families, after OPEN. Empty, the default, emits nothing; a
    #: row's BASE_REGIONS key overrides the artifact.
    base_regions: list[str] = Field(default_factory=list)

    @field_validator("exports")
    @classmethod
    def _known_export_kinds(cls, value: dict[str, bool]) -> dict[str, bool]:
        kinds = [kind for kind, _, _, _ in EXPORT_KINDS]
        unknown = sorted(set(value) - set(kinds))
        if unknown:
            raise ValueError(
                f"export kind(s) {', '.join(unknown)} are not among the eight a point "
                f"leaves: {', '.join(kinds)}"
            )
        if not value.get("loads", True):
            raise ValueError(
                "the loads table cannot be deselected: it is the export this package "
                "judges a run by"
            )
        return value

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
        """Return the output names a row naming this artifact declares."""
        return default_outputs(unsteady, self.exports)


#: The two selector words this release retires, each to its ledger entry.
#: They are the two that decide what a BLADE is from a pattern over the
#: family name; `all` and `each` guess nothing and stay (the author's decision of
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
    as the author's driver filtered its tables to the components it opened; an
    entry that resolves to nothing is an empty result and the caller
    skips it. ``all`` is the empty list standing for the command's own
    every-boundary form, which the caller spells as -1. An ALIAS of the
    row's setup (the author's decision of 2026-09-09) is read before the five
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
        # resolved. That is the only case the author's retirement is about: a
        # reference that declares `airframe` keeps working unchanged, which
        # is what every one of the author's does (the author's decision of 2026-09-10).
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
        # A bare word outside the five and the aliases is a family (the author's
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
#: shadowable, which is what the author's decision asked for.
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


#: The boundary aliases a setup preset defines, the author's decision of 2026-09-09:
#: a name to the boundary names or families it stands for. The type carries
#: the shape, so the setup artifact, the case and the run record hold one
#: rule between them rather than one validator at the artifact's door.
BoundaryAliases = Annotated[dict[str, list[str]], AfterValidator(_check_aliases)]


def resolve_alias(
    token: str, inventory: Sequence[str], aliases: Mapping[str, Sequence[str]] | None
) -> list[str] | None:
    """Resolve one cited name as an alias of the setup, or None when it is not one.

    The author's decision of 2026-09-09: an alias is a name the setup's
    ``[aliases]`` table gives to a list of boundary names or families,
    and it is read wherever a boundary is cited, the exact spelling
    first and case folded second, as a family is. Each member resolves as
    a name does, an exact name of the inventory first and a family (the
    label without its trailing number) second; a member the inventory
    does not carry is ignored, which is how one setup serves a wing-body
    and a rotor. The names come back in member order, each once; an
    alias every member of which is absent resolves to an empty list, and
    the caller says what that means for its key.

    THE AUTHOR'S DESIGN OF 2026-09-10 ADDED ONE THING and it changes this
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

    The author's design of 2026-09-10 (FR-59): a member may be a mesh family, a
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


def select_group_members(
    members: Sequence[int | str],
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[str]:
    """Resolve one ``[groups]`` entry's members against an inventory, in member order.

    The author's decisions of 2026-09-09 (PFS-2005.02). An EMPTY group is every
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
        chosen.extend(name for name in names if name not in chosen)
    return chosen


def point_tag(point: dict[str, float]) -> str:
    """Return the stable file-name tag of one sweep point.

    The tag encodes the point coordinates in a fixed axis order with
    signed fixed-width values, for example ``a+02.0_b+00.0``; it names
    the generated script and ends the ``run_id``.

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
    #: the frame the author's probe lines and rotor plots are defined in,
    #: and the rotor run turns about it. None when the reference declares
    #: no rotor.
    rotor_position_m: tuple[float, float, float] | None = None


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
        ``LAMINAR``, ``TRANSITIONAL``, or ``TURBULENT``.
    viscous_coupling : bool, optional
        Couple the boundary layer model to the potential solution.
        The solver's own words are accepted too (see below).
    max_threads : int, optional
        Parallel core count.
    timeout_s : float, optional
        Wall-clock limit for one point's solver process; enforced by
        the executor, not by FlightStream.
    solver_model : str, optional
        ``INCOMPRESSIBLE``, ``SUBSONIC_PRANDTL_GLAUERT``,
        ``TRANSONIC_FIELD_PANEL``, ``TANGENT_CONE`` or
        ``MODIFIED_NEWTONIAN``; an argument of ``INITIALIZE_SOLVER``.
        None leaves the emitter's own default, which is
        ``INCOMPRESSIBLE``.
    wall_collision_avoidance : bool, optional
        The other ``INITIALIZE_SOLVER`` argument a preset states.
    convergence_iterations : int, optional
        Iterations the residual must hold under the threshold before
        the solver calls the run converged.
    minimum_cp : float, optional
        Floor applied to the pressure coefficient.
    farfield_layers : int, optional
        Farfield layer count.
    mesh_induced_wake_velocity, unsteady_pressure_and_kutta,
    wake_on_wake_induction, additional_wake_relaxation,
    reynolds_averaged_drag : bool, optional
        Advanced-settings toggles; the solver's own ENABLE and DISABLE
        are read as well as Python booleans.
    solver_stabilization : float, optional
        Stabilization strength. A preset that gates it with a separate
        ENABLE/DISABLE key resolves the pair before it arrives here:
        disabled means None, not zero.
    wake_termination_revolutions : float, optional
        Wake termination stated in revolutions, negative counting
        backwards from the end of the run. Converted to time steps by
        the rotor builder, which is the only layer that knows how many
        steps a revolution is.

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
    #: The four settings the author's own scripts state and 0.10.1 did not
    #: (FR-54, PFS-2030.03.*). Each is None unless a preset states it, so a
    #: preset that says nothing emits nothing and every earlier golden holds.
    #: symmetry_loads reaches SET_ANALYSIS_SYMMETRY_LOADS AS STATED, the author's
    #: decision of 2026-09-02 (PFS-2028.05); an absent key stays silent.
    symmetry_loads: SolverToggle | None = None
    #: SET_SIGNIFICANT_DIGITS: how many decimals the solver prints in every
    #: export. The author's scripts state 7; the solver's own default prints 4.
    significant_digits: int | None = Field(default=None, ge=1)
    #: SOLVER_SET_REF_VELOCITY in m/s. None means the builders state the
    #: freestream velocity, which is what the coefficients are normalised
    #: on unless a preset says otherwise (PFS-2030.03.01).
    reference_velocity_m_per_s: float | None = Field(default=None, gt=0.0)
    #: SET_VORTICITY_DRAG_BOUNDARIES written as FAMILY NAMES; the builder
    #: resolves them through the opened geometry's inventory and leaves out
    #: the families the geometry does not carry, as the author's driver did
    #: (PFS-2030.03.03). An empty result is refused.
    vorticity_drag_families: list[str] | None = None
    #: The LOAD_SOLVER_INITIALIZATION argument of OPEN. None means DISABLE,
    #: which is what the author's scripts wrote on every open: a saved simulation
    #: may carry an initialised solver, and loading it would start the run
    #: from a state the row never declared (PFS-2030.03.01).
    load_solver_initialization: SolverToggle | None = None


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
        execution directory; the loop collects them into ``raw/`` and
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
    geometry: str | None = None
    sweep: SweepAxis
    flight_condition: dict[str, float] = Field(default_factory=dict)
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
    #: The boundary aliases the row's REFERENCE declares (FR-59, the author's
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
    #: The boundary order a sidecar beside the geometry states
    #: (PFS-2029.06.03), bound by the workspace; the builder refuses the
    #: run when the file's own mesh block disagrees with it.
    inventory: tuple[str, ...] | None = None
    #: Where the boundary inventory came from: ``sidecar``, ``mesh_block``
    #: or None when the geometry declares none.
    inventory_source: str | None = None
    point: dict[str, float] = Field(default_factory=dict)
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
        ``campaign.toml`` surface (the author's decision of 2026-09-08).

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
        ``scripts/``, collect into the same ``raw/``, and produce colliding
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
