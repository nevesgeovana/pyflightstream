"""Tier 1: a command this repository PUBLISHES is a command that runs.

Pipeline role: quality gate on reproducibility. Several committed files
tell a reader how to reproduce a measurement by printing a command line:
a script's module docstring, the version registry's own header, a
documentation page. Every one of those is a promise, and three of them
have been wrong.

WHAT THIS EXISTS TO CATCH, both measured on 2026-08-17 and 2026-08-18.
``src/pyflightstream/commands/_meta.yaml`` published the reproduction
command for the seventeen-page delta four claims rest on, and it omitted
the required ``--editions``, so the command as printed exits 2.
``scripts/restate_26123_notes.py`` documented itself with ``--dry-run``,
which its parser rejects, also exit 2. Both were found by a reader trying
the command, which is the expensive way.

HOW IT CHECKS, and the limits are stated because a guard that overclaims
is worse than none. The flags of each published invocation are read
statically, and the target script's own ``add_argument`` calls are read
statically too, so nothing is executed and no file is opened by the
scripts under test. A published flag the parser does not define is a
failure, and a required flag the invocation omits is a failure.

THREE LIMITS, all of them narrower than the title above.

It does not check whether the VALUES are usable: a placeholder such as
``<manifest>`` is a placeholder, and whether the file behind it exists is
not a property of the printed line.

It recognises ``scripts/*.py`` invocations ONLY. Every published console
script command, ``pyfs-qa probe ...``, ``pyfs-manual register ...``,
``pytest ...``, is outside it, and those are the commands a reader is
most likely to try. Widening it means resolving each console script to
its parser through the entry-point table, which is worth doing and is
registered rather than claimed here.

It searches the roots below and no others, so a reproduction published
under ``tests/`` or in an evidence directory's README is outside it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"

#: Where a published invocation may appear. Globbed from the filesystem
#: rather than asked of git, deliberately: a `git ls-files` population
#: answers differently before and after the commit that adds a file, and
#: an `--others` population makes tier 1 depend on whatever untracked
#: scratch a developer's tree happens to hold.
SEARCHED = (
    ("scripts", "*.py"),
    ("src", "**/*.py"),
    ("src", "**/*.yaml"),
    ("docs", "**/*.md"),
    ("", "*.md"),
)

#: A published reproduction: a line whose first token is the script,
#: with or without a ``python`` prefix. BOTH forms have shipped, and the
#: bare one is how the version registry printed its command until
#: 2026-08-18, so a pattern requiring the prefix would be blind to
#: exactly the file whose command was broken.
#:
#: ANCHORED AT THE START OF A LINE, which is the whole difference between
#: a command and a mention. Prose refers to these scripts constantly
#: ("``scripts/_mutation_harness.py`` states..."), a mention carries no
#: flags, and the required-flag rule below would read every one of them
#: as a defective command line.
_INVOCATION = re.compile(r"^[ \t]*(?:python[ \t]+)?(scripts/[A-Za-z0-9_]+\.py)(.*)$")

_FLAG = re.compile(r"--[a-z][a-z0-9-]*")


def _published_invocations() -> list[tuple[str, str, set[str]]]:
    """Return ``(source file, script, flags)`` for every published line.

    A published invocation may wrap: the version registry prints its
    command over two lines, indented. The continuation is joined when the
    next line starts with a flag once stripped, which is the only
    wrapping shape in the tree. The indentation is NOT tested, and this
    sentence said it was until 2026-08-18.
    """
    found: list[tuple[str, str, set[str]]] = []
    for directory, pattern in SEARCHED:
        root = REPO / directory if directory else REPO
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for index, line in enumerate(lines):
                match = _INVOCATION.match(line)
                if match is None:
                    continue
                tail = match.group(2)
                for following in lines[index + 1 :]:
                    stripped = following.strip()
                    # A SEPARATOR IS NOT A FLAG. `---` opens a markdown
                    # rule and a YAML document, and both start with two
                    # dashes, so the first version of this loop joined
                    # one and attributed everything after it to the
                    # command above.
                    if stripped.startswith("---"):
                        break
                    if stripped.startswith("--"):
                        tail += " " + stripped
                        continue
                    break
                # A COMMAND, NOT A SENTENCE. Prose wraps, so a line can
                # begin with a script name and continue into ordinary
                # English: `_meta.yaml` opens one with
                # "scripts/chm_to_pdf.py from the extracted archive, and
                # its page".
                #
                # THE FIRST VERSION OF THIS FILTER DEMANDED A FLAG and
                # dropped five real publishers with the one prose line:
                # a tail may legitimately open with a placeholder
                # (`<dir>`), a bracketed optional (`[label ...]`), a
                # comment (`# everything`), a label (`M1 M2 N1`) or a
                # version (`26.123`). Only PROSE opens with an ordinary
                # lowercase word, so that is what is tested, and the
                # floor at the bottom of this file names every publisher
                # so a filter cannot quietly shrink the population again.
                head = tail.strip().split(" ")[0] if tail.strip() else ""
                if head and head.isalpha() and head.islower():
                    continue
                found.append(
                    (
                        path.relative_to(REPO).as_posix(),
                        match.group(1),
                        set(_FLAG.findall(tail)),
                    )
                )
    return found


def _parser_flags(script: Path) -> tuple[set[str], set[str]]:
    """Return ``(every flag, the required ones)`` of a script's parser.

    Read from the source rather than by importing, so a script with a
    side effect at import time cannot be triggered by its own test.
    """
    every: set[str] = set()
    required: set[str] = set()
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if not isinstance(function, ast.Attribute) or function.attr != "add_argument":
            continue
        names = [
            argument.value
            for argument in node.args
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        ]
        flags = {name for name in names if name.startswith("--")}
        every |= flags
        for keyword in node.keywords:
            if (
                keyword.arg == "required"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
            ):
                required |= flags
    return every, required


def test_every_published_invocation_names_flags_its_parser_defines():
    """A flag nobody accepts turns a published reproduction into exit 2."""
    offenders = []
    for source, script, flags in _published_invocations():
        path = REPO / script
        if not path.is_file():
            offenders.append(f"{source}: publishes {script}, which does not exist")
            continue
        every, _ = _parser_flags(path)
        if not every:
            # A script with no argparse parser takes no flags, and a
            # published line for it should carry none.
            unknown = flags
        else:
            unknown = flags - every
        if unknown:
            offenders.append(
                f"{source}: {script} is published with {sorted(unknown)}, "
                f"which its parser does not define"
            )
    assert not offenders, (
        f"{len(offenders)} published command line(s) name a flag the script rejects, so "
        "the command as printed exits 2 for the reader who tries it.\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_every_published_invocation_carries_the_flags_its_parser_requires():
    """An omitted required flag is the same exit 2, from the other side."""
    offenders = []
    for source, script, flags in _published_invocations():
        path = REPO / script
        if not path.is_file():
            continue
        _, required = _parser_flags(path)
        missing = required - flags
        if missing:
            offenders.append(
                f"{source}: {script} is published without {sorted(missing)}, "
                f"which its parser requires"
            )
    assert not offenders, (
        f"{len(offenders)} published command line(s) omit a required flag, so the "
        "command as printed exits 2 for the reader who tries it. This is how the "
        "reproduction of the seventeen-page edition delta shipped.\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_the_search_finds_each_supported_invocation_shape(tmp_path, monkeypatch):
    """Exercise the walker and prose filter without pinning retired publishers."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    examples = ["<dir>", "[label ...]", "# everything", "M1 M2 N1", "26.123", "--input file"]
    for index, tail in enumerate(examples):
        (scripts / f"publisher{index}.py").write_text(
            f"python scripts/target.py {tail}\n", encoding="utf-8"
        )
    (scripts / "prose.py").write_text("scripts/target.py documents a tool\n", encoding="utf-8")
    monkeypatch.setattr("tests.tier1_offline.test_documented_invocations.REPO", tmp_path)
    found = _published_invocations()
    assert {source for source, _, _ in found} == {
        f"scripts/publisher{index}.py" for index in range(len(examples))
    }
