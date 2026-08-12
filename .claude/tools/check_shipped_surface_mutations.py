# ITACA / pyflightstream shared process kit
# kit-version: 0.2.18
# artifact: check_shipped_surface_mutations.py
# body-sha256: 09b94846024e803116f2308a6aecccc6d70e91da021104fa459ef06c0d486daa
# canonical-source: BUILT for the kit (0.2.7): the mutation companion for check_shipped_surface.py. Its fixtures are deliberately awkward because a review demonstrated that eight dangerous mutants survived a flat, all-committed, all-ASCII fixture tree. Two control PAIRS carry the defences that cannot be observed alone. 0.2.18 adds the src-layout case, its over-widened twin, and one mutant for each direction, so neither anchoring the exemption at the root again nor exempting anything whose name ends in PKG-INFO can survive.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Prove check_shipped_surface.py can still refuse, on real archives.

Usage:
  python check_shipped_surface_mutations.py

Every case writes an actual git repository and actual zip and tar archives into
a temporary directory and runs the checker as a subprocess, so what is asserted
is behaviour rather than the shape of the source. Then each mutant
reintroduces one way the checker can be weakened and must be REFUSED by at
least one case.

The sample identifiers here are built from code points, and that is load
bearing twice over. This file is vendored into repositories whose own rule
forbids those strings, so a literal token would make the mutation companion the
thing that ships the identifier; and building the samples independently of the
checker's own token table is what makes a mutation of that table visible,
rather than the two agreeing because they are one expression.

WHY THE CASE LIST IS THE SHAPE IT IS
------------------------------------

An adversarial review of the first version of this pair, run by a session that
did not write it, found twelve behaviour defects in the checker and eight
mutants that survived every case here. Most of those mutants survived because
the FIXTURE could not express the defect: the tree was flat, so a narrowing by
depth was invisible; every file was committed, so dropping untracked files was
invisible; every payload was ASCII, so a text encoding this platform writes by
default was invisible.

So the fixtures below are deliberately awkward. The tree has a file three
directories deep, a file in a dot-directory, an untracked file, a file whose
identifier is NOT on line 1, a UTF-16 payload, and a payload that is genuinely
binary. Each exists because a mutant survived without it.

A CASE THAT MOST OF THESE MUTANTS DIE ON IS `clean`. That is deliberate and it
is the strongest property here: the checker refuses a narrowed scan of a CLEAN
tree, because it accounts for every file rather than only reporting what it
happened to find. A guard that only speaks when it finds something cannot tell
a clean tree from an unread one.

DIVISION OF LABOUR, stated because a reader will look for the missing half.
This file proves the CHECKER fails on bad input. It does not prove the
repository it sits in is clean; that is the vendored tier-1 test's job, which
runs the checker against the repository's own tree and its own built artifacts.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE / "check_shipped_surface.py"
BACKSLASH = chr(92)

# The samples, from code points: the author's given name, her family name, the
# institution in the run-together form that appears in an address, and in the
# spaced form that appears in prose.
_GIVEN = "".join(map(chr, (71, 101, 111, 118, 97, 110, 97)))
_FAMILY = "".join(map(chr, (78, 101, 118, 101, 115)))
_DOMAIN = "".join(map(chr, (116, 117, 100, 101, 108, 102, 116)))
_SPACED = "".join(map(chr, (84, 85, 32, 68, 101, 108, 102, 116)))

DIRTY_DOCSTRING = f'"""Example: set_user("{_GIVEN.lower()}@{_DOMAIN}").\n"""\n'
DIRTY_TRAILER = f"# Co-Authored-By: {_GIVEN.lower()}n90@example.com\n"
DIRTY_PROSE = f"affiliation: {_SPACED}\n"
DIRTY_CITE = f"# cite: {_FAMILY.upper()}, G. (2026)\n"

# The identifier is on line 6, never line 1, so a scan that reads only the
# first line of a file misses it. That mutant survived every case in the first
# version of this file.
DIRTY_DEEP = "".join(f"# filler line {n}\n" for n in range(5)) + DIRTY_TRAILER

CLEAN_TEXT = (
    '"""Example: set_user("analyst@lab01").\n\n'
    "The unevenness of the grid never matters here, and an author call at\n"
    "the B1 checkpoint is a decision record, not a name.\n"
    '"""\n'
)

GOOD_CONFIG = """\
exempt-path: LICENSE
exempt-path: README.md
exempt-tree: docs/
wheel-floor: pkg/core.py
sdist-floor: pkg/core.py
sdist-floor: tests/test_core.py
"""


# ---- fixtures --------------------------------------------------------------


def _write(root: Path, files: dict[str, bytes]) -> None:
    for rel, payload in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def make_repo(
    tmp: Path,
    files: dict[str, bytes],
    *,
    untracked: dict[str, bytes] | None = None,
    delete_after_add: str | None = None,
    empty: bool = False,
) -> Path:
    """A real git checkout, because the tree boundary asks git for its
    inventory and a directory walk would not exercise that at all.

    ``untracked`` is written AFTER `git add`, so those files are
    untracked-but-not-ignored: written and not yet committed, which the checker
    documents as something a guard must still see.

    ``delete_after_add`` leaves a path in git's index and absent from disk,
    which is what a sparse checkout, an editor lock or a path over this
    platform's length limit looks like from here.
    """
    root = tmp / "repo"
    root.mkdir()
    if not empty:
        _write(root, files)
    for args in (["init", "-q"], ["add", "-A"]):
        done = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, check=False
        )
        if done.returncode != 0 and args[0] == "init":
            raise RuntimeError(f"git {args} failed: {done.stderr.decode()}")
    if untracked:
        _write(root, untracked)
    if delete_after_add:
        (root / delete_after_add).unlink()
    return root


