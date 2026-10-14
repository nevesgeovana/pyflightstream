"""Regression coverage grouped by subject."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import pyflightstream.utils.database as _core_small_database__database
from pyflightstream.commands import Phase
from pyflightstream.utils import (
    ManualCommand,
    cli,
    insert_version_row,
    parse_signatures,
    read_edition_manifest,
    render_entry,
)
from pyflightstream.utils import database as _core_small_review_scripts__database
from pyflightstream.utils.errors import ManualDraftError
from pyflightstream.utils.manual import _PHASE_BY_SECTION
from tests.tier1_offline.test_goal028_coherence_band_per_export import (
    _instrument as _core_small_coherence_total___instrument,
)
from tests.tier1_offline.test_p0320_changelog_fragments import (
    _checkout as _core_small_review_scripts___checkout,
)
from tests.tier1_offline.test_p0320_changelog_fragments import (
    _script as _core_small_review_scripts___script,
)
from tests.tier1_offline.test_p0400_core_small_parity import (
    _load as _core_small_review_scripts___load,
)
from tests.tier1_offline.test_p0400_core_small_prove_extras import (
    _load as _core_small_review_scripts___extras,
)
from tests.tier1_offline.test_utils_database import _run as _core_small_database___run
from tests.tier1_offline.test_utils_database import tree as _core_small_database__tree

_CORE_SMALL_COHERENCE_TOTAL__HEAD = (
    "Solver mode:                                Steady\n"
    "Angle of attack (Deg)                       2.0000\n"
    "Side-slip angle (Deg)                       0.0000\n"
    "Surface, Cx, Cy, Cz, CL, CDi, CDo\n"
)


class TestCoreSmallCoherenceTotal:
    """P0400-TOTALSTRICT (PFS-2135.050): the coherence instrument refuses a short Total row.

    measure_campaign_coherence dropped empty cells and zipped the header to the
    values with strict=False, so a Total row missing a middle cell shifted Cx, Cy,
    Cz, CDi and CDo onto the wrong names in silence. It now reads the row through
    the strict reader of extract_recorded_total_rows, the one the 0.24.0 review fixed.
    """

    @staticmethod
    @pytest.mark.parametrize(
        ("total", "words"),
        [
            ("Total, +0.0200, +0.1000, +0.1000, +0.0050, +0.0200", "Total row prints 5 cells"),
            ("Total, +0.0200, , +0.1000, +0.1000, +0.0050, +0.0200", "could not convert"),
        ],
        ids=["short", "blank"],
    )
    def test_p0400_totalstrict_a_missing_middle_cell_is_refused(
        tmp_path: Path, total: str, words: str
    ) -> None:
        """P0400-TOTALSTRICT: six names over five numbers, or a blank cell, is refused."""
        loads = tmp_path / "loads.txt"
        loads.write_text(_CORE_SMALL_COHERENCE_TOTAL__HEAD + total + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match=words):
            _core_small_coherence_total___instrument()._loads_total(loads)

    @staticmethod
    def test_p0400_totalstrict_a_whole_row_reads_by_name(tmp_path: Path) -> None:
        """P0400-TOTALSTRICT: the control: a whole row reads each number under its own name."""
        loads = tmp_path / "loads.txt"
        loads.write_text(
            _CORE_SMALL_COHERENCE_TOTAL__HEAD
            + "Total, +0.0200, +0.0000, +0.1000, +0.1000, +0.0050, +0.0200\n",
            encoding="utf-8",
        )
        row = _core_small_coherence_total___instrument()._loads_total(loads)
        assert (row["Cz"], row["CDo"], row["decimals"]) == (0.1, 0.02, 4.0)
        loads.write_text(
            _CORE_SMALL_COHERENCE_TOTAL__HEAD
            + "Total, +0.0200, +0.1000, +0.1000, +0.0050, +0.0200\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="Total row prints 5 cells"):
            _core_small_coherence_total___instrument()._loads_total(loads)


def _core_small_database___snapshot(chapters):
    return {path.name: path.read_bytes() for path in chapters.iterdir()}


class TestCoreSmallDatabase:
    """P0400-REGISTERATOMIC (PFS-2102.018): register_edition replaces every chapter or none.

    The final loop wrote chapter files one by one, so an OSError on the second
    of two chapters (a file locked by an editor or a sync client, a full disk)
    left the first rewritten, against the docstring's "nothing has been
    written", and the OSError reached the command line as a traceback.
    """

    tree = staticmethod(_core_small_database__tree)

    @staticmethod
    def test_p0400_registeratomic_the_fixture_writes_two_chapters(tree):  # noqa: F811
        """P0400-REGISTERATOMIC: the control: an unhindered write edits both chapters."""
        result = _core_small_database___run(tree, write=True)
        assert len(result.chapters) == 2

    @staticmethod
    def test_p0400_registeratomic_a_failed_write_replaces_nothing(tree, monkeypatch):  # noqa: F811
        """P0400-REGISTERATOMIC: the second write fails; no chapter changed, a ManualDraftError."""
        chapters = tree[0]
        before = _core_small_database___snapshot(chapters)
        real = _core_small_database__database._textio.write_text
        calls = []

        def failing(path, text, **kwargs):
            calls.append(path)
            if len(calls) == 2:
                raise PermissionError(13, "locked by another program", str(path))
            return real(path, text, **kwargs)

        monkeypatch.setattr(_core_small_database__database._textio, "write_text", failing)
        with pytest.raises(ManualDraftError, match="no chapter was replaced"):
            _core_small_database___run(tree, write=True)
        assert _core_small_database___snapshot(chapters) == before

    @staticmethod
    def test_p0400_registeratomic_a_failed_replace_puts_back_the_first(tree, monkeypatch):  # noqa: F811
        """P0400-REGISTERATOMIC: the second replace fails; the first chapter is put back."""
        chapters = tree[0]
        before = _core_small_database___snapshot(chapters)
        real = os.replace
        calls = []

        def failing(source, target):
            calls.append(target)
            if len(calls) == 2:
                raise PermissionError(13, "locked by another program", str(target))
            return real(source, target)

        monkeypatch.setattr(os, "replace", failing)
        with pytest.raises(ManualDraftError, match="were put back"):
            _core_small_database___run(tree, write=True)
        assert _core_small_database___snapshot(chapters) == before


def _core_small_manual___manifest(tmp_path: Path, row: str) -> Path:
    (tmp_path / "m.pdf").write_bytes(b"%PDF-1.4")
    path = tmp_path / "manifest.yaml"
    path.write_text(f"- manual: {tmp_path / 'm.pdf'}\n  chapter: 1-2\n{row}", encoding="utf-8")
    return path


class TestCoreSmallManual:
    """P0400-MANUALDRAFT: the manual drafter and the edition manifest reader.

    P0400-MANUALDRAFT-LABEL (PFS-2102.019): an unquoted manifest label 26.120 is
    the YAML number 26.12 and was read as the string "26.12"; it is refused with
    the quote hint, as the command loader refuses its unquoted version keys.

    P0400-MANUALDRAFT-SOURCE (PFS-2102.020): a blank ``source:`` is YAML null and
    became the four letters "None", which passed the citation refusal.

    P0400-MANUALDRAFT-PHASE (PFS-2102.021, PFS-2102.022): the section-to-phase map
    proposed ``solve`` and ``post``, which are not Phase members, and ``init`` for
    the file sections.

    P0400-MANUALDRAFT-SPLICE (PFS-2102.023): insert_version_row split with
    str.splitlines, which also breaks on form feed and NEL, and rejoined every
    line with one newline, rewriting a file of mixed line ends.

    P0400-MANUALDRAFT-PREFIX (PFS-2102.025): the parameter-table reader merged a
    FRAME_TYPE row into FRAME, the earlier placeholder its name starts with.

    P0400-MANUALDRAFT-ENUM (PFS-2102.026): drafted enum tokens were written
    unquoted, so YAML 1.1 loaded ON and OFF as booleans.
    """

    @staticmethod
    @pytest.mark.parametrize("label", ["26.120", "26.000", "26"])
    def test_p0400_manualdraft_label_unquoted_number_is_refused(tmp_path: Path, label: str) -> None:
        """P0400-MANUALDRAFT-LABEL: a bare number label is refused with the quote hint."""
        path = _core_small_manual___manifest(tmp_path, f"  label: {label}\n  source: SRC-751\n")
        with pytest.raises(ManualDraftError, match=r'quote it in the YAML \(label: "26.120"\)'):
            read_edition_manifest(path)

    @staticmethod
    def test_p0400_manualdraft_label_quoted_is_read_as_written(tmp_path: Path) -> None:
        """P0400-MANUALDRAFT-LABEL: the quoted label reaches the edition unchanged."""
        path = _core_small_manual___manifest(tmp_path, '  label: "26.120"\n  source: SRC-751\n')
        assert read_edition_manifest(path)[0].label == "26.120"

    @staticmethod
    def test_p0400_manualdraft_source_blank_is_refused(tmp_path: Path) -> None:
        """P0400-MANUALDRAFT-SOURCE: a blank source is refused naming the row, before any reader."""
        path = _core_small_manual___manifest(tmp_path, '  label: "26.120"\n  source:\n')
        with pytest.raises(ManualDraftError, match=r"entry 1: source None parsed as NoneType"):
            read_edition_manifest(path)

    @staticmethod
    def test_p0400_manualdraft_phase_map_holds_phase_members_only() -> None:
        """P0400-MANUALDRAFT-PHASE: every value of the section map is a Phase member."""
        members = {phase.value for phase in Phase}
        assert {section: p for section, p in _PHASE_BY_SECTION.items() if p not in members} == {}
        assert _PHASE_BY_SECTION["Mesh Import   Export"] == "geometry"

    @staticmethod
    @pytest.mark.parametrize("section", ["Unsteady Solver", "Solver Analysis", "Output Status"])
    def test_p0400_manualdraft_phase_mixed_section_drafts_a_question(section: str) -> None:
        """P0400-MANUALDRAFT-PHASE: a section whose entries span phases drafts ``???``."""
        command = ManualCommand(name="X_COMMAND", page=1, section=section)
        entry = render_entry(command, source="SRC-741", versions={"26.100": "documented"})
        assert "phase: ???" in entry

    @staticmethod
    @pytest.mark.parametrize("newline", ["\n", "\r\n"])
    def test_p0400_manualdraft_splice_leaves_every_other_byte(newline: str) -> None:
        """P0400-MANUALDRAFT-SPLICE: mixed line ends and a form feed in a note survive the splice."""  # noqa: E501
        text = (
            f"# chapter{newline}"
            f"X_CMD:{newline}"
            "  layout: inline\n"
            f"  versions:{newline}"
            f'    "26.120": {{status: documented, note: "a\x0cb\x85c"}}{newline}'
            f"Y_CMD:{newline}"
            "  layout: inline"
        )
        edited = insert_version_row(
            text, command="X_CMD", canonical="26.123", status="documented", note="SRC-751 p.1"
        )
        row = f'    "26.123": {{status: documented, note: "SRC-751 p.1"}}{newline}'
        marker = f'note: "a\x0cb\x85c"}}{newline}'
        assert edited == text.replace(marker, marker + row)

    @staticmethod
    def test_p0400_manualdraft_prefix_placeholder_opens_its_own_row() -> None:
        """P0400-MANUALDRAFT-PREFIX: FRAME_TYPE is its own row, not FRAME's continuation."""
        page = (
            "Function name: SET_FOO <FRAME> <FRAME_TYPE>\n"
            "Function parameters:\n"
            "Parameter Value\n"
            "FRAME Index of the coordinate system\n"
            "FRAME_TYPE Can be one of the following: LOCAL, GLOBAL.\n"
            "Sample:\n"
            "SET_FOO 1 LOCAL\n"
        )
        parameters = parse_signatures({300: page})["SET_FOO"].parameters
        assert parameters == {
            "FRAME": "Index of the coordinate system",
            "FRAME_TYPE": "Can be one of the following: LOCAL, GLOBAL.",
        }

    @staticmethod
    def test_p0400_manualdraft_enum_tokens_load_back_as_strings() -> None:
        """P0400-MANUALDRAFT-ENUM: a drafted ON/OFF enum loads back as the strings."""
        page = (
            "Function name: SET_SWITCH <TOGGLE>\n"
            "Function parameters:\n"
            "Parameter Value\n"
            "TOGGLE Turns the feature on or off. Can be ON or OFF\n"
            "Sample:\n"
            "SET_SWITCH ON\n"
        )
        command = parse_signatures({300: page})["SET_SWITCH"]
        entry = render_entry(command, source="SRC-741", versions={"26.100": "documented"})
        loaded = yaml.safe_load(entry)
        assert loaded["SET_SWITCH"]["args"][0]["values"] == ["ON", "OFF"]


