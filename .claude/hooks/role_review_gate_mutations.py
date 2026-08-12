# ITACA / pyflightstream shared process kit
# kit-version: 0.2.18
# artifact: role_review_gate_mutations.py
# body-sha256: fe9ecec7baed9a488a7609f9daab0465f4a35798b282435600a5720062ca791d
# canonical-source: BUILT for the kit (0.2.18) as the guard evidence for the CI-green tag rule promoted into role_review_gate.py from INC-20260810-2140-shared. It covers THAT ARM AND NOTHING ELSE in the gate, which its own docstring states first, because a companion named after a whole body is read as covering one. It drives the real gate as a subprocess against a real git repository and a real fake `gh` on PATH, and its first case is the original pyflightstream v0.7.0 push, refused at both of its moments: the run in progress at the instant the tag went out, and the failure that run concluded with. Three arms no case reaches are listed in UNPROVEN rather than counted as denied.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Guard evidence for the CI-GREEN RELEASE ARM of role_review_gate.py.

Run:  python role_review_gate_mutations.py

SCOPE, FIRST, BECAUSE THE FILENAME OVERSTATES IT. This companion covers the
rule kit 0.2.18 added and NOTHING ELSE in that gate. The rest of the gate's
evidence is the hub-local fixtures beside it, `test_gate_hardening_s5b.py`,
`test_gate_powershell_heredoc.py` and `test_known_passes_vocabulary.py`, and
a green run here is not a statement about the tokenizer, the attestation
scope, the option allowlist or the ledger arm. A companion whose name reads
as total coverage is how a partial guard gets trusted as a whole one.

WHAT IT DRIVES. The REAL gate, as a subprocess, on a REAL git repository,
with a REAL `gh` executable on PATH that is a fake. The whole chain runs:
the command is tokenized, the tag is resolved with git, `ci_state.py` is
located and executed as its own process, and its exit status becomes a
permission decision. Nothing in that chain is stubbed, which is the half a
pure-function fixture cannot reach.

THE CASE THAT IS THE REASON THIS EXISTS: the ORIGINAL pyflightstream v0.7.0
push must be REFUSED. That tag went out fifteen seconds after its branch with
seven of eight jobs still running and five of them red, and the gate of the
day ALLOWED it, measured against the live remote. Both moments are cases: the
state at the instant it was pushed (a run in progress) and the state that run
reached (failure). Neither may be allowed.

EVERY MUTANT IS A WAY TO FAIL OPEN, because for this arm that is the only
direction that matters: a tag is public, cannot be retracted, and triggers a
release workflow.

TWO CASES MUST ALLOW, and they are not padding. A gate that refuses
everything passes every safety case and is worth nothing: an ordinary branch
push must not be touched by this arm at all, and a version tag on a green
commit with both attestations in place must go through.

WHAT IS NOT VERIFIED HERE, stated rather than left to be assumed: no case in
this file has ever spoken to GitHub. The fake answers in `gh run list --json`
shape taken from the real CLI's documented fields, so what is proven is the
gate's behaviour GIVEN those answers, not that the remote produces them.

Exit 0 when every case holds and every mutant is denied, 1 otherwise.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent


def _locate(name: str) -> Path:
    """Find a kit body this companion needs, beside it or in a sibling.

    In the kit master directory everything is in one place. In a VENDORED
    tree it is not: the two libraries put the gate under `.claude/hooks` and
    the tools under `.claude/kit` or `.claude/tools`, measured rather than
    assumed, and the scaffold splits them the same way. A companion that only
    looked beside itself would be dead in exactly the trees it is vendored
    into, and it would fail by not finding a file rather than by finding a
    defect, which is the worst way for a guard to be wrong.
    """
    for folder in (KIT, KIT.parent / "hooks", KIT.parent / "tools",
                   KIT.parent / "kit", KIT.parent):
        candidate = folder / name
        if candidate.is_file():
            return candidate
    raise SystemExit(f"{name} is not beside this companion or in a sibling "
                     f"directory of {KIT}; this guard cannot run at all, "
                     "which is a configuration error and not a pass")


