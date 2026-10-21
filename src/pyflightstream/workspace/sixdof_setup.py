"""Resolve a row's ``SIXDOF: d<id>`` key to its 6DOF input (FR-461).

The key names ``inputs/sixdof/d<id>.toml``, the way ``FSI: f<id>`` names
``inputs/fsi/f<id>.toml``: the plan reads it, validates it
(:class:`~pyflightstream.cases.sixdof.SixDofSpec`), resolves each custom force's
file under the same folder and hashes the input and those files, so the run
record keeps what moved the body.
"""

from __future__ import annotations

import hashlib
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases.sixdof import SIXDOF_VARIABLE, SixDofCustomForce, SixDofSpec

__all__ = [
    "ResolvedSixDof",
    "SixDofSetupError",
    "resolve_row_sixdof",
]

#: The run type for a free body (FR-1087).
_SIXDOF_WORKFLOW = "unsteady"


class SixDofSetupError(PyflightstreamError, ValueError):
    """A row's 6DOF input cannot describe a body free to move here."""


@dataclass(frozen=True)
class ResolvedSixDof:
    """A resolved 6DOF input: the validated spec, its source and the digests (FR-1088)."""

    source: Path
    source_sha256: str
    spec: SixDofSpec
    files_sha256: dict[str, str] = field(default_factory=dict)

    def provenance(self) -> dict[str, Any]:
        """Return what ``sixdof-provenance.json`` records.

        The file is hashed into the run record (FR-3090), so the source is named by its file
        name, not its absolute path, and ``source_sha256`` keeps the identity.
        """
        return {
            "source": self.source.name,
            "source_sha256": self.source_sha256,
            "files_sha256": dict(self.files_sha256),
            "spec": self.spec.model_dump(mode="json"),
            "units_unsettled": (
                "the solver's unit of the initial angular velocity and of the trajectory file "
                "are probe questions (P4-1, P4-2); the input states deg/s"
            ),
        }


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_row_sixdof(
    inputs_dir: str | Path, variables: Mapping[str, Any], *, workflow: str, pol: str = ""
) -> ResolvedSixDof | None:
    """Resolve ``SIXDOF: d001`` from the matrix free cell, refusing what FR-1086 and FR-1087 name.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace's inputs folder.
    variables : mapping of str to object
        The row's free-cell variables.
    workflow : str
        The row's run type.
    pol : str, optional
        The row's POL, named in refusals.

    Returns
    -------
    ResolvedSixDof or None
        The resolved input, or None when the row states no ``SIXDOF``.

    Raises
    ------
    SixDofSetupError
        A code that is not ``d`` and a name, a file outside ``inputs/sixdof/`` or
        absent, an input the model refuses, a run type other than ``unsteady``, a
        row also stating ``FSI``, a mirrored row freeing a lateral freedom, or a
        custom force file that is not a file of ``inputs/sixdof/``.
    """
    code = str(variables.get(SIXDOF_VARIABLE, "")).strip()
    if code in ("", "-"):
        return None
    where = f"row POL {pol}: " if pol else ""
    if not re.fullmatch(r"d[A-Za-z0-9_-]+", code):
        raise SixDofSetupError(
            f"{where}SIXDOF={code!r}; name a d-prefixed code without an extension, such as d001."
        )
    if workflow != _SIXDOF_WORKFLOW:
        raise SixDofSetupError(
            f"{where}SIXDOF {code} on a {workflow or 'LEGACY'} row: a body free to move needs "
            "the time march of an unsteady row, and a free body with a rotor turning is "
            "outside this route (FR-1087). Run the row as WORKFLOW unsteady."
        )
    fsi = str(variables.get("FSI", "")).strip()
    if fsi not in ("", "-"):
        raise SixDofSetupError(
            f"{where}SIXDOF {code} with FSI {fsi}: a body free to move under its loads and a "
            "structure coupled to them at once is outside this route (FR-1087); state one."
        )
    root = (Path(inputs_dir) / "sixdof").resolve()
    path = (root / f"{code}.toml").resolve()
    if path.parent != root:
        raise SixDofSetupError(f"{where}SIXDOF {code}: input resolves outside {root}.")
    if not path.is_file():
        raise SixDofSetupError(f"{where}SIXDOF {code}: no input file {path}.")
    raw = path.read_bytes()
    try:
        spec = SixDofSpec.model_validate(tomllib.loads(raw.decode("utf-8-sig")))
    except (ValidationError, tomllib.TOMLDecodeError, UnicodeError) as error:
        raise SixDofSetupError(f"{path}: invalid 6DOF input: {error}") from error
    symmetry = str(variables.get("SYMMETRY", "NONE")).strip().upper()
    lateral = [name for name in ("v", "p", "r") if getattr(spec.free, name)]
    if symmetry == "MIRROR" and lateral:
        raise SixDofSetupError(
            f"{path}: [free] frees {', '.join(lateral)} on a row whose SYMMETRY is MIRROR; a "
            "mirrored half model carries no lateral loads, so a lateral freedom would move "
            "under none. Lock v, p and r, or mesh the whole body."
        )
    spec, files = _with_force_files(spec, root, path)
    return ResolvedSixDof(path, hashlib.sha256(raw).hexdigest(), spec, files)


def _with_force_files(
    spec: SixDofSpec, root: Path, path: Path
) -> tuple[SixDofSpec, dict[str, str]]:
    """Resolve and hash each custom force's file under ``root`` (FR-1086, FR-1088)."""
    files: dict[str, str] = {}
    forces = []
    for force in spec.forces:
        if isinstance(force, SixDofCustomForce):
            source = (root / force.file).resolve()
            if source.parent != root or not source.is_file():
                raise SixDofSetupError(
                    f"{path}: [[forces]] custom file {force.file!r} is not a file of {root}; "
                    "stage the force profile beside the input."
                )
            files[source.name] = _digest(source)
            force = force.model_copy(update={"resolved_file": str(source)})
        forces.append(force)
    return spec.model_copy(update={"forces": forces}), files
