"""The rotor products of a point: quasi-steady clockings, harmonics, noise and disc maps.

A private module of :mod:`pyflightstream.post` (AD-13, work package WP5 of
0.33.0): the orchestration of the advanced rotor products the post stage of
:mod:`pyflightstream.post.products` writes beside a point's tables. The
arithmetic of each lives in its own public module; what is here decides
which applies to a point, where its file goes and what the manifest says:

* the QUASI-STEADY wheel: the 1P reduced frequency and the validity of each
  section station, the clockings tables and their average, the validity
  cells of the superfile row, and the correction route with its diagnostic
  (:mod:`pyflightstream.post.qsteady`, :mod:`pyflightstream.post.corrections`);
* the per-station HARMONICS of a wheel over its clockings and of an unsteady
  rotor over its last revolution (:mod:`pyflightstream.post.harmonics`), and
  the same rows mapped over the disc (:mod:`pyflightstream.post.disc_maps`);
* the NOISE products of an unsteady rotor's acoustic signals export
  (:mod:`pyflightstream.post.acoustics`).

It also writes the SERIES of one record (:func:`_point_series`): its section
distributions and boundary-layer tables, its stamped per-step series, the
harmonics of an unsteady rotor cut from them, its noise products and its
surface averaged over the window, the per-record half of the campaign stage.

A rotor product of the backlog (a further harmonic, a wake or far-field
product of a rotor) joins this module beside the products it resembles.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import CampaignConfigError, PprocSpec
from pyflightstream.cases.qsteady import QsteadyRecordError, read_qsteady_record
from pyflightstream.cases.workflows import BLADE_FAMILIES_KEY, QSTEADY_ROTOR
from pyflightstream.post import acoustics as _acoustics
from pyflightstream.post import corrections as _corrections
from pyflightstream.post import disc_maps as _disc_maps
from pyflightstream.post import harmonics as _harmonics
from pyflightstream.post import qsteady as _qsteady
from pyflightstream.post._condition import (
    _last_time_step,
    _live_reference,
    _section_rotors,
    clock_rotor_facts,
    point_condition,
    point_state,
    row_rotor_speeds,
)
from pyflightstream.post._stage import (
    POLARS_DIR,
    SECTIONS_DIR,
    _a_name_a_file_may_carry,
    _judge_average,
)
from pyflightstream.post._tables import (
    CONTEXT_COLUMNS,
    ProductError,
    ProductExistsError,
    ReferenceValues,
    read_csv_table,
)
from pyflightstream.post.point_tables import write_sections_table
from pyflightstream.post.polar import PolarPoint
from pyflightstream.post.provenance import refuse_an_existing_product as _refuse_an_existing_product
from pyflightstream.post.rotor_table import rotor_shaft_loads
from pyflightstream.post.section_distributions import write_section_distributions
from pyflightstream.post.series import write_point_series
from pyflightstream.post.surfaces import write_point_surface_average
from pyflightstream.results import FrozenSolve, parse_loads
from pyflightstream.workspace.naming import sweep_file_stem

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow

if TYPE_CHECKING:
    from pyflightstream.workspace import CampaignWorkspace, RunRecord


def _qsteady_sections(
    table: Path,
    point: PolarPoint,
    record: RunRecord | None,
    skipped: dict[str, str],
    tabled: Callable[[Path, str], Path | None],
) -> dict[str, _qsteady.PointValidity]:
    """Complete a quasi-steady wheel point's sections table: its clockings and its 1P frequency.

    Every clocking's rows, each with its ``CLOCKING`` and each blade's own
    ``AZIMUTH`` (0.31.0, :func:`pyflightstream.post.qsteady.add_clockings_to_sections`,
    ``tabled`` writing one clocking's export as this stage writes the point's),
    then the 1P reduced frequency of each station (0.30.0). A clocking whose
    export cannot be tabled is named under the table and the others are
    written; a clocking not cut at clocking 0's stations is warned.

    Returns ``{point name: validity}`` for a wheel point whose sections are the
    rotor's, and nothing for any other point, whose table is left as written.
    """
    if record is None or record.recipe != QSTEADY_ROTOR:
        return {}
    relative = f"{SECTIONS_DIR}/{point.name}_sections.csv"
    try:
        # A record that cannot be read is a named skip of the column (0.31.0),
        # as a quasi-steady point always has one.
        quasi = read_qsteady_record(point.loads_path)
    except QsteadyRecordError as error:
        skipped[f"{relative}#k_1p"] = str(error)
        return {}
    if quasi.case != "wheel":
        return {}
    try:
        clocked = _qsteady.add_clockings_to_sections(
            table, quasi, point.loads_path.parent, tabled=tabled
        )
    except (ProductError, OSError, KeyError, ValueError) as error:
        skipped[f"{relative}#clockings"] = str(error)
    else:
        for clocking, reason in sorted(clocked.missing.items()):
            skipped[f"{relative}#clocking={clocking}"] = reason
        for note in clocked.misaligned:
            warn(
                f"point={point.name} product=sections: {note}", PyflightstreamWarning, stacklevel=2
            )
    try:
        # 0.31.0: the frame each block was cut in, so each station's force is
        # projected on the rotor's axis rather than read in the export's axes.
        validity = _qsteady.add_reduced_frequency_to_sections(
            table,
            quasi,
            velocity_m_per_s=float(point.loads.freestream_velocity_m_s),
            layout=list(getattr(record, "sections_layout", None) or []),
        )
    except (QsteadyRecordError, CampaignConfigError, KeyError, ValueError) as error:
        skipped[f"{SECTIONS_DIR}/{point.name}_sections.csv#k_1p"] = str(error)
        return {}
    if validity is None:
        return {}
    for note in validity.notes:
        warn(f"point={point.name} product=sections: {note}", PyflightstreamWarning, stacklevel=2)
    return {point.name: validity}


def _write_harmonics(
    table: Path,
    *,
    point: str,
    pol: str,
    rotors: Mapping[str, _harmonics.HarmonicRotor],
    sample_column: str,
    source: str,
    windows: Mapping[str, tuple[int, int]] | None,
    out: Path,
    target: Callable[[Path], Path],
    runs: Sequence[str],
    skipped: dict[str, str],
    extra: Mapping[str, object] | None = None,
    disc_maps: list[tuple[Path, dict[str, object]]] | None = None,
) -> tuple[Path, dict[str, object]] | None:
    """Write ``sections/<point>_harmonics.csv`` from a WRITTEN sections table (0.31.0).

    Where ``disc_maps`` is a list (0.32.0), the same rows, cut the same way,
    are also mapped over the disc (:func:`_write_disc_maps`) and each map's
    path and ``products.json`` entry is appended to it.

    ``table`` is the wheel's sections table or the unsteady point's sections
    series, read back as a user holds it; ``windows``, where given, keeps each
    rotor's rows of the steps of its last complete revolution. The condition
    is the table's own, the one its writer assembled. What is not fitted is
    named under the product's key in ``skipped`` and warned in ``post.log``: a
    rotor or a station (``#rotor=<alias>``, ``#rotor=<alias>#station=<j>``),
    and, once per rotor and harmonic, the rows whose harmonic is ``NA`` for
    want of distinct azimuths. Nothing blocks.

    Returns the path written and its ``products.json`` entry, or None where not
    one station could be fitted, which is named under the product's key.
    """
    relative = f"{SECTIONS_DIR}/{point}{_harmonics.HARMONICS_SUFFIX}"
    try:
        columns, rows = read_csv_table(table)
    except (ProductError, OSError) as error:
        skipped[relative] = f"the table {table.name} cannot be read back: {error}"
        warn(
            f"point={point} product={relative}: {skipped[relative]}",
            PyflightstreamWarning,
            stacklevel=2,
        )
        if disc_maps is not None:
            _skip_disc_maps(point, skipped[relative], skipped)
        return None
    if windows is not None:
        rows = [
            row
            for row in rows
            if (window := windows.get(row.get("ROTOR", ""))) is not None
            and (step := _step_of(row.get("STEP"))) is not None
            and window[0] <= step <= window[1]
        ]
    if disc_maps is not None:
        disc_maps.extend(
            _write_disc_maps(
                columns,
                rows,
                rotors,
                sample_column=sample_column,
                point=point,
                pol=pol,
                source=source,
                out=out,
                target=target,
                runs=runs,
                skipped=skipped,
                extra=extra,
            )
        )
    result = _harmonics.station_harmonics(columns, rows, rotors, sample_column=sample_column)
    for marker, reason in result.skipped.items():
        skipped[f"{relative}{marker}"] = reason
        warn(f"point={point} product={relative}: {reason}", PyflightstreamWarning, stacklevel=2)
    for note in result.notes:
        warn(f"point={point} product={relative}: {note}", PyflightstreamWarning, stacklevel=2)
    if not result.rows:
        skipped[relative] = "no station of any rotor could be fitted" + (
            ": " + "; ".join(result.skipped.values()) if result.skipped else ""
        )
        return None
    lead = next(row for row in rows if row.get("ROTOR") in result.samples)
    done = _harmonics.write_harmonics_table(
        target(out / relative),
        pol=pol,
        context=tuple(lead.get(name) for name in CONTEXT_COLUMNS),
        result=result,
    )
    return done, {
        "runs": list(runs),
        "kind": _harmonics.HARMONICS_KIND,
        "source": source,
        "samples": sum(result.samples.values()),
        "samples_by_rotor": dict(result.samples),
        **(extra or {}),
    }


def _acoustic_products(
    record: RunRecord,
    *,
    sim_dir: Path,
    stem: str,
    out: Path,
    rotors: Mapping[str, tuple[_harmonics.HarmonicRotor, object]],
    clocks: Mapping[str, Mapping[str, object]],
    target: Callable[[Path], Path],
    skipped: dict[str, str],
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write a point's acoustic products from the export its record lists (0.32.0, FR-264).

    The record lists the export among its ``outputs``, the entry that ends with
    :data:`~pyflightstream.cases.acoustics.ACOUSTIC_SIGNALS_SUFFIX` (how the run
    layer records it, ``with_acoustic_signals``): a path relative to the point's
    simulation folder, or absolute. A record without one asks for no acoustics,
    and nothing is said. A file
    that cannot be read is named under ``acoustics`` in ``skipped`` and warned
    in ``post.log``; every ``NA`` the writer owes is warned too. Nothing blocks.
    """
    listed = next(
        (
            str(name)
            for name in record.outputs
            if str(name).lower().endswith(_acoustics.ACOUSTIC_SIGNALS_SUFFIX)
        ),
        None,
    )
    if listed is None:
        return [], {}
    source = Path(listed)
    if not source.is_absolute():
        source = sim_dir / source
    key = _acoustics.ACOUSTICS_DIR
    try:
        signals = _acoustics.read_acoustic_signals(source)
    except ProductError as error:
        skipped[key] = str(error)
        warn(f"point={stem} product={key}: {error}", PyflightstreamWarning, stacklevel=2)
        return [], {}
    speeds: dict[str, tuple[int | None, float | None]] = {}
    for alias, (rotor, _) in rotors.items():
        rpm = clocks.get(alias, {}).get("rpm")
        speeds[alias] = (
            len(rotor.blades) or None,
            float(rpm) if isinstance(rpm, int | float) and not isinstance(rpm, bool) else None,
        )
    try:
        made = _acoustics.write_acoustic_products(
            signals, out / key, stem=stem, rotors=speeds, target=target
        )
    except (ProductError, OSError) as error:
        skipped[key] = str(error)
        warn(f"point={stem} product={key}: {error}", PyflightstreamWarning, stacklevel=2)
        return [], {}
    for note in made.notes:
        warn(f"point={stem} product={key}: {note}", PyflightstreamWarning, stacklevel=2)
    names: dict[str, dict[str, object]] = {
        (path.relative_to(out) if path.is_relative_to(out) else path).as_posix(): {
            "runs": [record.run_id],
            "kind": "acoustics",
            "source": "acoustic_signals",
            "observers": len(signals),
        }
        for path in made.files
    }
    return made.files, names


def _skip_disc_maps(point: str, reason: str, skipped: dict[str, str], marker: str = "") -> None:
    """Name the disc maps a point could not write, and why (0.32.0)."""
    relative = f"{SECTIONS_DIR}/{point}{_disc_maps.DISC_MAP_MARK}{marker}"
    skipped[relative] = f"no disc map: {reason}"
    warn(
        f"point={point} product={relative}: {skipped[relative]}",
        PyflightstreamWarning,
        stacklevel=3,
    )


def _write_disc_maps(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, str]],
    rotors: Mapping[str, _harmonics.HarmonicRotor],
    *,
    sample_column: str,
    point: str,
    pol: str,
    source: str,
    out: Path,
    target: Callable[[Path], Path],
    runs: Sequence[str],
    skipped: dict[str, str],
    extra: Mapping[str, object] | None,
) -> list[tuple[Path, dict[str, object]]]:
    """Write ``sections/<point>_disc_<ROTOR>_<QUANTITY>.csv`` from a table already read (0.32.0).

    One file per rotor and sectional load quantity of the rows given (a wheel's
    every clocking, an unsteady point's last complete revolution), by
    :mod:`pyflightstream.post.disc_maps`. A rotor with no blade at a stated
    azimuth is named under ``sections/<point>_disc_`` in ``skipped`` and
    warned; nothing blocks. Returns each file with its ``products.json`` entry.
    """
    relative = f"{SECTIONS_DIR}/{point}{_disc_maps.DISC_MAP_MARK}"
    mapped = _disc_maps.disc_map_rows(columns, rows, rotors, sample_column=sample_column)
    for marker, reason in mapped.skipped.items():
        skipped[f"{relative}{marker}"] = reason
        warn(f"point={point} product={relative}: {reason}", PyflightstreamWarning, stacklevel=2)
    if not mapped.maps:
        return []
    lead = next(row for row in rows if row.get("ROTOR") in mapped.samples)
    paths = _disc_maps.write_disc_maps(
        mapped,
        point=point,
        pol=pol,
        context=tuple(lead.get(name) for name in CONTEXT_COLUMNS),
        out_dir=out / SECTIONS_DIR,
        target=target,
    )
    return [
        (
            path,
            {
                "runs": list(runs),
                "kind": _disc_maps.DISC_MAP_KIND,
                "source": source,
                "samples": mapped.samples[alias],
                "rotor": alias,
                "quantity": quantity,
                **(extra or {}),
            },
        )
        for path, (alias, quantity) in zip(paths, sorted(mapped.maps), strict=True)
    ]


