"""The release-state file states no owed archive row (FR-346).

Marker P0340-RELEASE-READY. ``RELEASE-READY.md`` once said the archive row of a
release was owed after the row had entered. It must not say so, must name the
version it describes (the package's version without a development suffix) and
must name the archive of the releases by the concept DOI that ``CITATION.cff``
carries. A file with the phrase merely deleted and no archive named fails the
check, which the control below plants.

The title is compared with the package's version, so the re-title of the file
and the bump of ``pyproject.toml`` away from the released version are ONE
commit (FR-346 R2); a bump alone fails this test by design. The sequence's
commands are compared with it too: the one ``git tag -a`` line tags exactly
that version, and no ``git`` or ``gh`` command names another.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / "RELEASE-READY.md"

#: The owed phrase, with the spellings that say the same thing across a wrap.
OWED = re.compile(r"archive\s+row\s+(?:is\s+|was\s+)?owed", re.IGNORECASE)
SEMVER = re.compile(r"\b\d+\.\d+\.\d+\b")
#: The tag command of the sequence, and the version it tags.
TAG_LINE = re.compile(r"^git tag -a v(\d+\.\d+\.\d+)\b", re.MULTILINE)
#: A version inside a command, where it follows a ``v`` with no word boundary.
COMMAND_VERSION = re.compile(r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])")


def _package_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml carries no version"
    return re.sub(r"\.?dev\d*$", "", match.group(1))


def _concept_doi() -> str:
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(
        r"-\s*type:\s*doi\s+value:\s*(\S+)\s+description:\s*\"Zenodo concept DOI", text
    )
    assert match, "CITATION.cff carries no concept DOI"
    return match.group(1)


def _problems(text: str, version: str, doi: str) -> list[str]:
    found = []
    if OWED.search(text):
        found.append("it still says the archive row is owed")
    title = next(line for line in text.splitlines() if line.startswith("# "))
    if SEMVER.findall(title) != [version]:
        found.append(f"its title does not name exactly the version {version}")
    tags = TAG_LINE.findall(text)
    if tags != [version]:
        found.append(f"its git tag line tags {tags}, not exactly the version {version}")
    for line in text.splitlines():
        if line.startswith(("git ", "gh ")) and set(COMMAND_VERSION.findall(line)) - {version}:
            found.append(f"its command {line!r} names a version other than {version}")
    if doi not in text:
        found.append(f"it does not name the archive by the concept DOI {doi}")
    return found


def test_release_ready_names_its_version_and_the_archive_and_owes_no_row():
    """P0340-RELEASE-READY, FR-346 R1 to R3: the file as it stands."""
    text = FILE.read_text(encoding="utf-8")
    assert _problems(text, _package_version(), _concept_doi()) == []


def test_a_file_with_the_phrase_deleted_and_no_archive_named_fails():
    """P0340-RELEASE-READY, FR-346: the control for the archive row wording."""
    version, doi = _package_version(), _concept_doi()
    text = FILE.read_text(encoding="utf-8")
    assert _problems(text, version, doi) == []
    owed = text + "\nThe v" + version + " archive row is owed in the change log.\n"
    assert any("owed" in problem for problem in _problems(owed, version, doi))
    wrapped = text + "\nThe archive row\nowed is the thing.\n"
    assert any("owed" in problem for problem in _problems(wrapped, version, doi))
    no_archive = text.replace(doi, "")
    assert doi not in no_archive
    assert any("concept DOI" in problem for problem in _problems(no_archive, version, doi))
    wrong_title = text.replace(f"# pyflightstream {version}", "# pyflightstream 9.9.9", 1)
    assert any("title" in problem for problem in _problems(wrong_title, version, doi))
    assert not any("owed" in problem for problem in _problems(no_archive, version, doi))


def test_a_sequence_that_tags_or_pushes_another_version_fails():
    """P0340-RELEASE-READY, FR-346: the commands release the version of the title.

    The file once carried a 0.34.0 title over a sequence that still tagged,
    pushed and released v0.33.1: a reader following it would have cut the
    previous release again.
    """
    version, doi = _package_version(), _concept_doi()
    text = FILE.read_text(encoding="utf-8")
    assert _problems(text, version, doi) == []
    tag = f'git tag -a v{version} -m "v{version}"'
    assert text.count(tag) == 1, tag
    old_tag = text.replace(tag, 'git tag -a v0.0.1 -m "v0.0.1"')
    assert any("git tag line" in problem for problem in _problems(old_tag, version, doi))
    no_tag = text.replace(tag, "")
    assert any("git tag line" in problem for problem in _problems(no_tag, version, doi))
    push = f"git push origin v{version}"
    assert text.count(push) == 1, push
    old_push = text.replace(push, "git push origin v0.0.1")
    problems = _problems(old_push, version, doi)
    assert any("git push origin v0.0.1" in problem for problem in problems), problems
