"""Measure the rotation null test of PFS-2034.05 over the products of matriz_rotate.fs.

    python -m tests.tier3_licensed.rotation_null

THE EXPERIMENT: take a full wheel, turn the whole isolated propeller, and give
the flow the opposite angle of attack so that it is still uniform on the
propeller. Then see whether every output makes sense.

WHY IT IS A NULL TEST AND NOT A COMPARISON. Turning the model by an angle and
turning the freestream by the same angle does not change the physical problem;
it changes only the frame it is written in. So the answer is known BEFORE the
solver runs, exactly, with no band to argue about, and that is rare enough here
to be worth spending a seat on. FOUR things follow from it and this module
checks all four, as four separate verdicts, because each fails differently and
a merged verdict cannot show which kind failed:

  1. WIND AXES ARE INVARIANT. CL, CDi and CDo are defined against the
     freestream, and the freestream turned with the model, so they come back
     IDENTICAL. This is the coarsest check: it passes even if the rotation
     turned the model the wrong way, because a propeller at zero incidence is
     symmetric about its axis.

  2. BODY AXES ROTATE, BY EXACTLY THE STATED ANGLE. The global frame did NOT
     turn, so the force and moment VECTORS come back as the control's rotated
     by the angle. This is the check that has a direction in it: it is the one
     that catches a rotation applied the wrong way round, or twice, or about
     the wrong point. It is asserted as a rotation and not as a magnitude,
     because a magnitude is invariant under the wrong rotation too.

  3. THE SERIES AGREES STEP BY STEP, under the same two rules. A row's time
     average can agree while its individual steps do not, which is what an
     azimuthal phase error looks like.

  4. THE SECTIONS AGREE STATION BY STATION, in the blade's own frame, which
     turned with the alias that owns it, so they are invariant outright. This
     is the finest grid this workspace exports.

AND THE DERANGEMENT, which is the point of running THREE rows for a test that
compares TWO. Row 9002 turns the model by +6 and the flow by +6, so the flow
meets the propeller at twelve degrees and NOTHING above should hold. It is
here because a check that has only ever been shown to accept is not a check:
this estate has shipped one guard whose every pairing passed and one whose
only evidence was that it could refuse. So 9002 is asserted to FAIL, by name,
and its failure is printed beside 9003's pass.

IT ALSO SETTLES THE SIGN, which was not known when the rows were written.
"The opposite angle of attack" is unambiguous physics, and the solver's own
convention decides which arithmetic sign that is; rather than guess it and
report a pass that was half luck, both signs were run and the rows say which
one restored the flow.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRODUCTS = HERE / "post" / "matriz_rotate"

#: The row that turns nothing: the propeller square to a uniform axial flow.
CONTROL = "P9001-M100RE230AL+000"
#: The rows that turn the mesh by +6 degrees about the hub's Y axis. One of
#: them turns the flow the other way and is the null pair; the other turns it
#: the same way and is the derangement. WHICH IS WHICH IS NOT WRITTEN HERE:
#: it is what the measurement reports, because it is the solver's convention
#: and not this module's opinion.
TURNED = ("P9002-M100RE230AL+060", "P9003-M100RE230AL-060")

#: How far the mesh turned, degrees, about the hub frame's Y axis. It is the
#: ANGLE cell of rows 9002 and 9003 of matriz_rotate.fs.
MESH_ANGLE_DEG = 6.0

#: The coefficients defined against the freestream. Invariant.
WIND = ("CL", "CDi", "CDo")

#: The tolerance, and its reason. The lateral components of this row carry an
#: azimuthal residual of about 2e-4 in coefficient terms, because half a
#: revolution of a two-blade rotor does not average the azimuth away exactly.
#: A null test asserted tighter than the noise of the thing it measures
#: reports a defect that is the discretisation, so the band is set from the
#: MEASURED wobble of the control's own lateral force and stated here rather
#: than tuned until the answer came out right.
ABS_TOL = 5e-4

#: How many comparisons one turned row is scored on: 3 wind-axis, 6 body-axis,
#: 140 per-step and 60 sectional. ASSERTED RATHER THAN REPORTED, because the
#: number appears in a committed report and nothing measured it: a run over
#: products holding one shared step would have scored twenty comparisons and
#: still printed that the null test holds. The count is a property of the
#: products, so a thinner export changes it and must be seen to.
EXPECTED_COMPARISONS = 209


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def rotate_y(x: float, z: float, angle_deg: float) -> tuple[float, float]:
    """One vector's X and Z after the frame's contents turn by ``angle_deg`` about Y.

    Written out rather than taken from a library so the convention is READABLE
    beside the numbers it produces: a point of the mesh at (x, 0, z) that turns
    by a positive angle about Y lands at (x cos + z sin, 0, -x sin + z cos).
    """
    a = math.radians(angle_deg)
    return x * math.cos(a) + z * math.sin(a), -x * math.sin(a) + z * math.cos(a)


#: HOW MANY SIGNIFICANT DIGITS the sectional-loads export carries, MEASURED on
#: the control's own file rather than taken from the setup. The setup preset
#: s002 states `significant_digits = 7` and this export prints FOUR: of the 140
#: numbers in that file, the longest mantissa is four digits and the rest are
#: four with trailing zeros. So the finest difference the file can express at a
#: value of 2093 is 1.0, and two runs that differ by exactly that differ by the
#: smallest amount this artifact can represent, which is not a disagreement.
SECTION_SIGNIFICANT_DIGITS = 4


def quantum(value: float) -> float:
    """One unit in the last significant digit the sectional export prints for ``value``."""
    if value == 0.0:
        return 10.0 ** -(SECTION_SIGNIFICANT_DIGITS - 1)
    return 10.0 ** (math.floor(math.log10(abs(value))) - (SECTION_SIGNIFICANT_DIGITS - 1))


class Verdict:
    """What one comparison found, and enough of it to print a table."""

    def __init__(self, name: str, band: float = ABS_TOL) -> None:
        self.name = name
        self.band = band
        self.rows: list[tuple[str, float, float, float, bool]] = []

    def check(self, what: str, expected: float, got: float, band: float | None = None) -> None:
        gap = abs(got - expected)
        limit = self.band if band is None else band
        # THE BAND IS INCLUSIVE AND IS GIVEN A HAIR OF SLACK, which the
        # adversarial pass over this file found and which the run did not
        # happen to hit. The sectional band is one unit in the last printed
        # digit, and at a value of 108.1 that unit is 0.1: `108.2 - 108.1` is
        # 0.10000000000000853 in binary floating point, so a difference of
        # EXACTLY one quantum was refused as larger than one quantum. The run
        # this file scored was unaffected because its only one-quantum case sat
        # at 2093, where the quantum is 1.0 and exactly representable, which is
        # precisely why a green run is not evidence that a band is right.
        self.rows.append((what, expected, got, gap, gap <= limit * (1 + 1e-9)))

    @property
    def agrees(self) -> bool:
        return bool(self.rows) and all(row[4] for row in self.rows)

    @property
    def worst(self) -> float:
        return max((row[3] for row in self.rows), default=0.0)

    def failures(self) -> list[tuple[str, float, float, float, bool]]:
        return [row for row in self.rows if not row[4]]


def sweep_rows() -> dict[str, dict[str, str]]:
    """The campaign sweep table, keyed by the point each row is."""
    rows = read_csv(PRODUCTS / "campaign_sweep.csv")
    by_sim: dict[str, dict[str, str]] = {}
    for row in rows:
        by_sim[row["sim_id"]] = row
    return by_sim


def compare_wind_axes(control: dict[str, str], turned: dict[str, str]) -> Verdict:
    """The freestream-referred coefficients, which are INVARIANT outright.

    SEPARATE FROM THE BODY AXES, and the separation is the finding that made
    it. The first writing put both rules in one verdict, so a reader of the
    output saw three verdicts while this report's own table describes FOUR
    kinds of check, and the changelog said four. Worse, the merged verdict
    could not show what the table claims about this kind: that it passes even
    when the model turned the WRONG WAY, because a propeller at zero incidence
    is symmetric about its axis. A check whose weakness is described in prose
    and cannot be demonstrated by the instrument is a check the reader has to
    take on trust.
    """
    verdict = Verdict("wind-axis coefficients at MRP, invariant")
    for key in WIND:
        verdict.check(f"{key} (wind axes, invariant)", float(control[key]), float(turned[key]))
    return verdict


def compare_totals(control: dict[str, str], turned: dict[str, str]) -> Verdict:
    """The time-averaged force and moment VECTORS, which rotate by the stated angle."""
    verdict = Verdict("body-axis force and moment at MRP, rotated")
    fx, fz = rotate_y(float(control["Cx"]), float(control["Cz"]), MESH_ANGLE_DEG)
    verdict.check("Cx (body axes, rotated)", fx, float(turned["Cx"]))
    verdict.check("Cz (body axes, rotated)", fz, float(turned["Cz"]))
    verdict.check(
        "Cy (body axes, on the axis of rotation)", float(control["Cy"]), float(turned["Cy"])
    )
    mx, mz = rotate_y(float(control["CMx"]), float(control["CMz"]), MESH_ANGLE_DEG)
    verdict.check("CMx (body axes, rotated)", mx, float(turned["CMx"]))
    verdict.check("CMz (body axes, rotated)", mz, float(turned["CMz"]))
    verdict.check(
        "CMy (body axes, on the axis of rotation)", float(control["CMy"]), float(turned["CMy"])
    )
    return verdict


def compare_series(control_point: str, turned_point: str) -> Verdict:
    """The per-step loads of the exported window, step by step and surface by surface.

    THE STEPS ARE PAIRED BY STEP NUMBER, not by position in the file, because
    two rows whose exports began at different steps would otherwise be
    compared off by one and agree about nothing while the physics agreed.
    """
    verdict = Verdict("per-step loads series")
    series = PRODUCTS / "series"
    left = {row["STEP"]: row for row in read_csv(series / f"{control_point}_loads_series.csv")}
    right = {row["STEP"]: row for row in read_csv(series / f"{turned_point}_loads_series.csv")}
    shared = sorted(set(left) & set(right), key=int)
    if not shared:
        raise SystemExit(f"the two series share no step: {sorted(left)} against {sorted(right)}")
    surfaces = sorted({name.rsplit("_", 1)[0] for name in left[shared[0]] if name.endswith("_Cx")})
    for step in shared:
        for surface in surfaces:
            for key in WIND:
                verdict.check(
                    f"step {step} {surface} {key}",
                    float(left[step][f"{surface}_{key}"]),
                    float(right[step][f"{surface}_{key}"]),
                )
            fx, fz = rotate_y(
                float(left[step][f"{surface}_Cx"]),
                float(left[step][f"{surface}_Cz"]),
                MESH_ANGLE_DEG,
            )
            verdict.check(f"step {step} {surface} Cx", fx, float(right[step][f"{surface}_Cx"]))
            verdict.check(f"step {step} {surface} Cz", fz, float(right[step][f"{surface}_Cz"]))
    return verdict


def compare_sections(control_point: str, turned_point: str) -> Verdict:
    """The blade's sectional loads, station by station, in the blade's OWN frame.

    The distribution is measured in LOCAL_AXIS, which turned with the alias
    that owns it, so these are invariant OUTRIGHT: no rotation is applied to
    the expectation. That is what makes this the sharpest of the four checks.
    A rotation that moved the blades and left their axes behind agrees on the
    wind axes, very nearly agrees on the body axes, and fails here.
    """
    verdict = Verdict("sectional loads, in the blade's own frame")
    left = read_csv(PRODUCTS / "sections" / f"{control_point}_sections.csv")
    right = read_csv(PRODUCTS / "sections" / f"{turned_point}_sections.csv")
    if len(left) != len(right):
        raise SystemExit(f"{len(left)} stations against {len(right)}; the distributions differ")
    # EACH NUMBER AGAINST THE EXPORT'S OWN QUANTUM, and the first writing of
    # this function got it wrong in a way worth leaving written down. It
    # divided every column by the largest Fz in the file and judged the result
    # against the coefficient band, which compares a MOMENT in newton metres
    # against a scale in newtons: station 10's moment then had to agree eight
    # times tighter than the force beside it, and it was reported as the one
    # disagreement in the whole test. It was not one. Fx and Fz there are
    # identical to the last digit printed and the moment differs by 1 in 2093,
    # which is exactly one unit in the fourth significant digit, which is all
    # the resolution the file has. A band that is dimensionally incoherent is
    # not a strict band, it is a band measuring the wrong thing.
    for index, (a, b) in enumerate(zip(left, right, strict=True), start=1):
        for key in ("Fx", "Fz", "Moment"):
            expected = float(a[key])
            verdict.check(f"station {index} {key}", expected, float(b[key]), quantum(expected))
    return verdict


def report(point: str, verdicts: list[Verdict]) -> bool:
    agrees = all(verdict.agrees for verdict in verdicts)
    print(f"\n{point} against {CONTROL}")
    for verdict in verdicts:
        mark = "AGREES" if verdict.agrees else "DIFFERS"
        print(
            f"  {mark:8} {verdict.name}: {len(verdict.rows)} comparison(s), "
            f"worst gap {verdict.worst:.3e}"
        )
        for what, expected, got, gap, _ in verdict.failures()[:4]:
            print(f"           {what}: expected {expected:+.6f}, got {got:+.6f}, gap {gap:.3e}")
        if len(verdict.failures()) > 4:
            print(f"           ... and {len(verdict.failures()) - 4} more")
    return agrees


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)

    if not (PRODUCTS / "campaign_sweep.csv").is_file():
        print(
            f"no products under {PRODUCTS}. Run the matrix on a licensed seat first:\n"
            "  python -m pyflightstream.run.cli run matriz_rotate.fs --workspace . "
            "--fs-version 26.123 --fs-exe <the 26.123 executable>"
        )
        return 1

    by_sim = sweep_rows()
    control = by_sim["9001"]
    print(
        f"The rotation null test of PFS-2034.05. The mesh of rows 9002 and 9003 is turned "
        f"{MESH_ANGLE_DEG:+.1f} degrees about the hub frame's Y axis; row 9001 turns nothing.\n"
        f"Bands: {ABS_TOL:.0e} absolute on the coefficients, set from the control's own "
        f"lateral residual; on the sectional loads, one unit in the "
        f"{SECTION_SIGNIFICANT_DIGITS} significant digits that export actually prints."
    )

    agreeing: list[str] = []
    scored: dict[str, tuple[float, list[Verdict]]] = {}
    for point in TURNED:
        sim = point.split("-")[1].split("_")[0]
        verdicts = [
            compare_wind_axes(control, by_sim[sim]),
            compare_totals(control, by_sim[sim]),
            compare_series(CONTROL, point),
            compare_sections(CONTROL, point),
        ]
        alpha = float(by_sim[sim]["alpha"])
        scored[sim] = (alpha, verdicts)
        print(f"\n--- row {sim}, angle of attack {alpha:+.1f} degrees ---", end="")
        if report(point, verdicts):
            agreeing.append(f"{sim} (alpha {alpha:+.1f})")

    # THE COMPARISON COUNT IS ASSERTED, not narrated. The report quotes 209
    # and nothing checked it: a run over one shared step would have produced
    # twenty comparisons and still printed THE NULL TEST HOLDS. A count that
    # appears only in prose is a count nobody measured.
    total = sum(len(v.rows) for _, verdicts in scored.values() for v in verdicts) // len(scored)
    if total != EXPECTED_COMPARISONS:
        print(
            f"\nREFUSED: each row was scored on {total} comparisons and this test is "
            f"{EXPECTED_COMPARISONS}. Fewer means the products are thinner than the round that "
            "was reported -- a partial export, or a series sharing fewer steps -- and a verdict "
            "over a smaller set is not the verdict this report cites."
        )
        return 1

    print()
    if len(agreeing) == 1:
        which = agreeing[0]
        # THE DERANGEMENT'S FAILURE IS COUNTED, not asserted in prose. This
        # sentence used to read "it DIFFERS on every one of the four checks"
        # whatever the derangement had actually done, so a derangement that
        # agreed on three of four printed the same success line. The
        # independent lens of the 0.18.0 round built exactly that case and the
        # module reported a clean discriminating test over it. A success
        # message must name only properties this run evaluated.
        other = next(sim for sim in scored if f"{sim} (" not in which)
        other_alpha, other_verdicts = scored[other]
        differed = [v for v in other_verdicts if not v.agrees]
        print(
            f"THE NULL TEST HOLDS, on exactly one of the two rows: {which}. The other, row "
            f"{other} at alpha {other_alpha:+.1f}, DIFFERS on {len(differed)} of "
            f"{len(other_verdicts)} checks."
        )
        if len(differed) != len(other_verdicts):
            agreed = ", ".join(v.name for v in other_verdicts if v.agrees)
            print(
                f"REFUSED: the derangement AGREED on {agreed}. Those checks did not "
                "discriminate between a propeller in uniform flow and one meeting it at twice "
                "the angle, so a pass on the other row is not evidence that they measure the "
                "rotation. This is the check-that-accepts-everything shape, caught here rather "
                "than reported as a clean round."
            )
            return 1
        print(
            "That is what makes this a measurement rather than a check that accepts whatever "
            f"it is given, and it is why three rows were run for a test that compares two: "
            f"{EXPECTED_COMPARISONS} comparisons of four kinds, each kind shown to separate "
            "the two cases."
        )
        return 0
    if not agreeing:
        print(
            "THE NULL TEST FAILS on both rows. Neither sign of the angle of attack restored "
            "the flow the rotated mesh was turned out of, so the rotation the row asked for "
            "is not the rotation the script performed."
        )
        return 1
    print(
        "BOTH rows agree, which cannot be right: they differ by twelve degrees of incidence "
        "and a propeller that answers the same to both is a propeller the angle of attack "
        "never reached. The check is measuring nothing."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
