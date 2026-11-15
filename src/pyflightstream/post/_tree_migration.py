"""The post tree's earlier layout: what moved, what retired, and the one warning that says so.

0.58.0 writes each product to the folder named by its kind (``time_history/``,
``reductions/``) and retires two reductions. A file of the earlier layout
already in the matrix's post folder is left untouched; the post names each kind
once in one warning, and ``products.json`` lists them under ``migrated``. A
reader inside the package reads the new path and falls back to the earlier one
with the same warning, for one release.

The texts are those of ``docs/upgrading.md#0580-post-tree``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._errors import PyflightstreamWarning, warn

__all__ = [
    "EARLIER_KINDS",
    "POINTER",
    "RETIRED_REDUCTIONS",
    "EarlierKind",
    "earlier_layout",
    "earlier_path",
    "note_earlier_layout",
    "once_per_post",
    "said_once",
    "say_retired",
]

#: Every warning of the migration ends with this pointer.
POINTER = "See docs/upgrading.md#0580-post-tree."


@dataclass(frozen=True)
class EarlierKind:
    """One kind of file the 0.57.0 layout wrote where 0.58.0 does not.

    Attributes
    ----------
    key : str
        The kind, as the warning names it.
    folder : str
        The folder the earlier file sat in.
    pattern : str
        The glob of the earlier file names, inside ``folder``.
    new_folder : str or None
        The folder the same name is written to now; None for a retired kind.
    text : str
        The warning text; ``<old>`` and ``<new>`` stand for the files.
    """

    key: str
    folder: str
    pattern: str
    new_folder: str | None
    text: str


#: The earlier kinds, in the order the warning names them.
EARLIER_KINDS: tuple[EarlierKind, ...] = (
    EarlierKind(
        "plots",
        "probes",
        "*_plots.csv",
        "time_history",
        "The plots history moved from probes/ to time_history/: <old> -> <new>.",
    ),
    EarlierKind(
        "phase_locked",
        "probes",
        "*_phase_locked*.csv",
        "reductions",
        "phase_locked moved from probes/ to reductions/: <old> -> <new>.",
    ),
    EarlierKind(
        "per_revolution",
        "probes",
        "*_per_revolution*.csv",
        "reductions",
        "per_revolution moved from probes/ to reductions/: <old> -> <new>.",
    ),
    EarlierKind(
        "time_average",
        "probes",
        "*_time_average.csv",
        None,
        "The time_average table is retired; the window average of every family and group is "
        "its row in polars/FAM-*-P<POL>.csv and the group files: <old>.",
    ),
    EarlierKind(
        "per_blade",
        "probes",
        "*_per_blade*.csv",
        None,
        "The per_blade table is retired; each blade is a family row of "
        "polars/FAM-ACOEF-P<POL>.csv and FAM-RCOEF-P<POL>.csv: <old>.",
    ),
    EarlierKind(
        "harmonics",
        "sections",
        "*_harmonics.csv",
        "reductions",
        "harmonics moved from sections/ to reductions/: <old> -> <new>.",
    ),
    EarlierKind(
        "disc_maps",
        "sections",
        "*_disc_*.csv",
        "reductions",
        "The disc maps moved from sections/ to reductions/: <old> -> <new>.",
    ),
)

_BY_KEY = {kind.key: kind for kind in EARLIER_KINDS}

#: The reductions 0.58.0 no longer writes: the window average of every family
#: and group is its row in the polar files.
RETIRED_REDUCTIONS: tuple[str, ...] = ("time_average", "per_blade")


def say_retired(name: str) -> None:
    """Warn, once per post, that the reduction ``name`` is retired and was asked for.

    Parameters
    ----------
    name : str
        One of :data:`RETIRED_REDUCTIONS`.
    """
    if name in RETIRED_REDUCTIONS and said_once(f"retired:{name}"):
        text = _BY_KEY[name].text.replace(": <old>.", ".").replace("<old>", "")
        warn(f"{text} {POINTER}", PyflightstreamWarning, stacklevel=3)


#: The kinds already said in this post, so a stage that asks twice says it once.
_SAID: ContextVar[set[str] | None] = ContextVar("tree_migration_said", default=None)


@contextmanager
def once_per_post() -> Iterator[None]:
    """Make :func:`said_once` remember what it said inside this block, and only here."""
    token = _SAID.set(set())
    try:
        yield
    finally:
        _SAID.reset(token)


def said_once(key: str) -> bool:
    """Return True the first time ``key`` is asked in this post, False after.

    Outside a post (no :func:`once_per_post` block) it is always True.
    """
    said = _SAID.get()
    if said is None:
        return True
    if key in said:
        return False
    said.add(key)
    return True


def earlier_layout(out: Path) -> dict[str, tuple[str, str | None]]:
    """Return every earlier-layout file in the post folder ``out``, with where it went.

    Parameters
    ----------
    out : Path
        The matrix's post folder.

    Returns
    -------
    dict
        Earlier relative path to ``(kind, new relative path or None)``, sorted by path.
        The new path is None for a retired kind.

    Examples
    --------
    >>> with __import__("tempfile").TemporaryDirectory() as folder:
    ...     (Path(folder) / "probes").mkdir()
    ...     _ = (Path(folder) / "probes" / "AL+000_plots.csv").write_text("POL")
    ...     earlier_layout(Path(folder))
    {'probes/AL+000_plots.csv': ('plots', 'time_history/AL+000_plots.csv')}
    """
    found: dict[str, tuple[str, str | None]] = {}
    for kind in EARLIER_KINDS:
        folder = out / kind.folder
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob(kind.pattern)):
            if not path.is_file():
                continue
            new = None if kind.new_folder is None else f"{kind.new_folder}/{path.name}"
            found[f"{kind.folder}/{path.name}"] = (kind.key, new)
    return found


def _sentence(kind: EarlierKind, old: str, new: str | None) -> str:
    text = kind.text.replace("<old>", old)
    return text.replace("<new>", "" if new is None else new)


def note_earlier_layout(out: Path) -> dict[str, str | None]:
    """Warn once per kind of the earlier-layout files in ``out``; return them for ``migrated``.

    One :class:`PyflightstreamWarning` names every kind found, each once, with
    the first file of the kind (and how many more), and ends with
    :data:`POINTER`. A kind already said in this post is not said again.

    Parameters
    ----------
    out : Path
        The matrix's post folder.

    Returns
    -------
    dict
        Earlier relative path to the new relative path, None for a retired kind.

    Examples
    --------
    >>> note_earlier_layout(__import__("pathlib").Path("no-such-folder"))
    {}
    """
    found = earlier_layout(out)
    if not found:
        return {}
    lines: list[str] = []
    for kind in EARLIER_KINDS:
        own = [(old, new) for old, (key, new) in found.items() if key == kind.key]
        if not own or not said_once(kind.key):
            continue
        old, new = own[0]
        text = _sentence(kind, old, new)
        if len(own) > 1:
            text = f"{text.removesuffix('.')} (and {len(own) - 1} more of the kind)."
        lines.append(text)
    if lines:
        warn(" ".join(lines) + f" {POINTER}", PyflightstreamWarning, stacklevel=2)
    return {old: new for old, (_key, new) in found.items()}


def earlier_path(out: Path, relative: str, *, kind: str) -> Path:
    """Return where a reader finds ``relative``: the new path, else the earlier one.

    The earlier file is returned after one warning per post and kind.

    Parameters
    ----------
    out : Path
        The matrix's post folder.
    relative : str
        The new relative path of the product (``reductions/AL+000_harmonics.csv``).
    kind : str
        The kind of :data:`EARLIER_KINDS`.

    Returns
    -------
    Path
        ``out / relative`` when it exists or no earlier file does; else the
        earlier file, after one warning per post and kind.

    Examples
    --------
    >>> earlier_path(Path("x"), "reductions/a_harmonics.csv", kind="harmonics").as_posix()
    'x/reductions/a_harmonics.csv'
    """
    chosen = out / relative
    if chosen.is_file():
        return chosen
    spec = _BY_KEY[kind]
    old = f"{spec.folder}/{Path(relative).name}"
    if (out / old).is_file():
        if said_once(f"read:{kind}"):
            warn(f"{_sentence(spec, old, relative)} {POINTER}", PyflightstreamWarning, stacklevel=2)
        return out / old
    return chosen
