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
older report cannot revert a status established by a later run.
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

import pyflightstream._textio as _textio
from pyflightstream._digest import optional_file_sha256
from pyflightstream._tokens import NOT_APPLICABLE
from pyflightstream._yamlflow import flow_mapping
from pyflightstream.commands import CommandEntry, CommandRegistry, Status
from pyflightstream.qa._reanalysis import _citation, _withdrawals, _write_reanalysis
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.probes import ProbeOutcome, ProbeRun
from pyflightstream.qa.reports import (
    load_yaml,
    public_executable_identity,
    refuse_existing_report,
    report_paths,
    resolve_report_date,
)
from pyflightstream.run import describe_invocation
from pyflightstream.versions import resolve

__all__ = [
    "COMPAT_SCHEMA",
    "CORROBORATED",
    "EXECUTABLE_BASELINE_REPORT",
    "ExecutableIdentity",
    "ExecutableVerdict",
    "Judgment",
    "LicenceCandidate",
    "MEASURED_STATUSES",
    "PROMOTABLE_OUTCOMES",
    "WITHHELD_DIGEST",
    "apply_compat",
    "apply_reanalysis",
    "classify_executable",
    "compat_report_paths",
    "contradicting_evidence",
    "licence_sensitive_candidates",
    "read_compat_report",
    "record_unprobed_build",
    "read_compat_reports",
    "read_executable_baseline",
    "resolve_commands_dir",
    "write_compat_report",
    "write_reanalysis",
]

COMPAT_SCHEMA = "pyflightstream-compat-report/1"


