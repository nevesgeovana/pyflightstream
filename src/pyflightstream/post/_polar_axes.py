"""Explicit polar-axis selections from each row's recorded force components."""

import csv
from pathlib import Path
from typing import Literal

from pyflightstream import _textio


def selected_axes(path: Path, axes: Literal["wind", "stability"] | None) -> None:
    """Append selected force coefficients while keeping explicitly labelled frame columns."""
    if axes is None:
        return
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or ())
        rows = list(reader)
    suffix = "W" if axes == "wind" else "S"
    required = {quantity + suffix for quantity in ("CD", "CY", "CL")}
    if not required.issubset(columns):
        raise ValueError(f"{path}: polar axes require {sorted(required)}")
    for row in rows:
        row.update({quantity: row[quantity + suffix] for quantity in ("CD", "CY", "CL")})
        row["polar_axes"] = axes
    with _textio.open_text(path, "w") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*columns, "CD", "CY", "CL", "polar_axes"])
        writer.writeheader()
        writer.writerows(rows)
