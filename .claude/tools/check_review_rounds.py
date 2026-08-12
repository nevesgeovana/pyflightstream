# ITACA / pyflightstream shared process kit
# kit-version: 0.2.16
# artifact: check_review_rounds.py
# body-sha256: b09fdec02dc0674a540bb5429c6343a8d4b7747fc286232dcb54f9b6e4508c4e
# canonical-source: BUILT for the kit (0.2.15, HUB-11) as the mechanism for the recursion cap that review-policy.md has stated since 0.2.7 and nothing enforced. Its load-bearing rule comes from lane ITA-4, whose round-one FIXES were themselves defective: six guards did not guard, one false-fired, and it introduced a fresh defect in the same commit that guarded the old one, all of it seen only by round two. A flat two-rounds-then-register cap would have shipped every one of them. Records: coordination/DESIGN_HUB-11_kit_batch.md item 4. 0.2.16 adds RULE 8, a fixed row must carry a property= sentence stating the invariant the fix establishes (the author's adoption of ITA-11's proposal), and the LOCATOR: --root with --lane or --all resolving <root>/<lane>_rounds.ledger, plus --incremental for a mid-lane read (ITC-20260802-0120). No environment variable is added; that unset branch is the author's call. See coordination/DESIGN_HUB-12_kit_batch.md items 5 and 8.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""The two-round review cap, and what a round-two finding actually is.

Usage:
    python check_review_rounds.py --ledger <path>            [--incremental]
    python check_review_rounds.py --root <dir> --lane <id>   [--incremental]
    python check_review_rounds.py --root <dir> --all         [--incremental]

Exit codes: 0 clean, 1 a violation, 2 configuration error.

THE LOCATOR
-----------

Added 0.2.16, from ``ITC-20260802-0120``, the round ledger has no locator so
nothing can check it. At 0.2.15 this checker was vendored, drift-pinned and
mutation-proven, and NOTHING in any repository applied it to a ledger. A
skill instructed an operator to run it, which is an instruction rather than a
mechanism, and both libraries hold the rule that documentation is not a
guard. So the two-round cap was installed and unmeasured.

THE CONVENTION, and it is recorded rather than invented::

    <root>/<lane>_rounds.ledger

That is what the format's first consumer wrote, unprompted, before this
resolver existed. A convention a lane reached for on its own is better
evidence than one a checker asks for.

WHAT THIS DELIBERATELY DOES NOT DO: it adds NO environment variable and
reads none. The incident is explicit that a fourth member of the locator
family means deciding what its UNSET branch does and writing the charter row
for it, and that the decision is the author's. So the CALLER passes the root,
exactly as ``prepush_receipt.py`` takes its repository from the caller, and
each consumer's charter decides what an absent root means at its own gate.

A ROOT THAT HOLDS NO LEDGER IS A CONFIG ERROR, exit 2, never a clean run.
Same rule ``check_side_effect_guard.py`` applies to an empty skills tree: an
audit that examined nothing is a misconfiguration wearing a green verdict.

INCREMENTAL
-----------

Added 0.2.16, from the same incident's format feedback, measured by the first
lane to write a ledger: THIS CHECKER VALIDATES A CLOSING RECORD. Written
incrementally during a lane, ``rounds: 2`` with only round-one rows breaches
rule 2 twice, correctly and by construction, so a mid-lane run looks like a
broken checker to a reader who has not read the rules.

``--incremental`` suspends RULE 2 AND NOTHING ELSE, reports what it suspended
as notes, and says in its own verdict line that it is not a closing check.
Rules 1 and 3 to 8 all still run, including the load-bearing rule 4 and the
property rule 8. A mode that relaxed rule 4 would be the mechanism defeating
itself.

WHAT THIS IS FOR
----------------

``review-policy.md`` has capped reviews at two rounds since kit 0.2.7 and
nothing enforced it. The obvious mechanism is "two rounds, then register
whatever is left". THAT MECHANISM IS WRONG, and this file exists because the
evidence arrived one day before it was built.

Lane ITA-4 ran two rounds. Its round-one FIXES were themselves defective: six
guards it wrote did not guard, one false-fired on correct code, and it
introduced a fresh defect in the same commit that added the guard against the
old one, with the lane's central fix passing green on a tree that was never
built. Round two saw all of it. Under a flat count, round two would have been
register-only and every one of those would have shipped, documented as known.

So the count is not the rule. The rule is about WHAT A ROUND-TWO FINDING IS:

- a finding ABOUT A PREVIOUS ROUND'S FIX is THE FIX NOT BEING DONE. It
  belongs to the round it was found in, and it is FIXED there. It buys no
  further round and it is not deferred.
