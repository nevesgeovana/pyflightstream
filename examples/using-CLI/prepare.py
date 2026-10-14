"""Write synthetic meshes for a copied classic workspace, without FlightStream."""

import argparse
from pathlib import Path

import numpy as np

from pyflightstream.qa.geometry import BladeSpec, WingSpec, blade_triangles, wing_triangles


def prepare(workspace: Path) -> None:
    """Generate the geometry named by the workspace's matrix.

    Parameters
    ----------
    workspace : Path
        A copy of one of the four example workspaces.
    """
    geometries = workspace / "inputs" / "geometries"
    if (geometries / "prop.boundaries.toml").is_file():
        triangles = blade_triangles(BladeSpec(r_tip_m=1.0, n_chord=12, n_span=8))
        with (geometries / "prop.obj").open("w", encoding="utf-8") as stream:
            offset = 0
            for blade in range(2):
                vertices = triangles.reshape(-1, 3).copy()
                vertices[:, 1:] *= (-1) ** blade
                stream.write(f"o Blade{blade + 1}\n")
                for x, y, z in vertices:
                    stream.write(f"v {x:.12g} {y:.12g} {z:.12g}\n")
                for a, b, c in np.arange(len(vertices)).reshape(-1, 3) + offset + 1:
                    stream.write(f"f {a} {b} {c}\n")
                offset += len(vertices)
    else:
        for level in (1, 2) if (geometries / "wing_fine.boundaries.toml").is_file() else (1,):
            name = "wing" if level == 1 else "wing_fine"
            triangles = wing_triangles(
                WingSpec(chord_m=1.0, span_m=4.0, n_chord=12 * level, n_span=8 * level)
            )
            vertices, indices = np.unique(triangles.reshape(-1, 3), axis=0, return_inverse=True)
            with (geometries / f"{name}.obj").open("w", encoding="utf-8") as stream:
                stream.write("o Wing\n")
                for x, y, z in vertices:
                    stream.write(f"v {x:.12g} {y:.12g} {z:.12g}\n")
                for a, b, c in indices.reshape(-1, 3) + 1:
                    stream.write(f"f {a} {b} {c}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    prepare(parser.parse_args().workspace)
