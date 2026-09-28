"""Tier 1: a steady row run as ONE job records what its volume section's post needs.

Pipeline role: quality gate on FR-91 and FR-110 for the one-job steady path.

Measured on the licensed tier-3 run of 0.29.0 (row 5007 of
``tests/tier3_licensed/matriz_gui.fs``): a steady row of several points whose
pproc declares a ``[volume_section]`` runs as one job, ``.../sweep``, and the
post wrote no ``_vsec`` file for any point. Two fields the point path records
were missing from the job's record:

* ``probe_points_file``: the job never wrote where its script put its probe
  points, so the probe table read ``FRAME`` ``NA`` and the post refused every
  point's field as "probe table FRAME differs from its recorded sampling
  frame";
* ``fs_build`` and ``fs_version_reported``: the job never stamped the build its
  points read, so the post refused the native velocity convention, which is
  measured for one build only.

The existing post tests fill ``probe_points_file`` by hand, which is why the
path was never covered; here nothing is filled by hand except the digest of
the solver executable, which no stub can have: the stub solver is this
interpreter, and the convention is proved for the licensed executable alone.
"""

from __future__ import annotations

import csv
import json
import warnings
from pathlib import Path

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.post.products import write_campaign_products
from pyflightstream.run import Assessment, CampaignErrors
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from tests.tier1_offline.test_g06_actuator_disc import WING_PHY
from tests.tier1_offline.test_goal024_point_name import _matrix
from tests.tier1_offline.test_matrix_run import RECIPES, STUB_BODY, CountingStub, register

FIXTURES = Path(__file__).parent / "fixtures"

#: The build and version the velocity convention of a steady probe export is
#: measured for (post/field_frames.py), and the executable digest it names.
BUILD = "8172026"
VERSION = "26.124"
MEASURED_EXE_SHA256 = "68e64e666fad6e403a6c6747b20c263f5c9f3e4c7542eebe253397bedcc30c65"

PPROC = (
    '[groups]\n"1" = "all"\n\n'
    '[volume_section]\nshape = "rectangle"\nplane = "XZ"\n'
    "corners_m = [-1.0, -1.0, 1.0, 1.0]\npoints = [2, 2]\n"
)


def _probe_export_parts(tmp_path: Path) -> tuple[str, str]:
    """The solver's own probe export split around its rows, as two files.

    Returns the head (through the dashed line under the column header, with the
    count left as ``{count}``) and the tail (the closing dashed line and the
    footer, which names the build the convention is measured for).
    """
    lines = (FIXTURES / "probe_points_26.120.txt").read_text(encoding="utf-8").splitlines()
    header = next(i for i, line in enumerate(lines) if line.strip().startswith("X, Y, Z,"))
    closing = next(i for i in range(header + 2, len(lines)) if lines[i].strip().startswith("-----"))
    head = "\n".join(lines[: header + 2]).replace(
        "Number of Probe Points:                     12",
        "Number of Probe Points:                     {count}",
    )
    tail = "\n".join(lines[closing:]).replace("build #7012026", f"build #{BUILD}")
    head_path, tail_path = tmp_path / "probe_head.txt", tmp_path / "probe_tail.txt"
    head_path.write_text(head + "\n", encoding="utf-8")
    tail_path.write_text(tail + "\n", encoding="utf-8")
    return head_path.as_posix(), tail_path.as_posix()


