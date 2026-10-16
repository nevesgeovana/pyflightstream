"""Explicit withdrawal of a compatibility judgment without inventing another run.

Pipeline role: maintainer review of committed probe evidence. The original report
and every execution signal remain unchanged; a dated analysis identifies exactly
which judgment it withdraws. Ordinary unprobed runs never withdraw evidence.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from pyflightstream import _textio
from pyflightstream._digest import text_sha256
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.reports import refuse_existing_report, resolve_report_date

__all__ = ["apply_reanalysis", "write_reanalysis"]


def write_reanalysis(
    source: str | Path,
    explanations: Mapping[str, str],
    *,
    repo_root: str | Path,
    date: str,
    label: str,
) -> tuple[Path, Path]:
    """Write a dated, analysis-only withdrawal preserving the source execution.

    Each named command requires an explanation. This operation withdraws a
    judgment, not its observations, and launches nothing. The original report
    UTF-8 text with LF line ends is pinned so that checkout line endings do not
    change provenance and later content edits cannot silently change it.
    Apply the result explicitly with :func:`apply_reanalysis` after review.
    """
    from pyflightstream.qa.compat import compat_report_paths, read_compat_report

    root = Path(repo_root).resolve()
    source = Path(source).resolve()
    citation = _citation(source, root)
    original = read_compat_report(source)
    date = resolve_report_date(date)
    if not explanations or date <= str(original.get("date", "")):
        raise QaEvidenceError("a withdrawal requires commands and a date after the source report")
    document = copy.deepcopy(original)
    document.update(date=date, analysis_only=True, execution_date=original["date"])
    document["commands"] = {}
    for command, explanation in explanations.items():
        if command not in original["commands"] or not explanation.strip():
            raise QaEvidenceError(f"{command}: a source judgment and explanation are required")
        body = copy.deepcopy(original["commands"][command])
        if body["outcome"] not in {"verified", "broken", "removed"}:
            raise QaEvidenceError(f"{command}: only a measured judgment can be withdrawn")
        body["withdraws"] = {
            "report": citation,
            "sha256": text_sha256(source.read_text(encoding="utf-8")),
            "hash_domain": "utf8-lf",
            "outcome": body["outcome"],
        }
        body["source_detail"] = body.get("detail", "")
        body.update(outcome="unprobed", detail=explanation.strip())
        document["commands"][command] = body
    document["summary"] = dict(verified=0, broken=0, removed=0, unprobed=len(explanations))
    paths = compat_report_paths(
        root / "reports" / "compat", version=original["fs_version"], date=date, label=label
    )
    refuse_existing_report(*paths)
    markdown = [
        f"# Compatibility reanalysis: {original['fs_version']} ({date})",
        "",
        f"Analysis only; no solver run. Source execution: [{citation}]({source.name}), "
        f"dated {original['date']}. Execution identity, script hashes and signals are retained.",
        "",
    ]
    markdown.extend(f"- `{name}`: unprobed. {detail}" for name, detail in explanations.items())
    _textio.write_text(paths[0], yaml.safe_dump(document, sort_keys=False, width=100))
    _textio.write_text(paths[1], "\n".join(markdown) + "\n")
    return paths


def _citation(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        raise QaEvidenceError("compatibility evidence must be inside repo_root") from None


def _withdrawals(document: dict[str, Any], root: Path) -> set[tuple[str, str, str]]:
    """Validate explicit withdrawals, including unchanged execution provenance."""
    from pyflightstream.qa.compat import read_compat_report

    found: set[tuple[str, str, str]] = set()
    for name, body in document.get("commands", {}).items():
        withdrawn = body.get("withdraws")
        if withdrawn is None:
            continue
        if document.get("analysis_only") is not True or body["outcome"] != "unprobed":
            raise QaEvidenceError(f"{name}: a withdrawal must be analysis-only and unprobed")
        path = (root / withdrawn["report"]).resolve()
        citation = _citation(path, root)
        if text_sha256(path.read_text(encoding="utf-8")) != withdrawn["sha256"]:
            raise QaEvidenceError(f"{name}: withdrawn report bytes changed")
        original = read_compat_report(path)
        before = original["commands"].get(name, {})
        if (
            original["fs_version"] != document["fs_version"]
            or str(original["date"]) >= str(document["date"])
            or before.get("outcome") != withdrawn["outcome"]
        ):
            raise QaEvidenceError(f"{name}: withdrawal source, build or date disagrees")
        fields = ("signals", "script_sha256", "return_code", "wall_time_s", "observation")
        if any(body.get(key) != before.get(key) for key in fields):
            raise QaEvidenceError(f"{name}: withdrawal changed execution evidence")
        identity = ("solver_identity", "executor", "fs_exe", "fs_exe_sha256", "package_version")
        if any(document.get(key) != original.get(key) for key in identity):
            raise QaEvidenceError(f"{name}: withdrawal changed execution identity")
        found.add((name, document["fs_version"], citation))
    return found


def apply_reanalysis(report_path: str | Path, *, repo_root: str | Path) -> list[str]:
    """Reconcile withdrawn judgments through validated chapter rewrites.

    Independent measured evidence remains authoritative. Where none remains,
    the row records direct inconclusive evidence as documented, never verified
    or broken. The original report remains on disk and cannot be reapplied.
    """
    from pyflightstream.qa.compat import (
        _load_yaml,
        _release_order,
        _rewrite_version_line,
        _validate_chapter,
        _write_changed,
        read_compat_report,
        read_compat_reports,
        resolve_commands_dir,
    )

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
    from pyflightstream.qa.compat import _load_yaml

    directory = Path(reports_dir) if reports_dir is not None else root / "reports" / "compat"
    for path in directory.glob("*.yaml"):
        document = _load_yaml(path)
        if not isinstance(document, dict) or document.get("analysis_only") is not True:
            continue
        withdrawn = _withdrawals(document, root)
        if any((name, version, citation) in withdrawn for name in targets):
            raise QaEvidenceError(f"{citation}: judgment withdrawn by {path.name}; nothing written")
