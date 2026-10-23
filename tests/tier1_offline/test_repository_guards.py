"""Retained runtime, privacy and link checks, with shared test support."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


TOOLS = REPO / "tools"


SHIPPED_SURFACE_CONFIG = TOOLS / "shipped_surface.conf"


TESTS_UNGUARDED_SPAWNS = 5


LEAN_CAPS = {
    "tracked_files": 2016,
    "reports_files": 91,
    "reports_lines": 138107,
    "tests_files": 1147,
    "tests_lines": 389553,
}


def _assert_lean_caps(files: Iterable[tuple[bytes, bytes]]) -> dict[str, int]:
    """Count tracked paths and literal LF bytes, then report every exceeded cap."""
    measured = dict.fromkeys(LEAN_CAPS, 0)
    for path, blob in files:
        measured["tracked_files"] += 1
        for folder in ("reports", "tests"):
            if path.startswith(folder.encode() + b"/"):
                measured[f"{folder}_files"] += 1
                measured[f"{folder}_lines"] += blob.count(b"\n")
    exceeded = [
        f"{key}: measured {measured[key]}, cap {cap}"
        for key, cap in LEAN_CAPS.items()
        if measured[key] > cap
    ]
    assert not exceeded, "Lean repository caps exceeded:\n" + "\n".join(exceeded)
    return measured


@pytest.mark.pkg_guards
def test_repository_lean_caps() -> None:
    """Keep the tracked index within the fixed GOAL-056 repository budgets."""
    if not (REPO / ".git").exists():
        pytest.skip("Lean repository caps require a git checkout, not an installed wheel")

    def git(*args: str, data: bytes | None = None) -> bytes:
        return subprocess.run(
            ["git", "-C", str(REPO), *args],
            input=data,
            capture_output=True,
            check=True,
            env=os.environ.copy(),
        ).stdout

    paths = git("ls-files", "-z").split(b"\0")[:-1]
    selected = [path for path in paths if path.startswith((b"reports/", b"tests/"))]
    # NUL-delimited input handles even tracked names containing newlines.
    blobs = BytesIO(
        git("cat-file", "--batch", "-z", data=b"".join(b":" + p + b"\0" for p in selected))
    )

    def files() -> Iterable[tuple[bytes, bytes]]:
        for path in paths:
            blob = b""
            if path.startswith((b"reports/", b"tests/")):
                header = blobs.readline().split()
                assert len(header) == 3 and header[1] == b"blob", header
                size = int(header[2])
                blob = blobs.read(size)
                assert len(blob) == size and blobs.read(1) == b"\n", path
            yield path, blob

    _assert_lean_caps(files())


@pytest.mark.pkg_guards
def test_repository_lean_caps_control() -> None:
    """Accept every exact boundary and reject each excess, including all at once."""

    def listing(counts: dict[str, int]) -> list[tuple[bytes, bytes]]:
        files = []
        for folder in ("reports", "tests"):
            for index in range(counts[f"{folder}_files"]):
                # CR and an unterminated tail are not lines; binary LF bytes are.
                blob = b"\x00\r\n" * counts[f"{folder}_lines"] if index == 0 else b""
                files.append((f"{folder}/{index}".encode(), blob + b"tail\r"))
        files.extend(
            (f"src/{index}".encode(), b"ignored\n")
            for index in range(counts["tracked_files"] - len(files))
        )
        return files

    assert _assert_lean_caps(listing(LEAN_CAPS)) == LEAN_CAPS
    for key, cap in LEAN_CAPS.items():
        over = {**LEAN_CAPS, key: cap + 1}
        with pytest.raises(AssertionError) as caught:
            _assert_lean_caps(listing(over))
        assert f"{key}: measured {cap + 1}, cap {cap}" in str(caught.value)
        assert all(
            f"{other}: measured" not in str(caught.value) for other in LEAN_CAPS if other != key
        )
    with pytest.raises(AssertionError) as caught:
        _assert_lean_caps(listing({key: cap + 1 for key, cap in LEAN_CAPS.items()}))
    for key, cap in LEAN_CAPS.items():
        assert f"{key}: measured {cap + 1}, cap {cap}" in str(caught.value)


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    """Run a checker as a subprocess, with an explicit environment.

    ``env=`` is not decoration here: this file lives under ``tests`` and the
    ratchet below counts unguarded spawns in exactly this directory, so a
    helper that inherited by default would push its own measurement over the
    pin. A guard whose harness violates the rule it enforces is the shape
    this repository keeps finding.
    """
    return subprocess.run(
        [sys.executable, *argv],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )


def test_every_checker_this_module_runs_is_present() -> None:
    """Guard the guard: a checker that is not there denies nothing.

    Every test below runs a script BY PATH. A missing or moved script makes
    the subprocess fail with an interpreter error, which each test would
    report as a checker finding rather than as a broken wiring, and a
    relocation that silently disabled two repository-wide guards is exactly
    the failure this file exists to make impossible. Asserted first, and
    asserted on the whole set at once, so the message names what is absent.
    """
    required = (
        TOOLS / "check_shipped_surface.py",
        TOOLS / "check_shipped_surface_mutations.py",
        SHIPPED_SURFACE_CONFIG,
        TOOLS / "check_spawn_env.py",
        TOOLS / "check_spawn_env_mutations.py",
    )
    missing = [str(path.relative_to(REPO)) for path in required if not path.is_file()]
    assert not missing, (
        f"these checkers are named by this module and are not in the tree: {missing}. "
        "Every test below invokes one by path, so their absence would be reported "
        "as a finding about this repository rather than as a guard that stopped "
        "running. Restore the file or delete the test that runs it, deliberately."
    )


def test_every_spawn_under_src_and_scripts_passes_an_explicit_environment() -> None:
    """No subprocess in the package or its scripts inherits by default.

    An inherited environment carries whatever the parent had, including the
    coverage variables a test runner injects, and a child that reads them
    behaves differently under the suite than it does for a user. The remedy
    is one keyword at the call site.
    """
    done = _run(str(TOOLS / "check_spawn_env.py"), "src", "scripts")
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "0 unguarded" in done.stdout, done.stdout
    assert "0 unverifiable" in done.stdout, done.stdout


def test_the_spawn_env_guard_can_still_fail() -> None:
    """The companion beside the checker, run.

    Its first mutant restores the original defect: judging a call by every
    keyword in its module rather than by its own, which is what a line window
    over the source approximates. A checker whose evidence ships and is never
    run is the shape this repository keeps registering.
    """
    done = _run(str(TOOLS / "check_spawn_env_mutations.py"))
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "The guard can still fail." in done.stdout, done.stdout


def test_the_unguarded_spawns_under_tests_do_not_grow() -> None:
    """A RATCHET on ``tests``, and the number is the honest part of it.

    Both directions fail. Up, because a new spawn that inherits the whole
    environment is the defect. Down, because a pin nobody lowers stops being
    a measurement of the tree and becomes a floor: the downward arm asks for
    this constant to move in the same commit that closes a call site.
    """
    done = _run(str(TOOLS / "check_spawn_env.py"), "tests")
    summary = done.stdout.strip().splitlines()[-1]
    assert "spawn call(s)" in summary, done.stdout
    unguarded = int(summary.split(" unguarded")[0].split(", ")[-1])
    assert unguarded == TESTS_UNGUARDED_SPAWNS, (
        f"{unguarded} unguarded spawn call(s) under tests, differing from the pinned "
        f"{TESTS_UNGUARDED_SPAWNS}. Pass env= on new spawns; lower the pin when "
        "an unguarded spawn is removed."
    )


@pytest.mark.parametrize("count", [TESTS_UNGUARDED_SPAWNS - 1, TESTS_UNGUARDED_SPAWNS + 1])
def test_p0440_spawn_ratchet_rejects_both_directions(monkeypatch, count):
    from types import SimpleNamespace

    monkeypatch.setattr(
        sys.modules[__name__],
        "_run",
        lambda *args: SimpleNamespace(stdout=f"10 spawn call(s), {count} unguarded\n"),
    )
    with pytest.raises(AssertionError):
        test_the_unguarded_spawns_under_tests_do_not_grow()


def test_no_forbidden_identifier_in_the_versioned_tree() -> None:
    """The shipped-surface rule, over the tree boundary only.

    SCOPE, stated because the checker itself insists on it: this is the TREE
    boundary and it REASONS about what ships. Only the archive answers it,
    and the artifact boundary (``--dist`` over a built wheel and sdist) is
    not wired here, because wiring it needs a build in the loop. The config
    records that adding it later means adding a wheel-floor and an
    sdist-floor in the same change, which the checker refuses to run
    without.
    """
    _assert_no_internal_lane_records()
    done = _run(
        str(TOOLS / "check_shipped_surface.py"),
        "--config",
        str(SHIPPED_SURFACE_CONFIG),
        "--tree",
        str(REPO),
    )
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "no forbidden identifier found" in done.stdout, done.stdout

    # THE ACCOUNTING, PARSED, not merely present. An earlier version of this
    # test asserted that the words "inventory" and "scanned" appeared, which
    # a review pointed out is satisfied by a run that opened one file and by
    # a --tree pointed anywhere the checker accepts: both words are on a line
    # the checker prints unconditionally. The floors below are what would
    # actually catch a mis-pointed tree.
    line = next(ln for ln in done.stdout.splitlines() if "inventory" in ln)
    numbers = {key: int(value) for key, value in re.findall(r"(\w+) (\d+)", line.replace(":", " "))}
    assert numbers["inventory"]
    assert numbers["scanned"]
    assert numbers["undecodable"] == 0 and numbers["unreadable"] == 0, line
    _assert_exemption_policy(_shipped_surface_module().load_config(SHIPPED_SURFACE_CONFIG))


def _assert_no_internal_lane_records() -> None:
    tracked = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
        env=os.environ.copy(),
    ).stdout.split("\0")
    internal = [path for path in tracked if path.startswith("lanes/")]
    assert not internal, f"internal lane records are tracked: {internal}"


def test_p0420_internal_lane_records_control(monkeypatch) -> None:
    """A planted tracked lane path must fail even without forbidden text."""

    def tracked(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, "README.md\0lanes/control.json\0", "")

    monkeypatch.setattr(subprocess, "run", tracked)
    with pytest.raises(AssertionError, match="lanes/control.json"):
        _assert_no_internal_lane_records()


def test_the_shipped_surface_guard_can_still_fail() -> None:
    """The companion beside the checker, run. See the spawn-env one above.

    It builds real archives and asserts that each of its thirty mutants is
    denied by a detector rather than by a crash, and it carries control pairs
    that must PASS once their detector is removed. That last property is why
    running it matters more than for most: a battery whose cases all pass for
    the same reason proves one thing, not thirty.
    """
    done = _run(str(TOOLS / "check_shipped_surface_mutations.py"))
    assert done.returncode == 0, f"{done.stdout}\n{done.stderr}"
    assert "none merely by crashing" in done.stdout, done.stdout


def _shipped_surface_module():
    """Import the checker by path, since `tools/` is not a package.

    REGISTERED IN `sys.modules` BEFORE EXECUTION, which is not ceremony:
    the module defines a frozen dataclass, and dataclass field
    processing looks the defining class's module up in `sys.modules`.
    Without the registration that lookup returns None and the import
    dies inside the standard library, several frames from anything that
    names this file.
    """
    import importlib.util

    name = "check_shipped_surface_under_test"
    spec = importlib.util.spec_from_file_location(name, TOOLS / "check_shipped_surface.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[name]
        raise
    return module


def test_the_live_configuration_names_only_files_that_exist():
    """Every exempted path is a file this repository actually has.

    The assertion that would have caught the dangling one, and it fails
    if a future edit reintroduces the shape.
    """
    module = _shipped_surface_module()
    config = module.load_config(SHIPPED_SURFACE_CONFIG)
    assert config.exempt_paths, (
        "the configuration exempts nothing, so this test would pass over an empty set "
        "and prove nothing about the rule it guards"
    )
    absent = sorted(entry for entry in config.exempt_paths if not (REPO / entry).exists())
    assert not absent, (
        f"the shipped-surface configuration exempts {absent}, which this repository does "
        "not have. An exemption for an absent file never fires, so it never fails, and it "
        "reads as an exemption that is still needed long after the file it excused has gone"
    )


def _assert_exemption_policy(config) -> None:
    """Pin the granted paths and trees, independently of their current file counts."""
    assert config.exempt_paths == frozenset(
        {
            "LICENSE",
            "CITATION.cff",
            "README.md",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "pyproject.toml",
            ".github/workflows/release.yml",
            "properdocs.yml",
        }
    )
    assert set(config.exempt_trees) == {"guide/", "docs/"}


def test_xz_text_is_scanned_in_full_and_a_compressed_identifier_is_refused():
    """Compressed fixtures are text carriers; compression grants no exemption."""
    import lzma

    checker = _shipped_surface_module()
    config = checker.load_config(SHIPPED_SURFACE_CONFIG)
    clean = b"ASCII synthetic wake\n" * 10000
    good = checker.scan([("fixture.vtk.xz", lzma.compress(clean))], config)
    assert good.scanned == ["fixture.vtk.xz"] and not good.undecodable
    assert not good.findings and good.examined_chars > 100000
    # Use the checker's assembled token so the test ships no forbidden name.
    bad = checker.scan(
        [("fixture.vtk.xz", lzma.compress(clean + checker._INSTITUTION.encode()))], config
    )
    assert bad.scanned == ["fixture.vtk.xz"] and not bad.undecodable
    assert any("an institution name" in finding for finding in bad.findings)
    broken = checker.scan([("fixture.vtk.xz", lzma.compress(clean)[:-10])], config)
    assert broken.undecodable == ["fixture.vtk.xz"] and not broken.scanned
