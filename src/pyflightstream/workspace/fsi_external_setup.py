"""Resolve an FSI input of ``mode = "external"`` to the program it names (FR-462, 0.40.0).

The input names a structural program of the user's own and its node file, both
under the workspace's ``inputs/fsi/``, the files the program reads and writes,
and the one family the program's structure couples to. The plan reads it,
refuses what FR-462 R4 names, counts the nodes, and hashes the program, the
node file and every declared input, so the archiving step (``pyfs-fsi
external``) can verify at every call that it runs what the plan hashed.
"""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pyflightstream._errors import PyflightstreamError
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.external import ExternalStructure, count_structural_nodes

__all__ = [
    "ExternalFsiInput",
    "FsiExternalSetupError",
    "resolve_external_fsi",
]


class FsiExternalSetupError(PyflightstreamError, ValueError):
    """An external FSI input cannot name a program the plan can hash and the step can run."""


class _ExternalTable(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    executable: str = Field(min_length=1)
    arguments: list[str] = Field(default_factory=list)
    structural_nodes: str = Field(min_length=1)
    #: Kept for the use case's spelling; on route B the solver writes the section
    #: loads file every call, and the flag is recorded, never emitted.
    export_load_distributions: bool = False
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    timeout_s: float = Field(default=3600.0, gt=0.0)


class _CouplingTable(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    families: list[str] = Field(min_length=1)
    max_iterations: int | None = Field(default=None, ge=1)
    convergence_threshold: float | None = Field(default=None, gt=0.0)


class ExternalFsiInput(BaseModel):
    """The ``inputs/fsi/f<id>.toml`` of an external structural program (FR-462 R1).

    Attributes
    ----------
    mode : {'external'}
        The mode.
    external : table
        ``executable``, ``arguments``, ``structural_nodes``, ``inputs``,
        ``outputs``, ``timeout_s``.
    coupling : table
        ``families`` (one), ``max_iterations``, ``convergence_threshold``.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["external"]
    external: _ExternalTable
    coupling: _CouplingTable


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _under(root: Path, stated: str, *, what: str, source: Path) -> Path:
    """Resolve a file the input names under ``root``, refusing one outside or absent."""
    path = (root / stated).resolve()
    if root not in path.parents or not path.is_file():
        raise FsiExternalSetupError(
            f"{source}: {what} {stated!r} is not a file under {root}; stage it in the "
            "workspace's inputs/fsi/ so the plan can hash it and the run can repeat it."
        )
    return path


def _refuse_the_beam_keys(source: Path, data: dict[str, object]) -> None:
    """Refuse ``show_console`` and ``morphing`` by name (FR-462 R4)."""
    table = data.get("external")
    if isinstance(table, dict) and "show_console" in table:
        raise FsiExternalSetupError(
            f"{source}: [external] show_console: a console window per coupling call would "
            "open on the desktop; the step always runs the program with no window. Remove it."
        )
    if "morphing" in data or (isinstance(table, dict) and "morphing" in table):
        raise FsiExternalSetupError(
            f"{source}: morphing: the solver's direct mesh morphing is a route of the "
            "package's beam; an external program is coupled through the aeroelastic "
            "toolbox's interpolation. Remove it."
        )


def resolve_external_fsi(path: str | Path) -> ExternalStructure:
    """Read, check and hash an external FSI input (FR-462 R1, R4, R6).

    Parameters
    ----------
    path : str or Path
        The FSI input file, under ``inputs/fsi/``.

    Returns
    -------
    ExternalStructure
        The program, its node file and declared inputs, hashed.

    Raises
    ------
    FsiExternalSetupError
        ``show_console`` or ``morphing`` stated, a key the input does not define, a
        program, node file or declared input outside ``inputs/fsi/`` or absent, a
        node file with no node, or more than one coupled family.
    """
    source = Path(path).resolve()
    root = source.parent
    raw = source.read_bytes()
    try:
        data = tomllib.loads(raw.decode("utf-8-sig"))
    except (tomllib.TOMLDecodeError, UnicodeError) as error:
        raise FsiExternalSetupError(f"{source}: invalid FSI input: {error}") from error
    _refuse_the_beam_keys(source, data)
    try:
        spec = ExternalFsiInput.model_validate(data)
    except ValidationError as error:
        raise FsiExternalSetupError(f"{source}: invalid external FSI input: {error}") from error
    if len(spec.coupling.families) != 1:
        raise FsiExternalSetupError(
            f"{source}: [coupling] families = {spec.coupling.families}: the external route "
            "couples one family, the wing fed by one section distribution, as the beam's "
            "fixed-wing route does; name one."
        )
    executable = _under(root, spec.external.executable, what="executable", source=source)
    nodes = _under(root, spec.external.structural_nodes, what="structural_nodes", source=source)
    try:
        node_count = count_structural_nodes(nodes)
    except FsiInputError as error:
        raise FsiExternalSetupError(f"{source}: structural_nodes: {error}") from error
    inputs: dict[str, str] = {}
    digests: dict[str, str] = {}
    for stated in spec.external.inputs:
        found = _under(root, stated, what="declared input", source=source)
        if found.name in inputs:
            raise FsiExternalSetupError(
                f"{source}: two declared inputs share the name {found.name!r}, and both would "
                "be staged under it in the point folder; rename one."
            )
        inputs[found.name] = str(found)
        digests[found.name] = _digest(found)
    for name in spec.external.outputs:
        if Path(name).name != name:
            raise FsiExternalSetupError(
                f"{source}: declared output {name!r} is not a bare file name of the point folder."
            )
    return ExternalStructure(
        source=str(source),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        executable=str(executable),
        executable_sha256=_digest(executable),
        arguments=list(spec.external.arguments),
        structural_nodes=str(nodes),
        structural_nodes_sha256=_digest(nodes),
        node_count=node_count,
        inputs=inputs,
        inputs_sha256=digests,
        outputs=list(spec.external.outputs),
        timeout_s=spec.external.timeout_s,
        families=list(spec.coupling.families),
        max_iterations=spec.coupling.max_iterations,
        convergence_threshold=spec.coupling.convergence_threshold,
    )
