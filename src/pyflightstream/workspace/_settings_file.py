"""The workspace settings files, ``pyfs.toml`` and this machine's ``pyfs.local.toml`` (FR-436).

A user who runs the same commands day after day writes once, in the workspace,
the defaults of the options she would otherwise type on every command: the
version, the HPC profile, the cost file, the acceptance of the installed build,
how much the console says. This module is the one reader of those two files and
the one place their defaults reach a parsed command line.

THE FILES (FR-436 R1, R2). ``pyfs.toml`` at the workspace root is the
workspace's own file, meant to be versioned; ``pyfs.local.toml`` beside it is
this machine's overlay, meant to be kept out of version control as
``inputs/executables.local.toml`` is, and is read over ``pyfs.toml`` key by
key. Either may exist without the other. Each holds an optional
``schema_version = 1``, a ``[defaults]`` table and a ``[log]`` table, and
nothing else. A key of ``[defaults]`` is a long option without its leading
dashes, inner dashes written as underscores; ``[log]`` holds ``console`` and
``pproc_warnings``.

WHAT A FILE MAY SET (R3, R4). Only the facts about the workspace or the machine
in :data:`DEFAULT_KEYS`, each with the type its option takes. A key that acts on
one invocation (:data:`ACT_KEYS`), a key no command takes, ``workspace`` (which
is what locates the file), another table, a value of the wrong type, a console
level outside :data:`~pyflightstream._console.CONSOLE_LEVELS` and a file that is
not valid TOML are each refused before any work, naming the key (or the parse
error) and the file.

PRECEDENCE (the requirement's sentence). An option typed on the command line
wins over ``pyfs.local.toml``, which wins over ``pyfs.toml``, which wins over the
package default. The command line is told apart from silence by withholding the
parser's defaults (:func:`withhold_defaults`): an option still holding the
withheld marker after the parse was not typed, and only then does a file, or
the package default, answer for it (:func:`take_defaults`). A workspace without
either file therefore parses exactly as before.

PROVENANCE (R7, R8). The values a command took from a file, and the file each
came from, are held for the length of the invocation
(:func:`invocation_sources`), so ``plan.json`` and every run record can name
them. A value typed, or left at the package default, is recorded as before.

The reading lives in the workspace row because the files are the workspace's;
the command lines of both programs import it, downward.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pyflightstream._cli import for_this_invocation, set_console_level, set_post_warning_policy
from pyflightstream._console import CONSOLE_LEVELS
from pyflightstream._errors import InputArtifactError
from pyflightstream.workspace.builds import LOCAL_EXECUTABLES_FILE

__all__ = [
    "ACT_KEYS",
    "DEFAULT_KEYS",
    "ENTRY_ACCEPTANCE_SOURCE",
    "LOCAL_SETTINGS_FILE",
    "LOG_KEYS",
    "SETTINGS_FILE",
    "TYPED_ACCEPTANCE_SOURCE",
    "WITHHELD",
    "Invocation",
    "TakenDefaults",
    "Withheld",
    "WorkspaceSettings",
    "console_only",
    "declare_invocation",
    "defaults_lines",
    "entry_acceptance_allowed",
    "invocation",
    "invocation_sources",
    "parsed",
    "read_workspace_settings",
    "settings_supplied",
    "take_defaults",
    "typed_value",
    "withhold_defaults",
]

#: The workspace's own settings file, at the workspace root, meant to be versioned.
SETTINGS_FILE = "pyfs.toml"
#: This machine's overlay of :data:`SETTINGS_FILE`, beside it, meant to stay unversioned.
LOCAL_SETTINGS_FILE = "pyfs.local.toml"
#: The one schema this package reads; ``schema_version`` may be left out.
_SCHEMA_VERSION = 1

#: The source a record names for an acceptance stated on a build entry of
#: ``inputs/executables.local.toml`` (FR-436 R7, R8): the file's name, as R8 writes it.
ENTRY_ACCEPTANCE_SOURCE = LOCAL_EXECUTABLES_FILE
#: The source a record names for an acceptance typed on the command line, written
#: only beside another value taken from a file (FR-436 R8).
TYPED_ACCEPTANCE_SOURCE = "typed"

#: Every key ``[defaults]`` may set, and the kind of value its option takes:
#: ``text`` a string, ``switch`` a boolean, ``count`` a whole number,
#: ``texts`` a list of strings (a repeatable option). Each is a fact about the
#: workspace or the machine, never a decision about one invocation (R3).
DEFAULT_KEYS: Mapping[str, str] = MappingProxyType(
    {
        "fs_version": "text",
        "hpc": "text",
        "cost_file": "text",
        "runs": "text",
        "accept_unregistered_build": "switch",
        "fs_exe": "text",
        "point_name": "text",
        "recipe": "texts",
        "workflow": "texts",
        "ignore_missing_families": "switch",
        "check_frozen": "switch",
        "progress_every": "count",
        "local": "switch",
    }
)

#: Every key ``[log]`` may set, and its kind: the console level and the grouped
#: post-processing warnings.
LOG_KEYS: Mapping[str, str] = MappingProxyType({"console": "level", "pproc_warnings": "switch"})

#: The options that act on one invocation: refused in a file, because a file that
#: made one of them the default would act without being asked (R4).
ACT_KEYS = (
    "apply",
    "yes",
    "overwrite",
    "resume",
    "force_rerun",
    "force_rerun_all",
    "discard_walltime",
    "sims",
    "points",
    "no_post",
    "update_ids",
    "watch",
    "rounds",
    "from_sims",
)

_KIND_WORDS = {
    "text": "a string",
    "switch": "true or false",
    "count": "a whole number",
    "texts": "a list of strings",
    "level": "a string",
}

#: The option whose bare flag states the negation of a settable switch, when the
#: two are separate destinations: the file must not answer over a typed negation.
_NEGATIONS = MappingProxyType({"ignore_missing_families": "refuse_missing_families"})


@dataclass(frozen=True)
class WorkspaceSettings:
    """What the two settings files of one workspace state, merged.

    Attributes
    ----------
    root : Path
        The workspace folder the files were looked for in.
    defaults : Mapping of str to object
        The ``[defaults]`` keys, ``pyfs.local.toml`` read over ``pyfs.toml``.
    log : Mapping of str to object
        The ``[log]`` keys, merged the same way.
    sources : Mapping of str to str
        The file each value came from, keyed as ``defaults`` is and, for
        ``[log]``, as ``log.<key>``.
    """

    root: Path
    defaults: Mapping[str, object] = field(default_factory=dict)
    log: Mapping[str, object] = field(default_factory=dict)
    sources: Mapping[str, str] = field(default_factory=dict)


def read_workspace_settings(root: str | Path) -> WorkspaceSettings:
    """Read, check and merge the settings files of one workspace (FR-436 R1 to R4).

    Parameters
    ----------
    root : str or Path
        The workspace folder: the one ``--workspace`` names, or the current
        directory.

    Returns
    -------
    WorkspaceSettings
        Empty where neither file exists, which leaves every command as it was.

    Raises
    ------
    InputArtifactError
        A file that is not valid TOML, a table other than ``[defaults]`` and
        ``[log]``, an act, ``workspace``, a key no command takes, a value of
        the wrong type, a console level outside the three, or a schema this
        package does not read; the message names the key and the file.
    """
    folder = Path(root)
    defaults: dict[str, object] = {}
    log: dict[str, object] = {}
    sources: dict[str, str] = {}
    for name in (SETTINGS_FILE, LOCAL_SETTINGS_FILE):
        path = folder / name
        if not path.is_file():
            continue
        tables = _checked(path)
        for key, value in tables.get("defaults", {}).items():
            defaults[key] = value
            sources[key] = name
        for key, value in tables.get("log", {}).items():
            log[key] = value
            sources[f"log.{key}"] = name
    return WorkspaceSettings(folder, defaults, log, sources)


def _checked(path: Path) -> dict[str, dict[str, object]]:
    """Return the two tables of one settings file, refusing whatever R4 refuses."""
    try:
        with open(path, "rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise InputArtifactError(
            f"{path} is not valid TOML: {error}. Nothing ran: the workspace settings are "
            "read before any work."
        ) from error
    tables: dict[str, dict[str, object]] = {}
    for name, value in raw.items():
        if name == "schema_version":
            _check_schema(value, path)
        elif name in ("defaults", "log") and isinstance(value, dict):
            check = _check_default if name == "defaults" else _check_log
            for key, entry in value.items():
                check(key, entry, path)
            tables[name] = value
        else:
            raise InputArtifactError(
                f"{path} states {name!r} at the top level, and a workspace settings file "
                "holds schema_version, a [defaults] table and a [log] table and nothing "
                "else. Nothing ran."
            )
    return tables


def _check_schema(value: object, path: Path) -> None:
    if isinstance(value, bool) or value != _SCHEMA_VERSION:
        raise InputArtifactError(
            f"{path} states schema_version = {value!r}, and this package reads "
            f"schema_version = {_SCHEMA_VERSION}. Nothing ran."
        )


def _check_default(key: str, value: object, path: Path) -> None:
    """Refuse one ``[defaults]`` key that is not settable, or holds the wrong kind of value."""
    if key == "workspace":
        raise InputArtifactError(
            f"{path} [defaults] sets 'workspace', which is what locates this file and so "
            "is never one of its keys; state workspace (CLI: --workspace) on the command. "
            "Nothing ran."
        )
    if key in ACT_KEYS:
        raise InputArtifactError(
            f"{path} [defaults] sets {key!r}, which acts on one invocation and is never a "
            f"default; state {key} (CLI: --{key.replace('_', '-')}) on the command that "
            "should do it. "
            "Nothing ran."
        )
    kind = DEFAULT_KEYS.get(key)
    if kind is None:
        raise InputArtifactError(
            f"{path} [defaults] has the key {key!r}, which no command takes as a default. "
            f"The keys [defaults] may set are {', '.join(DEFAULT_KEYS)}: each is a long "
            "option without its leading dashes, inner dashes written as underscores, as "
            "each command's help lists them. Nothing ran."
        )
    _check_kind(f"[defaults] {key}", kind, value, path)


def _check_log(key: str, value: object, path: Path) -> None:
    """Refuse one ``[log]`` key this package does not read, or a level outside the three."""
    kind = LOG_KEYS.get(key)
    if kind is None:
        raise InputArtifactError(
            f"{path} [log] has the key {key!r}, and [log] holds "
            f"{' and '.join(LOG_KEYS)} and nothing else. Nothing ran."
        )
    _check_kind(f"[log] {key}", kind, value, path)
    if kind == "level" and value not in CONSOLE_LEVELS:
        raise InputArtifactError(
            f"{path} [log] {key} = {value!r}, and the console levels are "
            f"{', '.join(CONSOLE_LEVELS)}. Nothing ran."
        )


def _check_kind(where: str, kind: str, value: object, path: Path) -> None:
    """Refuse a value whose type is not the one its option takes."""
    if kind == "switch":
        good = isinstance(value, bool)
    elif kind == "count":
        good = isinstance(value, int) and not isinstance(value, bool)
    elif kind == "texts":
        good = isinstance(value, list) and all(isinstance(item, str) for item in value)
    else:
        good = isinstance(value, str)
    if not good:
        raise InputArtifactError(
            f"{path} {where} = {value!r} is a {type(value).__name__}, and {where.split()[-1]} "
            f"takes {_KIND_WORDS[kind]}. Nothing ran."
        )


# --- the command line: defaults withheld, then taken --------------------------------


class Withheld:
    """The marker an option holds after the parse when the command line did not state it.

    A repeatable option copies its default before appending to it, so a copy of
    the marker is an empty list: a typed ``--recipe`` starts from nothing, as it
    does with the package's own empty default.
    """

    def __copy__(self) -> list[object]:
        return []

    def __repr__(self) -> str:
        return "<not typed>"


#: The one marker :func:`withhold_defaults` installs.
WITHHELD = Withheld()


@dataclass
class _Held:
    """The defaults one parser had before they were withheld, and its relaxed requirements."""

    defaults: dict[tuple[int, str], object] = field(default_factory=dict)
    relaxed: set[tuple[int, str]] = field(default_factory=set)


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """Return every subcommand's parser by name, aliases included."""
    found: dict[str, argparse.ArgumentParser] = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            found.update(action.choices)
    return found


