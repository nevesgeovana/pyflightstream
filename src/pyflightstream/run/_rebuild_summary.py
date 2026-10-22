"""The report lines of ``pyfs-matrix restore`` and ``pyfs-matrix rebuild``.

Pipeline role: the text a restore or a rebuild entry becomes on the terminal.
The entries are made by :func:`pyflightstream.run.records.restore` and
:func:`pyflightstream.run._rebuild.rebuild`; this module only words them, and
:mod:`pyflightstream.run._rebuild` re-exports both public names unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: The word every rebuilt record's warning starts with.
REBUILT = "REBUILT"

#: What to do about a row this version cannot mint again (FR-858).
MINT_REMEDY = (
    "rebuild with the pyflightstream version that ran it, or pass the matrix revision that "
    "ran (CLI: --matrix FILE)"
)

NOT_RECOVERABLE_NOTE = (
    "do not run `pyfs-matrix run --resume` on a refused simulation: with no record, the "
    "resume takes it as never run and runs it again"
)


def _restore_lines(entry: Mapping[str, Any]) -> list[str]:
    """Return the lines ``pyfs-matrix restore`` prints for its entry."""
    lines = [
        f"restore {entry['kind']}: {entry['source']} -> {entry['target']} (stamp {entry['stamp']})",
        f"  stamps available: {', '.join(entry['stamps_available'])}",
    ]
    if "records" in entry:
        lines.append(f"  the archived manifest holds {entry['records']} record(s)")
    if entry["same"]:
        lines.append("  the current file already holds these bytes; nothing to do")
    elif entry["applied"]:
        kept = entry["archived_as"]
        lines.append("  restored" + (f"; the current file was archived as {kept}" if kept else ""))
    else:
        lines.append("  preview only: add --apply to restore it")
    return lines


def summary_lines(entry: Mapping[str, Any]) -> list[str]:
    """Return the lines ``pyfs-matrix restore`` and ``rebuild`` print for an entry.

    The entry is what :func:`~pyflightstream.run.records.restore` or
    :func:`rebuild` returned: the lines say what was, or would be, written,
    and name every refusal. A rebuild's lines end with the count rebuilt and
    the count refused (FR-858).
    """
    if "kind" in entry:
        return _restore_lines(entry)
    lines: list[str] = []
    rebuilt, refused = entry["rebuilt"], entry["refused"]
    lines.append(
        f"rebuild: {len(rebuilt)} record(s) rebuilt with pyflightstream "
        f"{entry['package_version']}, {len(refused)} simulation(s) refused"
    )
    for row in rebuilt:
        lines.append(f"  sim_{row['sim']}: {REBUILT} {row['status']} {row['run_id']}")
    waiting = set(entry["waiting_for_matrix"])
    for sim, reason in refused.items():
        # A simulation no matrix row names is listed once, as waiting for the
        # matrix revision that ran, with the reason that names the remedy.
        label = "WAITING FOR THE MATRIX THAT RAN" if sim in waiting else "NOT RECOVERABLE"
        lines.append(f"  sim_{sim}: {label}: {reason}")
    for run_id in entry["submitted"]:
        lines.append(f"  SUBMITTED, for pyfs-matrix collect: {run_id}")
    for run_id in entry["never_ran"]:
        lines.append(f"  never ran (no datapoint folder), no record: {run_id}")
    for line in entry["notes"]:
        lines.append(f"  note: {line}")
    for line in entry.get("changes", [])[:30]:
        lines.append(f"  the workspace changed during the rebuild: {line}")
    if entry["applied"]:
        kept = entry["archived_as"]
        lines.append(
            f"  wrote {entry['written']}"
            + (f"; the previous runs.json was archived as {kept}" if kept else "")
        )
    else:
        lines.append(f"  preview only: add --apply to write {entry['target']}")
    lines.append(f"rebuild: {len(rebuilt)} rebuilt, {len(refused)} refused")
    return lines
