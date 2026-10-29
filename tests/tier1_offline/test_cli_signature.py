"""Usage: ``pyfs-matrix --help`` leaves help on stdout and one signature on stderr.

The signature of 0.30.0 is the owner's box: a drawing with one phrase of its
pool on its second row and "geoversegoddess sees you" on its second-to-last,
on stderr, once per invocation. A successful post is always the koala; help
and version keep one short line, so their output stays compact.
"""

import importlib
import io
import random
import sys
import types

import pytest

from pyflightstream import _cli, _signature

SEES_YOU = "geoversegoddess sees you"
BORDER = "#" * 81


@pytest.mark.requirement("FR-3395")
def test_p0500_warning_off_preserves_post_and_refine_records(tmp_path, capsys, monkeypatch):
    """P0500-WARNOFF: real post and refinement warnings retain their durable records."""
    import json
    import warnings

    from pyflightstream.run.cli import main as matrix_main
    from tests.tier1_offline.test_b01_frozen_solve import _post_workspace
    from tests.tier1_offline.test_p0380_s1_refine import BOTH_TABLES, _two_tubes

    def show(message, category, filename, lineno, file=None, line=None):
        print(
            warnings.formatwarning(message, category, filename, lineno, line),
            end="",
            file=file or sys.stderr,
        )

    monkeypatch.setattr(warnings, "showwarning", show)
    recorded = []
    for disabled in (False, True):
        folder = tmp_path / str(disabled)
        folder.mkdir()
        workspace = _post_workspace(folder / "post", 2413, (60, 61))
        flags = ["--warning-off"] if disabled else []
        assert (
            matrix_main([*flags, "post", "--workspace", str(workspace.root), "--pproc-warnings"])
            == 0
        )
        output = capsys.readouterr()
        assert "[warning]" not in output.err
        post = workspace.products_dir(None)
        text = (post / "post.log").read_text(encoding="utf-8")
        record = json.loads((post / "post.log.json").read_text(encoding="utf-8"))
        assert "WARNING" in text and "frozen" in text
        assert "frozen" in json.dumps(record)
        mesh_dir = folder / "mesh"
        mesh_dir.mkdir()
        mesh = _two_tubes(mesh_dir, BOTH_TABLES)
        assert (
            matrix_main([*flags, "refine", str(mesh), "1", "--out-dir", str(folder / "refined")])
            == 0
        )
        output = capsys.readouterr()
        assert ("[warning]" in output.err) is (not disabled)
        reports = list((folder / "refined").rglob("*.refine.json"))
        assert len(reports) == 1
        refined = json.loads(reports[0].read_text(encoding="utf-8"))
        assert refined["ignored_families_tables"] == ["A", "B"]
        recorded.append(refined["ignored_families_tables"])
    assert recorded[0] == recorded[1]


@pytest.mark.parametrize("name", ["run", "workspace", "qa", "utils", "fsi"])
@pytest.mark.requirement("FR-3395")
def test_p0500_warning_off_keeps_command_output_and_warning_log(
    name, tmp_path, capsys, monkeypatch
):
    """P0500-WARNOFF: each program parses the flag and preserves recorded warnings."""
    import warnings

    from pyflightstream._errors import PyflightstreamWarning
    from pyflightstream._progress import command_console

    def show(message, category, filename, lineno, file=None, line=None):
        print(
            warnings.formatwarning(message, category, filename, lineno, line),
            end="",
            file=file or sys.stderr,
        )

    monkeypatch.setattr(warnings, "showwarning", show)
    module = importlib.import_module(f"pyflightstream.{name}.cli")
    builder = "_parser" if name == "utils" else "_build_parser"
    parser = getattr(module, builder)()
    assert "--warning-off" in parser.format_help()
    root = tmp_path / name
    (root / "inputs").mkdir(parents=True)
    calls = {
        "run": (["post", "--workspace", str(root)], "_cmd_post"),
        "workspace": (["init", str(root)], "_cmd_init"),
        "qa": (["cost", str(root)], "_cmd_cost"),
        "utils": (["surface", "--editions", "editions.yaml"], "_surface"),
        "fsi": (["step", "--out", str(root)], "_step"),
    }

    def operation(*args, **kwargs):
        with command_console(
            "test", "post", what="exercise warnings", workspace=root, live_log=True
        ):
            print("progress retained", file=sys.stderr)
            warnings.warn("recorded warning", PyflightstreamWarning, stacklevel=2)
            print("summary retained")
            print("error retained", file=sys.stderr)
        return 0

    argv, handler = calls[name]
    monkeypatch.setattr(module, handler, operation)
    if name == "utils":
        monkeypatch.setattr(module, "_manual_extra_error", lambda: None)
    for flags in ([], ["--warning-off"]):
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            assert module.main([*flags, *argv]) == 0
        output = capsys.readouterr()
        assert "summary retained" in output.out
        assert "progress retained" in output.err
        assert "error retained" in output.err
        assert output.err.count(SEES_YOU) == 1
        assert ("[warning]" in output.err) is (not flags)
        assert ("Warnings (" in output.err) is (not flags)
    # Matrix already owns a live console; the other dispatchers use the probe's console.
    logs = list((root / "logs").glob("post-*.log"))
    if name != "workspace":
        assert len(logs) == 2
        assert all("recorded warning" in log.read_text(encoding="utf-8") for log in logs)


