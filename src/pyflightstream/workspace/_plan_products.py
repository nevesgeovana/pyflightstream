"""Registry for optional plan products supplied by higher layers."""

from collections.abc import Callable
from pathlib import Path

from pyflightstream.cases import SimCase

_WRITERS: list[Callable[[SimCase, Path], list[Path]]] = []


def register_plan_product_writer(writer: Callable[[SimCase, Path], list[Path]]) -> None:
    """Register an optional plan-product writer once.

    Parameters
    ----------
    writer : callable
        Receives the resolved case and destination, and returns written paths.

    Returns
    -------
    None
        The callback is retained for subsequent plan requests.
    """
    if writer not in _WRITERS:
        _WRITERS.append(writer)


def write_plan_products(case: SimCase, folder: Path) -> list[Path]:
    """Write the explicitly requested plan products.

    Parameters
    ----------
    case : SimCase
        Resolved workspace point.
    folder : Path
        Destination for products of this point.

    Returns
    -------
    list[Path]
        Paths written by the registered callbacks.
    """
    return [path for writer in _WRITERS for path in writer(case, folder)]
