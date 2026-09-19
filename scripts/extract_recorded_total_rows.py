"""Extract the Total row of every recorded licensed loads export into one fixture.

The exports under ``tests/tier3_licensed/sims/`` are machine output and are not
tracked. Their Total rows are what the axes tests score a rotation against, so
they are extracted here, verbatim as printed, into a tracked table:

    python scripts/extract_recorded_total_rows.py

The fixture is never edited by hand; the axes test re-reads the live exports
where they exist and refuses a fixture that disagrees with them.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIMS = ROOT / "tests" / "tier3_licensed" / "sims"
FIXTURE = ROOT / "tests" / "tier1_offline" / "fixtures" / "recorded_total_rows.csv"
COLUMNS = ("export", "alpha_deg", "beta_deg", "frame", "Cx", "Cy", "Cz", "CL", "CDi", "CDo")


def total_row(text: str) -> dict[str, str] | None:
    """Return the Total row's cells as PRINTED, keyed by the export's own header."""
    header: list[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Surface,"):
            header = [cell.strip() for cell in stripped.split(",")]
        elif header and stripped.startswith("Total,"):
            return dict(
                zip(header[1:], (cell.strip() for cell in stripped.split(",")[1:]), strict=False)
            )
    return None


def labeled(text: str, label: str) -> str | None:
    """Return the value the export prints beside ``label``, as printed."""
    found = re.search(re.escape(label) + r"\s*:?\s*([-+.\dEe]+)", text)
    return found.group(1) if found else None


def rows() -> list[dict[str, str]]:
    """Return one row per recorded export that prints a Total row with a force vector."""
    table = []
    for path in sorted(SIMS.glob("sim_*/raw/*.txt")):
        text = path.read_text(errors="replace")
        alpha = labeled(text, "Angle of attack (Deg)")
        beta = labeled(text, "Side-slip angle (Deg)")
        total = total_row(text)
        frame = re.search(r"Coordinate frame for analysis:\s*(\S.*)", text)
        if alpha is None or beta is None or total is None or "Cx" not in total:
            continue
        table.append(
            {
                "export": f"{path.parent.parent.name}/{path.name}",
                "alpha_deg": alpha,
                "beta_deg": beta,
                "frame": frame.group(1).strip() if frame else "",
                **{name: total[name] for name in ("Cx", "Cy", "Cz", "CL", "CDi", "CDo")},
            }
        )
    return table


def main() -> int:
    """Write the fixture and say how many rows it holds."""
    table = rows()
    with FIXTURE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(table)
    print(f"{len(table)} Total rows -> {FIXTURE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
