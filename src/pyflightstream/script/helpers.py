"""Curated helpers for the common FlightStream workflows (SAD Section 4.3).

Pipeline role: a small, curated set of thin typed functions sitting on
top of :class:`~pyflightstream.script.Script`. Each helper only
translates its typed arguments into ``emit()`` calls, so every line
still passes the database validation, phase ordering, and
cross-reference checks of the builder. Helpers own the conditional
argument combinations the manual documents in prose (which extras each
SET_FREESTREAM type takes, when INITIALIZE_SOLVER takes per-surface
lines or a PERIODIC copy count), because the database records grammar,
not conditionality.

One generated function per command was rejected in the SAD: it would
reproduce the shape of the AGPL package, create a huge surface, and
teach nothing. The curated workflows are: free stream and atmosphere,
actuator disc (SRC-003 pp.323-324), rotary motion (pp.332-333), solver
settings (pp.339-343), solver initialization (p.337), sweeps (p.406),
analysis and export selection (pp.350-354), and probe management
(pp.362-363).

Toggles: every parameter that switches a solver flag on or off takes a
Python bool or the solver's own ``ENABLE`` and ``DISABLE`` (any case),
resolved by :func:`pyflightstream.script.toggles.resolve_toggle` before
the helper emits anything; a word in neither vocabulary is refused
naming the helper and the argument. A setup carried over from the
solver speaks that vocabulary, and a bare string is truthy in Python,
so reading it is what keeps ``'DISABLE'`` from emitting ENABLE.

Entity citations by label: every parameter that cites a frame,
actuator, motion, or mesh boundary accepts the 1-based index or the
label registered at creation (``label=``) or declared through
:meth:`~pyflightstream.script.Script.declare_existing`; labels resolve
to indices at emission through the script's entity registry.

Provenance: :func:`solver_settings` is the single entry point for every
solver flag of the runtime_settings, solver_settings, and
advanced_settings families. It carries the optional induced-drag
boundary selection (``vorticity_drag_boundaries``), emits the library
minimum-Cp default when the caller does not choose one, and attaches a
:class:`~pyflightstream.script.solver_setup.SolverSetup` snapshot of
every effective flag value to the script (``script.solver_setup``) for
the run manifest. The induced-drag selection itself is an
analysis-phase command, so when it is passed its emission is deferred
and lands right after the solver starts: :func:`start_solver` (or the
first analysis or export helper call) flushes it.

ONE PAIR HERE EMITS NOTHING, and it is stated in the module docstring
rather than only beside itself, because the sentence above says every
helper translates typed arguments into ``emit()`` calls and this is the
exception. :func:`parse_relaxed_trailing_edge` and
:class:`RelaxedTrailingEdge` read and write the relaxed trailing-edge
COMPONENT specification, the ``Relaxed_TE;u;v1;v2;direction`` line a CCS
file writes where a component is defined; no command on any registered
build takes its values, so they take no ``script`` and produce text
(SRC-752 p.85).
"""

from __future__ import annotations

import math
import re
import warnings
from collections.abc import Mapping, Sequence
from os import PathLike, fspath
from typing import Literal

from pyflightstream._decimal import plain_decimal
from pyflightstream._deprecations import ANALYSIS_SETUP_VORTICITY_DRAG_BOUNDARIES
from pyflightstream._digest import one_file_key
from pyflightstream._errors import (
    PyflightstreamDeprecationWarning,
    PyflightstreamWarning,
)
from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.script import (
    LENGTH_UNIT_COMMAND,
    CommandArgumentError,
    Script,
    ScriptReferenceError,
    UnsteadyActionUse,
    _settings,
)
from pyflightstream.script._relaxed_te import (  # noqa: F401  (this module is the public path)
    DEFAULT_SHEDDING_DIRECTION,
    RELAXED_SHEDDING_DIRECTIONS,
    RELAXED_TE_FIELDS_WITH_DIRECTION,
    RELAXED_TE_FIELDS_WITHOUT_DIRECTION,
    RELAXED_TE_KEYWORD,
    RelaxedTrailingEdge,
    parse_relaxed_trailing_edge,
    resolve_shedding_direction,
)
from pyflightstream.script._settings import (  # noqa: F401  (this module is the public path)
    _flush_pending_vorticity,
    _reject_bare_label,
    _reject_empty_selection,
    atmosphere,
    fluid_fifth_property,
    free_stream,
    initialize_solver,
    start_solver,
    unsteady_solver,
)
from pyflightstream.script.rotor_vocabulary import (
    EUCLIDEAN_ROTOR_UNIT,
    UNMARKED_EUCLIDEAN_ROTOR_UNIT,
    euclidean_rotor,
    unmarked_euclidean_rotor,
)
from pyflightstream.script.solver_setup import (  # noqa: F401  (this module is a public path)
    LIBRARY_MINIMUM_CP,
    SEPARATION_MODELS,
    AirfoilSeparation,
    AxialVortexSeparation,
    BulkSeparation,
    CylindricalBulkSeparation,
    SolverSetup,
    StratfordBulkSeparation,
    build_setup,
    with_vorticity_selection,
)
from pyflightstream.script.toggles import (  # noqa: F401  (resolve_toggle: the public path)
    Toggle,
    _optional_toggle,
    _read,
    _toggle,
    resolve_toggle,
)
from pyflightstream.versions import known_versions

#: One number of a radial thrust profile row as the check reads it: a plain
#: decimal, optionally signed, with an optional exponent. A word, a NaN and an
#: infinity are not one; an exponent too large for a float is refused as not
#: finite.
_PROFILE_NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")

#: The form a radial thrust profile takes, quoted by every refusal of one.
_PROFILE_FORM = (
    "A radial thrust profile is rows of two numbers separated by one comma, r,F: the "
    "radial station, normalised or dimensional, and the force there; no header line "
    "and no count line"
)

#: The report that measured what 26.124 makes of a profile file.
_ACTUATOR_PROFILE_REPORT = "RPT-070"


