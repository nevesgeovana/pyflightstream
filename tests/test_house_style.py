"""Tier 1: house-style guards that apply to the whole repository.

No em dash (U+2014) or en dash (U+2013) characters in Markdown or Python
files, per the project style. Binary and local-only content guards run in
pre-commit and in the CI guard job.
"""

import re
import subprocess
from pathlib import Path

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
# Built from codepoints so this file itself stays free of the characters.
FORBIDDEN = {chr(0x2013): "en dash", chr(0x2014): "em dash"}
# Built by concatenation so this file itself stays free of the words:
# the repository never names the author's employer or internal
# predecessor toolchains (CLAUDE.md invariant 5).
FORBIDDEN_WORDS = ("Embr" + "aer", "fts_" + "horse")


def iter_style_checked_files():
    for pattern in ("*.md", "*.py"):
        for path in REPO_ROOT.rglob(pattern):
            if not SKIP_DIRS.intersection(part for part in path.parts):
                yield path


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
        if host.lower() in IMPERSONAL_MAIL_HOSTS or user.lower() in IMPERSONAL_MAIL_USERS:
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
    return [REPO_ROOT / name for name in result.stdout.split("\0") if name]


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
    ):
        assert not _identifier_offenses(benign), f"the guard false-positives on {benign!r}"


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


def _container_offenders() -> list[str]:
    """Return tracked files naming the container directory, minus the allowlist."""
    offenders = []
    for path in _tracked_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in CONTAINER_PATH_ALLOWLIST:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if CONTAINER_DIRECTORY in text:
            offenders.append(relative)
    return offenders


def test_no_tracked_file_names_the_container_directory():
    """A path into the workspace container is machine configuration.

    CLAUDE.md states the rule ("never a literal path in a committed file") and
    until now only prose held it for this shape. The remote is public, so the
    literal names the author's machine layout to everyone who clones.
    """
    offenders = _container_offenders()
    assert not offenders, (
        "these tracked files carry an absolute path into the workspace "
        "container, which is machine configuration and belongs in the "
        "gitignored .claude/settings.local.json:\n" + "\n".join(offenders)
    )


def test_the_container_guard_fires_on_what_it_exists_to_catch():
    """Mutation proof, per the structural-fix rule.

    Run against the shapes actually found in the two vendored bodies,
    reconstructed here rather than quoted, plus the illustrative solver paths
    that must NOT fire: a guard that also refuses `C:/cases/wing.fsm` would be
    turned off within a week.
    """
    leaks = (
        "/c/WORK/" + CONTAINER_DIRECTORY + "/pyflightstream/_private",
        "C:/WORK/" + CONTAINER_DIRECTORY + "/_private/kit/check_plan_kit.py",
        "C:" + chr(92) + "WORK" + chr(92) + CONTAINER_DIRECTORY,
    )
    for leak in leaks:
        assert CONTAINER_DIRECTORY in leak, leak
    for benign in (
        "C:/cases/wing.fsm",
        "C:/path/to/FlightStream.exe",
        "D:/scratch",
        "/w/wing.stl",
    ):
        assert CONTAINER_DIRECTORY not in benign, (
            f"the guard would fire on the illustrative path {benign!r}, which is "
            "documentation and must stay"
        )


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
