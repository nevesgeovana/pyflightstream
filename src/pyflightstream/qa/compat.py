"""Compat reports and status promotion (SAD Sections 3.2 and 11).

Pipeline role: turns a probe run into committed evidence and the
evidence into database statuses. :func:`write_compat_report` writes the
machine-readable YAML report and its rendered Markdown table under
``reports/compat/``, one evidence line per database command of the
probed version. :func:`apply_compat` reads a committed report back and
promotes ``documented`` statuses to ``verified``, ``broken`` or
``removed`` in the chapter YAML files, citing the report in each
promoted entry; statuses are never hand-edited (CONTRIBUTING.md invariant 3),
and the schema rejects any of those three without its report citation.
A promotion writes every chapter it touches or none of them, and an
older report can no longer revert a status a later run already moved.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from pyflightstream._digest import optional_file_sha256
from pyflightstream._yamlflow import flow_mapping
from pyflightstream.commands import CommandEntry, CommandRegistry, Status
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.probes import ProbeOutcome, ProbeRun
from pyflightstream.qa.reports import (
    refuse_existing_report,
    report_paths,
    resolve_report_date,
)
from pyflightstream.run import describe_invocation
from pyflightstream.versions import resolve

COMPAT_SCHEMA = "pyflightstream-compat-report/1"


def compat_report_paths(
    out_dir: str | Path,
    *,
    version: str,
    date: str | None = None,
    label: str | None = None,
) -> tuple[Path, Path]:
    """Return where a compat report for one run WOULD be written.

    Split out of :func:`write_compat_report` so a caller can ask the
    question BEFORE it spends a licensed solver seat, which is the whole
    reason this function exists. The refusal on an existing report is
    right and its POSITION was wrong: on 2026-08-17 a full probe
    campaign on 26.123 ran to completion, 111 commands over five
    minutes of licensed solver, and then the write refused because a
    report of that stem already existed. The verdicts lived only in the
    process that was exiting, so a licence checkout was spent and
    discarded on a collision knowable before the solver started.

    Parameters
    ----------
    out_dir : str or Path
        Target directory, normally ``reports/compat/``.
    version : str, keyword-only
        Version identifier, as :attr:`ProbeRun.version` carries. A vendor
        release name is resolved through the registry, and an ambiguous
        one is refused here rather than after a seat is spent.
    date : str, optional, keyword-only
        ISO date stamped into the stem; defaults to today. A caller
        that will also write the report should resolve the date once
        and pass it here AND to :func:`write_compat_report`, so a run
        crossing midnight cannot check one stem and write another.
    label : str, optional
        Stem suffix distinguishing several reports on one day.

    Returns
    -------
    tuple of Path
        The YAML path and the Markdown path, in that order. Neither is
        created and the directory is not made.
    """
    date = resolve_report_date(date)
    return report_paths(out_dir, series="CMP", versions=[version], date=date, label=label)


def write_compat_report(
    run: ProbeRun, out_dir: str | Path, *, date: str | None = None, label: str | None = None
) -> tuple[Path, Path]:
    """Write one probe run as a compat report pair (YAML plus Markdown).

    The YAML file is the machine-readable evidence ``apply_compat``
    reads; the Markdown file renders the same content as a table for
    review. Both share the stem ``CMP-<version digits>_<date>`` plus
    the optional label. Existing report files are never overwritten:
    evidence supersedes evidence only through a new, dated report.

    Parameters
    ----------
    run : ProbeRun
        The probe run to record.
    out_dir : str or Path
        Target directory, normally ``reports/compat/``.
    date : str, optional
        ISO date stamped into the report; defaults to today.
    label : str, optional
        Stem suffix distinguishing several reports on the same day
        (for example ``"full"`` after a pilot).

    Returns
    -------
    tuple of Path
        The YAML path and the Markdown path, in that order.

    Raises
    ------
    FileExistsError
        When a report with the same stem already exists.
    QaEvidenceError
        When the date is not spelled ``YYYY-MM-DD``. The stem carries
        the string, so a value that cannot go in a file name is
        refused before the write rather than after it.
    UnknownVersionError, AmbiguousVersionAliasError
        When the run's version is not a registered build, or is a
        vendor release name shared by several. NEW on 2026-08-18:
        the stem's build key is resolved through the registry now,
        so these reach a direct Python caller where they did not
        before. ``pyfs-qa`` resolves first and never meets them.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Resolved HERE as well as inside compat_report_paths, and both from
    # the same default, so the stem the file is written under and the
    # date stamped inside it cannot disagree.
    date = resolve_report_date(date)
    yaml_path, md_path = compat_report_paths(out_dir, version=run.version, date=date, label=label)
    refuse_existing_report(yaml_path, md_path)
    counts = run.outcome_counts()
    document = {
        "schema": COMPAT_SCHEMA,
        "fs_version": run.version,
        "date": date,
        "package_version": run.package_version,
        "fs_exe": run.fs_exe_name,
        # WRITTEN EVEN WHEN IT IS None, and that is the point of it: a
        # key that appears only when a digest was taken makes absence
        # look like an older schema, and a reader cannot tell "nobody
        # measured it" from "this file predates the field".
        "fs_exe_sha256": run.fs_exe_sha256,
        "executor": describe_invocation(),
        "solver_identity": list(run.solver_identity),
        "summary": counts,
        "commands": {
            result.command: {
                "outcome": result.outcome.value,
                "detail": result.detail,
                "signals": {
                    "sentinel_before": result.sentinel_before,
                    "sentinel_after": result.sentinel_after,
                    "effect": result.effect,
                    "log_errors": list(result.log_errors),
                },
                "wall_time_s": None if result.wall_time_s is None else round(result.wall_time_s, 2),
                "return_code": result.return_code,
                "script_sha256": result.script_sha256,
            }
            for result in run.results
        },
    }
    yaml_path.write_text(yaml.safe_dump(document, sort_keys=False, width=100), encoding="utf-8")
    md_path.write_text(_render_markdown(run, date, counts), encoding="utf-8")
    return yaml_path, md_path


