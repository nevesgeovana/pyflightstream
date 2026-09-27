# GEOVERSE_HEADER
# file_version: 1.0.2
# artifact_id: cli-outcome-signature
# last_modified_at: 2026-09-27T20:09:05.841Z
# last_modified_by: OpenAI / Codex / GPT-6 / primary-agent
# dependencies: [Python standard library]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Narrow explicit CLI argument sequences before inspecting help and warning flags.
# revision_source: git
"""Shared CLI outcome reporting, below the package's domain layers.

Decorating a console ``main`` preserves its return value and exceptions.
Only the outermost entry point reports, including argparse's early exits.
Machine-readable stdout is never used for human outcome reporting.
"""

from __future__ import annotations

import random
import sys
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps

_ACTIVE: ContextVar[bool] = ContextVar("pyflightstream_cli_active", default=False)
_POST_WARNINGS: ContextVar[bool | None] = ContextVar(
    "pyflightstream_cli_post_warnings", default=None
)
_MESSAGES = {
    "help": ("Help delivered; the map is yours.", "Help ready; pick your next turn."),
    "version": ("Version reported; coordinates checked.", "Version ready; now you know the build."),
    "success": (
        "Great work! Another step in orbit.",
        "Great work! Mission step complete; onward at your pace.",
    ),
    "failed": (
        "Command failed; the details above mark the snag.",
        "Command failed; time to inspect the trail.",
    ),
    "cancelled": (
        "Command cancelled; taking a pause.",
        "Command cancelled; the controls are yours.",
    ),
}


def post_warning_policy() -> bool | None:
    """Return CLI warning preference, or None for ordinary Python callers."""
    return _POST_WARNINGS.get()


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
        outcome = "failed"
        try:
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
            _POST_WARNINGS.reset(warning_token)
            _ACTIVE.reset(token)
            try:
                print(f"{random.choice(_MESSAGES[outcome])} Ass: geoversegoddes", file=sys.stderr)
            except (OSError, ValueError):
                # A closed diagnostic stream must not replace the real result.
                pass

    return wrapped
