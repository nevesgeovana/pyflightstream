# ITACA / pyflightstream shared process kit
# kit-version: 0.2.16
# artifact: check_review_rounds_mutations.py
# body-sha256: 9da4b72e42fa1369d5c55c114a6096336001a1f905dbea5d69f6627501d81e26
# canonical-source: BUILT for the kit (0.2.15, HUB-11) as the guard evidence for check_review_rounds.py. Case 1 and case 2 are the two REAL shapes: lane ITA-4's round two, which found six defective round-one fixes, and the same lane's round two as a flat two-rounds-then-register cap would have recorded it. If case 2 ever stops being refused, this checker has stopped being able to tell the rule from the count. 0.2.16 adds nine ledger cases and seven locator checks for rule 8, --incremental and the resolver, and records the one mutant that was written and SURVIVED: rule 8's own strip() is redundant with the parser's, so neither is individually load bearing and both are kept.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Guard evidence for check_review_rounds.py, on real ledger files.

Run:  python check_review_rounds_mutations.py

Every case writes a real ledger to a temporary file and runs the real CLI,
asserting the exit code AND a phrase only the intended refusal produces. The
message matters as much as the code here: the kit has twice been bitten by a
case asserting a phrase the report prints unconditionally, so a needle that
sits on the violation's own wording is the standard rather than a nicety.

Two cases are HISTORY rather than design, and they are the two that matter:

- ``ita4_round_two`` is lane ITA-4's actual shape, six round-two findings
  about round-one fixes, all fixed in round two. It must be ACCEPTED.
- ``flat_cap_would_have_shipped_it`` is the same lane under the naive
  mechanism, those six findings REGISTERED instead. It must be REFUSED. If
  it ever stops being refused, this checker has stopped expressing the rule
  and is expressing a count.

ADDED 0.2.16, three groups.

RULE 8, the property field. Its cases include ``a_worthless_property_still
_passes``, which is deliberate: rule 8 is a PRESENCE check, and a case
asserting that a sentence saying nothing still passes is what stops a green
ledger from being read as evidence that the invariants are good.

``--incremental``. Two of its cases exist only to pin what the mode may NOT
do: ``incremental_does_not_relax_rule_4`` and
``incremental_does_not_relax_rule_8``. If either ever passes, the mode has
become a way around the mechanism rather than a way to read it mid-lane.

THE LOCATOR. Seven checks that drive DIRECTORIES rather than ledger files,
in ``locator_checks``. The one that matters most is that a root holding no
ledger is a CONFIG error and never a clean run.

Exit 0 when every case holds and every mutant is denied, 1 otherwise.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

MODULE = Path(__file__).resolve().parent / "check_review_rounds.py"

GOOD_TWO_ROUNDS = """
lane: ITA-2E
rounds: 2

finding: FND-071 | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names
finding: FND-072 | round=1 | ground=new | registered
finding: FND-080 | round=2 | ground=about:FND-071 | fixed | property=the fix establishes the invariant this row names
finding: FND-081 | round=2 | ground=new | registered
"""

ITA4_ROUND_TWO = """
# Lane ITA-4 as it actually ran: round one's fixes were themselves
# defective, and round two fixed them rather than registering them.
lane: ITA-4
rounds: 2

finding: FND-046 | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names
finding: FND-015 | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names
finding: FND-056 | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names
finding: FND-054 | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names
finding: FND-067 | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names
finding: R2-01 | round=2 | ground=about:FND-046 | fixed | property=the fix establishes the invariant this row names
finding: R2-02 | round=2 | ground=about:FND-015 | fixed | property=the fix establishes the invariant this row names
finding: R2-03 | round=2 | ground=about:FND-056 | fixed | property=the fix establishes the invariant this row names
finding: R2-04 | round=2 | ground=about:FND-054 | fixed | property=the fix establishes the invariant this row names
finding: R2-05 | round=2 | ground=about:FND-067 | fixed | property=the fix establishes the invariant this row names
finding: R2-06 | round=2 | ground=new | registered
"""