def render_actuator_profile(text: str, *, source: str = "the radial thrust profile") -> str:
    r"""Return a radial thrust profile's rows in the one form 26.124 was measured to read.

    MEASURED ON 26.124 (RPT-070): ``SET_PROP_ACTUATOR_PROFILE`` reads every
    line of the file as a point, the empty one after a final newline
    included. Eleven rows ending in a newline were read as twelve points, the
    file was logged as unreadable and refused in a modal dialog that holds
    the solver until a person closes it; the same eleven rows with no final
    newline were read, radii and forces. A first line that is a count or a
    header was read as one more point too, and every value then read as
    zero. Line ends, spaces, tabs and a dimensional radius changed nothing
    of the refusal.

    So the text returned is the rows, each ``r,F`` with its two numbers as
    written, joined by a newline, and NO final newline. What an editor adds
    is removed rather than refused: blank lines, the whitespace around a
    line and around each number, a byte-order mark. The numbers are not
    converted, so ``r`` stays normalised or dimensional as written.

    Parameters
    ----------
    text : str
        The profile file's text, as the user saved it.
    source : str
        What the refusals call the text, the file's path for one read from
        disk.

    Returns
    -------
    str
        The file's text for the solver: newline separated, NOT newline
        terminated.

    Raises
    ------
    CommandArgumentError
        Naming the line, 1-based with blank lines counted: a first row that
        is one number (a count) or holds a word (a header); a row that is
        not two numbers separated by one comma; a number that is not finite;
        or fewer than two rows.

    Examples
    --------
    >>> from pyflightstream.script import helpers
    >>> print(helpers.render_actuator_profile("0.2, 0.0\n0.6,127.3\n1.0,0.0\n"))
    0.2,0.0
    0.6,127.3
    1.0,0.0
    """
    rows: list[str] = []
    for number, raw in enumerate(text.removeprefix("\ufeff").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        where = f"{source}, line {number}: {line!r}"
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2 or not all(_PROFILE_NUMBER.fullmatch(part) for part in parts):
            words = [word for word in re.split(r"[\s,;]+", line) if word]
            numbers = all(_PROFILE_NUMBER.fullmatch(word) for word in words)
            if not rows and numbers and len(words) == 1:
                raise CommandArgumentError(
                    f"{where} is one number, a count line; remove it. On 26.124 a count is "
                    "read as one more point and every value of the profile then reads as zero "
                    f"({_ACTUATOR_PROFILE_REPORT}). {_PROFILE_FORM}"
                )
            if not rows and not numbers:
                raise CommandArgumentError(
                    f"{where} is a header line; remove it. On 26.124 a header is read as one "
                    "more point and every value of the profile then reads as zero "
                    f"({_ACTUATOR_PROFILE_REPORT}). {_PROFILE_FORM}"
                )
            raise CommandArgumentError(
                f"{where} is not two numbers separated by one comma. {_PROFILE_FORM}"
            )
        for part in parts:
            if not math.isfinite(float(part)):
                raise CommandArgumentError(
                    f"{source}, line {number}: {part!r} is not a finite number. {_PROFILE_FORM}"
                )
        rows.append(",".join(parts))
    if len(rows) < 2:
        raise CommandArgumentError(
            f"{source} holds {len(rows)} row{'' if len(rows) == 1 else 's'} of r,F, and a radial "
            f"distribution needs at least two. {_PROFILE_FORM}"
        )
    return "\n".join(rows)


def _same_file(parked: str, path: str) -> bool:
    """Whether two paths a script parks are one file where the run writes them.

    A path through a parent folder (``sub/../x``) names the file the folded path
    names, and a path equal to another but for case is the same file on a
    case-insensitive file system, as on Windows, as is a name Windows reads as
    another's alias (a trailing dot or space); the run's writer holds every
    parked file to the same rule (run._pending._write_pending_files).
    """
    return one_file_key(parked) == one_file_key(path)


def _where_parked(parked: str, path: str) -> str:
    """How a refusal names the parked file that ``path`` would replace."""
    if parked == path:
        return repr(path)
    if parked.casefold() == path.casefold():
        return (
            f"{parked!r}, which differs from {path!r} only in case: a case-insensitive "
            "file system reads the two as one file"
        )
    return f"{parked!r}, which is the file {path!r} names through a parent folder: one file"


def actuator_disc(
    script: Script,
    name: str,
    *,
    frame: int | str,
    axis: str,
    offset: float,
    r_tip: float,
    r_hub: float,
    rpm: float,
    thrust: float | None = None,
    thrust_type: str = "NEWTONS",
    profile: str | None = None,
    profile_force_unit: str = "NEWTONS",
    n_blades: int | None = None,
    profile_text: str | None = None,
    swirl: float | None = None,
    wake_type: str | None = None,
    enable: Toggle = True,
    label: str | None = None,
) -> int:
    """Create and configure one rotor actuator disc (SRC-003 pp.323-324).

    The disc is the linearized rotor slipstream surrogate
    (SRC-003 pp.185-187). Exactly one thrust specification is taken:
    a net ``thrust`` (ELLIPTICAL profile) or a radial force
    distribution file ``profile`` (CUSTOM profile, which also needs
    ``n_blades``).

    Parameters
    ----------
    script : Script
        Script under construction.
    name : str
        Actuator name shown in the interface.
    frame : int or str
        Local coordinate system carrying the disc axis (index greater
        than 1, or its creation label); it must exist earlier in the
        script.
    axis : str
        Disc axis within ``frame``: ``X``, ``Y``, or ``Z``.
    offset : float
        Disc position along the axis, in simulation length units.
    r_tip, r_hub : float
        Tip and hub radii, in simulation length units.
    rpm : float
        Rotational speed in rev/min; the sign selects the rotation
        direction about the axis.
    thrust : float, optional
        Net thrust for the ELLIPTICAL model, in ``thrust_type`` units.
    thrust_type : str
        ``COEFFICIENT``, ``NEWTONS``, or ``POUNDS``. The manual
        recommends dimensional thrust because the coefficient
        convention must match the solver formulation (SRC-003 p.187).
    profile : str, optional
        Path of the radial thrust profile file for the CUSTOM model, the
        path the command's next line names. Refused, before anything is
        emitted, on a build whose ``SET_PROP_ACTUATOR_PROFILE`` takes no
        blade count (25.000 and 25.100). Run on 26.124 (RPT-070), which
        reads a file in the form :func:`render_actuator_profile` returns
        and refuses one ending in a newline.
    profile_force_unit : str
        Force unit used inside the profile file: ``NEWTONS``,
        ``KILO-NEWTONS``, ``POUND-FORCE``, or ``KILOGRAM-FORCE``.
    n_blades : int, optional
        Blade count; required with ``profile``.
    profile_text : str, optional
        The profile's text, when the run is to write the file ``profile``
        names: put in the form 26.124 reads by
        :func:`render_actuator_profile`, which refuses a text the solver
        would misread before anything is emitted, and parked on the script
        (:attr:`~pyflightstream.script.Script.pending_input_files`) as the
        bytes the run writes there before the solver starts. Without it
        the file at ``profile`` is named as it stands.
    swirl : float, optional
        Fraction between 0 and 1 of the swirl velocity kept
        downstream; below 1 mimics a de-swirling stator
        (SRC-003 p.186).
    wake_type : str, optional
        RIGID or RELAXED, as documented from 26.122; omitted emits no wake setter.
    enable : bool or 'ENABLE' or 'DISABLE'
        Emit ENABLE_ACTUATOR at the end.
    label : str, optional
        Label registered for the created actuator in the script's
        entity registry, so later commands can cite it by name
        instead of by index.

    Returns
    -------
    int
        Index of the created actuator, for later citations.

    Raises
    ------
    CommandArgumentError
        If not exactly one thrust specification is given, a profile file lacks ``n_blades`` or is
        refused on the script's build, ``profile_text`` comes without ``profile`` or names a path
        the script already writes differently, or ``swirl`` is outside [0, 1].
    """
    enable = _read("actuator_disc", "enable", enable)
    if (thrust is None) == (profile is None):
        raise CommandArgumentError(
            "actuator_disc takes exactly one thrust specification: a net thrust "
            "(ELLIPTICAL model) or a radial profile file (CUSTOM model) "
            "(SRC-003 pp.185-187)"
        )
    if profile is not None and n_blades is None:
        raise CommandArgumentError(
            "actuator_disc with a profile file needs n_blades, because the imported "
            "radial distribution is per blade (SRC-003 pp.323-324)"
        )
    if profile_text is not None and profile is None:
        raise CommandArgumentError(
            "actuator_disc: profile_text is the text of the file profile names, and no "
            "profile was given. Name the path the run writes the profile to as profile"
        )
    if profile is not None:
        # REFUSED BY BUILD, BEFORE ANY LINE IS WRITTEN (G06). The 25.000 and
        # 25.100 editions print SET_PROP_ACTUATOR_PROFILE with no blade count,
        # so the call below would reach the emitter with one argument too many
        # after the disc was half written; and dropping the count would send
        # a distribution those builds may read differently, which no edition
        # says and no run has measured.
        entry = script.entry("SET_PROP_ACTUATOR_PROFILE")
        if "n_blades" not in {arg.name for arg in entry.args}:
            raise CommandArgumentError(
                f"actuator_disc with a profile file is refused on FlightStream "
                f"{script.version.canonical}: that build's SET_PROP_ACTUATOR_PROFILE takes "
                f"no blade count ({entry.citation}), where the editions from 26.000 take one, "
                "and what the file means there is not documented. Load the disc by its net "
                "thrust on this build, or run the profile on 26.000 or later."
            )
    # THE RUN'S OWN COPY (G06), checked and rendered BEFORE ANY LINE IS WRITTEN,
    # so a text the solver would misread leaves the script untouched. Parked as
    # BYTES, written as they are: the last row ends the file, and a text-mode
    # write is free to change the line ends of the one form measured (RPT-070).
    # A path equal to a parked one but for case is the same file on a
    # case-insensitive file system (Windows), so it is held to the same rule.
    copy: bytes | None = None
    if profile_text is not None and profile is not None:
        copy = render_actuator_profile(profile_text).encode("utf-8")
        path = fspath(profile)
        for parked, already in script._pending_input_files.items():
            if not _same_file(parked, path) or already == copy:
                continue
            where = _where_parked(parked, path)
            raise CommandArgumentError(
                f"actuator_disc: this script already writes a different file to {where}. "
                "One path is one file, so the second would silently replace the first and "
                "both discs would read whichever won. Give this disc's profile a path of "
                "its own"
            )
    if swirl is not None and not 0.0 <= swirl <= 1.0:
        raise CommandArgumentError(
            f"actuator_disc swirl must lie between 0 and 1, got {swirl}: it is the "
            "fraction of the swirl velocity kept downstream (SRC-003 p.186)"
        )
    if wake_type is not None:
        entry = script.entry("SET_ACTUATOR_WAKE_TYPE")
        allowed = next(arg.values for arg in entry.args if arg.name == "type") or ()
        if wake_type not in allowed:
            raise CommandArgumentError(
                f"actuator_disc wake_type {wake_type!r} is not one of {tuple(allowed)}"
            )
    subtype = "ELLIPTICAL" if thrust is not None else "CUSTOM"
    # THE SOLVER'S OWN WORD, not this package's. The rotor-word sweep of
    # 0.15.0 renamed this to ROTOR and the command database refused it:
    # PROPELLER is the enum value CREATE_NEW_ACTUATOR accepts, and a
    # vendor vocabulary is quoted rather than translated.
    script.emit("CREATE_NEW_ACTUATOR", "PROPELLER", subtype=subtype, name=name, label=label)
    index = script.num_actuators
    script.emit("SET_ACTUATOR_AXIS", index, frame, axis, offset)
    script.emit("SET_ACTUATOR_RADIUS", index, r_tip, r_hub)
    script.emit("SET_PROP_ACTUATOR_RPM", index, rpm)
    if thrust is not None:
        script.emit("SET_PROP_ACTUATOR_THRUST", index, thrust, thrust_type)
    else:
        script.emit("SET_PROP_ACTUATOR_PROFILE", index, profile_force_unit, n_blades, profile)
        if copy is not None and profile is not None:
            script._pending_input_files[fspath(profile)] = copy
    if swirl is not None:
        script.emit("SET_PROP_ACTUATOR_SWIRL", index, swirl)
    if wake_type is not None:
        script.emit("SET_ACTUATOR_WAKE_TYPE", index, wake_type)
    if enable:
        script.emit("ENABLE_ACTUATOR", index)
    return index


def rotary_motion(
    script: Script,
    *,
    frame: int | str,
    axis: str,
    rpm: float,
    boundaries: Sequence[int | str] | Literal["all"] = "all",
    moving_frames: Sequence[int | str] | Literal["all"] | None = None,
    start_time: float | None = None,
    wake_stabilization_blades: int | None = None,
    label: str | None = None,
) -> int:
    """Create and configure one rotary motion (SRC-003 pp.332-333).

    Rotary motion is the blade-resolved alternative to the actuator
    disc surrogate (SRC-003 p.234); it requires the unsteady solver
    (see :func:`unsteady_solver`).

    ON A BUILD WITHOUT THE ROTARY TYPE THAT DOCUMENTS THE EUCLIDEAN ROTOR
    (25.100 and 26.000, whose manuals name the motion type EUCLIDEAN) the
    same rotor is written in that build's own vocabulary: a Euclidean
    motion whose angular velocity is the speed converted to rad/s along
    the axis, marked as a rotor whose slipstream convects along that axis.
    The manual's rotor tutorial has the reader convert the rotor speed to
    radians per second for that field (SRC-741 p.394), and RPT-049
    measured the same unit for the script command
    (:data:`pyflightstream.script.rotor_vocabulary.EUCLIDEAN_ROTOR_UNIT`).
    The caller writes the same arguments on every build. The vocabulary is
    chosen by :func:`pyflightstream.script.rotor_vocabulary.euclidean_rotor`,
    which also holds on 25.000; the workflow refuses that build for its
    missing ``CREATE_NEW_MOTION``.

    ON 26.100, WHICH NAMES THE TYPE EUCLIDEAN AND HAS NO SCRIPTED ROTOR MARK
    (RPT-049), the motion is written as a Euclidean motion whose angular
    velocity is the speed IN REV/MIN along the axis, with no rotor mark
    (:func:`pyflightstream.script.rotor_vocabulary.unmarked_euclidean_rotor`,
    RPT-051). The unit and the sense of rotation there are not measured, the
    unit is a maintainer decision, and the solver is never told the motion is
    a rotor; the script says so in a comment above the motion.

    Each Euclidean speed is converted from rev/min by the unit its constant
    names (:data:`_FROM_REV_PER_MIN`), so a constant and the value written
    cannot disagree.

    Parameters
    ----------
    script : Script
        Script under construction.
    frame : int or str
        Local coordinate system of the rotation (index greater than
        1, or its creation label); it must exist earlier in the
        script.
    axis : str
        Rotor axis within ``frame``: ``X``, ``Y``, or ``Z``.
    rpm : float
        Rotor speed in rev/min.
    boundaries : sequence of int or str, or ``"all"``
        Geometry boundaries assigned to the motion, by 1-based index
        or declared boundary label; ``"all"`` selects every boundary
        (-1 form). Indices are verified against the inventory declared
        with declare_existing(boundaries=...) when one exists.
    moving_frames : sequence of int or str, ``"all"``, or None
        Local frames attached to the motion, by index or creation
        label; None attaches none.
    start_time : float, optional
        Motion start within the solver physical time, in s; a positive
        value converges a steady base flow before the motion begins.
    wake_stabilization_blades : int, optional
        Enables slipstream wake stabilization with this blade count,
        which is PER ROTOR and not a total across the motion
        (SRC-003 p.333). The February 2026 build's grammar for that
        command has two arguments and no blade count at all, and 25.100
        and 26.000 document no such command, so on a Euclidean build
        this argument is refused by name rather than emitted without the
        count it states.
    label : str, optional
        Label registered for the created motion in the script's
        entity registry, so later commands can cite it by name
        instead of by index.

    Returns
    -------
    int
        Identifier of the created motion, for later citations.

    Raises
    ------
    CommandArgumentError
        On a Euclidean build, marked or not, if the axis is given by index
        or a wake stabilization blade count is asked for, neither of which
        that vocabulary can state.
    """
    _reject_bare_label("rotary_motion", "boundaries", boundaries, allows_all=True)
    _reject_bare_label("rotary_motion", "moving_frames", moving_frames, allows_all=True)
    marked = euclidean_rotor(script._view)
    unmarked = unmarked_euclidean_rotor(script._view)
    euclidean = marked or unmarked
    if euclidean:
        _refuse_what_a_euclidean_rotor_cannot_state(script, axis, wake_stabilization_blades)
    if unmarked:
        script.comment(
            "\n".join(
                (
                    f"FlightStream {script.version.canonical} has no SET_MOTION_IS_ROTOR in the "
                    "command database: the 26.100 solver",
                    "does not recognize it (RPT-049), so this Euclidean motion is not marked as "
                    "a rotor. Its angular velocity is",
                    f"written in {UNMARKED_EUCLIDEAN_ROTOR_UNIT}, a maintainer decision, and "
                    "neither the unit nor the sense is",
                    "measured on this build. The 26.100 manual's rotor tutorial gives rad/s; if "
                    "the solver reads",
                    "rad/s, the rotor turns 60/(2 pi), about 9.55, times the speed stated "
                    "(pyflightstream RPT-051).",
                )
            )
        )
    script.emit("CREATE_NEW_MOTION", "EUCLIDEAN" if euclidean else "ROTARY", label=label)
    motion_id = script.num_motions
    if boundaries == "all":
        script.emit("SET_MOTION_BOUNDARIES", motion_id, -1)
    else:
        script.emit("SET_MOTION_BOUNDARIES", motion_id, len(boundaries), list(boundaries))
    if moving_frames == "all":
        script.emit("SET_MOTION_MOVING_FRAMES", motion_id, -1)
    elif moving_frames is not None:
        script.emit("SET_MOTION_MOVING_FRAMES", motion_id, len(moving_frames), list(moving_frames))
    script.emit("SET_MOTION_COORDINATE_SYSTEM", motion_id, frame)
    if euclidean:
        unit = EUCLIDEAN_ROTOR_UNIT if marked else UNMARKED_EUCLIDEAN_ROTOR_UNIT
        speed = rpm * _FROM_REV_PER_MIN[unit]
        script.emit(
            "SET_MOTION_ANGULAR_VELOCITY",
            motion_id,
            *(speed if axis == letter else 0.0 for letter in "XYZ"),
        )
    if marked:
        script.emit("SET_MOTION_IS_ROTOR", motion_id, "ENABLE", axis)
    elif not euclidean:
        script.emit("SET_MOTION_ROTOR_AXIS", motion_id, axis)
        script.emit("SET_MOTION_ROTOR_RPM", motion_id, rpm)
    if start_time is not None:
        script.emit("SET_MOTION_START_TIME", motion_id, start_time)
    if wake_stabilization_blades is not None:
        script.emit(
            "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION",
            motion_id,
            "ENABLE",
            wake_stabilization_blades,
        )
    return motion_id


def _refuse_what_a_euclidean_rotor_cannot_state(
    script: Script, axis: str, wake_stabilization_blades: int | None
) -> None:
    build = script.version.canonical
    if axis not in ("X", "Y", "Z"):
        raise CommandArgumentError(
            f"rotary_motion: FlightStream {build} writes a rotor as a Euclidean motion, "
            f"whose angular velocity is a vector in the motion's frame, and axis {axis!r} "
            "is not one of that frame's axes by letter. Write the axis as X, Y or Z."
        )
    if wake_stabilization_blades is not None:
        # The registry the script was built against, so the builds named are
        # the builds that database holds.
        registry = script._registry
        counted = [
            version.canonical
            for version in known_versions()
            if WAKE_STABILIZATION_COMMAND in (view := registry.for_version(version.canonical))
            and "num_blades" in {arg.name for arg in view[WAKE_STABILIZATION_COMMAND].args}
        ]
        raise CommandArgumentError(
            f"rotary_motion: FlightStream {build} documents no slipstream wake "
            "stabilization that takes a blade count, and this motion asks for it with "
            f"{wake_stabilization_blades} blades. Leave wake_stabilization_blades unset "
            f"on this build, or build the script for one that takes the count "
            f"(Script(version=...)): {', '.join(counted) or 'no registered build'}."
        )


#: The slipstream wake stabilization command; its one home (AD-10), which
#: cases.setup_surfaces emits too.
WAKE_STABILIZATION_COMMAND = "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION"

#: The factor from a speed in rev/min to each unit a Euclidean angular
#: velocity is written in. Keyed by the rotor_vocabulary unit constants, so
#: changing a constant changes the value written.
_FROM_REV_PER_MIN = {"rad/s": 2.0 * math.pi / 60.0, "rev/min": 1.0}


def solver_settings(
    script: Script,
    *,
    vorticity_drag_boundaries: Sequence[int | str] | Literal["all"] | None = None,
    mode: str | None = None,
    time_iterations: int | None = None,
    delta_time: float | None = None,
    aoa: float | None = None,
    sideslip: float | None = None,
    velocity: float | None = None,
    mach: float | None = None,
    ref_velocity: float | None = None,
    ref_mach: float | None = None,
    ref_area: float | None = None,
    ref_length: float | None = None,
    iterations: int | None = None,
    convergence: float | None = None,
    forced_iterations: Toggle | None = None,
    max_threads: int | None = None,
    boundary_layer: str | None = None,
    viscous_coupling: Toggle | None = None,
    viscous_excluded: Sequence[int | str] | None = None,
    surface_roughness: float | None = None,
    thin_boundaries: Sequence[int | str] | Literal["all"] | None = None,
    bulk_separation: BulkSeparation | Mapping | None = None,
    airfoil_separation: Sequence[AirfoilSeparation | Mapping] | None = None,
    axial_vortex_separation: Sequence[AxialVortexSeparation | Mapping] | None = None,
    cylindrical_bulk_separation: Sequence[CylindricalBulkSeparation | Mapping] | None = None,
    stratford_bulk_separation: Sequence[StratfordBulkSeparation | Mapping] | None = None,
    delete_separations: int | Literal["all"] | None = None,
    axial_separation_boundaries: Sequence[int | str] | Literal["all"] | None = None,
    valarezo_separation_boundaries: Sequence[int | str] | Literal["all"] | None = None,
    crossflow_separation_boundaries: Sequence[int | str] | Literal["all"] | None = None,
    crossflow_separation_diameter: float | None = None,
    crossflow_separation_axisymmetric: Toggle | None = None,
    laminar_separation: Toggle | None = None,
    convergence_iterations: int | None = None,
    minimum_cp: float | None = None,
    reynolds_averaged_drag: Toggle | None = None,
    mesh_induced_wake_velocity: Toggle | None = None,
    farfield_layers: int | None = None,
    unsteady_pressure_and_kutta: Toggle | None = None,
    wake_termination_time_steps: int | None = None,
    wake_on_wake_induction: Toggle | None = None,
    additional_wake_relaxation: Toggle | None = None,
    aeroelastic_rbf_type: str | None = None,
    kutta_joukowski_lift: Toggle | None = None,
    print_rotor_induced_velocities: Toggle | None = None,
    adaptive_field_grid_refinement: Toggle | None = None,
    jet_wake_filaments_grid_induction: Toggle | None = None,
    rotor_induced_velocity_blending: float | None = None,
    wake_numerical_relaxation: float | None = None,
    jet_wake_decay_normalized_length: float | None = None,
    wake_decay_constant: float | None = None,
    solver_stabilization: float | None = None,
    disable_ref_velocity: bool = False,
    solver_model: str | None = None,
    valarezo_criterion: Toggle | None = None,
    crossflow_separation_mean_diameter: float | None = None,
    wake_relaxation: Toggle | None = None,
    wake_streamwise_agglomeration: Toggle | None = None,
    adverse_gradient_boundary_layer: Toggle | None = None,
    vortex_ring_normalization: Toggle | None = None,
) -> SolverSetup:
    """Set the solver flags, record their provenance, and return the snapshot.

    Single entry point for every command of the runtime_settings
    (SRC-003 pp.339-340), solver_settings (pp.341-343), and
    advanced_settings (pp.344-346) families. Only the provided flags
    are emitted (plus the library minimum-Cp default, below), so the
    helper serves both the initial setup and the re-emission between
    campaign points; the returned
    :class:`~pyflightstream.script.solver_setup.SolverSetup` snapshot
    records the effective value and provenance of every flag, passed or
    not, and is attached to the script as ``script.solver_setup`` for
    the run manifest.

    Two flags have library-level behavior:

    - ``vorticity_drag_boundaries`` selects the boundaries whose
      induced drag comes from surface vorticity integration. Omitting
      it leaves this script's selection as it stands: nothing, on the
      first settings call, which is the solver default of surface
      pressure integration on every boundary (SRC-003 p.202); the
      selection of the earlier call, on a second settings call of the
      same script, since the line it emitted stays in the script. The
      selection is an analysis-phase command, so when it is passed its
      emission is deferred to the first curated call that reaches the
      analysis phase: :func:`start_solver`, :func:`sweep`,
      :func:`analysis_setup`, or :func:`export_results`. A raw
      ``script.emit("START_SOLVER")`` does not flush it.
    - ``minimum_cp`` unset emits ``SOLVER_MINIMUM_CP -100``: the
      solver's own default -20 (SRC-003 p.221) clips the suction peaks
      of rotor blades, so -100 is the library default (design decision
      of 2026-07-22, retiring the earlier reference-velocity
      workaround); pass the flag to override. The physics references
      were re-validated under this default, 30 of 30 metrics
      bit-identical (report
      PHY-26120_2026-07-23_reseed-cp100-2026-07-23). On a
      FlightStream version without the command nothing is emitted and
      the snapshot honestly records the flag as unknown.

    Parameters
    ----------
    script : Script
        Script under construction.
    vorticity_drag_boundaries : sequence of int or str, ``"all"``, or None
        Boundaries whose induced drag comes from surface vorticity
        integration, by 1-based index or declared boundary label;
        ``"all"`` selects every boundary (-1 form). The manual
        recommends the list for boundaries carrying a user-defined
        trailing-edge condition, a wing for instance, and advises
        against bluff bodies such as a tubular fuselage: a bluff body
        placed on this list reports zero induced drag, which is why
        ``"all"`` is unsafe on a mixed geometry (SRC-003 p.202). None (the
        default) emits no selection command and leaves every boundary
        on the solver's own surface pressure integration, which the
        manual also prescribes for every component in ground effect
        (SRC-003 p.202); an empty sequence is refused, because the
        solver default is expressed by omitting the argument, not by
        selecting nothing. A second settings call on the same script
        may omit the argument: the selection of the earlier call stays
        in the script and in the snapshot. There is no way to unselect
        on a script that already selected; build a fresh
        :class:`~pyflightstream.script.Script` for that.
    mode : str, optional
        Solver time regime: ``STEADY`` (SET_SOLVER_STEADY) or
        ``UNSTEADY`` (SET_SOLVER_UNSTEADY, physical time stepping,
        SRC-003 p.341).
    time_iterations : int, optional
        UNSTEADY only: number of physical time steps.
    delta_time : float, optional
        UNSTEADY only: physical time step in s. For rotary cases the
        manual recommends 8 to 12 degrees of blade rotation per step
        and at least two full rotations (SRC-003 p.210).
    aoa : float, optional
        Angle of attack in deg, magnitude below 90.
    sideslip : float, optional
        Side-slip angle in deg, magnitude below 90.
    velocity : float, optional
        Free-stream magnitude in native simulation length units per second.
        The case workflow converts its physical m/s value before this call.
    mach : float, optional
        Free-stream Mach number.
    ref_velocity : float, optional
        Reference velocity in native length units per second for normalization; for
        rotary or hover cases use the largest characteristic velocity,
        such as the rotor tip speed (SRC-003 p.201).
    ref_mach : float, optional
        Reference Mach number.
    ref_area : float, optional
        Reference area S_ref in simulation length units squared
        (Q*S_ref force normalization, SRC-003 p.223).
    ref_length : float, optional
        Reference length L_ref in simulation length units
        (Q*S_ref*L_ref moment normalization, SRC-003 p.223).
    iterations : int, optional
        Solver iteration count.
    convergence : float, optional
        Residual threshold declaring convergence (SRC-003 p.200).
    forced_iterations : bool or 'ENABLE' or 'DISABLE', optional
        Run the full iteration count regardless of convergence.
    max_threads : int, optional
        Parallel core count.
    boundary_layer : str, optional
        ``LAMINAR``, ``TRANSITIONAL``, or ``TURBULENT``; the default
        transitional model is stated valid for chord Reynolds numbers
        between 500000 and 1500000 (SRC-003 p.203).
    viscous_coupling : bool or 'ENABLE' or 'DISABLE', optional
        Couple the semi-empirical boundary layer model to the
        potential flow solution (attached-flow viscosity only,
        SRC-003 pp.207-208).
    surface_roughness : float, optional
        Surface roughness height in NANOMETRES, which is the manual's
        own unit and unlike every other length this helper takes
        (SRC-003 p.341). Zero states a smooth surface, so there is no
        separate toggle and the value carries the choice.
    thin_boundaries : sequence of int or str, ``"all"``, or None
        Boundaries the solver treats as thin, so both faces of a surface
        are resolved, by 1-based index or declared label
        (SRC-003 p.343). Three states, and they are all distinct: None
        leaves the solver's own list untouched, ``"all"`` emits
        SET_THIN_BOUNDARIES -1 and marks every mesh boundary thin, and
        the empty sequence emits DELETE_THIN_BOUNDARIES and erases the
        list, as on ``viscous_excluded`` below. Absent from the February
        2026 build, whose separation family is the per-mechanism one.
    viscous_excluded : sequence of int or str, optional
        Boundaries excluded from viscous coupling, by 1-based index
        or declared boundary label; verified against the inventory
        declared with declare_existing(boundaries=...) when one
        exists. The empty sequence emits
        DELETE_VISCOUS_EXCLUDED_BOUNDARIES, which is the solver's own
        way of erasing the list (SRC-003 p.341); pass None, or omit the
        flag, to leave the list as the script found it.
    bulk_separation : BulkSeparation or mapping, optional
        Bulk (bluff-body) flow-separation assignment
        (CREATE_BULK_SEPARATION, SRC-003 p.342); see
        :class:`~pyflightstream.script.solver_setup.BulkSeparation`.
        Documented on 26.101 and 26.120, and usable on 26.120 and
        26.121 only. The 26.101 grammar is three arguments
        (SRC-725 p.341) and :class:`BulkSeparation` models the
        four-argument form, so this keyword is REFUSED on that build
        with the three-argument emission named as the way through.
        26.121 is a hotfix of 26.120 and inherits the record, so the
        emitter accepts it there, although that edition documents the
        split commands ``cylindrical_bulk_separation`` and
        ``stratford_bulk_separation`` instead. Read RPT-015 before relying on any of the three: it
        found every documented form of this command refused on both
        26.120 and 26.121. 26.100 has no named separation models at all.
    airfoil_separation : sequence of AirfoilSeparation or mapping, optional
        Airfoil (trailing-edge) separation assignments, one per
        CREATE_AIRFOIL_SEPARATION emission (SRC-003 p.341).
    axial_vortex_separation : sequence of AxialVortexSeparation or mapping, optional
        Axial vortex separation assignments for slender bodies
        (CREATE_AXIAL_VORTEX_SEPARATION, SRC-003 p.342).
    cylindrical_bulk_separation : sequence of CylindricalBulkSeparation or mapping, optional
        Cylindrical bulk separation assignments (SRC-740 p.345);
        documented on 26.121.
    stratford_bulk_separation : sequence of StratfordBulkSeparation or mapping, optional
        Stratford bulk separation assignments (SRC-740 p.345);
        documented on 26.121.
    delete_separations : int or 'all', optional
        Delete one separation model by its 1-based creation index, or
        every one of them with ``"all"`` (DELETE_SEPARATION,
        SRC-003 p.342). Emitted before the four assignment flags above,
        so one call can clear what an opened simulation carried and then
        build its own models on a known-empty list.
    axial_separation_boundaries : sequence of int or str, or 'all', optional
        Boundaries on the axial flow separation list of 26.100
        (SET_AXIAL_SEPARATION_BOUNDARIES, SRC-741 p.339). The empty
        sequence emits the matching DELETE. Documented for 26.100 alone
        and refused elsewhere; RPT-018 measured this command reported
        deprecated and then refused by the 26.101 and 26.121 solvers,
        and did not run it on 26.120. What the later builds want in its
        place is a judgement rather than a measurement: the solver's
        deprecation notice leaves its replacement field empty, and
        ``axial_vortex_separation`` is the assignment model closest to
        this mechanism.
    valarezo_separation_boundaries : sequence of int or str, or 'all', optional
        Boundaries on the Valarezo maximum-lift criterion list of
        26.100 (SRC-741 p.339). The empty sequence emits the erase,
        like every other boundary-list keyword. It was REFUSED for one
        day: RPT-018 measured the name SRC-741 prints for that erase as
        unrecognised by the solver, and the working spelling could not
        be recorded until an entry was allowed to rest on a probe report
        instead of a manual page. It is recorded now, so the erase is
        emitted under the name that works. Superseded from 26.101 by the
        ``valarezo_criterion`` field of
        :class:`~pyflightstream.script.solver_setup.AirfoilSeparation`.
    crossflow_separation_boundaries : sequence of int or str, or 'all', optional
        Boundaries on the cross-flow separation list of 26.100
        (SRC-741 pp.339-340). The empty sequence emits the matching
        DELETE.
    crossflow_separation_diameter : float, optional
        Maximum diameter of the body carrying the 26.100 cross-flow
        separation model, in simulation length units (SRC-741 p.339).
        One diameter applies to the whole list, unlike the later named
        models, which carry a diameter per assignment.
    crossflow_separation_axisymmetric : bool or 'ENABLE' or 'DISABLE', optional
        Axisymmetric vortex shedding for the 26.100 cross-flow
        separation model (SRC-741 p.340).
    laminar_separation : bool or 'ENABLE' or 'DISABLE', optional
        Laminar boundary layer separation (SRC-003 p.345); the one
        member of the separation family documented unchanged across the
        four 26.1x editions. It carries no row for the three pre-26.100
        builds, so it is refused there, and the phrase used to read "all
        four editions" while eight are registered.
    convergence_iterations : int, optional
        Iterations the solver must stay below the convergence
        threshold before convergence is declared (SRC-003 p.344).
    minimum_cp : float, optional
        Lower limiter on the pressure coefficient, dimensionless
        (SRC-003 p.345); see the library-default note above.
    reynolds_averaged_drag : bool or 'ENABLE' or 'DISABLE', optional
        Toggle the Reynolds-averaged (flat plate) boundary layer
        calculations (SRC-003 p.344).
    mesh_induced_wake_velocity : bool or 'ENABLE' or 'DISABLE', optional
        Toggle the mesh-induced wake velocity computation
        (SRC-003 p.344).
    farfield_layers : int, optional
        Far-field agglomeration layer count, integer between 1 and 5;
        the solver default is 3 (SRC-003 p.344).
    unsteady_pressure_and_kutta : bool or 'ENABLE' or 'DISABLE', optional
        Toggle the unsteady Bernoulli and Kutta terms of the unsteady
        solver (SRC-003 p.344).
    wake_termination_time_steps : int, optional
        Time steps after which a fully faded wake vortex filament edge
        is removed (SRC-003 p.344).
    wake_on_wake_induction : bool or 'ENABLE' or 'DISABLE', optional
        Toggle the wake-on-wake induced velocity computation
        (SRC-003 pp.344-345).
    additional_wake_relaxation : bool or 'ENABLE' or 'DISABLE', optional
        Perform one additional wake relaxation iteration
        (SRC-003 p.345).
    aeroelastic_rbf_type : str, optional
        RBF mesh morphing algorithm of the aeroelastic coupling:
        ``WENDLAND_C2``, ``GAUSSIAN``, ``THIN_PLATE_SPLINE``,
        ``MULTI_QUADRATIC``, or ``INV_MULTI_QUADRATIC``
        (SRC-003 p.345).
    kutta_joukowski_lift : bool or 'ENABLE' or 'DISABLE', optional
        Compute the inviscid lift from the bound circulation by the
        Kutta-Joukowski theorem instead of by integrating the surface
        pressure. Changes a reported coefficient, not the flow field
        (SRC-003 p.344).
    print_rotor_induced_velocities : bool or 'ENABLE' or 'DISABLE', optional
        Write the rotor-induced velocities to the log at every time step
        of an unsteady run. A diagnostic whose output volume is
        unbounded on a long run (SRC-003 p.345).
    adaptive_field_grid_refinement : bool or 'ENABLE' or 'DISABLE', optional
        Refine the field-source grid where the solution needs it. The
        manual marks this transonic only, so on a subsonic case it has
        nothing to act on (SRC-003 p.345).
    jet_wake_filaments_grid_induction : bool or 'ENABLE' or 'DISABLE', optional
        Let the jet wake filaments induce velocity on the mesh
        (SRC-003 p.346). NOT AVAILABLE ON 26.121, where passing this
        raises rather than emitting: the build does not recognise the
        command, measured against the solver on 2026-08-08 (RPT-021).
        Documented by the 26.101 and 26.120 editions and by neither
        neighbour.
    rotor_induced_velocity_blending : float, optional
        Blending factor for wake stabilization, dimensionless, between 0
        and 1, solver default 0.25. Not available on 26.100
        (SRC-003 p.345).
    wake_numerical_relaxation : float, optional
        Relaxation factor applied to the wake between iterations,
        dimensionless, between 0 and 1, solver default 0.15. Lowering it
        steadies a wake that will not settle, at the cost of iterations.
        Not available on 26.100 (SRC-003 p.346).
    jet_wake_decay_normalized_length : float, optional
        Distance at which a jet wake decays to a tenth of its initial
        strength, in MULTIPLES OF THE JET WAKE DIAMETER rather than in
        length units. Solver default 100.0, minimum 1.0. Not available
        on 26.100 (SRC-003 p.346).
    solver_stabilization : float, optional
        Maximum level of stabilization applied to the main convergence,
        dimensionless, from 0 to 1. The manual states that 0 is the same
        as disabling it, so this is a strength and not a switch, and it
        takes intermediate values. Not available on 26.100
        (SRC-003 p.346).
    disable_ref_velocity : bool, default False
        Make the solver reference velocity track the free-stream
        velocity instead of holding what `ref_velocity` last set. The
        command takes no argument, so False is the ABSENCE of the
        request rather than a way of asking for the opposite: the solver
        has no way to be told not to do this. Documented by the 26.121
        edition alone (SRC-740 p.342).
    wake_decay_constant : float, optional
        Rate at which wake vorticity decays with distance, in units of
        1/m. The manual gives it as 19.1 divided by a characteristic
        length in METRES, so the unit is derived and is printed nowhere;
        a value computed with the length scale in other units gives a
        wake that decays orders of magnitude too fast or not at all, and
        the number itself does not reveal which. The characteristic
        length is the wing semi-span or largest fin for steady state,
        the blade radius for a rotor or rotor, and the larger of the
        two where both are present. Documented by the 26.121 edition
        alone (SRC-740 p.346).
    solver_model : str, optional
        Flow model the solver runs, one of INCOMPRESSIBLE, SUBSONIC,
        TRANSONIC and LOW_ORDER_SUPERSONIC. Documented by the 25.000
        edition alone (SRC-749 p.302), which is the last one to carry it
        as a command: the 25.100 edition drops the command and gives
        INITIALIZE_SOLVER a SOLVER_MODEL argument in the same release.
        On any build from 25.100 on, set the model there instead.
    valarezo_criterion : bool or 'ENABLE' or 'DISABLE', optional
        Enable the Valarezo pressure-difference criterion for predicting
        the onset of separation. Documented by the three pre-26.100
        editions (SRC-747 p.316) and by none after them.
    crossflow_separation_mean_diameter : float, optional
        Mean diameter of the body the cross-flow separation model
        applies to, strictly positive, in the simulation length units.
        The model needs it because the critical pressure coefficient it
        uses depends on the cross-sectional scale.

        NAMED FOR THE QUANTITY AND NOT FOR THE COMMAND, unlike its
        siblings, and deliberately: the vendor spells the command
        SET_CROSSFLOW_SEPARATION_CP, so mirroring it would put a
        keyword reading `_cp` on an argument the database itself calls
        `mean_diameter`, one screen from `minimum_cp`, which really is a
        pressure coefficient. It shipped as `crossflow_separation_cp`
        in no release. Its 26.100 counterpart is
        `crossflow_separation_diameter`, the same physical quantity
        under a command the vendor named after it. Documented by the
        three pre-26.100 editions (SRC-747 p.316).
    wake_relaxation : bool or 'ENABLE' or 'DISABLE', optional
        Enable relaxation of the wake geometry between solver
        iterations, which damps the wake movement and helps a case that
        oscillates rather than converging. Documented by the three
        pre-26.100 editions (SRC-747 p.319).
    wake_streamwise_agglomeration : bool or 'ENABLE' or 'DISABLE', optional
        Enable agglomeration of wake filament edges along the streamwise
        direction, trading wake resolution for fewer wake elements.
        Documented by the three pre-26.100 editions (SRC-747 p.318).
    adverse_gradient_boundary_layer : bool or 'ENABLE' or 'DISABLE', optional
        Enable the adverse-pressure-gradient treatment in the
        boundary-layer model, which lets the layer thicken approaching
        separation instead of following the flat-plate relation
        everywhere. Documented by the three pre-26.100 editions
        (SRC-747 p.318).
    vortex_ring_normalization : bool or 'ENABLE' or 'DISABLE', optional
        Enable normalization of the vortex-ring strengths on the wake
        panels. The page gives the switch and no definition of what the
        normalization does, so nothing further is stated here.
        Documented by the three pre-26.100 editions (SRC-747 p.318).

    Returns
    -------
    SolverSetup
        The snapshot of effective flag values and provenance, also
        attached to the script as ``script.solver_setup``.

    Raises
    ------
    CommandArgumentError
        If the unsteady arguments and ``mode`` disagree, ``delete_separations`` is neither a
        1-based index nor ``all``, an assignment list is empty, or a flag or field is one the
        script's build does not take.

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.124")
    >>> setup = helpers.solver_settings(script, aoa=2.0, velocity=30.0, iterations=500)
    >>> for line in script.render().splitlines():
    ...     print(line)
    SOLVER_SET_AOA 2.0
    SOLVER_SET_VELOCITY 30.0
    SOLVER_SET_ITERATIONS 500
    SOLVER_MINIMUM_CP -100
    """
    # The facade of AD-17: every keyword, exactly as received, goes to the
    # family emitters of script._settings, which emit in the 0.33.0 order.
    arguments = dict(locals())
    del arguments["script"]
    return _settings.emit_solver_settings(script, arguments)


def sweep(
    script: Script,
    *,
    aoa: Sequence[float] | None = None,
    beta: Sequence[float] | None = None,
    velocity_file: str | None = None,
    clear_solution: Toggle | None = None,
    ref_velocity_same: Toggle | None = None,
    post_run_script: str | None = None,
    start: Toggle = True,
    export_spreadsheet: str | None = None,
) -> None:
    """Configure and run a Sweeper Toolbox sweep (SRC-003 pp.358-360).

    Covers the CUSTOM mode only, which is a SUBSET of what the four
    sweep commands document, and the shape of the subset is an accident
    of how this chapter was first read rather than a design: the
    database and this helper were both written from the worked example
    at SRC-003 p.406, which sweeps three axes in one mode. The
    reference pages give every axis the same grammar, so what is
    missing here is the UNIFORM mode on all axes, the file form on the
    two angle axes, the inline list form on velocity, and the Mach axis
    entirely (PLN-20260806-1100).

    The database no longer has that gap, so the low-level path already
    reaches the whole grammar today::

        script.emit("SWEEPER_SET_AOA_SWEEP", "UNIFORM", [-10.0, 20.0, 1.0])

    Parameters
    ----------
    script : Script
        Script under construction.
    aoa : sequence of float, optional
        Custom angle of attack values in deg.
    beta : sequence of float, optional
        Custom side-slip values in deg.
    velocity_file : str, optional
        Path of the custom velocity list file.
    clear_solution : bool or 'ENABLE' or 'DISABLE', optional
        Clear the solution between sweep runs instead of reusing it.
    ref_velocity_same : bool or 'ENABLE' or 'DISABLE', optional
        Keep the reference velocity equal to the free-stream velocity
        at every sweep point.
    post_run_script : str, optional
        Script executed after each sweep point, for example a surface
        section extraction script.
    start : bool or 'ENABLE' or 'DISABLE'
        Emit SWEEPER_START after the configuration. Starting the sweep
        also lands the induced-drag selection deferred by
        :func:`solver_settings`, right after SWEEPER_START: the
        selection is an analysis-phase command, so this is its
        earliest legal position in a sweeper script.
    export_spreadsheet : str, optional
        Path of the sweep results spreadsheet export.

    Raises
    ------
    CommandArgumentError
        If no axis is given (``aoa``, ``beta`` or ``velocity_file``).

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.124")
    >>> helpers.initialize_solver(script, symmetry="NONE")
    >>> helpers.sweep(script, aoa=[0.0, 2.0, 4.0])
    >>> script.render().splitlines()[-2:]
    ['SWEEPER_SET_AOA_SWEEP CUSTOM 0.0 2.0 4.0', 'SWEEPER_START']
    """
    if aoa is None and beta is None and velocity_file is None:
        raise CommandArgumentError(
            "sweep needs at least one axis (aoa, beta, or velocity_file); a sweep "
            "without values has nothing to run (SRC-003 pp.358-359)"
        )
    clear_solution = _optional_toggle("sweep", "clear_solution", clear_solution)
    ref_velocity_same = _optional_toggle("sweep", "ref_velocity_same", ref_velocity_same)
    start = _read("sweep", "start", start)
    if aoa is not None:
        script.emit("SWEEPER_SET_AOA_SWEEP", "CUSTOM", list(aoa))
    if beta is not None:
        script.emit("SWEEPER_SET_BETA_SWEEP", "CUSTOM", list(beta))
    if velocity_file is not None:
        # BY NAME, not positionally. The velocity command used to declare
        # `filename` as its only tail, so a path was the second positional;
        # the 2026-08-06 redraft gave all four sweep axes the manual's real
        # grammar, where the inline value list comes first and the path
        # second. A positional path bound to `values` and raised, and no
        # test covered this keyword, so the whole suite stayed green.
        script.emit("SWEEPER_SET_VELOCITY_SWEEP", "CUSTOM", filename=velocity_file)
    if clear_solution is not None:
        script.emit("SWEEPER_CLEAR_SOLUTION", _toggle(clear_solution))
    if ref_velocity_same is not None:
        script.emit("SWEEPER_REF_VELOCITY_SAME", _toggle(ref_velocity_same))
    if post_run_script is not None:
        script.emit("SWEEPER_POST_RUN_SCRIPT", "ENABLE", post_run_script)
    if start:
        script.emit("SWEEPER_START")
        _flush_pending_vorticity(script)
    if export_spreadsheet is not None:
        script.emit("SWEEPER_EXPORT_SPREADSHEET", export_spreadsheet)


def analysis_setup(
    script: Script,
    *,
    loads_frame: int | str | None = None,
    moments_model: str | None = None,
    symmetry_loads: Toggle | None = None,
    load_units: str | None = None,
    boundaries: Sequence[int | str] | None = None,
    inviscid_only: Toggle | None = None,
    vorticity_drag_boundaries: Sequence[int | str] | Literal["all"] | None = None,
) -> None:
    """Select how loads and moments are analyzed (SRC-003 pp.350-351).

    TWO GROUPS, TWO POSITIONS. ``symmetry_loads``, ``loads_frame`` and
    ``moments_model`` are init-phase settings and go in a call made
    BEFORE :func:`start_solver`: the solve reads them, and an unsteady
    run's step exports, written during the march, state their moments in
    the frame set when they are written (RPT-064). The other arguments
    are analysis-phase selections and go in a call made after it. A call
    mixing the two groups fits neither position: before the start it
    reaches the analysis phase and the phase guard then refuses
    START_SOLVER; after the start the guard refuses the init setting.

    Parameters
    ----------
    script : Script
        Script under construction.
    loads_frame : int or str, optional
        Coordinate system for evaluating loads and moments; index 1 is
        the reference frame, and created frames may be cited by their
        creation label. Init phase since v0.27.0: set after
        START_SOLVER it reached the final export only (RPT-064).
    moments_model : str, optional
        ``PRESSURE`` (solver default) or ``VORTICITY``. Init phase since
        v0.27.0, with the loads frame.
    symmetry_loads : bool or 'ENABLE' or 'DISABLE', optional
        Include symmetry boundary loads; relevant to half-model runs.
    load_units : str, optional
        ``COEFFICIENTS``, ``NEWTONS``, ``KILO-NEWTONS``,
        ``POUND-FORCE``, or ``KILOGRAM-FORCE``.
    boundaries : sequence of int or str, optional
        Boundaries enabled in the analysis, by 1-based index or
        declared boundary label; boundaries not listed are disabled
        (SRC-003 p.351). Indices are verified against the inventory
        declared with declare_existing(boundaries=...) when one
        exists.
    inviscid_only : bool or 'ENABLE' or 'DISABLE', optional
        Restrict the analysis to inviscid loads and moments.
    vorticity_drag_boundaries : sequence of int or str, ``"all"``, or None
        Deprecated here since v0.3.0: the induced-drag boundary
        selection belongs to :func:`solver_settings` and leaves
        analysis_setup at v1.0.0, the release the ledger entry
        ``ANALYSIS_SETUP_VORTICITY_DRAG_BOUNDARIES`` records
        (PFS-2021.02; the warning text is built from it). Passing it
        still works (with a DeprecationWarning) and replaces any
        selection deferred by :func:`solver_settings`. Boundaries whose induced
        drag comes from surface vorticity integration, by index or
        declared label; a bluff body without a user-defined
        trailing-edge condition reports zero induced drag when placed
        on this list (SRC-003 p.202). The replacement is recorded in
        ``script.solver_setup``, which is the snapshot to serialize; a
        snapshot object returned by an earlier :func:`solver_settings`
        call is frozen and keeps the state of that call.
    """
    _reject_bare_label("analysis_setup", "boundaries", boundaries, allows_all=False)
    _reject_bare_label(
        "analysis_setup", "vorticity_drag_boundaries", vorticity_drag_boundaries, allows_all=True
    )
    symmetry_loads = _optional_toggle("analysis_setup", "symmetry_loads", symmetry_loads)
    inviscid_only = _optional_toggle("analysis_setup", "inviscid_only", inviscid_only)
    # Resolve this call's own selection before anything is emitted or
    # recorded, exactly as solver_settings does: a bad label must leave
    # the script, the deferred selection, and the snapshot untouched.
    chosen: list[int] | Literal["all"] | None = None
    if vorticity_drag_boundaries is not None:
        if vorticity_drag_boundaries == "all":
            chosen = "all"
        else:
            items = list(vorticity_drag_boundaries)
            _reject_empty_selection("analysis_setup", "vorticity_drag_boundaries", items)
            chosen = [
                script.resolve_boundary(
                    item, context="analysis_setup: argument 'vorticity_drag_boundaries'"
                )
                for item in items
            ]
        replaced = (
            " This explicit call replaces the selection deferred by solver_settings."
            if script._pending_vorticity is not None
            else ""
        )
        # The text comes from the ledger, so the version it names and
        # the one the deadline guard enforces cannot disagree.
        warnings.warn(
            f"{ANALYSIS_SETUP_VORTICITY_DRAG_BOUNDARIES.message()}{replaced}",
            PyflightstreamDeprecationWarning,
            stacklevel=2,
        )
    # THE INIT GROUP FIRST, and it does not flush. symmetry_loads, the loads
    # frame and the moments model are init-phase settings, read DURING the
    # solve: the per-step force plots consume the symmetry setting, and the
    # step exports written during an unsteady march state their moments in
    # whatever frame is set when they are written (RPT-064, B05). So they
    # precede START_SOLVER, and the induced-drag selection deferred by
    # solver_settings stays deferred to after it: flushing it here would put
    # an analysis-phase line before the start, and the phase guard would then
    # refuse START_SOLVER. A call mixing the init group with the analysis
    # selections below is therefore valid in neither position; make one call
    # of each, the first before the start and the second after it.
    if symmetry_loads is not None:
        script.emit("SET_ANALYSIS_SYMMETRY_LOADS", _toggle(symmetry_loads))
    if loads_frame is not None:
        script.emit("SET_SOLVER_ANALYSIS_LOADS_FRAME", loads_frame)
    if moments_model is not None:
        script.emit("SET_ANALYSIS_MOMENTS_MODEL", moments_model)
    if any(
        argument is not None
        for argument in (
            load_units,
            boundaries,
            inviscid_only,
            vorticity_drag_boundaries,
        )
    ):
        # The call reaches the analysis phase: land the selection
        # deferred by solver_settings before the analysis choices,
        # unless this call carries its own, which replaces it below.
        if chosen is None:
            _flush_pending_vorticity(script)
    if load_units is not None:
        script.emit("SET_LOADS_AND_MOMENTS_UNITS", load_units)
    if boundaries is not None:
        script.emit("SET_SOLVER_ANALYSIS_BOUNDARIES", len(boundaries), list(boundaries))
    if inviscid_only is not None:
        script.emit("SET_INVISCID_LOADS", _toggle(inviscid_only))
    if chosen == "all":
        script.emit("SET_VORTICITY_DRAG_BOUNDARIES", -1)
    elif chosen is not None:
        script.emit("SET_VORTICITY_DRAG_BOUNDARIES", len(chosen), list(chosen))
    if chosen is not None:
        # Every emission of this call succeeded, so the script state and
        # the snapshot may now record the replacement: a failure above
        # leaves the selection solver_settings deferred still pending.
        script._pending_vorticity = None
        script._vorticity_selection = chosen
        if script.solver_setup is not None:
            script.solver_setup = with_vorticity_selection(script.solver_setup, chosen)


def export_results(
    script: Script,
    *,
    spreadsheet: str | None = None,
    tecplot: str | None = None,
    vtk: str | None = None,
    vtk_boundaries: Sequence[int | str] | Literal["all"] = "all",
    vtk_variables: Sequence[str] | Literal["all"] | None = None,
    vtk_wake: Toggle = False,
    force_distributions: str | None = None,
) -> None:
    """Export the solver results that were requested (SRC-003 pp.352-354).

    Parameters
    ----------
    script : Script
        Script under construction.
    spreadsheet : str, optional
        Path of the loads and moments spreadsheet, the primary
        quantitative output of a steady run.
    tecplot : str, optional
        Path of the Tecplot .dat export.
    vtk : str, optional
        Path of the VTK export.
    vtk_boundaries : sequence of int or str, or ``"all"``
        Boundaries included in the VTK export, by 1-based index or
        declared boundary label.
    vtk_variables : sequence of str, ``"all"``, or None
        Variables selected before the VTK export; None keeps the
        current selection. ``CP`` is flagged for depreciation in favor
        of ``CP_REFERENCE`` and ``CP_FREESTREAM`` (SRC-003 p.352); the
        helper warns when it is requested.
    vtk_wake : bool or 'ENABLE' or 'DISABLE'
        Include the wake in the VTK variable selection.
    force_distributions : str, optional
        Path of the force distribution vectors export, all boundaries.
    """
    _reject_bare_label("export_results", "vtk_boundaries", vtk_boundaries, allows_all=True)
    vtk_wake = _read("export_results", "vtk_wake", vtk_wake)
    # Exports read the analysis state: land the induced-drag selection
    # deferred by solver_settings before the first export command.
    _flush_pending_vorticity(script)
    if spreadsheet is not None:
        script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", spreadsheet)
    if tecplot is not None:
        script.emit("EXPORT_SOLVER_ANALYSIS_TECPLOT", tecplot)
    if vtk_variables == "all":
        script.emit("SET_VTK_EXPORT_VARIABLES", -1, _toggle(vtk_wake))
    elif vtk_variables is not None:
        if any(variable.upper() == "CP" for variable in vtk_variables):
            warnings.warn(
                "the CP export variable is flagged for depreciation; prefer "
                "CP_REFERENCE or CP_FREESTREAM (SRC-003 p.352)",
                PyflightstreamWarning,
                stacklevel=2,
            )
        script.emit(
            "SET_VTK_EXPORT_VARIABLES", len(vtk_variables), _toggle(vtk_wake), list(vtk_variables)
        )
    if vtk is not None:
        if vtk_boundaries == "all":
            script.emit("EXPORT_SOLVER_ANALYSIS_VTK", vtk, -1)
        else:
            script.emit(
                "EXPORT_SOLVER_ANALYSIS_VTK", vtk, len(vtk_boundaries), list(vtk_boundaries)
            )
    if force_distributions is not None:
        script.emit("EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS", force_distributions, -1)


def probe_points(
    script: Script,
    points: Sequence[tuple[float, float, float]],
    *,
    kind: str = "VOLUME",
) -> None:
    """Create individual probe points (SRC-003 p.362).

    Parameters
    ----------
    script : Script
        Script under construction.
    points : sequence of (x, y, z) triples
        Probe positions in the reference frame, simulation length
        units.
    kind : str
        ``VOLUME`` or ``SURFACE`` probes.
    """
    for x, y, z in points:
        script.emit("NEW_PROBE_POINT", kind, x, y, z)


def probe_line(
    script: Script,
    *,
    points: int,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> None:
    """Create a survey line of probe points (SRC-003 p.362).

    Parameters
    ----------
    script : Script
        Script under construction.
    points : int
        Number of probe vertices between start and end.
    start, end : (x, y, z) triples
        Line ends in the reference frame, simulation length units.
    """
    script.emit("NEW_PROBE_LINE", points, *start, *end)


def probes_from_file(script: Script, path: str, *, units: str, frame: int | str = 1) -> None:
    """Import a probe lattice from a CSV file (SRC-003 pp.362-363).

    The file rows are X,Y,Z,TYPE with TYPE 0 for surface and 1 for
    volume probes; the first line holds the point count. This is the
    programmatic path for probe lattice generation.

    Parameters
    ----------
    script : Script
        Script under construction.
    path : str
        Probe lattice CSV path.
    units : str
        Length unit of the file coordinates (``METER``, ``INCH``, and
        the other simulation length units).
    frame : int or str
        Coordinate system of the file coordinates; index 1 is the
        reference frame, and created frames may be cited by their
        creation label.
    """
    script.emit("PROBE_POINTS_IMPORT", units, frame, path)


def export_probes(script: Script, path: str, *, update: Toggle = True) -> None:
    """Export the probe values, refreshing them first (SRC-003 pp.362-363).

    Parameters
    ----------
    script : Script
        Script under construction.
    path : str
        Export file path.
    update : bool or 'ENABLE' or 'DISABLE'
        Emit UPDATE_PROBE_POINTS first, so the export reflects the
        current solution; the manual instructs refreshing before
        exporting (SRC-003 p.362).

    Raises
    ------
    CommandArgumentError
        If this script has already exported to ``path``. The solver
        writes one file per path, so two exports to one path meant the
        second silently replaced the first; the script rendered two
        identical lines and nothing anywhere recorded that only one
        survived (PFS-2011.02).

        The message names BOTH call sites, because one naming only the
        second sends the reader to the wrong line: the one they need to
        change is usually the earlier one.

    Notes
    -----
    The register lives on the :class:`~pyflightstream.script.Script`
    rather than here, because the collision is between two CALLS and
    only the script sees both.
    """
    already = script._exported_paths.get(path)
    if already is not None:
        raise CommandArgumentError(
            f"this script already exports to {path!r}, from {already}. The solver "
            "writes one file per path, so the second export would silently replace "
            f"the first and the script would carry two identical lines. Give "
            f"export_probes a path of its own, for example one carrying the point "
            "or the survey name."
        )
    if _read("export_probes", "update", update):
        script.emit("UPDATE_PROBE_POINTS")
    script.emit("EXPORT_PROBE_POINTS", path)
    script._exported_paths[path] = "export_probes"


def coordinate_frame(
    script: Script,
    *,
    name: str,
    origin: Sequence[float],
    x_axis: Sequence[float],
    y_axis: Sequence[float],
    z_axis: Sequence[float] | None = None,
    label: str | None = None,
) -> int:
    """Create and define a local coordinate system, returning its index.

    Emits CREATE_NEW_COORDINATE_SYSTEM followed by
    EDIT_COORDINATE_SYSTEM with the origin and the three axis vectors
    in the reference frame (coordinate_systems chapter). Use it when
    the solver should carry the same plane a probe grid was
    prescribed on; probe positions themselves are always imported in
    the reference frame (frame 1), so this helper is presentation,
    not placement.

    Parameters
    ----------
    script : Script
        Script under construction.
    name : str
        Name of the new coordinate system.
    origin : sequence of float
        Frame origin in the reference frame (simulation length units).
    x_axis, y_axis : sequence of float
        Axis direction vectors in the reference frame.
    z_axis : sequence of float, optional
        Third axis; computed as the right-handed cross product of
        x_axis and y_axis when omitted.
    label : str, optional
        Label registered for the created frame in the script's entity
        registry, so later commands can cite it by name instead of by
        index. Distinct from ``name``, which is the display name
        FlightStream shows in the interface.

    Returns
    -------
    int
        Index of the created frame (the reference frame is 1; created
        local frames follow).
    """
    if z_axis is None:
        ax, ay, az = x_axis
        bx, by, bz = y_axis
        z_axis = (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)
    script.emit("CREATE_NEW_COORDINATE_SYSTEM", label=label)
    frame_index = script.num_local_frames + 1
    script.emit(
        "EDIT_COORDINATE_SYSTEM",
        frame=frame_index,
        name=name,
        origin_x=origin[0],
        origin_y=origin[1],
        origin_z=origin[2],
        vector_x_x=x_axis[0],
        vector_x_y=x_axis[1],
        vector_x_z=x_axis[2],
        vector_y_x=y_axis[0],
        vector_y_y=y_axis[1],
        vector_y_z=y_axis[2],
        vector_z_x=z_axis[0],
        vector_z_y=z_axis[1],
        vector_z_z=z_axis[2],
    )
    return frame_index


#: THE AZIMUTH DATUM, as one named table (PFS-2025.04).
#:
#: Per rotor axis, the two in-plane unit vectors that fix where azimuth
#: zero points and which way azimuth grows: the DATUM first, the
#: QUADRATURE second. They are cyclic, X to (Y, Z), Y to (Z, X) and Z to
#: (X, Y), so the datum crossed with the quadrature is the rotor axis
#: itself for all three, and every blade frame comes out right-handed
#: with its third axis along the rotation.
#:
#: IT IS A PROPOSAL AND NOT A DECISION. Which in-plane direction is
#: azimuth zero is the domain expert's call, recorded as a proposal in
#: reports/RPT-036_the-azimuth-convention-proposal_2026-08-19.md; a wrong
#: datum rotates every blade frame and every phase-locked reduction keyed
#: to blade index, and produces plausible numbers rather than a failure.
#: This table exists so that settling it is ONE edit here rather than a
#: search: nothing else in the library decides where azimuth zero is.
AZIMUTH_BASIS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "X": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "Y": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    "Z": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
}

#: The four angles a first blade is allowed to sit at, in deg. The
#: placement of the other blades is arithmetic, 360/N from this one, so
#: the anchor is the one measured quantity in it, and restricting it to
#: the quadrants is the instruction rather than a numerical
#: convenience.
BLADE_ANCHOR_ANGLES_DEG: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)

