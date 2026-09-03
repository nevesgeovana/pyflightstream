"""Input-artifact library of the managed campaign workspace.

Pipeline role: organizes the reusable inputs of a campaign the same
way the workspace organizes its outputs. A support library under
``inputs/`` holds one declarative artifact per file, referenced by a
stable id (the file name stem), so a campaign line can select its
reference data, solver preset, boundary groups, geometry, and profile
by id instead of by path; the pattern is translated from the author's
research workflow. Artifacts are TOML, never executable code:
they are validated by pydantic models at load time and fail with a
didactic message naming the file and the available ids.

AN ID OF A CODED KIND DECLARES THAT KIND, since 2026-08-19
(PFS-2009.01, PFS-2009.03, a BREAK carried by v0.8.0). A reference id
begins with ``r``, a setup id with ``s``, a group id with ``e``, so
``r003``, ``s003`` and ``e003`` are three ids rather than one number
meaning three files. Before that, the three folders each held a
``003.toml`` and a number mistyped between the REF, SET and ENTRY
columns of a run matrix resolved to another artifact with no signal at
all. Geometries and profiles keep bare stems, because their ids are the
names of files the user staged and a letter rule there would refuse a
mesh for being called what it is called.

The library tree, created by ``CampaignWorkspace.init``:

- ``inputs/references/<id>.toml``: reference data for coefficient
  normalization and propeller description (SI units in the field
  names: m, m^2, deg). The id begins with ``r``.
- ``inputs/setups/<id>.toml``: a named solver-setup preset, a free
  key-value table for now; the loader keeps the raw table verbatim so
  a later formal solver-setup model can consume it unchanged. The id
  begins with ``s``.
- ``inputs/pproc/<id>.toml``: post-processing, whose ``[groups]`` table maps a group
  name to a list of boundary labels or indices, stored verbatim. The id
  begins with ``e``, after the ENTRY column that carries it.
- ``inputs/geometries/``: staged geometry files of any extension,
  registered by file name; the id is the stem.
- ``inputs/profiles/``: input profile files (for example actuator
  thrust distributions), registered by file name.
- ``inputs/executables.toml``: the build registry, mapping a
  FlightStream build id to its executable path; an explicit override
  path bypasses the registry, and that override is the only way to run
  an unregistered build (the MANUAL mode of the run matrix). An entry
  is a bare path string, or a table carrying that path and, optionally,
  the FlightStream version the build's scripts are emitted under
  (:func:`resolve_build`).
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

# InputArtifactError is DEFINED in `_errors`, below every layer, and
# re-exported here and from `pyflightstream.workspace`, which is the name
# a user catches and the one every docstring in this module names. It
# moved there on 2026-08-19 (OPS-2007.02.01) because the layers that bind
# a run matrix to this library catch it too, and reaching up for the type
# alone is what the five call-time imports of `cases/matrix.py` were.
# Nothing about the class changed: same two bases, same three attributes,
# same public spelling.
from pyflightstream._errors import InputArtifactError
from pyflightstream.cases import PprocSpec

# DOWNWARD, and the two imports in this module that leave the workspace
# layer: `cases` sits below `workspace` in the house order, and the
# migration at the foot of this file has to rewrite the REF, SET and
# ENTRY cells of a run matrix in the same call that renames the library
# files. The matrix FORMAT is the cases layer's to own, so the cell
# rewrite is asked of it rather than reimplemented here, which is what
# would put a second reader of the pipe-delimited layout in the package
# (PFS-2009.03).
from pyflightstream.cases.matrix import CODE_COLUMNS, rewrite_codes
from pyflightstream.script.helpers import RotationSense

# DOWNWARD as well, and the lowest layer of the stack: `versions` sits
# below `commands`, which sits below everything else. It is imported so a
# version DECLARED in the build registry is checked against the version
# registry at the moment it is read, rather than at the moment a run
# emits a script under it. The sister module `wake_edges` already reaches
# down to `commands` for the same kind of reason (PFS-2009.05).
from pyflightstream.versions import (
    AmbiguousVersionAliasError,
    UnknownVersionError,
    resolve,
)

INPUT_KINDS = ("geometries", "references", "setups", "pproc", "profiles")
EXECUTABLES_FILE = "executables.toml"

#: Every key a TABLE-valued entry of the build registry carries, and the
#: only ones read. A key outside this tuple is REFUSED naming itself
#: rather than ignored: a silently dropped ``verison`` leaves a registry
#: that looks correct and a run emitted under the campaign default, and
#: the two look identical from the manifest (PFS-2009.05).
EXECUTABLE_ENTRY_KEYS = ("path", "version")

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: The letter a coded artifact id begins with, so the id DECLARES its
#: kind and a mistyped number cannot resolve to another artifact's file.
#:
#: Only the three CODED kinds are here, and their absence from the other
#: two is the rule rather than an omission. A reference, a setup and a
#: group are addressed by ids the author writes in the REF, SET and ENTRY
#: cells of a run matrix, so a bare ``003`` names three different files
#: in three folders and a typo between them is silent. A geometry or a
#: profile is addressed by the STEM OF A FILE THE USER STAGED, so a
#: letter rule there would refuse a mesh for being called what it is
#: called.
#:
#: ``e`` for groups, not ``g``: the matrix column that carries a group id
#: is ENTRY, which is the word the author's own files use, and the letter
#: follows the column a user types rather than the model's class name.
KIND_LETTERS = {"reference": "r", "setup": "s", "pproc": "p"}

#: The library folder each coded kind lives in, for the refusal below.
_KIND_DIRECTORIES = {"reference": "references", "setup": "setups", "pproc": "pproc"}

#: The matrix column that carries each coded kind's id. It is the pair
#: the migration walks: rename the file in the kind's folder AND rewrite
#: the cell of the column that names it, in the same call, because doing
#: one without the other is what half-resolves (PFS-2009.03).
KIND_COLUMNS = {"reference": "REF", "setup": "SET", "pproc": "PPROC"}


class PointXyz(BaseModel):
    """One point in the simulation geometry reference frame, meters.

    Attributes
    ----------
    x_m : float
        X coordinate in m.
    y_m : float
        Y coordinate in m.
    z_m : float
        Z coordinate in m.
    """

    model_config = ConfigDict(extra="forbid")

    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0


class PropellerReference(BaseModel):
    """Propeller description block of a reference artifact.

    Attributes
    ----------
    radius_m : float
        Propeller tip radius in m; must be positive.
    hub_radius_m : float, optional
        Hub (root cutout) radius in m.
    n_blades : int
        Blade count; at least 1.
    pitch_deg : float, optional
        Blade pitch angle in deg.
    toe_deg : float, optional
        Toe (in-plane inclination) angle of the propeller axis in deg.
    position : PointXyz
        Hub position in the simulation geometry frame, m.
    rotation : RotationSense
        Sense of rotation about the propeller axis, viewed from behind
        the aircraft looking forward, ``"clockwise"`` or
        ``"counterclockwise"``. Record the convention with the geometry
        so the sign of the swirl is never guessed.

        The domain is not declared here. It is
        :data:`pyflightstream.script.helpers.RotationSense`, imported
        from the layer that consumes it, so the vocabulary has one home
        rather than two homes held together by a test.
    blade_travel : {"inboard_up", "inboard_down"}, optional
        The SAME physical fact in the vocabulary a vendor datasheet
        prints: where the blade nearest the fuselage travels, stated in
        the aircraft body frame with the aircraft upright. It describes
        the blade at its inboard azimuth, not the disc as a whole.

        Written with an underscore, and a datasheet that prints
        ``inboard-up``, ``Inboard Up`` or ``INBOARD_UP`` is accepted:
        case, hyphens and whitespace are folded before the domain is
        checked. ``rotation`` is folded the same way, for the same
        reason, since both are transcribed off the same page.

        IT DOES NOT APPLY TO A CENTRELINE PROPELLER. A nose-mounted
        tractor has no blade nearer the fuselage than any other, so the
        field has no answer for that configuration and is left out;
        ``rotation`` alone describes it.

        It is a separate field rather than two more values of
        ``rotation`` because the two vocabularies are not
        interchangeable. This one is side-independent, so the left and
        the right propeller of a symmetric pair carry the same word,
        which is exactly why it cannot be converted to the
        viewed-from-behind sense without knowing which side this
        propeller is on. Keeping them apart makes "which vocabulary"
        a static fact of the field rather than something every consumer
        re-derives from a string.
    rpm_sign_installed : {-1, 1}, optional
        Measured sign of the rotor speed about the propeller's rotation
        axis, for the INSTALLED meshes of this configuration.
        Dimensionless. The axis is the one the case emits its rotary
        motion about and is a per-case argument, so this field states a
        sign and never an axis.
    rpm_sign_isolated : {-1, 1}, optional
        The same for the ISOLATED meshes, which may be the opposite hand
        of the installed ones and then take the opposite sign for the
        same published sense. The one campaign this model has been
        checked against was such a case, which is why the pair exists;
        how common it is across campaigns is not something this
        repository has measured.

    Notes
    -----
    NOTHING IN THIS PACKAGE READS THE PROPELLER BLOCK, and that is said
    here rather than left to be discovered. Not the signs, and not
    ``rotation``, ``blade_travel``, ``radius_m``, ``n_blades`` or
    ``position`` either: the whole block is RECORDED, and setting any of
    it changes no emitted script on its own.

    AND THE ARTIFACT DOES NOT REACH A RECIPE, which is the part that
    would otherwise be discovered the expensive way.
    :func:`pyflightstream.workspace.matrix.resolve_matrix` narrows this
    artifact to a :class:`pyflightstream.cases.ReferenceData` of area and
    length for the case, and a recipe is called with the case and the
    script. The full artifact survives only in ``ResolvedMatrix``
    ``.references``, keyed by the matrix REF code, so a recipe that wants
    a sign reads it from the workspace or the resolved matrix it closes
    over, and ``case.reference.propeller`` does not exist.

    Which of the two signs applies is likewise the recipe's knowledge and
    not the artifact's: nothing in the library records which geometries
    are the installed meshes and which the isolated ones.

    THE SENSE DOES NOT DETERMINE THE SIGN OF THE ROTOR SPEED, which is
    why those fields exist and are not derived. Going from a published
    sense to the number a motion command takes needs the rotor axis, the
    side of the aircraft, and the handedness of the mesh actually
    loaded; a mirrored mesh of the same aircraft takes the opposite sign
    for the same published sense.

    Read that against
    :data:`pyflightstream.script.helpers.ROTATION_SENSE_SIGN`, which DOES
    derive a sign from a sense and is not contradicted here: it signs the
    AZIMUTH INCREMENT, which way round the disc the blades are numbered,
    and that is a different quantity from the sign of the rotor speed.
    Two different signs, one of them derivable and one of them measured.

    Both sign fields are optional, and absence means the campaign has not
    established them rather than that the sign is ``+1``. NOT ESTABLISHED
    AND NOT APPLICABLE ARE THE SAME SILENCE, deliberately: a
    configuration with no isolated meshes leaves ``rpm_sign_isolated``
    out exactly as a campaign that never measured it does, and the model
    does not distinguish them. Distinguishing them would be a third
    value rather than a second field, and it is not built.

    The closed domain is also what makes assignment checked rather than
    merely loading checked: this model sets ``validate_assignment``, so
    ``propeller.rpm_sign_installed = 0`` is refused after loading and not
    only at it. It is not frozen, because a campaign may legitimately
    record a sign it measured after reading the artifact.

    One asymmetry worth a sentence, because it reads as an oversight
    otherwise: ``n_blades`` accepts the string ``"3"`` by pydantic's
    ordinary coercion while a sign field refuses ``1.0``. The strictness
    is deliberate and local to the signs, whose whole content is one bit
    that must have been measured. That promise is
    what closes them to COERCION as well as to value: ``true`` and
    ``1.0`` are refused rather than read as the integer ``1``, because a
    boolean that becomes a measured positive sign is the package
    deciding the physical fact this field exists to record. Without it
    the domain was also asymmetric in a way that modelled nothing:
    ``true`` was admitted as ``+1`` and ``false`` refused for being
    outside the domain.

    ``blade_travel`` and the two sign fields were added at 0.8.0
    (PFS-2009.02), after the shipped vocabulary was checked against a
    real campaign for the first time and refused that campaign's
    reference artifact on all three. ``rotation`` itself is unchanged,
    so an artifact written before 0.8.0 validates unaltered.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    #: OPTIONAL SINCE 0.11.0 (PFS-2029.05): the diameter at the artifact's
    #: root is the length the package reads (the advance ratio, the probe
    #: lines), and a radius beside it is the same fact twice; a file that
    #: states both is checked for agreement and a file stating the radius
    #: alone is refused naming the diameter key.
    radius_m: float | None = Field(default=None, gt=0.0)
    hub_radius_m: float | None = Field(default=None, ge=0.0)
    n_blades: int = Field(ge=1)
    pitch_deg: float | None = None
    toe_deg: float | None = None
    position: PointXyz = Field(default_factory=PointXyz)
    rotation: RotationSense
    blade_travel: Literal["inboard_up", "inboard_down"] | None = None
    rpm_sign_installed: Literal[-1, 1] | None = None
    rpm_sign_isolated: Literal[-1, 1] | None = None

    @field_validator("rotation", "blade_travel", mode="before")
    @classmethod
    def _the_vocabulary_is_read_the_way_a_datasheet_prints_it(
        cls, value: object, info: ValidationInfo
    ) -> object:
        """Fold case, hyphens and whitespace before the domain is checked.

        BOTH vocabularies, not one. The first version folded
        ``blade_travel`` alone, on the ground that its value is
        transcribed off paper, and left ``rotation`` refusing
        ``Clockwise`` and ``counter-clockwise`` with pydantic's bare
        literal error. They record the same fact, off the same
        datasheet, and ``rotation`` is the REQUIRED one, so the strict
        field was the one a reader meets first. It is also the field
        this model's own missing-value refusal tells them to add.

        Runs of whitespace collapse rather than a single space,
        because a value pasted out of a PDF arrives with two.
        """
        if not isinstance(value, str):
            return value

        def squash(word: str) -> str:
            """Lower case with every separator removed.

            Comparing SQUASHED forms on both sides is what lets one rule
            serve two vocabularies whose own spelling differs. Folding
            separators to an underscore, which is what this did first,
            reads ``Inboard Up`` correctly and turns ``Counter-Clockwise``
            into ``counter_clockwise``, a word no domain here contains:
            one vocabulary joins its parts with an underscore and the
            other with nothing at all.
            """
            return "".join(character for character in word.lower() if character.isalnum())

        # THE DOMAIN IS READ OFF THE FIELD, not restated here. Written as a
        # literal set this validator was a second declaration of one
        # vocabulary, exactly what the rotation sense was corrected for one
        # commit earlier: widening the annotation then changed nothing and
        # broke nothing, so the two could drift apart in silence.
        # TWO ANNOTATION SHAPES, flattened here rather than assumed. This
        # field is `Literal[...]` and `blade_travel` is `Literal[...] | None`,
        # so the optional arm nests the words one level deeper. Written for
        # the optional shape alone, this produced an EMPTY permitted set for
        # `rotation` and a refusal reading "this field takes ." with nothing
        # after it, which the first run printed.
        permitted = set()
        for arm in get_args(cls.model_fields[info.field_name].annotation):
            permitted.update(get_args(arm) or ({arm} if isinstance(arm, str) else ()))
        canonical = {squash(word): word for word in permitted}
        if squash(value) in canonical:
            return canonical[squash(value)]
        # The EXAMPLE is built from this field's own domain. Written with
        # a fixed pair of examples, the message showed one spelling from
        # each vocabulary, so a blade_travel refusal offered the word
        # "clockwise" to a reader who had just been told the field does
        # not take it.
        sample = sorted(permitted)[0]
        raise ValueError(
            f"{info.field_name} is {value!r}, and this field takes "
            f"{' or '.join(sorted(permitted))}. Case, hyphens and whitespace are "
            f"folded, so {sample.replace('_', '-').title()} is read as written; "
            "anything else is refused rather than guessed"
        )

    @model_validator(mode="before")
    @classmethod
    def _the_sense_is_required_and_the_other_vocabulary_is_not_a_substitute(
        cls, data: object
    ) -> object:
        """Refuse a propeller with no ``rotation`` in words, not in codes.

        The campaign this model was widened for records the sense in the
        INBOARD vocabulary, so a reader who fills in ``blade_travel``
        and stops is the expected case rather than a careless one. What
        they met was pydantic's ``Field required``, which names no cause
        and no remedy, while the message that routes them lives one
        layer down in a function they may never call.

        ONE TRADE-OFF, ACCEPTED RATHER THAN OVERLOOKED. Raising here
        aborts the whole model validation, so an artifact whose
        propeller block is wrong in more than one way at once reports
        this cause alone, where pydantic would have reported every
        cause. A reader who fixes the named one and meets a second
        refusal on the next load learns less. It is accepted because the
        alternative loses the message entirely for the case this exists
        to serve.

        A MAPPING RATHER THAN A DICT, deliberately: the TOML loader
        yields a dict, and a programmatic caller handing in any other
        mapping fell straight through to the refusal this replaces.
        """
        if not isinstance(data, Mapping) or "rotation" in data:
            return data
        if "blade_travel" in data:
            raise ValueError(
                "the propeller records blade_travel and no rotation. They are the same "
                "physical fact in two vocabularies and the package cannot convert "
                "between them: blade_travel is side-independent, so the left and the "
                "right propeller of a pair carry the same word, and turning it into a "
                "sense viewed from behind needs the side of the aircraft, which no "
                "field of this artifact records. You know the side, so the conversion "
                "is yours to make and it is mechanical: standing behind the aircraft "
                "looking forward, the inboard blade of a RIGHT-side propeller sits at "
                "the 9 o'clock position of its disc, and travelling up from there is "
                "travelling towards 12, which is clockwise. So inboard_up on the right "
                "side is clockwise, inboard_down on the right side is counterclockwise, "
                "and a left-side propeller is the mirror of both. Add the rotation you "
                "get from that, alongside the blade_travel you have"
            )
        raise ValueError(
            "the propeller records no rotation. The sense of rotation is clockwise or "
            "counterclockwise viewed from behind the aircraft looking forward, and it "
            "decides the sign of the swirl and which way round the disc the blades are "
            "numbered, so there is no safe default to guess"
        )

    @field_validator("rpm_sign_installed", "rpm_sign_isolated", mode="before")
    @classmethod
    def _sign_is_an_integer_and_not_something_that_coerces_to_one(
        cls, value: object, info: ValidationInfo
    ) -> object:
        """Refuse a value that would become a sign nobody measured.

        Runs BEFORE the literal domain, so a value of the right type and
        the wrong magnitude still meets the domain's own message.
        """
        if value is None or type(value) is int:
            return value
        raise ValueError(
            f"{info.field_name} is {value!r}, of type {type(value).__name__}, and a "
            "measured sign is written as a Python int, 1 or -1. A bool, a float or "
            "a number from an array library would be coerced to a sign this campaign "
            f"never measured, so convert the {type(value).__name__} to an int if it "
            "really is one. An unmeasured sign is recorded by leaving the field out"
        )


