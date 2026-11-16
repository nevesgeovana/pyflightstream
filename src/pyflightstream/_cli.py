"""Shared CLI outcome reporting, below the package's domain layers.

Decorating a console ``main`` preserves its return value and exceptions.
Only the outermost entry point reports, including argparse's early exits.
Machine-readable stdout is never used for human outcome reporting.

Every invocation ends with the package's signature on stderr: a box
drawn from :mod:`pyflightstream._signature` for an outcome, or one short line
for ``--help`` and ``--version`` so their output stays compact. For the length
of the call, a warning of the package's own categories prints as
``[warning] <message>`` with no file, line or echoed source, wrapped at 90
columns under its text and followed by a blank line; ``--verbose``
keeps Python's full format. A Python caller outside a console script is never
touched.

The signature always appears (FR-315): no flag, stream kind or error path hides it.
"""

from __future__ import annotations

import random
import sys
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from io import StringIO
from typing import Any, TextIO

import pyflightstream._progress as _progress
import pyflightstream._signature as _signature
from pyflightstream._console import CONSOLE_WARNINGS, console_warnings, warning_text
from pyflightstream._errors import PyflightstreamDeprecationWarning, PyflightstreamWarning
from pyflightstream._progress import command_terminal

_ACTIVE: ContextVar[bool] = ContextVar("pyflightstream_cli_active", default=False)
_POST_WARNINGS: ContextVar[bool | None] = ContextVar(
    "pyflightstream_cli_post_warnings", default=None
)
#: Python's own warning format, held for the length of one invocation so a
#: console level chosen after the parse can put it back (FR-997).
_STANDARD_FORMAT: ContextVar[Callable[..., str] | None] = ContextVar(
    "pyflightstream_cli_standard_format", default=None
)
#: What restores each value :func:`for_this_invocation` set, in the order set.
_SCOPED: ContextVar[list[Callable[[], None]] | None] = ContextVar(
    "pyflightstream_cli_scoped", default=None
)
#: Whether this invocation ran a post (the ``post`` subcommand or the post a
#: ``collect`` runs); a success that did is signed with the koala.
_POSTED: ContextVar[list[bool] | None] = ContextVar("pyflightstream_cli_posted", default=None)
#: The cost-file stem selected by ``--cost-file NAME`` for one invocation, or None.
_SELECTED_COST_FILE: ContextVar[str | None] = ContextVar("pyflightstream_cost_file", default=None)
#: The HPC profile stem selected by ``--hpc NAME`` for one invocation, or None.
_SELECTED_HPC: ContextVar[str | None] = ContextVar("pyflightstream_selected_hpc", default=None)
_MESSAGES = {
    "help": ("Help delivered; the map is yours.", "Help ready; pick your next turn."),
    "version": ("Version reported; coordinates checked.", "Version ready; now you know the build."),
}
#: The chooser of drawings and phrases; a test replaces it with a seeded one.
_RNG = random.Random()


def post_warning_policy() -> bool | None:
    """Return CLI warning preference, or None for ordinary Python callers.

    Returns
    -------
    bool or None
        The active command warning preference; None outside that context.
    """
    return _POST_WARNINGS.get()


def note_post_ran() -> None:
    """Record that this invocation ran a post, so its success is signed as one."""
    posted = _POSTED.get()
    if posted is not None:
        posted[0] = True


def set_post_warning_policy(enabled: bool) -> None:
    """Set whether this invocation prints grouped post-processing warnings (FR-996).

    Read from the raw command line before the parse; a workspace settings file
    or ``--no-pproc-warnings`` decides after it. Outside a console command it
    does nothing.

    Parameters
    ----------
    enabled : bool
        The resolved choice.
    """
    if _ACTIVE.get():
        _POST_WARNINGS.set(enabled)


