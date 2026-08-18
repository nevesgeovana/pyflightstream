"""Where an evidence report goes, and the refusal to overwrite one.

Pipeline role: the one home of the report-naming rule the three evidence
writers share. ``qa.compat``, ``qa.physics`` and ``qa.drift`` all name
their output ``<PREFIX>-<digits>_<date>[_label]`` and all refuse to
overwrite one, because a report states what a solver did on a day and
evidence supersedes evidence only through a new, dated report.

WHY IT IS A MODULE AND NOT THREE COPIES, which is the correction of
2026-08-17. The refusal was right in all three and its POSITION was wrong
in all three: it fired at WRITE time, after the run. On 26.123 that cost
a full probe campaign, 111 commands over five minutes of licensed solver,
discarded on a collision knowable from the command line before anything
started. The repair was made for the probe path alone and the other two
kept the defect, so a physics or drift run could still spend the whole
Tier 3 matrix and then die on an uncaught ``FileExistsError``.

Three copies of one rule is why a repair could reach one of them. There
is now one rule and each writer names its own prefix.

The date is NOT defaulted here, deliberately. The caller resolves it once
and passes the same value to this function and into the document body,
so the stem and the body cannot disagree; a second default here is
exactly the shape that wrote ``date: null`` under a dated file name
(``INC-20260817-2210-pyflightstream``). ``tests/test_qa_compat.py``
guards that pairing on both sides.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["refuse_existing_report", "report_paths"]


def report_paths(
    prefix: str,
    key: str,
    out_dir: str | Path,
    *,
    date: str,
    label: str | None = None,
) -> tuple[Path, Path]:
    """Return where one evidence report WOULD be written.

    Parameters
    ----------
    prefix : str
        Series prefix, ``"CMP"``, ``"PHY"`` or ``"DRF"``.
    key : str
        The build part of the stem, already joined and stripped of dots:
        ``"26123"`` for a single build, ``"26122-26123"`` for a
        comparison.
    out_dir : str or Path
        Target directory. NOT created here: asking where a report would
        go must not have the side effect of making a directory, because
        the whole point of asking is to decide whether to run at all.
    date : str
        ISO date, resolved by the caller. Required rather than
        defaulted; see this module's docstring.
    label : str, optional
        Stem suffix distinguishing several reports on one day.

    Returns
    -------
    tuple of Path
        The YAML path and the Markdown path, in that order. Neither is
        created.
    """
    stem = f"{prefix}-{key}_{date}"
    if label:
        stem += f"_{label}"
    directory = Path(out_dir)
    return directory / f"{stem}.yaml", directory / f"{stem}.md"


def refuse_existing_report(*paths: Path) -> None:
    """Refuse to overwrite a committed report, wherever it is asked.

    Evidence supersedes evidence only through a new, dated report, and a
    caller that has not yet spent a licensed seat should be told so
    BEFORE it does. Call it with the output of :func:`report_paths`.

    Raises
    ------
    FileExistsError
        If any named path exists. The BUILTIN, deliberately, and not a
        catalogued type: this preserves what the three writers have
        always raised, so ``except FileExistsError`` around a write still
        catches it. It is named in ``tests/test_exceptions_catalog.py``'s
        ratchet rather than left unobserved.

    Notes
    -----
    The message names ``label`` and the directory, and deliberately does
    NOT name a date: the two escapes a caller actually has are a
    different label and a different output directory. It used to say
    "pick another date", which no ``pyfs-qa`` user can do because none of
    those CLIs has a date flag, and each CLI re-words this in its own
    flags.
    """
    for path in paths:
        if path.exists():
            raise FileExistsError(
                f"{path} already exists; evidence reports are never overwritten. "
                "Pass a different label, or write to another directory. Removing a "
                "committed report is deliberate and is not the way past this."
            )
