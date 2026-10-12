"""The workspace settings files, ``pyfs.toml`` and this machine's ``pyfs.local.toml`` (FR-436).

A user who runs the same commands day after day writes once, in the workspace,
the defaults of the options otherwise typed on every command: the
version, the HPC profile, the cost file, the acceptance of the installed build,
how much the console says. This module is the one reader of those two files,
and the one place that decides which of their values a command takes.

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
package default (:func:`take_defaults`). The command line itself is parsed
above this module, by each command family (R11): the family states what was
typed and which settable options were left open, and gives its options the
values this module returns. A workspace without either file therefore takes
nothing from here and parses exactly as before.

PROVENANCE (R7, R8). The values a command took from a file, and the file each
came from, are held for the length of the invocation
(:func:`invocation_sources`), so ``plan.json`` and every run record can name
them. A value typed, or left at the package default, is recorded as before.

The reading lives in the workspace row because the files are the workspace's;
the command lines of both programs import it, downward.
"""

from __future__ import annotations

import sys
import tomllib
from collections.abc import Collection, Iterable, Mapping
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
    "Invocation",
    "TakenDefaults",
    "WorkspaceSettings",
    "console_only",
    "declare_invocation",
    "defaults_lines",
    "entry_acceptance_allowed",
    "invocation",
    "invocation_sources",
    "read_workspace_settings",
    "settings_supplied",
    "take_defaults",
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
    except UnicodeDecodeError as error:
        # TOML is UTF-8, and tomllib decodes before it parses, so a file saved
        # in a legacy code page never reaches TOMLDecodeError.
        raise InputArtifactError(
            f"{path} is not UTF-8 ({error}); save it as UTF-8, which TOML requires. "
            "Nothing ran: the workspace settings are read before any work."
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
    if not isinstance(value, int) or isinstance(value, bool) or value != _SCHEMA_VERSION:
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


# --- the precedence: what the command line did not state, the files answer ---------


@dataclass(frozen=True)
class TakenDefaults:
    """What one command took from the settings files.

    Attributes
    ----------
    sources : Mapping of str to str
        The file each value taken came from, ``[log]`` keys as ``log.<key>``.
    values : Mapping of str to object
        The values taken, keyed as ``sources``, as the file states them.
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
    settings: WorkspaceSettings,
    typed: Mapping[str, object],
    open_keys: Iterable[str],
    *,
    negated: Collection[str] = (),
    console: bool = False,
    post_warnings: bool = False,
) -> TakenDefaults:
    """Decide what a command takes from the files, the command line winning (FR-436).

    The precedence of the requirement: an option typed wins over
    ``pyfs.local.toml``, which wins over ``pyfs.toml`` (already overlaid in
    ``settings``), which wins over the package default. The command line
    itself is parsed by each command family, which states here what it typed
    and which settable options it left open, and gives its options the
    values returned.

    Parameters
    ----------
    settings : WorkspaceSettings
        The workspace's settings files, read.
    typed : Mapping of str to object
        The value of every settable or console option the command line
        stated, keyed as the files key it (``log_level``, ``verbose`` and
        ``pproc_warnings`` for the console).
    open_keys : iterable of str
        The ``[defaults]`` keys the command takes and the command line left
        unstated, in the order the command lists them.
    negated : collection of str, optional
        The open keys whose negation the command line stated through a flag
        of its own (``--no-ignore-missing-families``): a file never answers
        for them.
    console : bool, optional
        Whether the command takes a console level (``--log-level``).
    post_warnings : bool, optional
        Whether the command takes ``--pproc-warnings``.

    Returns
    -------
    TakenDefaults
        The values a file answers for and the file each came from, and the
        console choices the command line or a file made; an open key no
        file states keeps the package default.
    """
    sources: dict[str, str] = {}
    values: dict[str, object] = {}
    for key in open_keys:
        if key in settings.defaults and key not in negated:
            sources[key], values[key] = settings.sources[key], settings.defaults[key]
    level: str | None = None
    if console:
        if "log_level" in typed:
            level = str(typed["log_level"])
        elif typed.get("verbose") is not True and "console" in settings.log:
            level = str(settings.log["console"])
            sources["log.console"], values["log.console"] = settings.sources["log.console"], level
    post: bool | None = None
    if post_warnings:
        if "pproc_warnings" in typed:
            post = None if typed["pproc_warnings"] else False
        elif "pproc_warnings" in settings.log:
            post = bool(settings.log["pproc_warnings"])
            key = "log.pproc_warnings"
            sources[key], values[key] = settings.sources[key], post
    refused = typed.get("accept_unregistered_build") is False
    return TakenDefaults(sources, values, level, post, refused)


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