FLAT_CAP = ITA4_ROUND_TWO.replace(
    "finding: R2-01 | round=2 | ground=about:FND-046 | fixed | property=the fix establishes the invariant this row names",
    "finding: R2-01 | round=2 | ground=about:FND-046 | registered",
)

THIRD_ROUND = """
lane: ITA-2B
rounds: 3

finding: A | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names
finding: B | round=2 | ground=about:A | fixed | property=the fix establishes the invariant this row names
finding: C | round=3 | ground=new | registered
"""

THIRD_ROUND_AUTHORISED = THIRD_ROUND.replace(
    "rounds: 3",
    "rounds: 3\nauthority: the author, 2026-08-01, asked before it was opened",
)

CASES: list[tuple[str, str, int, str]] = [
    ("good_two_rounds", GOOD_TWO_ROUNDS, 0, "VERIFIED"),
    ("ita4_round_two", ITA4_ROUND_TWO, 0, "VERIFIED"),
    ("flat_cap_would_have_shipped_it", FLAT_CAP, 1,
     "six guards that did not guard"),
    ("third_round_unauthorised", THIRD_ROUND, 1, "rule 3"),
    ("third_round_authorised", THIRD_ROUND_AUTHORISED, 0, "VERIFIED"),
    ("empty_ledger", "lane: X\nrounds: 1\n", 1, "certifies nothing"),
    ("no_lane", "rounds: 1\n\nfinding: A | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names\n",
     1, "does not say what it certifies"),
    ("rounds_not_a_number",
     "lane: X\nrounds: two\n\nfinding: A | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names\n",
     1, "not a positive"),
    # The needle is the highest-round sentence and not the bare string
    # "rule 2", and that is a finding this file made against itself: rule 2
    # produces TWO messages, and the round-gap one also fires on this ledger,
    # so a needle of "rule 2" was satisfied while the count comparison was
    # deleted. The mutant survived until the needle moved onto the
    # violation's own wording, which is the same correction the kit made in
    # check_release_gate_mutations and in check_shipped_surface.
    ("declared_count_disagrees",
     "lane: X\nrounds: 2\n\nfinding: A | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names\n",
     1, "the highest round on any finding is"),
    ("round_with_no_findings",
     "lane: X\nrounds: 3\nauthority: the author\n\n"
     "finding: A | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names\n"
     "finding: C | round=3 | ground=new | registered\n",
     1, "did not happen"),
    ("duplicate_id",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names\n"
     "finding: A | round=1 | ground=new | registered\n",
     1, "rule 6"),
    ("about_names_nothing",
     "lane: X\nrounds: 2\n\nfinding: A | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names\n"
     "finding: B | round=2 | ground=about:ZZZ | fixed | property=the fix establishes the invariant this row names\n",
     1, "not a finding in this ledger"),
    ("about_names_the_same_round",
     "lane: X\nrounds: 2\n\nfinding: A | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names\n"
     "finding: B | round=2 | ground=new | fixed | property=the fix establishes the invariant this row names\n"
     "finding: C | round=2 | ground=about:B | fixed | property=the fix establishes the invariant this row names\n",
     1, "STRICTLY earlier round"),
    ("about_names_a_registered_finding",
     "lane: X\nrounds: 2\n\nfinding: A | round=1 | ground=new | registered\n"
     "finding: B | round=2 | ground=about:A | fixed | property=the fix establishes the invariant this row names\n",
     1, "there is no fix here"),
    ("withdrawn_needs_a_reason",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | ground=new | withdrawn\n",
     1, "cannot police"),
    ("withdrawn_with_a_reason",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | ground=new | withdrawn | "
     "reason=the reviewer read a stale copy\n",
     0, "VERIFIED"),
    ("no_ground",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | fixed | property=the fix establishes the invariant this row names\n",
     1, "has no `ground=`"),
    ("unknown_disposition",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | ground=new | deferred\n",
     1, "expected one of"),
    ("unknown_field_is_refused_not_ignored",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names | "
     "severity=P1\n",
     2, "unknown field"),
    ("unknown_line_is_refused_not_ignored",
     "lane: X\nrounds: 1\nreviewers: three\n\n"
     "finding: A | round=1 | ground=new | fixed | property=the fix establishes the invariant this row names\n",
     2, "unknown line"),
    ("wrapped_row_is_one_row",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | ground=new | withdrawn |\n"
     "    reason=wrapped onto a second line\n",
     0, "VERIFIED"),
    # ---- rule 8, the property field, 0.2.16 ----
    ("fixed_without_a_property",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | ground=new | fixed\n",
     1, "is `fixed` with no `property="),
    ("fixed_with_a_whitespace_property",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | ground=new | fixed | "
     "property=   \n",
     1, "is `fixed` with no `property="),
    ("registered_needs_no_property",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | ground=new | registered\n",
     0, "VERIFIED"),
    # THE HONEST CASE. Rule 8 is a PRESENCE check and this is what that
    # costs: a property sentence that states nothing passes. It is here so
    # that nobody reads a green ledger as evidence the invariants are good,
    # and so that a later lane tempted to make the check judge quality sees
    # the deliberate boundary rather than a gap.
    ("a_worthless_property_still_passes",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | ground=new | fixed | "
     "property=it works\n",
     0, "VERIFIED"),
    ("property_wrapped_onto_indented_lines",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | ground=new | fixed |\n"
     "    property=the parser rejects a delimiter it cannot resolve, and\n"
     "    every delimiter it accepts appears in the output verbatim\n",
     0, "VERIFIED"),
    # ---- --incremental, 0.2.16 ----
    ("mid_lane_ledger_is_refused_when_closing",
     "lane: X\nrounds: 2\n\nfinding: A | round=1 | ground=new | fixed | "
     "property=p\n",
     1, "the highest round on any finding is"),
    ("mid_lane_ledger_passes_under_incremental",
     "lane: X\nrounds: 2\n\nfinding: A | round=1 | ground=new | fixed | "
     "property=p\n",
     0, "THIS IS NOT A CLOSING CHECK", ["--incremental"]),
    # --incremental SUSPENDS RULE 2 AND NOTHING ELSE. If either of these
    # ever passes, the mode has become a way around the mechanism.
    ("incremental_does_not_relax_rule_4", FLAT_CAP, 1,
     "six guards that did not guard", ["--incremental"]),
    ("incremental_does_not_relax_rule_8",
     "lane: X\nrounds: 1\n\nfinding: A | round=1 | ground=new | fixed\n",
     1, "is `fixed` with no `property=", ["--incremental"]),
]

