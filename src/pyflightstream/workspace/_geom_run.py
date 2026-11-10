"""The runner of the geometry pipeline: stages in order, stop at the first failed check.

Pipeline role: executes the stages of :mod:`pyflightstream.geometry._stage_table` for one
resolved configuration and returns the report a design loop reads. A stage returns its checks,
and the runner writes one stage record per stage and a report last. The first failed check
stops the run and the report names its stage and its check, with the value measured and the
limit; a refused input stops it as ``refused``. A report is returned, never raised, so a loop
of parameter sets continues after a failed one (:func:`run_doe`, each set in a worker process of
its own, so a fault of the kernel ends that set only).

A stage with no function in this tree is recorded with every check ``skipped`` and the reason,
and a check of the table that a built stage did not return is added to its record as
``skipped``. The report lists each such check in ``not_run`` and its status is ``incomplete``
(exit code 3), never ``accepted``: a run that reaches ``S13`` through checks it never measured is
not read as a verified model.
"""

from __future__ import annotations

import copy
import json
import os
import re
import time
import tomllib
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from pyflightstream._errors import (
    InputArtifactError,
    InputValueError,
    PyflightstreamError,
)
from pyflightstream.extras import MissingExtraError
from pyflightstream.geometry import resolve_config
from pyflightstream.geometry.stages import (
    STAGE_ROWS,
    CheckFailedError,
    StageRow,
    adopt_surface_file,
    blister_model,
    check_entry,
    fillet_model,
    geometry_report,
    junctions,
    parameter_id,
    stage_index,
    stage_record,
    unpack,
    write_record,
)
from pyflightstream.workspace._geom_log import LOG_NAME, RunLog
from pyflightstream.workspace._gmsh_worker import _ENV as WORKER_ENV
from pyflightstream.workspace._gmsh_worker import run_isolated

__all__ = [
    "RunContext",
    "Stage",
    "StageOutcome",
    "add_control_surfaces",
    "default_stages",
    "run_doe",
    "run_geometry",
    "run_set",
    "split_symmetry",
]


@dataclass
class StageOutcome:
    """What one stage returns: its checks, findings, warnings and the files it wrote.

    ``wall_s`` is the stage's own wall time when the stage measured it apart from the call
    (a sub-step of S10, all run in one call); None lets the runner time the call.
    """

    checks: list[dict[str, Any]] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    wall_s: float | None = None


@dataclass
class RunContext:
    """The inputs every stage reads and the values a stage hands to the next.

    ``resolved`` is the resolved configuration (with every override applied), ``members`` the
    component names of the selected configuration, ``state`` the scratch the stages share, and
    ``out`` the folder the records and files are written to.
    """

    resolved: dict[str, Any]
    configuration: str | None
    variant: str
    out: Path
    parameter_id: str
    members: list[str]
    state: dict[str, Any] = field(default_factory=dict)


StageFn = Callable[[RunContext], StageOutcome]


@dataclass(frozen=True)
class Stage:
    """One stage of a run: its row of the table and its function, when this tree has one."""

    row: StageRow
    run: StageFn | None


def _definition(context: RunContext) -> StageOutcome:
    """S0: the configuration resolved, so every key is known and every relationship holds."""
    resolved = context.resolved
    return StageOutcome(
        checks=[check_entry("input.valid", "passed", 0, 0, unit="refused keys")],
        findings=[str(item) for item in resolved.get("findings", [])],
        warnings=[str(item) for item in resolved.get("warnings", [])],
        outputs={"components": list(resolved["components"]), "members": context.members},
    )


def _generate(resolved: dict[str, Any], target: Path, configuration: str | None):
    """Write the IGES with the kernel in a worker process, unless this already is one.

    gmsh state is a process singleton and the kernel can fault natively (design B.5), so a
    caller's own loop of :func:`run_geometry` keeps running after a fault: the fault returns as
    an ``InputArtifactError`` and the stage fails. Inside a :func:`run_doe` worker the set
    already has a process of its own.
    """
    arguments = {"config": resolved, "path": str(target), "configuration": configuration}
    if os.environ.get(WORKER_ENV) == "1":
        return _generate_record(resolved, str(target), configuration)
    return run_isolated(f"{__name__}:_generate_record", arguments, _generate_record)


def _generate_record(config: Any, path: str, configuration: str | None) -> dict[str, Any]:
    """Write the IGES and return the record of ``generate_iges`` as JSON values (a worker's)."""
    from pyflightstream.workspace._geom_export import generate_record

    written = generate_record(config, path, configuration)
    return json.loads(json.dumps(written, default=str))


