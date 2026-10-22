"""The rows and the whole-rotor proof a route 2 sector-offset calibration reads.

Pipeline role: what :func:`pyflightstream.post.corrections.sector_offset_calibration`
takes from the posted rotor tables of a wheel point and a sector point, and the check of the
sector run's own script before it derives an offset from its loads.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pyflightstream._digest import text_sha256
from pyflightstream.cases.corrections import CalibrationError
from pyflightstream.post._stage import PRODUCTS_MANIFEST
from pyflightstream.post._tables import ROTOR_TABLE_SUFFIX, read_csv_table


def _number(text: object) -> float | None:
    try:
        value = float(str(text))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _rotor_row(
    manifest: Mapping[str, Any], out: Path, run_id: str, rotor: str | None
) -> tuple[str, str, dict[str, str]]:
    """Return the rotor table row of a run: (table, alias, row)."""
    found = []
    for relative, entry in (manifest.get("products") or {}).items():
        if not relative.endswith(ROTOR_TABLE_SUFFIX) or not isinstance(entry, Mapping):
            continue
        runs = entry.get("runs")
        if not isinstance(runs, list) or run_id not in runs:
            continue
        if rotor is not None and str(entry.get("rotor")) != rotor:
            continue
        found.append((relative, str(entry.get("rotor")), runs))
    if len(found) != 1:
        raise CalibrationError(
            f"run {run_id!r} is a row of {len(found)} rotor tables of {out / PRODUCTS_MANIFEST}"
            + (f" for rotor {rotor!r}" if rotor else "")
            + "; the helper reads exactly one. Post the campaign first, or name the rotor"
        )
    relative, alias, runs = found[0]
    _, rows = read_csv_table(out / relative)
    if len(rows) != len(runs):
        raise CalibrationError(
            f"{relative} holds {len(rows)} rows and its entry names {len(runs)} runs, so the "
            f"row of {run_id!r} cannot be told"
        )
    return relative, alias, rows[runs.index(run_id)]


def _loads_of(row: Mapping[str, str], alias: str, where: str) -> dict[str, float]:
    values = {
        name: _number(row.get(column))
        for name, column in (
            ("J", f"J_{alias}"),
            ("CT", f"CT_{alias}"),
            ("CQ", f"CQ_{alias}"),
            ("RPM", f"RPM_{alias}"),
            ("D", f"DIAMETER_{alias}"),
            ("RHO", "RHO"),
            ("ALPHA", "ALPHA"),
            ("BETA", "BETA"),
        )
    }
    missing = sorted(name for name, value in values.items() if value is None)
    if missing:
        raise CalibrationError(f"the rotor table row of {where} states no {', '.join(missing)}")
    known = {name: float(value) for name, value in values.items() if value is not None}
    rate = abs(known["RPM"]) / 60.0
    known["THRUST"] = known["CT"] * known["RHO"] * rate**2 * known["D"] ** 4
    known["TORQUE"] = known["CQ"] * known["RHO"] * rate**2 * known["D"] ** 5
    return known


def _whole_rotor_gap(space: Any, record: Any) -> str | None:
    """Why a sector run's record does not prove whole-rotor loads; None where it does.

    Read from the run's own script, hashed as recorded: a solve under a
    ``SYMMETRY`` other than ``NONE`` (a periodic sector, a mirrored half)
    exports the whole rotor only where every ``SET_ANALYSIS_SYMMETRY_LOADS`` of
    the script is ``ENABLE``; a solve with no symmetry has no copies to omit.
    """
    script, digest = getattr(record, "script_path", None), getattr(record, "script_sha256", None)
    if not script or not digest:
        return "its record names no hashed script"
    try:
        text = (space.sim_dir(record.sim_id) / script).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return f"its script cannot be read ({error})"
    if text_sha256(text) != digest:
        return f"its script {script} no longer hashes as recorded"
    words = [line.split() for line in text.splitlines()]
    modes = [" ".join(w[1:]) for w in words if len(w) > 1 and w[0] == "SYMMETRY"]
    partial = [mode for mode in modes if mode.upper() != "NONE"]
    loads = [w[1].upper() for w in words if len(w) > 1 and w[0] == "SET_ANALYSIS_SYMMETRY_LOADS"]
    if not partial or (loads and set(loads) == {"ENABLE"}):
        return None
    stated = ", ".join(loads) if loads else "not stated"
    return (
        f"its script solves SYMMETRY {partial[-1]} with SET_ANALYSIS_SYMMETRY_LOADS {stated}, "
        "so its loads export carries the modelled part alone"
    )
