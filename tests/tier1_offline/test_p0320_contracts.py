"""Tier 1: the 0.32.0 contracts the work packages code against.

The preparation step laid down each 0.32.0 module with its public signatures
before any package filled a body, so the packages built in parallel agree on
names, parameters and refusals. This file pins that contract: every signature
by inspection, the refusal of every body not yet written, the one body the
contract implements (``resolve_manifest``), the no-op stage progress, and the
command-line hooks. A package that fills a body replaces the refusal check of
that body with tests of its own behaviour.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import os
from pathlib import Path

import pytest

from pyflightstream import exceptions
from pyflightstream._errors import ContractNotImplementedError, PyflightstreamError
from pyflightstream._progress import StageProgress, stage_progress
from pyflightstream.run import cli, records

NOT_YET = "not implemented yet (0.32.0 contract)"
EMPTY = inspect.Parameter.empty
KW = inspect.Parameter.KEYWORD_ONLY
POS = inspect.Parameter.POSITIONAL_OR_KEYWORD


def _shape(function) -> list[tuple[str, object, object]]:
    return [
        (name, parameter.kind, parameter.default)
        for name, parameter in inspect.signature(function).parameters.items()
    ]


def test_the_refusal_is_catalogued_and_keeps_its_builtin_base():
    assert issubclass(ContractNotImplementedError, PyflightstreamError)
    assert issubclass(ContractNotImplementedError, NotImplementedError)
    assert exceptions.ContractNotImplementedError is ContractNotImplementedError
    assert exceptions.RunsManifestError is records.RunsManifestError
    assert issubclass(records.RunsManifestError, ValueError)


def test_the_records_signatures():
    assert _shape(records.resolve_manifest) == [("root", POS, EMPTY), ("runs", POS, None)]
    assert _shape(records.restore) == [
        ("root", POS, EMPTY),
        ("kind", POS, EMPTY),
        ("stamp", KW, None),
        ("apply", KW, False),
        ("matrix", KW, None),
    ]
    assert _shape(records.rebuild) == [
        ("root", POS, EMPTY),
        ("out", KW, None),
        ("all_sims", KW, False),
        ("sims", KW, None),
        ("build_alias", KW, None),
        ("matrix", KW, None),
        ("apply", KW, False),
        ("inputs_from", KW, None),
    ]
    assert records.RESTORE_KINDS == ("runs", "storage", "products", "plan", "additional")


@pytest.mark.parametrize(
    ("call", "words"),
    [
        (lambda root: records.restore(root, "runs"), "no archived copy"),
        (
            lambda root: records.restore(root, "storage", stamp="20260929-1200", apply=True),
            "no archived copy",
        ),
        (lambda root: records.rebuild(root), "no sims/ folder"),
        (
            lambda root: records.rebuild(root, out="runs-rebuilt.json", all_sims=True, apply=True),
            "no sims/ folder",
        ),
    ],
)
def test_the_records_bodies_are_filled_and_refuse_an_empty_workspace(tmp_path, call, words):
    # Filled by B1 (tests/tier1_offline/test_p0320_records.py holds their behaviour).
    with pytest.raises(records.RecordsError, match=words):
        call(tmp_path)


def test_resolve_manifest_names_runs_json_by_default(tmp_path):
    assert records.resolve_manifest(tmp_path) == tmp_path / "runs.json"
    assert records.resolve_manifest(str(tmp_path)) == tmp_path / "runs.json"
    assert records.resolve_manifest(tmp_path, "runs.json") == tmp_path / "runs.json"


def test_resolve_manifest_names_a_file_directly_in_the_root(tmp_path):
    assert records.resolve_manifest(tmp_path, "runs-rebuilt.json") == (
        tmp_path / "runs-rebuilt.json"
    )
    # Whether it exists is not asked: `rebuild --out` names a new file here.
    assert not (tmp_path / "runs-rebuilt.json").exists()


@pytest.mark.parametrize(
    ("name", "words"),
    [
        ("sub/runs.json", "not a file name"),
        ("sub\\runs.json", "not a file name"),
        ("../runs.json", "not a file name"),
        ("", "not a file name"),
        ("runs.txt", "does not end in .json"),
        ("runs", "does not end in .json"),
        ("runs.JSON", "does not end in .json"),
        (".json", "does not end in .json"),
        ("..", "does not end in .json"),
    ],
)
def test_resolve_manifest_refuses_a_name_that_is_not_a_root_file(tmp_path, name, words):
    with pytest.raises(records.RunsManifestError, match=words):
        records.resolve_manifest(tmp_path, name)


@pytest.mark.skipif(os.name != "nt", reason="a drive exists only in a Windows path")
def test_resolve_manifest_refuses_a_drive_relative_name(tmp_path):
    # On Windows `C:runs.json` carries no separator and still leaves the root.
    with pytest.raises(records.RunsManifestError, match="outside the workspace root"):
        records.resolve_manifest(tmp_path, f"{Path(tmp_path).drive}runs.json")


def test_stage_progress_is_a_working_no_op(capsys):
    assert _shape(stage_progress) == [
        ("name", POS, EMPTY),
        ("total_files", KW, None),
        ("total_bytes", KW, None),
    ]
    assert _shape(StageProgress.advance) == [
        ("self", POS, EMPTY),
        ("files", POS, 0),
        ("bytes", POS, 0),
        ("current", POS, None),
    ]
    with stage_progress("sync: copy", total_files=3, total_bytes=30) as stage:
        assert (stage.name, stage.total_files, stage.total_bytes) == ("sync: copy", 3, 30)
        stage.advance()
        stage.advance(files=1, bytes=10, current="sims/sim_1/a.txt")
        stage.advance(1, 10, Path("sims/sim_1/b.txt"))
    with stage_progress("post") as stage:
        assert stage.total_files is None and stage.total_bytes is None
        stage.advance(files=-1, bytes=10**18)
    assert capsys.readouterr() == ("", "")


def test_stage_progress_lets_the_stage_error_through():
    with pytest.raises(KeyError), stage_progress("collect"):
        raise KeyError("the stage's own error")


def test_the_acoustic_signals_contract():
    from pyflightstream.cases import acoustics as cases_acoustics
    from pyflightstream.post import acoustics as post_acoustics

    signal_type = cases_acoustics.AcousticSignal
    assert dataclasses.is_dataclass(signal_type)
    assert [(field.name, field.type) for field in dataclasses.fields(signal_type)] == [
        ("observer", "str"),
        ("x_m", "float"),
        ("y_m", "float"),
        ("z_m", "float"),
        ("time_s", "tuple[float, ...]"),
        ("pressure_pa", "tuple[float, ...]"),
    ]
    signal = signal_type("mic1", 1.0, 0.0, -2.0, (0.0, 0.1), (0.5, -0.5))
    with pytest.raises(dataclasses.FrozenInstanceError):
        signal.observer = "mic2"  # type: ignore[misc]
    assert isinstance(cases_acoustics.ACOUSTIC_SIGNALS_SUFFIX, str)
    assert post_acoustics.AcousticSignal is signal_type
    assert post_acoustics.ACOUSTIC_SIGNALS_SUFFIX is cases_acoustics.ACOUSTIC_SIGNALS_SUFFIX
    assert _shape(post_acoustics.read_acoustic_signals) == [("path", POS, EMPTY)]
    # E1 filled the reader (FR-260): its behaviour is tested in test_p0320_noise_post.py;
    # here only that the contract name now refuses a file that is not there.
    with pytest.raises(exceptions.ProductError, match="cannot be read"):
        post_acoustics.read_acoustic_signals("P1_acoustic_signals.txt")


#: The placeholder modules: (module, the one stub, the arguments to call it with).
PLACEHOLDERS = [
    ("pyflightstream.post.qsteady_noise", "write_qsteady_noise_report", (".",)),
]


@pytest.mark.parametrize(("module_name", "stub", "arguments"), PLACEHOLDERS)
def test_every_placeholder_module_is_documented_and_refuses(module_name, stub, arguments):
    module = importlib.import_module(module_name)
    assert (module.__doc__ or "").strip(), f"{module_name} carries no docstring"
    with pytest.raises(ContractNotImplementedError) as refusal:
        getattr(module, stub)(*arguments)
    assert NOT_YET in str(refusal.value)
    assert f"{module_name}.{stub}" in str(refusal.value)


def test_the_cli_registers_restore_and_rebuild_with_their_flags():
    parser = cli._build_parser()
    choices = next(action.choices for action in parser._actions if isinstance(action.choices, dict))
    flags = {
        name: {option for action in choices[name]._actions for option in action.option_strings}
        for name in ("restore", "rebuild")
    }
    assert {"--workspace", "--stamp", "--apply"} <= flags["restore"]
    assert {
        "--workspace",
        "--out",
        "--all-sims",
        "--sims",
        "--build-alias",
        "--matrix",
        "--apply",
    } <= flags["rebuild"]
    kind = next(action for action in choices["restore"]._actions if action.dest == "kind")
    assert tuple(kind.choices) == records.RESTORE_KINDS
    for name in ("post", "collect", "free-space", "delete-sims", "sync"):
        runs = [action for action in choices[name]._actions if "--runs" in action.option_strings]
        assert len(runs) == 1 and runs[0].default is None, f"{name} lacks --runs"


def test_the_records_commands_reach_the_bodies_and_exit_two(tmp_path, capsys):
    assert cli.main(["restore", "runs", "--workspace", str(tmp_path)]) == 2
    assert "no archived copy of runs.json" in capsys.readouterr().err
    code = cli.main(
        ["rebuild", "--workspace", str(tmp_path), "--sims", "4001,2009", "--build-alias", "a=b"]
    )
    assert code == 2
    assert "no sims/ folder" in capsys.readouterr().err


def test_rebuild_refuses_a_build_alias_without_its_equals_sign(tmp_path, capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["rebuild", "--workspace", str(tmp_path), "--build-alias", "26.123"])
    assert stop.value.code == 2
    assert "BUILD=ALIAS" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("command", "filled"), [(["post"], False), (["collect"], False), (["sync", "runs"], True)]
)
def test_runs_resolves_its_name_and_refuses_another_manifest_until_filled(
    tmp_path, capsys, command, filled
):
    base = [*command, "--workspace", str(tmp_path)]
    assert cli.main([*base, "--runs", "sub/runs.json"]) == 2
    assert "not a file name" in capsys.readouterr().err
    # Filled by B2 for sync (tests/tier1_offline/test_p0320_sync_matrices.py):
    # the name reaches the command, which refuses tmp_path as no workspace.
    assert cli.main([*base, "--runs", "runs-rebuilt.json"]) == 2
    err = capsys.readouterr().err
    assert (NOT_YET not in err) if filled else (NOT_YET in err)
    if filled:
        assert "not a pyfs-matrix workspace" in err
