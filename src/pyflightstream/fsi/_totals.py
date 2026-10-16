"""Check explicitly staged, matching-boundary totals before a coupling solve.

An optional fsi_totals.json carries loads_sha256, solver_iteration and families
(each family maps fx_n and fz_n in the sectional export frame). A producer must
refresh it for each loads export; stale or incomplete attribution is refused.
Absent totals leave the measured per-span interpretation unchanged.
"""

import json
import math
from pathlib import Path

from pyflightstream._digest import file_sha256
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.loads import SectionalLoadsReport, SectionFamilyMap, cross_check_totals
from pyflightstream.fsi.state import LOADS_FILE


def _check_staged_totals(
    folder: Path, report: SectionalLoadsReport, family_map: SectionFamilyMap
) -> None:
    path = folder / "fsi_totals.json"
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if payload["loads_sha256"] != file_sha256(folder / LOADS_FILE):
            raise ValueError("loads_sha256 does not match the current sectional export")
        if payload["solver_iteration"] != report.current_iteration:
            raise ValueError("solver_iteration does not match the current sectional export")
        blocks = report.split(family_map)
        totals = payload["families"]
        names = {family.name for family in family_map.families if family.is_blade}
        if set(totals) != names:
            raise ValueError("families must name exactly the coupled blade boundaries")
        for name in sorted(names):
            fx, fz = float(totals[name]["fx_n"]), float(totals[name]["fz_n"])
            if not all(math.isfinite(value) for value in (fx, fz)):
                raise ValueError("integrated forces must be finite Newton values")
            cross_check_totals(blocks[name], fx, fz)
    except (KeyError, TypeError, ValueError) as error:
        raise FsiInputError(f"{path.name}: {error}") from error