def make_dist(
    tmp: Path,
    wheel_files: dict[str, bytes],
    sdist_files: dict[str, bytes],
    *,
    name: str = "pkg",
    version: str = "1.0.0",
    extra_wheel: bool = False,
    raw_sdist_member: tuple[str, bytes] | None = None,
) -> Path:
    """One wheel and one sdist, built as real archives.

    The sdist wraps everything in ``<name>-<version>/``, exactly as a real one
    does, because stripping that prefix is a rule with its own failure mode:
    left in place, every exemption stops matching and the scan reports offences
    in the files a decision exempted.

    ``raw_sdist_member`` is added through TarInfo rather than from a file on
    disk, which is the only way to put a name this platform's filesystem
    refuses into an archive. It is how the backslash case is built.
    """
    dist = tmp / "dist"
    dist.mkdir(exist_ok=True)
    with zipfile.ZipFile(dist / f"{name}-{version}-py3-none-any.whl", "w") as wheel:
        for rel, payload in wheel_files.items():
            wheel.writestr(rel, payload)
    if extra_wheel:
        with zipfile.ZipFile(dist / f"{name}-0.9.0-py3-none-any.whl", "w") as stale:
            stale.writestr(f"{name}/core.py", b"# stale\n")
    payload_dir = tmp / "sdist-src"
    shutil.rmtree(payload_dir, ignore_errors=True)
    payload_dir.mkdir()
    _write(payload_dir, sdist_files)
    with tarfile.open(dist / f"{name}-{version}.tar.gz", "w:gz") as bundle:
        for path in sorted(payload_dir.rglob("*")):
            if path.is_file():
                rel = path.relative_to(payload_dir).as_posix()
                bundle.add(path, arcname=f"{name}-{version}/{rel}")
        if raw_sdist_member is not None:
            member_name, data = raw_sdist_member
            info = tarfile.TarInfo(f"{name}-{version}/{member_name}")
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
    return dist


CLEAN_TREE: dict[str, bytes] = {
    "pkg/__init__.py": b"",
    "pkg/core.py": CLEAN_TEXT.encode(),
    # Three directories deep. A narrowing by depth was invisible while every
    # fixture file sat at depth two.
    "tests/unit/inner/test_deep.py": CLEAN_TEXT.encode(),
    "tests/test_core.py": CLEAN_TEXT.encode(),
    # A dot-directory, which a walk that skips them would drop silently.
    ".ci/steps.yml": b"steps: []\n",
    "docs/design.md": DIRTY_PROSE.encode(),  # exempt tree: the decision record
    "LICENSE": f"Copyright (c) 2026 {_GIVEN} {_FAMILY}\n".encode(),
    "README.md": f"By {_GIVEN} {_FAMILY}.\n".encode(),
    "pyproject.toml": b'[project]\nname = "pkg"\n',
    # Genuinely binary: no text codec decodes it, so it is counted as
    # undecodable rather than scanned, and the pair of assertions below pins
    # both directions of that classification.
    "tests/data/blob.bin": bytes(range(256)) * 8,
    # Large and clean. It carries no identifier, so no case can notice a
    # narrowing INSIDE a file by an identifier going missing; only the
    # character counters can. Without a file this size the counters were
    # unfalsifiable on this fixture set, which is a guard nobody tried to
    # break.
    "tests/data/large_clean.txt": b"a clean line of filler text\n" * 8000,
}
CLEAN_WHEEL: dict[str, bytes] = {
    "pkg/__init__.py": b"",
    "pkg/core.py": CLEAN_TEXT.encode(),
    "pkg-1.0.0.dist-info/METADATA": f"Author: {_GIVEN} {_FAMILY}\n".encode(),
    "pkg-1.0.0.dist-info/licenses/LICENSE": f"(c) {_GIVEN} {_FAMILY}\n".encode(),
}
CLEAN_SDIST: dict[str, bytes] = {
    "pkg/__init__.py": b"",
    "pkg/core.py": CLEAN_TEXT.encode(),
    "tests/test_core.py": CLEAN_TEXT.encode(),
    "docs/design.md": DIRTY_PROSE.encode(),
    "LICENSE": f"Copyright (c) 2026 {_GIVEN} {_FAMILY}\n".encode(),
    "README.md": f"By {_GIVEN} {_FAMILY}.\n".encode(),
    "PKG-INFO": f"Author: {_GIVEN} {_FAMILY}\n".encode(),
    "pyproject.toml": b'[project]\nname = "pkg"\n',
}


def run(checker: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(checker), *args], capture_output=True, check=False
    )


def _with(base: dict[str, bytes], **extra: bytes) -> dict[str, bytes]:
    merged = dict(base)
    merged.update(extra)
    return merged


def _replace(base: dict[str, bytes], key: str, value: bytes) -> dict[str, bytes]:
    merged = dict(base)
    merged[key] = value
    return merged


# ---- the cases -------------------------------------------------------------
#
# Each case is (label, key, expected exit code, a fragment that must appear in
# the combined output). The fragment is what keeps a case honest: a checker
# that exits 2 for the wrong reason satisfies the code alone.

