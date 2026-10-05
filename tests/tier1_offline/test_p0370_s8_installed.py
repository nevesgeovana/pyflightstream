"""Tier 1, 0.37.0 item S8: the pproc asks for installed-frame copies of the inflow tables.

FR-420. A recorded steady campaign whose probes sit on a YZ plane is posted with
``[products] installed_frame`` naming each family; the copies are read back
against their sources, and the one classification list is held equal to the
definitions page.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.post import inflow_tools
from pyflightstream.post.inflow_tools import to_installed_frame
from pyflightstream.post.products import write_campaign_products
from pyflightstream.run._pending import _write_probe_points
from pyflightstream.script import Script, helpers
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "definitions"
    / "the-installed-frame-copy-of-a-product-table.md"
)
MATRIX = "matriz"
SIM = "0001"
#: Four probes on the plane x = 0: (y, z), and the velocity each was given.
PLANE = ((1.0, -2.0), (1.0, 2.0), (-1.0, -2.0), (-1.0, 2.0))
EXPORT_HEAD = (
    (FIXTURES / "probe_points_26.120.txt").read_text(encoding="utf-8").split("X, Y, Z,")[0]
)
EXPORT_TAIL = (
    (FIXTURES / "probe_points_26.120.txt")
    .read_text(encoding="utf-8")
    .rsplit("     Force Units", 1)[1]
)


def _name(index: int) -> str:
    return f"M100AL+0{index}0BE+000"


def _export(*, extra: bool) -> str:
    """A probe export of the four planted points; ``extra`` adds a column nobody classifies."""
    head = EXPORT_HEAD.replace(
        "Number of Probe Points:                     12",
        "Number of Probe Points:                     4",
    )
    columns = "X, Y, Z, Mach, vx, vy, vz" + (", weird" if extra else "")
    dashes = "     " + "-" * 99 + "\n"
    rows = ""
    for index, (y, z) in enumerate(PLANE, start=1):
        cells = [0.0, y, z, 0.1, 29.0 + index, 1.5 * index, 0.25 * index]
        rows += "     " + ", ".join(f"{value:.4f}" for value in cells)
        rows += (", 7.0000," if extra else ",") + "\n"
    return head + columns + "\n" + dashes + rows + dashes + "     Force Units" + EXPORT_TAIL


def _workspace(root: Path, *, key: str = "", extra: bool = False) -> CampaignWorkspace:
    """A steady polar of two points, each sampling four probes on a YZ plane."""
    workspace = CampaignWorkspace.init(root / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        f'[groups]\n"1" = "Wing"\n\n[products]\nsettings_codebook = false\n{key}',
        encoding="utf-8",
    )
    collected = workspace.sim_dir(SIM) / "outputs"
    collected.mkdir(parents=True)
    loads = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
    positions = [(i, 0.0, y, z, "REFERENCE") for i, (y, z) in enumerate(PLANE, start=1)]
    relative = _write_probe_points(workspace.sim_dir(SIM), SIM, positions)
    setup = helpers.solver_settings(Script(version="26.124"), velocity=30.0)
    for index in range(2):
        stem = f"POLAR-{SIM}_{_name(index)}"
        (collected / f"{stem}.txt").write_text(loads, encoding="utf-8")
        (collected / f"{stem}_probes.txt").write_text(_export(extra=extra), encoding="utf-8")
        workspace.append_record(
            RunRecord(
                run_id=f"camp/sim_{SIM}/{_name(index)}",
                point_name=_name(index),
                sweep_name="M100AL+000BE+000+sweep",
                sim_id=SIM,
                point={"alpha": float(index), "beta": 0.0},
                matrix_stem=MATRIX,
                fs_version_requested="26.124",
                package_version="0.37.0",
                script_path=f"scripts/{stem}.txt",
                script_sha256="c" * 64,
                raw_flag=False,
                pproc="p001",
                description="WING",
                mach=0.1,
                reference={"SREF": 11.5, "CREF": 1.5, "BREF": 8.0, "XMOM": 1.0},
                status=RunStatus.CONVERGED,
                outputs=[f"outputs/{stem}.txt", f"outputs/{stem}_probes.txt"],
                probe_points_file=relative,
                solver_setup=setup.model_dump(mode="json"),
                probe_field_layout=[
                    {
                        "entry": 1,
                        "kind": "probe-field",
                        "probe_ids": [1, 2, 3, 4],
                        "frame": "REFERENCE",
                        "native_to_m": 1,
                        "formats": [],
                        "reusable_inflow": True,
                    }
                ],
            )
        )
    return workspace


def _post(workspace: CampaignWorkspace) -> Path:
    write_campaign_products(workspace, matrix_stem=MATRIX)
    return workspace.products_dir(MATRIX)


def _manifest(out: Path) -> dict:
    return json.loads((out / "products.json").read_text(encoding="utf-8"))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return [{k.upper(): v for k, v in row.items()} for row in csv.DictReader(stream)]


def _profile(path: Path) -> list[list[float]]:
    return [[float(cell) for cell in line.split()] for line in path.read_text().splitlines()]


def _tree(out: Path) -> dict[str, bytes]:
    return {
        path.relative_to(out).as_posix(): path.read_bytes()
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.name not in ("post.log", "post.log.json", "products.json")
    }


BOTH = 'installed_frame = ["probes", "inflow"]\n'


def test_a_probe_at_plus_y_appears_at_minus_y_with_its_velocity_mirrored(tmp_path):
    """P0370-S8-INSTALLED-INFLOW (FR-420): Y and VY negate, every other column stays."""
    out = _post(_workspace(tmp_path, key=BOTH))
    point = f"POLAR-{SIM}_{_name(0)}"
    source = _rows(out / "probes" / f"{point}_probes.csv")
    copy = _rows(out / "probes" / f"{point}_probes_installed.csv")
    assert len(source) == len(copy) == len(PLANE)
    for before, after in zip(source, copy, strict=True):
        assert float(before["Y"]) != 0.0
        assert float(after["Y"]) == -float(before["Y"])
        assert float(after["VY"]) == -float(before["VY"])
        for column in before:
            if column not in ("Y", "VY"):
                assert after[column] == before[column], column
    assert {float(row["Y"]) for row in source} == {1.0, -1.0}
    assert [float(row["Y"]) for row in copy] == [-float(row["Y"]) for row in source]


def test_the_inflow_profile_is_mirrored_through_y_zero(tmp_path):
    """P0370-S8-INSTALLED-INFLOW (FR-420): x y z vx vy vz becomes x -y z vx -vy vz."""
    out = _post(_workspace(tmp_path, key=BOTH))
    point = f"POLAR-{SIM}_{_name(0)}"
    source = _profile(out / "fields" / f"{point}_field_01.inflow.dat")
    copy = _profile(out / "fields" / f"{point}_field_01.inflow_installed.dat")
    assert len(source) == len(copy) == len(PLANE)
    assert {row[1] for row in source} == {1.0, -1.0}
    for before, after in zip(source, copy, strict=True):
        x, y, z, vx, vy, vz = before
        assert after == [x, -y, z, vx, -vy, vz]
        assert vy != 0.0 and y != 0.0


def test_the_vorticity_negates_its_x_and_z_and_keeps_y(tmp_path):
    """P0370-S8-INSTALLED-INFLOW (FR-420 R1): the axial vector's x and z change sign."""
    table = tmp_path / "t.csv"
    table.write_text(
        "POL,Y,VY,VORTICITY_X,VORTICITY_Y,VORTICITY_Z,AZIMUTH\n0001,2.5,3.5,4.5,5.5,6.5,30\n",
        encoding="utf-8",
    )
    (row,) = _rows(to_installed_frame(table))
    assert float(row["Y"]) == -2.5 and float(row["VY"]) == -3.5
    assert float(row["VORTICITY_X"]) == -4.5 and float(row["VORTICITY_Z"]) == -6.5
    assert float(row["VORTICITY_Y"]) == 5.5
    assert float(row["AZIMUTH"]) == 330.0


