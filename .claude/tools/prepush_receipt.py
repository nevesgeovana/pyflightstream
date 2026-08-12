# ITACA / pyflightstream shared process kit
# kit-version: 0.2.16
# artifact: prepush_receipt.py
# body-sha256: e44bde8efa27e0bed50db5e10903871936d688c55d833f4c707f29e3ec67aa94
# canonical-source: BUILT for the kit (0.2.15, HUB-11) from the author's specification of 2026-08-01, after the push step failed five times in one evening for five unrelated reasons, none about the code. The pre-push tier re-ran a full suite it had already run green minutes earlier; measured on itaca that suite is 12.1 minutes and the whole hook 12.5 to 13, and CI then runs it three more times. Records: ITC-20260801-2330 (the measurements and the correction of a wrong diagnosis), ITC-20260801-0900 (the lane), coordination/DESIGN_HUB-11_kit_batch.md item 1. 0.2.16 stores the key computed BEFORE the run instead of recomputing one after it (ITC-20260801-2320, against this body's own instruction), and writes NO receipt at all when the guarded command modified the working tree (ITC-20260802-0620: the receipt is written on exit 0, which is before pre-commit judges `files were modified by this hook`, so a receipt written by a failing push made the retry skip and turned a reproducible failure into an intermittent one). One fix, two records. See coordination/DESIGN_HUB-12_kit_batch.md items 2 and 3.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Pre-push receipt: do not re-run a suite that already passed on this tree.

Usage:
    prepush_receipt.py guard [--label <name>] [--repo <path>] -- <command> ...
    prepush_receipt.py status [--label <name>] [--repo <path>] -- <command> ...

``guard`` is the whole mechanism. It computes a KEY over the content under
test, the environment, and the command about to run. If a readable,
unexpired receipt carries that same key, the command is SKIPPED and the exit
status is 0. Otherwise the command RUNS as a child process, its exit status
is read FROM THE PROCESS, and a receipt is written only on exit 0.

``status`` answers the same question and runs nothing, for an operator who
wants to know whether the next push will be fast. It deliberately never
prints the key; see HAND-WRITING below.

WHY THIS EXISTS, with the measurement. itaca's pre-push tier runs the full
suite with coverage plus ``mypy --strict``: 12.1 minutes for the suite alone
(1628 passed, 3 skipped, 2 xfailed, EXIT 0), 12.5 to 13 for the whole hook,
against about 16 seconds for the commit tier. CI then runs the same suite on
three legs, so one push runs it four times, and five on the evening this was
raised, because the session had already run it green ten minutes earlier.

The reason that matters is not the duplication, it is the fragility. In two
lanes the push step failed five separate ways and none of them was about the
code being pushed. A step that expensive and that fragile gets routed around
eventually, and the way it gets routed around is ``--no-verify``. That is the
outcome this file exists to prevent, which is also why it adds NO environment
variable that skips the hook and why nothing here can be configured off.

EVERY UNKNOWN STATE RUNS THE SUITE. That is the acceptance criterion, not a
nicety. Absent receipt, unreadable receipt, malformed receipt, receipt whose
key does not match, receipt older than its time to live, receipt written by a
different version of this format, clock moved backwards, and ANY exception
raised anywhere inside this mechanism: all of them RUN. There is deliberately
no path in which a defect in this file results in a suite being skipped. A
defect here costs time and never safety.

THE ASYMMETRY WITH ``COORD_INCIDENT_LEDGER``, and it is written here rather
than only in the design note because the next reader will otherwise make the
two consistent and break one. There, an ABSENT configuration DENIES the push.
Here, an ABSENT receipt does not deny; it means DO THE WORK. Both are the
fail-CLOSED direction FOR THEIR OWN GUARD, and they point opposite ways. The
ledger guard's safe answer is "stop", because an unreadable ledger cannot
prove that no blocking incident exists. This guard's safe answer is "run",
because an unreadable receipt cannot prove that the suite passed. Making them
point the same way would either let a push through with an unread ledger or
skip a suite that never ran.

WHAT A RECEIPT IS NOT. It proves that a FILE SAYS the suite passed. It does
not prove the suite passed. This is exactly the limit the review attestation
documents about itself: that file proves an attestation exists, not that the
reviewer agents ran. Do not read this one for more than it claims.