GATE = _locate("role_review_gate.py")
CI_STATE = _locate("ci_state.py")

# ---------------------------------------------------------------------------
# The fake `gh`, IMPORTED rather than rewritten. It encodes one hard-won
# platform fact (Windows resolves a bare command name by appending `.exe`
# only, so the fake has to be a real executable, and a venv interpreter copied
# out of its venv cannot start) and two copies of that would drift apart.
_spec = importlib.util.spec_from_file_location(
    "_ci_state_mutations_helpers", _locate("ci_state_mutations.py")
)
if _spec is None or _spec.loader is None:  # pragma: no cover - a broken kit
    raise SystemExit("ci_state_mutations.py could not be loaded")
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
fake_gh = _helpers.fake_gh


def fake_gh_by_sha(where: Path, default: str, by_sha: dict[str, str]) -> None:
    """A fake `gh` whose answer depends on the SHA it is asked about.

    Needed because one property here cannot be observed with a single answer:
    whether the gate asked about the TAG's commit or about some other ref's.
    With one payload for every SHA, a mutant that reads the wrong commit gets
    the right answer by accident and survives.

    Built ON TOP of `ci_state_mutations.fake_gh` so the executable placement
    (and the Windows facts inside it) stays in one place; only the script BODY
    is replaced here. The script's filename per platform is the one thing this
    function has to know twice, and it is asserted rather than assumed.
    """
    fake_gh(where, default, 0)
    script = where / ("run" if os.name == "nt" else "gh_impl.py")
    if not script.is_file():  # pragma: no cover - a changed helper
        raise SystemExit(f"the fake gh script is not at {script}; "
                         "ci_state_mutations.fake_gh has moved it")
    for sha, payload in by_sha.items():
        (where / f"payload_{sha}.txt").write_text(payload, encoding="utf-8")
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "here = Path(__file__).resolve().parent\n"
        "argv = sys.argv[1:]\n"
        "sha = argv[argv.index('--commit') + 1] if '--commit' in argv else ''\n"
        "special = here / ('payload_%s.txt' % sha)\n"
        "path = special if special.is_file() else here / 'payload.txt'\n"
        "sys.stdout.write(path.read_text(encoding='utf-8'))\n",
        encoding="utf-8", newline="\n")


def _runs(**fields: object) -> str:
    row = {"status": "completed", "conclusion": "success", "workflowName": "ci",
           "databaseId": 1, "url": "https://example.invalid/run/1"}
    row.update(fields)
    return json.dumps([row])


#: The state at the instant the v0.7.0 tag was actually pushed: run 31436832528
#: on commit 2d754a7 had not concluded. In `gh run list` vocabulary that is one
#: run, in progress.
V070_AS_PUSHED = _runs(status="in_progress", conclusion=None)
#: The state that same run reached: five of eight jobs failed, so the run
#: concluded `failure`.
V070_TODAY = _runs(conclusion="failure")
GREEN = _runs()
NO_RUN = "[]"
FULL_PAGE = "[" + ",".join(
    '{"status":"completed","conclusion":"success","workflowName":"w%d",'
    '"databaseId":%d,"url":"u%d"}' % (i, i, i) for i in range(100)) + "]"


# ---------------------------------------------------------------------------
# fixtures


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, check=True)
    return done.stdout.strip()


def make_repo(where: Path, tag: str = "v0.7.0") -> tuple[Path, str]:
    """A real repository with one commit and one version tag."""
    repo = where / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "gate@example.invalid")
    _git(repo, "config", "user.name", "gate")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "pyproject.toml").write_text('[project]\nname = "fixture"\n',
                                         encoding="utf-8", newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "one")
    sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "tag", tag)
    _git(repo, "remote", "add", "origin", "https://example.invalid/o/r.git")
    return repo, sha