class ReferenceArtifact(BaseModel):
    """Reference data of one configuration (``inputs/references/<id>.toml``).

    Attributes
    ----------
    area_m2 : float
        Reference area S_ref in m^2; must be positive.
    chord_m : float
        Reference chord c_ref in m; must be positive.
    span_m : float
        Reference span b_ref in m; must be positive.
    propeller_diameter_m : float, optional
        Propeller diameter D in m; must be positive.

        IT LIVES HERE, BESIDE THE OTHER THREE LENGTHS, and not in
        :class:`PropellerReference`, which is the natural-looking home
        and the wrong one. The propeller block is RECORDED metadata of which
        this package reads one field, the position (0.11.0, the PROP_MRP
        frame); the diameter is a DIVISOR of
        published numbers, exactly like the area and the chord. It sets
        the rotor speed a row asks for by advance ratio
        (``n = V / (J D)``) and it normalises the propeller coefficients
        (``C_T = T / (rho n^2 D^4)``). A quantity a run is computed FROM
        belongs with the reference lengths, where a reader looking for
        "what were the coefficients divided by" finds all of them in one
        place.

        Optional because a configuration with no propeller has no
        diameter, and stating a placeholder would be worse than stating
        nothing. A row asking for an advance ratio without it is refused
        naming this field.
    moment_point : PointXyz
        Moment reference point in the simulation geometry frame, m.
    propeller : PropellerReference, optional
        Propeller block, present for propulsive configurations.
    """

    model_config = ConfigDict(extra="forbid")

    area_m2: float = Field(gt=0.0)
    chord_m: float = Field(gt=0.0)
    span_m: float = Field(gt=0.0)
    propeller_diameter_m: float | None = Field(default=None, gt=0.0)
    moment_point: PointXyz = Field(default_factory=PointXyz)
    propeller: PropellerReference | None = None

    @model_validator(mode="after")
    def _one_propeller_length(self) -> ReferenceArtifact:
        """Refuse a radius that disagrees with the diameter, or stands alone.

        PFS-2029.05. ``propeller_diameter_m`` is the length the package
        reads; ``propeller.radius_m`` is optional and, when stated, must be
        half of it, so a file cannot carry two propellers. A radius with no
        diameter is refused naming the key that carries the fact.
        """
        propeller = self.propeller
        if propeller is None or propeller.radius_m is None:
            return self
        diameter = self.propeller_diameter_m
        if diameter is None:
            raise ValueError(
                f"[propeller] states radius_m = {propeller.radius_m} and the artifact "
                "states no propeller_diameter_m. The diameter is the length this package "
                "reads (the advance ratio, the probe lines), so state "
                f"propeller_diameter_m = {2 * propeller.radius_m} at the top level; the "
                "radius may then be dropped."
            )
        if abs(diameter - 2 * propeller.radius_m) > 1e-9 * max(1.0, diameter):
            raise ValueError(
                f"propeller_diameter_m = {diameter} and [propeller] radius_m = "
                f"{propeller.radius_m} disagree: twice the radius is "
                f"{2 * propeller.radius_m}. One propeller has one length; fix one of "
                "the two, or drop the radius, which the package does not read."
            )
        return self


