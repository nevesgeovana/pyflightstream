"""Bounded concurrent solver runs for one campaign (PFS-2201.02).

The campaign loop stays the owner of staging, records and posting. This module
supplies only what concurrency adds: the count resolver, a gate that bounds the
solver subprocesses alive at once, and the worker pool.

The gate is placed around ``run_script`` of each local executor, so the bound
holds on the solver processes themselves. Three conditions hold a start: the
count of runs already alive, a free-memory floor per run, and a short settle
interval after the previous start, because a launched solver claims its memory
only as it loads. A run that fails on the licence while runs could overlap lowers
the bound to one and is repeated once, alone, so a seat count configured too high
costs a repeat of each refused run and no recorded failure.
"""

from __future__ import annotations

import contextvars
import copy
import os
import re
import threading
import time
import warnings
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.run._batch_exec import GroupingExecutor
from pyflightstream.run._executors import submits_jobs
from pyflightstream.run._ids import _say

#: A safety ceiling on concurrent runs, whatever is asked (owner decision).
PARALLEL_HARD_CAP = 8
#: Free memory one more run needs before it starts, in GB; measured about 0.6 GB.
RAM_FLOOR_GB = 1.0
#: Licence seats assumed when none is configured; the licence server is not queried.
LICENCE_SEATS = 2
#: What ``auto`` gives on a multi-core machine: the measured optimum, from the serial gaps.
AUTO_PARALLEL = 2
#: Seconds between two starts, so the previous run's memory is claimed before the next check.
SETTLE_S = 5.0
#: Seconds between two reads of the free memory while a start waits.
START_POLL_S = 0.5

#: Whole words only, within one clause: a word such as "Unknown" holds "no" and must not
#: turn a solver's own failure into a licence refusal (review round 23).
_LICENCE_FAILED = re.compile(
    r"\blicen[cs]e\b[^.;,\n]{0,80}?\b(unavailable|not available|no available|denied|failed|"
    r"failure|could not|cannot|unable|exceeded|in use|no seats?|not found|invalid|expired)\b"
    r"|\b(unable|failed|failure|cannot|could not|no|denied)\b[^.;,\n]{0,40}?\blicen[cs]e\b",
    re.IGNORECASE,
)


def licence_failure(result: Any) -> bool:
    """Whether a solver result is a failed run whose captured text blames the licence."""
    return bool(result.failed and _LICENCE_FAILED.search(result.diagnosis()))


def _licence_words(result: Any) -> str:
    """Return the line of the captured text that was taken for a licence refusal."""
    text = result.diagnosis()
    found = _LICENCE_FAILED.search(text)
    if found is None:
        return ""
    start = text.rfind("\n", 0, found.start()) + 1
    end = text.find("\n", found.end())
    return text[start : end if end >= 0 else len(text)].strip()