MUTANTS: list[tuple[str, str, str, str]] = [
    ("an about: finding may be registered",
     'if f.disposition == "registered":\n            v.append(f"rule 4:',
     'if False:\n            v.append(f"rule 4:',
     "flat_cap_would_have_shipped_it"),
    ("the cap is not enforced",
     "if rounds > CAP and not ledger.settings.get(\"authority\"):",
     "if False:",
     "third_round_unauthorised"),
    ("an authority is not required, so none is ever named",
     "rounds > CAP and not ledger.settings.get(\"authority\")",
     "rounds > CAP and True",
     "third_round_authorised"),
    ("an about: may point at a later or equal round",
     "if target.round is not None and f.round is not None \\\n                and target.round >= f.round:",
     "if False:",
     "about_names_the_same_round"),
    ("an about: need not resolve",
     "if target is None or target is f:",
     "if False and target is f:",
     "about_names_nothing"),
    ("an about: may point at something that was never fixed",
     'elif target.disposition != "fixed":',
     "elif False:",
     "about_names_a_registered_finding"),
    ("an empty ledger certifies a review",
     "if not ledger.findings:",
     "if False:",
     "empty_ledger"),
    ("a repeated id is accepted",
     "if f.ident in seen:",
     "if False:",
     "duplicate_id"),
    ("the declared round count is not compared to the rows",
     "if rounds >= 1 and highest != rounds:",
     "if False:",
     "declared_count_disagrees"),
    ("a round with no findings is accepted",
     "if missing:",
     "if False:",
     "round_with_no_findings"),
    ("a withdrawal needs no reason",
     'if f.disposition == "withdrawn" and not f.reason:',
     "if False:",
     "withdrawn_needs_a_reason"),
    ("an unknown field is silently dropped",
     '                    raise ConfigError(\n                        f"line {number}: unknown field {name!r} on finding "',
     '                    _ = ConfigError(\n                        f"line {number}: unknown field {name!r} on finding "',
     "unknown_field_is_refused_not_ignored"),
    ("a fixed row needs no property",
     'if f.disposition == "fixed" and not f.property.strip():',
     "if False:",
     "fixed_without_a_property"),
    # NO MUTANT FOR RULE 8's OWN `.strip()`, and this is recorded rather
    # than left as an absence. It was written, and it SURVIVED: the parser
    # already strips every field value, so `not f.property` and
    # `not f.property.strip()` are the same test and neither is
    # individually load bearing. Exactly one of the two strips is needed
    # and both are kept, so a later reader tidying either one alone does
    # not open a hole. `fixed_with_a_whitespace_property` still holds as a
    # CASE; what it does not do is discriminate a mutant.
    ("--incremental suspends rule 4 as well as rule 2",
     'if f.disposition == "registered":\n            v.append(f"rule 4:',
     'if incremental:\n            pass\n        elif f.disposition == '
     '"registered":\n            v.append(f"rule 4:',
     "incremental_does_not_relax_rule_4"),
    ("--incremental suspends rule 8 as well as rule 2",
     'if f.disposition == "fixed" and not f.property.strip():',
     'if not incremental and f.disposition == "fixed" and not '
     "f.property.strip():",
     "incremental_does_not_relax_rule_8"),
    ("rule 2 is suspended even when closing",
     "    rule_2 = notes if incremental else v",
     "    rule_2 = notes",
     "mid_lane_ledger_is_refused_when_closing"),
]