#: The sense of rotation a rotor descriptor records, viewed from
#: behind the aircraft looking forward. Declared HERE, in the layer that
#: consumes it, and imported downward by
#: :class:`pyflightstream.workspace.inputs.RotorReference` rather
#: than restated there: the layer rule permits the higher layer to
#: import the lower one, so a second declaration held together by a test
#: would be a second home for one vocabulary. This alias was that second
#: home for one day.
RotationSense = Literal["clockwise", "counterclockwise"]

#: How a rotor's recorded sense of rotation signs the azimuth
#: increment. Counterclockwise about the rotor axis is the
#: mathematically positive sense, so blade k sits at anchor plus k times
#: 360/N; clockwise numbers the blades the other way round the disc.
#: Which of the two a descriptor's own word means, given that the
#: descriptor states its sense as seen from behind, is the same open
#: question the datum is: see RPT-036.
ROTATION_SENSE_SIGN: dict[RotationSense, float] = {
    "counterclockwise": 1.0,
    "clockwise": -1.0,
}

#: Decimal places the emitted axis components are rounded to. A cosine of
#: 90 degrees is 6.1e-17 in binary floating point, and a script line
#: carrying that number is a script line a reader cannot check by eye.
_AXIS_DECIMALS = 12


def _clean(value: float) -> float:
    """Round one axis component and normalise a negative zero away."""
    return round(value, _AXIS_DECIMALS) + 0.0


