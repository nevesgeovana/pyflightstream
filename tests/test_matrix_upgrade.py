"""The third stage of `pyfs-matrix upgrade`: the 0.11.0 layout and the pproc library.

PFS-2029.04, PFS-2029.07.01 and PFS-2029.07.02. The two committed samples are
the same eight rows at the v0.9.0 layout (fifteen columns, ENTRY and
FS_SCRIPT) and at the v0.11.0 layout (fourteen, PPROC), so the converter is
measured against a file a reader can diff.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.cases.matrix import RECIPE_VARIABLE, read_matrix, upgrade_matrix
from pyflightstream.workspace import CampaignWorkspace, migrate_groups_to_pproc
from pyflightstream.workspace.inputs import InputArtifactError

FIXTURES = Path(__file__).parent / "fixtures"
LAYOUT_0_9_0 = FIXTURES / "pfs202609_matrix15.fs"
LAYOUT_0_11_0 = FIXTURES / "pfs202609_matrix14.fs"
#: The author's 0.10.1 reference workspace, outside this repository; the
#: same conversion is measured on it when the estate is present.
PFS0101 = (
    Path(__file__).resolve().parents[2] / "GeoverseResearch/tools/fts_workspace/pfs0101/matriz.fs"
)


def test_upgrade_to_0_11_0_round_trips():
    """The 0.9.0 sample converts byte for byte into the committed 0.11.0 sample."""
    assert upgrade_matrix(LAYOUT_0_9_0) == LAYOUT_0_11_0.read_bytes()
    assert upgrade_matrix(LAYOUT_0_11_0) == LAYOUT_0_11_0.read_bytes(), "running it twice is safe"


@pytest.mark.parametrize(
    "source",
    [LAYOUT_0_9_0] + ([PFS0101] if PFS0101.is_file() else []),
    ids=lambda p: p.name if p.name != "matriz.fs" else "pfs0101",
)
def test_upgrade_drops_fs_script_and_round_trips(tmp_path, source):
    """Lossless in content: every cell but the three the stage owns is unchanged.

    The FS_SCRIPT cell goes; a LEGACY row keeps its code as the RECIPE
    variable and a workflow row drops it, since WORKFLOW names its builder;
    the ENTRY id gains its p; OUTPUTS and LOG_OUTPUT leave a workflow row.
    """
    target = tmp_path / source.name
    target.write_bytes(source.read_bytes())
    before_header = [
        cell.strip() for cell in source.read_text(encoding="utf-8").splitlines()[0].split("|")
    ]
    assert "FS_SCRIPT" in before_header and "ENTRY" in before_header, "not a 0.9.0-layout sample"
    old_rows = {
        cells[0].strip(): [c.strip() for c in cells]
        for cells in (
            line.split("|") for line in source.read_text(encoding="utf-8").splitlines()[2:]
        )
        if len(cells) == len(before_header)
    }
    upgrade_matrix(target, in_place=True)
    after = {row.pol: row for row in read_matrix(target, active_only=False)}
    assert set(after) == set(old_rows)
    script = before_header.index("FS_SCRIPT")
    entry = before_header.index("ENTRY")
    workflow = before_header.index("WORKFLOW")
    for pol, cells in old_rows.items():
        row = after[pol]
        assert row.pproc_code == "p" + cells[entry][1:] if cells[entry][:1] == "e" else cells[entry]
        if cells[workflow] == "LEGACY":
            assert row.script_code == cells[script], "a LEGACY row keeps its recipe code"
            assert row.variables[RECIPE_VARIABLE] == cells[script]
        else:
            assert row.script_code == "", "a workflow row names its builder in WORKFLOW"
            assert "OUTPUTS" not in row.variables and "LOG_OUTPUT" not in row.variables
        assert row.fs_build == cells[before_header.index("FS_BUILD")]
        assert row.ref_code == cells[before_header.index("REF")]


def test_groups_migrate_to_pproc_verbatim(tmp_path):
    """inputs/groups/e001.toml becomes inputs/pproc/p001.toml: its own lines under [groups]."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    groups = workspace.inputs_dir / "groups"
    groups.mkdir()
    body = '# nine entries\n"1" = ["Blade1", "S"]  # every surface\n"2" = ["W", "B"]\n'
    (groups / "e001.toml").write_text(body, encoding="utf-8")
    moved = migrate_groups_to_pproc(workspace.inputs_dir)
    assert moved == {"e001": "p001"}
    target = workspace.inputs_dir / "pproc" / "p001.toml"
    text = target.read_text(encoding="utf-8")
    assert text.endswith("[groups]\n" + body), (
        "the groups are the file's own lines, comments and all"
    )
    assert not (groups / "e001.toml").exists() and not groups.exists()
    assert workspace.resolve_pproc("p001").groups == {"1": ["Blade1", "S"], "2": ["W", "B"]}
    # A second run finds nothing to move, and a groups file left at the top
    # level of a pproc file is named with the migration that fixes it.
    assert migrate_groups_to_pproc(workspace.inputs_dir) == {}
    (workspace.inputs_dir / "pproc" / "p002.toml").write_text("wing = [1]\n", encoding="utf-8")
    with pytest.raises(InputArtifactError, match="migrate_groups_to_pproc"):
        workspace.resolve_pproc("p002")


def test_upgrade_adds_the_extension_to_every_geometry_cell(tmp_path):
    """PFS-2029.09.02: a GEOMETRY value with no extension gains .fsm; one with one is kept."""
    source = FIXTURES / "workflow_rotor_matrix.fs"
    text = source.read_text(encoding="utf-8")
    assert "GEOMETRY:" not in text, "the fixture is expected to name no geometry"
    target = tmp_path / "geometry.fs"
    target.write_text(
        text.replace(
            "| VELOCITY: 30.0 / RPM", "| GEOMETRY: blade_sector / VELOCITY: 30.0 / RPM", 1
        ).replace("| VELOCITY: 30.0\n", "| GEOMETRY: wing.v2.fsm / VELOCITY: 30.0\n", 1),
        encoding="utf-8",
    )
    before = target.read_bytes()
    upgraded = upgrade_matrix(target, in_place=True)
    assert b"GEOMETRY: blade_sector.fsm / VELOCITY" in upgraded
    assert b"GEOMETRY: wing.v2.fsm / VELOCITY" in upgraded, (
        "a value with an extension is left alone"
    )
    assert upgraded.count(b".fsm") == before.count(b".fsm") + 1
    assert upgrade_matrix(target) == upgraded, "running it twice is safe"
