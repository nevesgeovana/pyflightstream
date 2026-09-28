"""Usage: ``pyfs-matrix --help`` leaves help on stdout and one signature on stderr."""

import importlib

import pytest


@pytest.mark.parametrize("name", ["run", "workspace", "qa", "utils", "fsi"])
def test_help_has_one_signature_and_keeps_help_stdout(name, capsys):
    """GOAL033:logging:checks:literal_signature_geoversegoddes."""
    main = importlib.import_module(f"pyflightstream.{name}.cli").main
    with pytest.raises(SystemExit) as exited:
        main(["--help"])
    assert exited.value.code == 0
    streams = capsys.readouterr()
    assert "usage:" in streams.out
    assert "Ass: geoversegoddes" not in streams.out
    assert streams.err.count("Ass: geoversegoddes") == 1
    assert "help" in streams.err.lower()


def test_invalid_arguments_are_not_congratulated(capsys):
    """GOAL033:logging:checks:truthful_success_failure."""
    from pyflightstream.run.cli import main

    with pytest.raises(SystemExit) as exited:
        main(["--not-a-command"])
    assert exited.value.code == 2
    streams = capsys.readouterr()
    assert streams.err.count("Ass: geoversegoddes") == 1
    assert "failed" in streams.err.lower()
    assert "great work" not in streams.err.lower()


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
    assert streams.err.count("Ass: geoversegoddes") == 1
    assert "failed" in streams.err.lower()


def test_cancellation_preserves_interrupt(monkeypatch, capsys):
    from pyflightstream.run import cli

    def interrupted(_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_cmd_post", interrupted)
    with pytest.raises(KeyboardInterrupt):
        cli.main(["post"])
    streams = capsys.readouterr()
    assert streams.err.count("Ass: geoversegoddes") == 1
    assert "cancel" in streams.err.lower()


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
        assert "Ass: geoversegoddes" not in streams.out
        assert streams.err.count("Ass: geoversegoddes") == 1
        assert "help" in streams.err.lower()


def test_success_phrases_vary_without_changing_json_or_status(monkeypatch, capsys):
    """GOAL033:logging:checks:variable_fun_phrases."""
    from pyflightstream import _cli
    from pyflightstream.run import cli

    choices = []

    def alternate(options):
        choices.append(tuple(options))
        return options[0] if len(choices) == 1 else options[-1]

    def succeeded(_args):
        print('{"status":"complete"}')
        return 0

    monkeypatch.setattr(_cli.random, "choice", alternate)
    monkeypatch.setattr(cli, "_cmd_post", succeeded)
    phrases = []
    for _ in range(2):
        assert cli.main(["post"]) == 0
        streams = capsys.readouterr()
        assert streams.out == '{"status":"complete"}\n'
        assert streams.err.startswith("Great work!")
        assert streams.err.count("Ass: geoversegoddes") == 1
        phrases.append(streams.err)
    assert phrases[0] != phrases[1]
    assert all(len(set(options)) >= 2 for options in choices)
