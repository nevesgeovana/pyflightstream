"""Shared CLI outcome reporting, below the package's domain layers.

Decorating a console ``main`` preserves its return value and exceptions.
Only the outermost entry point reports, including argparse's early exits.
Machine-readable stdout is never used for human outcome reporting.

Every invocation ends with the package's signature on stderr (0.30.0): a box
drawn from :mod:`pyflightstream._signature` for an outcome, or one short line
for ``--help`` and ``--version`` so their output stays compact. For the length
of the call, a warning of the package's own categories prints as
``[warning] <message>`` with no file, line or echoed source; ``--verbose``
keeps Python's full format. A Python caller outside a console script is never
touched.
"""

from __future__ import annotations

import random
import sys
import warnings
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps

from pyflightstream import _signature
from pyflightstream._errors import PyflightstreamWarning
from pyflightstream._progress import command_terminal

_ACTIVE: ContextVar[bool] = ContextVar("pyflightstream_cli_active", default=False)
_POST_WARNINGS: ContextVar[bool | None] = ContextVar(
    "pyflightstream_cli_post_warnings", default=None
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


def _signature_text(outcome: str) -> str:
    """Return what the invocation prints on stderr for ``outcome``."""
    if outcome in _MESSAGES:
        return f"{_RNG.choice(_MESSAGES[outcome])} {_signature.SEES_YOU}"
    name, phrase = _signature.pick(outcome, _RNG)
    return f"\n{_signature.box(name, phrase)}\n"


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
            return f"[warning] {message}\n"
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
        if not verbose:
            warnings.formatwarning = _short_warnings(standard)
        outcome = "failed"
        try:
            with command_terminal(verbose=verbose):
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
            _POSTED.reset(posted_token)
            _POST_WARNINGS.reset(warning_token)
            _ACTIVE.reset(token)
            if outcome == "success" and posted[0]:
                outcome = "post"
            try:
                print(_signature_text(outcome), file=sys.stderr)
            except (OSError, ValueError):
                # A closed or unencodable diagnostic stream must not replace
                # the real result.
                pass

    return wrapped
