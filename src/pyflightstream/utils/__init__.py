"""Maintainer utilities that are not part of a run.

Pipeline role: none. Nothing in the run pipeline imports this
subpackage, and this subpackage imports nothing from it. It sits at the
bottom of the layer rule beside :mod:`pyflightstream._errors`, so a
utility can be used from any layer without inverting the dependency
direction (CLAUDE.md Layout, AD-01).

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
    Coverage,
    ManualCommand,
    coverage_against,
    parse_script_index,
    parse_signatures,
    propose_layout,
    propose_type,
    read_pdf_pages,
    render_chapter,
    render_entry,
    write_chapter,
)

__all__ = [
    "Coverage",
    "ManualDraftError",
    "ManualCommand",
    "coverage_against",
    "parse_script_index",
    "parse_signatures",
    "propose_layout",
    "propose_type",
    "read_pdf_pages",
    "render_chapter",
    "render_entry",
    "write_chapter",
]
