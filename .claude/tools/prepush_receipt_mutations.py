# ITACA / pyflightstream shared process kit
# kit-version: 0.2.16
# artifact: prepush_receipt_mutations.py
# body-sha256: 228d9e359c55a0d14f2e890b7130d405d279a63273b5d6710b429844af58f633
# canonical-source: BUILT for the kit (0.2.15, HUB-11) as the guard evidence for prepush_receipt.py, per the incident policy: a guard that makes recurrence impossible, and mutation evidence that it blocks the original failure. The specification's acceptance criterion is that every unknown state RUNS, so every case here asserts a verdict rather than an exit code, and the two SKIP controls exist because a mechanism that never skips is not the mechanism. 0.2.16 adds three cases that report the VERDICT and whether a receipt exists, because the verdict alone cannot tell a receipt that was refused from one written that happens not to match, plus one compound mutant restoring both 0.2.15 lines and SAYING it is compound.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Guard evidence for prepush_receipt.py, on real git repositories.

Run:  python prepush_receipt_mutations.py

WHAT IT PROVES, and the shape is deliberate. The specification's acceptance
criterion is not "the checker is correct", it is EVERY UNKNOWN STATE RUNS.
So every case below drives the real CLI against a real git repository built
in a temporary directory, and asserts the VERDICT the operator would get:
``SKIP`` or ``WOULD RUN``. Nothing here reconstructs the digest or reasons
about the code.

SOME CASES MUST SKIP. A mechanism that never skips passes every safety case
and is worth nothing, so ``control_skip``, ``ignored_file_ignored`` and
``clean_run_still_writes_a_receipt`` are failures if they run. Every other
case is a failure if it skips.

THREE CASES REPORT TWO THINGS, added 0.2.16: the verdict AND whether a
receipt exists on disk. The verdict alone cannot tell a receipt that was
REFUSED from one that was written and happens not to match, and the
0.2.16 fix is exactly about the difference. Their expected values are
therefore strings like ``RUN, no receipt``.

THE MUTANTS. Each removes exactly one defence from a copy of the module and
names the case it must break. A mutant is DENIED when that case's verdict
flips. SCOPE, stated because it bounds the claim: a mutant runs only the
cases it names, not all of them, so this file proves that each named defence
is what produces that case's verdict, and does not prove that no other case
would also have caught it.

ONE MUTANT IS COMPOUND AND SAYS SO, added 0.2.16, because pretending
otherwise would be the thing this kit keeps catching. ``ITC-20260801-2320``
(the key recomputed after the run) and ``ITC-20260802-0620`` (a receipt
written before pre-commit's verdict) have ONE repair and ONE observable
between them: a run that moved the tree writes no receipt. Once that check
holds, the key's SOURCE is no longer independently observable, because the
check returns before the write is reached. A mutant deleting only the
pre-run key would therefore survive every case here and prove nothing. The
last mutant restores BOTH 0.2.15 lines instead, which reproduces exactly
what the incident measured: ``SKIP, receipt written``.

WHAT IT CANNOT PROVE. A perfectly forged receipt authorizes a skip, and the
module's own docstring says so. ``handwritten_receipt`` demonstrates the
realistic forgery, one written by hand with plausible fields, and not the
unrealistic one, which is a reimplementation of the digest.

Exit 0 when every case holds and every mutant is denied, 1 otherwise.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MODULE = Path(__file__).resolve().parent / "prepush_receipt.py"
RECEIPT = ".claude/.prepush_receipt.json"
# A command that is green, fast, and identical on every platform.
CMD = [sys.executable, "-c", "pass"]


def _run(args: list[str], cwd: Path | None = None,
         env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=None if cwd is None else str(cwd),
                          capture_output=True, text=True, env=env)


def _git(repo: Path, *args: str) -> None:
    r = _run(["git", "-C", str(repo), "-c", "user.name=kit",
              "-c", "user.email=kit@example.invalid", *args])
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr}")


def make_repo(base: Path) -> Path:
    """A real repository with a tracked file, an ignored one, and a commit."""
    repo = base / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "src" / "blob.bin").write_bytes(bytes(range(256)))
    (repo / ".gitignore").write_text(".claude/\nscratch/\n", encoding="utf-8")
    _git(repo, "init", "-q", ".")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "one")
    return repo