def _export(context: RunContext) -> StageOutcome:
    """S11: the exposed skin of the selected members as one named IGES, read by the profile gate."""
    if context.variant != "clean":
        return _waiting_variant(context, "S11")
    name = context.configuration or str(
        unpack(context.resolved["aircraft"]).get("name", "geometry")
    )
    target = context.out / f"{name}.igs"
    try:
        assembled = context.state.get("assembly")
        written = (
            assembled["export"]
            if assembled
            else _generate(context.resolved, target, context.configuration)
        )
    except InputArtifactError as error:
        if "solid entities" not in str(error):
            raise
        return StageOutcome(
            checks=[check_entry("profile.surfaces_only", "failed", 1, 0, note=str(error))]
        )
    warnings = [
        str(item) for item in written["warnings"] if item not in context.resolved["warnings"]
    ]
    context.state["export"] = written
    measured = _export_step("S11")(context)
    return StageOutcome(
        checks=measured.checks,
        warnings=warnings + measured.warnings,
        outputs={
            **measured.outputs,
            "iges": written["iges"],
            "manifest": written["manifest"],
            "surface_id": written["surface_id"],
            "build_id": written["build_id"],
            "faces": written["faces"],
            "audit": written["audit"],
        },
    )


def _export_step(stage: str) -> StageFn:
    """Run one measured export sub-step with the independently retained source identity."""

    def run(context: RunContext) -> StageOutcome:
        from pyflightstream.workspace._geom_export import check_export

        if context.variant != "clean":
            return _waiting_variant(context, stage)
        return StageOutcome(
            **check_export(
                stage,
                context.resolved,
                configuration=context.configuration,
                members=context.members,
                out=context.out,
                source=context.state["export"],
            )
        )

    return run


def _waiting_variant(context: RunContext, stage: str) -> StageOutcome:
    note = f"waiting for G9: applied-control variant {context.variant}"
    row = next(r for r in STAGE_ROWS if r.stage == stage)
    return StageOutcome(
        checks=[check_entry(cid, "skipped", note=note) for cid, _ in row.checks],
        outputs={"state": "waiting", "waiting_for": "G9", "variant": context.variant},
    )


#: The inputs of a blend piece that each of its sub-steps reports, by component type.
_BLEND_INPUTS = {
    "fillet": ("hosts", "laws", "extend_lower_to_te", "patches", "wing_band", "host_band"),
    "blister": ("host", "stations", "profile", "sections", "sections_file", "tips"),
}


#: The stage ids of each blend piece's sub-steps start with its prefix.
_BLEND_PREFIX = {"fillet": "S8.F", "blister": "S8.B"}


def _blend_model(kind: str, component, components, name):
    """Return the model of one piece, or the failed check its build stopped at."""
    try:
        if kind == "fillet":
            return fillet_model(component, components, name)
        host = component["host"]
        if components[host]["type"] != "body":
            raise InputValueError(f"{name}.host: a blister lies on a body; {host!r} is not one")
        return blister_model(component, components[host])
    except CheckFailedError as failure:
        return failure.check


def _blend_models(context: RunContext, kind: str) -> dict[str, Any]:
    """Return the fillet or blister models of the selected members, built once per run.

    A piece whose build stopped at a failed check holds that check in place of its model.
    """
    key = f"blend.{kind}"
    if key not in context.state:
        components = unpack(context.resolved)["components"]
        context.state[key] = {
            name: _blend_model(kind, components[name], components, name)
            for name in context.members
            if components[name]["type"] == kind
        }
    return context.state[key]


def _owner(kind: str, check_id: str) -> str:
    """Return the sub-step of ``kind`` whose row names ``check_id``; its first one otherwise."""
    rows = [r for r in STAGE_ROWS if r.stage.startswith(_BLEND_PREFIX[kind])]
    return next((r.stage for r in rows if check_id in {c for c, _ in r.checks}), rows[0].stage)


def _stopped_piece(kind, stage, wanted, name, failed):
    """Return the checks of ``stage`` for a piece whose build stopped at the check ``failed``."""
    owner = _owner(kind, failed["id"])
    if owner == stage:
        return [{**failed, "where": {**failed["where"], "component": name}}]
    note = f"not measured: {name} stopped at {owner} {failed['id']}"
    return [check_entry(cid, "skipped", where={"component": name}, note=note) for cid in wanted]


