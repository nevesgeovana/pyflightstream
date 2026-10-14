"""P0410 suite partition: select a package with ``pytest -m pkg_post``."""

import json
from collections import Counter
from pathlib import Path, PurePosixPath

import pytest

PACKAGES = {
    "core",
    "script-results",
    "probes-farfield",
    "fsi",
    "cases",
    "workspace",
    "run",
    "post",
    "qa",
    "guards",
}
REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "tests/tier1_offline/packages.json"


def validate_packages(manifest: Path, repo: Path) -> None:
    """Refuse an incomplete, ambiguous or stale tier-1 file partition."""
    assert manifest.is_file(), "suite package manifest is missing"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["version"] == 1, "unsupported suite package version"
    packages = data["packages"]
    assert set(packages) == PACKAGES, "unknown or missing package name"
    listed = []
    for name, paths in [*packages.items(), ("shared_support", data["shared_support"])]:
        assert paths == sorted(paths), f"unsorted list: {name}"
        for path in paths:
            relative = PurePosixPath(path)
            assert (
                not relative.is_absolute()
                and ".." not in relative.parts
                and relative.as_posix() == path
                and "\\" not in path
            ), f"not a repository-relative POSIX path: {path}"
            assert (repo / path).exists(), f"listed path does not exist: {path}"
        if name != "shared_support":
            listed.extend(paths)
    duplicates = sorted(path for path, count in Counter(listed).items() if count > 1)
    assert not duplicates, f"file in two packages or repeated: {duplicates}"
    actual = {
        path.relative_to(repo).as_posix()
        for path in (repo / "tests/tier1_offline").rglob("test_*.py")
    }
    assert actual == set(listed), (
        f"unlisted tier-1 files: {sorted(actual - set(listed))}; "
        f"not tier-1 test files: {sorted(set(listed) - actual)}"
    )


def test_p0410_real_suite_packages():
    validate_packages(MANIFEST, REPO)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("unlisted", "unlisted tier-1 files"),
        ("duplicate", "file in two packages"),
        ("missing", "listed path does not exist"),
        ("unknown", "unknown or missing package name"),
        ("unsorted", "unsorted list"),
    ],
    ids=lambda value: f"P0410-{value}",
)
def test_p0410_suite_packages_refuses_controls(tmp_path, mutation, message):
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    core = data["packages"]["core"]
    if mutation == "unlisted":
        core.pop()
    elif mutation == "duplicate":
        data["packages"]["post"].append(core[0])
        data["packages"]["post"].sort()
    elif mutation == "missing":
        core.append("tests/tier1_offline/test_missing_package_control.py")
        core.sort()
    elif mutation == "unknown":
        data["packages"]["unknown"] = []
    elif mutation == "unsorted":
        core.reverse()
    manifest = tmp_path / "packages.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AssertionError, match=message):
        validate_packages(manifest, REPO)