class TestCoreSmallManualCli:
    """P0400-MANUALPATH (PFS-2102.017): a missing or bad --manual path is a usage error.

    ``pyfs-manual coverage`` and ``draft`` caught only ManualDraftError around the
    pdf read, so the FileNotFoundError or IsADirectoryError the pdf reader raises
    for a mistyped path escaped as a traceback. The pdf reader is replaced by one
    that opens the path as pypdf does, so the test needs no pdf extra.
    """

    @staticmethod
    @pytest.fixture
    def opening_reader(monkeypatch: pytest.MonkeyPatch) -> None:
        """A stand-in pypdf whose reader opens its path, raising what the real one raises."""

        class PdfReader:
            def __init__(self, path: str) -> None:
                with open(path, "rb"):
                    pass
                self.pages: list[object] = []

        monkeypatch.setitem(sys.modules, "pypdf", types.SimpleNamespace(PdfReader=PdfReader))

    @staticmethod
    @pytest.mark.usefixtures("opening_reader")
    @pytest.mark.parametrize("command", ["coverage", "draft"])
    @pytest.mark.parametrize("kind", ["missing", "directory"])
    def test_p0400_manualpath_bad_manual_is_a_usage_error(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str, kind: str
    ) -> None:
        """P0400-MANUALPATH: exit 2 with the path named, for a missing file and a folder."""
        manual = tmp_path / "absent.pdf" if kind == "missing" else tmp_path
        argv = [command, "--manual", str(manual), "--source", "SRC-741", "--chapter-pages", "1-2"]
        if command == "draft":
            argv += ["--fs-version", "26.120"]
        with pytest.raises(SystemExit) as stopped:
            cli.main(argv)
        assert stopped.value.code == 2
        assert "is not a file" in capsys.readouterr().err