def set_console_level(level: str) -> None:
    """Set the console level of this invocation, chosen after the parse (FR-997).

    ``verbose`` prints warnings in Python's full format, the other two levels in
    the package's short one; :func:`pyflightstream._progress.set_console_level`
    sets what the console shows. Outside a console command it does nothing.

    Parameters
    ----------
    level : str
        One of :data:`pyflightstream._console.CONSOLE_LEVELS`.
    """
    standard = _STANDARD_FORMAT.get()
    if standard is None:
        return
    warnings.formatwarning = standard if level == "verbose" else _short_warnings(standard)
    _progress.set_console_level(level)


def for_this_invocation[T](variable: ContextVar[T], value: T) -> None:
    """Set ``variable`` for the rest of this console command, restored when it ends.

    Outside a console command the variable is set plainly, as a Python caller
    would set it.

    Parameters
    ----------
    variable : contextvars.ContextVar
        The variable, owned by the layer that reads it.
    value : object
        Its value for this invocation.
    """
    token = variable.set(value)
    scoped = _SCOPED.get()
    if scoped is not None:
        scoped.append(lambda: variable.reset(token))


def _close_invocation(scoped: list[Callable[[], None]], show: Callable[..., None]) -> None:
    """Restore what this invocation set: its scoped variables, then the warning printer."""
    for restore in reversed(scoped):
        restore()
    warnings.showwarning = show


def _signature_text(outcome: str) -> str:
    """Return what the invocation prints on stderr for ``outcome``."""
    if outcome in _MESSAGES:
        return f"{_RNG.choice(_MESSAGES[outcome])} {_signature.SEES_YOU}"
    name, phrase = _signature.pick(outcome, _RNG)
    return f"\n{_signature.box(name, phrase)}\n"


def _write_replaced(text: str, stream: TextIO) -> None:
    """Write ``text`` with the stream's own encoding, a replacement mark for what it lacks."""
    encoding = getattr(stream, "encoding", None) or "ascii"
    data = text.encode(encoding, errors="replace")
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        stream.flush()
        buffer.write(data)
        buffer.flush()
    else:
        stream.write(data.decode(encoding, errors="replace"))


def _sign(outcome: str) -> None:
    """Print the signature of ``outcome`` on stderr; it always appears (FR-315).

    It is never optional and no flag, stream kind or error path silences it: a
    stream that cannot encode the drawing gets the same text with replacement
    marks, and a drawing that cannot be built falls back to the bare line. Only
    a closed or broken stream prints nothing, and it never replaces the
    command's own result or exit code.
    """
    try:
        text = _signature_text(outcome)
    except Exception:
        text = _signature.SEES_YOU
    stream = sys.stderr
    if stream is None:
        # print(file=None) would fall back to stdout and break its byte contract.
        return
    try:
        try:
            print(text, file=stream)
        except UnicodeEncodeError:
            _write_replaced(f"{text}\n", stream)
    except (OSError, ValueError, AttributeError):
        # A closed diagnostic stream must not replace the real result.
        pass


def _short_warnings(standard: Callable[..., str]) -> Callable[..., str]:
    """Return a ``warnings.formatwarning`` that prints the package's own warnings short."""

    def formatwarning(
        message: Warning | str,
        category: type[Warning],
        filename: str,
        lineno: int,
        line: str | None = None,
    ) -> str:
        if issubclass(category, PyflightstreamWarning):
            return warning_text(message)
        return standard(message, category, filename, lineno, line)

    return formatwarning


def _visible_warnings(show: Callable[..., None]) -> Callable[..., None]:
    """Filter only the warning's console rendering, after its recording and error policy."""

    def shown(*args: Any, **kwargs: Any) -> None:
        # The signature of warnings.showwarning: message, category, filename, lineno, file, line.
        call = dict(
            zip(("message", "category", "filename", "lineno", "file", "line"), args, strict=False)
        )
        call.update(kwargs)
        file = call.get("file")
        elsewhere = file is not None and file is not sys.stderr
        elsewhere = elsewhere and file is not sys.stdout
        if console_warnings() or elsewhere:
            show(*args, **kwargs)
        else:
            with StringIO() as hidden:
                show(**{**call, "file": hidden})
                _progress.log_console_warning(hidden.getvalue())

    return shown


