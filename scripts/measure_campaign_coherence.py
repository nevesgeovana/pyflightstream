"""Measure whether the products of a licensed rotor campaign are COHERENT IN NUMBER.

Usage::

    python scripts/measure_campaign_coherence.py <workspace> <matrix stem> <evidence.json>

It reads a workspace a campaign already ran and posted, and nothing else: no solver,
no package import. Every check is recomputed from the raw exports and from the CSV
products with the standard library, so a number the package wrote is compared with
one it did not compute. Each check states what was measured, the band it was held
to and a verdict; could-not-measure is never `coherent`.

The checks:

- `rotor_table_equals_window_mean`: a rotor table's `CT` times `rho n^2 D^4` is the
  mean, over the window the unsteady polar states, of the rotor's shaft force in the
  plots history, and NOT the last step.
- `sector_times_copies_against_full_wheel`: the periodic sector's `CT` against the
  full wheel's at the same condition, on the same nacelle (row 2414); the wheel on
  the non-axisymmetric nacelle (row 2412) and the first run of the same wheel, whose
  solve froze (row 2413), are reported beside it and decide nothing.
- `etaw_equals_eta_at_alpha_zero` and `etaw_departs_with_alpha`: `ETAW` against
  `ETA`, and against `J CTW / CP` with `CTW` recomputed from the history's force
  projected on the free stream `(cos a, 0, sin a)` of the export frame.
- `cdw_equals_cd_on_steady_exports`: on each steady loads export, `CDi + CDo`
  against the projection of `(Cx, Cy, Cz)` on `(ca cb, -ca sb, sa)`, and the polar's
  `CDW` against both.
- `every_file_says_average_or_instant`: each unsteady product's manifest entry
  states what kind of table it is.
- `manifest_equals_disk`: the products the manifest names and the product files on
  disk, in both directions.
"""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from pathlib import Path

SIX = ("FX", "FY", "FZ", "MX", "MY", "MZ")
CONDITION_LABELS = {
    "ALPHA": "Angle of attack (Deg)",
    "BETA": "Side-slip angle (Deg)",
    "MACH": "Mach Number",
    "RE": "Reynolds Number",
    "VINF": "Freestream velocity (m/s)",
    "VREF": "Reference velocity (m/s)",
}


def _table(path: Path, skip: int = 0) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        for _ in range(skip):
            handle.readline()
        return list(csv.DictReader(handle))


def _number(text: object) -> float | None:
    try:
        value = float(str(text))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _loads_total(path: Path) -> dict[str, float] | None:
    """Return the Total row and the two angles of one raw loads export."""
    text = path.read_text(encoding="utf-8", errors="replace")
    header = re.search(r"^\s*Surface,\s*(.+)$", text, flags=re.M)
    total = re.search(r"^\s*Total,\s*(.+)$", text, flags=re.M)
    alpha = re.search(r"Angle of attack \(Deg\)\s+(\S+)", text)
    beta = re.search(r"Side-slip angle \(Deg\)\s+(\S+)", text)
    if not (header and total and alpha and beta):
        return None
    names = [name.strip() for name in header.group(1).split(",")]
    cells = [cell.strip() for cell in total.group(1).split(",") if cell.strip()]
    values = [float(cell) for cell in cells]
    row = dict(zip(names, values, strict=False))
    # HOW MANY DECIMALS THE EXPORT PRINTS, which is the precision of every number read
    # off it: some builds print seven and some four.
    row["decimals"] = float(min(len(cell.partition(".")[2]) for cell in cells))
    row["alpha"] = float(alpha.group(1))
    row["beta"] = float(beta.group(1))
    return row


def _verdict(ok: bool | None) -> str:
    return "could not measure" if ok is None else ("coherent" if ok else "INCOHERENT")


def _export_condition(path: Path) -> dict[str, tuple[float, float]]:
    """Read the shared condition and its printed rounding allowance from an export."""
    text = path.read_text(encoding="utf-8", errors="replace")
    condition = {}
    for column, label in CONDITION_LABELS.items():
        found = re.search(re.escape(label) + r"\s*:?\s*(\S+)", text, re.I)
        if found is None or (value := _number(found.group(1))) is None:
            continue
        mantissa, _, exponent = found.group(1).lower().partition("e")
        half = 0.5 * 10.0 ** (int(exponent or 0) - len(mantissa.partition(".")[2]))
        scale = 1e-6 if column == "RE" else 1.0
        condition[column] = (value * scale, half * scale)
    return condition