def compat_report_paths(
    out_dir: str | Path,
    *,
    version: str,
    date: str | None = None,
    label: str | None = None,
) -> tuple[Path, Path]:
    """Return where a compat report for one run WOULD be written.

    Derive the paths before spending a licensed solver seat so a caller can
    refuse an existing report stem before launching probes. The writer uses
    the same paths, avoiding a late collision that would discard run results.

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
        vendor release name shared by several. The stem's build key resolves
        through the registry. ``pyfs-qa`` resolves first, so these errors
        surface here only for direct callers.
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
        # The BUILD, never the digest (NFR-31): the report is committed.
        "fs_exe_sha256": public_executable_identity(run.fs_exe_sha256, run.version),
        "executor": describe_invocation(run.executor),
        "solver_identity": list(run.solver_identity),
        "summary": counts,
        "commands": {
            result.command: {
                "outcome": result.outcome.value,
                "detail": result.detail,
                # PFS-2003.10.03: what the run read, apart from what the
                # specification expected; None is a missing observation.
                "expected": result.expected or None,
                "observation": result.observation,
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
    _textio.write_text(yaml_path, yaml.safe_dump(document, sort_keys=False, width=100))
    _textio.write_text(md_path, _render_markdown(run, date, counts))
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
        f"(sha256 {public_executable_identity(run.fs_exe_sha256, run.version) or 'not recorded'}, "
        "local, `_private/exe/`, never committed) |",
        f"| Executor | {describe_invocation(run.executor, markdown=True)} |",
        f"| Package | pyflightstream {run.package_version} |",
        f"| Solver identity lines | {'; '.join(run.solver_identity) or 'none captured'} |",
        "",
        "## Summary",
        "",
        ", ".join(f"{count} {name}" for name, count in counts.items()) + ".",
        "",
        "## Evidence per command",
        "",
        "| Command | Outcome | Evidence | Expected effect | Observation |",
        "|---|---|---|---|---|",
    ]
    for result in run.results:
        detail = result.detail.replace("|", "\\|")
        # PFS-2003.10.03. The observation is the run's reading or the word
        # missing, never the specification's expectation in its place.
        expected = (result.expected or NOT_APPLICABLE).replace("|", "\\|")
        observation = (
            "missing" if result.observation is None else result.observation.replace("|", "\\|")
        )
        lines.append(
            f"| {result.command} | {result.outcome.value} | {detail} | {expected} | {observation} |"
        )
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

    The reader itself is :func:`pyflightstream.qa.reports.load_yaml`
    (PFS-2102.010), shared with the physics evidence path.
    """
    return load_yaml(path, consequence="nothing was written")


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
    QaEvidenceError
        When the file does not carry the compat report schema marker
        (a ``ValueError``).
    """
    document = _load_yaml(Path(path))
    if not isinstance(document, dict) or document.get("schema") != COMPAT_SCHEMA:
        raise QaEvidenceError(
            f"{path} is not a compat report (expected schema {COMPAT_SCHEMA!r}); "
            "apply-compat only promotes statuses from probe evidence"
        )
    # PFS-2102.030. A hand-edited or partial report reached apply_compat
    # and the CLI as a KeyError, TypeError or AttributeError.
    if not isinstance(document.get("fs_version"), str):
        raise QaEvidenceError(
            f"{path} carries no fs_version string (found {document.get('fs_version')!r}); "
            "a compat report names the version it judged"
        )
    commands = document.get("commands")
    if not isinstance(commands, dict):
        raise QaEvidenceError(
            f"{path} carries no commands mapping (found {type(commands).__name__}); a compat "
            "report maps each judged command to its outcome"
        )
    for name, body in commands.items():
        if not isinstance(body, dict) or not isinstance(body.get("outcome"), str):
            raise QaEvidenceError(
                f"{path}: commands.{name} is not a mapping carrying an outcome (found "
                f"{body!r}); nothing was written"
            )
    return document


def _compare_compat_reports(report_a: str | Path, report_b: str | Path) -> dict[str, Any]:
    """Compare recorded command evidence while retaining each executable's identity.

    Equal build labels do not merge the two sides. This is a read-only comparison
    of reports, not a command-status promotion or a new solver measurement.

    Parameters
    ----------
    report_a, report_b : str or Path
        Baseline and comparison compatibility reports. Each must record its
        executable name and SHA-256 identity.

    Returns
    -------
    dict
        Separate ``a`` and ``b`` identity blocks and a ``commands`` mapping.
        Each command retains both evidence rows (None when absent); ``changed``
        compares outcome, signals and observation, excluding execution timing.

    Raises
    ------
    QaEvidenceError
        A report is invalid or lacks a recorded executable identity.

    Examples
    --------
    Compare retained reports without running either executable:

    >>> comparison = _compare_compat_reports("baseline.yaml", "candidate.yaml")  # doctest: +SKIP
    >>> comparison["commands"]["PRINT"]["changed"]  # doctest: +SKIP
    False
    """
    result: dict[str, Any] = {}
    documents = []
    for side, path in (("a", report_a), ("b", report_b)):
        document = read_compat_report(path)
        for key in ("fs_exe", "fs_exe_sha256"):
            if not isinstance(document.get(key), str) or not document[key].strip():
                raise QaEvidenceError(
                    f"{path}: {key} is missing; compare reports with recorded executable "
                    "identities instead of inferring identity from a build label"
                )
        if re.fullmatch(r"[0-9a-fA-F]{64}", document["fs_exe_sha256"]) is None:
            raise QaEvidenceError(
                f"{path}: fs_exe_sha256 is not a recorded SHA-256 digest; use private "
                "evidence with executable digests, not a withheld build-only identity"
            )
        result[side] = {key: document[key] for key in ("fs_version", "fs_exe", "fs_exe_sha256")}
        result[side]["report"] = Path(path).as_posix()
        documents.append(document["commands"])
    before, after = documents
    result["commands"] = {}
    for command in sorted(before.keys() | after.keys()):
        a, b = before.get(command), after.get(command)
        changed = (
            a is None
            or b is None
            or any(a.get(key) != b.get(key) for key in ("outcome", "signals", "observation"))
        )
        result["commands"][command] = {"a": a, "b": b, "changed": changed}
    return result


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
_EDITION_PAGE = re.compile(r"FSM-(?:\d{2}\.\d{3}|TEST)\s+pp?\.", re.IGNORECASE)


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
    outcome : ProbeOutcome
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

    def __post_init__(self) -> None:
        """Normalize accepted strings to the public outcome vocabulary."""
        try:
            object.__setattr__(self, "outcome", ProbeOutcome(self.outcome))
        except ValueError as error:
            raise QaEvidenceError(
                f"judgment outcome {self.outcome!r} is unknown; use a ProbeOutcome value"
            ) from error


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

    Raises
    ------
    QaEvidenceError
        If ``reports_dir`` is given explicitly and is not a directory.
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
    withdrawn: set[tuple[str, str, str]] = set()
    if not reports_dir.is_dir():
        # An absent default is the first-report case and yields an empty index.
        # An explicitly named missing path is refused here for every caller:
        # missing evidence must not be interpreted as permission to promote.
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
        withdrawn.update(_withdrawals(document, root))
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
                        outcome=ProbeOutcome(outcome),
                        date=date,
                        report=citation,
                    )
                )
    return {
        key: tuple(sorted(active, key=lambda j: j.date))
        for key, value in index.items()
        if (active := [j for j in value if (*key, j.report) not in withdrawn])
    }


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


def resolve_commands_dir(repo_root: str | Path, commands_dir: str | Path | None = None) -> Path:
    """Return the command database a promotion writes, refusing one outside the repository.

    PFS-2102.032, PFS-2088.016: anchor command data, citations and the
    supersession index on repo_root so installed-package data or another
    editable checkout cannot receive this repository's promotions.

    Parameters
    ----------
    repo_root : str or Path
        The repository root.
    commands_dir : str or Path, optional
        An explicit chapter directory. When left out,
        ``<repo_root>/src/pyflightstream/commands`` if it exists, else
        the installed package's data.

    Returns
    -------
    Path
        The resolved chapter directory, under ``repo_root``.

    Raises
    ------
    QaEvidenceError
        If the directory is not under ``repo_root``.
    """
    root = Path(repo_root).resolve()
    if commands_dir is None:
        candidate = root / "src" / "pyflightstream" / "commands"
        if candidate.is_dir():
            commands_dir = candidate
        else:
            commands_dir = Path(str(resources.files("pyflightstream.commands")))
    resolved = Path(commands_dir).resolve()
    if not resolved.is_relative_to(root):
        raise QaEvidenceError(
            f"the command database {resolved} is not under the repository root {root}, so "
            "the promotions would land in a tree the report citation does not name (an "
            "installed copy, or another checkout); nothing was written. Pass the "
            "repository as repo_root (CLI: --root), or a chapter directory under it as "
            "commands_dir (CLI: --commands-dir)"
        )
    return resolved


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
        Chapter YAML directory, which must lie under ``repo_root``;
        defaults to ``<repo_root>/src/pyflightstream/commands`` when it
        exists, else the installed ``pyflightstream.commands`` package
        data (:func:`resolve_commands_dir`). Tests point it at a copy.
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
        When the report is not a compat report, when it or the command
        database lies outside ``repo_root``, when it names an unregistered version, when an
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
    commands_dir = resolve_commands_dir(root, commands_dir)
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

    _refuse_withdrawn_promotion(citation, canonical, targets, reports_dir, root)
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
    rewritten: list[tuple[Path, str, str]] = []
    for chapter_path in sorted(commands_dir.glob("*.yaml")):
        if chapter_path.name == "_meta.yaml":
            continue
        text = chapter_path.read_text(encoding="utf-8")
        original = text
        names = [name for name in _load_yaml(chapter_path) if name in pending]
        if not names:
            continue
        outcomes: dict[str, str] = {}
        for name in names:
            body = pending.pop(name)
            before = text
            text = _rewrite_version_line(
                text, chapter_path.name, name, canonical, body, citation, order
            )
            # A verified row that kept its earlier citation leaves the text
            # as it was; the report corroborates it and promotes nothing.
            outcomes[name] = CORROBORATED if text == before else str(body["outcome"])
        _validate_chapter(chapter_path.name, text, names)
        rewritten.append((chapter_path, original, text))
        promotions.extend((name, outcomes[name], chapter_path.name) for name in names)
    if pending:
        raise QaEvidenceError(
            f"report judges {', '.join(sorted(pending))} but no chapter file defines "
            "them; the report and the database have diverged, and nothing was written"
        )
    _write_changed(rewritten)
    return promotions


def record_unprobed_build(
    report_path: str | Path,
    command: str,
    *,
    manual_ref: str,
    repo_root: str | Path,
    commands_dir: str | Path | None = None,
) -> None:
    """Record direct inconclusive evidence instead of inherited verification.

    This explicit maintenance route adds a documented row only where the build
    has no row and no committed measured verdict. It never changes a measured
    record and never interprets unprobed as a broken command.

    Parameters
    ----------
    report_path : str or Path
        Committed report containing an unprobed outcome for the command.
    command : str
        One command to reconcile; other report entries are not applied.
    manual_ref : str
        Page citation of this build's manual, checked by the caller.
    repo_root : str or Path
        Repository containing both the report and command chapters.
    commands_dir : str or Path, optional
        Chapter directory under the repository.

    Raises
    ------
    QaEvidenceError
        If evidence is not inconclusive, a direct record or measured verdict
        exists, the manual citation names another build, or paths are invalid.
    """
    report = read_compat_report(report_path)
    canonical = report["fs_version"]
    root = Path(repo_root).resolve()
    try:
        citation = Path(report_path).resolve().relative_to(root).as_posix()
    except ValueError:
        raise QaEvidenceError("the unprobed report must be inside repo_root") from None
    if report["commands"].get(command, {}).get("outcome") != "unprobed":
        raise QaEvidenceError(f"{command}: the report must record unprobed")
    if not manual_ref.startswith(f"FSM-{canonical} p."):
        raise QaEvidenceError(f"{command}: cite a page of FSM-{canonical}")
    if read_compat_reports(repo_root=root).get((command, canonical)):
        raise QaEvidenceError(f"{command}: explicit measured evidence requires reconciliation")
    directory = resolve_commands_dir(root, commands_dir)
    order = _release_order(directory)
    if canonical not in order:
        raise QaEvidenceError(f"unregistered build {canonical}")
    for path in sorted(directory.glob("*.yaml")):
        entries = _load_yaml(path)
        if command in entries:
            _record_unprobed_row(
                path,
                entries[command],
                command,
                canonical,
                citation=citation,
                manual_ref=manual_ref,
                order=order,
            )
            return
    raise QaEvidenceError(f"unknown command {command}")


def _record_unprobed_row(
    path: Path,
    entry: dict,
    command: str,
    canonical: str,
    *,
    citation: str,
    manual_ref: str,
    order: dict[str, int],
) -> None:
    """Validate and atomically add the one explicit inconclusive row."""
    if canonical in entry.get("versions", {}):
        raise QaEvidenceError(f"{command}: an explicit build record already exists")
    original = path.read_text(encoding="utf-8")
    updated = _rewrite_version_line(
        original,
        path.name,
        command,
        canonical,
        {
            "outcome": "documented",
            "detail": (
                f"{manual_ref}; unprobed on this build; direct inconclusive evidence "
                "takes precedence over inherited verification."
            ),
        },
        citation,
        order,
    )
    _validate_chapter(path.name, updated, [command])
    _write_changed([(path, original, updated)])


def _write_changed(rewritten: list[tuple[Path, str, str]]) -> None:
    """Write each chapter whose text changed; a corroborated chapter is left alone.

    Reading a chapter folds CRLF into LF, so writing unchanged content back would
    change every line end of a checkout that keeps CRLF.
    """
    for chapter_path, original, text in rewritten:
        if text != original:
            _textio.write_text(chapter_path, text)


#: The outcome apply_compat reports for a verified row whose earlier
#: citation it kept (see _rewritten_flow_entry): not a promotion, and the
#: caller prints it as such.
CORROBORATED = "corroborated"

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


def _parsed_flow_entry(line: str, chapter: str, name: str, canonical: str) -> tuple[str, dict]:
    """Return the indentation and the parsed mapping of one single-line version entry."""
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
    return indent, existing


def _rewritten_flow_entry(
    line: str,
    chapter: str,
    name: str,
    canonical: str,
    citation: str,
    body: dict,
) -> str:
    """Rewrite one single-line version entry, KEEPING the keys it already has.

    Replace only the keys owned by promotion. Carry through note,
    successor, probe_ref and inline args overrides: dropping them can
    leave valid YAML while losing evidence or changing grammar.

    Preserve notes just as for block-form rows: per-edition citations belong
    to the existing evidence and must not disappear during promotion.

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
    indent, existing = _parsed_flow_entry(line, chapter, name, canonical)

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
        if existing.get("status") == status and existing.get("report") == citation:
            # The row was edited deliberately from THIS report already, as the
            # refusal below asks: its page note is the reading that edit made.
            # Re-applying the report (for the other commands it judges) has
            # nothing to decide about this one and leaves the line as it is.
            return line
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

    # Keep a verified row's existing committed report when an incoming run
    # corroborates it. A run-level outcome must not replace discriminating
    # per-command evidence. Report this as corroborated, not promoted.
    if (
        status == ProbeOutcome.VERIFIED.value
        and existing.get("status") == ProbeOutcome.VERIFIED.value
        and existing.get("report")
        and existing.get("report") != citation
        and not body.get("reconciles_withdrawal")
    ):
        return line

    # The keys this promotion OWNS are rendered exactly as they were
    # before this function existed, because the shape of a promoted line
    # is pinned by tests and by the whole database's worth of precedent. Only the
    # carried-through keys are new output, and they go after.
    owned = {"status", "report"}
    pairs: dict[str, object] = {"status": status, "report": citation}
    if status in (ProbeOutcome.BROKEN.value, ProbeOutcome.REMOVED.value, "documented"):
        # A removed row REQUIRES a note (the model refuses one without),
        # because the status alone cannot say which of the three ways it
        # arrived; the probe detail says it was measured.
        pairs["note"] = _promoted_note(existing.get("note"), body.get("detail", ""), status)
        owned.add("note")
    pairs.update({key: value for key, value in existing.items() if key not in owned})
    return f'{indent}"{canonical}": {_flow_mapping(pairs)}'


