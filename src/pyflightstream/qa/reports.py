"""Where an evidence report goes, and the refusal to overwrite one.

Pipeline role: the one home of the report-naming rule the three evidence
writers share. ``qa.compat``, ``qa.physics`` and ``qa.drift`` all name
their output ``<SERIES>-<digits>_<date>[_label]`` and all refuse to
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

Three copies of one rule is why a repair could reach one of them.

THE VERSION KEY IS DERIVED HERE TOO, which is the correction of 2026-08-18
and is the half the first version left behind. The template lived here
and the KEY did not, so the dot-stripping and the two-build join were
each written twice: once in a writer to produce the name, once in the CLI
to predict it. Two independent expressions agreeing today is not the same
as one rule, and the day a series changes its key the pre-flight silently
asks about a stem nobody writes, with every guard still green. That is
the original defect, one field over: a licensed seat spent and then
discarded. ``tests/test_qa_cli.py`` now asserts each writer's own output
path against the helper the CLI asks, rather than against a literal.

The date is NOT defaulted here, deliberately. The caller resolves it once
and passes the same value to this function and into the document body,
so the stem and the body cannot disagree; a second default here is
exactly the shape that wrote ``date: null`` under a dated file name
(``INC-20260817-2210-pyflightstream``). ``tests/test_qa_compat.py``
guards that pairing on both sides.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from pathlib import Path

from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.versions import resolve

__all__ = ["refuse_existing_report", "report_paths", "resolve_report_date"]

#: The report series this repository writes. `reports/README.md` is the
#: home of the taxonomy; this is the machine-readable half of it, and a
#: series outside it is refused rather than pasted into a file name.
#: `RPT-` and `TRI-` are deliberately absent: both are narrative and
#: neither is written by any code path.
_SERIES = frozenset({"CMP", "PHY", "DRF"})


def resolve_report_date(date: str | None = None) -> str:
    """Return the ISO date a report is stamped with, defaulting to today.

    Parameters
    ----------
    date : str, optional
        An explicit ISO date. Returned unchanged when given, so this is
        safe to call on a value that may already be resolved.

    Returns
    -------
    str
        The ISO date, ``YYYY-MM-DD``.

    Notes
    -----
    ONE HOME FOR THE DEFAULT, which is the correction of 2026-08-18 and
    is the same repair as the build key beside it. ``date or
    datetime.date.today().isoformat()`` was written TEN times: once in
    each of the three series helpers, once in each of their three
    writers, once in each of the three ``pyfs-qa`` subcommands, and once
    in ``update_reference``. A rule written ten times is a rule that can
    drift in nine places without anyone noticing.

    The first version of this repair reached six of the ten and claimed
    all of them, excusing the CLI with "``pyfs-qa`` is not exposed". That
    excused nothing: whether a command line offers a date flag has
    nothing to do with which expression computes today, and the three
    subcommands went on spelling it themselves. All ten call this now.

    WHAT IS STILL NOT CLOSED, stated because the sentence above used to
    overclaim. A caller who asks a helper whether a report exists, spends
    a licensed seat, and then calls a writer resolves today TWICE across
    that window, and across midnight the two disagree. One home makes the
    two calls agree on the RULE; it cannot make them agree on the ANSWER.
    Closing that needs the writer to accept what the pre-flight already
    computed, which is registered in
    ``PLN-20260818-0300-the-preflight-answer-does-not-reach-the-writer``.
    ``pyfs-qa`` itself is not exposed: each subcommand resolves once and
    passes the value to both, which ``tests/test_qa_cli.py`` pins by
    replacing this function in the CLI's namespace.
    """
    if date is None:
        return datetime.date.today().isoformat()
    return _validated_date(date)


def _validated_date(date: str) -> str:
    """Return ``date`` unchanged, or refuse it as a report stem.

    SEPARATE FROM :func:`resolve_report_date` because the two callers
    need different halves. The resolver DEFAULTS and validates; the
    primitive below must validate WITHOUT defaulting, since a `date=None`
    reaching it is a caller error rather than a request for today, and
    the module's whole reason for requiring the argument is that a second
    default is what wrote ``date: null`` under a dated file name.

    The first version of this validation lived only in the resolver, one
    layer ABOVE the site it protects: `report_paths` is exported and its
    own examples call it directly, so
    ``report_paths(d, series="PHY", versions=["26.123"], date="17/08/2026")``
    returned ``d/PHY-26123_17/08/2026.yaml``, a stem carrying path
    separators. The pre-flight then tested a path under a directory that
    does not exist, answered "no collision", and the licensed run
    proceeded to a write that fails on a missing parent.

    THE ROUND TRIP IS THE TEST, not `fromisoformat` alone. On Python 3.11
    and later that function also accepts ``20260817`` and ``2026-W33-1``,
    neither of which carries a separator, so nothing would fail until a
    committed stem met the tier-1 walk in ``tests/test_command_db.py``,
    which is after the seat is spent. Comparing the parsed date's own
    ``isoformat()`` against the input admits exactly ``YYYY-MM-DD``, which
    is what the message promises.
    """
    try:
        parsed = datetime.date.fromisoformat(date)
    except (ValueError, TypeError) as error:
        raise QaEvidenceError(
            f"a report date is written as YYYY-MM-DD and this one is {date!r} "
            f"({error}). It goes straight into the report's file name, so a value "
            "this function cannot parse becomes a stem no reader can find and, if "
            "it carries a separator, a path under a directory that does not exist."
        ) from None
    if parsed.isoformat() != date:
        raise QaEvidenceError(
            f"a report date is written as YYYY-MM-DD and this one is {date!r}, "
            f"which parses as {parsed.isoformat()} but is not spelled that way. "
            "The stem carries the string, not the date, so two runs on one day "
            "would write two reports nothing can tell apart."
        )
    return date


def _canonical(version: object) -> str:
    """Return one version's canonical identifier with its dots stripped.

    Accepts whatever the sibling entry points accept, a string or an
    :class:`~pyflightstream.versions.FsVersion`, and puts both through
    the registry. An unregistered identifier or an ambiguous vendor alias
    raises from :func:`~pyflightstream.versions.resolve`, which is the
    right answer here: both are decidable with no I/O, and this function
    is called from the pre-flight that exists to refuse before a licensed
    seat is spent.
    """
    return resolve(str(version)).canonical.replace(".", "")


def report_paths(
    out_dir: str | Path,
    *,
    series: str,
    versions: Sequence[str],
    date: str,
    label: str | None = None,
) -> tuple[Path, Path]:
    """Return where one evidence report WOULD be written.

    Parameters
    ----------
    out_dir : str or Path
        Target directory. NOT created here: asking where a report would
        go must not have the side effect of making a directory, because
        the whole point of asking is to decide whether to run at all.
    series : str, keyword-only
        Report series, ``"CMP"``, ``"PHY"`` or ``"DRF"``. The word is
        the one ``reports/README.md`` uses for the same idea.
    versions : sequence of str, keyword-only
        The canonical version identifiers the report is about, in the
        order the series states them: one for a single-version report,
        two for a comparison. The dots are stripped and the identifiers
        joined here rather than by the caller, so the writer and the
        pre-flight ask one question rather than two that happen to
        agree.

        A LIST, NEVER A BARE STRING, and the refusal below is why the
        distinction is worth a paragraph. ``versions="26.123"`` type
        checks against ``Sequence[str]``, is not empty, and iterates its
        CHARACTERS, producing the stem ``PHY-2-6--1-2-3_2026-08-18``; the
        doubled hyphen is the dot stripping to nothing.
        That is this module's own failure, one input over: a pre-flight
        asked that way is green against a name nothing will ever write,
        the licensed run proceeds, and the writer refuses at the end.
    date : str, keyword-only
        ISO date, resolved by the caller. Required rather than
        defaulted; see this module's docstring.
    label : str, optional, keyword-only
        Stem suffix distinguishing several reports on one day.

    Returns
    -------
    tuple of Path
        The YAML path and the Markdown path, in that order. Neither is
        created.

    Raises
    ------
    QaEvidenceError
        If ``versions`` is empty, or is a bare string. Both produce a
        stem no later reader can trace back to a solver: the empty
        sequence gives ``CMP-_2026-08-18`` and a string gives one
        character per version. The word BUILD is kept only for the
        vendor's build number, which is a different field. The catalogued type rather than a bare
        ``ValueError``, per FR-39, and it keeps ``ValueError`` as a base
        so an existing handler catches what it always did.

    Notes
    -----
    Everything after ``out_dir`` is keyword-only, and that is the
    adopted rule rather than a preference. ``series`` and the elements
    of ``versions`` are all strings, so a positional signature makes a
    swapped pair silent: ``report_paths("26123", "CMP", ...)`` would
    produce ``26123-CMP_2026-08-18`` and complain about nothing, and the
    failure would surface much later as a citation that does not
    resolve.

    This is the PRIMITIVE the three series helpers call. A caller with a
    run in hand wants
    :func:`pyflightstream.qa.compat.compat_report_paths`,
    :func:`pyflightstream.qa.physics.physics_report_paths` or
    :func:`pyflightstream.qa.drift.drift_report_paths` instead: each
    knows its own series letter, so asking through one of them cannot
    put the wrong letter on a stem.

    Examples
    --------
    THE PRIMITIVE, with the series named explicitly. A caller with a
    run in hand should ask its series' helper instead, and the two
    examples below exist to show what that helper does rather than to
    be copied; the first version of this block introduced them with
    the sentence "ask with the series' own helper rather than with a
    literal" and then demonstrated the literal.

    >>> from pyflightstream.qa import report_paths
    >>> yaml_path, md_path = report_paths(
    ...     "reports/physics", series="PHY", versions=["26.123"], date="2026-08-17"
    ... )
    >>> yaml_path.name
    'PHY-26123_2026-08-17.yaml'

    Two versions make a comparison stem, joined in the order given:

    >>> yaml_path, _ = report_paths(
    ...     "reports/physics",
    ...     series="DRF",
    ...     versions=["26.122", "26.123"],
    ...     date="2026-08-17",
    ...     label="full",
    ... )
    >>> yaml_path.name
    'DRF-26122-26123_2026-08-17_full.yaml'

    A bare string is refused rather than iterated:

    >>> from pyflightstream.qa import QaEvidenceError
    >>> try:
    ...     report_paths(
    ...         "reports/physics", series="PHY", versions="26.123", date="2026-08-17"
    ...     )
    ... except QaEvidenceError as refused:
    ...     print(str(refused).split(";")[0])
    versions is a sequence of version identifiers, not one string
    """
    if series not in _SERIES:
        raise QaEvidenceError(
            f"{series!r} is not a report series; this repository writes "
            f"{', '.join(sorted(_SERIES))}, and a stem carrying anything else "
            "is a name no reader can trace back to a solver. Ask the series' own "
            "helper rather than this primitive, and the letter cannot be wrong."
        )
    if isinstance(versions, str):
        raise QaEvidenceError(
            f"versions is a sequence of version identifiers, not one string; "
            f"pass ['{versions}'] rather than '{versions}'. A string is iterated "
            "character by character, so this would have produced the stem "
            f"{series}-{'-'.join(versions).replace('.', '')}_{date}, which no later "
            "reader could "
            "trace back to a solver and which the writer would never produce."
        )
    if not versions:
        raise QaEvidenceError(
            "a report names at least one version; report_paths was given none, "
            "which would produce a stem no reader can trace back to a solver. "
            "Pass the canonical identifier the run used, for example ['26.123']."
        )
    # RESOLVED, NOT TAKEN AS TYPED, which is the correction of 2026-08-18.
    # Every writer resolves its version before naming anything, and the
    # helpers did not, so a pre-flight asked with a vendor release name
    # predicted a stem the writer would never produce: `version="26.0"`
    # gave `PHY-260_<date>` against the writer's `PHY-26000_<date>`. That
    # matters because `run_physics` and `probe_version` both invite a
    # vendor name in their own Parameters blocks, so the caller doing it
    # is the caller the documentation created. Resolving here also accepts
    # an `FsVersion`, which those two entry points already take, and
    # refuses an ambiguous alias BEFORE a seat is spent rather than after.
    key = "-".join(_canonical(version) for version in versions)
    stem = f"{series}-{key}_{_validated_date(date)}"
    if label:
        stem += f"_{label}"
    directory = Path(out_dir)
    return directory / f"{stem}.yaml", directory / f"{stem}.md"


def refuse_existing_report(*paths: Path) -> None:
    """Refuse to overwrite a committed report, wherever it is asked.

    Evidence supersedes evidence only through a new, dated report, and a
    caller that has not yet spent a licensed seat should be told so
    BEFORE it does. Call it with the output of :func:`report_paths`.

    Parameters
    ----------
    *paths : Path
        Report paths to test, normally the pair returned by
        :func:`report_paths`. Nothing is created and nothing is read;
        only existence is tested.

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
    The message names the two escapes a caller actually has, a
    distinguishing label or another directory, and deliberately does NOT
    name a date: it used to say "pick another date", which no ``pyfs-qa``
    user can do because none of those CLIs has a date flag. It names
    neither as a parameter of this function, because this function has
    neither; a caller who did not come through :func:`report_paths` has
    no ``label`` to pass. Each CLI re-words the remedy in its own flags.
    """
    for path in paths:
        if path.exists():
            raise FileExistsError(
                f"{path} already exists; evidence reports are never overwritten. "
                "Write under a different stem: a distinguishing label, or another "
                "directory. Removing a committed report is deliberate and is not "
                "the way past this."
            )
