"""Read query evidence in ordinary, running-batch and compacted simulation homes.

Pipeline role: workspace-only file access for the point query readers. ZIP
members are read in place; no query expands, locks or repairs its evidence.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any
from zipfile import ZipFile

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
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


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


def _evidence(ledger: Ledger, path: str | None, *, lines: int = 5) -> dict[str, Any]:
    if path is None:
        return {"path": None, "state": "absent", "last_lines": []}
    return {
        "path": path,
        "state": "present",
        "last_lines": _text(ledger, path).splitlines()[-lines:],
    }


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
    name = Path(value).name
    return name[: -len(".fs")] if name.lower().endswith(".fs") else name
