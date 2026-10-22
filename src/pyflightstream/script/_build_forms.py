"""The forms a command takes on the builds whose manual changed it (FR-423).

Pipeline role: emission helpers below the workflows and the probe catalog.
Private form checks validate argument slots, creation references and parked
inputs before emission mutates a script.
Each function here writes the one form the build the script targets
documents, where two builds document two forms of the same request, so a
caller states the request once and the script states the form.

THE EVERY-BOUNDARY DETECTIONS. The 26.125 edition of the manual (FSM-26.125)
stops printing ``AUTO_DETECT_TRAILING_EDGES``, ``AUTO_DETECT_BASE_REGIONS`` and
``AUTO_DETECT_WAKE_TERMINATION_NODES`` and documents, in their place, the -1
(every boundary) form of the three ``DETECT_*_BY_SURFACE`` commands
(FSM-26.125 pp.327, 329, 331). A build that carries the automatic command
emits it. On 26.125 trailing-edge detection uses a counted inventory:
the solver has been measured to mark zero edges with the -1 form (PFS-2104.051).

THE WAKE-EDGE IMPORT TOKEN. 26.124 was measured to require a third token on
``IMPORT_WAKE_EDGES_FROM_FILE`` and to read the node list from the next line
only after it (RPT-061); its manual printed two values. FSM-26.125 p.329 names
that token EDGE_TYPE, 1 for a file of edge mid-points and 2 for edge corner
nodes. The package's node file lists mid-points, so a build whose grammar
declares the enum gets 1, and a build whose grammar is the measured 26.124
form keeps the simulation's length unit it was measured with.

THE CCS CURVE ASSIGNMENT. FSM-26.125 asks for
``ASSIGN_SELECTED_CURVES_TO_CCS_<COMPONENT>`` before a CCS component gets a
control surface, a refinement zone or a trailing edge (pp.307, 311, 314).
No earlier edition prints it, so it is emitted only where the build
carries it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import PureWindowsPath
from typing import TYPE_CHECKING, Any, Literal

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.commands import ArgSpec, ArgType, CommandEntry, CommandNotInVersionError, Layout
from pyflightstream.script import CommandArgumentError, Script, ScriptReferenceError
from pyflightstream.script._arg_checks import _bind_line_tokens, _check_scalar, _is_all
from pyflightstream.script._ledger_tables import _COUNT_REFERENCE_ARGS, _reference_kind
from pyflightstream.script._settings import _reject_empty_selection, _toggle

if TYPE_CHECKING:
    from pyflightstream.commands import VersionView
    from pyflightstream.script import Script, UnsteadyActionUse

__all__ = [
    "assign_selected_ccs_curves",
    "detect_every_boundary",
    "every_boundary_detection",
    "solver_time_averaging",
    "takes_every_boundary",
    "wake_edge_import_token",
]

#: Every-boundary detection, by what it detects: the automatic command of the
#: builds that carry it, and the by-surface command whose -1 form FSM-26.125
#: documents in its place. The wake-termination nodes keep the automatic command
#: on 26.125 too, which accepts it (L4 PFS-2131.001).
_DETECTIONS: dict[str, tuple[str, str]] = {
    "trailing_edges": ("AUTO_DETECT_TRAILING_EDGES", "DETECT_TRAILING_EDGES_BY_SURFACE"),
    "base_regions": ("AUTO_DETECT_BASE_REGIONS", "DETECT_BASE_REGIONS_BY_SURFACE"),
    "wake_termination_nodes": (
        "AUTO_DETECT_WAKE_TERMINATION_NODES",
        "DETECT_WAKE_TERMINATION_NODES_BY_SURFACE",
    ),
}

#: The index the by-surface detections read as every boundary (FSM-26.125
#: pp.327, 329, 331).
EVERY_BOUNDARY = -1

#: The EDGE_TYPE token of a node file listing edge mid-points (FSM-26.125 p.329),
#: which is the file the package writes.
MIDPOINT_EDGE_TYPE = "1"

#: The CCS curve assignment, by the component kind the CCS builders name.
_CCS_ASSIGNMENT: dict[str, str] = {
    "wing": "ASSIGN_SELECTED_CURVES_TO_CCS_WING",
    "fuselage": "ASSIGN_SELECTED_CURVES_TO_CCS_FUSELAGE",
    "revolution": "ASSIGN_SELECTED_CURVES_TO_CCS_REVOLVE_BODY",
}


def every_boundary_detection(script: Script, kind: str) -> tuple[str, tuple[int, ...]]:
    """Return the command and arguments that detect ``kind`` on every boundary.

    Parameters
    ----------
    script : Script
        The script whose build decides the form.
    kind : str
        ``"trailing_edges"``, ``"base_regions"`` or ``"wake_termination_nodes"``.

    Returns
    -------
    tuple of (str, tuple of int)
        The automatic command with no argument where the build carries it,
        else the by-surface command with the every-boundary index. For
        ``"trailing_edges"`` on 26.125 that index is the -1 form the manual
        documents, which the solver answers with zero edges marked; use
        :func:`detect_every_boundary`, which lists the declared boundaries
        instead, to emit that detection.

    Raises
    ------
    KeyError
        If ``kind`` is not one of the three detections.
    """
    automatic, by_surface = _DETECTIONS[kind]
    if automatic in script._view or not takes_every_boundary(script._view, by_surface):
        # A build with neither form is refused by the emitter, naming the
        # automatic command, as it always was.
        return automatic, ()
    return by_surface, (EVERY_BOUNDARY,)


def takes_every_boundary(view: VersionView, command: str) -> bool:
    """Say whether a build's grammar of a by-surface detection takes the -1 form.

    Parameters
    ----------
    view : VersionView
        The command database's view of one build.
    command : str
        A ``DETECT_*_BY_SURFACE`` command.

    Returns
    -------
    bool
        True where the build carries the command and its grammar takes the
        every-boundary index or omits the index list (26.125); False on the
        builds whose by-surface detection names its surfaces only.
    """
    if command not in view:
        return False
    args = view[command].args
    return any(arg.all_sentinel == EVERY_BOUNDARY or not arg.required for arg in args)


def detect_every_boundary(script: Script, kind: str) -> str:
    """Emit the every-boundary detection of ``kind`` in the build's form.

    Parameters
    ----------
    script : Script
        The script being built.
    kind : str
        ``"trailing_edges"``, ``"base_regions"`` or ``"wake_termination_nodes"``.

    Returns
    -------
    str
        The command emitted.

    Examples
    --------
    >>> from pyflightstream.script import Script
    >>> old, new = Script(version="26.124"), Script(version="26.125")
    >>> new.declare_existing(boundaries=2)
    >>> detect_every_boundary(old, "trailing_edges"), detect_every_boundary(new, "trailing_edges")
    ('AUTO_DETECT_TRAILING_EDGES', 'DETECT_TRAILING_EDGES_BY_SURFACE')
    >>> print(new.render().strip())
    DETECT_TRAILING_EDGES_BY_SURFACE
    SURFACES 2
    1,2
    """
    command, all_arguments = every_boundary_detection(script, kind)
    arguments: tuple[object, ...] = all_arguments
    if kind == "trailing_edges" and script.version.canonical == "26.125":
        from pyflightstream.script import CommandArgumentError

        count = script.num_boundaries
        if not count:
            raise CommandArgumentError(
                "automatic trailing-edge detection on 26.125 needs a declared boundary "
                "inventory; the solver has marked zero edges with SURFACES -1. "
                "Declare the boundaries or select explicit surface indices"
            )
        arguments = (count, list(range(1, count + 1)))
    script.emit(command, *arguments)
    return command


def _wake_argument_alias(entry: CommandEntry, key: str) -> str:
    """Preserve the former 26.124 keyword without broadening the later enum."""
    if (
        entry.name == "IMPORT_WAKE_EDGES_FROM_FILE"
        and key == "units"
        and any(spec.name == "edge_type" and spec.type is ArgType.STR for spec in entry.args)
    ):
        return "edge_type"
    return key


def _refuse_interactive_profile(script: Script, entry: CommandEntry) -> None:
    """Keep a measured modal operation out of a validated batch script."""
    if entry.name == "EXPORT_BL_VELOCITY_PROFILE" and script.version.canonical == "26.122":
        raise CommandArgumentError(
            "EXPORT_BL_VELOCITY_PROFILE on 26.122 waits for a modal Done button "
            "even under -hidden (RPT-027), so a validated unattended script refuses it. "
            "The database remains documented: this is an interface restriction, "
            "not a new broken probe verdict. Use raw() only for an explicitly "
            "supervised interactive run."
        )


def _warn_unmeasured_ccs_grammar(script: Script, entry: CommandEntry) -> None:
    """Flag a suspect older grammar without attributing a newer run to it."""
    if entry.name not in {"NEW_CCS_REVOLVE_RELAXED_TE", "EXPORT_REVOLVE_CCS_FILE"}:
        return
    if script.version.canonical not in {"26.120", "26.121", "26.122", "26.123"}:
        return
    record = entry.status_in(script.version)
    if record is not None and str(record.status) == "documented":
        warn(
            f"{entry.name}: this grammar is unmeasured on {script.version.canonical}; "
            "the same form aborted on 26.124 (CMP-26124_2026-10-02_qa-promote) and "
            "26.125 requires a different form (CMP-26125_2026-10-05_probe-campaign). "
            "The older build remains documented, not measured broken. Probe this "
            "build with a timeout before using the command unattended.",
            PyflightstreamWarning,
        )


def wake_edge_import_token(script: Script, units: str) -> str:
    """Return the third token of the wake-edge import on the script's build.

    Parameters
    ----------
    script : Script
        The script whose build decides the token.
    units : str
        The simulation's length unit, the token 26.124 was measured with.

    Returns
    -------
    str
        :data:`MIDPOINT_EDGE_TYPE` where the build's grammar declares the
        EDGE_TYPE enum (26.125), else the measured legacy token ``units``.
    """
    grammar = script._view["IMPORT_WAKE_EDGES_FROM_FILE"]
    if any(arg.name == "edge_type" and arg.type is ArgType.ENUM for arg in grammar.args):
        return MIDPOINT_EDGE_TYPE
    return units


def solver_time_averaging(script: Script, window: tuple[int, int]) -> None:
    """Emit ``ENABLE_SOLVER_TIME_AVERAGING`` over a window of time iterations.

    The command it replaces, ``SOLVER_TIME_AVERAGING``, hung the 26.124 solver
    (C01). This one is a different command of a different build and no run
    has measured it, so on a build where it is documented and not verified
    the line is written and a warning says so, naming the remedy.

    Parameters
    ----------
    script : Script
        The script being built.
    window : tuple of (int, int)
        The first and the last time iteration of the average, both counted
        from 1 in the solver's own time steps (FSM-26.125 p.360).

    Raises
    ------
    CommandArgumentError
        If the window is not two positive integers in order.
    """
    first, last = window
    if not (0 < first <= last):
        raise CommandArgumentError(
            f"solver_time_averaging = [{first}, {last}] is not a window: state the first "
            "and the last time iteration of the average, both positive, the first not "
            "after the last"
        )
    command = "ENABLE_SOLVER_TIME_AVERAGING"
    script.emit(command, first, last)
    record = script.registry.commands[command].status_in(script.version)
    if record is not None and str(record.status) != "verified":
        warn(
            f"solver_time_averaging: {command} is documented on FlightStream "
            f"{script.version.canonical} and no run has verified it, and the command it "
            "replaces hung the 26.124 solver. Run the 26.125 probe campaign before relying "
            "on it, or average with the pproc [time_averaging] table instead",
            PyflightstreamWarning,
            stacklevel=2,
        )


def assign_selected_ccs_curves(script: Script, kind: str) -> str | None:
    """Emit the CCS curve assignment of ``kind`` where the build carries it.

    Parameters
    ----------
    script : Script
        The script being built, after its curves were selected.
    kind : str
        ``"wing"``, ``"fuselage"`` or ``"revolution"``.

    Returns
    -------
    str or None
        The command emitted, or None on a build that does not carry it.
    """
    command = _CCS_ASSIGNMENT[kind]
    if command not in script._view:
        return None
    script.emit(command)
    return command


def _checked_helper_value(script: Script, command: str, argument: str, value: object) -> object:
    """Validate a helper argument against its target build before creating an entity."""
    entry = script.entry(command)
    spec = next(spec for spec in entry.args if spec.name == argument)
    if spec.cites is not None:
        context = f"{command}: argument {argument!r}"
        value = script.entities.resolve(spec.cites, value, context=context)
        script.entities.check_index(spec.cites, value, context=context)
    return _check_scalar(entry, spec, value)


def _check_actuator_creation(
    script: Script,
    *,
    frame: int | str,
    axis: str,
    thrust: float | None,
    thrust_type: str,
    profile_force_unit: str,
    label: str | None,
) -> None:
    """Validate the selected actuator form before its creation line."""
    for command, argument, value in (
        ("SET_ACTUATOR_AXIS", "frame", frame),
        ("SET_ACTUATOR_AXIS", "axis", axis),
    ):
        _checked_helper_value(script, command, argument, value)
    if thrust is not None:
        _checked_helper_value(script, "SET_PROP_ACTUATOR_THRUST", "thrust_type", thrust_type)
    else:
        _checked_helper_value(script, "SET_PROP_ACTUATOR_PROFILE", "units_type", profile_force_unit)
    if label is not None:
        script.entities.assert_label_free("actuators", label)


def _check_motion_creation(
    script: Script,
    *,
    frame: int | str,
    axis: str,
    euclidean: bool,
    boundaries: Sequence[int | str] | Literal["all"],
    moving_frames: Sequence[int | str] | Literal["all"] | None,
    label: str | None,
) -> None:
    """Validate all rotary entity citations before creating the motion."""
    _checked_helper_value(script, "SET_MOTION_COORDINATE_SYSTEM", "coordinate_system_id", frame)
    if not euclidean:
        _checked_helper_value(script, "SET_MOTION_ROTOR_AXIS", "axis", axis)
    for kind, selection in (("boundaries", boundaries), ("frames", moving_frames)):
        if selection is not None and not _is_all(selection):
            for value in selection:
                resolved = script.entities.resolve(kind, value, context="rotary_motion")
                script.entities.check_index(kind, resolved, context="rotary_motion")
    if label is not None:
        script.entities.assert_label_free("motions", label)


def _check_blade_labels(script: Script, labels: Sequence[str] | None) -> None:
    """Reserve no frame until every proposed label is unique and available."""
    if labels is not None:
        if len(set(labels)) != len(labels):
            raise CommandArgumentError(
                "blade_frames: labels must be unique; give each blade its own label"
            )
        for label in labels:
            script.entities.assert_label_free("frames", label)


#: The arguments each SET_FREESTREAM form takes.
_FREESTREAM_MODE_ARGUMENTS: dict[str, set[str]] = {
    "CONSTANT": {"type"},
    "ROTATION": {"type", "frame", "axis", "angular_velocity"},
    "CUSTOM": {"type", "filetype", "filename"},
}


def _positional_form(
    entry: CommandEntry, specs: tuple[ArgSpec, ...], checked: Mapping[str, object]
) -> list[ArgSpec]:
    """Select the manual-defined alternative argument form."""
    positional = [spec for spec in specs if not spec.own_line]
    # These grammars select alternative positional forms by a leading mode.
    if entry.name == "SET_FREESTREAM":
        selected = _FREESTREAM_MODE_ARGUMENTS.get(str(checked.get("type")), set())
        positional = [spec for spec in positional if spec.name in selected]
    elif entry.name.startswith("SWEEPER_SET_") and "filename" in checked:
        positional = [spec for spec in positional if spec.name != "values"]
    return positional


def _check_bound_form(
    entry: CommandEntry, specs: tuple[ArgSpec, ...], checked: Mapping[str, object]
) -> None:
    """Refuse a missing bare folder or a shifted positional argument."""
    if entry.name == "EXECUTE_SOLVER_SWEEPER":
        exporting = checked["export_surface_data_per_step"] != "DISABLE"
        if exporting != ("export_folder" in checked):
            raise CommandArgumentError(
                f"{entry.name}: export_folder is required exactly when "
                "export_surface_data_per_step is enabled; provide the folder for "
                f"TXT, CSV, DAT or VTK, and omit it for DISABLE ({entry.citation})"
            )
    if entry.name == "SET_FREESTREAM":
        mode = str(checked.get("type"))
        allowed = _FREESTREAM_MODE_ARGUMENTS.get(mode, {"type"})
        stray = [name for name in checked if name not in allowed]
        if stray:
            raise CommandArgumentError(
                f"{entry.name}: the {mode} form does not take {', '.join(stray)}; it takes "
                f"{', '.join(sorted(allowed))}, and the others would be written into the "
                f"line as if they belonged to it ({entry.citation})"
            )
    if entry.layout in (Layout.INLINE, Layout.MIXED_INLINE):
        positional = _positional_form(entry, specs, checked)
        missing = None
        for spec in positional:
            if spec.name not in checked:
                missing = missing or spec.name
            elif missing is not None:
                raise CommandArgumentError(
                    f"{entry.name}: argument {spec.name!r} follows omitted inline "
                    f"argument {missing!r}; supply preceding positional arguments "
                    f"to preserve their slots ({entry.citation})"
                )


def _check_inline_token(entry: CommandEntry, spec: ArgSpec, value: object) -> None:
    """Keep scalar string arguments in their documented token slot."""
    # PRINT consumes the remainder as a message (FSM-26.120 p.281).
    if (
        spec.type is ArgType.STR
        and entry.name != "PRINT"
        and (not str(value) or any(character.isspace() for character in str(value)))
    ):
        raise CommandArgumentError(
            f"{entry.name}: argument {spec.name!r} is {value!r}; "
            "an inline string must be one nonempty token without whitespace. "
            f"Use a single-token name ({entry.citation})"
        )


#: Names Windows reads as devices, whatever the extension: never a staged file.
_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


def _park_input_file(script: Script, path: str, payload: str | bytes) -> None:
    """Check the relative input destination and both parked-file registers."""
    destination = PureWindowsPath(path)
    if (
        not path
        or destination.drive
        or destination.root
        or ".." in destination.parts
        or not destination.name
        or path.endswith(("/", "\\"))
        or destination.name.split(".")[0].upper() in _DEVICE_NAMES
    ):
        raise CommandArgumentError(
            f"input file {path!r} must be a relative file path inside the point folder; "
            "use a filename (not a folder, and not a device name such as NUL) or a "
            "subfolder without parent traversal"
        )
    parked = script._parked_file(path)
    if parked is not None:
        kind, held = parked
        if kind == "input file" and script._pending_input_files[held] == payload:
            return
        raise CommandArgumentError(f"input file {path!r} collides with {kind} {held!r}")
    script._pending_input_files[path] = payload


def _carry_unsteady_actions(
    script: Script, uses: Sequence[UnsteadyActionUse], scripts: Mapping[str, str]
) -> None:
    """Preflight the complete carried action set before publishing either register."""
    from pyflightstream._digest import one_file_key

    actions = dict(script._unsteady_actions)
    for use in uses:
        if use.name in actions and actions[use.name] != use:
            raise CommandArgumentError(f"carried unsteady action {use.name!r} conflicts")
        actions[use.name] = use
    paths = {
        one_file_key(path): (path, text) for path, text in script._pending_action_scripts.items()
    }
    inputs = {one_file_key(path) for path in script.pending_input_files}
    for path, text in scripts.items():
        key = one_file_key(path)
        if key in inputs or (key in paths and paths[key][1] != text):
            raise CommandArgumentError(
                f"carried action script {path!r} conflicts with a parked file"
            )
        paths[key] = (path, text)
    script._unsteady_actions = actions
    script._pending_action_scripts = dict(paths.values())


def _refuse_export_collision(script: Script, path: str, *, asker: str) -> None:
    """Refuse an output path already held by the script's export register.

    Helpers and direct command emission share this check before committing
    state. File identity follows the same normalization as parked input files.
    """
    from pyflightstream._digest import one_file_key

    key = one_file_key(path)
    for held, site in script._exported_paths.items():
        if one_file_key(held) == key:
            same = "" if held == path else f" (as {held!r}, the same file)"
            raise CommandArgumentError(
                f"this script already exports to {path!r}{same}, from {site}. The "
                "solver writes one file per path, so the second export would "
                "silently replace the first and the script would carry two "
                f"exports of one file. Give {asker} a path of its own, for "
                "example one carrying the point or the survey name."
            )


def _parked_file(script: Script, path: str) -> tuple[str, str] | None:
    """Find the same destination across action and input file registers."""
    from pyflightstream._digest import one_file_key

    key = one_file_key(path)
    for register, parked in (
        ("action script", script._pending_action_scripts),
        ("input file", script._pending_input_files),
    ):
        for held in parked:
            if one_file_key(held) == key:
                return register, held
    return None


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


def _emit_compact_line(script: Script, line: str) -> None:
    """Bind compact input and preserve the command's declared physical layout."""
    tokens = line.split()
    if not tokens:
        raise CommandArgumentError("an empty line names no command")
    name, arguments = tokens[0], tokens[1:]
    spec = script.entry(name)
    if not (
        spec.layout in (Layout.BARE, Layout.INLINE, Layout.MIXED_INLINE)
        or (spec.layout is Layout.PARAM_LINES and all(arg.own_line for arg in spec.args))
    ):
        raise CommandArgumentError(
            f"{name} is a {spec.layout.value.replace('_', ' ')} and not a one-line "
            "command; a raw entry is one line as the solver reads it, and a block "
            "has no place in it. State what the block sets through the preset's own "
            "keys or the row's, or drop the entry"
        )
    bound: dict[str, Any] = _bind_line_tokens(name, spec.args, arguments)
    previous = script._emitting_line
    script._emitting_line = True
    try:
        script.emit(name, **bound)
    finally:
        script._emitting_line = previous