- a finding on NEW GROUND is what gets REGISTERED as a plan item, and the
  lane closes.

A fix made in the final round is verified by its own evidence, the failing
measurement before it and the passing one after, per the INERTNESS rule in
the policy. That evidence is what replaces the round the cap forbids.

THE LEDGER FORMAT
-----------------

Line oriented, ``#`` comments and blank lines ignored. Settings first, then
one row per finding::

    lane: ITA-4
    rounds: 2
    # authority: only for a third round, and it names who authorised it

    finding: FND-046 | round=1 | ground=new | fixed |
        property=the parser rejects a delimiter it cannot resolve, and every
        delimiter it accepts appears in the output verbatim
    finding: FND-054 | round=1 | ground=new          | registered
    finding: FND-101 | round=2 | ground=about:FND-046 | fixed |
        property=a nested delimiter is resolved against the innermost open
        block, not the first one
    finding: FND-102 | round=2 | ground=new          | registered
    finding: FND-103 | round=2 | ground=new          | withdrawn |
        reason=the reviewer read a stale copy of the file

Grounds: ``new``, or ``about:<id>`` naming a finding from a STRICTLY earlier
round that was ``fixed``. Dispositions: ``fixed``, ``registered``,
``withdrawn``. A ``withdrawn`` row must carry a non-empty ``reason=``, and a
``fixed`` row must carry a non-empty ``property=``.

A row may be wrapped onto following INDENTED lines, which is how a property
sentence fits without becoming unreadable.

PROPOSED, NOT SETTLED. This format was written from three lanes' data
(ITA-2B, ITA-2E, ITA-4). The next lane is entitled to correct it, and
correcting it is a kit promotion rather than a local edit.

THE RULES
---------

1. ``lane`` and ``rounds`` must be present, and ``rounds`` must be a positive
   integer.
2. ``rounds`` must equal the highest round any finding carries, and every
   round from 1 to that number must carry at least one finding. A declared
   count no row supports is a ledger disagreeing with itself, and a gap is a
   round that did not happen.
3. More than two rounds requires ``authority``, naming who authorised it.
   This is the escalation lane ITA-2E actually performed: it reached the cap,
   stopped, asked the author, and recorded her authorisation rather than
   counting a third round. A mechanism that cannot express what already
   happened would be refused by the first lane that met it.
4. THE LOAD-BEARING RULE. A finding whose ground is ``about:<id>`` may not be
   ``registered``. It is the previous round's fix not being done.
5. An ``about:<id>`` must resolve: the id must exist in this ledger, at a
   strictly earlier round, and must have been ``fixed``. A reference to a
   registered or withdrawn finding is not a finding about a FIX.
6. A finding id may appear once. A repeated id silently replaces a verdict.
7. The ledger must carry at least one finding. An empty ledger certifying a
   review is the vacuous pass this class of guard exists to refuse.
8. A ``fixed`` finding must carry a non-empty ``property=``: ONE SENTENCE
   STATING THE INVARIANT THE FIX ESTABLISHES, written BEFORE the edit.

RULE 8, AND WHAT IT CANNOT DO
-----------------------------

Added 0.2.16, the author's adoption of lane ITA-11's proposal. The evidence
is unusually direct, because the lane that proposed it is the lane that
demonstrated the failure, four times, and in each of the four THE INVARIANT
WRITTEN AS A SENTENCE CONTAINS THE DEFECT INSIDE IT:

- a guard repaired from substring to parsed proved the right PROGRAM runs
  and not that it measures THIS tree, so ``--repo /tmp/elsewhere`` was
  accepted. The sentence, "the wrapper is the vendored receipt gating THIS
  repository's tree under a label unique to the hook", contains the defect;
- a commit-tier marker whose whole purpose is to admit a test to a gate was
  admitted to a gate that did not MEASURE it, found independently by all
  three lenses. The sentence, "a test admitted by `fast` is measured by the
  budget of the tier it joined", is again the defect stated;
- the repair of that repair matched a word instead of the condition one line
  later, so an unmarked test whose parametrize id was `slow` was exempt;
- a cost figure was asserted twice from methods that could not resolve it.

IT IS A PRESENCE CHECK, in exactly the words the attestation uses about
itself: it proves a SENTENCE EXISTS, not that it is a good sentence. Nothing
here reads the property, compares it to the diff, or knows when it was typed.
THE GAIN IS AT THE MOMENT OF WRITING, which is the only moment at which
stating an invariant can change what gets built. A checker claiming more than
that would be the defect this rule exists to catch, one level up.

