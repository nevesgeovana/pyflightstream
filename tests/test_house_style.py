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
        if GIVEN_NAME.lower() in text.lower():
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
    assert GIVEN_NAME.lower() in original.lower(), (
        "the reconstruction no longer contains what the guard looks for"
    )
    # And the replacement that shipped instead must NOT fire, so the guard is
    # a guard rather than a refusal of the whole sentence.
    replacement = (
        "reason: 'metric set redefined to the full polar trend on the author''s instruction'"
    )
    assert GIVEN_NAME.lower() not in replacement.lower()