HAND-WRITING is made AWKWARD rather than impossible. The receipt is written
by the run itself, at the point where the child's exit status is known, and
no subcommand of this file prints a key, so forging one means reimplementing
the digest below rather than copying a value out of an error message. A
perfectly forged receipt WOULD authorize a skip. That sentence is here
because the alternative is a reader assuming otherwise.

THE KEY, which is the deliverable. Four components:

1. CONTENT, not the commit. The hook tests the WORKING TREE, which can differ
   from HEAD, so ``git rev-parse HEAD`` alone is insufficient. Every path in
   ``git ls-files`` plus every path in
   ``git ls-files --others --exclude-standard``, hashed from its bytes on
   disk, with a distinct marker for a tracked path that is absent. A deleted,
   modified, staged, or untracked-but-not-ignored file all move the key.
   REJECTED: HEAD plus a hash of ``git diff HEAD``. A binary modification
   renders in that diff as "Binary files differ" with no content, so the key
   would not move. Hashing bytes has no such hole and costs under a second on
   a repository of this size. Any path that cannot be read for a reason other
   than absence makes the key UNAVAILABLE, which RUNS.
2. ENVIRONMENT. ``sys.version``, ``platform.platform()``, and the sorted
   ``name==version`` of EVERY distribution ``importlib.metadata`` can see.
   Deliberately a SUPERSET of what the suite uses: a superset
   over-invalidates, and over-invalidating is the fail-closed direction. A
   green run under pytest 8 must not authorize a push under pytest 9, and
   itaca moved both its pytest and pytest-cov floors in one week, so this is
   live and not hypothetical.
3. WHAT ACTUALLY RAN. The child argv verbatim, plus ``--label``. A receipt
   from a partial or deselected run therefore authorizes only an identical
   partial run, which is a mechanism rather than a promise.
4. THIS MECHANISM. The sha256 of this file's own kit body. A promotion of
   this artifact cannot inherit authority that was granted under different
   rules.

WHAT THE KEY DOES NOT COVER, stated rather than hidden.

AMBIENT ENVIRONMENT VARIABLES. Including ``os.environ`` would
over-invalidate on nearly every session, since it carries session
identifiers and working directories, and the mechanism would then never skip
anything. Excluding it means a suite whose result depends on an environment
variable can be authorized by a run made under a different value. A
repository in that position puts the variable and its value into
``--label``, which is part of the key.

THE INTERPRETER THE CHILD RESOLVES, added 0.2.16 from ``ITC-20260801-2320``.
Component 2 describes the interpreter running THIS WRAPPER: ``sys.version``,
``platform.platform()`` and the distributions ``importlib.metadata`` can see
from here. The guarded command resolves its OWN interpreter, through PATH, a
virtual environment, or a launcher, and that one may be a different Python
with a different set of distributions. So a green run made with one
environment on PATH can authorize a skip for a push made with another. It is
NOT a new hole opened by anything here; it is the boundary of what a wrapper
can observe about a child it has not run yet. A repository whose pre-push
tier can resolve more than one interpreter puts the one it means into
``--label``, exactly as for an environment variable.

THE TIME TO LIVE IS 4 HOURS, and the number has a reason. Content-keying
argues that a receipt never expires; reality argues otherwise in three shapes
the key cannot see: a yanked or re-resolved dependency, a clock-dependent
test crossing a boundary, and a machine that changed underneath the
interpreter. The measured benefit lives entirely inside one working session:
the waste observed was a suite run green and then re-run at the push minutes
to tens of minutes later. Four hours spans that session. Longer buys nothing
measured and widens every risk the key cannot see; much shorter starts
failing to cover the ordinary case it exists for. The receipt records its own
ttl for a reader, and the DECISION ignores that field and uses the constant
below, so a receipt claiming a longer life does not get one.

A FAILING RUN DELETES THE RECEIPT. Without that, a tree that passed and then
failed on a flaky or environmental cause would still carry a matching key and
the next push would skip a red suite.

