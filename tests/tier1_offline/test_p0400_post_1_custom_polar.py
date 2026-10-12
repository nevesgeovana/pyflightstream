"""P0400 custom polar defects (post-1 lane).

P0400-CUSTOMREAD (PFS-2095.018): malformed input is a ProductError naming the
file and the line, never a bare ValueError or UnicodeDecodeError.
P0400-CUSTOMWIDTH (PFS-2105.012): every field keeps a blank before it, so a
long reference value or a large coefficient never fuses with its neighbour.
"""

from __future__ import annotations

import pytest

from pyflightstream._errors import ProductError
from pyflightstream.post._tables import COEFFICIENT_COLUMNS, ReferenceValues
from pyflightstream.post.custom_polar import read_custom_polar_format, write_custom_polar_format


def _written(tmp_path, reference, rows):
    return write_custom_polar_format(
        tmp_path / "7_M20_g01.dat",
        polar=7,
        description="wing",
        group=1,
        mach=0.2,
        reference=reference,
        rows=rows,
        date="Tue Sep 08 23:41:07  2026",
    )


def _row(first: float) -> tuple[float, ...]:
    return (first, *([0.125] * (len(COEFFICIENT_COLUMNS) - 1)))


@pytest.mark.parametrize((), [pytest.param(id="P0400-CUSTOMWIDTH")])
def test_p0400_customwidth_a_long_reference_and_a_large_value_round_trip(tmp_path):
    """P0400-CUSTOMWIDTH: 0.0785398... and -12.3456789 on line 6, 12345.6 in a row."""
    reference = ReferenceValues(sref_m2=0.07853981633974483, cref_m=2.5, bref_m=-12.3456789)
    path = _written(tmp_path, reference, [_row(12345.6), _row(0.5)])
    lines = path.read_text(encoding="ascii").splitlines()
    for line in [lines[5], *lines[9:]]:
        fields = [line[start : start + 10] for start in range(0, len(line), 10)]
        assert all(field.startswith(" ") for field in fields), line
    table = read_custom_polar_format(path)
    assert table.reference.sref_m2 == pytest.approx(0.07853981633974483, rel=1e-6)
    assert table.reference.bref_m == pytest.approx(-12.3456789, rel=1e-6)
    first = COEFFICIENT_COLUMNS[0]
    assert [row[first] for row in table.rows] == pytest.approx([12345.6, 0.5])


@pytest.mark.parametrize((), [pytest.param(id="P0400-CUSTOMREAD")])
@pytest.mark.parametrize(
    ("line", "text", "said"),
    [
        (3, "009 xx", "line 4"),
        (5, "0.2 50.0 abc", "line 6"),
        (9, "nonsense", "line 10"),
    ],
)
def test_p0400_customread_names_the_line(tmp_path, line, text, said):
    """P0400-CUSTOMREAD: a word where a number belongs is refused naming its line."""
    reference = ReferenceValues(sref_m2=50.0, cref_m=2.5, bref_m=20.0)
    path = _written(tmp_path, reference, [_row(0.5)])
    lines = path.read_text(encoding="ascii").splitlines()
    if line == 9:
        lines[9] = " ".join([text] * len(COEFFICIENT_COLUMNS))
    elif line == 5:
        lines[5] = " ".join(lines[5].split()[:-1] + ["abc"])
    else:
        lines[line] = text
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    with pytest.raises(ProductError, match=said):
        read_custom_polar_format(path)


@pytest.mark.parametrize((), [pytest.param(id="P0400-CUSTOMREAD")])
def test_p0400_customread_reads_a_non_ascii_byte(tmp_path):
    """P0400-CUSTOMREAD: a non-ASCII byte is read back, never a bare UnicodeDecodeError.

    The writer transliterates its own titles; the reader follows the same policy.
    """
    reference = ReferenceValues(sref_m2=50.0, cref_m=2.5, bref_m=20.0)
    path = _written(tmp_path, reference, [_row(0.5)])
    path.write_bytes(path.read_bytes().replace(b"wing", b"w\xe9ng"))
    table = read_custom_polar_format(path)
    assert table is not None
