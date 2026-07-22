"""Managed campaign workspace: inputs, run files, and the manifest.

Pipeline role: owns where campaign files live, inputs and outputs
alike. Folder layout, the reusable input-artifact library, staging of
solver inputs, collection of outputs, and archiving are managed by the
package, not by the user: folder identity mistakes were a recurring
failure mode in the predecessor toolchain. Run identity lives in the
manifest (``runs.json``), never in folder or file names; names are
generated, English, and stable, and are never parsed for meaning (SAD
Section 6). Human-readable names come from the output-only
:class:`~pyflightstream.workspace.naming.NamingTemplate`.

The managed layout under a user-chosen campaign root, created by
:meth:`CampaignWorkspace.init` (or ``pyfs-workspace init``):

- ``runs.json``: the authoritative manifest, one record per executed
  point.
- ``inputs/``: the reusable input-artifact library
  (:mod:`pyflightstream.workspace.inputs`): ``geometries/``,
  ``references/``, ``setups/``, ``groups/``, ``profiles/``, plus the
  ``executables.toml`` build registry; artifacts are declarative TOML
  resolved by stable id.
- ``sims/sim_<sim_id>/``: per-simulation folder with ``inputs/``
  (staged copies with recorded sha256), ``scripts/`` (generated script
  text per point), ``raw/`` (solver outputs as produced), and
  ``parsed/`` (typed extracts).
- ``post/``: post-processing products (sweep tables and exports built
  by reading the manifest).
- ``archive/``: zipped completed simulations, manifest-driven.

Archiving and cleaning refuse to act when the manifest is missing or
does not record the target simulation, so file management can never
destroy an unrecorded run.

This package was renamed from ``pyflightstream.files`` in v0.3.0; the
old module name re-exports everything with a DeprecationWarning for
one minor release.
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
import shutil
import zipfile
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from pyflightstream.workspace.inputs import (
    EXECUTABLES_FILE,
    INPUT_KINDS,
    GroupsArtifact,
    InputArtifactError,
    PointXyz,
    PropellerReference,
    ReferenceArtifact,
    SetupArtifact,
    resolve_executable,
    resolve_geometry,
    resolve_group,
    resolve_profile,
    resolve_reference,
    resolve_setup,
)
from pyflightstream.workspace.naming import NamingTemplate, NamingTemplateError

__all__ = [
    "EXECUTABLES_FILE",
    "INPUT_KINDS",
    "CampaignWorkspace",
    "GroupsArtifact",
    "InputArtifactError",
    "NamingTemplate",
    "NamingTemplateError",
    "PointXyz",
    "PropellerReference",
    "ReferenceArtifact",
    "RunRecord",
    "RunStatus",
    "SetupArtifact",
    "WorkspaceError",
]

_SIM_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_SIM_SUBDIRS = ("inputs", "scripts", "raw", "parsed")

# Comment-only template written by init when no registry exists yet;
# didactic: shows the entry shape without registering a fake build.
_EXECUTABLES_TEMPLATE = """\
# FlightStream build registry of this workspace (one entry per build):
#   "26.120" = "C:/path/to/FlightStream.exe"
# resolve_executable(build_id) reads this table; an explicit override
# path is the only way to run an unregistered build.
"""


class WorkspaceError(RuntimeError):
    """A file-management operation was refused or impossible.

    The refusals protect run evidence: archiving or cleaning without a
    manifest record would destroy a run the manifest cannot account
    for, and collection of a declared output that the solver never
    produced points at an incomplete run.
    """


class RunStatus(enum.StrEnum):
    """Terminal status of one executed campaign point (SAD Section 7).

    Every executed point lands in exactly one of these; a silent skip
    is structurally impossible in the campaign loop.
    """

    CONVERGED = "CONVERGED"
    COMPLETED_MAX_ITER = "COMPLETED_MAX_ITER"
    FAILED_EXECUTION = "FAILED_EXECUTION"
    FAILED_SCRIPT = "FAILED_SCRIPT"
    FAILED_INCOMPLETE_OUTPUT = "FAILED_INCOMPLETE_OUTPUT"
    FAILED_DIVERGED = "FAILED_DIVERGED"


class RunRecord(BaseModel):
    """One manifest record: a single executed campaign point.

    The record plus the staged inputs reproduce the run (NFR-07).

    Attributes
    ----------
    run_id : str
        Unique identity of the executed point, for example
        ``"campaign/sim_9001/a+02.0_b+00.0"``; the manifest rejects
        duplicates.
    sim_id : str
        Simulation identity; ties the record to ``sims/sim_<sim_id>``.
    point : dict of str to float
        Sweep point coordinates, for example alpha and beta in deg.
    fs_version_requested : str
        Canonical FlightStream version the script was built for.
    fs_version_reported : str, optional
        Version printed in the solver outputs; filled by the parsers
        and cross-checked against the requested one (FR-18).
    fs_build : str, optional
        Build string reported by the solver, when available.
    package_version : str
        pyflightstream version that produced the run.
    script_sha256 : str
        Hash of the executed script text.
    inputs_sha256 : dict of str to str
        Hash per staged input file name, recorded at staging time.
    raw_flag : bool
        True when the script used the ``raw()`` escape hatch and its
        content bypassed database validation (FR-07).
    solver_setup : dict, optional
        Serialized solver-setup snapshot
        (:class:`pyflightstream.script.solver_setup.SolverSetup`) of
        the built script: every solver flag with its effective value
        and provenance (explicit, default with citation, or unknown).
        None for scripts built without the curated ``solver_settings``
        helper and for manifests written before v0.3.0.
    status : RunStatus
        Terminal status of the point.
    iterations : int, optional
        Solver iterations reached, when parsed.
    residual : float, optional
        Final residual, when parsed.
    wall_time_s : float, optional
        Wall-clock duration of the solver process in seconds.
    outputs : list of str
        Collected output files, relative to the simulation folder
        (for example ``"raw/loads.txt"``).
    error : str, optional
        Error text for failed points.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    sim_id: str
    point: dict[str, float] = Field(default_factory=dict)
    fs_version_requested: str
    fs_version_reported: str | None = None
    fs_build: str | None = None
    package_version: str
    script_sha256: str
    inputs_sha256: dict[str, str] = Field(default_factory=dict)
    raw_flag: bool
    solver_setup: dict | None = None
    status: RunStatus
    iterations: int | None = None
    residual: float | None = None
    wall_time_s: float | None = None
    outputs: list[str] = Field(default_factory=list)
    error: str | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


