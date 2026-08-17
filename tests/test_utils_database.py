"""The registration transaction, which used to live in an argument parser.

Tier 1, hermetic: a synthetic two-edition manifest, a fake page reader
and a chapter tree in ``tmp_path``. No pdf, no ``[manual]`` extra, no
licensed material.

WHY THIS FILE EXISTS AT ALL. ``pyfs-manual register`` wrote 369 rows into
the shipped command database on 2026-08-17 and had no test of any kind:
the whole subcommand could be deleted and the suite stayed green. Its
sibling writer, ``qa.compat.apply_compat``, has a 1200-line test module.
Two writers into the package's evidence authority with materially
different guarantees is the defect this module and
:mod:`pyflightstream.utils.database` were split out to end.

Every refusal below was reachable before the split and none of them was
observed.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

import pyflightstream.commands
from pyflightstream.commands import CommandEntry, CommandRegistry
from pyflightstream.utils import Edition, EditionVerdict
from pyflightstream.utils.database import register_edition
from pyflightstream.utils.errors import ManualDraftError

#: The real committed chapter tree, located from the package rather than
#: from the current working directory, so the test does not depend on
#: where pytest was invoked.
COMMANDS_DIR = pathlib.Path(pyflightstream.commands.__file__).resolve().parent

# A minimal scripting-reference page in the shape the parser reads. One
# command per page keeps the fixture legible; the parser's own page and
# block handling is tested in tests/test_utils_manual.py.
PAGE = """Function name: {name}
{name} {args}

Sample script command
{name} {args}

