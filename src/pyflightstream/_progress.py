"""Durable workspace activity records."""

from __future__ import annotations

import inspect
import json
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
        print(f"[{stage}] could not persist diagnostic: {log_error}", file=sys.stderr, flush=True)


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


def workspace_activity(stage: str, argument: str = "workspace"):
    """Log one stage without changing its result."""

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
            quiet = bool(bound.arguments.get("quiet", False))
            try:
                record_activity(stage, "started", str(root), **context)
                if not quiet:
                    print(f"[{stage}] started: {root}", file=sys.stderr, flush=True)
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
                    print(f"[{stage}] {status}{detail}", file=sys.stderr, flush=True)
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
                    print(
                        f"[{stage}] could not persist diagnostic: {log_error}",
                        file=sys.stderr,
                        flush=True,
                    )
                print(f"[{stage}] {type(error).__name__}: {error}", file=sys.stderr, flush=True)
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
            print(f"[{stage}] could not persist diagnostic: {log_error}", file=sys.stderr)
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