def _step_of(cell: object) -> int | None:
    """Return a table's ``STEP`` cell as a whole step, or None where it states none."""
    try:
        return int(float(str(cell)))
    except ValueError:
        return None


def _wheel_harmonics(
    table: Path,
    point: PolarPoint,
    record: RunRecord | None,
    *,
    out: Path,
    target: Callable[[Path], Path],
    runs: Sequence[str],
    skipped: dict[str, str],
    disc_maps: list[tuple[Path, dict[str, object]]] | None = None,
) -> tuple[Path, dict[str, object]] | None:
    """Fit a quasi-steady WHEEL point's harmonics over its blades and clockings (0.31.0).

    None, and nothing said, for any point that is not a wheel, and for a
    wheel whose record cannot be read (its sections table names that).
    """
    if record is None or record.recipe != QSTEADY_ROTOR:
        return None
    try:
        quasi = read_qsteady_record(point.loads_path)
    except QsteadyRecordError:
        return None
    if quasi.case != "wheel":
        return None
    rotor = _harmonics.HarmonicRotor(
        alias=quasi.rotor_alias,
        blades=tuple((str(family),) for family in quasi.families_blades),
        diameter_m=float(quasi.diameter_m),
        azimuth_is_blade_one=False,
    )
    return _write_harmonics(
        table,
        point=point.name,
        pol=record.sim_id,
        rotors={rotor.alias: rotor},
        sample_column=_qsteady.CLOCKING_COLUMN,
        source=_harmonics.SOURCE_WHEEL,
        windows=None,
        out=out,
        target=target,
        runs=runs,
        skipped=skipped,
        extra={"clockings": len(quasi.positions)},
        disc_maps=disc_maps,
    )


