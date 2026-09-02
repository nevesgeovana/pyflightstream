"""Maintainer utilities that are not part of a run.

Pipeline role: none. Nothing in the run pipeline imports this
subpackage, which is what keeps it outside the layer rule rather than
at a position within it (CONTRIBUTING.md Layout, AD-01).

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
the maintainer's machine against licensed material in ``_private/``.

ITS OUTPUT WAS A DRAFT A PERSON REVIEWS AND NEVER A DATABASE WRITE, and
that stopped being true on 2026-08-17. ``pyfs-manual register`` writes
``documented`` version rows for the commands a new edition describes
exactly as its predecessor did, which is the one write that carries no
judgement: it copies nothing and asserts nothing beyond "these two
editions say the same thing", and anything they do not it reports for a
person to read. Everything else here is still a draft.

The layer statement above is unchanged by it, and the split is why.
:func:`~pyflightstream.utils.manual.insert_version_row` takes the text
of a chapter file and returns the edited text; it opens nothing.

THE IO LIVES IN :mod:`~pyflightstream.utils.database`, and this
paragraph said ``cli`` until 2026-08-17, when the registration
transaction was lifted out of the argument parser. That module reads and
writes the chapter bytes, validates every edit against the command
schema before any of them reaches the disk, and is the one importable
home of a registration.

SO THIS SUBPACKAGE HAS THREE POSITIONS, not the two the statement above
enumerates: ``manual`` and ``errors`` at the bottom, and ``cli`` and
``database`` above :mod:`pyflightstream.commands`. ``database`` is
deliberately NOT re-exported from this module, and that is load bearing
rather than an oversight: re-exporting it would make
``import pyflightstream.utils`` pull :mod:`pyflightstream.commands` in,
and cost ``manual`` the property that it can be used from any layer.
Import it by its own name.

What does NOT belong here is anything a user's run depends on. A helper
that a script, a campaign or a parser needs is part of that layer and
belongs in it; putting it here would make ``utils`` a bag that everything
reaches into, which is the shape this subpackage is most at risk of
becoming.
"""

from pyflightstream.utils.errors import ManualDraftError
from pyflightstream.utils.manual import (
    TYPE_RULES,
    CommandEntryLike,
    Coverage,
    Edition,
    EditionDelta,
    EditionVerdict,
    ManualCommand,
    Reachability,
    RegistryLike,
    StaleCitation,
    SurfaceChange,
    SweptCommand,
    TypeRule,
    UnreachableCommand,
    VersionRowLike,
    coverage_against,
    documentation_delta,
    edition_surfaces,
    insert_version_row,
    parse_script_index,
    parse_signatures,
    propose_layout,
    propose_type,
    read_edition,
    read_edition_manifest,
    read_pdf_pages,
    render_chapter,
    render_entry,
    sample_contradiction,
    stale_citations,
    surface_changes,
    sweep_editions,
    unreachable_commands,
    write_chapter,
)

__all__ = [
    "TYPE_RULES",
    "Coverage",
    "Edition",
    "EditionDelta",
    "EditionVerdict",
    "CommandEntryLike",
    "ManualCommand",
    "Reachability",
    "RegistryLike",
    "ManualDraftError",
    "SurfaceChange",
    "UnreachableCommand",
    "VersionRowLike",
    "SweptCommand",
    "TypeRule",
    "coverage_against",
    "documentation_delta",
    "edition_surfaces",
    "insert_version_row",
    "parse_script_index",
    "parse_signatures",
    "propose_layout",
    "propose_type",
    "read_edition",
    "read_edition_manifest",
    "read_pdf_pages",
    "render_chapter",
    "render_entry",
    "sample_contradiction",
    "StaleCitation",
    "stale_citations",
    "surface_changes",
    "sweep_editions",
    "unreachable_commands",
    "write_chapter",
]
