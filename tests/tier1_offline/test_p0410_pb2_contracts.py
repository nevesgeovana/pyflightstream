"""P0410-PB2: executable refusal and pre-write contracts, with negative controls."""

from __future__ import annotations

import ast
import importlib
import inspect
import re
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from pyflightstream._errors import InputArtifactError, PyflightstreamError
from pyflightstream.qa import COMPAT_SCHEMA, apply_compat
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.workspace.inputs import PprocArtifact

ROOT = Path(__file__).resolve().parents[2]


def _documented_models():
    """Resolve documented refusal names, then check real model inheritance."""
    source = ROOT / "src" / "pyflightstream"
    for path in sorted(source.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        classes = [
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and re.search(r"\b\w+Error\b", ast.get_docstring(node) or "")
        ]
        if not classes:
            continue
        parts = path.relative_to(source.parent).with_suffix("").parts
        module = importlib.import_module(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
        for node in classes:
            model = getattr(module, node.name)
            if not isinstance(model, type) or not issubclass(model, BaseModel):
                continue
            for name in set(re.findall(r"\b\w+Error\b", inspect.getdoc(model) or "")):
                refusal = getattr(module, name, None)
                if isinstance(refusal, type) and issubclass(refusal, PyflightstreamError):
                    yield model, refusal


def _assert_refusal(operation: Callable[[], object], refusal: type[Exception], field: str = ""):
    try:
        operation()
    except Exception as error:
        assert isinstance(error, refusal), (
            f"expected {refusal.__name__}, got {type(error).__name__}: {error}"
        )
        assert not isinstance(error, ValidationError), "bare pydantic refusal escaped"
        assert field in str(error), f"refusal does not name {field!r}: {error}"
    else:
        pytest.fail("invalid request was accepted")


def test_p0410_pb2_documented_model_refusals_are_executable():
    contracts = list(_documented_models())
    assert (PprocArtifact, InputArtifactError) in contracts
    for model, refusal in contracts:
        _assert_refusal(lambda model=model: model.model_validate(None), refusal)


@pytest.mark.parametrize("data", [{"groups": {"BODY": 7}}, {"unknown_field": True}])
def test_p0410_pb2_pproc_constructor_uses_its_documented_refusal(data):
    _assert_refusal(lambda: PprocArtifact(**data), InputArtifactError)


def test_p0410_pb2_model_guard_catches_a_planted_bare_validation_error():
    class BrokenModel(BaseModel):
        value: float

    with pytest.raises(AssertionError, match="got ValidationError"):
        _assert_refusal(lambda: BrokenModel(value="invalid"), InputArtifactError)
    with pytest.raises(pytest.fail.Exception, match="accepted"):
        _assert_refusal(lambda: None, InputArtifactError)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_p0410_pb2_nfr47_nonfinite_pproc_names_nested_field_in_public_refusal(value):
    data = {"farfield": {"families": ["wing"], "ledgers": {"frame": "survey", "tip_radius_m": 1.0}}}
    assert PprocArtifact(**data).farfield.ledgers.tip_radius_m == 1.0
    data["farfield"]["ledgers"]["tip_radius_m"] = value
    _assert_refusal(lambda: PprocArtifact(**data), InputArtifactError, "tip_radius_m")


def _assert_console_refusal(main, argv, capsys, cause):
    capsys.readouterr()
    try:
        code = main(argv)
    except SystemExit as error:
        code = error.code
    except BaseException as error:
        pytest.fail(f"uncaught {type(error).__name__}: {error}")
    output = "".join(capsys.readouterr())
    assert isinstance(code, int) and code != 0, "failed operation reported success"
    assert cause in output
    assert "Traceback (most recent call last)" not in output


def test_p0410_pb2_nfr48_console_refuses_invalid_workspace_settings(tmp_path, capsys):
    from pyflightstream.run.cli import main

    (tmp_path / "pyfs.toml").write_text("[defaults]\nunknown_setting = 1\n", encoding="utf-8")
    _assert_console_refusal(
        main, ["plan", "absent.fs", "--workspace", str(tmp_path)], capsys, "unknown_setting"
    )


@pytest.mark.parametrize("failure", [OSError("planted failure"), KeyboardInterrupt()])
def test_p0410_pb2_console_guard_catches_planted_uncaught_failures(failure, capsys):
    def broken(argv):
        raise failure

    with pytest.raises(pytest.fail.Exception, match="uncaught"):
        _assert_console_refusal(broken, [], capsys, "planted")


def _assert_unchanged_refusal(operation, files):
    before = {path: path.read_bytes() for path in files}
    _assert_refusal(operation, QaEvidenceError)
    assert {path: path.read_bytes() for path in files} == before, "write occurred before refusal"


def test_p0410_pb2_nfr49_second_chapter_refusal_precedes_every_write(tmp_path, monkeypatch):
    import pyflightstream._textio as textio

    chapters = tmp_path / "commands"
    chapters.mkdir()
    (chapters / "_meta.yaml").write_text(
        'versions:\n  - canonical: "26.120"\n    alias: "26.12"\n', encoding="utf-8"
    )
    paths = []
    for filename, name, note in [
        ("a.yaml", "PRINT", ""),
        ("z.yaml", "STOP", ', note: "FSM-26.100 p.358, this edition"'),
    ]:
        path = chapters / filename
        path.write_text(
            f"{name}:\n  layout: bare\n  phase: control\n  args: []\n"
            '  manual_ref: "FSM-26.120 p.281"\n  versions:\n'
            f'    "26.120": {{status: documented{note}}}\n',
            encoding="utf-8",
        )
        paths.append(path)
    report = tmp_path / "CMP-26120_2026-08-11.yaml"
    report.write_text(
        yaml.safe_dump(
            {
                "schema": COMPAT_SCHEMA,
                "fs_version": "26.120",
                "date": "2026-08-11",
                "commands": {
                    "PRINT": {"outcome": "verified", "detail": "observed"},
                    "STOP": {"outcome": "removed", "detail": "name refused"},
                },
            }
        ),
        encoding="utf-8",
    )
    writes = []
    original = textio.write_text

    def observe(path, *args, **kwargs):
        writes.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(textio, "write_text", observe)
    _assert_unchanged_refusal(
        lambda: apply_compat(report, repo_root=tmp_path, commands_dir=chapters), paths
    )
    assert not writes, f"write started before the final validation: {writes}"


def test_p0410_pb2_prewrite_guard_catches_a_planted_early_replacement(tmp_path):
    path = tmp_path / "existing.txt"
    path.write_text("preserve", encoding="utf-8")

    def broken():
        path.write_text("replaced", encoding="utf-8")
        raise QaEvidenceError("invalid second destination")

    with pytest.raises(AssertionError, match="write occurred"):
        _assert_unchanged_refusal(broken, [path])
