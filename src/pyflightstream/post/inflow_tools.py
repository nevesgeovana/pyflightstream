"""The quasi-steady inflow tools: fluctuation per probe, frame change, harmonics.

Pipeline role: the post row, where recorded exports become products.
It holds the inflow tools beyond the field operations of
:mod:`pyflightstream.workspace.fields`: the fluctuation of the field at
each probe over time, the move of a table from the isolated to the
installed frame, and the harmonics of an inflow beyond the plan's
``inflow_fft`` record.

Laid down by the 0.32.0 preparation step so work package D writes its
code in a module of its own.

The stub's name and signature are a placeholder: the module is what the
contract fixes, and its package may rename the stub when it fills it.
Until then it refuses with
:class:`~pyflightstream._errors.ContractNotImplementedError`.
"""

from __future__ import annotations

from pathlib import Path

from pyflightstream._errors import ContractNotImplementedError


def to_installed_frame(table: str | Path, *, out: str | Path | None = None) -> Path:
    """Write a table stated in the isolated frame in the installed frame.

    Parameters
    ----------
    table : str or Path
        A table stated in the isolated frame.
    out : str or Path, optional
        Where the converted table is written.

    Returns
    -------
    Path
        The file written.

    Raises
    ------
    ContractNotImplementedError
        Always, until work package D fills this body.
    """
    raise ContractNotImplementedError(
        "pyflightstream.post.inflow_tools.to_installed_frame: not implemented yet (0.32.0 contract)"
    )
