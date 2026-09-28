# %% [markdown]
# # Export a sampled field
# This example writes a four-point synthetic field as VTK, Tecplot and
# reusable inflow. It performs no native solve and labels the data source.
# Run with `--output` pointing to a new directory.

# %%
"""Export a synthetic four-point field; no FlightStream run is performed."""

import argparse
from pathlib import Path

import numpy as np

from pyflightstream._cli import cli_entrypoint
from pyflightstream.post import OutputProvenance, write_probe_field
from pyflightstream.script import Script, helpers


@cli_entrypoint
def main(argv=None):
    """Write a synthetic source plus VTK, Tecplot and reusable-inflow products."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    source = args.output / "synthetic-source.csv"
    if source.exists():
        parser.error("the synthetic source already exists; choose a new output directory")
    points = np.array([[0, -1, -2], [0, -1, 2], [0, 1, -2], [0, 1, 2]], dtype=float)
    velocity = np.array([[11, 1, 2], [12, 3, 4], [13, 5, 6], [14, 7, 8]], dtype=float)
    np.savetxt(
        source,
        np.column_stack((points, velocity)),
        delimiter=",",
        header="X,Y,Z,VX,VY,VZ",
        comments="",
    )
    provenance = OutputProvenance(
        run_id="synthetic-example-no-solver",
        setup=helpers.solver_settings(Script("26.124"), velocity=30),
    )
    written = write_probe_field(
        args.output / "synthetic-field",
        points,
        velocity,
        source=source,
        provenance=provenance,
        formats=("vtk", "tecplot"),
        reusable_inflow=True,
        sample_metadata={"data_origin": "synthetic example; no native solver execution"},
    )
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
