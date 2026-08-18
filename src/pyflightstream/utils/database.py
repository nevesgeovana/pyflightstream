"""Carry a build's documentation forward into the command database.

Pipeline role: maintainer tooling beside :mod:`pyflightstream.utils.cli`,
above :mod:`pyflightstream.commands` because it constructs the schema it
writes, and the ONE importable home of the registration transaction.

WHY IT IS A MODULE AND NOT A CLI FUNCTION, which is the correction of
2026-08-17 rather than a preference. The command database is this
package's evidence authority (CLAUDE.md invariant 3) and it has two
writers: :func:`pyflightstream.qa.compat.apply_compat`, which promotes a
status from a committed probe report, and this one, which writes a
``documented`` row from a reading. The first is a library function with
its own test module and it validates every chapter it rewrites before a
byte reaches the disk. The second was written inside ``pyfs-manual``'s
argument parser, so nothing importable could perform a registration,
nothing could test one, and it wrote unvalidated bytes. Two writers into
one authority with materially different guarantees is the defect; the
architecture chapter's own rule, that a CLI is a thin argument layer over
the public Python API, is what it broke.

WHAT IT REFUSES, and each of these was reachable before it existed:

  A BUILD THE VERSION REGISTRY DOES NOT KNOW. :attr:`Edition.label` says
  in as many words that nothing resolves it, which is right for SWEEPING
  an unregistered build and wrong for WRITING one. Unchecked, a manifest
  label that is not a registered canonical writes hundreds of rows keyed
  to a version ``_meta.yaml`` does not carry, the run exits reporting
  success, and the refusal arrives on the next import of the registry as
  a complaint about some unrelated entry. The remedy would be a revert of
  thirty chapter files.

  A MANIFEST ROW WITH NO CITATION ID. ``source`` is optional in the
  manifest because a sweep does not need one. A row written from an
  edition with no ``source`` carries the literal text ``None`` as its
  provenance, in every row, and nothing downstream rejects a note.

  A CHAPTER THE WRITE WOULD LEAVE INVALID. Every edit is built in memory,
  re-parsed, and every touched entry reconstructed through
  :class:`~pyflightstream.commands.CommandEntry` before anything is
  written, which is what ``apply_compat`` does and this path did not.

Re-running is not an error. A build already recorded for a command is
counted and excluded rather than refused, so a second ``--write`` is a
no-op that says so. The first version refused on the first such row,
after two full manual reads, with a message telling the operator to "fix
the entry", which is an invitation to hand-edit a database whose whole
invariant is that its rows are not hand-edited.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from pyflightstream.commands import CommandEntry, CommandRegistry
from pyflightstream.utils.errors import ManualDraftError
from pyflightstream.utils.manual import (
    Edition,
    EditionDelta,
    EditionVerdict,
    documentation_delta,
    insert_version_row,
    read_edition,
)
from pyflightstream.versions import (
    AmbiguousVersionAliasError,
    UnknownVersionError,
    known_versions,
    resolve,
)

__all__ = ["Registration", "register_edition"]


@dataclass(frozen=True, kw_only=True)
class Registration:
    """What one registration would write, and everything it would not.

    Returned by :func:`register_edition` whether or not it wrote, so a
    dry run and a write report the same object and a caller cannot
    render a rehearsal that differs from what happens.

    Attributes
    ----------
    target, previous : Edition
        The edition being registered and the one it is carried forward
        from, in that order.
    deltas : tuple of EditionDelta
        Every recorded command, classified. Grouped for a caller by
        :meth:`by_verdict`.
    writable : tuple of EditionDelta
        The unchanged commands that do NOT already carry a row for this
        build, which is exactly what a write touches.
    already_recorded : tuple of str
        Unchanged commands whose entry already records this build. Not
        an error and not written again.
    undatabased : tuple of str
        Commands the new edition documents that the database does not
        record at all. Entering one is a different piece of work from
        carrying an existing one forward, so they are reported and never
        written.
    written : int
        Rows actually written; zero on a dry run.
    chapters : tuple of Path
        Chapter files actually written; empty on a dry run.
    directory : Path
        Where the rows would go or did go. A dry run reports it so the
        rehearsal names its own destination.
    """

    target: Edition
    previous: Edition
    deltas: tuple[EditionDelta, ...]
    writable: tuple[EditionDelta, ...]
    already_recorded: tuple[str, ...]
    undatabased: tuple[str, ...]
    directory: Path
    written: int = 0
    chapters: tuple[Path, ...] = field(default_factory=tuple)

    def by_verdict(self, verdict: EditionVerdict) -> tuple[EditionDelta, ...]:
        """Every delta carrying one verdict, in name order."""
        return tuple(delta for delta in self.deltas if delta.verdict is verdict)


def _note(target: Edition, previous: Edition, delta: EditionDelta) -> str:
    """Provenance of one carried-forward row.

    IT NAMES BOTH EDITIONS BY THEIR CITATION ID and both pages. The
    first version wrote "same grammar as the 26.122 edition", which
    names a BUILD where an EDITION is meant, in 368 shipped rows. This
    package is careful that the two are different objects, and its own
    citation checker reads notes for ``SRC-nnn`` ids, so the note taught
    the confusion that checker exists to catch. Dropping the
    predecessor's page also cost the reader the one thing that makes the
    claim checkable: the claim is that TWO pages say the same thing, so
    a note naming one of them cannot be verified without redoing the
    comparison.
    """
    return (
        f"{target.source} p.{delta.page}, unchanged from {previous.source} p.{delta.previous_page}"
    )


def _validate_chapter(path: Path, text: str, names: list[str]) -> None:
    """Refuse a rewritten chapter that the command schema will not take.

    Takes the TEXT rather than the path, so a rewrite is rejected before
    it reaches the disk; reading the file back would mean the file had
    already been written, which is the partial-registration state this
    module promises not to leave behind.

    It duplicates the SHAPE of ``qa.compat._validate_chapter`` and not
    its code, deliberately: that one raises the qa layer's own evidence
    error, which this module sits below and must not import. The two
    differ in the exception they raise and in nothing else.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ManualDraftError(
            f"{path.name}: the rewritten chapter does not parse as YAML ({error}). "
            "NOTHING HAS BEEN WRITTEN"
        ) from None
    chapter = path.stem
    for name in names:
        try:
            CommandEntry(name=name, chapter=chapter, **data[name])
        except ValueError as error:
            raise ManualDraftError(
                f"{path.name}: after this registration the {name} entry does not satisfy "
                f"the command schema ({error}). NOTHING HAS BEEN WRITTEN. If the entry "
                "was already invalid before this run, repair it first"
            ) from None


