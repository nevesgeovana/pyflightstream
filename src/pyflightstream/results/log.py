"""The solver log and its residual history, parsed.

The residual history and the per-solve residuals (:func:`parse_residual_history`,
:func:`parse_residual_solves`), the frozen time steps of an unsteady solve
(:func:`frozen_time_steps`), the run's wall times (:func:`parse_log_times`)
and the trailing edges the solver reports it imported
(:func:`imported_trailing_edges`); and the cumulative log of a job that
ran several points cut into each point's own log (:func:`split_job_log`,
:func:`point_log_text`).

Residual, timing and trailing-edge helpers are re-exported by
:mod:`pyflightstream.results` (AD-11). Job-log splitting helpers are
accessed through this module by grouped collection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pyflightstream import versions
from pyflightstream.results.core import (
    RESIDUAL_PAGE,
    IncompleteOutputError,
    MalformedOutputError,
    delimited_table,
    parse_count,
    parse_number,
)

__all__ = [
    "lifting_log_warnings",
    "RESTART_MARKER",
    "FrozenSolve",
    "LogSegment",
    "LogTimes",
    "ResidualSample",
    "UnjudgeableSolve",
    "frozen_time_steps",
    "imported_trailing_edges",
    "parse_log_times",
    "parse_residual_history",
    "parse_residual_solves",
    "point_log_text",
    "split_job_log",
]


@dataclass(frozen=True)
class ResidualSample:
    """One row of the solver residual history.

    Attributes
    ----------
    iteration : int
        Solver iteration number.
    velocity_residual : float
        Surface velocity residual, dimensionless.
    pressure_residual : float
        Surface pressure residual, dimensionless.
    overflowed : frozenset of str
        The columns (``"velocity"``, ``"pressure"``) the solver printed as a
        field of asterisks on this row, read as NaN. Kept apart from a NaN the
        solver PRINTED, because a field too narrow for a tiny number is not a
        diverged solve.
    """

    iteration: int
    velocity_residual: float
    pressure_residual: float
    overflowed: frozenset[str] = frozenset()


#: A printed field the solver could not fit its value into. Fortran writes a
#: run of asterisks when a number is wider than its format, and the log's
#: residual columns are narrow.
_OVERFLOWED_FIELD = re.compile(r"^\*+$")


def _residual_cell(token: str) -> float:
    """One residual cell, or NaN where the solver could not print it.

    NOT A REFUSAL, and not infinity either. Measured on 26.123, iteration
    146 of a 198-iteration run, with its two neighbours beside it:

        145    +2.1752754E-6    +9.1412955E-9
        146    +2.1313669E-6    *************
        147    +2.0894156E-6    +7.5856726E-9

    The neighbours are tiny, so the asterisks most plausibly mark a field too
    NARROW rather than a magnitude too large; the file does not state the
    cause, and reading them as infinity would be a claim it does not make.
    Raising would be worse: the convergence verdict is the LAST row, and one
    unprintable cell in the middle would throw a whole run's history away.

    NaN is also the conservative direction for a test written as
    ``residual < tolerance``: that comparison is False for NaN, so an unknown
    residual is not read as converged. A test written as the negation of
    ``residual > tolerance`` would read it as converged, so a consumer
    checks finiteness explicitly rather than relying on the comparison.
    """
    if _OVERFLOWED_FIELD.match(token.strip()):
        return float("nan")
    return parse_number(token)


def parse_residual_history(text: str) -> list[ResidualSample]:
    """Parse the residual table of an exported solver log.

    The log's iteration table carries the velocity and pressure
    residuals the convergence threshold applies to (FSM-26.120 p.200);
    the final row is the convergence evidence of the run.

    Parameters
    ----------
    text : str
        Complete log text (EXPORT_LOG output or captured log file).

    Returns
    -------
    list of ResidualSample
        The history in iteration order; the first three columns of
        each row (iteration, velocity residual, pressure residual)
        are parsed, further columns vary with the run setup.

    Raises
    ------
    IncompleteOutputError
        If the log holds no residual table (a ``ValueError``).
    MalformedOutputError
        If a row cannot be read, or the iteration counter does not
        increase down the table (a ``ValueError``).
    """
    # Real hidden-mode log exports carry stray NUL bytes between lines
    # (observed on 26.120 build 7012026); scrub them before parsing.
    clean = text.replace("\x00", "")
    # EVERY PAGE, AND NOT ONLY THE FIRST, joined (:func:`_residual_rows`, which
    # says why and what it measured). A log of several solves is read by
    # :func:`parse_residual_solves`; here a restart is refused.
    history: list[ResidualSample] = []
    for row, _ in _residual_rows(clean):
        sample = _residual_sample(row)
        # PYFS-009. The counter was read and never checked, so a history of
        # [1, 2, 1574, 2] parsed clean. That shape is two runs' logs
        # concatenated, or a table that wrapped, and the CONVERGENCE JUDGMENT
        # READS THE LAST ROW: the run would be judged on a residual belonging
        # to an earlier iteration of a different solve. A monotonic counter is
        # what makes "the last row" mean "the final state".
        if history and sample.iteration <= history[-1].iteration:
            raise MalformedOutputError(
                f"the residual table's iteration counter goes from "
                f"{history[-1].iteration} to {sample.iteration}, so it does not increase. "
                "The final row is the convergence evidence of the run, and it is only "
                "the final state if the counter orders the table; a repeat or a "
                "decrease means two logs were concatenated or the table wrapped"
            )
        history.append(sample)
    if not history:
        raise IncompleteOutputError("the log residual table is empty")
    return history


_VELOCITY_COLUMN = re.compile(r"res\.?\s*vel", re.IGNORECASE)
_PRESSURE_COLUMN = re.compile(r"res\.?\s*pres", re.IGNORECASE)


def _page_rows(page: str) -> list[list[str]]:
    """Read one residual page's rows as ``[iteration, velocity, pressure, ...]``.

    The columns are found by the NAMES the page's header prints, never by
    position alone: a header that lists the pressure residual before the
    velocity one would otherwise swap the two. A header that names neither
    column keeps the measured layout (iteration, velocity, pressure); one
    that names only one of them is refused.
    """
    text = "Iteration" + page
    table = delimited_table(text, "Iteration", delimiter=None)
    names = [name for name in re.split(r"\t|\s{2,}", text.splitlines()[0].strip()) if name]
    velocity = next((at for at, name in enumerate(names) if _VELOCITY_COLUMN.search(name)), None)
    pressure = next((at for at, name in enumerate(names) if _PRESSURE_COLUMN.search(name)), None)
    if velocity is None and pressure is None:
        return table
    if velocity is None or pressure is None:
        raise MalformedOutputError(
            f"the residual table's header {names!r} names only one of the velocity and "
            "pressure residual columns, so the other cannot be told from its neighbours"
        )
    if velocity == pressure:
        # Names separated by single spaces read as one cell: only their order in
        # the line is known, and the two sit right after the iteration counter.
        first_line = text.splitlines()[0]
        vel_at = _VELOCITY_COLUMN.search(first_line)
        pres_at = _PRESSURE_COLUMN.search(first_line)
        if vel_at is None or pres_at is None or vel_at.start() < pres_at.start():
            return table
        velocity, pressure = 2, 1
    if (velocity, pressure) == (1, 2):
        return table
    reordered = []
    for row in table:
        if len(row) <= max(velocity, pressure):
            raise MalformedOutputError(
                f"residual row {row!r} holds fewer values than the header {names!r} names"
            )
        rest = [cell for at, cell in enumerate(row) if at not in (0, velocity, pressure)]
        reordered.append([row[0], row[velocity], row[pressure], *rest])
    return reordered


def _residual_rows(clean: str) -> list[tuple[list[str], bool]]:
    """Return every residual row with whether it opens a page.

    EXPORT_LOG repeats the Iteration header and closing dashed rule on
    each page. Read every page so the final row represents the final state.
    The iteration counter continues across pages, including unsteady
    time-step boundaries; parse_residual_history checks monotonicity
    across the joined sequence.
    """
    pages = RESIDUAL_PAGE.split(clean)
    rows: list[tuple[list[str], bool]] = []
    for index, page in enumerate(pages):
        if index == 0:
            continue
        table = _page_rows(page)
        rows.extend((row, at == 0) for at, row in enumerate(table))
    if not rows:
        # Use the table parser's diagnostic when no residual page is found.
        table = delimited_table(clean, "Iteration", delimiter=None)
        rows = [(row, at == 0) for at, row in enumerate(table)]
    return rows


def _residual_sample(row: list[str]) -> ResidualSample:
    """Read one row of the residual table: its iteration and its two residuals."""
    if len(row) < 3:
        raise MalformedOutputError(
            f"residual row {row!r} holds fewer than three columns (iteration, "
            "velocity residual, pressure residual); the log table layout changed"
        )
    return ResidualSample(
        iteration=parse_count(row[0], label="the residual table's iteration counter"),
        velocity_residual=_residual_cell(row[1]),
        pressure_residual=_residual_cell(row[2]),
        overflowed=frozenset(
            name
            for name, token in (("velocity", row[1]), ("pressure", row[2]))
            if _OVERFLOWED_FIELD.match(token.strip())
        ),
    )


def parse_residual_solves(text: str) -> list[list[ResidualSample]]:
    r"""Parse a solver log that holds several steady solves, one residual history each.

    A quasi-steady rotor wheel is solved at each of its clockings in one run: the solver is
    initialised again between them and each solve
    prints its own residual table, its counter starting again at 1, so the
    one log the run exports holds every clocking's solve in the order the
    script ran them. :func:`parse_residual_history` refuses such a log, as it
    must for a log of one solve, where a restart is two logs concatenated.

    A NEW SOLVE IS A TABLE OF ITS OWN: the counter goes back to 1 on the
    first row after the ``Iteration`` header. A counter that falls or repeats
    anywhere else, or starts again at any other number, is refused as
    :func:`parse_residual_history` refuses it, because it is not a solve the
    solver started. Within each solve the counter increases. How many solves
    the log must hold is the caller's to check against the run.

    Parameters
    ----------
    text : str
        Complete log text (EXPORT_LOG output or captured log file).

    Returns
    -------
    list of list of ResidualSample
        One history per solve, in the order the log prints them; a log of one
        solve gives one.

    Raises
    ------
    MalformedOutputError
        A counter that does not increase inside a solve, or a restart that is
        not a new table starting at iteration 1.
    IncompleteOutputError
        No residual row at all.

    Examples
    --------
    >>> page = "Iteration  Res.Vel.  Res.Pres.\n{}\n----------\n"
    >>> log = page.format("1 1.0 1.0\n2 1e-6 1e-6") + page.format("1 1.0 1.0\n2 2e-6 1e-6")
    >>> [[sample.iteration for sample in solve] for solve in parse_residual_solves(log)]
    [[1, 2], [1, 2]]
    """
    clean = text.replace("\x00", "")
    solves: list[list[ResidualSample]] = []
    for row, opens_a_page in _residual_rows(clean):
        sample = _residual_sample(row)
        current = solves[-1] if solves else None
        if current is None or (
            sample.iteration <= current[-1].iteration and opens_a_page and sample.iteration == 1
        ):
            solves.append([sample])
            continue
        if sample.iteration <= current[-1].iteration:
            raise MalformedOutputError(
                f"the residual table's iteration counter goes from "
                f"{current[-1].iteration} to {sample.iteration} inside one solve, so it "
                "does not increase. A new solve prints a table of its own whose counter "
                "starts at 1; a repeat or a decrease anywhere else means two logs were "
                "concatenated or the table wrapped"
            )
        current.append(sample)
    if not solves:
        raise IncompleteOutputError("the log residual table is empty")
    return solves


@dataclass(frozen=True)
class FrozenSolve:
    """A frozen unsteady solve, counted in the log's 1-based time steps."""

    first_step: int
    count: int

    @property
    def reason(self) -> str:
        """Describe the freeze for assessment and product skip records."""
        return f"frozen solve: first frozen time step {self.first_step}; {self.count} frozen steps"


