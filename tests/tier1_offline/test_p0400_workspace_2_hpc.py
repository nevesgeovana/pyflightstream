"""P0400-HPCPROFILE: an HPC profile's tables and booleans are typed; its selector is a stem."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace.costs import select_cost_file
from pyflightstream.workspace.hpc import read_hpc_profile, resolve_hpc_profile, select_hpc_profile
from tests.tier1_offline.test_goal024_profile_log import PROFILE


@pytest.fixture(autouse=True)
def _clear_selection():
    select_hpc_profile(None)
    select_cost_file(None)
    yield
    select_hpc_profile(None)
    select_cost_file(None)


def _profile(tmp_path: Path, text: str, stem: str = "h001") -> Path:
    directory = tmp_path / "hpc"
    directory.mkdir(exist_ok=True)
    path = directory / f"{stem}.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_p0400_hpcprofile_a_quoted_export_log_is_refused(tmp_path):
    """P0400-HPCPROFILE (PFS-2094.023, PFS-2095.032): export_log = "false" is refused as not
    a TOML boolean, where bool("false") kept EXPORT_LOG in the script."""
    path = _profile(tmp_path, PROFILE + '\n[log]\nexport_log = "false"\nnative_log = "x.log"\n')
    with pytest.raises(InputArtifactError, match="true or false, unquoted"):
        read_hpc_profile(path)


@pytest.mark.parametrize(
    ("old", "new", "table"),
    [
        ('[submit]\ncommand = ["esub", "{descriptor_path}"]\n', "", "submit"),
        ("[descriptor]\n", "", "descriptor"),
    ],
)
def test_p0400_hpcprofile_a_table_stated_as_a_value_is_refused_by_name(tmp_path, old, new, table):
    """P0400-HPCPROFILE (PFS-2095.032): a top-level submit = [...] or descriptor = "..." is an
    InputArtifactError naming the profile and the table, never an AttributeError."""
    assert old in PROFILE
    stated = '["esub", "{descriptor_path}"]' if table == "submit" else '"yaml"'
    text = f"{table} = {stated}\n" + PROFILE.replace(old, new)
    if table == "descriptor":
        text = text.replace("[descriptor.fields]", "[fields_elsewhere]")
    path = _profile(tmp_path, text)
    with pytest.raises(InputArtifactError) as caught:
        read_hpc_profile(path)
    message = str(caught.value)
    assert f"{table} entry that is not a table" in message and str(path) in message, message


def test_p0400_hpcprofile_the_selector_takes_the_stem_of_a_named_file(tmp_path):
    """P0400-HPCPROFILE (PFS-2089.005): --hpc h002.toml selects h002, as --cost-file c002.toml
    selects c002."""
    _profile(tmp_path, PROFILE, "h001")
    _profile(tmp_path, PROFILE, "h002")
    select_hpc_profile("h002.toml")
    profile = resolve_hpc_profile(tmp_path)
    assert profile is not None and profile.path.name == "h002.toml"


@pytest.mark.parametrize("table", ["descriptor", "submit", "defaults", "log"])
@pytest.mark.parametrize("value", ['""', "false", "[]", "0"])
def test_p0400_hpcprofile_an_empty_value_is_still_not_a_table(tmp_path, table, value):
    """P0400-HPCPROFILE (PFS-2095.032): falsey values cannot stand in for tables."""
    # Replace exactly one table without moving its fields into another table.
    path = _profile(tmp_path, PROFILE)
    lines = [f"{table} = {value}", 'application_id = "solver"']
    if table != "descriptor":
        lines += ["[descriptor.fields]", 'job = "{sim}"']
    if table != "submit":
        lines += ["[submit]", 'command = ["esub", "{descriptor_path}"]']
    path.write_text(chr(10).join(lines), encoding="utf-8")
    with pytest.raises(InputArtifactError, match=f"{table} entry that is not a table"):
        read_hpc_profile(path)