ONLY ``fixed`` NEEDS ONE. A ``registered`` finding has no fix and therefore
no invariant to state; a ``withdrawn`` one already carries a required
``reason=``. Requiring a property of all three would produce a field written
to satisfy a checker, which is how a record starts being worked around.

WHAT THIS DOES NOT DO
---------------------

It does not read the review and cannot know whether a finding was classified
honestly. It checks that the lane's own record is internally consistent,
which is the half a machine can hold.

ONE ESCAPE IS NAMED RATHER THAN CLOSED. A lane can mark an ``about:`` finding
``withdrawn`` with a reason and escape rule 4. Nothing here can tell a real
withdrawal from a convenient one. The reason is required so that the claim is
at least WRITTEN, in the record a reader opens, rather than being made
silently. A lane using it to escape rule 4 has defeated the mechanism, not
passed it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

USAGE = (
    "usage: check_review_rounds.py --ledger <path> [--incremental]\n"
    "       check_review_rounds.py --root <dir> --lane <id> [--incremental]\n"
    "       check_review_rounds.py --root <dir> --all [--incremental]"
)

DISPOSITIONS = ("fixed", "registered", "withdrawn")
SETTINGS = ("lane", "rounds", "authority")
CAP = 2
# THE ONE FILENAME CONVENTION. See THE LOCATOR in the module docstring.
SUFFIX = "_rounds.ledger"


class ConfigError(Exception):
    """The check could not run. Never reported as a clean ledger."""


@dataclass
class Finding:
    ident: str
    line: int
    round: int | None = None
    ground: str | None = None
    disposition: str | None = None
    reason: str = ""
    property: str = ""
    raw: str = ""


@dataclass
class Ledger:
    settings: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)


