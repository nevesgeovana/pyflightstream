# ITACA / pyflightstream shared process kit
# kit-version: 0.2.17
# artifact: detached_gate.py
# body-sha256: 86ac1759c867c6a215e9ccc44779bd4e4954efa058c54b1b3e05cbc3e70831f7
# canonical-source: BUILT for the kit (0.2.17, HUB-13, author decision 1 of 2026-08-02) from a ceiling nobody had declared. A lane session cuts a command at 10 minutes; itaca's pre-push suite is 12.1 minutes, so a push of changed content can never complete inside a lane and the failure looks environmental. The decision is general and not about itaca: ANY gate that grows past the caller's ceiling becomes unrunnable in a lane, silently. See coordination/DESIGN_HUB-13_kit_0217.md item 1 and coordination/DESIGN_HUB-13_lane.md section 1.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Run a long gate in a process that outlives the caller; read the answer.

Usage:
    detached_gate.py start  --label <name> [--repo <path>] -- <command> ...
    detached_gate.py state  --label <name> [--run-id <id>] [--repo <path>]
    detached_gate.py report --label <name> [--repo <path>]

``start`` writes a RUNNING record, spawns the command detached, and RETURNS
AT ONCE printing the run id. It never waits. ``state`` reads the record and
prints one of four states, running nothing. ``report`` prints the captured
output of a finished run, so a RED is diagnosable without hunting for a path.

WHY THIS EXISTS, and the ceiling is the point. A lane session cuts a command
at 10 minutes. That is a property of the CALLER, not of the gate, and no gate
can observe it. So every mechanism that answers "did the gate pass" by
WAITING on the gate inherits a limit it cannot see, and the failure surfaces
as an environmental one: the command dies, the exit status belongs to the
shell rather than to the gate, and nothing in the output distinguishes "the
suite failed" from "the suite was cut off". Measured: itaca's pre-push tier
is 12.1 minutes against a 10 minute ceiling, so a push of changed content
could never complete inside a lane at all.

The fix is to stop making the answer depend on the caller staying alive. The
gate runs in a process that outlives the invocation and the answer is a FILE.
Nothing changes about what runs, there is no ceiling, and a lane stops
needing to know a limit exists.

THE STATE CONTRACT, which is the load-bearing part of this file.

    RUNNING   the gate has not finished: a record with no terminal field
              AND a runner process that is still alive
    GREEN     a terminal record whose exit status is 0
    RED       a terminal record whose exit status is not 0
    UNKNOWN   nothing above could be established

UNKNOWN IS NEVER GREEN. Enumerated, so no reader has to infer the set: absent
record, unreadable record, malformed JSON, a record written under a different
FORMAT, a record written by a DIFFERENT BODY of this mechanism, a record
whose run id does not match the one asked for, a record that says running
whose runner pid is not alive, a record that says running whose liveness
could not be determined at all, a terminal record with no exit status, a
clock that moved backwards, and ANY exception raised anywhere inside this
mechanism. All of them are UNKNOWN.

There is deliberately NO path in which a defect in this file yields GREEN. A
defect here costs a human a look at CI and never a false pass.

THE ASYMMETRY WITH ``prepush_receipt.py``, written here rather than only in
the design note because the next reader will otherwise make the two
"consistent" and break one. That file carries the same paragraph about
``COORD_INCIDENT_LEDGER``, for the same reason.

There, EVERY UNKNOWN STATE RUNS THE SUITE: an unreadable receipt cannot prove
the suite passed, so the safe answer is DO THE WORK. Here, EVERY UNKNOWN
STATE REFUSES TO CLAIM GREEN: an unreadable record cannot prove the gate
passed, so the safe answer is DO NOT CLAIM IT DID.

Those are the SAME direction and not opposite ones, which is the thing worth
holding onto. Both guards answer their own unknown with "you have not earned
the shortcut yet". The receipt's shortcut is skipping a suite; this one's
shortcut is saying closed. Making either one say green on unknown is
``INC-20260802-1450-shared``, a gate that fails OPEN, which this project has
already paid for once.

