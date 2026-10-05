"""The CCS mesh read states what the mesh judge compares (FR-401).

Reproduction: export a reference and a variant loft with equal vertex and
face counts but one moved coordinate. The judge calls them different; the
read must say so too, rather than printing two equal counts.
"""

from pyflightstream.qa.specs import PROBE_SPECS
from tests.tier1_offline._p0340_probe_support import artifacts_in

COMMAND = "CCS_FUSELAGE_MESH_GROWTH_RATE"
REFERENCE = "o reference\nv 0 0 0\nv 1 0 0\nv 0 2 0\nf 1 2 3\n"


def _write(folder, variant):
    (folder / "reference.obj").write_text(REFERENCE, encoding="utf-8")
    (folder / "variant.obj").write_text(variant, encoding="utf-8")


def test_equal_counts_with_moved_geometry_read_as_different(tmp_path):
    """P0370-S10-MESH-READ (FR-401): the read agrees with the judge on equal counts."""
    _write(tmp_path, REFERENCE.replace("reference", "variant").replace("v 1 0 0", "v 3 0 0"))
    spec = PROBE_SPECS[COMMAND]
    artifacts = artifacts_in(tmp_path)
    read = spec.observe(artifacts)
    assert spec.assert_effect(artifacts) is True
    assert "variant geometry differs from reference" in read
    digests = [part.rsplit(" ", 1)[1] for part in read.split("; ")[:2]]
    assert len(digests[0]) == 16 and digests[0] != digests[1]


def test_equal_geometry_reads_as_equal(tmp_path):
    """P0370-S10-MESH-READ (FR-401): renamed but equal lofts read equal, one digest."""
    _write(tmp_path, REFERENCE.replace("reference", "variant"))
    spec = PROBE_SPECS[COMMAND]
    read = spec.observe(artifacts_in(tmp_path))
    assert "variant geometry equals reference" in read
    digests = [part.rsplit(" ", 1)[1] for part in read.split("; ")[:2]]
    assert digests[0] == digests[1]
