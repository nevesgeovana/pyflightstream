"""Tier 1, 0.32.0 package B3: the post and the collect of another manifest, and the post from sims.

Three requirements, each driven through the REAL command line over a REAL
workspace on disk, the one the super file tests already build (a steady alpha
sweep of two points and an unsteady rotor row, recorded as a run leaves it):

* P0320-RUNS-NAME: ``pyfs-matrix post --runs NAME`` and ``collect --runs NAME``
  read and complete the records of another manifest, and runs.json is never
  touched;
* P0320-POST-RUNS-APART: the products of such a post go to their own folder,
  ``post/<matrix>@<name stem>/``, and every byte the default post wrote, its
  reports included, is left as it was, so the two posts can be compared;
* P0320-POST-NO-MANIFEST: ``pyfs-matrix post MATRIX --from-sims`` assembles the
  records in memory from the simulation folders and posts them to
  ``post/<matrix>@sims/``; what a record would carry and cannot be recovered
  (the averaging window, the steps per revolution, the aliases and reference,
  the flight condition) is REFUSED by name, never guessed.

Every fixture is synthetic.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pyflightstream.run import cli, records
from pyflightstream.run.collect import collect_once
from pyflightstream.workspace import CampaignWorkspace, WorkspaceError
from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace
from tests.tier1_offline.test_post_superfile import _workspace

REFERENCE = "area_m2 = 50.0\nchord_m = 2.526\nspan_m = 20.0\n"
SETUP = "[flight_condition]\nTK = 288.15\nPPA = 101325.0\n"


def _tree(folder: Path) -> dict[str, bytes]:
    """Every file under ``folder``, by its relative path, with its bytes."""
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _recorded(tmp_path: Path) -> CampaignWorkspace:
    """The recorded campaign, posted once by the default post."""
    workspace = _workspace(tmp_path)
    assert cli.main(["post", "matriz", "--workspace", str(workspace.root)]) == 0
    return workspace


def _without_one_point(workspace: CampaignWorkspace, name: str) -> str:
    """Write ``name`` beside runs.json holding every record but the alpha 0 point."""
    raw = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    kept = [row for row in raw if not str(row["run_id"]).endswith("AL+000BE+000")]
    assert len(kept) == len(raw) - 1
    (workspace.root / name).write_text(json.dumps(kept, indent=1), encoding="utf-8")
    return name


# ------------------------------------------------ post --runs NAME, products apart


def test_p0320_runs_name_post_reads_another_manifest_into_its_own_folder(tmp_path):
    """P0320-RUNS-NAME and P0320-POST-RUNS-APART, through the command line.

    The named manifest holds one point fewer than runs.json, so a post that
    read runs.json by mistake would write a two-row polar and be told apart.
    """
    workspace = _recorded(tmp_path)
    root = workspace.root
    default = _tree(root / "post" / "matriz")
    reports = _tree(root / "reports")
    runs_json = workspace.manifest_path.read_bytes()
    name = _without_one_point(workspace, "runs-rebuilt.json")

    assert cli.main(["post", "matriz", "--workspace", str(root), "--runs", name]) == 0

    apart = root / "post" / "matriz@runs-rebuilt"
    manifest = json.loads((apart / "products.json").read_text(encoding="utf-8"))
    assert manifest["complete"] is True
    # Group "2" is the wing. The named manifest holds one point of the sweep, so
    # its table is named for that point; the default one is the two-point sweep.
    (polar,) = apart.glob("polars/P6001-*_g02.csv")
    assert len(_rows(polar)) == 1, "the post read runs.json, not the named manifest"
    assert "AL-020" in polar.name
    (sweep,) = (root / "post" / "matriz").glob("polars/P6001-*_g02.csv")
    assert len(_rows(sweep)) == 2
    # THE DEFAULT POST IS LEFT AS IT WAS, byte for byte, its reports included:
    # the measurement files of the apart post sit inside its own folder.
    assert _tree(root / "post" / "matriz") == default
    assert _tree(root / "reports") == reports
    assert (apart / "reports").is_dir()
    assert workspace.manifest_path.read_bytes() == runs_json
    assert manifest["superfile_report"].startswith("post/matriz@runs-rebuilt/reports/")


def test_p0320_post_runs_apart_twice_archives_inside_its_own_folder(tmp_path):
    """P0320-POST-RUNS-APART: a second apart post archives its own products only."""
    workspace = _recorded(tmp_path)
    root = workspace.root
    default = _tree(root / "post" / "matriz")
    name = _without_one_point(workspace, "runs-b.json")
    for _ in range(2):
        assert cli.main(["post", "matriz", "--workspace", str(root), "--runs", name]) == 0
    assert list((root / "post" / "matriz@runs-b" / "archive").iterdir())
    assert _tree(root / "post" / "matriz") == default


def test_p0320_runs_name_resolves_the_workspace_of_a_manifest(tmp_path):
    """P0320-RUNS-NAME at the library: which manifest, which products folder."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    root = workspace.root
    (root / "runs-hpc.json").write_text("[]", encoding="utf-8")

    plain = records.manifest_workspace(root)
    assert plain.manifest_path == root / "runs.json"
    assert plain.products_dir("m") == root / "post" / "m"
    assert records.manifest_workspace(root, "runs.json").products_dir("m") == root / "post" / "m"

    named = records.manifest_workspace(root, "runs-hpc.json")
    assert named.manifest_path == root / "runs-hpc.json"
    assert named.products_dir("m") == root / "post" / "m@runs-hpc"
    assert named.products_dir(None) == root / "post" / "products@runs-hpc"
    assert named.reports_root("m") == root / "post" / "m@runs-hpc"