class SetupArtifact(BaseModel):
    """A named solver-setup preset (``inputs/setups/<id>.toml``).

    The preset is a free key-value table for now: the file's top-level
    TOML table is kept verbatim in :attr:`settings`, so the future
    formal solver-setup model can consume the same raw table without a
    file format change.

    Attributes
    ----------
    settings : dict
        The raw TOML table of the preset, verbatim (keys are setting
        names, values are TOML scalars, arrays, or nested tables).
    """

    model_config = ConfigDict(extra="forbid")

    settings: dict[str, Any]


class PprocArtifact(PprocSpec):
    """The post-processing artifact (``inputs/pproc/<id>.toml``).

    PFS-2029.07.01, her decision of 2026-09-02: the groups artifact IS the
    home of post-processing and is renamed. The file carries six tables,
    every one optional: ``[groups]`` exactly as the groups file held it,
    a name to the boundary labels or 1-based indices it aggregates;
    ``[exports]`` which of the eight export kinds a point writes;
    ``[sections]``, ``[plots]`` and ``[probes]`` the solver definitions
    the builders emit; ``[products]`` the post-processed files written
    after the run. Group members are stored verbatim and resolved by the
    script layer at emission time, as before. The shape is
    :class:`pyflightstream.cases.PprocSpec`; this class is the file.
    """


