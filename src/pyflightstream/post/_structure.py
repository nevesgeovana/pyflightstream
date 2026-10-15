"""Structural products decoded from a coupled point's recorded working folder."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from pyflightstream import _textio
from pyflightstream._digest import file_sha256
from pyflightstream.fsi.config import DIRECT_MORPHING, load_config
from pyflightstream.fsi.kinematics import decode_station_translations
from pyflightstream.fsi.nodes import generate_node_layout, read_fsidisp, unflatten_translations

if TYPE_CHECKING:
    from pyflightstream.post._sim import SimContext


def structure_products(ctx: SimContext) -> None:
    """Write deflection and twist, retaining recorded history without re-solving."""
    for point in ctx.points:
        record = ctx.record_of[point.name]
        if "fsi-provenance.json" not in record.inputs_sha256:
            continue
        relative = f"structure/{point.name}_deflection.csv"
        try:
            if not record.cwd:
                raise ValueError("the coupled record has no working folder")
            folder = Path(record.cwd)
            config_path = folder / "config.json"
            if file_sha256(config_path) != record.inputs_sha256.get("config.json"):
                raise ValueError("config.json differs from the coupled run's recorded input")
            config = load_config(config_path)
            if config.morphing == DIRECT_MORPHING:
                raise ValueError(
                    "direct morphing displacements are mesh vertices, not station triads"
                )
            layout = generate_node_layout(config)
            source = folder / "FSIDisp.txt"
            flat = read_fsidisp(source, expected_rows=layout.total_nodes)
            if not np.isfinite(flat).all():
                raise ValueError("structural displacements contain non-finite values")
            rows = []
            for blade, translations in enumerate(unflatten_translations(layout, flat), start=1):
                deflection, twist = decode_station_translations(
                    translations, np.asarray(layout.le_offset_m), np.asarray(layout.te_offset_m)
                )
                for station, radius in enumerate(config.blade.station_radii_m):
                    rows.append((blade, radius, deflection[station], math.degrees(twist[station])))
        except (OSError, ValueError) as error:
            ctx.skipped[relative] = f"structure: {error}"
            continue
        target = ctx.target(ctx.out / relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        with _textio.open_text(target, "w") as handle:
            writer = csv.writer(handle)
            writer.writerow(("blade", "station_radius_m", "deflection_m", "twist_deg"))
            writer.writerows(rows)
        ctx.add(
            target,
            {
                "runs": ctx.sources[point.name],
                "kind": "structure",
                "source_sha256": file_sha256(source),
            },
        )
        history = folder / "fsi_convergence_log.csv"
        if history.is_file():
            target = ctx.target(ctx.out / "structure" / f"{point.name}_history.csv")
            _textio.write_text(target, history.read_text(encoding="utf-8"))
            ctx.add(
                target,
                {
                    "runs": ctx.sources[point.name],
                    "kind": "structure_history",
                    "source_sha256": file_sha256(history),
                },
            )
