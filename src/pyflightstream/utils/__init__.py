"""Maintainer utilities that are not part of a run.

Pipeline role: none. Nothing in the run pipeline imports this
subpackage, which is what keeps it outside the layer rule rather than
at a position within it (CLAUDE.md Layout, AD-01).

The two positions are stated separately, because one declaration for
the subpackage was wrong for half of it. :mod:`~pyflightstream.utils.manual`
and :mod:`~pyflightstream.utils.errors` import nothing from this package
and sit at the bottom beside :mod:`pyflightstream._errors`, so they can
be used from any layer. :mod:`~pyflightstream.utils.cli` is an ENTRY
POINT above :mod:`pyflightstream.commands`, which it reads to answer
what the database already records, the same shape as
:mod:`pyflightstream.reference`.

What belongs here is the work of KEEPING the package current rather than
of using it: reading a new vendor manual, comparing it against the
command database, reporting what a new release added. That work runs on
the maintainer's machine against licensed material in ``_private/``, and
its output is a draft a person reviews, never a database write.

What does NOT belong here is anything a user's run depends on. A helper
that a script, a campaign or a parser needs is part of that layer and
belongs in it; putting it here would make ``utils`` a bag that everything
reaches into, which is the shape this subpackage is most at risk of
becoming.
"""

from pyflightstream.utils.errors import ManualDraftError
from pyflightstream.utils.manual import (
    TYPE_RULES,
    Coverage,
    Edition,
    ManualCommand,
    SurfaceChange,
    SweptCommand,
    TypeRule,
    coverage_against,
    edition_surfaces,
    parse_script_index,
    parse_signatures,
    propose_layout,
    propose_type,
    read_edition_manifest,
    read_pdf_pages,
    render_chapter,
    render_entry,
    sample_contradiction,
    surface_changes,
    sweep_editions,
    write_chapter,
)

__all__ = [
    "TYPE_RULES",
    "Coverage",
    "Edition",
    "ManualCommand",
    "ManualDraftError",
    "SurfaceChange",
    "SweptCommand",
    "TypeRule",
    "coverage_against",
    "edition_surfaces",
    "parse_script_index",
    "parse_signatures",
    "propose_layout",
    "propose_type",
    "read_edition_manifest",
    "read_pdf_pages",
    "render_chapter",
    "render_entry",
    "sample_contradiction",
    "surface_changes",
    "sweep_editions",
    "write_chapter",
]