def available_ids(directory: Path, suffix: str | None = ".toml") -> list[str]:
    """List the artifact ids present in one library directory.

    Parameters
    ----------
    directory : Path
        One ``inputs/<kind>/`` directory.
    suffix : str, optional
        Restrict to files with this extension (default ``".toml"``);
        None lists every file (geometries and profiles register any
        extension).

    Returns
    -------
    list of str
        Sorted file name stems; empty when the directory is missing.
    """
    if not directory.is_dir():
        return []
    stems = {
        path.stem
        for path in directory.iterdir()
        if path.is_file() and (suffix is None or path.suffix == suffix)
    }
    return sorted(stems)


def is_valid_artifact_id(artifact_id: str) -> bool:
    """Whether a string is well formed as an input-library id.

    THE ONE HOME OF THE SHAPE RULE, published rather than left private
    because two layers need to ask it and the alternative was reaching
    for the private pattern across a module boundary, which a tier 1
    guard refuses by design: an underscore-private name crossing into a
    public sibling is a layer boundary crossed for a helper.

    An id is a file name STEM: letters, digits, dot, underscore or
    hyphen, beginning with a letter or a digit. It is never a path, and
    the leading-character half is the part a caller cannot infer from the
    permitted set, which is why a refusal that merely lists the permitted
    characters sends an author back to make the same mistake.

    Parameters
    ----------
    artifact_id : str
        The candidate id, as the matrix cell or the caller wrote it.

    Returns
    -------
    bool
        True when the shape is acceptable. It says nothing about whether
        anything is STAGED under that id, which is
        :func:`available_ids`'s question.

    Examples
    --------
    >>> is_valid_artifact_id("wing_clean")
    True
    >>> is_valid_artifact_id("blade.v2")
    True
    >>> is_valid_artifact_id("_scratch")
    False
    """
    return bool(_ID_PATTERN.match(artifact_id))


