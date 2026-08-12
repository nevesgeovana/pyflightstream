# ITACA / pyflightstream shared process kit
# kit-version: 0.2.7
# artifact: check_probe_closure.py
# body-sha256: 5b4a76ea8e94d6185cd200d0f0324e6501967d1d959c94e5a0e0f31019c142a2
# canonical-source: BUILT for the kit (0.2.7): the mechanism for the probe-closure rule stated in review-policy.md, so that guard 3 of INC-20260729-0854-shared is a check rather than a paragraph. The ledger's own rule is that documentation is not a guard.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""A probe counts as closed only if it reproduced against the pre-fix tree.

Usage:
    python check_probe_closure.py --ledger <path>

Exit codes: 0 clean, 1 a violation, 2 configuration error.

WHAT THIS IS FOR
----------------

A checkpoint closes findings by running probes. A probe reporting a finding
closed looks EXACTLY the same whether the code changed or the probe was always
inert, and nothing about a green result distinguishes them. One review round
found two tests that passed against pre-fix code: one whose fixture contained
no delimiter at all, and one that turned on a symbol neither tree imports. Both
were green and both proved nothing.

Exactly one measurement separates "the fix works" from "the probe never
worked", and it is running the probe against the tree where the defect existed.
This refuses a checkpoint that skipped it. The rule and its authority are in
``review-policy.md`` beside this file; this is its mechanism.

THE LEDGER FORMAT
-----------------

Line oriented, ``#`` comments and blank lines ignored. Three settings and then
one row per probe::

    checkpoint: CHK-1
    base: 6af2aeb
    head: 730649f

    probe: FIND-007 | base=reproduced | head=absent   | closed
    probe: FIND-012 | base=reproduced | head=reproduced | open
    probe: FIND-019 | base=absent     | head=absent   | open

``base`` is the reviewed tree the findings were raised against; ``head`` is the
tree being certified. Each probe row carries its verdict at each tree and its
disposition.

Verdicts: ``reproduced`` (the probe fired) or ``absent`` (it did not).
Dispositions: ``closed`` or ``open``.

PROPOSED, NOT SETTLED. This format was written from one checkpoint's data. The
next checkpoint is entitled to correct it, and correcting it is a kit promotion
rather than a local edit.

THE RULES
---------

1. ``base`` and ``head`` must both be present and must DIFFER. Two names for
   one commit means the distinguishing measurement was never taken, whatever
   the rows say.
2. A probe marked ``closed`` must be ``base=reproduced``. A probe that did not
   fire against the tree where the defect existed is a BROKEN PROBE; its
   finding stays open regardless of what the current tree says.
3. A probe marked ``closed`` must be ``head=absent``. A probe still firing on
   the tree being certified has not closed anything.
4. The ledger must carry at least one probe. An empty ledger certifying a
   checkpoint is the vacuous pass this whole class of guard exists to refuse.
5. A probe id may appear once. A repeated id silently replaces a verdict.

WHAT THIS DOES NOT DO
---------------------

It does not run the probes and it cannot know whether the recorded verdicts are
true. It checks that the checkpoint's own record is internally honest, which is
the half a machine can hold. The half it cannot hold is that someone actually
ran execution 1, and that is why the ledger names the base commit: a reader can
check out that commit and re-run.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

USAGE = "usage: check_probe_closure.py --ledger <path>"

VERDICTS = ("reproduced", "absent")
DISPOSITIONS = ("closed", "open")
SETTINGS = ("checkpoint", "base", "head")


class ConfigError(Exception):
    """The check could not run. Never reported as a clean ledger."""


@dataclass(frozen=True)
class Probe:
    lineno: int
    id: str
    at_base: str
    at_head: str
    disposition: str


def _field(chunk: str, key: str, lineno: int) -> str:
    name, sep, value = chunk.partition("=")
    if not sep or name.strip() != key:
        raise ConfigError(
            f"line {lineno}: expected {key}=<verdict> and found {chunk.strip()!r}"
        )
    verdict = value.strip()
    if verdict not in VERDICTS:
        raise ConfigError(
            f"line {lineno}: {key}={verdict!r} is not one of {VERDICTS}. An "
            f"unknown verdict is refused rather than read as either one: "
            f"guessing it means 'absent' closes findings nobody measured, and "
            f"guessing it means 'reproduced' reopens findings nobody reported."
        )
    return verdict