def _dests(sub: argparse.ArgumentParser) -> Iterator[tuple[str, argparse.Action]]:
    """Yield each settable or console destination of a parser once, with its first action."""
    seen: set[str] = set()
    names = {*DEFAULT_KEYS, "log_level", "verbose", "pproc_warnings"}
    for action in sub._actions:
        # Options only: a positional sharing a key's name (the recipe id of
        # `free-space`) is never typed as an option, so no file answers for it.
        if not action.option_strings:
            continue
        if action.dest in names and action.dest not in seen:
            seen.add(action.dest)
            yield action.dest, action


@contextmanager
def withhold_defaults(
    parser: argparse.ArgumentParser, *, supplied: Mapping[str, object] | None = None
) -> Iterator[_Held]:
    """Hold the defaults of every settable option back for the length of one parse.

    Inside, each settable option of each subcommand defaults to
    :data:`WITHHELD`, so an option still holding it after the parse was not
    typed. The parser's own defaults are put back on the way out, whatever
    happened inside, so the parser a reader inspects (``--help``, the
    generated command-line reference) shows the package's defaults.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The program's parser, whose subcommands are walked.
    supplied : Mapping of str to object, optional
        The ``[defaults]`` keys a settings file already states, read before
        the parse: a REQUIRED option a file supplies stops being required at
        the parse, and is required again by :func:`take_defaults` if no file
        answers for it after all. None relaxes nothing.

    Yields
    ------
    _Held
        What :func:`take_defaults` needs to restore a default nobody stated.
    """
    held = _Held()
    changed: list[tuple[argparse.Action, object, bool]] = []
    for sub in {id(sub): sub for sub in _subparsers(parser).values()}.values():
        for dest, _first in _dests(sub):
            same = (action for action in sub._actions if action.dest == dest)
            for action in (action for action in same if action.option_strings):
                changed.append((action, action.default, action.required))
                held.defaults.setdefault((id(sub), dest), action.default)
                action.default = WITHHELD
                if action.required and supplied is not None and dest in supplied:
                    action.required = False
                    held.relaxed.add((id(sub), dest))
    try:
        yield held
    finally:
        for action, default, required in changed:
            action.default, action.required = default, required


