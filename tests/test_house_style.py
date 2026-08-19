"""Tier 1: house-style guards that apply to the whole repository.

No em dash (U+2014) or en dash (U+2013) characters in Markdown or Python
files, per the project style. Binary and local-only content guards run in
pre-commit and in the CI guard job.
"""

import importlib.util
import re
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest

# The hash-pinned vendored kit population and the ONE definition of where a
# vendored body begins. Imported rather than re-derived: the private-ledger
# ratchet at the foot of this file counts the provenance HEADER of these
# files and not their body, and if the two modules disagreed about that line
# the exemption would silently move (OPS-2010.15).
from test_kit_drift import MANIFEST as KIT_MANIFEST
from test_kit_drift import _read_lf, _split_at_marker

REPO_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    "_private",
    "site",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}

#: The one directory skipped by ABSOLUTE PREFIX rather than by name.
#:
#: A review's isolated worktree is a full second copy of the tree, under
#: .claude/worktrees/. Walking it doubles every check, and an abandoned
#: one (the removal fails on Windows while a handle is open) would report
#: offenders against a path nobody edits.
#:
#: IT WAS A NAME IN `SKIP_DIRS` UNTIL 2026-08-19 and that made this walk
#: blank ITSELF. Inside a worktree every path carries the component
#: `worktrees`, so the walk yielded ZERO files and all three guards built
#: on it passed over anything: a QA pass proved it by writing an em dash
#: and the forbidden employer name into README.md and watching them pass.
#: The guards were off in exactly the environment the review process
#: uses. A prefix cannot do that, because it is anchored at this tree's
#: own root.
WORKTREE_ROOT = (REPO_ROOT / ".claude" / "worktrees").resolve()
# Built from codepoints so this file itself stays free of the characters.
FORBIDDEN = {chr(0x2013): "en dash", chr(0x2014): "em dash"}
# Built by concatenation so this file itself stays free of the words:
# the repository never names the author's employer or internal
# predecessor toolchains (CLAUDE.md invariant 5).
FORBIDDEN_WORDS = ("Embr" + "aer", "fts_" + "horse")


def iter_style_checked_files():
    # YAML joined the list on 2026-08-06. The command database is the
    # largest English prose surface in this repository, roughly 900 lines
    # of notes across the chapter files, and invariants 5 and 6 did not
    # reach a line of it: the walk read *.md and *.py only. Nothing was
    # in violation when it was widened, which is the cheap moment to do
    # it rather than the moment it would have caught something.
    for pattern in ("*.md", "*.py", "*.yaml"):
        for path in REPO_ROOT.rglob(pattern):
            if SKIP_DIRS.intersection(path.parts):
                continue
            if WORKTREE_ROOT in path.resolve().parents:
                continue
            yield path


#: The walk's own floor. Three guards subtract from it and none of them
#: asserted it had anything to subtract from, which is how a collapse to
#: zero read as a clean tree. Measured 2026-08-19 at 470 files; the floor
#: is set well below so ordinary work never moves it and a collapse
#: cannot hide.
STYLE_WALK_FLOOR = 300


def test_the_style_walk_has_something_to_check():
    """The guard on the three guards, and it is not hypothetical.

    Until 2026-08-19 this walk yielded ZERO files inside a reviewer
    worktree, because it skipped by path component and a worktree lives
    under a directory of that name. Invariants 5 and 6 were unenforced
    there and nothing said so: each of the three consumers iterates the
    walk and asserts per file, so an empty walk satisfies all of them.
    """
    walked = list(iter_style_checked_files())
    assert len(walked) >= STYLE_WALK_FLOOR, (
        f"the style walk yielded {len(walked)} files against a floor of "
        f"{STYLE_WALK_FLOOR}. Every guard built on it subtracts from this "
        "population, so a collapse makes all three pass over a tree nobody "
        f"checked. Walk root: {REPO_ROOT}"
    )
    # And it must reach the two surfaces the invariants are about, not
    # merely count to the floor on one of them.
    suffixes = {path.suffix for path in walked}
    assert {".md", ".py", ".yaml"} <= suffixes, (
        f"the walk reached only {sorted(suffixes)}; invariants 5 and 6 cover the "
        "command database (yaml) and the prose (md) as well as the code"
    )


def test_no_em_or_en_dashes():
    offenders = []
    for path in iter_style_checked_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for char, name in FORBIDDEN.items():
            if char in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: contains {name}")
    assert not offenders, "\n".join(offenders)


def test_no_private_names():
    offenders = []
    for path in iter_style_checked_files():
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for word in FORBIDDEN_WORDS:
            if word.lower() in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: names {word}")
    assert not offenders, "\n".join(offenders)


# The session documents (state file, handoffs, logbook, inbox, progress
# reports) left `_private/` for the coordination hub on 2026-07-27 and are
# located by PYFS_SESSION_ROOT. Nothing enforced that move: it was five
# documents edited by hand, and a later edit re-hardcoding a retired path
# would be invisible until a session wrote its handoff into a folder that
# no longer exists. This guard is the mechanism that migration lacked.
#
# `archive` is deliberately ABSENT from this list. Two folders share that
# name across the boundary: the session root has one (the migrated inbox
# history) and this repository keeps `_private/archive/` for the superseded
# plan table, which the `plan` skill still cites correctly. Forbidding the
# name outright would fail a legitimate path.
MIGRATED_SESSION_DIRS = ("STATUS.md", "logbook.csv", "handoffs", "inbox", "progress")
# Both separators. The backslash spelling is the MORE likely mistake on this
# machine, because a PowerShell block in a skill writes paths that way, and it
# produces the identical defect.
MIGRATED_PATH = re.compile(
    r"_private[/\\](" + "|".join(re.escape(name) for name in MIGRATED_SESSION_DIRS) + r")\b"
)

# No exemption list. The nine vendored kit bodies were exempted here at first,
# defensively, and the exemption was then verified to be unnecessary: none of
# them names a migrated session path. The stale prose they DO carry is
# `_private/kit`, which is not on the list above. A permanently silenced push
# gate is worse than a hypothetical future conflict, so the silence was
# removed. If a re-vendor ever does introduce one of these paths into a kit
# body, this guard should fire and the fix belongs in the kit.


