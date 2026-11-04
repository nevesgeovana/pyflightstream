"""PFS-2010.01.06: the HPC profile names a build the way its scheduler does.

THE THREE SPELLINGS. A row's `FS_BUILD` is a canonical build, `26.123`; the
scheduler accepts an application family, `26.1`; and this package refuses
`26.1` because it names more than one build. So neither vocabulary can carry
the other, the matrix cell cannot hold the scheduler's word, and the
descriptor cannot hold `{fs_build}`. The `[builds]` table in the profile
translates, keyed by build because the relation is many-to-one.

THE FIXTURE PROFILE IS THE DOCUMENTED ONE, read out of
`docs/workspace-and-workflows.md`, so the page a user copies from and the
feature under test cannot drift apart.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyflightstream.exceptions import InputArtifactError
from pyflightstream.run import SubmittingExecutor
from pyflightstream.run._executors import _unmapped_build_refusal
from pyflightstream.workspace.inputs import read_hpc_profile
from tests.tier1_offline._workflow_docs import WORKFLOW_DOCS

REPO = Path(__file__).resolve().parents[2]
DOC = WORKFLOW_DOCS


def documented_profile() -> str:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## Naming the build to a cluster's scheduler", 1)
    assert len(section) == 2, "the docs no longer carry the section that documents [builds]"
    match = re.search(r"```toml\n(.*?)```", section[1], re.S)
    assert match, "the section carries no toml example"
    return match.group(1)


def _profile(tmp_path, text: str | None = None):
    path = tmp_path / "h001.toml"
    path.write_text(documented_profile() if text is None else text, encoding="utf-8")
    return read_hpc_profile(path)


def _render(tmp_path, profile, build="26.123"):
    executor = SubmittingExecutor(profile, values={"fs_build": build}, submit=False)
    script = tmp_path / "point.txt"
    script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
    executor.run_script(script, working_dir=tmp_path / "work")
    return executor.descriptor_path.read_text(encoding="utf-8")


def test_goal021_build_alias_the_documented_table_is_a_declaration_and_says_so():
    text = documented_profile()
    assert "[builds]" in text
    comments = " ".join(line for line in text.splitlines() if line.lstrip().startswith("#"))
    assert comments.count("DECLARATION") == 1, comments
    assert "not a verification" in comments, comments
    assert "suse15" not in text, "the module path prefix is the scheduler's business"
    assert 'application_id = "flightstream"' in text


def test_goal021_build_alias_a_mapped_build_renders_the_schedulers_word(tmp_path):
    descriptor = _render(tmp_path, _profile(tmp_path))
    versions = [line for line in descriptor.splitlines() if line.startswith("version:")]
    assert versions == ['version: "26.1"'], descriptor
    assert "26.123" not in descriptor, (
        "the descriptor carries the build where the scheduler expects its family name"
    )


def test_goal021_build_alias_an_unmapped_build_is_refused_by_name(tmp_path):
    # The refusal is this point's failed result, not an exception (PFS-2094.037).
    profile = _profile(tmp_path)
    executor = SubmittingExecutor(profile, values={"fs_build": "26.120"}, submit=False)
    script = tmp_path / "point.txt"
    script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
    result = executor.run_script(script, working_dir=tmp_path / "work")
    assert result.return_code == 2 and executor.descriptor_path is None
    message = result.stderr
    assert message.startswith("nothing was submitted: "), message
    assert message.count("maps no alias for build(s) 26.120") == 1, message
    assert message.count("[builds]") == 2, message
    assert "26.123 -> 26.1" in message, "the refusal does not say what the table DOES map"
    assert not (tmp_path / "work" / profile.descriptor_name).exists(), (
        "a descriptor was written for a build the scheduler cannot be told"
    )


def _two_build_cluster(tmp_path, monkeypatch, profile_text):
    """A two-row matrix on a patched cluster: row one names 26.123, row two 26.120.

    THE MAPPED ROW COMES FIRST, so a refusal that arrived at the second row's
    descriptor, after the first row had been submitted, would leave the first
    row's descriptor and record behind. That is the ordering the refusal
    exists to prevent, and a one-row matrix cannot show it.
    """
    from pyflightstream.run import matrix as matrix_module
    from tests.tier1_offline.test_matrix_run import _steady_sweep_matrix, register

    workspace, matrix = _steady_sweep_matrix(tmp_path)
    register(workspace, "26.123", "C:/fs26123/FlightStream.exe")
    header, rule, row = matrix.read_text(encoding="utf-8").splitlines()
    first = row.replace("5001 ", "5002 ", 1).replace("26.120", "26.123")
    assert first.count("26.123") == 1 and first.startswith("5002"), first
    matrix.write_text("\n".join((header, rule, first, row)) + "\n", encoding="utf-8")
    (workspace.inputs_dir / "hpc").mkdir(parents=True, exist_ok=True)
    (workspace.inputs_dir / "hpc" / "h001.toml").write_text(profile_text, encoding="utf-8")
    monkeypatch.setattr(matrix_module, "on_a_cluster", lambda: True)
    return workspace, matrix


def _run_on_the_cluster(workspace, matrix):
    import warnings

    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run.matrix import run_matrix
    from tests.tier1_offline.test_matrix_run import RECIPES, converged

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run_matrix(
            matrix,
            workspace,
            name="cluster",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=converged,
        )


def _descriptors(workspace):
    sims = workspace.root / "sims"
    return sorted(sims.rglob("submit.yaml")) if sims.is_dir() else []


def test_goal021_build_alias_the_matrix_path_refuses_before_any_point_is_submitted(
    tmp_path, monkeypatch
):
    workspace, matrix = _two_build_cluster(tmp_path, monkeypatch, documented_profile())
    with pytest.raises(InputArtifactError, match=r"maps no alias for build\(s\) 26\.120"):
        _run_on_the_cluster(workspace, matrix)
    assert _descriptors(workspace) == [], "a descriptor was written before the refusal"
    assert workspace.read_manifest() == [], "a point was recorded before the refusal"


def test_goal021_build_alias_the_same_matrix_submits_both_rows_when_both_are_mapped(
    tmp_path, monkeypatch
):
    """The control: with 26.120 mapped too, run_matrix reaches both descriptors.

    Without it the refusal test above would pass on a run_matrix that never
    reached the cluster branch at all, because an unreached branch also
    writes no descriptor.
    """
    profile = documented_profile().replace(
        '"26.123" = "26.1"', '"26.123" = "26.1"\n"26.120" = "26.1"'
    )
    import pyflightstream.run._executors as executors_module
    from pyflightstream.run import CampaignErrors

    workspace, matrix = _two_build_cluster(tmp_path, monkeypatch, profile)
    # THE SCHEDULER IS STUBBED AT THE SUBPROCESS BOUNDARY (the opening round of
    # 0.27.0). This test used to rely on the scheduler NOT being installed, so on
    # a machine that has it a tier-1 test would have submitted real jobs. The
    # stub answers the way a missing client does, so each submission is
    # rejected and the campaign raises after recording both; the descriptor is
    # written BEFORE the scheduler is called, which is what this control measures.
    submitted = []
    real_run = executors_module.subprocess.run

    def no_scheduler(argv, **kwargs):
        if not (isinstance(argv, list) and argv and argv[0] == "esub"):
            return real_run(argv, **kwargs)
        submitted.append(list(argv))
        raise OSError("no scheduler in a tier-1 test")

    monkeypatch.setattr(executors_module.subprocess, "run", no_scheduler)
    with pytest.raises(CampaignErrors):
        _run_on_the_cluster(workspace, matrix)
    assert len(workspace.read_manifest()) == 2, workspace.read_manifest()
    descriptors = _descriptors(workspace)
    assert len(descriptors) == 2, descriptors
    for descriptor in descriptors:
        text = descriptor.read_text(encoding="utf-8")
        assert text.count('version: "26.1"') == 1, text
    assert len(submitted) == 2, submitted
    assert all(
        any(descriptor.as_posix() in part for part in argv for descriptor in descriptors)
        for argv in submitted
    ), submitted


@pytest.mark.parametrize(
    ("line", "clause"),
    [
        ('"26.1" = "26.1"', "must name ONE registered build"),
        ('"26.123" = ""', "cannot be empty"),
        ('"99.999" = "99"', "must name ONE registered build"),
    ],
)
def test_goal021_build_alias_a_key_that_is_not_one_build_is_refused_when_read(
    tmp_path, line, clause
):
    text = documented_profile().replace('"26.123" = "26.1"', line)
    assert line in text
    with pytest.raises(InputArtifactError) as raised:
        _profile(tmp_path, text)
    assert str(raised.value).count(clause) == 1, str(raised.value)


def test_goal021_build_alias_a_profile_that_never_writes_it_is_untouched(tmp_path):
    """Every profile written before the table existed renders exactly as before."""
    text = documented_profile().replace('"{fs_build_alias}"', '"{fs_build}"')
    text = text.split("[builds]", 1)[0]
    profile = _profile(tmp_path, text)
    assert profile.builds == {}
    assert _unmapped_build_refusal(profile, ["26.120", "26.123"]) is None
    assert 'version: "26.123"' in _render(tmp_path, profile)


def test_goal021_build_alias_a_callers_own_submitting_executor_is_refused_up_front(
    tmp_path, monkeypatch
):
    """The independent review: a passed executor skipped the campaign-wide refusal."""
    from pyflightstream.workspace.inputs import read_hpc_profile

    workspace, matrix = _two_build_cluster(tmp_path, monkeypatch, documented_profile())
    executor = SubmittingExecutor(
        read_hpc_profile(workspace.inputs_dir / "hpc" / "h001.toml"),
        values={"fs_build": "26.120"},
        submit=False,
    )
    import warnings

    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run.matrix import run_matrix
    from tests.tier1_offline.test_matrix_run import RECIPES, converged

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(InputArtifactError, match=r"maps no alias for build\(s\) 26\.120"):
            run_matrix(
                matrix,
                workspace,
                name="cluster",
                default_fs_version="26.120",
                recipes=RECIPES,
                recipe_registry=workflow_registry(),
                assess=converged,
                executor=executor,
            )
    assert _descriptors(workspace) == [], "a descriptor was written before the refusal"
    assert workspace.read_manifest() == [], "a point was recorded before the refusal"


def test_goal021_build_alias_a_later_row_naming_an_unmapped_build_is_refused_up_front(
    tmp_path, monkeypatch
):
    """The independent review, second pass: the preflight read only the campaign default.

    THE DEFAULT HERE IS THE MAPPED BUILD. The refusal tests above use a default
    that is itself unmapped, so they passed on a preflight that never read a
    row's own FS_BUILD; this one maps the default, names the unmapped build only
    in the second row's cell, and still expects nothing submitted.
    """
    import warnings

    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run.matrix import run_matrix
    from tests.tier1_offline.test_matrix_run import RECIPES, converged

    workspace, matrix = _two_build_cluster(tmp_path, monkeypatch, documented_profile())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(InputArtifactError, match=r"maps no alias for build\(s\) 26\.120"):
            run_matrix(
                matrix,
                workspace,
                name="cluster",
                default_fs_version="26.123",
                recipes=RECIPES,
                recipe_registry=workflow_registry(),
                assess=converged,
            )
    assert _descriptors(workspace) == [], "a descriptor was written before the refusal"
    assert workspace.read_manifest() == [], "a point was recorded before the refusal"


def test_f6_0102_a_relative_steady_coupled_script_is_read_from_the_working_directory(tmp_path):
    """F-832: the steady coupled refusal reads the script where the job will, not the cwd."""
    from pyflightstream.exceptions import CampaignConfigError

    profile = _profile(tmp_path)
    executor = SubmittingExecutor(profile, values={"fs_build": "26.123"}, submit=False)
    work = tmp_path / "work"
    work.mkdir()
    (work / "point.txt").write_text("EXECUTE_AEROELASTIC_ANALYSIS\n", encoding="utf-8")
    with pytest.raises(CampaignConfigError, match="steady coupled run"):
        executor._prepared(Path("point.txt"), work)


def _with_application_ids(lines: str) -> str:
    """The documented profile, three builds mapped, its [application_ids] replaced by ``lines``."""
    text = documented_profile().replace(
        '"26.123" = "26.1"', '"26.123" = "26.1"\n"26.124" = "26.1"\n"26.127" = "26.1"'
    )
    head, _ = text.split("[application_ids]", 1)
    return head + "[application_ids]\n" + lines + "\n"


def _application_ids_written(descriptor: str) -> list[str]:
    return [line for line in descriptor.splitlines() if line.startswith("ApplicationId:")]


def test_application_ids_a_build_with_a_line_writes_it_and_the_others_the_top_level(tmp_path):
    profile = _profile(tmp_path, _with_application_ids('"26.127" = "Flightstream"'))
    assert _application_ids_written(_render(tmp_path, profile, "26.127")) == [
        'ApplicationId: "Flightstream"'
    ]
    assert _application_ids_written(_render(tmp_path, profile, "26.124")) == [
        'ApplicationId: "flightstream"'
    ]


def test_application_ids_no_table_keeps_the_old_bytes(tmp_path):
    with_table = _profile(tmp_path, _with_application_ids('"26.127" = "Flightstream"'))
    without = _profile(tmp_path, _with_application_ids("").split("[application_ids]")[0])
    assert without.application_ids == {}
    assert _render(tmp_path, without, "26.127") == _render(tmp_path, with_table, "26.124")


@pytest.mark.parametrize(
    ("lines", "clause"),
    [
        ('"26.1" = "Flightstream"', "must name ONE registered build"),
        ('"26.127" = ""', "cannot be empty"),
        ('"99.999" = "x"', "must name ONE registered build"),
    ],
)
def test_application_ids_a_bad_key_or_value_is_refused_when_read(tmp_path, lines, clause):
    with pytest.raises(InputArtifactError) as raised:
        _profile(tmp_path, _with_application_ids(lines))
    message = str(raised.value)
    assert message.count(clause) == 1 and "[application_ids]" in message, message


def test_application_ids_a_non_table_is_refused_when_read(tmp_path):
    text = documented_profile().replace(
        'application_id = "flightstream"', 'application_id = "flightstream"\napplication_ids = "x"'
    )
    text = text.split("[application_ids]")[0]
    with pytest.raises(InputArtifactError, match=r"application_ids entry that is not a table"):
        _profile(tmp_path, text)


def test_application_ids_the_matrix_path_writes_each_rows_own_name(tmp_path, monkeypatch):
    import pyflightstream.run._executors as executors_module
    from pyflightstream.run import CampaignErrors

    profile = documented_profile().replace(
        '"26.123" = "26.1"', '"26.123" = "26.1"\n"26.120" = "26.1"'
    )
    head = profile.split("[application_ids]")[0]
    profile = head + '[application_ids]\n"26.123" = "Flightstream"\n'
    workspace, matrix = _two_build_cluster(tmp_path, monkeypatch, profile)
    real_run = executors_module.subprocess.run

    def no_scheduler(argv, **kwargs):
        if not (isinstance(argv, list) and argv and argv[0] == "esub"):
            return real_run(argv, **kwargs)
        raise OSError("no scheduler in a tier-1 test")

    monkeypatch.setattr(executors_module.subprocess, "run", no_scheduler)
    with pytest.raises(CampaignErrors):
        _run_on_the_cluster(workspace, matrix)
    written = sorted(
        tuple(_application_ids_written(d.read_text(encoding="utf-8")))
        for d in _descriptors(workspace)
    )
    assert written == [
        ('ApplicationId: "Flightstream"',),
        ('ApplicationId: "flightstream"',),
    ], written


def test_application_ids_a_grouped_job_writes_and_records_its_builds_name(tmp_path):
    from tests.tier1_offline import test_p0350_batch_run as grouped

    workspace, profile, _ = grouped._workspace(tmp_path)
    profile.write_text(
        profile.read_text(encoding="utf-8")
        + f'\n[application_ids]\n"{grouped.BUILD}" = "Flightstream"\n',
        encoding="utf-8",
    )
    matrix = grouped._matrix(tmp_path)
    grouped._plan(workspace, matrix, mode="batch", batch=1)
    records = grouped._run(workspace, matrix, executor=grouped._submitting(profile))
    descriptor = workspace.root / "sims" / "batch" / f"{grouped.MATRIX}_b1" / "submit.yaml"
    assert _application_ids_written(descriptor.read_text(encoding="utf-8")) == [
        'ApplicationId: "Flightstream"'
    ]
    assert {r.submission["application_id"] for r in records} == {"Flightstream"}


def test_application_ids_a_points_record_carries_the_name_it_wrote(tmp_path):
    profile = _profile(tmp_path, _with_application_ids('"26.127" = "Flightstream"'))
    for build, name in (("26.127", "Flightstream"), ("26.124", "flightstream")):
        executor = SubmittingExecutor(profile, values={"fs_build": build}, submit=False)
        script = tmp_path / "point.txt"
        script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
        executor.run_script(script, working_dir=tmp_path / f"work_{build}")
        assert executor.submission_record()["application_id"] == name


def test_application_ids_the_example_says_its_build_also_needs_a_builds_line(tmp_path):
    """The example maps 26.124 for the application but 26.123 for the build alias."""
    text = DOC.read_text(encoding="utf-8")
    assert "also needs its own line under `[builds]`" in text
    profile = _profile(tmp_path)
    assert "26.124" in profile.application_ids and "26.124" not in profile.builds
    executor = SubmittingExecutor(profile, values={"fs_build": "26.124"}, submit=False)
    script = tmp_path / "point.txt"
    script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
    result = executor.run_script(script, working_dir=tmp_path / "work")
    assert result.return_code == 2 and "maps no alias for build(s) 26.124" in result.stderr