def azimuth_basis(rotor_axis: str) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return the in-plane datum and quadrature vectors of a rotor axis.

    The single reader of :data:`AZIMUTH_BASIS`, so the convention has one
    home and changing it is one edit.

    Parameters
    ----------
    rotor_axis : str
        Rotation axis of the rotor in the reference frame: ``X``, ``Y``
        or ``Z`` (any case).

    Returns
    -------
    tuple of tuple of float
        The unit vector azimuth zero points along, then the unit vector
        90 degrees of positive azimuth from it.

    Raises
    ------
    CommandArgumentError
        If the axis is not one of the three, naming what was passed.

    Examples
    --------
    >>> from pyflightstream.script.helpers import azimuth_basis
    >>> azimuth_basis("Z")
    ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    """
    key = rotor_axis.upper() if isinstance(rotor_axis, str) else rotor_axis
    try:
        return AZIMUTH_BASIS[key]
    except (KeyError, TypeError) as error:
        raise CommandArgumentError(
            f"blade_frames: rotor_axis is {rotor_axis!r}, and a rotor axis is one of "
            f"{', '.join(sorted(AZIMUTH_BASIS))}. The axis is what fixes the plane the "
            "blades are placed in, so there is no default to fall back on"
        ) from error


def blade_frames(
    script: Script,
    *,
    hub_origin: Sequence[float],
    rotor_axis: str,
    n_blades: int,
    blade1_azimuth_deg: float,
    rotation: RotationSense,
    names: Sequence[str] | None = None,
    labels: Sequence[str] | None = None,
) -> list[int]:
    """Create one motion-following coordinate system per blade.

    Places ``n_blades`` local frames 360/N apart around the rotor disc,
    anchored on the first blade, each with its x axis along that blade's
    radial direction and its z axis along the rotor axis, so an azimuthal
    reduction afterwards has a frame per blade to reduce in. The returned
    indices are what :func:`rotary_motion` is handed as ``moving_frames``,
    which is what binds the frames to the motion and makes them follow it.

    THE PLACEMENT IS ARITHMETIC AND NOT GEOMETRY. Nothing here reads a
    mesh and nothing computes a centroid: N blades sit 360/N apart, and
    the only measured quantity is the first blade's azimuth, which must
    be one of :data:`BLADE_ANCHOR_ANGLES_DEG`.

    Parameters
    ----------
    script : Script
        Script under construction.
    hub_origin : sequence of float
        Hub position in the reference frame, in simulation length units.
        Every blade frame shares it: the frames differ in orientation and
        not in origin, because they rotate about the same hub.
    rotor_axis : str
        Rotation axis in the reference frame, ``X``, ``Y`` or ``Z``. It
        selects the in-plane pair of :data:`AZIMUTH_BASIS`.
    n_blades : int
        Blade count, at least 1.
    blade1_azimuth_deg : float
        Azimuth of the first blade, in deg, measured from the datum of
        :func:`azimuth_basis` and positive towards the quadrature vector.
        One of :data:`BLADE_ANCHOR_ANGLES_DEG`.
    rotation : {"clockwise", "counterclockwise"}
        Sense of rotation, viewed from behind the aircraft looking
        forward, the vocabulary a rotor descriptor records in its
        ``rotation`` field. It signs the azimuth increment, so it decides
        which way round the disc the blades are numbered and nothing
        else.

        REQUIRED, with no default. It carried one on the branch that
        added this function and never in a release, so no caller is
        migrating: the default was removed before shipping because the
        refusal below says there is no safe default to guess and the
        signature was making one. A wrong sense renumbers the blades,
        raises nothing, and every phase-locked reduction keyed to blade
        index inherits it.
    names : sequence of str, optional
        Display names of the created frames, one per blade; ``Blade1`` to
        ``BladeN`` by default.
    labels : sequence of str, optional
        Labels registered in the script's entity registry, one per blade,
        so later commands can cite a blade frame by name. A frame label
        and a boundary label are different entity kinds and cannot
        collide.

    Returns
    -------
    list of int
        The created frame indices, in blade order, ready to pass to
        :func:`rotary_motion` as ``moving_frames``.

    Raises
    ------
    CommandArgumentError
        If the blade count is below one, the rotor axis is not one of the
        three, the rotation sense is not one of the two, the first
        blade's azimuth is not one of the four anchors (the measured
        angle is named), or a ``names`` or ``labels`` sequence has a
        different length from the blade count. Every one of these fires
        before anything is emitted, so a refused call leaves the script
        untouched.

    Notes
    -----
    The azimuth datum this places blades against is a PROPOSAL awaiting
    the domain expert's decision (RPT-036). A wrong datum rotates every
    blade frame together, and every phase-locked reduction keyed to blade
    index with them, and it produces plausible numbers rather than an
    error, which is why it is written down where the placement is made.

    Deleting a coordinate system renumbers the frames above it downward
    (RPT-021 section 3), and this helper creates N of them per rotor. Do
    not delete a frame between this call and the citations of the indices
    it returned.

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.120")
    >>> frames = helpers.blade_frames(
    ...     script,
    ...     hub_origin=(1.2, 0.0, 0.0),
    ...     rotor_axis="Z",
    ...     n_blades=3,
    ...     blade1_azimuth_deg=90.0,
    ...     rotation="counterclockwise",
    ... )
    >>> frames
    [2, 3, 4]
    >>> motion = helpers.rotary_motion(
    ...     script, frame=frames[0], axis="Z", rpm=2400.0, moving_frames=frames
    ... )
    """
    datum, quadrature = azimuth_basis(rotor_axis)
    if not isinstance(n_blades, int) or isinstance(n_blades, bool) or n_blades < 1:
        raise CommandArgumentError(
            f"blade_frames: n_blades is {n_blades!r}, and a rotor with {n_blades} blades "
            "has no blade to anchor the placement on. Pass the blade count of the "
            "rotor, which is at least 1"
        )
    if rotation not in ROTATION_SENSE_SIGN:
        raise CommandArgumentError(
            f"blade_frames: rotation is {rotation!r}, and the sense of rotation is "
            f"{' or '.join(sorted(ROTATION_SENSE_SIGN))}, the two words the rotation "
            "field of a rotor descriptor records. It decides which way round the "
            "disc the blades are numbered, so there is no safe default to guess. If "
            "you are holding inboard_up or inboard_down, that is the same fact in the "
            "vocabulary a datasheet prints, it is recorded separately as blade_travel, "
            "and turning it into a sense here needs the side of the aircraft this "
            "rotor is on, which this function is never told"
        )
    if float(blade1_azimuth_deg) not in BLADE_ANCHOR_ANGLES_DEG:
        anchors = ", ".join(str(angle) for angle in BLADE_ANCHOR_ANGLES_DEG)
        raise CommandArgumentError(
            f"blade_frames: the first blade was measured at {float(blade1_azimuth_deg)} "
            f"deg, and this placement anchors on one of {anchors} deg. The other blades "
            "are placed arithmetically at 360/N from that one, so an anchor off the "
            "quadrants would put every blade somewhere the convention cannot name. "
            "Rotate the mesh onto a quadrant, or record the rotor with the blade "
            "the mesh actually starts at"
        )
    if names is not None and len(names) != n_blades:
        raise CommandArgumentError(
            f"blade_frames: names carries {len(names)} name(s) for {n_blades} blades. "
            f"One display name per blade, or leave it out for Blade1 to Blade{n_blades}"
        )
    if labels is not None and len(labels) != n_blades:
        raise CommandArgumentError(
            f"blade_frames: labels carries {len(labels)} label(s) for {n_blades} blades. "
            "One registry label per blade, or leave it out to cite the frames by the "
            "indices this returns"
        )

    sign = ROTATION_SENSE_SIGN[rotation]
    spacing = 360.0 / n_blades
    created: list[int] = []
    for blade in range(n_blades):
        azimuth = math.radians(float(blade1_azimuth_deg) + sign * blade * spacing)
        cosine, sine = math.cos(azimuth), math.sin(azimuth)
        pair = list(zip(datum, quadrature, strict=True))
        radial = tuple(_clean(cosine * d + sine * q) for d, q in pair)
        tangential = tuple(_clean(-sine * d + cosine * q) for d, q in pair)
        created.append(
            coordinate_frame(
                script,
                name=names[blade] if names is not None else f"Blade{blade + 1}",
                origin=hub_origin,
                # x radial, y tangential towards growing azimuth; z is
                # left to the cross product, which is then the rotor axis
                # exactly because the basis pair is cyclic.
                x_axis=radial,
                y_axis=tangential,
                label=labels[blade] if labels is not None else None,
            )
        )
    return created


#: The mesh rotation, in the two names it goes by, newest first.
#:
#: THE ORDER CARRIES NOTHING TODAY, and saying so is the correction the
#: adversarial pass forced: this comment claimed the order was the search
#: order, and reversing the tuple broke no test, because EXACTLY ONE of
#: the two resolves on every registered build. That is the load-bearing
#: property, and it is what
#: `test_exactly_one_rotation_command_resolves_on_every_registered_build`
#: measures. The order would start mattering the day a build documented
#: both, which is why the loop takes the first that resolves rather than
#: asserting there is only one.
#:
#: They are NOT one command renamed, which the database records as its
#: own reading: SURFACE_ROTATE is a keyword block of eight arguments and
#: ROTATE_SURFACE is a payload-lines command of six, with no equivalent
#: of SPLIT_VERTICES or ADAPTIVE_MESH.
ROTATION_COMMANDS: tuple[str, ...] = ("ROTATE_SURFACE", "SURFACE_ROTATE")

#: Trailing index of a boundary label, which is what a component name is
#: the label without. ``Blade_1``, ``Blade 2`` and ``Blade3`` all carry
#: the component ``blade``.
_COMPONENT_INDEX = re.compile(r"[\s_.-]*\d+$")


def _component_of(label: str) -> str:
    """Return the component a boundary label belongs to, case-folded."""
    return _COMPONENT_INDEX.sub("", label).casefold()


def _rotation_command(script: Script) -> str:
    """Return the mesh-rotation command this script's build documents."""
    for name in ROTATION_COMMANDS:
        try:
            script._view[name]
        except CommandNotInVersionError:
            continue
        return name
    raise CommandArgumentError(
        f"rotate_surfaces: FlightStream {script.version.canonical} documents neither "
        f"{ROTATION_COMMANDS[0]} nor {ROTATION_COMMANDS[1]}, so this build has no "
        "recorded way to rotate an existing mesh. The capability is one command on "
        "every build up to 26.121 and the other from 26.122; a build carrying neither "
        "has no row for either command in this database rather than no capability"
    )


