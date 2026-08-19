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

import tomllib
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from importlib import import_module
from inspect import Parameter, signature
from pathlib import Path
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

from pyflightstream._digest import file_sha256, text_sha256
from pyflightstream._errors import PyflightstreamError
from pyflightstream.script import Script
from pyflightstream.script.toggles import resolve_toggle
from pyflightstream.versions import resolve

__all__ = [
    "Campaign",
    "CampaignConfigError",
    "DerivedFrom",
    "ReferenceData",
    "ScriptRecipe",
    "SimCase",
    "SolverSettings",
    "SolverToggle",
    "SweepAxis",
    "check_recipe",
    "derived_body_sha256",
    "load_campaign",
    "point_tag",
    "resolve_recipe",
    "stamp_derived_campaign",
]

_TAG_PREFIXES = (("alpha", "a"), ("beta", "b"), ("advance_ratio", "j"))


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
        (propeller advance ratio J, dimensionless).
    values : list
        Axis values; for ``alpha_beta`` each entry is an
        ``[alpha, beta]`` pair in deg.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["alpha", "beta", "alpha_beta", "advance_ratio"]
    values: list[float] | list[tuple[float, float]]

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
            ``advance_ratio`` (both keys for ``alpha_beta``).
        """
        for value in self.values:
            if self.type == "alpha_beta":
                alpha, beta = value
                yield {"alpha": alpha, "beta": beta}
            else:
                yield {self.type: value}


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

    model_config = ConfigDict(extra="forbid")

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
    reference: ReferenceData | None = None
    solver: SolverSettings = Field(default_factory=SolverSettings)
    recipe: str
    variables: dict[str, str | float | int | bool] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    point: dict[str, float] = Field(default_factory=dict)
    fs_build: str | None = None


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
        build. Validated against
        the registered versions at load time, resolved to canonical in
        the manifest.
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
        resolve(value)
        return value

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
