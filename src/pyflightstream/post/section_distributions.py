"""Sectional loads and chordwise Cp, one table per recorded pproc distribution."""

from __future__ import annotations

import math
import re
import warnings
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import cast

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream._tokens import INTEGRATED_SECTION_COLUMNS
from pyflightstream.cases import PprocSpec, RotorBlock, SimCase, select_families
from pyflightstream.cases.workflows import pproc_emissions
from pyflightstream.fsi.loads import parse_sectional_loads
from pyflightstream.post._tables import (
    CONTEXT_COLUMNS,
    ProductError,
    context_row,
    section_identity,
    write_csv_table,
)
from pyflightstream.post.series import SECTIONS_SERIES_LEAD, run_clock, stamped_exports
from pyflightstream.results import labeled_value, parse_surface_sections
from pyflightstream.workspace import RunRecord

__all__ = ["write_section_distributions"]


def _integrated_strips(values: list[list[float]]) -> list[tuple[float, ...]]:
    """Integrate one instant/block in its export axes about each quarter chord.

    Strip edges are the endpoint stations and the intervening midpoints.
    Positive lengths tile only the interval between the first and last Offset.
    Forces are N/m and Moment is N m/m; the added columns are m, N, N, N m.
    """
    if len(values) < 2:
        raise ProductError("integration needs at least two stations in each block")
    if not all(math.isfinite(value) for row in values for value in row):
        raise ProductError("integration needs finite sectional values (NaN or infinity found)")
    gaps = [b[0] - a[0] for a, b in zip(values[:-1], values[1:], strict=True)]
    if not (all(gap > 0 for gap in gaps) or all(gap < 0 for gap in gaps)):
        raise ProductError("integration needs strictly monotonic Offset in each block")
    halves = [abs(gap) / 2 for gap in gaps]
    lengths = [
        halves[0],
        *(a + b for a, b in zip(halves[:-1], halves[1:], strict=True)),
        halves[-1],
    ]
    result = [
        (length, *(row[i] * length for i in (4, 5, 6)))
        for row, length in zip(values, lengths, strict=True)
    ]
    if not all(math.isfinite(value) for row in result for value in row):
        raise ProductError("integration produced a non-finite length or load")
    return result


def _distributions(
    record: RunRecord, pproc: PprocSpec | None
) -> tuple[list[dict[str, object]], dict[int, str | list[str]]]:
    """Resolve block ownership, refusing ambiguous pre-0.25.0 layouts."""
    if not record.sections_layout:
        raise ProductError(
            "distribution split needs the recorded sections_layout; never guessed. "
            "A new run is needed to record the missing layout."
        )
    layout = [dict(block) for block in record.sections_layout]
    selections: dict[int, str | list[str]] = {}
    for block in layout:
        families = block.get("families")
        if not isinstance(families, list) or not all(isinstance(f, str) for f in families):
            raise ProductError("sections_layout has an invalid families list")
    for block in layout:
        count = block.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ProductError("sections_layout has an invalid section count")
        position = block.get("distribution")
        selection = block.get("distribution_families")
        if position is None and pproc is not None:
            matches = _matching_distributions(record, pproc, block)
            if len(matches) == 1:
                position = matches[0]
                selection = pproc.sections.distributions[position - 1].families
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or position < 1
            or not isinstance(selection, str | list)
            or not selection
            or (isinstance(selection, list) and not all(isinstance(s, str) for s in selection))
        ):
            raise ProductError(
                "sections_layout does not identify each pproc distribution unambiguously; "
                "split needs recorded distribution positions/families "
                "or a uniquely matching pproc. "
                "Restore the matching pproc, or a new run is needed "
                "to record distribution identity."
            )
        if position in selections and selections[position] != selection:
            raise ProductError(f"sections_layout disagrees on families of distribution {position}")
        selections[position] = selection
        block["distribution"] = position
    if pproc is not None:
        for k, entry in enumerate(pproc.sections.distributions, 1):
            selections.setdefault(k, entry.families)
    return layout, selections


