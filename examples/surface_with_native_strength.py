# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.3
# artifact_id: native-surface-example
# last_modified_at: 2026-09-27T19:06:07.787Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementer
# dependencies: [pyflightstream]
# authority: pyflightstream
# status: draft
# confidentiality: public
# change_summary: Render a didactic example and preserve standard CLI outcome messages.
# revision_source: git
# GEOVERSE_HEADER_END
# %% [markdown]
# # A surface with native nodal singularity strength
#
# Preserve exact VTK panel values and attach the same-step native strength by a
# unique coordinate and polygon-topology match. Supply the actual recorded loads
# frame. Existing outputs are preserved; missing or ambiguous sources are refused.
#
# %%
"""Translate VTK panel values and native nodal strength without interpolation.

Usage: python surface_with_native_strength.py surface.vtk native.dat result.dat frame.json
The frame JSON is the recorded surface_translations entry's frame object.
Existing outputs are refused. Workspace runs do this automatically.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pyflightstream._cli import cli_entrypoint
from pyflightstream.results.surface import SurfaceFrame, translate_vtk_surface


def translate_with_native(
    vtk: Path, native: Path, output: Path, frame: dict[str, object]
) -> dict[str, object]:
    """Write a new mixed-association product with both input hashes in provenance."""
    return translate_vtk_surface(
        vtk, output, frame=SurfaceFrame.from_record(frame), native_tecplot=native
    )


@cli_entrypoint
def main() -> None:
    """Translate one pair using the supplied recorded frame."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("vtk", "native", "output", "frame"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    result = translate_with_native(
        args.vtk, args.native, args.output, json.loads(args.frame.read_text(encoding="utf-8"))
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
