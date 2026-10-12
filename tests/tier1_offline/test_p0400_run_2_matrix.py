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
