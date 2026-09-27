# GEOVERSE_HEADER
# file_version: 1.0.2
# file_role: explicit-custom-field-unit-preparation
# last_modified_at: 2026-09-27T21:58:19.804Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [RPT-083, pyflightstream.cases]
# authority: geoverse-goddess-control-plane
# status: active
# confidentiality: public
# change_summary: Reuse the shared length scale without widening measured units.
# revision_source: git
"""Prepare explicitly declared custom fields for the solver's measured file units."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._lengths import scale
from pyflightstream.cases import CampaignConfigError


@dataclass(frozen=True)
class PreparedField:
    """Effective solver input and the separate source/effective byte identities."""

    path: str
    payload: bytes | None
    provenance: dict[str, object]


def prepare_field(
    path: Path,
    *,
    form: str,
    source_units: str | None,
    native_unit: str | None,
) -> PreparedField:
    """Convert an explicit SI declaration only; undeclared inputs retain their bytes.

    The six file columns carry global XYZ and velocity components. In the
    measured METER/MILLIMETER custom-file boundary, all six use native length
    units (seconds are unchanged). Multiplication changes representation only.
    It never rotates vectors or coordinates, and never writes the source.
    """
    if source_units not in {None, "SI", "NATIVE"}:
        raise CampaignConfigError("FREESTREAM_UNITS must be SI or NATIVE, or omitted.")
    original = path.read_bytes()
    source_hash = hashlib.sha256(original).hexdigest()
    provenance: dict[str, object] = {
        "schema_version": "1.0.0",
        "source_path": str(path),
        "source_sha256": source_hash,
        "source_units": source_units or "undeclared",
        "native_length_unit": native_unit,
        "rotation_applied": False,
        "effective_sha256": source_hash,
        "effective_path": str(path),
        "hash_domain": "exact-file-bytes",
    }
    if source_units != "SI":
        return PreparedField(str(path), None, provenance)
    if native_unit not in {"METER", "MILLIMETER"}:
        raise CampaignConfigError(
            "Explicit SI custom-field conversion requires measured METER or "
            f"MILLIMETER simulation units; got {native_unit!r}."
        )
    factor = scale("METER", native_unit)
    assert factor is not None  # The measured-unit whitelist above guarantees this.
    lines = [line.strip() for line in original.decode("utf-8").splitlines() if line.strip()]
    out = []
    expected = None
    if form == "STRUCTURED":
        if not lines:
            raise CampaignConfigError(f"Custom field {path} has no header.")
        header = lines.pop(0).split()
        if len(header) != 2 or any(not v.isdigit() or int(v) <= 0 for v in header):
            raise CampaignConfigError(f"Custom field {path} requires two positive grid counts.")
        expected = int(header[0]) * int(header[1])
        out.append(" ".join(header))
    elif form != "UNSTRUCTURED":
        raise CampaignConfigError(f"Unknown custom-field form {form!r}.")
    if not lines or (expected is not None and len(lines) != expected):
        raise CampaignConfigError(f"Custom field {path} has an invalid row count.")
    for line in lines:
        try:
            values = [float(value) * factor for value in line.split()]
        except ValueError as error:
            raise CampaignConfigError(f"Custom field {path} contains nonnumeric values.") from error
        if len(values) != 6 or not all(math.isfinite(value) for value in values):
            raise CampaignConfigError(f"Custom field {path} requires six finite columns.")
        out.append(" ".join(format(value, ".17g") for value in values))
    payload = ("\n".join(out) + "\n").encode("utf-8")
    effective_hash = hashlib.sha256(payload).hexdigest()
    name = f"pfs-field-{effective_hash[:24]}{path.suffix.lower()}"
    provenance.update(
        effective_sha256=effective_hash,
        effective_path=name,
        scale_from_source=factor,
        source_coordinate_units="m",
        source_velocity_units="m/s",
        evidence="RPT-083: exact 26.124 build 8172026 METER/MILLIMETER custom-file controls",
    )
    return PreparedField(name, payload, provenance)