@dataclass(frozen=True)
class UnjudgeableSolve(FrozenSolve):
    """A solve whose native log cannot answer the freeze question.

    A run that was stopped or killed leaves its last residual page without a
    closing separator, and the detector refuses to read a table that ends
    mid-write. That is not evidence of a freeze and it is NOT evidence of a
    healthy solve either: on a real frozen log, cutting the last page hides
    ``FrozenSolve(60, 2)`` entirely. An average that cannot be shown to avoid a
    frozen solve is therefore refused exactly as a frozen one is -- and so
    ``first_step`` is 1, which every window of the point ends at or after.

     ``steps`` names the time
    steps whose residual blocks could not be read; ``first_step`` is the first
    of them, so a reader that knows only ``FrozenSolve`` still refuses rather
    than accepts.
    """

    steps: tuple[int, ...] = ()
    #: The first step of a freeze confirmed in the blocks that WERE read, if any.
    #: A log can hold both kinds of evidence, and returning only one of them
    #: published averages over the other .
    frozen_from: int | None = None
    detail: str = ""

    @property
    def reason(self) -> str:
        """Say what could not be read and what would settle it."""
        named = ", ".join(str(step) for step in self.steps) or str(self.first_step)
        frozen = (
            f"; the blocks that WERE read show a frozen solve from time step {self.frozen_from}"
            if self.frozen_from is not None
            else ""
        )
        return (
            f"the native log cannot be read for time step(s) {named} (unread), so the freeze check "
            "could not run over them and an average covering them cannot be shown to avoid a "
            f"frozen solve{frozen}"
            + (f": {self.detail}" if self.detail else "")
            + ". The solver stopped mid-write there; recollect that log, or run the point "
            "again, and the average returns on its own."
        )


