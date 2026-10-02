"""Durable workspace activity records, and the console of a running command.

The activity log (``logs/activity.log`` and its JSON twin) records every stage
of a workspace; :func:`workspace_activity` and :func:`activity_stage` write it
and say a stage's ``started`` and ``finished`` lines on stderr.

Since 0.32.0 (work package A, FR-200 to FR-205) this module also holds the
console of one command-line invocation. :func:`command_console` opens it: the
command's titled opening block on stderr, its warnings held and printed
together at the end, and for a long command a live log
``logs/<command>-<stamp>.log`` that receives every line the console shows
while the command runs. :func:`stage_progress` shows the progress of one
stage of a long command: files and bytes done over the total, the current
file, the elapsed time and an estimate, redrawn in place on a terminal and as
plain periodic lines otherwise. All of it prints only inside a console
command; a Python caller sees every line exactly as before, and nothing here
changes a stage's result or raises in its place.
"""

from __future__ import annotations

import inspect
import json
import os
import shutil
import sys
import time
import traceback
import warnings
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import IO, Any

import pyflightstream._textio as _textio
from pyflightstream._console import (
    blocks,
    clock_text,
    held_warnings,
    opening_lines,
    progress_done_text,
    progress_text,
    release_warnings,
    warnings_title,
)
from pyflightstream._errors import PyflightstreamWarning

_ACTIVE: ContextVar[Path | None] = ContextVar("pyfs_activity", default=None)

#: The commands that keep a live log while they run (0.32.0, FR-203): the
#: long ones, whose work can run for minutes between two lines of their own.
LIVE_LOG_COMMANDS = ("sync", "restore", "free-space", "delete-sims", "collect", "post")

#: Seconds between two plain progress lines, where stderr is not a terminal
#: and in the live log (FR-204): a cluster job's log gains six lines a minute
#: per stage at most, and a stage that runs for hours still says it is alive.
PLAIN_PERIOD_S = 10.0

#: Seconds between two redraws of a stage's progress line on a terminal.
REDRAW_PERIOD_S = 0.2

#: Cells of the progress bar a terminal draws.
BAR_CELLS = 20

#: The clock the progress reads; a test replaces it.
_clock: Callable[[], float] = time.monotonic


class _LiveLog:
    """The live log of one command: every console line, written and flushed as it is said."""

    __slots__ = ("path", "stream")

    def __init__(self, path: Path, stream: IO[str]) -> None:
        self.path = path
        self.stream: IO[str] | None = stream

    def write(self, text: str) -> None:
        """Append ``text``; a log that cannot be written is dropped, never raised."""
        if self.stream is None or not text:
            return
        try:
            self.stream.write(text)
            self.stream.flush()
        except (OSError, ValueError):
            self.close()

    def close(self) -> None:
        stream, self.stream = self.stream, None
        if stream is not None:
            try:
                stream.close()
            except (OSError, ValueError):
                pass


class _Console:
    """The console of one command: its title, its live log, its opening still owed."""

    __slots__ = ("log", "pending", "raw_err", "title")

    def __init__(self, title: str, raw_err: IO[str]) -> None:
        self.title = title
        self.raw_err = raw_err
        self.log: _LiveLog | None = None
        #: The opening block, while a command that prints its own header has
        #: printed nothing yet (``plan``): said before the first other line.
        self.pending: str | None = None


