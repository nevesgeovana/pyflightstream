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


def test_p0440_confirmed_reachability_decisions_name_the_confirmation():
    import json

    data = json.loads((REPO / "tests/tier1_offline/reachability_exceptions.json").read_text())
    rows = {row["id"]: row for row in data["rows"]}
    for name in ("RX-13", "RX-17", "RX-18", "RX-21", "RX-37"):
        assert "the owner confirmed on 2026-10-22" in rows[name]["decision"], name


SHIPPED_SURFACE_CONFIG = TOOLS / "shipped_surface.conf"


TESTS_UNGUARDED_SPAWNS = 5


#: 0.51.0 (FR-3402) budgets the two 26.126 probe campaigns, the evidence every 26.126 row
#: cites (reports/compat/CMP-26126_2026-10-30_probe-campaign and -fsm, yaml and md): +4
#: tracked files, +3 report files counted here, +11505 report lines, measured.
#: 0.52.0 budgets the six test modules of the no-refusal lane (FR-3404, FR-3405:
#: tests/tier1_offline/test_p0520_norefusal*.py, +6 tracked files) and the 26.127
#: evidence (FR-3406, FR-3407: reports/compat/CMP-26127_2026-10-30_probe-campaign and
#: -fsm, yaml and md, the vendor CCS export report, the 26.127 row of RPT-032), measured.
#: 0.52.1 budgets the test module of the XPROP sector's coupled rows (FR-3408:
#: tests/tier1_offline/test_p0521_fsi_sector.py, +1 tracked file), measured.
#: 0.53.0 (PFS-2185.18) budgets run/_post_selection.py, the post selection moved out of
#: run/cli.py to hold its AD-18 size bound (+1 tracked file), measured.
#: The p0410 manual-help test folded into test_p0410_fx3_contributing.py (-1 tracked file).
#: 0.54.0 (PFS-2186) budgets the sector-to-wheel, merge, remesh, marking and slope modules of the
#: five lanes (src/pyflightstream: post/_cn_slope.py, qa/_spec_0540_marking.py, run/_cli_merge.py,
#: run/_cli_wheel.py, workspace/_mark_rims.py, _merge.py, _sector_body.py, _sector_driver.py,
#: _sector_read.py, _sector_remesh.py, _sector_save.py, _wheel.py, _wheel_fsm.py), their tests
#: and the four 26.100 marking probe reports (reports/compat/CMP-26100_2026-11-02_mark-26100-base
#: and -vertex, yaml and md: +4 report files, +9698 report lines): +30 tracked files, measured.
#: 0.55.1 (PFS-2187) budgets repitch, blade order, rotor sections and tests: 2102, measured.
#: RELDOCS measures 2093 tracked files: base 2094, collision regression +1,
#: folded H03/H04 changelog fragments -2. The existing 2100 cap has seven spare files.
#: 0.56.0 (collapse-te) budgets the module and its test file: 2104, measured (+2 tracked files).
#: 0.56.0 (morph, PFS-2192 and PFS-2193) budgets run/_cli_morph.py, workspace/_pitch_axis.py,
#: _hub_rings_grid.py, hub_rings.py, morph.py and test_p0560_morph.py: 2110, measured (+6).
#: 0.56.0 (wheel, PFS-2195) budgets test_p0560_wheel_terminations.py: 2111, measured (+1).
#: 0.56.0 (iges, PFS-2198 and PFS-2199) budgets run/_cli_iges.py, workspace/_gmsh.py,
#: _iges_names.py, _iges_grid_config.py, _iges_mesh.py, iges_grid.py, iges_convert.py,
#: test_p0560_iges.py and docs/mesh/iges.md: 2119, measured (+9).
#: integration of 0.56.0: 2110 + 1 (wheel) + 9 (iges) + 2 (hubq) + 1 (pbug) = 2123, then the 26.127
#: marking report pair (CMP-26127_2026-11-06_marking): 2125 files, 107 reports,
#: 177027 report lines, measured.
#: then the v127 lane at 7a7ce6ee7 (14 probe reports of PFS-2187.04, .05 and PFS-2191, 4 tests and
#: specs): 2143 files, 121 reports, 208338 report lines, measured.
#: then the 26.127 rim face-order test (test_p0560_rim_face_order.py): 2144 files, measured.
#: then the outer skin of iges-grid (workspace/_iges_skin.py): 2145 files, measured.
#: then the CI shard selector test (test_p0560_ci_shards.py): 2146 files, measured.
#: Runtime and timing files and the scripts marker bring the tree to 2154 (two SRS pages folded).
#: then the IGES decisions (R1-IGES-008 worker, R1-IGES-010, R2-006, R3-006): four changelog
#: fragments, workspace/_gmsh_worker.py and test_p0570_iges_decisions.py: 2160, measured (+6).
#: then the L1 merge (+15 files, RL57B-5) and the lane-057-debt commits: 2175, measured.
#: then geometry._boundary, the private home of the L1 boundary helpers: 2176, measured (+1).
#: then item 3 lanes L2 and L4 (seven private geometry modules, four workspace modules,
#: five test files, two changelog fragments): 2194, measured (+18).
LEAN_CAPS = {
    "tracked_files": 2205,
    "reports_files": 121,
    "reports_lines": 208338,
    "tests_files": 1167,
    "tests_lines": 406996,
}

