"""Durable workspace activity records."""

from __future__ import annotations

import inspect
import json
import os
import sys
import time
import traceback
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path

_ACTIVE: ContextVar[Path | None] = ContextVar("pyfs_activity", default=None)


class _Terminal:
    """The console of one command-line invocation: its verbosity and its root."""

    __slots__ = ("root", "verbose")

    def __init__(self, verbose: bool) -> None:
        self.verbose = verbose
        self.root: Path | None = None


#: Set by a console script for the length of one invocation, and by nothing
#: else: a Python caller sees every line exactly as before (0.30.0 clean log).
_TERMINAL: ContextVar[_Terminal | None] = ContextVar("pyfs_terminal", default=None)


@contextmanager
def command_terminal(*, verbose: bool) -> Iterator[None]:
    """Mark the console output of one command-line invocation.

    Inside it, a path under the workspace root is printed relative to that
    root after the root itself was printed once, absolute, on the first
    ``[<stage>] started:`` line, and without ``verbose`` a site that repeats one
    warning per item may say it once with a count (:func:`terse_terminal`).
    The records and the activity log keep absolute paths and every item.
    """
    token = _TERMINAL.set(_Terminal(verbose))
    try:
        yield
    finally:
        _TERMINAL.reset(token)


def terse_terminal() -> bool:
    """Return whether a console command without ``--verbose`` is printing."""
    terminal = _TERMINAL.get()
    return terminal is not None and not terminal.verbose


def terminal_path(path: str | Path) -> str:
    """Return ``path`` as the console of a command shows it.

    Relative to the root the command announced when it lies under that root,
    and exactly ``str(path)`` otherwise, which is also everything a Python
    caller outside a console command ever sees.
    """
    terminal = _TERMINAL.get()
    if terminal is None or terminal.root is None:
        return str(path)
    try:
        relative = Path(path).relative_to(terminal.root)
    except ValueError:
        return str(path)
    return relative.as_posix()


def terminal_glob(paths: list[Path]) -> str:
    """Return one pattern for several paths as the console shows them.

    Each component the paths share is kept, and each one they do not becomes
    ``*`` after the text up to its first ``-`` when they all share that, so
    ten archived datapoints read as ``sims/sim_1/datapoints/DP-*/archive/<stamp>``.
    """
    shown = [Path(terminal_path(path)) for path in paths]
    if len({len(path.parts) for path in shown}) != 1:
        return f"{Path(os.path.commonpath(shown)).as_posix()}/*"
    merged = [
        parts[0] if len(set(parts)) == 1 else _wildcard(parts)
        for parts in zip(*(path.parts for path in shown), strict=True)
    ]
    return Path(*merged).as_posix()


def _wildcard(names: tuple[str, ...]) -> str:
    """Return ``<prefix>-*`` when every name shares the text before its first ``-``, else ``*``."""
    prefixes = {name.split("-", 1)[0] for name in names if "-" in name}
    if len(prefixes) == 1 and all("-" in name for name in names):
        return f"{prefixes.pop()}-*"
    return "*"


def _announced(root: Path) -> str:
    """Print a console command's first root absolute and later paths under it relative."""
    terminal = _TERMINAL.get()
    if terminal is not None and terminal.root is None:
        terminal.root = root
        return str(root)
    return terminal_path(root)


