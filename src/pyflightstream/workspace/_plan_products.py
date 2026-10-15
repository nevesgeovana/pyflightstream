"""Registry for optional plan products supplied by higher layers."""

from collections.abc import Callable
from pathlib import Path

from pyflightstream.cases import SimCase

_WRITERS: list[Callable[[SimCase, Path], list[Path]]] = []


def register(writer: Callable[[SimCase, Path], list[Path]]) -> None:
    """Register an inflow-map writer once."""
    if writer not in _WRITERS:
        _WRITERS.append(writer)


def write(case: SimCase, folder: Path) -> list[Path]:
    """Write the explicitly requested plan products."""
    return [path for writer in _WRITERS for path in writer(case, folder)]
