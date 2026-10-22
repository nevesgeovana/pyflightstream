"""Where an evidence report goes, and the refusal to overwrite one.

Pipeline role: the one home of the report-naming rule the three evidence
writers share. ``qa.compat``, ``qa.physics`` and ``qa.drift`` all name
their output ``<SERIES>-<digits>_<date>[_label]`` and all refuse to
overwrite one, because a report states what a solver did on a day and
evidence supersedes evidence only through a new, dated report.

Pre-flight checks and writers share the naming rule, including the version
key, so a collision can be refused before a licensed run starts. The CLI
tests compare each writer's output path with the helper's predicted path.

The caller resolves the date once and passes that value to the path helper
and document body. This keeps the file name and its recorded date aligned;
the compatibility-report tests check both representations.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.versions import resolve
from pyflightstream.workspace.naming import is_portable_name

__all__ = ["refuse_existing_report", "report_paths", "resolve_report_date"]

#: The longest label a report file name carries, in characters (X-F-1217).
_MAX_LABEL_LENGTH = 64

#: The report series this repository writes. This is the machine-readable
#: list of the taxonomy (CMP compat, PHY physics, DRF drift), and a series
#: outside it is refused rather than pasted into a file name.
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
    Series helpers, writers, CLI subcommands and reference updates share
    this default. Resolve once and pass the result to both pre-flight
    and writer: independent calls can disagree across midnight. Each
    ``pyfs-qa`` subcommand passes one resolved value to both; direct
    Python callers must likewise retain the value across the run.
    """
    if date is None:
        return datetime.date.today().isoformat()
    return _validated_date(date)


def _validated_date(date: str) -> str:
    """Validate a report-stem date without supplying a default.

    report_paths is public, so validate at this boundary as well as in the
    defaulting resolver. Require an ISO round trip to YYYY-MM-DD: Python's
    fromisoformat also accepts compact and week-date forms that are not
    valid report-stem dates. Refuse None and path-bearing date strings.
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


_PRINTED_BUILD = re.compile(r"\bbuild\s*#\s*(\d+)", re.IGNORECASE)


def public_executable_identity(
    digest: str | None, version: object, solver_identity: Sequence[str] = ()
) -> str | None:
    """Return what a committed report states for the executable a run hashed.

    A report is committed and the remote is public, so it names the
    executable by its solver build and never by its digest (NFR-31): the
    digest identifies the user's machine and stays in the run record. A run
    that recorded no digest still reads as ``None``, so "nobody measured it"
    stays distinguishable from "measured and withheld".

    Parameters
    ----------
    digest : str or None
        The run's own ``fs_exe_sha256``, or ``None`` when none was taken.
    version : str or FsVersion
        The version the run used; its registered build is stated unless
        the hashed binary printed another.
    solver_identity : sequence of str, optional
        The identity lines the hashed binary printed. A ``build #<digits>``
        among them names the binary that was hashed and wins over the
        registered build of the requested version (F-536).

    Returns
    -------
    str or None
        ``"withheld; build <build>"``, or ``None`` for an unrecorded digest.

    Raises
    ------
    UnknownVersionError
        When ``version`` is not a registered build.
    """
    if not digest:
        return None
    registered = resolve(str(version)).build or "unregistered"
    for line in solver_identity:
        printed = _PRINTED_BUILD.search(line)
        if printed:
            return f"withheld; build {printed.group(1)}"
    return f"withheld; build {registered}"


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
        Report series, ``"CMP"``, ``"PHY"`` or ``"DRF"``: compat, physics and
        drift reports.
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
        If ``label`` is not a portable file-name token, which the write
        could not create after the run. If ``versions`` is empty, or is
        a bare string. Both produce a
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
    These examples show the primitive with an explicit series. For a
    run object, prefer its series-specific helper, which supplies that
    value and delegates to this function.

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
    # Resolve versions before naming a report so pre-flight and writer use
    # the same stem. Vendor alias 26.0 resolves to 26.000; FsVersion inputs
    # are accepted too. Refuse ambiguous aliases before spending a seat.
    key = "-".join(_canonical(version) for version in versions)
    stem = f"{series}-{key}_{_validated_date(date)}"
    if label:
        # PFS-2102.015. Checked here, where the pre-flight asks, for the
        # reason the date is: a label carrying a separator or a character
        # Windows forbids passed the collision check against a path that
        # cannot exist, and the write failed after the licensed run.
        if len(label) > _MAX_LABEL_LENGTH:
            raise QaEvidenceError(
                f"the label is {len(label)} characters long and the longest a report file "
                f"name carries is {_MAX_LABEL_LENGTH}, so the write could fail on a file "
                "system with short paths after the licensed run; choose a shorter label"
            )
        if not is_portable_name(label) or any(ord(character) < 32 for character in label):
            raise QaEvidenceError(
                f"the label {label!r} is not a plain file-name token (no separators, no "
                'whitespace or control characters, none of <>:"/\\|?*), and it becomes '
                "part of the report stem; "
                "choose a label such as pilot-2"
            )
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
        catches it. It is named in ``tests/tier1_offline/test_exceptions_catalog.py``'s
        ratchet rather than left unobserved.

    Notes
    -----
    The message suggests a distinguishing label or another directory.
    These describe ways to choose a new stem, not parameters of this
    function. Each CLI expresses the remedy using its own flags; the
    QA CLIs do not expose a date flag.
    """
    for path in paths:
        if path.exists():
            raise FileExistsError(
                f"{path} already exists; evidence reports are never overwritten. "
                "Write under a different stem: a distinguishing label, or another "
                "directory. Removing a committed report is deliberate and is not "
                "the way past this."
            )


def load_yaml(path: str | Path, *, consequence: str = "") -> Any:
    """Read and parse one YAML evidence file, refusing in the catalogued type.

    PFS-2102.010. The compat path fixed this as a class and the physics
    path kept the bare read, so a mistyped report path or an unparsable
    reference reached ``pyfs-qa update-reference`` as a traceback: a
    ``FileNotFoundError``, or a ``yaml.YAMLError``, which is not a
    ``ValueError``. Every evidence reader of ``pyflightstream.qa`` reads
    through here.

    Parameters
    ----------
    path : str or Path
        The file to read.
    consequence : str, optional
        What the refusal means for the caller, appended to the message
        (``"nothing was written"``).

    Returns
    -------
    Any
        The parsed document.

    Raises
    ------
    QaEvidenceError
        If the file cannot be read or is not parsable YAML.
    """
    suffix = f"; {consequence}" if consequence else ""
    try:
        return yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise QaEvidenceError(f"{path} cannot be read ({error}){suffix}") from None
    except yaml.YAMLError as error:
        raise QaEvidenceError(f"{path} is not parsable YAML ({error}){suffix}") from None
