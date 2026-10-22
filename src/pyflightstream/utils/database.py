"""Carry a build's documentation forward into the command database.

Maintainer tooling above commands: this module constructs the schema and
owns the registration transaction used by the thin pyfs-manual CLI.
Like qa.compat.apply_compat, it validates every rewritten chapter before
writing any file (CONTRIBUTING.md invariant 3).

Registration requires a canonical build in the version registry and a
manifest source citation. Edition labels can describe unregistered builds
for comparisons, but may not write unregistered database rows. A comparison
may omit source; a written documented row must cite its manual.

Build edits in memory, reparse them and reconstruct each touched entry
through CommandEntry before writing. Already-recorded rows are counted
and excluded, making a repeated --write a reported no-op.
"""

from __future__ import annotations

import dataclasses
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

import yaml

import pyflightstream._textio as _textio
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
    withheld : tuple of EditionDelta
        Unchanged commands whose predecessor row is ``broken`` or a
        MEASURED ``removed`` (the row cites a run). A reading of the new
        edition cannot carry that measurement forward, so no row is
        written for them; each needs a probe on the new build.
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
    withheld: tuple[EditionDelta, ...] = ()
    written: int = 0
    chapters: tuple[Path, ...] = field(default_factory=tuple)

    def by_verdict(self, verdict: EditionVerdict) -> tuple[EditionDelta, ...]:
        """Every delta carrying one verdict, in name order."""
        return tuple(delta for delta in self.deltas if delta.verdict is verdict)