def run_case(module: Path, text: str,
             flags: list[str] | None = None) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="review-rounds-") as tmp:
        ledger = Path(tmp) / "rounds.txt"
        ledger.write_text(text, encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(module), "--ledger", str(ledger),
             *(flags or [])],
            capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


def locator_checks(module: Path) -> list[str]:
    """The LOCATOR, ITC-20260802-0120, added 0.2.16.

    Not ledger CONTENT but ledger RESOLUTION, so these drive directories
    rather than files. The one that matters most is the third: a root that
    holds no ledger must be a CONFIG error and never a clean run, on the
    rule check_side_effect_guard.py already applies to an empty skills tree.
    """
    good = ("lane: L1\nrounds: 1\n\n"
            "finding: A | round=1 | ground=new | fixed | property=p\n")
    bad = ("lane: L2\nrounds: 1\n\n"
           "finding: A | round=1 | ground=new | fixed\n")
    failures: list[str] = []

    def expect(name: str, args: list[str], code: int, needle: str,
               tmp: str) -> None:
        r = subprocess.run([sys.executable, str(module), *args],
                           capture_output=True, text=True)
        out = r.stdout + r.stderr
        ok = r.returncode == code and needle in out
        print(f"  [{'ok ' if ok else 'FAIL'}] {name}: exit {r.returncode} "
              f"(expected {code}), needle "
              f"{'found' if needle in out else 'MISSING'}")
        if not ok:
            failures.append(name)
            print("      " + out.strip().replace("\n", "\n      ")[:400])

    with tempfile.TemporaryDirectory(prefix="review-rounds-root-") as tmp:
        root = Path(tmp) / "management"
        root.mkdir()
        (root / "L1_rounds.ledger").write_text(good, encoding="utf-8")
        empty = Path(tmp) / "empty"
        empty.mkdir()
        expect("locator_by_lane", ["--root", str(root), "--lane", "L1"],
               0, "VERIFIED", tmp)
        expect("locator_lane_with_no_ledger",
               ["--root", str(root), "--lane", "L9"], 2,
               "The convention is", tmp)
        expect("locator_root_with_no_ledger_is_a_config_error",
               ["--root", str(empty), "--all"], 2,
               "An audit that examined nothing", tmp)
        expect("locator_root_that_is_not_a_directory",
               ["--root", str(root / "nope"), "--all"], 2,
               "is not a directory", tmp)
        (root / "L2_rounds.ledger").write_text(bad, encoding="utf-8")
        expect("locator_all_refuses_when_any_ledger_is_refused",
               ["--root", str(root), "--all"], 1,
               "2 ledger(s) checked, 1 refused", tmp)
        expect("locator_needs_exactly_one_of_lane_or_all",
               ["--root", str(root)], 2, "exactly one of the two", tmp)
        expect("ledger_and_root_are_not_combined",
               ["--ledger", str(root / "L1_rounds.ledger"),
                "--root", str(root), "--all"], 2,
               "do not combine it", tmp)
    return failures


