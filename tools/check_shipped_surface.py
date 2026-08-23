#!/usr/bin/env python3
"""Identifiers that must not travel to a user's machine, and the scan.

Usage:
    python check_shipped_surface.py --config <path> [--tree <root>] [--dist <dir>]

Exit codes: 0 clean, 1 a violation, 2 configuration error.

ONE RULE, TWO BOUNDARIES
------------------------

The rule is a denylist of personal and institutional identifiers. The
boundaries are the VERSIONED TREE, scanned every round, and the BUILT wheel and
sdist, scanned by relative path. Both are here, in one body, so that neither
boundary re-derives the rule and the two cannot disagree about what a forbidden
identifier is.

The artifact boundary is not a second opinion, it is the load-bearing one. A
source scan's notion of what ships is a JUDGEMENT; the artifact is the ground
truth. The version of this guard that reasoned about the package directory was
green on the commit that shipped fourteen occurrences across seven files inside
an sdist, because the sdist ships the whole tracked tree and the guard was
looking at one directory of it. That measurement is the reason the artifact
boundary exists, and its structural cause is stated in one line: measure the
carrier, never the mention.

The tree boundary is not redundant with it. It runs in ordinary tier 1, where a
build is not paid for, so an identifier is caught in the round that introduces
it rather than in the round that builds a release.

TOTAL ACCOUNTING, WHICH IS THE PART THAT WAS GOT WRONG FIRST
------------------------------------------------------------

Every file offered to a boundary ends in exactly one of four states, and the
four are required to add up to the whole inventory:

    SCANNED     decoded as text and matched against every pattern
    EXEMPT      carries an identifier by a recorded decision
    UNDECODABLE no text codec produced clean text, so scanning is meaningless
    UNREADABLE  could not be opened at all, which is a VIOLATION and not a note

A file in none of those four is a file the walk silently dropped, and that is
refused. This replaces an earlier floor that compared TOP-LEVEL COMPONENTS of
the inventory against top-level components of what was opened, and the reason
it was replaced is measured rather than theorised: a review of this file
demonstrated that the component floor was satisfied by opening ONE FILE PER
COMPONENT, 15 of 190 files, and reported a clean tree on the very commit that
shipped fourteen offenders. A floor whose sensitivity is "did an entire
top-level tree go unread" tolerates a scan of eight percent of the repository.

Two counters close the same hole one level down. A file can be opened, counted
as scanned, and have only its first line examined. So the number of characters
DECODED and the number of characters EXAMINED are counted at different places
and required to be equal. Narrowing inside a file has to defeat both.

The floors below are then assertions about what was SCANNED, never about what
was merely PRESENT. That distinction is the whole incident: a path appearing in
an archive's namelist is a MENTION, and the bytes going through the patterns
are the CARRIER. A floor satisfied by the namelist is green over a file the
scan is guaranteed never to read, which a review of this file also demonstrated
by adding one line to a real repository's config.

WHAT IS IN THIS BODY AND WHAT IS IN A REPOSITORY'S CONFIG
---------------------------------------------------------

The TOKENS are here, assembled from code points, and they are here for a reason
that is not convenience. A repository config is a committed plaintext file, so a
token written there would be spelled in the tree, would ship in the sdist, and
would make the config the one file able to defeat the rule. That is not
hypothetical: an earlier implementation of this rule spelled two tokens and
exempted itself, which put both names into every sdist. So the tokens cannot
live in per-repo configuration, and once they cannot, this body is the only
place left. That is the correct home anyway: the identifiers are the same
author's in every workspace, so a token removed in one place and kept in
another is exactly the drift this rule exists to stop, and it has already
happened once.

CONSEQUENCE, stated rather than discovered: widening the token set is an edit
to THIS FILE and to its sibling in the other library, never to a config. That
cost is deliberate; the alternative reintroduces the drift.

What this repository's config carries is what genuinely differs: which of its files
carry an identifier BY DECISION (authorship), and which paths its floors name.
No exemption list appears in this body.

An exemption is the one thing in the config that can silently disable the rule,
so the loader constrains it rather than trusting it. A floor entry may not be
exempt, an exempt subtree may not contain a floor entry, and an sdist floor must
name at least two distinct top-level DIRECTORIES. Each of those refusals exists
because the un-refused version was demonstrated to turn a leaking artifact
green.

WHAT THIS RULE DOES NOT CATCH
-----------------------------

It is a denylist and catches only the tokens listed. A colleague's name, a
second institution or a personal filesystem path passes.

The trailing ``\\w*`` on the name tokens is deliberate: without it a commit
trailer's email local part slips through, because no word boundary falls between
a given name and the characters that follow it. The LEADING side is deliberately
not widened, because a leading ``\\w*`` matches a surname inside ordinary words,
and the measured need was the trailing side alone. A login formed from an
initial followed by the surname is therefore missed.

An email-SHAPED rule was measured and rejected: a package that documents a
default identity of the form user-at-host false-positives on shape, and the
occurrence that started this had no dot in its domain, so the usual pattern
would have missed the very case it was written for.

A file that no text codec decodes cleanly is UNDECODABLE and is counted rather
than scanned. A zipped data format carries a user identity by design, so a
committed archive fixture is invisible to this rule. The earlier form of this
limit was a NUL byte in the first 8192 bytes, and it was worse in two directions
that a review measured: it discarded a whole UTF-16 text file, which is what
this platform's shell writes by default, and it discarded a twenty-kilobyte text
file for one stray NUL near its start.

The DERIVED_METADATA exemption is packaging's shapes and is not narrowable by a
repository. A file placed inside a wheel's ``.dist-info/licenses/`` directory is
exempt, and only at one level: an earlier pattern ended in ``.+``, which matches
a separator, so it exempted arbitrary nested content under that directory.

The egg-info exemption is the one place depth is ALLOWED, and the asymmetry is
deliberate. A ``.dist-info`` directory is always at the root of a wheel, so a
copy of it anywhere else is a misplacement and stays a finding; an
``.egg-info`` directory sits wherever the package tree does, which under a
src-layout is ``src/<name>.egg-info/``. What is widened is where that directory
may BE, never what may sit under it.

A surname is also a citation risk. If a docstring ever cites a paper by an
author of that name, the right move is to widen the exemption with the reason
stated, not to drop the citation.
"""