def _residual_cell_is_readable(cell: str) -> bool:
    """Whether a residual cell is a number or an overflowed field of asterisks."""
    if re.fullmatch(r"\*+", cell):
        return True
    try:
        parse_number(cell)
    except MalformedOutputError:
        return False
    return True


def frozen_time_steps(log_text: str, *, unjudged: list[int] | None = None) -> FrozenSolve | None:
    """Detect a freeze from the printed residuals of an unsteady log.

    A time step is frozen when every inner iteration after its first prints
    exactly zero velocity residual and its last iteration prints both residuals
    exactly zero. A solve is
    frozen only when at least two consecutive time steps meet this rule; the
    result names the first step of the first such stretch and counts the frozen
    steps in qualifying stretches. Step numbers come from the solver's 1-based
    ``(k/N)`` markers, never from its cumulative inner-iteration counter.
    Steady logs, which have no unsteady step markers, return None.

    ``unjudged`` OPTS IN TO TOLERANCE, and the post stage is its only caller.
    A block whose residual pages cannot be read -- a header with no rows under
    it, which is what a run stopped by its walltime guard leaves, or a page cut
    mid-write -- is then SKIPPED and its step number appended, rather than
    raising. Without it this raises as it always has, which is what the collect
    path needs to record FAILED_INCOMPLETE_OUTPUT (FR-17).

    A skipped block is not evidence of a healthy step and must never be read as
    one: it breaks the streak, so it can neither begin nor extend a freeze, and
    the caller is handed the step numbers to refuse the windows they fall in.

    Parameters
    ----------
    log_text : str
        Complete text of an unsteady solver log.
    unjudged : list of int, optional
        When given, the tolerant mode described above: the number of
        every block whose residual pages cannot be read is appended to
        this list instead of raising.

    Returns
    -------
    FrozenSolve or None
        The first frozen step and the count of frozen steps, or None
        when no stretch of two consecutive steps is frozen.

    Raises
    ------
    IncompleteOutputError
        If a block has no readable residual page and ``unjudged`` is
        None (a ``ValueError``).
    MalformedOutputError
        If a residual page of a block cannot be parsed and ``unjudged``
        is None (a ``ValueError``).
    """
    clean = log_text.replace("\x00", "")
    markers = list(
        re.finditer(r"Solving unsteady time-step iteration \(\s*(\d+)\s*/\s*(\d+)\s*\)", clean)
    )
    log_has_pages = RESIDUAL_PAGE.search(clean) is not None
    # Compare the printed mantissa: a tiny nonzero value must not underflow to
    # zero, and neither an overflow field nor NaN is evidence of a freeze.
    zero = re.compile(r"[+-]?(?:0+(?:\.0*)?|\.0+)(?:[EeDd][+-]?\d+)?\Z")
    first: int | None = None
    count = 0
    streak = 0
    previous: int | None = None
    #: Whether the block IMMEDIATELY BEFORE this one could not be read, and
    #: which step it was. A log can hold two attempts, and a measured one does,
    #: so "the last unread step" is not "the previous block": comparing against
    #: the former marked a frozen step of the second attempt unread because a
    #: step of the same number in the first could not be read .
    unread: int | None = None
    #: Whether ANY block of this log carried a residual page. A marker at the
    #: end with no page is a CUT only in a log that prints pages: a log whose
    #: markers never carry one (progress lines only, or a steady history with
    #: unsteady markers appended, the collect fixture) was not cut, it
    #: never had tables, and calling it cut failed the assessor (the suite arm
    #: after the post-log merge).
    pages_seen = False
    for index, marker in enumerate(markers):
        step = int(marker[1])
        end = markers[index + 1].start() if index + 1 < len(markers) else len(clean)
        block = clean[marker.end() : end]
        try:
            pages = RESIDUAL_PAGE.split(block)[1:]
            if pages:
                pages_seen = True
            if not pages:
                if index + 1 < len(markers) and int(markers[index + 1][1]) == step:
                    # Per-step export actions repeat the marker before its table.
                    continue
                if index + 1 == len(markers) and pages_seen:
                    raise IncompleteOutputError(
                        f"time step {step} ends before its Iteration anchor; recollect the log"
                    )
                if index + 1 < len(markers) and log_has_pages:
                    raise IncompleteOutputError(
                        f"time step {step} holds no Iteration page while the log prints them "
                        "for other steps, so the step cannot be judged; recollect the log"
                    )
            rows = [row for page in pages for row in _page_rows(page)]
            for row in rows:
                if len(row) < 3 or not all(_residual_cell_is_readable(cell) for cell in row[1:3]):
                    raise MalformedOutputError(
                        f"time step {step} prints the residual row {row!r}, whose velocity and "
                        "pressure cells are not numbers; the step cannot be judged"
                    )
        except (IncompleteOutputError, MalformedOutputError):
            if unjudged is None:
                raise
            # A frozen step beside an unreadable step can be an unjudgeable freeze.
            # Check predecessor and successor only when their printed step numbers
            # are consecutive; a gap cannot establish the required pair.
            if streak >= 1 and previous == step - 1:
                unjudged.append(previous)
            unjudged.append(step)
            unread = step
            streak = 0
            previous = step
            continue
        frozen = (
            bool(rows)
            and len(rows[-1]) >= 3
            and all(len(row) >= 3 and zero.fullmatch(row[1]) for row in rows[1:])
            and zero.fullmatch(rows[-1][1]) is not None
            and zero.fullmatch(rows[-1][2]) is not None
        )
        if frozen and unread == step - 1 and unjudged is not None:
            # The block before this one could not be read and this one froze:
            # the pair may be a freeze, and the streak alone cannot say so.
            unjudged.append(step)
        unread = None  # this block WAS read, whatever it says
        streak = (streak + 1 if previous == step - 1 else 1) if frozen else 0
        if streak == 2:
            if first is None:
                first = step - 1
            count += 2
        elif streak > 2:
            count += 1
        previous = step
    return None if first is None else FrozenSolve(first_step=first, count=count)