def test_mirroring_twice_returns_the_source(tmp_path):
    """P0370-S8-INSTALLED-INFLOW (FR-420): the copy of a copy is the source, byte for byte."""
    out = _post(_workspace(tmp_path, key=BOTH))
    point = f"POLAR-{SIM}_{_name(0)}"
    source = out / "probes" / f"{point}_probes.csv"
    again = to_installed_frame(
        out / "probes" / f"{point}_probes_installed.csv", out=tmp_path / "b.csv"
    )
    assert again.read_bytes() == source.read_bytes()
    profile = out / "fields" / f"{point}_field_01.inflow.dat"
    copy = _profile(out / "fields" / f"{point}_field_01.inflow_installed.dat")
    twice = [[x, -y, z, vx, -vy, vz] for x, y, z, vx, vy, vz in copy]
    assert twice == _profile(profile)


def test_a_column_the_classification_cannot_place_is_copied_and_named_once(tmp_path):
    """P0370-S8-INSTALLED-INFLOW (FR-420 R2): unknown column unchanged, one post.log line."""
    out = _post(_workspace(tmp_path, key='installed_frame = ["probes"]\n', extra=True))
    for index in range(2):
        point = f"POLAR-{SIM}_{_name(index)}"
        source = _rows(out / "probes" / f"{point}_probes.csv")
        copy = _rows(out / "probes" / f"{point}_probes_installed.csv")
        assert [row["WEIRD"] for row in copy] == [row["WEIRD"] for row in source]
        assert {row["WEIRD"] for row in copy} == {row["WEIRD"] for row in source} != set()
    log = (out / "post.log").read_text(encoding="utf-8")
    named = [line for line in log.splitlines() if "weird" in line and "installed" in line]
    assert len(named) == 1, named
    assert not [line for line in log.splitlines() if "installed" in line and "VY" in line]