@pytest.mark.parametrize("name", ["run", "workspace"])
@pytest.mark.requirement("FR-3395")
def test_p0500_warning_defaults_and_strict_refusals(name, tmp_path, capsys, monkeypatch):
    """P0500-WARNOFF: files set visibility, CLI wins, and a refusal still raises."""
    import warnings

    from pyflightstream._errors import InputArtifactError, UnknownKeyWarning, demote
    from pyflightstream.options import describe_option, get_option, option_context

    module = importlib.import_module(f"pyflightstream.{name}.cli")
    args = ["post", "--workspace", str(tmp_path)] if name == "run" else ["init", str(tmp_path)]
    handler = "_cmd_post" if name == "run" else "_cmd_init"
    seen = []

    def operation(*args):
        from pyflightstream._console import console_warnings

        seen.append(console_warnings())
        demote(InputArtifactError("unknown optional entry; remove it"), warning=UnknownKeyWarning)
        return 0

    monkeypatch.setattr(module, handler, operation)
    assert "console_warnings" in describe_option()
    assert get_option("console_warnings") is True
    with option_context("console_warnings", False), warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        assert module.main(args) == 0
        assert seen[-1] is False
    assert get_option("console_warnings") is True
    for value, flags, expected in (
        (False, [], False),
        (True, [], True),
        (True, ["--warning-off"], False),
    ):
        (tmp_path / "pyfs.toml").write_text(
            f"[log]\nwarnings = {str(value).lower()}\n", encoding="utf-8"
        )
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            assert module.main([*flags, *args]) == 0
        assert seen[-1] is expected
    # Matrix catches its ordinary input errors; workspace propagates from this probe.
    strict = ["--warning-off", "--warning-refusals", *args]
    if name == "run":
        assert module.main(strict) != 0
        assert "unknown optional entry" in capsys.readouterr().err
    else:
        with pytest.raises(InputArtifactError, match="unknown optional entry"):
            module.main(strict)
    assert get_option("warning_refusals") is False
    assert get_option("console_warnings") is True


@pytest.mark.requirement("FR-3395")
def test_rel1_003_every_log_key_is_in_the_settings_table():
    """REL1-003: the workspace settings page lists every key ``[log]`` accepts."""
    from pathlib import Path

    from pyflightstream.workspace._settings_file import LOG_KEYS

    page = Path(__file__).resolve().parents[2] / "docs" / "workspace-settings.md"
    lines = page.read_text(encoding="utf-8").splitlines()
    row = next(line for line in lines if line.startswith("| `[log]`"))
    assert [key for key in LOG_KEYS if f"`{key}`" not in row] == []


#: The koala with its one phrase, exactly as the owner drew it.
KOALA = """\
#################################################################################
#                                                                               #
#                                          .-"-.               .-"-.            #
# Let now COALA do its magic              / .-. \\   _.---._   / .-. \\           #
#                                        | (   ) |.'       '.| (   ) |          #
#                                         \\ '-' /  o       o  \\ '-' /           #
#                                          '-._|      ___      |_.-'            #
#                                               \\    (___)    /                 #
# geoversegoddess sees you                       '.    V    .'                  #
#                                                  '-.___.-'                    #
#                                                                               #
#################################################################################"""