def _promoted_note(previous: object, detail: object, status: str) -> str:
    """Preserve edition evidence and keep repeated broken promotions idempotent."""
    note = _one_line_note(str(detail))
    previous = str(previous or "").strip()
    if previous == note or previous.endswith(f"Probe: {note}"):
        return previous
    if status == "documented" and _EDITION_PAGE.search(previous):
        return note if previous.startswith(note) else f"{note} Prior edition evidence: {previous}"
    if status == ProbeOutcome.BROKEN.value and previous:
        return f"{previous} Probe: {note}"
    return note


#: Shared promoted-value renderer from pyflightstream._yamlflow, below every
#: layer so QA and manual-registration writers can both use it. Keep this
#: alias for callers of this module.
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

    Flow and block version mappings are both supported. A block promotion
    preserves its grammar and unchanged notes; insertion follows complete
    version mappings rather than splitting a multiline row.
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
    if status in (ProbeOutcome.BROKEN.value, ProbeOutcome.REMOVED.value, "documented"):
        pairs["note"] = _one_line_note(str(body.get("detail", "")))

    recorded = [
        (index, match.group(1), match.group(2))
        for index in range(start, end)
        if (match := re.match(r'^( {4})"([^"]+)":', lines[index])) is not None
    ]

    for index, indent, recorded_canonical in recorded:
        if recorded_canonical != canonical:
            continue
        if _VERSION_LINE.match(lines[index]):
            lines[index] = _rewritten_flow_entry(
                lines[index], chapter, name, canonical, citation, body
            )
        else:
            stop = _version_row_end(lines, index, end)
            existing = yaml.safe_load("\n".join(lines[index:stop]))[canonical]
            synthetic = f'{indent}"{canonical}": {_flow_mapping(existing)}'
            rewritten = _rewritten_flow_entry(synthetic, chapter, name, canonical, citation, body)
            _, updated = _parsed_flow_entry(rewritten, chapter, name, canonical)
            if existing == updated:
                return text
            _rewrite_block_fields(lines, index, stop, existing, updated)
        return "\n".join(lines) + "\n"

    if not recorded:
        raise QaEvidenceError(f"{chapter}: {name} records no version mapping to extend")

    position = order[canonical]
    indent = recorded[0][1]
    insert_at = next(
        (
            index
            for index, _, recorded_canonical in recorded
            if order.get(recorded_canonical, -1) > position
        ),
        _version_row_end(lines, recorded[-1][0], end),
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
        # Wrap an unparsable rewrite in QaEvidenceError so the CLI handles it
        # through the promotion refusal contract.
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

#: Where the executables in hand are recorded by build, relative to the
#: repository root, their digests withheld (NFR-31). A narrative report
#: rather than a machine series because CMP, PHY and DRF each assert that a
#: solver ran, and this one is measured by hashing files with the solver
#: never started.
EXECUTABLE_BASELINE_REPORT = "reports/RPT-032_executable-identity-baseline_2026-08-19.md"

#: How a baseline cell begins when the public tree withholds that build's
#: digest (NFR-31), as in ``withheld; build 8172026``. The row is read with
#: an empty digest, so the build, not the bytes, identifies that executable;
#: a local, uncommitted copy of the table that keeps the digest is read by
#: the same function and compares bytes again.
WITHHELD_DIGEST = "withheld"


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


def _baseline_digest(cell: str, *, path: Path, version: str) -> str:
    """Return a baseline cell's digest, or ``""`` when it is withheld (NFR-31)."""
    digest = cell.strip("`").lower()
    if digest.startswith(WITHHELD_DIGEST):
        return ""
    if len(digest) != 64 or set(digest) - set("0123456789abcdef"):
        raise QaEvidenceError(
            f"{path} records {digest!r} for {version}, which is not a sha256; a "
            "baseline digest is 64 hexadecimal characters and is measured, never typed"
        )
    return digest


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
        ``names`` and ``bytes`` as read from the row. ``sha256`` is the
        empty string for a row whose cell begins with
        :data:`WITHHELD_DIGEST` (NFR-31).

    Raises
    ------
    QaEvidenceError
        When the file carries no table with the expected labels, when a
        digest is neither withheld nor 64 hexadecimal characters, or when one version is
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
        digest = _baseline_digest(row["sha256"], path=path, version=version)
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
    baseline_sha256 = (recorded or {}).get("sha256") or None
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
                (
                    f"the public baseline withholds the digest of FlightStream "
                    f"{resolved.canonical} (NFR-31), so this binary is compared by its build "
                    "(a local baseline that keeps the digest compares bytes instead). "
                    if recorded is not None and baseline_sha256 is None
                    else f"this binary is not the one recorded for FlightStream "
                    f"{resolved.canonical}, so nothing is known about it yet. "
                )
                + "Ask it its build number FIRST, with "
                f"`pyfs-qa probe --fs-version {resolved.canonical} --fs-exe <path> "
                "--identity-only`, and start no campaign, probe or physics run until that "
                f"number is compared with the registry's. {common}"
            ),
        )
    if resolved.build is None:
        # PFS-2102.003. A registry with no build recorded has no number to
        # match, so CONFIRMED named a match that did not exist.
        return ExecutableIdentity(
            verdict=ExecutableVerdict.UNKNOWN,
            version=resolved.canonical,
            fs_exe_name=name,
            fs_exe_sha256=digest,
            baseline_sha256=baseline_sha256,
            printed_build=printed_build,
            registry_build=None,
            message=(
                f"this binary prints build {printed_build}, and the registry holds no build "
                f"for FlightStream {resolved.canonical} yet, so there is nothing to compare "
                "it with. Record the build from a committed identity report "
                f"(`pyfs-qa probe --fs-version {resolved.canonical} --fs-exe <path> "
                "--identity-only`, then its solver_identity into the build field of "
                f"commands/_meta.yaml) before any evidence is said to transfer. {common}"
            ),
        )
    if printed_build != resolved.build:
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
    licensed seat is actually spent on is a domain judgment the owner
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
    behind a tier. Both are the domain-expert seat's. This returns
    the candidates and the reason each is one; the membership is written
    where that seat records it, and never inferred here.

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