def activity_event(stage: str, event: str, message: str = "", **details: object) -> None:
    """Append to both logs; never to stdout."""
    folder = _ACTIVE.get()
    if folder is None:
        return
    folder.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "stage": stage,
        "event": event,
        "message": message,
        **details,
    }
    with (folder / "activity.log.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    with (folder / "activity.log").open("a", encoding="utf-8") as stream:
        stream.write(f"{record['timestamp']} [{stage}] {event}: {message}\n")
        if details:
            stream.write(json.dumps(details, ensure_ascii=False, default=str) + "\n")


def say_line(text: str) -> None:
    """Say one progress or diagnostic line; a closed or broken stderr is not an error.

    Everything this module prints observes a stage and must not change its
    result (Q0-src-other-1; GOAL-034 Q8 CXQ8R2-2): a line that cannot be said is
    dropped, and the stage's own result or exception stands.
    """
    try:
        print(text, file=sys.stderr, flush=True)
    except (OSError, ValueError):
        pass


def record_activity(stage: str, event: str, message: str = "", **details: object) -> None:
    """Append an activity event; a log that cannot be written is said, never raised.

    The activity log observes a stage and must not change its result
    (Q0-src-other-1): a read-only, full or locked workspace would otherwise
    stop a stage before it ran, or turn a finished solver run into an OSError.
    Every writer outside this module goes through this one, never through
    :func:`activity_event` itself (GOAL-034 Q8 CXQ8-1).
    """
    try:
        activity_event(stage, event, message, **details)
    except (OSError, ValueError) as log_error:
        say_line(f"[{stage}] could not persist diagnostic: {log_error}")


def _failure_message(result: object) -> str:
    """Return a failed result's own report; a report that raises is named, not raised."""
    try:
        diagnosis = getattr(result, "diagnosis", None)
        message = diagnosis() if callable(diagnosis) else ""
        report_lines = getattr(result, "lines", None)
        if not message and callable(report_lines):
            message = "\n".join(report_lines())
    except Exception as report_error:
        return f"diagnosis unavailable: {report_error}"
    return str(message)


def workspace_activity(stage: str, argument: str = "workspace", *, verbose_only: bool = False):
    """Log one stage without changing its result.

    With ``verbose_only`` the stage's ``started`` and ``finished`` lines reach
    the console of a command only under ``--verbose`` (0.31.0): a stage that
    runs once per point whether or not it has anything to do is otherwise noise.
    The activity log records it either way, a Python caller outside a command
    sees the lines as before, and a stage that raises is always said.
    """

    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        def wrapped(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            target = bound.arguments.get(argument)
            if target is None:
                return function(*args, **kwargs)
            root = Path(target if isinstance(target, str | Path) else target.root)
            token = _ACTIVE.set(_ACTIVE.get() or root / "logs")
            context = {
                key: str(bound.arguments[key])
                for key in ("sim_id", "datapoint", "run_id")
                if key in bound.arguments
            }
            started = time.monotonic()
            quiet = bool(bound.arguments.get("quiet", False)) or (verbose_only and terse_terminal())
            try:
                record_activity(stage, "started", str(root), **context)
                if not quiet:
                    say_line(f"[{stage}] started: {_announced(root)}")
                result = function(*args, **kwargs)
                records = result if isinstance(result, list | tuple) else []
                # ADDITIONAL-POST RETURNS `(plans, records)` (Q0 CX-8): the
                # outcomes are the second list's, not the tuple's two members,
                # which carry no status and hid a failed extraction.
                if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], list):
                    records = result[1]
                outcomes = dict(
                    Counter(str(record.status) for record in records if hasattr(record, "status"))
                )
                failed = bool(getattr(result, "failed", False)) or any(
                    status.startswith("FAILED") for status in outcomes
                )
                message = _failure_message(result) if failed else ""
                record_activity(
                    stage,
                    "failed" if failed else "finished",
                    message,
                    duration_s=time.monotonic() - started,
                    outcomes=outcomes,
                    **context,
                )
                if not quiet:
                    status = "failed" if failed else "finished"
                    detail = f"; outcomes={outcomes}" if outcomes else ""
                    say_line(f"[{stage}] {status}{detail}")
                return result
            except BaseException as error:
                try:
                    activity_event(
                        stage,
                        "cancelled" if isinstance(error, KeyboardInterrupt) else "failed",
                        str(error),
                        exception_type=type(error).__name__,
                        duration_s=time.monotonic() - started,
                        traceback=traceback.format_exc(),
                        **context,
                    )
                except (OSError, ValueError) as log_error:
                    say_line(f"[{stage}] could not persist diagnostic: {log_error}")
                say_line(f"[{stage}] {type(error).__name__}: {error}")
                raise
            finally:
                _ACTIVE.reset(token)

        return wrapped

    return decorate


@contextmanager
def activity_stage(stage: str, **details: object) -> Iterator[dict[str, object]]:
    """Record one batch within the active workspace; leave product bytes alone."""
    started = time.monotonic()
    outcome: dict[str, object] = {}
    record_activity(stage, "started", "", **details)
    try:
        yield outcome
    except BaseException as error:
        try:
            activity_event(
                stage,
                "failed",
                str(error),
                **details,
                duration_s=time.monotonic() - started,
                exception_type=type(error).__name__,
            )
        except (OSError, ValueError) as log_error:
            say_line(f"[{stage}] could not persist diagnostic: {log_error}")
        raise
    else:
        record_activity(
            stage,
            "failed" if outcome.get("problems") else "finished",
            "",
            **details,
            **outcome,
            duration_s=time.monotonic() - started,
        )


class StageProgress:
    """The progress of one stage of a long command, as :func:`stage_progress` hands it.

    The 0.32.0 contract of work package A, which the sync (B2) and the
    records commands (B3) call: a stage announces its totals when it knows
    them, and advances by the files and bytes it finished and the file it is
    on. The body of :meth:`advance` is a NO-OP until A fills it, and it never
    raises, so a caller adopts it before the progress is drawn.
    """

    __slots__ = ("name", "total_bytes", "total_files")

    def __init__(self, name: str, total_files: int | None, total_bytes: int | None) -> None:
        self.name = name
        self.total_files = total_files
        self.total_bytes = total_bytes

    def advance(
        self,
        files: int = 0,
        bytes: int = 0,
        current: str | Path | None = None,
    ) -> None:
        """Advance the stage by ``files`` files and ``bytes`` bytes, now on ``current``."""


@contextmanager
def stage_progress(
    name: str, *, total_files: int | None = None, total_bytes: int | None = None
) -> Iterator[StageProgress]:
    """Show the progress of one stage of a long command (0.32.0 contract, package A).

    Yields a :class:`StageProgress` whose ``advance`` the stage calls as it
    works. It prints nothing and records nothing until work package A fills
    it, and it never raises.
    """
    yield StageProgress(name, total_files, total_bytes)
