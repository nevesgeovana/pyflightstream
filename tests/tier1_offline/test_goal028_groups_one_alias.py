"""A pproc group is ONE alias, written as a string (0.24.0).

The rule, as the requirement states it: a group of the ``[groups]`` table names
ONE alias, so its value is a string and not a list.

    [groups]
    PUSHER   = "PUSHER"      # a rotor: its families come from the reference
    AIRFRAME = "airframe"    # an alias of the reference's [aliases] table
    TOTAL    = "all"         # the selector

The key names the product file; the value says what is summed. It is what makes
a STEADY polar per alias a one-line declaration.

0.23.0 typed the value ``list[int | str]`` and refused a string. Three defects
lived in that list form and end here by construction:

- an INTEGER member is a position the motion path reads, and the polar selector
  skips it, so ``Wing = [1]`` wrote a polar row of plausible zeros
  (INTEGER-GROUP-ZERO);
- a group whose members select NO surface of the export summed to zero instead of
  saying so (PO-07, and the false zero of WT-02);
- the list form let a group be several things at once, which is what an alias of
  the reference is for.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream.cases import PprocSpec, RotorBlock
from pyflightstream.workspace.inputs import rotor_integration_groups


def _rotor(alias: str, blades: list[str], general: list[str] | None = None) -> RotorBlock:
    return RotorBlock(
        alias=alias,
        axis="Z",
        diameter_m=1.0,
        families_blades=blades,
        families_general=general or [],
    )


def test_a_group_is_one_alias_written_as_a_string():
    with warnings.catch_warnings():
        warnings.simplefilter("error", PyflightstreamWarning)
        spec = PprocSpec(groups={"PUSHER": "PUSHER", "AIRFRAME": "airframe", "TOTAL": "all"})
    assert spec.group_alias("PUSHER") == "PUSHER"
    assert spec.group_alias("AIRFRAME") == "airframe"
    # What the rest of the package iterates is unchanged in shape.
    assert list(spec.groups["AIRFRAME"]) == ["airframe"]


@pytest.mark.parametrize(
    "members, replacement",
    [
        (["Blade1"], 'PUSHER = "Blade1"'),
        (["W", "B"], 'PUSHER = "<alias>"'),
        ([], 'PUSHER = "all"'),
        ([1], 'PUSHER = "<alias>"'),
    ],
)
def test_the_list_form_is_refused_with_the_one_alias_line(members, replacement):
    """Since 0.26.0 every list is refused; the reference owns its members."""
    with pytest.raises(InputArtifactError) as refused:
        PprocSpec(groups={"PUSHER": members})
    assert replacement in str(refused.value)


def test_a_member_list_is_refused_by_the_artifact_loader(tmp_path):
    """The TOML loader refuses positions too, before any product is written."""
    from pyflightstream.workspace import CampaignWorkspace

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        "[groups]\nMOVED = [1]\n", encoding="utf-8"
    )
    with pytest.raises(InputArtifactError, match='MOVED = "<alias>"'):
        workspace.resolve_pproc("p001")


def test_a_group_naming_a_rotor_is_that_rotors_families():
    rotors = {"PUSHER": _rotor("PUSHER", ["Blade1", "Blade2"], ["Spinner"])}
    resolved = rotor_integration_groups(rotors, {"PUSHER": ["PUSHER"], "PROP": ["PUSHER"]})
    assert resolved["PUSHER"] == ["Spinner", "Blade1", "Blade2"]
    assert resolved["PROP"] == ["Spinner", "Blade1", "Blade2"], (
        "a group of another name that points at the rotor is the rotor too"
    )


def test_a_group_that_selects_no_surface_is_a_named_skip_and_not_a_row_of_zeros(tmp_path):
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_post_products import _products_manifest, _unsteady_workspace

    # The loads fixture carries surfaces W and B. `GHOST` points at a family the
    # export does not have, which is what a renamed alias leaves behind.
    workspace = _unsteady_workspace(tmp_path, reductions=None)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\nWB = "W"\nGHOST = "Nacelle"\n', encoding="utf-8"
    )
    written = write_campaign_products(workspace)
    names = {Path(path).name for path in written}
    manifest = _products_manifest(workspace)
    ghost = [key for key in manifest.get("skipped", {}) if key.endswith("_GHOST.csv")]
    assert ghost, f"no skip names the group that selected nothing: {manifest.get('skipped')}"
    assert "Nacelle" in manifest["skipped"][ghost[0]]
    assert not any(name.endswith("_GHOST.csv") for name in names), sorted(names)
    assert any(name.endswith("_WB.csv") for name in names), sorted(names)


def test_a_named_group_gets_its_fixed_width_polar_and_states_its_position(tmp_path):
    """`int(group)` on a name was a bare ValueError that stopped the whole stage."""
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_post_products import _products_manifest, _unsteady_workspace

    workspace = _unsteady_workspace(tmp_path, reductions=None)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        "\n".join(
            [
                "[groups]",
                'FIRST = "W"',
                'SECOND = "B"',
                "",
                "[products]",
                "custom_polar_format = true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written = write_campaign_products(workspace)
    dats = sorted(Path(path) for path in written if str(path).endswith(".dat"))
    assert [path.name.rsplit("_", 1)[-1] for path in dats] == ["FIRST.dat", "SECOND.dat"], (
        [path.name for path in dats],
        _products_manifest(workspace).get("skipped"),
    )
    # Line four: the count of reference columns, then the group's NUMBER, which for a
    # named group is its 1-based position in the table.
    numbers = [path.read_text(encoding="utf-8").splitlines()[3].split()[1] for path in dats]
    assert numbers == ["01", "02"], numbers


def test_the_replacement_for_an_empty_list_selects_every_family():
    """The refused empty list points at all, which selects the whole inventory."""
    from pyflightstream.cases import select_group_members

    inventory = ["W", "B", "Blade1", "Blade2"]
    with pytest.raises(InputArtifactError, match='TOTAL = "all"'):
        PprocSpec.model_validate({"groups": {"TOTAL": []}})
    written = PprocSpec.model_validate({"groups": {"TOTAL": "all"}})
    assert select_group_members(written.groups["TOTAL"], inventory) == inventory
    with pytest.warns(PyflightstreamWarning):
        assert select_group_members(["all"], inventory, {"all": ["W"]}) == ["W"]