CASES: list[tuple[str, str, int, str]] = [
    ("a clean tree and clean archives pass", "clean", 0, "no forbidden identifier"),
    (
        "an identifier in the package is refused in the wheel",
        "dirty_wheel",
        1,
        "wheel: pkg/core.py",
    ),
    (
        "an identifier only in the test tree is refused in the sdist",
        "dirty_sdist_tests",
        1,
        "sdist: tests/test_core.py",
    ),
    (
        "an identifier tracked in the test tree is refused in the tree scan",
        "dirty_tree_tests",
        1,
        "tracked: tests/test_core.py",
    ),
    (
        "an identifier three directories deep is refused",
        "dirty_deep_tree",
        1,
        "tracked: tests/unit/inner/test_deep.py",
    ),
    (
        "an identifier inside a dot-directory is refused",
        "dirty_dot_dir",
        1,
        "tracked: .ci/steps.yml",
    ),
    (
        "an identifier in an UNTRACKED but not ignored file is refused",
        "dirty_untracked",
        1,
        "tracked: pkg/scratch.py",
    ),
    (
        "an identifier below line 1 is refused",
        "dirty_below_line_one",
        1,
        "pkg/core.py:6",
    ),
    (
        "a UTF-16 payload is decoded and refused",
        "dirty_utf16",
        1,
        "wheel: pkg/notes.md",
    ),
    (
        "a text payload with one stray NUL is still scanned and refused",
        "dirty_stray_nul",
        1,
        "wheel: pkg/notes.md",
    ),
    (
        "an identifier in the PATH is refused even with clean content",
        "dirty_path",
        1,
        "in the PATH itself",
    ),
    (
        "a commit-trailer email local part is caught by the trailing wildcard",
        "dirty_trailer",
        1,
        "the author's given name",
    ),
    (
        "the institution in its spaced prose form is caught",
        "dirty_spaced",
        1,
        "an institution name",
    ),
    ("a surname in a citation is caught", "dirty_cite", 1, "the author's family name"),
    (
        "a genuinely binary payload is counted, not scanned",
        "clean",
        0,
        "undecodable 1",
    ),
    (
        "a tracked file absent from the checkout is refused, not noted",
        "unreadable",
        1,
        "could not be read",
    ),
    (
        "an empty repository is refused rather than reported clean",
        "empty_repo",
        1,
        "no files at all",
    ),
    (
        "derived metadata is exempt by SHAPE, a misplaced copy is not",
        "misplaced_metadata",
        1,
        "wheel: pkg/METADATA",
    ),
    (
        "the dist-info licenses exemption does not reach nested content",
        "nested_license",
        1,
        "licenses/notes/secret.py",
    ),
    # COORD-17, added at 0.2.18. The measured shape: a src-layout project's
    # egg-info sits at src/<name>.egg-info/, the root-anchored pattern could
    # not span the separator, and one real repository carried 7 permanent
    # false findings in a set it is not allowed to narrow locally.
    (
        "a src-layout egg-info is exempt at its own depth",
        "src_layout_egg_info",
        0,
        "no forbidden identifier",
    ),
    # The other side of the same widening, so nobody widens it further on
    # principle: what moved is where the egg-info DIRECTORY may sit, not what
    # a path may end in.
    (
        "an arbitrary path ending in PKG-INFO is still a finding",
        "misplaced_pkg_info",
        1,
        "sdist: tests/PKG-INFO",
    ),
    (
        "the sdist root prefix is stripped, so exemptions still match",
        "clean",
        0,
        "no forbidden identifier",
    ),
    (
        "an sdist member whose name holds a backslash is refused",
        "backslash_member",
        1,
        "contains a backslash",
    ),
    (
        "an exempt-tree matches a PREFIX and not any path segment",
        "segment_not_prefix",
        1,
        "tracked: src/docs/x.py",
    ),
    (
        "a wheel missing its floor path is refused",
        "wheel_floor_absent",
        1,
        "did not read it",
    ),
    (
        "a floor path PRESENT but not readable as text is refused",
        "wheel_floor_binary",
        1,
        "it was undecodable",
    ),
    (
        "an sdist missing its floor path is refused",
        "sdist_floor_absent",
        1,
        "did not read it",
    ),
    (
        "a second, stale wheel in the dist directory is a config error",
        "stale_wheel",
        2,
        "exactly one of each is required",
    ),
    ("a subtree passed as --tree is a config error", "subtree", 2, "is a SUBTREE"),
    ("an absent config is a config error", "no_config", 2, "no config at"),
    ("an unknown config key is a config error", "bad_key", 2, "is not a known setting"),
    (
        "an exempt-tree without a trailing slash is a config error",
        "bad_tree",
        2,
        "must name a subtree",
    ),
    (
        "an sdist floor inside one top-level tree is a config error",
        "narrow_floor",
        2,
        "at least TWO distinct top-level DIRECTORIES",
    ),
    (
        "an sdist floor of two ROOT FILES is a config error",
        "root_file_floor",
        2,
        "at least TWO distinct top-level DIRECTORIES",
    ),
    (
        "a floor entry that is also exempt is a config error",
        "exempt_floor",
        2,
        "named as a floor and is also exempt",
    ),
    (
        "a config with no archive floor is fine for a TREE-only run",
        "tree_only_no_floors",
        0,
        "NOT VERIFIED: what actually ships",
    ),
    ("a config with no wheel floor is a config error", "no_wheel_floor", 2, "no wheel-floor"),
    ("a config with no sdist floor is a config error", "no_sdist_floor", 2, "no sdist-floor"),
    (
        "a '#' inside a value does not silently broaden it",
        "hash_in_value",
        1,
        "tracked: docs/x.md",
    ),
    (
        "neither --tree nor --dist reads nothing and is refused",
        "no_boundary",
        2,
        "at least one of --tree and --dist",
    ),
]

