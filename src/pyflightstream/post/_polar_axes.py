"""Explicit polar-axis selections from each row's recorded force components."""

import csv
from pathlib import Path
from typing import Literal

import pyflightstream._textio as _textio


def selected_axes(path: Path, axes: Literal["wind", "stability"] | None) -> None:
    """Append selected force coefficients while keeping explicitly labelled frame columns."""
    if axes is None:
        return
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or ())
        rows = list(reader)
    suffix = "W" if axes == "wind" else "S"
    quantities = {"CD": "drag", "CY": "side_force", "CL": "lift"}
    groups = [
        column[len("CD" + suffix) :] for column in columns if column.startswith(f"CD{suffix}_")
    ]
    if f"CD{suffix}" in columns:
        groups.insert(0, "")
    required = {quantity + suffix + group for group in groups or [""] for quantity in quantities}
    if not required.issubset(columns):
        raise ValueError(f"{path}: polar axes require {sorted(required)}")
    selected = {
        (f"selected_{physical}_coefficient{group}" if group else quantity): quantity
        + suffix
        + group
        for group in groups
        for quantity, physical in quantities.items()
    }
    added = [*selected, "polar_axes"]
    if collisions := set(added).intersection(columns):
        raise ValueError(
            f"{path}: selected polar axes would replace existing columns {sorted(collisions)}"
        )
    for row in rows:
        row.update({name: row[source] for name, source in selected.items()})
        row["polar_axes"] = axes
    with _textio.open_text(path, "w") as handle:
        writer = _textio.csv_dict_writer(handle, fieldnames=[*columns, *added])
        writer.writeheader()
        writer.writerows(rows)