def _render_markdown(run: ProbeRun, date: str, counts: dict[str, int]) -> str:
    """Render the human-readable side of the report."""
    lines = [
        f"# Compat report: FlightStream {run.version} ({date})",
        "",
        "Tier 2 command-validity evidence produced by the probe harness",
        "(`pyfs-qa probe`); one evidence line per database command of this",
        "version. Database statuses are promoted from this report only",
        "through `pyfs-qa apply-compat`, never edited by hand (CONTRIBUTING.md",
        "invariant 3). Probe scripts and logs are local scratch; this",
        "report is the committed evidence.",
        "",
        "## Setup",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Executable | {run.fs_exe_name} "
        f"(sha256 {run.fs_exe_sha256 or 'not recorded'}, "
        "local, `_private/exe/`, never committed) |",
        f"| Executor | {describe_invocation(markdown=True)} |",
        f"| Package | pyflightstream {run.package_version} |",
        f"| Solver identity lines | {'; '.join(run.solver_identity) or 'none captured'} |",
        "",
        "## Summary",
        "",
        ", ".join(f"{count} {name}" for name, count in counts.items()) + ".",
        "",
        "## Evidence per command",
        "",
        "| Command | Outcome | Evidence |",
        "|---|---|---|",
    ]
    for result in run.results:
        detail = result.detail.replace("|", "\\|")
        lines.append(f"| {result.command} | {result.outcome.value} | {detail} |")
    lines.append("")
    return "\n".join(lines)


def _load_yaml(path: Path) -> Any:
    """Read and parse one YAML file, refusing in this module's own type.

    Fixed as a CLASS rather than at the one site review found. The
    promotion path documents ``QaEvidenceError`` and the CLI traps it,
    and three reachable inputs escaped both: a mistyped report path
    (``FileNotFoundError``), an unparsable report (``yaml.YAMLError``,
    which is not a ``ValueError``), and any unparsable file in the
    evidence directory. Each reached the operator as a stack that says
    nothing about whether the database was written.
    """
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise QaEvidenceError(f"{path} cannot be read ({error}); nothing was written") from None
    except yaml.YAMLError as error:
        raise QaEvidenceError(
            f"{path} is not parsable YAML ({error}); nothing was written"
        ) from None


def read_compat_report(path: str | Path) -> dict:
    """Load and check a machine-readable compat report.

    Parameters
    ----------
    path : str or Path
        The report YAML file.

    Returns
    -------
    dict
        The parsed report document.

    Raises
    ------
    ValueError
        When the file does not carry the compat report schema marker.
    """
    document = _load_yaml(Path(path))
    if not isinstance(document, dict) or document.get("schema") != COMPAT_SCHEMA:
        raise QaEvidenceError(
            f"{path} is not a compat report (expected schema {COMPAT_SCHEMA!r}); "
            "apply-compat only promotes statuses from probe evidence"
        )
    return document


#: Outcomes ``apply_compat`` writes into the database. Only these carry
#: a judgment, so only these can supersede one: ``unprobed`` records why
#: no judgment exists and must never invalidate a citation, or every
#: identity run would unseat the full run before it.
#:
#: DERIVED from the enum by subtracting the one non-judgment, rather
#: than listed. A listed set makes a future outcome silently
#: unpromotable while :class:`~pyflightstream.qa.probes.ProbeOutcome`,
#: where a reader looks, says otherwise. The members are the enum
#: members, not their strings, which compares identically against a
#: report's raw values because ``ProbeOutcome`` is a ``StrEnum`` and
#: lets a consumer get back to the enum it documents.
PROMOTABLE_OUTCOMES = frozenset(ProbeOutcome) - {ProbeOutcome.UNPROBED}

#: A per-edition manual page citation, as the database writes one. Used
#: to recognise a row that an EDITION documents, which a measured
#: removal contradicts rather than supersedes.
_EDITION_PAGE = re.compile(r"SRC-\d+\s+pp?\.", re.IGNORECASE)


@dataclass(frozen=True, kw_only=True)
class Judgment:
    """One report's promotable judgment of one command in one build.

    Keyword-only, and that is the whole point of the type rather than a
    style choice. The five fields are consecutive strings, so a
    positional constructor would put the swap hazard it was created to
    remove back on the mandatory path: ``contradicting_evidence`` takes
    this record, so building one by hand is the only way to call it, and
    a swapped pair makes the index lookup miss and answer "nothing
    contradicts, promote it". ``ProbeSpec`` is keyword-only for the same
    reason.

    Attributes
    ----------
    command : str
        Database command name.
    fs_version : str
        Canonical FlightStream identifier the report probed.
    outcome : str
        One of :data:`PROMOTABLE_OUTCOMES`: ``verified``, ``broken`` or
        ``removed``.
    date : str
        The report's ISO date, or the empty string when it carries
        none. ISO dates order lexicographically, which is what makes
        the comparison below a plain string comparison.
    report : str
        Repository-relative POSIX path of the report, the same form
        the database cites.
    """

    command: str
    fs_version: str
    outcome: ProbeOutcome
    date: str
    report: str


def read_compat_reports(
    reports_dir: str | Path | None = None, *, repo_root: str | Path = "."
) -> dict[tuple[str, str], tuple[Judgment, ...]]:
    """Index every promotable judgment in a directory of compat reports.

    Files that do not carry the compat schema are skipped rather than
    refused: the directory is committed evidence, not a curated input,
    and a README beside the reports must not stop a promotion.

    Parameters
    ----------
    reports_dir : str or Path, optional
        Directory of compat report YAML files; defaults to
        ``<repo_root>/reports/compat``. An absent DEFAULT yields an
        empty index, which is the first-report case; a path given
        explicitly that is not a directory is refused.
    repo_root : str or Path, optional
        Repository root; report paths are recorded relative to it, in
        POSIX form, so they compare directly against the ``report``
        field of a database row.

    Returns
    -------
    dict
        ``(command, fs_version)`` to the judgments of that pair, oldest
        first. A pair no report judges promotably is absent.
    """
    root = Path(repo_root).resolve()
    # Defaulting here rather than only in apply_compat: every caller of
    # this function was retyping the location that function already
    # knows, so the default lived in one of the pair and was duplicated
    # by the other.
    given = reports_dir is not None
    if reports_dir is None:
        reports_dir = Path(repo_root) / "reports" / "compat"
    reports_dir = Path(reports_dir)
    index: dict[tuple[str, str], list[Judgment]] = {}
    if not reports_dir.is_dir():
        # An ABSENT DEFAULT is the first-report case and yields an empty
        # index. A path the caller TYPED is different, and the guard
        # belongs here rather than in apply_compat, where it used to
        # live: this function is exported, so the caller it protected
        # was one of several. Reading a mistyped path as an empty index
        # answers "nothing contradicts, promote it", which is a guard
        # reading its own missing information as permission.
        if not given:
            return {}
        hint = (
            " That is a file; read_compat_report (singular) reads one report and this "
            "reads a directory of them."
            if reports_dir.is_file()
            else ""
        )
        raise QaEvidenceError(
            f"reports_dir {reports_dir} is not a directory, and it was given "
            f"explicitly.{hint} An unreadable evidence directory would disable the "
            "supersession check rather than run it, so this is refused instead of "
            "skipped"
        )
    for path in sorted(reports_dir.glob("*.yaml")):
        # An unparsable file is REFUSED rather than skipped, and the
        # difference matters here: skipping means the supersession check
        # silently loses whatever that file judged, which is a guard
        # reading its own missing information as permission. A file that
        # parses and is not a report is a different thing and is skipped
        # by design, so a README beside the evidence cannot stop a
        # promotion.
        document = _load_yaml(path)
        if not isinstance(document, dict) or document.get("schema") != COMPAT_SCHEMA:
            continue
        try:
            citation = path.resolve().relative_to(root).as_posix()
        except ValueError:
            citation = path.resolve().as_posix()
        version = str(document.get("fs_version", ""))
        date = str(document.get("date") or "")
        for command, body in (document.get("commands") or {}).items():
            outcome = body.get("outcome")
            if outcome in PROMOTABLE_OUTCOMES:
                index.setdefault((command, version), []).append(
                    Judgment(
                        command=command,
                        fs_version=version,
                        outcome=outcome,
                        date=date,
                        report=citation,
                    )
                )
    return {key: tuple(sorted(value, key=lambda j: j.date)) for key, value in index.items()}


