"""P0580-CITATION (PFS-2230): CITATION.cff carries the archive DOI of each published release.

The archive of v0.57.0 exists (Zenodo record 24210551); a citation file that names version
0.57.0 and does not list that DOI sends a reader to the wrong or no archive.
"""

import re
from pathlib import Path

CFF = (Path(__file__).resolve().parents[2] / "CITATION.cff").read_text(encoding="utf-8")


def _archives() -> dict[str, str]:
    """Map each ``vX.Y.Z`` named in an identifier description to its DOI."""
    found = re.findall(
        r"value:\s*(10\.5281/zenodo\.\d+)\s*\n"
        r"\s*description:\s*\"Zenodo archive of release (v[\d.]+)\"",
        CFF,
    )
    return {release: doi for doi, release in found}


def test_p0580_citation_lists_the_archive_of_release_0_57_0():
    assert _archives().get("v0.57.0") == "10.5281/zenodo.24210551"


def test_p0580_citation_version_is_0_57_0_until_the_next_release_updates_it():
    assert re.search(r"^version:\s*0\.57\.0\s*$", CFF, re.M)
