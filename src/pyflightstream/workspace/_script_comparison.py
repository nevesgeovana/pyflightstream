"""Shared read-only script comparison for rebuild and ledger diff (FR-391).

Pipeline role: normalize workspace and interpreter paths before comparing
commands, and attribute changed commands to their input files. The run layer
imports this workspace helper so every comparison uses the same rules.
"""

from __future__ import annotations

import contextlib
import dataclasses
import difflib
import re
from collections.abc import Sequence
from pathlib import Path

#: A quoted interpreter path in a rendered script, which names the Python that wrote it.
_INTERPRETER = re.compile(r'"[^"\n]*[\\/]python[w]?[0-9.]*(?:\.exe)?"', re.IGNORECASE)

#: The drift classes a difference between the executed and the rendered script
#: is named by, keyed by the verb that opens the line. A line of no listed verb
#: whose token is a group of the row's pproc is a renamed group.
_DRIFT_VERBS = {
    "EXPORT_SOLVER_ANALYSIS_VTK": "VTK export line",
    "SET_SOLVER_ANALYSIS_LOADS_FRAME": "loads frame line",
    "SET_PLOT_TYPE": "plot type line",
}


def slashes(text: str) -> str:
    return text.replace("\\", "/")


@dataclasses.dataclass
class _Comparison:
    same: bool
    run_root: str | None
    rendered: list[str]
    executed: list[str]


#: The characters that continue a file name; a root is set aside only at a path boundary.
_NAME_CHAR = "A-Za-z0-9_.-"

#: The token a workspace root is replaced by, and the one the interpreter path is.
_ROOT_TOKEN = "<workspace>"

_MESSAGE = re.compile(r"\s*PRINT(?:\s|$)")


def _root_regex(root: str) -> str:
    """Return a pattern for ``root`` that reads a backslash and a slash alike, at a boundary."""
    separator = r"[\\/]+"
    parts = [re.escape(part) for part in re.split(separator, root.strip()) if part]
    lead = separator if root.strip()[:1] in ("/", "\\") else ""
    return rf"(?<![{_NAME_CHAR}]){lead}{separator.join(parts)}(?![{_NAME_CHAR}])"


def _set_root(line: str, root: str, token: str) -> str:
    """Replace each path that starts at ``root`` with ``token`` and its tail with forward slashes.

    Only a path under the root changes spelling; the rest of the line, a message
    text above all, is left as written. A root is matched whole, so ``/ws`` does
    not match inside ``/ws2``.
    """
    if not root.strip("\\/ "):
        return line
    pattern = re.compile(_root_regex(root) + r"(?P<tail>[^\"'\s]*)")
    return pattern.sub(lambda found: token + slashes(found.group("tail")), line)


def normalise_line(line: str, root: str | None) -> str:
    """Return one script line with its root and its interpreter each set to one token.

    The backslashes of a line become forward slashes (a rebuild on Windows
    renders them, a cluster writes the others), except in a ``PRINT`` line,
    whose message text is compared as written: only the paths under the root
    and the interpreter path change there.
    """
    if root:
        line = _set_root(line, root, _ROOT_TOKEN)
    line = _INTERPRETER.sub('"<python>"', line)
    return line if _MESSAGE.match(line) else slashes(line)


def _find_run_root(
    shadow: str, rendered: list[str], executed: list[str], raw: list[str]
) -> str | None:
    """Return the root the executed script spells where the rendered one names the shadow."""
    pattern = re.compile(_root_regex(shadow))
    for index, line in enumerate(rendered):
        found = list(pattern.finditer(line))
        if not found:
            continue
        regex, at = "", 0
        for number, match in enumerate(found):
            regex += re.escape(line[at : match.start()])
            regex += "(?P<root>.+?)" if number == 0 else "(?P=root)"
            at = match.end()
        compiled = re.compile(regex + re.escape(line[at:]), re.DOTALL)
        for number in ([index] if index < len(executed) else []) + list(range(len(executed))):
            whole = compiled.fullmatch(executed[number])
            if whole:
                return raw[number][whole.start("root") : whole.end("root")]
    return None


def compare_scripts(rendered: str, executed: str, shadow: Path) -> _Comparison:
    """Ask whether the executed script is the rendered one, once the roots are set aside.

    A run on a cluster names a POSIX root with forward slashes; a rebuild on
    Windows renders the shadow with backslashes (RST-5). The workspace root on
    each side is replaced by one token (the paths under it written with forward
    slashes) and the interpreter path by another. The run's root is returned AS
    THE EXECUTED SCRIPT SPELLS IT; it is looked for in every rendered line that
    names the shadow until one of them matches an executed line.
    """
    shadow_form = str(shadow)
    rendered_raw, executed_raw = rendered.splitlines(), executed.splitlines()
    run_root = _find_run_root(
        shadow_form,
        [slashes(line) for line in rendered_raw],
        [slashes(line) for line in executed_raw],
        executed_raw,
    )
    left = [normalise_line(line, shadow_form) for line in rendered_raw]
    right = [normalise_line(line, run_root) for line in executed_raw]
    return _Comparison(left == right, run_root, left, right)


