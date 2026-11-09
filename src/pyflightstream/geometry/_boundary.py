"""Private helpers at the file and value boundary of the geometry package.

Pipeline role: private helpers of :mod:`pyflightstream.geometry.config` and
:mod:`pyflightstream.geometry.component`. For the configuration: the unit of a
dotted parameter path and the stripping of the ``{value, unit, source}`` wrappers
of a resolved configuration back to plain values (checking each unit). For the
component record: the named deviation profile's limit, the SHA-256 of a file, and
the draft 2020-12 JSON Schema export of the record model (the packaged copy is
compared with it in the test suite).
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from pyflightstream._digest import file_sha256, text_sha256
from pyflightstream._errors import InputValueError
from pyflightstream.geometry._schema import unit_of
from pyflightstream.geometry.component import DEVIATION_PROFILES, ComponentRecord


def unit_for(path):
    """Return the unit of the parameter at a dotted path: deg, mm, m, m2 or 1."""
    return unit_of(path)


def unpack(value, path=""):
    """Strip the ``{value, unit, source}`` wrappers, checking each unit, and return plain values.

    Parameters
    ----------
    value : object
        A resolved configuration value: a wrapper, a mapping, a list or a plain value.
    path : str, optional
        Dotted path of ``value``, which names the expected unit; default empty.

    Returns
    -------
    object
        A deep copy of ``value`` with every wrapper replaced by its plain value.

    Raises
    ------
    InputValueError
        If a wrapper carries a unit other than the one its path implies, or a source other than
        ``given`` or ``default``.
    """
    if isinstance(value, list):
        return [unpack(v, path) for v in value]
    if isinstance(value, dict) and set(value) == {"value", "unit", "source"}:
        if value["unit"] != unit_for(path):
            raise InputValueError(f"{path}.unit: expected {unit_for(path)}")
        if value["source"] not in ("given", "default"):
            raise InputValueError(f"{path}.source: expected given or default")
        return deepcopy(value["value"])
    if isinstance(value, dict):
        return {k: unpack(v, f"{path}.{k}".strip(".")) for k, v in value.items()}
    return deepcopy(value)


def deviation_limit_mm(local_size_mm: float, profile: str = "study_default") -> float:
    """Return the allowed deviation for a local chord or diameter under a named profile."""
    try:
        constants = DEVIATION_PROFILES[profile]
    except KeyError:
        raise InputValueError(
            f"deviation profile {profile!r}: unknown; available: {sorted(DEVIATION_PROFILES)}"
        ) from None
    return max(constants["floor_mm"], constants["local_fraction"] * local_size_mm)


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 of the exact bytes of a file as lowercase hex."""
    return file_sha256(path)


def export_schema() -> dict:
    """Return the draft 2020-12 JSON Schema of :class:`ComponentRecord`.

    Returns
    -------
    dict
        The schema, carrying its ``$schema`` and ``title`` keys.
    """
    schema = ComponentRecord.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Shared geometry component"
    return schema


def schema_digest() -> str:
    """Return the SHA-256 of the exported schema in its canonical JSON form."""
    text = json.dumps(export_schema(), sort_keys=True, separators=(",", ":"))
    return text_sha256(text)