def _drawn(err):
    """Return the (drawing, phrase) whose box ``err`` carries, or None."""
    for name, phrases in _signature.PHRASES.items():
        for phrase in phrases:
            if _signature.box(name, phrase) in err:
                return name, phrase
    return None


def _outcome_of(err):
    drawn = _drawn(err)
    assert drawn is not None, err
    return next(k for k, v in _signature.OUTCOME_DRAWINGS.items() if drawn[0] in v)


@pytest.mark.parametrize("name", ["run", "workspace", "qa", "utils", "fsi"])
def test_help_has_one_signature_and_keeps_help_stdout(name, capsys):
    """Help of every CLI module keeps usage on stdout and one short signature on stderr."""
    main = importlib.import_module(f"pyflightstream.{name}.cli").main
    with pytest.raises(SystemExit) as exited:
        main(["--help"])
    assert exited.value.code == 0
    streams = capsys.readouterr()
    assert "usage:" in streams.out
    assert SEES_YOU not in streams.out
    assert streams.err.count(SEES_YOU) == 1
    assert BORDER not in streams.err, "help stays compact: no box"
    assert len(streams.err.strip().splitlines()) == 1
    assert "help" in streams.err.lower()


@pytest.mark.requirement("FR-178")
def test_every_outcome_signs_once_on_stderr_with_the_fixed_phrase(capsys):
    """GOAL033:logging:checks:literal_signature_geoversegoddes.

    Every outcome path, success, failure, help, version and cancellation,
    prints "geoversegoddess sees you" exactly once on stderr and nothing on
    stdout; the three outcomes are boxes from their own pools, help and version
    one line each.
    """

    def returns(code):
        return lambda argv: code

    def exits(code):
        def command(argv):
            raise SystemExit(code)

        return command

    def interrupted(argv):
        raise KeyboardInterrupt

    paths = {
        "success": (returns(0), [], None),
        "failed": (returns(1), [], None),
        "help": (exits(0), ["--help"], SystemExit),
        "version": (exits(0), ["--version"], SystemExit),
        "cancelled": (interrupted, [], KeyboardInterrupt),
    }
    for outcome, (body, argv, raised) in paths.items():
        command = _cli.cli_entrypoint(body)
        if raised is None:
            command(argv)
        else:
            with pytest.raises(raised):
                command(argv)
        streams = capsys.readouterr()
        assert streams.out == "", outcome
        assert streams.err.count(SEES_YOU) == 1, outcome
        if outcome in ("help", "version"):
            assert streams.err.endswith(f" {SEES_YOU}\n"), outcome
            assert len(streams.err.splitlines()) == 1, outcome
        else:
            # A blank line before and after the box.
            assert streams.err.startswith("\n" + BORDER + "\n"), outcome
            assert streams.err.endswith("\n" + BORDER + "\n\n"), outcome
            assert _outcome_of(streams.err) == outcome


def test_every_box_is_81_columns_of_ascii_and_every_phrase_fits():
    """Every drawing with every phrase of its pool renders 81 ASCII columns."""
    assert set(_signature.DRAWINGS) == set(_signature.PHRASES)
    assert {n for names in _signature.OUTCOME_DRAWINGS.values() for n in names} == set(
        _signature.DRAWINGS
    )
    for name, phrases in _signature.PHRASES.items():
        for phrase in phrases:
            lines = _signature.box(name, phrase).split("\n")
            assert all(len(line) == 81 for line in lines), (name, phrase)
            assert all(line.isascii() for line in lines), (name, phrase)
            assert lines[0] == lines[-1] == BORDER
            assert all(line[0] == line[-1] == "#" for line in lines)
            art = lines[2:-2]
            assert art[1].startswith(f"# {phrase} "), (name, phrase)
            assert art[-2].startswith(f"# {SEES_YOU} "), name


def test_the_koala_is_drawn_exactly_as_approved():
    assert _signature.box("coala", "Let now COALA do its magic") == KOALA


