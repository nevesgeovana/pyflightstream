"""The verdicts on a run read off the solver's own log, whatever the assessor said.

G02 of 0.27.0 (RPT-061, RPT-065): a run that imported trailing edges is held to
the count the solver logged. G06: a run whose solver could not use the radial
thrust profile of its actuator disc is held to the line the solver logged about
it. Private to the run layer: the point path and the collect path both apply
them, so they live beneath both rather than in the package module one of them
would otherwise reach into. The rule that finds a point's solver log among its
collected outputs lives here for the same reason: the package's assessor finds
its log by it, and both verdicts read the log it finds whichever assessor
judged the point.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from pathlib import Path, PureWindowsPath

from pyflightstream.cases import EXPORT_KINDS
from pyflightstream.results import (
    IncompleteOutputError,
    imported_trailing_edges,
    parse_residual_history,
)
from pyflightstream.workspace import RunStatus

__all__ = [
    "ACTUATOR_PROFILE_REFUSALS",
    "actuator_profile_refusals",
    "actuator_profile_verdict",
    "collected_log_texts",
    "collected_solver_log",
    "reads_as_residual_history",
    "script_log_names",
    "wake_edge_import_verdict",
    "with_wake_edge_verdict",
]

#: The four sentences the solver executable carries for the radial thrust
#: profile an actuator disc names (``SET_PROP_ACTUATOR_PROFILE``) when it cannot
#: use the file, each followed on its own line by the file's path. 26.124 logged
#: the second for a profile it could not read, put up a dialog, and ran on to the
#: end with the disc acting on a loading that was not the file's (G06).
ACTUATOR_PROFILE_REFUSALS: tuple[str, ...] = (
    "Failed to find custom radial thrust profile file:",
    "Failed to read custom radial thrust profile file:",
    "No data found in custom radial thrust profile file:",
    "Failed to load custom radial thrust profile file:",
)

_ACTUATOR_PROFILE_REFUSAL = re.compile(
    "(?:"
    + "|".join(re.escape(sentence) for sentence in ACTUATOR_PROFILE_REFUSALS)
    + r")[ \t]*(?P<path>[^\r\n]*)"
)


def actuator_profile_refusals(log_text: str | None) -> list[tuple[str, str]]:
    """Return each line in which the solver says it could not use a disc's profile file.

    Parameters
    ----------
    log_text : str or None
        A solver log, an EXPORT_LOG output, the log the solver left or a
        scheduler's job output. The NUL bytes a hidden-mode log carries are
        removed first.

    Returns
    -------
    list of (str, str)
        The line as logged, from the sentence to the end of the line, and the
        path it names (empty when it names none), once each and in the order
        logged. Empty for no log and for a log carrying none of the four
        sentences.
    """
    if not log_text:
        return []
    found: list[tuple[str, str]] = []
    for match in _ACTUATOR_PROFILE_REFUSAL.finditer(log_text.replace("\x00", "")):
        entry = (match.group(0).strip(), match.group("path").strip())
        if entry not in found:
            found.append(entry)
    return found


def actuator_profile_verdict(*log_texts: str | None) -> tuple[RunStatus, str] | None:
    """Judge a run by what the solver logged about its actuator disc's profile file.

    G06. When the solver cannot use the radial thrust profile a disc names, it
    logs one of the four :data:`ACTUATOR_PROFILE_REFUSALS` and the run goes on to
    the end with the disc acting on a loading that is not the file's. The loads
    converge and nothing else in the outputs says so, so the line decides: a run
    whose log carries one is FAILED_SCRIPT, the status the trailing-edge count
    gives a script whose file the solver did not take as written.

    Parameters
    ----------
    *log_texts : str or None
        Every log of the run there is to read: the collected log, every
        collected output named as a log (:func:`collected_log_texts`), and the
        one the solver left or the job's. None and empty entries are skipped,
        and a line logged in two of them is named once.

    Returns
    -------
    tuple of (RunStatus, str) or None
        None when no log carries one of the lines; else FAILED_SCRIPT with a
        reason that quotes each line, names the file and says the disc did not
        use it.
    """
    refusals: list[tuple[str, str]] = []
    for text in log_texts:
        for refusal in actuator_profile_refusals(text):
            if refusal not in refusals:
                refusals.append(refusal)
    if not refusals:
        return None
    # QUOTED AS LOGGED, never by repr: a repr doubles every backslash of a
    # Windows path, and the line would then not be the one the log carries.
    reasons = [
        f"the solver logged '{line}': it could not use the radial thrust profile file "
        f"{path or '(no path logged)'}, so the actuator disc did not use the file"
        for line, path in refusals
    ]
    return (
        RunStatus.FAILED_SCRIPT,
        "; ".join(reasons) + ". The run went on to the end with the disc acting on a loading "
        "that is not the file's, so these loads are not the row's; nothing else in the "
        "outputs says so. Check the file the row's PROFILE names and run the point again",
    )


def reads_as_residual_history(path: Path) -> bool:
    """Whether one collected file parses as a solver residual history.

    The identification is by CONTENT and never by name, the same rule
    the loads table is found under: a swept case names its outputs per
    point, so no literal could name them all. False on anything that
    does not parse, including a file this process cannot read, because
    the caller's fallback is the judgment that existed before and never
    an error about a file nobody asked it to read.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    try:
        return bool(parse_residual_history(text))
    except (IncompleteOutputError, ValueError):
        return False