def _version_row_end(lines: list[str], index: int, end: int) -> int:
    for following in range(index + 1, end):
        line = lines[following]
        if (
            line.strip()
            and not line.lstrip().startswith("#")
            and len(line) - len(line.lstrip()) <= 4
        ):
            return following
    return end


def _rewrite_block_fields(
    lines: list[str],
    index: int,
    stop: int,
    existing: dict,
    updated: dict,
) -> None:
    """Replace changed evidence fields while retaining untouched grammar text."""
    fields = [
        (at, match.group(1))
        for at in range(index + 1, stop)
        if (match := re.match(r"^      ([a-z_]+):", lines[at])) is not None
    ]
    # Replace only owned values, from bottom to top; grammar, comments and
    # multiline edition notes that did not change retain their exact text.
    for position in range(len(fields) - 1, -1, -1):
        at, key = fields[position]
        if existing.get(key) == updated.get(key):
            continue
        finish = fields[position + 1][0] if position + 1 < len(fields) else stop
        lines[at:finish] = ["      " + _flow_mapping({key: updated[key]})[1:-1]]
    missing = {key: value for key, value in updated.items() if key not in existing}
    for key, value in reversed(list(missing.items())):
        lines.insert(index + 1, "      " + _flow_mapping({key: value})[1:-1])