@contextmanager
def _deprecations_shown() -> Iterator[None]:
    """Show a deprecation of the package once during one command.

    The package's input deprecations are visible to TOML and command-line
    callers by default. A warning option or PYTHONWARNINGS the person chose
    is theirs and is left untouched.

    Yields
    ------
    None
        The filters stay in force until the block ends.

    Examples
    --------
    >>> with _deprecations_shown():
    ...     pass
    """
    with warnings.catch_warnings():
        if not sys.warnoptions:
            warnings.filterwarnings("default", category=PyflightstreamDeprecationWarning)
        yield


#: The records, storage and query verbs ``pyfs-workspace`` runs through the ``pyfs-matrix``
#: pipeline: they act on what the workspace already holds, its records, its storage and the
#: queries over them, whichever matrix wrote it.
WORKSPACE_VERBS = (
    "space-in-use",
    "free-space",
    "delete-sims",
    "sync",
    "restore",
    "rebuild",
    "mark-failed",
    "mark-converged",
    "search-log-batch",
    "show",
    "log",
    "trace",
    "history",
    "diff",
)

#: The storage verbs a leading flag also names, ``--free-space m001`` (the flag form).
_FLAG_FORM = ("space-in-use", "free-space", "delete-sims", "sync")

#: The parser builder and the entry point of :data:`WORKSPACE_VERBS`, as ``module:function``,
#: registered by the layer that defines them and imported when a verb is run or listed.
_DELEGATED: list[tuple[str, str]] = []


def register_delegated_commands(build: str, entry: str) -> None:
    """Register the runner of :data:`WORKSPACE_VERBS`, which a higher layer defines.

    Named, not imported: the layer that registers them imports this module, and its entry
    point imports that layer's package, so holding the functions would close a cycle.

    Parameters
    ----------
    build : str
        ``module:function`` returning the parser that holds the verbs.
    entry : str
        ``module:function`` running a command line naming one of them; returns its exit code.
    """
    if not _DELEGATED:
        _DELEGATED.append((build, entry))
    elif _DELEGATED[0] != (build, entry):
        first_build, first_entry = _DELEGATED[0]
        raise RuntimeError(
            f"delegated commands are already registered as ({first_build!r}, {first_entry!r}); "
            f"a second registration ({build!r}, {entry!r}) differs"
        )


def _resolved(target: str) -> Callable[..., Any]:
    import importlib

    module, _, name = target.partition(":")
    found: Callable[..., Any] = getattr(importlib.import_module(module), name)
    return found


def add_delegated(subparsers: Any) -> None:
    """List :data:`WORKSPACE_VERBS` under a program, each with the options its parser gives it.

    Parameters
    ----------
    subparsers : argparse subparsers action
        The program's subcommand table.
    """
    import argparse

    for build, _ in _DELEGATED:
        root = _resolved(build)()
        (verbs,) = [a for a in root._actions if isinstance(a, argparse._SubParsersAction)]
        helps = {choice.dest: choice.help for choice in verbs._choices_actions}
        for name, source in verbs.choices.items():
            command = subparsers.add_parser(
                name,
                parents=[source],
                add_help=False,
                help=helps.get(name),
                description=source.description,
            )
            command.set_defaults(delegated=True)


def delegated_entry(argv: list[str] | None) -> Callable[[list[str] | None], int] | None:
    """Return the entry point that runs ``argv`` whole, when it names a delegated verb.

    Parameters
    ----------
    argv : list of str or None
        The command line without the program name; None reads ``sys.argv``.

    Returns
    -------
    callable or None
        The registered entry point, or None for any other command.
    """
    tokens = list(sys.argv[1:] if argv is None else argv)
    word = next((token for token in tokens if not token.startswith("-")), None)
    flags = {f"--{name}" for name in _FLAG_FORM}
    flag_form = bool(tokens) and tokens[0].startswith("-")
    flag_form = flag_form and any(token.split("=", 1)[0] in flags for token in tokens)
    if _DELEGATED and (word in WORKSPACE_VERBS or flag_form):
        return _resolved(_DELEGATED[0][1])
    return None


