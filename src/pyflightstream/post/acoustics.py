"""The acoustic signals product of a point: reading the solver's acoustic export.

Pipeline role: the post row. Work package E1 fills it: it reads the file a
point's ``EXPORT_ACOUSTIC_SIGNALS`` wrote (named by
:data:`pyflightstream.cases.acoustics.ACOUSTIC_SIGNALS_SUFFIX`) into one
:class:`~pyflightstream.cases.acoustics.AcousticSignal` per observer, the
contract :mod:`pyflightstream.cases.acoustics` states together with what the
command database says the export is and what is unmeasured about it. Both
names are re-exported here so a reader of the product needs one import.

Laid down by the 0.32.0 preparation step; :func:`read_acoustic_signals`
refuses with :class:`~pyflightstream._errors.ContractNotImplementedError`
until E1 fills it.
"""

from __future__ import annotations

from pathlib import Path

from pyflightstream._errors import ContractNotImplementedError
from pyflightstream.cases.acoustics import ACOUSTIC_SIGNALS_SUFFIX, AcousticSignal

__all__ = ["ACOUSTIC_SIGNALS_SUFFIX", "AcousticSignal", "read_acoustic_signals"]


def read_acoustic_signals(path: str | Path) -> tuple[AcousticSignal, ...]:
    """Read a point's acoustic export into one signal per observer.

    Parameters
    ----------
    path : str or Path
        The exported file, ``<point>`` followed by
        :data:`~pyflightstream.cases.acoustics.ACOUSTIC_SIGNALS_SUFFIX`.

    Returns
    -------
    tuple of AcousticSignal
        One per observer, in the order the file holds them.

    Raises
    ------
    ContractNotImplementedError
        Always, until work package E1 fills this body.
    """
    raise ContractNotImplementedError(
        "pyflightstream.post.acoustics.read_acoustic_signals: not implemented yet (0.32.0 contract)"
    )