def _note(target: Edition, previous: Edition, delta: EditionDelta) -> str:
    """Record both manual edition IDs and both compared page numbers.

    The claim concerns matching grammar on two pages, so each page must
    remain identifiable by its FSM citation.
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


def _write_all_or_none(edited: Mapping[Path, str], originals: Mapping[Path, str]) -> None:
    """Replace every chapter of ``edited``, or leave every one as it was.

    Each new text goes to a sibling temporary file first; only when all of
    them are on disk are the chapters replaced. A failure while writing
    the temporaries replaces nothing; a failure while replacing puts back
    the chapters already replaced from their original bytes. Either way
    the OSError arrives as a ManualDraftError naming the files.
    """
    pending: dict[Path, Path] = {}
    try:
        for path, text in edited.items():
            handle, name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".register-tmp", dir=path.parent
            )
            os.close(handle)
            temporary = Path(name)
            pending[path] = temporary
            _textio.write_text(temporary, text)
    except OSError as error:
        for temporary in pending.values():
            temporary.unlink(missing_ok=True)
        raise ManualDraftError(
            f"could not write the new text of {path.name} ({error}); no chapter was "
            f"replaced: {', '.join(sorted(p.name for p in edited))} are unchanged"
        ) from error
    replaced: list[Path] = []
    try:
        for path, temporary in pending.items():
            os.replace(temporary, path)
            replaced.append(path)
    except OSError as error:
        failed_path = path
        not_put_back: list[str] = []
        for restored in replaced:
            try:
                _textio.write_text(restored, originals[restored])
            except OSError:
                not_put_back.append(restored.name)
        for temporary in pending.values():
            temporary.unlink(missing_ok=True)
        if not_put_back:
            raise ManualDraftError(
                f"could not replace {failed_path.name} ({error}), and could not put back "
                f"{', '.join(not_put_back)} either: those chapters hold their new text, "
                "and every other chapter is as it was"
            ) from error
        raise ManualDraftError(
            f"could not replace {failed_path.name} ({error}); the chapters already replaced "
            f"({', '.join(p.name for p in replaced) or 'none'}) were put back, so no "
            "chapter changed"
        ) from error


def _refuse_unlabelled_build(build: str, labels: Sequence[str]) -> NoReturn:
    """Refuse a build the manifest has no row labelled, naming the closest true cause."""
    # Resolve aliases before testing manifest membership so the refusal
    # identifies the canonical build or lists ambiguous candidates. This
    # requires no manual read and avoids misdiagnosing a correctly labelled
    # manifest when the caller supplies a vendor release name.
    try:
        resolved = resolve(build)
    except AmbiguousVersionAliasError as ambiguous:
        carried = [name for name in ambiguous.candidates if name in labels]
        if carried:
            raise ManualDraftError(
                f"the manifest has no row labelled {build!r}, and {build} is a "
                f"vendor release name shared by "
                f"{', '.join(ambiguous.candidates)}. The manifest carries "
                f"{', '.join(carried)}; re-run with the canonical identifier of "
                "the edition you actually read, since a documented row is keyed "
                "by that identifier and one edition documents one build."
            ) from None
        raise ManualDraftError(
            f"the manifest has no row labelled {build!r}, and {build} is a "
            f"vendor release name shared by "
            f"{', '.join(ambiguous.candidates)}, none of which the manifest "
            "carries either. Add the row for the edition you read, keyed by "
            "its canonical identifier."
        ) from None
    except UnknownVersionError:
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


def _registered_position(editions: Sequence[Edition], build: str) -> int:
    """Return the manifest position of ``build``, refusing a label that cannot be registered."""
    labels = [edition.label for edition in editions]
    if build not in labels:
        _refuse_unlabelled_build(build, labels)
    position = labels.index(build)
    if position == 0:
        raise ManualDraftError(
            f"{build} is the first row of the manifest, so it has no predecessor to "
            "compare against. This subcommand carries documentation FORWARD; a first "
            "edition is drafted, not registered"
        )
    # Check the manifest and registry before opening either manual.
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
    return position


def _read_chapter(path: Path) -> tuple[str, Mapping[str, Any]]:
    """Return a chapter file decoded from bytes, and the YAML it holds.

    DECODED FROM BYTES, so the line endings survive the round trip.
    ``read_text`` translates CRLF to LF before anything can preserve it.
    """
    try:
        text = path.read_bytes().decode("utf-8")
    except OSError as error:
        raise ManualDraftError(f"cannot read {path}: {error}. NOTHING HAS BEEN WRITTEN") from None
    try:
        recorded = yaml.safe_load(text) or {}
    except yaml.YAMLError as error:
        raise ManualDraftError(
            f"{path} is not valid YAML ({error}). NOTHING HAS BEEN WRITTEN"
        ) from None
    return text, recorded


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
    position = _registered_position(editions, build)
    target = editions[position]
    previous = editions[position - 1]
    for edition in (target, previous):
        if not edition.source:
            raise ManualDraftError(
                f"the manifest row for {edition.label} carries no source, so a row "
                "written from it would cite nothing. Every documented row states which "
                "edition was read, as a manual_ref would spell it, for example FSM-26.123"
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
    withheld: list[EditionDelta] = []
    for chapter, rows in sorted(by_chapter.items()):
        texts[chapter], recorded = _read_chapter(commands_dir / f"{chapter}.yaml")
        for delta in rows:
            entry = recorded.get(delta.name) or {}
            # ALREADY RECORDED IS NOT AN ERROR. A second --write is a
            # no-op that says so, rather than dying on the first such row
            # with a message reading as a failure of the whole run and
            # telling the operator to "fix the entry", which is an
            # invitation to hand-edit a database whose rows are not
            # hand-edited.
            versions = entry.get("versions") or {}
            before = versions.get(previous.label) or {}
            measured_removed = before.get("status") == "removed" and bool(
                before.get("report") or before.get("probe_ref")
            )
            if target.label in versions:
                already.append(delta.name)
            elif before.get("status") == "broken" or measured_removed:
                # A probe measured this command broken or refused on the
                # predecessor build; an unchanged manual page says nothing
                # about the solver, so it cannot carry that forward as
                # "documented".
                withheld.append(delta)
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
        withheld=tuple(withheld),
    )
    if not write or not writable:
        return result

    # Build and validate every edit before writing any chapter so a late
    # refusal cannot leave a partially registered database.
    edited: dict[Path, str] = {}
    originals: dict[Path, str] = {}
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
        originals[path] = texts[chapter]

    _write_all_or_none(edited, originals)
    # REPLACED, not rebuilt. The class docstring says a dry run and a
    # write report the same object, and nothing enforced it: seven fields
    # were repeated across two constructions, so one added to the write
    # and not the rehearsal would make them disagree silently, in the
    # object whose whole purpose is that they cannot.
    return dataclasses.replace(result, written=written, chapters=tuple(edited))
