"""P0400-CRLFGLOSSARY (PFS-2105.034): a CRLF checkout of INPUTS.md is not rewritten.

write_input_glossary compared raw bytes, so a page a checkout turned CRLF never
equalled the LF block it generates: every plan or post rewrote it, mixed.
"""

from __future__ import annotations

import pytest

from pyflightstream.post.glossary import write_input_glossary


@pytest.mark.parametrize((), [pytest.param(id="P0400-CRLFGLOSSARY")])
def test_p0400_crlfglossary_a_crlf_page_is_left_alone(tmp_path):
    """P0400-CRLFGLOSSARY: unchanged content in CRLF is not written, and stays CRLF."""
    page = write_input_glossary(tmp_path)
    crlf = page.read_bytes().replace(b"\n", b"\r\n")
    page.write_bytes(b"# Our notes\r\n\r\n" + crlf)
    changed: list = []
    write_input_glossary(tmp_path, changed=changed)
    assert changed == []
    assert page.read_bytes() == b"# Our notes\r\n\r\n" + crlf


@pytest.mark.parametrize((), [pytest.param(id="P0400-CRLFGLOSSARY")])
def test_p0400_crlfglossary_a_refresh_keeps_the_pages_endings(tmp_path):
    """P0400-CRLFGLOSSARY: a stale block in a CRLF page is refreshed in CRLF, not mixed."""
    page = write_input_glossary(tmp_path)
    text = page.read_bytes()
    begin = text.index(b"-->") + len(b"-->")
    end = text.index(b"<!-- pyflightstream:input-glossary:end")
    stale = text[:begin] + b"\nstale\n" + text[end:]
    page.write_bytes(stale.replace(b"\n", b"\r\n"))
    changed: list = []
    write_input_glossary(tmp_path, changed=changed)
    assert changed == [page]
    assert page.read_bytes() == text.replace(b"\n", b"\r\n")