from __future__ import annotations

import re
import sys
import tarfile
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

USAGE = "usage: check_shipped_surface.py --config <path> [--tree <root>] [--dist <dir>]"

# Assembled from code points so this file carries none of the strings it
# forbids and needs no exemption of its own. In order: the author's given
# name, her family name, and the institution, whose pattern accepts the
# spaced and hyphenated spellings that appear in prose as well as the
# run-together form that appears in an address.
_GIVEN = "".join(map(chr, (103, 101, 111, 118, 97, 110, 97)))
_FAMILY = "".join(map(chr, (110, 101, 118, 101, 115)))
_INSTITUTION = "".join(map(chr, (116, 117, 100, 101, 108, 102, 116)))

FORBIDDEN: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(rf"\b{_GIVEN}\w*", re.IGNORECASE), "the author's given name"),
    (re.compile(rf"\b{_FAMILY}\w*", re.IGNORECASE), "the author's family name"),
    (
        re.compile(rf"\b{_INSTITUTION[:2]}[ _-]?{_INSTITUTION[2:]}\b", re.IGNORECASE),
        "an institution name",
    ),
)

#: Build output derives its metadata from the authorship files and renames it.
#: Matched by SHAPE rather than by basename, so that a stray package-internal
#: LICENSE or a test fixture called PKG-INFO is guarded like any other file
#: instead of being exempted by its name alone. This is fixed in this body because the
#: shapes are packaging's, not any repository's.
DERIVED_METADATA: tuple[re.Pattern[str], ...] = (
    re.compile(r"PKG-INFO"),
    # AT ANY DEPTH, and the widening was measured. The pattern was
    # `[^/]+\.egg-info/PKG-INFO`, applied with fullmatch, so it assumed the
    # egg-info directory sits at the archive root. A src-layout project puts
    # it at `src/<name>.egg-info/PKG-INFO`, where `[^/]+` cannot span the
    # separator, and the exemption missed: 7 permanent false findings measured
    # on one real repository, in a set this file deliberately does not let a
    # repository narrow. The leading group matches whole path SEGMENTS only, so
    # the widening is to the LOCATION of the egg-info directory and not to what
    # may sit under it: an arbitrary path ending in PKG-INFO is still a
    # finding, because `.egg-info/` must still be the last segment before it.
    re.compile(r"(?:[^/]+/)*[^/]+\.egg-info/PKG-INFO"),
    re.compile(r"[^/]+\.dist-info/METADATA"),
    re.compile(r"[^/]+\.dist-info/licenses/[^/]+"),
)

