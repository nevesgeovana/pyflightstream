"""The mesh matrix read back: one body through three routes, compared (T07).

``matriz_mesh.fs`` runs the tier-3 wing and blade three ways each: the saved
simulation opened (the control), the same surface imported from an OBJ with
its trailing edge marked by a points file, and imported with the edge
detected. The three scripts differ in their geometry lines alone
(``tests/tier1_offline/test_tier3_offline.py`` holds them to that), so a
difference in the coefficients is a difference in the body the solver
built. This module reads what the runs recorded and says, per body and per
route, how far each OBJ row lands from its control, relative to the larger
of the two magnitudes and never to less than :data:`FLOOR`.

WHAT IS JUDGED AND WHAT IS REPORTED, as the test was defined before it ran:
the control is the saved simulation; the OBJ with the points file must land
within the repeatability band; the OBJ with detection is reported with its
difference and no band. The band itself is not written here. It is the
number of the committed ``Band (T07): <number> -- <why>`` line, stated
before the matrix runs, and :func:`committed_band` reads it from the
history, so the judgement cannot be tuned after the answer is known.

The fourth wing row imports the same body written in millimetres. It is a
question, not a check: whether ``IMPORT`` converts a body from the file's
unit into the simulation's metres. Its gap to the METER row of the same
route answers it, either way.

    python -m tests.tier3_licensed.mesh_routes      # the table, from runs.json
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MATRIX = "matriz_mesh"

#: The coefficients the band is stated on.
COEFFICIENTS = ("CL", "CDi", "CMy")

#: The magnitude below which a gap is measured against this number instead
#: of the coefficient itself. The loads table prints seven decimals, so a
#: band of 1e-4 over this floor is one unit of the last printed digit, and a
#: coefficient that prints as nearly zero (the blade's lift at zero incidence
#: is a radial force) is never asked for more than its print can say.
FLOOR = 1e-3

#: Each body's point, its control row, the row judged against the band (the
#: points file) and the row reported with its difference (detection).
BODIES: dict[str, tuple[dict[str, float], str, str, str]] = {
    "wing": ({"alpha": 4.0}, "4101", "4102", "4103"),
    "blade": ({"alpha": 0.0, "beta": 0.0}, "4111", "4112", "4113"),
}

#: The unit question: the MILLIMETER row against the METER row of its route.
UNIT_ROWS = ("4104", "4103")

#: The rows whose trailing edge is imported from a points file, and how
#: many points each file names (the file's own count, 16 and 12).
FILE_ROUTE = {"4102": ("Wing", 16), "4112": ("Blade1", 12)}

_BAND_LINE = re.compile(r"^Band \(T07\):\s*([0-9.]+(?:e-?\d+)?)\s", re.M)


def committed_band(repo: Path = REPO) -> float | None:
    """The number of the latest committed ``Band (T07)`` line, or None when there is none."""
    done = subprocess.run(
        ["git", "log", "--format=%B"],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    match = _BAND_LINE.search(done.stdout or "")
    return float(match.group(1)) if match else None


def relative_gap(value: float, control: float, floor: float = FLOOR) -> float:
    """``|value - control|`` over the larger magnitude of the two, or ``floor`` if larger."""
    return abs(value - control) / max(abs(value), abs(control), floor)


def gaps(route: dict[str, float], control: dict[str, float]) -> dict[str, float]:
    """The relative gap of each banded coefficient of a route to its control."""
    return {name: relative_gap(route[name], control[name]) for name in COEFFICIENTS}


def _entry(runs: Any, pol: str, control_pol: str, point: dict[str, float]) -> dict[str, Any]:
    total = runs.total(runs.one(MATRIX, pol, **point))
    control = runs.total(runs.one(MATRIX, control_pol, **point))
    return {
        "control": control_pol,
        "values": {name: total[name] for name in COEFFICIENTS},
        "control_values": {name: control[name] for name in COEFFICIENTS},
        "gaps": gaps(total, control),
    }


def compare(runs: Any) -> dict[str, Any]:
    """Every OBJ row against its body's control, and the unit row against its route.

    ``runs`` is :class:`tests.tier3_licensed.conftest.Runs`. Each entry
    carries the two totals and the gaps, and says whether the band judges
    it; nothing here passes or fails.
    """
    table: dict[str, Any] = {"routes": {}}
    for body, (point, control, banded, reported) in BODIES.items():
        for pol, judged in ((banded, True), (reported, False)):
            table["routes"][pol] = {
                "body": body,
                "banded": judged,
                **_entry(runs, pol, control, point),
            }
    millimetre, metre = UNIT_ROWS
    table["units"] = {"row": millimetre, **_entry(runs, millimetre, metre, BODIES["wing"][0])}
    return table


def outside(table: dict[str, Any], band: float) -> dict[str, dict[str, float]]:
    """The banded rows whose worst gap exceeds the band, with their gaps.

    A gap of exactly one printed unit over the floor is the band itself in
    exact arithmetic; the relative 1e-9 keeps the binary rounding of that
    quotient from turning an equality into a failure.
    """
    return {
        pol: entry["gaps"]
        for pol, entry in table["routes"].items()
        if entry["banded"] and max(entry["gaps"].values()) > band * (1.0 + 1e-9)
    }


def unit_answer(table: dict[str, Any], band: float) -> str:
    """Whether the MILLIMETER import gave the METER body's coefficients, in words."""
    worst = max(table["units"]["gaps"].values())
    if worst <= band:
        return (
            f"IMPORT CONVERTS: the body written in millimetres gives the METER row's "
            f"coefficients within {band:g} (worst gap {worst:.3g})"
        )
    return (
        f"IMPORT DOES NOT CONVERT, or not to this band: the body written in millimetres "
        f"lands {worst:.3g} from the METER row, beyond {band:g}"
    )


def main() -> int:
    from pyflightstream.workspace import CampaignWorkspace
    from tests.tier3_licensed.conftest import Runs

    table = compare(Runs(CampaignWorkspace(HERE)))
    band = committed_band()
    table["band"] = band
    if band is not None:
        table["outside_the_band"] = outside(table, band)
        table["unit_answer"] = unit_answer(table, band)
    print(json.dumps(table, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