# Personal-identifier guard, added 2026-07-28 with the kit 0.2.4 re-vendor.
#
# Why it exists: `.claude/tools/snap.sh` set the private snapshot repositories'
# git identity from two literals, a full name and a personal email address, and
# located a tree by an absolute path under a personal user profile. That file is
# TRACKED and this remote is public, so a hashed kit body published an email
# address. The kit promotion removed the instance. This guard is the other half
# the structural-fix rule requires, because without it the same literal reaching
# any tracked file is undetectable: `iter_style_checked_files` yields `*.md` and
# `*.py` only, so the file that actually leaked was outside every house-style
# guard by file type, and the drift test pins bytes rather than content.
#
# What is deliberately NOT guarded: the author's NAME. It appears by intention
# in LICENSE, CITATION.cff, pyproject.toml, the SRS and the guide, because she
# publishes under it. Guarding a string that is meant to be published would need
# an allow-list long enough to be its own maintenance defect. An email address
# and a user-profile path have no legitimate home in this tree at all, which is
# what makes them checkable without one.
#
# Scope is TRACKED files, from `git ls-files`, not a worktree walk. The
# gitignored `.claude/settings.local.json` legitimately holds the profile path
# (it is the documented home for machine configuration) and a worktree walk
# would fail on it.
_AT = chr(64)
# A dotted top-level domain is REQUIRED, which is what separates an address
# from a version pin: `actions/checkout@v4` and `gh-action-pypi-publish@release`
# are the shape without it, and the workflows are full of them now that this
# guard scans every tracked file rather than only Markdown and Python.
MAIL_SHAPE = re.compile(
    r"[A-Za-z0-9._%+-]+" + _AT + r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)
# Reserved documentation domains (RFC 2606) and the loopback host: they name
# no person. `noreply` is a LOCAL part, not a host, and is listed separately
# because putting it among the hosts is a bug that lets nothing through and
# looks like it works.
IMPERSONAL_MAIL_HOSTS = ("example.com", "example.org", "example.net", "localhost")
# The RESERVED TOP-LEVEL NAMES of the same RFC, matched as a suffix because a
# reserved TLD reserves everything under it. The comment above has claimed
# "RFC 2606" since this guard was written and the tuple implemented four of
# its names while omitting the other four, which is a claim wider than the
# code; completed on 2026-08-11.
#
# It was found the way these things are found. PFS-12 vendored
# `role_review_gate_mutations.py` and `prepush_receipt_mutations.py`, which
# set a throwaway git identity in a temp repository from `gate@example.invalid`
# and `kit@example.invalid`, and this guard called both personal identifiers.
#
# WHAT WAS NOT DONE, because the sister library's precedent pointed at it: the
# vendored directories were NOT exempted wholesale. This guard exists because a
# vendored kit body published a real name, a real address and a real
# user-profile path on this public remote, so the vendored tree is the exact
# place it must keep watching. Exempting it to clear two RFC-reserved
# non-addresses would have blinded the guard where it was born. A drift-pinned
# body still cannot be hand-edited here; the answer was to make the detector
# right rather than to make its scope smaller.
IMPERSONAL_MAIL_TLDS = (".invalid", ".test", ".example", ".localhost")
IMPERSONAL_MAIL_USERS = ("noreply", "no-reply")
# `/Users/<name>`, `\Users\<name>` and the Windows environment form. The
# separator class covers both spellings for the reason MIGRATED_PATH gives.
# Assembled from fragments, like FORBIDDEN and FORBIDDEN_WORDS above, so that
# this file does not itself carry the literals it forbids: the guard scans
# every tracked file and would otherwise be its own only offender.
PROFILE_PATH_SHAPE = re.compile(
    r"[/\\][Uu]sers[/\\][A-Za-z0-9._-]+|%" + "USER" + "PROFILE%", re.IGNORECASE
)


def _identifier_offenses(text: str) -> list[str]:
    """Return the personal identifiers in ``text``, or an empty list.

    Factored out of the tree scan so the guard can be falsified directly:
    :func:`test_the_identifier_guard_fires_on_what_it_exists_to_catch` feeds it
    the exact shapes the 0.2.4 promotion removed and asserts it reports them.
    A guard whose own detection is never exercised is the class this
    repository keeps registering, so it is exercised here.
    """
    found = []
    for match in MAIL_SHAPE.finditer(text):
        address = match.group(0)
        user, _, host = address.partition(_AT)
        host = host.lower()
        if (
            host in IMPERSONAL_MAIL_HOSTS
            or host.endswith(IMPERSONAL_MAIL_TLDS)
            or user.lower() in IMPERSONAL_MAIL_USERS
        ):
            continue
        found.append(f"an email address ({address})")
    for match in PROFILE_PATH_SHAPE.finditer(text):
        found.append(f"a user-profile path ({match.group(0)})")
    return found


