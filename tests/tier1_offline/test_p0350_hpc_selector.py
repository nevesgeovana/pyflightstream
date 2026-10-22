"""The HPC profile selector of 0.35: ``--hpc NAME`` picks one of several profiles."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.run._cli_parsers import _build_parser, parsed
from pyflightstream.run.cli import main
from pyflightstream.workspace.hpc import resolve_hpc_profile, select_hpc_profile

_REST = """
[descriptor]
template = "descriptor.tmpl"

[descriptor.fields]
walltime = "{walltime}"

[submit]
command = ["sbatch", "{descriptor}"]
"""


@pytest.fixture(autouse=True)
def _clear_selection():
    select_hpc_profile(None)
    yield
    select_hpc_profile(None)


def _inputs(tmp_path: Path, *stems: str) -> Path:
    hpc = tmp_path / "inputs" / "hpc"
    hpc.mkdir(parents=True)
    for stem in stems:
        text = f'application_id = "app-{stem}"\n{_REST}'
        (hpc / f"{stem}.toml").write_text(text, encoding="utf-8")
    return tmp_path / "inputs"


def test_several_profiles_without_selection_name_the_remedy(tmp_path):
    inputs = _inputs(tmp_path, "h001", "h002")
    with pytest.raises(InputArtifactError, match=re.escape("hpc (CLI: --hpc)")):
        resolve_hpc_profile(inputs)


def test_selection_returns_that_profile(tmp_path):
    inputs = _inputs(tmp_path, "h001", "h002")
    select_hpc_profile("h002")
    profile = resolve_hpc_profile(inputs)
    assert profile is not None
    assert profile.application_id == "app-h002"


def test_selection_of_an_absent_stem_names_the_available_ones(tmp_path):
    inputs = _inputs(tmp_path, "h001", "h002")
    select_hpc_profile("h009")
    with pytest.raises(InputArtifactError, match=r"h009.*h001, h002"):
        resolve_hpc_profile(inputs)


def test_cli_parse_sets_the_selection(tmp_path):
    inputs = _inputs(tmp_path, "h001", "h002")
    # The parse selects the profile; outside a console command it stays set.
    parsed(_build_parser(), ["run", "none.fs", "--workspace", str(tmp_path), "--hpc", "h002"])
    profile = resolve_hpc_profile(inputs)
    assert profile is not None
    assert profile.application_id == "app-h002"
    # A console command selects it for itself alone (PFS-2094.008): `run` stops
    # at its own gate and a later resolve sees no selection.
    select_hpc_profile(None)
    main(["run", "none.fs", "--workspace", str(tmp_path), "--hpc", "h002"])
    with pytest.raises(InputArtifactError, match="holds 2 profiles"):
        resolve_hpc_profile(inputs)


def test_one_profile_without_selection_is_unchanged(tmp_path):
    inputs = _inputs(tmp_path, "h001")
    profile = resolve_hpc_profile(inputs)
    assert profile is not None
    assert profile.application_id == "app-h001"
    assert resolve_hpc_profile(tmp_path / "nowhere") is None


def test_p0430_f1566_a_dotted_cost_file_name_keeps_its_dots(tmp_path) -> None:
    """F-1566: only a final .toml is a suffix of --cost-file."""
    import argparse

    from pyflightstream.run._cli_parsers import _select_for_this_invocation
    from pyflightstream.workspace.costs import resolve_cost_file, select_cost_file

    (tmp_path / "costs").mkdir()
    try:
        # The refusal of a selection that names no file quotes the selected stem.
        _select_for_this_invocation(argparse.Namespace(hpc=None, cost_file="c1.2"))
        with pytest.raises(InputArtifactError, match=r"named 'c1\.2'"):
            resolve_cost_file(tmp_path)
        _select_for_this_invocation(argparse.Namespace(hpc=None, cost_file="c001.toml"))
        with pytest.raises(InputArtifactError, match=r"named 'c001'"):
            resolve_cost_file(tmp_path)
    finally:
        select_cost_file(None)


def test_p0430_f1567_f1563_a_windows_command_line_quotes_metacharacters(monkeypatch) -> None:
    """F-1567, F-1563: a word with & or a space is quoted in the printed command."""
    from pyflightstream.run import _ids

    monkeypatch.setattr(_ids.os, "name", "nt")
    text = _ids.command_line_text(["pyfs-matrix", "--workspace", "C:/a b/c&d", "x"])
    assert text == 'pyfs-matrix --workspace "C:/a b/c&d" x'
    assert _ids.command_line_text(["a&b"]) == '"a&b"'


def test_p0430_f1893_the_post_local_help_does_not_call_the_submitting_post_unbuilt(capsys) -> None:
    """F-1893: the submitted additional post is implemented, so its help must not say it is not."""
    with pytest.raises(SystemExit):
        main(["post", "--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "--local" in out
    assert "is not built" not in out


_DEFAULTS_BLOCK = """
[defaults]
memory = 4
"""


def test_pfs_2117_026_a_profile_with_a_defaults_block_loads_and_warns(tmp_path):
    """HpcProfile.defaults is gone; a profile that still carries the block loads with a WARNING."""
    import dataclasses

    from pyflightstream._errors import PyflightstreamWarning

    inputs = _inputs(tmp_path, "h001")
    path = inputs / "hpc" / "h001.toml"
    path.write_text(path.read_text(encoding="utf-8") + _DEFAULTS_BLOCK, encoding="utf-8")
    with pytest.warns(PyflightstreamWarning, match="defaults block, which was removed in 0.43.0"):
        profile = resolve_hpc_profile(inputs)
    assert profile is not None
    assert "defaults" not in {f.name for f in dataclasses.fields(profile)}
