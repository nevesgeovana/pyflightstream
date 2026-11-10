"""Compare an export manifest with the selected registry and generated sources.

Pipeline role: the pure S11 version and membership check. The registry states
what was requested; the separately retained source record states what was
generated. Copying a requested version into a manifest cannot make them agree.
"""

from __future__ import annotations

import numpy as np

from ._boundary import unpack
from ._identity import surface_id
from ._patch import Patch
from ._records import check_entry
from ._trims import Trim

__all__ = ["manifest_checks", "manifest_record", "sidecar_identity"]


def sidecar_identity(name, layout):
    """Recompute source identity from every original base and loop in a sidecar."""
    patches = []
    for key in layout["base_order"]:
        p = layout["bases"][key]
        patches.append(
            Patch(
                key,
                np.asarray(p["controls"]),
                tuple(p["knots_u"]),
                tuple(p["knots_v"]),
                tuple(p["mult_u"]),
                tuple(p["mult_v"]),
                p["degree_u"],
                p["degree_v"],
            )
        )
    return surface_id({name: patches}, {name: [Trim(**t) for t in layout["source_trims"]]})


def manifest_record(state, *, configuration, identities, dominance, coverage) -> dict:
    """Publish measured piece records, leaving unperformed measurements unset.

    The live assembly snapshot is input only. There is one published piece
    list, with detailed face records alongside the specified integer count.
    """
    return {
        "format": "pyflightstream-geom-manifest/1",
        "configuration": configuration,
        "variant": "clean",
        **identities,
        "dominance": dominance,
        "pieces": [
            _piece_record(name, piece, dominance, coverage.get(name))
            for name, piece in state["components"].items()
        ],
        **{key: value for key, value in state.items() if key != "components"},
    }


def _piece_record(name, piece, dominance, coverage):
    return {
        "component": name,
        "version": piece["version"],
        "file": piece["iges"],
        "sha256": piece["sha256"],
        "layout": piece["layout"],
        "faces": len(piece["faces"]),
        "face_records": piece["faces"],
        "source_surface_id": piece["source_surface_id"],
        "source_area_m2": piece["source_area_m2"],
        "trimmed_area_m2": sum(f["area_m2"] for f in piece["faces"]),
        "reimport_area_m2": None,
        "missing_area_m2": None if coverage is None else coverage["missing_m2"],
        "free_edges": piece["free_edges"],
        "junctions": [row for row in dominance if name in (*row["dominant"], *row["dominated"])],
    }


def manifest_checks(resolved, configuration, members, manifest, sources) -> list[dict]:
    """Check member set, declared versions and actual generated surface identities."""
    config = unpack(resolved)
    expected = (
        {m["component"]: m["version"] for m in config["registry"][configuration]["members"]}
        if configuration is not None
        else {n: config["components"][n]["version"] for n in members}
    )
    written = {piece["component"]: piece for piece in manifest.get("pieces", [])}
    checks = []
    for name in sorted(set(expected) | set(written)):
        actual, source = written.get(name, {}), sources.get(name, {})
        version, identity = actual.get("version"), actual.get("source_surface_id")
        valid = (
            name in expected
            and name in written
            and name in sources
            and version == expected[name] == source.get("version")
            and bool(identity)
            and identity == source.get("source_surface_id")
        )
        checks.append(
            check_entry(
                "manifest.piece_version",
                "passed" if valid else "failed",
                int(not valid),
                0,
                unit="mismatches",
                where={
                    "component": name,
                    "declared_version": expected.get(name),
                    "manifest_version": version,
                    "generated_version": source.get("version"),
                    "source_surface_id": identity,
                    "generated_surface_id": source.get("source_surface_id"),
                },
            )
        )
    return checks
