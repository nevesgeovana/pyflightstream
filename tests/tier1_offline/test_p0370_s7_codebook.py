"""Tier 1, 0.37.0 item S7: the settings table and its codebook are a campaign product.

FR-419. A recorded campaign is posted with and without ``[products]
settings_codebook = true``; the table's rows are read back against the
records, the legend against the library's own codebook, and the manifest
entries against what is on disk.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pyflightstream.post.products import write_campaign_products
from pyflightstream.post.settings_table import CODEBOOK_VERSION, FLAG_IDS, codebook
from pyflightstream.script import Script, helpers
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

FIXTURES = Path(__file__).parent / "fixtures"
MATRIX = "matriz"
SIM = "0001"
SPEEDS = (20.0, 30.0, 40.0)
VELOCITY = FLAG_IDS["SOLVER_SET_VELOCITY"]
TABLE = f"settings/{MATRIX}_settings.csv"
LEGEND = f"settings/{MATRIX}_settings.codebook.json"


def _name(index: int) -> str:
    return f"M100AL+0{index}0BE+000"


def _workspace(
    root: Path, *, key: str = "", without_snapshot: tuple[int, ...] = ()
) -> CampaignWorkspace:
    """A recorded steady polar of three points, each with its own velocity snapshot."""
    workspace = CampaignWorkspace.init(root / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        f'[groups]\n"1" = "Wing"\n\n[products]\n{key}', encoding="utf-8"
    )
    collected = workspace.sim_dir(SIM) / "outputs"
    collected.mkdir(parents=True)
    export = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
    for index, speed in enumerate(SPEEDS):
        stem = f"POLAR-{SIM}_{_name(index)}"
        (collected / f"{stem}.txt").write_text(export, encoding="utf-8")
        setup = helpers.solver_settings(Script(version="26.120"), velocity=speed)
        workspace.append_record(
            RunRecord(
                run_id=f"camp/sim_{SIM}/{_name(index)}",
                point_name=_name(index),
                sweep_name="M100AL+000BE+000+sweep",
                sim_id=SIM,
                point={"alpha": float(index), "beta": 0.0},
                matrix_stem=MATRIX,
                fs_version_requested="26.120",
                package_version="0.36.0",
                script_path=f"scripts/{stem}.txt",
                script_sha256="c" * 64,
                raw_flag=False,
                pproc="p001",
                description="WING",
                mach=0.1,
                reference={"SREF": 11.5, "CREF": 1.5, "BREF": 8.0, "XMOM": 1.0},
                status=RunStatus.CONVERGED,
                outputs=[f"outputs/{stem}.txt"],
                solver_setup=None if index in without_snapshot else setup.model_dump(mode="json"),
            )
        )
    return workspace


def _post(workspace: CampaignWorkspace, **keywords: object) -> Path:
    write_campaign_products(workspace, matrix_stem=MATRIX, **keywords)
    return workspace.products_dir(MATRIX)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _manifest(out: Path) -> dict:
    return json.loads((out / "products.json").read_text(encoding="utf-8"))


def _tree(out: Path) -> dict[str, bytes]:
    return {
        path.relative_to(out).as_posix(): path.read_bytes()
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.name not in ("post.log", "post.log.json", "products.json")
    }


def test_the_table_has_one_row_per_point_read_from_its_record(tmp_path):
    """P0370-S7-CODEBOOK (FR-419): one numeric row per point, its velocity the record's own."""
    out = _post(_workspace(tmp_path, key="settings_codebook = true\n"))
    rows = _rows(out / TABLE)
    assert len(rows) == len(SPEEDS)
    assert [float(row[f"f{VELOCITY}_value"]) for row in rows] == list(SPEEDS)
    assert [int(row["run_index"]) for row in rows] == [0, 1, 2]
    assert {row["codebook_version"] for row in rows} == {str(CODEBOOK_VERSION)}
    assert [row["POL"] for row in rows] == [SIM] * len(SPEEDS)
    assert [row["RUN_ID"] for row in rows] == [
        f"camp/sim_{SIM}/{_name(index)}" for index in range(len(SPEEDS))
    ]
    for row in rows:
        for name, cell in row.items():
            if name not in ("POL", "RUN_ID") and cell != "NA":  # NA: no value exists
                float(cell)  # every other cell is a code or a number


def test_the_legend_is_the_library_codebook_and_the_table_opens_with_its_key(tmp_path):
    """P0370-S7-CODEBOOK (FR-419): the legend carries its version; the table opens POL, RUN_ID."""
    out = _post(_workspace(tmp_path, key="settings_codebook = true\n"))
    legend = json.loads((out / LEGEND).read_text(encoding="utf-8"))
    assert legend["codebook_version"] == CODEBOOK_VERSION
    assert legend == json.loads(json.dumps(codebook()))
    with (out / TABLE).open(encoding="utf-8", newline="") as stream:
        header = next(csv.reader(stream))
    assert header[:3] == ["POL", "RUN_ID", "codebook_version"]