def _harmonic_rotors(
    live: object | None, aliases: Mapping[str, Sequence[str]] | None, record: RunRecord
) -> dict[str, tuple[_harmonics.HarmonicRotor, object]]:
    """Return each rotor of an unsteady point for the harmonic product, with its clock.

    Blade n is the n-th entry of the rotor's ``families_blades`` (the count of
    blades is their number), expanded through the aliases as the sections
    identity expands them; the diameter is the rotor block's own, from the
    reference the row names today, and None where there is none to ask. The
    clock (``steps_per_revolution``) is the point's record's, through
    :func:`_section_rotors`.
    """
    clocks = _section_rotors(live, aliases, record)
    blocks = getattr(live, "rotors", None) or {}
    reductions = record.reductions if isinstance(record.reductions, Mapping) else {}
    stated = reductions.get("rotors")
    table: dict[str, tuple[_harmonics.HarmonicRotor, object]] = {}
    for alias, clock in clocks.items():
        block = blocks.get(alias)
        names: Sequence[object] = []
        diameter: object = None
        if block is not None:
            names = list(getattr(block, "families_blades", ()) or ())
            diameter = getattr(block, "diameter_m", None)
        else:
            own = stated.get(alias) if isinstance(stated, Mapping) else None
            recorded = own if isinstance(own, Mapping) else reductions
            named = recorded.get(BLADE_FAMILIES_KEY)
            if isinstance(named, Sequence) and not isinstance(named, str):
                names = list(named)
        blades = tuple(
            tuple(str(member) for member in (aliases or {}).get(str(name), (str(name),)))
            for name in names
        )
        stated_diameter = (
            float(diameter)
            if isinstance(diameter, int | float) and not isinstance(diameter, bool)
            else None
        )
        table[alias] = (
            _harmonics.HarmonicRotor(
                alias=alias,
                blades=blades,
                diameter_m=stated_diameter,
                azimuth_is_blade_one=False,
            ),
            clock.get("steps_per_revolution"),
        )
    return table


