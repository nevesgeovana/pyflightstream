# GEOVERSE_HEADER_BEGIN
# file_version: 1.0.1
# artifact_id: synthetic-duct-fixture-generator
# last_modified_at: 2026-09-27T23:06:27.528Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-author
# dependencies: [inputs/duct/duct.boundaries.toml]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Format the approved generator while preserving its exact payload bytes.
# revision_source: git
# GEOVERSE_HEADER_END
"""Reproduce the measured eight-vertex, six-quad synthetic duct locally."""

from __future__ import annotations

from pathlib import Path

_CAPTURE_HEADER = """# GEOVERSE_HEADER_BEGIN
# file_version: "1.0.0"
# last_modified_at: "2026-09-27T14:59:01.788097+00:00"
# last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: implementer}
# dependencies: []
# authority: pyflightstream
# status: draft
# confidentiality: public
# change_summary: "Add synthetic uniform-normal-velocity duct fixture for G07."
# revision_source: git
# GEOVERSE_HEADER_END
"""


def write_duct_obj(path: Path) -> Path:
    """Write the existing synthetic fixture to a new path; refuse overwrite."""
    vertices = [
        (0, -0.5, -0.5),
        (0, 0.5, -0.5),
        (0, 0.5, 0.5),
        (0, -0.5, 0.5),
        (2, -0.5, -0.5),
        (2, 0.5, -0.5),
        (2, 0.5, 0.5),
        (2, -0.5, 0.5),
    ]
    groups = [
        ("Inlet", [(1, 4, 3, 2)]),
        ("Outlet", [(5, 6, 7, 8)]),
        ("Wall", [(1, 2, 6, 5), (4, 8, 7, 3), (1, 5, 8, 4), (2, 3, 7, 6)]),
    ]
    lines = _CAPTURE_HEADER.splitlines()
    lines.extend("v " + " ".join(f"{value:g}" for value in v) for v in vertices)
    for name, faces in groups:
        lines.append("g " + name)
        lines.extend("f " + " ".join(map(str, face)) for face in faces)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(("\r\n".join(lines) + "\r\n").encode("ascii"))
    return path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    write_duct_obj(parser.parse_args().output)