def _blend_step(kind: str, stage: str) -> StageFn:
    """Return the function of one sub-step of a blend piece: its own checks of each piece.

    The sub-step reports, per piece, the checks its row of the stage table names (each with the
    piece in ``where``) and the piece's inputs; a configuration with no such piece reports each
    check skipped with that reason.
    """

    def run(context: RunContext) -> StageOutcome:
        row = next(r for r in STAGE_ROWS if r.stage == stage)
        wanted = [cid for cid, _ in row.checks]
        models = _blend_models(context, kind)
        if not models:
            note = f"no {kind} among the members of this configuration"
            return StageOutcome(checks=[check_entry(cid, "skipped", note=note) for cid in wanted])
        components = unpack(context.resolved)["components"]
        checks, inputs = [], {}
        for name, model in models.items():
            if isinstance(model, dict):  # the build stopped at this failed check
                checks += _stopped_piece(kind, stage, wanted, name, model)
            else:
                for record in model.records:
                    if record["id"] in wanted:
                        checks.append({**record, "where": {**record["where"], "component": name}})
            inputs[name] = {
                k: components[name][k]
                for k in _BLEND_INPUTS[kind]
                if components[name].get(k) not in (None, "")
            }
        return StageOutcome(checks=checks, outputs={"inputs": inputs})

    return run


def _plan(context: RunContext) -> tuple[list[Any], list[str]]:
    """Return the dominance operations on the members of the run, and the rows it skipped."""
    warnings: list[str] = []
    rows = unpack(context.resolved).get("dominance", [])
    return junctions.dominance_plan(rows, context.members, warnings), warnings


def _dominance(context: RunContext) -> StageOutcome:
    """S10: the dominance rows read on the members; a cycle was refused at S0 already."""
    plan, warnings = _plan(context)
    names = [f"{op.operation} {op.dominant} > {op.dominated}" for op in plan]
    return StageOutcome(
        checks=[check_entry("dominance.plan", "passed", 0, 0, unit="cycles")],
        warnings=warnings,
        outputs={"operations": names},
    )


def _assembly(context: RunContext) -> dict[str, Any] | None:
    """Return the sub-step records of the assembly, run once per run in a worker.

    None when no dominance row applies to the members: nothing is assembled, no kernel opens.
    """
    if "assembly" not in context.state:
        plan, _ = _plan(context)
        arguments: dict[str, Any] = {
            "config": context.resolved,
            "members": context.members,
            "out": str(context.out / "S10-assembly.json"),
            "configuration": context.configuration,
        }
        if not plan:
            context.state["assembly"] = None
        elif os.environ.get(WORKER_ENV) == "1":
            context.state["assembly"] = _assembly_record(**arguments)
        else:
            context.state["assembly"] = run_isolated(
                f"{__name__}:_assembly_record", arguments, _assembly_record
            )
    return context.state["assembly"]


def _assembly_record(
    config: Any, members: list[str], out: str, configuration: str | None = None
) -> dict[str, Any]:
    """Build the members on a kernel and run the S10 sub-steps; return their records as JSON."""
    from pyflightstream.geometry import resolve_config
    from pyflightstream.geometry.stages import GeneratedPiece, generate_components
    from pyflightstream.workspace._geom_assembly import Assembly
    from pyflightstream.workspace._geom_export import write_assembly
    from pyflightstream.workspace._gmsh import open_kernel

    resolved = resolve_config(copy.deepcopy(config))
    every = generate_components(resolved, trimmed=True)
    again = generate_components(resolve_config(copy.deepcopy(config)), trimmed=True)
    plain = unpack(resolved)
    pieces = {name: every[name] for name in members if name in every}
    half = all(
        float(p.controls[..., 1].min()) >= -1e-9
        for ps in pieces.values()
        for p in (ps.bases.values() if isinstance(ps, GeneratedPiece) else ps)
    )
    kernel = open_kernel("assembling the pieces by the dominance rows")
    try:
        assembly = Assembly(
            kernel,
            pieces,
            plain.get("dominance", []),
            out=Path(out).parent,
            members=members,
            kinds={name: plain["components"][name]["type"] for name in pieces},
            plane_axis=1 if half else None,
            regenerated={
                name: list(p.bases.values()) if isinstance(p, GeneratedPiece) else list(p)
                for name, p in again.items()
                if name in pieces
            },
            coverage_fraction=float(plain["acceptance"]["coverage_fraction"]),
            coverage_spacing=float(plain["acceptance"]["coverage_spacing"]),
        )
        records = assembly.run()
        written = {}
        if not any(c["status"] == "failed" for r in records for c in r["checks"]):
            for name in pieces:
                if name not in assembly.models:
                    assembly.models[name] = GeneratedPiece.from_patches(
                        name, plain["components"][name]["version"], assembly.sources[name]
                    )
            written = write_assembly(
                assembly,
                Path(out).parent / "assembly.igs",
                resolved=resolved,
                configuration=configuration,
            )
            written["sections"] = {
                n: p.layout["sections"]
                for n, p in every.items()
                if isinstance(p, GeneratedPiece) and "sections" in p.layout
            }
    finally:
        kernel.close()
    result = json.loads(json.dumps({"records": records, "export": written}, default=str))
    write_record(Path(out), result)
    return result