def steady_drag(workspace: Path, out: Path) -> dict[str, object]:
    """Check `CDW == CDi + CDo` on every steady export and on every steady polar row."""
    # EACH MEASUREMENT AGAINST ITS OWN BAND (release review of 0.24.0, VV-V1). One
    # band for the whole population, set by the loosest export, let a four-decimal
    # export hide a sign defect on a seven-decimal one: the y-sign of 0.23.0 moves
    # the projection by about 7e-5 at beta 4, and a four-decimal band is 1.5e-4.
    # The verdict is the worst RATIO of a gap to its own band, with its row.
    judged: list[tuple[float, str]] = []
    measured: list[dict[str, object]] = []
    worst = 0.0
    for polar in sorted((out / "polars").glob("P*.csv")):
        if polar.name.endswith(("_uns_avg.csv", "_rotor.csv")) or polar.name.startswith("SUPER"):
            continue
        for row in _table(polar):
            cdw, cd0, cdi = (_number(row.get(k)) for k in ("CDW", "CD0", "CDI"))
            if None in (cdw, cd0, cdi):
                continue
            gap = abs(cdw - (cd0 + cdi))  # type: ignore[operator]
            worst = max(worst, gap)
            # Three columns printed at five decimals: half a unit on each. The band of
            # the export the row was computed from is added below, once it is known.
            allowed = 3 * 0.5e-5
            measured.append(
                {
                    "polar": polar.name,
                    **{key: row[key] for key in CONDITION_LABELS if key in row},
                    "CDW": cdw,
                    "CD0_plus_CDI": cd0 + cdi,
                    "gap": gap,
                    "allowed": allowed,
                }
            )  # type: ignore[operator]
    exports: list[dict[str, object]] = []
    source_band: dict[tuple[str | None, Path], tuple[dict[str, tuple[float, float]], float]] = {}
    for loads in sorted(workspace.glob("sims/sim_*/datapoints/*/*.txt")):
        if re.search(r"_(plots|sloads|probes|cp|log)\b|_iteration=", loads.name):
            continue
        total = _loads_total(loads)
        if total is None or "Steady" not in loads.read_text(encoding="utf-8", errors="replace"):
            continue
        if "Solver mode:                                Unsteady" in loads.read_text(
            encoding="utf-8", errors="replace"
        ):
            continue
        a, b = math.radians(total["alpha"]), math.radians(total["beta"])
        stream = (math.cos(a) * math.cos(b), -math.cos(a) * math.sin(b), math.sin(a))
        projected = sum(total[k] * s for k, s in zip(("Cx", "Cy", "Cz"), stream, strict=True))
        gap = abs(projected - (total["CDi"] + total["CDo"]))
        # Half a unit of the last printed digit on each of the five numbers read: the
        # three force components, weighted as the projection weighs them, and the two
        # drag integrals.
        half = 0.5 * 10.0 ** -total["decimals"]
        allowed = half * (sum(abs(weight) for weight in stream) + 2.0)
        worst = max(worst, gap)
        judged.append((gap / allowed, loads.name))
        sim = next((part[4:] for part in loads.parts if part.startswith("sim_")), None)
        source_band[(sim, loads)] = (_export_condition(loads), allowed)
        exports.append(
            {
                "export": loads.name,
                "alpha": total["alpha"],
                "beta": total["beta"],
                "projected": projected,
                "CDi_plus_CDo": total["CDi"] + total["CDo"],
                "gap": gap,
                "printed_decimals": total["decimals"],
                "allowed": allowed,
            }
        )
    # THE UNSTEADY POLAR TOO: its wind-axis drag is built from the averaged Newtons of a
    # global-frame plot group and the row's own density, and the solver plots its own
    # `CD` of the same group. Two five-decimal columns of one file.
    unsteady: list[dict[str, object]] = []
    said_by_point = frozen_by_point(workspace)
    left_out: list[dict[str, object]] = []
    for polar in sorted((out / "polars").glob("P*_uns_avg.csv")):
        for row in _table(polar):
            # A FROZEN OR UNREADABLE POINT JUDGES NOTHING HERE EITHER. This check read
            # every unsteady row until the independent review of the evidence
            # (2026-09-19) found the page claiming an exclusion the rotor checks made
            # and this one did not.
            # THE SIM TOO, NOT THE POINT NAME ALONE: two rows of one campaign share a
            # point name (`M144RE438AL+100BE+000` is row 2412's and row 2415's), and
            # matching on the name alone struck out the live row with the frozen one's
            # log. Measured on this campaign while the exclusion was being written.
            run_id = str(row.get("run_id") or "")
            point = run_id.rsplit("/", 1)[-1]
            sim = re.search(r"sim_(\w+)", run_id)
            stem = f"P{sim.group(1)}-{point}" if sim and point else None
            if stem not in said_by_point:
                stem = None
            if stem is not None:
                steps = said_by_point[stem]["steps"]
                first, last = _number(row.get("FIRST_STEP")), _number(row.get("LAST_STEP"))
                if steps is None:
                    left_out.append({"polar": polar.name, "point": point, "why": "log unreadable"})
                    continue
                if None not in (first, last) and [s for s in steps if first <= s <= last]:  # type: ignore[operator]
                    left_out.append(
                        {
                            "polar": polar.name,
                            "point": point,
                            "why": f"the solve froze at step {steps[0]}, inside the window",
                        }
                    )
                    continue
            for name in row:
                if not name.startswith("CDW_"):
                    continue
                group = name[len("CDW_") :]
                plotted = next(
                    (
                        _number(row.get(candidate))
                        # The axis block names the WHOLE plot group since the release
                        # review (`CDW_MRP_TOTAL`); a polar written before took off
                        # its `MRP_` (`CDW_TOTAL`).
                        for candidate in (f"CD_{group}", f"CD_MRP_{group}")
                        if _number(row.get(candidate)) is not None
                    ),
                    None,
                )
                turned = _number(row.get(name))
                if plotted is None or turned is None:
                    continue
                gap = abs(turned - plotted)
                # Two five-decimal columns, and the density the row states against
                # the one the solver divided by: 2e-5, measured coherent on the
                # licensed sector.
                judged.append((gap / 2.0e-5, f"{polar.name} {name}"))
                unsteady.append(
                    {
                        "polar": polar.name,
                        "ALPHA": row.get("ALPHA"),
                        "group": group,
                        name: turned,
                        "CD_plotted": plotted,
                        "gap": gap,
                    }
                )
    # A POLAR ROW IS NO MORE PRECISE THAN THE EXPORT IT WAS COMPUTED FROM: its CDW is
    # the projection of that export's vector and its CD0, CDI are that export's
    # integrals, so the export's rounding reaches the row. Found by the campaign's
    # own dry run, where a four-decimal export at beta 5 left a row 4e-5 off.
    for row in measured:
        sim = re.match(r"P(\d+)", str(row["polar"]))
        matches = [
            (path, allowed)
            for (source_sim, path), (condition, allowed) in source_band.items()
            if sim
            and source_sim == sim.group(1)
            and all(_number(row.get(key)) is not None for key in ("ALPHA", "BETA"))
            and all(
                math.isclose(actual, value, rel_tol=0.0, abs_tol=half + 0.5e-5)
                for key, (value, half) in condition.items()
                if (actual := _number(row.get(key))) is not None
            )
        ]
        if len(matches) > 1:
            raise ValueError(
                f"ambiguous export match for {row['polar']} at "
                f"{ {key: row[key] for key in CONDITION_LABELS if key in row} }: "
                + ", ".join(str(path) for path, _ in matches)
            )
        inherited = matches[0][1] if matches else 0.0
        row["allowed"] = float(row["allowed"]) + inherited  # type: ignore[arg-type]
        row["inherited_from_its_export"] = inherited
        judged.append(
            (float(row["gap"]) / row["allowed"], f"{row['polar']} ALPHA {row.get('ALPHA')}")  # type: ignore[arg-type]
        )
    ratio, where = max(judged) if judged else (None, None)
    ok = None if not (measured and exports) else ratio is not None and ratio <= 1.0
    return {
        "measured": {
            "polar_rows": measured,
            "exports": exports,
            "unsteady_polar_rows": unsteady,
            "unsteady_rows_left_out": left_out,
            "worst_gap": worst,
            "worst_ratio": ratio,
            "worst_ratio_at": where,
        },
        "band": (
            "EACH against its own: an export, half a unit of the last digit IT prints on "
            "each of the five numbers read off it; a polar row, half a unit on each of its "
            "three five-decimal columns PLUS the matched export's allowance; an unsteady "
            "polar's CDW against the CD the solver "
            "plots for the same group, 2e-5. The verdict is the worst gap over its own band"
        ),
        "verdict": _verdict(ok),
    }