#: Measured and reported, not enforced, in 0.46.0: the tests review before 1.0.0 (PFS-2177)
#: sets these two caps again.
REPORTED_ONLY = frozenset({"tests_files", "tests_lines"})


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
        if measured[key] > cap and key not in REPORTED_ONLY
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
    enforced = {key: cap for key, cap in LEAN_CAPS.items() if key not in REPORTED_ONLY}
    for key, cap in enforced.items():
        over = {**LEAN_CAPS, key: cap + 1}
        with pytest.raises(AssertionError) as caught:
            _assert_lean_caps(listing(over))
        assert f"{key}: measured {cap + 1}, cap {cap}" in str(caught.value)
        assert all(
            f"{other}: measured" not in str(caught.value) for other in LEAN_CAPS if other != key
        )
    for key in REPORTED_ONLY:
        over = {**LEAN_CAPS, key: LEAN_CAPS[key] + 1}
        assert _assert_lean_caps(listing(over)) == over
    with pytest.raises(AssertionError) as caught:
        _assert_lean_caps(listing({key: cap + 1 for key, cap in LEAN_CAPS.items()}))
    for key, cap in LEAN_CAPS.items():
        reported = f"{key}: measured {cap + 1}, cap {cap}" in str(caught.value)
        assert reported is (key not in REPORTED_ONLY), key


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


def test_p0440_release_checks_built_archives_and_declares_scanned_floors():
    config = _shipped_surface_module().load_config(SHIPPED_SURFACE_CONFIG)
    assert "pyflightstream/__init__.py" in config.wheel_floor
    assert "src/pyflightstream/__init__.py" in config.sdist_floor
    assert "tools/check_shipped_surface.py" in config.sdist_floor
    workflow = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
    build = workflow.split("  test-artifact:")[0]
    assert (
        "python tools/check_shipped_surface.py --config tools/shipped_surface.conf --dist dist"
        in build
    )
    assert build.index("python -m build") < build.index("--dist dist")
    assert build.index("--dist dist") < build.index("actions/upload-artifact@")


def test_p0440_dist_boundary_reads_both_archives_and_rejects_an_omitted_floor(tmp_path):
    import tarfile
    import zipfile

    config = _shipped_surface_module().load_config(SHIPPED_SURFACE_CONFIG)
    with zipfile.ZipFile(tmp_path / "control-1.0-py3-none-any.whl", "w") as archive:
        for path in config.wheel_floor:
            archive.writestr(path, "clean control\n")

    def sdist(omit):
        with tarfile.open(tmp_path / "control-1.0.tar.gz", "w:gz") as archive:
            for path in config.sdist_floor:
                if path != omit:
                    payload = b"clean control\n"
                    member = tarfile.TarInfo(f"control-1.0/{path}")
                    member.size = len(payload)
                    archive.addfile(member, BytesIO(payload))

    args = (
        str(TOOLS / "check_shipped_surface.py"),
        "--config",
        str(SHIPPED_SURFACE_CONFIG),
        "--dist",
        str(tmp_path),
    )
    sdist(None)
    clean = _run(*args)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "ARTIFACT boundary" in clean.stdout
    sdist("tools/check_shipped_surface.py")
    refused = _run(*args)
    assert refused.returncode != 0
    assert "tools/check_shipped_surface.py" in refused.stdout + refused.stderr


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

    This checks the TREE boundary. The release workflow separately checks
    the built wheel and sdist with ``--dist`` before uploading either archive.
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


def test_rl57_public_files_do_not_narrate_who_chose_the_allowance():
    """A requirement is stated, never its provenance."""
    for parts in (
        ("CHANGELOG.md",),
        ("docs", "upgrading.md"),
        ("src", "pyflightstream", "qa", "_spec_0560_export_detect.py"),
    ):
        text = REPO.joinpath(*parts).read_text(encoding="utf-8").lower()
        assert "owner-chosen" not in text, parts
        assert "owner's numerical call" not in text, parts


def test_rl57_unreleased_changelog_has_one_section_per_heading():
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = text.split("## [Unreleased]")[1].split("## [")[0]
    headings = [line for line in unreleased.splitlines() if line.startswith("### ")]
    assert len(headings) == len(set(headings)), headings


def test_rl57_runtime_docs_do_not_call_the_defaults_open():
    text = (REPO / "docs" / "setup-standards.md").read_text(encoding="utf-8")
    section = text.split("## Launch runtime resources")[1].split("## ")[0]
    assert "still open" not in section
    assert "owner" not in section.lower()