def write_attestations(repo: Path, sha: str, kinds: tuple[str, ...]) -> None:
    """Write the attestation file so the CI arm is what a case measures.

    The review attestation is a PRECONDITION here rather than a subject: the
    review arm runs before the release block, so without it every case would
    stop one refusal early and this file would be measuring that arm instead.
    """
    body = {kind: {"commits": [sha]} for kind in kinds}
    path = repo / ".claude" / ".role_review_attestation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8", newline="\n")


def quiet_ledger(where: Path) -> str:
    """A reachable ledger that reports nothing blocking.

    An ABSENT ledger variable DENIES since kit 0.2.8, so popping it is not a
    neutral starting point: every case would stop at the [config] arm.
    """
    folder = where / "ledger"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "check_incidents.py").write_text("import sys\nsys.exit(0)\n",
                                               encoding="utf-8", newline="\n")
    return str(folder)


def stage_gate(where: Path, body: Path, with_ci_state: bool) -> Path:
    """Put the gate under test in its own directory, optionally with its pair.

    ALWAYS a staged copy, even for the unmutated body, and that is deliberate.
    The gate looks for `ci_state.py` BESIDE ITSELF first, so a real body run
    from the kit directory and a mutant run from a temp directory would differ
    in a way that has nothing to do with the mutation: every mutant would look
    denied because every case would stop at the [ci-config] arm. Staging both
    the same way is what makes the comparison mean anything.
    """
    folder = where / ("hooks_with_ci" if with_ci_state else "hooks_bare")
    folder.mkdir(parents=True, exist_ok=True)
    staged = folder / "role_review_gate.py"
    shutil.copy(body, staged)
    if with_ci_state:
        shutil.copy(CI_STATE, folder / "ci_state.py")
    return staged