def _check_id(artifact_id: str, kind: str) -> None:
    """Refuse ids that could not have come from a library file name.

    Two rules, and the second applies to the coded kinds alone. An id is
    a file name stem, and a reference, setup or group id also DECLARES
    its kind with a leading letter (:data:`KIND_LETTERS`), so a number
    mistyped between the REF, SET and ENTRY cells of a run matrix is
    refused instead of resolving to another artifact's file.
    """
    if not is_valid_artifact_id(artifact_id):
        raise InputArtifactError(
            f"{kind} id {artifact_id!r} is not a valid artifact id: ids are file "
            "name stems of letters, digits, dot, underscore or hyphen, beginning "
            "with a letter or a digit. The id selects a file inside the library; it "
            "is never a path.",
            kind=kind,
            artifact_id=artifact_id,
        )
    letter = KIND_LETTERS.get(kind)
    # Case-insensitive on purpose: the id is a file stem, and the two
    # spellings name the same file on a case-insensitive file system, so
    # refusing one of them would refuse a file that resolves.
    if letter is not None and artifact_id[:1].lower() != letter:
        directory = _KIND_DIRECTORIES[kind]
        raise InputArtifactError(
            f"{kind} id {artifact_id!r} does not declare its kind: a {kind} id begins "
            f"with {letter!r} (for example {letter}003), so a number mistyped between "
            "the REF, SET and ENTRY columns cannot resolve to another artifact's file. "
            f"Rename the library file to inputs/{directory}/{letter}{artifact_id}.toml "
            "and the matrix cell that names it in the same edit; the letter is part of "
            "the id, not a prefix the library adds or strips. A library written before "
            "v0.8.0 is migrated in ONE call rather than one rename per artifact: "
            "pyflightstream.workspace.migrate_input_ids(inputs_dir, matrices, "
            "apply=True) renames every file and rewrites the REF, SET and ENTRY cells "
            "of the matrices you hand it, together.",
            kind=kind,
            artifact_id=artifact_id,
        )


def _miss(
    kind: str, artifact_id: str, directory: Path, suffix: str | None = ".toml"
) -> InputArtifactError:
    """Build the didactic not-found refusal listing what exists.

    Returns the exception (structured: kind, artifact_id, available)
    instead of a bare message, so every miss site raises with the same
    attributes.
    """
    ids = available_ids(directory, suffix)
    if ids:
        listing = f"available {kind} ids: {', '.join(ids)}"
    else:
        listing = (
            f"the library directory {directory} holds no {kind} artifacts yet "
            "(create it with CampaignWorkspace.init or pyfs-workspace init, then "
            "add the artifact file)"
        )
    return InputArtifactError(
        f"no {kind} artifact with id {artifact_id!r}; {listing}",
        kind=kind,
        artifact_id=artifact_id,
        available=tuple(ids),
    )


def _load_toml(path: Path, kind: str) -> dict[str, Any]:
    """Read one TOML artifact file, naming the file on a syntax error."""
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise InputArtifactError(
            f"the {kind} artifact {path} is not valid TOML: {error}. Artifacts are "
            "declarative TOML files, one artifact per file."
        ) from error


def _validate(model: type[BaseModel], data: dict[str, Any], path: Path, kind: str) -> BaseModel:
    """Validate one artifact table, naming the file on a model error."""
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise InputArtifactError(
            f"the {kind} artifact {path} does not validate: {error}"
        ) from error


def resolve_reference(inputs_dir: Path, artifact_id: str) -> ReferenceArtifact:
    """Load the reference artifact one id names.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    artifact_id : str
        File name stem under ``references/``.

    Returns
    -------
    ReferenceArtifact
        The validated reference data (SI units in the field names).

    Raises
    ------
    InputArtifactError
        Unknown id (the message lists the available ids) or a file
        that does not validate.
    """
    _check_id(artifact_id, "reference")
    directory = Path(inputs_dir) / "references"
    path = directory / f"{artifact_id}.toml"
    if not path.is_file():
        raise _miss("reference", artifact_id, directory)
    data = _load_toml(path, "reference")
    return _validate(ReferenceArtifact, data, path, "reference")


def resolve_setup(inputs_dir: Path, artifact_id: str) -> SetupArtifact:
    """Load the solver-setup preset one id names.

    The file's top-level table is kept verbatim in
    :attr:`SetupArtifact.settings`; see the module docstring for why.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    artifact_id : str
        File name stem under ``setups/``.

    Returns
    -------
    SetupArtifact
        The preset with its raw settings table.

    Raises
    ------
    InputArtifactError
        Unknown id (the message lists the available ids) or invalid
        TOML.
    """
    _check_id(artifact_id, "setup")
    directory = Path(inputs_dir) / "setups"
    path = directory / f"{artifact_id}.toml"
    if not path.is_file():
        raise _miss("setup", artifact_id, directory)
    data = _load_toml(path, "setup")
    return _validate(SetupArtifact, {"settings": data}, path, "setup")


def resolve_pproc(inputs_dir: Path, artifact_id: str) -> PprocArtifact:
    """Load the post-processing artifact one id names.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    artifact_id : str
        File name stem under ``pproc/``.

    Returns
    -------
    PprocArtifact
        The validated artifact, group members stored verbatim.

    Raises
    ------
    InputArtifactError
        Unknown id (the message lists the available ids), a file that
        does not validate, or a file in the shape the groups artifact
        had, which is named with the command that moves it.
    """
    _check_id(artifact_id, "pproc")
    directory = Path(inputs_dir) / "pproc"
    path = directory / f"{artifact_id}.toml"
    if not path.is_file():
        raise _miss("pproc", artifact_id, directory)
    data = _load_toml(path, "pproc")
    bare = sorted(key for key, value in data.items() if isinstance(value, list))
    if bare:
        raise InputArtifactError(
            f"the pproc artifact {path} carries group(s) {', '.join(bare)} at the top "
            "level, which is the shape the groups artifact had before 0.11.0. A pproc "
            "file holds its groups under a [groups] table, beside [exports], "
            "[sections], [plots], [probes] and [products]; "
            "pyflightstream.workspace.migrate_groups_to_pproc moves a groups file into "
            "that shape, given the workspace inputs directory (the command line "
            "spells it inputs (CLI: --inputs) on `pyfs-matrix upgrade`)."
        )
    return _validate(PprocArtifact, data, path, "pproc")