def _check_references(script: Script, entry: CommandEntry, bound: dict[str, object]) -> None:
    frames = bound.get("frame_indices")
    if (
        entry.name == "ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS"
        and script.version.canonical in {"26.124", "26.125"}
        and isinstance(frames, Sequence)
        and 1 in frames
    ):
        raise CommandArgumentError(
            "ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS: index 1 is the reference frame "
            "and cannot be assigned on 26.124 or 26.125. Select local frame indices "
            "greater than 1; a count of one is valid "
            "(reports/PFS-2005.07_frame-index-evidence_2026-10-16.md)."
        )
    if entry.name == "DELETE_COORDINATE_SYSTEM" and bound.get("frame") == 1:
        raise CommandArgumentError(
            "DELETE_COORDINATE_SYSTEM: frame 1 is the reference frame and cannot "
            "be deleted. Select a local frame with an index greater than 1 "
            f"({entry.citation})"
        )
    for spec in entry.args:
        if spec.name not in bound:
            continue
        context = f"{entry.name}: argument {spec.name!r}"
        value = bound[spec.name]
        kind = _reference_kind(spec)
        if kind is not None and not spec.is_list:
            script.entities.check_index(
                kind,
                value,
                context=context,
                citation=entry.citation,
                all_sentinel=spec.all_sentinel,
            )
        elif kind is not None and isinstance(value, Sequence) and not isinstance(value, str):
            # Each item uses the argument's declared sentinel, just like a scalar.
            # Frames and motions have no documented -1 form; surface selections
            # may instead declare zero.
            for item in value:
                script.entities.check_index(
                    kind,
                    item,
                    context=context,
                    citation=entry.citation,
                    all_sentinel=spec.all_sentinel,
                )
        kind = _COUNT_REFERENCE_ARGS.get(spec.name)
        if kind is not None:
            script.entities.check_boundary_count(value, context=context, citation=entry.citation)


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


def _surface_selection(
    script: Script, component: str | None, boundaries: Sequence[int | str] | str
) -> list[int | str]:
    """Return the boundary indices ``rotate_surfaces`` rotates (empty for all of them)."""
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
    elif _is_all(boundaries):
        selection = []
    else:
        selection = list(boundaries)
        _reject_empty_selection("rotate_surfaces", "boundaries", list(selection))
    return selection


def _refuse_options_without_equivalent(
    script: Script, command: str, split_on: bool, adaptive_on: bool
) -> None:
    """Refuse the SURFACE_ROTATE-only options on a build that documents ROTATE_SURFACE."""
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


def _rotation_emission(
    script: Script,
    command: str,
    *,
    frame: int | str,
    axis: str,
    angle_deg: float,
    selection: list[int | str],
    whole: bool,
    toggles: tuple[bool, bool, bool],
    after_initialization: bool,
) -> None:
    """Emit the rotation command with the arguments its layout takes."""
    detach_on, split_on, adaptive_on = toggles
    count = -1 if whole else len(selection)
    arguments: dict[str, Any] = {
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