def rotate_surfaces(
    script: Script,
    *,
    frame: int | str,
    axis: str,
    angle_deg: float,
    component: str | None = None,
    boundaries: Sequence[int | str] | Literal["all"] = "all",
    detach: Toggle = False,
    split_vertices: Toggle = False,
    adaptive_mesh: Toggle = False,
    after_initialization: bool = False,
) -> None:
    """Rotate existing mesh surfaces about an axis of a named frame.

    THIS ACTS ON THE MESH AND NOT ON THE GEOMETRY, which is what decides
    which command family is meant: the surface transforms, never the
    CAD-body or curve ones. The rotation is about an axis of the named
    coordinate system, so the system's origin is the point it turns
    about.

    The command is chosen from the script's own build, because the
    capability changed name at 26.122 and the two grammars are not
    interchangeable (:data:`ROTATION_COMMANDS`).

    Parameters
    ----------
    script : Script
        Script under construction.
    frame : int or str
        Coordinate system the rotation is about, by 1-based index or by
        creation label. Its origin is the point rotated about and its
        ``axis`` is the axis rotated around. An unknown label is refused
        by the emitter, naming the labels the script knows.
    axis : str
        Axis of ``frame``: ``X``, ``Y`` or ``Z``. The older command also
        documents the numeric spellings; this helper passes the token
        through, so a numeric one is refused by the emitter on the build
        whose grammar does not carry it.
    angle_deg : float
        Rotation angle in deg, about ``axis``, in the sense the solver
        applies for that command.
    component : str, optional
        Rotate every declared boundary whose label belongs to this
        component, which is the label with its trailing index removed
        and matched without regard to case. ``"Blade"`` therefore selects
        all N blades, which is the way a rotor incidence change is
        expressed. Mutually exclusive with ``boundaries``.
    boundaries : sequence of int or str, or ``"all"``
        Explicit selection, by 1-based index or declared boundary label;
        ``"all"`` is the -1 form and selects every surface.
    detach : bool or 'ENABLE' or 'DISABLE'
        Emitted as DETACH_NORMAL_TO_AXIS on the older command and as
        DETACH_VERTICES on the newer one. WHETHER THOSE ARE ONE OPTION
        RENAMED IS UNMEASURED: it is read from their position on the
        manual page and no probe has asked, which the command database
        records for the pair. Left off by default for that reason.
    split_vertices, adaptive_mesh : bool or 'ENABLE' or 'DISABLE'
        Options of the older command only. Asking for either on a build
        that documents the newer one is refused rather than dropped: a
        silently discarded mesh option produces a different mesh, on a
        build the helper chose rather than the caller.
    after_initialization : bool
        Emit the rotation through
        :meth:`~pyflightstream.script.Script.emit_after_initialization`, on a
        solver already initialised, which must then be initialised again
        before it starts. The quasi-steady rotor clocks its wheel this way
        between two steady solves (0.30.0).

    Raises
    ------
    CommandArgumentError
        If both ``component`` and an explicit ``boundaries`` selection
        are given, if a dropped option is asked for on the build that
        does not carry it, or if the build documents neither command.
    ScriptReferenceError
        If ``component`` matches no declared boundary label (the message
        names the component and every label declared), or if a cited
        frame or boundary label is unknown.

    Notes
    -----
    Component matching reads the boundary inventory declared with
    :meth:`~pyflightstream.script.Script.declare_existing`, because the
    boundary names live in the geometry file and the builder cannot know
    them otherwise. A script that declared no inventory has no component
    to expand and is told so.

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.123")
    >>> script.declare_existing(frames=1, boundaries={"Blade_1": 1, "Blade_2": 2})
    >>> helpers.rotate_surfaces(script, frame=1, axis="Z", angle_deg=2.5, component="Blade")
    >>> print(script.render().strip())
    ROTATE_SURFACE 1 Z 2.5 2 DISABLE
    1,2
    """
    command = _rotation_command(script)
    detach_on = _read("rotate_surfaces", "detach", detach)
    split_on = _read("rotate_surfaces", "split_vertices", split_vertices)
    adaptive_on = _read("rotate_surfaces", "adaptive_mesh", adaptive_mesh)

    _reject_bare_label("rotate_surfaces", "boundaries", boundaries, allows_all=True)
    if component is not None and boundaries != "all":
        raise CommandArgumentError(
            f"rotate_surfaces: component={component!r} and an explicit boundaries "
            "selection were both given, and they are two answers to one question. "
            "Name the component, or list the boundaries, not both"
        )

    if command == "ROTATE_SURFACE":
        for argument, requested in (
            ("split_vertices", split_on),
            ("adaptive_mesh", adaptive_on),
        ):
            if requested:
                raise CommandArgumentError(
                    f"rotate_surfaces: {argument} was asked for, and "
                    f"{command}, which is what FlightStream "
                    f"{script.version.canonical} documents, has no equivalent of it. "
                    "The option belongs to SURFACE_ROTATE, which that build stops "
                    "printing. Emitting the rotation without it would give you a "
                    "different mesh under an argument the call still carried, so it is "
                    "refused instead. Run this rotation on a build up to 26.121, or "
                    "drop the option deliberately"
                )

    if component is not None:
        declared = script.entities.labels("boundaries")
        wanted = component.casefold()
        selection: list[int | str] = [
            index for label, index in sorted(declared.items()) if _component_of(label) == wanted
        ]
        if not selection:
            known = ", ".join(f"{label!r}" for label in sorted(declared)) or "none"
            raise ScriptReferenceError(
                f"rotate_surfaces: component {component!r} matches no declared boundary "
                f"label; declared labels are {known}. A component is a label with its "
                "trailing index removed, so 'Blade' selects Blade_1 and Blade2 alike. "
                "Declare the geometry's boundary names with declare_existing("
                "boundaries={...}) before rotating by component"
            )
    elif boundaries == "all":
        selection = []
    else:
        selection = list(boundaries)
        _reject_empty_selection("rotate_surfaces", "boundaries", list(selection))

    count = -1 if (component is None and boundaries == "all") else len(selection)
    arguments: dict[str, object] = {
        "frame": frame,
        "axis": axis,
        "angle": angle_deg,
        "surfaces": count,
    }
    if count != -1:
        arguments["surface_indices"] = selection
    if command == "ROTATE_SURFACE":
        arguments["detach_vertices"] = _toggle(detach_on)
    else:
        arguments["split_vertices"] = _toggle(split_on)
        arguments["adaptive_mesh"] = _toggle(adaptive_on)
        arguments["detach_normal_to_axis"] = _toggle(detach_on)
    if after_initialization:
        script.emit_after_initialization(command, **arguments)
    else:
        script.emit(command, **arguments)