#: The kind letter a groups id carried before 0.11.0, when the kind was
#: renamed pproc (PFS-2029.07): ``e`` for ENTRY, the column that named it.
GROUPS_LETTER = "e"


def migrate_groups_to_pproc(inputs_dir: Path) -> dict[str, str]:
    """Move every ``inputs/groups/e*.toml`` to ``inputs/pproc/p*.toml`` under ``[groups]``.

    PFS-2029.07.01: the groups artifact becomes the pproc artifact, the
    file's nine groups migrating verbatim: the new file is the old one's
    text under a ``[groups]`` header, comments and all, so a diff of the
    two shows one added line. Returns the id mapping (old to new) for the
    matrix cells that name them, which :func:`upgrade_matrix` rewrites.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.

    Returns
    -------
    dict of str to str
        Old id to new id, ``e001`` to ``p001``; empty when there is no
        groups directory or it holds no file.

    Raises
    ------
    InputArtifactError
        A groups file whose id does not carry the ``e`` letter (it
        predates the kind-letter rule; run the id migration first), a
        file that already carries a table (it is not a groups file), or
        a target that already exists.
    """
    source_dir = Path(inputs_dir) / "groups"
    target_dir = Path(inputs_dir) / "pproc"
    if not source_dir.is_dir():
        return {}
    mapping: dict[str, str] = {}
    for path in sorted(source_dir.glob("*.toml")):
        old = path.stem
        if old[:1].lower() != GROUPS_LETTER:
            raise InputArtifactError(
                f"the groups file {path} carries the id {old!r}, which does not declare "
                f"its kind with the letter {GROUPS_LETTER!r}; give the library its kind "
                "letters first (migrate_input_ids) and then move the groups to pproc."
            )
        data = _load_toml(path, "groups")
        tables = sorted(key for key, value in data.items() if isinstance(value, dict))
        if tables:
            raise InputArtifactError(
                f"the groups file {path} carries table(s) {', '.join(tables)}, so it is "
                "not a groups file of the shape this migration moves (a flat table of "
                "group name to members)."
            )
        new = KIND_LETTERS["pproc"] + old[1:]
        target = target_dir / f"{new}.toml"
        if target.exists():
            raise InputArtifactError(
                f"cannot move {path} to {target}: the target already exists. Remove or "
                "rename it, then run the migration again."
            )
        mapping[old] = new
    for old, new in mapping.items():
        path = source_dir / f"{old}.toml"
        target = target_dir / f"{new}.toml"
        text = path.read_text(encoding="utf-8")
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "# Moved from inputs/groups/" + path.name + " by `pyfs-matrix upgrade --inputs`;\n"
            "# the groups are the file's own lines, under the [groups] table a pproc\n"
            "# artifact holds them in (PFS-2029.07).\n[groups]\n" + text,
            encoding="utf-8",
        )
        path.unlink()
    try:
        source_dir.rmdir()
    except OSError:
        pass
    return mapping


def _resolve_file(inputs_dir: Path, kind: str, subdir: str, artifact_id: str) -> Path:
    """Resolve a file artifact (geometry or profile) registered by stem."""
    _check_id(artifact_id, kind)
    directory = Path(inputs_dir) / subdir
    matches = sorted(
        path
        for path in (directory.iterdir() if directory.is_dir() else [])
        if path.is_file() and path.stem == artifact_id
    )
    if not matches:
        raise _miss(kind, artifact_id, directory, suffix=None)
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise InputArtifactError(
            f"{kind} id {artifact_id!r} matches {len(matches)} files ({names}); the "
            "id is the file name stem and must be unique within the library, so "
            "rename or remove the extras."
        )
    return matches[0]


def resolve_geometry(inputs_dir: Path, artifact_id: str) -> Path:
    """Resolve the staged geometry file one id names.

    Geometries register by file name (any extension); the id is the
    stem, so ``resolve_geometry(inputs_dir, "wing_v2")`` finds
    ``inputs/geometries/wing_v2.fsm``.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    artifact_id : str
        File name stem under ``geometries/``.

    Returns
    -------
    Path
        The geometry file.

    Raises
    ------
    InputArtifactError
        Unknown id (the message lists the available ids) or an
        ambiguous stem shared by several files.
    """
    return _resolve_file(inputs_dir, "geometry", "geometries", artifact_id)


def resolve_profile(inputs_dir: Path, artifact_id: str) -> Path:
    """Resolve the input profile file one id names.

    Profiles (for example actuator thrust distributions) register by
    file name; the id is the stem.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    artifact_id : str
        File name stem under ``profiles/``.

    Returns
    -------
    Path
        The profile file.

    Raises
    ------
    InputArtifactError
        Unknown id (the message lists the available ids) or an
        ambiguous stem shared by several files.
    """
    return _resolve_file(inputs_dir, "profile", "profiles", artifact_id)


@dataclass(frozen=True)
class RegisteredBuild:
    """One entry of the workspace build registry, as the registry states it.

    Attributes
    ----------
    fs_exe : Path
        The executable this build id names. Existence is checked by the
        executor at construction, so a campaign can be authored away
        from the licensed machine.
    fs_version : str or None
        The FlightStream version the registry DECLARES this build's
        scripts are emitted under, canonical identifier (``"26.123"``)
        or a vendor release name that resolves to exactly one registered
        build. None means the registry declares none, and the caller's
        campaign default answers for it.

        It is a DECLARATION and never an inference. Nothing here reads a
        version out of the executable path or out of the build id, which
        is the rule :class:`pyflightstream.run.SolverBuild` exists to
        state: a build id is a key of this registry, and which command
        database a build carries is a fact only its owner knows.
    """

    fs_exe: Path
    fs_version: str | None


def _refuse_declared_version(version: str, build_id: str, registry_path: Path) -> None:
    """Refuse a declared version the version registry does not carry.

    The check happens where the version is READ rather than where a
    script is emitted under it, so a typed identifier is refused with the
    file and the build id in the message instead of surfacing much later
    as an unknown-version error from the script layer.

    Parameters
    ----------
    version : str
        The version string the registry entry declares.
    build_id : str
        The build id whose entry declares it, for the message.
    registry_path : Path
        The registry file, for the message.

    Raises
    ------
    InputArtifactError
        The identifier names no registered version, or names a vendor
        release name that more than one registered build carries. The
        chained message lists the registered versions or the candidates.
    """
    try:
        resolve(version)
    except (UnknownVersionError, AmbiguousVersionAliasError) as error:
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {registry_path} declares "
            f"version {version!r}, which this package cannot resolve to one registered "
            "FlightStream version. The version decides which command database the "
            "build's scripts are emitted against, so it is never guessed from the "
            f"build id or the executable path. {error}"
        ) from error