def _matching_distributions(
    record: RunRecord,
    pproc: PprocSpec,
    block: Mapping[str, object],
    aliases: Mapping[str, Sequence[str]] | None = None,
    rotors: Mapping[str, RotorBlock] | None = None,
) -> list[int]:
    """Match current entries to recorded geometry, never to mutable positions."""
    inventory = list(
        dict.fromkeys(
            str(f) for b in record.sections_layout or [] for f in cast(list[str], b["families"])
        )
    )
    matches = []
    for k, entry in enumerate(pproc.sections.distributions, 1):
        families = cast(list[str], block["families"])
        if rotors:
            # Use the export builder's grouping and rotor vocabulary, including
            # aliases of rotor names and one emission per blade in LOCAL_AXIS.
            case = SimCase.model_construct(
                sim_id=record.sim_id,
                aliases=dict(record.aliases if aliases is None else aliases),
                rotors=dict(rotors),
                pproc=pproc,
            )
            frames = {str(b.get("frame", "")): 1 for b in record.sections_layout or []}
            try:
                emissions = pproc_emissions(
                    case,
                    entry.frame,
                    entry.families,
                    inventory,
                    pproc.is_blade,
                    f"section distribution {k}",
                    frames,
                    blades_only=True,
                )
            except PyflightstreamError:
                # An invalid current selector cannot cost recorded raw columns.
                emissions = []
            if (
                any(
                    frame == block.get("frame", "") and set(families) == set(members or inventory)
                    for frame, members, _ in emissions
                )
                and block.get("plane") in entry.planes
                and block["count"] == (entry.count or pproc.sections.count)
            ):
                matches.append(k)
            continue
        expanded_families = select_families(
            entry.families,
            inventory,
            pproc.is_blade,
            record.aliases if aliases is None else aliases,
        )
        expanded = {
            "LOCAL_AXIS": r".+_RMRP[1-9][0-9]*",
            "RMRP": r".+_RMRP",
            "SMRP": r".+_SMRP(?:_ORIGINAL)?",
        }.get(entry.frame.strip().upper())
        frame_matches = (
            re.fullmatch(expanded, str(block.get("frame", ""))) is not None
            if expanded is not None
            else block.get("frame", "") == entry.frame
        )
        # No rotor definition reaches this path, so it cannot rebuild the export
        # builder's grouping. On an EXPANDING frame the builder emits one block
        # per rotor or per blade, each a subset of the entry's selection, so a
        # recorded block that lies inside the selection is one of them; on a
        # common frame the builder emits ONE block over the whole selection,
        # so only the equal set is that block.
        owned = (
            (lambda block_set, members: block_set <= members)
            if expanded is not None
            else (lambda block_set, members: block_set == members)
        )
        if (
            families
            and any(
                owned(set(families), set(members or inventory)) for members in expanded_families
            )
            and block.get("plane") in entry.planes
            and block["count"] == (entry.count or pproc.sections.count)
            and frame_matches
        ):
            matches.append(k)
    return matches


def _integration_requests(
    record: RunRecord,
    pproc: PprocSpec | None,
    layout: list[dict[str, object]],
    aliases: Mapping[str, Sequence[str]] | None = None,
    rotors: Mapping[str, RotorBlock] | None = None,
) -> tuple[set[int], dict[int, str]]:
    """Bind integration to recorded owners; a doubtful block keeps its file raw."""
    requested: set[int] = set()
    errors: dict[int, str] = {}
    disabled: dict[int, str] = {}
    if pproc is None or not any(entry.integrate for entry in pproc.sections.distributions):
        return requested, errors
    for number, block in enumerate(layout, 1):
        owner = cast(int, block["distribution"])
        matches = _matching_distributions(record, pproc, block, aliases, rotors)
        if len(matches) != 1:
            reason = "ambiguous" if matches else "missing"
            errors[owner] = (
                f"block {number}: {reason} pproc match by families, plane, frame and count; "
                "restore one uniquely matching distribution to integrate this file"
            )
        elif pproc.sections.distributions[matches[0] - 1].integrate:
            requested.add(owner)
        else:
            # All blocks in one CSV must carry the same columns.
            disabled[owner] = (
                f"block {number}: matching pproc distribution has integrate=false; "
                "set integrate=true on every matching block to integrate this file"
            )
    for owner in requested & disabled.keys():
        errors.setdefault(owner, disabled[owner])
    return requested, errors