@dataclass(frozen=True)
class LogTimes:
    """The times and the step count a solver log prints.

    Every field is None where the log does not print it, so an absent line
    is never reported as a zero.

    Attributes
    ----------
    solver_run_time_s : float or None
        The LAST ``Solver run time`` or ``Unsteady solver run time`` line, in
        seconds (the log prints minutes). The last, because a steady row that
        solves several angles in one job prints one line per angle and its
        point's own solve is the latest.
    solver_initialization_s : float or None
        The last ``Solver initialized in`` line, in seconds.
    time_steps : int or None
        The total of the ``Solving unsteady time-step iteration (i/N)`` lines,
        N; None on a steady log.
    solver_mode : str or None
        ``steady`` or ``unsteady`` from time-step or run-time lines; None when
        neither is printed. Time-step evidence takes precedence.
    """

    solver_run_time_s: float | None = None
    solver_initialization_s: float | None = None
    time_steps: int | None = None
    solver_mode: str | None = None


_RUN_TIME_LINE = re.compile(r"^\s*(Unsteady solver|Solver) run time:\s*(\S+?)\s*minutes", re.M)
_INITIALIZED_LINE = re.compile(r"^\s*Solver initialized in\s*(\S+?)\s*seconds", re.M)


def _latest_seconds(token: str | None, scale: float) -> float | None:
    """Return the latest timing line's value, or None when that line holds no number.

    An earlier run's value is never returned in place of a latest line that
    cannot be read.
    """
    if token is None:
        return None
    try:
        return parse_number(token) * scale
    except MalformedOutputError:
        return None