@dataclass(frozen=True)
class TakenDefaults:
    """What one command took from the settings files.

    Attributes
    ----------
    sources : Mapping of str to str
        The file each value taken came from, ``[log]`` keys as ``log.<key>``.
    values : Mapping of str to object
        The values taken, keyed as ``sources``.
    console : str or None
        The console level the command line or a file chose through
        ``--log-level`` or ``[log] console``; None where ``--verbose`` or
        nothing chose it, which the console already reads as before.
    post_warnings : bool or None
        The grouped post-processing warnings a file or ``--no-pproc-warnings``
        chose; None where the command line's own flag answers as before.
    refused_acceptance : bool
        ``--no-accept-unregistered-build`` was typed: no route accepts.
    """

    sources: Mapping[str, str] = field(default_factory=dict)
    values: Mapping[str, object] = field(default_factory=dict)
    console: str | None = None
    post_warnings: bool | None = None
    refused_acceptance: bool = False


def take_defaults(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    held: _Held,
    settings: WorkspaceSettings,
) -> TakenDefaults:
    """Give every option the command line did not state its file default, else its own.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The program's parser, as :func:`withhold_defaults` left it.
    args : argparse.Namespace
        The parsed command line, changed in place.
    held : _Held
        What :func:`withhold_defaults` returned.
    settings : WorkspaceSettings
        The workspace's settings files, read.

    Returns
    -------
    TakenDefaults
        The values taken from a file, where each came from, and the console
        choices the command line or a file made.
    """
    sub = _subparsers(parser)[args.subcommand]
    sources: dict[str, str] = {}
    values: dict[str, object] = {}
    typed: dict[str, object] = {}
    for dest, action in _dests(sub):
        current = getattr(args, dest, WITHHELD)
        if current is not WITHHELD:
            typed[dest] = current
            continue
        negation = _NEGATIONS.get(dest)
        if dest in settings.defaults and not (negation and getattr(args, negation, False)):
            value = settings.defaults[dest]
            if isinstance(value, str) and callable(action.type):
                value = action.type(value)
            setattr(args, dest, value)
            sources[dest], values[dest] = settings.sources[dest], value
            continue
        _restore(sub, args, dest, action, held)
    console = _console_choice(args, typed, settings, sources, values)
    post = _post_warnings_choice(args, typed, settings, sources, values)
    refused = typed.get("accept_unregistered_build") is False
    return TakenDefaults(sources, values, console, post, refused)


