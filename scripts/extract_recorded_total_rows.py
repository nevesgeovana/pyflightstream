"""Extract the Total row of every recorded licensed loads export into one fixture.

The exports under ``tests/tier3_licensed/sims/`` are machine output and are not
tracked. Their Total rows are what the axes tests score a rotation against, so
they are extracted here, verbatim as printed, into a tracked table:

    python scripts/extract_recorded_total_rows.py

The fixture is never edited by hand; the axes test re-reads the live exports
where they exist and refuses a fixture that disagrees with them. The final
``sha256`` column witnesses the exact export bytes, including line endings.
Set ``PYFLIGHTSTREAM_RECORDED_SIMS`` to read exports from another checkout;
the generated fixture still belongs to this checkout.
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIMS = Path(os.environ.get("PYFLIGHTSTREAM_RECORDED_SIMS", ROOT / "tests/tier3_licensed/sims"))
FIXTURE = ROOT / "tests" / "tier1_offline" / "fixtures" / "recorded_total_rows.csv"
COLUMNS = (
    "export",
    "alpha_deg",
    "beta_deg",
    "frame",
    "Cx",
    "Cy",
    "Cz",
    "CL",
    "CDi",
    "CDo",
    "sha256",
)


def _cells(line: str) -> list[str]:
    """Return the cells of one printed row, without the empty ones a trailing comma adds."""
    cells = [cell.strip() for cell in line.split(",")]
    while cells and not cells[-1]:
        cells.pop()
    return cells


def total_row(text: str) -> dict[str, str] | None:
    """Return the Total row's cells as PRINTED, keyed by the export's own header.

    A Total row whose cell count differs from its header's is REFUSED, naming both
    counts: a shorter row read leniently would narrow the oracle every axes test is
    scored against, in silence (release review of 0.24.0, QA-Q3).
    """
    header: list[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Surface,"):
            header = _cells(stripped)
        elif header and stripped.startswith("Total,"):
            values = _cells(stripped)
            if len(values) != len(header):
                raise ValueError(
                    f"the Total row prints {len(values) - 1} cells under a header of "
                    f"{len(header) - 1}, so which number is which cannot be read"
                )
            return dict(zip(header[1:], values[1:], strict=True))
    return None


def labeled(text: str, label: str) -> str | None:
    """Return the value the export prints beside ``label``, as printed."""
    found = re.search(re.escape(label) + r"\s*:?\s*([-+.\dEe]+)", text)
    return found.group(1) if found else None


def rows() -> list[dict[str, str]]:
    """Return one row per recorded export that prints a Total row with a force vector."""
    table = []
    for path in sorted(SIMS.glob("sim_*/raw/*.txt")):
        if path.stem.lower().endswith(("_cp", "_sloads", "_probes", "_plots", "_log")):
            continue
        payload = path.read_bytes()
        text = payload.decode("utf-8", errors="replace")
        if not text.strip():
            raise ValueError(f"{path}: empty export")
        if not any(line.strip().startswith("Surface,") for line in text.splitlines()):
            continue
        alpha = labeled(text, "Angle of attack (Deg)")
        beta = labeled(text, "Side-slip angle (Deg)")
        try:
            total = total_row(text)
        except ValueError as refused:
            raise ValueError(f"{path}: {refused}") from None
        if total is None:
            raise ValueError(f"{path}: loads export has no Total row")
        frame = re.search(r"Coordinate frame for analysis:\s*(\S.*)", text)
        if alpha is None or beta is None or total is None or "Cx" not in total:
            continue
        table.append(
            {
                "export": f"{path.parent.parent.name}/{path.name}",
                "sha256": hashlib.sha256(payload).hexdigest(),
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