#: The action registration, and the two kinds it takes.
UNSTEADY_ACTION_COMMAND = "SET_NEW_UNSTEADY_SOLVER_ACTION"
UNSTEADY_ACTION_KINDS = ("SCRIPT", "COMMAND_LINE")


def unsteady_action(
    script: Script,
    *,
    name: str,
    kind: str,
    filename: str,
    action_script: str | None = None,
) -> UnsteadyActionUse:
    """Register an action the solver runs after each unsteady time step.

    This is what lets a section export come out mid-run instead of by
    stopping the solver and restarting it: the solver executes the
    registered action after each time step, in the order the actions
    were created.

    THE EVIDENCE IS STATED ONCE, HERE. The command is documented on the
    two newest builds and probed on none, so the returned record carries
    the status the database holds for this script's build and whether it
    was inherited. A build that does not document the command at all is
    refused by the emitter, naming the command and the build, rather
    than the workflow degrading into a run whose sections never appear.

    Parameters
    ----------
    script : Script
        Script under construction.
    name : str
        Name of the action, unique within this script. The solver
        accepts several actions and runs them in creation order, so the
        name is how a reader tells two apart.
    kind : str
        ``SCRIPT`` to run a FlightStream script, ``COMMAND_LINE`` to run
        a shell command.
    filename : str
        The path the registration line names, passed through unchanged.
        NOTHING IN EITHER MANUAL EDITION SAYS WHICH DIRECTORY THE SOLVER
        RUNS AN ACTION FROM (RPT-030), so this helper neither resolves
        nor rewrites it. Measured on 26.123 (RPT-041, the script-action
        re-read probe): the action runs from the directory the solver was
        started in, the simulation folder. That a relative path resolves
        there follows from it and was not measured; the probe used
        absolute paths.
    action_script : str, optional
        Text of the child FlightStream script, parked on the script for
        the run layer to write at ``filename``. Only for ``SCRIPT``
        actions: a shell action names a command, and there is no child
        script for this library to write.

    Returns
    -------
    UnsteadyActionUse
        The record of the registration, also appended to
        :attr:`~pyflightstream.script.Script.unsteady_actions`.

    Raises
    ------
    CommandArgumentError
        If ``kind`` is not one of the two, if the name repeats one
        already registered on this script, if two actions would write
        one filename (the second would silently replace the first), or
        if a shell action is given a child script.
    CommandNotInVersionError
        If the build does not document the command. Raised by the
        emitter, so the message carries the recorded evidence of every
        build that does.

    Notes
    -----
    WHAT THE ACTION RECEIVES IS UNSTATED, on all four of the things a
    step-aware action would need: arguments, working directory, step
    index or physical time, and environment (RPT-030). An action that
    has to behave differently on different steps therefore needs state
    of its own, and the correctness of that route rests on the
    invocation count being exactly the step count. MEASURED ON 26.123
    (RPT-041, the script-action re-read probe, 2026-09-08): a SCRIPT
    action's file is re-read on every
    invocation, the count is exactly the step count with nothing before
    the first step, the action gets no arguments and no solver-named
    environment, runs from the simulation folder, and an export it makes
    is stamped ``_iteration=<step>`` on its name. That is evidence about
    one build; nothing here builds on it for another.

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.123")
    >>> record = helpers.unsteady_action(
    ...     script,
    ...     name="sections",
    ...     kind="SCRIPT",
    ...     filename="actions/sections.txt",
    ...     action_script="EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
    ... )
    >>> record.evidence
    'documented'
    >>> sorted(script.pending_action_scripts)
    ['actions/sections.txt']
    """
    if kind not in UNSTEADY_ACTION_KINDS:
        raise CommandArgumentError(
            f"unsteady_action: kind is {kind!r}, and an action is one of "
            f"{' or '.join(UNSTEADY_ACTION_KINDS)}: a FlightStream script the solver "
            "runs, or a shell command it runs. The two are not interchangeable, so "
            "there is no default"
        )
    if kind == "COMMAND_LINE" and action_script is not None:
        raise CommandArgumentError(
            "unsteady_action: a COMMAND_LINE action names a shell command and has no "
            "child FlightStream script, so action_script has nowhere to be written. "
            "Register the action with kind='SCRIPT' to have this library write the "
            "child script, or write the command's own file yourself"
        )
    if name in script._unsteady_actions:
        raise CommandArgumentError(
            f"unsteady_action: this script already registers an action named {name!r}. "
            "The solver runs registered actions in creation order and the order cannot "
            "be changed afterwards, so the name is the only handle a reader has on "
            "which action is which; give the second one a name of its own"
        )
    # A filename equal to a parked one but for case is the same file on a
    # case-insensitive file system (Windows), so it is held to the same rule.
    parked = next(
        (key for key in script._pending_action_scripts if _same_file(key, filename)),
        None,
    )
    if parked is not None and action_script is not None:
        where = _where_parked(parked, filename)
        raise CommandArgumentError(
            f"unsteady_action: this script already writes an action script to "
            f"{where}. One path is one file, so the second would silently replace "
            "the first and both registration lines would point at whichever text won. "
            "Give this action a filename of its own"
        )

    entry = script.registry.commands.get(UNSTEADY_ACTION_COMMAND)
    evidence = entry.evidence_in(script.version) if entry is not None else None
    record = UnsteadyActionUse(
        name=name,
        kind=kind,
        filename=filename,
        evidence=str(evidence.record.status) if evidence is not None else None,
        inherited=evidence.inherited if evidence is not None else False,
    )

    # Emit BEFORE recording: a build that does not carry the command must
    # leave the script with no action registered and nothing parked, so
    # the refusal is not half applied.
    script.emit(UNSTEADY_ACTION_COMMAND, kind, name, filename)
    script._unsteady_actions[name] = record
    if action_script is not None:
        script._pending_action_scripts[filename] = action_script
    return record