def free_ram_gb() -> float | None:
    """Free physical memory in GB, or None when this host cannot say."""
    try:
        import psutil

        return float(psutil.virtual_memory().available / 2**30)
    except ImportError:
        pass
    try:
        if os.name == "nt":
            import ctypes

            class _Status(ctypes.Structure):
                _fields_ = [  # noqa: RUF012
                    ("length", ctypes.c_ulong),
                    ("load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong),
                    ("avail_phys", ctypes.c_ulonglong),
                    ("total_page", ctypes.c_ulonglong),
                    ("avail_page", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("avail_virtual", ctypes.c_ulonglong),
                    ("avail_ext", ctypes.c_ulonglong),
                ]

            status = _Status()
            status.length = ctypes.sizeof(_Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))  # type: ignore[attr-defined]
            return float(status.avail_phys / 2**30)
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return float(line.split()[1]) / 2**20
    except (OSError, ValueError, AttributeError):
        return None
    return None


def resolve_parallel(
    requested: int | str | None,
    *,
    seats: int = LICENCE_SEATS,
    ram_floor_gb: float = RAM_FLOOR_GB,
    cpu_count: int | None = None,
    free_gb: Callable[[], float | None] = free_ram_gb,
    hard_cap: int = PARALLEL_HARD_CAP,
) -> tuple[int, list[str]]:
    """Resolve the concurrent-run count and the notes the resolution owes the user.

    ``None`` and ``1`` are serial. An explicit count is the user's and is cut only
    at the hard cap. ``"auto"`` is the smallest of the machine default (2 on any
    multi-core machine), the configured licence seats, the free memory over the
    floor per run, and the hard cap.
    """
    notes: list[str] = []
    if requested is None:
        return 1, notes
    if requested == "auto":
        cores = cpu_count if cpu_count is not None else (os.cpu_count() or 1)
        count = AUTO_PARALLEL if cores > 1 else 1
        count = min(count, seats, hard_cap)
        free = free_gb()
        if free is not None:
            count = min(count, max(1, int(free // ram_floor_gb)))
        return max(1, count), notes
    count = int(requested)
    if count > hard_cap:
        notes.append(f"parallel {count} is above the hard cap {hard_cap}; running {hard_cap}")
        count = hard_cap
    return max(1, count), notes


class RunGate:
    """Bound the solver runs alive at once; hold a start for memory; fall back on the licence."""

    def __init__(
        self,
        limit: int,
        *,
        ram_floor_gb: float = RAM_FLOOR_GB,
        free_gb: Callable[[], float | None] | None = None,
        settle_s: float | None = None,
        poll_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        is_licence_failure: Callable[[Any], bool] = licence_failure,
    ) -> None:
        self.limit = max(1, limit)
        self.running = 0
        self.peak = 0
        self.fell_back = False
        self._floor = ram_floor_gb
        # Resolved when the gate is made, from the module's values, so a test can set them.
        self._free = free_gb if free_gb is not None else (lambda: free_ram_gb())
        self._settle = SETTLE_S if settle_s is None else settle_s
        self._poll = START_POLL_S if poll_s is None else poll_s
        self._clock = clock
        self._licence_failure = is_licence_failure
        self._last_start = -1e18
        self._cond = threading.Condition()

    def _may_start(self) -> bool:
        if self.running >= self.limit:
            return False
        if self.running == 0:
            return True  # the first run always starts: waiting on memory alone would never end
        if self._clock() - self._last_start < self._settle:
            return False
        free = self._free()
        return free is None or free >= self._floor

    @contextmanager
    def slot(self) -> Iterator[bool]:
        """Hold one run's place: wait until the bound, the settle time and the floor allow it.

        Yields whether the run started while the bound was above one, so runs could overlap.
        """
        with self._cond:
            while not self._may_start():
                self._cond.wait(timeout=self._poll)
            self.running += 1
            self.peak = max(self.peak, self.running)
            self._last_start = self._clock()
            shared = self.limit > 1
        try:
            yield shared
        finally:
            with self._cond:
                self.running -= 1
                self._cond.notify_all()

    def fall_back_to_serial(self) -> bool:
        """Lower the bound to one; True when it was above one before."""
        with self._cond:
            changed = self.limit > 1
            self.limit = 1
            self.fell_back = self.fell_back or changed
            self._cond.notify_all()
            return changed

    def wrap(self, run_script: Callable[..., Any]) -> Callable[..., Any]:
        """Return ``run_script`` gated, repeating once, alone, after a licence failure.

        Every run that started while runs could overlap and fails on the licence is
        repeated, not only the first: runs refused together are each the seat's, not theirs.
        """

        def gated(script_path: Path, working_dir: Path, timeout_s: float | None = None) -> Any:
            with self.slot() as shared:
                result = run_script(script_path, working_dir=working_dir, timeout_s=timeout_s)
            if shared and self._licence_failure(result):
                self.fall_back_to_serial()
                warnings.warn(
                    f"the solver run in {working_dir} failed and its output reads "
                    f"{_licence_words(result)!r}, taken for a licence refusal: later runs go "
                    "one at a time and this run is repeated once, alone",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
                with self.slot():
                    result = run_script(script_path, working_dir=working_dir, timeout_s=timeout_s)
            return result

        return gated


@contextmanager
def gated_campaign(executors: Sequence[Any], workspace: Any, gate: RunGate) -> Iterator[None]:
    """Gate the executors' runs and serialise the workspace's manifest appends.

    Both are instance attributes shadowing the class methods, removed on exit,
    so the objects are exactly as they were once the campaign ends. The manifest
    append already holds a cross-process lease; the thread lock keeps threads of
    this process out of one another's read-modify-write.
    """
    lock = threading.Lock()
    gated_executors: list[Any] = []
    for executor in {id(item): item for item in executors}.values():
        executor.run_script = gate.wrap(executor.run_script)
        gated_executors.append(executor)
    append = workspace.append_record

    def locked_append(record: Any) -> None:
        with lock:
            append(record)

    workspace.append_record = locked_append
    try:
        yield
    finally:
        for executor in gated_executors:
            vars(executor).pop("run_script", None)
        vars(workspace).pop("append_record", None)


def run_pool(units: Sequence[Callable[[], None]], workers: int) -> None:
    """Run every unit on at most ``workers`` threads; the first error is raised after all end.

    Each unit runs in a copy of the caller's context, so the activity log and the
    console of the command reach the worker threads as they reach the serial loop.
    """
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(contextvars.copy_context().run, unit) for unit in units]
    for future in futures:
        error = future.exception()
        if error is not None:
            raise error


def settings_from_cases(cases: Sequence[Any]) -> tuple[int | str | None, int, float]:
    """Read parallel, licence seats and the memory floor from the first case that sets each."""
    values: dict[str, Any] = {}
    for case in cases:
        runtime = getattr(case.solver, "runtime", None)
        if runtime is None:
            continue
        for name in ("parallel", "licence_seats", "ram_floor_gb"):
            if name not in values and getattr(runtime, name) is not None:
                values[name] = getattr(runtime, name)
    return (
        values.get("parallel"),
        values.get("licence_seats", LICENCE_SEATS),
        values.get("ram_floor_gb", RAM_FLOOR_GB),
    )


def campaign_workers(state: Any) -> int:
    """Resolve how many solver runs may be alive at once; 1 is the serial path."""
    cases = [case for case, _, _ in state.scheduled]
    requested, seats, floor = settings_from_cases(cases)
    if state.parallel is not None:
        requested = state.parallel
    count, notes = resolve_parallel(requested, seats=seats, ram_floor_gb=floor)
    for note in notes:
        warnings.warn(note, PyflightstreamWarning, stacklevel=4)
    if count <= 1 or len(state.scheduled) < 2:
        return 1
    executors = [b.executor if b is not None else state.executor for _, b, _ in state.scheduled]
    if any(submits_jobs(e) or isinstance(e, GroupingExecutor) for e in executors):
        _say("parallel applies to local solver runs; running one at a time", quiet=state.quiet)
        return 1
    return min(count, len(state.scheduled))


def run_cases_in_parallel(
    state: Any,
    workers: int,
    prepare: Callable[[Any], None],
    execute: Callable[[Any], None],
    post: Callable[[Any, str], None],
) -> None:
    """Run the scheduled cases on a bounded pool, every case staged before the pool starts.

    Each worker owns a shallow copy of the state taken once its case is prepared, so
    no worker sees another's case; the records, outcomes and failures lists, the
    recorded set and the workspace are shared, and the workspace's appends are
    serialised. A simulation is posted after the pool, once every case ran.
    """
    views: list[Any] = []
    first = 0
    for case, build, pending in state.scheduled:
        state.case, state.build, state.pending = case, build, pending
        prepare(state)
        view = copy.copy(state)
        view.number, view.ran_here = first, 0
        first += len(pending)
        views.append(view)
    floor = settings_from_cases([case for case, _, _ in state.scheduled])[2]
    gate = RunGate(workers, ram_floor_gb=floor)
    _say(f"running up to {workers} solver run(s) at once", quiet=state.quiet)
    units = [lambda view=view: execute(view) for view in views]
    try:
        with gated_campaign([view.case_executor for view in views], state.workspace, gate):
            run_pool(units, workers)
    finally:
        state.number = first
        state.ran_here += sum(view.ran_here for view in views)
    if gate.fell_back:
        _say("a run failed on the licence: later runs went one at a time", quiet=state.quiet)
    last_case = {case.sim_id: index for index, (case, _, _) in enumerate(state.scheduled)}
    for sim_id in sorted(last_case, key=last_case.__getitem__):
        post(state, sim_id)
