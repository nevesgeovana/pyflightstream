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


def _slashes(text: str) -> str:
    return text.replace("\\", "/")


@dataclasses.dataclass
class _Comparison:
    same: bool
    run_root: str | None
    rendered: list[str]
    executed: list[str]


def _compare_scripts(rendered: str, executed: str, shadow: Path) -> _Comparison:
    """Ask whether the executed script is the rendered one, once the roots are set aside.

    A run on a cluster names a POSIX root with forward slashes; a rebuild on
    Windows renders the shadow with backslashes (RST-5). Both sides are
    compared with every backslash turned into a forward slash, the workspace
    root on each side replaced by one token, and the interpreter path by
    another. The run's root is returned AS THE EXECUTED SCRIPT SPELLS IT.
    """
    shadow_form = _slashes(str(shadow))
    rendered_lines = [_slashes(line) for line in rendered.splitlines()]
    executed_raw = executed.splitlines()
    executed_lines = [_slashes(line) for line in executed_raw]
    run_root = None
    for index, line in enumerate(rendered_lines):
        if shadow_form not in line:
            continue
        head, tail = line.split(shadow_form, 1)
        candidates = ([index] if index < len(executed_lines) else []) + list(
            range(len(executed_lines))
        )
        for number in candidates:
            other = executed_lines[number]
            if (
                other.startswith(head)
                and other.endswith(tail)
                and len(other) >= len(head) + len(tail)
            ):
                middle = other[len(head) : len(other) - len(tail)]
                raw = executed_raw[number]
                run_root = (
                    raw[len(head) : len(head) + len(middle)] if len(raw) == len(other) else middle
                )
                break
        break
    token = "<workspace>"
    left = [
        _INTERPRETER.sub('"<python>"', line.replace(shadow_form, token)) for line in rendered_lines
    ]
    root_form = _slashes(run_root) if run_root else None
    right = [
        _INTERPRETER.sub('"<python>"', line.replace(root_form, token) if root_form else line)
        for line in executed_lines
    ]
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


def _drift(
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
        words = [word for word in left_words ^ right_words if len(word) > 2 and word != verb]
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
                else "from no input of the row (the package's own rendering)"
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
        at = ran[0][0] if ran else (ran_commands[i1][0] if i1 < len(ran_commands) else 0)
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
