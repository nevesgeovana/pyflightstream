"""The signature ends every command, always (FR-315).

The owner's decision of 2026-09-30: "quero que sempre apareça a mensagem,
sempre". No flag, non-terminal stream or error path hides it, and a standard
error that cannot encode the drawing still carries the words.
"""

import importlib
import io
import tomllib
import types
from pathlib import Path

import pytest

from pyflightstream import _cli, _signature

SEES_YOU = _signature.SEES_YOU
ROOT = Path(__file__).resolve().parents[2]

#: Modules the documentation tells a person to run with ``python -m``.
DOCUMENTED_MODULES = ("pyflightstream.workspace.excel", "pyflightstream.workspace.excel_bridge")


#: A phrase ascii cannot encode: a c-cedilla, an a-tilde and "o".
ACCENTED = "a\u00e7\u00e3o"


def _phrases_with(monkeypatch, phrase):
    """Make every pool of the signature offer only ``phrase``."""
    for name in list(_signature.PHRASES):
        monkeypatch.setitem(_signature.PHRASES, name, (phrase,))


def _is_wrapped(function):
    return function.__code__ is _cli.cli_entrypoint(lambda: 0).__code__


def _scripts():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["scripts"]


def test_every_console_script_is_wrapped_fr_315():
    """FR-315: each console script and documented ``python -m`` module is wrapped."""
    scripts = _scripts()
    assert len(scripts) >= 5, "non-vacuity: pyproject must list its console scripts"
    targets = list(scripts.values()) + [f"{name}:main" for name in DOCUMENTED_MODULES]
    for target in targets:
        module_name, _, attribute = target.partition(":")
        function = getattr(importlib.import_module(module_name), attribute)
        assert _is_wrapped(function), f"{target} is not wrapped by cli_entrypoint"


def _ascii_stderr():
    raw = io.BytesIO()
    return io.TextIOWrapper(raw, encoding="ascii", write_through=True), raw


def _outcomes():
    def exits(code):
        def command(argv):
            raise SystemExit(code)

        return command

    def crashes(argv):
        raise RuntimeError("boom")

    def interrupted(argv):
        raise KeyboardInterrupt

    def posts(argv):
        _cli.note_post_ran()
        return 0

    return {
        "success": (lambda argv: 0, [], None),
        "failed return": (lambda argv: 1, [], None),
        "nonzero exit": (exits(2), [], SystemExit),
        "uncaught exception": (crashes, [], RuntimeError),
        "interrupt": (interrupted, [], KeyboardInterrupt),
        "help": (exits(0), ["--help"], SystemExit),
        "version": (exits(0), ["--version"], SystemExit),
        "post": (posts, [], None),
    }


@pytest.mark.parametrize("label", list(_outcomes()))
def test_every_outcome_signs_on_a_non_terminal_stderr_fr_315(label, monkeypatch):
    """FR-315: every outcome ends with SEES_YOU on a non-terminal stderr."""
    body, argv, raised = _outcomes()[label]
    err = io.StringIO()
    monkeypatch.setattr("sys.stderr", err)
    command = _cli.cli_entrypoint(body)
    if raised is None:
        command(argv)
    else:
        with pytest.raises(raised):
            command(argv)
    assert SEES_YOU in err.getvalue(), label


@pytest.mark.parametrize("label", ["success", "uncaught exception", "post"])
def test_an_ascii_stderr_still_carries_the_signature_fr_315(label, monkeypatch):
    """FR-315: a stderr that cannot encode the text still shows the words."""
    body, argv, raised = _outcomes()[label]
    err, raw = _ascii_stderr()
    monkeypatch.setattr("sys.stderr", err)
    _phrases_with(monkeypatch, ACCENTED)
    command = _cli.cli_entrypoint(body)
    if raised is None:
        command(argv)
    else:
        with pytest.raises(raised):
            command(argv)
    err.flush()
    written = raw.getvalue().decode("ascii")
    assert SEES_YOU in written, label
    assert "?" in written, "the characters ascii lacks become replacement marks"


def test_the_real_drawing_reaches_an_ascii_stderr_fr_315(monkeypatch):
    """FR-315: the unchanged box reaches an ascii stderr whole."""
    err, raw = _ascii_stderr()
    monkeypatch.setattr("sys.stderr", err)
    _cli.cli_entrypoint(lambda argv: 0)([])
    assert SEES_YOU in raw.getvalue().decode("ascii")


def test_a_failure_while_drawing_falls_back_to_the_bare_line_fr_315(monkeypatch):
    """FR-315: a drawing that cannot be built does not hide the signature."""

    err = io.StringIO()
    monkeypatch.setattr("sys.stderr", err)
    _phrases_with(monkeypatch, "x" * (_signature.TEXT_COLUMN + 1))
    assert _cli.cli_entrypoint(lambda argv: 7)([]) == 7
    assert err.getvalue().strip() == SEES_YOU


def test_a_closed_stderr_prints_nothing_and_keeps_the_result_fr_315(monkeypatch):
    """FR-315: only a closed stream prints nothing, and the exit code survives."""
    err = io.StringIO()
    err.close()
    monkeypatch.setattr("sys.stderr", err)
    assert _cli.cli_entrypoint(lambda argv: 3)([]) == 3


def _mutant_cli():
    """Return the _cli module rebuilt from its source without the encoding fallback."""
    path = Path(_cli.__file__)
    source = path.read_text(encoding="utf-8")
    mutated = source.replace("except UnicodeEncodeError:", "except ZeroDivisionError:")
    assert mutated != source, "the mutation must take effect"
    module = types.ModuleType("pyflightstream_cli_mutant")
    exec(compile(mutated, str(path), "exec"), module.__dict__)  # noqa: S102
    return module


def test_mutant_without_the_fallback_loses_the_signature_fr_315(monkeypatch):
    """FR-315 control: with the fallback removed the ascii case prints nothing."""
    err, raw = _ascii_stderr()
    monkeypatch.setattr("sys.stderr", err)
    _phrases_with(monkeypatch, ACCENTED)
    _mutant_cli().cli_entrypoint(lambda argv: 0)([])
    err.flush()
    assert SEES_YOU not in raw.getvalue().decode("ascii"), "the test can fail"
    # The same stream with the shipped code carries it.
    err2, raw2 = _ascii_stderr()
    monkeypatch.setattr("sys.stderr", err2)
    _cli.cli_entrypoint(lambda argv: 0)([])
    assert SEES_YOU in raw2.getvalue().decode("ascii")


def test_a_nested_entrypoint_signs_once_fr_315(monkeypatch):
    # Verifies FR-315.
    err = io.StringIO()
    monkeypatch.setattr("sys.stderr", err)
    inner = _cli.cli_entrypoint(lambda argv: 0)
    outer = _cli.cli_entrypoint(lambda argv: inner(argv))
    assert outer([]) == 0
    assert err.getvalue().count(_signature.SEES_YOU) == 1, err.getvalue()