_TIME_STEP_LINE = re.compile(r"Solving unsteady time-step iteration \(\s*\d+\s*/\s*(\d+)\s*\)")


def parse_log_times(text: str) -> LogTimes:
    """Read the solver run time, the initialization time and the time steps off a log.

    Parameters
    ----------
    text : str
        Complete log text, an EXPORT_LOG output or a scheduler's job output
        carrying the same lines.

    Returns
    -------
    LogTimes
        Each field None where the log prints no such line.
    """
    clean = text.replace("\x00", "")
    run_times = _RUN_TIME_LINE.findall(clean)
    initialized = _INITIALIZED_LINE.findall(clean)
    steps = _TIME_STEP_LINE.findall(clean)
    return LogTimes(
        solver_run_time_s=_latest_seconds(run_times[-1][1] if run_times else None, 60.0),
        solver_initialization_s=_latest_seconds(initialized[-1] if initialized else None, 1.0),
        time_steps=int(steps[-1]) if steps else None,
        solver_mode=(
            "unsteady"
            if steps or (run_times and run_times[-1][0] == "Unsteady solver")
            else "steady"
            if run_times
            else None
        ),
    )


#: The line the wake-edge import writes when it marks something (RPT-061):
#: ``16 trailing edges imported for boundary Wing``. Detection writes
#: ``... marked on surface ...`` instead, which is not an import and is not
#: matched.
_IMPORTED_TRAILING_EDGES_LINE = re.compile(
    r"^\s*(\d+) trailing edges? imported for boundary (.+?)\s*$", re.M
)