class _Terminal:
    """The console of one command-line invocation: its verbosity, its root, its console."""

    __slots__ = ("console", "redrawn", "root", "verbose")

    def __init__(self, verbose: bool) -> None:
        self.verbose = verbose
        self.root: Path | None = None
        self.console: _Console | None = None
        #: The width of the progress line a terminal shows now, to clear before any other line.
        self.redrawn = 0


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
    with _textio.open_text(folder / "activity.log.jsonl", "a") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    with _textio.open_text(folder / "activity.log", "a") as stream:
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
            asked_quiet = bool(bound.arguments.get("quiet", False))
            hidden = verbose_only and terse_terminal()
            quiet = asked_quiet or hidden
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
                # A RETURNED FAILURE IS SAID EVEN WHERE THE STAGE IS KEPT OFF A
                # TERSE CONSOLE (ARCH2-B1, 0.32.0): `verbose_only` hides a stage
                # that has nothing to say, and a failure is something to say. A
                # raised one always was; a returned one vanished.
                if not quiet or (failed and hidden and not asked_quiet):
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
    on. Inside a console command each :meth:`advance` shows the stage's line
    (FR-202): redrawn in place on a terminal at most every
    :data:`REDRAW_PERIOD_S`, and as a plain line at most every
    :data:`PLAIN_PERIOD_S` where stderr is not a terminal and in the live log
    (FR-204). Outside a command it shows nothing, and it never raises.
    """

    __slots__ = (
        "_bytes",
        "_current",
        "_files",
        "_last_plain",
        "_last_redraw",
        "_said",
        "_started",
        "_terminal",
        "name",
        "total_bytes",
        "total_files",
    )

    def __init__(self, name: str, total_files: int | None, total_bytes: int | None) -> None:
        self.name = name
        self.total_files = total_files
        self.total_bytes = total_bytes
        self._terminal = _TERMINAL.get()
        self._files = 0
        self._bytes = 0
        self._current: str | None = None
        self._started = _clock()
        self._last_plain = self._started
        self._last_redraw = self._started
        self._said = False

    def advance(
        self,
        files: int = 0,
        bytes: int = 0,
        current: str | Path | None = None,
    ) -> None:
        """Advance the stage by ``files`` files and ``bytes`` bytes, now on ``current``."""
        try:
            self._files += int(files)
            self._bytes += int(bytes)
            if current is not None:
                self._current = _shown_path(current)
            self._show()
        except Exception:  # an observer never changes the stage it observes
            return

    def each[T](self, items: Iterable[T], label: Callable[[T], object] = str) -> Iterator[T]:
        """Yield each item, the stage on it while the caller's body runs, one file done after.

        A ``continue`` in the caller's loop still counts the item, since the
        count moves when the loop asks for the next one.
        """
        for item in items:
            self.advance(current=_label(label, item))
            yield item
            self.advance(files=1)

    def _unfinished(self) -> bool:
        """Return whether the stage stated a file total and has not reached it."""
        return self.total_files is not None and self._files < self.total_files

    def _line(self, *, bar: int = 0) -> str:
        return progress_text(
            self.name,
            files=self._files,
            total_files=self.total_files,
            done_bytes=self._bytes,
            total_bytes=self.total_bytes,
            elapsed_s=_clock() - self._started,
            current=self._current,
            bar=bar,
        )

    def _show(self) -> None:
        terminal = self._terminal
        if terminal is None:
            return
        now = _clock()
        first = not self._said
        self._said = True
        plain_due = first or now - self._last_plain >= PLAIN_PERIOD_S
        if plain_due:
            self._last_plain = now
        if _is_terminal(terminal):
            if first or now - self._last_redraw >= REDRAW_PERIOD_S:
                self._last_redraw = now
                _redraw(terminal, self._line(bar=BAR_CELLS))
            if plain_due and terminal.console is not None and terminal.console.log is not None:
                terminal.console.log.write(self._line() + "\n")
        elif plain_due:
            say_line(self._line())

    def _close(self, *, stopped: bool) -> None:
        """Say the stage's closing line, where it had anything to do."""
        terminal = self._terminal
        if terminal is None:
            return
        if not (self._said or self._files or self._bytes or self.total_files):
            return
        _clear_redraw(terminal)
        say_line(
            progress_done_text(
                self.name,
                files=self._files,
                total_files=self.total_files,
                done_bytes=self._bytes,
                total_bytes=self.total_bytes,
                elapsed_s=_clock() - self._started,
                stopped=stopped,
            )
        )


@contextmanager
def stage_progress(
    name: str, *, total_files: int | None = None, total_bytes: int | None = None
) -> Iterator[StageProgress]:
    """Show the progress of one stage of a long command (0.32.0 contract, package A).

    Yields a :class:`StageProgress` whose ``advance`` the stage calls as it
    works, and closes with one line saying what was done, or where the stage
    stopped when it raised or was interrupted; the stage's own exception
    passes through unchanged. A stage with nothing to do says nothing, and a
    Python caller outside a console command sees nothing at all.
    """
    stage = StageProgress(name, total_files, total_bytes)
    try:
        yield stage
    except GeneratorExit:
        # A loop that left :func:`tracked` early, by an error of its body or a
        # ``break``, closes the generator: the stage stopped where its count is.
        _close_quietly(stage, stopped=stage._unfinished())
        raise
    except BaseException:
        _close_quietly(stage, stopped=True)
        raise
    else:
        _close_quietly(stage, stopped=False)