def register_edition(
    editions: Sequence[Edition],
    build: str,
    *,
    commands_dir: Path,
    registry: CommandRegistry | None = None,
    reader: Callable[..., Mapping[int, str]] | None = None,
    write: bool = False,
) -> Registration:
    """Write ``documented`` rows for the commands a new edition did not change.

    Parameters
    ----------
    editions : sequence of Edition
        The edition manifest, in release order.
    build : str
        Which row of it to register. Must be a manifest label AND a
        registered build; see this module's docstring for why both.
    commands_dir : Path
        Directory holding the chapter files. Point it at a copy to
        rehearse a write against real data.
    registry : CommandRegistry, optional
        The database to classify against, defaulting to the shipped one.
    reader : callable, optional
        Page reader, passed through to :func:`read_edition`, so this
        function is testable without a pdf and without the ``[manual]``
        extra.
    write : bool, default False
        Write the rows. The default is a rehearsal that opens the
        manuals, classifies everything and touches nothing.

    Returns
    -------
    Registration
        What was written, and everything that was not.

    Raises
    ------
    ManualDraftError
        If the build is not a manifest label, is the first row of the
        manifest, is not a registered build, has no citation id, or if
        any chapter the write would produce is not valid afterwards. A
        chapter file that cannot be read raises it too. In every case
        nothing has been written.
    """
    labels = [edition.label for edition in editions]
    if build not in labels:
        # THE MOST USEFUL REFUSAL FIRST, and it used to be unreachable
        # for the input that most needs it. Membership was tested before
        # anything resolved, so `--fs-version 26.0` against a correctly
        # labelled manifest was told "no row labelled '26.0'", while the
        # tool already knew, one line later, that 26.0 names 26.000 and
        # that the manifest carries THAT. The reader went editing a
        # manifest that was right. Resolving costs nothing and opens no
        # manual, so it is asked here.
        try:
            resolved = resolve(build)
        except (UnknownVersionError, AmbiguousVersionAliasError):
            resolved = None
        if resolved is not None and resolved.canonical in labels:
            raise ManualDraftError(
                f"the manifest has no row labelled {build!r}, but {build} is a vendor "
                f"display name for {resolved.canonical}, which the manifest DOES carry. "
                f"Re-run with {resolved.canonical}: a documented row is keyed by the "
                "canonical identifier, so the label and the key are one string."
            )
        raise ManualDraftError(
            f"the manifest has no row labelled {build!r}; it carries " + ", ".join(labels)
        )
    position = labels.index(build)
    if position == 0:
        raise ManualDraftError(
            f"{build} is the first row of the manifest, so it has no predecessor to "
            "compare against. This subcommand carries documentation FORWARD; a first "
            "edition is drafted, not registered"
        )
    # BEFORE EITHER MANUAL IS OPENED. Both refusals are decidable from
    # the manifest and the registry, and a 400-page read is what they
    # used to cost.
    try:
        known = resolve(build)
    except (UnknownVersionError, AmbiguousVersionAliasError) as error:
        raise ManualDraftError(
            f"{build} is a manifest label and is not a registered build ({error}). A "
            "documented row is keyed by the canonical identifier, so registering "
            "against an unregistered one writes rows the registry cannot answer for. "
            "Register the build first; the ordered list in commands/_meta.yaml is the "
            "only ordering authority, and it currently carries "
            + ", ".join(str(known) for known in known_versions())
        ) from None

    # AND IT MUST BE THE CANONICAL, not merely something that RESOLVES.
    # `resolve` accepts a display alias that names exactly one build, and
    # three do today (25.0, 25.1, 26.0), so a manifest row labelled that
    # way cleared the gate, both manuals were read, and rows keyed to the
    # ALIAS were built. The refusal then arrived from the command schema,
    # about an unregistered version, phrased as a complaint about an
    # entry rather than about the label that caused it.
    if known.canonical != build:
        raise ManualDraftError(
            f"{build} is a vendor display name for {known.canonical}, not a canonical "
            "identifier. A documented row is keyed by the canonical identifier, so a "
            "row written under an alias is one the registry cannot answer for. Label "
            f"the manifest row {known.canonical} and re-run."
        )

    target = editions[position]
    previous = editions[position - 1]
    for edition in (target, previous):
        if not edition.source:
            raise ManualDraftError(
                f"the manifest row for {edition.label} carries no source, so a row "
                "written from it would cite nothing. Every documented row states which "
                "edition was read, as a manual_ref would spell it, for example SRC-751"
            )

    registry = registry or CommandRegistry.load()
    current = read_edition(target, reader=reader)
    earlier = read_edition(previous, reader=reader)
    deltas = documentation_delta(earlier, current, recorded=registry.commands)

    unchanged = [d for d in deltas if d.verdict is EditionVerdict.UNCHANGED]
    by_chapter: dict[str, list[EditionDelta]] = {}
    for delta in unchanged:
        by_chapter.setdefault(registry.commands[delta.name].chapter, []).append(delta)

    # READ THE CHAPTER FILES DURING CLASSIFICATION, and read what is
    # already recorded OUT OF THEM rather than out of the registry.
    #
    # The registry is the SHIPPED database and `commands_dir` may be a
    # copy: `--commands-dir` exists precisely so a write can be rehearsed
    # somewhere else. Asking the registry what a file in another
    # directory already contains answers a different question, and it
    # answers it wrongly in both directions, so a rehearsal reports a
    # count the real run will not produce.
    #
    # DECODED FROM BYTES, so the line endings survive the round trip.
    # read_text translates CRLF to LF before anything can preserve it,
    # and insert_version_row's preservation then looks at a string that
    # has none, so the whole file comes back LF. Its `newline=` keyword
    # is NOT the fix: that is 3.13 only and raises TypeError on this
    # tree's 3.12 against a requires-python of 3.11, which is how this
    # correction first shipped and failed.
    texts: dict[str, str] = {}
    already: list[str] = []
    writable: list[EditionDelta] = []
    for chapter, rows in sorted(by_chapter.items()):
        path = commands_dir / f"{chapter}.yaml"
        try:
            texts[chapter] = path.read_bytes().decode("utf-8")
        except OSError as error:
            raise ManualDraftError(
                f"cannot read {path}: {error}. NOTHING HAS BEEN WRITTEN"
            ) from None
        recorded = yaml.safe_load(texts[chapter]) or {}
        for delta in rows:
            entry = recorded.get(delta.name) or {}
            # ALREADY RECORDED IS NOT AN ERROR. A second --write is a
            # no-op that says so, rather than dying on the first such row
            # with a message reading as a failure of the whole run and
            # telling the operator to "fix the entry", which is an
            # invitation to hand-edit a database whose rows are not
            # hand-edited.
            if target.label in (entry.get("versions") or {}):
                already.append(delta.name)
            else:
                writable.append(delta)

    undatabased = tuple(sorted(set(current) - set(registry.commands)))
    result = Registration(
        target=target,
        previous=previous,
        deltas=deltas,
        writable=tuple(writable),
        already_recorded=tuple(sorted(already)),
        undatabased=undatabased,
        directory=commands_dir,
    )
    if not write or not writable:
        return result

    # EVERY EDIT IS BUILT AND VALIDATED BEFORE ANY FILE IS WRITTEN. The
    # first version wrote each chapter inside the loop, so a refusal on a
    # late chapter left the earlier ones on disk and the database was in
    # a state no single command produced.
    edited: dict[Path, str] = {}
    written = 0
    per_chapter: dict[str, list[EditionDelta]] = {}
    for delta in writable:
        per_chapter.setdefault(registry.commands[delta.name].chapter, []).append(delta)
    for chapter, rows in sorted(per_chapter.items()):
        path = commands_dir / f"{chapter}.yaml"
        text = texts[chapter]
        for delta in rows:
            text = insert_version_row(
                text,
                command=delta.name,
                canonical=target.label,
                status="documented",
                note=_note(target, previous, delta),
            )
            written += 1
        _validate_chapter(path, text, [delta.name for delta in rows])
        edited[path] = text

    for path, text in edited.items():
        path.write_bytes(text.encode("utf-8"))
    # REPLACED, not rebuilt. The class docstring says a dry run and a
    # write report the same object, and nothing enforced it: seven fields
    # were repeated across two constructions, so one added to the write
    # and not the rehearsal would make them disagree silently, in the
    # object whose whole purpose is that they cannot.
    return dataclasses.replace(result, written=written, chapters=tuple(edited))