#: Tried in order; the first that yields text with no NUL codepoint wins.
#: ``utf-8-sig`` before ``utf-8`` so a byte-order mark does not become a
#: character in line 1. The UTF-16 entries are not decoration on this
#: platform: its default shell redirection writes UTF-16LE, so a note or a
#: generated table committed that way is human-readable and would otherwise
#: have been classified as binary and skipped whole.
TEXT_CODECS = ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be")

#: The remedy, worded once so every boundary says the same thing.
REMEDY = (
    "state the fact without the name (a requirement, decision or question id "
    "is what a reader can follow), and use a neutral example identity"
)

CONFIG_KEYS = frozenset({"exempt-path", "exempt-tree", "wheel-floor", "sdist-floor"})


class ConfigError(Exception):
    """The check could not run. Never reported as a clean tree."""


@dataclass(frozen=True)
class Config:
    """The per-repository half of the rule.

    Every field is a repository's own decision. None of them may be defaulted
    to something plausible: a guard that invents an exemption set exempts files
    nobody decided to exempt, and a guard that invents a floor asserts coverage
    nobody measured.
    """

    exempt_paths: frozenset[str]
    exempt_trees: tuple[str, ...]
    wheel_floor: tuple[str, ...]
    sdist_floor: tuple[str, ...]


@dataclass
class Scan:
    """What a boundary actually did, in four totals that must add up.

    ``decoded_chars`` is counted where a payload becomes text and
    ``examined_chars`` where a line is matched, deliberately in two places. A
    narrowing inside a file changes one and not the other, and the caller
    compares them; a single-site counter would agree with the narrowing that
    produced it.
    """

    findings: list[str] = field(default_factory=list)
    scanned: list[str] = field(default_factory=list)
    exempt: list[str] = field(default_factory=list)
    undecodable: list[str] = field(default_factory=list)
    decoded_chars: int = 0
    examined_chars: int = 0

    def accounted(self) -> set[str]:
        return set(self.scanned) | set(self.exempt) | set(self.undecodable)


def _strip_comment(line: str) -> str:
    """Drop a trailing comment, but only where a comment can start.

    A bare ``split("#")`` truncates a value at any ``#``, so
    ``exempt-tree: docs/#draft/`` silently became ``docs/``, which is BROADER
    than what was written. A comment starts at the beginning of a line or
    after whitespace; anywhere else the character is part of the value.
    """
    if line.lstrip().startswith("#"):
        return ""
    cut = re.search(r"\s#", line)
    return line[: cut.start()] if cut else line


def _top_level_dirs(paths: Iterable[str]) -> set[str]:
    """The first path segment of each entry that HAS a subdirectory.

    A root-level file is deliberately not a component here. Counting it as one
    let a floor of two root files satisfy the two-component rule below, which
    is the rule's exact opposite: the floor is supposed to prove the scan
    reaches into the trees an sdist ships.
    """
    found = set()
    for path in paths:
        head, sep, _ = path.replace("\\", "/").partition("/")
        if sep and head:
            found.add(head)
    return found