def collected_solver_log(folder: Path, collected: Sequence[str], named: str | None) -> str | None:
    """Return the text of the solver log among a point's collected outputs, or None.

    WHICHEVER ASSESSOR JUDGED THE POINT. The package's own assessor names the
    file it read (``log_file_used``), and that file is read. An assessor a
    caller passes answers with a status and need not name anything, so the log
    is then found as the package's own assessor finds it: the one collected
    output that parses as a residual history. Until this, a caller's assessor
    left a collected log unread, and a point whose log carried every imported
    edge was recorded FAILED_INCOMPLETE_OUTPUT with the remedy to export the
    log it had exported (the qa lens, 2026-09-24).

    Parameters
    ----------
    folder : Path
        The simulation folder the collected entries are relative to.
    collected : sequence of str
        The point's collected outputs.
    named : str or None
        The file name the assessor says it read, when it says one.

    Returns
    -------
    str or None
        The log's text; None when no collected output is the log, or when
        several parse as one, since which of them is this point's would be a
        guess.
    """
    paths = [folder / entry for entry in collected]
    if named:
        for path in paths:
            if path.name == named and path.is_file():
                return path.read_text(encoding="utf-8", errors="replace")
    candidates = [path for path in paths if path.is_file() and reads_as_residual_history(path)]
    if len(candidates) == 1:
        return candidates[0].read_text(encoding="utf-8", errors="replace")
    return None


#: The suffix every solver log the package names carries (the ``log`` kind of
#: EXPORT_KINDS): the name EXPORT_LOG writes, the name `collect` copies a
#: scheduler's log to, and the name a local run writes the printed output under.
_LOG_SUFFIX = next(suffix for kind, suffix, _, _ in EXPORT_KINDS if kind == "log")

#: The commands that write the solver log to a file: the verb of the ``log``
#: kind of EXPORT_KINDS, which is where the package states which command writes
#: which export (EXPORT_LOG; the command database marks no other as writing it).
_LOG_VERBS = frozenset(verb for kind, _, verb, _ in EXPORT_KINDS if kind == "log")


def script_log_names(script_text: str | None) -> list[str]:
    """Return the name of every file a script tells the solver to write its log to.

    EXPORT_LOG is ``param_lines``: the command alone on its line and the file on
    the next. The name is the file's own, without its folder, since that is how
    a collected output is matched to it: the script names the file where the
    job runs, and the collected entry names it where it was filed. Either
    separator is read, so a script written for a cluster is read here too.

    Parameters
    ----------
    script_text : str or None
        The script as rendered, or as it stands on disk.

    Returns
    -------
    list of str
        Each name once, in the order the script writes them; empty for no script.
    """
    if not script_text:
        return []
    lines = script_text.splitlines()
    names: list[str] = []
    for line, following in zip(lines, lines[1:], strict=False):
        if line.strip() in _LOG_VERBS and following.strip():
            name = PureWindowsPath(following.strip()).name
            if name not in names:
                names.append(name)
    return names


