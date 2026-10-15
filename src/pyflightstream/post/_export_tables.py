"""Numeric per-point tables from the recorded solver exports."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyflightstream._textio as _textio
from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import classify_outputs
from pyflightstream.results import parse_force_distributions, parse_solver_analysis_csv

if TYPE_CHECKING:
    from pyflightstream.post._sim import SimContext


def export_tables(ctx: SimContext) -> None:
    """Table exported numbers without inferring an unstated scalar field."""
    for point in ctx.points:
        record = ctx.record_of[point.name]
        exports = classify_outputs(record.outputs, package_version=record.package_version)
        for kind, product in (
            ("force_distributions", "force_distributions"),
            ("csv", "surface_values"),
        ):
            if kind not in exports:
                continue
            source = ctx.workspace.sim_dir(record.sim_id) / exports[kind]
            relative = f"tables/{point.name}_{product}.csv"
            try:
                text = source.read_text(encoding="utf-8")
                if kind == "force_distributions":
                    force = parse_force_distributions(
                        text, requested_version=record.fs_version_requested
                    )
                    columns, values = force.columns, force.values
                    details = {"force_units": force.force_units, "moment_units": force.moment_units}
                else:
                    surface = parse_solver_analysis_csv(text)
                    columns, values = surface.columns, surface.values
                    details = {"scalar_field": surface.scalar_field}
            except (OSError, ValueError, PyflightstreamError) as error:
                ctx.skipped[relative] = f"{product}: {error}"
                continue
            target = ctx.target(ctx.out / relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with _textio.open_text(target, "w") as handle:
                writer = _textio.csv_writer(handle)
                writer.writerow(columns)
                writer.writerows(values)
            ctx.add(
                target,
                {
                    "runs": ctx.sources[point.name],
                    "kind": product,
                    "source_sha256": file_sha256(source),
                    **details,
                },
            )