def tracked[T](
    name: str,
    items: Iterable[T],
    *,
    label: Callable[[T], object] = str,
    size: Callable[[T], int] | None = None,
) -> Iterator[T]:
    """Iterate ``items`` as one stage, each item one file of it: the one-line hook of a loop.

    ``for record in tracked("collect: points", submitted, label=...)`` shows
    the stage exactly as :func:`stage_progress` with :meth:`StageProgress.each`
    would, without indenting the loop under a ``with``. ``size``, where the
    stage already knows each item's bytes, adds them: the byte total, and
    each item's bytes done once its body has run.
    """
    listed = list(items)
    sizes = [_size_of(size, item) for item in listed] if size is not None else None
    total = sum(sizes) if sizes is not None else None
    with stage_progress(name, total_files=len(listed), total_bytes=total) as stage:
        for index, item in enumerate(stage.each(listed, label)):
            yield item
            if sizes is not None:
                stage.advance(bytes=sizes[index])


def _size_of[T](size: Callable[[T], int], item: T) -> int:
    try:
        return max(int(size(item)), 0)
    except Exception:  # an observer never changes the stage it observes
        return 0


def _close_quietly(stage: StageProgress, *, stopped: bool) -> None:
    try:
        stage._close(stopped=stopped)
    except Exception:  # the closing line never replaces the stage's result
        return


def _label(label: Callable[[Any], object], item: object) -> str | None:
    try:
        return str(label(item))
    except Exception:
        return None


def _shown_path(current: str | Path) -> str:
    """Return the current file as the console shows it: relative to the announced root."""
    return terminal_path(current) if isinstance(current, Path) else str(current)


def _is_terminal(terminal: _Terminal) -> bool:
    """Return whether the console's stderr is a terminal, where a line can be redrawn."""
    stream = terminal.console.raw_err if terminal.console is not None else sys.stderr
    try:
        return bool(stream is not None and stream.isatty())
    except (AttributeError, OSError, ValueError):
        return False


def _raw_err(terminal: _Terminal) -> IO[str] | None:
    return terminal.console.raw_err if terminal.console is not None else sys.stderr


def _redraw(terminal: _Terminal, text: str) -> None:
    """Draw ``text`` over the progress line a terminal shows now; it goes to no log."""
    stream = _raw_err(terminal)
    if stream is None:
        return
    width = max(shutil.get_terminal_size(fallback=(100, 24)).columns - 1, 20)
    shown = text[:width]
    try:
        stream.write("\r" + shown.ljust(terminal.redrawn))
        stream.flush()
    except (OSError, ValueError):
        return
    terminal.redrawn = len(shown)


def _clear_redraw(terminal: _Terminal) -> None:
    """Clear the progress line a terminal shows, so the next line starts on a clean one."""
    if not terminal.redrawn:
        return
    width, terminal.redrawn = terminal.redrawn, 0
    stream = _raw_err(terminal)
    try:
        if stream is not None:
            stream.write("\r" + " " * width + "\r")
    except (OSError, ValueError):
        return


class _ConsoleStream:
    """Standard output or error for the length of a console command.

    Each write clears a progress line a terminal shows, says the opening block
    first where it is still owed, then goes to the stream it wraps and to the
    live log. Every other attribute is the wrapped stream's.
    """

    def __init__(self, raw: IO[str], terminal: _Terminal, console: _Console) -> None:
        self._raw = raw
        self._terminal = terminal
        self._console = console

    def write(self, text: str) -> int:
        if text:
            _before_a_line(self._terminal, self._console, text)
        written = self._raw.write(text)
        if self._console.log is not None:
            self._console.log.write(text)
        return written

    def flush(self) -> None:
        self._raw.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)


def _before_a_line(terminal: _Terminal, console: _Console, text: str) -> None:
    _clear_redraw(terminal)
    pending, console.pending = console.pending, None
    if pending is None or text.startswith(console.title):
        return
    try:
        console.raw_err.write(pending)
        console.raw_err.flush()
    except (OSError, ValueError):
        return
    if console.log is not None:
        console.log.write(pending)


