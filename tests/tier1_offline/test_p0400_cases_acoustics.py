"""Tier 1: a byte order mark opens an observer file or a CCS file without changing it (0.40.0)."""

from pyflightstream.cases._ccs import ccs_component_names
from pyflightstream.cases.acoustics import read_observers_file


def test_p0400_observer_file_with_a_byte_order_mark_is_read(tmp_path):
    """P0400-BOM (PFS-2095.039): Excel's CSV UTF-8 still opens with a count of observers."""
    path = tmp_path / "observers.csv"
    path.write_bytes(b"\xef\xbb\xbf2\r\n0.0,0.0,1.0\r\n1.0,0.0,0.0\r\n")
    assert read_observers_file(path) == ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0))


def test_p0400_ccs_component_count_reads_past_a_byte_order_mark():
    """P0400-BOM (PFS-2095.039): the first Component line counts, BOM or not."""
    text = "\ufeffComponent;WING\nsection data\nComponent;TAIL\n"
    assert ccs_component_names(text) == ("WING", "TAIL")
