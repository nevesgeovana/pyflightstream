"""Outcome-first point cards and product provenance, read without changing evidence.

Pipeline role: workspace readers for ``show`` and ``trace``. Effective records
come from Ledger; archived manifests never participate in a current card.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pyflightstream.workspace._query_files import (
    _evidence,
    _files,
    _indexes,
    _json,
    _point_files,
    _relative_name,
    _text,
)
from pyflightstream.workspace._query_logs import _activity, _mentions, _post_rows

if TYPE_CHECKING:
    from pyflightstream.workspace.ledger import Ledger

_OUTCOME = (
    "status",
    "marked",
    "error",
    "warnings",
    "residual_note",
    "stopped_at",
    "iterations",
    "residual",
)
_IDENTITY = (
    "package_version",
    "package_commit",
    "package_dirty",
    "fs_version_requested",
    "fs_version_reported",
    "fs_build",
    "recipe",
    "recipe_sha256",
    "script_sha256",
    "executor",
    "job_id",
    "started_at",
    "finished_at",
    "wall_time_s",
)


def _take(record: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: record.get(key) for key in keys}


def _inputs(record: dict[str, Any]) -> dict[str, Any]:
    setup = record.get("solver_setup") or {}
    flags = {
        key: value
        for key, value in setup.get("flags", {}).items()
        if value.get("provenance") == "explicit"
    }
    return {
        "pproc": record.get("pproc"),
        "solver_setup": {**setup, "flags": flags},
        "reference": record.get("reference"),
        "inputs_sha256": record.get("inputs_sha256", {}),
    }


def _coupling(
    ledger: Ledger, record: dict[str, Any], files: dict[str, str]
) -> dict[str, Any] | None:
    names = {Path(name).name: path for name, path in files.items()}
    digests = record.get("inputs_sha256", {})
    coupled = any(Path(name).name == "fsi-provenance.json" for name in (*names, *digests))
    if not coupled and "state.json" not in names and "fsi_convergence_log.csv" not in names:
        return None
    block: dict[str, Any] = {}
    for name in ("fsi-provenance.json", "state.json", "fsi_convergence_log.csv"):
        path = names.get(name)
        item: dict[str, Any] = {"path": path or name, "state": "present" if path else "absent"}
        if path:
            text = _text(ledger, path)
            if name.endswith(".json"):
                item["record"] = json.loads(text)
            else:
                rows = list(csv.DictReader(io.StringIO(text)))
                item["last_row"] = rows[-1] if rows else None
        block[name] = item
    return block


def _card(ledger: Ledger, run_id: str) -> dict[str, Any] | None:
    record: dict[str, Any] | None = ledger.card(run_id)
    if record is None:
        return None
    files = _point_files(record, _files(ledger, str(record["sim_id"])))
    used = record.get("log_file_used")
    evidence = []
    for name in sorted(files, key=lambda name: (name != used, name)):
        if name in record.get("outputs", []) or Path(name).suffix.lower() in {
            ".log",
            ".txt",
            ".csv",
            ".tsv",
            ".dat",
            ".out",
            ".err",
        }:
            evidence.append(_evidence(ledger, files[name]))
    raw = _json(ledger.manifest, [])
    outcome = _take(record, _OUTCOME)
    outcome["outside_tolerance"] = [
        c for c in record.get("conditions") or [] if c.get("within") is False
    ]
    matrix = str(record.get("matrix_stem") or "products")
    result = {
        "outcome": outcome,
        "evidence": evidence,
        "activity": [row for row in _activity(ledger) if _mentions(row, run_id)],
        "post": [row for row in _post_rows(ledger, matrix) if _mentions(row, run_id)],
        "chain": {
            "continues": record.get("continues"),
            "continued_by": [
                r["run_id"] for r in raw if isinstance(r, dict) and r.get("continues") == run_id
            ],
            "archives": [
                path
                for name, path in _files(ledger, str(record["sim_id"])).items()
                if "/archive/" in f"/{name}" and record["run_id"].rsplit("/", 1)[-1] in name
            ],
        },
        "identity": {"run_id": run_id, "sim_id": record["sim_id"], **_take(record, _IDENTITY)},
        "inputs": _inputs(record),
    }
    coupling = _coupling(ledger, record, files)
    if coupling is not None:
        result["coupling"] = coupling
    return result


def _identity(ledger: Ledger, run_id: str) -> dict[str, Any]:
    """Find the effective identity of a product's recorded point, including its continuation."""
    record: dict[str, Any] | None = ledger.card(run_id)
    if record is None:
        parts = run_id.split("/")
        sim = next((part[4:] for part in parts if part.startswith("sim_")), "")
        matches = [row for row in ledger.points(sims=[sim]) if row["point"] == parts[-1]]
        record = ledger.card(str(matches[0]["run_id"])) if matches else None
    if record is None:
        return {"run_id": run_id, "state": "no effective record"}
    return {"run_id": record["run_id"], **_take(record, _IDENTITY), **_inputs(record)}


def _provenance(ledger: Ledger, run_id: str) -> tuple[str | None, dict[str, Any] | None]:
    for index, document in _indexes(ledger):
        relative = document.get("provenance", {}).get(run_id)
        if relative:
            path = index.parent / relative
            return path.relative_to(ledger.root).as_posix(), _json(path)
    return None, None


def _trace_run(ledger: Ledger, run_id: str) -> dict[str, Any]:
    """Trace one run id to its identity and its provenance document.

    Parameters
    ----------
    ledger : Ledger
        The workspace ledger.
    run_id : str
        The run id to trace.

    Returns
    -------
    dict[str, Any]
        The identity, the provenance path, whether the document is present
        or absent, and the document itself.
    """
    path, document = _provenance(ledger, run_id)
    return {
        "identity": _identity(ledger, run_id),
        "provenance": path,
        "state": "present" if document is not None else "absent",
        "document": document,
    }


def _trace(ledger: Ledger, product: str) -> list[dict[str, Any]]:
    requested = Path(_relative_name(product))
    target = requested if requested.is_absolute() else ledger.root / requested
    rows = []
    for index, document in _indexes(ledger):
        for name, entry in document.get("products", {}).items():
            path = index.parent / _relative_name(name)
            if path.resolve() != target.resolve():
                continue
            sidecars = (
                path.with_suffix(path.suffix + ".json"),
                path.with_suffix(".json"),
                path.with_suffix(".prov.json"),
            )
            rows.append(
                {
                    "product": path.relative_to(ledger.root).as_posix(),
                    "sim_id": entry.get("sim_id"),
                    "pproc": entry.get("pproc"),
                    "sidecar": next(
                        (p.relative_to(ledger.root).as_posix() for p in sidecars if p.is_file()),
                        None,
                    ),
                    "runs": [_trace_run(ledger, run_id) for run_id in entry.get("runs", [])],
                }
            )
    return rows