def write_reanalysis(
    source: str | Path,
    explanations: Mapping[str, str],
    *,
    repo_root: str | Path,
    date: str,
    label: str,
    withdraw: bool = True,
) -> tuple[Path, Path]:
    """Write dated analysis preserving the source execution, optionally withdrawing judgment.

    Each named command requires an explanation. By default this withdraws a
    judgment while preserving its observations; withdraw=False adds an analysis
    note without changing that judgment. It launches nothing. The original report
    UTF-8 text with LF line ends is pinned so that checkout line endings do not
    change provenance and later content edits cannot silently change it.
    Apply the result explicitly with :func:`apply_reanalysis` after review.

    Parameters
    ----------
    source : str or Path
        Original committed compatibility report, inside the repository.
    explanations : mapping of str to str
        Commands to withdraw and the reason for each withdrawal.
    repo_root : str or Path
        Repository containing the original report and output directory.
    date : str
        ISO analysis date, later than the original report.
    label : str
        Distinguishing suffix for the analysis report filenames.
    withdraw : bool, optional
        Withdraw the source judgment by default. False records an unprobed
        analysis note while retaining the source judgment and database status.

    Returns
    -------
    tuple of Path
        New YAML report and rendered Markdown report, respectively.

    Raises
    ------
    QaEvidenceError
        If provenance, dates, explanations or report destinations are invalid.
    """
    return _write_reanalysis(
        source, explanations, repo_root=repo_root, date=date, label=label, withdraw=withdraw
    )