def test_p0320_runs_name_refuses_a_manifest_that_is_not_there(tmp_path, capsys):
    """P0320-RUNS-NAME: a named manifest that does not exist is refused by its name."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    with pytest.raises(records.RunsManifestError, match="runs-missing.json"):
        records.manifest_workspace(workspace.root, "runs-missing.json")
    for command in (["post"], ["collect"]):
        argv = [*command, "--workspace", str(workspace.root), "--runs", "runs-missing.json"]
        assert cli.main(argv) == 2
        assert "runs-missing.json" in capsys.readouterr().err


def test_p0320_runs_name_refuses_the_name_of_the_from_sims_folder(tmp_path):
    """P0320-POST-RUNS-APART: ``--runs sims.json`` is refused, its folder is --from-sims's."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.root / "sims.json").write_text("[]", encoding="utf-8")
    with pytest.raises(records.RunsManifestError, match="--from-sims"):
        records.manifest_workspace(workspace.root, "sims.json")


# ------------------------------------------------------- collect --runs NAME


def test_p0320_runs_name_collect_completes_the_named_manifest(tmp_path):
    """P0320-RUNS-NAME: collect completes a SUBMITTED record of the named manifest only."""
    workspace, sim = _submitted_workspace(tmp_path)
    root = workspace.root
    workspace.manifest_path.replace(root / "runs-hpc.json")
    (root / "runs.json").write_text("[]\n", encoding="utf-8")
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    (sim / "run_log.txt").write_text("log", encoding="utf-8")

    argv = ["collect", "--workspace", str(root), "--runs", "runs-hpc.json", "--interval", "0"]
    cli.main(argv)

    raw = json.loads((root / "runs-hpc.json").read_text(encoding="utf-8"))
    assert raw[0]["status"] != "SUBMITTED"
    assert raw[0]["outputs"]
    assert (root / "runs.json").read_text(encoding="utf-8") == "[]\n"


def test_p0320_runs_name_collect_once_writes_only_the_named_manifest(tmp_path):
    """P0320-RUNS-NAME at the library: the lock and the rewrite follow the named manifest."""
    workspace, sim = _submitted_workspace(tmp_path)
    root = workspace.root
    workspace.manifest_path.replace(root / "runs-hpc.json")
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    (sim / "run_log.txt").write_text("log", encoding="utf-8")
    named = records.manifest_workspace(root, "runs-hpc.json")
    report = collect_once(named, interval=0.0, sleep=_no_sleep)
    assert len(report.collected) == 1
    assert not (root / "runs.json").exists()
    assert not list(root.glob("runs-hpc.json.lock"))
    # THE LEASE WAS THE NAMED MANIFEST'S: its persistent guard is what a lease
    # leaves behind, and a lease of runs.json would have left none for it.
    assert (root / ".runs-hpc.json.lock.guard").is_file()