#: Marking wake edges from an imported node list, and the angle
#: criterion it replaces. Named as a pair because the whole point of the
#: refusal below is that one is never silently substituted for the other.
WAKE_EDGE_IMPORT_ROUTE = "IMPORT_WAKE_EDGES_FROM_FILE"
WAKE_EDGE_ANGLE_ROUTE = "AUTO_DETECT_TRAILING_EDGES"

#: The coordinate line the 26.124 import consumes after the count and does
#: not use (RPT-061): the first line holding three numbers is read and
#: discarded, so a file without it loses its first point. It is a triple
#: because a bare number or an empty line is skipped rather than consumed.
WAKE_EDGE_NODE_PLACEHOLDER = "0,0,0"


def render_wake_edge_node_file(midpoints: Sequence[Sequence[float]]) -> str:
    """Return the text of the node file the wake-edge import reads on 26.124.

    The layout is the one measured to mark (RPT-061): the number of points,
    then :data:`WAKE_EDGE_NODE_PLACEHOLDER`, the coordinate line the solver
    consumes and does not use, then one ``x,y,z`` row per trailing-edge
    MID-POINT, in the simulation's length unit. There is no unit line and
    no id column: the file's unit is not read, and a word or an id on any
    line makes the import mark nothing, in silence.

    Parameters
    ----------
    midpoints : sequence of (x, y, z)
        The mid-points of the mesh edges to mark, already in the
        simulation's length unit. Any sequence of three-number rows,
        including an (n, 3) array.

    Returns
    -------
    str
        The file's text, newline separated and newline terminated.

    Raises
    ------
    CommandArgumentError
        If there is no point, a row is not three coordinates, or a
        coordinate is not a finite number. Each names the point.

    Examples
    --------
    >>> from pyflightstream.script import helpers
    >>> print(helpers.render_wake_edge_node_file([(1.0, -3.75, 0.0)]), end="")
    1
    0,0,0
    1.0,-3.75,0.0
    """
    rows = list(midpoints)
    if not rows:
        raise CommandArgumentError(
            f"{WAKE_EDGE_IMPORT_ROUTE} node file: 0 edge mid-points were given, and the "
            "points are what name the edges to mark. With none the import marks nothing "
            "and says nothing, so the run would solve with no wake"
        )
    lines = [str(len(rows)), WAKE_EDGE_NODE_PLACEHOLDER]
    for position, row in enumerate(rows, start=1):
        where = f"point {position} of {len(rows)}"
        try:
            values = [float(value) for value in row]
        except (TypeError, ValueError) as error:
            raise CommandArgumentError(
                f"{WAKE_EDGE_IMPORT_ROUTE} node file: {where} is {row!r}, which is not "
                f"three coordinates ({error})"
            ) from error
        if len(values) != 3:
            raise CommandArgumentError(
                f"{WAKE_EDGE_IMPORT_ROUTE} node file: {where} holds {len(values)} values, "
                "and every point is three coordinates, x, y and z"
            )
        if not all(math.isfinite(value) for value in values):
            raise CommandArgumentError(
                f"{WAKE_EDGE_IMPORT_ROUTE} node file: {where} is {tuple(values)!r}, and a "
                "coordinate that is not a finite number would be written as a word, which "
                "makes the import mark nothing"
            )
        lines.append(",".join(plain_decimal(value) for value in values))
    return "\n".join(lines) + "\n"