def lifting_log_warnings(log_text: str) -> list[str]:
    """Name explicitly zero trailing-edge or growing-wake counts in a lifting log.

    Parameters
    ----------
    log_text : str
        Native solver log text to inspect.

    Returns
    -------
    list[str]
        Diagnostic warning strings for the lifting-surface log findings.
    """
    messages = []
    if re.search(r"(?im)^\s*0 trailing edges? (?:found|marked|created)\b", log_text):
        messages.append(
            "the solver reports zero trailing edges; check the lifting geometry and detection"
        )
    if re.search(r"(?im)\b0 (?:wake )?strands? marked for growth\b", log_text):
        messages.append("the solver reports zero wake strands; check the lifting wake")
    return messages


def imported_trailing_edges(log_text: str) -> dict[str, int]:
    """Read how many trailing edges the solver says it imported, per boundary.

    The wake-edge import logs ``N trailing edges imported for boundary
    <name>`` when it marks something and logs nothing when a file marks
    nothing (RPT-061), so this count is the one statement the solver makes
    about a file of points. Several import lines for one boundary are
    summed.

    Parameters
    ----------
    log_text : str
        Complete log text, an EXPORT_LOG output or the log the solver left.
        The NUL bytes a hidden-mode log carries between lines are removed.

    Returns
    -------
    dict of str to int
        Edges imported per boundary name, in the order first logged. Empty
        when the log carries no import line, which is what a file that
        matched no edge leaves.

    Examples
    --------
    >>> from pyflightstream.results import imported_trailing_edges
    >>> imported_trailing_edges("16 trailing edges imported for boundary Wing")
    {'Wing': 16}
    """
    clean = log_text.replace("\x00", "")
    counts: dict[str, int] = {}
    for count, boundary in _IMPORTED_TRAILING_EDGES_LINE.findall(clean):
        counts[boundary] = counts.get(boundary, 0) + int(count)
    return counts


#: The line the solver prints when one instance clears a solution to run the
#: next point (FR-368). On 26.124 build 8172026, printed by REMOVE_INITIALIZATION
#: and by NEW_SIMULATION, so in the cumulative log of a job it opens every
#: point but the first.
RESTART_MARKER = "Solution cleared. Initialization removed."

#: The first line of the solver's initialisation echo. A point's own run
#: starts here; what a polar's first segment prints before it (the OPEN
#: echo, the wake-edge import lines) is the polar's preamble.
_INITIALIZATION_ECHO = "Following geometry is being initialized"