def test_p0320_post_and_collect_report_their_stage_progress(tmp_path, monkeypatch):
    """P0320-RUNS-NAME: post and collect each announce their stage to the progress interface."""
    import contextlib

    from pyflightstream import _progress

    seen: list[str] = []
    real = _progress.stage_progress

    @contextlib.contextmanager
    def spy(name, **totals):
        seen.append(name)
        with real(name, **totals) as progress:
            yield progress

    monkeypatch.setattr(cli, "stage_progress", spy)
    workspace = _recorded(tmp_path)
    assert "post" in seen
    seen.clear()
    workspace2, _ = _submitted_workspace(tmp_path / "other")
    cli.main(["collect", "--workspace", str(workspace2.root), "--interval", "0"])
    assert "collect" in seen
    assert workspace.root.is_dir()


# ------------------------------------------------------- post --from-sims


def _from_sims_workspace(tmp_path: Path, *, variables: str | None = None) -> CampaignWorkspace:
    """The same campaign with its inputs and NO runs.json: polars run outside the package."""
    workspace = _workspace(tmp_path)
    root = workspace.root
    workspace.manifest_path.unlink()
    for ref in ("r001", "r002"):
        (workspace.inputs_dir / "references" / f"{ref}.toml").write_text(REFERENCE, "utf-8")
    for setup in ("s001", "s002"):
        (workspace.inputs_dir / "setups" / f"{setup}.toml").write_text(SETUP, "utf-8")
    if variables is not None:
        matrix = root / "matriz.fs"
        text = matrix.read_text(encoding="utf-8")
        text = text.replace(
            "CLOCK_MOTION: PUSHER / MOTIONS: {MOVING_BC_ALIAS: PUSHER}",
            f"CLOCK_MOTION: PUSHER / MOTIONS: {{MOVING_BC_ALIAS: PUSHER}} / {variables}",
        )
        matrix.write_text(text, encoding="utf-8")
    return workspace


def _post_log(folder: Path) -> str:
    return (folder / "post.log").read_text(encoding="utf-8")


def test_p0320_post_no_manifest_assembles_the_records_from_the_sims(tmp_path, capsys):
    """P0320-POST-NO-MANIFEST: the steady polar is posted from its exports alone, apart."""
    workspace = _from_sims_workspace(tmp_path)
    root = workspace.root

    assert cli.main(["post", "matriz", "--workspace", str(root), "--from-sims"]) == 0

    apart = root / "post" / "matriz@sims"
    manifest = json.loads((apart / "products.json").read_text(encoding="utf-8"))
    (polar,) = apart.glob("polars/P6001-*_g02.csv")
    assert polar.name == "P6001-AL+sweep_g02.csv"
    rows = _rows(polar)
    assert sorted(float(row["ALPHA"]) for row in rows) == [-2.0, 0.0]
    assert all(abs(float(row["MACH"]) - 0.2) < 1e-9 for row in rows)
    # THE AIR IS THE PACKAGE'S OWN RESOLUTION OF THE ROW, never a blank.
    assert all(float(row["RHO"]) > 0.0 for row in rows)
    assert manifest["complete"] is True
    assert not (root / "runs.json").exists(), "the post from the sims wrote a manifest"
    assert not (root / "post" / "matriz").exists()
    assert "assembled from the simulation folder" in _post_log(apart)


def test_p0320_post_no_manifest_refuses_a_window_it_cannot_recover(tmp_path, capsys):
    """P0320-POST-NO-MANIFEST: an unsteady row stating no window is refused, not defaulted."""
    workspace = _from_sims_workspace(tmp_path)
    root = workspace.root

    assert cli.main(["post", "matriz", "--workspace", str(root), "--from-sims"]) == 0

    err = capsys.readouterr().err
    assert "refused" in err and "6002" in err and "averaging window" in err
    apart = root / "post" / "matriz@sims"
    assert "averaging window" in _post_log(apart)
    manifest = json.loads((apart / "products.json").read_text(encoding="utf-8"))
    assert not any(entry.get("sim_id") == "6002" for entry in manifest["products"].values())

    assembled, refusals = records.assemble_records(root, "matriz")
    assert {record.sim_id for record in assembled} == {"6001"}
    assert any("averaging window" in reason for reason in refusals.values())