def contradicting_evidence(
    judgments: dict[tuple[str, str], tuple[Judgment, ...]],
    *,
    incoming: Judgment,
) -> tuple[Judgment, ...]:
    """Judgments in the committed evidence that supersede ``incoming``.

    A judgment supersedes when it is at least as recent AND records a
    DIFFERENT outcome. Both halves are deliberate.

    Agreement never supersedes. The plan behind this guard
    (``PLN-20260804-1500``) asked for the strictly newest report to be
    the cited one, and measurement of the committed evidence refuted it as the
    rule to enforce: four rows cite a full run while a later
    ``--identity-only`` run of the same build also judges ``PRINT``,
    because the baseline probe exercises it. Nothing is wrong with
    those four rows, and a guard red on a correct database is a guard
    that gets switched off. What the plan actually measured, and what
    this catches, is a report REVERTING a status another report
    already moved.

    Same-date is included because two reports of one day that disagree
    are ambiguous, and an ambiguity resolved silently by file order is
    the failure this whole function exists to prevent. A report with no
    date sorts oldest and so can never supersede a dated one: a report
    that cannot show it is newer is treated as not newer.

    Parameters
    ----------
    judgments : dict
        Index from :func:`read_compat_reports`.
    incoming : Judgment
        The judgment about to be written. Passed as the record rather
        than as its five fields, because five interchangeable strings in
        a row fail SILENTLY when two are swapped: the lookup misses, the
        answer is empty, and the caller reads that as "nothing
        contradicts, promote it". The record cannot be mis-ordered.
        Its ``report`` field excludes it from its own answer, so a
        report never supersedes itself.

    Returns
    -------
    tuple of Judgment
        Superseding judgments, oldest first; empty when nothing
        contradicts the incoming one.
    """
    return tuple(
        judgment
        for judgment in judgments.get((incoming.command, incoming.fs_version), ())
        if judgment.report != incoming.report
        and judgment.date >= incoming.date
        and judgment.outcome != incoming.outcome
    )


def apply_compat(
    report_path: str | Path,
    *,
    repo_root: str | Path = ".",
    commands_dir: str | Path | None = None,
    reports_dir: str | Path | None = None,
) -> list[tuple[str, str, str]]:
    """Promote database statuses from a committed compat report.

    Every command the report judged with one of
    :data:`PROMOTABLE_OUTCOMES` (``verified``, ``broken`` or
    ``removed``) gets its version line in the chapter YAML written with
    the new status and the report cited in the ``report`` field;
    ``unprobed`` commands are untouched. A command that already records the version is rewritten
    in place; one that does not gains the line at its release position,
    which is what the first probe run of a newly registered version
    needs. The edit is line-level on the flow-mapping version lines, so
    chapter comments and layout survive; a command whose version block
    holds no single-line entry to pattern on is refused loudly rather
    than mangled.

    Parameters
    ----------
    report_path : str or Path
        The committed report YAML (``reports/compat/CMP-*.yaml``).
    repo_root : str or Path
        Repository root; the report citation written into the database
        is the report path relative to it, in POSIX form.
    commands_dir : str or Path, optional
        Chapter YAML directory; defaults to the installed
        ``pyflightstream.commands`` package data (the working tree in
        an editable install). Tests point it at a copy.
    reports_dir : str or Path, optional
        Directory of committed compat reports the incoming one is
        checked against for supersession; defaults to
        ``<repo_root>/reports/compat``. It is anchored on the
        repository rather than on the report's own folder so that
        applying a report written to a scratch directory is still
        checked against the committed evidence. A directory that does
        not exist yields an empty index, which is the first-report
        case.

    Returns
    -------
    list of tuple
        One ``(command, status, chapter file name)`` per promotion.

    Raises
    ------
    QaEvidenceError
        When the report is not a compat report, when it lies outside
        ``repo_root``, when it names an unregistered version, when an
        explicitly given ``reports_dir`` is not a directory, when a
        judged command or its version line cannot be found, when a
        rewritten entry fails schema validation, when a report at least
        as recent already records a different outcome for a pair this
        one would write (``PLN-20260804-1500``), or when a ``removed``
        promotion would overwrite a row carrying a page citation of that
        edition or a per-version argument grammar, neither of which is a
        mechanical decision (RPT-026). Nothing is written in any of
        these cases: every chapter is rewritten and validated in memory
        and the writes happen only once all of them have succeeded.
    """
    report = read_compat_report(report_path)
    canonical = report["fs_version"]
    root = Path(repo_root).resolve()
    try:
        citation = Path(report_path).resolve().relative_to(root).as_posix()
    except ValueError:
        raise QaEvidenceError(
            f"{report_path} is outside {root}, so the citation written into the "
            "database would not be a repository-relative path and no reader could "
            "follow it. Move the report under the repository first, or pass repo_root"
        ) from None
    if commands_dir is None:
        commands_dir = Path(str(resources.files("pyflightstream.commands")))
    commands_dir = Path(commands_dir)
    order = _release_order(commands_dir)
    if canonical not in order:
        raise QaEvidenceError(
            f"the report names FlightStream version {canonical!r}, which the version "
            f"registry beside {commands_dir} does not list. Register it in "
            "commands/_meta.yaml first (the ordered list is the only ordering "
            "authority); nothing was written. Registered: "
            f"{', '.join(sorted(order, key=order.__getitem__))}"
        )

    targets = {
        name: body
        for name, body in report["commands"].items()
        if body["outcome"] in PROMOTABLE_OUTCOMES
    }

    # Supersession, checked for the WHOLE report before a byte is
    # written. Per-command refusal would leave the database half
    # promoted from a report the tool has already judged unfit, which
    # is a worse state than either applying it or refusing it.
    judgments = read_compat_reports(reports_dir, repo_root=repo_root)
    incoming_date = str(report.get("date") or "")
    superseded = [
        (name, body["outcome"], contradicting)
        for name, body in targets.items()
        if (
            contradicting := contradicting_evidence(
                judgments,
                incoming=Judgment(
                    command=name,
                    fs_version=canonical,
                    outcome=body["outcome"],
                    date=incoming_date,
                    report=citation,
                ),
            )
        )
    ]
    if superseded:
        detail = "; ".join(
            f"{name} would be written {outcome} from a report dated "
            f"{incoming_date or 'nothing'}, but "
            + ", ".join(f"{j.report} ({j.date}) records {j.outcome}" for j in contradicting)
            for name, outcome, contradicting in sorted(superseded)
        )
        raise QaEvidenceError(
            f"{report_path} is superseded evidence for {len(superseded)} of the "
            f"{len(targets)} commands it judges, and nothing was written. Re-applying it "
            "would revert a status that a later run already moved, with a citation that "
            "agrees with itself and every guard green, which is why this is refused "
            f"rather than warned about. {detail}. Promote from the newest run, or, if "
            "the older reading is the right one, re-probe and let a new report say so"
        )

    # EVERY chapter is rewritten and validated in memory, and the writes
    # happen only once all of them have succeeded. The docstring above
    # promises that a refusal writes nothing, and before this loop was
    # restructured that promise held for the up-front checks alone: a
    # refusal raised while rewriting chapter n left chapters 1..n-1
    # already promoted on disk, under an error message naming one
    # command in one file. The two removal refusals and the diverged
    # report check below are all such mid-loop raise sites.
    promotions: list[tuple[str, str, str]] = []
    pending = dict(targets)
    rewritten: list[tuple[Path, str]] = []
    for chapter_path in sorted(commands_dir.glob("*.yaml")):
        if chapter_path.name == "_meta.yaml":
            continue
        text = chapter_path.read_text(encoding="utf-8")
        names = [name for name in _load_yaml(chapter_path) if name in pending]
        if not names:
            continue
        for name in names:
            body = pending.pop(name)
            text = _rewrite_version_line(
                text, chapter_path.name, name, canonical, body, citation, order
            )
        _validate_chapter(chapter_path.name, text, names)
        rewritten.append((chapter_path, text))
        promotions.extend((name, targets[name]["outcome"], chapter_path.name) for name in names)
    if pending:
        raise QaEvidenceError(
            f"report judges {', '.join(sorted(pending))} but no chapter file defines "
            "them; the report and the database have diverged, and nothing was written"
        )
    for chapter_path, text in rewritten:
        chapter_path.write_text(text, encoding="utf-8")
    return promotions


