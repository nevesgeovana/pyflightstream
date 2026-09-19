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
  full wheel's at the same condition.
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


def steady_drag(workspace: Path, out: Path) -> dict[str, object]:
    """Check `CDW == CDi + CDo` on every steady export and on every steady polar row."""
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
            measured.append(
                {
                    "polar": polar.name,
                    "ALPHA": row.get("ALPHA"),
                    "BETA": row.get("BETA"),
                    "CDW": cdw,
                    "CD0_plus_CDI": cd0 + cdi,
                    "gap": gap,
                }
            )  # type: ignore[operator]
    exports: list[dict[str, object]] = []
    band = 0.0
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
        band = max(band, allowed)
        worst = max(worst, gap)
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
    # A polar row prints five decimals of numbers read off the same export.
    band += 1.0e-5
    ok = None if not (measured and exports) else worst <= band
    return {
        "measured": {"polar_rows": measured, "exports": exports, "worst_gap": worst},
        "band": (
            f"{band:.2e}: half a unit of the last digit the export prints, on each of the "
            "five numbers read off it, plus the polar's own five decimals"
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


def rotor_checks(out: Path, manifest: dict) -> dict[str, dict[str, object]]:
    """Check each rotor table against the plots history it was read from, and ETAW."""
    products = manifest.get("products", {})
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
                            table_thrust_N=None if numbers["CT"] is None else numbers["CT"] * unit,
                            force_along_the_stream_N=along,
                            unit_N=unit,
                        )
            points.append(point)

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
    sector = [p for p in zero if "2411" in str(p["table"])]
    wheel = [p for p in zero if "2412" in str(p["table"])]
    ratio = None
    if sector and wheel and wheel[0]["CT"]:
        ratio = sector[0]["CT"] / wheel[0]["CT"]  # type: ignore[operator]
    checks["sector_times_copies_against_full_wheel"] = {
        "measured": {
            "CT_sector": sector[0]["CT"] if sector else None,
            "CT_full_wheel": wheel[0]["CT"] if wheel else None,
            "ratio": ratio,
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
        expected = abs(p["J"] * (p["force_along_the_stream_N"] / p["unit_N"]) / p["CP"])  # type: ignore[operator]
        tilted.append(
            {
                "ALPHA": p["ALPHA"],
                "ETA": p.get("ETA"),
                "ETAW": p["ETAW"],
                "J_CTW_over_CP_from_the_history": expected,
                "gap": abs(abs(p["ETAW"]) - expected),
            }
        )  # type: ignore[arg-type]
    checks["etaw_departs_with_alpha"] = {
        "measured": {"points": tilted},
        "band": "ETAW differs from ETA, and equals J CTW / CP from the history within 1e-3",
        "verdict": _verdict(
            None if not tilted else all(t["gap"] <= 1e-3 and t["ETAW"] != t["ETA"] for t in tilted)
        ),
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
