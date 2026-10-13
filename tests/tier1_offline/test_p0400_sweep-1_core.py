# ruff: noqa: N999
"""Offline regressions for the remaining sweep-1 cross-file joins."""

from __future__ import annotations

import importlib
import json
import warnings

import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.cases.reference_blocks import CampaignConfigError
from pyflightstream.cases.selection import resolve_alias, select_families, select_group_members
from pyflightstream.run._alias import planned_in_workspace
from pyflightstream.run._cli_print import _alias_block
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.script import CommandArgumentError, Script
from pyflightstream.workspace._refine import _config
from pyflightstream.workspace._settings_file import read_workspace_settings
from tests.tier1_offline.test_p0340_run_usability import _names, _two_simulations
from tests.tier1_offline.test_p0390_taglen import _request


@pytest.mark.parametrize("filename", ["pyfs.toml", "pyfs.local.toml"])
@pytest.mark.parametrize("key", ["console", "verbose", "log_level", "pproc_warnings"])
def test_p0400_log_defaults_remedy(tmp_path, filename, key):
    """P0400-SWEEP-LOG-DEFAULTS (FR-436): misplaced console keys name the [log] remedy."""
    (tmp_path / filename).write_text(f'[defaults]\n{key} = "normal"\n', encoding="utf-8")
    with pytest.raises(InputArtifactError, match=r"\[log\]"):
        read_workspace_settings(tmp_path)


@pytest.mark.parametrize("filename", ["pyfs.toml", "pyfs.local.toml"])
@pytest.mark.parametrize("value", ["true", "false"])
def test_p0400_acceptance_defaults_refused(tmp_path, filename, value):
    """P0400-SWEEP-ACCEPTANCE (FR-436): acceptance belongs to an entry or a typed flag."""
    (tmp_path / filename).write_text(
        f"[defaults]\naccept_unregistered_build = {value}\n", encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match="executables.local.toml"):
        read_workspace_settings(tmp_path)


@pytest.mark.parametrize("key,value", [("fs_exe", '"solver.exe"'), ("local", "true")])
def test_p0400_machine_defaults_local_only(tmp_path, key, value):
    """P0400-SWEEP-LOCAL-DEFAULTS (FR-436): machine choices stay in the local overlay."""
    path = tmp_path / "pyfs.toml"
    path.write_text(f"[defaults]\n{key} = {value}\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match="pyfs.local.toml"):
        read_workspace_settings(tmp_path)
    path.unlink()
    (tmp_path / "pyfs.local.toml").write_text(f"[defaults]\n{key} = {value}\n", encoding="utf-8")
    assert key in read_workspace_settings(tmp_path).defaults


@pytest.mark.parametrize("filename", ["pyfs.toml", "pyfs.local.toml"])
def test_p0400_runs_default_refused(tmp_path, filename):
    """P0400-SWEEP-RUNS-DEFAULT: manifest selection is per invocation."""
    (tmp_path / filename).write_text('[defaults]\nruns = "other.json"\n', encoding="utf-8")
    with pytest.raises(InputArtifactError, match="one invocation"):
        read_workspace_settings(tmp_path)


def test_p0400_overview_relative_path(tmp_path, monkeypatch):
    """P0400-SWEEP-OVERVIEW-RELPATH: a relative destination opens an absolute URI."""
    module = importlib.import_module("pyflightstream.overview")
    opened = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module.webbrowser, "open", opened.append)
    assert module.overview(path="overview.html").is_file()
    assert opened == [(tmp_path / "overview.html").as_uri()]


def test_p0400_uniform_tag_limit(tmp_path):
    """P0400-SWEEP-UNIFORM-TAG: every automatic tag obeys the 32 character limit."""
    spec = _config.FamilySpec(factor=0.0000123456, chordwise=0.0000123456, spanwise=0.0000123456)
    request = _request(tmp_path, ["Wing"], over={"Wing": spec})
    assert len(_config.level_tag(request, ["Wing"])) <= _config.TAG_MAX
    assert _config.tag_selection(request, ["Wing"]) == ["Wing"]