_VERSION_LINE = re.compile(r'^(\s+)"(\d{2}\.\d{3})":\s*\{.*\}\s*$')

# A note lives on one flow-mapping line of a chapter file, so it is
# capped. The cap is not the problem; a cap that hides itself is. The
# marker below is what makes the cut visible.
_NOTE_LIMIT = 140
_NOTE_CUT_MARKER = " [...]"


def _one_line_note(detail: str) -> str:
    """Render a probe detail as the one-line ``note:`` of a version entry.

    Collapses whitespace, replaces the double quotes that would end the
    YAML scalar, and caps the length. A capped note ENDS WITH
    ``[...]``, cut at a word boundary, because the note reaches human
    readers in two places where a silent cut misleads: the compatibility
    reference, and the refusal that
    :class:`~pyflightstream.script.BrokenCommandError` raises when a
    recipe emits the command. Before the marker existed, that refusal
    ended mid-word ("reports the 5000 m standa"), which reads as a
    corrupted database rather than as an extract. The full text is in
    the committed report the same entry cites, and the marker is what
    tells the reader to go there.

    Parameters
    ----------
    detail : str
        The probe report's ``detail`` field, any length, any whitespace.

    Returns
    -------
    str
        A single line safe to embed in a double-quoted YAML scalar, at
        most :data:`_NOTE_LIMIT` characters.
    """
    text = " ".join(detail.replace('"', "'").split())
    if len(text) <= _NOTE_LIMIT:
        return text
    head = text[: _NOTE_LIMIT - len(_NOTE_CUT_MARKER)]
    # Cut at a word boundary when there is one to cut at; a single word
    # longer than the limit has none, and a hard cut with the marker
    # still beats a hard cut without it.
    trimmed = head.rsplit(" ", 1)[0].rstrip(" ,;:") if " " in head else head
    return f"{trimmed}{_NOTE_CUT_MARKER}"


def _release_order(commands_dir: Path) -> dict[str, int]:
    """Return canonical identifier to release position for one command tree.

    Read from ``_meta.yaml`` INSIDE ``commands_dir``, not from the
    installed package. The two are the same tree in normal use and
    different whenever a caller points ``apply_compat`` at a copy, and
    placing a line into one tree using another tree's ordering is two
    authorities for one edit. ``known_versions`` is also cached for the
    process, so it would answer with the registry as it was before a
    version registered in the same run.

    Parameters
    ----------
    commands_dir : Path
        Chapter directory being edited; its ``_meta.yaml`` is the
        ordering authority for that tree (CONTRIBUTING.md invariant 4).

    Returns
    -------
    dict of str to int
        Position per canonical identifier, oldest first. Empty when the
        directory carries no ``_meta.yaml``, which is the shape a test
        fixture of loose chapter files has; the caller then refuses the
        report rather than guessing a position.
    """
    meta_path = commands_dir / "_meta.yaml"
    if not meta_path.is_file():
        return {}
    meta = _load_yaml(meta_path) or {}
    return {
        str(entry["canonical"]): position
        for position, entry in enumerate(meta.get("versions") or [])
    }