def drive(gate: Path, repo: Path, command: str, ghdir: Path | None,
          ledger: str) -> tuple[str, str]:
    """Run the gate on one command and return (decision, reason)."""
    env = dict(os.environ)
    for key in [k for k in env if k.endswith("_INCIDENT_LEDGER")]:
        env.pop(key)
    env["COORD_INCIDENT_LEDGER"] = ledger
    if ghdir is not None:
        env["PATH"] = str(ghdir) + os.pathsep + env.get("PATH", "")
    else:
        env["PATH"] = str(Path(tempfile.gettempdir()) / "kit-no-gh-here")
    done = subprocess.run(
        [sys.executable, str(gate)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True, text=True, cwd=str(repo), env=env,
    )
    out = done.stdout.strip()
    if not out:
        return "allow-silently", done.stderr.strip()
    payload = json.loads(out)["hookSpecificOutput"]
    return payload["permissionDecision"], payload["permissionDecisionReason"]


# ---------------------------------------------------------------------------
# the cases
#
# (label, gh stdout or None for "no gh at all", command, attestations to
#  write, whether ci_state.py is staged beside the gate, expected decision,
#  a needle only the intended arm produces)

CASES: list[tuple[str, str | None, str, tuple[str, ...], bool, str, str]] = [
    # THE INCIDENT ITSELF, both moments of it.
    ("the ORIGINAL v0.7.0 push, as it was pushed, is REFUSED",
     V070_AS_PUSHED, "git push origin v0.7.0", ("review", "release"), True,
     "deny", "[ci-running]"),
    ("the same commit, after that run concluded, is REFUSED",
     V070_TODAY, "git push origin v0.7.0", ("review", "release"), True,
     "deny", "[ci-red]"),
    # Everything unknown denies, one arm per reason a releaser has to act on.
    ("no run at all for the commit is REFUSED",
     NO_RUN, "git push origin v0.7.0", ("review", "release"), True,
     "deny", "[ci-unknown]"),
    # `None` is the remote answering an ERROR rather than `gh` being absent
    # from PATH. Emptying PATH would take `git` with it, and the gate would
    # then refuse at its [repo] arm having never reached this one: the case
    # would pass while measuring nothing, which is the vacuity this kit keeps
    # paying for. `ci_state_mutations.py` covers a genuinely absent `gh`.
    ("a remote that answers an error is REFUSED",
     None, "git push origin v0.7.0", ("review", "release"), True,
     "deny", "[ci-unknown]"),
    ("a full page that may be truncated is REFUSED",
     FULL_PAGE, "git push origin v0.7.0", ("review", "release"), True,
     "deny", "[ci-unknown]"),
    ("ci_state.py not vendored is a REFUSAL, never a skip",
     GREEN, "git push origin v0.7.0", ("review", "release"), False,
     # The needle is the ARM'S OWN sentence, not its bracketed label, and the
     # difference is not cosmetic. With the refusal deleted the gate runs
     # `python None`, the interpreter exits 2 for a file it cannot open, 2 is
     # ci_state's CONFIG status, and the mutant answers `[ci-config]` too. The
     # label alone let it survive; measured, not reasoned about.
     "deny", "is not vendored anywhere this gate looks"),
    # Pinned because it is what makes this gate's own [ci-tag] arm
    # unreachable, which that arm's comment claims: a version tag that does
    # not resolve is refused by the SCOPE arm before CI is ever asked. If this
    # case ever stops saying [scope], the CI arm has become reachable and its
    # comment has become false.
    ("a version tag that does not resolve is refused before CI is asked",
     GREEN, "git push origin v9.9.9", ("review", "release"), True,
     "deny", "[scope]"),
    # The refspec forms publish the same tag and must be judged the same way.
    ("a refspec publishing the tag is judged on its SOURCE side",
     V070_TODAY, "git push origin HEAD:refs/tags/v0.8.0",
     ("review", "release"), True, "deny", "[ci-red]"),
    ("refs/tags/ spelling of the same push is REFUSED",
     V070_TODAY, "git push origin refs/tags/v0.7.0", ("review", "release"),
     True, "deny", "[ci-red]"),
    ("a shell-wrapped release push is REFUSED",
     V070_TODAY, 'bash -c "git push origin v0.7.0"', ("review", "release"),
     True, "deny", "[ci-red]"),
    # CI is asked BEFORE the release panel, because a red commit cannot ship
    # and the panel would be spent on it.
    ("a red commit is refused on CI before the release attestation is asked",
     V070_TODAY, "git push origin v0.7.0", ("review",), True,
     "deny", "[ci-red]"),
    # And the two that must NOT be refused by this arm.
    ("a green commit reaches the release attestation arm",
     GREEN, "git push origin v0.7.0", ("review",), True,
     "deny", "[release]"),
    ("a green commit with both attestations is ALLOWED",
     GREEN, "git push origin v0.7.0", ("review", "release"), True,
     "allow-silently", "ALLOWED a push"),
    ("an ordinary branch push on a RED commit is not this arm's business",
     V070_TODAY, "git push origin main", ("review",), True,
     "allow-silently", "ALLOWED a push"),
]


def special_cases(body: Path, root: Path, ledger: str,
                  report: bool) -> list[str]:
    """The two cases the table above cannot express.

    Both need a fixture the tabular form has no column for: one needs two
    commits answering DIFFERENTLY, and the other needs a deliberately broken
    `ci_state.py`. Each exists because a mutant survived without it.
    """
    problems: list[str] = []

    # 1. A BRANCH NAMED LIKE A VERSION TAG. Release conventions produce these,
    # and `sneaky:refs/heads/v0.7.0` must NOT move the CI question onto the
    # branch's commit. Only a two-answer fixture can see the difference.
    where = root / "branch_named_like_a_tag"
    where.mkdir(parents=True, exist_ok=True)
    repo, red_sha = make_repo(where)
    _git(repo, "checkout", "-q", "-b", "sneaky")
    (repo / "later.txt").write_text("later\n", encoding="utf-8", newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "two")
    green_sha = _git(repo, "rev-parse", "HEAD")
    body_att = {kind: {"commits": [red_sha, green_sha]}
                for kind in ("review", "release")}
    att = repo / ".claude" / ".role_review_attestation.json"
    att.parent.mkdir(parents=True, exist_ok=True)
    att.write_text(json.dumps(body_att), encoding="utf-8", newline="\n")
    fake_gh_by_sha(repo, GREEN, {red_sha: V070_TODAY})
    gate = stage_gate(where, body, True)
    decision, reason = drive(
        gate, repo, "git push origin v0.7.0 sneaky:refs/heads/v0.7.0",
        repo, ledger)
    label = "a branch named like the tag does not move the CI question"
    ok = decision == "deny" and "[ci-red]" in reason
    if not ok:
        problems.append(label)
    if report:
        print(f"  [{'ok ' if ok else 'FAIL'}] {label}"
              + ("" if ok else f": got {decision!r} / {reason[:160]!r}"))

    # 2. AN EXIT STATUS OUTSIDE ci_state's CONTRACT. Without this, a mapping
    # that defaults an unrecognised status to GREEN survives every other case,
    # because every other case exits 0, 1, 3 or 4.
    where = root / "off_contract_exit"
    where.mkdir(parents=True, exist_ok=True)
    repo, sha = make_repo(where)
    write_attestations(repo, sha, ("review", "release"))
    fake_gh(repo, GREEN, 0)
    gate = stage_gate(where, body, True)
    (gate.parent / "ci_state.py").write_text(
        "import sys\nprint('a state nobody declared')\nsys.exit(7)\n",
        encoding="utf-8", newline="\n")
    decision, reason = drive(gate, repo, "git push origin v0.7.0", repo, ledger)
    label = "an exit status outside ci_state's contract is not a pass"
    ok = decision == "deny" and "outside its documented contract" in reason
    if not ok:
        problems.append(label)
    if report:
        print(f"  [{'ok ' if ok else 'FAIL'}] {label}"
              + ("" if ok else f": got {decision!r} / {reason[:160]!r}"))
    return problems


def every_case_holds(body: Path, report: bool) -> list[str]:
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="gate-ci-") as tmp:
        root = Path(tmp)
        ledger = quiet_ledger(root)
        for (label, answer, command, kinds, with_ci_state, want, needle) in CASES:
            where = root / re.sub(r"\W+", "_", label)[:60]
            where.mkdir(parents=True, exist_ok=True)
            repo, sha = make_repo(where)
            write_attestations(repo, sha, kinds)
            gate = stage_gate(where, body, with_ci_state)
            # Into the repository, because that is the working directory
            # `ci_state` hands `gh`, and the Windows fake reads its script
            # from there.
            if answer is None:
                fake_gh(repo, "HTTP 401: Bad credentials", 1)
            else:
                fake_gh(repo, answer, 0)
            ghdir = repo
            decision, reason = drive(gate, repo, command, ghdir, ledger)
            ok = decision == want and needle in reason
            if not ok:
                problems.append(label)
            if report:
                print(f"  [{'ok ' if ok else 'FAIL'}] {label}"
                      + ("" if ok else f": got {decision!r} want {want!r}, "
                                       f"needle {needle!r} in {reason[:160]!r}"))
        problems += special_cases(body, root, ledger, report)
    return problems


