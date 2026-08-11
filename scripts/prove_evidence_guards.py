"""Mutation battery for the evidence guards, committed so the claim is checkable.

A reviewer refused to accept "eight mutants died and two controls
survived" on 2026-08-11, correctly: the battery lived in a scratch
directory, so the claim had nothing reproducible behind it and the
reviewer had to rebuild one to check it. This is that battery, in the
repository, runnable.

Every mutant is a real regression of a guard added or repaired on
2026-08-11: each edits one line of source, runs the test written for
it, and expects a FAILURE. The two controls edit prose and expect a
PASS, because a battery in which everything dies is one whose selection
is broken rather than one whose guards are strong.

The tree is restored in a finally block and from a backup copy under
.git/, because a battery killed mid-run once left two mutations behind
in this repository (PLN-20260806-1400).

    python scripts/prove_evidence_guards.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON = REPO / ".venv" / "Scripts" / "python.exe"
BACKUP = REPO / ".git" / "evidence-guard-mutation-backup"

PROBES = "src/pyflightstream/qa/probes.py"
REFERENCE = "src/pyflightstream/reference.py"
SPECS = "src/pyflightstream/qa/specs.py"
COMPAT = "src/pyflightstream/qa/compat.py"

MUTANTS = [
    # --- the two that survived round one -------------------------------
    (
        "SURVIVED R1: reference citation reads probe_ref alone",
        REFERENCE,
        'citation = record.probe_ref or (record.report if record.status is Status.REMOVED else "")',
        "citation = record.probe_ref",
        "tests/test_reference.py",
        "machine_promoted_removal_shows_its_run",
        True,
    ),
    (
        "SURVIVED R1: halt guard narrowed to the target case",
        PROBES,
        "    if spec.expects_halt and not refused:",
        "    if spec.expects_halt and spec.command not in refused:",
        "tests/test_qa_probes.py",
        "prelude_hits_an_absent_command",
        True,
    ),
    # --- the three unguarded discriminators ----------------------------
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
        "detector accepts an unquoted third field",
        PROBES,
        r"'(?P<line>[^']+)'\s*\|\s*Unrecognized command",
        r"'?(?P<line>[^'|]+)'?\s*\|\s*Unrecognized command",
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
    # --- the two blocking API repairs ----------------------------------
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
        "the Syntax channel is not checked",
        PROBES,
        r'r"ERROR\s*\|\s*Syntax',
        r'r"ERROR\s*\|\s*\w+',
        "tests/test_qa_probes.py",
        "each_discriminator_alone",
        True,
    ),
    (
        "the phrase is matched by its first word only",
        PROBES,
        r"\s*\|\s*Unrecognized command",
        r"\s*\|\s*Unrecognized",
        "tests/test_qa_probes.py",
        "each_discriminator_alone",
        True,
    ),
    (
        "the flow scalar stops escaping",
        COMPAT,
        "    return json.dumps(str(value))",
        "    return chr(34) + str(value) + chr(34)",
        "tests/test_qa_compat.py",
        "backslash_survives_a_yaml_round_trip",
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
    # --- negative controls, on a different axis from round one ---------
    (
        "CONTROL: a test docstring word changes",
        PROBES,
        "Command names the solver refused as unrecognised, from its crash log.",
        "Command names the solver refused as unrecognized, from its crash log.",
        "tests/test_qa_probes.py",
        "",
        False,
    ),
    (
        "CONTROL: a numeric literal in a comment changes",
        PROBES,
        "#: 26.122 records ``'SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE'`` in",
        "#: 26.121 records ``'SET_JET_WAKE_FILAMENTS_GRID_INDUCTION ENABLE'`` in",
        "tests/test_qa_probes.py",
        "",
        False,
    ),
]


def run(test_file: str, selector: str) -> tuple[str, str]:
    """Return (verdict, tail) for one test selection.

    A collection error is INCONCLUSIVE rather than a kill: a mutant
    that stops the suite from importing proves nothing about the guard.
    """
    argv = [str(PYTHON), "-m", "pytest", test_file, "-q"]
    if selector:
        argv += ["-k", selector]
    process = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, timeout=900)
    out = process.stdout + process.stderr
    tail = " | ".join(line for line in out.splitlines()[-3:] if line.strip())
    if "error" in out.lower() and " passed" not in out and " failed" not in out:
        return "INCONCLUSIVE", tail
    if " failed" in out:
        return "FAILED", tail
    if " passed" in out:
        return "passed", tail
    return "INCONCLUSIVE", tail


if BACKUP.exists():
    shutil.rmtree(BACKUP)
BACKUP.mkdir(parents=True)
touched = {path for _, path, *_ in MUTANTS}
for rel in touched:
    shutil.copy2(REPO / rel, BACKUP / rel.replace("/", "__"))


def restore() -> None:
    """Put every touched file back from the backup copy."""
    for rel in touched:
        shutil.copy2(BACKUP / rel.replace("/", "__"), REPO / rel)


problems = []
offered = ran = 0
try:
    for label, rel, old, new, test_file, selector, should_die in MUTANTS:
        offered += 1
        path = REPO / rel
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            problems.append(f"{label}: anchor matched {text.count(old)} times, NOT APPLIED")
            print(f"  {label:52} ANCHOR MISS ({text.count(old)})")
            continue
        ran += 1
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        verdict, tail = run(test_file, selector)
        restore()
        expected = "FAILED" if should_die else "passed"
        mark = "ok" if verdict == expected else "UNEXPECTED"
        if verdict != expected:
            problems.append(f"{label}: expected {expected}, got {verdict}. {tail}")
        print(f"  {label:52} {verdict:14} {mark}")
finally:
    restore()

print(f"\noffered {offered}, applied {ran}")
if problems:
    print("PROBLEMS:")
    for line in problems:
        print(f"  {line}")
    sys.exit(1)
print("every mutant behaved as predicted")