def test_p0320_post_no_manifest_refuses_steps_per_revolution_it_cannot_recover(tmp_path):
    """P0320-POST-NO-MANIFEST: LAST_REVS_AVG with no stated clock is refused naming the flag."""
    workspace = _from_sims_workspace(tmp_path, variables="LAST_REVS_AVG: 1")
    assembled, refusals = records.assemble_records(workspace.root, "matriz")
    assert "6002" not in {record.sim_id for record in assembled}
    reason = next(reason for key, reason in refusals.items() if "6002" in key)
    assert "steps per revolution" in reason and "--steps-per-revolution" in reason

    assembled, refusals = records.assemble_records(
        workspace.root, "matriz", steps_per_revolution=2.0
    )
    (rotor,) = [record for record in assembled if record.sim_id == "6002"]
    assert rotor.reductions is not None
    assert rotor.reductions["steps_per_revolution"] == 2.0
    assert rotor.reductions["time_average"]["windows"] == [[1, 2]]
    assert not any("6002" in key for key in refusals)


def test_p0320_post_no_manifest_posts_a_window_the_row_states(tmp_path):
    """P0320-POST-NO-MANIFEST: an unsteady row stating LAST_ITERS_AVG is averaged over it."""
    workspace = _from_sims_workspace(tmp_path, variables="LAST_ITERS_AVG: 2")
    root = workspace.root
    assert cli.main(["post", "matriz", "--workspace", str(root), "--from-sims"]) == 0
    apart = root / "post" / "matriz@sims"
    manifest = json.loads((apart / "products.json").read_text(encoding="utf-8"))
    windowed = [
        entry
        for path, entry in manifest["products"].items()
        if entry.get("sim_id") == "6002" and path.endswith("_uns_avg.csv")
    ]
    assert windowed, sorted(manifest["products"])
    assert windowed[0]["window"]


def test_p0320_post_no_manifest_refuses_a_reference_that_does_not_resolve(tmp_path):
    """P0320-POST-NO-MANIFEST: with no reference, neither the aliases nor SREF are guessed."""
    workspace = _from_sims_workspace(tmp_path)
    (workspace.inputs_dir / "references" / "r001.toml").unlink()
    assembled, refusals = records.assemble_records(workspace.root, "matriz")
    assert "6001" not in {record.sim_id for record in assembled}
    reason = next(reason for key, reason in refusals.items() if "6001" in key)
    assert "aliases" in reason and "r001" in reason


def test_p0320_post_no_manifest_refuses_a_flight_condition_it_cannot_resolve(tmp_path):
    """P0320-POST-NO-MANIFEST: a condition the row and its setup cannot resolve is refused."""
    workspace = _from_sims_workspace(tmp_path)
    (workspace.inputs_dir / "setups" / "s001.toml").write_text(
        "[flight_condition]\nNOT_A_PIN = 1.0\n", encoding="utf-8"
    )
    assembled, refusals = records.assemble_records(workspace.root, "matriz")
    assert "6001" not in {record.sim_id for record in assembled}
    reason = next(reason for key, reason in refusals.items() if "6001" in key)
    assert "flight condition" in reason


def test_p0320_post_no_manifest_refuses_an_angle_outside_the_sweep(tmp_path):
    """P0320-POST-NO-MANIFEST: an export whose angle is no value of the row's sweep is refused."""
    workspace = _from_sims_workspace(tmp_path)
    outputs = workspace.sim_dir("6001") / "outputs"
    loads = outputs / "POLAR-6001_M20AL-020BE+000.txt"
    loads.write_text(
        loads.read_text(encoding="utf-8").replace("-2.000", "-3.000"), encoding="utf-8"
    )
    assembled, refusals = records.assemble_records(workspace.root, "matriz")
    assert len([record for record in assembled if record.sim_id == "6001"]) == 1
    assert any("-3" in reason and "sweep" in reason for reason in refusals.values())


