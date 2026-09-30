"""The acoustic signals of a point: the contract between their emission and their reading.

Pipeline role: the cases row, because both sides of the contract name it: the
setup and collect of an unsteady point emit the solver's acoustic toolbox and
declare its export (work package E2, here), and the post stage reads that
export back (work package E1, :mod:`pyflightstream.post.acoustics`), and the
post row may import the cases row and never the reverse. Laid down by the
0.32.0 preparation step so the two packages code against one fixed form:

* :class:`AcousticSignal`, one observer's signal as the post stage hands it on;
* :data:`ACOUSTIC_SIGNALS_SUFFIX`, the end of the name of the file a point's
  acoustic export is written to.

WHAT THE COMMAND DATABASE SAYS THE EXPORT IS (``commands/acoustics.yaml``,
from the scripting reference): ``ACOUSTIC_SOURCES ENABLE`` is a setup command
that must precede solver initialization; each observer is created by name at
``x``, ``y``, ``z`` in simulation length units of the reference coordinate
system (``CREATE_NEW_ACOUSTIC_OBSERVER``, or ``ACOUSTIC_OBSERVERS_IMPORT``
from a file); ``SET_ACOUSTIC_OBSERVER_TIME`` sets the observer's own time
window in seconds and its number of steps; ``COMPUTE_ACOUSTIC_SIGNALS``
computes the signal at every observer; ``EXPORT_ACOUSTIC_SIGNALS`` writes the
signals of EVERY observer to ONE file, the path on its next line, with no
per-observer export.

WHAT IS UNMEASURED, and E1 and E2 must measure before relying on it: no
command of the toolbox has been run on any registered build (the 26.124 rows
are "not run"); the layout of the exported file, its columns, its delimiter,
how an observer's block is marked and the unit of its pressure column are not
in the database; the length unit of the exported coordinates is not known to
be the observer's. The metre and pascal of :class:`AcousticSignal` are the
contract's units, so a reader converts to them; they are not a claim about
the file.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The end of the name of a point's acoustic export, written beside its
#: other exports as ``<point><suffix>``. The minimal form of the 0.32.0
#: contract, following the ``_<kind>.txt`` form of the point's other solver
#: exports; E2 confirms it against the first run that writes one.
ACOUSTIC_SIGNALS_SUFFIX = "_acoustic_signals.txt"


@dataclass(frozen=True)
class AcousticSignal:
    """One observer's acoustic pressure signal.

    Parameters
    ----------
    observer : str
        The observer's name, as its creation named it.
    x_m, y_m, z_m : float
        The observer's position in the reference coordinate system, in metres.
    time_s : tuple of float
        The observer's time samples, in seconds.
    pressure_pa : tuple of float
        The acoustic pressure at each time sample, in pascals.
    """

    observer: str
    x_m: float
    y_m: float
    z_m: float
    time_s: tuple[float, ...]
    pressure_pa: tuple[float, ...]
