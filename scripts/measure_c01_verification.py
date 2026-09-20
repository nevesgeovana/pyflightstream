"""Read the C01 campaign and write numerical evidence without running a solver.

Usage: python scripts/measure_c01_verification.py WORKSPACE EVIDENCE.json
       [--probe-workspace PROBES]

Only aggregate measurements enter the report; private geometry and native exports
stay in the workspace. Unsupported or incomplete evidence is never verified.
Probe wall times have no on-disk receipt in the original campaign: the explicitly
labelled transcription is the supplied measurement, not a filesystem timestamp.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

REMEDY = (
    "The package refuses the pproc [time_averaging] key at plan on a build where "
    "SOLVER_TIME_AVERAGING is not verified."
)
PROBES = Path("C:/WORK/codex-rel0250/probe_time_averaging")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\x00", "")


def _one(paths: Iterator[Path]) -> Path:
    found = sorted(paths)
    if len(found) != 1:
        raise ValueError(f"expected one evidence file, found {len(found)}")
    return found[0]


def _match(pattern: str, text: str) -> re.Match[str]:
    match = re.search(pattern, text, re.M)
    if match is None:
        raise ValueError(f"missing evidence field: {pattern}")
    return match


def _result(measured: object, ok: bool, how: str, **extra: object) -> dict:
    return {"measured": measured, "verdict": "verified" if ok else "failed", "how": how, **extra}


def _attempt(read: Callable[[], dict]) -> dict:
    try:
        return read()
    except (OSError, ValueError, StopIteration, SyntaxError, csv.Error) as exc:
        # No absolute/private filenames or native lines in the public evidence.
        reason = "evidence file unavailable" if isinstance(exc, OSError) else str(exc)
        return {"measured": "NA", "verdict": "could-not-measure", "how": reason + "."}


def _finite(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("non-finite export value")
    return value


def _vtk(path: Path) -> dict:
    """Validate every payload of the native ASCII POLYDATA export, including topology."""
    with path.open(encoding="utf-8") as handle:
        if not handle.readline().startswith("# vtk DataFile Version "):
            raise ValueError("missing VTK header")
        handle.readline()  # Free-form title is private, never report it.
        if handle.readline().strip() != "ASCII":
            raise ValueError("expected ASCII VTK")
        tokens = (token for line in handle for token in line.split())

        def expect(word: str) -> None:
            if next(tokens) != word:
                raise ValueError(f"expected VTK {word}")

        expect("DATASET")
        expect("POLYDATA")
        expect("POINTS")
        points = int(next(tokens))
        expect("float")
        if points <= 0:
            raise ValueError("VTK has no points")
        for _ in range(3 * points):
            _finite(next(tokens))
        expect("POLYGONS")
        cells, size = int(next(tokens)), int(next(tokens))
        polygons = []
        consumed = 0
        for _ in range(cells):
            n = int(next(tokens))
            vertices = [int(next(tokens)) for _ in range(n)]
            if n < 3 or any(v < 0 or v >= points for v in vertices):
                raise ValueError("invalid VTK polygon")
            polygons.append(vertices)
            consumed += n + 1
        if cells <= 0 or consumed != size:
            raise ValueError("VTK polygon payload count disagrees with its header")
        association, count = "", 0
        variables: set[tuple[str, str]] = set()
        boundaries = []
        for token in tokens:
            if token in ("POINT_DATA", "CELL_DATA"):
                association, count = token, int(next(tokens))
                if count != (points if token == "POINT_DATA" else cells):
                    raise ValueError("VTK data count disagrees with topology")
                continue
            if token != "SCALARS" or not association:
                raise ValueError("unsupported VTK data block")
            name = next(tokens)
            if (association, name) in variables:
                raise ValueError("duplicate VTK variable")
            variables.add((association, name))
            expect("FLOAT")
            expect("LOOKUP_TABLE")
            expect("default")
            values = [_finite(next(tokens)) for _ in range(count)]
            if name == "Boundary_Index" and association == "CELL_DATA":
                if any(v <= 0 or not v.is_integer() for v in values):
                    raise ValueError("invalid VTK boundary index")
                boundaries = [int(v) for v in values]
        if not boundaries:
            raise ValueError("missing VTK surface identities")
        surface_points: dict[int, set[int]] = defaultdict(set)
        for boundary, vertices in zip(boundaries, polygons, strict=True):
            surface_points[boundary].update(vertices)
        if len(set().union(*surface_points.values())) != points:
            raise ValueError("VTK contains points outside its surfaces")
        counts = Counter(boundaries)
        return {
            "points": points,
            "variables": len(variables),
            "surfaces": {
                str(b): {"cells": counts[b], "points": len(v)}
                for b, v in sorted(surface_points.items())
            },
        }


def vtk_export(workspace: Path) -> dict:
    """Check native VTK payload lengths and surface connectivity."""
    return _attempt(
        lambda: _result(
            _vtk(_one((workspace / "sims/sim_2505").glob("datapoints/*/*.vtk"))),
            True,
            "Compared ASCII POLYDATA coordinates, polygons and scalar payload lengths with "
            "their headers and Boundary_Index surface connectivity.",
        )
    )


def csv_export(workspace: Path) -> dict:
    """Compare headerless FEM CSV rows with independently recorded sector points."""

    def read() -> dict:
        sim = workspace / "sims/sim_2505"
        vtk = _vtk(_one(sim.glob("datapoints/*/*.vtk")))
        rows, columns = 0, 0
        with _one(sim.glob("datapoints/*/*.csv")).open(encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                if len(row) != 4:
                    raise ValueError("FEM CSV must have four numeric columns in every row")
                for cell in row:
                    _finite(cell)
                rows += 1
                columns = len(row)
        script = _text(_one(sim.glob("scripts/*.txt")))
        copies = int(_match(r"^SYMMETRY PERIODIC (\d+)\s*$", script)[1])
        log = _text(_one(sim.glob("datapoints/*/*_log.txt")))
        sector = int(_match(r"^(\d+) vertices assigned to solver\.", log)[1])
        return _result(
            {
                "rows": rows,
                "columns": columns,
                "sector_points": sector,
                "vtk_points": vtk["points"],
                "periodic_copies": copies,
            },
            rows == sector and copies > 0 and rows * copies == vtk["points"],
            "Compared CSV rows with native-log sector vertices and VTK surface points "
            "with those rows times the script's periodic-copy count (CSV is one sector; "
            "VTK includes all copies).",
        )

    return _attempt(read)


def _iterations(log: str) -> list[int]:
    steps: list[int] = []
    expected_steps, iteration = 0, 0
    for line in log.splitlines():
        step = re.search(r"Solving unsteady time-step iteration \((\d+)/(\d+)\)", line)
        if step:
            k, n = map(int, step.groups())
            if k != len(steps) + 1 or (expected_steps and n != expected_steps):
                raise ValueError("missing or duplicate native-log time step")
            expected_steps = n
            steps.append(0)
        elif re.match(r"^\s*\d+\s+", line):
            cells = line.split()
            if len(cells) != 6:
                continue  # Other numeric summaries (e.g. vertices assigned).
            if not steps or int(cells[0]) != iteration + 1:
                raise ValueError("missing or duplicate inner iteration")
            for value in cells[1:]:
                if not re.fullmatch(r"\*+", value):
                    _finite(value)
            iteration += 1
            steps[-1] += 1
    if not steps or len(steps) != expected_steps or min(steps) == 0:
        raise ValueError("incomplete native-log time steps")
    if "Unsteady solver run time:" not in log:
        raise ValueError("missing native-log completion marker")
    return steps


def niter_limit(workspace: Path) -> dict:
    """Count inner-iteration lines in every time step, independently of global counters."""

    def read() -> dict:
        measured = {}
        ok = True
        for row in (2502, 2503):
            sim = workspace / "sims" / f"sim_{row}"
            log_path = _one(sim.glob("datapoints/*/*_log.txt"))
            log = _text(log_path)
            counts = _iterations(log)
            header = _text(log_path.with_name(log_path.name.removesuffix("_log.txt") + ".txt"))
            limit = int(_match(r"Requested solver iterations\s+(\d+)", header)[1])
            total = int(_match(r"Current solver iteration number:\s+(\d+)", header)[1])
            stats = {
                "min": min(counts),
                "max": max(counts),
                "median": statistics.median(counts),
                "total": sum(counts),
                "steps": len(counts),
                "niter": limit,
            }
            ok &= max(counts) <= limit and sum(counts) == total
            if row == 2502:
                ok &= min(counts) == limit and sum(counts) > limit
            else:
                script = _text(_one(sim.glob("scripts/*.txt")))
                convergence = int(_match(r"^SET_SOLVER_CONVERGENCE_ITERATIONS (\d+)", script)[1])
                stats["convergence_iterations"] = convergence
                ok &= min(counts) > convergence
            measured[str(row)] = stats
        a, b = measured["2502"], measured["2503"]
        return _result(
            measured,
            ok,
            f"Compared counted inner iterations with each row's recorded NITER and export "
            f"total: 2502 has {a['min']}..{a['max']} on {a['steps']} steps (total {a['total']}), "
            f"so NITER bounds each time step; 2503 has {b['min']}..{b['max']} "
            f"(median {b['median']:g}, total {b['total']}, NITER {b['niter']}), "
            f"so convergence_iterations={b['convergence_iterations']} is not a cap.",
        )

    return _attempt(read)


def solver_time_averaging(probes: Path, remedy: str = REMEDY) -> dict:
    """Compare the one-line probe variants and their actual output counts."""

    def read() -> dict:
        control = _text(probes / "without/probe.txt").splitlines()
        measured = {"control_wall_seconds": 126, "mutant_wall_seconds": 300}
        outputs = [
            p for p in (probes / "without").iterdir() if p.is_file() and p.name != "probe.txt"
        ]
        measured["control_output_count"] = len(outputs)
        ok = bool(outputs) and bool(remedy.strip())
        positions = {}
        for name in ("with", "after_init"):
            lines = _text(probes / name / "probe.txt").splitlines()
            command = "SOLVER_TIME_AVERAGING ENABLE 19 36"
            index = lines.index(command)
            init = lines.index("INITIALIZE_SOLVER")
            positions["before_initialize" if index < init else "after_initialize"] = 1
            ok &= lines[:index] + lines[index + 1 :] == control
            count = sum(p.is_file() and p.name != "probe.txt" for p in (probes / name).iterdir())
            measured["mutant_output_count" if name == "with" else "after_init_output_count"] = count
            ok &= count == 0
        measured["positions_tried"] = len(positions)
        ok &= len(positions) == 2 and any(p.name.endswith("_log.txt") for p in outputs)
        result = _result(
            measured,
            ok,
            "Compared probe scripts differing only by SOLVER_TIME_AVERAGING before/after "
            "INITIALIZE_SOLVER and counted their outputs; wall seconds (126 control, "
            "300 killed mutant) are transcribed from the supplied probe measurement "
            "because the folders contain no wall-time receipt.",
            remedy=remedy,
        )
        if ok:
            result["verdict"] = "refused-by-measurement"
        return result

    result = _attempt(read)
    result.setdefault("remedy", remedy)
    return result


def per_step_exports(workspace: Path) -> dict:
    """Compare every stamped export with the recorded action program's expected range."""

    def read() -> dict:
        sim = workspace / "sims/sim_2506"
        # Parse literals only; never execute a campaign's Python program.
        tree = ast.parse(_text(sim / "actions/pfs_unsteady_actions.py"))
        settings = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name in {
                    "TIME_ITERATIONS",
                    "THRESHOLD_FORM",
                    "THRESHOLD",
                    "STEP_DEG",
                    "EXPORTS",
                }:
                    settings[name] = ast.literal_eval(node.value)
        if len(settings) != 5:
            raise ValueError("missing per-step action settings")
        threshold = settings["THRESHOLD"]
        if settings["THRESHOLD_FORM"] == "revolutions":
            if not settings["STEP_DEG"] or settings["STEP_DEG"] <= 0:
                raise ValueError("invalid per-step rotor clock")
            threshold = threshold * 360 / settings["STEP_DEG"]
        elif settings["THRESHOLD_FORM"] != "iterations":
            raise ValueError("unknown per-step threshold form")
        first, last = max(1, math.ceil(threshold - 1e-9)), settings["TIME_ITERATIONS"]
        templates = [
            Path(line.strip())
            for line in settings["EXPORTS"].splitlines()
            if line.strip().endswith((".txt", ".dat", ".vtk", ".csv"))
        ]
        if not templates or first > last:
            raise ValueError("empty per-step export range")
        expected = {
            f"{p.stem}_iteration={step}{p.suffix}"
            for p in templates
            for step in range(first, last + 1)
        }
        files = list(sim.glob("*_iteration=*.*")) + list(sim.glob("datapoints/*/*_iteration=*.*"))
        if not files:
            raise ValueError("no stamped per-step exports")
        steps = [int(_match(r"_iteration=(\d+)\.", p.name)[1]) for p in files]
        actual = Counter(p.name for p in files)
        return _result(
            {
                "files": len(files),
                "first_step": min(steps),
                "last_step": max(steps),
                "steps": len(set(steps)),
                "expected_files": len(expected),
            },
            set(actual) == expected
            and all(n == 1 for n in actual.values())
            and all(p.stat().st_size > 0 for p in files),
            "Compared nonempty stamped files and every step with the range and export "
            "templates recorded in the per-step action program.",
        )

    return _attempt(read)


def measure(workspace: Path, probes: Path = PROBES) -> dict:
    """Return five checks with a measurement date and the campaign's supplied build identity."""
    return {
        "build": "26.124",
        "campaign": workspace.name,
        "date": date.today().isoformat(),
        "checks": {
            "solver_time_averaging": solver_time_averaging(probes),
            "vtk_export": vtk_export(workspace),
            "csv_export": csv_export(workspace),
            "niter_limit": niter_limit(workspace),
            "per_step_exports": per_step_exports(workspace),
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Write evidence, returning nonzero if any check failed or could not be measured."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--probe-workspace", type=Path, default=PROBES)
    args = parser.parse_args(argv)
    evidence = measure(args.workspace, args.probe_workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8", newline="\n")
    for name, check in evidence["checks"].items():
        print(f"{check['verdict']:>22}  {name}")
    return (
        0
        if all(
            c["verdict"] in {"verified", "refused-by-measurement"}
            for c in evidence["checks"].values()
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
