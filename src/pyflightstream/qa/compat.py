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
from pyflightstream.qa.probes import ProbeOutcome, ProbeRun

COMPAT_SCHEMA = "pyflightstream-compat-report/1"


def write_compat_report(
    run: ProbeRun, out_dir: str | Path, *, date: str | None = None
) -> tuple[Path, Path]:
    """Write one probe run as a compat report pair (YAML plus Markdown).

    The YAML file is the machine-readable evidence ``apply_compat``
    reads; the Markdown file renders the same content as a table for
    review. Both share the stem ``CMP-<version digits>_<date>``.
    Existing report files are never overwritten: evidence supersedes
    evidence only through a new, dated report.

    Parameters
    ----------
    run : ProbeRun
        The probe run to record.
    out_dir : str or Path
        Target directory, normally ``reports/compat/``.
    date : str, optional
        ISO date stamped into the report; defaults to today.

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
        raise ValueError(
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
    version line in the chapter YAML rewritten to the new status with
    the report cited in the ``report`` field; ``unprobed`` commands are
    untouched. The edit is line-level on the flow-mapping version
    lines, so chapter comments and layout survive; a version entry
    spanning several lines is refused loudly rather than mangled.

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
            text = _rewrite_version_line(text, chapter_path.name, name, canonical, body, citation)
        chapter_path.write_text(text, encoding="utf-8")
        _validate_chapter(chapter_path, names)
        promotions.extend((name, targets[name]["outcome"], chapter_path.name) for name in names)
    if pending:
        raise ValueError(
            f"report judges {', '.join(sorted(pending))} but no chapter file defines "
            "them; the report and the database have diverged"
        )
    return promotions


def _rewrite_version_line(
    text: str, chapter: str, name: str, canonical: str, body: dict, citation: str
) -> str:
    """Rewrite one command's version line to its promoted status."""
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
    pattern = re.compile(rf'^(\s+)"{re.escape(canonical)}":\s*\{{.*\}}\s*$')
    for index in range(start, end):
        match = pattern.match(lines[index])
        if match is None:
            continue
        status = body["outcome"]
        fields = f'status: {status}, report: "{citation}"'
        if status == ProbeOutcome.BROKEN.value:
            note = str(body.get("detail", "")).replace('"', "'").replace("\n", " ")[:140]
            fields += f', note: "{note}"'
        lines[index] = f'{match.group(1)}"{canonical}": {{{fields}}}'
        return "\n".join(lines) + "\n"
    raise ValueError(
        f"{chapter}: no single-line version entry for {canonical!r} in {name}; "
        "promote this entry manually reviewable or normalize the block first"
    )


def _validate_chapter(chapter_path: Path, names: list[str]) -> None:
    """Re-validate the rewritten entries against the command schema."""
    data = yaml.safe_load(chapter_path.read_text(encoding="utf-8"))
    chapter = chapter_path.name.removesuffix(".yaml")
    for name in names:
        CommandEntry(name=name, chapter=chapter, **data[name])