# ---------------------------------------------------------------------------
# the mutants. Each is (name, exact source to find, replacement, note).

MUTANTS: list[tuple[str, str, str]] = [
    ("anything that is not RED is treated as green",
     '                if ci_state == "GREEN":\n                    continue',
     '                if ci_state != "RED":\n                    continue'),
    ("the CI question is never asked at all",
     "            ci_body = _ci_state_body(root)",
     "            ci_body = None if True else _ci_state_body(root)\n"
     "            ci_body = ci_body or _NEVER"),
    ("an absent ci_state.py is read as nothing to check",
     "            if ci_body is None:",
     "            if ci_body is not None and False:"),
    ("a tag is resolved by its own NAME instead of the refspec source",
     "        if name in targets:\n            targets[name] = source",
     "        if name in targets:\n            targets[name] = targets[name]"),
    ("a refs/heads destination is accepted as a tag rename",
     '        if destination.startswith("refs/heads/") or not source:',
     "        if not source:"),
    ("an exit status outside ci_state's contract is assumed green",
     '    state = CI_EXIT_STATE.get(done.returncode, "UNKNOWN")',
     '    state = CI_EXIT_STATE.get(done.returncode, "GREEN")'),
]

#: Arms of this rule that NO case here reaches, listed rather than left for a
#: reader to assume covered. Both were written as mutants first, both survived
#: every case, and both were removed from the list above instead of being
#: counted as denied. A guard's own report is the wrong place to be optimistic.
UNPROVEN = [
    "_ci_state's OSError arm (the interpreter itself unusable). It cannot be "
    "provoked without breaking the running interpreter, so a mutant flipping "
    "it to GREEN survives every case. Reviewed by reading only.",
    "_ci_state's TimeoutExpired arm. Reaching it costs the full "
    "CI_CALL_TIMEOUT of wall clock per case, which is a fixture that would "
    "not be run. Reviewed by reading only.",
    "the CI_BUDGET_SECONDS exhaustion arm, for the same reason.",
]