def parse(path: Path) -> Ledger:
    """Read the ledger. A row this cannot understand is a VIOLATION later,
    never a row silently dropped."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    ledger = Ledger()
    # A row may be wrapped onto a following indented line, so joined first.
    joined: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[:1].isspace() and joined:
            joined[-1] = (joined[-1][0], joined[-1][1] + " " + raw.strip())
            continue
        joined.append((number, raw.strip()))
    for number, line in joined:
        key, _, rest = line.partition(":")
        key = key.strip().lower()
        if key in SETTINGS:
            ledger.settings[key] = rest.strip()
            continue
        if key != "finding":
            raise ConfigError(
                f"line {number}: unknown line {line!r}; expected one of "
                f"{SETTINGS} or a finding row"
            )
        parts = [p.strip() for p in rest.split("|")]
        ident = parts[0]
        finding = Finding(ident=ident, line=number, raw=line)
        for part in parts[1:]:
            if not part:
                continue
            if "=" in part:
                name, _, value = part.partition("=")
                name = name.strip().lower()
                value = value.strip()
                if name == "round":
                    finding.round = int(value) if value.isdigit() else None
                elif name == "ground":
                    finding.ground = value
                elif name == "reason":
                    finding.reason = value
                elif name == "property":
                    finding.property = value
                else:
                    # An unknown field is refused rather than ignored. A
                    # ledger whose fields are silently dropped produces a
                    # clean verdict over less than it was given, which is
                    # this level's own most repeated failure.
                    raise ConfigError(
                        f"line {number}: unknown field {name!r} on finding "
                        f"{ident!r}; expected round, ground, property or "
                        "reason"
                    )
            elif part in DISPOSITIONS:
                finding.disposition = part
            else:
                finding.disposition = finding.disposition or f"?{part}"
        ledger.findings.append(finding)
    return ledger


def check(ledger: Ledger, incremental: bool = False) -> tuple[list[str],
                                                             list[str]]:
    """Every violation, in the order the rules are numbered.

    Returns ``(violations, notes)``. Notes are never violations and never
    change the exit status; they exist for ``--incremental``, where rule 2
    is expected to be unsatisfiable and saying nothing would be worse than
    saying so. See the INCREMENTAL section of the module docstring.
    """
    v: list[str] = []
    notes: list[str] = []
    lane = ledger.settings.get("lane", "")
    rounds_raw = ledger.settings.get("rounds", "")
    if not lane:
        v.append("rule 1: no `lane` setting; the ledger does not say what it "
                 "certifies. Add `lane: <id>`.")
    rounds = int(rounds_raw) if rounds_raw.isdigit() else 0
    if rounds < 1:
        v.append(f"rule 1: `rounds` is {rounds_raw!r}, not a positive "
                 "integer. Add `rounds: <n>` naming how many review rounds "
                 "ran.")

    if not ledger.findings:
        v.append("rule 7: the ledger carries no finding row, so it certifies "
                 "nothing. A review with no findings is recorded as a finding "
                 "row with `ground=new` and `withdrawn`, or it is not "
                 "recorded here at all.")
        return v, notes

    seen: dict[str, Finding] = {}
    for f in ledger.findings:
        if not f.ident:
            v.append(f"line {f.line}: a finding row with no id. Write "
                     "`finding: <id> | round=<n> | ground=<new|about:id> | "
                     "<disposition>`.")
            continue
        if f.ident in seen:
            v.append(f"rule 6: finding id {f.ident!r} appears twice, at lines "
                     f"{seen[f.ident].line} and {f.line}. Give the second one "
                     "its own id; a repeated id silently replaces a verdict.")
            continue
        seen[f.ident] = f
        if f.round is None or f.round < 1:
            v.append(f"line {f.line}: finding {f.ident} has no usable "
                     "`round=`. Write `round=1` for the first review round.")
        if f.disposition not in DISPOSITIONS:
            v.append(f"line {f.line}: finding {f.ident} has disposition "
                     f"{f.disposition!r}; expected one of {DISPOSITIONS}. "
                     "Add the disposition as a bare word in its own field.")
        if not f.ground:
            v.append(f"line {f.line}: finding {f.ident} has no `ground=`. "
                     "Write `ground=new`, or `ground=about:<id>` naming the "
                     "earlier finding whose FIX this one is about.")
        elif f.ground != "new" and not f.ground.startswith("about:"):
            v.append(f"line {f.line}: finding {f.ident} has ground "
                     f"{f.ground!r}; expected `new` or `about:<id>`.")
        if f.disposition == "fixed" and not f.property.strip():
            v.append(f"line {f.line}: finding {f.ident} is `fixed` with no "
                     "`property=`. Write one sentence stating the INVARIANT "
                     "the fix establishes, before making the edit. Add "
                     "`property=<the invariant the fix must establish>`. "
                     "Only `fixed` needs one: a `registered` finding has no "
                     "fix and therefore no invariant, and a `withdrawn` one "
                     "already carries `reason=`.")
        if f.disposition == "withdrawn" and not f.reason:
            v.append(f"line {f.line}: finding {f.ident} is `withdrawn` with "
                     "no `reason=`. A withdrawal is the one disposition this "
                     "checker cannot police, so it must at least be written "
                     "down. Add `reason=<why it was not real>`.")

    # RULE 2 IS THE ONE `--incremental` SUSPENDS, and only this one. Both of
    # its halves compare the DECLARED count against the rows present, which
    # a ledger being written during a lane cannot satisfy: `rounds: 2` with
    # only round-one rows breaches it twice, correctly and by construction.
    # Measured by the format's first consumer. Under --incremental they
    # become notes, so a mid-lane run reports what is still missing instead
    # of looking like a broken checker.
    rule_2 = notes if incremental else v
    highest = max((f.round or 0) for f in ledger.findings)
    if rounds >= 1 and highest != rounds:
        rule_2.append(f"rule 2: `rounds: {rounds}` but the highest round on "
                      f"any finding is {highest}. The declared count and the "
                      "rows disagree; correct whichever is wrong.")
    if rounds >= 1:
        present = {f.round for f in ledger.findings}
        missing = [n for n in range(1, rounds + 1) if n not in present]
        if missing:
            rule_2.append(f"rule 2: round(s) {missing} carry no finding. A "
                          "round that found nothing did not happen; lower "
                          "`rounds` or record what it found.")
    if rounds > CAP and not ledger.settings.get("authority"):
        v.append(f"rule 3: {rounds} rounds exceeds the cap of {CAP} and no "
                 "`authority` is named. The cap is two rounds; a third exists "
                 "only when someone authorised it. Add "
                 "`authority: <who authorised it, and when>`, or fold the "
                 "third round's findings into round 2 as `about:` fixes.")

    for f in ledger.findings:
        if not f.ground or not f.ground.startswith("about:"):
            continue
        target_id = f.ground[len("about:"):].strip()
        target = seen.get(target_id)
        if target is None or target is f:
            v.append(f"rule 5: finding {f.ident} is `about:{target_id}`, "
                     "which is not a finding in this ledger. An `about:` "
                     "names the EARLIER finding whose fix this one is about; "
                     "if it is not about a fix, write `ground=new`.")
            continue
        if target.round is not None and f.round is not None \
                and target.round >= f.round:
            v.append(f"rule 5: finding {f.ident} (round {f.round}) is "
                     f"`about:{target_id}`, which is round {target.round}. "
                     "An `about:` names a STRICTLY earlier round; two "
                     "findings in one round are both `ground=new`.")
        elif target.disposition != "fixed":
            v.append(f"rule 5: finding {f.ident} is `about:{target_id}`, "
                     f"which was {target.disposition!r} rather than `fixed`. "
                     "An `about:` is a finding about a FIX; there is no fix "
                     "here. Write `ground=new`.")
        if f.disposition == "registered":
            v.append(f"rule 4: finding {f.ident} is about "
                     f"{target_id}'s fix and is REGISTERED. That is the "
                     "previous round's fix not being done, and it belongs to "
                     "this round: fix it here, with the failing measurement "
                     "before and the passing one after. Registering it is "
                     "exactly what shipped six guards that did not guard.")
    return v, notes


def ledger_name(lane: str) -> str:
    """The one filename convention. See THE LOCATOR in the docstring."""
    return f"{lane}{SUFFIX}"


def resolve(root: Path, lane: str | None) -> list[Path]:
    """Every ledger this invocation is asking about.

    Raises ConfigError rather than returning an empty list, on the rule
    ``check_side_effect_guard.py`` already applies to an empty skills tree:
    an audit that examined nothing is a configuration error and never a
    clean run.
    """
    if not root.is_dir():
        raise ConfigError(f"{root} is not a directory. Pass --root the "
                          "directory the lane's round ledgers live in.")
    if lane is not None:
        path = root / ledger_name(lane)
        if not path.is_file():
            raise ConfigError(
                f"no ledger for lane {lane!r}: looked for {path}. The "
                f"convention is <root>/<lane>{SUFFIX}; either the lane wrote "
                "no ledger, or it wrote one under another name.")
        return [path]
    found = sorted(root.glob(f"*{SUFFIX}"))
    if not found:
        raise ConfigError(
            f"{root} holds no *{SUFFIX} file. An audit that examined nothing "
            "is a configuration error, not a clean run: either the root is "
            "wrong, or no lane in it recorded a round ledger.")
    return found


def report(path: Path, incremental: bool) -> int:
    """Check one ledger and print its verdict. 0 clean, 1 refused."""
    ledger = parse(path)
    violations, notes = check(ledger, incremental)
    lane = ledger.settings.get("lane", "(unnamed)")
    rounds = ledger.settings.get("rounds", "?")
    print(f"lane {lane}, {rounds} round(s), {len(ledger.findings)} finding(s)")
    for item in notes:
        print(f"  note (not a violation, --incremental): {item}")
    if violations:
        print(f"REFUSED: {len(violations)} violation(s)")
        for item in violations:
            print(f"  - {item}")
        return 1
    if incremental:
        print("VERIFIED SO FAR: rules 1 and 3 to 8 ran against this ledger. "
              "THIS IS NOT A CLOSING CHECK: rule 2 was suspended, so nothing "
              "here says the lane's rounds are complete. Run without "
              "--incremental to close.")
        return 0
    print("VERIFIED: rules 1 to 8 all ran against this ledger.")
    return 0


def main(argv: list[str]) -> int:
    args = argv[1:]
    incremental = "--incremental" in args
    args = [a for a in args if a != "--incremental"]

    def value(flag: str) -> str | None:
        return args[args.index(flag) + 1] if flag in args \
            and args.index(flag) + 1 < len(args) else None

    ledger_arg, root_arg, lane_arg = (value("--ledger"), value("--root"),
                                      value("--lane"))
    every = "--all" in args
    try:
        if ledger_arg is not None:
            if root_arg or lane_arg or every:
                raise ConfigError("--ledger names one file directly; do not "
                                  "combine it with --root, --lane or --all.")
            paths = [Path(ledger_arg)]
        elif root_arg is not None:
            if (lane_arg is None) == (not every):
                raise ConfigError("--root takes either --lane <id> for one "
                                  "lane or --all for every ledger under it, "
                                  "and exactly one of the two.")
            paths = resolve(Path(root_arg), lane_arg)
        else:
            print(USAGE, file=sys.stderr)
            return 2
    except ConfigError as exc:
        print(f"CONFIG: {exc}", file=sys.stderr)
        return 2

    refused = 0
    for path in paths:
        if len(paths) > 1:
            print(f"---- {path.name} ----")
        try:
            refused += report(path, incremental)
        except ConfigError as exc:
            # A CONFIG error is never reported as a clean ledger.
            print(f"CONFIG: {exc}", file=sys.stderr)
            return 2
    if len(paths) > 1:
        print(f"{len(paths)} ledger(s) checked, {refused} refused")
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