def _stub(tmp_path: Path) -> CountingStub:
    """A solver that writes every export its script asks for.

    The probe export is written in the solver's format, one row per probe point
    the script created since its last ``DELETE_PROBE_POINTS``, at the position
    the script gave it; every other export gets the placeholder the other
    steady stubs write, except the loads spreadsheet, which is the solver's own
    recorded export, because the post reads each point's coefficients off it.
    """
    head, tail = _probe_export_parts(tmp_path)
    loads = (FIXTURES / "loads_steady_26.120.txt").as_posix()
    source = tmp_path / "stub_solver.py"
    source.write_text(
        "import pathlib, sys\n"
        "from pyflightstream.cases import EXPORT_KINDS\n"
        "verbs = {kind[2] for kind in EXPORT_KINDS}\n"
        f"head = pathlib.Path({head!r}).read_text()\n"
        f"tail = pathlib.Path({tail!r}).read_text()\n"
        "lines = pathlib.Path(sys.argv[1]).read_text().splitlines()\n"
        "points = []\n"
        "for i, line in enumerate(lines):\n"
        "    word = line.split(' ')[0]\n"
        "    if word == 'DELETE_PROBE_POINTS':\n"
        "        points = []\n"
        "    elif word == 'NEW_PROBE_POINT':\n"
        "        points.append([float(v) for v in line.split()[2:5]])\n"
        "    elif word == 'EXPORT_PROBE_POINTS' and i + 1 < len(lines):\n"
        "        rows = ''.join(\n"
        "            '     ' + ','.join(f'{v: .4E}' for v in (x, y, z, 0.09, 0.05, 29.0 + x,\n"
        "            0.5, 2.0 + z, 29.1, 0.05) + (0.0,) * 6) + ',\\n'\n"
        "            for x, y, z in points)\n"
        "        pathlib.Path(lines[i + 1]).write_text(\n"
        "            head.replace('{count}', str(len(points))) + rows + tail)\n"
        "    elif word == 'EXPORT_SOLVER_ANALYSIS_SPREADSHEET' and i + 1 < len(lines):\n"
        f"        pathlib.Path(lines[i + 1]).write_text(pathlib.Path({loads!r}).read_text())\n"
        "    elif word in verbs and i + 1 < len(lines):\n"
        f"        pathlib.Path(lines[i + 1]).write_text({STUB_BODY})\n",
        encoding="utf-8",
    )
    return CountingStub(f"import runpy; runpy.run_path({source.as_posix()!r})")


def _assessor(builds: dict[float, str]):
    """Converged points that read the build ``builds`` gives their incidence."""

    def assess(case, execution, sim_dir):
        return Assessment(
            status=RunStatus.CONVERGED,
            iterations=120,
            residual=3.2e-6,
            fs_build=builds[float(case.point["alpha"])],
            fs_version_reported=VERSION,
        )

    return assess


def _run(
    tmp_path: Path, builds: dict[float, str], *, before=None
) -> tuple[CampaignWorkspace, RunRecord, CountingStub]:
    """Run one steady row of two points, on 26.124, as the one job it is."""
    workspace, matrix = _matrix(
        tmp_path, condition="MACH:0.2, REmi:2.3, ALPHA:sweep", values="0.0,2.0"
    )
    register(workspace, VERSION, "C:/fs/FS124.exe")
    matrix.write_text(matrix.read_text(encoding="utf-8").replace("26.120", VERSION))
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(PPROC, encoding="utf-8")
    # A SAVED SIMULATION IN METRES, the committed tier-3 one, because the
    # convention is measured per length unit and a placeholder states none.
    (workspace.inputs_dir / "geometries" / "wing_clean.fsm").write_bytes(WING_PHY.read_bytes())
    if before is not None:
        before(workspace)
    stub = _stub(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        try:
            run_matrix(
                matrix,
                workspace,
                name="vsec",
                default_fs_version=VERSION,
                recipes=RECIPES,
                recipe_registry=workflow_registry(),
                assess=_assessor(builds),
                executor=stub,
            )
        except CampaignErrors:
            pass  # a failed job is still recorded, and the record is what is read
    (record,) = workspace.read_manifest()
    return workspace, record, stub


def test_a_steady_job_records_its_probe_points_and_the_build_that_ran(tmp_path):
    workspace, record, stub = _run(tmp_path, {0.0: BUILD, 2.0: BUILD})
    assert record.run_id.endswith("/sweep") and len(record.points_ran) == 2, (
        "the fixture took the point path; the one-job path is the one measured here"
    )
    assert len(stub.invocations) == 1, stub.invocations
    assert record.status is RunStatus.CONVERGED, record.error

    # FR-91: where the job's one script put its probe points, written and named.
    assert record.probe_points_file == "profiles/3207_probe_points.csv", (
        f"the job recorded probe_points_file={record.probe_points_file!r}; without it the "
        "probe table reads FRAME NA and the post refuses the volume section"
    )
    written = workspace.sim_dir("3207") / record.probe_points_file
    assert written.is_file(), written
    with written.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["FRAME"] for row in rows] == ["REFERENCE"] * 4, rows

    # The build and version every point read, on the job and on each point.
    assert (record.fs_build, record.fs_version_reported) == (BUILD, VERSION), (
        f"the job recorded fs_build={record.fs_build!r}, "
        f"fs_version_reported={record.fs_version_reported!r}"
    )
    for point in record.as_points():
        assert point.probe_points_file == record.probe_points_file, point.run_id
        assert (point.fs_build, point.fs_version_reported) == (BUILD, VERSION), point.run_id