def resolve_build(
    inputs_dir: Path, build_id: str, override: str | Path | None = None
) -> RegisteredBuild:
    """Read the registry entry of one build id: its executable and its version.

    Two explicit modes, translated from the run matrix's MANUAL pattern:

    - Registry mode (default): the build id must exist in
      ``inputs/executables.toml``, a top-level TOML table mapping build
      ids to entries.
    - Override mode: an explicit ``override`` path wins over the
      registry and is the only way to run an unregistered build; it is
      never guessed from the environment. An override declares NO
      version, because it is a bare path with no registry entry behind
      it to carry one.

    TWO ENTRY SHAPES, and the difference is what a build may say about
    itself:

    - ``"26.120" = "C:/fs26120/FlightStream.exe"`` is the shape this
      registry has always had and means exactly what it meant: the build
      id names an executable and declares no version, so a campaign that
      sends a row to it emits that row's script under the campaign
      default version.
    - ``"26.123" = { path = "C:/fs26123/FlightStream.exe", version =
      "26.123" }`` declares the version as well, which is what lets ONE
      run matrix send its rows to two solver builds and record each row
      against the version its own build emits under (PFS-2009.05).

    The table is where the declaration lives because it is already the
    file in which the user says what a build id MEANS on this machine.
    Deriving the version from the build id instead would be the
    inference :class:`pyflightstream.run.SolverBuild` refuses, and the
    two are not the same thing: a registry key is a name the campaign
    author chose, and nothing stops it naming an installation whose
    command database is anything at all.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    build_id : str
        Build identifier key of the registry, for example ``"26.120"``.
    override : str or Path, optional
        Explicit executable path bypassing the registry.

    Returns
    -------
    RegisteredBuild
        The executable, and the declared version or None.

    Raises
    ------
    InputArtifactError
        Registry file missing; build id not registered (the message
        lists the registered build ids and the override mode); an entry
        that is neither a path string nor a table; a table with no
        ``path``; a table carrying a key outside
        :data:`EXECUTABLE_ENTRY_KEYS`; or a declared version the version
        registry does not carry.

    Examples
    --------
    >>> from pyflightstream.workspace.inputs import resolve_build
    >>> build = resolve_build(workspace.inputs_dir, "26.123")  # doctest: +SKIP
    >>> build.fs_version                                       # doctest: +SKIP
    '26.123'
    """
    if override is not None:
        return RegisteredBuild(fs_exe=Path(override), fs_version=None)
    registry_path = Path(inputs_dir) / EXECUTABLES_FILE
    if not registry_path.is_file():
        raise InputArtifactError(
            f"no executable registry at {registry_path}; register builds as "
            '"<build_id>" = "<path>" entries in that TOML file, or pass the '
            "explicit override path. The executable is always explicit input, "
            "never guessed."
        )
    table = _load_toml(registry_path, "executables")
    entry = table.get(build_id)
    if entry is None:
        # BOTH shapes count as registered. Listing only the string entries,
        # which is what this did while a string was the only shape, would
        # tell a user with a table-valued registry that nothing is
        # registered at all.
        registered = sorted(key for key, value in table.items() if isinstance(value, (str, dict)))
        listing = ", ".join(registered) if registered else "none yet"
        raise InputArtifactError(
            f"build id {build_id!r} is not in the executable registry "
            f"{registry_path} (registered: {listing}); add it there, or pass the "
            "explicit override path to run an unregistered build."
        )
    if isinstance(entry, str):
        return RegisteredBuild(fs_exe=Path(entry), fs_version=None)
    if not isinstance(entry, dict):
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {registry_path} must be "
            f"a path string or a table, got {type(entry).__name__}; write "
            f'"{build_id}" = "C:/path/to/FlightStream.exe" for a build whose scripts '
            f'are emitted under the campaign default version, or "{build_id}" = '
            '{ path = "C:/path/to/FlightStream.exe", version = "26.123" } to declare '
            "the version this build's scripts are emitted under."
        )
    unknown = sorted(key for key in entry if key not in EXECUTABLE_ENTRY_KEYS)
    if unknown:
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {registry_path} carries "
            f"key(s) {', '.join(unknown)}, and a build entry reads "
            f"{', '.join(EXECUTABLE_ENTRY_KEYS)} and nothing else. The key is refused "
            "rather than ignored because an ignored one is invisible: a misspelled "
            "version key leaves the registry looking correct and every row of this "
            "build emitted under the campaign default. Correct the spelling, or "
            "remove the key."
        )
    path_value = entry.get("path")
    if not isinstance(path_value, str):
        stated = "declares no path" if path_value is None else f"declares path {path_value!r}"
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {registry_path} {stated}, "
            "and a table entry must carry path as a string; write "
            f'"{build_id}" = {{ path = "C:/path/to/FlightStream.exe" }}. The '
            "executable is always explicit input, never guessed."
        )
    version = entry.get("version")
    if version is None:
        return RegisteredBuild(fs_exe=Path(path_value), fs_version=None)
    if not isinstance(version, str):
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {registry_path} declares "
            f"version {version!r} of type {type(version).__name__}, and a FlightStream "
            'version is written as a string: version = "26.123". A bare 26.123 is a '
            "TOML float and loses the three-digit form the canonical identifier is."
        )
    _refuse_declared_version(version, build_id, registry_path)
    return RegisteredBuild(fs_exe=Path(path_value), fs_version=version)


def resolve_executable(inputs_dir: Path, build_id: str, override: str | Path | None = None) -> Path:
    """Resolve the FlightStream executable of one build id.

    The path half of :func:`resolve_build`, which is where the registry
    is read and where both entry shapes are described. This is the call
    for a caller who wants the executable and nothing else; a caller who
    also needs the version the build declares calls
    :func:`resolve_build` instead, because the two facts come from one
    entry and reading it twice is how they would drift apart.

    Existence of the executable is checked by the executor at
    construction (so campaigns can be authored away from the licensed
    machine), not here.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    build_id : str
        Build identifier key of the registry, for example ``"26.120"``.
    override : str or Path, optional
        Explicit executable path bypassing the registry.

    Returns
    -------
    Path
        The executable path.

    Raises
    ------
    InputArtifactError
        Every refusal of :func:`resolve_build`: registry file missing,
        build id not registered, or a malformed entry.
    """
    return resolve_build(inputs_dir, build_id, override=override).fs_exe