def verdict(module: Path, repo: Path, command: list[str] | None = None,
            label: str = "suite", env: dict[str, str] | None = None) -> str:
    """What the operator would be told, without running anything."""
    r = _run([sys.executable, str(module), "status", "--label", label,
              "--repo", str(repo), "--", *(command or CMD)], env=env)
    out = r.stdout + r.stderr
    if "SKIP" in out:
        return "SKIP"
    if "WOULD RUN" in out:
        return "RUN"
    return f"UNKNOWN({out.strip()[:120]})"


def prime(module: Path, repo: Path, command: list[str] | None = None,
          label: str = "suite", env: dict[str, str] | None = None) -> None:
    """Run the guard once so a receipt exists."""
    r = _run([sys.executable, str(module), "guard", "--label", label,
              "--repo", str(repo), "--", *(command or CMD)], env=env)
    if r.returncode != 0:
        raise SystemExit(f"priming failed: {r.stdout}{r.stderr}")


def receipt_of(repo: Path) -> dict:
    return json.loads((repo / RECEIPT).read_text(encoding="utf-8"))


def rewrite(repo: Path, **fields) -> None:
    record = receipt_of(repo)
    record.update(fields)
    (repo / RECEIPT).write_text(json.dumps(record, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# The cases. Each returns the verdict it produced; EXPECT says what it must be.
# --------------------------------------------------------------------------

def case_control_skip(module: Path, base: Path) -> str:
    """The one thing the mechanism is for: same tree, same command, skip."""
    repo = make_repo(base)
    prime(module, repo)
    return verdict(module, repo)


def case_ignored_file_ignored(module: Path, base: Path) -> str:
    """A gitignored file is not content under test, so it must not invalidate."""
    repo = make_repo(base)
    prime(module, repo)
    (repo / "scratch").mkdir()
    (repo / "scratch" / "noise.txt").write_text("x" * 100, encoding="utf-8")
    return verdict(module, repo)


def case_receipt_does_not_invalidate_itself(module: Path, base: Path) -> str:
    """The receipt is written into the tree it measures.

    A consumer is asked to gitignore it, but the key must not DEPEND on that:
    a repository that has not yet added the line would otherwise write a
    receipt that can never match, and the mechanism would silently do
    nothing while appearing installed. So the path is excluded by exact name
    and this case is run in a repository that does not ignore it.
    """
    repo = base / "repo"
    repo.mkdir(parents=True)
    (repo / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / ".gitignore").write_text("scratch/\n", encoding="utf-8")
    _git(repo, "init", "-q", ".")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "one")
    prime(module, repo)
    return verdict(module, repo)


def case_absent_receipt(module: Path, base: Path) -> str:
    repo = make_repo(base)
    prime(module, repo)
    # missing_ok rather than unlink(), and the reason is a finding this file
    # made against itself. A mutant that lets an ABSENT receipt authorize a
    # skip makes ``prime`` skip too, so no receipt is ever written, and a
    # bare unlink() then raised FileNotFoundError. The case still failed, but
    # it failed by CRASHING, and a mutant detected only by a crash is the
    # coarse criterion this kit already corrected once in
    # check_shipped_surface_mutations. Tolerating the absence puts the needle
    # back on the verdict.
    (repo / RECEIPT).unlink(missing_ok=True)
    return verdict(module, repo)


def case_empty_receipt(module: Path, base: Path) -> str:
    repo = make_repo(base)
    prime(module, repo)
    (repo / RECEIPT).write_text("", encoding="utf-8")
    return verdict(module, repo)


def case_truncated_receipt(module: Path, base: Path) -> str:
    repo = make_repo(base)
    prime(module, repo)
    text = (repo / RECEIPT).read_text(encoding="utf-8")
    (repo / RECEIPT).write_text(text[: len(text) // 2], encoding="utf-8")
    return verdict(module, repo)


def case_receipt_is_a_list(module: Path, base: Path) -> str:
    repo = make_repo(base)
    prime(module, repo)
    (repo / RECEIPT).write_text("[]", encoding="utf-8")
    return verdict(module, repo)


def case_foreign_format(module: Path, base: Path) -> str:
    repo = make_repo(base)
    prime(module, repo)
    rewrite(repo, receipt_version=99)
    return verdict(module, repo)


def case_records_a_failure(module: Path, base: Path) -> str:
    repo = make_repo(base)
    prime(module, repo)
    rewrite(repo, exit_status=1, outcome="fail")
    return verdict(module, repo)


def case_modified_tracked_text(module: Path, base: Path) -> str:
    repo = make_repo(base)
    prime(module, repo)
    (repo / "src" / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    return verdict(module, repo)


def case_modified_tracked_binary(module: Path, base: Path) -> str:
    """The case that rules out HEAD plus a hash of ``git diff HEAD``.

    A binary modification renders in that diff as "Binary files differ" with
    no content, so a key built that way would not move. This one must.
    """
    repo = make_repo(base)
    prime(module, repo)
    blob = bytearray((repo / "src" / "blob.bin").read_bytes())
    blob[7] ^= 0xFF
    (repo / "src" / "blob.bin").write_bytes(bytes(blob))
    return verdict(module, repo)


def case_staged_but_uncommitted(module: Path, base: Path) -> str:
    repo = make_repo(base)
    prime(module, repo)
    (repo / "src" / "a.py").write_text("VALUE = 3\n", encoding="utf-8")
    _git(repo, "add", "src/a.py")
    return verdict(module, repo)


def case_new_untracked_file(module: Path, base: Path) -> str:
    repo = make_repo(base)
    prime(module, repo)
    (repo / "src" / "b.py").write_text("VALUE = 9\n", encoding="utf-8")
    return verdict(module, repo)


def case_deleted_tracked_file(module: Path, base: Path) -> str:
    repo = make_repo(base)
    prime(module, repo)
    (repo / "src" / "a.py").unlink()
    return verdict(module, repo)


def case_different_command(module: Path, base: Path) -> str:
    """A receipt from a partial run must not authorize the full run."""
    repo = make_repo(base)
    prime(module, repo, command=[*CMD, "-X", "dev"])
    return verdict(module, repo, command=CMD)


def case_different_label(module: Path, base: Path) -> str:
    repo = make_repo(base)
    prime(module, repo, label="fast")
    return verdict(module, repo, label="suite")


def case_expired(module: Path, base: Path) -> str:
    repo = make_repo(base)
    prime(module, repo)
    rewrite(repo, written_at=time.time() - (4 * 60 * 60) - 60)
    return verdict(module, repo)


def case_dated_in_the_future(module: Path, base: Path) -> str:
    """A clock that moved backwards is an unknown state, so it runs."""
    repo = make_repo(base)
    prime(module, repo)
    rewrite(repo, written_at=time.time() + 3600)
    return verdict(module, repo)


def case_unusable_timestamp(module: Path, base: Path) -> str:
    """This one asserts the REASON, and the reason for that is a measurement.

    The timestamp type check is NOT what keeps this state from skipping. With
    it deleted, ``float("this morning")`` raises and the blanket exception
    guard runs the suite anyway, so a mutant that removes the check SURVIVED
    a verdict-only case. The check's real job is to turn a crash into a
    sentence an operator can act on, so the needle belongs on the wording.
    That is the same correction this kit made twice before: a case that
    asserts a phrase the report prints unconditionally measures nothing.
    """
    repo = make_repo(base)
    prime(module, repo)
    rewrite(repo, written_at="this morning")
    out = _run([sys.executable, str(module), "status", "--label", "suite",
                "--repo", str(repo), "--", *CMD])
    text = out.stdout + out.stderr
    if "SKIP" in text:
        return "SKIP"
    if "no usable timestamp" in text:
        return "RUN, named"
    if "evaluation failed" in text:
        return "RUN, crashed"
    return f"UNKNOWN({text.strip()[:120]})"


def case_handwritten_receipt(module: Path, base: Path) -> str:
    """The realistic forgery: plausible fields, a key nobody computed."""
    repo = make_repo(base)
    (repo / ".claude").mkdir(parents=True, exist_ok=True)
    (repo / RECEIPT).write_text(json.dumps({
        "receipt_version": 1,
        "key": "0" * 64,
        "written_at": time.time(),
        "ttl_seconds": 4 * 60 * 60,
        "command": CMD,
        "label": "suite",
        "exit_status": 0,
        "outcome": "pass",
    }, indent=2), encoding="utf-8")
    return verdict(module, repo)


def case_environment_moved(module: Path, base: Path) -> str:
    """A distribution appearing must invalidate the receipt.

    A real measurement rather than a simulated one: a dist-info directory is
    put on PYTHONPATH, so ``importlib.metadata`` genuinely reports a package
    that was not there when the receipt was written.
    """
    repo = make_repo(base)
    prime(module, repo)
    site = base / "site"
    info = site / "ghost-9.9.9.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: ghost\nVersion: 9.9.9\n",
        encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(site)
    return verdict(module, repo, env=env)


def case_mechanism_moved(module: Path, base: Path) -> str:
    """A receipt written by a different body of this file must not be honored."""
    repo = make_repo(base)
    prime(module, repo)
    moved = base / "moved_receipt.py"
    moved.write_text(module.read_text(encoding="utf-8") + "\n# promoted\n",
                     encoding="utf-8")
    return verdict(moved, repo)


def case_failing_run_discards_the_receipt(module: Path, base: Path) -> str:
    """A red run must not leave authority behind for the tree that passed.

    Sequence: pass on tree A and get a receipt; edit the tree so the key
    moves; run a command that fails, which therefore actually runs; restore
    tree A. Without the discard, the receipt for tree A is still there and
    the next push skips after a red run.
    """
    repo = make_repo(base)
    prime(module, repo)
    original = (repo / "src" / "a.py").read_text(encoding="utf-8")
    (repo / "src" / "a.py").write_text("VALUE = 4\n", encoding="utf-8")
    red = [sys.executable, "-c", "raise SystemExit(1)"]
    r = _run([sys.executable, str(module), "guard", "--label", "suite",
              "--repo", str(repo), "--", *red])
    if r.returncode != 1:
        return f"UNKNOWN(guard returned {r.returncode}, expected the child's 1)"
    (repo / "src" / "a.py").write_text(original, encoding="utf-8")
    return verdict(module, repo)


def _guard_and_report(module: Path, repo: Path, command: list[str]) -> str:
    """Run the guard, then report the verdict AND whether a receipt exists.

    The two halves are reported together because 0.2.16's fix is about both:
    the verdict alone cannot tell a receipt that was refused from a receipt
    that was written and happens not to match.
    """
    r = _run([sys.executable, str(module), "guard", "--label", "suite",
              "--repo", str(repo), "--", *command])
    if r.returncode != 0:
        return f"UNKNOWN(guard rc={r.returncode}: {(r.stdout + r.stderr)[:120]})"
    wrote = (repo / RECEIPT).is_file()
    return (f"{verdict(module, repo, command=command)}, "
            f"{'receipt written' if wrote else 'no receipt'}")


# The child writes into the tree and exits 0, which is what a pre-commit hook
# that reformats a file does, and it is the shape of ITC-20260802-0620.
CREATES = [sys.executable, "-c",
           "open('created.txt', 'w', encoding='utf-8').write('x')"]
REWRITES = [sys.executable, "-c",
            "open('src/a.py', 'w', encoding='utf-8').write('VALUE = 99\\n')"]
TOUCHES_NOTHING = [sys.executable, "-c", "pass"]


def case_run_that_creates_a_file_writes_no_receipt(module: Path,
                                                   base: Path) -> str:
    """ITC-20260801-2320 and ITC-20260802-0620, which are one fix.

    A guarded command that exits 0 and leaves an untracked, unignored file
    behind used to leave a receipt keyed on the POST-run tree, so the next
    check answered SKIP over content the suite never saw. It is also the
    shape pre-commit FAILS after the exit status, with `files were modified
    by this hook`, so the receipt made that failure intermittent.

    Both halves are refused by one rule: a run that moved the tree writes
    no receipt at all.
    """
    repo = make_repo(base)
    return _guard_and_report(module, repo, CREATES)


def case_run_that_rewrites_a_tracked_file_writes_no_receipt(
        module: Path, base: Path) -> str:
    """The same, through a TRACKED file rather than a new one.

    Both reach the content digest, and they are separate cases because a
    repair that only watched `ls-files --others` would pass the first.
    """
    repo = make_repo(base)
    return _guard_and_report(module, repo, REWRITES)


def case_clean_run_still_writes_a_receipt(module: Path, base: Path) -> str:
    """THE CONTROL, and it is what stops the fix from being "never write".

    A command that changes nothing must still leave a receipt and the next
    check must still SKIP. Without this case, deleting the receipt writer
    outright would pass every case above.
    """
    repo = make_repo(base)
    return _guard_and_report(module, repo, TOUCHES_NOTHING)


def case_not_a_repository(module: Path, base: Path) -> str:
    """Outside a repository the mechanism refuses rather than guessing."""
    loose = base / "loose"
    loose.mkdir()
    r = _run([sys.executable, str(module), "status", "--repo", str(loose),
              "--", *CMD])
    return "CONFIG" if r.returncode == 2 else f"UNKNOWN(rc={r.returncode})"


CASES: list[tuple[str, object, str]] = [
    ("control_skip", case_control_skip, "SKIP"),
    ("ignored_file_ignored", case_ignored_file_ignored, "SKIP"),
    ("receipt_does_not_invalidate_itself",
     case_receipt_does_not_invalidate_itself, "SKIP"),
    ("absent_receipt", case_absent_receipt, "RUN"),
    ("empty_receipt", case_empty_receipt, "RUN"),
    ("truncated_receipt", case_truncated_receipt, "RUN"),
    ("receipt_is_a_list", case_receipt_is_a_list, "RUN"),
    ("foreign_format", case_foreign_format, "RUN"),
    ("records_a_failure", case_records_a_failure, "RUN"),
    ("modified_tracked_text", case_modified_tracked_text, "RUN"),
    ("modified_tracked_binary", case_modified_tracked_binary, "RUN"),
    ("staged_but_uncommitted", case_staged_but_uncommitted, "RUN"),
    ("new_untracked_file", case_new_untracked_file, "RUN"),
    ("deleted_tracked_file", case_deleted_tracked_file, "RUN"),
    ("different_command", case_different_command, "RUN"),
    ("different_label", case_different_label, "RUN"),
    ("expired", case_expired, "RUN"),
    ("dated_in_the_future", case_dated_in_the_future, "RUN"),
    ("unusable_timestamp", case_unusable_timestamp, "RUN, named"),
    ("handwritten_receipt", case_handwritten_receipt, "RUN"),
    ("environment_moved", case_environment_moved, "RUN"),
    ("mechanism_moved", case_mechanism_moved, "RUN"),
    ("failing_run_discards_the_receipt",
     case_failing_run_discards_the_receipt, "RUN"),
    ("run_that_creates_a_file_writes_no_receipt",
     case_run_that_creates_a_file_writes_no_receipt, "RUN, no receipt"),
    ("run_that_rewrites_a_tracked_file_writes_no_receipt",
     case_run_that_rewrites_a_tracked_file_writes_no_receipt,
     "RUN, no receipt"),
    ("clean_run_still_writes_a_receipt",
     case_clean_run_still_writes_a_receipt, "SKIP, receipt written"),
    ("not_a_repository", case_not_a_repository, "CONFIG"),
]

# Each mutant deletes one defence and names the case that must flip.
MUTANTS: list[tuple[str, str, str, str]] = [
    ("absent receipt reads as authority",
     'if not path.is_file():\n        return False, "no receipt"',
     'if not path.is_file():\n        return True, "no receipt"',
     "absent_receipt"),
    ("the key is not compared",
     'if record.get("key") != key:',
     'if False:',
     "modified_tracked_text"),
    ("file bytes are not hashed, only path names",
     'h.update(hashlib.sha256(data).hexdigest().encode("ascii"))',
     'h.update(b"NAME-ONLY")',
     "modified_tracked_binary"),
    ("untracked files are outside the content",
     "for rel in sorted(set(tracked) | set(others)):",
     "for rel in sorted(set(tracked)):",
     "new_untracked_file"),
    ("the receipt is part of the content it measures",
     "        if rel == RECEIPT:",
     "        if False:",
     "receipt_does_not_invalidate_itself"),
    ("the environment is not in the key",
     '"environment": _environment_digest(),',
     '"environment": "",',
     "environment_moved"),
    ("the command is not in the key",
     '"command": command,\n            "label": label,',
     '"command": [],\n            "label": label,',
     "different_command"),
    ("the label is not in the key",
     '"label": label,\n            "mechanism"',
     '"label": "",\n            "mechanism"',
     "different_label"),
    ("this mechanism's own body is not in the key",
     '"mechanism": _self_body_sha256(),',
     '"mechanism": "",',
     "mechanism_moved"),
    ("the time to live is not enforced",
     "if age > TTL_SECONDS:",
     "if False:",
     "expired"),
    ("a backwards clock is accepted",
     "if age < 0:",
     "if False:",
     "dated_in_the_future"),
    ("a receipt recording a failure is accepted",
     'if record.get("outcome") != "pass" or record.get("exit_status") != 0:',
     'if False:',
     "records_a_failure"),
    ("a foreign receipt format is accepted",
     'if record.get("receipt_version") != FORMAT:',
     'if False:',
     "foreign_format"),
    ("an unusable timestamp is accepted",
     "if not isinstance(written, (int, float)) or isinstance(written, bool):",
     "if False:",
     "unusable_timestamp"),
    ("a red run leaves its predecessor's authority behind",
     "        _discard(root)\n        return status",
     "        return status",
     "failing_run_discards_the_receipt"),
    ("a run that modified the tree still writes a receipt",
     "    if after != content:",
     "    if False:",
     "run_that_creates_a_file_writes_no_receipt"),
    # THE 0.2.15 BODY RESTORED, and it is a compound mutant on purpose.
    # Recomputing the key after the run is NOT independently observable once
    # the tree-modification check holds, because that check returns before
    # the write is reached, so a mutant deleting only the pre-run key would
    # survive every case here and say nothing. Restoring BOTH lines
    # reproduces exactly what ITC-20260801-2320 measured: a receipt keyed on
    # the POST-run tree, which the tree it describes then matches, so the
    # next check answers SKIP over content the suite never saw. Recorded as
    # a compound rather than dressed up as a single-defence mutant.
    ("the 0.2.15 pair restored: no tree check, and the key recomputed after "
     "the run",
     "    if after != content:",
     "    key = compute_key(root, command, label)\n    if False:",
     "run_that_creates_a_file_writes_no_receipt"),
]


def run_case(name: str, fn, expect: str, module: Path) -> tuple[bool, str]:
    base = Path(tempfile.mkdtemp(prefix="prepush-receipt-"))
    try:
        got = fn(module, base)
    except Exception as exc:  # a case that crashes is a failing case
        got = f"CRASH({exc!r})"
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return got == expect, got


def main() -> int:
    if not MODULE.is_file():
        print(f"CONFIG: {MODULE} not found beside this file", file=sys.stderr)
        return 2
    print(f"prepush_receipt guard evidence, {len(CASES)} cases, "
          f"{len(MUTANTS)} mutants")
    failed = []
    results: dict[str, str] = {}
    for name, fn, expect in CASES:
        ok, got = run_case(name, fn, expect, MODULE)
        results[name] = got
        print(f"  [{'ok ' if ok else 'FAIL'}] {name}: expected {expect}, "
              f"got {got}")
        if not ok:
            failed.append(name)
    if failed:
        print(f"\n{len(failed)} case(s) failed on the real module; the "
              "mutants are not run, because a mutation result over a broken "
              "baseline says nothing.")
        return 1

    source = MODULE.read_text(encoding="utf-8")
    survivors = []
    work = Path(tempfile.mkdtemp(prefix="prepush-receipt-mutants-"))
    try:
        for i, (label, old, new, case_name) in enumerate(MUTANTS):
            if source.count(old) != 1:
                print(f"  [FAIL] mutant {i}: the text it replaces occurs "
                      f"{source.count(old)} times, not once")
                survivors.append(label)
                continue
            mutant = work / f"mutant_{i}.py"
            mutant.write_text(source.replace(old, new), encoding="utf-8")
            fn, expect = next((f, e) for n, f, e in CASES if n == case_name)
            ok, got = run_case(case_name, fn, expect, mutant)
            denied = not ok
            print(f"  [{'denied ' if denied else 'SURVIVED'}] {label} "
                  f"-> {case_name} gave {got} (baseline "
                  f"{results[case_name]})")
            if not denied:
                survivors.append(label)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if survivors:
        print(f"\n{len(survivors)} mutant(s) SURVIVED: {survivors}")
        return 1
    print(f"\nAll {len(CASES)} cases hold and all {len(MUTANTS)} mutants "
          "are denied. The guard can still fail.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