def _file_names(selections: Mapping[int, str | list[str]]) -> dict[int, str]:
    """Sanitize and disambiguate names, including collisions with generated suffixes."""
    names = {
        k: re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s if isinstance(s, str) else "-".join(s)).rstrip(
            " ."
        )
        or "distribution"
        for k, s in selections.items()
    }
    while True:
        counts = Counter(name.casefold() for name in names.values())
        clashes = {k for k, name in names.items() if counts[name.casefold()] > 1}
        if not clashes:
            return names
        names = {k: f"{name}_{k}" if k in clashes else name for k, name in names.items()}


def write_section_distributions(
    *,
    sim_dir: Path,
    record: RunRecord,
    stem: str,
    out: Path,
    target: Callable[[Path], Path],
    skipped: dict[str, str],
    step: int | None,
    pproc: PprocSpec | None = None,
    current_pproc: PprocSpec | None = None,
    current_aliases: Mapping[str, Sequence[str]] | None = None,
    current_rotors: Mapping[str, RotorBlock] | None = None,
    integration_error: str | None = None,
    condition: Mapping[str, object] | None = None,
    reference: Mapping[str, object] | None = None,
    rotors: Mapping[str, Mapping[str, object]] | None = None,
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write both distribution products from all stamps, or the end-of-run exports.

    A bad or missing export skips its kind by name without costing the other
    kind. Layout counts must cover every section before any split is written.

    Parameters
    ----------
    sim_dir : Path
        Simulation directory containing the recorded exports.
    record : RunRecord
        Run metadata, including outputs, section layout and export clock.
    stem : str
        Point's export filename stem.
    out : Path
        Root directory for the products.
    target : callable
        Prepare a destination path, applying the caller's archive policy.
    skipped : dict[str, str]
        Mutable mapping of product names to skip reasons.
    step : int or None
        End-of-run STEP when there are no stamped exports. On an unsteady
        run this is the solver's 1-based time step, never the export header's
        inner-iteration counter; stamps supply their own time steps. On a
        steady run it is the exported solver iteration. Unknown values are
        written as ``NA``. See `The sections table, and which row is which
        <../post-processing-definitions.md#the-sections-table-and-which-row-is-which>`_.
    pproc : PprocSpec or None, optional
        Recorded post-processing specification used to resolve legacy distribution
        ownership. Also selects strip integrals when current_pproc is omitted.
        See `Per-distribution sectional loads and Cp
        <../post-processing-definitions.md#per-distribution-sectional-loads-and-cp-0250>`_.
    current_pproc : PprocSpec or None, optional
        Effective post specification selecting integration against recorded blocks.
    current_aliases : Mapping[str, Sequence[str]] or None, optional
        Live reference aliases for integration selections. Recorded aliases remain
        the fallback when no live reference is available and own legacy layouts.
    current_rotors : Mapping[str, RotorBlock] or None, optional
        Live rotor definitions for the export builder's family and frame expansion.
    integration_error : str or None, optional
        Unresolved effective specification; retain raw files and name integration skips.
    condition : Mapping[str, object] or None, optional
        Point's condition, with case-insensitive keys: ``ALPHA``, ``BETA``
        (degrees, solver-reported angles in the export frame: x aft, y right,
        z up), ``MACH`` and ``J`` (dimensionless), ``RE`` (millions),
        ``VINF`` and ``VREF`` (m/s), ``ALT`` (ft), ``RHO`` (kg/m3),
        ``TEMP`` (K) and ``MU`` (Pa s). Spellings in
        :data:`pyflightstream.post.products.CONDITION_KEY_ALIASES` are also
        accepted without unit conversion. Missing values are ``NA``. See
        `What every product states
        <../post-processing-definitions.md#what-every-product-states>`_ and
        `The axes of a steady polar
        <../post-processing-definitions.md#the-axes-of-a-steady-polar>`_.
    reference : Mapping[str, object] or None, optional
        Reference dimensions, with case-insensitive keys ``SREF`` (m2),
        ``CREF`` and ``BREF`` (m); missing values are ``NA``. These scalars
        require no frame transformation. See `What every product states
        <../post-processing-definitions.md#what-every-product-states>`_.
    rotors : Mapping[str, Mapping[str, object]] or None, optional
        Rotor alias to metadata: ``families`` is the list of owned geometry
        families, ``blade1_azimuth_deg`` is blade one's datum in degrees in
        that rotor's frame, ``rpm`` is its signed speed in revolutions/minute,
        and ``steps_per_revolution`` is its own clock in time steps/turn.
        They determine ``ROTOR`` and ``AZIMUTH`` at each STEP; missing
        identity or azimuth is ``NA``. Section coordinates and loads retain
        their recorded distribution frame. See `The sections table, and
        which row is which
        <../post-processing-definitions.md#the-sections-table-and-which-row-is-which>`_.

    Returns
    -------
    tuple[list[Path], dict[str, dict[str, object]]]
        Written paths and their product-manifest entries.
    """
    folders = [sim_dir / Path(output).parent for output in record.outputs]
    stamped = stamped_exports(sim_dir, stem, *folders)
    if (
        not record.sections_layout
        and pproc is not None
        and not pproc.sections.distributions
        and not any(Path(o).stem.endswith(("_sloads", "_cp")) for o in record.outputs)
        and not any(suffix in ("_sloads", "_cp") for suffix, _ in stamped)
    ):
        return [], {}  # No requested or recorded sections product applies to this point.
    try:
        layout, selections = _distributions(record, pproc)
    except ProductError as error:
        for kind in ("sloads", "cp"):
            skipped[f"sections/{stem}_{kind}#distributions"] = str(error)
        if pproc is not None and any(entry.integrate for entry in pproc.sections.distributions):
            warnings.warn(
                f"{stem}: ambiguous or missing distribution identity; no integration: {error}",
                PyflightstreamWarning,
                stacklevel=2,
            )
        return [], {}
    names = _file_names(selections)
    integrate, matching_errors = _integration_requests(
        record, current_pproc or pproc, layout, current_aliases, current_rotors
    )
    if integration_error is not None:
        integrate = set()
        matching_errors = dict.fromkeys(selections, integration_error)
    delta, _ = run_clock(record)
    context = context_row(condition, reference)
    written: list[Path] = []
    entries: dict[str, dict[str, object]] = {}
    total = sum(cast(int, block["count"]) for block in layout)
    owners = [cast(int, b["distribution"]) for b in layout for _ in range(cast(int, b["count"]))]
    for kind in ("sloads", "cp"):
        relatives = {k: f"sections/{stem}_{kind}_{name}.csv" for k, name in names.items()}
        files: list[tuple[int | None, Path]]
        if record.export_window:
            files = sorted(stamped.get((f"_{kind}", "txt"), {}).items())
            expected = range(
                int(record.export_window["first_step"]),
                int(record.export_window["time_iterations"]) + 1,
            )
            present = {current for current, _ in files}
            for missing in expected:
                if missing not in present:
                    for relative in relatives.values():
                        skipped[f"{relative}#step={missing}"] = (
                            f"missing {stem}_{kind}_iteration={missing}.txt"
                        )
        else:
            end = next(
                (sim_dir / o for o in record.outputs if Path(o).name == f"{stem}_{kind}.txt"),
                sim_dir / f"{stem}_{kind}.txt",
            )
            files = [(step, end)] if end.is_file() else []
        rows: dict[int, list[tuple[object, ...]]] = {k: [] for k in names}
        integrated: dict[int, list[tuple[float, ...]]] = {k: [] for k in names}
        integration_errors = dict(matching_errors)
        tabled: dict[int, list[int | None]] = {k: [] for k in names}
        try:
            if not files:
                raise ProductError(
                    f"no {stem}_{kind} export found in {sim_dir} or its recorded output folders"
                )
            columns: tuple[str, ...] = ()
            for current, path in files:
                text = path.read_text(encoding="utf-8", errors="replace")
                if current is None and record.recipe not in ("unsteady", "unsteady_rotor"):
                    try:
                        current = int(
                            float(labeled_value(text, "Current solver iteration number:"))
                        )
                    except (PyflightstreamError, ValueError):
                        pass
                samples: list[tuple[int, tuple[object, ...]]] = []
                if kind == "sloads":
                    loads = parse_sectional_loads(text)
                    count = loads.count
                    columns = tuple(loads.columns)
                    samples = [(i, tuple(v)) for i, v in enumerate(loads.values.tolist())]
                else:
                    cp = parse_surface_sections(text)
                    count = cp.count
                    columns = ("SECTION", *cp.columns)
                    samples = [
                        (i, (section.index, *v))
                        for i, section in enumerate(cp.sections)
                        for v in section.values.tolist()
                    ]
                if count != total:
                    raise ProductError(
                        f"{path}: sections_layout counts {total} sections; export holds {count}"
                    )
                if kind == "sloads" and integrate:
                    start = 0
                    for block_number, block in enumerate(layout, 1):
                        owner = cast(int, block["distribution"])
                        block_end = start + cast(int, block["count"])
                        if owner in integrate and owner not in integration_errors:
                            try:
                                integrated[owner].extend(
                                    _integrated_strips(loads.values[start:block_end].tolist())
                                )
                            except ProductError as error:
                                integration_errors[owner] = (
                                    f"{path.name}, STEP {current}, block {block_number}: {error}"
                                )
                        start = block_end
                identity = section_identity(total, layout, rotors, current, None)
                touched: set[int] = set()
                for i, values in samples:
                    owner = owners[i]
                    rows[owner].append(
                        (
                            current,
                            None if current is None or delta is None else current * delta,
                            *identity[i],
                            *context,
                            *values,
                        )
                    )
                    touched.add(owner)
                for k in touched:
                    tabled[k].append(current)
                for k in names.keys() - touched:
                    skipped[f"{relatives[k]}#step={current}"] = (
                        "recorded layout has no blocks for this distribution"
                        if k not in owners
                        else "export has no chordwise stations for this distribution"
                    )
        except (PyflightstreamError, OSError, ValueError) as error:
            for relative in relatives.values():
                skipped[relative] = str(error)
            continue
        for k, relative in relatives.items():
            if not rows[k]:
                skipped[relative] = "recorded layout/export has no rows for this distribution"
                continue
            headings = (*SECTIONS_SERIES_LEAD, *CONTEXT_COLUMNS, *columns)
            output_rows = rows[k]
            if kind == "sloads" and (k in integrate or k in matching_errors):
                if k in integration_errors:
                    skipped[f"{relative}#integration"] = integration_errors[k]
                    warnings.warn(
                        f"{stem}: {relative} written without integrated columns: "
                        f"{integration_errors[k]}",
                        PyflightstreamWarning,
                        stacklevel=2,
                    )
                else:
                    headings = (*headings, *INTEGRATED_SECTION_COLUMNS)
                    output_rows = [
                        (*row, *extra) for row, extra in zip(rows[k], integrated[k], strict=True)
                    ]
            done = write_csv_table(target(out / relative), headings, output_rows)
            written.append(done)
            key = done.relative_to(out) if done.is_relative_to(out) else done
            entries[key.as_posix()] = {
                "runs": [record.run_id],
                "distribution": k,
                "families": selections[k],
                "steps_tabled": tabled[k],
                "kind": "history" if record.export_window else "instant",
            }
    return written, entries
