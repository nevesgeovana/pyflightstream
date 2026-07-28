"""Tier 1: house-style guards that apply to the whole repository.

No em dash (U+2014) or en dash (U+2013) characters in Markdown or Python
files, per the project style. Binary and local-only content guards run in
pre-commit and in the CI guard job.
"""

import re
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