#: Where each drift class's lines come from when no changed word names an
#: input: the row's inputs under these folders are the candidates.
_DRIFT_HOMES = {
    "VTK export line": ("pproc/",),
    "loads frame line": ("pproc/", "references/"),
    "plot type line": ("pproc/",),
}

_VERB = re.compile(r"^[A-Z][A-Z0-9_]*(?:\s|$)")


def _commands(lines: Sequence[str]) -> list[tuple[int, str]]:
    """Group script lines into commands: a verb line and the argument lines after it."""
    commands: list[tuple[int, list[str]]] = []
    for number, line in enumerate(lines):
        if not line.strip():
            continue
        if _VERB.match(line) or not commands:
            commands.append((number, [line.strip()]))
        else:
            commands[-1][1].append(line.strip())
    return [(number, " | ".join(parts)) for number, parts in commands]


def drift(
    comparison: _Comparison, inputs: Path, input_files: Sequence[str], *, limit: int | None = 6
) -> str:
    """Name each difference between the executed and the rendered script (RST-8).

    The scripts are compared command by command (a verb and its argument
    lines). Each changed command says what it is (a VTK export line, the
    loads frame line, a plot type line, a renamed pproc group, or a script
    line) and which of the row's inputs holds the text the package renders
    there now, so a reader knows WHICH input changed after the run rather
    than only that something did. An input is named when it holds a word the
    two sides differ by; failing that, the inputs a class's lines come from
    are named as candidates.
    """
    texts = {}
    for name in input_files:
        with contextlib.suppress(OSError, UnicodeDecodeError):
            texts[name] = (inputs / name).read_text(encoding="utf-8")
    items = _changed_commands(comparison)
    described: list[str] = []
    for line, left, right in items[:limit]:
        verb = (left or right).split(" ")[0]
        what = _DRIFT_VERBS.get(verb)
        left_words = {word for word in re.split(r"[\s,|]+", left) if word}
        right_words = {word for word in re.split(r"[\s,|]+", right) if word}
        differing = sorted(word for word in left_words ^ right_words if word != verb)
        words = [word for word in differing if len(word) > 2]
        holders = sorted(
            name
            for name, text in texts.items()
            if any(
                re.search(rf"(?<![A-Za-z0-9_]){re.escape(word)}(?![A-Za-z0-9_])", text)
                for word in words
            )
        )
        if what is None:
            what = (
                "pproc group renamed"
                if any(name.startswith("pproc/") for name in holders)
                else "script line"
            )
        if holders:
            where = f"from inputs/{', inputs/'.join(holders)}"
        else:
            homes = _DRIFT_HOMES.get(what, ())
            candidates = [name for name in input_files if name.startswith(homes)] if homes else []
            where = (
                f"from inputs/{', inputs/'.join(candidates)} (candidates)"
                if candidates
                else (
                    f"from an input not identified: the changed text {differing[:4]} is too "
                    "short to attribute to one"
                    if differing and not words
                    else "from no input of the row (the package's own rendering)"
                )
            )
        described.append(
            f"line {line + 1}: ran {left[:90] or '(nothing)'!r}, renders "
            f"{right[:90] or '(nothing)'!r} ({what}, {where})"
        )
    if limit is not None and len(items) > limit:
        described.append(f"and {len(items) - limit} more changed command(s)")
    return "; ".join(described) or (
        f"ran {len(comparison.executed)} lines, renders {len(comparison.rendered)}"
    )


def _changed_commands(comparison: _Comparison) -> list[tuple[int, str, str]]:
    """Pair inserted, removed and replaced commands with their original line numbers."""
    ran_commands = _commands(comparison.executed)
    render_commands = _commands(comparison.rendered)
    matcher = difflib.SequenceMatcher(
        a=[text for _, text in ran_commands],
        b=[text for _, text in render_commands],
        autojunk=False,
    )
    items: list[tuple[int, str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ran = list(ran_commands[i1:i2])
        renders = list(render_commands[j1:j2])
        # A command rendered after the last executed one lands after the
        # executed script's last line, not at its first.
        at = (
            ran[0][0]
            if ran
            else (ran_commands[i1][0] if i1 < len(ran_commands) else len(comparison.executed))
        )
        while ran or renders:
            if ran and renders and ran[0][1].split(" ")[0] == renders[0][1].split(" ")[0]:
                (line, left), (_, right) = ran.pop(0), renders.pop(0)
            elif ran and (
                not renders
                or ran[0][1].split(" ")[0] not in {text.split(" ")[0] for _, text in renders}
            ):
                (line, left), right = ran.pop(0), ""
            else:
                left, (line, right) = "", renders.pop(0)
                line = at
            items.append((line, left, right))
    return items