def _restore(
    sub: argparse.ArgumentParser,
    args: argparse.Namespace,
    dest: str,
    action: argparse.Action,
    held: _Held,
) -> None:
    """Give an option nobody stated its package default, required where it was required."""
    if dest in ("log_level", "verbose", "pproc_warnings"):
        default = held.defaults.get((id(sub), dest))
        setattr(args, dest, default)
        return
    if (id(sub), dest) in held.relaxed:
        sub.error(f"the following arguments are required: {'/'.join(action.option_strings)}")
    default = held.defaults.get((id(sub), dest))
    if isinstance(default, str) and callable(action.type):
        default = action.type(default)
    setattr(args, dest, default)


def _console_choice(
    args: argparse.Namespace,
    typed: Mapping[str, object],
    settings: WorkspaceSettings,
    sources: dict[str, str],
    values: dict[str, object],
) -> str | None:
    """Resolve ``--log-level``, ``--verbose`` and ``[log] console`` for a command taking them."""
    if not hasattr(args, "log_level"):
        return None
    level: str | None = None
    if "log_level" in typed:
        level = str(typed["log_level"])
    elif typed.get("verbose") is not True and "console" in settings.log:
        level = str(settings.log["console"])
        sources["log.console"], values["log.console"] = settings.sources["log.console"], level
    shown = level or ("verbose" if typed.get("verbose") is True else "normal")
    args.log_level = shown
    args.verbose = shown == "verbose"
    return level