_CORE_SMALL_RESTATE_NOTES__REPO = Path(__file__).resolve().parents[2]


def _core_small_restate_notes___load():
    spec = importlib.util.spec_from_file_location(
        "restate_26123_notes_p0400",
        _CORE_SMALL_RESTATE_NOTES__REPO / "scripts" / "restate_26123_notes.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCoreSmallRestateNotes:
    """P0400-RESTATELABEL (PFS-2135.055): restate_26123_notes refuses the two manifest-label defects.

    A manifest without 26.123 raised a bare ValueError from ``labels.index``, and
    26.123 as the FIRST row made ``editions[position - 1]`` the last row, so the
    newest edition was compared against the oldest. Both are refused before a
    manual is read, as prove_edition_comparison already refuses them.
    """  # noqa: E501

    @staticmethod
    @pytest.mark.parametrize(
        ("labels", "words"),
        [(["26.120", "26.122"], "no row labelled '26.123'"), (["26.123", "26.124"], "first row")],
        ids=["absent", "first"],
    )
    def test_p0400_restatelabel_bad_manifest_is_refused_before_reading(
        monkeypatch, labels, words
    ) -> None:
        """P0400-RESTATELABEL: an absent or first-row 26.123 stops with a SystemExit naming it."""
        module = _core_small_restate_notes___load()
        editions = [SimpleNamespace(label=label) for label in labels]
        monkeypatch.setattr(module, "read_edition_manifest", lambda path: editions)

        def never(edition):
            raise AssertionError("a manual was read before the manifest was judged")

        monkeypatch.setattr(module, "read_edition", never)
        with pytest.raises(SystemExit, match=words):
            module.main(["--editions", "manifest.yaml"])


class TestCoreSmallReviewScripts:
    """P0400 review: directed parity changes and safe chapter replacement."""

    @staticmethod
    @pytest.mark.parametrize(
        "old,new",
        [
            ("VALAREZO_CRITERION DISABLE\n", "VALAREZO_CRITERION ENABLE\n"),
            ("VALAREZO_CRITERION ENABLE\n", "SET_WAKE_RELAXATION DISABLE\n"),
            ("", "VALAREZO_CRITERION DISABLE\n"),
        ],
    )
    def test_p0400_parity_toggle_allowance_preserves_direction_and_command(old, new):
        module = _core_small_review_scripts___load()
        assert "requirement" not in module.name_difference(
            "scripts", "x", old, new, {"FR-349"}, "0.33.1"
        )
        assert (
            module.name_difference(
                "scripts",
                "x",
                "VALAREZO_CRITERION ENABLE\n",
                "VALAREZO_CRITERION DISABLE\n",
                {"FR-349"},
                "0.33.1",
            )["requirement"]
            == "FR-349"
        )

    @staticmethod
    def test_p0400_register_does_not_overwrite_an_existing_temporary(tmp_path: Path):
        chapter = tmp_path / "chapter.yaml"
        chapter.write_bytes(b"original\n")
        parked = tmp_path / "chapter.yaml.register-tmp"
        parked.write_bytes(b"someone else's work\n")
        _core_small_review_scripts__database._write_all_or_none(
            {chapter: "new\n"}, {chapter: "original\n"}
        )
        assert chapter.read_bytes() == b"new\n"
        assert parked.read_bytes() == b"someone else's work\n"

    @staticmethod
    def test_p0400_register_failed_replace_names_the_failed_chapter(tmp_path: Path, monkeypatch):
        first, second = tmp_path / "a.yaml", tmp_path / "b.yaml"
        originals = {first: "old a\n", second: "old b\n"}
        for path, text in originals.items():
            path.write_bytes(text.encode())
        replace = _core_small_review_scripts__database.os.replace

        def fail_second(source, target):
            if target == second:
                raise OSError("locked")
            replace(source, target)

        monkeypatch.setattr(_core_small_review_scripts__database.os, "replace", fail_second)
        with pytest.raises(ManualDraftError, match="could not replace b.yaml"):
            _core_small_review_scripts__database._write_all_or_none(
                dict.fromkeys(originals, "new\n"), originals
            )
        assert {p: p.read_bytes().decode() for p in originals} == originals

    @staticmethod
    def test_p0400_extras_collection_error_is_not_a_kill():
        battery = _core_small_review_scripts___extras().Battery("unused")
        battery._verdict("M1", 2, "1 failed during collection", "KILLED")
        assert battery.failures == ["M1 (INCONCLUSIVE)"]

    @staticmethod
    def test_p0400_extras_append_normalizes_crlf_input_to_lf_target(tmp_path, monkeypatch):
        module = _core_small_review_scripts___extras()
        monkeypatch.setattr(module, "REPO", tmp_path)
        monkeypatch.setattr(module, "BACKUP", tmp_path / ".backup")
        target = tmp_path / "x.py"
        target.write_bytes(b"x = 1\n")
        seen = []

        def run(_target):
            seen.append(target.read_bytes())
            return 1, "1 failed"

        monkeypatch.setattr(module, "run", run)
        module.Battery("unused").append(target, "import pypdf\r\n", "M99")
        assert seen == [b"x = 1\nimport pypdf\n"]

    @staticmethod
    def test_p0400_library_fold_requires_migration_destination(tmp_path):
        repo = _core_small_review_scripts___checkout(
            tmp_path, A="## Migration\n\nRename the key.\n"
        )
        module = _core_small_review_scripts___script()
        with pytest.raises(module.FragmentError, match="--migration-page"):
            module.assemble(repo)
        assert (repo / "changelog.d" / "A.md").is_file()

    @staticmethod
    def test_p0400_srs_idempotency_compares_only_the_requirement_box(tmp_path):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "review_srs", Path(__file__).resolve().parents[2] / "scripts" / "assemble_srs.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        box = '!!! requirement "FR-999 A box"\n\n    Body.'
        text = box + "\n\n## Next section\n\nUnrelated prose.\n"
        assert module.fold_page(text, [(tmp_path / "fragment.md", [("FR-999", box)])]) == (text, 0)