def _rewrite_row(workspace: CampaignWorkspace, **fields: object) -> None:
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    rows = payload["runs"] if isinstance(payload, dict) else payload
    (row,) = rows
    row.update(fields)
    workspace.manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_the_post_writes_each_point_s_volume_section_from_the_job(tmp_path):
    """Row 5007 end to end: every point of the job gets its ``_vsec`` file."""
    workspace, record, _ = _run(tmp_path, {0.0: BUILD, 2.0: BUILD})
    # THE ONE FIELD A STUB CANNOT EARN: the digest of the licensed executable.
    # Every other field the post reads is the run's own.
    _rewrite_row(workspace, fs_exe_sha256=MEASURED_EXE_SHA256)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        write_campaign_products(workspace, matrix_stem=record.matrix_stem, overwrite=True)
    products = workspace.products_dir(record.matrix_stem)
    manifest = json.loads((products / "products.json").read_text(encoding="utf-8"))
    tags = [point.point_name for point in record.as_points()]
    assert len(tags) == 2, tags
    refused = {key: why for key, why in manifest["skipped"].items() if key.startswith("fields/")}
    assert not refused, f"the post refused the sampled field of the job's points: {refused}"
    # The probe table of each point places its samples in the frame they were
    # recorded in; FRAME NA is the refusal "differs from its recorded sampling frame".
    tables = sorted((products / "probes").glob("*_probes.csv"))
    assert [table.name for table in tables] == [f"P3207-{tag}_probes.csv" for tag in tags]
    for table in tables:
        with table.open(encoding="utf-8", newline="") as stream:
            frames = [row["FRAME"] for row in csv.DictReader(stream)]
        assert frames == ["REFERENCE"] * 4, (table.name, frames)
    fields = sorted(path.name for path in (products / "fields").glob("*_vsec.vtk"))
    assert fields == [f"P3207-{tag}_vsec.vtk" for tag in tags], (
        f"the post wrote {fields} for the points {tags}; skipped: {manifest['skipped']}"
    )


def test_points_that_read_different_builds_fail_the_job_naming_both(tmp_path):
    """One process ran every point; two builds read off it are not settled by a pick."""
    _, record, _ = _run(tmp_path, {0.0: BUILD, 2.0: "7012026"})
    assert record.status is RunStatus.FAILED_EXECUTION, (record.status, record.error)
    assert record.fs_build is None, record.fs_build
    assert "fs_build" in (record.error or ""), record.error
    assert BUILD in record.error and "7012026" in record.error, record.error
    # The version the points agree on is still recorded.
    assert record.fs_version_reported == VERSION


def test_a_user_file_where_the_probe_points_go_fails_the_job_before_the_solver(tmp_path):
    """The collision the point path records as its failure, on the job path too."""

    def user_file(workspace: CampaignWorkspace) -> None:
        target = workspace.sim_dir("3207") / "profiles" / "3207_probe_points.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("my,own,survey\n", encoding="utf-8")

    workspace, record, stub = _run(tmp_path, {0.0: BUILD, 2.0: BUILD}, before=user_file)
    assert record.status is RunStatus.FAILED_SCRIPT, (record.status, record.error)
    assert "is not a probe positions file" in (record.error or ""), record.error
    assert stub.invocations == [], "the solver started although the job was refused"
    target = workspace.sim_dir("3207") / "profiles" / "3207_probe_points.csv"
    assert target.read_text(encoding="utf-8") == "my,own,survey\n"