@dataclass(frozen=True)
class LogSegment:
    """One point's run inside the cumulative log of a job (FR-368).

    Attributes
    ----------
    index : int
        The segment's position in the log, from 0; a job's point of order
        ``i`` is segment ``i - 1``.
    first_line : int
        The segment's first line, a 0-based index into the log's lines.
    last_line : int
        The segment's last line, inclusive. The marker lines belong to no
        segment.
    complete : bool
        True when a later marker follows the segment. The last segment of a
        log is never complete here: whether its point finished is known only
        to a caller that knows the job ended.
    """

    index: int
    first_line: int
    last_line: int
    complete: bool


def _initialization_reset(lines: list[str], at: int) -> bool:
    """Recognize the reset between two initializations of the same model.

    On 26.124 a second INITIALIZE_SOLVER prints the same reset as a new
    point. Its preceding nonblank line is the first initialization's solver
    mode, and its next is the symmetry echo of the second initialization.
    A new model's opening echo, or a reset after a solve, is a point boundary.
    Keep this setup reset inside the point so its opening evidence and solve
    reach the same LoadsAssessor as a point run alone (FR-407).
    The splitter carries no build identity, so it uses the newest listed
    build's vocabulary, also the fallback for a build without an entry.
    """
    before = next((lines[i] for i in range(at - 1, -1, -1) if lines[i].strip()), "")
    after = next((lines[i] for i in range(at + 1, len(lines)) if lines[i].strip()), "")
    newest = max(versions.SETUP_RESET_LOG_PREFIXES, key=versions.resolve)
    mode, symmetry = versions.SETUP_RESET_LOG_PREFIXES[newest]
    return before.strip().startswith(mode) and after.strip().startswith(symmetry)


def split_job_log(text: str) -> list[LogSegment]:
    r"""Cut a job log at point resets, retaining resets between initializations.

    Parameters
    ----------
    text : str
        The cumulative log, a point's own ``EXPORT_LOG`` copy inside a job or
        the job's native log. NUL bytes are ignored where the marker is
        looked for.

    Returns
    -------
    list of LogSegment
        One segment per point, in the order the job ran them; empty for an
        empty text. Line indexes count the lines of ``text.splitlines()``.

    Examples
    --------
    >>> setup = f"Solver mode: Unsteady\n{RESTART_MARKER}\nSymmetry is disabled."
    >>> len(split_job_log(setup))
    1
    >>> len(split_job_log(f"{setup}\nsolve ended\n{RESTART_MARKER}\nnext point"))
    2
    """
    lines = text.splitlines()
    clean = [line.replace("\x00", "") for line in lines]
    if not lines:
        return []
    markers = [
        at
        for at, line in enumerate(clean)
        if RESTART_MARKER in line and not _initialization_reset(clean, at)
    ]
    starts = [0, *(at + 1 for at in markers)]
    ends = [*(at - 1 for at in markers), len(lines) - 1]
    return [
        LogSegment(index=index, first_line=start, last_line=end, complete=index < len(markers))
        for index, (start, end) in enumerate(zip(starts, ends, strict=True))
    ]


def point_log_text(text: str, segment: LogSegment, *, polar_start: LogSegment) -> str:
    """Return one point's own log: its polar's preamble, then its own segment.

    A point after the first of its polar runs in an instance that opened the
    model once, so its segment carries neither the ``OPEN`` echo nor the
    wake-edge import lines; they are in the polar's first segment, before its
    initialisation echo, and they are put in front of the point's segment so
    its log reads as the log of the point run alone (the trailing-edge import
    count is judged per point). The process banner with the build is printed
    once per job, so a point of a later polar does not
    carry it; nothing of the package reads it off a log.

    Parameters
    ----------
    text : str
        The cumulative log :func:`split_job_log` cut.
    segment : LogSegment
        The point's segment.
    polar_start : LogSegment
        The segment of the first point of the same polar; the point's own
        segment when it is that first point, which then takes no preamble.

    Returns
    -------
    str
        The point's log, every line ending in a line feed.
    """
    lines = text.splitlines()
    own = lines[segment.first_line : segment.last_line + 1]
    preamble: list[str] = []
    if polar_start.index != segment.index:
        head = lines[polar_start.first_line : polar_start.last_line + 1]
        cut = next((at for at, line in enumerate(head) if _INITIALIZATION_ECHO in line), 0)
        preamble = head[:cut]
    return "".join(f"{line}\n" for line in [*preamble, *own])