def test_both_files_are_in_the_manifest_with_the_runs_they_derive_from(tmp_path):
    """P0370-S7-CODEBOOK (FR-419): products.json lists the pair with kind settings_codebook."""
    out = _post(_workspace(tmp_path, key="settings_codebook = true\n"))
    products = _manifest(out)["products"]
    expected = [f"camp/sim_{SIM}/{_name(index)}" for index in range(len(SPEEDS))]
    for name in (TABLE, LEGEND):
        assert (out / name).is_file()
        assert products[name]["kind"] == "settings_codebook"
        assert products[name]["runs"] == expected


def test_the_key_absent_is_on_and_false_changes_no_byte_of_0_36_0(tmp_path):
    """P0370-S7-CODEBOOK (FR-419 R3): absent equals true; false differs from them by the pair."""
    absent = _post(_workspace(tmp_path / "a"))
    true = _post(_workspace(tmp_path / "b", key="settings_codebook = true\n"))
    false = _post(_workspace(tmp_path / "c", key="settings_codebook = false\n"))
    assert not (false / "settings").exists()
    assert not any(name.startswith("settings/") for name in _manifest(false)["products"])
    assert not any(name.startswith("settings/") for name in _manifest(false)["skipped"])
    assert _tree(absent) == _tree(true)
    assert {TABLE, LEGEND} <= set(_tree(absent))
    assert {
        name: data for name, data in _tree(absent).items() if name not in (TABLE, LEGEND)
    } == _tree(false)
    assert set(_manifest(absent)["products"]) - set(_manifest(false)["products"]) == {TABLE, LEGEND}


def test_a_point_without_a_snapshot_is_named_and_gets_no_row(tmp_path):
    """P0370-S7-CODEBOOK (FR-419 R1): skipped in the manifest and post.log, never a blank row."""
    out = _post(_workspace(tmp_path, key="settings_codebook = true\n", without_snapshot=(1,)))
    missing = f"camp/sim_{SIM}/{_name(1)}"
    rows = _rows(out / TABLE)
    assert [float(row[f"f{VELOCITY}_value"]) for row in rows] == [SPEEDS[0], SPEEDS[2]]
    skipped = _manifest(out)["skipped"]
    assert [name for name in skipped if name.startswith(TABLE)] == [f"{TABLE}#{missing}"]
    assert "no solver-setup snapshot" in skipped[f"{TABLE}#{missing}"]
    log = (out / "post.log").read_text(encoding="utf-8")
    assert missing in log and "settings table" in log
    assert [row["RUN_ID"] for row in rows] == [
        f"camp/sim_{SIM}/{_name(0)}",
        f"camp/sim_{SIM}/{_name(2)}",
    ]
    assert all(cell != "" for row in rows for cell in row.values())


def test_a_rebuild_replaces_the_pair_and_a_key_withdrawn_retires_it(tmp_path):
    """P0370-S7-CODEBOOK (FR-419 R2): a second post replaces the files; key off retires them."""
    workspace = _workspace(tmp_path)
    out = _post(workspace)
    first = (out / TABLE).read_bytes()
    _post(workspace, overwrite=True)
    assert (out / TABLE).read_bytes() == first
    assert set(_manifest(out)["products"]) >= {TABLE, LEGEND}
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "Wing"\n\n[products]\nsettings_codebook = false\n', encoding="utf-8"
    )
    _post(workspace, overwrite=True)
    assert not (out / TABLE).exists() and not (out / LEGEND).exists()
    manifest = _manifest(out)
    assert TABLE not in manifest["products"] and LEGEND not in manifest["products"]
    assert "retired previous product" in manifest["skipped"][TABLE]


def test_the_library_writer_keeps_both_forms_and_keys_only_the_wide_one(tmp_path):
    """P0370-S7-CODEBOOK (FR-419): keys lead a wide table and read back as text; long refuses."""
    from pyflightstream.post.settings_table import read_settings_table, write_settings_table
    from pyflightstream.results import MalformedOutputError

    setups = [helpers.solver_settings(Script(version="26.120"), velocity=v) for v in SPEEDS]
    keys = [{"POL": "7", "RUN_ID": f"r{index}"} for index in range(len(SPEEDS))]
    table, legend = write_settings_table(tmp_path / "w.csv", setups, wide=True, keys=keys)
    assert legend.name == "w.csv.codebook.json"
    rows = read_settings_table(table)
    assert [(row["POL"], row["RUN_ID"]) for row in rows] == [("7", f"r{i}") for i in range(3)]
    assert [row[f"f{VELOCITY}_value"] for row in rows] == list(SPEEDS)
    long_table, _ = write_settings_table(tmp_path / "t.csv", setups)
    assert "POL" not in long_table.read_text(encoding="utf-8").splitlines()[0]
    with pytest.raises(MalformedOutputError, match="wide"):
        write_settings_table(tmp_path / "x.csv", setups, keys=keys)
    with pytest.raises(MalformedOutputError, match="one mapping per run"):
        write_settings_table(tmp_path / "y.csv", setups, wide=True, keys=keys[:2])
