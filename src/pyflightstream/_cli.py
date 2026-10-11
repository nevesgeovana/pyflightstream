"""Shared CLI outcome reporting, below the package's domain layers.

Decorating a console ``main`` preserves its return value and exceptions.
Only the outermost entry point reports, including argparse's early exits.
Machine-readable stdout is never used for human outcome reporting.

Every invocation ends with the package's signature on stderr (0.30.0): a box
drawn from :mod:`pyflightstream._signature` for an outcome, or one short line
for ``--help`` and ``--version`` so their output stays compact. For the length
of the call, a warning of the package's own categories prints as
``[warning] <message>`` with no file, line or echoed source, wrapped at 90
columns under its text and followed by a blank line (0.31.0); ``--verbose``
keeps Python's full format. A Python caller outside a console script is never
touched.

The signature always appears (FR-315): no flag, stream kind or error path hides it.
"""

from __future__ import annotations

import random
import sys
import warnings
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from typing import TextIO

import pyflightstream._progress as _progress
import pyflightstream._signature as _signature
from pyflightstream._console import warning_text
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream._progress import command_terminal

_ACTIVE: ContextVar[bool] = ContextVar("pyflightstream_cli_active", default=False)
_POST_WARNINGS: ContextVar[bool | None] = ContextVar(
    "pyflightstream_cli_post_warnings", default=None
)
#: Python's own warning format, held for the length of one invocation so a
#: console level chosen after the parse can put it back (FR-436 R6).
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
_MESSAGES = {
    "help": ("Help delivered; the map is yours.", "Help ready; pick your next turn."),
    "version": ("Version reported; coordinates checked.", "Version ready; now you know the build."),
}
#: The chooser of drawings and phrases; a test replaces it with a seeded one.
_RNG = random.Random()


def post_warning_policy() -> bool | None:
    """Return CLI warning preference, or None for ordinary Python callers."""
    return _POST_WARNINGS.get()


def note_post_ran() -> None:
    """Record that this invocation ran a post, so its success is signed as one."""
    posted = _POSTED.get()
    if posted is not None:
        posted[0] = True


def set_post_warning_policy(enabled: bool) -> None:
    """Set whether this invocation prints grouped post-processing warnings (FR-436 R5).

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
    """Set the console level of this invocation, chosen after the parse (FR-436 R6).

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


def cli_entrypoint[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    """Report the actual CLI outcome once, without changing CLI semantics."""

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
        if not verbose:
            warnings.formatwarning = _short_warnings(standard)
        outcome = "failed"
        terminal = None
        try:
            with command_terminal(verbose=verbose) as terminal:
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
            # FR-436 R6: a quiet console says its errors and final line, then the signature.
            _progress.release_quiet(terminal, failed=outcome in ("failed", "cancelled"))
            if outcome == "success" and posted[0]:
                outcome = "post"
            _sign(outcome)

    return wrapped