def _post_warnings_choice(
    args: argparse.Namespace,
    typed: Mapping[str, object],
    settings: WorkspaceSettings,
    sources: dict[str, str],
    values: dict[str, object],
) -> bool | None:
    """Resolve ``--pproc-warnings``, ``--no-pproc-warnings`` and ``[log] pproc_warnings``."""
    if not hasattr(args, "pproc_warnings"):
        return None
    if "pproc_warnings" in typed:
        args.pproc_warnings = bool(typed["pproc_warnings"])
        return None if args.pproc_warnings else False
    if "pproc_warnings" in settings.log:
        chosen = bool(settings.log["pproc_warnings"])
        key = "log.pproc_warnings"
        sources[key], values[key] = settings.sources[key], chosen
        args.pproc_warnings = chosen
        return chosen
    args.pproc_warnings = False
    return None


def parsed(parser: argparse.ArgumentParser, argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse a command line, then take what it did not state from the workspace files.

    The one entry ``pyfs-matrix`` parses through (FR-436): an option typed
    wins over ``pyfs.local.toml``, which wins over ``pyfs.toml``, which wins
    over the package default, and a workspace holding neither file parses
    exactly as before. A file the reader refuses stops the command here,
    exit 2, before its console opens and before anything is written.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The program's parser, with its subcommands.
    argv : sequence of str or None
        The command line; None reads ``sys.argv``.

    Returns
    -------
    argparse.Namespace
        The parsed command line, every option it did not state filled in.
    """
    supplied = settings_supplied(_named_workspace(argv))
    with withhold_defaults(parser, supplied=supplied) as held:
        args = parser.parse_args(argv)
    try:
        settings = read_workspace_settings(getattr(args, "workspace", None) or ".")
        taken = take_defaults(parser, args, held, settings)
    except InputArtifactError as error:
        print(f"workspace settings refused: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    declare_invocation(taken, verbose=bool(getattr(args, "verbose", False)))
    return args


def _named_workspace(argv: Sequence[str] | None) -> str:
    """Return the folder ``--workspace`` names on a command line, else the current one (R1).

    Read before the full parse, so the REQUIRED options a file supplies are
    relaxed against the files of the workspace the command names, not of
    wherever it was typed. The tokens are scanned rather than parsed: a second
    parser would be the first ``parse_args`` a reader of the command line (the
    generated command-line reference) catches. ``--workspace PATH`` and
    ``--workspace=PATH`` are read, the last one winning as in the parse; a
    malformed one is the full parse's to refuse, in its own words.
    """
    tokens = sys.argv[1:] if argv is None else list(argv)
    named = "."
    for index, token in enumerate(tokens):
        if token == "--":
            break
        if token == "--workspace" and index + 1 < len(tokens):
            named = tokens[index + 1]
        elif token.startswith("--workspace="):
            named = token.partition("=")[2]
    return named or "."


def console_only(settings: WorkspaceSettings) -> TakenDefaults:
    """Return what ``pyfs-workspace`` takes from the files: the ``[log]`` console only (R9).

    Parameters
    ----------
    settings : WorkspaceSettings
        The workspace's settings files, read and checked as every command reads them.

    Returns
    -------
    TakenDefaults
        The console level of ``[log]`` and its file, or nothing; no key of
        ``[defaults]`` reaches a ``pyfs-workspace`` command.
    """
    if "console" not in settings.log:
        return TakenDefaults()
    level = str(settings.log["console"])
    source = settings.sources["log.console"]
    return TakenDefaults({"log.console": source}, {"log.console": level}, level)


def defaults_lines(taken: TakenDefaults) -> list[str]:
    """Return the lines a ``verbose`` command prints before its work (FR-436 R8).

    Parameters
    ----------
    taken : TakenDefaults
        What the command took from the settings files.

    Returns
    -------
    list of str
        One titled block: each value taken and the file it came from; empty
        where nothing came from a file.
    """
    if not taken.sources:
        return []
    lines = ["Defaults taken from the workspace settings files"]
    for key, source in taken.sources.items():
        lines.append(f"  {key} = {_shown(taken.values.get(key))}  ({source})")
    return [*lines, ""]


def _shown(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


# --- the invocation: what the records name ---------------------------------------


@dataclass(frozen=True)
class Invocation:
    """What one command-line invocation took from the settings files, for its records.

    Attributes
    ----------
    sources : Mapping of str to str
        The file each value taken came from (FR-436 R8).
    entry_acceptance : bool
        Whether an ``accept_unregistered_build`` on a build entry of
        ``inputs/executables.local.toml`` may accept its build; False when
        ``--no-accept-unregistered-build`` was typed (R5, R7).
    """

    sources: Mapping[str, str] = field(default_factory=dict)
    entry_acceptance: bool = True


#: The invocation a console command declared; None (the empty one) for a Python caller.
_INVOCATION: ContextVar[Invocation | None] = ContextVar("pyflightstream_invocation", default=None)


def invocation() -> Invocation:
    """Return what the running console command took from the settings files.

    Returns
    -------
    Invocation
        Set by the command line through
        :func:`pyflightstream._cli.for_this_invocation`, so it is restored
        when the command ends; a Python caller reads the empty invocation.
    """
    return _INVOCATION.get() or Invocation()


def invocation_sources() -> dict[str, str]:
    """Return the values this invocation took from a settings file, and each one's file.

    Returns
    -------
    dict of str to str
        Empty for a Python caller and for a command whose workspace has
        neither file, which leaves every record and ``plan.json`` as before.
    """
    return dict(invocation().sources)


def declare_invocation(taken: TakenDefaults, *, verbose: bool) -> None:
    """Make what a command took from the files hold for the rest of its invocation.

    Sets the console level and the grouped post-processing warnings a file or
    the new options chose, holds the sources for the records
    (:func:`invocation_sources`) and, at the ``verbose`` level, prints every
    value taken and its file on stderr before the command's work (FR-436 R8).
    Everything set here is restored when the console command ends.

    Parameters
    ----------
    taken : TakenDefaults
        What :func:`take_defaults` returned.
    verbose : bool
        Whether the command's console level is ``verbose``.
    """
    if taken.console is not None:
        set_console_level(taken.console)
    if taken.post_warnings is not None:
        set_post_warning_policy(taken.post_warnings)
    for_this_invocation(_INVOCATION, Invocation(taken.sources, not taken.refused_acceptance))
    if verbose:
        for line in defaults_lines(taken):
            print(line, file=sys.stderr)


def typed_value(args: argparse.Namespace, flag: str) -> object:
    """Return the value of ``flag`` where the command line typed it, else None (FR-436 R2).

    A value a workspace settings file supplied is not the command line's: a
    command that judges what was asked of it judges the typed value alone, and
    leaves unused a file's value it does not use.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line, as :func:`parsed` returned it.
    flag : str
        The long option, ``--fs-exe`` for instance.

    Returns
    -------
    object
        The option's value, or None where a settings file supplied it.
    """
    dest = flag.removeprefix("--").replace("-", "_")
    return None if dest in invocation().sources else getattr(args, dest)


def entry_acceptance_allowed() -> bool:
    """Return whether a build entry's own acceptance may accept its build (FR-436 R7).

    Returns
    -------
    bool
        False only when the command line typed ``--no-accept-unregistered-build``.
    """
    return invocation().entry_acceptance


def settings_supplied(root: str | Path) -> Mapping[str, Any]:
    """Return the ``[defaults]`` a workspace's files state, or nothing where they cannot be read.

    Read before the parse to relax a required option a file supplies; a file
    that cannot be read is refused by :func:`read_workspace_settings` once the
    parse has named the workspace, never here.

    Parameters
    ----------
    root : str or Path
        The folder to look in.

    Returns
    -------
    Mapping of str to object
        The merged ``[defaults]``; empty when neither file is there or one is refused.
    """
    try:
        return read_workspace_settings(root).defaults
    except InputArtifactError:
        return {}
