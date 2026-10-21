"""Execution provenance checks shared by compatibility withdrawal operations."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

import pyflightstream._textio as _textio
from pyflightstream._digest import text_sha256
from pyflightstream._yamlflow import flow_mapping
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.reports import refuse_existing_report, resolve_report_date


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


def _write_reanalysis(
    source: str | Path,
    explanations: Mapping[str, str],
    *,
    repo_root: str | Path,
    date: str,
    label: str,
    withdraw: bool = True,
) -> tuple[Path, Path]:
    """Construct dated analysis with an explicit choice to withdraw the source judgment."""
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
        provenance = {
            "report": citation,
            "sha256": text_sha256(source.read_text(encoding="utf-8")),
            "hash_domain": "utf8-lf",
            "outcome": body["outcome"],
        }
        body["withdraws" if withdraw else "source_judgment"] = provenance
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
        lines[at:finish] = ["      " + flow_mapping({key: updated[key]})[1:-1]]
    missing = {key: value for key, value in updated.items() if key not in existing}
    for key, value in reversed(list(missing.items())):
        lines.insert(index + 1, "      " + flow_mapping({key: value})[1:-1])
