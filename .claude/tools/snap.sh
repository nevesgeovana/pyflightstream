# ITACA / pyflightstream shared process kit
# kit-version: 0.2.5
# artifact: snap.sh
# body-sha256: 0835e6ae1bd43d05e213a88552bcd94a1b91ebec946f9dabb5411d7595b265d1
# canonical-source: local-only _private snapshot tool, shared across all three workspaces plus the shared incident ledger.
# note: derived copy; canonical master at the coordination level (`ClaudeCoordinator/kit`); do not hand-edit, re-vendor on promotion.
# END KIT PROVENANCE (body verbatim below)
#!/usr/bin/env bash
# Local-only version control for the _private trees of both repositories.
#
# Why this exists: _private holds the critical session state (plan.csv,
# DECISION_QUEUE.md, STATUS.md, logbook.csv, handoffs) and is deliberately
# gitignored, so it had NO version control. On 2026-07-23 a truncating
# read-modify-write destroyed plan.csv (73 of 77 rows) and only the OneDrive
# version history got it back, manually. This gives `git restore` instead.
#
# Design: the git dir lives HERE, outside OneDrive, while the work tree stays
# inside the OneDrive-synced _private. That sync is the author's private mobile
# channel (notes and files dropped from the phone) and is unaffected; keeping
# .git out of it avoids the corruption that concurrent OneDrive sync causes on
# git internals, which matters because several lane sessions run at once.
#
# These repositories have NO remote and never get one: local-only versioning of
# local-only files, so invariant 5 holds.
#
# Usage:
#   snap.sh                      snapshot both repos
#   snap.sh pyflightstream       snapshot one
#   snap.sh <repo> log           recent snapshots
#   snap.sh <repo> restore <file> [commit]
#                                restore one file (default: last snapshot)
#   snap.sh <repo> diff [file]   what changed since the last snapshot

set -uo pipefail

BASE="/c/WORK/_private_snapshots"
declare -A TREES=(
  [pyflightstream]="/c/WORK/ClaudeProjects/pyflightstream/_private"
  [itaca]="/c/WORK/ClaudeProjects/itaca/_private"
  # The shared incident ledger read by both push gates. Its location is
  # MACHINE CONFIGURATION, never a literal here: it lived under a personal
  # user profile and a private cloud tree, inside this hashed body, in a
  # file vendored into a public repository. Set COORD_SHARED_LEDGER_TREE to
  # point at it; unset, the shared tree is simply skipped.
  [shared]="${COORD_SHARED_LEDGER_TREE:-}"
)

g() { # g <repo> <git args...>
  local repo=$1; shift
  # Refuse an unconfigured tree HERE, so log, diff and restore are covered
  # too. Putting the check only in snapshot() left the body's skip promise
  # wider than the code that honoured it: the other three actions reached
  # git with an empty --work-tree and died on a git-level message about the
  # empty string, which tells the reader nothing about what to configure.
  if [ -z "${TREES[$repo]}" ]; then
    echo "$repo: no tree configured, skipped" >&2
    return 1
  fi
  git --git-dir="$BASE/${repo}_private.git" --work-tree="${TREES[$repo]}" "$@"
}

ensure() { # create the repo on first use
  local repo=$1
  # The WORK TREE is checked FIRST, before the already-exists shortcut.
  # Reversed, this was the 2026-07-28 defect: the shortcut returned 0 for any
  # repo whose git dir already existed, so an unset or missing tree never
  # reached this test, snapshot() proceeded, and `add -A` ran with an EMPTY
  # --work-tree. The body promised the tree was "simply skipped" and it was
  # not. An empty tree is a skip, not a snapshot of whatever the cwd happens
  # to be.
  [ -n "${TREES[$repo]}" ] && [ -d "${TREES[$repo]}" ] || return 1
  [ -d "$BASE/${repo}_private.git" ] && return 0
  git --git-dir="$BASE/${repo}_private.git" --work-tree="${TREES[$repo]}" init -q
  # Identity comes from the AMBIENT git configuration, never from this file.
  # It used to be two literals here, which put a full name and a personal
  # email address inside a hashed kit body that is vendored into a public
  # repository. A snapshot tool needs an author, not this author.
  local snap_name snap_email
  snap_name=$(git config --get user.name 2>/dev/null || true)
  snap_email=$(git config --get user.email 2>/dev/null || true)
  g "$repo" config user.name "${snap_name:-private-snapshot}"
  g "$repo" config user.email "${snap_email:-private-snapshot@localhost}"
  g "$repo" config core.autocrlf false   # restores must be byte exact
  g "$repo" config core.safecrlf false
  echo "created $BASE/${repo}_private.git"
}

snapshot() {
  local repo=$1
  ensure "$repo" || { echo "$repo: no _private tree, skipped"; return 0; }
  g "$repo" add -A
  if g "$repo" diff --cached --quiet; then
    echo "$repo: nothing changed"
  else
    local n
    n=$(g "$repo" diff --cached --name-only | wc -l | tr -d ' ')
    # The exit status is CHECKED. Swallowing it and echoing success anyway is
    # how a tool whose whole purpose is recovery reports a snapshot it did not
    # take, which is the failure mode that made this file necessary.
    if g "$repo" commit -q -m "snapshot: $n file(s)" 2>/dev/null; then
      echo "$repo: snapshot taken ($n file(s)) -> $(g "$repo" rev-parse --short HEAD)"
    else
      echo "$repo: SNAPSHOT FAILED, $n staged file(s) NOT committed" >&2
      return 1
    fi
  fi
}

repo=${1:-}
action=${2:-}

if [ -z "$repo" ]; then
  # The exit status carries the worst outcome. The loop used to discard every
  # snapshot() return and exit 0 unconditionally, so the no-argument run, which
  # is the documented normal usage, reported success after a failure it had
  # just printed. Same class as the defect this file was fixed for, one layer
  # out: the message told the truth and the status did not.
  rc=0
  for r in "${!TREES[@]}"; do snapshot "$r" || rc=1; done
  exit "$rc"
fi

[ -n "${TREES[$repo]+x}" ] || { echo "unknown repo: $repo (use: ${!TREES[*]})"; exit 2; }

case "$action" in
  ""|snapshot) snapshot "$repo" ;;
  log)         g "$repo" log --oneline -20 ;;
  diff)        shift 2; g "$repo" diff -- "${@:-.}" ;;
  restore)
    file=${3:-}; commit=${4:-HEAD}
    [ -n "$file" ] || { echo "usage: snap.sh $repo restore <file> [commit]"; exit 2; }
    g "$repo" checkout "$commit" -- "$file" && echo "restored $file from $commit"
    ;;
  *) echo "unknown action: $action"; exit 2 ;;
esac