_CONFIG_VARIANTS = {
    "bad_key": GOOD_CONFIG + "exempt-paths: LICENSE\n",
    "bad_tree": GOOD_CONFIG.replace("exempt-tree: docs/", "exempt-tree: docs"),
    "narrow_floor": GOOD_CONFIG.replace(
        "sdist-floor: tests/test_core.py", "sdist-floor: pkg/other.py"
    ),
    # Two ROOT FILES, neither of them exempt, so this case reaches the
    # two-directories rule instead of dying on the exempt-floor rule first.
    # It failed exactly that way when written with LICENSE and README.md, and
    # the fragment assertion is what caught it.
    "root_file_floor": GOOD_CONFIG.replace(
        "sdist-floor: pkg/core.py\nsdist-floor: tests/test_core.py",
        "sdist-floor: pyproject.toml\nsdist-floor: CHANGELOG.md",
    ),
    # The single line that turned a leaking artifact green before the loader
    # refused it: an exempt tree that swallows a named floor entry.
    "exempt_floor": GOOD_CONFIG + "exempt-tree: tests/\n",
    "no_wheel_floor": GOOD_CONFIG.replace("wheel-floor: pkg/core.py\n", ""),
    "no_sdist_floor": GOOD_CONFIG.replace(
        "sdist-floor: pkg/core.py\nsdist-floor: tests/test_core.py\n", ""
    ),
    # No archive floor at all, which is legitimate for a repository that
    # builds no wheel. The requirement lives at the boundary that uses it, so
    # this config is a config error for --dist and correct for --tree, and
    # both directions are cases.
    "tree_only_no_floors": (
        "exempt-path: LICENSE\nexempt-path: README.md\nexempt-tree: docs/\n"
    ),
    "hash_in_value": GOOD_CONFIG.replace(
        "exempt-tree: docs/", "exempt-tree: docs/#draft/"
    ),
}