def _assembly_step(stage: str) -> StageFn:
    """Return the function of one sub-step of S10: its record from the assembly's run."""

    def run(context: RunContext) -> StageOutcome:
        if context.variant != "clean":
            return _waiting_variant(context, stage)
        ids = [cid for cid, _ in next(r for r in STAGE_ROWS if r.stage == stage).checks]
        result = _assembly(context)
        if result is None:
            note = "no dominance row applies to the members of this configuration"
            return StageOutcome(checks=[check_entry(c, "skipped", note=note) for c in ids])
        record = next((r for r in result["records"] if r["stage"] == stage), None)
        if record is None:
            note = f"not measured: the assembly stopped at {result['records'][-1]['stage']}"
            return StageOutcome(checks=[check_entry(c, "skipped", note=note) for c in ids])
        # the assembly runs every sub-step in the first call; each record keeps its own time
        return StageOutcome(
            checks=record["checks"],
            warnings=record["warnings"],
            outputs=record["outputs"],
            wall_s=float(record["wall_s"]),
        )

    return run


def _closures(context: RunContext) -> StageOutcome:
    """S8: measure the preceding stage's lifting models, building absent models once."""
    from pyflightstream.geometry import stages

    checks, inputs = [], {}
    models = context.state.setdefault("lifting_models", {})
    components = unpack(context.resolved)["components"]
    for name in context.members:
        component = components[name]
        if component["type"] != "lifting_surface":
            continue
        if name not in models:
            models[name] = stages.lifting_model(component)
        model = models[name]
        if not model.caps:
            continue
        gap = stages.cap_edge_gap(model)
        checks.append(
            check_entry(
                "closure.cap_edge_gap",
                "passed" if gap <= stages.CAP_EDGE_GAP else "failed",
                gap,
                stages.CAP_EDGE_GAP,
                unit="m",
                where={"component": name},
                note="BUG: a cap boundary leaves its neighbouring edge"
                if gap > stages.CAP_EDGE_GAP
                else "4001 samples on each shared cap boundary",
            )
        )
        inputs[name] = {"cap": component["tip_cap"], "root": component["root"]}
    if not checks:
        checks.append(check_entry("closure.cap_edge_gap", "skipped", note="no lifting caps"))
    return StageOutcome(checks=checks, outputs={"inputs": inputs})


#: The stage functions of this tree, by stage id. A stage not named here is recorded skipped.
STAGE_FUNCTIONS: dict[str, StageFn] = {
    "S0": _definition,
    "S8": _closures,
    "S10": _dominance,
    **{row.stage: _assembly_step(row.stage) for row in STAGE_ROWS if row.stage.startswith("S10.")},
    "S11": _export,
    "S11.V": _export_step("S11.V"),
    "S11.P": _export_step("S11.P"),
    "S11.R": _export_step("S11.R"),
    "S11.S": _export_step("S11.S"),
    "S13.R": _export_step("S13.R"),
    "S13": _export_step("S13"),
    "S8.F1": _blend_step("fillet", "S8.F1"),
    "S8.F2": _blend_step("fillet", "S8.F2"),
    "S8.F3": _blend_step("fillet", "S8.F3"),
    "S8.B1": _blend_step("blister", "S8.B1"),
    "S8.B2": _blend_step("blister", "S8.B2"),
    "S8.B3": _blend_step("blister", "S8.B3"),
}


def default_stages() -> list[Stage]:
    """Return every stage of the table with the function this tree holds for it, if any."""
    return [Stage(row, STAGE_FUNCTIONS.get(row.stage)) for row in STAGE_ROWS]


def _package_version() -> str:
    try:
        return metadata.version("pyflightstream")
    except metadata.PackageNotFoundError:
        return "0.0.0+uninstalled"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _set_path(raw: dict[str, Any], dotted: str, value: Any) -> None:
    """Set ``component.key.key`` of the raw ``components`` table, refusing an unknown component."""
    parts = dotted.split(".")
    components = raw.get("components")
    if len(parts) < 2 or not isinstance(components, dict) or parts[0] not in components:
        known = sorted(components) if isinstance(components, dict) else []
        raise InputValueError(
            f"overrides: {dotted!r} must be <component>.<key>[.<key>] of a declared component "
            f"(declared: {known})"
        )
    node = components[parts[0]]
    for part in parts[1:-1]:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise InputValueError(f"overrides: {dotted!r}: {part!r} is not a table")
    node[parts[-1]] = value


