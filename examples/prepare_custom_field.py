# GEOVERSE_HEADER
# file_version: 1.0.1
# file_role: explicit-custom-field-preparation-example
# last_modified_at: 2026-09-27T20:46:29.475Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-author
# dependencies: [pyflightstream.cases.freestream]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Document the executable field-preparation example and its public entry.
# revision_source: git

# %% [markdown]
# # Prepare an explicitly SI custom field
#
# The source below contains metres and metres per second in global coordinates.
# A MILLIMETER solver input needs all six numeric columns multiplied by 1000.
# This changes representation and preserves each physical vector; it does not
# rotate the flow. Existing files require an explicit unit declaration.
#
# A complete matrix workflow uses FREESTREAM_UNITS: SI, or the Python field
# SimCase.freestream_units="SI", and stages/hashes the prepared input itself.
# This small example exercises preparation only. It never starts FlightStream
# or installs the field into another simulation.

# %%
"""Prepare an explicitly SI custom field without launching a solver."""

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from pyflightstream.cases.freestream import prepare_field


def demonstrate(folder: Path) -> dict[str, object]:
    """Write separate source/effective examples and verify physical equivalence."""
    source = folder / "source.txt"
    original = b"2 2\n0 -2 -1 11 3 5\n0 -2 1 12 4 6\n0 2 -1 13 5 7\n0 2 1 14 6 8\n"
    source.write_bytes(original)
    prepared = prepare_field(source, form="STRUCTURED", source_units="SI", native_unit="MILLIMETER")
    assert prepared.payload is not None
    effective = folder / prepared.path
    effective.write_bytes(prepared.payload)
    assert source.read_bytes() == original
    converted = [float(value) for value in prepared.payload.splitlines()[1].split()]
    assert [value / 1000 for value in converted] == [0, -2, -1, 11, 3, 5]
    assert prepared.provenance["rotation_applied"] is False
    assert prepared.provenance["source_sha256"] == sha256(original).hexdigest()
    assert prepared.provenance["effective_sha256"] == sha256(effective.read_bytes()).hexdigest()
    return prepared.provenance


if __name__ == "__main__":
    with TemporaryDirectory(prefix="pyfs-custom-field-") as temporary:
        result = demonstrate(Path(temporary))
        print("Physical XYZ and velocity preserved; source bytes unchanged.")
        print("Prepared input SHA-256:", result["effective_sha256"])