def load_config(path: Path) -> Config:
    """Read the per-repo config, refusing anything it cannot mean.

    Line oriented, ``key: value``, repeated keys accumulate, ``#`` comments and
    blank lines ignored. No TOML and no YAML, so the checker adds no dependency
    to a repository that has none.

    An unreadable-but-present file raises rather than returning an empty
    config. Empty would silently mean "no exemptions and no floor", which is
    both wrong and green.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"the config at {path} exists but could not be read ({exc}). "
            f"This is a configuration error and not an empty config: an empty "
            f"config means no exemptions and no floor, which would report a "
            f"clean scan over a rule nobody supplied."
        ) from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(f"the config at {path} is not UTF-8 ({exc})") from exc

    values: dict[str, list[str]] = {key: [] for key in CONFIG_KEYS}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        key, sep, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not sep or key not in CONFIG_KEYS:
            raise ConfigError(
                f"{path}:{lineno}: {raw.strip()!r} is not a known setting. "
                f"Known keys: {', '.join(sorted(CONFIG_KEYS))}. A typo is "
                f"refused rather than ignored, because an ignored "
                f"'exempt-path' line reads as an exemption that was never "
                f"granted."
            )
        if not value:
            raise ConfigError(f"{path}:{lineno}: {key!r} has no value")
        values[key].append(value.replace("\\", "/"))

    for entry in values["exempt-path"] + values["exempt-tree"]:
        if entry.startswith("/") or ".." in entry.split("/") or ":" in entry:
            raise ConfigError(
                f"{path}: {entry!r} is not a repository-relative path. An "
                f"absolute or upward path in an exemption is refused because "
                f"it cannot be checked against an archive member, where every "
                f"path is relative by construction."
            )
    for entry in values["exempt-tree"]:
        if not entry.endswith("/") or entry == "/":
            raise ConfigError(
                f"{path}: exempt-tree {entry!r} must name a subtree and end "
                f"with '/'. A bare or empty prefix exempts the whole "
                f"repository, which is the one exemption this rule can never "
                f"survive."
            )

    config = Config(
        exempt_paths=frozenset(values["exempt-path"]),
        exempt_trees=tuple(values["exempt-tree"]),
        wheel_floor=tuple(values["wheel-floor"]),
        sdist_floor=tuple(values["sdist-floor"]),
    )

    # The floors are required by the boundary that USES them, in `check`, not
    # here. Demanding them at load time made the artifact boundary's config a
    # precondition of the tree boundary, so a repository that builds no wheel
    # had to invent floors for archives it never produces. That is a guard
    # asking for a decision nobody has any basis to make, which is the thing
    # this file refuses to do elsewhere, and it locked the coordination
    # repository out of running the tree boundary on itself.

    # THE EXEMPTION MAY NOT COVER THE FLOOR. This is the single refusal that
    # closes the sharpest hole this file has had. A floor entry asserts that a
    # named path was SCANNED; if that path is exempt it is never scanned, the
    # floor is satisfied by its mere presence, and the whole subtree around it
    # can be exempt with the report still clean. Adding ONE exempt-tree line to
    # a real repository's config turned an artifact carrying fourteen
    # identifiers fully green on both boundaries, with both floors satisfied.
    for entry in config.wheel_floor + config.sdist_floor:
        if is_authorship(entry, config):
            raise ConfigError(
                f"{path}: {entry!r} is named as a floor and is also exempt. A "
                f"floor asserts that a path was SCANNED, and an exempt path is "
                f"never scanned, so this floor would be satisfied by a file "
                f"the rule is guaranteed not to read. That is the exact shape "
                f"of the incident this guard exists for: a MENTION measured in "
                f"place of the CARRIER. Name a floor entry the scan actually "
                f"reads, or drop the exemption."
            )

    if config.sdist_floor and len(_top_level_dirs(config.sdist_floor)) < 2:
        raise ConfigError(
            f"{path}: the sdist-floor reaches into "
            f"{sorted(_top_level_dirs(config.sdist_floor))} and must name "
            f"paths inside at least TWO distinct top-level DIRECTORIES. An "
            f"sdist ships more than the package, and a floor whose every entry "
            f"sits in one tree stays satisfied while the scan is narrowed out "
            f"of the others. Root-level files do not count: a floor of LICENSE "
            f"and README.md satisfied an earlier form of this rule while "
            f"proving nothing about any tree at all."
        )

    return config


def is_authorship(relpath: str, config: Config) -> bool:
    """Whether this path carries the author's name by deliberate decision.

    The path is relative to the repository root or to the ARTIFACT root, in
    either separator, so one implementation serves both boundaries.
    """
    posix = relpath.replace("\\", "/")
    if posix in config.exempt_paths:
        return True
    if config.exempt_trees and posix.startswith(config.exempt_trees):
        return True
    return any(pattern.fullmatch(posix) for pattern in DERIVED_METADATA)


def as_text(content: bytes) -> str | None:
    """The payload as text, or None when it is genuinely not text.

    A NUL codepoint after a successful decode has two very different causes and
    an earlier version treated them as one, which was wrong in both directions.

    UTF-16LE bytes decode WITHOUT ERROR as UTF-8 and yield a NUL between every
    character, so accepting that decode would scan a string no pattern can
    match. This platform's default shell redirection writes UTF-16LE, so that
    is an ordinary committed file and not an exotic case.

    A twenty-kilobyte text file with one stray NUL is the opposite: it is text,
    and discarding it whole loses everything after the accident. The two are
    told apart by the RATIO. Real UTF-16 of mostly-ASCII content is about half
    NUL bytes; a stray NUL is one byte in thousands.
    """
    if content[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return content.decode("utf-16")
        except (UnicodeDecodeError, UnicodeError):
            return None
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Not UTF-8 and no byte-order mark. Treated as binary rather than
        # forced through a wide codec: utf-16-le decodes almost any even-length
        # byte string into something, so trying it here would classify every
        # archive and image as text and scan the garbage.
        return None
    if "\x00" not in text:
        return text
    if content.count(0) * 3 >= len(content):
        for codec in ("utf-16-le", "utf-16-be"):
            try:
                wide = content.decode(codec)
            except (UnicodeDecodeError, UnicodeError):
                continue
            if "\x00" not in wide:
                return wide
        return None
    return text.replace("\x00", "")


def scan(items: Iterable[tuple[str, bytes]], config: Config) -> Scan:
    """Match every pattern against every line of every non-exempt payload.

    Takes ``(path, content)`` pairs rather than a directory, so one
    implementation serves a filesystem walk and an archive without either
    boundary re-deriving the rule.

    The PATH is matched too. A file named after the author travels to a user's
    disk, into the wheel's RECORD and into ``pip show -f``, and a rule whose
    title is about what reaches a user cannot look only inside the file.
    """
    result = Scan()
    for relpath, content in items:
        if is_authorship(relpath, config):
            result.exempt.append(relpath)
            continue
        for pattern, label in FORBIDDEN:
            if pattern.search(relpath):
                result.findings.append(f"{relpath}: {label}, in the PATH itself")
        text = as_text(content)
        if text is None:
            result.undecodable.append(relpath)
            continue
        result.scanned.append(relpath)
        result.decoded_chars += len(text)
        for lineno, line in enumerate(text.splitlines(), start=1):
            result.examined_chars += len(line)
            for pattern, label in FORBIDDEN:
                if pattern.search(line):
                    result.findings.append(f"{relpath}:{lineno}: {label}")
    return result


def _coverage(
    result: Scan,
    inventory: list[str],
    label: str,
    floor: Iterable[str],
    also_accounted: Iterable[str] = (),
) -> list[str]:
    """The floor, stated over what was SCANNED and not over what was present.

    ``inventory`` MUST come from the source of truth for this boundary (git, or
    the archive's namelist) and never from the list the scan happened to build.
    That distinction is the whole check, and getting it wrong once is how this
    function was first written: it compared the scan's output against a list
    derived from the same loop, so a narrowing of that loop shrank both sides
    and the coverage check agreed with it. That is the instrument counting
    itself, which is the incident this guard is for, committed inside the guard
    for the second time in one session.
    """
    violations: list[str] = []

    dropped = sorted(set(inventory) - result.accounted() - set(also_accounted))
    if dropped:
        violations.append(
            f"the {label} scan silently dropped {len(dropped)} file(s) that "
            f"are part of what it was given, for example {dropped[:5]}. Every "
            f"file must end as scanned, exempt or undecodable; one in none of "
            f"those was never looked at, and a clean result over it means "
            f"nothing."
        )

    # Line splitting discards the separators, so examined is at most decoded
    # and equals it only when every line of every scanned file was matched.
    # The two are counted in different places on purpose.
    newlines = result.decoded_chars - result.examined_chars
    if newlines < 0 or newlines > result.decoded_chars // 2:
        violations.append(
            f"the {label} scan decoded {result.decoded_chars} character(s) and "
            f"examined {result.examined_chars}. Those are counted in two "
            f"places precisely so that reading part of a file cannot look like "
            f"reading it; this gap is too large to be line separators."
        )

    for entry in floor:
        if entry not in result.scanned:
            where = (
                "it was exempt"
                if entry in result.exempt
                else "it was undecodable"
                if entry in result.undecodable
                else "it is absent"
            )
            violations.append(
                f"the {label} floor names {entry} and the scan did not read "
                f"it: {where}. A floor is an assertion about what was READ, "
                f"never about what was merely present."
            )
    return violations


def _git(root: Path, *args: str) -> tuple[int, str]:
    import subprocess  # noqa: PLC0415

    try:
        done = subprocess.run(["git", *args], capture_output=True, cwd=str(root), check=False)
    except OSError as exc:
        raise ConfigError(
            f"git could not be run in {root} ({exc}). The tree boundary takes "
            f"its inventory from git rather than from a directory walk, so a "
            f"missing git is a configuration error and not an empty tree."
        ) from exc
    return done.returncode, done.stdout.decode(errors="surrogateescape")


def repository_files(root: Path) -> list[str]:
    """Everything git considers part of the repository, top level enforced.

    The union of tracked files and untracked-but-not-ignored ones: the first is
    what an sdist is built from, and the second is a file written but not yet
    added, which a guard must still see.

    Asking git rather than the filesystem keeps the verdict off local state. A
    working-tree walk reads build output, virtual environments and one
    machine's absolute paths, so its result depends on what happened to have
    been built.
    """
    code, top = _git(root, "rev-parse", "--show-toplevel")
    if code != 0:
        raise ConfigError(
            f"{root} is not inside a git checkout, so the tree boundary has no "
            f"inventory to scan. Run this against a checkout, or pass only "
            f"--dist."
        )
    resolved_top = Path(top.strip()).resolve()
    if resolved_top != root.resolve():
        raise ConfigError(
            f"--tree was given {root}, which is a SUBTREE of the repository at "
            f"{resolved_top}. A subtree is refused rather than scanned: it "
            f"produces a well-formed green result over the wrong subject, "
            f"which is exactly the failure this guard exists for. The sdist "
            f"ships the whole tracked tree, so the whole tracked tree is what "
            f"has to be read."
        )
    names: list[str] = []
    for extra in ([], ["--others", "--exclude-standard"]):
        code, out = _git(root, "ls-files", "-z", *extra)
        if code != 0:
            raise ConfigError(f"git ls-files failed in {root}")
        names += [name for name in out.split("\0") if name]
    return sorted(set(names))


def scan_tree(root: Path, config: Config) -> tuple[list[str], list[str]]:
    """The versioned tree, every file accounted for."""
    report: list[str] = [f"TREE boundary, {root}"]
    violations: list[str] = []

    inventory = repository_files(root)
    if not inventory:
        report.append("  inventory: 0 file(s)")
        violations.append(
            f"git reported no files at all in {root}, so nothing was scanned "
            f"and a clean result would mean nothing"
        )
        return violations, report

    opened: list[tuple[str, bytes]] = []
    unreadable: list[str] = []
    for name in inventory:
        try:
            opened.append((name, (root / name).read_bytes()))
        except OSError:
            unreadable.append(name)

    result = scan(opened, config)
    report.append(
        f"  inventory {len(inventory)}: scanned {len(result.scanned)}, "
        f"exempt {len(result.exempt)}, undecodable {len(result.undecodable)}, "
        f"unreadable {len(unreadable)}"
    )
    report.append(
        f"  {result.examined_chars} character(s) examined of {result.decoded_chars} decoded"
    )
    if result.undecodable:
        report.append(f"    NOT TEXT: {result.undecodable[:5]}")

    if unreadable:
        # A hole in the coverage the floor is about to certify. Reporting it
        # and exiting 0 was the earlier behaviour, and it contradicted this
        # file's own rule that a scan which read too little is refused.
        violations.append(
            f"{len(unreadable)} tracked path(s) could not be read, for example "
            f"{unreadable[:5]}. That is a hole in the coverage this run would "
            f"otherwise certify, so it is refused rather than noted."
        )

    # The inventory git reported, NOT the list the loop above built. See
    # _coverage: deriving it from `opened` makes a narrowed walk invisible.
    violations += _coverage(result, inventory, "tree", (), also_accounted=unreadable)
    violations += [f"tracked: {entry}" for entry in result.findings]
    return violations, report


def _archive_members(dist: Path) -> tuple[Path, Path]:
    """The one wheel and the one sdist, or a configuration error.

    Refusing two is not pedantry. A stale artifact from an earlier build sits
    in the same directory, sorts before or after the new one by accident, and a
    scan of it reports on code that is no longer there while looking exactly
    like a scan of the release.
    """
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ConfigError(
            f"{dist} holds {len(wheels)} wheel(s) and {len(sdists)} sdist(s); "
            f"exactly one of each is required. Found {[p.name for p in wheels]} "
            f"and {[p.name for p in sdists]}. Build into a clean directory: a "
            f"stale artifact scanned in place of the new one is green about "
            f"code that is not being released."
        )
    return wheels[0], sdists[0]


def _reject_backslash(label: str, names: Iterable[str]) -> list[str]:
    """A backslash is a legal character in an archive member name.

    Path normalization is right for the tree boundary, where a Windows
    separator means a directory, and wrong here, where it does not. Rewriting
    it let a single flat member be read as living in a directory and pick up
    that directory's exemption. Such a name is refused rather than normalized,
    because no ordinary build produces one.
    """
    return [
        f"the {label} holds a member named {name!r}, which contains a "
        f"backslash. In an archive that is a filename character and not a "
        f"separator, so normalizing it would let a flat file inherit a "
        f"directory's exemption."
        for name in names
        if "\\" in name
    ]


def _wheel_names(wheel: Path) -> list[str]:
    """The archive's own table of contents, read on its own.

    Deliberately separate from ``_wheel_payload``: it is the inventory the
    coverage check measures the scan against, so a narrowing of the payload
    builder must not be able to shrink it too.
    """
    with zipfile.ZipFile(wheel) as archive:
        return [name for name in archive.namelist() if not name.endswith("/")]


def _wheel_payload(wheel: Path) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(wheel) as archive:
        return [(name, archive.read(name)) for name in archive.namelist() if not name.endswith("/")]


def _sdist_names(sdist: Path) -> list[str]:
    """The sdist's table of contents, relative to the distribution root."""
    with tarfile.open(sdist) as bundle:
        return [member.name.split("/", 1)[-1] for member in bundle.getmembers() if member.isfile()]


def _sdist_payload(sdist: Path) -> list[tuple[str, bytes]]:
    """Members by path RELATIVE to the distribution root.

    An sdist wraps everything in a single ``<name>-<version>/`` directory. Left
    in place, that prefix makes every exemption miss: a config naming
    ``LICENSE`` never matches ``thing-0.2.0/LICENSE``, so the whole exemption
    set silently stops applying and the scan reports offences in the very files
    a decision exempted.
    """
    payload: list[tuple[str, bytes]] = []
    with tarfile.open(sdist) as bundle:

        def entries() -> Iterator[tuple[str, bytes]]:
            for member in bundle.getmembers():
                handle = bundle.extractfile(member) if member.isfile() else None
                if handle is not None:
                    yield member.name.split("/", 1)[-1], handle.read()

        payload.extend(entries())
    return payload


def scan_dist(dist: Path, config: Config) -> tuple[list[str], list[str]]:
    """The built wheel and sdist, which is the only thing that cannot be wrong
    about its own contents."""
    report: list[str] = [f"ARTIFACT boundary, {dist}"]
    violations: list[str] = []

    # Required HERE, by the boundary that uses them. A run that reads an
    # archive and asserts nothing about what it read is the vacuous pass this
    # whole file exists to refuse; a run that never opens an archive owes no
    # such assertion.
    for label, floor in (("wheel", config.wheel_floor), ("sdist", config.sdist_floor)):
        if not floor:
            raise ConfigError(
                f"--dist was given but the config names no {label}-floor. An "
                f"archive scan that finds nothing looks exactly like a clean "
                f"archive, so at least one path it must CONTAIN AND READ has "
                f"to be named. A repository that builds no archive should not "
                f"pass --dist at all rather than declare a floor for one."
            )

    wheel, sdist = _archive_members(dist)
    for label, archive, names, payload, floor in (
        (
            "wheel",
            wheel,
            _wheel_names(wheel),
            _wheel_payload(wheel),
            config.wheel_floor,
        ),
        (
            "sdist",
            sdist,
            _sdist_names(sdist),
            _sdist_payload(sdist),
            config.sdist_floor,
        ),
    ):
        violations += _reject_backslash(label, names)
        if not names:
            violations.append(
                f"the {label} holds no readable member, so scanning it certifies nothing"
            )
        result = scan(payload, config)
        report.append(
            f"  {label} {archive.name}: {len(names)} member(s), scanned "
            f"{len(result.scanned)}, exempt {len(result.exempt)}, undecodable "
            f"{len(result.undecodable)}, {result.examined_chars} character(s) "
            f"examined"
        )
        # `names` is the archive's own table of contents, read separately from
        # the payload, for the reason given in _coverage.
        violations += _coverage(result, names, label, floor)
        violations += [f"{label}: {entry}" for entry in result.findings]

    return violations, report


def check(config: Config, tree: Path | None, dist: Path | None) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    report: list[str] = []
    ran: list[str] = []
    if tree is not None:
        found, lines = scan_tree(tree, config)
        violations += found
        report += lines
        ran.append("the versioned tree")
    if dist is not None:
        found, lines = scan_dist(dist, config)
        violations += found
        report += lines
        ran.append("the built wheel and sdist")
    # Which boundaries actually RAN, named on every run. A tree-only run is a
    # legitimate tier-1 invocation and a complete-sounding pass over half the
    # rule; saying so is the difference between the two.
    report.append(
        f"  VERIFIED: {' and '.join(ran)}; "
        f"{len(FORBIDDEN)} token pattern(s) over content AND path, "
        f"{len(config.exempt_paths)} exempt path(s), "
        f"{len(config.exempt_trees)} exempt tree(s)"
    )
    if dist is None:
        report.append(
            "  NOT VERIFIED: what actually ships. The tree boundary reasons "
            "about that; only the archive answers it."
        )
    if tree is None:
        report.append(
            "  NOT VERIFIED: anything written but not yet built. The archive "
            "answers what ships from this build and nothing about the tree it "
            "was built from."
        )
    return violations, report


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    opts: dict[str, str] = {}
    i = 0
    while i < len(argv):
        if not argv[i].startswith("--"):
            print(f"unrecognized argument {argv[i]!r}\n{USAGE}", file=sys.stderr)
            return 2
        if i + 1 >= len(argv):
            print(f"option {argv[i]!r} needs a value\n{USAGE}", file=sys.stderr)
            return 2
        opts[argv[i][2:]] = argv[i + 1]
        i += 2
    unknown = sorted(set(opts) - {"config", "tree", "dist"})
    if unknown:
        print(f"unknown option(s) {', '.join(unknown)}\n{USAGE}", file=sys.stderr)
        return 2
    if "config" not in opts:
        print(f"--config is required\n{USAGE}", file=sys.stderr)
        return 2
    if "tree" not in opts and "dist" not in opts:
        print(
            f"at least one of --tree and --dist is required; a run with "
            f"neither would exit 0 having read nothing\n{USAGE}",
            file=sys.stderr,
        )
        return 2

    try:
        config_path = Path(opts["config"]).resolve()
        if not config_path.is_file():
            raise ConfigError(
                f"no config at {config_path}. The exemption set and the floors "
                f"are a repository's own decisions and this checker will not "
                f"invent them: without them it would either flag every "
                f"authorship file or certify a scan with no floor at all."
            )
        config = load_config(config_path)
        violations, report = check(
            config,
            Path(opts["tree"]).resolve() if "tree" in opts else None,
            Path(opts["dist"]).resolve() if "dist" in opts else None,
        )
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2

    # Printed ALWAYS, clean or not. A checker whose passing run says nothing is
    # read as coverage it may not have.
    for line in report:
        print(line)
    sys.stdout.flush()
    if violations:
        print(f"\nREFUSED: {len(violations)} finding(s)", file=sys.stderr)
        for entry in violations:
            print(f"  - {entry}", file=sys.stderr)
        print(f"\nRemedy: {REMEDY}", file=sys.stderr)
        return 1
    print("\nno forbidden identifier found, within what the VERIFIED line above actually read")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
