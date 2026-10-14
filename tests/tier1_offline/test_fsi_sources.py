"""Retained runtime, privacy and link checks, with shared test support."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


PACKAGE = REPO_ROOT / "src" / "pyflightstream"


RETIRED_TRACKER_ID = "TSR" + "-014"


def test_no_shipped_file_names_a_tracker_a_reader_cannot_open():
    """The identifier is dead, so it must not ship.

    reports/ holds RPT-001 to RPT-012 and then RPT-014, so there is no
    report the retired id could have been repointed at: deletion was the
    only move. The walk is over the whole package rather than over the
    five known sites, because the next such id will be somewhere else,
    and it includes ``fsi/README.md``, which sits inside ``src/`` and
    reaches readers through the repository even though the wheel does
    not carry it.
    """
    offenders = []
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if RETIRED_TRACKER_ID in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert not offenders, (
        "a shipped file names a tracking identifier whose only home is another "
        f"repository, so a reader following it reaches nothing: {offenders}. "
        "State the status in plain words instead."
    )
