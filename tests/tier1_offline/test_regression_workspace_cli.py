"""Regression coverage grouped by subject."""

from __future__ import annotations

import hashlib
from zipfile import ZipFile

import pytest

from pyflightstream.run.cli import main as matrix_main
from pyflightstream.workspace.cli import _build_parser
from pyflightstream.workspace.cli import main as workspace_cli
from pyflightstream.workspace.cli import main as workspace_main
from pyflightstream.workspace.ledger import point_card
from tests.tier1_offline.test_p0350_query_history import RUN as _WORKSPACE_1_QUERY__RUN
from tests.tier1_offline.test_p0350_query_history import _record as _workspace_1_query___record
from tests.tier1_offline.test_p0350_query_history import _write as _workspace_1_query___write


class TestWorkspace1Cli:
    """P0400-WSCLI: `pyfs-workspace` refusals (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """

    pytestmark = pytest.mark.requirement("P0400-WSCLI")

    @staticmethod
    def test_p0400_wscli_init_on_a_bad_root_is_a_refusal_with_exit_2(tmp_path, capsys):
        """P0400-WSCLI (PFS-2095.059): init refuses a root that is a file, like its siblings."""
        taken = tmp_path / "taken"
        taken.write_text("not a folder", encoding="utf-8")
        assert workspace_cli(["init", str(taken)]) == 2
        assert "taken" in capsys.readouterr().err

    @staticmethod
    @pytest.mark.parametrize("command", ["init", "migrate-geometries"])
    def test_p0400_wscli_every_command_accepts_the_workspace_option(tmp_path, command):
        """P0400-WSCLI (PFS-2089.004): init and migrate-geometries accept --workspace."""
        args = _build_parser().parse_args([command, "--workspace", str(tmp_path)])
        assert args.workspace == str(tmp_path)

    @staticmethod
    def test_p0400_wscli_two_different_campaigns_are_refused(tmp_path, capsys):
        """P0400-WSCLI (PFS-2089.004): --workspace and a different positional root, exit 2."""
        first, second = tmp_path / "a", tmp_path / "b"
        assert workspace_cli(["init", str(first), "--workspace", str(second)]) == 2
        assert "named twice" in capsys.readouterr().err
        assert not first.exists() and not second.exists()

    @staticmethod
    def test_p0400_wscli_init_uses_the_named_workspace(tmp_path):
        """P0400-WSCLI (PFS-2089.004): --workspace routes init into the selected campaign."""
        target = tmp_path / "campaign"
        assert workspace_cli(["init", "--workspace", str(target)]) == 0
        assert (target / "inputs").is_dir()


_WORKSPACE_1_QUERY__POINT = "sims/sim_2006/datapoints/DP-A0"


def _workspace_1_query___card_workspace(tmp_path, *outputs: str):
    _workspace_1_query___write(
        tmp_path / "runs.json",
        [_workspace_1_query___record(outputs=list(outputs), point_name="A0")],
    )
    return tmp_path


def _workspace_1_query___evidence(card, name):
    (item,) = [row for row in card["evidence"] if row["path"].endswith(name)]
    return item


