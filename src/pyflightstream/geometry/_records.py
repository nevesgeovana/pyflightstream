"""Stage records and the run report of the geometry pipeline.

Pipeline role: pure helper of the geometry package. A stage record is the file a paper cites:
it names the package version, the identity of the inputs, and for each check its id, its
limit and the value measured. A report is what a design loop reads after a parameter set
that failed: it names the stage and the check, and it is returned, never raised.

``started`` and ``wall_s`` change from run to run and stay out of every identity; use
:func:`identity_view` to compare two records.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path

from pyflightstream._errors import InputValueError
from pyflightstream._textio import write_text

__all__ = [
    "REPORT_FORMAT",
    "STAGE_FORMAT",
    "check_entry",
    "exit_code",
    "geometry_report",
    "identity_view",
    "stage_record",
    "validate_stage_record",
    "write_record",
]

STAGE_FORMAT = "pyflightstream-geom-stage/1"
REPORT_FORMAT = "pyflightstream-geom-report/1"
_STATUSES = ("passed", "failed", "skipped")
_OUTCOMES = {"accepted": 0, "failed": 1, "refused": 2}
_VOLATILE = ("started", "wall_s")


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def check_entry(check_id, status, measured=None, limit=None, unit="", where=None, note=""):
    """Return one check of a stage record.

    A check that ran (``passed`` or ``failed``) carries a finite measured value and a finite
    limit, so a paper can cite both; a ``skipped`` check carries a note that says why.
    """
    if status not in _STATUSES:
        raise InputValueError(f"check {check_id}: status expected one of {_STATUSES}")
    if status == "skipped":
        if not note:
            raise InputValueError(f"check {check_id}: a skipped check names its reason in note")
    elif not (_finite(measured) and _finite(limit)):
        raise InputValueError(f"check {check_id}: measured and limit are required numbers")
    return {
        "id": check_id,
        "status": status,
        "measured": measured,
        "limit": limit,
        "unit": unit,
        "where": dict(where or {}),
        "note": note,
    }


def stage_record(
    stage,
    name,
    *,
    package_version,
    inputs_id,
    parameter_id,
    checks=(),
    findings=(),
    warnings=(),
    outputs=None,
    kernel=None,
    started="",
    wall_s=0.0,
):
    """Return the record of one stage; its status follows from its checks.

    ``failed`` when any check failed, ``skipped`` when none ran, else ``passed``. The record
    names ``package_version`` and ``inputs_id`` (the identity of what the stage read).
    """
    checks = [dict(c) for c in checks]
    ran = [c for c in checks if c["status"] != "skipped"]
    status = "failed" if any(c["status"] == "failed" for c in checks) else "passed"
    if not ran:
        status = "skipped"
    return {
        "format": STAGE_FORMAT,
        "stage": stage,
        "name": name,
        "status": status,
        "package_version": package_version,
        "inputs_id": inputs_id,
        "parameter_id": parameter_id,
        "started": started,
        "wall_s": wall_s,
        "kernel": kernel,
        "checks": checks,
        "findings": list(findings),
        "warnings": list(warnings),
        "outputs": dict(outputs or {}),
    }


def validate_stage_record(record: Mapping) -> None:
    """Refuse a stage record a paper could not cite: a missing field or a check without a value."""
    required = ("format", "stage", "name", "status", "package_version", "inputs_id", "checks")
    for key in required:
        if key not in record:
            raise InputValueError(f"stage record: {key} is required")
    if record["format"] != STAGE_FORMAT:
        raise InputValueError(f"stage record: format expected {STAGE_FORMAT}")
    for check in record["checks"]:
        check_entry(
            check.get("id"),
            check.get("status"),
            check.get("measured"),
            check.get("limit"),
            check.get("unit", ""),
            check.get("where"),
            check.get("note", ""),
        )


def identity_view(record: Mapping) -> dict:
    """Return a record without ``started`` and ``wall_s``, the form two runs are compared in."""
    return {k: v for k, v in record.items() if k not in _VOLATILE}


def geometry_report(
    status,
    parameter_id,
    *,
    surface_id=None,
    build_id=None,
    stage=None,
    check=None,
    message="",
    measured=None,
    limit=None,
    where=None,
    stages=(),
    outputs=None,
    warnings=(),
):
    """Return the report of a run: ``accepted``, ``failed`` (a stage and a check) or ``refused``."""
    if status not in _OUTCOMES:
        raise InputValueError(f"report: status expected one of {sorted(_OUTCOMES)}")
    if status == "failed" and not (stage and check):
        raise InputValueError("report: a failed run names its stage and its check")
    return {
        "format": REPORT_FORMAT,
        "status": status,
        "parameter_id": parameter_id,
        "surface_id": surface_id,
        "build_id": build_id,
        "stage": stage,
        "check": check,
        "message": message,
        "measured": measured,
        "limit": limit,
        "where": dict(where or {}),
        "stages": list(stages),
        "outputs": dict(outputs or {}),
        "warnings": list(warnings),
    }


def exit_code(report: Mapping) -> int:
    """Return the exit code of a run: 0 accepted, 1 failed, 2 refused."""
    return _OUTCOMES[report["status"]]


def write_record(path, record: Mapping) -> None:
    """Write a record or report as sorted, indented JSON."""
    write_text(Path(path), json.dumps(record, indent=2, sort_keys=True) + "\n")