def parse(path: Path) -> tuple[dict[str, str], list[Probe]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"the ledger at {path} could not be read ({exc})") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(f"the ledger at {path} is not UTF-8 ({exc})") from exc

    settings: dict[str, str] = {}
    probes: list[Probe] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, sep, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not sep:
            raise ConfigError(f"line {lineno}: {raw.strip()!r} is not key: value")
        if key in SETTINGS:
            if key in settings:
                raise ConfigError(f"line {lineno}: {key!r} is set twice")
            if not value:
                raise ConfigError(f"line {lineno}: {key!r} has no value")
            settings[key] = value
            continue
        if key != "probe":
            raise ConfigError(
                f"line {lineno}: {key!r} is not a known key. Known: "
                f"{', '.join((*SETTINGS, 'probe'))}. A typo is refused rather "
                f"than ignored, because an ignored probe row is a finding that "
                f"silently left the ledger."
            )
        chunks = [c.strip() for c in value.split("|")]
        if len(chunks) != 4:
            raise ConfigError(
                f"line {lineno}: a probe row is "
                f"'probe: <id> | base=<verdict> | head=<verdict> | "
                f"<disposition>', and this has {len(chunks)} field(s)"
            )
        probe_id, at_base, at_head, disposition = chunks
        if not probe_id:
            raise ConfigError(f"line {lineno}: the probe has no id")
        if disposition not in DISPOSITIONS:
            raise ConfigError(
                f"line {lineno}: disposition {disposition!r} is not one of "
                f"{DISPOSITIONS}"
            )
        probes.append(
            Probe(
                lineno=lineno,
                id=probe_id,
                at_base=_field(at_base, "base", lineno),
                at_head=_field(at_head, "head", lineno),
                disposition=disposition,
            )
        )

    missing = [key for key in SETTINGS if key not in settings]
    if missing:
        raise ConfigError(
            f"{path}: the ledger does not name {missing}. The base commit is "
            f"not decoration: it is what lets a reader check out that tree and "
            f"re-run the probes, which is the half of this rule a machine "
            f"cannot hold."
        )
    return settings, probes


def check(settings: dict[str, str], probes: list[Probe]) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    closed = [p for p in probes if p.disposition == "closed"]
    report = [
        f"checkpoint {settings['checkpoint']}: base {settings['base']}, "
        f"head {settings['head']}",
        f"  {len(probes)} probe(s), {len(closed)} marked closed",
    ]

    # ---- rule 4, first, because every other rule is vacuous without it.
    if not probes:
        violations.append(
            "the ledger carries no probe at all, so it certifies nothing. An "
            "empty ledger and a clean checkpoint are indistinguishable, which "
            "is the failure this file exists to refuse."
        )

    # ---- rule 1.
    if settings["base"] == settings["head"]:
        violations.append(
            f"base and head are both {settings['base']}, so no probe was run "
            f"against a tree where the defect existed. That single measurement "
            f"is the only thing separating 'the fix works' from 'the probe "
            f"never worked', and this ledger does not contain it."
        )

    # ---- rule 5.
    seen: dict[str, int] = {}
    for probe in probes:
        if probe.id in seen:
            violations.append(
                f"line {probe.lineno}: probe {probe.id} was already recorded at "
                f"line {seen[probe.id]}. A repeated id silently replaces a "
                f"verdict, so which one certified the checkpoint is unknowable."
            )
        else:
            seen[probe.id] = probe.lineno

    # ---- rules 2 and 3.
    for probe in closed:
        if probe.at_base != "reproduced":
            violations.append(
                f"line {probe.lineno}: probe {probe.id} is marked closed but "
                f"did not reproduce against the base tree {settings['base']}. "
                f"That is a BROKEN PROBE, not a fixed defect: it proves nothing "
                f"about the current tree because it never proved anything about "
                f"the tree the finding was raised on. The finding stays open."
            )
        if probe.at_head != "absent":
            violations.append(
                f"line {probe.lineno}: probe {probe.id} is marked closed and "
                f"still reproduces at {settings['head']}."
            )

    broken = [p for p in probes if p.at_base != "reproduced"]
    report.append(
        f"  {len(broken)} probe(s) did not reproduce at the base and are "
        f"therefore not evidence about anything"
    )
    report.append(
        f"  VERIFIED: rules 1 to 5 over {len(probes)} probe row(s). NOT "
        f"VERIFIED: that the recorded verdicts are true; re-run against "
        f"{settings['base']} to check that."
    )
    return violations, report


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    opts: dict[str, str] = {}
    i = 0
    while i < len(argv):
        if not argv[i].startswith("--"):
            print(f"unrecognized argument {argv[i]!r}\n{USAGE}", file=sys.stderr)
            return 2
        if i + 1 >= len(argv):
            print(f"option {argv[i]!r} needs a value\n{USAGE}", file=sys.stderr)
            return 2
        opts[argv[i][2:]] = argv[i + 1]
        i += 2
    unknown = sorted(set(opts) - {"ledger"})
    if unknown or "ledger" not in opts:
        print(
            f"{'unknown option(s) ' + ', '.join(unknown) if unknown else '--ledger is required'}"
            f"\n{USAGE}",
            file=sys.stderr,
        )
        return 2

    try:
        path = Path(opts["ledger"]).resolve()
        if not path.is_file():
            raise ConfigError(
                f"no ledger at {path}. A checkpoint with no probe record is "
                f"not a clean checkpoint; it is an unrecorded one."
            )
        violations, report = check(*parse(path))
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2

    for line in report:
        print(line)
    sys.stdout.flush()
    if violations:
        print(f"\nREFUSED: {len(violations)} finding(s)", file=sys.stderr)
        for entry in violations:
            print(f"  - {entry}", file=sys.stderr)
        return 1
    print("\nevery closed probe reproduced against the base tree first")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
