"""The HPC profile selector of 0.35: ``--hpc NAME`` picks one of several profiles."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
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
    # `plan` and `run` parse the option, then stop at their own gates.
    main(["run", "none.fs", "--workspace", str(tmp_path), "--hpc", "h002"])
    profile = resolve_hpc_profile(inputs)
    assert profile is not None
    assert profile.application_id == "app-h002"


def test_one_profile_without_selection_is_unchanged(tmp_path):
    inputs = _inputs(tmp_path, "h001")
    profile = resolve_hpc_profile(inputs)
    assert profile is not None
    assert profile.application_id == "app-h001"
    assert resolve_hpc_profile(tmp_path / "nowhere") is None