#: A mutant whose refusal comes from somewhere other than the rule it deletes
#: is recorded, not counted silently. This kit has twice shipped a case that
#: passed on wording the report prints unconditionally.
NOTES = {
    "an absent ci_state.py is read as nothing to check":
        "denied by the arm's own SENTENCE, not by its verdict and not even by "
        "its label. With the refusal removed the gate runs `python None`, the "
        "interpreter exits 2, and 2 is ci_state's CONFIG status, so the "
        "mutant still denies and still says [ci-config]. The push is refused "
        "either way, by luck rather than by design, and this mutant is "
        "evidence about the message rather than about the refusal.",
    "the CI question is never asked at all":
        "the replacement also references an undefined name, so this mutant "
        "proves the arm RUNS rather than that any particular clause in it is "
        "load bearing.",
}


def main() -> int:
    print("role-review gate, CI-GREEN RELEASE ARM only")
    problems = every_case_holds(GATE, report=True)
    if problems:
        print(f"\n{len(problems)} case(s) FAILED on the real body: {problems}")
        return 1

    source = GATE.read_text(encoding="utf-8")
    print("\nmutants, each asserted present before it is applied:")
    survivors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="gate-mutant-") as tmp:
        for name, old, new in MUTANTS:
            if source.count(old) != 1:
                print(f"  [FAIL] {name}: its target appears "
                      f"{source.count(old)} time(s), so the mutation is not "
                      "the one described. A mutation that did not apply looks "
                      "exactly like a guard that does not fire.")
                survivors.append(name + " [not applied]")
                continue
            mutant = Path(tmp) / ("mutant_" + re.sub(r"\W+", "_", name)[:40] + ".py")
            mutant.write_text(source.replace(old, new), encoding="utf-8",
                              newline="\n")
            denied = bool(every_case_holds(mutant, report=False))
            print(f"  [{'ok ' if denied else 'FAIL'}] {name}"
                  + ("" if denied else ": SURVIVED every case, so no case "
                                       "discriminates it"))
            if name in NOTES:
                print(f"         note: {NOTES[name]}")
            if not denied:
                survivors.append(name)

    if survivors:
        print(f"\n{len(survivors)} mutant(s) not denied: {survivors}")
        return 1
    print(f"\n{len(CASES) + 2} case(s) hold and all {len(MUTANTS)} mutants "
          "are denied. Scope: the CI-green release arm only.")
    print("arms NO case here reaches:")
    for item in UNPROVEN:
        print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