def test_a_phrase_wider_than_the_text_column_is_refused_not_truncated():
    with pytest.raises(ValueError, match="does not widen"):
        _signature.box("coala", "x" * (_signature.TEXT_COLUMN + 1))


def test_post_success_is_signed_with_the_koala(monkeypatch, capsys):
    """`post` succeeding is always the koala with its one phrase."""
    from pyflightstream.run import cli

    monkeypatch.setattr(cli, "_cmd_post", lambda _args: 0)
    for _ in range(5):
        assert cli.main(["post"]) == 0
        streams = capsys.readouterr()
        assert streams.out == ""
        assert KOALA in streams.err
    monkeypatch.setattr(cli, "_cmd_post", lambda _args: 1)
    assert cli.main(["post"]) == 1
    err = capsys.readouterr().err
    assert KOALA not in err
    assert _outcome_of(err) == "failed"


def test_the_post_a_collect_runs_is_signed_with_the_koala(monkeypatch, tmp_path, capsys):
    """A `collect` that posted is the koala; one that did not post is an ordinary success."""
    from pyflightstream import workspace as workspace_module
    from pyflightstream.run import cli
    from pyflightstream.run import collect as collect_module

    report = types.SimpleNamespace(
        lines=lambda: [],
        failed_lines=lambda: [],
        collected=[],
        failed=[],
        outstanding=0,
        unknown=[],
    )

    def collected(workspace, *, post_matrix, **_):
        if post_matrix is not None:
            post_matrix(workspace, None)
        return report

    monkeypatch.setattr(collect_module, "collect_and_post", collected)
    monkeypatch.setattr(workspace_module, "post_stages", lambda: [])
    assert cli.main(["collect", "--workspace", str(tmp_path)]) == 0
    assert KOALA in capsys.readouterr().err
    assert cli.main(["collect", "--workspace", str(tmp_path), "--no-post"]) == 0
    err = capsys.readouterr().err
    assert KOALA not in err
    assert _outcome_of(err) == "success"


def test_every_drawing_and_every_phrase_is_reachable(monkeypatch, capsys):
    """Seeded: each outcome's draws reach every drawing of its pool and every phrase."""
    monkeypatch.setattr(_cli, "_RNG", random.Random(20260928))
    reached = set()
    bodies = {
        "success": lambda argv: 0,
        "failed": lambda argv: 1,
        "cancelled": lambda argv: (_ for _ in ()).throw(KeyboardInterrupt),
    }
    for body in bodies.values():
        command = _cli.cli_entrypoint(body)
        for _ in range(400):
            try:
                command([])
            except KeyboardInterrupt:
                pass
            drawn = _drawn(capsys.readouterr().err)
            assert drawn is not None
            reached.add(drawn)
    expected = {
        (name, phrase)
        for outcome in ("success", "failed", "cancelled")
        for name in _signature.OUTCOME_DRAWINGS[outcome]
        for phrase in _signature.PHRASES[name]
    }
    assert reached == expected, sorted(expected - reached)


def test_invalid_arguments_are_not_congratulated(capsys):
    """GOAL033:logging:checks:truthful_success_failure."""
    from pyflightstream.run.cli import main

    with pytest.raises(SystemExit) as exited:
        main(["--not-a-command"])
    assert exited.value.code == 2
    streams = capsys.readouterr()
    assert streams.err.count(SEES_YOU) == 1
    assert _outcome_of(streams.err) == "failed"


def test_returned_failure_preserves_code_and_stdout(monkeypatch, capsys):
    """GOAL033:logging:checks:structured_stdout_clean."""
    from pyflightstream.run import cli

    def failed(_args):
        print('{"status":"failed"}')
        return 3

    monkeypatch.setattr(cli, "_cmd_post", failed)
    assert cli.main(["post"]) == 3
    streams = capsys.readouterr()
    assert streams.out == '{"status":"failed"}\n'
    assert streams.err.count(SEES_YOU) == 1
    assert _outcome_of(streams.err) == "failed"


