"""The quasi-steady rotor noise report: an exploratory comparison of routes.

Pipeline role: the post row, where recorded exports become products.
It writes a report comparing the routes that estimate a quasi-steady
rotor's noise with the unsteady reference run's acoustic signals, with no
threshold and no gate.

Laid down by the 0.32.0 preparation step so work package F writes its
code in a module of its own.

The stub's name and signature are a placeholder: the module is what the
contract fixes, and its package may rename the stub when it fills it.
Until then it refuses with
:class:`~pyflightstream._errors.ContractNotImplementedError`.
"""

from __future__ import annotations

from pathlib import Path

from pyflightstream._errors import ContractNotImplementedError


def write_qsteady_noise_report(root: str | Path, *, matrix: str | None = None) -> Path:
    """Write the exploratory quasi-steady noise report of a workspace.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    matrix : str, optional
        The matrix stem whose points are compared.

    Returns
    -------
    Path
        The file written.

    Raises
    ------
    ContractNotImplementedError
        Always, until work package F fills this body.
    """
    raise ContractNotImplementedError(
        "pyflightstream.post.qsteady_noise.write_qsteady_noise_report: "
        "not implemented yet (0.32.0 contract)"
    )
