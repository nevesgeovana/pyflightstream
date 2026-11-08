"""Private helpers at the file and value boundary of the geometry package.

Pipeline role: private helpers of :mod:`pyflightstream.geometry.config` and
:mod:`pyflightstream.geometry.component`. For the configuration: the unit of a
dotted parameter path, the stripping of the ``{value, unit, source}`` wrappers
of a resolved configuration back to plain values (checking each unit), and the
TOML writer whose output ``load_config`` reads back unchanged. For the
component record: the named deviation profile's limit, the SHA-256 pin check
of every file a :class:`ComponentRecord` references, and the draft 2020-12 JSON
Schema export of the record model (the packaged copy is compared with it in the
test suite).
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path

from pyflightstream._digest import file_sha256, text_sha256
from pyflightstream._errors import InputValueError
from pyflightstream._textio import write_text
from pyflightstream.geometry.component import DEVIATION_PROFILES, ComponentRecord


def unit_for(path):
    """Return the unit of the parameter at a dotted path: ``deg``, ``m``, ``m2`` or ``1``."""
    key = path.split(".")[-1]
    if key in (
        "sweep",
        "dihedral",
        "incidence",
        "tip_twist",
        "twist",
        "rotation",
        "azimuths",
        "setting_angle",
        "footprint_upper",
        "footprint_lower",
    ):
        return "deg"
    if key in ("area",):
        return "m2"
    if key in (
        "span",
        "root_chord",
        "tip_chord",
        "radius",
        "hub_radius",
        "base_radius",
        "translation",
        "radii",
        "mac",
        "centre_height",
        "body_blend_radius",
        "wing_blend_radius",
    ):
        return "m"
    if key == "length" and "tip_cap" not in path:
        return "m"
    return "1"


def unpack(value, path=""):
    """Strip the ``{value, unit, source}`` wrappers, checking each unit, and return plain values."""
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


def toml_value(value):
    """Render a plain value as an inline TOML value."""
    if isinstance(value, dict):
        return (
            "{ " + ", ".join(f"{json.dumps(k)} = {toml_value(v)}" for k, v in value.items()) + " }"
        )
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)) and math.isfinite(value):
        return repr(value)
    raise InputValueError(f"Unsupported TOML value: {value!r}")


def write_config(config, path):
    """Write a resolved configuration as TOML that :func:`load_config` reads back unchanged."""
    text = "\n".join(f"{json.dumps(k)} = {toml_value(v)}" for k, v in config.items()) + "\n"
    write_text(path, text)


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


def verify_pins(record: ComponentRecord, asset_root: str | Path) -> list[str]:
    """Check every referenced file against its pin; return one message per failure.

    Paths resolve against ``asset_root``. An empty list means every referenced
    file exists with matching bytes. A path that escapes the root is a failure.
    """
    root = Path(asset_root).resolve()
    problems: list[str] = []
    for reference in record.referenced_files():
        target = (root / reference.path).resolve()
        if root != target and root not in target.parents:
            problems.append(f"{reference.path}: outside the asset root")
        elif not target.is_file():
            problems.append(f"{reference.path}: missing")
        elif sha256_file(target) != reference.sha256:
            problems.append(f"{reference.path}: SHA-256 differs from the pin")
    return problems


def export_schema() -> dict:
    """Return the draft 2020-12 JSON Schema of :class:`ComponentRecord`."""
    schema = ComponentRecord.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Shared geometry component"
    return schema


def schema_digest() -> str:
    """Return the SHA-256 of the exported schema in its canonical JSON form."""
    text = json.dumps(export_schema(), sort_keys=True, separators=(",", ":"))
    return text_sha256(text)