def collected_log_texts(
    folder: Path, collected: Sequence[str], declared: Collection[str] = ()
) -> list[str]:
    """Return the text of every collected output that is a solver log.

    FOR THE FOUR LINES OF G06, which decide wherever they are logged. The log
    :func:`collected_solver_log` finds is ONE, found by the name an assessor
    gives or by reading as a residual history, and a log carrying no residual
    table is neither: a scheduler's log of the job, copied to the row's declared
    log, or an export the solver cut short. Its refusal line was not read, and a
    point whose loads converged was recorded CONVERGED on a disc that did not use
    its file. So the refusal is also read in every output named as a log, which
    is every log this package declares, whatever its content.

    AND EVERY FILE THE POINT WAS TOLD TO WRITE ITS LOG TO, WHATEVER ITS NAME.
    Read by the suffix alone, a case built in Python or a LEGACY row whose
    LOG_OUTPUT names ``FlightStreamLog.txt``, or whose script's EXPORT_LOG
    writes ``log_<point>.txt``, carried its refusal line unread, and the point
    was recorded CONVERGED where the same bytes under ``run_log.txt`` were
    FAILED_SCRIPT. Nothing else is read: an export can be large, and what is a
    log is what the script and the row declared.

    Parameters
    ----------
    folder : Path
        The simulation folder the collected entries are relative to.
    collected : sequence of str
        The point's collected outputs.
    declared : collection of str, optional
        The names the point's script writes its log to
        (:func:`script_log_names`) and the output its LOG_OUTPUT names; a
        folder a name carries is ignored.

    Returns
    -------
    list of str
        The text of each collected output whose name ends in ``_log.txt`` or is
        one of ``declared``, in the order collected; empty when none is collected.
    """
    # A name equal to a declared one but for case is the same file on a
    # case-insensitive file system, so the names are compared casefolded.
    named = {PureWindowsPath(str(name)).name.casefold() for name in declared}
    return [
        path.read_text(encoding="utf-8", errors="replace")
        for path in (folder / entry for entry in collected)
        if (path.name.endswith(_LOG_SUFFIX) or path.name.casefold() in named) and path.is_file()
    ]


def wake_edge_import_verdict(
    expected: int | None, log_text: str | None
) -> tuple[RunStatus, str] | None:
    """Judge a run that imported trailing edges by the count the solver logged.

    G02 (RPT-061, RPT-065). The import marks nothing and says nothing for a
    point that matches no mesh edge, and initialisation does not add what
    it missed, so the solver's ``N trailing edges imported`` line is the one
    statement that tells a file that marked from one that did not.

    Parameters
    ----------
    expected : int or None
        The points the script wrote (``Script.wake_edge_points``); None
        for a script that imports nothing, which is never judged here, so a
        continuation that opens a saved state is not held to a count.
    log_text : str or None
        The run's solver log.

    Returns
    -------
    tuple of (RunStatus, str) or None
        None when there is nothing to object to; FAILED_INCOMPLETE_OUTPUT
        when no log was read; FAILED_SCRIPT when the logged count differs
        from the points written. Each with its reason.
    """
    if expected is None:
        return None
    if log_text is None:
        return (
            RunStatus.FAILED_INCOMPLETE_OUTPUT,
            f"the script imported {expected} trailing-edge points and no solver log was "
            "read, so whether the file marked anything cannot be told: a file whose "
            "points match no edge marks nothing and says nothing. Export the solver log "
            "among the row's outputs",
        )
    counts = imported_trailing_edges(log_text)
    logged = sum(counts.values())
    if logged == expected:
        return None
    per_boundary = ", ".join(f"{count} for {name}" for name, count in counts.items()) or "none"
    return (
        RunStatus.FAILED_SCRIPT,
        f"the script wrote {expected} trailing-edge points and the solver logged "
        f"{logged} imported (per boundary: {per_boundary}); a point matching no mesh edge "
        "is dropped in silence, so this run's wake is not the one declared",
    )


def with_wake_edge_verdict(
    status: RunStatus, error: str | None, verdict: tuple[RunStatus, str] | None
) -> tuple[RunStatus, str | None]:
    """Apply a verdict read off the log over a status that is not already a failure.

    The trailing-edge count's (G02) and the actuator profile's (G06) alike.
    """
    if verdict is None or str(status).startswith("FAILED"):
        return status, error
    return verdict[0], "; ".join(part for part in (error, verdict[1]) if part)