def apply_reanalysis(report_path: str | Path, *, repo_root: str | Path) -> list[str]:
    """Reconcile withdrawn judgments through validated chapter rewrites.

    Independent measured evidence remains authoritative. Where none remains,
    the row records direct inconclusive evidence as documented, never verified
    or broken. The original report remains on disk and cannot be reapplied.

    Parameters
    ----------
    report_path : str or Path
        Explicit dated withdrawal report to apply.
    repo_root : str or Path
        Repository holding the reports and command chapters.

    Returns
    -------
    list of str
        Sorted command names whose judgments were reconciled.

    Raises
    ------
    QaEvidenceError
        If source evidence changed, a command is unknown or validation fails.
    """
    root = Path(repo_root).resolve()
    report = read_compat_report(report_path)
    citation = _citation(Path(report_path).resolve(), root)
    withdrawn = _withdrawals(report, root)
    names = {name for name, _, _ in withdrawn}
    if names != set(report["commands"]):
        raise QaEvidenceError("every reanalysis command must withdraw its own source judgment")
    directory = resolve_commands_dir(root)
    order = _release_order(directory)
    version = report["fs_version"]
    judgments = read_compat_reports(repo_root=root)
    pending = set(names)
    rewritten = []
    for path in sorted(directory.glob("*.yaml")):
        entries = _load_yaml(path)
        selected = sorted(pending.intersection(entries))
        if not selected:
            continue
        original = text = path.read_text(encoding="utf-8")
        for name in selected:
            remaining = judgments.get((name, version), ())
            source = remaining[-1].report if remaining else citation
            body = (
                read_compat_report(root / source)["commands"][name]
                if remaining
                else dict(
                    outcome="documented",
                    detail="direct inconclusive evidence; " + report["commands"][name]["detail"],
                )
            )
            body = {**body, "reconciles_withdrawal": True}
            text = _rewrite_version_line(text, path.name, name, version, body, source, order)
            pending.remove(name)
        _validate_chapter(path.name, text, selected)
        rewritten.append((path, original, text))
    if pending:
        raise QaEvidenceError(f"unknown commands in reanalysis: {sorted(pending)}")
    _write_changed(rewritten)
    return sorted(names)


def _refuse_withdrawn_promotion(
    citation: str,
    version: str,
    targets: Mapping[str, Any],
    reports_dir: str | Path | None,
    root: Path,
) -> None:
    """Prevent reapplying precisely the judgments an explicit review withdrew."""
    directory = Path(reports_dir) if reports_dir is not None else root / "reports" / "compat"
    for path in directory.glob("*.yaml"):
        document = _load_yaml(path)
        if not isinstance(document, dict) or document.get("analysis_only") is not True:
            continue
        withdrawn = _withdrawals(document, root)
        if any((name, version, citation) in withdrawn for name in targets):
            raise QaEvidenceError(f"{citation}: judgment withdrawn by {path.name}; nothing written")