class TestWorkspace1Query:
    """P0400-WSQUERY: the point card's evidence and archives (0.40.0 lane workspace-1).

    Each test is the regression of one planning node and fails on the code before its fix.
    """

    pytestmark = pytest.mark.requirement("P0400-WSQUERY")

    @staticmethod
    def test_p0400_wsquery_a_binary_output_is_named_by_size_and_digest(tmp_path):
        """P0400-WSQUERY (PFS-2101.004): a binary export prints no decoded garbage."""
        payload = bytes(range(256)) * 300
        target = tmp_path / _WORKSPACE_1_QUERY__POINT / "surface.dat"
        target.parent.mkdir(parents=True)
        target.write_bytes(payload)
        card = point_card(
            _workspace_1_query___card_workspace(tmp_path, "datapoints/DP-A0/surface.dat"),
            _WORKSPACE_1_QUERY__RUN,
        )
        item = _workspace_1_query___evidence(card, "surface.dat")
        assert item["last_lines"] == [] and item["binary"] is True
        assert item["bytes"] == len(payload)
        assert item["sha256"] == hashlib.sha256(payload).hexdigest()

    @staticmethod
    def test_p0400_wsquery_binary_bytes_without_a_nul_are_not_decoded(tmp_path):
        """P0400-WSQUERY (PFS-2101.004): invalid UTF-8 is summarized without decoded garbage."""
        payload = bytes([255]) * 72000
        target = tmp_path / _WORKSPACE_1_QUERY__POINT / "surface.dat"
        target.parent.mkdir(parents=True)
        target.write_bytes(payload)
        card = point_card(
            _workspace_1_query___card_workspace(tmp_path, "datapoints/DP-A0/surface.dat"),
            _WORKSPACE_1_QUERY__RUN,
        )
        item = _workspace_1_query___evidence(card, "surface.dat")
        assert item["last_lines"] == []
        assert item["sha256"] == hashlib.sha256(payload).hexdigest()

    @staticmethod
    def test_p0400_wsquery_a_long_text_file_shows_its_last_lines(tmp_path):
        """P0400-WSQUERY (PFS-2101.004): the last five lines come from the tail alone."""
        target = tmp_path / _WORKSPACE_1_QUERY__POINT / "P2006-A0_log.txt"
        target.parent.mkdir(parents=True)
        target.write_text("".join(f"iteration {n}\n" for n in range(20000)), encoding="utf-8")
        card = point_card(_workspace_1_query___card_workspace(tmp_path), _WORKSPACE_1_QUERY__RUN)
        item = _workspace_1_query___evidence(card, "P2006-A0_log.txt")
        assert item["last_lines"] == [f"iteration {n}" for n in range(19995, 20000)]
        assert "binary" not in item

    @staticmethod
    def test_p0400_wsquery_text_evidence_does_not_read_the_whole_file(tmp_path, monkeypatch):
        """P0400-WSQUERY (PFS-2101.004): show never calls the whole-file text reader."""
        target = tmp_path / _WORKSPACE_1_QUERY__POINT / "iterations.log"
        target.parent.mkdir(parents=True)
        target.write_text("step\n" * 20000, encoding="utf-8")
        real = type(target).read_text

        def guarded(path, *args, **kwargs):
            assert path != target, "evidence was read whole"
            return real(path, *args, **kwargs)

        monkeypatch.setattr(type(target), "read_text", guarded)
        card = point_card(_workspace_1_query___card_workspace(tmp_path), _WORKSPACE_1_QUERY__RUN)
        assert _workspace_1_query___evidence(card, target.name)["last_lines"] == ["step"] * 5

    @staticmethod
    def test_p0400_wsquery_a_binary_zip_member_has_a_streamed_digest(tmp_path):
        """P0400-WSQUERY (PFS-2101.004): compacted evidence has the same binary summary."""
        payload = bytes(range(256)) * 300
        (tmp_path / "sims").mkdir()
        with ZipFile(tmp_path / "sims/sim_2006.zip", "w") as archive:
            archive.writestr("datapoints/DP-A0/surface.dat", payload)
        card = point_card(
            _workspace_1_query___card_workspace(tmp_path, "datapoints/DP-A0/surface.dat"),
            _WORKSPACE_1_QUERY__RUN,
        )
        item = _workspace_1_query___evidence(card, "surface.dat")
        assert item["last_lines"] == []
        assert item["bytes"] == len(payload)
        assert item["sha256"] == hashlib.sha256(payload).hexdigest()

    @staticmethod
    def test_p0400_wsquery_a_point_card_lists_only_its_own_archives(tmp_path):
        """P0400-WSQUERY (PFS-2094.020): the archives of A01 and A0_b are not A0's."""
        for folder in ("DP-A0", "DP-A01", "DP-A0_b+05"):
            archived = tmp_path / "sims/sim_2006/datapoints" / folder / "archive/20261001/x.txt"
            archived.parent.mkdir(parents=True)
            archived.write_text("x\n", encoding="utf-8")
        card = point_card(_workspace_1_query___card_workspace(tmp_path), _WORKSPACE_1_QUERY__RUN)
        archives = card["chain"]["archives"]
        assert archives and all("/DP-A0/archive/" in path for path in archives), archives


def _workspace_2_cli___exit(call) -> int:
    try:
        return call()
    except SystemExit as stopped:
        return int(stopped.code or 0)


class TestWorkspace2Cli:
    """P0400-WSCLI: the workspace command line says what it does, and reads settings where it parses."""  # noqa: E501

    @staticmethod
    def test_p0400_wscli_archive_help_does_not_promise_a_status_check(capsys):
        """P0400-WSCLI (PFS-2081.21): archive reads no run status, so its help names a recorded
        simulation, not a completed one, and says the status is not read."""
        assert _workspace_2_cli___exit(lambda: workspace_main(["archive", "--help"])) == 0
        help_text = " ".join(capsys.readouterr().out.split())
        assert "completed simulation" not in help_text, help_text
        assert "does not read the status" in help_text, help_text

    @staticmethod
    def test_p0400_wscli_an_abbreviated_workspace_is_refused_not_read_elsewhere(tmp_path, capsys):
        """P0400-WSCLI (PFS-2094.021): settings are read from the folder an exact --workspace
        names, so `--works PATH` is refused by the parse instead of parsing to PATH while the
        settings came from the current folder."""
        assert _workspace_2_cli___exit(lambda: matrix_main(["post", "--works", str(tmp_path)])) == 2
        assert "unrecognized arguments: --works" in capsys.readouterr().err

    @staticmethod
    @pytest.mark.parametrize("flag", ["--workspace", "--workspace="])
    def test_p0400_wscli_the_exact_workspace_option_still_parses(tmp_path, capsys, flag):
        """P0400-WSCLI (PFS-2094.021): the exact spelling, either form, is not refused."""
        argv = (
            ["post", flag + str(tmp_path)] if flag.endswith("=") else ["post", flag, str(tmp_path)]
        )
        _workspace_2_cli___exit(lambda: matrix_main(argv))
        assert "unrecognized arguments" not in capsys.readouterr().err