def refused_command(program: str, argv: list[str] | None) -> bool:
    """Refuse a removed command of ``program`` by name, before parsing; True when refused.

    The command words are those past the global flags, so ``--warning-refusals refine``
    is found as well as ``refine``, and ``--help`` after them changes nothing. A command
    of two words (a group and its verb) is looked up before its first word alone, each
    as ``REMOVED_FORMS["<program>.<word>[.<word>]"]``; the message names the new command
    and nothing is run.

    Parameters
    ----------
    program : str
        The program, such as ``pyfs-workspace``.
    argv : list of str or None
        The command line without the program name; None reads ``sys.argv``.

    Returns
    -------
    bool
        True when the command line is a removed form and its refusal was printed.
    """
    from pyflightstream._retired_names import REMOVED_FORMS

    words = [w for w in (sys.argv[1:] if argv is None else argv) if not w.startswith("-")]
    for depth in (2, 1):
        entry = REMOVED_FORMS.get(".".join([program, *words[:depth]]))
        if len(words) >= depth and entry is not None:
            print(f"{entry.message()} Nothing was run.", file=sys.stderr)
            return True
    return False


def cli_entrypoint[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    """Report the actual CLI outcome once, without changing CLI semantics.

    Parameters
    ----------
    function : Callable[P, R]
        Console entry point whose return value and exceptions are preserved.

    Returns
    -------
    Callable[P, R]
        Wrapped entry point with scoped console reporting.

    Examples
    --------
    >>> def main(argv=None):
    ...     return 0
    >>> callable(cli_entrypoint(main))
    True
    """

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        if _ACTIVE.get():
            return function(*args, **kwargs)
        token = _ACTIVE.set(True)
        supplied = args[0] if args else kwargs.get("argv")
        argv = supplied if isinstance(supplied, (list, tuple)) else sys.argv[1:]
        warning_token = _POST_WARNINGS.set("--pproc-warnings" in argv)
        posted = [False]
        posted_token = _POSTED.set(posted)
        # THE FORMAT IS SCOPED TO THIS CALL and restored in `finally`, so a
        # Python caller's warnings, before and after, are Python's own (L1).
        verbose = "--verbose" in argv
        standard = warnings.formatwarning
        format_token = _STANDARD_FORMAT.set(standard)
        scoped: list[Callable[[], None]] = []
        scoped_token = _SCOPED.set(scoped)
        show = warnings.showwarning
        warning_args = list(argv)
        if "--" in warning_args:
            warning_args = warning_args[: warning_args.index("--")]
        for_this_invocation(CONSOLE_WARNINGS, False if "--warning-off" in warning_args else None)
        warnings.showwarning = _visible_warnings(show)
        if not verbose:
            warnings.formatwarning = _short_warnings(standard)
        outcome = "failed"
        terminal = None
        try:
            with command_terminal(verbose=verbose) as terminal, _deprecations_shown():
                result = function(*args, **kwargs)
            outcome = "success" if result is None or result == 0 else "failed"
            return result
        except SystemExit as error:
            if error.code is None or error.code == 0:
                outcome = (
                    "help"
                    if "--help" in argv or "-h" in argv
                    else "version"
                    if "--version" in argv
                    else "success"
                )
            raise
        except KeyboardInterrupt:
            outcome = "cancelled"
            raise
        finally:
            warnings.formatwarning = standard
            _close_invocation(scoped, show)
            _SCOPED.reset(scoped_token)
            _STANDARD_FORMAT.reset(format_token)
            _POSTED.reset(posted_token)
            _POST_WARNINGS.reset(warning_token)
            _ACTIVE.reset(token)
            # FR-997: a quiet console says its errors and final line, then the signature.
            _progress.release_quiet(terminal, failed=outcome in ("failed", "cancelled"))
            if outcome == "success" and posted[0]:
                outcome = "post"
            _sign(outcome)

    return wrapped