WHAT A RECORD IS NOT. It proves that A FILE SAYS the gate exited with a
status. It does not prove the gate ran, and a hand-written record would
authorize a claim. This is exactly the limit ``prepush_receipt.py`` documents
about itself and the review attestation documents about itself. Do not read
it for more than it claims. Forging is made AWKWARD rather than impossible:
the terminal record is written only by this file's own ``_run`` mode at the
point where the child's exit status is known, and it carries the sha256 of
this file's body, so a forged record must reimplement that digest.

THERE IS DELIBERATELY NO ``wait`` VERB. A caller that wants to wait starts a
WAITER detached and reads its record, which is this mechanism composed with
itself rather than a second mechanism holding the same rule in a second
vocabulary. ``ci_state.py await`` is exactly that caller, and it is how a
close waits for a CI run with no CALLER-side ceiling. ``await`` carries its
own 6 hour bound on an ORPHANED waiter, whose expiry is UNKNOWN and therefore
cannot become a false pass; see that file. "No ceiling" means the caller's 10
minute cut is gone, not that no bound exists anywhere.

WHAT THE RECORD KEYS ON, and what it does not. It carries FORMAT, the label,
the run id, the argv verbatim, the start time, the runner pid, and the
sha256 of this file's own body. That last component is component 4 of the
receipt's key and is here for the same reason: a promotion of this artifact
cannot inherit authority granted under different rules, so a record written
by a different body reads UNKNOWN.

It deliberately does NOT key on the content of the working tree. The receipt
does, because its whole question is "has this content already passed". This
mechanism's question is narrower: "did the process I started finish, and with
what status". A caller that needs the content question composes the two by
starting the receipt-guarded command detached, which is the intended shape
and the reason neither file grew the other's responsibility.

LIVENESS, AND THE ONE HOLE, stated rather than hidden. A RUNNING record
carries the runner's pid, and ``state`` answers RUNNING only if that pid is
alive. If it is not, the runner died without writing a terminal record and
the answer is UNKNOWN.

THE HOLE IS PID REUSE. If the operating system reassigns the runner's pid to
an unrelated process, a dead runner reads as alive and ``state`` answers
RUNNING. That is wrong, and it is wrong in the SAFE direction: RUNNING is not
GREEN, so the worst outcome is a caller that waits for a run which will never
finish and refuses to say closed. Closing the hole portably needs a
process-creation-time read the standard library does not offer on both
platforms. It is recorded here rather than fixed.

``os.kill(pid, 0)`` IS NOT USED ON WINDOWS AND THE REASON IS NOT STYLE. On
Windows, Python's ``os.kill`` maps any signal that is not a console control
event onto ``TerminateProcess``, with the signal number as the exit code. So
the POSIX idiom for "is this process alive" TERMINATES the process on
Windows, and a liveness probe would kill the very gate it was asking about.
Both libraries and the coordination level run on Windows. The Windows branch
opens the process with SYNCHRONIZE rights and waits on it with a zero
timeout, which observes without touching.

ATOMICITY. The terminal record is written to a temporary file and moved with
``os.replace``, so a half-written record is not a state any reader can
observe. A torn write leaves the previous record intact, and the previous
record says RUNNING, which is not GREEN.

WHERE THE RECORD LIVES. Beside the attestation and the pre-push receipt,
under ``.claude/.detached_gate/`` at the root resolved by
``git rev-parse --show-toplevel`` from the caller's working directory. There
is NO environment variable, deliberately, on the receipt's reasoning: an
environment variable's unset branch is charter material at each consumer
rather than the kit's to decide alone, and this location is derivable, so the
question does not have to be asked. Each consumer gitignores the directory,
beside the attestation, so it does not enter a shipped-surface or
house-style walk.

Standalone, stdlib only, no third-party deps, like every kit checker.

EXIT STATUS, PER VERB, because one namespace carrying two meanings is how a
caller reads a red gate as a pass.

