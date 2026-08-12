# ITACA / pyflightstream shared process kit
# kit-version: 0.2.17
# artifact: review_runner.py
# body-sha256: f906c6c92b3b504ade3e4defcfe03803925b33f66128acf35101800bfab0025c
# canonical-source: BUILT for the kit (0.2.11, HUB-9, BRF-061 item 15, author decision 7) from two recorded failures with one structural cause: a reviewer ran git restore in the live tree and destroyed a lane's edits, and two Bash-holding lenses shared one worktree and corrupted each other's measurements (ITC-20260730-0250). One detached worktree per lens, diff and paths only, findings collected at close, worktree removed; a reviewer never receives the live tree as cwd. The charters' restore-prohibition paragraphs shrink to a pointer at each repository's next re-vendor, now that the mechanism they asked for exists. 0.2.15 fixes two defects both measured by lanes: ITC-20260801-0130, close aborting on the first worktree it cannot remove, stranding the rest AND destroying their findings files; and ITC-20260801-1600, the three RR_ files sitting inside the worktree where a house-style walk scans them, reddening every Bash lens. It also fixes a third defect found by executing this promotion's own contract fixture rather than by reading: the shared temp root was keyed on the repository's directory NAME alone, so two checkouts with the same basename shared one root and one repository's close enumerated the other's worktrees. See coordination/DESIGN_HUB-11_kit_batch.md item 7. 0.2.16 fixes ITC-20260802-0010, close force-deletes a worktree a lens is still using: the rmtree fallback is gated on git no longer registering the path, and the sidecar is re-read immediately before removal so a finding written AFTER collection is collected and that sidecar is kept. See coordination/DESIGN_HUB-12_kit_batch.md item 4. 0.2.17 fixes BRF-077: `close` printed `len(collected)`, which counts WORKTREES, so it printed the same number whether five lenses reported or none did. It now counts lenses that actually WROTE and NAMES the silent ones. The trap the fix had to clear is that `cmd_open` seeds every findings file with a heading, measured at 68 bytes on the fixture, so a byte-length test would have counted a lens that never wrote. See coordination/DESIGN_HUB-13_kit_0217.md item 7.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env python3
"""Review runner: one detached worktree per reviewer lens, never the live tree.

Usage:
    review_runner.py open  <repo> [--ref HEAD] [--base <rev>] <lens> [<lens> ...]
    review_runner.py close <repo> [--out <dir>]

WHY THIS EXISTS, twice over. A recorded incident has a reviewer running
``git restore`` inside the live tree and destroying the session's edits; a
second (`ITC-20260730-0250`) has two Bash-holding lenses sharing one
worktree and corrupting each other's measurements. Both failure modes are
the same structural cause: reviewers execute inside a tree someone else is
mutating. The charters said a separate worktree "would be stronger and is
not in place"; this artifact is that mechanism, so the restore-prohibition
paragraphs can shrink to a pointer at each repository's next re-vendor.

``open`` creates, per lens, a DETACHED worktree of ``--ref`` under the
system temp directory, and writes BESIDE it, in a sidecar directory named
``<worktree>.io``:

  RR_DIFF.patch   ``git diff <base>..<ref>`` (base defaults to the last
                  commit on any remote, i.e. the unpushed range; an empty
                  range yields an empty patch, stated in the file)
  RR_PATHS.txt    the changed paths, one per line
  RR_FINDINGS.md  an empty findings file the lens appends to

and prints one tab-separated line per lens, five fields:

    <lens>	<worktree>	<diff>	<paths>	<findings>

BESIDE THE WORKTREE AND NOT INSIDE IT, changed at 0.2.15 from
``ITC-20260801-1600``. Those three files used to live inside the worktree,
where they are untracked-but-not-ignored, so a repository whose house-style
walk asks git for tracked plus untracked files SCANNED THEM. ``RR_DIFF.patch``
contains the diff, so a diff touching a file that quotes the author's name
made every reviewer lens report a RED that does not exist on the reviewed
ref. Measured in lane ITA-4: two independent lenses reported it without
prompting, both correctly called it a harness artifact, and both spent tool
calls on it first; round two of that lane carried an "ignore these" paragraph
in all four lens prompts, which is a workaround living in a prompt. The cost
is not the red, it is that a reviewer whose first measurement is a false
positive learns to discount the guard.

THE ALTERNATIVE WAS MEASURED AND REJECTED. Adding the three names to the
worktree's ``.git/info/exclude`` looks cheaper and changes no interface, and
it cannot work: inside a linked worktree ``git rev-parse --git-path
info/exclude`` resolves to the COMMON directory, ``<repo>/.git/info/exclude``.
There is no per-worktree exclude file git reads. So that shape writes into
the operator's own repository, a change that outlives the review and that a
crashed run leaves behind. Measured 2026-08-01 in a scratch repository rather
than argued. Having the consumers exempt the filenames was rejected by the
incident itself: it puts a kit artifact's name into every consumer's guard,
and a repository that forgets inherits the false red silently.

The worktree is therefore a PRISTINE checkout of the reviewed ref. Nothing
the ref does not contain appears in it, under ANY consumer's scanning
discipline rather than only one that keys on ignored-versus-untracked.

``close`` collects every ``RR_FINDINGS.md`` into ``--out`` (default: print
to stdout under a per-lens heading), then removes the worktrees with
``git worktree remove --force`` and prunes. A worktree is only ever removed
by ``close``; a crashed run leaves the trees on disk for inspection and a
later ``close`` still finds them through the marker prefix.

COLLECT EVERYTHING FIRST, THEN REMOVE, AND NEVER ABORT ON A REMOVAL,
changed at 0.2.15 from ``ITC-20260801-0130``. ``close`` used to collect and
remove one worktree at a time and to abort on the first git failure, so a
single lens still running inside its own worktree stranded every worktree
after it AND their findings were never collected. Measured: four worktrees,
the QA lens still running, its removal denied, ``close`` aborted, two later
worktrees left registered with no findings collected, and the QA findings
file printed and then gone. Those findings survived only because an agent
still held them and returned them as text minutes later; had it crashed,
an entire lens's work would have been destroyed by the step whose job is to
collect it. A lens still running is the ORDINARY case, not an exceptional
one.

The two fixes reinforce each other rather than overlapping: with the findings
outside the worktree, a failed worktree removal cannot destroy them at all.

THE FALLBACK IS GATED AND THE SIDECAR IS NEVER DISCARDED UNREAD, added at
0.2.16 from ``ITC-20260802-0010``, close force-deletes a worktree a lens is
still using. Two changes, because the incident has two halves and its own
lane corrected itself twice before settling which was which.

1. ``shutil.rmtree`` now runs ONLY when git no longer registers the path,
   parsed from ``git worktree list --porcelain`` after the prune. Through
   0.2.15 any removal failure reached it, justified by the HALF-REMOVED
   state and keyed on nothing that tests for it: "removal failed and the
   directory exists" is also exactly what a BUSY worktree looks like. A busy
   worktree is now a reported failure with exit 1, which is what the retry
   text already told the operator to do.
2. Before a sidecar is removed, its ``RR_FINDINGS.md`` is re-read and
   compared with what phase 1 collected. If it grew, the newer bytes are
   collected in its place and THE SIDECAR IS KEPT. This is the half the
   fallback gate does not reach and is the one the incident's second
   correction identified as the real boundary: not the fallback, not the
   platform, but the COLLECTION. What a lens writes before phase 1 survives;
   what it wrote after used to go with the sidecar on the ORDINARY path, on
   every platform, because a SUCCESSFUL removal deletes the sidecar too.

WHAT NEITHER OF THEM DOES, stated so this file is not read for more than it
holds: a successful ``worktree remove --force`` still pulls a running lens's
working DIRECTORY out from under it, and nothing portable can detect that a
process is inside. ``close`` is not a way to ask whether a lens has finished.
The operator rule stands: run it once every lens has reported. What changed
is that breaking that rule now costs a lens its cwd and no longer costs it
its findings.

Standalone, stdlib only, no third-party deps, like every kit checker.
Exit 0 on success, 1 on a git failure (reported with the command), 2 for a
CONFIG error (not a repository, unknown usage, no lenses). A ``close`` that
collected every findings file and failed to remove some worktrees exits 1
and names each failure with the command that clears it: the collection
succeeded and the tidying did not, and reporting that as success would hide
worktrees that are still registered.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PREFIX = "rr-"
SIDECAR = ".io"


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"git {' '.join(args)} failed in {repo}: "
              f"{r.stderr.strip() or r.stdout.strip()}", file=sys.stderr)
        raise SystemExit(1)
    return r.stdout


def _git_try(repo: Path, *args: str) -> tuple[bool, str]:
    """A git call whose failure is REPORTED and not raised.

    ``close`` uses this for every removal. The raising form aborts the whole
    command at the first failure, which is what stranded three worktrees and
    lost their findings; a removal that fails while a lens is still working
    inside is the ordinary case and must not stop the rest.
    """
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return False, (r.stderr.strip() or r.stdout.strip()
                       or f"git exited {r.returncode}")
    return True, r.stdout


def _registered_worktrees(repo: Path) -> set[str] | None:
    """Every path git still holds a worktree registration for.

    None when git could not be asked, which is NOT the same as "none are
    registered" and must not be read as one. See ``cmd_close``: the
    difference decides whether a directory may be deleted.
    """
    ok, out = _git_try(repo, "worktree", "list", "--porcelain")
    if not ok:
        return None
    paths: set[str] = set()
    for line in out.splitlines():
        if not line.startswith("worktree "):
            continue
        raw = line[len("worktree "):].strip()
        try:
            paths.add(str(Path(raw).resolve()))
        except OSError:
            paths.add(raw)
    return paths


def _reported(lens: str, text: str) -> bool:
    """Did this lens actually write anything, beyond what ``open`` seeded?

    THREE SHAPES OF NOTHING, and only the first is obvious. `close` used to
    count all three as a reported finding (BRF-077, HUB-13 item 7).

    1. NO FILE AT ALL. Collection substitutes the literal
       ``(no findings file)``, which is this module's own placeholder and
       never a lens's words.
    2. AN EMPTY OR WHITESPACE-ONLY FILE.
    3. THE SEEDED HEADING, UNTOUCHED, and this is the one a byte-length test
       gets wrong. ``cmd_open`` writes ``# Findings: <lens> lens, <range>``
       into every findings file before any lens runs, so a lens that never
       wrote leaves a file that is 68 bytes on the measured fixture and
       non-empty by every naive test. Counting that as a report is exactly
       the defect: a number that reads as confirmation and cannot fail.

    The range is not available here, so the seeded line is matched by its
    prefix rather than reconstructed. A lens that wrote its own heading and
    nothing else is therefore ALSO counted as silent, which is correct: a
    heading is not a finding.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if stripped == "(no findings file)":
        return False
    seed = f"# Findings: {lens} lens,"
    remainder = [line for line in stripped.splitlines()
                 if line.strip() and not line.strip().startswith(seed)]
    return bool(remainder)