def main() -> int:
    if not MODULE.is_file():
        print(f"CONFIG: {MODULE} not found beside this file", file=sys.stderr)
        return 2
    print(f"check_review_rounds guard evidence, {len(CASES)} cases, "
          f"{len(MUTANTS)} mutants")
    failed = []
    for entry in CASES:
        name, text, code, needle = entry[:4]
        flags = list(entry[4]) if len(entry) > 4 else []
        got, out = run_case(MODULE, text, flags)
        ok = got == code and needle in out
        print(f"  [{'ok ' if ok else 'FAIL'}] {name}: exit {got} "
              f"(expected {code}), needle {'found' if needle in out else 'MISSING'}")
        if not ok:
            failed.append(name)
            print("      " + out.strip().replace("\n", "\n      ")[:600])
    failed += locator_checks(MODULE)
    if failed:
        print(f"\n{len(failed)} case(s) failed on the real module; the "
              "mutants are not run, because a mutation result over a broken "
              "baseline says nothing.")
        return 1

    source = MODULE.read_text(encoding="utf-8")
    survivors: list[str] = []
    crash_denials: list[str] = []
    with tempfile.TemporaryDirectory(prefix="review-rounds-mutants-") as tmp:
        for i, (label, old, new, case_name) in enumerate(MUTANTS):
            if source.count(old) != 1:
                print(f"  [FAIL] mutant {i} ({label}): the text it replaces "
                      f"occurs {source.count(old)} times, not once")
                survivors.append(label)
                continue
            mutant = Path(tmp) / f"mutant_{i}.py"
            mutant.write_text(source.replace(old, new), encoding="utf-8")
            entry = next(e for e in CASES if e[0] == case_name)
            text, code, needle = entry[1:4]
            flags = list(entry[4]) if len(entry) > 4 else []
            got, out = run_case(mutant, text, flags)
            denied = not (got == code and needle in out)
            # A mutant detected only because the mutated body CRASHED is
            # weaker evidence than one detected by a changed verdict: the
            # case proves the line is load bearing, not that the check is
            # what produced the refusal. Named rather than hidden, because
            # this kit already corrected a mutant criterion that counted a
            # crash as a detection without saying so.
            kind = "crash" if "Traceback" in out else "verdict"
            if denied:
                crash_denials.append(label) if kind == "crash" else None
            print(f"  [{'denied ' if denied else 'SURVIVED'}] {label} "
                  f"-> {case_name} gave exit {got} (expected {code}), "
                  f"by {kind}")
            if not denied:
                survivors.append(label)

    if survivors:
        print(f"\n{len(survivors)} mutant(s) SURVIVED: {survivors}")
        return 1
    print(f"\nAll {len(CASES)} ledger cases and 7 locator checks hold, and "
          f"all {len(MUTANTS)} mutants are denied. The guard can still fail.")
    if crash_denials:
        print(f"{len(crash_denials)} of them were denied BY A CRASH rather "
              f"than by a changed verdict: {crash_denials}. That proves the "
              "line is load bearing and does not prove the check is what "
              "produced the refusal. Stated rather than counted silently.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