# The command whose enumeration is the simulation's length-unit vocabulary,
# which is where the import's third token is drawn from, is
# `LENGTH_UNIT_COMMAND`, imported from its one home in the script root (AD-10).

#: The one build the file route was run on, and the report that ran it.
WAKE_EDGE_FILE_ROUTE_MEASURED_ON = "26.124"
WAKE_EDGE_FILE_ROUTE_REPORT = "RPT-061"


def _simulation_length_units(script: Script) -> tuple[str, ...]:
    """Return the length-unit tokens the script's database records, OTHER excluded.

    OTHER names no scale, so a node file converted to it would carry
    coordinates in nothing the package can state.
    """
    entry = script.registry.commands.get(LENGTH_UNIT_COMMAND)
    if entry is None:
        return ()
    for arg in entry.args:
        if arg.name == "units":
            return tuple(value for value in (arg.values or ()) if value != "OTHER")
    return ()


def mark_wake_edges(
    script: Script,
    *,
    edge_type: str,
    tolerance: float,
    units: str,
    node_file: str | PathLike[str],
    midpoints: Sequence[Sequence[float]],
) -> str:
    """Mark trailing edges from a file of edge mid-points, not by angle.

    Emits the import route INSTEAD of the angle criterion, which is what
    the route is for: auto detection marks an edge because the surface
    creases there, and a strongly twisted blade has a trailing edge that
    is not a crease. The file marks exactly the edges it names, since
    initialisation does not add the ones detection would find (RPT-065),
    so this replaces rather than runs beside.

    THE FORM IS THE ONE 26.124 READS (RPT-061):
    ``IMPORT_WAKE_EDGES_FROM_FILE <TYPE> <TOLERANCE> <UNITS>`` with the
    node file's path on the next line. The manual prints a two-value line,
    which that build refuses as a syntax error, and the path is read only
    when the line carries a third token. The third token is required and
    had no measured effect; the simulation's length unit is written there.
    The node file's text is parked on the script
    (:attr:`~pyflightstream.script.Script.pending_input_files`) and the
    run writes it before the solver starts, and the number of points is
    recorded (:attr:`~pyflightstream.script.Script.wake_edge_points`) so
    the run can compare it with the count the solver logs as imported.

    Parameters
    ----------
    script : Script
        Script under construction.
    edge_type : str
        Edge type applied to every edge the import matches: the same
        four values SET_TRAILING_EDGE_TYPE takes, so this sets for a
        whole imported file what that command sets for one edge.
    tolerance : float
        Maximum distance between a mesh edge mid-point and an imported
        point for the two to count as the same edge, in the simulation's
        own length units.
    units : str
        The simulation's length unit, a token of SET_SIMULATION_LENGTH_UNITS
        other than OTHER. Written as the third token; the points must
        already be in it, because the solver reads no unit from the file.
    node_file : str or path-like
        Where the node file is written and read, the path the command's
        next line names.
    midpoints : sequence of (x, y, z)
        The mid-points of the mesh edges to mark, in ``units``. See
        :func:`render_wake_edge_node_file`.

    Returns
    -------
    str
        The command emitted, for a run record that has to name the route
        it took.

    Raises
    ------
    CommandNotInVersionError
        If the build does not document the import route, or documents
        only the two-value line (26.122, 26.123), which has not been run
        and which 26.124 refuses. The message names the build and the
        angle criterion this library will NOT substitute unasked: a
        campaign that silently fell back would mark a twisted blade by an
        angle criterion and report nothing about it.
    CommandArgumentError
        If ``units`` is not a length unit with a scale, if the points
        cannot make a node file (see :func:`render_wake_edge_node_file`),
        or if this script already writes different text to ``node_file``.
        Every refusal leaves the script untouched.

    Notes
    -----
    NEITHER THE TYPE NOR THE TOLERANCE HAS A DEFAULT HERE, deliberately.
    The vendor's own defaults live one layer up, on
    :class:`~pyflightstream.workspace.wake_edges.WakeEdgeImport`,
    together with the refusals a grammatically perfect call still needs.

    Two calls on one script import two files, and
    :attr:`~pyflightstream.script.Script.wake_edge_points` is their sum,
    since the solver logs one imported count per import.

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.124")
    >>> helpers.mark_wake_edges(
    ...     script,
    ...     edge_type="STANDARD",
    ...     tolerance=0.0001,
    ...     units="METER",
    ...     node_file="wing.wake_nodes.txt",
    ...     midpoints=[(1.0, -3.75, 0.0), (1.0, -3.25, 0.0)],
    ... )
    'IMPORT_WAKE_EDGES_FROM_FILE'
    >>> print(script.render().strip())
    IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER
    wing.wake_nodes.txt
    >>> script.wake_edge_points
    2
    """
    try:
        grammar = script._view[WAKE_EDGE_IMPORT_ROUTE]
    except CommandNotInVersionError as error:
        raise CommandNotInVersionError(
            f"mark_wake_edges: FlightStream {script.version.canonical} does not carry "
            f"{WAKE_EDGE_IMPORT_ROUTE}, the route this campaign marks its trailing "
            f"edges by, and this library will not fall back to {WAKE_EDGE_ANGLE_ROUTE} "
            "for you. That route marks an edge where the surface creases, which is "
            "the criterion an imported node list exists to replace on a blade whose "
            "trailing edge is not a crease, so substituting it would change the "
            f"physics in silence. Run this case on a build that documents "
            f"{WAKE_EDGE_IMPORT_ROUTE}, or ask for the angle criterion deliberately. "
            f"The database says: {error}"
        ) from error
    if not any(arg.name == "file" for arg in grammar.args):
        raise CommandNotInVersionError(
            f"mark_wake_edges: FlightStream {script.version.canonical} documents "
            f"{WAKE_EDGE_IMPORT_ROUTE} only as the two-value line its manual prints, "
            "with no node file, and that route was measured on "
            f"{WAKE_EDGE_FILE_ROUTE_MEASURED_ON} only ({WAKE_EDGE_FILE_ROUTE_REPORT}), "
            "where the two-value line is a syntax error that stops the script and the "
            "file is read only from the line after a third token. Nothing has been "
            f"run on {script.version.canonical}, so no form is emitted for it. Run the "
            f"case on {WAKE_EDGE_FILE_ROUTE_MEASURED_ON}, or mark the trailing edges by "
            f"detection ({WAKE_EDGE_ANGLE_ROUTE}) deliberately"
        )
    known = _simulation_length_units(script)
    if units not in known:
        raise CommandArgumentError(
            f"mark_wake_edges: units is {units!r}, and the third token is the "
            f"simulation's length unit, one of the {LENGTH_UNIT_COMMAND} tokens with a "
            f"scale: {', '.join(known)}. The solver reads the node file in the "
            "simulation's unit and reads no unit from the file, so the points must "
            "already be in it"
        )
    text = render_wake_edge_node_file(midpoints)
    path = fspath(node_file)
    # A path equal to a parked one but for case is the same file on a
    # case-insensitive file system (Windows), so it is held to the same rule,
    # as actuator_disc holds a profile.
    for parked, already in script._pending_input_files.items():
        if not _same_file(parked, path) or already == text:
            continue
        where = _where_parked(parked, path)
        raise CommandArgumentError(
            f"mark_wake_edges: this script already writes a different node file to "
            f"{where}. One path is one file, so the second would silently replace "
            "the first and both import lines would read whichever text won. Give "
            "this import a node file of its own"
        )

    # Emit, then park, then record: a build or an argument the emitter
    # refuses leaves no file parked and no count recorded.
    script.emit(WAKE_EDGE_IMPORT_ROUTE, edge_type, tolerance, units, path)
    script._pending_input_files[path] = text
    # The count is the file's own first line, so the number recorded is
    # the number written.
    points = int(text.split(maxsplit=1)[0])
    script.wake_edge_points = (script.wake_edge_points or 0) + points
    return WAKE_EDGE_IMPORT_ROUTE
