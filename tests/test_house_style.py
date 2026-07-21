"""Tier 1: house-style guards that apply to the whole repository.

No em dash (U+2014) or en dash (U+2013) characters in Markdown or Python
files, per the project style. Binary and local-only content guards run in
pre-commit and in the CI guard job.
"""

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