class CampaignWorkspace:
    """The managed folder layout of one campaign root.

    Parameters
    ----------
    root : str or Path
        User-chosen campaign root; everything below it is managed by
        this class and never hand-built.
    naming : NamingTemplate, optional
        Output-only naming template for generated scripts, rendered
        export names, and archive names; the default reproduces the
        historical names (``{point}`` stems, ``sim_<sim_id>`` zips).
        Identity always stays in the manifest, never in a name.

    Attributes
    ----------
    root : Path
        The campaign root.
    naming : NamingTemplate
        The active naming template.
    """

    def __init__(self, root: str | Path, naming: NamingTemplate | None = None):
        self.root = Path(root)
        self.naming = naming if naming is not None else NamingTemplate()

    @classmethod
    def init(cls, root: str | Path, naming: NamingTemplate | None = None) -> CampaignWorkspace:
        """Create the full campaign tree under ``root``, idempotently.

        Creates the input-artifact library skeleton
        (``inputs/geometries``, ``inputs/references``,
        ``inputs/setups``, ``inputs/groups``, ``inputs/profiles``),
        ``sims/``, ``post/``, and ``archive/``; existing folders and
        files are kept untouched, so re-running init on a live
        campaign root is safe. When no build registry exists yet, a
        comment-only ``inputs/executables.toml`` template is written
        showing the entry shape.

        Parameters
        ----------
        root : str or Path
            Campaign root to create or complete.
        naming : NamingTemplate, optional
            Naming template of the returned workspace.

        Returns
        -------
        CampaignWorkspace
            The workspace over the created tree.
        """
        workspace = cls(root, naming=naming)
        for kind in INPUT_KINDS:
            (workspace.inputs_dir / kind).mkdir(parents=True, exist_ok=True)
        for name in ("sims", "post", "archive"):
            (workspace.root / name).mkdir(parents=True, exist_ok=True)
        registry = workspace.inputs_dir / EXECUTABLES_FILE
        if not registry.exists():
            registry.write_text(_EXECUTABLES_TEMPLATE, encoding="utf-8")
        return workspace

    @property
    def manifest_path(self) -> Path:
        """Location of the authoritative manifest, ``runs.json``."""
        return self.root / "runs.json"

    @property
    def inputs_dir(self) -> Path:
        """Root of the input-artifact library, ``inputs/``."""
        return self.root / "inputs"

    def resolve_reference(self, artifact_id: str) -> ReferenceArtifact:
        """Load the reference-data artifact one id names.

        See :func:`pyflightstream.workspace.inputs.resolve_reference`;
        the id is the file name stem under ``inputs/references/``, and
        a miss lists the available ids.
        """
        return resolve_reference(self.inputs_dir, artifact_id)

    def resolve_setup(self, artifact_id: str) -> SetupArtifact:
        """Load the solver-setup preset one id names.

        See :func:`pyflightstream.workspace.inputs.resolve_setup`; the
        raw settings table is kept verbatim for the future formal
        solver-setup model.
        """
        return resolve_setup(self.inputs_dir, artifact_id)

    def resolve_group(self, artifact_id: str) -> GroupsArtifact:
        """Load the named boundary groups one id names.

        See :func:`pyflightstream.workspace.inputs.resolve_group`;
        members are boundary labels or indices, stored verbatim.
        """
        return resolve_group(self.inputs_dir, artifact_id)

    def resolve_geometry(self, artifact_id: str) -> Path:
        """Resolve the staged geometry file one id (file stem) names.

        See :func:`pyflightstream.workspace.inputs.resolve_geometry`.
        """
        return resolve_geometry(self.inputs_dir, artifact_id)

    def resolve_profile(self, artifact_id: str) -> Path:
        """Resolve the input profile file one id (file stem) names.

        See :func:`pyflightstream.workspace.inputs.resolve_profile`.
        """
        return resolve_profile(self.inputs_dir, artifact_id)

    def resolve_executable(self, build_id: str, override: str | Path | None = None) -> Path:
        """Resolve the FlightStream executable of one build id.

        Registry mode reads ``inputs/executables.toml``; an explicit
        ``override`` path bypasses the registry and is the only way to
        run an unregistered build. See
        :func:`pyflightstream.workspace.inputs.resolve_executable`.
        """
        return resolve_executable(self.inputs_dir, build_id, override=override)

    def sim_dir(self, sim_id: str) -> Path:
        """Return the managed folder of one simulation.

        Parameters
        ----------
        sim_id : str
            Simulation identity; letters, digits, underscore, and
            hyphen only, so the derived folder name is stable and
            portable (NFR-10).
        """
        if not _SIM_ID_PATTERN.match(sim_id):
            raise WorkspaceError(
                f"sim_id {sim_id!r} cannot name a managed folder: use letters, digits, "
                "underscore, or hyphen. Folder names derive from sim_id and must stay "
                "stable and portable; identity lives in the manifest, not in names."
            )
        return self.root / "sims" / f"sim_{sim_id}"

    def create_sim(self, sim_id: str) -> Path:
        """Create the managed subfolders of one simulation and return its path.

        Creates ``inputs/``, ``scripts/``, ``raw/``, and ``parsed/``;
        existing folders are kept, so the call is idempotent.
        """
        sim = self.sim_dir(sim_id)
        for name in _SIM_SUBDIRS:
            (sim / name).mkdir(parents=True, exist_ok=True)
        return sim

    def stage_inputs(self, sim_id: str, sources: Sequence[str | Path]) -> dict[str, str]:
        """Copy input files into ``inputs/`` and record their hashes.

        Staging happens before execution so the manifest can tie the
        run to the exact input content (NFR-07).

        Parameters
        ----------
        sim_id : str
            Target simulation.
        sources : sequence of str or Path
            Files to copy; each must exist.

        Returns
        -------
        dict of str to str
            sha256 per staged file name, ready for
            :attr:`RunRecord.inputs_sha256`.
        """
        sim = self.create_sim(sim_id)
        hashes: dict[str, str] = {}
        for source in sources:
            origin = Path(source)
            if not origin.is_file():
                raise WorkspaceError(
                    f"cannot stage {origin}: the file does not exist. Staging copies "
                    "inputs before execution so the manifest records what actually ran."
                )
            target = sim / "inputs" / origin.name
            shutil.copy2(origin, target)
            hashes[origin.name] = _sha256(target)
        return hashes

    def write_script(self, sim_id: str, name: str, text: str) -> tuple[Path, str]:
        """Write one generated script into ``scripts/`` and hash it.

        Parameters
        ----------
        sim_id : str
            Target simulation.
        name : str
            Script file name, for example ``"a+02.0_b+00.0.txt"``.
        text : str
            Rendered script text from the builder.

        Returns
        -------
        Path
            Location of the written script.
        str
            sha256 of the written text, for
            :attr:`RunRecord.script_sha256`.
        """
        sim = self.create_sim(sim_id)
        target = sim / "scripts" / name
        target.write_text(text, encoding="utf-8")
        return target, _sha256(target)

    def collect_outputs(self, sim_id: str, produced: Sequence[str | Path]) -> list[str]:
        """Move declared solver outputs into ``raw/``.

        Parameters
        ----------
        sim_id : str
            Target simulation.
        produced : sequence of str or Path
            Output files the run declared it would produce, wherever
            the script wrote them.

        Returns
        -------
        list of str
            Collected names relative to the simulation folder
            (``"raw/<name>"``), ready for :attr:`RunRecord.outputs`.

        Raises
        ------
        WorkspaceError
            If a declared output does not exist; the campaign loop
            turns this into FAILED_INCOMPLETE_OUTPUT, never into a
            silently shorter output set.
        """
        sim = self.create_sim(sim_id)
        missing = [str(path) for path in produced if not Path(path).is_file()]
        if missing:
            raise WorkspaceError(
                f"declared outputs were not produced: {', '.join(missing)}. A missing "
                "declared output marks the point FAILED_INCOMPLETE_OUTPUT; outputs are "
                "never silently dropped."
            )
        collected: list[str] = []
        for path in produced:
            origin = Path(path)
            shutil.move(str(origin), sim / "raw" / origin.name)
            collected.append(f"raw/{origin.name}")
        return collected

    def read_manifest(self) -> list[RunRecord]:
        """Read and validate every record of ``runs.json``.

        Returns an empty list when the manifest does not exist yet.
        """
        if not self.manifest_path.is_file():
            return []
        entries = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return [RunRecord.model_validate(entry) for entry in entries]

    def append_record(self, record: RunRecord) -> None:
        """Append one record to the manifest, atomically.

        The manifest is rewritten through a temporary file and an
        atomic replace, so a crash never leaves it half-written; a
        duplicate ``run_id`` is rejected because the manifest is the
        run identity (PP-6).
        """
        records = self.read_manifest()
        if any(existing.run_id == record.run_id for existing in records):
            raise WorkspaceError(
                f"run_id {record.run_id!r} is already in the manifest; run identity "
                "must be unique. Use a new run_id or archive the campaign first."
            )
        records.append(record)
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([entry.model_dump(mode="json") for entry in records], indent=2)
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(payload + "\n", encoding="utf-8")
        temporary.replace(self.manifest_path)

    def archive_sim(self, sim_id: str, campaign: str | None = None) -> Path:
        """Zip one recorded simulation into ``archive/`` and remove its folder.

        The zip name comes from the workspace naming template
        (default ``sim_<sim_id>.zip``); like every generated name it
        is output only and never parsed back.

        Parameters
        ----------
        sim_id : str
            Recorded simulation to archive.
        campaign : str, optional
            Campaign name, needed only when the archive template uses
            the ``{campaign}`` placeholder.

        Returns
        -------
        Path
            Location of the written zip file.

        Raises
        ------
        WorkspaceError
            If the manifest is missing, does not record ``sim_id``, or
            the simulation folder does not exist: file management
            never destroys an unrecorded run.
        """
        sim = self._recorded_sim(sim_id, operation="archive")
        archive_dir = self.root / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        stem = self.naming.render_archive(sim=sim_id, campaign=campaign)
        target = archive_dir / f"{stem}.zip"
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(sim.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(sim))
        shutil.rmtree(sim)
        return target

    def clean_sim(self, sim_id: str) -> None:
        """Remove one recorded simulation folder without archiving it.

        Raises
        ------
        WorkspaceError
            Same refusals as :meth:`archive_sim`.
        """
        sim = self._recorded_sim(sim_id, operation="clean")
        shutil.rmtree(sim)

    def _recorded_sim(self, sim_id: str, operation: str) -> Path:
        sim = self.sim_dir(sim_id)
        if not self.manifest_path.is_file():
            raise WorkspaceError(
                f"refusing to {operation} sim_{sim_id}: no manifest (runs.json) exists "
                "in this campaign root. Without the manifest the folder content cannot "
                "be accounted for, and file management never destroys an unrecorded run."
            )
        if not any(record.sim_id == sim_id for record in self.read_manifest()):
            raise WorkspaceError(
                f"refusing to {operation} sim_{sim_id}: the manifest has no record of "
                "this simulation, so its folder would be destroyed unaccounted."
            )
        if not sim.is_dir():
            raise WorkspaceError(
                f"cannot {operation} sim_{sim_id}: the folder {sim} does not exist."
            )
        return sim