def _deliver(out: Path | None, lens: str, text: str) -> None:
    """Hand one lens's findings to the caller, by file or by stdout."""
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / f"findings-{lens}.md").write_text(text, encoding="utf-8")
    else:
        print(f"---- {lens} ----\n{text}")


def _root(repo: Path) -> Path:
    """The shared temp root for one repository.

    The directory NAME alone was the key through 0.2.11, and that is a
    collision: two checkouts with the same basename, which is the ordinary
    shape of a clone and a scratch copy, shared one root, so one repository's
    ``close`` enumerated the other's worktrees and reported them as its own
    with `is not a working tree`. Found by execution while building this
    promotion's own contract fixture, not by reading. The path digest keeps
    the name readable and makes the key unique.

    CONSEQUENCE FOR ADOPTION, and it is why `close` must be run BEFORE
    re-vendoring: a worktree opened under the old root is not found under the
    new one.
    """
    base = Path(tempfile.gettempdir()) / "kit-review-runner"
    resolved = repo.resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:8]
    return base / f"{resolved.name}-{digest}"


def cmd_open(repo: Path, ref: str, base: str | None,
             lenses: list[str]) -> int:
    _git(repo, "rev-parse", "--verify", ref)
    if base is None:
        # The unpushed range: what a PUSH review must read. No remote at all
        # is reported rather than guessed around.
        remotes = _git(repo, "remote").split()
        if not remotes:
            print("no remote and no --base given; name the base revision "
                  "the review diff starts from", file=sys.stderr)
            return 2
        merge_base = _git(repo, "rev-list", ref, "--not", "--remotes",
                          "--reverse").split()
        base = (merge_base[0] + "^") if merge_base else ref
    diff = _git(repo, "diff", f"{base}..{ref}")
    paths = _git(repo, "diff", "--name-only", f"{base}..{ref}")
    root = _root(repo)
    root.mkdir(parents=True, exist_ok=True)
    for lens in lenses:
        wt = root / f"{PREFIX}{lens}"
        io = root / f"{PREFIX}{lens}{SIDECAR}"
        if wt.exists() or io.exists():
            print(f"{wt} already exists; run close first", file=sys.stderr)
            return 2
        _git(repo, "worktree", "add", "--detach", str(wt), ref)
        # The sidecar, never the worktree. See ITC-20260801-1600 in the
        # module docstring: these three files are untracked-but-not-ignored,
        # and a repository that walks that set scans them.
        io.mkdir(parents=True, exist_ok=True)
        (io / "RR_DIFF.patch").write_text(
            diff or f"(empty diff: {base}..{ref} contains no change)\n",
            encoding="utf-8")
        (io / "RR_PATHS.txt").write_text(paths, encoding="utf-8")
        (io / "RR_FINDINGS.md").write_text(
            f"# Findings: {lens} lens, {base}..{ref}\n", encoding="utf-8")
        print(f"{lens}\t{wt}\t{io / 'RR_DIFF.patch'}\t"
              f"{io / 'RR_PATHS.txt'}\t{io / 'RR_FINDINGS.md'}")
    return 0


