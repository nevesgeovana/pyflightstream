"""Compat reports and status promotion (SAD Sections 3.2 and 11).

Pipeline role: turns a probe run into committed evidence and the
evidence into database statuses. :func:`write_compat_report` writes the
machine-readable YAML report and its rendered Markdown table under
``reports/compat/``, one evidence line per database command of the
probed version. :func:`apply_compat` reads a committed report back and
promotes ``documented`` statuses to ``verified`` or ``broken`` in the
chapter YAML files, citing the report in each promoted entry; statuses
are never hand-edited (CLAUDE.md invariant 3), and the schema rejects a
``verified`` or ``broken`` entry without its report citation.
"""

from __future__ import annotations

import datetime
import re
from importlib import resources
from pathlib import Path

import yaml

from pyflightstream.commands import CommandEntry
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.probes import ProbeOutcome, ProbeRun

COMPAT_SCHEMA = "pyflightstream-compat-report/1"


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
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date = date or datetime.date.today().isoformat()
    stem = f"CMP-{run.version.replace('.', '')}_{date}"
    if label:
        stem += f"_{label}"
    yaml_path = out_dir / f"{stem}.yaml"
    md_path = out_dir / f"{stem}.md"
    for path in (yaml_path, md_path):
        if path.exists():
            raise FileExistsError(
                f"{path} already exists; compat reports are evidence and are never "
                "overwritten. Remove the stale file deliberately or pick another date."
            )
    counts = run.outcome_counts()
    document = {
        "schema": COMPAT_SCHEMA,
        "fs_version": run.version,
        "date": date,
        "package_version": run.package_version,
        "fs_exe": run.fs_exe_name,
        "executor": "LocalExecutor, -hidden --script (SRC-003 pp.279-280)",
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
        "through `pyfs-qa apply-compat`, never edited by hand (CLAUDE.md",
        "invariant 3). Probe scripts and logs are local scratch; this",
        "report is the committed evidence.",
        "",
        "## Setup",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Executable | {run.fs_exe_name} (local, `_private/exe/`, never committed) |",
        "| Executor | LocalExecutor, `-hidden --script` (SRC-003 pp.279-280) |",
        f"| Package | pyflightstream {run.package_version} |",
        f"| Solver identity lines | {'; '.join(run.solver_identity) or 'none captured'} |",
        "",
        "## Summary",
        "",
        f"{counts['verified']} verified, {counts['broken']} broken, {counts['unprobed']} unprobed.",
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
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema") != COMPAT_SCHEMA:
        raise QaEvidenceError(
            f"{path} is not a compat report (expected schema {COMPAT_SCHEMA!r}); "
            "apply-compat only promotes statuses from probe evidence"
        )
    return document


def apply_compat(
    report_path: str | Path,
    *,
    repo_root: str | Path = ".",
    commands_dir: str | Path | None = None,
) -> list[tuple[str, str, str]]:
    """Promote database statuses from a committed compat report.

    Every command the report judged ``verified`` or ``broken`` gets its
    version line in the chapter YAML written with the new status and the
    report cited in the ``report`` field; ``unprobed`` commands are
    untouched. A command that already records the version is rewritten
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

    Returns
    -------
    list of tuple
        One ``(command, status, chapter file name)`` per promotion.

    Raises
    ------
    ValueError
        When the report is not a compat report, when a judged command
        or its version line cannot be found, or when a rewritten entry
        fails schema validation.
    """
    report = read_compat_report(report_path)
    canonical = report["fs_version"]
    citation = Path(report_path).resolve().relative_to(Path(repo_root).resolve()).as_posix()
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
        if body["outcome"] in (ProbeOutcome.VERIFIED.value, ProbeOutcome.BROKEN.value)
    }
    promotions: list[tuple[str, str, str]] = []
    pending = dict(targets)
    for chapter_path in sorted(commands_dir.glob("*.yaml")):
        if chapter_path.name == "_meta.yaml":
            continue
        text = chapter_path.read_text(encoding="utf-8")
        names = [name for name in yaml.safe_load(text) if name in pending]
        if not names:
            continue
        for name in names:
            body = pending.pop(name)
            text = _rewrite_version_line(
                text, chapter_path.name, name, canonical, body, citation, order
            )
        chapter_path.write_text(text, encoding="utf-8")
        _validate_chapter(chapter_path, names)
        promotions.extend((name, targets[name]["outcome"], chapter_path.name) for name in names)
    if pending:
        raise QaEvidenceError(
            f"report judges {', '.join(sorted(pending))} but no chapter file defines "
            "them; the report and the database have diverged"
        )
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
        ordering authority for that tree (CLAUDE.md invariant 4).

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
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    return {
        str(entry["canonical"]): position
        for position, entry in enumerate(meta.get("versions") or [])
    }


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
        raise ValueError(f"{chapter}: command block {name} not found")

    status = body["outcome"]
    fields = f'status: {status}, report: "{citation}"'
    if status == ProbeOutcome.BROKEN.value:
        fields += f', note: "{_one_line_note(str(body.get("detail", "")))}"'

    recorded = [
        (index, match.group(1), match.group(2))
        for index in range(start, end)
        if (match := _VERSION_LINE.match(lines[index])) is not None
    ]
    for index, indent, recorded_canonical in recorded:
        if recorded_canonical == canonical:
            lines[index] = f'{indent}"{canonical}": {{{fields}}}'
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
            raise ValueError(
                f"{chapter}: {name} already records {canonical!r} as a multi-line "
                "block, which this promotion cannot rewrite without discarding the "
                "note or argument override the block carries. Fold the new status "
                f"and report into that block by hand, citing {citation!r}, and leave "
                "the rest of it alone; the status still comes from a committed "
                "report, which is what invariant 3 asks."
            )

    if not recorded:
        raise ValueError(
            f"{chapter}: {name} records no version as a single-line entry, so this "
            f"promotion has no line to copy the shape of the new {canonical!r} entry "
            f"from. Rewrite the versions: block of {name} as one line per version "
            "(for example '\"26.120\": {status: documented}') and re-run "
            "pyfs-qa apply-compat; a status is promoted from a committed report, "
            "never hand-edited (CLAUDE.md invariant 3)."
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
    lines.insert(insert_at, f'{indent}"{canonical}": {{{fields}}}')
    return "\n".join(lines) + "\n"


def _validate_chapter(chapter_path: Path, names: list[str]) -> None:
    """Re-validate the rewritten entries against the command schema."""
    data = yaml.safe_load(chapter_path.read_text(encoding="utf-8"))
    chapter = chapter_path.name.removesuffix(".yaml")
    for name in names:
        CommandEntry(name=name, chapter=chapter, **data[name])