def _tracked_files() -> list[Path]:
    """Every tracked file, from git itself.

    Fails rather than skips when git cannot answer: a guard that reports
    nothing when it cannot run is worse than no guard, because it reports
    green. That failure mode is the one this repository has registered most.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "the personal-identifier guard could not list tracked files "
        f"(git exited {result.returncode}: {result.stderr.strip()}). It scans what is "
        "COMMITTED, so it needs git; a skip here would report green over an unscanned tree."
    )
    files = [REPO_ROOT / name for name in result.stdout.split("\0") if name]
    # A FLOOR, added 2026-08-12, because "git could not run" was never the only
    # way to scan nothing. A QA pass ran this guard with GIT_DIR pointing at a
    # throwaway repository: git exited 0, returned a handful of paths that are
    # not this tree's, and the test PASSED having examined none of the files it
    # exists to examine. That is the false green the assertion above is worded
    # against, arriving through the one door it does not watch, and GIT_DIR is
    # set by ordinary things (`git rebase -x`, any hook, any wrapper).
    assert len(files) > 300, (
        f"git listed {len(files)} tracked files under {REPO_ROOT}, far below "
        "this repository's real size. GIT_DIR or GIT_WORK_TREE is pointing git "
        "at another tree, so this guard would report clean over a repository "
        "nobody asked about. Unset them and re-run."
    )
    return files


def test_no_personal_identifier_in_a_tracked_file():
    """No tracked file carries an email address or a user-profile path.

    The name is out of scope by decision (see the comment above): it is
    published deliberately. These two are not published deliberately anywhere.
    """
    offenders = []
    for path in _tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable: no literal to find
        for offense in _identifier_offenses(text):
            offenders.append(f"{path.relative_to(REPO_ROOT)}: contains {offense}")
    assert not offenders, (
        "a tracked file carries a personal identifier, and this remote is public:\n"
        + "\n".join(offenders)
        + "\n\nMachine-specific values belong in the gitignored "
        ".claude/settings.local.json, never in a committed file. If the file is a "
        "vendored kit body, the fix is a kit promotion at the coordination level, "
        "not an edit here."
    )


def test_the_identifier_guard_fires_on_what_it_exists_to_catch():
    """Mutation proof: the guard blocks the original failure when re-run.

    The structural-fix rule says a fix is not complete until it carries a guard
    that makes recurrence impossible AND the evidence that the guard blocks the
    original failure. These are the two shapes the kit 0.2.4 promotion removed
    from ``.claude/tools/snap.sh``, reconstructed here rather than quoted, so
    this file stays clean of them while still proving the detector fires.
    """
    address = "someone.personal" + _AT + "gmail.com"
    assert _identifier_offenses(f'config user.email "{address}"'), (
        "the guard does not detect a personal email address, which is the exact "
        "literal that reached the public remote"
    )
    # Assembled, never written literally, for the reason PROFILE_PATH_SHAPE gives.
    users = "Users"
    profiles = (
        "/c/" + users + "/someone/OneDrive/tree",
        "C:" + chr(92) + users + chr(92) + "someone",
        "%" + "USER" + "PROFILE%",
    )
    for profile in profiles:
        assert _identifier_offenses(f'BASE="{profile}"'), (
            f"the guard does not detect the user-profile path {profile!r}"
        )
    # A version pin is the mail shape without a dotted TLD and must not fire.
    for pin in ("actions/checkout" + _AT + "v4", "pypa/gh-action-pypi-publish" + _AT + "release"):
        assert not _identifier_offenses(pin), f"the guard false-positives on the action pin {pin!r}"
    # And it stays quiet on the impersonal forms the tree legitimately holds,
    # so it is a guard rather than a blanket refusal.
    for benign in (
        "user" + _AT + "example.com",
        "private-snapshot" + _AT + "localhost",
        "noreply" + _AT + "github.com",
        # The RFC 2606 reserved TLDs, added 2026-08-11 with the branch that
        # accepts them. Both of the first two are real literals from vendored
        # kit bodies (role_review_gate_mutations.py and
        # prepush_receipt_mutations.py set a throwaway git identity from them);
        # the rest are the remaining reserved names, asserted so the tuple is
        # exercised rather than trusted, since a name nobody tests is a name
        # that can be dropped without anything going red.
        "gate" + _AT + "example.invalid",
        "kit" + _AT + "example.invalid",
        "anyone" + _AT + "something.test",
        "anyone" + _AT + "host.example",
        "anyone" + _AT + "box.localhost",
    ):
        assert not _identifier_offenses(benign), f"the guard false-positives on {benign!r}"
    # And the reserved names must be matched as a SUFFIX of the host, never as
    # a substring anywhere in it. A domain someone really owns can contain the
    # word, and that address is personal.
    for personal in (
        "someone" + _AT + "invalid-domain.com",
        "someone" + _AT + "example.invalid.co",
        "someone" + _AT + "test.org.uk",
    ):
        assert _identifier_offenses(personal), (
            f"the reserved-TLD exemption swallowed {personal!r}, which is a real host"
        )


def test_no_committed_path_to_a_migrated_session_document():
    """No committed file names a session document under ``_private/``.

    The plan ledger, the design documents and the licensed local assets DID
    stay in ``_private/``, so this guard names the five migrated entries
    explicitly rather than forbidding ``_private/`` wholesale.

    Scope, stated so the limit is visible: ``iter_style_checked_files`` yields
    ``*.md`` and ``*.py`` only, so ``.github/workflows/*.yml``,
    ``.claude/settings.json`` and ``.claude/tools/snap.sh`` are outside this
    guard. The first two carry no such path today and the third is a
    hash-pinned kit body whose stale wording is tracked by
    PLN-20260727-1854-kit-side-residue (the re-vendor entry that first
    carried it has since closed, and a closed entry is not a tracker).
    """
    offenders = []
    for path in iter_style_checked_files():
        relative = path.relative_to(REPO_ROOT)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in MIGRATED_PATH.finditer(text):
            offenders.append(f"{relative}: names the migrated _private/{match.group(1)}")
    assert not offenders, (
        "session documents live under PYFS_SESSION_ROOT since 2026-07-27:\n" + "\n".join(offenders)
    )


# The author's name inside the SHIPPED PACKAGE. Scope is `src/` only, and the
# narrowness is the whole point of the rule rather than a weakness of it.
#
# BRF-049, routed from the answered decision BRF019 (2026-07-28). The name in
# LICENSE, CITATION.cff, README.md, CHANGELOG.md, pyproject.toml, the guide and
# the docs is AUTHORSHIP of a library published under her own name: intentional,
# and it stays. That is why the identifier guard above excludes it by decision.
#
# src/ is different for one reason: it is installed. PHY-06.yaml is declared
# package data at pyproject.toml:86, so `reason: ... on <name>'s instruction`
# travelled inside the wheel to every machine that ran `pip install
# pyflightstream`. There the name is incidental rather than a credit, and no
# decision ever put it there.
#
# The reason field itself was kept, not deleted: it records WHY a metric set was
# redefined and cites the probe reports that justify it, which is real
# provenance a QA reference should carry. What was checked before rewriting it,
# because a QA reference's prose can be evidence rather than commentary: nothing
# asserts against that text. `qa/physics.py` requires the string to be non-empty
# and echoes it into reports; no test, requirement or report compares it. The
# load-bearing half is the report citation inside it, and that is untouched.
GIVEN_NAME = "Geo" + "vana"


def _names_the_author(text: str) -> bool:
    """Whether ``text`` carries the author's given name.

    Factored out so the tree scan and the mutation proof run the SAME
    code, which is the only arrangement under which the proof proves
    anything about the scan. Mirrors ``_identifier_offenses`` above and
    exists for the same reason.
    """
    return GIVEN_NAME.lower() in text.lower()


def test_no_personal_name_inside_the_installed_package():
    """The shipped surface carries no personal name.

    Tracked files under ``src/`` only. A failure here is not a style nit: the
    file reaches a user's machine, and removing it from HEAD stops it
    spreading without unpublishing what already shipped.
    """
    offenders = []
    for path in _tracked_files():
        relative = path.relative_to(REPO_ROOT)
        if relative.parts[0] != "src":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _names_the_author(text):
            offenders.append(str(relative))
    assert not offenders, (
        "a file inside the installed package carries the author's given name:\n"
        + "\n".join(offenders)
        + "\n\nThe name is deliberate in LICENSE, CITATION.cff, README.md and the "
        "docs, which are authorship of a published library. It is not deliberate "
        "inside src/, which ships in the wheel: there it is incidental. Write "
        '"the author" instead, and keep whatever provenance the sentence '
        "carried (BRF-049)."
    )


def test_the_shipped_name_guard_fires_on_what_it_exists_to_catch():
    """Mutation proof, per the structural-fix rule.

    The guard must be shown to block the ORIGINAL failure, so the original
    line is reconstructed here (assembled, never written literally) and the
    detector is run against it directly.
    """
    original = (
        "reason: 'metric set redefined to the full polar trend on "
        + GIVEN_NAME
        + "''s instruction'"
    )
    # Run the DETECTOR, not the `in` operator. The first version of this test
    # asserted `GIVEN_NAME in original`, which exercises str.__contains__ and
    # would stay green if the scan above were scoped wrongly or filtered to
    # the wrong file types. The role-review QA pass measured that.
    assert _names_the_author(original), (
        "the detector does not fire on the exact line that shipped in the wheel"
    )
    # And the replacement that shipped instead must NOT fire, so the guard is
    # a guard rather than a refusal of the whole sentence.
    replacement = (
        "reason: 'metric set redefined to the full polar trend on the author''s instruction'"
    )
    assert not _names_the_author(replacement), (
        "the detector fires on the replacement, so it refuses the sentence "
        "rather than the identifier"
    )


# ---------------------------------------------------------------------------
# NFR-14: research geometry never enters the repository.
#
# SRS NFR-14 asks for this guard and NFR-08 states the wider rule; the breach
# is the one this project treats as irreversible, and until now it was
# enforced by discipline alone. Measured before this guard existed, on a real
# case rather than in the abstract: a 37 kB synthetic-but-research-shaped .stl
# added under examples/ and staged passed the ENTIRE tier-1 suite (863 tests)
# and the CI guard job's own grep, which looks only for pdf, ipynb and
# _private/. Nothing in the repository objected to a tracked mesh.
#
# The extension set below is derived from the command database rather than
# invented: IMPORT's file_type enum in commands/mesh_import_export.yaml is the
# authority on what this solver reads, and .fsm is a first-class geometry
# artifact in workspace/inputs.py (a saved simulation carries the mesh). The
# CAD-interchange suffixes are added because research geometry ARRIVES in them
# even though the solver does not read them directly.
#
# WHAT THIS GUARD DOES NOT COVER, stated so its scope is not mistaken for the
# invariant. It keys on EXTENSION, which is what NFR-14 asks for and which
# cannot see geometry carried in a generic container: tests/fixtures/fsi/
# structural_nodes.csv is a node coordinate list and no extension rule will
# ever fire on it. NFR-08 is wider than NFR-14 and stays a discipline for that
# residual. This guard also runs on the TREE, not on the built wheel; the
# artifact-side check is a separate mechanism this repository has not vendored.
GEOMETRY_SUFFIXES = frozenset(
    {
        # IMPORT file_type enum (commands/mesh_import_export.yaml)
        ".stl",
        ".tri",
        ".p3d",
        ".inp",
        ".lawgs",
        ".vtk",
        ".ac",
        ".fac",
        ".obj",
        # saved simulation: carries the mesh (workspace/inputs.py, file_io.yaml)
        ".fsm",
        # CAD and mesh interchange research geometry arrives in
        ".step",
        ".stp",
        ".iges",
        ".igs",
        ".sat",
        ".x_t",
        ".x_b",
        ".3dm",
        ".msh",
        ".cgns",
        ".ply",
        ".off",
        ".nas",
        ".bdf",
    }
)

#: Tracked paths allowed to carry a geometry extension, each with the reason
#: it is provably synthetic. A path joins this list only with such a reason;
#: "it was already there" is not one.
SYNTHETIC_GEOMETRY_ALLOWLIST = {
    # Hand-written in the file's own header: a closed unit cube, 8 vertices and
    # 12 triangles, for the probe geometry gate. No research content possible.
    "tests/fixtures/cube.obj",
    # VTK POLYDATA golden with two points at (0,0,0) and (1,0,0): an
    # output-FORMAT golden, not a geometry input.
    "tests/goldens/planar_probes.vtk",
}


def _geometry_offenses(relative_posix_paths):
    """Tracked paths carrying a geometry extension without an allowlist entry.

    Factored out so the tree scan and the mutation proof run the SAME code,
    for the reason ``_names_the_author`` states above.
    """
    return sorted(
        path
        for path in relative_posix_paths
        if Path(path).suffix.lower() in GEOMETRY_SUFFIXES
        and path not in SYNTHETIC_GEOMETRY_ALLOWLIST
    )


@pytest.mark.requirement("NFR-14")
def test_no_geometry_file_is_tracked_outside_the_synthetic_allowlist():
    """NFR-14. Research geometry entering Git is the irreversible breach.

    Irreversible is meant literally: a push publishes it, and removing it
    from HEAD afterwards does not unpublish it from any clone, fork or
    mirror that already fetched. So the guard runs on every tracked path,
    all extensions, and fails loudly rather than skipping.
    """
    offenders = _geometry_offenses(
        str(path.relative_to(REPO_ROOT).as_posix()) for path in _tracked_files()
    )
    assert not offenders, (
        "these tracked files carry a geometry or mesh extension and are not in "
        "the synthetic-fixtures allowlist:\n"
        + "\n".join(offenders)
        + "\n\nResearch geometry never enters this repository (CLAUDE.md "
        "invariant 5, SRS NFR-08 and NFR-14). Keep it in _private/ or in the "
        "research workspace and reference it from a local QA run. If the file "
        "really is synthetic, generate it from pyflightstream.qa.geometry "
        "instead of committing it, or add it to SYNTHETIC_GEOMETRY_ALLOWLIST "
        "with the reason it cannot carry research content."
    )


def test_the_geometry_guard_fires_on_what_it_exists_to_catch():
    """Mutation proof, per the structural-fix rule.

    Runs the DETECTOR against the exact case measured red above, plus the
    live tree, so the proof is about the scan and not about ``str.endswith``.
    """
    leak = "examples/leaked_blade.stl"
    assert _geometry_offenses([leak]) == [leak], (
        "the detector does not fire on a mesh committed under examples/, which "
        "is the case measured passing the whole suite before this guard existed"
    )
    # Every allowlisted path must be recognised as allowlisted, or the entry is
    # dead and the file it names is unguarded by accident rather than decision.
    assert _geometry_offenses(sorted(SYNTHETIC_GEOMETRY_ALLOWLIST)) == []
    # The allowlist must not be a list of paths that no longer exist: a stale
    # entry silently widens the exemption for whatever later takes that name.
    tracked = {str(path.relative_to(REPO_ROOT).as_posix()) for path in _tracked_files()}
    stale = sorted(SYNTHETIC_GEOMETRY_ALLOWLIST - tracked)
    assert not stale, (
        f"allowlisted paths {stale} are not tracked; remove the entry rather "
        "than leaving an exemption waiting for a future file of that name"
    )
    # And the guard must not be vacuous: a suffix outside the set is untouched.
    assert _geometry_offenses(["README.md", "examples/steady_polar.py"]) == []


# --- The container directory's absolute path (PYFS-023) --------------------
#
# The identifier guard above catches an email address and a user-profile path.
# It does not catch the other machine-specific literal CLAUDE.md forbids: an
# absolute path into the directory that holds this repository and its sibling
# workspaces. Scanning every tracked file for an absolute-path SHAPE is not the
# guard, and measuring said so: 32 tracked files match one, and 30 of them are
# illustrative solver paths in examples, goldens and fixtures
# (`C:/cases/wing.fsm`, `C:/path/to/FlightStream.exe`). Those are
# documentation. The container's name is what separates a path that teaches
# from a path that leaks, and it is machine independent, so the guard reads it
# rather than the drive letter.
#
# Assembled from fragments for the reason PROFILE_PATH_SHAPE gives: this file
# is scanned too, and a guard that is its own only offender is no guard.
CONTAINER_DIRECTORY = "Claude" + "Projects"

#: Tracked files allowed to name it, each with the reason. Both are
#: hash-pinned vendored kit bodies: CLAUDE.md's rule is that a vendored body is
#: corrected by a kit promotion at the coordination level, never by an edit
#: here, so allowlisting them is the honest state rather than a concession. The
#: routing is registered as PLN-20260803-1500. Remove each entry as its kit row
#: is re-vendored, and delete the allowlist when the last one goes.
CONTAINER_PATH_ALLOWLIST = {
    ".claude/tools/snap.sh": "vendored kit body, row at 0.2.4; three literals",
    ".claude/tools/check_plan_kit_mutations.py": "vendored kit body; one literal",
}


def _container_offenders(entries: Iterable[tuple[str, str]]) -> list[str]:
    """Return which of ``(relative_path, text)`` name the container directory.

    Takes its input rather than reading the tree, so the detector can be
    driven with synthetic content. That is not a style preference: the
    first version read `_tracked_files()` itself, which left its
    "mutation proof" with nothing to drive and no way to fail. The
    geometry detector next door was already written this way.
    """
    return [
        relative
        for relative, text in entries
        if relative not in CONTAINER_PATH_ALLOWLIST and CONTAINER_DIRECTORY in text
    ]


def _tracked_text() -> list[tuple[str, str]]:
    """Every tracked file as ``(relative_path, text)``.

    A file that cannot be decoded is yielded as an EMPTY string rather
    than skipped, so the detector sees one entry per tracked file and a
    future binary-with-a-literal cannot vanish between the two.
    """
    entries = []
    for path in _tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        entries.append((path.relative_to(REPO_ROOT).as_posix(), text))
    return entries


def test_no_tracked_file_names_the_container_directory():
    """A path into the workspace container is machine configuration.

    CLAUDE.md states the rule ("never a literal path in a committed file") and
    until now only prose held it for this shape. The remote is public, so the
    literal names the author's machine layout to everyone who clones.
    """
    offenders = _container_offenders(_tracked_text())
    assert not offenders, (
        "these tracked files carry an absolute path into the workspace "
        "container, which is machine configuration and belongs in the "
        "gitignored .claude/settings.local.json:\n" + "\n".join(offenders)
    )


def test_the_container_guard_fires_on_what_it_exists_to_catch():
    """Mutation proof, per the structural-fix rule.

    The DETECTOR is driven, which the first version of this test did not
    do: it compared a constant against strings built from that constant,
    so the detector could have returned an empty list unconditionally and
    every assertion would still have passed. Caught by the QA pass of
    2026-08-03, and the repair is the seam rather than more assertions.

    Run against the shapes actually found in the two vendored bodies,
    reconstructed here rather than quoted, plus the illustrative solver
    paths that must NOT fire: a guard that also refuses
    `C:/cases/wing.fsm` would be turned off within a week.
    """
    leaks = (
        "/c/WORK/" + CONTAINER_DIRECTORY + "/pyflightstream/_private",
        "C:/WORK/" + CONTAINER_DIRECTORY + "/_private/kit/check_plan_kit.py",
        "C:" + chr(92) + "WORK" + chr(92) + CONTAINER_DIRECTORY,
    )
    for leak in leaks:
        assert _container_offenders([("some/file.sh", leak)]) == ["some/file.sh"], leak
    for benign in (
        "C:/cases/wing.fsm",
        "C:/path/to/FlightStream.exe",
        "D:/scratch",
        "/w/wing.stl",
    ):
        assert _container_offenders([("examples/x.py", benign)]) == [], (
            f"the guard fires on the illustrative path {benign!r}, which is "
            "documentation and must stay"
        )
    # The exemption branch needs a witness too, or an allowlist that
    # stopped being consulted would look exactly like a clean tree.
    allowlisted = next(iter(CONTAINER_PATH_ALLOWLIST))
    assert _container_offenders([(allowlisted, leaks[0])]) == []

    # And the live scan must see a plausible number of files, or the
    # tree walk could be empty while every assertion above passes.
    entries = _tracked_text()
    assert len(entries) > 50, f"the tracked-file walk yielded {len(entries)} entries"


def test_the_container_allowlist_has_no_stale_entry():
    """An allowlist that outlives its files silently widens the guard.

    Each entry names a vendored body awaiting a kit promotion. When one is
    re-vendored the literal goes, and so must its entry; when the file stops
    being tracked at all, the entry is dead. Either way this fails rather than
    letting the exemption drift into covering something else.
    """
    tracked = {path.relative_to(REPO_ROOT).as_posix() for path in _tracked_files()}
    missing = sorted(set(CONTAINER_PATH_ALLOWLIST) - tracked)
    assert not missing, (
        f"allowlisted paths {missing} are not tracked; remove the entry rather "
        "than leaving an exemption for a file that no longer exists"
    )
    unneeded = sorted(
        name
        for name in CONTAINER_PATH_ALLOWLIST
        if CONTAINER_DIRECTORY not in (REPO_ROOT / name).read_text(encoding="utf-8")
    )
    assert not unneeded, (
        f"allowlisted paths {unneeded} no longer carry the literal, so the kit "
        "promotion landed; delete the entry and close its half of "
        "PLN-20260803-1500"
    )


#: Every codepoint this workflow renders as nothing: delete, the C1
#: control range, the invisible spaces and joiners, the direction marks
#: and the byte order mark. A byte threshold cannot reach any of these,
#: because they all encode above 127 in utf-8, which is how a
#: zero-width space reproduced the backspace defect past the first
#: version of the guard below.
#:
#: Built from codepoints, like FORBIDDEN above and for the same reason:
#: written as literals this file would be its own only offender, and a
#: first attempt wrote exactly that.
_INVISIBLE = frozenset(
    chr(code)
    for code in (
        0x7F,
        0x85,
        0xA0,
        0x200B,
        0x200C,
        0x200D,
        0x200E,
        0x200F,
        0x2028,
        0x2029,
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
        0x2060,
        0xFEFF,
        *range(0x80, 0xA0),
    )
)


def test_no_tracked_text_file_carries_a_control_byte():
    """A backspace in a regex spent a guard and nothing could see it.

    On 2026-08-10 a raw string meant to read `\b` was written through a
    shell heredoc and reached the file as byte 0x08. The pattern then
    required a literal backspace, the helper it powered returned the
    empty set, and two assertions built on it stopped asserting: one
    loop ran zero iterations and one set difference was empty minus
    anything. The suite stayed green while seven of eight editions could
    go silent in the published coverage section.

    NOTHING COULD SEE IT BY READING. Editors, diffs and the tools used
    to review this repository all render 0x08 as nothing at all, so the
    line looked correct in every view anyone had of it. Four more of the
    same byte were then found in a second file, from the same cause, and
    one deliberate 0x1f that was functional and indistinguishable from
    the accident.

    Tab, newline and carriage return are the three that belong in text.
    Everything else is written as an escape, which is visible.

    THE FIRST VERSION OF THIS GUARD CHECKED BYTES BELOW 32 ONLY, and a
    reviewer got the same defect past it with a zero-width space: put
    U+200B where the escape belongs and the pattern matches nothing, the
    helper returns the empty set, two assertions go silent, and the
    suite is green. It encodes as three bytes above 127, so a byte
    threshold cannot see it. The set below is every codepoint this
    workflow renders as nothing: the C0 controls, delete, the C1 range,
    the invisible spaces and the direction marks.

    The file list is a BINARY denylist rather than a text allowlist, for
    the same reason: an allowlist scans the extensions somebody thought
    of, so thirteen tracked text files including every golden and
    fixture that is not .txt or .yaml went unscanned by the first
    version.
    """
    offenders = []
    binary_suffixes = {".obj", ".pdf", ".png", ".jpg", ".ico", ".stl", ".whl", ".gz"}
    for path in _tracked_files():
        if path.suffix.lower() in binary_suffixes:
            continue
        raw = path.read_bytes()
        found = sorted({byte for byte in raw if byte < 32 and byte not in (9, 10, 13)})
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = ""
        invisible = sorted({char for char in text if char in _INVISIBLE})
        if found or invisible:
            names = [hex(byte) for byte in found]
            names += [f"U+{ord(char):04X}" for char in invisible]
            offenders.append(f"{path}: {', '.join(names)}")
    assert not offenders, (
        "these tracked files carry a control byte, which every editor and diff in "
        "this workflow renders as nothing: " + "; ".join(offenders) + ". Write it as "
        r"an escape (\b, \x1f) so the character is visible to a reader"
    )


# --- Public anchors only: the private-ledger-id ratchet (OPS-2010.15) ------
#
# The policy is decided and until now nothing held it: a page in this
# repository cites anchors its READER can resolve. This remote is public and
# the records these identifiers name are not. The plan ledger and the design
# documents are local-only under `_private/` (CLAUDE.md, "Session protocol"),
# the incident ledger is a separate repository located by an environment
# variable, and the coordination hub is a third. A committed sentence citing
# one of them sends a reader to a document that does not exist for them.
#
# NO ID IS RESOLVED AGAINST A LEDGER, and that is the decision rather than a
# shortcut. The ledgers live outside this repository, so continuous
# integration cannot reach any of them; a checker that needs them would be
# green on this machine and unrunnable everywhere else. What is checkable
# from inside the tree is the SHAPE, and the shape is what this counts.
#
# THE SWEEP IS NOT THIS GUARD. Deleting the citations already committed is
# registered separately and is a large edit across public pages. This only
# stops the leak growing back the day after it, which is why it ships as a
# shrink-only ratchet over a committed inventory rather than as a refusal:
# the same shape `tests/test_exceptions_catalog.py` already uses, including
# that precedent's load-bearing qualifier, that any unit THE WALK REACHES
# without a row fails.
#
# WHAT STAYS LEGAL: report ids (`RPT-...`), SRS requirement ids and the plan
# node ids of the coordination tree. `reports/` and `docs/srs/` are committed
# and public, so citing them resolves.
#
# THE READING IS UNBOUNDED IN FRONT: a prefix, a hyphen and a digit, with no
# word boundary before the prefix. That is deliberate, and it is what decides
# the numbers. The word-bounded variant misses the private plan filenames of
# the form `DESIGN_<prefix>-12_kit_batch.md`, where the prefix follows an
# underscore, and an id at the start of a line inside a Python string
# literal, where it follows the `n` of an escape. Those are precisely the
# citations this exists to catch.
#
# Prefixes are built by concatenation, like FORBIDDEN_WORDS above and for the
# same reason: this file is walked by its own guard, and a guard that is its
# own only offender is no guard.
_PRIVATE_LEDGER_PREFIXES = (
    "IN" + "C",
    "PL" + "N",
    "BR" + "F",
    "COO" + "RD",
    "IT" + "C",
    "O" + "Q",
    "HU" + "B",
)
PRIVATE_LEDGER_ID = re.compile("(?:" + "|".join(_PRIVATE_LEDGER_PREFIXES) + ")" + "-[0-9]")

#: The committed inventory of counted units. Paths and counts only: it is
#: walked by this guard like every other tracked ``*.py``, so it must not
#: become its own offender, and no walked path carries a refused id in its
#: own name today (measured, empty set).
PRIVATE_ID_INVENTORY_PATH = REPO_ROOT / "tests" / "data" / "private_id_inventory.py"


def _recorded_private_id_counts() -> dict[str, int]:
    """Load the committed inventory from its file.

    Loaded by path rather than imported by name, so the guard does not
    depend on ``tests/`` sitting on ``sys.path`` and does not need
    ``tests/data`` to be a package. A missing or unreadable inventory FAILS
    here rather than degrading to an empty mapping: an empty inventory
    compared against a clean tree reports green, which is the false pass
    this repository has registered most.
    """
    spec = importlib.util.spec_from_file_location(
        "pyflightstream_private_id_inventory", PRIVATE_ID_INVENTORY_PATH
    )
    assert spec is not None and spec.loader is not None, (
        f"the recorded inventory {PRIVATE_ID_INVENTORY_PATH} could not be loaded. "
        "It is the ratchet's only record of what is already committed; without it "
        "this guard has nothing to compare against and would report green."
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.PRIVATE_ID_COUNTS)


def _counted_region(relative: str, text: str) -> str:
    """The region of a walked file the ratchet counts, given its LF text.

    The counted unit is the whole file, EXCEPT for the hash-pinned vendored
    kit bodies, where it is the provenance HEADER alone. That partition is
    not a convenience: ``tests/test_kit_drift.py`` hashes only the body below
    the ``END KIT PROVENANCE`` marker, so correcting a citation in the header
    moves no body hash and is a legal edit here, while correcting one in the
    body breaks the pin and must be done at the kit and re-vendored. The
    boundary comes from that module's own ``_split_at_marker`` so the two
    cannot disagree about which line the body starts on.
    """
    if relative in KIT_MANIFEST:
        lines, body_start = _split_at_marker(text)
        return "\n".join(lines[:body_start])
    return text


def _count_private_ids(relative: str, text: str) -> int:
    """Occurrences of a private-ledger id in this unit's counted region."""
    return len(PRIVATE_LEDGER_ID.findall(_counted_region(relative, text)))


def _private_id_units() -> dict[str, int]:
    """Every walked file as ``{relative posix path: counted occurrences}``.

    One entry per walked file, including the files carrying none, so the
    comparison below can tell "counts zero now" from "is no longer walked"
    without a second traversal.
    """
    units: dict[str, int] = {}
    for path in iter_style_checked_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        # The kit bodies are hashed over LF-normalized text, so the header
        # split must run on the same normalization the pin uses.
        if relative in KIT_MANIFEST:
            text = _read_lf(path)
        else:
            text = path.read_text(encoding="utf-8", errors="ignore")
        units[relative] = _count_private_ids(relative, text)
    return units


def _ratchet_offenses(counted: Mapping[str, int], recorded: Mapping[str, int]) -> list[str]:
    """Compare live counts against the inventory, in all four directions.

    Takes both mappings rather than reading the tree, for the reason
    ``_container_offenders`` states above: a detector that reads the tree
    itself leaves its mutation proof with nothing to drive.
    """
    offenses = []
    for relative in sorted(set(counted) | set(recorded)):
        found = counted.get(relative, 0)
        was = recorded.get(relative)
        if was is None:
            if found:
                offenses.append(
                    f"{relative}: cites a private ledger id {found} time(s) and has no "
                    "row in the inventory. Cite a public anchor instead."
                )
        elif found > was:
            offenses.append(
                f"{relative}: {found} citations, {was} recorded. A new private "
                "ledger citation was added; cite a public anchor instead."
            )
        elif found == 0:
            offenses.append(
                f"{relative}: 0 citations and a row recording {was}. The unit is "
                "clean or is no longer walked; delete its row so the inventory "
                "cannot cover a future file of that name."
            )
        elif found < was:
            offenses.append(
                f"{relative}: {found} citations, {was} recorded. The sweep moved; "
                f"lower the recorded number to {found} so the inventory tracks it."
            )
    return offenses


def test_no_new_private_ledger_citation_in_a_walked_file():
    """A walked file cites no private ledger id beyond its recorded count.

    Shrink-only. The recorded number is a ceiling AND a floor: adding a
    citation fails, and removing one fails until the inventory is lowered, so
    the record cannot quietly stop describing the tree.
    """
    counted = _private_id_units()
    # A FLOOR on the population, for the reason `_tracked_files` states: the
    # walk is `REPO_ROOT.rglob` minus SKIP_DIRS, and a walk that yields
    # nothing satisfies every comparison below. 430 files at delivery, of
    # which 150 carry a citation and hold a row; the exact per-unit numbers
    # are pinned by the inventory, so this is a collapse detector and not a
    # second population pin.
    assert len(counted) > 350, (
        f"the style walk yielded {len(counted)} files, far below this "
        "repository's real size, so this ratchet compared almost nothing. "
        "Check REPO_ROOT and SKIP_DIRS before reading the result as clean."
    )
    recorded = _recorded_private_id_counts()
    offenses = _ratchet_offenses(counted, recorded)
    assert not offenses, (
        f"the private-ledger-id ratchet counted {len(counted)} walked units against "
        f"{len(recorded)} recorded rows and found:\n"
        + "\n".join(offenses)
        + "\n\nThis remote is public and these records are not: the plan ledger and "
        "the design documents are local-only under _private/, and the incident "
        "ledger and the coordination hub are other repositories. Cite something a "
        "reader can open: a report under reports/, an SRS requirement, a commit, or "
        "the sentence itself. If a citation was legitimately REMOVED, lower its "
        "recorded number in tests/data/private_id_inventory.py in the same commit."
    )


def test_the_private_id_ratchet_counts_the_partition_it_claims():
    """The header/body partition is live, not a branch nothing takes.

    The exemption exists because a citation inside a hashed kit body cannot
    be corrected here at all. If the marker split drifted, every kit file
    would silently become "header equals whole file", the exempt region would
    be empty, and the ratchet above would still pass on a clean tree. This
    asserts the partition is doing something and that its population is not
    empty.
    """
    counted = _private_id_units()
    walked_kit = sorted(set(KIT_MANIFEST) & set(counted))
    assert len(KIT_MANIFEST) >= 30, (
        f"the vendored manifest holds {len(KIT_MANIFEST)} rows; the partition "
        "this ratchet applies is keyed on it, and a collapsed manifest would "
        "widen the counted unit to the whole file without anything going red"
    )
    assert len(walked_kit) >= 30, (
        f"only {len(walked_kit)} of {len(KIT_MANIFEST)} manifest rows are inside "
        "the style walk; the header exemption is being applied to almost nothing"
    )
    exempt = 0
    for relative in walked_kit:
        whole = len(PRIVATE_LEDGER_ID.findall(_read_lf(REPO_ROOT / relative)))
        assert whole >= counted[relative], (
            f"{relative}: the counted header carries {counted[relative]} ids and the "
            f"whole file {whole}. The header cannot hold more than the file, so "
            "_split_at_marker returned a boundary past the end of the text."
        )
        exempt += whole - counted[relative]
    # 112 occurrences in 26 hashed bodies at delivery. Asserted as non-empty
    # rather than pinned to that number, because a re-vendor legitimately
    # moves it and the exact per-unit numbers are pinned by the inventory.
    assert exempt > 0, (
        "no citation at all sits inside a hashed kit body, so the header/body "
        "partition currently exempts nothing. Either the bodies were swept (in "
        "which case delete this partition and count the whole file) or the "
        "END KIT PROVENANCE split has drifted and the exemption is silently "
        "covering the whole of every kit file."
    )


def test_the_private_id_ratchet_fires_on_what_it_exists_to_catch():
    """Mutation proof, per the structural-fix rule.

    A guard is proven by restoring the defect and watching it deny, never by
    a suite that passes. The defect here is a private ledger citation in a
    public file, so one is reconstructed and put back: into synthetic text
    for the four failure modes, and into the real text of a real walked file
    for the counter itself.
    """
    cite = "PL" + "N" + "-20260818-2015-public-anchors"
    # 1. The shape. Every prefix must fire, and the digit is required.
    for prefix in _PRIVATE_LEDGER_PREFIXES:
        assert PRIVATE_LEDGER_ID.search(prefix + "-1"), prefix
        assert not PRIVATE_LEDGER_ID.search(prefix + "-name"), prefix
        assert not PRIVATE_LEDGER_ID.search(prefix + "_01"), prefix
    # Unbounded in front, which is the whole reason the numbers are what they
    # are: a private plan filename embeds the prefix after an underscore.
    assert PRIVATE_LEDGER_ID.search("coordination/DESIGN_" + "HU" + "B" + "-12_kit.md")
    # Public anchors stay legal, or the guard would be a refusal of citation
    # itself and would be turned off within a week.
    for legal in ("RPT-021", "FR-48", "NFR-11", "AD-06", "DLV-007", "OPS-2010.15", "v0.8.0"):
        assert not PRIVATE_LEDGER_ID.search(legal), f"the guard refuses the public anchor {legal}"
    # 2. The four failure modes, each driven through the real comparator.
    assert _ratchet_offenses({"a.md": 3}, {"a.md": 2}), "a NEW citation is not refused"
    assert _ratchet_offenses({"a.md": 1}, {}), "an UNRECORDED unit carrying one is not refused"
    assert _ratchet_offenses({"a.md": 1}, {"a.md": 2}), "a DROPPED count is not refused"
    assert _ratchet_offenses({"a.md": 0}, {"a.md": 2}), "a row over a clean unit survives"
    assert _ratchet_offenses({}, {"gone.md": 2}), "a row over an unwalked path survives"
    # And a file carrying none, with no row, passes: the ratchet must not
    # require a row per walked file.
    assert _ratchet_offenses({"a.md": 0, "b.md": 2}, {"b.md": 2}) == []
    # 3. The counter, on the REAL text of a real walked unit rather than on a
    # string built here. Restoring one citation into it must be refused.
    counted = _private_id_units()
    recorded = _recorded_private_id_counts()
    plain = sorted((set(recorded) & set(counted)) - set(KIT_MANIFEST))
    assert plain, "the inventory records no walked ordinary file, so this proof drives nothing"
    victim = max(plain, key=lambda name: (recorded[name], name))
    text = (REPO_ROOT / victim).read_text(encoding="utf-8", errors="ignore")
    before = _count_private_ids(victim, text)
    assert before == counted[victim], f"{victim}: the counter is not reading the walked text"
    after = _count_private_ids(victim, text + "\nsee " + cite + "\n")
    assert after == before + 1, (
        f"{victim}: restoring one citation moved the count from {before} to {after}"
    )
    # Compared against what this run MEASURED for the unit, not against its
    # recorded row: the claim being proved is that one more citation than the
    # tree already holds is refused, and reading the row here would make the
    # proof fail for the unrelated reason that the row is stale.
    assert _ratchet_offenses({victim: after}, {victim: before}), (
        f"{victim} was given one more citation than it carries and the ratchet did not refuse it"
    )
    # 4. The exemption boundary, both ways, on a real manifest path so the
    # branch is selected by the same membership test the scan uses.
    kit = sorted(KIT_MANIFEST)[0]
    marker = "END KIT " + "PROVENANCE"
    in_body = "# note: kit\n# " + marker + "\nbody cites " + cite + "\n"
    in_header = "# note: " + cite + "\n# " + marker + "\nbody\n"
    assert _count_private_ids(kit, in_body) == 0, (
        f"{kit}: a citation inside the HASHED body is counted, so the ratchet "
        "asks for an edit that would break the body pin"
    )
    assert _count_private_ids(kit, in_header) == 1, (
        f"{kit}: a citation in the provenance header is not counted, so the one "
        "region a vendored file may legally be corrected in is unguarded"
    )
    # The same text under an ordinary path counts both, which is what proves
    # the exemption is keyed on the manifest and not on the marker.
    assert _count_private_ids("docs/whatever.md", in_body) == 1