def _unsteady_harmonics(
    record: RunRecord,
    *,
    stem: str,
    out: Path,
    series: Sequence[Path],
    rotors: Mapping[str, tuple[_harmonics.HarmonicRotor, object]],
    target: Callable[[Path], Path],
    skipped: dict[str, str],
    disc_maps: list[tuple[Path, dict[str, object]]] | None = None,
) -> tuple[Path, dict[str, object]] | None:
    """Fit an ``unsteady_rotor`` point's harmonics over each rotor's last complete revolution.

    Read from the WRITTEN sections series; each rotor is cut on its own
    ``steps_per_revolution`` from the record, counted from the series' first
    step (:func:`pyflightstream.post.harmonics.last_complete_revolution`). A
    rotor with no stated clock or no complete revolution is named under the
    product's key. A point that cuts sections (its record states a sections
    layout) and has no sections series, no export window or no rotor to fit
    writes nothing and is named under the product's key too, with a line in
    ``post.log`` (invariant 2): the product was silently absent on a licensed
    run whose row cut sections and exported no per-step sectional loads. A
    point that cuts no sections asked for no harmonics, and nothing is said.
    """
    name = f"{stem}_sections_series.csv"
    table = next((path for path in series if path.name == name), None)
    window = record.export_window
    relative = f"{SECTIONS_DIR}/{stem}{_harmonics.HARMONICS_SUFFIX}"
    if table is None and not record.sections_layout:
        return None
    if table is None or not window or not rotors:
        if not rotors:
            missing = "the point's record states no rotor whose blades and clock the fit can read"
        elif table is None:
            missing = (
                f"the point wrote no sections series ({name}), which the harmonics of an "
                "unsteady rotor are fitted from: the row exported no per-step sectional "
                "loads, or the series was not written (see its own entry)"
            )
        else:
            missing = "the point's record states no export window to find its last revolution in"
        skipped[relative] = missing
        warn(f"point={stem} product={relative}: {missing}", PyflightstreamWarning, stacklevel=2)
        _skip_disc_maps(stem, missing, skipped)
        return None
    first, last = int(window["first_step"]), int(window["time_iterations"])
    windows: dict[str, tuple[int, int]] = {}
    clocks: dict[str, float] = {}
    for alias, (_, per_revolution) in rotors.items():
        if (
            isinstance(per_revolution, bool)
            or not isinstance(per_revolution, int | float)
            or not per_revolution >= 0.5
        ):
            reason = f"rotor {alias!r} states no steps per revolution in the point's record"
        else:
            revolution = _harmonics.last_complete_revolution(first, last, float(per_revolution))
            if revolution is not None:
                windows[alias] = revolution
                clocks[alias] = float(per_revolution)
                continue
            reason = (
                f"the series holds steps {first} to {last}, not one complete revolution of "
                f"rotor {alias!r} at {float(per_revolution):g} steps per revolution"
            )
        skipped[f"{relative}#rotor={alias}"] = reason
        warn(f"point={stem} product={relative}: {reason}", PyflightstreamWarning, stacklevel=2)
        _skip_disc_maps(stem, reason, skipped, f"#rotor={alias}")
    if not windows:
        skipped.setdefault(relative, "no rotor of the point has a complete revolution to fit")
        return None
    return _write_harmonics(
        table,
        point=stem,
        pol=record.sim_id,
        rotors={alias: rotors[alias][0] for alias in windows},
        sample_column="STEP",
        source=_harmonics.SOURCE_UNSTEADY,
        windows=windows,
        out=out,
        target=target,
        runs=[record.run_id],
        skipped=skipped,
        extra={
            "revolution": {alias: list(steps) for alias, steps in windows.items()},
            "steps_per_revolution": clocks,
        },
        disc_maps=disc_maps,
    )