THE KEY STORED IS THE ONE COMPUTED BEFORE THE RUN, because that is the
content that was tested. THIS WAS A CLAIM AND NOT A FACT UNTIL 0.2.16.
``ITC-20260801-2320``, the receipt key is stored after the run: ``guard``
computed a key in ``_decide``, discarded it, and recomputed one after the
child exited, against this paragraph's own instruction. Measured on a real
temporary repository by the reporting lane AND independently by an architect
lens, each in its own scratch repository: a guarded command that exits 0 and
writes one untracked, unignored file left a receipt keyed on the POST-run
tree, and the next ``status`` answered SKIP over content the suite never saw.
The key computed before the run is now the key stored.

AND A RUN THAT MODIFIED THE TREE WRITES NO RECEIPT AT ALL, 0.2.16, from
``ITC-20260802-0620``, the first push fails on `files were modified` and the
receipt hides it. The two are one fix; they arrived as two records and they
have one sentence between them.

The receipt is written when the guarded command exits 0. A caller can judge
that command AFTER its exit status and on a different criterion:
pre-commit's ``files were modified by this hook`` FAILS a hook that exited 0
but changed files. So the failing run wrote a receipt, the retry skipped the
suite, and the push passed. One occurrence in three attempts, and the retry's
success is what made it look intermittent; a faithful reproduction with the
receipt removed did not reproduce. The mechanism was behaving exactly as
specified and this was its emergent cost.

The wrapper cannot see pre-commit's verdict. It does not need to: that
verdict is computed from an observable the wrapper CAN see, which is whether
the command changed the working tree. So the content digest is recomputed
once after a green run, and if it differs from the pre-run one, NO RECEIPT IS
WRITTEN and the reason is printed. The next run does the work again, and the
failure stays reproducible.

Keeping the pre-run key alone would already be safe, since a key describing a
tree that no longer exists can never match a later one, so the next run would
RUN. It would be safe silently, by accident, through a receipt that is dead
on arrival. Refusing to write it makes the property observable, gives the
operator the sentence that explains the slow retry, and costs one content
digest, measured at 0.42 s against a 12.1-minute suite.

CROSS-REPOSITORY. Nothing here assumes any repository's paths or its
``.venv``. The root is resolved with ``git rev-parse --show-toplevel`` from
the caller's working directory and the receipt sits beside the attestation.
There is NO environment variable, deliberately: an env var's unset branch is
charter material at each consumer rather than the kit's to decide alone, and
this location is derivable, so the question does not have to be asked. Each
consumer must gitignore the receipt path, beside the attestation; that is not
needed for the key, which excludes the path explicitly, but is needed so the
file does not enter a repository's own shipped-surface and house-style walks.

Standalone, stdlib only, no third-party deps, like every kit checker.
Exit status: the child's, or 0 on a skip, or 2 for a CONFIG error.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

RECEIPT = ".claude/.prepush_receipt.json"
FORMAT = 1
TTL_SECONDS = 4 * 60 * 60
MARKER = "END KIT PROVENANCE"


