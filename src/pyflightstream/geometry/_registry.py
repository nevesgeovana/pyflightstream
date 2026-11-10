"""Compare an export manifest with the selected registry and generated sources.

Pipeline role: the pure S11 version and membership check. The registry states
what was requested; the separately retained source record states what was
generated. Copying a requested version into a manifest cannot make them agree.
"""

from __future__ import annotations

from ._boundary import unpack
from ._records import check_entry

__all__ = ["manifest_checks"]


def manifest_checks(resolved, configuration, members, manifest, sources) -> list[dict]:
    """Check member set, declared versions and actual generated surface identities."""
    config = unpack(resolved)
    expected = (
        {m["component"]: m["version"] for m in config["registry"][configuration]["members"]}
        if configuration is not None
        else {n: config["components"][n]["version"] for n in members}
    )
    written = manifest.get("components", {})
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