def _reported_unknown(warnings: Sequence[Any], dotted: str) -> bool:
    """Whether the resolver warned that ``dotted``, or a table on its path, is an unknown key.

    A published key is translated to the resolver's names, so whether it is known cannot be read
    from the resolved names; the resolver's own unknown-key warning on the key or on any table
    above it is what says the override was skipped.
    """
    parts = dotted.split(".")
    prefixes = [".".join(parts[:n]) for n in range(2, len(parts) + 1)]
    return any(
        re.search(rf"(?:^|\s)(?:components\.)?{re.escape(prefix)}: unknown key", str(w))
        for prefix in prefixes
        for w in warnings
    )


def _resolve(config, overrides):
    """Return the resolved configuration of a path or mapping with ``overrides`` applied."""
    if isinstance(config, (str, Path)):
        path = Path(config)
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
        stem, base = path.stem, path.parent
    else:
        raw, stem, base = copy.deepcopy(dict(config)), None, None
    if overrides and raw.get("format") == "pyflightstream-geometry-resolved":
        raise InputValueError("overrides: give a path or a raw configuration, not a resolved one")
    if overrides:
        # a [surface] or [body] file is one component named by its table: overrides address it
        raw = adopt_surface_file(raw)
    for dotted, value in (overrides or {}).items():
        _set_path(raw, dotted, value)
    resolved = resolve_config(raw, stem=stem, base=base)
    for dotted in overrides or {}:
        if _reported_unknown(resolved["warnings"], dotted):
            raise InputValueError(f"overrides: {dotted!r}: unknown parameter, nothing was run")
    return resolved


def _members(resolved, configuration, variant):
    configurations = resolved["configurations"]
    if configuration is None:
        members = list(resolved["components"])
    elif configuration not in configurations:
        raise InputValueError(
            f"configuration {configuration!r}: unknown; available: {sorted(configurations)}"
        )
    else:
        members = list(configurations[configuration])
    if variant not in unpack(resolved["variants"]):
        raise InputValueError(
            f"variant {variant!r}: unknown; available: {sorted(unpack(resolved['variants']))}"
        )
    if configuration is not None:
        allowed = unpack(resolved["registry"])[configuration]["variants"]
        if variant not in allowed:
            raise InputValueError(
                f"configuration {configuration!r}: variant {variant!r} is excluded; "
                f"available: {allowed}"
            )
    return members