def test_cancellation_preserves_interrupt(monkeypatch, capsys):
    from pyflightstream.run import cli

    def interrupted(_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_cmd_post", interrupted)
    with pytest.raises(KeyboardInterrupt):
        cli.main(["post"])
    streams = capsys.readouterr()
    assert streams.err.count(SEES_YOU) == 1
    assert _outcome_of(streams.err) == "cancelled"


def test_a_closed_or_unencodable_stderr_never_changes_the_result(monkeypatch):
    """The signature observes the outcome; a stream that refuses it changes nothing."""
    closed = io.StringIO()
    closed.close()
    ascii_only = io.TextIOWrapper(io.BytesIO(), encoding="ascii", errors="strict")
    for stream in (closed, ascii_only):
        monkeypatch.setattr(sys, "stderr", stream)
        assert _cli.cli_entrypoint(lambda argv: 4)([]) == 4
        assert _cli.cli_entrypoint(lambda argv: 0)([]) == 0
    monkeypatch.setattr(_signature, "SEES_YOU", "geoversegoddess sees you é")
    monkeypatch.setattr(sys, "stderr", ascii_only)
    with pytest.raises(SystemExit) as exited:
        _cli.cli_entrypoint(lambda argv: (_ for _ in ()).throw(SystemExit(0)))(["--help"])
    assert exited.value.code == 0


def test_every_declared_console_entrypoint_reports_the_owner_signature(capsys):
    """GOAL033:logging:checks:owner_brand_every_cli."""
    import tomllib
    from pathlib import Path

    project = Path(__file__).resolve().parents[2] / "pyproject.toml"
    entries = tomllib.loads(project.read_text(encoding="utf-8"))["project"]["scripts"]
    assert len(entries) >= 5
    for entry in entries.values():
        module, function = entry.split(":", 1)
        main = getattr(importlib.import_module(module), function)
        with pytest.raises(SystemExit) as exited:
            main(["--help"])
        assert exited.value.code == 0
        streams = capsys.readouterr()
        assert "usage:" in streams.out
        assert SEES_YOU not in streams.out
        assert streams.err.count(SEES_YOU) == 1
        assert "help" in streams.err.lower()


def test_success_phrases_vary_without_changing_json_or_status(monkeypatch, capsys):
    """GOAL033:logging:checks:variable_fun_phrases."""
    from pyflightstream.run import cli

    def succeeded(_args):
        print('{"status":"complete"}')
        return 0

    monkeypatch.setattr(_cli, "_RNG", random.Random(7))
    monkeypatch.setattr(cli, "_cmd_records", succeeded)
    seen = set()
    for _ in range(20):
        assert cli.main(["status"]) == 0
        streams = capsys.readouterr()
        assert streams.out == '{"status":"complete"}\n'
        assert streams.err.count(SEES_YOU) == 1
        assert _outcome_of(streams.err) == "success"
        seen.add(_drawn(streams.err))
    assert len(seen) >= 2


def test_the_signature_module_imports_nothing_from_the_package():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(_signature.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and not (node.module or "").startswith("pyflightstream")
        if isinstance(node, ast.Import):
            assert not any(a.name.startswith("pyflightstream") for a in node.names)


def test_nfr_48_an_uncaught_package_failure_is_a_diagnostic_and_a_nonzero_exit(monkeypatch, capsys):
    """NFR-48: the cause and the remedy are said, the exit is nonzero, and no traceback prints."""
    from pyflightstream.run import cli
    from pyflightstream.workspace import WorkspaceError

    def broken(_args):
        raise WorkspaceError("runs.json is not a list of records")

    monkeypatch.setattr(cli, "_cmd_post", broken)
    assert cli.main(["post"]) == 1
    streams = capsys.readouterr()
    assert "pyfs-matrix post failed: WorkspaceError: runs.json is not a list of records" in (
        streams.err
    )
    assert "Fix the cause named above and run the command again" in streams.err
    assert "Traceback (most recent call last)" not in streams.err
    assert _outcome_of(streams.err) == "failed"

    def locked(_args):
        raise PermissionError("runs.json is locked by another program")

    monkeypatch.setattr(cli, "_cmd_post", locked)
    assert cli.main(["post"]) == 1
    assert "PermissionError: runs.json is locked" in capsys.readouterr().err
