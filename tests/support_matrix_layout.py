"""Matrix text at the current layout, for tests that write a matrix inline.

A matrix written with the header of v0.56.0 (no ``MESH_ROUTE`` column) is no longer read
(PFS-2237). A test that composes its matrix as one string with that header and its rows
passes the text through :func:`current_layout`, which is the package's own migration: the
column is inserted after ``GEOMETRY``, unstated, in the header and in every row, and every
other byte stays.
"""

from __future__ import annotations

from pyflightstream.cases.matrix import upgrade_layout_bytes


def current_layout(text: str) -> str:
    """Return ``text`` with every matrix table at the current layout."""
    rewritten, _lines = upgrade_layout_bytes(text.encode("utf-8"))
    return rewritten.decode("utf-8")
