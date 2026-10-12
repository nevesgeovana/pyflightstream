"""P0400-ASCIITITLE: a non-ASCII description reaches the custom polar transliterated.

At the 0.40.0 base the .dat was written in strict ASCII, so one accented
letter in the row's DESCRIPTION or CONFIGURATION raised a UnicodeEncodeError
out of the campaign post; the reader refused a non-ASCII file the same way.
"""

from __future__ import annotations

from pyflightstream.post._tables import COEFFICIENT_COLUMNS, ReferenceValues
from pyflightstream.post.custom_polar import read_custom_polar_format, write_custom_polar_format

_ACCENTED = "Asa em cruzeiro, " + chr(0xE2) + "ngulo m" + chr(0xE9) + "dio"


def _write(path, *, description, configuration=None):
    return write_custom_polar_format(
        path,
        polar="3207",
        description=description,
        group=1,
        mach=0.2,
        reference=ReferenceValues(sref_m2=50.0, cref_m=2.5, bref_m=20.0),
        rows=[[0.0] * len(COEFFICIENT_COLUMNS)],
        date="2026-10-12",
        configuration=configuration,
    )


def test_p0400_asciititle_a_non_ascii_description_is_transliterated(tmp_path):
    """P0400-ASCIITITLE: the title is written in ASCII, accents dropped, and reads back."""
    written = _write(
        tmp_path / "p.dat", description=_ACCENTED, configuration="cruzeiro " + chr(0x2192)
    )
    first = written.read_bytes().split(b"\n")[0]
    assert first == b"FlightStream - Asa em cruzeiro, angulo medio - cruzeiro ?"
    assert read_custom_polar_format(written).description == (
        "Asa em cruzeiro, angulo medio - cruzeiro ?"
    )


def test_p0400_asciititle_the_reader_takes_a_non_ascii_file(tmp_path):
    """P0400-ASCIITITLE: a file someone wrote in UTF-8 is read, its title transliterated."""
    written = _write(tmp_path / "p.dat", description="plain")
    text = written.read_text(encoding="ascii").replace("plain", _ACCENTED, 1)
    written.write_bytes(text.encode("utf-8"))
    assert read_custom_polar_format(written).description == "Asa em cruzeiro, angulo medio"