def _the_sections_writer(**arguments: Any) -> Callable[[Path, str], Path | None]:
    """Return :func:`write_sections_table` bound to one steady point's arguments (0.31.0).

    The writer of a quasi-steady wheel's further clockings, so each clocking's
    export is tabled with the point's own condition, layout and rotors, by the
    one writer of a sections table.
    """

    def tabled(path: Path, text: str) -> Path | None:
        return write_sections_table(path, text, **arguments)

    return tabled


def _qsteady_super_cells(
    point: PolarPoint,
    record: RunRecord | None,
    validity_of: Mapping[str, _qsteady.PointValidity],
) -> dict[str, str]:
    """Return a quasi-steady wheel point's validity cells for its super-file row (0.30.0).

    Empty for any other point, and for one whose quasi-steady record cannot be
    read (the clockings tables name that point under their own key).
    """
    if record is None or record.recipe != QSTEADY_ROTOR:
        return {}
    try:
        quasi = read_qsteady_record(point.loads_path)
    except QsteadyRecordError:
        return {}
    if quasi.case != "wheel":
        return {}
    validity = validity_of.get(point.name) or _qsteady.validity_of_the_plan(quasi)
    return _qsteady.validity_cells(validity)


def _qsteady_products(
    sim_id: str,
    points: Sequence[PolarPoint],
    record_of: Mapping[str, RunRecord],
    *,
    reference: ReferenceValues,
    out: Path,
    validity_of: Mapping[str, _qsteady.PointValidity],
    condition_of: Callable[[PolarPoint], Mapping[str, object]],
    target: Callable[[Path], Path],
    skipped: dict[str, str],
) -> list[tuple[Path, dict[str, object]]]:
    """Write a quasi-steady simulation's clockings table and average table (0.30.0).

    One pair per rotor, named after it like the rotor table:
    ``polars/P<sim>-<ALIAS>_qs_positions.csv`` and ``_qs_avg.csv``. A point
    whose record or clocking export is missing is left out and named under the
    file's key. A sector point is one clocking and is tabled like a wheel of
    one position. The validity is the sections' where the point has them, else
    the plan's estimate from the mesh (:mod:`pyflightstream.post.qsteady`).
    """
    wheel: dict[str, list[_qsteady.WheelPoint]] = {}
    runs: dict[str, list[str]] = {}
    left_out: dict[str, list[str]] = {}
    validity_files: dict[str, dict[str, str]] = {}
    for point in points:
        record = record_of.get(point.name)
        if record is None or record.recipe != QSTEADY_ROTOR:
            continue
        # A MISSING, UNREADABLE OR UNKNOWN RECORD is one refusal (0.31.0), and
        # the point is named under the clockings tables' key, never a traceback.
        try:
            quasi = read_qsteady_record(point.loads_path)
        except QsteadyRecordError as error:
            left_out.setdefault("?", []).append(f"{point.name}: {error}")
            continue
        alias = quasi.rotor_alias
        validity = validity_of.get(point.name) or _qsteady.validity_of_the_plan(quasi)
        own = point.state
        density = (
            own.density_kg_m3
            if own is not None and own.density_kg_m3 is not None
            else record.density_kg_m3
        )
        clockings = (
            _qsteady.clockings_of(
                quasi,
                point.loads_path.parent,
                reference=reference,
                density_kg_m3=float(density),
                shaft_loads=rotor_shaft_loads,
            )
            if density is not None
            else None
        )
        # 0.31.0: A WHEEL POINT'S ROTOR STATE, from the mean thrust over its
        # clockings, for the average table and the validity file; what cannot
        # be taken is NA and a WARNING line of the post's log.
        state: _qsteady.RotorState | None = None
        if quasi.case == "wheel" and isinstance(clockings, list) and density is not None:
            loads = point.loads
            state = _qsteady.rotor_state(
                quasi,
                clockings,
                density_kg_m3=float(density),
                velocity_m_s=getattr(loads, "freestream_velocity_m_s", None),
                alpha_deg=float(getattr(loads, "angle_of_attack_deg", None) or 0.0),
                beta_deg=float(getattr(loads, "sideslip_deg", None) or 0.0),
            )
            product = (
                f"{POLARS_DIR}/{sweep_file_stem(sim_id, _a_name_a_file_may_carry(alias))}"
                f"{_qsteady.AVERAGE_SUFFIX}"
            )
            for note in state.notes:
                warn(
                    f"point={point.name} product={product}: {note}",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
        if quasi.case == "wheel":
            # 0.30.0: THE WHEEL POINT'S VALIDITY AFTER THE RUN, in its datapoint
            # folder beside the run's record, the shares of thrust and torque
            # from the stations above k = 0.1 included (0.30.0), and its rotor
            # state (0.31.0).
            try:
                written_file = _qsteady.write_point_validity_file(
                    point.loads_path, quasi, validity, state
                )
            except OSError as error:
                skipped[f"runs/{record.run_id}#qsteady_validity"] = (
                    f"the per-point validity file of {point.name} could not be written: {error}"
                )
            else:
                validity_files.setdefault(alias, {})[point.name] = Path(
                    os.path.relpath(written_file, out)
                ).as_posix()
        if density is None:
            left_out.setdefault(alias, []).append(f"{point.name}: the point states no density")
            continue
        if isinstance(clockings, str):
            left_out.setdefault(alias, []).append(f"{point.name}: {clockings}")
            continue
        assert clockings is not None
        wheel.setdefault(alias, []).append(
            _qsteady.WheelPoint(
                pol=sim_id,
                condition=condition_of(point),
                record=quasi,
                clockings=clockings,
                validity=validity,
                state=state,
            )
        )
        runs.setdefault(alias, []).append(record.run_id)
    written: list[tuple[Path, dict[str, object]]] = []
    for alias in sorted(set(wheel) | set(left_out)):
        stem = sweep_file_stem(sim_id, _a_name_a_file_may_carry(alias))
        positions = out / POLARS_DIR / f"{stem}{_qsteady.POSITIONS_SUFFIX}"
        average = out / POLARS_DIR / f"{stem}{_qsteady.AVERAGE_SUFFIX}"
        if left_out.get(alias):
            skipped[positions.relative_to(out).as_posix()] = (
                "these quasi-steady points are not rows of the clockings tables: "
                + "; ".join(left_out[alias])
            )
        points_of = wheel.get(alias) or []
        if not points_of:
            continue
        done = _qsteady.write_qsteady_tables(
            target(positions), target(average), points_of, reference=reference
        )
        if done is None:
            continue
        for path, kind in zip(done, ("clockings", "average"), strict=True):
            written.append(
                (
                    path,
                    {
                        "runs": runs[alias],
                        "rotor": alias,
                        "kind": kind,
                        "source": (
                            "the loads export of each steady clocking of a quasi-steady rotor"
                            if kind == "clockings"
                            else "the mean of the steady clockings of a quasi-steady rotor"
                        ),
                        # Where each wheel point's validity file sits, relative to
                        # this products folder (0.30.0).
                        "validity_files": dict(sorted(validity_files.get(alias, {}).items())),
                    },
                )
            )
    return written


def _qsteady_corrections(
    workspace: CampaignWorkspace,
    sim_id: str,
    points: Sequence[PolarPoint],
    record_of: Mapping[str, RunRecord],
    *,
    pproc: PprocSpec,
    out: Path,
    written_names: Mapping[str, Mapping[str, object]],
    target: Callable[[Path], Path],
    skipped: dict[str, str],
) -> list[tuple[Path, dict[str, object]]]:
    """Write a simulation's corrected wheel products and diagnostic (0.31.0, P0310-CAL).

    Nothing where the pproc states no ``[qsteady_correction]`` table or states
    it with no route and no diagnostic, which is the default. Otherwise the
    applicator (:mod:`pyflightstream.post.corrections`) reads back each wheel
    point's written tables and writes ``<name>_corrected.csv`` beside them;
    what it cannot correct is named in ``skipped`` and warned, and nothing
    blocks.
    """
    spec = getattr(pproc, "qsteady_correction", None)
    if spec is None or (spec.route == "none" and spec.diagnostic == "none"):
        return []
    wheel: list[_corrections.WheelPointRef] = []
    stated = False
    for point in points:
        record = record_of.get(point.name)
        if record is None or record.recipe != QSTEADY_ROTOR:
            continue
        stated = True
        try:
            quasi = read_qsteady_record(point.loads_path)
        except QsteadyRecordError:
            # The record's refusal is named under the products that need it.
            continue
        if quasi.case == "wheel":
            wheel.append(_corrections.WheelPointRef(point.name, record.run_id, quasi.rotor_alias))
    if stated and not wheel:
        skipped[f"qsteady_correction#sim={sim_id}"] = (
            f"the pproc states [qsteady_correction] and simulation {sim_id} holds no "
            "quasi-steady WHEEL point, which is the only point it applies to"
        )
    if not wheel:
        return []
    try:
        known_runs: set[str] | None = {record.run_id for record in workspace.read_manifest()}
    except (OSError, ValueError, PyflightstreamError):
        known_runs = None
    return _corrections.write_qsteady_corrections(
        spec,
        sim_id=sim_id,
        inputs_dir=Path(workspace.inputs_dir),
        out=out,
        wheel_points=wheel,
        written_names=written_names,
        known_runs=known_runs,
        target=target,
        skipped=skipped,
        sections_dir=SECTIONS_DIR,
    )


def _point_series(
    workspace: CampaignWorkspace,
    sim_id: str,
    record: RunRecord,
    out: Path,
    *,
    overwrite: bool,
    archive: bool = True,
    archive_stamp: datetime | None = None,
    matrix_row: MatrixRow | None = None,
    skipped: dict[str, str] | None = None,
    pproc: PprocSpec | None = None,
    recorded_pproc: PprocSpec | None = None,
    pproc_error: str | None = None,
    surface_freeze: FrozenSolve | None = None,
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write distribution tables and any per-step series of one record.

    Each existing table is archived under the rebuild's stamp before it is
    rewritten, by the same archiver as every other product; ``archive``
    false keeps no copy. ``surface_freeze`` is the point's frozen solve, which
    the surface average (G25) is judged against before it is written.
    """
    from pyflightstream.cases import classify_outputs

    kinds = classify_outputs([Path(o).name for o in record.outputs])
    loads_name = kinds.get("loads")
    if loads_name is None:
        sectional = kinds.get("sectional_loads") or kinds.get("sections")
        if sectional is None:
            return [], {}
        stem = sectional.rsplit("_", 1)[0]
        loads_name = f"{stem}.txt"
    else:
        stem = loads_name[: -len(".txt")]
    # THE CONDITION EVERY OTHER PRODUCT OF THE POINT STATES (NL-05), assembled by
    # the same function from the same sources. A loads table that is not on disk
    # leaves the cells `NA`; the series rest on the stamped files and are still
    # written.
    condition: Mapping[str, object] | None = None
    # BOUND BEFORE THE BRANCH THAT FILLS THEM: a loads table that is not on disk
    # leaves the point unbuilt, and the clock block below reads both.
    point: PolarPoint | None = None
    cell: Mapping[str, object] | None = None
    loads_path = workspace.sim_dir(sim_id) / next(
        (o for o in record.outputs if Path(o).name == loads_name), loads_name
    )
    if loads_path.is_file():
        try:
            report = parse_loads(loads_path.read_text(encoding="utf-8", errors="replace"))
        except PyflightstreamError:
            report = None
        if report is not None:
            point = PolarPoint(
                name=stem,
                loads=report,
                loads_path=loads_path,
                point=dict(record.point),
                state=point_state(record),
            )
            cell = record.flight_condition if isinstance(record.flight_condition, Mapping) else None
    reference = (
        ReferenceValues.from_mapping(record.reference).as_lengths() if record.reference else None
    )
    live = _live_reference(workspace, matrix_row)
    if point is not None and record.mach is not None:
        # THE CLOCK COLUMNS REACH THIS FAMILY TOO. Both lenses measured the
        # rotor table and the per-step series carrying neither while the polar
        # beside them carried both, which is the drift the shared condition
        # exists to prevent (2026-09-22).
        condition = point_condition(
            point,
            mach=record.mach,
            cell=cell,
            clock=clock_rotor_facts(
                record,
                matrix_row,
                live,
                own_speeds=row_rotor_speeds(record, point.loads_path),
            ),
        )
    live_aliases = getattr(live, "aliases", None) if live is not None else None
    aliases = live_aliases if live_aliases is not None else record.aliases
    surface_exports: dict[str, dict[str, object]] = {}
    split_skips = skipped if skipped is not None else {}
    from pyflightstream.post.boundary_layer import write_boundary_layer_products

    boundary_files, boundary_names = write_boundary_layer_products(
        sim_dir=workspace.sim_dir(sim_id),
        record=record,
        stem=stem,
        out=out,
        target=lambda path: _refuse_an_existing_product(path, archive=archive, stamp=archive_stamp),
        skipped=split_skips,
        step=_last_time_step(record),
        pproc=pproc or recorded_pproc,
    )
    split_files, split_names = write_section_distributions(
        sim_dir=workspace.sim_dir(sim_id),
        record=record,
        stem=stem,
        out=out,
        target=lambda path: _refuse_an_existing_product(path, archive=archive, stamp=archive_stamp),
        skipped=split_skips,
        step=_last_time_step(record),
        pproc=recorded_pproc,
        current_pproc=pproc,
        current_aliases=getattr(live, "aliases", None),
        current_rotors=getattr(live, "rotors", None),
        integration_error=pproc_error,
        condition=condition,
        reference=reference,
        rotors=_section_rotors(live, aliases, record),
        # R03 and R04 of 0.27.0: the geometry's names, recorded since 0.27.0 or
        # recovered by the hash an older record carries; hashed for every point
        # except one whose record proves an EMPTY layout ([]). A legacy record
        # (layout None) is hashed too, deliberately: its layout is recovered
        # from its hashed script against these names
        # (section_distributions._legacy_script_layout),
        # so a truthiness test here would silently disable that recovery.
        inventory=workspace.recorded_inventory(record) if record.sections_layout != [] else None,
    )
    try:
        written, names = write_point_series(
            workspace.root,
            sim_dir=workspace.sim_dir(sim_id),
            record=record,
            stem=stem,
            out=out,
            overwrite=overwrite,
            condition=condition,
            reference=reference,
            rotors=_section_rotors(live, aliases, record),
            skipped=skipped,
            surface_exports=surface_exports,
            # `archive` WAS ACCEPTED HERE AND NEVER USED until 2026-09-14, so the
            # series were the one product a rebuild rewrote in place.
            target=lambda path: _refuse_an_existing_product(
                path, archive=archive, stamp=archive_stamp
            ),
        )
    except ProductExistsError:
        raise
    except ProductError as error:
        split_skips[f"series/{record.run_id}"] = str(error)
        warn(
            f"series of {record.run_id} not written: {error}",
            PyflightstreamWarning,
            stacklevel=2,
        )
        written, names = [], {}
    # 0.31.0 (P0310-HARMONICS): AN UNSTEADY ROTOR POINT'S PER-STATION HARMONICS,
    # fitted over its last complete revolution of the sections series just written.
    if record.recipe == "unsteady_rotor":
        series_maps: list[tuple[Path, dict[str, object]]] = []
        harmonics = _unsteady_harmonics(
            record,
            stem=stem,
            out=out,
            series=written,
            rotors=_harmonic_rotors(live, aliases, record),
            target=lambda path: _refuse_an_existing_product(
                path, archive=archive, stamp=archive_stamp
            ),
            skipped=split_skips,
            disc_maps=series_maps,
        )
        if harmonics is not None:
            written = [*written, harmonics[0]]
            done = harmonics[0]
            key = done.relative_to(out) if done.is_relative_to(out) else done
            names = {**names, key.as_posix(): harmonics[1]}
        for mapped_path, mapped_entry in series_maps:
            written = [*written, mapped_path]
            mapped_key = (
                mapped_path.relative_to(out) if mapped_path.is_relative_to(out) else mapped_path
            )
            names = {**names, mapped_key.as_posix(): mapped_entry}
    # 0.32.0 (P0320-NOISE-POST): the acoustic signals the record lists, read into
    # the per-observer products, whatever the recipe was.
    acoustic_files, acoustic_names = _acoustic_products(
        record,
        sim_dir=workspace.sim_dir(sim_id),
        stem=stem,
        out=out,
        rotors=_harmonic_rotors(live, aliases, record),
        clocks=_section_rotors(live, aliases, record),
        target=lambda path: _refuse_an_existing_product(path, archive=archive, stamp=archive_stamp),
        skipped=split_skips,
    )
    written = [*written, *acoustic_files]
    names = {**names, **acoustic_names}
    # G25: THE SURFACE AVERAGED OVER THE RECORD'S WINDOW, by the package, from the
    # per-step VTK exports; a VTK beside the Tecplot where the pproc asks for one.
    asked = recorded_pproc if recorded_pproc is not None else pproc
    averaged, averaged_names = write_point_surface_average(
        workspace.root,
        sim_dir=workspace.sim_dir(sim_id),
        record=record,
        out=out,
        target=lambda path: _refuse_an_existing_product(path, archive=archive, stamp=archive_stamp),
        vtk=bool(asked is not None and asked.exports.get("vtk", False)),
        skipped=split_skips,
        judge=lambda product, bounds: _judge_average(
            surface_freeze, list(bounds), point=record.run_id, product=product
        ),
    )
    return [*split_files, *written, *averaged, *boundary_files], {
        **boundary_names,
        **split_names,
        **names,
        **surface_exports,
        **averaged_names,
    }