def _history(plots: Path, group: str, window: tuple[int, int]) -> dict[str, float] | None:
    rows = _table(plots)
    if not rows or f"FX_{group}" not in rows[0]:
        return None
    inside = [r for r in rows if window[0] <= round(float(r["Time-step"])) <= window[1]]
    if not inside:
        return None
    mean = {part: sum(float(r[f"{part}_{group}"]) for r in inside) / len(inside) for part in SIX}
    mean["last_FX"] = float(rows[-1][f"FX_{group}"])
    mean["steps"] = float(len(inside))
    return mean


_STEP_HEADER = re.compile(r"Solving unsteady time-step iteration \((\d+)/(\d+)\)")
_RESIDUALS = re.compile(r"^\d+\s+([+-][\d.]+E[+-]\d+)\s+([+-][\d.]+E[+-]\d+)", re.M)


def frozen_steps(log: Path) -> list[int] | None:
    """Return the time steps of a native log whose solve FROZE, or None if unreadable.

    None means the log states no time step at all, so this measurement could not be
    made: the caller leaves such a point out rather than taking silence for a clean
    solve (the independent review of the evidence, 2026-09-19).

    A step froze when its velocity and pressure residuals are exactly zero on every
    inner iteration after its first two: the solver stops iterating and every later
    load is a
    constant, not a solution. Measured on pfs0240 rows 2413 (from step 60) and 2412 at
    alpha 10 (from step 64); every other log of the campaign has none.
    """
    parts = _STEP_HEADER.split(log.read_text(encoding="latin-1"))
    if len(parts) < 4:
        return None
    frozen = []
    for k in range(1, len(parts), 3):
        rows = _RESIDUALS.findall(parts[k + 2])
        if len(rows) > 2 and all(float(a) == 0.0 and float(b) == 0.0 for a, b in rows[2:]):
            frozen.append(int(parts[k]))
    return frozen