@pytest.mark.parametrize("route", ["group", "family", "family-list"])
def test_p0400_numbered_boundary_exact(route):
    """P0400-SWEEP-BOUNDARY-EXACT: an absent numbered label cited alone is refused by name."""
    inventory = ["Hub2", "Hub3", "MainWing"]

    def operation(**options):
        if route == "group":
            return select_group_members(["Hub1"], inventory, **options)
        selection = "Hub1" if route == "family" else ["Hub1"]
        return select_families(selection, inventory, lambda name: False, **options)

    with pytest.raises(CampaignConfigError, match="Hub1.*Hub2.*Hub3"):
        operation()
    assert select_group_members(["Hub"], inventory) == ["Hub2", "Hub3"]
    with pytest.warns(PyflightstreamWarning, match="Hub1"):
        assert operation(strict=False) == []


@pytest.mark.parametrize("route", ["group", "family-list", "alias", "nested-alias"])
@pytest.mark.parametrize("strict", [True, False])
def test_p0400_numbered_member_exact(route, strict):
    """P0400-SWEEP-BOUNDARY-EXACT: a numbered MEMBER selects its exact name, never refused.

    The decision of 2026-10-12 on PFS-2029.25: a member of a list, a group or
    an alias the geometry lacks is left to the FR-320 warning and the FR-435
    rule, and it never selects its numbered siblings.
    """
    inventory = ["Hub2", "Hub3", "MainWing"]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        if route == "group":
            found = select_group_members(["Hub1", "MainWing"], inventory, strict=strict)
        elif route == "family-list":
            found = select_families(
                ["Hub1", "MainWing"], inventory, lambda name: False, strict=strict
            )
        elif route == "alias":
            found = resolve_alias("hubs", inventory, {"hubs": ["Hub1", "MainWing"]})
        else:
            found = select_families(
                "outer",
                inventory,
                lambda name: False,
                {"outer": ["hubs"], "hubs": ["Hub1"]},
                strict=strict,
            )
    expected = {"family-list": [["MainWing"]], "nested-alias": []}
    assert found == expected.get(route, ["MainWing"])


@pytest.mark.parametrize("number", [1, 2, 3, 4, 5])
def test_p0400_rbf_numeric_vocabulary(number):
    """P0400-SWEEP-RBF-VOCABULARY: the documented numeric options are accepted."""
    script = Script("26.124")
    script.emit("AEROELASTIC_RBF_TYPE", number)
    assert f"AEROELASTIC_RBF_TYPE {number}" in script.render()


def test_p0400_animation_missing_anchor():
    """P0400-SWEEP-JOIN-ANCHOR: a joined value cannot attach to another keyword."""
    script = Script("26.124")
    with pytest.raises(CommandArgumentError, match="volume_sections"):
        script.emit(
            "UNSTEADY_SOLVER_ANIMATION", "ENABLE", frequency=2, volume_sections_format="VTK"
        )
    script.emit(
        "UNSTEADY_SOLVER_ANIMATION",
        "ENABLE",
        volume_sections="ENABLE",
        volume_sections_format="VTK",
    )
    assert "VOLUME_SECTIONS ENABLE VTK" in script.render()


def test_p0400_matrix_selection_preserves_order(tmp_path, monkeypatch):
    """P0400-SWEEP-ALIAS-PLAN: matrix planning retains the full sweep's alias order."""
    workspace, matrix, _ = _two_simulations(tmp_path, monkeypatch)
    names = _names(workspace, matrix, "5002")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        plan = plan_matrix(
            matrix,
            workspace,
            name="warm",
            fs_version="26.120",
            recipes={},
            sims=["5002"],
            points=[names[2]],
            ignore_missing_families=True,
        )
    assert _alias_block(plan, []) == [f"  5002_3  POL 5002 {names[2]}"]
    assert planned_in_workspace(workspace.root, [])["5002"] == names
    saved = json.loads((workspace.plan_dir(matrix.stem) / "plan.json").read_text(encoding="utf-8"))
    assert [point["run_id"].rsplit("/", 1)[-1] for point in saved["points"]] == [names[2]]