def _leaves(node: Any, path: str) -> Iterator[dict[str, Any]]:
    """Yield ``{path, value, unit, source}`` for every wrapped value under ``node``."""
    if isinstance(node, dict) and {"value", "unit", "source"} <= set(node):
        yield {"path": path, **node}
    elif isinstance(node, dict):
        for key, child in node.items():
            yield from _leaves(child, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from _leaves(child, f"{path}[{index}]")


def describe_config(config: Any, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Resolve a configuration (S0 only) and return every value with its unit and source.

    Parameters
    ----------
    config : Mapping or str or Path
        A configuration, or the path of a TOML file.
    overrides : Mapping, optional
        Values to set before resolving, by dotted path.

    Returns
    -------
    dict
        ``status``, the ``parameter_id``, the ``values`` with unit and source, and the
        ``warnings`` and ``findings`` of the resolution.

    Examples
    --------
    >>> from pyflightstream.workspace.geometry_pipeline import describe_config
    >>> describe_config({"type": "lifting_surface"})["status"]
    'valid'
    """
    resolved = _resolve(config, overrides)
    values = [
        leaf
        for section in ("aircraft", "acceptance", "reader", "components")
        for leaf in _leaves(resolved[section], section)
    ]
    return {
        "status": "valid",
        "parameter_id": parameter_id(resolved),
        "values": values,
        "warnings": list(resolved["warnings"]),
        "findings": list(resolved["findings"]),
    }


def list_configurations(config: Any) -> dict[str, Any]:
    """Return the configurations of a configuration file with their members and variants.

    Parameters
    ----------
    config : Mapping or str or Path
        A configuration, or the path of a TOML file.

    Returns
    -------
    dict
        The ``components``, the ``variants`` and, per configuration, its ``members``.

    Examples
    --------
    >>> from pyflightstream.workspace.geometry_pipeline import list_configurations
    >>> list_configurations({"type": "lifting_surface"})["components"]
    ['COMPONENT']
    """
    resolved = unpack(dict(_resolve(config, None)))
    return {
        "components": list(resolved["components"]),
        "variants": sorted(resolved["variants"]),
        "configurations": {
            name: {"members": members, "variants": resolved["registry"][name].get("variants")}
            for name, members in resolved["configurations"].items()
        },
    }


def built_stages() -> set[str]:
    """Return the ids of the stages this tree has a function for.

    Returns
    -------
    set of str
        The stage ids that run; the other stages of the table are reported as not measured.

    Examples
    --------
    >>> from pyflightstream.workspace.geometry_pipeline import built_stages
    >>> "S0" in built_stages()
    True
    """
    return set(STAGE_FUNCTIONS)


#: The note of a check of the stage table that a built stage did not return.
_OMITTED = "not measured by this stage in this tree"


def _skipped(row: StageRow) -> StageOutcome:
    note = "stage not built in this tree"
    return StageOutcome(
        checks=[check_entry(cid, "skipped", note=note) for cid, _ in row.checks],
        warnings=[f"{row.stage} {row.name}: {note}"],
    )


def _with_table_checks(row: StageRow, outcome: StageOutcome) -> list[dict[str, Any]]:
    """Return the stage's checks plus a ``skipped`` entry for each check of its row it omitted."""
    given = {check["id"] for check in outcome.checks}
    missing = [
        check_entry(cid, "skipped", note=_OMITTED) for cid, _ in row.checks if cid not in given
    ]
    return [*outcome.checks, *missing]


def _not_measured(record: Mapping[str, Any], built: bool) -> list[str]:
    """Return ``"<stage> <check>"`` for each check of a record the stage did not measure.

    Every check of a stage that is not built, and each check a built stage omitted; a check a
    built stage itself reports skipped (it does not apply, with its reason) is not listed.
    """
    return [
        f"{record['stage']} {check['id']}"
        for check in record["checks"]
        if check["status"] == "skipped"
        and (not built or check["note"] == _OMITTED or check["note"].startswith("waiting for "))
    ]


def _refused(message, *, parameter="", stage="S0", check="input.valid"):
    return geometry_report("refused", parameter or None, stage=stage, check=check, message=message)


def _first_failure(checks):
    return next((c for c in checks if c["status"] == "failed"), None)


def run_geometry(
    config: Any,
    *,
    out: str | Path,
    configuration: str | None = None,
    variant: str = "clean",
    overrides: Mapping[str, Any] | None = None,
    until: str = "S13",
    stages: Sequence[Stage] | None = None,
) -> dict[str, Any]:
    """Run the stages S0 to ``until`` and return the report; it stops at the first failed check.

    Parameters
    ----------
    config : path or mapping
        A configuration file or its raw mapping.
    out : path
        The folder the stage records (``S<n>.json``), the report (``report.json``) and the files
        of the export stage are written to.
    configuration, variant : str
        The entry of the configuration registry to build, and the variant of it.
    overrides : mapping, optional
        ``{"main.planform.sref_m2": 12.0}``: component, then key path. A name no component holds is
        refused and nothing runs.
    until : str
        The last stage to run, ``S0`` to ``S13``. A run to ``S9`` needs no kernel.
    stages : sequence of Stage, optional
        The stages to run, for a caller that replaces one; the stages of this tree by default.

    Returns
    -------
    dict
        The report: ``status`` accepted (every check of the stages run was measured and none
        failed), incomplete (none failed, and ``not_run`` names each check of the stage table
        that was not measured), failed (its ``stage``, ``check``, ``measured`` and ``limit``
        name the first failed check) or refused (the input, or the kernel, is not usable).
        Never raised for a failed or a refused run.
    """
    last = stage_index(until)
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    clock = time.perf_counter()
    log = RunLog(folder)
    log.start(
        config=str(config) if isinstance(config, (str, Path)) else "(mapping given in memory)",
        package_version=_package_version(),
        configuration=configuration,
        variant=variant,
        until=until,
        started=_now(),
        overrides=overrides,
    )
    planned = list(stages if stages is not None else default_stages())[: last + 1]
    try:
        resolved = _resolve(config, overrides)
        members = _members(resolved, configuration, variant)
    except (PyflightstreamError, ValueError, OSError, tomllib.TOMLDecodeError) as error:
        later = [f"{s.row.stage} {s.row.name}" for s in planned[1:]]
        return _refuse(folder, log, clock, later, _refused(str(error)))
    parameter = parameter_id(resolved)
    log.note(f"parameter id: {parameter}")
    context = RunContext(resolved, configuration, variant, folder, parameter, members)
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    not_run: list[str] = []
    for position, stage in enumerate(planned):
        began = _now()
        ticked = time.perf_counter()
        later = [f"{s.row.stage} {s.row.name}" for s in planned[position + 1 :]]
        try:
            outcome = stage.run(context) if stage.run else _skipped(stage.row)
        except MissingExtraError as error:
            report = _refused(
                str(error), parameter=parameter, stage=stage.row.stage, check="kernel"
            )
            return _refuse(folder, log, clock, later, report)
        except InputValueError as error:
            # An input a stage cannot build is refused, not failed: nothing was measured.
            report = _refused(str(error), parameter=parameter, stage=stage.row.stage, check="input")
            return _refuse(folder, log, clock, later, report)
        except (PyflightstreamError, ValueError, OSError) as error:
            outcome = StageOutcome(
                checks=[check_entry("stage.raised", "failed", 1, 0, note=str(error))]
            )
        record = stage_record(
            stage.row.stage,
            stage.row.name,
            package_version=_package_version(),
            inputs_id=parameter,
            parameter_id=parameter,
            checks=_with_table_checks(stage.row, outcome),
            findings=outcome.findings,
            warnings=outcome.warnings,
            outputs=outcome.outputs,
            started=began,
            wall_s=round(
                outcome.wall_s if outcome.wall_s is not None else time.perf_counter() - ticked, 3
            ),
        )
        write_record(folder / f"{stage.row.stage}.json", record)
        log.stage(record)
        records.append(record)
        warnings.extend(outcome.warnings)
        not_run.extend(_not_measured(record, stage.run is not None))
        failed = _first_failure(record["checks"])
        if failed is not None:
            report = _finish(
                "failed",
                parameter,
                folder,
                records,
                warnings=warnings,
                failure=(stage.row, failed),
                not_run=not_run,
            )
            log.finish(report, later, time.perf_counter() - clock)
            return report
    status = "incomplete" if not_run else "accepted"
    report = _finish(
        status, parameter, folder, records, warnings=warnings, failure=None, not_run=not_run
    )
    log.finish(report, [], time.perf_counter() - clock)
    return report


def _refuse(folder: Path, log: RunLog, clock: float, later: list[str], report: dict[str, Any]):
    """Write the report and the end of the log of a refused run, and return the report."""
    write_record(folder / "report.json", report)
    log.finish(report, later, time.perf_counter() - clock)
    return report


def _finish(status, parameter, folder, records, *, warnings, failure, not_run):
    row, failed = failure or (None, None)
    summary = [
        {
            "stage": r["stage"],
            "name": r["name"],
            "status": r["status"],
            "record": f"{r['stage']}.json",
        }
        for r in records
    ]
    outputs = {k: v for r in records for k, v in r["outputs"].items()}
    report = geometry_report(
        status,
        parameter,
        surface_id=outputs.get("surface_id"),
        build_id=outputs.get("build_id"),
        stage=row.stage if row else None,
        check=failed["id"] if failed else None,
        message=failed["note"] if failed else "",
        measured=failed["measured"] if failed else None,
        limit=failed["limit"] if failed else None,
        where=failed["where"] if failed else None,
        stages=summary,
        outputs=outputs,
        warnings=warnings,
        not_run=not_run,
    )
    write_record(folder / "report.json", report)
    return report


def run_set(
    config: Any,
    out: str | Path,
    *,
    overrides: Mapping[str, Any] | None = None,
    configuration: str | None = None,
    variant: str = "clean",
    until: str = "S13",
) -> dict[str, Any]:
    """Run one parameter set and return its report; ``out`` is its report file."""
    return run_geometry(
        config,
        out=Path(out).parent,
        configuration=configuration,
        variant=variant,
        overrides=overrides,
        until=until,
    )


def _one_set(job):
    """Run one parameter set of :func:`run_doe` in a worker; ``job`` is its index and arguments."""
    index, params, common = job
    arguments = {
        **common,
        "out": str(Path(common["out"]) / f"set-{index + 1:04d}" / "report.json"),
        "overrides": dict(params),
    }
    # A report or a log left by an earlier run in this set folder would be read as this run's
    # when the worker dies before writing its own: neither survives the start of the set.
    for stale in ("report.json", LOG_NAME):
        (Path(arguments["out"]).parent / stale).unlink(missing_ok=True)
    try:
        return run_isolated(f"{__name__}:run_set", arguments, run_set)
    except Exception as error:  # a worker fault must end this set only
        report = geometry_report(
            "failed",
            None,
            stage="worker",
            check="worker.completed",
            message=f"{type(error).__name__}: {error}",
        )
        return _record_worker_fault(Path(arguments["out"]).parent, arguments, report)


def _record_worker_fault(folder: Path, arguments: Mapping[str, Any], report: dict[str, Any]):
    """Leave a report and a log in the set folder of a set whose worker died; return the report."""
    clock = time.perf_counter()
    folder.mkdir(parents=True, exist_ok=True)
    log = RunLog(folder)
    if not log.path.exists():
        config = arguments["config"]
        log.start(
            config=config if isinstance(config, str) else "(mapping given in memory)",
            package_version=_package_version(),
            configuration=arguments["configuration"],
            variant=arguments["variant"],
            until=arguments["until"],
            started=_now(),
            overrides=arguments["overrides"],
        )
    if not (folder / "report.json").exists():
        write_record(folder / "report.json", report)
    log.finish(report, [], time.perf_counter() - clock)
    return report


def run_doe(
    config: Any,
    parameter_sets: Sequence[Mapping[str, Any]],
    *,
    out: str | Path,
    configuration: str | None = None,
    variant: str = "clean",
    until: str = "S13",
    workers: int = 1,
) -> Iterator[dict[str, Any]]:
    """Yield one report per parameter set, in order; a failed or refused set never stops the loop.

    Each set runs in a worker process of its own (the kernel can fault natively) and writes
    to ``out/set-0001``, ``out/set-0002`` and so on. A set whose worker dies is reported
    ``failed`` at stage ``worker``.

    Parameters
    ----------
    config : Mapping or str or Path
        A configuration, or the path of a TOML file.
    parameter_sets : sequence of Mapping
        One table of overrides per set, by dotted path.
    out : str or Path
        The folder that receives one sub-folder per set.
    configuration : str, optional
        The configuration to build, for a file that holds several.
    variant : str, optional
        The variant to build; ``"clean"`` by default.
    until : str, optional
        The last stage to run; ``"S13"`` by default.
    workers : int, optional
        The number of sets run at once; 1 runs them in order.

    Yields
    ------
    dict
        The report of each set, as :func:`pyflightstream.geometry.stages.geometry_report`.

    Raises
    ------
    InputValueError
        If ``workers`` is below 1 or ``until`` is not a stage id.

    Examples
    --------
    >>> from pyflightstream.workspace.geometry_pipeline import run_doe
    >>> next(run_doe({}, [], out="doe", workers=0))
    Traceback (most recent call last):
    ...
    pyflightstream._errors.InputValueError: workers: at least 1 required
    """
    if workers < 1:
        raise InputValueError("workers: at least 1 required")
    stage_index(until)
    common = {
        "config": config if isinstance(config, Mapping) else str(config),
        "out": str(out),
        "configuration": configuration,
        "variant": variant,
        "until": until,
    }
    jobs = [(i, params, common) for i, params in enumerate(parameter_sets)]
    if workers == 1:
        for job in jobs:
            yield _one_set(job)
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(_one_set, jobs)


def _not_built(what: str) -> InputValueError:
    return InputValueError(f"{what}: not built yet in this tree; nothing was written")


def add_control_surfaces(
    iges: str | Path, component: str, entries: Sequence[Mapping[str, Any]], out: str | Path
) -> dict[str, Any]:
    """Add control surfaces to a component of an IGES file (PFS-2215); not built yet.

    Parameters
    ----------
    iges : str or Path
        The IGES file to read.
    component : str
        The component that carries the control surfaces.
    entries : sequence of Mapping
        One table per control surface, with the keys of a ``[[control]]`` entry.
    out : str or Path
        The IGES file to write.

    Returns
    -------
    dict
        The record of the edit, once built.

    Raises
    ------
    InputValueError
        Always for now: the verb is not built in this tree and writes nothing.

    Examples
    --------
    >>> from pyflightstream.workspace.geometry_pipeline import add_control_surfaces
    >>> add_control_surfaces("a.igs", "WING", [], "b.igs")  # doctest: +ELLIPSIS
    Traceback (most recent call last):
    ...
    pyflightstream._errors.InputValueError: add_control_surfaces: not built yet ...
    """
    raise _not_built("add_control_surfaces")


def split_symmetry(
    iges: str | Path, out: str | Path, *, plane: str = "y", component: str | None = None
) -> dict[str, Any]:
    """Cut a full model at its symmetry plane and write the half model (C8); not built yet.

    The faces that cross the plane are to be trimmed exactly on it and the plane edges left
    open and marked as symmetry. The geometry belongs to another lane of the release.

    Parameters
    ----------
    iges : str or Path
        The full model to read.
    out : str or Path
        The half model to write.
    plane : str, optional
        The symmetry plane, ``"x"``, ``"y"`` (default) or ``"z"``.
    component : str, optional
        The component to cut; None cuts every one.

    Returns
    -------
    dict
        The record of the cut, once built.

    Raises
    ------
    InputValueError
        If ``plane`` is not ``x``, ``y`` or ``z``, and always for now otherwise: the verb is
        not built in this tree and writes nothing.

    Examples
    --------
    >>> from pyflightstream.workspace.geometry_pipeline import split_symmetry
    >>> split_symmetry("a.igs", "b.igs", plane="w")
    Traceback (most recent call last):
    ...
    pyflightstream._errors.InputValueError: plane: one of x, y, z required, got 'w'
    """
    if plane not in ("x", "y", "z"):
        raise InputValueError(f"plane: one of x, y, z required, got {plane!r}")
    raise _not_built("split_symmetry")