def test_the_manifest_names_each_copy_and_its_source(tmp_path):
    """P0370-S8-INSTALLED-INFLOW (FR-420 R3): kind installed_frame and the source table."""
    out = _post(_workspace(tmp_path, key=BOTH))
    products = _manifest(out)["products"]
    for index in range(2):
        point = f"POLAR-{SIM}_{_name(index)}"
        pairs = {
            f"probes/{point}_probes_installed.csv": f"probes/{point}_probes.csv",
            f"fields/{point}_field_01.inflow_installed.dat": f"fields/{point}_field_01.inflow.dat",
        }
        for name, source in pairs.items():
            assert products[name]["source"] == source
            assert products[name]["kind"] == "installed_frame"
            assert products[name]["runs"] == [f"camp/sim_{SIM}/{_name(index)}"]
            assert (out / name).is_file() and (out / source).is_file()


def test_with_the_key_empty_or_absent_nothing_new_is_written(tmp_path):
    """P0370-S8-INSTALLED-INFLOW (FR-420 R3): absent equals empty and lacks the copies."""
    absent = _post(_workspace(tmp_path / "a"))
    empty = _post(_workspace(tmp_path / "b", key="installed_frame = []\n"))
    full = _post(_workspace(tmp_path / "c", key=BOTH))
    assert _tree(absent) == _tree(empty)
    assert not [name for name in _tree(absent) if "installed" in name]
    assert set(_manifest(full)["products"]) - set(_manifest(absent)["products"]) == {
        f"{folder}/POLAR-{SIM}_{_name(i)}{tail}"
        for i in range(2)
        for folder, tail in (
            ("probes", "_probes_installed.csv"),
            ("fields", "_field_01.inflow_installed.dat"),
        )
    }
    assert {name: data for name, data in _tree(full).items() if "installed" not in name} == _tree(
        absent
    )


def test_a_family_the_post_does_not_mirror_is_refused_where_the_pproc_is_read(tmp_path):
    """P0370-S8-INSTALLED-INFLOW (FR-420 R4): the refusal names the accepted families."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "Wing"\n\n[products]\ninstalled_frame = ["probes", "wake"]\n',
        encoding="utf-8",
    )
    with pytest.raises(InputArtifactError, match=r"'wake'.*probes, inflow"):
        workspace.resolve_pproc("p001")


def test_the_classification_list_is_the_definitions_page_with_the_flow_columns():
    """P0370-S8-INSTALLED-INFLOW (FR-420 R1): the code's one list equals the page's flip rows."""
    section = PAGE.read_text(encoding="utf-8").split("## The installed-frame copy", 1)[1]
    section = section.split("\n## ", 1)[0]
    listed = re.findall(r"^\| `([^`]+)` \| (flip|azimuth|keep) \|", section, flags=re.M)
    flip = tuple(name for name, kind in listed if kind == "flip")
    assert flip == inflow_tools.FLIPPED_COLUMNS
    assert {"Y", "VY", "VORTICITY_[XZ]"} <= set(flip)


def test_to_installed_frame_now_mirrors_the_flow_columns_of_a_table_that_carries_them(tmp_path):
    """P0370-S8-INSTALLED-INFLOW (FR-420 R1): the migration consequence, held by behaviour."""
    table = tmp_path / "t.csv"
    table.write_text("X,Y,Z,VX,VY,VZ\n1,2,3,4,5,6\n", encoding="utf-8")
    (row,) = _rows(to_installed_frame(table))
    assert [float(row[c]) for c in ("X", "Y", "Z", "VX", "VY", "VZ")] == [1, -2, 3, 4, -5, 6]


def test_the_reference_chord_is_not_a_roll_coefficient(tmp_path):
    """P0370-S8-INSTALLED-INFLOW (FR-420 R1): CREF stays as written, CRB25 changes sign."""
    table = tmp_path / "t.csv"
    table.write_text("CREF,CRB25,CR\n1.5,2.5,3.5\n", encoding="utf-8")
    (row,) = _rows(to_installed_frame(table))
    assert (float(row["CREF"]), float(row["CRB25"]), float(row["CR"])) == (1.5, -2.5, -3.5)
