"""The three identities of a geometry run: parameters, surfaces and build.

Pipeline role: pure helper of the geometry package. Each identity is a SHA-256 of a
canonical form, stored whole and truncated to 16 hex digits where it names a file.

* ``parameter_id`` covers the resolved values only: the source of a value (``given`` or
  ``default``), file paths, comments and warnings are left out, so stating a default
  explicitly does not change it. A data file a component names enters by its SHA-256, not
  its path. Every number is written by ``float.hex``, so ``9`` and ``9.0`` agree.
* ``surface_id`` covers the control nets, knots and degrees of every patch, ordered by
  component name and patch index. It is compared exactly on one platform; across platforms a
  small committed golden is compared to a tolerance.
* ``build_id`` ties a ``parameter_id`` to the package version and the kernel that built it.

The bytes of an IGES file are deliberately not an identity: they depend on creation order and
on the time, and a pure stage has no IGES.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

import numpy as np

from pyflightstream.geometry._boundary import unpack
from pyflightstream.geometry._patch import Patch

__all__ = ["SCHEMA_MAJOR", "build_id", "canonical", "parameter_id", "short", "surface_id"]

SCHEMA_MAJOR = 1
_PATH_KEYS = frozenset({"rings_file", "sections_file", "original", "file"})
_DROPPED = ("aircraft", "warnings", "findings", "derived", "configurations", "format")


def canonical(value) -> str:
    """Return the canonical JSON of plain data: sorted keys, every number by ``float.hex``."""

    def convert(node):
        if isinstance(node, Mapping):
            return {str(k): convert(v) for k, v in node.items()}
        if isinstance(node, (list, tuple)):
            return [convert(v) for v in node]
        if isinstance(node, (bool, str)) or node is None:
            return node
        if isinstance(node, (int, float, np.integer, np.floating)):
            return "f:" + float(node).hex()
        raise TypeError(f"not plain data: {type(node).__name__}")

    return json.dumps(convert(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def short(identity: str) -> str:
    """Return the 16-hex form of an identity, the form used in names."""
    return identity[:16]


def _strip_paths(node):
    if isinstance(node, dict):
        return {k: _strip_paths(v) for k, v in node.items() if k not in _PATH_KEYS}
    if isinstance(node, list):
        return [_strip_paths(v) for v in node]
    return node


def parameter_id(resolved: Mapping) -> str:
    """Return the ``parameter_id`` of a resolved configuration, as 64 hex digits."""
    values = unpack(dict(resolved))
    for key in _DROPPED:
        values.pop(key, None)
    values = _strip_paths(values)
    values["schema"] = SCHEMA_MAJOR
    return _digest(canonical(values))


def surface_id(patches: Mapping[str, Sequence[Patch]]) -> str:
    """Return the ``surface_id`` of placed patches given per component name, as 64 hex digits."""
    rows = []
    for name in sorted(patches):
        for index, patch in enumerate(patches[name]):
            rows.append(
                {
                    "component": name,
                    "patch": index,
                    "degree": [patch.degree_u, patch.degree_v],
                    "knots_u": list(patch.knots_u),
                    "knots_v": list(patch.knots_v),
                    "mult_u": list(patch.multiplicities_u),
                    "mult_v": list(patch.multiplicities_v),
                    "controls": np.asarray(patch.controls, dtype=float).tolist(),
                }
            )
    return _digest(canonical(rows))


def build_id(parameter: str, package_version: str, kernel_name: str, kernel_version: str) -> str:
    """Return the ``build_id``: a parameter identity tied to the package and the kernel."""
    return _digest(
        canonical(
            {
                "parameter_id": parameter,
                "package": package_version,
                "kernel": [kernel_name, kernel_version],
            }
        )
    )
