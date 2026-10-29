"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import copy
import re
import subprocess
import tomllib
from importlib import metadata
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

REPO = Path(__file__).resolve().parents[2]


def _workflow_jobs():
    return yaml.safe_load((REPO / ".github/workflows/ci.yml").read_text())["jobs"]


def _user_ranges(project):
    return project["dependencies"] + [
        item
        for name, items in project["optional-dependencies"].items()
        if name not in {"dev", "manual"}
        for item in items
    ]


@pytest.mark.requirement("FR-3333")
def test_p0500_runtime_and_user_extras_declare_both_bounds():
    for text in _user_ranges(_pyproject()["project"]):
        requirement = Requirement(text)
        assert any(s.operator == ">=" for s in requirement.specifier), text
        assert any(s.operator == "<" for s in requirement.specifier), text


@pytest.mark.requirement("FR-3334")
@pytest.mark.requirement("FR-3335")
@pytest.mark.parametrize("endpoint", ["floors", "ceilings"])
def test_p0500_endpoint_resolver_reads_every_declared_range(endpoint, monkeypatch):
    job = _workflow_jobs().get(f"test-{endpoint}")
    assert job is not None, f"Missing test-{endpoint} job"
    steps = [s for s in job["steps"] if s.get("name") == "Install declared endpoint"]
    assert len(steps) == 1, "The endpoint must be resolved from package metadata"
    step = steps[0]
    assert step["env"]["DEPENDENCY_ENDPOINT"] == endpoint
    script = step["run"]
    assert script.startswith("python - <<'PY'\n")
    assert script.rstrip().endswith("\nPY")
    source = script.split("\n", 1)[1].rsplit("\nPY", 1)[0]
    data = copy.deepcopy(_pyproject())
    # A new dependency and a new user extra must reach pip without editing CI.
    data["project"]["dependencies"].append("future-runtime>=1.2,<2")
    data["project"]["optional-dependencies"]["future"] = ["future-extra>=4.5,<5"]
    calls = []
    monkeypatch.setattr(tomllib, "loads", lambda text: data)
    monkeypatch.setattr(subprocess, "check_call", lambda args: calls.append(args))
    monkeypatch.setattr(metadata, "version", lambda name: "1.0")
    monkeypatch.setenv("DEPENDENCY_ENDPOINT", endpoint)
    monkeypatch.chdir(REPO)
    exec(compile(source, "ci-endpoint", "exec"), {})
    assert len(calls) == 1
    args = calls[0]
    assert args[1:4] == ["-m", "pip", "install"]
    assert ".[dev]" in args
    expected = []
    for text in _user_ranges(data["project"]):
        req = Requirement(text)
        floor = next(s.version for s in req.specifier if s.operator == ">=")
        expected.append(f"{req.name}=={floor}" if endpoint == "floors" else text)
    assert args[args.index(".[dev]") + 1 :] == expected
    assert ("--upgrade" in args) == (endpoint == "ceilings")
    assert any(s.get("run") == "pytest -n auto tests/tier1_offline" for s in job["steps"])
    if endpoint == "ceilings":
        setup = next(s for s in job["steps"] if "setup-python@" in s.get("uses", ""))
        assert setup["with"] == {"python-version-file": "pyproject.toml"}


@pytest.mark.requirement("FR-3330")
def test_p0500_python_ceiling_follows_the_newest_ci_minor():
    spec = SpecifierSet(_pyproject()["project"]["requires-python"])
    bounds = [Version(s.version) for s in spec if s.operator == "<"]
    assert len(bounds) == 1, "requires-python must declare one exclusive ceiling"
    ceiling = bounds[0]
    versions = []
    for job in _workflow_jobs().values():
        versions.extend(job.get("strategy", {}).get("matrix", {}).get("python-version", []))
        for step in job["steps"]:
            version = step.get("with", {}).get("python-version", "")
            if version and not version.startswith("${{"):
                versions.append(version)
            if step.get("with", {}).get("python-version-file") == "pyproject.toml":
                # This leg selects the newest minor allowed by the same metadata.
                versions.append(f"{ceiling.major}.{ceiling.minor - 1}")
    newest = max(map(Version, versions))
    assert all(Version(version) in spec for version in versions)
    assert ceiling == Version(f"{newest.major}.{newest.minor + 1}")


@pytest.mark.requirement("FR-3331")
def test_p0500_lean_job_runs_parallel_tier_one_without_user_extras():
    runs = [step.get("run", "") for step in _workflow_jobs()["test-lean"]["steps"]]
    assert "pytest -n auto tests/tier1_offline" in runs
    lean = "\n".join(runs)
    assert "pip install -e .[dev]" in lean
    assert not any(f"[{extra}" in lean for extra in ("pandas", "fsi", "excel", "manual"))


def _pyproject() -> dict:
    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


def _declared_floor(specifier: str, name: str) -> Version:
    match = re.search(r">=\s*([0-9][0-9.]*)", specifier)
    assert match, f"{name} declares {specifier!r}, which names no floor"
    return Version(match.group(1))


def test_the_continuous_integration_legs_start_at_the_declared_floor():
    """The matrix follows pyproject, not the other way round."""
    floor = _declared_floor(_pyproject()["project"]["requires-python"], "requires-python")
    for workflow in ("ci.yml", "release.yml"):
        text = (REPO / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        matrices = re.findall(r"python-version:\s*\[([^\]]+)\]", text)
        assert matrices, f"{workflow} declares no python-version matrix"
        for matrix in matrices:
            legs = [Version(leg.strip().strip('"')) for leg in matrix.split(",")]
            assert min(legs) == floor, (
                f"{workflow} runs Python {min(legs)} and the declared floor is {floor}"
            )


def test_the_linter_targets_the_declared_floor():
    """ruff's target-version and the floor say one thing (mypy is deliberately unpinned)."""
    data = _pyproject()
    floor = _declared_floor(data["project"]["requires-python"], "requires-python")
    target = data["tool"]["ruff"]["target-version"]
    assert target == f"py{floor.major}{floor.minor}", (
        f"ruff targets {target} and the floor is {floor}"
    )
    classifiers = [
        c.rsplit(" ", 1)[1]
        for c in data["project"]["classifiers"]
        if c.startswith("Programming Language :: Python :: 3.")
    ]
    assert classifiers and min(map(Version, classifiers)) == floor, (
        f"the classifiers list {classifiers} and the floor is {floor}"
    )


def test_the_installed_version_of_each_declared_dependency_is_inside_its_range():
    """F-797, X-F-0001: the declared envelope of every dependency is measured on this tree.

    A floor above the installed version, or a ceiling at or below it, is a declaration the
    tree itself contradicts. (The CI leg test-floors runs this on all runtime and user-extra floors,
    and every other leg runs it on the newest release.)
    """
    from importlib import metadata

    from packaging.requirements import Requirement

    for text in _pyproject()["project"]["dependencies"]:
        requirement = Requirement(text)
        installed = Version(metadata.version(requirement.name))
        assert requirement.specifier.contains(installed, prereleases=True), (
            f"{requirement.name} {installed} is outside the declared {requirement.specifier}"
        )
