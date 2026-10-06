"""P0380-DOCS (FR-424 docs, owner request of 2026-10-06): every pyfs-matrix option in the sheet.

The parser of ``pyfs-matrix`` is captured the way the generated command-line
reference captures it (``scripts/gen_cli_reference.py``: the entry point's own
``main`` is called and its first parse is intercepted), every subcommand is
walked, and every option string of every subcommand must appear somewhere in
the cheatsheet sources, ``guide/latex-sources/04-cheatsheet/text/*.tex``.

Both sides are read through one normalization, so a source may write an option
in any LaTeX form the decks use: ``\\_`` for ``_``, ``-{}-`` or ``\\-\\-`` for
``--``. LaTeX comments are dropped first, so a commented-out line documents
nothing.

An option left out on purpose goes in :data:`ALLOWED_ABSENT` with its reason.
The list is empty: every option is documented, which is the preferred state.

What it does NOT check: that an option is described in its own subcommand's
entry, or truthfully (``test_p0330_cheatsheet.py`` holds page 1 to the
entries), nor the compiled PDF.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections.abc import Iterable
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = REPO / "guide" / "latex-sources" / "04-cheatsheet" / "text"
ENTRY_POINT = "pyflightstream.run.cli:main"

#: Options of pyfs-matrix the cheatsheet leaves out on purpose, each with its
#: reason. Empty: prefer documenting an option to listing it here.
ALLOWED_ABSENT: dict[str, str] = {}


def _generator():
    spec = importlib.util.spec_from_file_location(
        "gen_cli_reference", REPO / "scripts" / "gen_cli_reference.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs: a dataclass looks its module up by name.
    sys.modules["gen_cli_reference"] = module
    spec.loader.exec_module(module)
    return module


def _parser() -> argparse.ArgumentParser:
    """A fresh capture of the parser ``pyfs-matrix`` builds, safe to mutate."""
    return _generator().capture_parser(ENTRY_POINT)


def parser_options(parser: argparse.ArgumentParser) -> list[tuple[str, str]]:
    """Return ``(subcommand, option string)`` for every option of every subcommand.

    An alias shares its parser object with the subcommand it aliases, so each
    parser is read once, under the first name the selector lists.
    """
    generator = _generator()
    seen: set[int] = set()
    found: list[tuple[str, str]] = []
    for name, _help, sub in generator.subcommands(parser):
        if id(sub) in seen:
            continue
        seen.add(id(sub))
        for action in generator.options(sub):
            found.extend((name, option) for option in action.option_strings)
    return found


def normalize(text: str) -> str:
    """Read LaTeX as a reader sees it: comments dropped, escaped dashes and underscores plain."""
    text = re.sub(r"(?<!\\)%.*", "", text)
    text = text.replace("\\_", "_").replace("\\-", "-")
    return re.sub(r"-\{\}", "-", text)


def cheatsheet_text(sources: Iterable[Path] | None = None) -> str:
    """Return every cheatsheet source joined, normalized."""
    files = sorted(SOURCES.glob("*.tex")) if sources is None else list(sources)
    assert files, f"no cheatsheet source under {SOURCES}"
    return "\n".join(normalize(path.read_text(encoding="utf-8")) for path in files)


def _named(option: str, text: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(option)}(?![\w-])", text) is not None


def missing_options(
    options: Iterable[tuple[str, str]], text: str, allowed: dict[str, str] | None = None
) -> list[str]:
    """Return ``<subcommand>: <option>`` for each option the normalized text never names.

    Parameters
    ----------
    options : iterable of (str, str)
        The parser's output, ``(subcommand, option string)`` pairs.
    text : str
        The normalized cheatsheet sources.
    allowed : dict of str to str, optional
        Options left out on purpose; :data:`ALLOWED_ABSENT` when None.

    Returns
    -------
    list of str
        One line per missing option, in the parser's order. Empty when complete.
    """
    allowed = ALLOWED_ABSENT if allowed is None else allowed
    return [
        f"{sub}: {option}"
        for sub, option in options
        if option not in allowed and not _named(normalize(option), text)
    ]


def test_every_option_of_every_pyfs_matrix_subcommand_is_in_the_cheatsheet():
    """P0380-DOCS (FR-424 docs, owner request of 2026-10-06): no option of pyfs-matrix is missing.

    A floor on the walk, so a capture that reads nothing cannot pass: 0.37.0
    offers 23 subcommands (an alias read once) and 219 option strings, help
    included.
    """
    options = parser_options(_parser())
    assert len({sub for sub, _ in options}) >= 23, len({sub for sub, _ in options})
    assert len(options) >= 200, len(options)
    missing = missing_options(options, cheatsheet_text())
    assert not missing, (
        "the cheatsheet sources never name these options of pyfs-matrix:\n"
        + "\n".join(missing)
        + f"\n\nDocument each in {SOURCES.relative_to(REPO).as_posix()}/*.tex, or add it to "
        "ALLOWED_ABSENT with its reason."
    )


def test_a_planted_option_in_a_copy_of_the_parser_output_is_named():
    """P0380-DOCS (FR-424 docs, owner request of 2026-10-06): control, a planted option fails.

    Planted twice: in a copy of the parser's output, and as a real argument of
    a freshly captured parser, so both the check and the walk can fail.
    """
    text = cheatsheet_text()
    options = parser_options(_parser())
    assert missing_options(options, text) == []
    planted = [*options, ("collect", "--planted-option")]
    assert missing_options(planted, text) == ["collect: --planted-option"]
    parser = _parser()
    collect = next(sub for name, _, sub in _generator().subcommands(parser) if name == "collect")
    collect.add_argument("--planted-flag", action="store_true")
    assert missing_options(parser_options(parser), text) == ["collect: --planted-flag"]


def test_the_normalization_reads_every_latex_form_and_drops_comments():
    """P0380-DOCS (FR-424 docs, owner request of 2026-10-06): escaped forms pass, cut lines fail.

    An option written ``-{}-`` or ``\\-\\-`` still counts; one removed from
    every source, or left only in a comment, is named.
    """
    options = [("collect", "--discard-walltime"), ("plan", "--cost-file")]
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(SOURCES.glob("*.tex")))
    assert "--discard-walltime" in text and "--cost-file" in text
    braced = text.replace("--discard-walltime", "-{}-discard-walltime")
    escaped = braced.replace("--cost-file", "\\-\\-cost\\-file")
    assert missing_options(options, normalize(escaped)) == []
    removed = text.replace("--discard-walltime", "")
    assert missing_options(options, normalize(removed)) == ["collect: --discard-walltime"]
    commented = re.sub(r"^(.*--cost-file)", r"% \1", text, flags=re.M)
    assert missing_options(options, normalize(commented)) == ["plan: --cost-file"]


def test_the_allow_list_names_only_real_absent_options():
    """P0380-DOCS (FR-424 docs, owner request of 2026-10-06): no stale or unknown allow-list entry.

    An allowed option must be an option of the parser and still absent from
    the sources; once it is documented it leaves the list. The control shows
    the check would refuse an option the sheet already names.
    """
    options = {option for _, option in parser_options(_parser())}
    text = cheatsheet_text()

    def stale(allowed: dict[str, str]) -> list[str]:
        return [
            option
            for option, reason in allowed.items()
            if option not in options or _named(option, text) or not reason.strip()
        ]

    assert stale(ALLOWED_ABSENT) == []
    assert stale({"--watch": "planted: documented already"}) == ["--watch"]
    assert stale({"--no-such-option": "planted: not an option"}) == ["--no-such-option"]