def build_case(name: str, tmp: Path) -> list[str]:
    """The argv for one case, with its fixtures written."""
    config = tmp / "surface.conf"
    config.write_text(
        _CONFIG_VARIANTS.get(name, GOOD_CONFIG), encoding="utf-8", newline="\n"
    )

    if name == "clean":
        repo = make_repo(tmp, CLEAN_TREE)
        dist = make_dist(tmp, CLEAN_WHEEL, CLEAN_SDIST)
        return ["--config", str(config), "--tree", str(repo), "--dist", str(dist)]
    if name == "dirty_wheel":
        dist = make_dist(
            tmp, _replace(CLEAN_WHEEL, "pkg/core.py", DIRTY_DOCSTRING.encode()),
            CLEAN_SDIST,
        )
        return ["--config", str(config), "--dist", str(dist)]
    if name == "dirty_sdist_tests":
        # The recorded shape exactly: the package is clean, so a wheel-only or
        # a package-directory scan is green, and the sdist ships the tree.
        dist = make_dist(
            tmp, CLEAN_WHEEL,
            _replace(CLEAN_SDIST, "tests/test_core.py", DIRTY_DOCSTRING.encode()),
        )
        return ["--config", str(config), "--dist", str(dist)]
    if name == "dirty_below_line_one":
        dist = make_dist(
            tmp, _replace(CLEAN_WHEEL, "pkg/core.py", DIRTY_DEEP.encode()), CLEAN_SDIST
        )
        return ["--config", str(config), "--dist", str(dist)]
    if name == "dirty_utf16":
        dist = make_dist(
            tmp,
            _with(CLEAN_WHEEL, **{"pkg/notes.md": DIRTY_PROSE.encode("utf-16-le")}),
            CLEAN_SDIST,
        )
        return ["--config", str(config), "--dist", str(dist)]
    if name == "dirty_stray_nul":
        payload = b"\x00" + b"filler\n" * 2000 + DIRTY_PROSE.encode()
        dist = make_dist(
            tmp, _with(CLEAN_WHEEL, **{"pkg/notes.md": payload}), CLEAN_SDIST
        )
        return ["--config", str(config), "--dist", str(dist)]
    if name == "dirty_path":
        named = f"pkg/{_GIVEN.lower()}_notes.py"
        dist = make_dist(
            tmp, _with(CLEAN_WHEEL, **{named: CLEAN_TEXT.encode()}), CLEAN_SDIST
        )
        return ["--config", str(config), "--dist", str(dist)]
    if name == "src_layout_egg_info":
        # Exactly what `python -m build` leaves in the sdist of a src-layout
        # project, identifier and all: the metadata is DERIVED from the
        # authorship files, which is what the exemption is for.
        member = "src/pkg.egg-info/PKG-INFO"
        dist = make_dist(
            tmp, CLEAN_WHEEL,
            _with(CLEAN_SDIST, **{member: f"Author: {_GIVEN} {_FAMILY}\n".encode()}),
        )
        return ["--config", str(config), "--dist", str(dist)]
    if name == "misplaced_pkg_info":
        dist = make_dist(
            tmp, CLEAN_WHEEL,
            # NOT under docs/, which this config exempts as a tree: the case
            # has to reach the pattern rather than the exemption set.
            _with(CLEAN_SDIST, **{"tests/PKG-INFO": DIRTY_PROSE.encode()}),
        )
        return ["--config", str(config), "--dist", str(dist)]
    if name == "nested_license":
        nested = "pkg-1.0.0.dist-info/licenses/notes/secret.py"
        dist = make_dist(
            tmp, _with(CLEAN_WHEEL, **{nested: DIRTY_DOCSTRING.encode()}), CLEAN_SDIST
        )
        return ["--config", str(config), "--dist", str(dist)]
    if name == "backslash_member":
        dist = make_dist(
            tmp, CLEAN_WHEEL, CLEAN_SDIST,
            raw_sdist_member=(
                "docs" + BACKSLASH + "x.md", DIRTY_PROSE.encode()
            ),
        )
        return ["--config", str(config), "--dist", str(dist)]
    if name == "wheel_floor_absent":
        thin = {k: v for k, v in CLEAN_WHEEL.items() if k != "pkg/core.py"}
        dist = make_dist(tmp, thin, CLEAN_SDIST)
        return ["--config", str(config), "--dist", str(dist)]
    if name == "wheel_floor_binary":
        # The floor entry is in the archive and is not text, so it is
        # ACCOUNTED but not SCANNED. This is the only shape that separates
        # "the floor was read" from "the floor was present", now that a config
        # may no longer exempt its own floor.
        dist = make_dist(
            tmp,
            _replace(CLEAN_WHEEL, "pkg/core.py", bytes(range(256)) * 8),
            CLEAN_SDIST,
        )
        return ["--config", str(config), "--dist", str(dist)]
    if name == "sdist_floor_absent":
        thin = {k: v for k, v in CLEAN_SDIST.items() if k != "tests/test_core.py"}
        dist = make_dist(tmp, CLEAN_WHEEL, thin)
        return ["--config", str(config), "--dist", str(dist)]
    if name == "stale_wheel":
        dist = make_dist(tmp, CLEAN_WHEEL, CLEAN_SDIST, extra_wheel=True)
        return ["--config", str(config), "--dist", str(dist)]
    if name == "misplaced_metadata":
        dist = make_dist(
            tmp,
            _with(CLEAN_WHEEL, **{"pkg/METADATA": f"By {_GIVEN} {_FAMILY}\n".encode()}),
            CLEAN_SDIST,
        )
        return ["--config", str(config), "--dist", str(dist)]

    # ---- tree-only cases
    tree_files = {
        "dirty_tree_tests": _replace(
            CLEAN_TREE, "tests/test_core.py", DIRTY_DOCSTRING.encode()
        ),
        "dirty_deep_tree": _replace(
            CLEAN_TREE, "tests/unit/inner/test_deep.py", DIRTY_DOCSTRING.encode()
        ),
        "dirty_dot_dir": _replace(CLEAN_TREE, ".ci/steps.yml", DIRTY_PROSE.encode()),
        "dirty_trailer": _replace(CLEAN_TREE, "pkg/core.py", DIRTY_TRAILER.encode()),
        "dirty_spaced": _replace(CLEAN_TREE, "pkg/core.py", DIRTY_PROSE.encode()),
        "dirty_cite": _replace(CLEAN_TREE, "pkg/core.py", DIRTY_CITE.encode()),
        "segment_not_prefix": _with(
            CLEAN_TREE, **{"src/docs/x.py": DIRTY_PROSE.encode()}
        ),
        "hash_in_value": _with(CLEAN_TREE, **{"docs/x.md": DIRTY_PROSE.encode()}),
    }
    if name in tree_files:
        repo = make_repo(tmp, tree_files[name])
        return ["--config", str(config), "--tree", str(repo)]
    if name == "dirty_untracked":
        repo = make_repo(
            tmp, CLEAN_TREE, untracked={"pkg/scratch.py": DIRTY_DOCSTRING.encode()}
        )
        return ["--config", str(config), "--tree", str(repo)]
    if name == "unreadable":
        repo = make_repo(tmp, CLEAN_TREE, delete_after_add="tests/test_core.py")
        return ["--config", str(config), "--tree", str(repo)]
    if name == "empty_repo":
        repo = make_repo(tmp, {}, empty=True)
        return ["--config", str(config), "--tree", str(repo)]
    if name == "subtree":
        repo = make_repo(tmp, CLEAN_TREE)
        return ["--config", str(config), "--tree", str(repo / "pkg")]
    if name == "no_config":
        repo = make_repo(tmp, CLEAN_TREE)
        return ["--config", str(tmp / "absent.conf"), "--tree", str(repo)]
    if name in ("no_wheel_floor", "no_sdist_floor"):
        # Through --dist, because that is the boundary the floors belong to.
        dist = make_dist(tmp, CLEAN_WHEEL, CLEAN_SDIST)
        return ["--config", str(config), "--dist", str(dist)]
    if name in _CONFIG_VARIANTS:
        repo = make_repo(tmp, CLEAN_TREE)
        return ["--config", str(config), "--tree", str(repo)]
    if name == "no_boundary":
        return ["--config", str(config)]
    raise KeyError(name)


def check(checker: Path) -> list[str]:
    failures: list[str] = []
    for label, name, expected, fragment in CASES:
        tmp = Path(tempfile.mkdtemp(prefix="surface-"))
        try:
            done = run(checker, *build_case(name, tmp))
            output = (done.stdout + done.stderr).decode(errors="replace")
            if done.returncode != expected:
                failures.append(
                    f"{label}: exit {done.returncode}, expected {expected}\n"
                    f"    {output.strip()[:400]}"
                )
            elif fragment not in output:
                failures.append(
                    f"{label}: exit {expected} as expected, but the output "
                    f"never said {fragment!r}, so it may be right for the "
                    f"wrong reason\n    {output.strip()[:400]}"
                )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return failures


# ---- the mutants -----------------------------------------------------------


