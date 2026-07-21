"""Fluid-structure interaction coupling for rotating blades.

Pipeline role: this subpackage implements the external structural
executable of the FlightStream Aeroelastic Toolbox loop (M6, DLV-007;
FR-23a). Per coupling call FlightStream exports sectional loads on
user-defined surface sections; the executable reads them together with
its configuration and persisted state, solves one beam per blade,
converts the solution to nodal translations, and writes the
displacement file back for the solver to deform the mesh. All exchange
happens in the rotating blade frames; this package never handles
azimuth or global-frame transforms (FSI-R02).

The structural backend is PyNite (PyPI distribution ``PyNiteFEA``,
import name ``Pynite``), pulled in only by the optional ``[fsi]``
extra; importing :mod:`pyflightstream.fsi` itself stays dependency
free so the core package works without the extra installed.

The evidence status of the structural model is recorded in DLV-007
Section 2: formulas live in small isolated functions with their source
cited in the docstring, so a later primary-source correction stays a
localized change.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable

from pyflightstream.fsi.config import FsiConfig, config_hash, load_config

__all__ = ["FsiConfig", "StructuralSolver", "config_hash", "load_config"]


@runtime_checkable
class StructuralSolver(Protocol):
    """Contract of one structural coupling call (HND-008 loop).

    FlightStream calls the executable between coupling iterations; the
    executable is stateless per call (FSI-R01) and all state persists
    in files inside the run folder. An implementation reads the
    exported sectional loads, ``config.json`` and ``state.json`` from
    ``run_dir``, solves the structure, and writes ``FSIDisp.txt`` plus
    the updated ``state.json`` atomically (FSI-R13).
    """

    def step(self, run_dir: Path) -> None:
        """Execute one coupling call inside ``run_dir``.

        Parameters
        ----------
        run_dir : Path
            Run folder managed by :mod:`pyflightstream.files` (FR-28)
            containing the FlightStream loads export, ``config.json``
            and ``state.json``. The written ``FSIDisp.txt`` carries one
            translation vector (dx, dy, dz) per structural node, in
            meters, in the rotating blade frame, in exactly the node
            order imported into FlightStream (FSI-R14).
        """
        ...
