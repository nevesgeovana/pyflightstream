"""PFS-2220 G15: ``kernel_or_skip`` skips where the kernel cannot load, fails where required."""

from __future__ import annotations

import importlib.abc
import sys

import pytest

from tests.tier1_offline._kernel_support import REQUIRE_VARIABLE, kernel_or_skip


class _LibraryFails(importlib.abc.MetaPathFinder):
    """Make ``import gmsh`` raise OSError, as a missing shared library does."""

    def find_spec(self, name, path=None, target=None):
        if name == "gmsh":
            raise OSError("libGLU.so.1: cannot open shared object file")
        return None


@pytest.fixture
def library_fails(monkeypatch):
    monkeypatch.delitem(sys.modules, "gmsh", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_LibraryFails(), *sys.meta_path])


@pytest.fixture
def library_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "gmsh", None)


@pytest.mark.parametrize("broken", ["library_absent", "library_fails"])
def test_p0570_gm15_a_kernel_that_cannot_load_skips_by_default(broken, request, monkeypatch):
    request.getfixturevalue(broken)
    monkeypatch.delenv(REQUIRE_VARIABLE, raising=False)
    with pytest.raises(pytest.skip.Exception, match="cannot load"):
        kernel_or_skip()


@pytest.mark.parametrize("broken", ["library_absent", "library_fails"])
@pytest.mark.parametrize("value", ["1"])
def test_p0570_gm15_a_kernel_that_cannot_load_fails_when_required(
    broken, value, request, monkeypatch
):
    request.getfixturevalue(broken)
    monkeypatch.setenv(REQUIRE_VARIABLE, value)
    # BaseException: a skip raised in its place must read as a failure of this test, not a skip.
    with pytest.raises(BaseException, match="PYFS_REQUIRE_KERNEL=1 requires it") as raised:
        kernel_or_skip()
    assert isinstance(raised.value, pytest.fail.Exception), type(raised.value)


def test_p0570_gm15_a_value_other_than_one_does_not_require_the_kernel(library_absent, monkeypatch):
    monkeypatch.setenv(REQUIRE_VARIABLE, "0")
    with pytest.raises(pytest.skip.Exception):
        kernel_or_skip()


def test_p0570_gm15_a_loadable_kernel_is_returned():
    assert kernel_or_skip().__name__ == "gmsh"


# ---------------------------------------------------------------- the jobs that prove the kernel


def _workflow(name):
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]


def _steps(job):
    return job["steps"]


def _index(steps, fragment):
    found = [i for i, step in enumerate(steps) if fragment in step.get("name", "")]
    assert found, f"no step named like {fragment!r}"
    return found[0]


@pytest.mark.parametrize("job", ["test", "test-lean"])
def test_p0570_gm15_the_jobs_that_prove_the_kernel_require_it(job):
    steps = _steps(_workflow("ci.yml")[job])
    required = [s for s in steps if s.get("env", {}).get("PYFS_REQUIRE_KERNEL") == "1"]
    assert required, f"job {job} never sets PYFS_REQUIRE_KERNEL=1 on a pytest step"
    assert all("pytest" in s["run"] for s in required)


def test_p0570_gm15_no_install_line_names_the_retired_extra():
    for workflow in ("ci.yml", "release.yml"):
        for name, job in _workflow(workflow).items():
            for step in _steps(job):
                assert "gmsh]" not in step.get("run", "") and ",gmsh" not in step.get("run", ""), (
                    workflow,
                    name,
                )


def test_p0570_gm15_the_lean_probe_runs_before_the_system_libraries():
    steps = _steps(_workflow("ci.yml")["test-lean"])
    probe = _index(steps, "geometry path on a base install")
    libraries = _index(steps, "System libraries")
    tier1 = _index(steps, "Tier 1 with no user-facing extras")
    assert _index(steps, "Install the package") < probe < libraries < tier1
    text = steps[probe]["run"]
    assert "'gmsh' not in sys.modules" in text and "kernel.err" in text
    assert "Traceback" in text and "needs the CAD kernel library gmsh" in text


def test_p0570_gm15_the_wheel_job_installs_the_libraries_and_checks_the_wheel():
    steps = _steps(_workflow("release.yml")["test-artifact"])
    check = _index(steps, "names gmsh as a dependency")
    libraries = _index(steps, "System libraries")
    install = _index(steps, "Install the built wheel")
    assert check < install and libraries < install
    assert steps[libraries]["if"] == "runner.os == 'Linux'"
    assert "Requires-Dist: gmsh" in steps[check]["run"]