def test_p0320_post_no_manifest_takes_a_points_exports_by_their_kinds_only(tmp_path):
    """P0320-POST-NO-MANIFEST: a point's exports are its stem plus an export kind's suffix.

    The surface export ``<stem>.dat`` is the point's own and must be taken; the
    log of another point whose stem merely begins with this one's must not.
    """
    workspace = _from_sims_workspace(tmp_path)
    outputs = workspace.sim_dir("6001") / "outputs"
    stem = "POLAR-6001_M20AL+000BE+000"
    (outputs / f"{stem}.dat").write_text("surface", encoding="utf-8")
    # The alpha -2 point, named so its stem begins with the alpha 0 point's.
    (outputs / "POLAR-6001_M20AL-020BE+000.txt").replace(outputs / f"{stem}_b.txt")
    (outputs / f"{stem}_b_log.txt").write_text("log", encoding="utf-8")

    assembled, _ = records.assemble_records(workspace.root, "matriz")
    (zero,) = [record for record in assembled if record.point.get("alpha") == 0.0]
    assert f"outputs/{stem}.dat" in zero.outputs, "the point's own surface export was dropped"
    assert f"outputs/{stem}_b_log.txt" not in zero.outputs, "another point's log was taken"


def test_p0320_post_no_manifest_refuses_a_post_that_assembled_nothing(tmp_path, capsys):
    """P0320-POST-NO-MANIFEST: every row refused is said as such, each refusal once.

    Not as a manifest that "records no run" with the advice to run a matrix:
    the points ran, and what refused each of them is the answer.
    """
    workspace = _from_sims_workspace(tmp_path)
    for ref in ("r001", "r002"):
        (workspace.inputs_dir / "references" / f"{ref}.toml").unlink()

    assert cli.main(["post", "matriz", "--workspace", str(workspace.root), "--from-sims"]) == 2

    err = capsys.readouterr().err
    assert "--from-sims assembled no record" in err
    assert "records no run" not in err and "run a matrix first" not in err
    assert err.count("names the reference 'r001'") == 1, err
    assert not (workspace.root / "post" / "matriz@sims").exists()


def test_p0320_post_no_manifest_refuses_two_exports_at_one_point(tmp_path):
    """P0320-POST-NO-MANIFEST: two exports at one point cost both, none is chosen."""
    workspace = _from_sims_workspace(tmp_path)
    outputs = workspace.sim_dir("6001") / "outputs"
    again = outputs / "again"
    again.mkdir()
    name = "POLAR-6001_M20AL+000BE+000.txt"
    (again / name).write_bytes((outputs / name).read_bytes())

    assembled, refusals = records.assemble_records(workspace.root, "matriz")
    steady = [record for record in assembled if record.sim_id == "6001"]
    assert [record.point["alpha"] for record in steady] == [-2.0]
    refused = [key for key, reason in refusals.items() if "none is chosen" in reason]
    assert set(refused) == {f"sims/sim_6001/outputs/again/{name}", f"sims/sim_6001/outputs/{name}"}


def test_p0320_post_no_manifest_refuses_a_row_sweeping_no_angle_over_two_values(tmp_path):
    """P0320-POST-NO-MANIFEST: a J sweep of two values cannot be told apart by the angles."""
    workspace = _from_sims_workspace(tmp_path, variables="LAST_ITERS_AVG: 2")
    matrix = workspace.root / "matriz.fs"
    text = matrix.read_text(encoding="utf-8")
    assert text.count("| 1.7 | 05_NX.fsm") == 1
    matrix.write_text(text.replace("| 1.7 | 05_NX.fsm", "| 1.7,2.0 | 05_NX.fsm"), "utf-8")

    assembled, refusals = records.assemble_records(workspace.root, "matriz")
    assert "6002" not in {record.sim_id for record in assembled}
    reason = next(reason for key, reason in refusals.items() if "6002" in key)
    assert "split the row" in reason


def test_p0320_post_no_manifest_status_is_the_collects_assessment(tmp_path):
    """P0320-POST-NO-MANIFEST: a steady point with no log export is not called converged."""
    workspace = _from_sims_workspace(tmp_path)
    assembled, _ = records.assemble_records(workspace.root, "matriz")
    steady = [record for record in assembled if record.sim_id == "6001"]
    assert {record.status.value for record in steady} == {"FAILED_INCOMPLETE_OUTPUT"}
    assert all(record.warnings == [records.ASSEMBLED_NOTE] for record in steady)