def _live_log(root: Path, command: str, title: str) -> tuple[_LiveLog | None, str | None]:
    """Open ``logs/<command>-<stamp>.log`` of a workspace; return it and how the opening names it.

    Only in a campaign workspace (a ``runs.json`` or an ``inputs/`` folder), so
    a command pointed at another folder creates nothing there; a log that
    cannot be opened is named in the opening block and the command runs on.
    """
    if not ((root / "runs.json").is_file() or (root / "inputs").is_dir()):
        return None, None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = root / "logs"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for attempt in range(1, 100):
            name = f"{command}-{stamp}.log" if attempt == 1 else f"{command}-{stamp}-{attempt}.log"
            try:
                stream = _textio.open_text(folder / name, "x")
            except FileExistsError:
                continue
            log = _LiveLog(folder / name, stream)
            log.write(f"# {title} started {datetime.now(UTC).isoformat()}\n")
            return log, f"logs/{name}"
    except OSError as error:
        return None, f"not written ({error})"
    return None, "not written (every name of this second is taken)"


def print_held_warnings(held: list[warnings.WarningMessage]) -> None:
    """Print held warnings as one titled block on stderr, a blank line before and after.

    The one printer of the ``Warnings (<count>)`` block (FR-201): ``plan``
    prints it after its header, every other command at its end.
    """
    if not held:
        return
    print(f"\n{warnings_title(len(held))}", file=sys.stderr, flush=True)
    release_warnings(held)
    if not terse_terminal() or not issubclass(held[-1].category, PyflightstreamWarning):
        # Python's own format (under --verbose, or a third party's warning)
        # ends without the blank line the short form adds.
        print(file=sys.stderr)
    sys.stderr.flush()


@contextmanager
def command_console(
    program: str,
    command: str,
    *,
    what: str,
    workspace: str | Path | None = None,
    live_log: bool = False,
    header: bool = False,
    hold: bool = True,
) -> Iterator[None]:
    """Open the console of one command (0.32.0 console contract, FR-200 to FR-204).

    Prints the titled opening block on stderr: ``<program> <command>``, then
    what the command is for (``what``), the workspace and, with ``live_log``,
    where the live log is written. A command that prints its own header
    (``header``, the ``plan`` summary) has the block said only when some
    other line would come first. With ``hold`` every warning is held and
    printed as one block at the end, a refusal and an interruption included.
    With ``live_log`` in a campaign workspace, every line the console shows,
    standard output included, is written to ``logs/<command>-<stamp>.log`` as
    it is said. Standard output carries exactly what it carried before.

    Only inside :func:`command_terminal`, and once: a nested command runs in
    the console already open.
    """
    terminal = _TERMINAL.get()
    if terminal is None or terminal.console is not None or sys.stderr is None:
        yield
        return
    title = f"{program} {command}"
    root = None if workspace is None else Path(workspace).resolve()
    console = _Console(title, sys.stderr)
    shown = None
    if live_log and root is not None:
        console.log, shown = _live_log(root, command, title)
    opening = blocks([(title, opening_lines(what, workspace=root, live_log=shown))]) + "\n\n"
    streams = (sys.stdout, sys.stderr)
    terminal.console = console
    if sys.stdout is not None:
        sys.stdout = _ConsoleStream(sys.stdout, terminal, console)  # type: ignore[assignment]
    sys.stderr = _ConsoleStream(sys.stderr, terminal, console)  # type: ignore[assignment]
    started = _clock()
    ended = "finished"
    held: list[warnings.WarningMessage] = []
    try:
        if header:
            console.pending = opening
        else:
            print(opening, end="", file=sys.stderr, flush=True)
        with ExitStack() as stack:
            if hold:
                held = stack.enter_context(held_warnings())
            yield
    except SystemExit as error:
        if error.code not in (None, 0):
            ended = f"ended with exit {error.code}"
        raise
    except BaseException as error:
        ended = f"ended by {type(error).__name__}"
        raise
    finally:
        try:
            if console.pending is not None:
                _before_a_line(terminal, console, "")
            if held:
                if sys.stdout is not None:
                    sys.stdout.flush()
                print_held_warnings(held)
        finally:
            _clear_redraw(terminal)
            sys.stdout, sys.stderr = streams
            terminal.console = None
            if console.log is not None:
                console.log.write(
                    f"# {ended} {datetime.now(UTC).isoformat()} after "
                    f"{clock_text(_clock() - started)}\n"
                )
                console.log.close()