def cmd_close(repo: Path, out: Path | None) -> int:
    root = _root(repo)
    trees = sorted(p for p in root.glob(f"{PREFIX}*")
                   if p.is_dir() and not p.name.endswith(SIDECAR)) \
        if root.exists() else []
    if not trees:
        print(f"no review worktrees under {root}; nothing to close")
        return 0

    # PHASE 1: COLLECT EVERYTHING. Nothing is removed until every findings
    # file is in hand, so no removal failure can cost a lens its work.
    collected: list[tuple[Path, str, str]] = []
    for wt in trees:
        lens = wt.name[len(PREFIX):]
        sidecar = wt.parent / f"{wt.name}{SIDECAR}" / "RR_FINDINGS.md"
        # The in-worktree path is read as a FALLBACK, so a worktree opened by
        # a pre-0.2.15 body is still collected rather than silently reported
        # as having no findings.
        legacy = wt / "RR_FINDINGS.md"
        if sidecar.exists():
            text = sidecar.read_text(encoding="utf-8")
        elif legacy.exists():
            text = legacy.read_text(encoding="utf-8")
        else:
            text = "(no findings file)\n"
        collected.append((wt, lens, text))

    for wt, lens, text in collected:
        _deliver(out, lens, text)

    # The text each lens is FINALLY credited with. It starts as what phase 1
    # collected and is replaced if phase 3 finds newer bytes, so the count
    # printed at the end describes what was actually delivered rather than
    # what was read first. A lens that wrote only after collection would
    # otherwise be reported as silent when its finding WAS collected.
    final: dict[str, str] = {lens: text for _, lens, text in collected}

    # PHASE 2: REMOVE, continuing past every failure. A lens still running
    # inside its worktree is the ordinary case.
    failures: list[tuple[Path, str]] = []
    superseded: list[str] = []
    removed = 0
    for wt, lens, text in collected:
        ok, message = _git_try(repo, "worktree", "remove", "--force", str(wt))
        if not ok:
            # THE RETRY MUST BE ABLE TO RECOVER, which is the second half of
            # ITC-20260801-0130 and was measured on this promotion's own
            # fixture. A failed `worktree remove --force` can leave the tree
            # HALF removed: git has forgotten the registration while the
            # directory is still on disk, so a second close is told `is not a
            # working tree` and the entry can never be cleared by this tool
            # at all. Prune first, then take the directory directly.
            #
            # AND THE FALLBACK IS GATED, 0.2.16, from ITC-20260802-0010,
            # close force-deletes a worktree a lens is still using. Through
            # 0.2.15 ANY removal failure reached `shutil.rmtree`, justified
            # by the half-removed state and keyed on nothing that checks for
            # it: the condition it actually tested, "removal failed and the
            # directory exists", is also exactly what a BUSY worktree looks
            # like, which the code two lines down calls the ordinary case.
            # So ask git. If it still holds the registration, the state is
            # not the half-removed one and the directory is left alone; the
            # busy case stays a reported failure with exit 1, which is what
            # the retry text below already tells the operator to do.
            #
            # Deleting a directory is the one destructive act in this file
            # and it is bounded three ways now: the path came from this
            # tool's own root, carries its own PREFIX, git has just tried to
            # delete it, and git no longer registers it.
            _git_try(repo, "worktree", "prune")
            if not wt.exists():
                ok = True
            else:
                registered = _registered_worktrees(repo)
                if registered is None:
                    message = (f"{message}; git could not be asked whether it "
                               "still registers this worktree, so the "
                               "directory was left alone")
                elif str(wt.resolve()) in registered:
                    message = (f"{message}; git still registers it as a "
                               "worktree, so this is not the half-removed "
                               "state and the directory was left alone")
                else:
                    try:
                        shutil.rmtree(wt)
                        ok = True
                    except OSError as exc:
                        message = (f"{message}; git no longer registers it, "
                                   "so the directory was taken directly, and "
                                   f"that failed too: {exc}")
        if not ok:
            failures.append((wt, message))
            continue
        removed += 1
        # THE SIDECAR IS NEVER DISCARDED UNREAD, 0.2.16, and this is the
        # half of ITC-20260802-0010 that the fallback gate above does NOT
        # address. The incident was corrected twice by its own lane, and the
        # second correction is the one that matters: the real boundary is
        # not the fallback and not the platform, it is the COLLECTION. What
        # a lens writes BEFORE phase 1 survives; what it writes after used
        # to be deleted with the sidecar, on the ORDINARY path, on every
        # platform, because a successful removal deletes the sidecar too.
        #
        # So the findings file is re-read immediately before the sidecar
        # goes. If it still says what phase 1 collected, nothing changes. If
        # it says MORE, the newer bytes are delivered in place of the older
        # and THE SIDECAR IS KEPT, because a lens that was demonstrably
        # still writing a moment ago should not have its file removed by the
        # step whose job is to collect it.
        #
        # What this cannot do is stated in the module docstring: it does not
        # save the lens's working DIRECTORY, which a successful
        # `worktree remove --force` takes out from under a running process.
        sidecar_dir = wt.parent / f"{wt.name}{SIDECAR}"
        findings = sidecar_dir / "RR_FINDINGS.md"
        if findings.is_file():
            try:
                latest = findings.read_text(encoding="utf-8")
            except OSError as exc:
                superseded.append(f"{lens}: its findings file could not be "
                                  f"re-read before removal ({exc}), so the "
                                  "sidecar was kept")
                continue
            if latest != text:
                _deliver(out, lens, latest)
                final[lens] = latest
                superseded.append(
                    f"{lens}: wrote to its findings file AFTER it was "
                    "collected. The newer content was collected in its "
                    f"place and the sidecar was KEPT at {sidecar_dir}")
                continue
        for child in sorted(sidecar_dir.glob("*")) if sidecar_dir.is_dir() \
                else []:
            try:
                child.unlink()
            except OSError:
                pass
        try:
            sidecar_dir.rmdir()
        except OSError:
            pass
    _git_try(repo, "worktree", "prune")

    # THE COUNT NAMES WHAT IT COUNTED, 0.2.17, from BRF-077 and HUB-13 item
    # 7. Through 0.2.16 this printed `len(collected)`, which is the number of
    # WORKTREES and not the number of lenses that reported: it printed the
    # same number whether five lenses wrote findings or none did, because a
    # lens that never wrote still leaves the heading `cmd_open` seeded and a
    # lens with no file at all still gets the `(no findings file)`
    # placeholder counted. A number that reads as confirmation and cannot
    # fail is the same shape as a guard proven only green.
    silent = sorted(lens for lens, text in final.items()
                    if not _reported(lens, text))
    reported = len(final) - len(silent)
    print(f"collected {reported} findings file(s) with content, of "
          f"{len(final)} lens(es); removed {removed} of {len(collected)} "
          "review worktree(s)")
    if silent:
        print(f"{len(silent)} lens(es) wrote NOTHING: {', '.join(silent)}")
        print("  An empty findings file is not a clean review; it is a lens "
              "that did not write. A lens with no writing tool cannot write "
              "one at all, and returns its findings as final text that a "
              "human must absorb. Read the transcript for these before "
              "treating the review as complete.")
    if superseded:
        print(f"{len(superseded)} lens(es) wrote after collection; their "
              "newer findings were collected and their sidecars kept:")
        for item in superseded:
            print(f"  {item}")
        print("  A lens still writing when close ran is the cause. close is "
              "not a way to ask whether a lens has finished; run it once "
              "every lens has reported.")
    if failures:
        print(f"{len(failures)} worktree(s) could NOT be removed. Every "
              "findings file above was collected first, so nothing was lost; "
              "these are still registered and still on disk:", file=sys.stderr)
        for wt, message in failures:
            print(f"  {wt}: {message}", file=sys.stderr)
        print("  A lens still working inside its worktree is the usual "
              "cause. Let it finish, then run close again; it collects and "
              "removes what is left.", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] not in ("open", "close"):
        print(__doc__, file=sys.stderr)
        return 2
    repo = Path(argv[2])
    if not (repo / ".git").exists():
        print(f"{repo} is not a git repository", file=sys.stderr)
        return 2
    rest = argv[3:]
    if argv[1] == "open":
        ref, base, lenses = "HEAD", None, []
        it = iter(rest)
        for a in it:
            if a == "--ref":
                ref = next(it, "HEAD")
            elif a == "--base":
                base = next(it, None)
            else:
                lenses.append(a)
        if not lenses:
            print("no lenses named; e.g. architect qa vv", file=sys.stderr)
            return 2
        return cmd_open(repo, ref, base, lenses)
    out = None
    if "--out" in rest:
        out = Path(rest[rest.index("--out") + 1])
    return cmd_close(repo, out)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
