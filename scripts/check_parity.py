#!/usr/bin/env python3
"""Prove that a release does everything the previous release did (GOAL-038 arm R1).

    python scripts/check_parity.py --workspace <recorded campaign> --out <parity.json>
    python scripts/check_parity.py --base v0.32.0 --release HEAD --workspace W --out F

WHAT IS COMPARED. Two trees of this repository, the base tag and the release
commit, each exported from git (never the working tree), each exercised in its
own interpreter process whose ``pyflightstream`` is asserted to be imported
from that tree:

1. **api**: every name in every ``__all__`` of the base still imports from the
   same dotted path at the release, and so does every public name a base module
   WITHOUT ``__all__`` offers (bound at module level, not starting with ``_``,
   not a module, not imported from outside the package; see
   :func:`offered_names`). ``stamp_derived_campaign`` is the one exemption,
   deleted by decision 9 of the 0.33 scope.
2. **cli**: every console script of the base ``pyproject.toml``, every
   subcommand, every option string and every ``choices`` value is still in the
   release parser (a parser diff; each parser is captured at the moment its
   ``main`` calls ``parse_args``).
3. **scripts**: the emitted scripts of the golden campaign set
   (``GOLDEN_RENDERS`` of ``tests/tier1_offline/test_workflows.py``) and of the
   tier-3 matrices (``tests.tier3_licensed.offline.render``), each rendered by
   its own tree, are byte-identical.
4. **post**: ``pyfs-matrix post`` over one recorded workspace, run by each
   tree's console-script target on a fresh copy at the same path, writes the
   same ``post/`` bytes, ``products.json`` included.

A difference in 3 or 4 passes only when :data:`NAMED_DIFFERENCES` names it with
a requirement that the release SRS defines, and, where the entry gives a line
pattern, only when every changed line matches it. Anything else is a failure.

CONTROLS. A comparator that cannot see a difference would report parity for
everything, so each run plants one difference per comparison into the real
observations (a name no module exports, a name a module without ``__all__``
lacks, a flag no parser has, one changed line of a render, one changed byte of
a product) and requires each to be caught; the reader of a module without
``__all__`` is also run over a planted module whose offered names are known. The
receipt records ``caught <k> of <k>``; anything less is PARITY: FAIL.

TEMPORARY FILES. The exported trees, the renders and the workspace copy live in
one temporary folder, deleted at the end of the run (``--keep`` keeps it).

The receipt names the SHA-256 of this script as committed at the release; a run
whose own bytes differ from that revision concludes PARITY: FAIL, because its
receipt would otherwise claim a script that did not produce it.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import difflib
import fnmatch
import hashlib
import importlib
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import types
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
SCRIPT = "scripts/check_parity.py"
EXPORTED = ("src", "tests", "docs/srs", "pyproject.toml")
PACKAGE = "pyflightstream"
MATRIX_CONSOLE = "pyfs-matrix"

#: Base names that may be absent at the release, with the decision that removed them.
API_EXEMPT = {"stamp_derived_campaign": "0.33 scope decision 9 deletes it"}

#: The message of a per-revolution drift warning, old or new wording: the column
#: drifts by a percentage of itself or, for a force or moment column, of the
#: scale of its group, between two revolutions, over the limit.
_DRIFT_MESSAGE = (
    r"rotor '[^']*' column \w+ drifts [+-][\d.]+ per cent "
    r"(?:of its scale [\d.eE+-]+ \(the magnitude of \w+, the largest (?:force|moment) mean "
    r"of its group in the earlier revolution; a change of [+-][\d.eE+-]+\) )?"
    r"between revolution \d+ and revolution \d+, over the drift limit of [\d.]+ per cent "
    r"\(\[per_revolution\] drift_limit_pct\): the last revolution is still moving"
)

#: Differences a named 0.33 requirement states. ``kind`` is "scripts" or "post";
#: ``pattern`` is an fnmatch glob over the render name or the post-relative file;
#: ``lines``, when given, is a regex every changed line must match; ``block``,
#: when given, is a regex the changed lines of one file, joined by line feeds,
#: must match whole, so a difference is held to its lines, their order and
#: their number; ``release_lacks``, when given, is a regex the release's own
#: text must NOT match, so a difference that removes lines is held to its
#: direction and to the state the requirement names.
NAMED_DIFFERENCES: list[dict[str, str]] = [
    {
        "kind": "scripts",
        "pattern": "*",
        # The disc speed lines and nothing else, each removed line followed by
        # the added line of the same disc index and the same magnitude with
        # the other sign: 0.33.0 handed the solver plus the block's hand times
        # the speed, 0.34.0 hands it minus (FR-331, measured in RPT-137).
        "lines": r"^SET_PROP_ACTUATOR_RPM \d+ -?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$",
        "block": (
            r"(?:SET_PROP_ACTUATOR_RPM (\d+) "
            r"(?:-(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\nSET_PROP_ACTUATOR_RPM \1 \2"
            r"|(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\nSET_PROP_ACTUATOR_RPM \1 -\3)"
            r"(?:\n|$))+"
        ),
        "requirement": "FR-331",
        "why": (
            "an actuator disc swirls its wake the way a rotor of the same rpm_sign "
            "turns: the disc speed handed to the solver is minus the block's hand "
            "times the speed, where 0.33.0 handed plus, the sense measured on 26.124 "
            "to swirl with the rotor"
        ),
    },
    {
        "kind": "scripts",
        "pattern": "*",
        # The section Cp plot's three export lines and the blank line closing
        # them, REMOVED from a script that cuts no section: the release must
        # carry neither a section command nor a section Cp plot, so a drop from
        # a row that still cuts a section, or an added plot, does not match.
        "lines": r"^(SET_PLOT_TYPE SECTIONS_CP|SAVE_PLOT_TO_FILE|.+_plot_cp_sections\.txt|)$",
        "block": (
            r"(SET_PLOT_TYPE SECTIONS_CP\nSAVE_PLOT_TO_FILE\n[^\n]+_plot_cp_sections\.txt\n"
            r"|\nSET_PLOT_TYPE SECTIONS_CP\nSAVE_PLOT_TO_FILE\n[^\n]+_plot_cp_sections\.txt)"
        ),
        "release_lacks": r"(?m)^(NEW_SURFACE_SECTION_DISTRIBUTION|SET_PLOT_TYPE SECTIONS_CP)\b",
        "requirement": "FR-51",
        "why": (
            "P0331-SECTIONS-ABSENT-FAMILY: a row whose geometry carries no family a "
            "section distribution of its artifact cuts declares and exports no section "
            "Cp plot; the solver writes no such file with no section to plot"
        ),
    },
    {
        "kind": "scripts",
        "pattern": "*",
        # The three lines of the counter's registration and nothing else: its
        # head, its command line (the interpreter as the render spells it, then
        # the program) and the blank line that closes the action. The diff may
        # place the blank line before or after the two, and nothing else.
        "lines": (
            r"^(SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE pfs_unsteady_counter"
            r'|"[^"]+" "actions/pfs_unsteady_actions\.py"|)$'
        ),
        "block": (
            r"(SET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE pfs_unsteady_counter\n"
            r'"[^"\n]+" "actions/pfs_unsteady_actions\.py"\n'
            r"|\nSET_NEW_UNSTEADY_SOLVER_ACTION COMMAND_LINE pfs_unsteady_counter\n"
            r'"[^"\n]+" "actions/pfs_unsteady_actions\.py")'
        ),
        "requirement": "FR-314",
        "why": (
            "every unsteady row registers the step counter; a row asking no per-step "
            "export gains the count-only counter's registration, on a build that "
            "documents the unsteady solver action"
        ),
    },
    {
        "kind": "post",
        "pattern": "*/post.log",
        # Only a per-revolution drift WARNING record: the whole line, down to
        # the closing clause. A changed line of any other warning, or of this
        # warning with another wording, does not match and fails.
        "lines": (
            r"^WARNING point=\S+ product=probes/\S+_per_revolution_\S+\.csv: "
            rf"{_DRIFT_MESSAGE}$"
        ),
        "requirement": "FR-180",
        "why": (
            "a force or moment column's per-revolution drift is judged against the "
            "scale of its group, so the warning records are worded and counted anew; "
            "the products are byte-identical"
        ),
    },
    {
        "kind": "post",
        "pattern": "*/post.log.json",
        # The record's own fixed lines as the log writes them (indent 1 and 3),
        # its point, its per-revolution product, its message and its constant
        # category. A line of any other record, or of another level, fails.
        "lines": (
            r"^(  \{|  \},?"
            r'|   "point": "P\d+-[^"]*",'
            r'|   "product": "probes/[^"]*_per_revolution_[^"]*\.csv",'
            rf'|   "message": "{_DRIFT_MESSAGE}",'
            r'|   "remedy": null,|   "category": "postprocessing",|   "severity": "warning")$'
        ),
        "requirement": "FR-180",
        "why": (
            "the machine-readable form of the same per-revolution drift warning "
            "records, which FR-180 words and counts anew"
        ),
    },
]

#: Rewrites applied to both sides of a post file before comparison, as
#: (file glob, regex, replacement, reason). Only measured volatile fields.
_STAMP = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:[+-]\d\d:\d\d|Z)"
POST_NORMALIZE: list[tuple[str, str, str, str]] = [
    (
        "*/post.log",
        rf"(?m)^time={_STAMP}(?=\r?$)",
        "time=<TIME>",
        "the wall-clock stamp of each log record; measured 2026-09-30 as the only difference",
    ),
    (
        "*/post.log.json",
        rf'"time": "{_STAMP}"',
        '"time": "<TIME>"',
        "the same stamp in the machine-readable log",
    ),
]

TEXT_SUFFIXES = {".csv", ".json", ".log", ".txt", ".md", ".dat", ".vtk", ".toml", ".fs"}
PLANTED_NAME = "__parity_control_name__"
PLANTED_FLAG = "--parity-control-flag"
#: The planted controls a run must catch: three api, one cli, one scripts, one post.
CONTROLS = 6


# --------------------------------------------------------------------------- collectors
# These run inside a child interpreter whose sys.path starts at one exported tree.


def _assert_tree(tree: Path) -> None:
    module = importlib.import_module(PACKAGE)
    where = Path(module.__file__ or "").resolve()
    if tree.resolve() not in where.parents:
        raise SystemExit(f"{PACKAGE} imported from {where}, not from the tree {tree}")


def _is_package_import(node: ast.ImportFrom) -> bool:
    """Return whether a ``from ... import`` statement reads from this package."""
    module = node.module or ""
    return node.level > 0 or module == PACKAGE or module.startswith(f"{PACKAGE}.")


def _module_bindings(source: str) -> dict[str, set[str]]:
    """Map every name bound at module level to how it is bound.

    The kinds are ``defined`` (a def, a class, an assignment or any other
    binding statement), ``package`` (imported from this package) and
    ``outside`` (imported from anywhere else). Statements nested in a module
    level ``if``, ``try`` or ``with`` count; function and class bodies do not.
    """
    kinds: dict[str, set[str]] = {}

    def bind(name: str, kind: str) -> None:
        kinds.setdefault(name, set()).add(kind)

    def targets(node: ast.AST) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name):
                bind(sub.id, "defined")

    def visit(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bind(node.name, "defined")
            elif isinstance(node, ast.ImportFrom):
                kind = "package" if _is_package_import(node) else "outside"
                for alias in node.names:
                    if alias.name != "*":
                        bind(alias.asname or alias.name, kind)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    bind(alias.asname or alias.name.partition(".")[0], "outside")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    targets(target)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                targets(node.target)
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                targets(node.target)
                visit(node.body + node.orelse)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if item.optional_vars is not None:
                        targets(item.optional_vars)
                visit(node.body)
            elif isinstance(node, ast.If):
                visit(node.body + node.orelse)
            elif isinstance(node, ast.Try):
                handlers = [stmt for h in node.handlers for stmt in h.body]
                visit(node.body + handlers + node.orelse + node.finalbody)

    visit(ast.parse(source).body)
    return kinds


def offered_names(module: Any, source: str) -> list[str]:
    """Return the public names a module without ``__all__`` offers.

    A name is offered when it is bound at module level, does not start with
    ``_``, is not a module object, and is not imported from outside this
    package: it is defined in the module, or re-exported from another module of
    the package. A function or class re-exported from the package whose own
    ``__module__`` lies outside it (``Path`` passed along by a sibling) is not
    offered by the package, and neither is a name the source never binds
    unless its object's ``__module__`` is in the package.
    """
    kinds = _module_bindings(source)
    offered = []
    for name, value in vars(module).items():
        if name.startswith("_") or inspect.ismodule(value):
            continue
        bound = kinds.get(name, set())
        owner = getattr(value, "__module__", None)
        named_object = inspect.isclass(value) or inspect.isroutine(value)
        foreign = (
            named_object
            and isinstance(owner, str)
            and owner != PACKAGE
            and not owner.startswith(f"{PACKAGE}.")
        )
        if "defined" in bound:
            offered.append(name)
        elif "package" in bound:
            if not foreign:
                offered.append(name)
        elif not bound and named_object and not foreign:
            offered.append(name)
    return sorted(offered)


#: The classifier's control: a planted module source and the names it must offer.
_CLASSIFIER_SOURCE = (
    "from __future__ import annotations\n"
    "import os\n"
    "from pathlib import Path\n"
    f"from {PACKAGE} import __name__ as package_name\n"
    "LIMIT = 3\n"
    "def act() -> None: ...\n"
    "class Kind: ...\n"
    "_hidden = 1\n"
)
_CLASSIFIER_OFFERS = ["Kind", "LIMIT", "act", "package_name"]


def classifier_control() -> bool:
    """Run :func:`offered_names` over a planted module; return whether it is exact."""
    planted = types.ModuleType(f"{PACKAGE}._parity_control_module")
    exec(compile(_CLASSIFIER_SOURCE, "<parity control>", "exec"), planted.__dict__)  # noqa: S102
    return offered_names(planted, _CLASSIFIER_SOURCE) == _CLASSIFIER_OFFERS


def collect_api(tree: Path) -> dict[str, Any]:
    """Every ``__all__`` of the tree, the names of each module without one, and failures.

    ``exports`` holds each ``__all__`` by module; ``offered`` holds, for every
    module that has no ``__all__``, the public names :func:`offered_names` finds.
    """
    src = tree / "src"
    exports: dict[str, list[str]] = {}
    offered: dict[str, list[str]] = {}
    unimportable: dict[str, str] = {}
    for path in sorted((src / PACKAGE).rglob("*.py")):
        rel = path.relative_to(src).with_suffix("")
        if rel.name == "__main__":
            continue
        parts = rel.parts[:-1] if rel.name == "__init__" else rel.parts
        name = ".".join(parts)
        try:
            module = importlib.import_module(name)
        except BaseException as exc:  # noqa: BLE001 - a module that exits is reported
            unimportable[name] = f"{type(exc).__name__}: {exc}"[:300]
            continue
        names = getattr(module, "__all__", None)
        if names is not None:
            exports[name] = sorted(str(n) for n in names)
        else:
            offered[name] = offered_names(module, path.read_text(encoding="utf-8"))
    return {
        "exports": exports,
        "offered": offered,
        "unimportable": unimportable,
        "classifier_control": classifier_control(),
    }


def resolve_api(pairs: list[list[str]]) -> list[str]:
    """Return ``module.name`` for every pair that no longer imports."""
    missing = []
    for module_name, name in pairs:
        try:
            module = importlib.import_module(module_name)
            if not hasattr(module, name):
                importlib.import_module(f"{module_name}.{name}")
        except BaseException:  # noqa: BLE001 - any failure to import is the finding
            missing.append(f"{module_name}.{name}")
    return missing


class _CapturedError(Exception):
    def __init__(self, parser: argparse.ArgumentParser) -> None:
        super().__init__("parser captured")
        self.parser = parser


def _capture_parser(target: str) -> argparse.ArgumentParser:
    module_name, _, attr = target.partition(":")
    main = getattr(importlib.import_module(module_name), attr)

    def grab(self: argparse.ArgumentParser, *args: Any, **kwargs: Any) -> Any:
        raise _CapturedError(self)

    saved = argparse.ArgumentParser.parse_args, argparse.ArgumentParser.parse_known_args
    argparse.ArgumentParser.parse_args = grab  # type: ignore[method-assign,assignment]
    argparse.ArgumentParser.parse_known_args = grab  # type: ignore[method-assign,assignment]
    try:
        # "--help", never an empty argv: pyfs-fsi called bare runs a coupling
        # step in the working directory. The parse is intercepted before help.
        main(["--help"])
    except _CapturedError as caught:
        return caught.parser
    finally:
        argparse.ArgumentParser.parse_args = saved[0]  # type: ignore[method-assign]
        argparse.ArgumentParser.parse_known_args = saved[1]  # type: ignore[method-assign]
    raise RuntimeError(f"{target} returned without parsing its arguments")


def _spellings(parser: argparse.ArgumentParser, path: str, out: set[str]) -> None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                out.add(f"{path} {name}")
                _spellings(sub, f"{path} {name}", out)
            continue
        label = " ".join(action.option_strings) if action.option_strings else None
        for option in action.option_strings:
            out.add(f"{path} {option}")
        if action.choices is not None and not isinstance(action.choices, dict):
            key = action.option_strings[0] if label else f"<{action.dest}>"
            for choice in action.choices:
                out.add(f"{path} {key}={choice}")


def collect_cli(tree: Path) -> dict[str, Any]:
    """Every console script of the tree's pyproject and its accepted spellings."""
    project = tomllib.loads((tree / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = project["project"]["scripts"]
    spellings: set[str] = set()
    unavailable: dict[str, str] = {}
    for console, target in sorted(scripts.items()):
        try:
            parser = _capture_parser(target)
        except BaseException as exc:  # noqa: BLE001 - reported per console script
            unavailable[console] = f"{type(exc).__name__}: {exc}"[:300]
            continue
        spellings.add(console)
        _spellings(parser, console, spellings)
    return {"targets": dict(scripts), "spellings": sorted(spellings), "unavailable": unavailable}


def collect_scripts(tree: Path) -> dict[str, str]:
    """Every golden-campaign and tier-3 render of the tree, by name."""
    sys.path.insert(0, str(tree / "tests" / "tier1_offline"))
    from test_workflows import GOLDEN_RENDERS, golden_name, render_or_refusal
    from tests.tier3_licensed import offline

    renders: dict[str, str] = {}
    for name, label, build in GOLDEN_RENDERS:
        renders[f"workflows/{golden_name(name, label, build)}"] = render_or_refusal(
            name, label, build
        )
    for matrix in offline.matrices():
        _, rendered = offline.render(matrix)
        for stem, text in rendered.items():
            renders[f"tier3/{matrix.stem}/{stem}"] = text
    return renders


def child(mode: str, tree: Path, out: Path, argument: Path | None) -> int:
    """Run one collector in this process and write its JSON result."""
    _assert_tree(tree)
    result: Any
    if mode == "api":
        result = collect_api(tree)
    elif mode == "resolve":
        assert argument is not None
        result = resolve_api(json.loads(argument.read_text(encoding="utf-8")))
    elif mode == "cli":
        result = collect_cli(tree)
    elif mode == "scripts":
        result = collect_scripts(tree)
    else:
        raise SystemExit(f"unknown collector {mode!r}")
    out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return 0


# --------------------------------------------------------------------------- the parent


def git(*args: str, binary: bool = False) -> Any:
    """Run git in this repository and return its output."""
    done = subprocess.run(
        ["git", "-C", str(REPO), *args],
        check=True,
        capture_output=True,
        # Explicit, and identical to the inherited default: git needs the
        # ambient environment to find its own configuration.
        env=os.environ.copy(),
    )
    return done.stdout if binary else done.stdout.decode("utf-8").strip()


def export(sha: str, tree: Path) -> None:
    """Extract ``EXPORTED`` of one commit into ``tree``, replacing what is there."""
    if tree.exists():
        shutil.rmtree(tree)
    tree.mkdir(parents=True)
    data = git("archive", "--format=tar", sha, "--", *EXPORTED, binary=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(tree, filter="data")


def child_env(tree: Path) -> dict[str, str]:
    """Return the environment in which a child imports ``tree``."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(tree / "src"), str(tree)])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_child(python: str, mode: str, tree: Path, work: Path, argument: Path | None = None) -> Any:
    """Run one collector in a child interpreter over ``tree`` and return its result."""
    out = work / f"{mode}.json"
    command = [python, str(Path(__file__).resolve()), "--collect", mode, "--tree", str(tree)]
    command += ["--collect-out", str(out)]
    if argument is not None:
        command += ["--collect-arg", str(argument)]
    done = subprocess.run(command, cwd=tree, env=child_env(tree), capture_output=True, timeout=3600)
    if done.returncode != 0:
        tail = done.stderr.decode("utf-8", "replace")[-2000:]
        raise SystemExit(f"collector {mode} failed in {tree} (exit {done.returncode}):\n{tail}")
    return json.loads(out.read_text(encoding="utf-8"))


def run_post(python: str, tree: Path, source: Path, ws: Path, keep: Path) -> dict[str, Any]:
    """Post a fresh copy of ``source`` at ``ws`` with the tree's pyfs-matrix; keep post/."""
    if ws.exists():
        shutil.rmtree(ws)
    shutil.copytree(source, ws, ignore=lambda d, names: ["post"] if Path(d) == source else [])
    project = tomllib.loads((tree / "pyproject.toml").read_text(encoding="utf-8"))
    module_name, _, attr = project["project"]["scripts"][MATRIX_CONSOLE].partition(":")
    code = f"import sys; from {module_name} import {attr} as m; sys.exit(m(sys.argv[1:]))"
    command = [python, "-c", code, "post", "--workspace", str(ws)]
    done = subprocess.run(command, cwd=ws, env=child_env(tree), capture_output=True, timeout=3600)
    if keep.exists():
        shutil.rmtree(keep)
    if (ws / "post").exists():
        shutil.move(str(ws / "post"), str(keep))
    shutil.rmtree(ws)
    return {
        "exit": done.returncode,
        "stderr_tail": done.stderr.decode("utf-8", "replace")[-800:],
    }


def read_tree(root: Path) -> dict[str, bytes]:
    """Return every file under ``root`` by its relative POSIX path."""
    if not root.exists():
        return {}
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def normalize(name: str, data: bytes) -> bytes:
    """Apply the :data:`POST_NORMALIZE` rules whose glob matches ``name``."""
    rules = [r for r in POST_NORMALIZE if fnmatch.fnmatch(name, r[0])]
    if not rules:
        return data
    text = data.decode("utf-8")
    for _, pattern, replacement, _ in rules:
        text = re.sub(pattern, replacement, text)
    return text.encode("utf-8")


def changed_lines(old: str, new: str) -> list[str]:
    """Return the removed and added lines between two texts."""
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
    return [line[1:] for line in diff if line[:1] in "+-" and not line.startswith(("+++", "---"))]


def name_difference(
    kind: str, name: str, old: str | None, new: str | None, defined: set[str]
) -> dict[str, Any]:
    """Describe one difference and attach the requirement that states it, if any."""
    entry: dict[str, Any] = {"state": "missing" if new is None else "changed"}
    lines = changed_lines(old or "", new or "") if old is not None and new is not None else []
    if lines:
        entry["first_changed_lines"] = lines[:6]
        entry["changed_line_count"] = len(lines)
    for named in NAMED_DIFFERENCES:
        if named["kind"] != kind or not fnmatch.fnmatch(name, named["pattern"]):
            continue
        if new is None:
            continue
        pattern = named.get("lines")
        if pattern and not all(re.search(pattern, line) for line in lines):
            continue
        block = named.get("block")
        if block and not re.fullmatch(block, "\n".join(lines)):
            continue
        lacks = named.get("release_lacks")
        if lacks and re.search(lacks, new):
            continue
        if named["requirement"] not in defined:
            entry["unnamed_because"] = f"{named['requirement']} is not defined in the release SRS"
            continue
        entry["requirement"] = named["requirement"]
        entry["why"] = named["why"]
        break
    return entry


def compare_texts(
    kind: str, key: str, base: dict[str, str], release: dict[str, str], defined: set[str]
) -> dict[str, Any]:
    """Compare every base item with its release counterpart, naming each difference."""
    differing = []
    for name in sorted(base):
        new = release.get(name)
        if new == base[name]:
            continue
        differing.append({key: name, **name_difference(kind, name, base[name], new, defined)})
    return {
        "checked": len(base),
        "differing": differing,
        "added_at_release": sorted(set(release) - set(base)),
    }


def srs_ids(tree: Path) -> set[str]:
    """Return every requirement id the tree's ``docs/srs`` pages mention."""
    text = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in (tree / "docs" / "srs").rglob("*.md")
    )
    return set(re.findall(r"\b(?:FR|NFR|IR|DR|AD|CR|SR|QR)-\d+[a-z]?\b", text))


def api_pairs(api: dict[str, Any], key: str = "exports") -> list[list[str]]:
    """Flatten the collected ``exports`` (or ``offered``) into ``[module, name]`` pairs."""
    return [[m, n] for m, names in sorted(api[key].items()) for n in names]


def as_text(files: dict[str, bytes]) -> dict[str, str]:
    """Decode post products for comparison; a non-text file compares by its digest."""
    out = {}
    for name, data in files.items():
        data = normalize(name, data)
        if Path(name).suffix.lower() in TEXT_SUFFIXES:
            out[name] = data.decode("utf-8", "replace")
        else:
            out[name] = "sha256:" + hashlib.sha256(data).hexdigest()
    return out


def parity(args: argparse.Namespace) -> dict[str, Any]:
    """Measure both trees and return the receipt."""
    base_sha = git("rev-parse", f"{args.base}^{{commit}}")
    release_sha = git("rev-parse", f"{args.release}^{{commit}}")
    try:
        committed = git("show", f"{release_sha}:{SCRIPT}", binary=True)
    except subprocess.CalledProcessError:
        committed = None
    running = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    failures: list[str] = []
    if committed is None:
        failures.append(f"{SCRIPT} is not committed at the release {release_sha[:8]}")
    elif committed.replace(b"\r\n", b"\n") != running:
        failures.append(f"the running {SCRIPT} differs from its revision at {release_sha[:8]}")

    temp = Path(tempfile.mkdtemp(prefix="pfs-parity-", dir=args.temp))
    tree, ws = temp / "tree", temp / "ws"
    python = args.python
    try:
        # The base tree first, then the release tree AT THE SAME PATH, so no
        # absolute path in a render or a product can differ between them.
        export(base_sha, tree)
        (temp / "base").mkdir()
        api_base = run_child(python, "api", tree, temp / "base")
        cli_base = run_child(python, "cli", tree, temp / "base")
        scripts_base = run_child(python, "scripts", tree, temp / "base")
        post_run_base = run_post(python, tree, args.workspace, ws, temp / "post-base")

        export(release_sha, tree)
        (temp / "release").mkdir()
        listed = api_pairs(api_base)
        offered = api_pairs(api_base, "offered")
        listed_pairs = [p for p in listed if p[1] not in API_EXEMPT]
        offered_pairs = [p for p in offered if p[1] not in API_EXEMPT]
        pairs = [*listed_pairs, *offered_pairs]
        exempt = [f"{m}.{n}" for m, n in [*listed, *offered] if n in API_EXEMPT]
        # The second planted name sits in the first module without __all__, so
        # the path that reads such modules is itself shown able to fail.
        planted_module = min(api_base["offered"], default=PACKAGE)
        planted = [*pairs, [PACKAGE, PLANTED_NAME], [planted_module, PLANTED_NAME]]
        request = temp / "release" / "pairs.json"
        request.write_text(json.dumps(planted), encoding="utf-8")
        missing_api = run_child(python, "resolve", tree, temp / "release", request)
        cli_release = run_child(python, "cli", tree, temp / "release")
        scripts_release = run_child(python, "scripts", tree, temp / "release")
        post_run_release = run_post(python, tree, args.workspace, ws, temp / "post-release")
        defined = srs_ids(tree)

        post_base = as_text(read_tree(temp / "post-base"))
        post_release = as_text(read_tree(temp / "post-release"))
    finally:
        if args.keep:
            print(f"kept {temp}")
        else:
            shutil.rmtree(temp, ignore_errors=True)

    controls: list[str] = []
    planted_key = f"{PACKAGE}.{PLANTED_NAME}"
    planted_offered = f"{planted_module}.{PLANTED_NAME}"
    if planted_key in missing_api:
        controls.append("api: a name no module exports was reported missing")
    if planted_module != PACKAGE and planted_offered in missing_api:
        controls.append(
            f"api: a name {planted_module} (no __all__) lacks at the release was reported missing"
        )
    if api_base.get("classifier_control") is True:
        controls.append(
            "api: the reader of a module without __all__ offered exactly its defined and "
            "package names of a planted module, and none of its outside imports"
        )
    missing_api = [m for m in missing_api if m not in (planted_key, planted_offered)]
    offered_keys = {f"{m}.{n}" for m, n in offered_pairs}
    api = {
        "checked": len(pairs),
        "checked_from_all": len(listed_pairs),
        "checked_without_all": len(offered_pairs),
        "modules": len(api_base["exports"]),
        "modules_without_all": len(api_base["offered"]),
        "missing": missing_api,
        "missing_without_all": [m for m in missing_api if m in offered_keys],
        "exempt": {name: API_EXEMPT[name.rsplit(".", 1)[1]] for name in exempt},
        "unimportable_at_base": api_base["unimportable"],
    }

    base_spellings, release_spellings = set(cli_base["spellings"]), set(cli_release["spellings"])
    planted_flag = f"{MATRIX_CONSOLE} {PLANTED_FLAG}"
    if planted_flag in (base_spellings | {planted_flag}) - release_spellings:
        controls.append("cli: a flag no parser has was reported refused")
    cli = {
        "checked": len(base_spellings),
        "missing": sorted(base_spellings - release_spellings),
        "added_at_release": len(release_spellings - base_spellings),
        "unavailable_at_base": cli_base["unavailable"],
        "unavailable_at_release": cli_release["unavailable"],
    }

    scripts = compare_texts("scripts", "name", scripts_base, scripts_release, defined)
    post = compare_texts("post", "file", post_base, post_release, defined)
    post["workspace"] = str(args.workspace)
    post["exit"] = {"base": post_run_base["exit"], "release": post_run_release["exit"]}
    for side, run in (("base", post_run_base), ("release", post_run_release)):
        if run["exit"] != 0:
            post[f"stderr_{side}"] = run["stderr_tail"]
    post["normalized"] = [
        {"files": g, "pattern": p, "replacement": r, "why": why} for g, p, r, why in POST_NORMALIZE
    ]

    # The two text controls: one changed line of a real render and one changed
    # byte of a real product must each come back differing and unnamed.
    if scripts_base:
        victim = sorted(scripts_base)[0]
        mutated = {**scripts_base, victim: scripts_base[victim] + "PARITY CONTROL\n"}
        probe = compare_texts("scripts", "name", scripts_base, mutated, defined)["differing"]
        if [d["name"] for d in probe if "requirement" not in d] == [victim]:
            controls.append(f"scripts: a changed line of {victim} was reported unnamed")
    if post_base:
        victim = sorted(post_base)[0]
        mutated = {**post_base, victim: post_base[victim] + "\x00"}
        probe = compare_texts("post", "file", post_base, mutated, defined)["differing"]
        if [d["file"] for d in probe if "requirement" not in d] == [victim]:
            controls.append(f"post: a changed byte of {victim} was reported unnamed")

    if not pairs:
        failures.append("no public name was compared")
    if missing_api:
        failures.append(f"{len(missing_api)} public names of the base no longer import")
    if not base_spellings or cli["missing"]:
        failures.append(f"{len(cli['missing'])} console spellings of the base are refused")
    if cli_release["unavailable"]:
        failures.append(
            f"console scripts do not build at the release: {cli_release['unavailable']}"
        )
    for kind, block, key in (("scripts", scripts, "name"), ("post", post, "file")):
        if not block["checked"]:
            failures.append(f"no {kind} were compared")
        loose = [d[key] for d in block["differing"] if "requirement" not in d]
        if loose:
            failures.append(f"{len(loose)} {kind} differ without a named requirement: {loose[:3]}")
    if post["exit"] != {"base": 0, "release": 0}:
        failures.append(f"post exited {post['exit']}")
    if len(controls) != CONTROLS:
        failures.append(f"the planted controls caught {len(controls)} of {CONTROLS}")

    return {
        "script": SCRIPT,
        "script_sha256": hashlib.sha256(committed).hexdigest() if committed is not None else None,
        "base_ref": args.base,
        "base_sha": base_sha,
        "release_ref": args.release,
        "release_sha": release_sha,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "api": api,
        "cli": cli,
        "scripts": scripts,
        "post": post,
        "named_differences": NAMED_DIFFERENCES,
        "controls": {"caught": f"caught {len(controls)} of {CONTROLS}", "detail": controls},
        "failures": failures,
        "verdict": "PARITY: FAIL" if failures else "PARITY: PASS",
    }


def main(argv: list[str] | None = None) -> int:
    """Compare the base and the release trees and write the parity receipt."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", default="v0.32.0", help="the previous release tag")
    parser.add_argument("--release", default="HEAD", help="the release commit")
    parser.add_argument("--workspace", type=Path, help="a recorded campaign workspace to post")
    parser.add_argument("--out", type=Path, help="where the JSON receipt is written")
    parser.add_argument("--python", default=sys.executable, help="interpreter for both trees")
    parser.add_argument("--temp", default=None, help="parent of the one temporary folder")
    parser.add_argument("--keep", action="store_true", help="keep the temporary folder")
    parser.add_argument("--collect", help=argparse.SUPPRESS)
    parser.add_argument("--tree", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--collect-out", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--collect-arg", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.collect:
        return child(args.collect, args.tree, args.collect_out, args.collect_arg)
    if args.workspace is None or args.out is None:
        parser.error("--workspace and --out are required")
    if not (args.workspace / "runs.json").is_file():
        parser.error(f"{args.workspace} is not a recorded workspace (no runs.json)")

    receipt = parity(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"api {receipt['api']['checked']} names, cli {receipt['cli']['checked']} spellings, "
        f"scripts {receipt['scripts']['checked']}, post {receipt['post']['checked']} files, "
        f"{receipt['controls']['caught']}"
    )
    for failure in receipt["failures"]:
        print(f"FAIL: {failure}")
    print(receipt["verdict"])
    return 0 if receipt["verdict"] == "PARITY: PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