def frozen_by_point(workspace: Path) -> dict[str, dict[str, object]]:
    """Return, per point name, what its native log says about a frozen solve.

    The key is the point's file stem as every product spells it (`P2412-M144RE...`).
    A point with no unsteady log at all is absent: a steady run has no time step to
    freeze. `steps` is None where the log could not be read for them.
    """
    found: dict[str, dict[str, object]] = {}
    for log in sorted(workspace.glob("sims/sim_*/datapoints/*/*_log.txt")):
        steps = frozen_steps(log)
        if steps is None and "unsteady time-step" not in log.read_text(encoding="latin-1"):
            continue  # a steady run: nothing to say
        found[log.name[: -len("_log.txt")]] = {
            "log": log.name,
            "steps": steps,
            "first_frozen_step": None if not steps else steps[0],
        }
    return found


def rotor_checks(out: Path, manifest: dict) -> dict[str, dict[str, object]]:
    """Check each rotor table against the plots history it was read from, and ETAW.

    A point whose window touches a FROZEN step (:func:`frozen_steps`) is listed under
    `no_frozen_solve_in_a_window` and takes part in no other verdict: its numbers are
    no solution.
    """
    products = manifest.get("products", {})
    workspace = out.parent.parent
    points: list[dict[str, object]] = []
    for table in sorted((out / "polars").glob("P*_rotor.csv")):
        alias = table.read_text(encoding="utf-8").splitlines()[0].strip()
        entry = products.get(f"polars/{table.name}", {})
        source = str(entry.get("source", ""))
        group = source.rsplit(" ", 1)[-1] if "plot group" in source else None
        for row in _table(table, skip=1):
            numbers = {
                k: _number(row.get(f"{k}_{alias}"))
                for k in ("J", "CT", "CP", "ETA", "ETAW", "RPM", "DIAMETER")
            }
            rho, alpha = _number(row.get("RHO")), _number(row.get("ALPHA"))
            point: dict[str, object] = {
                "table": table.name,
                "alias": alias,
                "group": group,
                "ALPHA": alpha,
                **numbers,
            }
            windows = entry.get("windows") or {}
            for name, span in windows.items():
                plots = out / "probes" / f"{name}_plots.csv"
                at = re.search(r"AL([+-]\d+)", name)
                if at is None or alpha is None or abs(int(at.group(1)) / 10.0 - alpha) > 1e-6:
                    continue
                said = frozen_by_point(workspace).get(str(name))
                if said is not None:
                    steps = said["steps"]
                    if steps is None:
                        point["left_out"] = f"{said['log']} states no time step: not measured"
                    elif [s for s in steps if int(span[0]) <= s <= int(span[1])]:
                        point["left_out"] = (
                            f"the solve froze at step {said['first_frozen_step']} of "
                            f"{said['log']}, inside this window"
                        )
                        point["first_frozen_step"] = said["first_frozen_step"]
                if (
                    group
                    and plots.is_file()
                    and None not in (rho, numbers["RPM"], numbers["DIAMETER"])
                ):
                    mean = _history(plots, group, (int(span[0]), int(span[1])))
                    if mean is not None:
                        unit = rho * (numbers["RPM"] / 60.0) ** 2 * numbers["DIAMETER"] ** 4  # type: ignore[operator]
                        a = math.radians(alpha)
                        along = mean["FX"] * math.cos(a) + mean["FZ"] * math.sin(a)
                        point.update(
                            window=list(span),
                            steps=mean["steps"],
                            mean_shaft_force_N=mean["FX"],
                            last_step_shaft_force_N=mean["last_FX"],
                            mean_shaft_torque_N_m=mean["MX"],
                            mean_side_force_N=mean["FY"],
                            mean_lift_force_N=mean["FZ"],
                            table_thrust_N=None if numbers["CT"] is None else numbers["CT"] * unit,
                            force_along_the_stream_N=along,
                            unit_N=unit,
                        )
            points.append(point)
    frozen_points = [
        {
            "table": p["table"],
            "ALPHA": p["ALPHA"],
            "first_frozen_step": p.get("first_frozen_step"),
            "left_out": p["left_out"],
        }
        for p in points
        if "left_out" in p
    ]
    points = [p for p in points if "left_out" not in p]

    def _gap(point: dict) -> float | None:
        t, m = point.get("table_thrust_N"), point.get("mean_shaft_force_N")
        if t is None or m is None or not m:
            return None
        return abs(abs(t) - abs(m)) / abs(m)

    gaps = [g for g in (_gap(p) for p in points) if g is not None]
    contrast = [
        abs(abs(p["last_step_shaft_force_N"]) - abs(p["mean_shaft_force_N"]))
        / abs(p["mean_shaft_force_N"])
        for p in points
        if p.get("mean_shaft_force_N")
    ]
    checks: dict[str, dict[str, object]] = {}
    checks["rotor_table_equals_window_mean"] = {
        "measured": {
            "points": points,
            "worst_relative_gap": max(gaps) if gaps else None,
            "last_step_against_mean": contrast,
        },
        "band": "1e-3 of the window mean: CT is printed at five decimals",
        "verdict": _verdict(None if not gaps else max(gaps) <= 1e-3),
    }
    zero = [p for p in points if p.get("ALPHA") == 0.0 and p.get("CT") is not None]
    # THE WHEEL IS THE SECTOR'S OWN GEOMETRY, COMPLETED: geometry 17, the sector 13
    # six times over (the axisymmetric NMIN nacelle). Row 2414 runs it; row 2413 ran it
    # first and its solve FROZE at time step 60 (residuals exactly zero from then on),
    # so its window is no solution and it decides nothing. Row 2412 (geometry 24, the
    # NMI nacelle, not axisymmetric) is no copy of the sector either; both are reported
    # beside the verdict (reports/pfs0240/README.md).
    sector = [p for p in zero if "2411" in str(p["table"])]
    wheel = [p for p in zero if "2414" in str(p["table"])]
    frozen = [p for p in zero if "2413" in str(p["table"])]
    other = [p for p in zero if "2412" in str(p["table"])]
    ratio = None
    if sector and wheel and wheel[0]["CT"]:
        ratio = sector[0]["CT"] / wheel[0]["CT"]  # type: ignore[operator]
    ratio_other = None
    if sector and other and other[0]["CT"]:
        ratio_other = sector[0]["CT"] / other[0]["CT"]  # type: ignore[operator]
    checks["sector_times_copies_against_full_wheel"] = {
        "measured": {
            "CT_sector": sector[0]["CT"] if sector else None,
            "CT_full_wheel": wheel[0]["CT"] if wheel else None,
            "ratio": ratio,
            "full_wheel_row": "2414",
            "frozen_solve_2413": {"CT": frozen[0]["CT"] if frozen else None},
            "not_axisymmetric_wheel_2412": {
                "CT": other[0]["CT"] if other else None,
                "ratio": ratio_other,
            },
        },
        "band": "the ratio within 5 per cent of one: the products state the WHOLE rotor either way",
        "verdict": _verdict(None if ratio is None else abs(ratio - 1.0) <= 0.05),
    }
    at_zero = [
        abs(p["ETAW"] - p["ETA"])
        for p in zero
        if p.get("ETAW") is not None and p.get("ETA") is not None
    ]  # type: ignore[operator]
    checks["etaw_equals_eta_at_alpha_zero"] = {
        "measured": {"gaps": at_zero},
        "band": "2e-5: two columns printed at five decimals",
        "verdict": _verdict(None if not at_zero else max(at_zero) <= 2e-5),
    }
    tilted = []
    for p in points:
        if (
            not p.get("ALPHA")
            or p.get("force_along_the_stream_N") is None
            or None in (p.get("J"), p.get("CP"), p.get("ETAW"))
        ):
            continue
        expected = p["J"] * (p["force_along_the_stream_N"] / p["unit_N"]) / p["CP"]  # type: ignore[operator]
        tilted.append(
            {
                "ALPHA": p["ALPHA"],
                "ETA": p.get("ETA"),
                "ETAW": p["ETAW"],
                "J_CTW_over_CP_from_the_history": expected,
                "gap": abs(p["ETAW"] - expected),
            }
        )  # type: ignore[arg-type]
    checks["etaw_departs_with_alpha"] = {
        "measured": {"points": tilted},
        "band": (
            "ETAW differs from ETA and equals the SIGNED J CTW / CP from the history within 1e-3"
        ),
        "verdict": _verdict(
            None if not tilted else all(t["gap"] <= 1e-3 and t["ETAW"] != t["ETA"] for t in tilted)
        ),
    }
    checks["no_frozen_solve_in_a_window"] = {
        "measured": {"frozen_points_left_out": frozen_points},
        "band": "none: a point whose window touches a frozen step is no solution",
        "note": (
            "informational; the frozen points take part in no other verdict, so a "
            "check left with no valid point reads could-not-measure, never coherent"
        ),
        "verdict": "coherent",
    }
    return checks


