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
    StageRow,
    adopt_surface_file,
    check_entry,
    geometry_report,
    parameter_id,
    stage_index,
    stage_record,
    unpack,
    write_record,
)
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
    """What one stage returns: its checks, findings, warnings and the files it wrote."""

    checks: list[dict[str, Any]] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)


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
    from pyflightstream.workspace._geometry_generate import generate_iges

    written = generate_iges(config, path, configuration=configuration)
    return json.loads(json.dumps(written, default=str))


def _export(context: RunContext) -> StageOutcome:
    """S11: the exposed skin of the selected members as one named IGES, read by the profile gate."""
    name = context.configuration or str(
        unpack(context.resolved["aircraft"]).get("name", "geometry")
    )
    target = context.out / f"{name}.igs"
    try:
        written = _generate(context.resolved, target, context.configuration)
    except InputArtifactError as error:
        if "solid entities" not in str(error):
            raise
        return StageOutcome(
            checks=[check_entry("profile.surfaces_only", "failed", 1, 0, note=str(error))]
        )
    warnings = [
        str(item) for item in written["warnings"] if item not in context.resolved["warnings"]
    ]
    if context.variant != "clean":
        warnings.append(f"variant {context.variant}: not applied by the export stage in this tree")
    return StageOutcome(
        checks=[check_entry("profile.surfaces_only", "passed", 0, 0, unit="solid entities")],
        warnings=warnings,
        outputs={"iges": str(target), "faces": written["faces"], "audit": written["audit"]},
    )


#: The stage functions of this tree, by stage id. A stage not named here is recorded skipped.
STAGE_FUNCTIONS: dict[str, StageFn] = {"S0": _definition, "S11": _export}


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
    """Resolve a configuration (S0 only) and return every value with its unit and source."""
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
    """Return the configurations of a configuration file with their members and variants."""
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
    """Return the ids of the stages this tree has a function for."""
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
        if check["status"] == "skipped" and (not built or check["note"] == _OMITTED)
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
    try:
        resolved = _resolve(config, overrides)
        members = _members(resolved, configuration, variant)
    except (PyflightstreamError, ValueError, OSError, tomllib.TOMLDecodeError) as error:
        return _refused(str(error))
    parameter = parameter_id(resolved)
    folder.mkdir(parents=True, exist_ok=True)
    context = RunContext(resolved, configuration, variant, folder, parameter, members)
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    not_run: list[str] = []
    for stage in list(stages if stages is not None else default_stages())[: last + 1]:
        began = _now()
        try:
            outcome = stage.run(context) if stage.run else _skipped(stage.row)
        except MissingExtraError as error:
            return _refused(str(error), parameter=parameter, stage=stage.row.stage, check="kernel")
        except InputValueError as error:
            # An input a stage cannot build is refused, not failed: nothing was measured.
            return _refused(str(error), parameter=parameter, stage=stage.row.stage, check="input")
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
        )
        write_record(folder / f"{stage.row.stage}.json", record)
        records.append(record)
        warnings.extend(outcome.warnings)
        not_run.extend(_not_measured(record, stage.run is not None))
        failed = _first_failure(record["checks"])
        if failed is not None:
            return _finish(
                "failed",
                parameter,
                folder,
                records,
                warnings=warnings,
                failure=(stage.row, failed),
                not_run=not_run,
            )
    status = "incomplete" if not_run else "accepted"
    return _finish(
        status, parameter, folder, records, warnings=warnings, failure=None, not_run=not_run
    )


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
    report = geometry_report(
        status,
        parameter,
        stage=row.stage if row else None,
        check=failed["id"] if failed else None,
        message=failed["note"] if failed else "",
        measured=failed["measured"] if failed else None,
        limit=failed["limit"] if failed else None,
        where=failed["where"] if failed else None,
        stages=summary,
        outputs={k: v for r in records for k, v in r["outputs"].items()},
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
    try:
        return run_isolated(f"{__name__}:run_set", arguments, run_set)
    except Exception as error:  # a worker fault must end this set only
        return geometry_report(
            "failed",
            None,
            stage="worker",
            check="worker.completed",
            message=f"{type(error).__name__}: {error}",
        )


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
    """Add control surfaces to a component of an IGES file (PFS-2215); not built yet."""
    raise _not_built("add_control_surfaces")


def split_symmetry(
    iges: str | Path, out: str | Path, *, plane: str = "y", component: str | None = None
) -> dict[str, Any]:
    """Cut a full model at its symmetry plane and write the half model (C8); not built yet.

    The faces that cross the plane are to be trimmed exactly on it and the plane edges left
    open and marked as symmetry. The geometry belongs to another lane of the release.
    """
    if plane not in ("x", "y", "z"):
        raise InputValueError(f"plane: one of x, y, z required, got {plane!r}")
    raise _not_built("split_symmetry")
