"""The build registry of a workspace: which executable a FlightStream build id names.

``inputs/executables.toml`` maps a build id to its executable path; an entry
is a bare path string, or a table carrying that path and, optionally, the
FlightStream version the build's scripts are emitted under, checked against
the version registry when it is read (PFS-2009.05). This machine's overlay,
``inputs/executables.local.toml`` (PFS-2031.15), supplies the real path of a
build a versioned workspace carries with a placeholder. An explicit override
path bypasses the registry, and that override is the only way to run an
unregistered build (the MANUAL mode of the run matrix).

Every public name is re-exported, unchanged, by :mod:`pyflightstream.workspace.inputs`,
its path of 0.32.0 (AD-11, since 0.33.0).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyflightstream._errors import InputArtifactError
from pyflightstream.versions import AmbiguousVersionAliasError, UnknownVersionError, resolve
from pyflightstream.workspace.sidecars import _load_toml

__all__ = [
    "EXECUTABLES_FILE",
    "EXECUTABLE_ENTRY_KEYS",
    "LOCAL_EXECUTABLES_FILE",
    "RegisteredBuild",
    "resolve_build",
    "resolve_executable",
]


#: The build registry, at the root of a workspace's ``inputs`` folder.
EXECUTABLES_FILE = "executables.toml"
#: This machine's overlay of the build registry (PFS-2031.15). A workspace
#: kept in version control carries placeholder paths in the registry,
#: because where a solver is installed is machine configuration; the
#: overlay beside it, gitignored, supplies the real path of a build id. A
#: bare path keeps the committed entry's declared version, a table replaces
#: the entry, and a build id the overlay is silent on reads as committed.
LOCAL_EXECUTABLES_FILE = "executables.local.toml"

#: Every key a TABLE-valued entry of the build registry carries, and the
#: only ones read. A key outside this tuple is REFUSED naming itself
#: rather than ignored: a silently dropped ``verison`` leaves a registry
#: that looks correct and a run emitted under the campaign default, and
#: the two look identical from the manifest (PFS-2009.05).
EXECUTABLE_ENTRY_KEYS = ("path", "version")


@dataclass(frozen=True)
class RegisteredBuild:
    """One entry of the workspace build registry, as the registry states it.

    Attributes
    ----------
    fs_exe : Path
        The executable this build id names. Existence is checked by the
        executor at construction, so a campaign can be authored away
        from the licensed machine.
    fs_version : str or None
        The FlightStream version the registry DECLARES this build's
        scripts are emitted under, canonical identifier (``"26.123"``)
        or a vendor release name that resolves to exactly one registered
        build. None means the registry declares none, and the caller's
        campaign default answers for it.

        It is a DECLARATION and never an inference. Nothing here reads a
        version out of the executable path or out of the build id, which
        is the rule :class:`pyflightstream.run.SolverBuild` exists to
        state: a build id is a key of this registry, and which command
        database a build carries is a fact only its owner knows.
    """

    fs_exe: Path
    fs_version: str | None


def _refuse_declared_version(version: str, build_id: str, registry_path: Path) -> None:
    """Refuse a declared version the version registry does not carry.

    The check happens where the version is READ rather than where a
    script is emitted under it, so a typed identifier is refused with the
    file and the build id in the message instead of surfacing much later
    as an unknown-version error from the script layer.

    Parameters
    ----------
    version : str
        The version string the registry entry declares.
    build_id : str
        The build id whose entry declares it, for the message.
    registry_path : Path
        The registry file, for the message.

    Raises
    ------
    InputArtifactError
        The identifier names no registered version, or names a vendor
        release name that more than one registered build carries. The
        chained message lists the registered versions or the candidates.
    """
    try:
        resolve(version)
    except (UnknownVersionError, AmbiguousVersionAliasError) as error:
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {registry_path} declares "
            f"version {version!r}, which this package cannot resolve to one registered "
            "FlightStream version. The version decides which command database the "
            "build's scripts are emitted against, so it is never guessed from the "
            f"build id or the executable path. {error}"
        ) from error


def resolve_build(
    inputs_dir: Path, build_id: str, override: str | Path | None = None
) -> RegisteredBuild:
    """Read the registry entry of one build id: its executable and its version.

    Two explicit modes, translated from the run matrix's MANUAL pattern:

    - Registry mode (default): the build id must exist in
      ``inputs/executables.toml``, a top-level TOML table mapping build
      ids to entries.
    - Override mode: an explicit ``override`` path wins over the
      registry and is the only way to run an unregistered build; it is
      never guessed from the environment. An override declares NO
      version, because it is a bare path with no registry entry behind
      it to carry one.

    TWO ENTRY SHAPES, and the difference is what a build may say about
    itself:

    - ``"26.120" = "C:/fs26120/FlightStream.exe"`` is the shape this
      registry has always had and means exactly what it meant: the build
      id names an executable and declares no version, so a campaign that
      sends a row to it emits that row's script under the campaign
      default version.
    - ``"26.123" = { path = "C:/fs26123/FlightStream.exe", version =
      "26.123" }`` declares the version as well, which is what lets ONE
      run matrix send its rows to two solver builds and record each row
      against the version its own build emits under (PFS-2009.05).

    The table is where the declaration lives because it is already the
    file in which the user says what a build id MEANS on this machine.
    Deriving the version from the build id instead would be the
    inference :class:`pyflightstream.run.SolverBuild` refuses, and the
    two are not the same thing: a registry key is a name the campaign
    user chose, and nothing stops it naming an installation whose
    command database is anything at all.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    build_id : str
        Build identifier key of the registry, for example ``"26.120"``.
    override : str or Path, optional
        Explicit executable path bypassing the registry.

    Returns
    -------
    RegisteredBuild
        The executable, and the declared version or None.

    Raises
    ------
    InputArtifactError
        Registry file missing; build id not registered (the message
        lists the registered build ids and the override mode); an entry
        that is neither a path string nor a table; a table with no
        ``path``; a table carrying a key outside
        :data:`EXECUTABLE_ENTRY_KEYS`; or a declared version the version
        registry does not carry.

    Examples
    --------
    >>> from pyflightstream.workspace.inputs import resolve_build
    >>> build = resolve_build(workspace.inputs_dir, "26.123")  # doctest: +SKIP
    >>> build.fs_version                                       # doctest: +SKIP
    '26.123'
    """
    if override is not None:
        return RegisteredBuild(fs_exe=Path(override), fs_version=None)
    registry_path = Path(inputs_dir) / EXECUTABLES_FILE
    if not registry_path.is_file():
        raise InputArtifactError(
            f"no executable registry at {registry_path}; register builds as "
            '"<build_id>" = "<path>" entries in that TOML file (this machine\'s paths may '
            f"go in {LOCAL_EXECUTABLES_FILE} beside it, read over the registry, but the "
            "registry itself must exist), or pass the explicit override path. The "
            "executable is always explicit input, never guessed."
        )
    table = _load_toml(registry_path, "executables")
    overlay_path = registry_path.with_name(LOCAL_EXECUTABLES_FILE)
    #: Which file each build id's entry came from, so a refusal about an
    #: entry names the file the user has to edit (a review of 2026-09-08
    #: found the overlay's own mistakes reported against the registry).
    source_of: dict[str, Path] = dict.fromkeys(table, registry_path)
    if overlay_path.is_file():
        for key, local in _load_toml(overlay_path, "executables").items():
            committed = table.get(key)
            if committed is None:
                # The committed registry is the declaration of which builds
                # this workspace knows; the overlay supplies paths for them
                # and may not add one, or a row would run on one machine
                # and be refused as unregistered on another from the same
                # tree, with the file that explains it gitignored.
                raise InputArtifactError(
                    f"{overlay_path} supplies build {key!r}, which {registry_path.name} "
                    f"does not register (registered: "
                    f"{', '.join(sorted(table)) if table else 'none yet'}). The overlay "
                    "gives this machine's path for a build the committed registry "
                    "declares; declare the build there first, with a placeholder path."
                )
            if isinstance(local, str) and isinstance(committed, dict):
                table[key] = {**committed, "path": local}
            else:
                table[key] = local
            source_of[key] = overlay_path
    entry = table.get(build_id)
    entry_path = source_of.get(build_id, registry_path)
    if entry is None:
        # BOTH shapes count as registered. Listing only the string entries,
        # which is what this did while a string was the only shape, would
        # tell a user with a table-valued registry that nothing is
        # registered at all.
        registered = sorted(key for key, value in table.items() if isinstance(value, (str, dict)))
        listing = ", ".join(registered) if registered else "none yet"
        raise InputArtifactError(
            f"build id {build_id!r} is not in the executable registry "
            f"{registry_path} (registered: {listing}); add it there, or pass the "
            "explicit override path to run an unregistered build."
        )
    if isinstance(entry, str):
        return RegisteredBuild(fs_exe=Path(entry), fs_version=None)
    if not isinstance(entry, dict):
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {entry_path} must be "
            f"a path string or a table, got {type(entry).__name__}; write "
            f'"{build_id}" = "C:/path/to/FlightStream.exe" for a build whose scripts '
            f'are emitted under the campaign default version, or "{build_id}" = '
            '{ path = "C:/path/to/FlightStream.exe", version = "26.123" } to declare '
            "the version this build's scripts are emitted under."
        )
    unknown = sorted(key for key in entry if key not in EXECUTABLE_ENTRY_KEYS)
    if unknown:
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {entry_path} carries "
            f"key(s) {', '.join(unknown)}, and a build entry reads "
            f"{', '.join(EXECUTABLE_ENTRY_KEYS)} and nothing else. The key is refused "
            "rather than ignored because an ignored one is invisible: a misspelled "
            "version key leaves the registry looking correct and every row of this "
            "build emitted under the campaign default. Correct the spelling, or "
            "remove the key."
        )
    path_value = entry.get("path")
    if not isinstance(path_value, str):
        stated = "declares no path" if path_value is None else f"declares path {path_value!r}"
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {entry_path} {stated}, "
            "and a table entry must carry path as a string; write "
            f'"{build_id}" = {{ path = "C:/path/to/FlightStream.exe" }}. The '
            "executable is always explicit input, never guessed."
        )
    version = entry.get("version")
    if version is None:
        return RegisteredBuild(fs_exe=Path(path_value), fs_version=None)
    if not isinstance(version, str):
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {entry_path} declares "
            f"version {version!r} of type {type(version).__name__}, and a FlightStream "
            'version is written as a string: version = "26.123". A bare 26.123 is a '
            "TOML float and loses the three-digit form the canonical identifier is."
        )
    _refuse_declared_version(version, build_id, registry_path)
    return RegisteredBuild(fs_exe=Path(path_value), fs_version=version)


def resolve_executable(inputs_dir: Path, build_id: str, override: str | Path | None = None) -> Path:
    """Resolve the FlightStream executable of one build id.

    The path half of :func:`resolve_build`, which is where the registry
    is read and where both entry shapes are described. This is the call
    for a caller who wants the executable and nothing else; a caller who
    also needs the version the build declares calls
    :func:`resolve_build` instead, because the two facts come from one
    entry and reading it twice is how they would drift apart.

    Existence of the executable is checked by the executor at
    construction (so campaigns can be authored away from the licensed
    machine), not here.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    build_id : str
        Build identifier key of the registry, for example ``"26.120"``.
    override : str or Path, optional
        Explicit executable path bypassing the registry.

    Returns
    -------
    Path
        The executable path.

    Raises
    ------
    InputArtifactError
        Every refusal of :func:`resolve_build`: registry file missing,
        build id not registered, or a malformed entry.
    """
    return resolve_build(inputs_dir, build_id, override=override).fs_exe