``state`` and ``report`` return the STATE: 0 GREEN, 1 RED, 3 RUNNING, 4
UNKNOWN. 2 is the kit's configuration-error status everywhere and is
therefore never reused for a state.

``start`` returns 0 for "THE GATE WAS SPAWNED AND IS TRACKED", and 2 if it
could not be. IT NEVER MEANS THE GATE PASSED. A fast gate can already be RED
by the time ``start`` returns, so ``start ... && something`` would run
``something`` over a red gate. Ask ``state``; never branch on ``start``. This
was an architecture lens's round-one finding against this file.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

DIRNAME = ".claude/.detached_gate"
FORMAT = 1
# How long `start` waits for the runner to write its FIRST record. This is a
# bound on process startup and never on the gate; see cmd_start.
RECORD_APPEARS_WITHIN = 30.0
MARKER = "END KIT PROVENANCE"

GREEN = "GREEN"
RED = "RED"
RUNNING = "RUNNING"
UNKNOWN = "UNKNOWN"

EXIT = {GREEN: 0, RED: 1, RUNNING: 3, UNKNOWN: 4}
CONFIG = 2


UNAVAILABLE = "unavailable"


def _self_body_sha256() -> str:
    """The sha256 of this file's kit body, or UNAVAILABLE.

    A failure here must not raise. It returns UNAVAILABLE, and EVERY CALLER
    MUST TEST FOR THAT VALUE BEFORE COMPARING, because UNAVAILABLE equals
    itself: a record written while the digest was uncomputable and read while
    it was still uncomputable would otherwise satisfy the identity check by
    matching a sentinel against itself, and a terminal record claiming exit 0
    would read GREEN with the identity never actually established. That is
    the fail-OPEN shape this whole file exists to prevent, found by an
    architecture lens in round one, and the sentinel's own docstring had
    called it "a sentinel that never matches", which was false.

    ``read_state`` therefore answers UNKNOWN on UNAVAILABLE before it
    compares anything. This is the same hinge ``prepush_receipt.py`` puts at
    ``Unavailable``, where a key that cannot be computed RUNS the suite.
    """
    try:
        text = Path(__file__).read_text(encoding="utf-8")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        marker = next(i for i, ln in enumerate(lines) if MARKER in ln)
        body = "\n".join(lines[marker + 1:])
        return hashlib.sha256(body.encode("utf-8")).hexdigest()
    except Exception:
        return UNAVAILABLE


def _root(where: Path) -> Path | None:
    try:
        r = subprocess.run(["git", "-C", str(where), "rev-parse",
                            "--show-toplevel"],
                           capture_output=True, text=True, env=os.environ.copy())
        if r.returncode != 0:
            return None
        return Path(r.stdout.strip())
    except Exception:
        return None


def _paths(root: Path, label: str) -> tuple[Path, Path]:
    d = root / DIRNAME
    return d / f"{label}.json", d / f"{label}.log"