def test_p0320_runs_name_collect_posts_the_named_manifest_apart(tmp_path, monkeypatch):
    """P0320-POST-RUNS-APART: the post a collect of NAME runs lands in post/<matrix>@<stem>/."""
    from pyflightstream import workspace as workspace_module

    seen: list[Path] = []

    def spy(ws, *, matrix_stem=None, **_):
        seen.append(ws.products_dir(matrix_stem))
        return []

    monkeypatch.setattr(workspace_module, "post_stages", lambda: [spy])
    workspace, sim = _submitted_workspace(tmp_path)
    root = workspace.root
    workspace.manifest_path.replace(root / "runs-hpc.json")
    (sim / "loads.txt").write_text("numbers", encoding="utf-8")
    (sim / "run_log.txt").write_text("log", encoding="utf-8")

    cli.main(["collect", "--workspace", str(root), "--runs", "runs-hpc.json", "--interval", "0"])

    assert seen == [root / "post" / "matriz@runs-hpc"]


def test_p0320_post_no_manifest_never_writes_a_manifest(tmp_path):
    """P0320-POST-NO-MANIFEST: records assembled in memory refuse every manifest writer."""
    workspace = _from_sims_workspace(tmp_path)
    assembled = records.from_sims_workspace(workspace.root, "matriz")
    with pytest.raises(WorkspaceError, match="never written"):
        assembled.append_record((assembled.assembled or [])[0])
    assert not (workspace.root / "runs.json").exists()


@pytest.mark.parametrize(
    "extra, words",
    [
        ([], "names the matrix"),
        (["--runs", "runs.json"], "--runs"),
        (["--additional-pproc"], "--additional-pproc"),
    ],
)
def test_p0320_post_no_manifest_refuses_what_it_cannot_combine(tmp_path, capsys, extra, words):
    """P0320-POST-NO-MANIFEST: refused with no matrix, beside --runs, beside the additional post."""
    workspace = _from_sims_workspace(tmp_path)
    matrix = [] if not extra else ["matriz"]
    argv = ["post", *matrix, "--workspace", str(workspace.root), "--from-sims", *extra]
    assert cli.main(argv) == 2
    assert words in capsys.readouterr().err


def test_p0320_steps_per_revolution_is_refused_without_from_sims(tmp_path, capsys):
    """P0320-POST-NO-MANIFEST: the clock flag means nothing to a post that reads a manifest."""
    workspace = _recorded(tmp_path)
    argv = ["post", "matriz", "--workspace", str(workspace.root), "--steps-per-revolution", "2"]
    assert cli.main(argv) == 2
    assert "--from-sims" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Integration of B3 with B1 and B2 (merge of package b3 into feat/0-32).


def test_p0320_from_sims_reads_the_matrix_by_the_workspaces_two_homes_rule(tmp_path):
    """B3 x B2: ``--from-sims`` finds its matrix by B2's ONE two-homes rule.

    The same bytes in both homes are read once; different bytes are refused
    with B2's words, which name both paths, so post and sync cannot disagree
    on which matrix a stem means.
    """
    workspace = _from_sims_workspace(tmp_path)
    root = workspace.root
    home = root / "inputs" / "matrices"
    home.mkdir(parents=True, exist_ok=True)
    twin = home / "matriz.fs"
    twin.write_bytes((root / "matriz.fs").read_bytes())
    assembled, _ = records.assemble_records(root, "matriz")
    assert assembled, "the same matrix in both homes was not read"

    twin.write_bytes(twin.read_bytes() + b"\n# another revision\n")
    with pytest.raises(WorkspaceError, match="in both homes of the workspace") as refused:
        records.assemble_records(root, "matriz")
    assert str(twin) in str(refused.value)


def test_p0320_from_sims_leaves_the_rebuilds_row_inputs_in_place(tmp_path):
    """B3 x B1: the rebuild's ``_row_inputs(matrix, pol)`` is not shadowed by B3's helper.

    Both packages appended a private ``_row_inputs`` to run/records.py; a later
    definition would replace the rebuild's and break its drift report.
    """
    workspace = _from_sims_workspace(tmp_path)
    names = records._row_inputs(workspace.root / "matriz.fs", "6001")
    assert "references/r001.toml" in names
    assert any(name.startswith("setups/") for name in names)