def _drop_a_token(src: str) -> str:
    """Forget the family name."""
    return src.replace(
        '    (re.compile(rf"\\b{_FAMILY}\\w*", re.IGNORECASE), '
        '"the author\'s family name"),\n',
        "",
        1,
    )


def _drop_trailing_wildcard(src: str) -> str:
    """Match the bare name, so an email local part slips through."""
    return src.replace(rf'rf"\b{{_GIVEN}}\w*"', rf'rf"\b{{_GIVEN}}\b"', 1)


def _institution_exact_only(src: str) -> str:
    """Accept only the run-together spelling, not the prose one."""
    return src.replace(
        r'rf"\b{_INSTITUTION[:2]}[ _-]?{_INSTITUTION[2:]}\b"',
        r'rf"\b{_INSTITUTION}\b"',
        1,
    )


def _exempt_by_basename(src: str) -> str:
    """Exempt derived metadata by name rather than by shape."""
    return src.replace(
        "    return any(pattern.fullmatch(posix) for pattern in DERIVED_METADATA)",
        "    return posix.rsplit('/', 1)[-1] in {'PKG-INFO', 'METADATA', 'LICENSE'}",
        1,
    )


def _licenses_reach_nested(src: str) -> str:
    """Let the licenses exemption swallow a whole subtree again."""
    return src.replace(
        r'    re.compile(r"[^/]+\.dist-info/licenses/[^/]+"),',
        r'    re.compile(r"[^/]+\.dist-info/licenses/.+"),',
        1,
    )


def _egg_info_at_root_only(src: str) -> str:
    """Anchor the egg-info exemption at the archive root again.

    This is COORD-17 itself, restored: `[^/]+` cannot span a separator, so a
    src-layout project's `src/<name>.egg-info/PKG-INFO` is scanned and every
    build reports the same finding for ever.
    """
    return src.replace(
        r'    re.compile(r"(?:[^/]+/)*[^/]+\.egg-info/PKG-INFO"),',
        r'    re.compile(r"[^/]+\.egg-info/PKG-INFO"),',
        1,
    )


def _egg_info_over_wide(src: str) -> str:
    """Widen the same exemption to anything ending in PKG-INFO.

    The opposite failure, and the one a reader is most likely to introduce
    while fixing the first: dropping the `.egg-info/` segment exempts any file
    with that basename anywhere, which is the exempt-by-name shape this table
    is written by SHAPE to avoid.
    """
    return src.replace(
        r'    re.compile(r"(?:[^/]+/)*[^/]+\.egg-info/PKG-INFO"),',
        r'    re.compile(r".*PKG-INFO"),',
        1,
    )


def _keep_the_sdist_prefix(src: str) -> str:
    """Leave the distribution root on every sdist member."""
    return src.replace(
        '                    yield member.name.split("/", 1)[-1], handle.read()',
        "                    yield member.name, handle.read()",
        1,
    )


def _floor_is_presence(src: str) -> str:
    """Satisfy a floor by the file being PRESENT rather than READ.

    This is the defect that let one added config line turn an artifact
    carrying fourteen identifiers green on both boundaries.
    """
    return src.replace(
        "        if entry not in result.scanned:",
        "        if entry not in result.accounted():",
        1,
    )


def _coverage_counts_itself(src: str) -> str:
    """Measure coverage against the scan's own output instead of the inventory.

    The instrument counting itself. This was a real defect in the first version
    of this checker and it is kept as a mutant rather than described in a
    comment, because a described defect regresses silently and a mutant does
    not.
    """
    return src.replace(
        "    dropped = sorted(set(inventory) - result.accounted() - set(also_accounted))",
        "    dropped = sorted(set(result.scanned) - result.accounted())",
        1,
    )


def _drop_char_accounting(src: str) -> str:
    """Stop comparing characters decoded against characters examined."""
    return src.replace(
        "    if newlines < 0 or newlines > result.decoded_chars // 2:",
        "    if False:",
        1,
    )


def _first_line_only(src: str) -> str:
    """Examine only the first line of every file."""
    return src.replace(
        "        for lineno, line in enumerate(text.splitlines(), start=1):",
        "        for lineno, line in enumerate(text.splitlines()[:1], start=1):",
        1,
    )


def _one_file_per_component(src: str) -> str:
    """Open one file per top-level component, which an earlier floor allowed."""
    return src.replace(
        "    for name in inventory:\n",
        "    seen_top = set()\n"
        "    for name in inventory:\n"
        "        top = name.split('/', 1)[0]\n"
        "        if top in seen_top:\n"
        "            continue\n"
        "        seen_top.add(top)\n",
        1,
    )


def _drop_root_files(src: str) -> str:
    """Skip every file at the repository root.

    No case plants an identifier in a root file, and the two root files that
    DO carry one are exempt by config, so the offender scan cannot notice this
    narrowing at all. Only the coverage comparison can, which is what makes it
    the right narrowing for the control pair below.
    """
    return src.replace(
        "    for name in inventory:\n",
        "    for name in [n for n in inventory if '/' in n]:\n",
        1,
    )


def _truncate_long_files(src: str) -> str:
    """Examine only the first 20000 characters of each file.

    Every planted identifier in this fixture set sits well inside that, so no
    case's offender scan changes. The large clean fixture is what makes it
    visible, and only through the character counters.
    """
    return src.replace(
        "        for lineno, line in enumerate(text.splitlines(), start=1):",
        "        for lineno, line in enumerate(text[:20000].splitlines(), start=1):",
        1,
    )


def _narrow_by_depth(src: str) -> str:
    """Skip anything more than one directory deep."""
    return src.replace(
        "    for name in inventory:\n",
        "    for name in [n for n in inventory if n.count('/') < 2]:\n",
        1,
    )


