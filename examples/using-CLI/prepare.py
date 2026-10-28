"""Write synthetic meshes for a copied classic workspace, without FlightStream."""

import argparse
import hashlib
from pathlib import Path

import numpy as np

from pyflightstream.qa.geometry import BladeSpec, WingSpec, blade_triangles, wing_triangles


def _declarations(geometries: Path, mesh: str, boundaries: list[str], faces: list[int]) -> None:
    """Write the declarations consumed by mark-boundaries beside one generated OBJ."""
    import json

    (geometries / f"{mesh}.obj.boundaries.toml").write_text(
        'fs_build = "26.124"\n'
        f'mesh_sha256 = "{hashlib.sha256((geometries / f"{mesh}.obj").read_bytes()).hexdigest()}"\n'
        f"boundaries = {json.dumps(boundaries)}\n"
        f"boundary_faces = {json.dumps(faces)}\nmesh_faces = {sum(faces)}\n\n"
        '[import]\nunits = "METER"\n\n'
        f'[trailing_edges.{mesh}]\ntype = "STANDARD"\ndetect = "auto"\n',
        encoding="utf-8",
    )


def prepare(workspace: Path) -> None:
    """Generate the geometry named by the workspace's matrix.

    Parameters
    ----------
    workspace : Path
        A copy of one of the four example workspaces.
    """
    geometries = workspace / "inputs" / "geometries"
    if (geometries / "prop.obj.boundaries.toml").is_file():
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
        _declarations(geometries, "prop", ["Blade1", "Blade2"], [len(triangles)] * 2)
    else:
        for level in (1, 2) if (geometries / "wing_fine.obj.boundaries.toml").is_file() else (1,):
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
            _declarations(geometries, name, ["Wing"], [len(triangles)])
            if name == "wing" and (geometries / "wing.refine.toml").is_file():
                faces = indices.reshape(-1, 3)
                edges = np.unique(
                    np.sort(
                        np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1
                    ),
                    axis=0,
                )
                aft = np.isclose(vertices[:, 0], 1.0) & np.isclose(vertices[:, 2], 0.0)
                nodes = np.unique(edges[aft[edges].all(axis=1)])
                # The trailing edge's nodes as the node window of an ANSA SET saves them.
                rows = "".join(
                    f"{n + 1}, Wing, {x:.12g}, {y:.12g}, {z:.12g}\n"
                    for n, (x, y, z) in zip(nodes, vertices[nodes], strict=True)
                )
                (geometries / "wing.nodes.txt").write_text(
                    "#  Id, Name, X , Y, Z\n" + rows, encoding="utf-8"
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    prepare(parser.parse_args().workspace)