def _rewritten_flow_entry(
    line: str,
    chapter: str,
    name: str,
    canonical: str,
    citation: str,
    body: dict,
) -> str:
    """Rewrite one single-line version entry, KEEPING the keys it already has.

    The first version of this rewrote the whole line from `status` and
    `report`, which discarded every other key silently: the `note` that
    carries a per-edition page citation, a `successor`, a `probe_ref`, an
    inline `args` override. `_validate_chapter` re-parses the result and
    passes, because what is left is well-formed YAML saying less.

    That is the same loss the block form now refuses loudly, one shape
    over, and the exposed population is not small: most rows of this
    database carry a `note`, and those notes are the per-edition
    citations the v0.5.0 backfill was written to record. One probe run on
    an older build would have erased a chapter's worth with every guard
    green.

    Parameters
    ----------
    line : str
        The existing entry line, indentation included.
    chapter, name, canonical : str
        Chapter file, command, and the build being promoted, for messages.
    citation : str
        Repository-relative path of the compat report being promoted from.
    body : dict
        The report's record for this command; ``outcome`` and, for a
        broken outcome, ``detail``.

    Returns
    -------
    str
        The rewritten line, same indentation, same key order, with the
        keys this promotion owns replaced and every other key carried
        through unchanged.

    Raises
    ------
    QaEvidenceError
        If the entry cannot be parsed as a flow mapping, or if it carries
        a narrative citation that the new status contradicts.
    """
    match = _VERSION_LINE.match(line)
    if match is None:  # pragma: no cover - the caller matched it already
        raise QaEvidenceError(f"{chapter}: {name} entry for {canonical!r} is not a flow mapping")
    indent = match.group(1)
    mapping = line[line.index("{") : line.rindex("}") + 1]
    try:
        existing = yaml.safe_load(mapping)
    except yaml.YAMLError as error:
        raise QaEvidenceError(
            f"{chapter}: the {canonical!r} entry of {name} does not parse as YAML "
            f"({error}), so this promotion cannot rewrite it without guessing at its "
            "shape. Repair the line by hand and re-run"
        ) from None
    if not isinstance(existing, dict):
        raise QaEvidenceError(
            f"{chapter}: the {canonical!r} entry of {name} is not a mapping, so there "
            "is nothing to rewrite in place"
        )

    status = body["outcome"]
    # A measured removal cites a narrative report through `probe_ref`,
    # which the model admits for `removed` alone, so promoting over one
    # would either write a row the loader refuses or drop the citation.
    # Neither is a mechanical decision: a probe that RUNS a command the
    # database records as absent from the build means one of the two
    # measurements is wrong, and which one is a person's call.
    if existing.get("probe_ref") and status != existing.get("status"):
        raise QaEvidenceError(
            f"{chapter}: {name} records {canonical!r} as {existing.get('status')!r} on the "
            f"strength of {existing['probe_ref']!r}, and this run judges it {status!r}. "
            "One of the two measurements is wrong about whether the build carries the "
            "command at all, which is not a promotion to make mechanically. Read both "
            "and edit the row deliberately"
        )

    if status == ProbeOutcome.REMOVED.value:
        # The edition documents the command and the solver refuses the
        # name. One of the two is wrong about the product and neither
        # can be picked mechanically: the manual defect classes this
        # repository already records include an edition printing a
        # command the build does not carry, and so does a probe script
        # misspelling one, and the solver's wording is IDENTICAL for a
        # real absent command and a token that was never a command
        # (RPT-026).
        note = str(existing.get("note") or "")
        if _EDITION_PAGE.search(note):
            raise QaEvidenceError(
                f"{chapter}: {name} records {canonical!r} with a page citation of that "
                f"edition ({note[:80]!r}), and this run measured the solver refusing "
                "the name. An edition documenting a command the build does not carry "
                "is a manual defect and a probe emitting a misspelling is a spec "
                "defect, and the solver says the same thing in both cases. Read the "
                "page and the probe script, then edit the row deliberately"
            )
        if existing.get("args") is not None:
            raise QaEvidenceError(
                f"{chapter}: {name} declares a per-version argument grammar for "
                f"{canonical!r}, and a removed version has no grammar to emit. "
                "Promoting would write a row the loader refuses. Decide whether the "
                "override or the measurement is wrong before promoting"
            )

    # The keys this promotion OWNS are rendered exactly as they were
    # before this function existed, because the shape of a promoted line
    # is pinned by tests and by the whole database's worth of precedent. Only the
    # carried-through keys are new output, and they go after.
    owned = {"status", "report"}
    pairs: dict[str, object] = {"status": status, "report": citation}
    if status in (ProbeOutcome.BROKEN.value, ProbeOutcome.REMOVED.value):
        # A removed row REQUIRES a note (the model refuses one without),
        # because the status alone cannot say which of the three ways it
        # arrived; the probe detail says it was measured.
        pairs["note"] = _one_line_note(str(body.get("detail", "")))
        owned.add("note")
    pairs.update({key: value for key, value in existing.items() if key not in owned})
    return f'{indent}"{canonical}": {_flow_mapping(pairs)}'


#: The renderer of a promoted value, which THIS MODULE NO LONGER OWNS.
#: It lived here from the repair of `INC-20260811-1511-both` until
#: 2026-08-17, and its docstring closed with "there is now no site",
#: which was true of this module and became untrue of the package the day
#: `pyfs-manual register` began writing the same chapter files from
#: :mod:`pyflightstream.utils`. That subpackage sits BELOW this one and
#: cannot import from here, so it built the mapping by concatenation and
#: the class came back. The renderer moved to
#: :mod:`pyflightstream._yamlflow`, below every layer, where both writers
#: can reach it. The alias is kept so this module reads as it did.
_flow_mapping = flow_mapping