def _alive(pid: int) -> bool | None:
    """Is this pid a live process? None means the question could not be asked.

    None is NOT False. A liveness probe that failed cannot prove the runner
    died, so the caller turns None into UNKNOWN rather than into a terminal
    verdict.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            SYNCHRONIZE = 0x00100000
            WAIT_TIMEOUT = 0x00000102
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if not handle:
                # No handle means no such process, in the ordinary case. It
                # can also mean access denied, which is why this returns
                # None rather than False on any unexpected error below.
                return False
            try:
                return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return None
    try:
        os.kill(pid, 0)          # POSIX only; see the docstring for why.
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return None


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def read_state(record: Path, want_run_id: str | None,
               now: float) -> tuple[str, str]:
    """The whole decision. Any failure inside it means UNKNOWN."""
    try:
        if not record.exists():
            return UNKNOWN, f"no record at {record}"
        try:
            data = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return UNKNOWN, f"record unreadable or malformed: {exc}"
        if not isinstance(data, dict):
            return UNKNOWN, "record is not an object"
        if data.get("format") != FORMAT:
            return UNKNOWN, (f"record format {data.get('format')!r}, this "
                             f"body speaks {FORMAT}")
        mine = _self_body_sha256()
        if mine == UNAVAILABLE:
            return UNKNOWN, ("this body's own digest could not be computed, "
                             "so the record's origin cannot be established. "
                             "The sentinel is NOT compared, because it would "
                             "match itself")
        if data.get("mechanism") != mine:
            return UNKNOWN, ("record was written by a different body of this "
                             "mechanism; authority is not inherited across a "
                             "promotion")
        if want_run_id is not None and data.get("run_id") != want_run_id:
            return UNKNOWN, (f"record holds run id {data.get('run_id')!r}, "
                             f"not the {want_run_id!r} that was asked for")

        started = data.get("started_at")
        if not isinstance(started, (int, float)):
            return UNKNOWN, "record carries no usable start time"
        if now + 1 < started:
            return UNKNOWN, ("the record starts in the future; the clock "
                             "moved backwards and no age here is meaningful")

        if "exit_status" in data:
            status = data.get("exit_status")
            if not isinstance(status, int):
                return UNKNOWN, (f"terminal record carries a non-integer exit "
                                 f"status {status!r}")
            if status == 0:
                return GREEN, f"the gate finished and exited 0"
            return RED, f"the gate finished and exited {status}"

        pid = data.get("runner_pid")
        if not isinstance(pid, int):
            return UNKNOWN, "running record carries no usable runner pid"
        alive = _alive(pid)
        if alive is None:
            return UNKNOWN, (f"the record says running and whether pid {pid} "
                             "is alive could not be determined")
        if not alive:
            return UNKNOWN, (f"the record says running but pid {pid} is gone: "
                             "the runner died without writing a terminal "
                             "record, so the gate's result is not known")
        return RUNNING, (f"the gate is still running as pid {pid}, started "
                         f"{int(now - started)}s ago")
    except Exception as exc:                       # noqa: BLE001
        return UNKNOWN, f"this mechanism raised: {exc!r}"


def cmd_start(root: Path, label: str, command: list[str]) -> int:
    record, log = _paths(root, label)
    run_id = hashlib.sha256(
        f"{label}|{time.time()}|{os.getpid()}|{command}".encode("utf-8")
    ).hexdigest()[:16]

    runner = [sys.executable, str(Path(__file__).resolve()), "_run",
              "--record", str(record), "--log", str(log),
              "--run-id", run_id, "--"] + command

    log.parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {"cwd": str(root), "env": os.environ.copy(),
                    "stdin": subprocess.DEVNULL,
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    try:
        child = subprocess.Popen(runner, **kwargs)
    except Exception as exc:                       # noqa: BLE001
        print(f"detached-gate: could not spawn the runner: {exc}",
              file=sys.stderr)
        return CONFIG

    # THE RUNNER IS THE ONLY WRITER OF ANY RECORD, and that is a correctness
    # requirement rather than a tidiness one. An earlier shape had `start`
    # write the RUNNING record after spawning, which loses a race that a
    # FAST gate wins every time: the runner finishes and writes the terminal
    # record, then `start` overwrites it with RUNNING, and the record can
    # never become terminal again because the runner has already exited. The
    # state would then be a running record with a dead pid, which this file
    # correctly reads as UNKNOWN forever. A gate that passed in two seconds
    # would be unable to report that it passed.
    #
    # So `start` writes nothing. It waits only for the record to APPEAR,
    # which is the runner's first act and is bounded by process startup, not
    # by the gate. The wait is on the mechanism, never on the work, so the
    # ceiling this file exists to remove is not reintroduced here.
    deadline = time.time() + RECORD_APPEARS_WITHIN
    while time.time() < deadline:
        state, _ = read_state(record, run_id, time.time())
        if state != UNKNOWN:
            # 0 here means TRACKED, not GREEN. See the exit-status paragraph
            # in the module docstring: a fast gate can already be RED by now.
            print(run_id)
            return 0
        if child.poll() is not None and not record.exists():
            break
        time.sleep(0.05)

    print(f"detached-gate: the runner did not write a record within "
          f"{RECORD_APPEARS_WITHIN}s; the gate's state is not tracked and "
          f"nothing may be claimed about it. See {log}", file=sys.stderr)
    return CONFIG


def cmd_run(record: Path, log: Path, run_id: str, command: list[str]) -> int:
    """The hidden mode that actually runs the gate. It is the ONLY writer of
    a terminal record, which is what makes forging awkward."""
    started = time.time()
    base = {
        "format": FORMAT,
        "mechanism": _self_body_sha256(),
        "label": record.stem,
        "run_id": run_id,
        "command": command,
        "started_at": started,
        # os.getpid() and NOT the pid `start` saw. This is the process whose
        # death is the thing that matters: it is the one that will write the
        # terminal record, so its absence is exactly the condition that makes
        # the gate's result unknowable.
        "runner_pid": os.getpid(),
        "log": str(log),
    }
    _write_atomic(record, base)
    try:
        with log.open("w", encoding="utf-8", errors="replace") as handle:
            proc = subprocess.run(command, stdout=handle,
                                  stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL,
                                  env=os.environ.copy())
        status = proc.returncode
    except Exception as exc:                       # noqa: BLE001
        # The gate could not be run at all. That is NOT a red gate and it is
        # NOT a green one: no terminal record is written, so the next read
        # finds a running record whose runner is gone, which is UNKNOWN.
        try:
            log.open("a", encoding="utf-8").write(
                f"\ndetached-gate: the command could not be run: {exc!r}\n")
        except Exception:                          # noqa: BLE001
            pass
        return CONFIG

    base.update({
        "format": FORMAT,
        "mechanism": _self_body_sha256(),
        "run_id": run_id,
        "command": command,
        "started_at": base.get("started_at", started),
        "finished_at": time.time(),
        "exit_status": status,
        "log": str(log),
    })
    _write_atomic(record, base)
    return status


def cmd_state(root: Path, label: str, run_id: str | None) -> int:
    record, _ = _paths(root, label)
    state, reason = read_state(record, run_id, time.time())
    print(f"detached-gate: {state}, {reason}")
    return EXIT[state]


def cmd_report(root: Path, label: str) -> int:
    record, log = _paths(root, label)
    state, reason = read_state(record, None, time.time())
    print(f"detached-gate: {state}, {reason}")
    if log.exists():
        print(f"--- {log} ---")
        sys.stdout.write(log.read_text(encoding="utf-8", errors="replace"))
    else:
        print(f"(no captured output at {log})")
    return EXIT[state]


def _split(argv: list[str]) -> tuple[dict, list[str]]:
    opts: dict = {}
    rest: list[str] = []
    it = iter(argv)
    for a in it:
        if a == "--":
            rest = list(it)
            break
        if a.startswith("--"):
            opts[a[2:]] = next(it, "")
        else:
            rest.append(a)
    return opts, rest


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("start", "state", "report", "_run"):
        print(__doc__, file=sys.stderr)
        return CONFIG
    verb = argv[1]
    opts, rest = _split(argv[2:])

    if verb == "_run":
        try:
            return cmd_run(Path(opts["record"]), Path(opts["log"]),
                           opts["run-id"], rest)
        except KeyError as exc:
            print(f"detached-gate: _run is internal and needs {exc}",
                  file=sys.stderr)
            return CONFIG

    label = opts.get("label")
    if not label or "/" in label or "\\" in label or label.startswith("."):
        print("detached-gate: --label is required and must be a simple name",
              file=sys.stderr)
        return CONFIG

    root = _root(Path(opts.get("repo", ".")))
    if root is None:
        print("detached-gate: no git repository resolves from "
              f"{opts.get('repo', '.')!r}, and the record location is derived "
              "from it", file=sys.stderr)
        return CONFIG

    if verb == "start":
        if not rest:
            print("detached-gate: name the command after --", file=sys.stderr)
            return CONFIG
        return cmd_start(root, label, rest)
    if verb == "state":
        return cmd_state(root, label, opts.get("run-id"))
    return cmd_report(root, label)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
