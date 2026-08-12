# ITACA / pyflightstream shared process kit
# kit-version: 0.2.22
# artifact: execution_guard_mutations.py
# body-sha256: d8131f93820b1d010a219969229d2e9d5749af2bcaa812753f26ea58df5e2ffb
# canonical-source: BUILT for the kit 2026-08-11 beside execution_guard.py. Proves both arms deny what they exist to catch, proves the exemptions are real rather than accidental, and sabotages the body to prove each clause is load bearing. The guard runs as a subprocess over real PreToolUse payloads, so what is proven is the deployed contract and not an imported function.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Mutation tests for execution_guard.py. Standalone runner, no pytest:

    python execution_guard_mutations.py

The guard is invoked AS A SUBPROCESS with a real PreToolUse payload on
stdin, so these cases prove the deployed contract (the JSON decision and
the exit code) rather than an imported predicate that a wiring mistake
would bypass.

SCOPE, said first. This proves the two arms the guard claims: a
status-bearing command piped into a line filter, and a heredoc whose body
carries a backslash or a control byte. It proves NOTHING about any other
pipeline, because the guard deliberately judges none: see its docstring
for why the filter list is short rather than imagined.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent
GUARD = KIT / "execution_guard.py"


def run(command: str, guard: Path = GUARD) -> tuple[str | None, str]:
    """Run the guard on a command and return (decision, reason).

    ``(None, "")`` is silence, which is how the guard says out of scope.
    """
    payload = json.dumps({"tool_input": {"command": command}})
    proc = subprocess.run(
        [sys.executable, str(guard)],
        input=payload,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ("CRASHED", proc.stderr)
    out = proc.stdout.strip()
    if not out:
        return (None, "")
    try:
        block = json.loads(out)["hookSpecificOutput"]
    except Exception:
        return ("UNPARSEABLE", out)
    return (block.get("permissionDecision"), block.get("permissionDecisionReason", ""))


def case(name: str, command: str, expect: str | None,
         expect_in_reason: str | None = None, guard: Path = GUARD) -> bool:
    decision, reason = run(command, guard)
    ok = decision == expect
    if ok and expect_in_reason is not None:
        ok = expect_in_reason in reason
    print(f"  [{'ok ' if ok else 'FAIL'}] {name}")
    if not ok:
        print(f"        got decision={decision!r} reason={reason!r}")
    return ok


def mutant(name: str, old: str, new: str, command: str, expect_after: str | None) -> bool:
    """Sabotage one substring of the guard and assert a case flips.

    The anchor is asserted present AND unique before replacement, so a
    mutant whose anchor drifted fails loudly instead of mutating nothing
    and passing vacuously.
    """
    src = GUARD.read_text(encoding="utf-8")
    if old not in src:
        print(f"  [FAIL] {name}: anchor NOT FOUND, so nothing was mutated")
        return False
    if src.count(old) != 1:
        print(f"  [FAIL] {name}: anchor is not unique ({src.count(old)})")
        return False
    d = Path(tempfile.mkdtemp(prefix="execguard_mut_"))
    try:
        broken = d / "execution_guard.py"
        broken.write_text(src.replace(old, new), encoding="utf-8")
        decision, reason = run(command, broken)
        ok = decision == expect_after
        print(f"  [{'ok ' if ok else 'FAIL'}] {name}: mutated decision={decision!r}")
        if not ok:
            print(f"        reason={reason!r}")
        return ok
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    r = []
    print("execution guard, kit 0.2.22: two arms, both mechanically decidable")
    print()
    print("arm 1, the piped status:")

    # THE CASE THIS SESSION KEPT COMMITTING. verify_hub.py piped into tail
    # was run repeatedly on 2026-08-11 and the verdict was read from the
    # printed text, which happened to carry it. The next checker may not.
    r.append(case("a verify_ script piped into tail is refused",
                  "python scripts/verify_hub.py 2>&1 | tail -4",
                  "deny", "[piped-status]"))
    r.append(case("pytest piped into tail is refused",
                  "pytest -q | tail -5", "deny", "[piped-status]"))
    r.append(case("a check_ script piped into head is refused",
                  "python kit/check_incidents.py . | head -20", "deny"))
    r.append(case("a mutations companion piped into wc is refused",
                  "python kit/ci_state_mutations.py | wc -l", "deny"))
    r.append(case("git push piped into tail is refused",
                  "git push origin main | tail -2", "deny"))

    # The exemptions, which must be real rather than accidental.
    r.append(case("the same checker UNPIPED is out of scope",
                  "python scripts/verify_hub.py", None))
    r.append(case("an ordinary command piped into tail is out of scope",
                  "git log --oneline | tail -5", None))
    r.append(case("a filter BEFORE the checker does not implicate it",
                  "cat notes.txt | head -3 && python kit/check_incidents.py .",
                  None))
    r.append(case("a checker redirected to a file is out of scope",
                  "pytest -q > report.txt", None))
    # A path prefix must not defeat the basename patterns.
    r.append(case("a full path to a check_ script is still caught",
                  "python C:/repo/kit/check_plan_kit.py x | tail -1", "deny"))
    # A word that merely CONTAINS a listed name is not that name.
    r.append(case("a longer word containing a listed name is not it",
                  "python tools/pytest_helper_report.py | tail -3", None))
    # THE FALSE POSITIVE THE GUARD PRODUCED ON ITS FIRST DAY. A checker
    # named in PROSE inside a heredoc body is data being written, not a
    # command being run, and it used to count as upstream of a later
    # filter. Nothing here is piped except project_map.
    r.append(case("a checker named inside a heredoc body is not a command",
                  "python - <<'PY'\nlog = 'verify_hub.py was piped'\nPY\n"
                  "python scripts/project_map.py --audit | head -2", None))
    # And the guard must still catch a REAL offence in the same command.
    r.append(case("a real offence beside a heredoc is still caught",
                  "python - <<'PY'\nlog = 'a note'\nPY\n"
                  "pytest -q | tail -3", "deny"))
    # THE SECOND FALSE POSITIVE, one hour after the first and the same
    # class: the checker name is the SEARCH PATTERN, and nothing runs it.
    r.append(case("a checker named in a quoted search pattern is not a command",
                  'grep -n "run:.*pytest" ci.yml | head -20', None))
    r.append(case("a checker named in a quoted commit message is not a command",
                  'git commit -m "speed up pytest" | head -2', None))
    # The unquoted offence beside a quoted mention is still caught, so the
    # blanking did not become a way past the guard.
    r.append(case("an unquoted offence beside a quoted mention is caught",
                  'echo "mentions pytest" && pytest -q | tail -3', "deny"))

    # 0.2.22, ITC-20260811-2250, routed by itaca and reproduced by
    # importing the vendored body. The hook matcher is Bash|PowerShell and
    # the filter list was bash-only, so the shape this arm exists to refuse
    # was unrefused on the shell that repository actually uses.
    r.append(case("a PowerShell Select-Object filter is refused",
                  "pytest -q | Select-Object -Last 5", "deny", "[piped-status]"))
    r.append(case("the select alias is refused",
                  "ruff check . | select -First 3", "deny"))
    r.append(case("Measure-Object is refused",
                  "mypy src | Measure-Object", "deny"))
    r.append(case("the PowerShell half is case-insensitive, as PowerShell is",
                  "pytest -q | SELECT-OBJECT -Last 5", "deny"))
    # THE NAMED GAP, asserted as a gap so it goes RED if anyone closes it
    # without reading why it is open. Out-String owns $? like any terminal
    # cmdlet, but it drops no lines and $LASTEXITCODE survives a PowerShell
    # pipeline, so the status is still recoverable.
    r.append(case("Out-String is a KNOWN GAP and not an exemption",
                  "pytest -q | Out-String", None))

    print()
    print("arm 2, the corrupting heredoc:")

    r.append(case("a control byte in a heredoc body is refused",
                  "python - <<PY\nx = '\x01'\nPY",
                  "deny", "[heredoc-content]"))
    r.append(case("a backslash in an UNQUOTED heredoc body is refused",
                  "python - <<PY\np = 'C:\\\\WORK'\nPY",
                  "deny", "[heredoc-content]"))
    r.append(case("a control byte is refused even with a QUOTED delimiter",
                  "python - <<'PY'\nx = '\x01'\nPY", "deny"))
    # The exemption that keeps this guard usable, and the reason it is
    # narrow: a quoted delimiter is the form that survives.
    r.append(case("a backslash in a QUOTED heredoc body is allowed",
                  "python - <<'PY'\np = 'C:\\\\WORK'\nPY", None))
    r.append(case("an ordinary heredoc is out of scope",
                  "git commit -F - <<'MSG'\na message\nMSG", None))

    # 0.2.22, ITC-20260811-2240, routed by itaca with a control. The
    # refusal turned on PROSE: the same quoted heredoc without the opener
    # spelled in its body was silent. Arm 1 blanked data spans and arm 2
    # blanked nothing, and the operator had NO remedy because the token was
    # already inside the strongest quoting the shell offers.
    # THE BACKSLASH IS LOad-BEARING and its absence made the first draft
    # of this case VACUOUS: with nothing the arm objects to after the named
    # opener, the command was silent before and after the fix. The mutant
    # below refused to flip, which is how it was caught.
    r.append(case("an opener merely NAMED inside a quoted body is not an opener",
                  "python - <<'PY'\nnaming <<EOF then C:\\\\WORK\nPY\n", None))
    r.append(case("the control: the same body without the name is also silent",
                  "python - <<'PY'\nnaming nothing then C:\\\\WORK\nPY\n", None))
    # The real openers beside the named one are still found, so the mask
    # did not become a way past this arm.
    r.append(case("a real unquoted backslash heredoc is still refused after the mask",
                  "cat <<PY\npath C:\\\\WORK\nPY\n", "deny", "[heredoc-content]"))

    print()
    print("contract:")
    r.append(case("an empty command is out of scope", "", None))
    r.append(case("a payload with no command at all is out of scope",
                  "   ", None))

    print()
    print("mutants, each asserted present and unique before it is applied:")

    r.append(mutant("the filter list no longer matches tail",
                    r'_BASH_FILTERS = r"(?:head|tail|wc)"',
                    r'_BASH_FILTERS = r"(?:head|wc)"',
                    "pytest -q | tail -5", None))
    # 0.2.22, ITC-20260811-2250. The guard is wired for Bash|PowerShell
    # and at 0.2.20 refused nothing PowerShell could express, on a
    # repository whose primary shell IS PowerShell.
    r.append(mutant("the PowerShell half is removed",
                    r'_PS_FILTERS = r"(?i:Select-Object|Measure-Object|select|measure)"',
                    r'_PS_FILTERS = r"(?i:__never_matches__)"',
                    "pytest -q | Select-Object -Last 5", None))
    r.append(mutant("the case-insensitive flag on the PowerShell half is dropped",
                    r'(?i:Select-Object|Measure-Object|select|measure)',
                    r'(?-i:Select-Object|Measure-Object|select|measure)',
                    "pytest -q | SELECT-OBJECT -Last 5", None))
    # 0.2.22, ITC-20260811-2240. Arm 2 scanned the raw string, so an
    # opener merely NAMED inside an already-quoted body was refused, and
    # the operator had no remedy because the quoting was already maximal.
    r.append(mutant("arm 2 stops consulting the data mask",
                    "        if mask[opener.start()]:\n            continue",
                    "        if False:\n            continue",
                    "python - <<'PY'\nnaming <<EOF then C:\\\\WORK\nPY\n", "deny"))
    r.append(mutant("every pipeline is judged, not just status-bearing ones",
                    "    name = _is_status_bearing(upstream)\n    if not name:\n        return None",
                    "    name = _is_status_bearing(upstream) or 'anything'",
                    "git log --oneline | tail -5", "deny"))
    r.append(mutant("a quoted delimiter also exempts the control byte",
                    'if CONTROL_BYTE.search(body):',
                    'if CONTROL_BYTE.search(body) and not quoted:',
                    "python - <<'PY'\nx = '\x01'\nPY", None))
    r.append(mutant("an unquoted backslash stops being refused",
                    'if not quoted and "\\\\" in body:',
                    'if quoted and "\\\\" in body:',
                    "python - <<PY\np = 'C:\\\\WORK'\nPY", None))
    r.append(mutant("data spans are scanned as commands again",
                    "    scannable = _without_data_spans(command)",
                    "    scannable = command",
                    "python - <<'PY'\nlog = 'verify_hub.py was piped'\nPY\n"
                    "python scripts/project_map.py --audit | head -2", "deny"))
    r.append(mutant("quoted spans stop being blanked",
                    "        if quote is not None and command[i] != \"\\n\":\n            mask[i] = True",
                    "        if False:\n            mask[i] = True",
                    'grep -n "run:.*pytest" ci.yml | head -20', "deny"))
    r.append(mutant("the guard denies instead of staying silent when clean",
                    "    _allow_silently()\n\n\nif __name__",
                    "    _decide('deny', 'mutated')\n\n\nif __name__",
                    "python scripts/verify_hub.py", "deny"))

    passed = sum(1 for x in r if x)
    print()
    print(f"{passed}/{len(r)} passed")
    return 0 if passed == len(r) else 1


if __name__ == "__main__":
    raise SystemExit(main())