@dataclass(frozen=True)
class IdMigration:
    """What a kind-letter migration renamed and rewrote, or would.

    Attributes
    ----------
    renames : tuple of (Path, Path)
        Library files to rename, source then destination, sorted by
        source. Empty for a library already migrated, which is a
        legitimate outcome and not an error.
    cells : dict of str to dict of str to int
        Per matrix (as given, stringified) and per column, how many
        cells the rewrite changed. A matrix that names no migrated id
        appears with zeros rather than being dropped, so a caller can
        tell "this matrix was looked at and nothing matched" from "this
        matrix was never read".
    applied : bool
        Whether the plan was carried out. False is the dry run.
    """

    renames: tuple[tuple[Path, Path], ...]
    cells: dict[str, dict[str, int]]
    applied: bool

    @property
    def is_empty(self) -> bool:
        """True when nothing would move: no rename and no changed cell."""
        return not self.renames and not any(
            count for columns in self.cells.values() for count in columns.values()
        )


def _rename_plan(inputs_dir: Path) -> tuple[list[tuple[Path, Path]], dict[str, dict[str, str]]]:
    """Plan the renames of one library, and the cell mapping they imply.

    A file whose stem already begins with its kind's letter is left
    alone; it is already an id of the new form. Matching is
    case-insensitive for the same reason :func:`_check_id` is: the id is
    a file stem and two spellings name one file on a case-insensitive
    file system.
    """
    renames: list[tuple[Path, Path]] = []
    mapping: dict[str, dict[str, str]] = {column: {} for column in CODE_COLUMNS}
    for kind, letter in KIND_LETTERS.items():
        directory = inputs_dir / _KIND_DIRECTORIES[kind]
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix != ".toml":
                continue
            old = path.stem
            if old[:1].lower() == letter:
                continue
            new = f"{letter}{old}"
            renames.append((path, path.with_name(f"{new}{path.suffix}")))
            mapping[KIND_COLUMNS[kind]][old] = new
    return renames, mapping


def migrate_input_ids(
    inputs_dir: str | Path,
    matrices: Sequence[str | Path] = (),
    *,
    apply: bool = False,
) -> IdMigration:
    r"""Give every coded library id its kind letter, and move the matrices with it.

    A reference, setup or group id declares its kind with a leading
    letter since v0.8.0 (:data:`KIND_LETTERS`, PFS-2009.01), so a library
    written before that break holds files no id can reach and matrices
    whose REF, SET and ENTRY cells name ids the library refuses. This
    performs BOTH halves of the repair IN ONE CALL, which is the whole
    safety property: renaming the files without rewriting the cells, or
    the other way round, leaves a corpus that half-resolves, and half of
    it silently.

    Nothing is written until every step is known to be possible. A
    rename onto an existing file, a matrix that is missing, and a matrix
    at any other layout are all refused with the library and the
    matrices untouched, so a refused migration is a no-op rather than a
    half-done one.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace ``inputs/`` directory
        (:attr:`~pyflightstream.workspace.CampaignWorkspace.inputs_dir`).
    matrices : sequence of str or Path
        Every run matrix whose cells name ids of this library. It
        defaults to none, and passing none is a real choice rather than
        an oversight: a library with no matrix beside it still migrates,
        and this signature makes the omission visible in the call.
    apply : bool
        Carry the plan out. Keyword-only and False by default, so the
        call that finds out what would happen cannot be the call that
        does it.

    Returns
    -------
    IdMigration
        The renames and the per-column cell counts, with ``applied``
        saying whether they happened.

    Raises
    ------
    InputArtifactError
        A rename would land on a file that already exists, or a named
        matrix does not exist. Both are refused before anything is
        written.
    pyflightstream.cases.matrix.MatrixError
        A named matrix does not read at the verified layout. Also
        refused before anything is written.

    Examples
    --------
    >>> from pyflightstream.workspace import CampaignWorkspace, migrate_input_ids
    >>> workspace = CampaignWorkspace("campaign")            # doctest: +SKIP
    >>> plan = migrate_input_ids(                            # doctest: +SKIP
    ...     workspace.inputs_dir, ["matrix.fs"]
    ... )
    >>> [(old.name, new.name) for old, new in plan.renames]  # doctest: +SKIP
    [('003.toml', 'r003.toml')]
    >>> migrate_input_ids(                                   # doctest: +SKIP
    ...     workspace.inputs_dir, ["matrix.fs"], apply=True
    ... ).applied
    True
    """
    inputs = Path(inputs_dir)
    renames, mapping = _rename_plan(inputs)
    collisions = [(old, new) for old, new in renames if new.exists()]
    if collisions:
        listing = "; ".join(f"{old.name} -> {new.name} in {new.parent}" for old, new in collisions)
        raise InputArtifactError(
            f"{len(collisions)} rename(s) would land on a file that already exists: "
            f"{listing}. Nothing was renamed and no matrix was rewritten. Both files "
            "answer to one id once the letter is added, so the migration cannot say "
            "which artifact a matrix cell means; open the pair, decide which one the "
            "campaign uses, and give the other a distinct id first."
        )
    missing = [str(path) for path in matrices if not Path(path).is_file()]
    if missing:
        raise InputArtifactError(
            f"matrix file(s) {', '.join(missing)} do not exist, so their REF, SET and "
            "ENTRY cells cannot be rewritten. Nothing was renamed: renaming the "
            "library while a matrix that names it stays behind is exactly the "
            "half-resolving state this migration exists to prevent."
        )
    # DRY FIRST, every matrix, before a single byte moves. rewrite_codes
    # refuses a wrong layout or a malformed row, and finding that out
    # after the library has been renamed would leave the corpus split.
    rewritten: dict[str, bytes] = {}
    cells: dict[str, dict[str, int]] = {}
    for path in matrices:
        text, counts = rewrite_codes(path, mapping)
        rewritten[str(path)] = text
        cells[str(path)] = counts
    if apply:
        for old, new in renames:
            old.rename(new)
        for name, text in rewritten.items():
            Path(name).write_bytes(text)
    return IdMigration(renames=tuple(renames), cells=cells, applied=apply)
