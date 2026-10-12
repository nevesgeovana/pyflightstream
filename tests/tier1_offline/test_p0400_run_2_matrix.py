"""Tier 1, 0.40.0 lane run-2: the matrix entry points (plan, run, additional post).

Every fixture is synthetic.
"""

from __future__ import annotations

from types import SimpleNamespace

from pyflightstream.run import matrix as run_matrix


def _resolved(builds: dict[str, str | None]):
    """A bound matrix of one row per build, each registered as a bare path or with a version."""
    sims = [SimpleNamespace(sim_id=f"700{index}") for index in range(1, len(builds) + 1)]
    return SimpleNamespace(
        campaign=SimpleNamespace(sims=sims),
        row_builds=list(builds),
        builds={build: SimpleNamespace(fs_version=version) for build, version in builds.items()},
    )


def test_p0400_preflight_versions_follow_the_run_s_fallback_chain():
    """P0400-ROW-VERSIONS (PFS-2094.018): the pre-flight version is the one the run emits under.

    With no default and two bare-path builds, the run emits each row under
    its build id (_bind_row_builds); the pre-flight gave such rows no version
    of their own, so they were pre-flighted under the first row's build.
    """
    resolved = _resolved({"26.120": None, "26.124": None})
    assert run_matrix._row_versions(resolved) == {"7001": "26.120", "7002": "26.124"}
    assert run_matrix._row_versions(resolved, "26.123") == {"7001": "26.123", "7002": "26.123"}
    declared = _resolved({"26.120": "26.120.1", "26.124": None})
    assert run_matrix._row_versions(declared) == {"7001": "26.120.1", "7002": "26.124"}


def test_p0400_a_local_extraction_with_a_translation_problem_fails_as_a_collected_one(
    tmp_path, monkeypatch
):
    """P0400-EXTRACTION-ONE-RULE (PFS-2103.008): the local path refuses a translation problem.

    The collected path fails an extraction whose stamped translation reports a
    problem; the local path judged by file existence alone and recorded it
    EXTRACTED, deleting the private copy first. Both now complete by one rule.
    """
    from pyflightstream.run import _additional
    from tests.tier1_offline.test_additional_post import (
        POST_ADDITIONAL_TOML,
        a_recorded_campaign,
        a_stub,
        extract,
    )

    def refused(folder, translations):
        for entry in translations:
            (folder / str(entry["dat"])).write_text("preserved surface export", "utf-8")
        return [
            {**entry, "written": [], "problems": ["the frame changed"]} for entry in translations
        ]

    workspace, matrix = a_recorded_campaign(tmp_path, additional=POST_ADDITIONAL_TOML)
    monkeypatch.setattr(_additional, "translate_surface_exports", refused)
    monkeypatch.setattr(run_matrix, "translate_surface_exports", refused, raising=False)
    _, records = extract(workspace, matrix, a_stub(tmp_path))
    assert records and {record.status for record in records} == {"FAILED_EXECUTION"}, [
        (record.status, record.error) for record in records
    ]
    assert all("the frame changed" in (record.error or "") for record in records)
    for record in records:
        folder = workspace.sim_dir(record.sim_id) / record.working_dir
        assert list(folder.glob("*.reopened.fsm")), "the private copy was deleted"