def _rewrite_version_line(
    text: str,
    chapter: str,
    name: str,
    canonical: str,
    body: dict,
    citation: str,
    order: dict[str, int],
) -> str:
    """Write one command's evidence for ``canonical``, rewriting or inserting.

    A version the command already records is rewritten in place. A
    version it does not record yet is INSERTED, at its release position
    among the lines already there, taking their indentation.

    The insert is what onboarding a new FlightStream version needs: the
    first probe run of a new version judges commands that carry no line
    for it at all, since a version starts life recorded nowhere but
    ``_meta.yaml``. Refusing there would leave the run's evidence
    unpromotable and the only remaining route a hand edit, which
    invariant 3 forbids outright.

    Still refused loudly: a command whose ``versions:`` block holds no
    single-line flow-mapping entry to pattern the new one on. That block
    is either multi-line or malformed, and guessing its shape is how a
    mechanical edit mangles a file.
    """
    lines = text.splitlines()
    start = None
    end = len(lines)
    for index, line in enumerate(lines):
        if start is None:
            if line.rstrip() == f"{name}:":
                start = index
        elif re.match(r"^[A-Za-z0-9_]+:", line):
            end = index
            break
    if start is None:
        raise QaEvidenceError(
            f"{chapter}: command block {name} not found, so the report's evidence for "
            "it has nowhere to be promoted to. The report and the database disagree "
            "about which commands exist; re-run the probe against this tree"
        )

    status = body["outcome"]
    pairs: dict[str, object] = {"status": status, "report": citation}
    if status in (ProbeOutcome.BROKEN.value, ProbeOutcome.REMOVED.value):
        pairs["note"] = _one_line_note(str(body.get("detail", "")))

    recorded = [
        (index, match.group(1), match.group(2))
        for index in range(start, end)
        if (match := _VERSION_LINE.match(lines[index])) is not None
    ]
    for index, _indent, recorded_canonical in recorded:
        if recorded_canonical == canonical:
            lines[index] = _rewritten_flow_entry(
                lines[index], chapter, name, canonical, citation, body
            )
            return "\n".join(lines) + "\n"

    # A version already recorded as a BLOCK rather than a one-line flow
    # mapping is invisible to _VERSION_LINE, and inserting beside it
    # writes the key twice. YAML keeps the last and drops the first
    # silently, so on 2026-08-08 a promotion nearly erased a
    # hand-authored per-version GRAMMAR (SOLVER_PROXIMAL_BOUNDARIES on
    # 26.121). Refused rather than rewritten: the block carries a note
    # and possibly an args override that this function has no way to
    # preserve, and dropping either would be the same silent loss in a
    # different place.
    block = f'{" " * 4}"{canonical}":'
    for index in range(start, end):
        if lines[index].rstrip() == block:
            raise QaEvidenceError(
                f"{chapter}: {name} already records {canonical!r} as a multi-line "
                "block, which this promotion cannot rewrite without discarding the "
                "note or argument override the block carries. Fold the new status "
                f"and report into that block by hand, citing {citation!r}, and leave "
                "the rest of it alone; the status still comes from a committed "
                "report, which is what invariant 3 asks."
            )

    if not recorded:
        raise QaEvidenceError(
            f"{chapter}: {name} records no version as a single-line entry, so this "
            f"promotion has no line to copy the shape of the new {canonical!r} entry "
            f"from. Rewrite the versions: block of {name} as one line per version "
            "(for example '\"26.120\": {status: documented}') and re-run "
            "pyfs-qa apply-compat; a status is promoted from a committed report, "
            "never hand-edited (CONTRIBUTING.md invariant 3)."
        )

    position = order[canonical]
    indent = recorded[0][1]
    insert_at = next(
        (
            index
            for index, _, recorded_canonical in recorded
            if order.get(recorded_canonical, -1) > position
        ),
        recorded[-1][0] + 1,
    )
    lines.insert(insert_at, f'{indent}"{canonical}": {_flow_mapping(pairs)}')
    return "\n".join(lines) + "\n"