def _skip_dot_dirs(src: str) -> str:
    """Skip dot-directories, which a walk written for a package would."""
    return src.replace(
        "    for name in inventory:\n",
        "    for name in [n for n in inventory if not n.startswith('.')]:\n",
        1,
    )


def _tracked_only(src: str) -> str:
    """Drop untracked-but-not-ignored files from the inventory."""
    return src.replace(
        '    for extra in ([], ["--others", "--exclude-standard"]):\n',
        "    for extra in ([],):\n",
        1,
    )


def _empty_inventory_is_clean(src: str) -> str:
    """Let a repository git reports nothing for pass."""
    return src.replace("    if not inventory:", "    if False and not inventory:", 1)


def _unreadable_is_a_note(src: str) -> str:
    """Report an unreadable tracked path and certify the run anyway."""
    return src.replace(
        "    if unreadable:\n        # A hole in the coverage",
        "    if False and unreadable:\n        # A hole in the coverage",
        1,
    )


def _nul_means_binary(src: str) -> str:
    """Classify any NUL-bearing payload as binary, discarding UTF-16 whole."""
    return src.replace(
        '    if content[:2] in (b"\\xff\\xfe", b"\\xfe\\xff"):',
        '    if b"\\x00" in content[:8192]:\n        return None\n'
        '    if content[:2] in (b"\\xff\\xfe", b"\\xfe\\xff"):',
        1,
    )


def _skip_the_path(src: str) -> str:
    """Scan content only, so a file NAMED after the author travels."""
    return src.replace(
        "        for pattern, label in FORBIDDEN:\n"
        "            if pattern.search(relpath):\n",
        "        for pattern, label in ():\n"
        "            if pattern.search(relpath):\n",
        1,
    )


def _normalize_archive_backslash(src: str) -> str:
    """Accept a backslash member and rewrite it into a directory again."""
    return src.replace('        if "\\\\" in name\n', "        if False\n", 1)


def _exempt_tree_by_segment(src: str) -> str:
    """Match an exempt tree anywhere in the path rather than as a prefix."""
    return src.replace(
        "    if config.exempt_trees and posix.startswith(config.exempt_trees):",
        "    if config.exempt_trees and any(t in posix for t in config.exempt_trees):",
        1,
    )


def _comment_anywhere(src: str) -> str:
    """Strip at any '#', silently broadening a value that contains one."""
    return src.replace(
        '        line = _strip_comment(raw).strip()',
        '        line = raw.split("#", 1)[0].strip()',
        1,
    )


def _floor_may_be_exempt(src: str) -> str:
    """Allow an exemption to swallow a floor entry."""
    return src.replace(
        "        if is_authorship(entry, config):", "        if False:", 1
    )


def _root_files_are_components(src: str) -> str:
    """Count a root-level file as a top-level component again."""
    return src.replace(
        "        if sep and head:", "        if head:", 1
    )


def _accept_any_config(src: str) -> str:
    """Let a floor that names one tree through."""
    return src.replace(
        "    if config.sdist_floor and len(_top_level_dirs(config.sdist_floor)) < 2:",
        "    if False:",
        1,
    )


def _archive_floor_optional(src: str) -> str:
    """Read an archive and assert nothing about what was read."""
    return src.replace("        if not floor:", "        if False:", 1)


def _floors_required_at_load(src: str) -> str:
    """Demand archive floors before knowing whether an archive will be read.

    Not a weakening of the scan; a weakening of who the guard can serve. It
    locks out a repository that builds no wheel, which has to invent a floor
    for an archive it never produces. The tree-only case is what catches it.
    """
    return src.replace(
        "    if config.sdist_floor and len(_top_level_dirs(config.sdist_floor)) < 2:",
        "    if not config.wheel_floor or not config.sdist_floor:\n"
        '        raise ConfigError(f"{path}: no wheel-floor and no sdist-floor")\n'
        "    if config.sdist_floor and len(_top_level_dirs(config.sdist_floor)) < 2:",
        1,
    )


def _subtree_is_fine(src: str) -> str:
    """Scan whatever root it was handed."""
    return src.replace("    if resolved_top != root.resolve():", "    if False:", 1)


def _config_error_passes(src: str) -> str:
    """Turn an unrunnable check into a clean tree."""
    return src.replace(
        '        print(f"CONFIG ERROR: {exc}", file=sys.stderr)\n        return 2',
        '        print(f"CONFIG ERROR: {exc}", file=sys.stderr)\n        return 0',
        1,
    )