class Unavailable(Exception):
    """The key cannot be computed, so the command must run."""


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise Unavailable(f"git {' '.join(args)}: "
                          f"{r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def _self_body_sha256() -> str:
    """This file's kit body, by the same rule the drift tests use.

    The body rather than the whole file, and normalized, so a checkout that
    flipped line endings does not read as a different mechanism.
    """
    text = Path(__file__).read_text(encoding="utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if MARKER in text:
        after = text.split(MARKER, 1)[1]
        text = after.split("\n", 1)[1] if "\n" in after else ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _content_digest(root: Path) -> str:
    """Hash the working tree as git sees it, by content."""
    tracked = [p for p in _git(root, "ls-files", "-z").split("\0") if p]
    others = [p for p in _git(root, "ls-files", "--others",
                              "--exclude-standard", "-z").split("\0") if p]
    h = hashlib.sha256()
    for rel in sorted(set(tracked) | set(others)):
        if rel == RECEIPT:
            # Excluded by exact path: it is written into the tree it
            # measures and would otherwise never match itself.
            continue
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        path = root / rel
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            # A tracked path deleted from the working tree. This is a real
            # state with a stable meaning, so it gets a marker rather than
            # making the whole key unavailable.
            h.update(b"ABSENT\0")
            continue
        except OSError as exc:
            # Anything else (a directory where a file was expected, a
            # permission refusal, a submodule gitlink) is a state this
            # digest cannot describe honestly, so it refuses to describe it.
            raise Unavailable(f"cannot read {rel}: {exc}") from exc
        h.update(hashlib.sha256(data).hexdigest().encode("ascii"))
        h.update(b"\0")
    return h.hexdigest()


def _environment_digest() -> str:
    """Interpreter, platform, and every visible distribution."""
    from importlib import metadata

    names = []
    for dist in metadata.distributions():
        try:
            name = dist.metadata["Name"]
        except Exception:  # a broken dist must not be silently dropped
            raise Unavailable("an installed distribution has no readable "
                              "metadata")
        if name:
            names.append(f"{name}=={dist.version}")
    payload = "\n".join([sys.version, platform.platform(), *sorted(set(names))])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_key(root: Path, command: list[str], label: str,
                content: str | None = None) -> str:
    """The key. ``content`` may be supplied when it was already computed.

    The parameter exists at 0.2.16 so that the key stored after a run is
    built from the content digest taken BEFORE it, rather than from a
    second walk of a tree that may have changed underneath. See ``guard``.
    """
    if content is None:
        content = _content_digest(root)
    payload = json.dumps(
        {
            "format": FORMAT,
            "content": content,
            "environment": _environment_digest(),
            "command": command,
            "label": label,
            "mechanism": _self_body_sha256(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evaluate(path: Path, key: str, now: float) -> tuple[bool, str]:
    """Decide whether the receipt at ``path`` authorizes a skip.

    Returns (skip, reason). Every branch that is not an exact match returns
    False, and the reason is written for an operator rather than a debugger.
    """
    if not path.is_file():
        return False, "no receipt"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"receipt unreadable ({exc})"
    if not raw.strip():
        return False, "receipt empty"
    try:
        record = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return False, "receipt malformed"
    if not isinstance(record, dict):
        return False, "receipt is not an object"
    if record.get("receipt_version") != FORMAT:
        return False, "receipt written by a different receipt format"
    if record.get("outcome") != "pass" or record.get("exit_status") != 0:
        return False, "receipt does not record a pass"
    if record.get("key") != key:
        # Deliberately does not print either key. Printing the expected one
        # would hand a forger the value the digest exists to withhold.
        return False, "receipt key does not match this tree, environment or command"
    written = record.get("written_at")
    if not isinstance(written, (int, float)) or isinstance(written, bool):
        return False, "receipt has no usable timestamp"
    age = now - float(written)
    if age < 0:
        return False, "receipt is dated in the future; the clock moved"
    if age > TTL_SECONDS:
        return False, (f"receipt expired ({int(age)}s old, "
                       f"ttl {TTL_SECONDS}s)")
    return True, f"receipt valid ({int(age)}s old)"


def _decide(root: Path, command: list[str], label: str
            ) -> tuple[bool, str, str | None, str | None]:
    """The whole decision, and any failure inside it means RUN.

    This is the acceptance criterion in one function: there is no exception
    path out of here that returns True.

    Returns ``(skip, reason, key, content)``. The last two are the values
    computed BEFORE the command runs, and they are returned rather than
    discarded, which is ``ITC-20260801-2320``, the receipt key is stored
    after the run. Either is None when it could not be computed, and a
    None key means no receipt may be written afterwards.
    """
    path = root / RECEIPT
    try:
        content = _content_digest(root)
        key = compute_key(root, command, label, content)
    except Unavailable as exc:
        return False, f"key unavailable: {exc}", None, None
    except Exception as exc:  # noqa: BLE001 - deliberate: unknown means run
        return False, f"key computation failed: {exc!r}", None, None
    try:
        skip, reason = evaluate(path, key, time.time())
    except Exception as exc:  # noqa: BLE001 - deliberate: unknown means run
        return False, f"receipt evaluation failed: {exc!r}", key, content
    return skip, reason, key, content


def _write(root: Path, command: list[str], label: str, key: str) -> None:
    record = {
        "receipt_version": FORMAT,
        "key": key,
        "written_at": time.time(),
        "ttl_seconds": TTL_SECONDS,
        "command": command,
        "label": label,
        "exit_status": 0,
        "outcome": "pass",
        "head": _git(root, "rev-parse", "HEAD").strip(),
        "note": ("This records that the command above exited 0 on the tree "
                 "and environment the key covers. It proves a file says the "
                 "suite passed; it does not prove the suite passed."),
    }
    path = root / RECEIPT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def _discard(root: Path) -> None:
    try:
        (root / RECEIPT).unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        print(f"prepush-receipt: could not remove the receipt: {exc}",
              file=sys.stderr)


def _root(where: Path) -> Path | None:
    r = subprocess.run(["git", "-C", str(where), "rev-parse",
                        "--show-toplevel"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return Path(r.stdout.strip())


def guard(root: Path, command: list[str], label: str, run: bool) -> int:
    skip, reason, key, content = _decide(root, command, label)
    if skip:
        print(f"prepush-receipt: SKIP, {reason}")
        print(f"prepush-receipt: not run: {' '.join(command)}")
        return 0
    if not run:
        print(f"prepush-receipt: WOULD RUN, {reason}")
        return 0
    print(f"prepush-receipt: RUN, {reason}")
    status = subprocess.run(command, cwd=str(root)).returncode
    if status != 0:
        # A tree that passed and then failed must not keep authority to skip.
        _discard(root)
        return status
    if key is None:
        # The key could not be computed before the run, so there is no
        # honest key to store. Recomputing one now would describe a tree
        # the suite was never measured against, which is the defect below.
        print(f"prepush-receipt: passed, but no receipt written ({reason})",
              file=sys.stderr)
        return 0
    # DID THE COMMAND MODIFY THE TREE. ITC-20260802-0620, the first push
    # fails on `files were modified` and the receipt hides it. The receipt
    # is written when the guarded command exits 0, and pre-commit's own
    # verdict on a hook is decided AFTER that exit status, from exactly
    # this observable: whether the hook changed files. So a run that
    # modified the tree, exited 0, and was then FAILED by pre-commit used
    # to leave a receipt, and the retry skipped the suite and passed. A
    # reproducible failure became an intermittent one.
    #
    # This wrapper cannot see pre-commit's verdict and does not need to.
    # It can see the thing that verdict is computed from, and when the
    # tree moved it declines to authorise anything at all.
    try:
        after = _content_digest(root)
    except Exception as exc:  # noqa: BLE001 - unknown means no receipt
        print(f"prepush-receipt: passed, but no receipt written ({exc!r})",
              file=sys.stderr)
        return 0
    if after != content:
        print("prepush-receipt: the command MODIFIED the working tree, so no "
              "receipt was written. The suite measured the tree as it was "
              "BEFORE the run, and a caller that judges this command by what "
              "it changed (pre-commit's `files were modified by this hook`) "
              "has not judged it yet. The next run does the work again, "
              "which keeps that failure reproducible.", file=sys.stderr)
        return 0
    try:
        _write(root, command, label, key)
    except (OSError, Unavailable) as exc:
        # Failing to write a receipt costs the next run its time and nothing
        # else, so it is reported and is never an error.
        print(f"prepush-receipt: passed, but no receipt written ({exc})",
              file=sys.stderr)
        return 0
    print(f"prepush-receipt: receipt written, valid for {TTL_SECONDS}s "
          "on this tree, environment and command")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("guard", "status"):
        print(__doc__, file=sys.stderr)
        return 2
    rest = argv[2:]
    if "--" not in rest:
        print("no command given; usage: prepush_receipt.py guard "
              "[--label <name>] [--repo <path>] -- <command> ...",
              file=sys.stderr)
        return 2
    head, command = rest[: rest.index("--")], rest[rest.index("--") + 1:]
    if not command:
        print("the command after -- is empty", file=sys.stderr)
        return 2
    label, where = "", Path.cwd()
    i = 0
    while i < len(head):
        if head[i] == "--label" and i + 1 < len(head):
            label = head[i + 1]
            i += 2
        elif head[i] == "--repo" and i + 1 < len(head):
            where = Path(head[i + 1])
            i += 2
        else:
            print(f"unknown option {head[i]!r}", file=sys.stderr)
            return 2
    root = _root(where)
    if root is None:
        print(f"{where} is not a git repository", file=sys.stderr)
        return 2
    return guard(root, command, label, run=argv[1] == "guard")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
