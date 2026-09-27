# GEOVERSE_HEADER
# file_version: 1.0.1
# last_modified_at: 2026-09-27T19:08:09.397Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementer
# dependencies: [pyflightstream.post.boundary_layer]
# authority: pyflightstream
# status: draft
# confidentiality: public
# change_summary: Render the executable synthetic BL example as documented notebook cells.
# revision_source: git
# %% [markdown]
# # Boundary-layer cell association
#
# This executable example writes a CSV from synthetic panel values. It preserves
# both cells where the cut lies on their shared edge and never invents a
# wall-normal velocity profile. Run it with an output CSV path; no solver starts.

# %%
"""Write a synthetic BL table; this example does not launch a solver."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from pyflightstream._cli import cli_entrypoint
from pyflightstream.post.boundary_layer import sample_boundary_layer, write_boundary_layer_table
from pyflightstream.results import SurfaceSection
from pyflightstream.results.surface import REFERENCE_FRAME, VtkSurface


@cli_entrypoint
def main(argv: list[str] | None = None) -> int:
    """Write the synthetic example to the requested CSV path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    surface = VtkSurface(
        points=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]]),
        offsets=np.array([0, 3, 6]),
        connectivity=np.array([0, 1, 2, 0, 2, 3]),
        cell_data={
            "BL_displacement_thickness": np.array([1e-9, 2e-9]),
            "BL_momentum_thickness": np.array([0.5e-9, 1e-9]),
            "BL_shape_factor": np.array([2.0, 2.0]),
        },
    )
    cut = np.zeros((1, 20))
    cut[0, 1:4] = [0.5, 0.5, 0.0]
    section = SurfaceSection(index=1, edges=1, values=cut)
    samples = sample_boundary_layer(
        surface, [section], surface_frame=REFERENCE_FRAME, section_frames={1: REFERENCE_FRAME}
    )
    write_boundary_layer_table(args.output, samples)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
