"""Read query evidence in ordinary, running-batch and compacted simulation homes.

Pipeline role: workspace-only file access for the point query readers. ZIP
members are read in place; no query expands, locks or repairs its evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import IO, TYPE_CHECKING, Any
from zipfile import ZipFile

from pyflightstream._digest import file_sha256

if TYPE_CHECKING:
    from pyflightstream.workspace.ledger import Ledger


def _json(path: Path, default: Any = None) -> Any:
    """Read one JSON document, or give the default when the file is absent.

    Parameters
    ----------
    path : pathlib.Path
        The file to read.
    default : Any, optional
        What to return when ``path`` is not a file.

    Returns
    -------
    Any
        The parsed document, or ``default``.
    """
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        # A ValueError still, as the decoder raised; now naming the damaged file.
        raise ValueError(f"{path}: not readable JSON ({error})") from error


def _files(ledger: Ledger, sim: str) -> dict[str, str]:
    """Map simulation-relative names to physical paths, preferring the home copy."""
    found: dict[str, str] = {}
    for folder in ledger.sim_folders(sim):
        path = ledger.root / folder
        if path.suffix == ".zip":
            with ZipFile(path) as archive:
                for name in archive.namelist():
                    if not name.endswith("/"):
                        found.setdefault(name, f"{folder}!/{name}")
        else:
            for base, dirs, names in os.walk(path, followlinks=False):
                dirs[:] = [d for d in dirs if not _linked(Path(base) / d)]
                for name in names:
                    file = Path(base) / name
                    if not _linked(file):
                        found.setdefault(
                            file.relative_to(path).as_posix(),
                            file.relative_to(ledger.root).as_posix(),
                        )
    return found


def _linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _text(ledger: Ledger, path: str) -> str:
    archive, separator, member = path.partition("!/")
    if separator:
        with ZipFile(ledger.root / archive) as source:
            return source.read(member).decode("utf-8", errors="replace")
    return (ledger.root / path).read_text(encoding="utf-8", errors="replace")


#: How much of a file's end ``show`` reads for its last lines.
_TAIL_BYTES = 64 * 1024


@contextmanager
def _stream(ledger: Ledger, path: str) -> Iterator[IO[bytes]]:
    """Open a file, or a ZIP member read in place, as a binary stream."""
    archive, separator, member = path.partition("!/")
    if separator:
        with ZipFile(ledger.root / archive) as source, source.open(member) as stream:
            yield stream
    else:
        with (ledger.root / path).open("rb") as stream:
            yield stream


def _tail(ledger: Ledger, path: str) -> tuple[bytes, int]:
    """Return the last bytes of a file and its size, never holding the whole file."""
    with _stream(ledger, path) as stream:
        if "!/" not in path and stream.seekable():
            size = stream.seek(0, os.SEEK_END)
            stream.seek(max(0, size - _TAIL_BYTES))
            return stream.read(), size
        tail, size = b"", 0
        for chunk in iter(lambda: stream.read(_TAIL_BYTES), b""):
            size += len(chunk)
            tail = (tail + chunk)[-_TAIL_BYTES:]
        return tail, size


def _tail_text(tail: bytes, size: int) -> str | None:
    """Decode a text tail, or identify binary bytes without replacement characters."""
    if b"\x00" in tail:
        return None
    start = 0
    if len(tail) < size:
        # A seek can start inside one UTF-8 character; at most three continuation bytes.
        while start < min(3, len(tail)) and 0x80 <= tail[start] <= 0xBF:
            start += 1
    try:
        return tail[start:].decode("utf-8")
    except UnicodeDecodeError:
        return None


def _evidence(ledger: Ledger, path: str | None, *, lines: int = 5) -> dict[str, Any]:
    """Return one evidence file's last lines, or a binary file's size and sha256.

    PFS-2101.004: the whole file was read and decoded to print five lines, so a
    surface export was loaded in full and a binary one printed replacement
    characters. The end is read now; NUL bytes or bytes that are not UTF-8
    identify binary evidence, shown by size and digest. A ZIP member's digest
    is computed in chunks from its stream.
    """
    if path is None:
        return {"path": None, "state": "absent", "last_lines": []}
    tail, size = _tail(ledger, path)
    decoded = _tail_text(tail, size)
    if decoded is None:
        if "!/" in path:
            with _stream(ledger, path) as stream:
                hashed = hashlib.sha256()
                for chunk in iter(lambda: stream.read(_TAIL_BYTES), b""):
                    hashed.update(chunk)
                digest = hashed.hexdigest()
        else:
            digest = file_sha256(ledger.root / path)
        return {
            "path": path,
            "state": "present",
            "binary": True,
            "bytes": size,
            "sha256": digest,
            "last_lines": [],
        }
    found = decoded.splitlines()
    if len(tail) < size:
        if len(found) == 1:
            # F-1219: one line longer than the window. Dropping it as a partial first
            # line left a present file that showed no lines and no sign of why. Its
            # end is shown and the answer says it begins earlier.
            return {"path": path, "state": "present", "last_lines": found, "truncated": True}
        found = found[1:]  # the first line read may begin inside a line
    return {"path": path, "state": "present", "last_lines": found[-lines:]}


def _point_files(record: dict[str, Any], files: dict[str, str]) -> dict[str, str]:
    name = record.get("point_name") or record["run_id"].rsplit("/", 1)[-1]
    prefix = f"datapoints/DP-{name}/"
    outputs = set(record.get("outputs", []))
    outputs.add(record.get("log_file_used"))
    return {
        key: value
        for key, value in files.items()
        if (key.startswith(prefix) or key in outputs) and "/archive/" not in key
    }


def _indexes(ledger: Ledger) -> list[tuple[Path, dict[str, Any]]]:
    return [(path, _json(path, {})) for path in sorted(ledger.root.glob("post/*/products.json"))]


def _relative_name(value: str) -> str:
    """Normalize a recorded relative path without following it."""
    return PurePosixPath(value.replace("\\", "/")).as_posix()


def _category(product: str, message: str) -> str:
    """Return the family of one post warning, read from its product and message words.

    Parameters
    ----------
    product : str
        The product the warning names.
    message : str
        The warning's text.

    Returns
    -------
    str
        The family word (``section-layout``, ``reference-frame``, ``convergence`` and so on).

    Examples
    --------
    >>> _category("loads", "residual did not converge")
    'convergence'
    """
    text = f"{product} {message}".lower()
    groups = (
        ("section-layout", ("section", "distribution", "layout", "block")),
        ("reference-frame", ("frame", "reference", "axis", "rotation")),
        ("convergence", ("converg", "residual", "iteration")),
        ("translation", ("tecplot", "vtk", "translation", "variable")),
        ("missing-data", ("missing", "absent", "no data", "not found", "empty")),
        ("configuration", ("configuration", "pproc", "setting", "option")),
    )
    return next(
        (category for category, words in groups if any(w in text for w in words)), "postprocessing"
    )


def _groups(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        product, message = str(record.get("product") or "stage"), str(record.get("message") or "")
        category = str(record.get("category") or _category(product, message))
        family = str(record.get("family") or product.replace("\\", "/").split("/")[0])
        shape = re.sub(r"\b\d+(?:\.\d+)?\b", "#", message)
        shape = re.sub(r"(?:[\w.+-]+/)+[\w.+-]+", "<path>", shape)
        key = category, family, shape
        group = grouped.setdefault(
            key,
            {
                "category": category,
                "family": family,
                "shape": shape,
                "count": 0,
                "example": dict(record),
            },
        )
        group["count"] += 1
    return [grouped[key] for key in sorted(grouped)]


def matrix_stem(value: str) -> str:
    """Return the stem a matrix argument names: ``l1_g6``, ``l1_g6.fs`` or a path to it.

    Parameters
    ----------
    value : str
        A matrix stem, file name or path.

    Returns
    -------
    str
        The file name without its ``.fs`` suffix.

    Examples
    --------
    >>> matrix_stem("inputs/matrices/l1_g6.fs")
    'l1_g6'
    """
    # F-1512: a Windows-form path names its file by the last of either separator, on any
    # platform; a POSIX Path keeps the backslashes in the name.
    name = PureWindowsPath(value).name
    return name[: -len(".fs")] if name.lower().endswith(".fs") else name