def kinds_and_disk(out: Path, manifest: dict) -> dict[str, dict[str, object]]:
    """Check that the manifest says what kind each table is, and names what is on disk."""
    products = manifest.get("products", {})
    silent = []
    stated = 0
    for name, entry in products.items():
        unsteady = name.endswith(("_uns_avg.csv", "_rotor.csv")) or name.startswith(
            ("sections/", "probes/")
        )
        if not unsteady or name.endswith(("_plots.csv", "_probes.csv")):
            continue
        says = any(key in entry for key in ("kind", "source", "reduction"))
        stated += says
        if not says:
            silent.append(name)
    on_disk = {
        path.relative_to(out).as_posix()
        for path in out.rglob("*")
        if path.is_file()
        and "archive" not in path.parts
        and path.suffix in (".csv", ".dat")
        and path.parent != out
    }
    named = {name for name in products if name.rsplit(".", 1)[-1] in ("csv", "dat")}
    return {
        "every_file_says_average_or_instant": {
            "measured": {"stated": stated, "silent": silent},
            "band": "no unsteady product's manifest entry is silent about its kind",
            "verdict": _verdict(None if not stated else not silent),
        },
        "manifest_equals_disk": {
            "measured": {
                "named_and_absent": sorted(named - on_disk),
                "on_disk_and_unnamed": sorted(on_disk - named),
                "named": len(named),
                "on_disk": len(on_disk),
            },
            "band": "both differences empty",
            "verdict": _verdict(None if not named else named == on_disk),
        },
    }


def main(argv: list[str]) -> int:
    """Measure one posted workspace and write the evidence; 0 when every check is coherent."""
    workspace, stem, target = Path(argv[1]), argv[2], Path(argv[3])
    out = workspace / "post" / stem
    manifest = json.loads((out / "products.json").read_text(encoding="utf-8"))
    matrix = (workspace / f"{stem}.fs").read_text(encoding="utf-8")
    checks = {"cdw_equals_cd_on_steady_exports": steady_drag(workspace, out)}
    checks.update(rotor_checks(out, manifest))
    checks.update(kinds_and_disk(out, manifest))
    evidence = {
        "campaign": workspace.name,
        "matrix": f"{stem}.fs",
        "geometries": sorted(set(re.findall(r"[\w.-]+\.fsm", matrix))),
        "manifest_complete": manifest.get("complete"),
        "skipped": manifest.get("skipped", {}),
        "checks": checks,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, indent=1) + "\n", encoding="utf-8")
    for name, check in checks.items():
        print(f"{check['verdict']:>18}  {name}")
    return 0 if all(c["verdict"] == "coherent" for c in checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
