"""The disc maps of a rotor point: sectional load by radius and azimuth.

Pipeline role: the post row, where recorded exports become products.
It writes the sectional load of a rotor over its disc, by radius and
azimuth, from the written sections of its clockings or revolution.

Laid down by the 0.32.0 preparation step so work package G5 writes its
code in a module of its own.

The stub's name and signature are a placeholder: the module is what the
contract fixes, and its package may rename the stub when it fills it.
Until then it refuses with
:class:`~pyflightstream._errors.ContractNotImplementedError`.
"""

from __future__ import annotations

from pathlib import Path

from pyflightstream._errors import ContractNotImplementedError


def write_disc_map(sections: str | Path, *, out_dir: str | Path | None = None) -> Path:
    """Write the disc map of one rotor point's sections.

    Parameters
    ----------
    sections : str or Path
        A written sections table of a rotor point.
    out_dir : str or Path, optional
        Where the map is written.

    Returns
    -------
    Path
        The file written.

    Raises
    ------
    ContractNotImplementedError
        Always, until work package G5 fills this body.
    """
    raise ContractNotImplementedError(
        "pyflightstream.post.disc_maps.write_disc_map: not implemented yet (0.32.0 contract)"
    )
