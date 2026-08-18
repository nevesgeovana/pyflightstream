"""Mutation battery for the evidence guards, committed so the claim is checkable.

A reviewer refused to accept "eight mutants died and two controls
survived" on 2026-08-11, correctly: the battery lived in a scratch
directory, so the claim had nothing reproducible behind it and the
reviewer had to rebuild one to check it. This is that battery, in the
repository, runnable.

Every mutant is a real regression of a guard added or repaired on
2026-08-11: each edits one line of source, runs the test written for
it, and expects a FAILURE. The controls edit prose and expect a PASS,
because a battery in which everything dies is one whose selection is
broken rather than one whose guards are strong.

Parking, recovery, the git directory and the interpreter come from
``_mutation_harness``, which the sibling battery also uses. The first
version of this file re-implemented all four and got three of them
wrong; the shared module's docstring records which three.

    python scripts/prove_evidence_guards.py [label prefix ...]
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _mutation_harness import PYTHON, REPO, park, recover, unpark  # noqa: E402

PROBES = "src/pyflightstream/qa/probes.py"
REFERENCE = "src/pyflightstream/reference.py"
SPECS = "src/pyflightstream/qa/specs.py"
COMPAT = "src/pyflightstream/qa/compat.py"
#: The renderer moved out of `qa/compat.py` on 2026-08-17, below every
#: layer, because a second writer sits BELOW qa and could not reach it.
#: Two mutants below followed it; a third followed the guard that moved
#: with it. Anchors that stay behind mutate nothing and score anyway.
YAMLFLOW = "src/pyflightstream/_yamlflow.py"

SUITE_TIMEOUT = 600.0

MUTANTS = [
    # --- the two that survived the round-one battery -------------------
    (
        "reference citation reads probe_ref alone",
        REFERENCE,
        'citation = record.probe_ref or (record.report if record.status is Status.REMOVED else "")',
        "citation = record.probe_ref",
        "tests/test_reference.py",
        "machine_promoted_removal_shows_its_run",
        True,
    ),
    (
        "halt guard narrowed to the target case",
        PROBES,
        "    if spec.expects_halt and not refused:",
        "    if spec.expects_halt and spec.command not in refused:",
        "tests/test_qa_probes.py",
        "prelude_hits_an_absent_command",
        True,
    ),
    # --- the four discriminators of the refusal pattern ----------------
    (
        "detector accepts any level, not ERROR",
        PROBES,
        r'r"ERROR\s*\|\s*Syntax',
        r'r"\w+\s*\|\s*Syntax',
        "tests/test_qa_probes.py",
        "each_discriminator_alone",
        True,
    ),
    (
        "detector accepts any channel, not Syntax",
        PROBES,
        r'r"ERROR\s*\|\s*Syntax',
        r'r"ERROR\s*\|\s*\w+',
        "tests/test_qa_probes.py",
        "each_discriminator_alone",
        True,
    ),
    (
        "detector accepts an unquoted third field",
        PROBES,
        r"'(?P<line>[^']+)'\s*\|\s*Unrecognized command",
        r"'?(?P<line>[^'|]+)'?\s*\|\s*Unrecognized command",
        "tests/test_qa_probes.py",
        "each_discriminator_alone",
        True,
    ),
    (
        "detector matches the phrase by its first word",
        PROBES,
        r"\s*\|\s*Unrecognized command",
        r"\s*\|\s*Unrecognized",
        "tests/test_qa_probes.py",
        "each_discriminator_alone",
        True,
    ),
    (
        "detector drops the case normalisation",
        PROBES,
        "            names.add(tokens[0].upper())",
        "            names.add(tokens[0])",
        "tests/test_qa_probes.py",
        "lower_case_echo",
        True,
    ),
    # --- the timeout lean and the family prelude -----------------------
    (
        "timeout swallows a measured removal",
        PROBES,
        "    if execution.timed_out and not refused:",
        "    if execution.timed_out:",
        "tests/test_qa_probes.py",
        "timed_out_run_whose_log_names",
        True,
    ),
    (
        "shared motion prelude flipped to 6DOF",
        SPECS,
        '_MOTION_PRELUDE = _emit("CREATE_NEW_MOTION", "ROTARY")',
        '_MOTION_PRELUDE = _emit("CREATE_NEW_MOTION", "6DOF")',
        "tests/test_qa_probes.py",
        "shared_motion_prelude_stays_rotary",
        True,
    ),
    # --- the promotion path --------------------------------------------
    (
        "Judgment accepts positional construction again",
        COMPAT,
        "@dataclass(frozen=True, kw_only=True)\nclass Judgment:",
        "@dataclass(frozen=True)\nclass Judgment:",
        "tests/test_qa_compat.py",
        "judgment_cannot_be_built_positionally",
        True,
    ),
    (
        "the flow scalar stops escaping",
        YAMLFLOW,
        "    return json.dumps(str(value))",
        "    return chr(34) + str(value) + chr(34)",
        "tests/test_yamlflow.py",
        "round_trips",
        True,
    ),
    (
        "the emitter interpolates a value raw again",
        YAMLFLOW,
        '        f"{key}: {value if key in RAW_KEYS else flow_scalar(value)}"'
        " for key, value in pairs.items()",
        '        f"{key}: " + chr(34) + str(value) + chr(34)',
        "tests/test_yamlflow.py",
        "round_trips",
        True,
    ),
    (
        "a rendering site escapes the emitter again",
        COMPAT,
        "    return f'{indent}\"{canonical}\": {_flow_mapping(pairs)}'",
        "    return f'{indent}\"{canonical}\": BROKEN'",
        "tests/test_qa_compat.py",
        "promotes_citing_the_report",
        True,
    ),
    (
        "the rewrite parse leaves the try again",
        COMPAT,
        "    try:\n        data = yaml.safe_load(text)",
        "    data = yaml.safe_load(text)\n    try:\n        pass",
        "tests/test_qa_compat.py",
        "unparsable_rewrite_refuses",
        True,
    ),
    (
        "the schema refusal escapes as pydantic again",
        COMPAT,
        "        except ValueError as error:",
        "        except ZeroDivisionError as error:",
        "tests/test_qa_compat.py",
        "refuses_in_this_modules_type",
        True,
    ),
    (
        "the insert path drops the removed note",
        COMPAT,
        "    recorded = [",
        "    fields = fields.replace(', note:', ', unused:')\n    recorded = [",
        "tests/test_qa_compat.py",
        "inserted_at_its_release_position",
        True,
    ),
    (
        "the args guard is deleted and only the schema catches it",
        COMPAT,
        '        if existing.get("args") is not None:',
        "        if False:",
        "tests/test_qa_compat.py",
        "compat_guard_and_not_the_schema_backstop",
        True,
    ),
    # --- negative controls, on two different axes ----------------------
    # Negative controls. A prose-only control cannot fail, since no test
    # asserts on comment text, so it has no discriminating power and the
    # first version of this battery shipped two of them. These are
    # EQUIVALENT CODE: real edits that change no behaviour, so a suite
    # that fails on them is over-pinned rather than strong.
    (
        "CONTROL: an emptiness test is spelled the other way",
        PROBES,
        "    if not log_text:\n        return frozenset()",
        '    if log_text is None or log_text == "":\n        return frozenset()',
        "tests/test_qa_probes.py",
        "",
        False,
    ),
    (
        "CONTROL: an inequality is spelled the other way",
        COMPAT,
        "        if judgment.report != incoming.report",
        "        if not judgment.report == incoming.report",
        "tests/test_qa_compat.py",
        "",
        False,
    ),
]


def run(test_file: str, selector: str) -> tuple[str, str]:
    """Return (verdict, tail) for one test selection.

    A collection error is INCONCLUSIVE rather than a kill: a mutant that
    stops the suite from importing proves nothing about the guard. So is
    a timeout, and it is reported rather than retried.
    """
    argv = [str(PYTHON), "-m", "pytest", test_file, "-q"]
    if selector:
        argv += ["-k", selector]
    try:
        # env= is explicit and identical to the inherited default: the child
        # is pytest and needs this interpreter's own environment. The point is
        # that the inheritance is chosen here rather than defaulted.
        done = subprocess.run(
            argv,
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=SUITE_TIMEOUT,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return "INCONCLUSIVE", f"timed out after {SUITE_TIMEOUT:.0f}s"
    out = done.stdout + done.stderr
    tail = " | ".join(line for line in out.splitlines()[-3:] if line.strip())
    if "error" in out.lower() and " passed" not in out and " failed" not in out:
        return "INCONCLUSIVE", tail
    if " failed" in out:
        return "FAILED", tail
    if " passed" in out:
        return "passed", tail
    return "INCONCLUSIVE", tail


def main() -> int:
    """Run the battery and report; non-zero when anything is unexpected."""
    wanted = sys.argv[1:]

    stranded = recover()
    if stranded:
        print("RECOVERED mutations a previous run was killed in the middle of:")
        for name in stranded:
            print(f"  {name}")
        print("Re-run from a clean tree.")
        return 1

    selected = [m for m in MUTANTS if not wanted or any(m[0].startswith(w) for w in wanted)]
    if not selected:
        print(f"no mutant matches {wanted}; refusing to report a proof of nothing")
        return 1

    problems: list[str] = []
    for label, rel, old, new, test_file, selector, should_die in selected:
        path = REPO / rel
        original = path.read_bytes()
        # Normalised for MATCHING, and the file's own convention is put
        # back on write. A multi-line anchor written with a newline
        # escape matches nothing in a CRLF file, and the failure looks
        # exactly like a stale anchor: this battery reported three
        # ANCHOR MISSes that way before the normalisation went in.
        crlf = b"\r\n" in original
        text = original.decode("utf-8").replace("\r\n", "\n")
        if text.count(old) != 1:
            problems.append(f"{label}: anchor matched {text.count(old)} times, NOT APPLIED")
            print(f"  {label:52} ANCHOR MISS ({text.count(old)})")
            continue
        park(path, original)
        try:
            mutated = text.replace(old, new, 1)
            if crlf:
                mutated = mutated.replace("\n", "\r\n")
            path.write_bytes(mutated.encode("utf-8"))
            verdict, tail = run(test_file, selector)
        finally:
            path.write_bytes(original)
            unpark(path)
        expected = "FAILED" if should_die else "passed"
        mark = "ok" if verdict == expected else "UNEXPECTED"
        if verdict != expected:
            problems.append(f"{label}: expected {expected}, got {verdict}. {tail}")
        print(f"  {label:52} {verdict:14} {mark}")

    print(f"\noffered {len(MUTANTS)}, ran {len(selected)}")
    if problems:
        print("PROBLEMS:")
        for line in problems:
            print(f"  {line}")
        return 1
    print("every mutant behaved as predicted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
