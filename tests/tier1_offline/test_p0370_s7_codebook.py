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


def _info_lines(out: Path) -> list[str]:
    log = (out / "post.log").read_text(encoding="utf-8")
    return [line for line in log.splitlines() if line.startswith("INFO ") and "settings/" in line]


def test_a_point_without_a_snapshot_has_no_row_and_one_info_line_and_no_skip(tmp_path):
    """P0370-S7-CODEBOOK (FR-419 R1): INFO in post.log, never a blank row, never a skip."""
    out = _post(_workspace(tmp_path, without_snapshot=(1,)))
    missing = f"camp/sim_{SIM}/{_name(1)}"
    rows = _rows(out / TABLE)
    assert [float(row[f"f{VELOCITY}_value"]) for row in rows] == [SPEEDS[0], SPEEDS[2]]
    assert [row["RUN_ID"] for row in rows] == [
        f"camp/sim_{SIM}/{_name(0)}",
        f"camp/sim_{SIM}/{_name(2)}",
    ]
    assert all(cell != "" for row in rows for cell in row.values())
    assert not [name for name in _manifest(out)["skipped"] if name.startswith("settings/")]
    (line,) = _info_lines(out)
    assert missing in line and "no solver-setup snapshot" in line
    document = json.loads((out / "post.log.json").read_text(encoding="utf-8"))
    assert [r["severity"] for r in document["records"] if "settings/" in r["product"]] == ["info"]


def test_no_snapshot_anywhere_writes_neither_file_and_says_so_once(tmp_path):
    """P0370-S7-CODEBOOK (FR-419 R1): no table, one INFO line, no skip."""
    out = _post(_workspace(tmp_path, without_snapshot=(0, 1, 2)))
    assert not (out / "settings").exists()
    assert not any(name.startswith("settings/") for name in _manifest(out)["products"])
    assert not any(name.startswith("settings/") for name in _manifest(out)["skipped"])
    lines = [line for line in _info_lines(out) if "no point of the matrix" in line]
    assert len(lines) == 1, lines


def test_strict_counts_no_settings_skip_for_records_that_predate_the_snapshot(tmp_path, capsys):
    """P0370-S7-CODEBOOK (FR-419 R1): --strict sees the same skips with the product on and off."""
    from pyflightstream.run.cli import main

    verdicts = {}
    for name, key in (("on", ""), ("off", "settings_codebook = false\n")):
        workspace = _workspace(tmp_path / name, key=key, without_snapshot=(0, 1, 2))
        code = main(["post", "--workspace", str(workspace.root), "--strict"])
        err = capsys.readouterr().err
        skipped = set(_manifest(workspace.products_dir(MATRIX))["skipped"])
        verdicts[name] = (code, skipped)
        assert "settings/" not in err
    assert verdicts["on"] == verdicts["off"]