def _validate_chapter(chapter_name: str, text: str, names: list[str]) -> None:
    """Validate the rewritten entries against the command schema.

    Takes the TEXT rather than the path, so a rewrite can be rejected
    before it reaches the disk. Reading the file back would mean the
    file had already been written, which is the partial-promotion state
    :func:`apply_compat` promises not to leave behind.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        # Outside the try until 2026-08-11, so an unparsable rewrite
        # left this function raising a scanner error out of a
        # promotion documented to raise QaEvidenceError, past the
        # CLI trap. Reachable: one backslash in a solver message
        # used to reach the note unescaped.
        raise QaEvidenceError(
            f"{chapter_name}: the rewritten chapter does not parse as YAML "
            f"({error}). Nothing was written"
        ) from None
    chapter = chapter_name.removesuffix(".yaml")
    for name in names:
        try:
            CommandEntry(name=name, chapter=chapter, **data[name])
        except ValueError as error:
            # Re-raised as this module's own type, because the caller
            # documents QaEvidenceError and the CLI traps it. A bare
            # pydantic ValidationError escaped both and reached the
            # operator as a stack, on a reachable path: a hand-written
            # `removed` report with no `detail` yields an empty note,
            # which the model refuses.
            # "after this promotion" rather than "the rewritten entry",
            # because this validates the WHOLE entry: a defect that
            # predates the run would otherwise be reported as something
            # the tool wrote.
            raise QaEvidenceError(
                f"{chapter_name}: after this promotion the {name} entry does not "
                f"satisfy the command schema ({error}). Nothing was written. The "
                "report's judgment for this command produced a value the model "
                "refuses, so fix the report or the row and re-run; if the entry was "
                "already invalid before this run, repair it first"
            ) from None


# --------------------------------------------------------------------------
# PFS-2026.15: one cheap question, asked before a seat is spent
# --------------------------------------------------------------------------

#: Where the digests of the executables in hand are recorded, relative to
#: the repository root. A narrative report rather than a machine series
#: because CMP, PHY and DRF each assert that a solver ran, and this one
#: is measured by hashing files with the solver never started.
EXECUTABLE_BASELINE_REPORT = "reports/RPT-032_executable-identity-baseline_2026-08-19.md"


class ExecutableVerdict(enum.StrEnum):
    """What a candidate executable does to the evidence already gathered."""

    #: The binary is byte-for-byte the one the baseline recorded for this
    #: version. Every row of that version's evidence transfers untouched.
    TRANSFERS = "transfers"
    #: The digest is not in the baseline, so nothing is known about this
    #: binary yet. The identity-only probe is the next step and it is the
    #: ONLY licensed work this verdict authorises.
    UNKNOWN = "unknown"
    #: The identity probe printed the build number the registry records,
    #: so the evidence transfers and both digests are named.
    CONFIRMED = "confirmed"
    #: The identity probe printed a different build number. It is a
    #: different registered version, and no further licensed work starts.
    MISMATCH = "mismatch"


@dataclass(frozen=True, kw_only=True)
class ExecutableIdentity:
    """The answer to "does the evidence already gathered still apply?".

    Attributes
    ----------
    verdict : ExecutableVerdict
        What the caller may do next.
    version : str
        Canonical version whose evidence is in question.
    fs_exe_name : str
        File name of the candidate executable (never its path).
    fs_exe_sha256 : str
        Lowercase hexadecimal sha256 of the candidate's bytes.
    baseline_sha256 : str or None
        Digest the baseline records for this version, when it records
        one. This is the OLD side of the comparison, and it exists
        before any replacement arrives precisely because hashing a file
        costs no licensed seat.
    printed_build : str or None
        Build number the solver printed, when an identity run has
        happened; ``None`` before one has.
    registry_build : str or None
        Build number the registry records for this version.
    message : str
        One sentence naming the physical cause and the next step, in the
        form an operator can act on.
    """

    verdict: ExecutableVerdict
    version: str
    fs_exe_name: str
    fs_exe_sha256: str
    baseline_sha256: str | None
    printed_build: str | None
    registry_build: str | None
    message: str

    @property
    def spends_a_seat(self) -> bool:
        """Whether the next step needs the licensed machine."""
        return self.verdict is ExecutableVerdict.UNKNOWN


def read_executable_baseline(path: str | Path) -> dict[str, dict[str, str]]:
    """Read the committed executable digest baseline.

    The baseline is a Markdown table in
    :data:`EXECUTABLE_BASELINE_REPORT`, and its columns are resolved by
    LABEL. A table makes no guarantee about column order, so a reader
    that counts positions breaks on an edit that changes nothing.

    Parameters
    ----------
    path : str or Path
        The report to read.

    Returns
    -------
    dict of str to dict
        Keyed by canonical version; each value carries ``sha256``,
        ``names`` and ``bytes`` as read from the row.

    Raises
    ------
    QaEvidenceError
        When the file carries no table with the expected labels, when a
        digest is not 64 hexadecimal characters, or when one version is
        recorded twice with different digests. A baseline that cannot be
        read is refused rather than treated as empty: an empty baseline
        makes every executable UNKNOWN, which reads as caution and is
        really a file nobody parsed.
    """
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise QaEvidenceError(
            f"the executable baseline {path} cannot be read ({error}); without it no "
            "replacement executable can be compared against the binaries in hand"
        ) from None
    wanted = {"version", "sha256"}
    baseline: dict[str, dict[str, str]] = {}
    header: list[str] | None = None
    for line in lines:
        if not line.startswith("|"):
            header = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if header is None:
            labels = [cell.lower() for cell in cells]
            header = labels if wanted <= set(labels) else None
            continue
        if set(cells[0]) <= set("-: "):
            continue
        row = dict(zip(header, cells, strict=False))
        # A SHORT ROW is refused rather than dropped or half-read. `zip`
        # truncates, so a row with fewer cells than the header silently
        # loses its last columns, and where the lost one is the digest a
        # KeyError would leave this public function raising something
        # outside the exception catalogue.
        if not wanted <= set(row):
            raise QaEvidenceError(
                f"{path} carries a row with fewer cells than its header ({cells}); a "
                "baseline row that loses a column is a row whose digest cannot be read"
            )
        version = row["version"].strip("`")
        digest = row["sha256"].strip("`").lower()
        if len(digest) != 64 or set(digest) - set("0123456789abcdef"):
            raise QaEvidenceError(
                f"{path} records {digest!r} for {version}, which is not a sha256; a "
                "baseline digest is 64 hexadecimal characters and is measured, never typed"
            )
        if version in baseline and baseline[version]["sha256"] != digest:
            raise QaEvidenceError(
                f"{path} records two different digests for {version}; one version names one "
                "binary here, and two rows disagreeing is the ambiguity this baseline exists "
                "to remove"
            )
        baseline[version] = {
            "sha256": digest,
            "names": row.get("names", ""),
            "bytes": row.get("bytes", ""),
        }
    if not baseline:
        raise QaEvidenceError(
            f"{path} carries no baseline table with {sorted(wanted)} columns; a baseline "
            "read as empty makes every executable look unknown, which is a parse failure "
            "wearing the costume of caution"
        )
    return baseline


def classify_executable(
    fs_exe: str | Path,
    *,
    version: str,
    baseline: Mapping[str, Mapping[str, str]],
    printed_build: str | None = None,
) -> ExecutableIdentity:
    """Ask a candidate executable whether the evidence in hand still applies.

    This is the cheap question that decides whether a licensed seat is
    worth spending, and it is asked BEFORE any campaign, probe or
    physics run. Command evidence in this package is keyed by the
    canonical version string alone: a version row carries status,
    successor, note, report, probe reference and arguments, and no hash,
    path or size of any binary. So a relicensed or replaced binary
    reporting the same version is the same solver as far as every
    lookup, promotion and refusal here is concerned, and the only thing
    that separates them is the digest and the build number it prints.

    Parameters
    ----------
    fs_exe : str or Path
        The candidate executable. It is hashed; it is never started.
    version : str, keyword-only
        Canonical version whose evidence is in question.
    baseline : mapping, keyword-only
        The committed digest baseline, as
        :func:`read_executable_baseline` returns.
    printed_build : str, optional, keyword-only
        Build number an identity-only probe read from the solver's own
        banner. ``None`` before one has run, which is the state every
        replacement arrives in.

    Returns
    -------
    ExecutableIdentity
        The verdict, both digests where both exist, both build numbers
        where both exist, and the next step in words.

    Raises
    ------
    QaEvidenceError
        When the executable cannot be read, so no digest exists to
        compare. A missing binary is a machine problem and this function
        refuses rather than reporting an unknown binary that is really
        an absent one.
    UnknownVersionError
        When ``version`` is not a registered build.

    Examples
    --------
    >>> from pyflightstream.qa.compat import (           # doctest: +SKIP
    ...     classify_executable,
    ...     read_executable_baseline,
    ... )
    >>> baseline = read_executable_baseline(              # doctest: +SKIP
    ...     "reports/RPT-032_executable-identity-baseline_2026-08-19.md"
    ... )
    >>> answer = classify_executable(                     # doctest: +SKIP
    ...     "_private/exe/FlightStream_26123/FlightStream_26123.exe",
    ...     version="26.123",
    ...     baseline=baseline,
    ... )
    >>> answer.verdict, answer.spends_a_seat              # doctest: +SKIP
    (<ExecutableVerdict.TRANSFERS: 'transfers'>, False)
    """
    resolved = resolve(version)
    digest = optional_file_sha256(fs_exe)
    if digest is None:
        raise QaEvidenceError(
            f"the executable {Path(fs_exe).name} cannot be read, so it has no digest to "
            "compare against the baseline; check the install before spending a licensed seat"
        )
    name = Path(fs_exe).name
    recorded = baseline.get(resolved.canonical)
    baseline_sha256 = None if recorded is None else recorded["sha256"]
    common = (
        f"executable {name} sha256 {digest}; baseline for {resolved.canonical} "
        f"{baseline_sha256 or 'not recorded'}"
    )
    if printed_build is None:
        if baseline_sha256 == digest:
            return ExecutableIdentity(
                verdict=ExecutableVerdict.TRANSFERS,
                version=resolved.canonical,
                fs_exe_name=name,
                fs_exe_sha256=digest,
                baseline_sha256=baseline_sha256,
                printed_build=None,
                registry_build=resolved.build,
                message=(
                    f"this binary IS the one recorded for FlightStream {resolved.canonical} "
                    f"(build {resolved.build or 'unrecorded'}), so the evidence gathered on "
                    f"it transfers untouched and no seat is spent. {common}"
                ),
            )
        return ExecutableIdentity(
            verdict=ExecutableVerdict.UNKNOWN,
            version=resolved.canonical,
            fs_exe_name=name,
            fs_exe_sha256=digest,
            baseline_sha256=baseline_sha256,
            printed_build=None,
            registry_build=resolved.build,
            message=(
                f"this binary is not the one recorded for FlightStream {resolved.canonical}, "
                "so nothing is known about it yet. Ask it its build number FIRST, with "
                f"`pyfs-qa probe --fs-version {resolved.canonical} --fs-exe <path> "
                "--identity-only`, and start no campaign, probe or physics run until that "
                f"number is compared with the registry's. {common}"
            ),
        )
    if resolved.build is not None and printed_build != resolved.build:
        return ExecutableIdentity(
            verdict=ExecutableVerdict.MISMATCH,
            version=resolved.canonical,
            fs_exe_name=name,
            fs_exe_sha256=digest,
            baseline_sha256=baseline_sha256,
            printed_build=printed_build,
            registry_build=resolved.build,
            message=(
                f"this binary prints build {printed_build} where the registry records "
                f"{resolved.build} for FlightStream {resolved.canonical}: it is a DIFFERENT "
                "build, so none of that version's evidence describes it and no further "
                f"licensed work starts on this identifier. {common}"
            ),
        )
    return ExecutableIdentity(
        verdict=ExecutableVerdict.CONFIRMED,
        version=resolved.canonical,
        fs_exe_name=name,
        fs_exe_sha256=digest,
        baseline_sha256=baseline_sha256,
        printed_build=printed_build,
        registry_build=resolved.build,
        message=(
            f"this binary prints build {printed_build}, the number the registry records for "
            f"FlightStream {resolved.canonical}, so the evidence transfers. {common}"
        ),
    )


# --------------------------------------------------------------------------
# PFS-2026.16: what a licence tier could falsify, derived rather than judged
# --------------------------------------------------------------------------

#: Statuses that came from RUNNING the solver. They are the only ones a
#: licence tier can falsify: a ``documented`` row rests on a manual page,
#: which no licence changes, while these two rest on a measurement taken
#: under whatever seat was checked out that day.
MEASURED_STATUSES = frozenset({Status.VERIFIED, Status.BROKEN})


@dataclass(frozen=True, kw_only=True)
class LicenceCandidate:
    """One command whose evidence a licence change could falsify.

    A CANDIDATE and not a member. Which commands belong in the subset a
    licensed seat is actually spent on is a domain judgment the author
    holds; this type is the derived input to that judgment, carrying the
    fact that put each command on the list.

    Attributes
    ----------
    command : str
        Command name.
    chapter : str
        Stem of the chapter YAML the entry came from, which is the
        chapter split this derivation groups by.
    status : str
        The measured status, ``verified`` or ``broken``.
    citation : str or None
        The committed report the measurement came from.
    inherited : bool
        True when the record was inherited from the base release rather
        than measured on the version asked about. An inherited row is a
        weaker candidate and says so rather than being dropped silently.
    reason : str
        Why this command is a candidate, in one sentence naming what
        would be lost if a licence refused it.
    """

    command: str
    chapter: str
    status: str
    citation: str | None
    inherited: bool
    reason: str


def licence_sensitive_candidates(
    version: str,
    *,
    registry: CommandRegistry | None = None,
) -> tuple[LicenceCandidate, ...]:
    """Derive the commands a licence change could falsify, for one build.

    THE RISK THIS ANSWERS is not the build number. Command evidence here
    is keyed by the canonical version string alone, so a relicensed
    binary reporting the same version is the same solver as far as every
    lookup, promotion and refusal in this package is concerned. A command
    the new licence REFUSES therefore stays marked verified on a
    measurement taken under the old one, and no guard fires.

    THE DERIVATION, and it is a deduction rather than a judgment: a
    licence changes what the solver PERMITS, so it can only falsify
    evidence that came from running the solver. A ``documented`` row
    rests on a manual page and is untouched; a ``verified`` or ``broken``
    row is a measurement taken under one seat, and it is the population
    returned here, grouped by the chapter split through
    :attr:`LicenceCandidate.chapter`.

    THE PROBE SPECIFICATIONS ARE NOT A SECOND FILTER, and the reason is
    that they cannot disagree with the first one: a ``verified`` or
    ``broken`` row is what a probe run WROTE, so every row here has a
    specification the harness can run again. That coincidence is
    asserted by a test rather than enforced here, so if the two
    populations ever drift apart the suite says so instead of this
    function silently dropping a candidate.

    WHAT THIS FUNCTION DELIBERATELY DOES NOT DO is choose the subset. Two
    things decide that and neither is mechanical: how many commands a
    seat can afford, and which capabilities a vendor plausibly gates
    behind a tier. Both are the author's domain-expert seat. This returns
    the candidates and the reason each is one; the membership is written
    where she writes it, and never inferred here.

    Parameters
    ----------
    version : str
        Version identifier whose evidence is in question.
    registry : CommandRegistry, optional, keyword-only
        Alternative database, used by tests.

    Returns
    -------
    tuple of LicenceCandidate
        Sorted by chapter and then by command, so two runs of it over
        one database produce the same list in the same order.

    Raises
    ------
    UnknownVersionError
        When ``version`` is not a registered build.

    Examples
    --------
    >>> from pyflightstream.qa.compat import licence_sensitive_candidates
    >>> candidates = licence_sensitive_candidates("26.123")
    >>> {candidate.status for candidate in candidates} <= {"verified", "broken"}
    True
    """
    resolved = resolve(version)
    database = registry or CommandRegistry.load()
    candidates: list[LicenceCandidate] = []
    for name, entry in database.commands.items():
        evidence = entry.evidence_in(resolved)
        if evidence is None or evidence.record.status not in MEASURED_STATUSES:
            continue
        status = str(evidence.record.status.value)
        verb = "inherited from" if evidence.inherited else "measured on"
        source = f"{verb} {evidence.source}"
        candidates.append(
            LicenceCandidate(
                command=name,
                chapter=entry.chapter,
                status=status,
                citation=evidence.record.report,
                inherited=evidence.inherited,
                reason=(
                    f"{status} in the {entry.chapter} chapter, {source} under the licence "
                    f"in force at the time ({evidence.record.report or 'no report cited'}); "
                    "a seat that refuses this command would leave that status asserting a "
                    "measurement the new licence contradicts"
                ),
            )
        )
    return tuple(sorted(candidates, key=lambda candidate: (candidate.chapter, candidate.command)))