MUTANTS = {
    "forget one token in the table": _drop_a_token,
    "drop the trailing wildcard on a name": _drop_trailing_wildcard,
    "match only the run-together institution spelling": _institution_exact_only,
    "exempt derived metadata by basename instead of by shape": _exempt_by_basename,
    "let the licenses exemption reach nested content": _licenses_reach_nested,
    "anchor the egg-info exemption at the archive root": _egg_info_at_root_only,
    "exempt anything whose name ends in PKG-INFO": _egg_info_over_wide,
    "leave the distribution root on sdist member paths": _keep_the_sdist_prefix,
    "satisfy a floor by presence instead of by having read it": _floor_is_presence,
    "examine only the first line of every file": _first_line_only,
    "open one file per top-level component": _one_file_per_component,
    "skip anything more than one directory deep": _narrow_by_depth,
    "skip every file at the repository root": _drop_root_files,
    "examine only the first 20000 characters of a file": _truncate_long_files,
    "skip dot-directories": _skip_dot_dirs,
    "drop untracked but not ignored files": _tracked_only,
    "let an empty inventory pass": _empty_inventory_is_clean,
    "report an unreadable tracked path and certify anyway": _unreadable_is_a_note,
    "treat any NUL-bearing payload as binary": _nul_means_binary,
    "scan content only, never the path": _skip_the_path,
    "normalize a backslash in an archive member": _normalize_archive_backslash,
    "match an exempt tree by segment instead of by prefix": _exempt_tree_by_segment,
    "strip a comment at any '#'": _comment_anywhere,
    "allow an exemption to swallow a floor entry": _floor_may_be_exempt,
    "count a root file as a top-level component": _root_files_are_components,
    "accept a floor that names one tree": _accept_any_config,
    "read an archive and assert nothing about it": _archive_floor_optional,
    "demand archive floors before knowing an archive will be read": _floors_required_at_load,
    "scan whatever root it was handed": _subtree_is_fine,
    "let a configuration error exit 0": _config_error_passes,
}


#: (label, the narrowing, the accounting removed with it).
#:
#: Two of this checker's defences cannot be observed on their own, and saying
#: so is better than a mutant list that implies they can. Removing the coverage
#: comparison changes no verdict while nothing is narrowing, and removing the
#: character counters changes no verdict while every file is read whole. What
#: is observable is the PAIR: the narrowing alone must be DENIED, and the same
#: narrowing with its detector removed must SURVIVE.
#:
#: That pair is the evidence, and it is the only honest form of it. A mutant
#: asserted to survive is not a weaker test than one asserted to die; it is the
#: test of whether the detector is what did the detecting.
CONTROL_PAIRS = [
    (
        "coverage measured against the scan's own output",
        _drop_root_files,
        _coverage_counts_itself,
    ),
    (
        "characters decoded never compared against examined",
        _truncate_long_files,
        _drop_char_accounting,
    ),
]


def mutate(src: str, mutant, tmp: Path) -> Path:
    mutated = mutant(src)
    if mutated == src:
        raise RuntimeError(
            f"{mutant.__name__} changed nothing, so it proves nothing. The "
            f"checker's source moved and this mutant's anchor text no longer "
            f"appears in it."
        )
    path = tmp / "mutant_check_shipped_surface.py"
    path.write_text(mutated, encoding="utf-8", newline="\n")
    return path


def denied_by(checker: Path) -> str | None:
    """The first case-contract this build breaks, or None if it holds them all.

    The contract is the exit code AND the fragment, the same pair `check` uses.
    Comparing exit codes alone was too coarse in both directions. It let pure
    vandalism, a mutant that merely crashes, count as detection; and it let a
    mutant survive when a LATER rule happened to produce the same exit code for
    a different reason, which is a guard reporting the wrong cause and being
    scored as if it had reported the right one.
    """
    for label, name, expected, fragment in CASES:
        fixtures = Path(tempfile.mkdtemp(prefix="surface-fix-"))
        try:
            done = run(checker, *build_case(name, fixtures))
            output = (done.stdout + done.stderr).decode(errors="replace")
            if "Traceback (most recent call last)" in output:
                return f"CRASHED on {name}, which is not detection"
            if done.returncode != expected or fragment not in output:
                return label
        finally:
            shutil.rmtree(fixtures, ignore_errors=True)
    return None


def main(argv: list[str]) -> int:
    if argv:
        print("usage: check_shipped_surface_mutations.py", file=sys.stderr)
        return 2
    if not CHECKER.is_file():
        print(f"CONFIG ERROR: no checker beside this file at {CHECKER}", file=sys.stderr)
        return 2
    src = CHECKER.read_text(encoding="utf-8")

    failures = check(CHECKER)
    if failures:
        print(f"FAILED: {len(failures)} of {len(CASES)} cases", file=sys.stderr)
        for entry in failures:
            print(f"  {entry}", file=sys.stderr)
        return 1
    print(f"shipped-surface contracts hold: {len(CASES)} cases on real archives")

    survived: list[str] = []
    crashed: list[str] = []
    for label, mutant in MUTANTS.items():
        tmp = Path(tempfile.mkdtemp(prefix="surface-mut-"))
        try:
            verdict = denied_by(mutate(src, mutant, tmp))
            if verdict is None:
                survived.append(label)
            elif verdict.startswith("CRASHED"):
                crashed.append(f"{label}: {verdict}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    if survived or crashed:
        print(
            f"FAILED: {len(survived)} mutant(s) survived, {len(crashed)} only "
            f"crashed",
            file=sys.stderr,
        )
        for label in survived:
            print(f"  survived: {label}", file=sys.stderr)
        for label in crashed:
            print(f"  crashed:  {label}", file=sys.stderr)
        return 1
    print(f"all {len(MUTANTS)} mutants denied, none merely by crashing")

    for label, narrowing, remove_detector in CONTROL_PAIRS:
        tmp = Path(tempfile.mkdtemp(prefix="surface-ctl-"))
        try:
            both = mutate(src, lambda s: remove_detector(narrowing(s)), tmp)
            if denied_by(both) is not None:
                print(
                    f"FAILED control: with {label}, the narrowing it hides was "
                    f"still caught. That is not a pass. Something other than "
                    f"the detector is refusing it, so the evidence that the "
                    f"detector is load bearing no longer exists. Re-read the "
                    f"pair before changing it.",
                    file=sys.stderr,
                )
                return 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(
        f"{len(CONTROL_PAIRS)} control pair(s): each narrowing above is caught "
        f"by its own detector and passes once that detector is removed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
