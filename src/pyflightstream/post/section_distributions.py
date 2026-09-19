"""Sectional loads and chordwise Cp, one table per recorded pproc distribution."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import PprocSpec, select_group_members
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
    inventory = list(
        dict.fromkeys(str(f) for b in layout for f in cast(list[str], b.get("families", [])))
    )
    for block in layout:
        count = block.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ProductError("sections_layout has an invalid section count")
        position = block.get("distribution")
        selection = block.get("distribution_families")
        if position is None and pproc is not None:
            matches = []
            for k, entry in enumerate(pproc.sections.distributions, 1):
                tokens = [entry.families] if isinstance(entry.families, str) else entry.families
                members = select_group_members(tokens, inventory, record.aliases)
                families = cast(list[str], block.get("families", []))
                frame = entry.frame.strip().upper()
                recorded_frame = str(block.get("frame", ""))
                expanded = {
                    "LOCAL_AXIS": r".+_RMRP[1-9][0-9]*",
                    "RMRP": r".+_RMRP",
                    "SMRP": r".+_SMRP(?:_ORIGINAL)?",
                }.get(frame)
                frame_matches = (
                    re.fullmatch(expanded, recorded_frame) is not None
                    if expanded is not None
                    else recorded_frame == entry.frame
                )
                if (
                    families
                    and set(families) <= set(members)
                    and block.get("plane") in entry.planes
                    and count == (entry.count or pproc.sections.count)
                    and frame_matches
                ):
                    matches.append((k, entry.families))
            if len(matches) == 1:
                position, selection = matches[0]
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
    condition: Mapping[str, object] | None = None,
    reference: Mapping[str, object] | None = None,
    rotors: Mapping[str, Mapping[str, object]] | None = None,
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write both distribution products from all stamps, or the end-of-run exports.

    A bad or missing export skips its kind by name without costing the other
    kind. Layout counts must cover every section before any split is written.
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
        return [], {}
    names = _file_names(selections)
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
            done = write_csv_table(
                target(out / relative), (*SECTIONS_SERIES_LEAD, *CONTEXT_COLUMNS, *columns), rows[k]
            )
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