Parameter Description
{args} {description}
"""


def _pages(specs):
    """One page per command, numbered from 10."""
    return {
        10 + index: PAGE.format(name=name, args=args, description=description)
        for index, (name, args, description) in enumerate(specs)
    }


def _reader(by_edition):
    """A page reader keyed on the manual path, so two editions differ."""

    def read(manual, *, first, last):
        pages = by_edition[str(manual)]
        return {number: text for number, text in pages.items() if first <= number <= last}

    return read


def _entry(name, chapter):
    return CommandEntry(
        name=name,
        chapter=chapter,
        layout="inline",
        phase="init",
        manual_ref="SRC-750 p.10",
        versions={"26.120": {"status": "documented"}},
    )


@pytest.fixture
def tree(tmp_path):
    """A chapter directory, a registry over it, and the two editions."""
    chapters = tmp_path / "commands"
    chapters.mkdir()
    for chapter, names in (("alpha", ["KEPT", "EDITED"]), ("beta", ["MOVED"])):
        body = {}
        for name in names:
            body[name] = {
                "layout": "inline",
                "phase": "init",
                "manual_ref": "SRC-750 p.10",
                "versions": {"26.120": {"status": "documented"}},
            }
        # write_bytes, not write_text: on Windows the latter translates
        # LF to CRLF, so the CRLF case below would start from a file that
        # already has them and measure nothing.
        (chapters / f"{chapter}.yaml").write_bytes(
            yaml.safe_dump(body, sort_keys=False).encode("utf-8")
        )
    registry = CommandRegistry(
        commands={
            "KEPT": _entry("KEPT", "alpha"),
            "EDITED": _entry("EDITED", "alpha"),
            "MOVED": _entry("MOVED", "beta"),
        }
    )
    old = _pages([("KEPT", "A", "the a"), ("EDITED", "B", "the b"), ("MOVED", "C", "the c")])
    # MOVED repaginates without changing; EDITED gains an argument.
    new = _pages([("KEPT", "A", "the a"), ("EDITED", "B D", "the b"), ("MOVED", "C", "the c")])
    new[13] = new.pop(12)
    editions = [
        Edition(label="26.120", manual=tmp_path / "old.pdf", chapter=(10, 20), source="SRC-750"),
        Edition(label="26.123", manual=tmp_path / "new.pdf", chapter=(10, 20), source="SRC-751"),
    ]
    reader = _reader({str(tmp_path / "old.pdf"): old, str(tmp_path / "new.pdf"): new})
    return chapters, registry, editions, reader


def _run(tree, **kwargs):
    chapters, registry, editions, reader = tree
    return register_edition(
        editions,
        kwargs.pop("build", "26.123"),
        commands_dir=kwargs.pop("commands_dir", chapters),
        registry=registry,
        reader=reader,
        **kwargs,
    )


def test_a_dry_run_classifies_everything_and_touches_nothing(tree):
    """The default is a rehearsal, and it must be a rehearsal of the write."""
    chapters, _, _, _ = tree
    before = {path: path.read_bytes() for path in chapters.glob("*.yaml")}

    result = _run(tree)

    assert {d.name for d in result.writable} == {"KEPT", "MOVED"}
    assert [d.name for d in result.by_verdict(EditionVerdict.CHANGED)] == ["EDITED"]
    assert result.written == 0
    assert result.chapters == ()
    assert {path: path.read_bytes() for path in chapters.glob("*.yaml")} == before


def test_a_write_adds_a_row_only_where_the_reading_says_it_may(tree):
    """The changed command gets nothing, which is the whole safety property."""
    chapters, _, _, _ = tree

    result = _run(tree, write=True)

    assert result.written == 2
    alpha = yaml.safe_load((chapters / "alpha.yaml").read_text(encoding="utf-8"))
    beta = yaml.safe_load((chapters / "beta.yaml").read_text(encoding="utf-8"))
    assert alpha["KEPT"]["versions"]["26.123"] == {
        "status": "documented",
        "note": "SRC-751 p.10, unchanged from SRC-750 p.10",
    }
    assert "26.123" not in alpha["EDITED"]["versions"], (
        "a command the new edition documents DIFFERENTLY must not get a row from a "
        "reading; that is fabricated evidence"
    )
    assert beta["MOVED"]["versions"]["26.123"] == {
        "status": "documented",
        "note": "SRC-751 p.13, unchanged from SRC-750 p.12",
    }


def test_the_note_names_both_editions_by_citation_id_and_both_pages(tree):
    """A build is not an edition, and the claim is about two pages.

    The first version wrote "same grammar as the 26.122 edition" into 368
    shipped rows: a BUILD label where an EDITION is meant, in a package
    whose own citation checker reads notes for SRC ids. It also dropped
    the predecessor's page, which is the one thing that makes the claim
    checkable, since the claim is that TWO pages say the same thing.
    """
    chapters, _, _, _ = tree
    _run(tree, write=True)
    alpha = yaml.safe_load((chapters / "alpha.yaml").read_text(encoding="utf-8"))
    note = alpha["KEPT"]["versions"]["26.123"]["note"]
    assert "SRC-751" in note and "SRC-750" in note
    assert "26.122" not in note and "edition" not in note.split(",")[0]


def test_running_the_write_twice_is_a_no_op_that_says_so(tree):
    """Not a refusal, and the message must not invite a hand edit.

    The first version died on the first already-recorded row with "Fix
    the entry and re-run", after two full manual reads. The entry is not
    broken: the row is there because the previous run worked, and the
    database's whole invariant is that its rows are not hand-edited.
    """
    chapters, _, _, _ = tree
    _run(tree, write=True)
    after_first = {path: path.read_bytes() for path in chapters.glob("*.yaml")}

    second = _run(tree, write=True)

    assert second.written == 0
    assert set(second.already_recorded) == {"KEPT", "MOVED"}
    assert second.writable == ()
    assert {path: path.read_bytes() for path in chapters.glob("*.yaml")} == after_first


def test_an_unregistered_build_is_refused_before_a_manual_is_opened(tree):
    """The refusal that stops 369 rows keyed to a version nothing answers for.

    ``Edition.label`` says in as many words that nothing resolves it,
    which is right for SWEEPING an unregistered build and wrong for
    WRITING one. Unchecked, the run exits reporting success and the
    refusal arrives on the next import of the registry, about some
    unrelated entry.
    """
    chapters, registry, editions, reader = tree
    editions[1] = Edition(
        label="26.999", manual=editions[1].manual, chapter=(10, 20), source="SRC-751"
    )
    opened = []

    def watching(manual, *, first, last):
        opened.append(manual)
        return reader(manual, first=first, last=last)

    with pytest.raises(ManualDraftError, match="not a registered build"):
        register_edition(
            editions,
            "26.999",
            commands_dir=chapters,
            registry=registry,
            reader=watching,
            write=True,
        )
    assert opened == [], "a 400-page read happened before a refusal decidable from the manifest"


def test_an_edition_with_no_citation_id_is_refused(tree):
    """A row written from it would carry the literal text None as provenance."""
    chapters, registry, editions, reader = tree
    editions[1] = Edition(label="26.123", manual=editions[1].manual, chapter=(10, 20))

    with pytest.raises(ManualDraftError, match="carries no source"):
        register_edition(
            editions, "26.123", commands_dir=chapters, registry=registry, reader=reader
        )


def test_the_first_row_of_the_manifest_is_refused(tree):
    """It has no predecessor, so there is nothing to carry forward FROM.

    Without this, ``editions[position - 1]`` at position zero is the LAST
    row, and the run compares the oldest edition against the newest while
    reporting success.
    """
    with pytest.raises(ManualDraftError, match="first row of the manifest"):
        _run(tree, build="26.120")


def test_a_label_the_manifest_does_not_carry_is_refused_naming_the_rows(tree):
    with pytest.raises(ManualDraftError, match="26.120, 26.123"):
        _run(tree, build="26.121")


def test_a_chapter_that_would_not_load_afterwards_leaves_every_file_untouched(tree):
    """Validation before the write, which the sibling writer has and this had not.

    Without it the refusal arrives at the next ``CommandRegistry.load()``,
    as a complaint about an entry rather than about the run that wrote
    it, and the remedy is a revert of every chapter the run touched.
    """
    chapters, registry, editions, reader = tree
    # A note carrying a lone backslash escape: the row renders, the file
    # parses as YAML only because the renderer escapes it. Corrupt the
    # ENTRY instead, which is what the schema check is for.
    beta = chapters / "beta.yaml"
    beta.write_text(
        beta.read_text(encoding="utf-8").replace("phase: init", "phase: not_a_phase"),
        encoding="utf-8",
    )
    before = {path: path.read_bytes() for path in chapters.glob("*.yaml")}

    with pytest.raises(ManualDraftError, match="does not satisfy the command schema"):
        _run(tree, write=True)

    assert {path: path.read_bytes() for path in chapters.glob("*.yaml")} == before, (
        "alpha.yaml was written before beta.yaml failed, so the database is in a state "
        "no single command produced"
    )


def test_a_chapter_file_that_cannot_be_read_leaves_every_file_untouched(tree):
    chapters, _, _, _ = tree
    (chapters / "beta.yaml").unlink()
    before = {path: path.read_bytes() for path in chapters.glob("*.yaml")}

    with pytest.raises(ManualDraftError, match="NOTHING HAS BEEN WRITTEN"):
        _run(tree, write=True)

    assert {path: path.read_bytes() for path in chapters.glob("*.yaml")} == before


def _manifest(tmp_path, editions):
    """The two editions as the manifest file the CLI reads."""
    path = tmp_path / "editions.yaml"
    path.write_text(
        yaml.safe_dump(
            [
                {
                    "label": edition.label,
                    "manual": str(edition.manual),
                    "chapter": f"{edition.chapter[0]}-{edition.chapter[1]}",
                    "source": edition.source,
                }
                for edition in editions
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_the_command_line_reaches_the_transaction(tmp_path, tree, monkeypatch, capsys):
    """The dispatch itself, which could be deleted with the suite green.

    Measured by the QA pass on 2026-08-17: removing ``register`` from
    ``pyfs-manual`` entirely left 164 tests passing, because every test
    of this subcommand went through the library. The library tests above
    are the right shape and they cannot see an unwired command.
    """
    from pyflightstream.utils import cli as cli_module
    from pyflightstream.utils import database as database_module
    from pyflightstream.utils import manual as manual_module

    chapters, registry, editions, reader = tree
    for edition in editions:
        edition.manual.write_bytes(b"not a real pdf; the reader is patched")
    monkeypatch.setattr(manual_module, "read_pdf_pages", reader)
    # The CLI passes no registry, so the SHIPPED one would answer and
    # this fixture's three synthetic commands would all read as
    # undatabased. Patching where the transaction looks it up is what
    # makes the dispatch measure this fixture rather than the shipped
    # database, which would drift under the test every release.
    monkeypatch.setattr(database_module.CommandRegistry, "load", classmethod(lambda cls: registry))

    code = cli_module.main(
        [
            "register",
            "--editions",
            str(_manifest(tmp_path, editions)),
            "--fs-version",
            "26.123",
            "--commands-dir",
            str(chapters),
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "2 row(s) would be written into" in out, out
    assert str(chapters) in out, "a dry run that does not name its destination is not a rehearsal"
    assert "1 described differently" in out
    alpha = yaml.safe_load((chapters / "alpha.yaml").read_text(encoding="utf-8"))
    assert "26.123" not in alpha["KEPT"]["versions"], "a dry run wrote"


def test_a_command_line_refusal_does_not_exit_with_the_usage_code(tmp_path, tree, monkeypatch):
    """Exit 2 means "you typed it wrong", and this is not that.

    ``main``'s own docstring states the contract: a usage error exits 2
    through argparse, and a refusal from the library is a different
    thing. Routing "this entry already records that build" through
    ``parser.error`` made every database-state refusal look like a
    mistyped command line.
    """
    from pyflightstream.utils import cli as cli_module
    from pyflightstream.utils import manual as manual_module

    chapters, _, editions, reader = tree
    for edition in editions:
        edition.manual.write_bytes(b"not a real pdf; the reader is patched")
    monkeypatch.setattr(manual_module, "read_pdf_pages", reader)

    code = cli_module.main(
        [
            "register",
            "--editions",
            str(_manifest(tmp_path, editions)),
            "--fs-version",
            "26.120",
            "--commands-dir",
            str(chapters),
        ]
    )
    assert code == 1, "a library refusal exited with the usage code"


def test_a_missing_manifest_is_a_usage_error_like_its_siblings(tmp_path, tree):
    """`sweep` and `citations` trap this; `register` showed a traceback."""
    from pyflightstream.utils import cli as cli_module

    chapters, _, _, _ = tree
    with pytest.raises(SystemExit) as raised:
        cli_module.main(
            [
                "register",
                "--editions",
                str(tmp_path / "no-such-manifest.yaml"),
                "--fs-version",
                "26.123",
                "--commands-dir",
                str(chapters),
            ]
        )
    assert raised.value.code == 2


def test_a_commands_dir_that_is_not_a_directory_is_refused_before_any_read(tmp_path, tree):
    """--commands-dir exists to rehearse, and the rehearsal never checked it.

    It was resolved only under ``--write`` and only after two 400-page
    reads, which is the shape this module's own help text was written to
    close.
    """
    from pyflightstream.utils import cli as cli_module

    _, _, editions, _ = tree
    with pytest.raises(SystemExit) as raised:
        cli_module.main(
            [
                "register",
                "--editions",
                str(_manifest(tmp_path, editions)),
                "--fs-version",
                "26.123",
                "--commands-dir",
                str(tmp_path / "nowhere"),
            ]
        )
    assert raised.value.code == 2


def test_the_splice_works_on_a_real_committed_chapter_file(tmp_path):
    """The primitive encodes the chapter format; pin it to the real one.

    ``insert_version_row`` carries the ``commands`` file format as bare
    literals: the two-space ``versions:`` key, the four-space row indent,
    the top-level-key terminator. Everywhere else in its module, upward
    knowledge is declared as a runtime-checkable Protocol and pinned by a
    test asserting the real registry satisfies it; this one had neither,
    and its own tests used a synthetic five-line string. If ``commands``
    ever changes chapter indentation or block shape, those tests stay
    green and the real database is mis-edited.

    So this runs the splice against a REAL committed chapter file and
    re-validates the result with the real schema, which is the shape the
    Protocol conformance test already uses.
    """
    from pyflightstream.commands import CommandEntry
    from pyflightstream.utils.manual import insert_version_row
    from pyflightstream.versions import known_versions

    registered = [version.canonical for version in known_versions()]
    chapters = sorted(COMMANDS_DIR.glob("*.yaml"))
    real = [path for path in chapters if not path.name.startswith("_")]
    assert len(real) > 20, f"only {len(real)} chapter files found; the walk is broken"

    checked = 0
    for path in real[:8]:
        text = path.read_bytes().decode("utf-8")
        body = yaml.safe_load(text)
        # A REGISTERED build the entry does not already record, because
        # the schema refuses an unregistered one and would fail this test
        # for a reason that has nothing to do with the splice. An entry
        # already carrying every registered build is skipped rather than
        # forced.
        target = spliced = None
        for name, entry in body.items():
            if not isinstance(entry, dict) or not entry.get("versions"):
                continue
            free = [known for known in registered if known not in entry["versions"]]
            if free:
                target, spliced = name, free[0]
                break
        if target is None:
            continue
        edited = insert_version_row(
            text,
            command=target,
            canonical=spliced,
            status="documented",
            note='a note with a "quote" and a backslash ' + chr(92),
        )
        reparsed = yaml.safe_load(edited)
        assert reparsed[target]["versions"][spliced]["status"] == "documented"
        # EVERY OTHER ENTRY IS UNTOUCHED, which is the property that
        # matters when the file has thirty of them.
        for name in body:
            if name == target:
                continue
            assert reparsed[name] == body[name], f"{path.name}: editing {target} moved {name}"
        # And the result still satisfies the real schema.
        entry = dict(reparsed[target])
        CommandEntry(name=target, chapter=path.stem, **entry)
        # LINE ENDINGS PRESERVED, and one committed chapter file here is
        # CRLF on disk, which is the case that makes this worth asserting
        # against the real tree rather than against a synthetic string.
        crlf = chr(13) + chr(10)
        assert edited.count(crlf) == text.count(crlf) + (1 if crlf in text else 0)
        checked += 1
    assert checked >= 5, f"only {checked} real chapter files were exercised"


def test_the_line_endings_of_a_crlf_chapter_survive(tree):
    """One chapter file in this repository is CRLF on disk.

    ``read_text`` translates CRLF to LF before anything can preserve it,
    so the whole file comes back LF and the diff is every line. The
    transaction reads BYTES for that reason.
    """
    chapters, _, _, _ = tree
    alpha = chapters / "alpha.yaml"
    alpha.write_bytes(alpha.read_bytes().replace(b"\n", b"\r\n"))
    before = alpha.read_bytes().count(b"\r\n")

    _run(tree, write=True)

    after = alpha.read_bytes()
    assert after.count(b"\r\n") == before + 1
    assert b"\n" not in after.replace(b"\r\n", b"")
