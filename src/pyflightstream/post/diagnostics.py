"""Read-only Markdown diagnostics and concise warning presentation.

``render_post_diagnostics`` reads existing post logs only. It neither executes
post stages nor writes products, guides, manifests, or archives. Every report
identifies its recorded timestamp; an absent log is explicitly unavailable.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

from pyflightstream._cli import post_warning_policy
from pyflightstream._errors import ProductArgumentError, ProductError

__all__ = [
    "render_post_diagnostics",
    "report_post_warnings",
    "warning_category",
]


def warning_category(product: str, message: str) -> str:
    """Assign a stable presentation category without changing warning detail.

    Parameters
    ----------
    product : str
        The product the warning is about.
    message : str
        The warning's text.

    Returns
    -------
    str
        One of ``configuration``, ``convergence``, ``missing-data``, ``postprocessing``,
        ``reference-frame`` and ``section-layout``.
    """
    text = f"{product} {message}".lower()
    if any(word in text for word in ("section", "distribution", "layout", "block")):
        return "section-layout"
    if any(word in text for word in ("frame", "reference", "axis", "rotation")):
        return "reference-frame"
    if any(word in text for word in ("converg", "residual", "iteration")):
        return "convergence"
    if any(word in text for word in ("tecplot", "vtk", "translation", "variable")):
        return "translation"
    if any(word in text for word in ("missing", "absent", "no data", "not found", "empty")):
        return "missing-data"
    if any(word in text for word in ("configuration", "pproc", "setting", "option")):
        return "configuration"
    return "postprocessing"


def report_post_warnings(records: Sequence[Mapping[str, str | None]], log_path: Path) -> None:
    """Print category totals only when this CLI invocation opted in.

    Parameters
    ----------
    records : sequence of mapping
        The diagnostic records of the invocation, each with its category and severity.
    log_path : Path
        The log holding the details, named in each line.
    """
    if post_warning_policy() is not True:
        return
    counts = Counter(
        record.get("category") or "postprocessing"
        for record in records
        if record.get("severity", "warning") == "warning"
    )
    for category, count in sorted(counts.items()):
        print(f"pproc warning [{category}]: {count}; details: {log_path}", file=sys.stderr)


def render_post_diagnostics(log_paths: Sequence[Path]) -> str:
    """Render all recorded diagnostics, clearly separating missing records.

    The function returns Markdown and performs no writes. Older logs without
    categories remain readable; their classification is presentation only.
    Malformed logs raise a named argument error rather than report a clean run.

    Parameters
    ----------
    log_paths : sequence of Path
        The post logs to read, one section each.

    Returns
    -------
    str
        The Markdown report.

    Raises
    ------
    ProductArgumentError
        If a log cannot be read, or is not an object holding a list of records.
    """
    lines = [
        "# Recorded postprocessing diagnostics",
        "",
        "This report reads saved logs. It does not recompute or validate products.",
        "",
    ]
    for path in log_paths:
        lines.extend([f"## {path}", ""])
        if not path.is_file():
            lines.extend(["No recorded postprocessing log is available for this matrix.", ""])
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict) or not isinstance(document.get("records"), list):
                raise ProductError("expected an object with a records list")
            records = document["records"]
            if any(not isinstance(record, dict) for record in records):
                raise ProductError("each diagnostic record must be an object")
        except (OSError, ValueError) as error:
            raise ProductArgumentError(
                f"cannot read recorded diagnostics {path}: {error}"
            ) from error
        lines.extend(
            [
                f"Recorded at: {document.get('time', 'unrecorded')}",
                "",
                f"Package version: {document.get('version', 'unrecorded')}",
                "",
                f"Matrix: {document.get('matrix') or '(unnamed)'}",
                "",
            ]
        )
        if not records:
            lines.extend(["The saved log contains no diagnostic records.", ""])
        for number, record in enumerate(records, 1):
            product = str(record.get("product", "stage"))
            message = str(record.get("message", ""))
            category = record.get("category") or warning_category(product, message)
            lines.extend(
                [
                    f"### {number}. {record.get('severity', 'warning')} / {category}",
                    "",
                    f"Point: {record.get('point', 'unrecorded')}",
                    "",
                    f"Product: {product}",
                    "",
                    message,
                    "",
                ]
            )
            if record.get("remedy"):
                lines.extend([f"Remedy: {record['remedy']}", ""])
    return "\n".join(lines)
