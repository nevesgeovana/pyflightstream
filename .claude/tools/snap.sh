# ITACA / pyflightstream shared process kit
# kit-version: 0.1.0
# artifact: snap.sh
# body-sha256: 0da13e4da525c1c470dc4429ef6c557a3b74600ad817c534344e999180786383
# canonical-source: local-only _private snapshot tool, shared across all three workspaces plus the shared incident ledger.
# note: this file is the CANONICAL kit master. Repositories vendor a derived copy carrying this same header; a tier-1 drift test in each repo recomputes the body sha256 and asserts it equals the declared value for the kit-version above. Do not hand-edit a vendored copy; promotion is a reviewed seat step at the coordination level.
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
  # The shared incident ledger read by both push gates. It lives in
  # OneDrive so the author can add entries from her phone, and is
  # versioned here for the same reason the _private trees are.
  [shared]="/c/Users/geova/OneDrive/Education/ResearchHub/shared_incidents"
)

g() { # g <repo> <git args...>
  local repo=$1; shift
  git --git-dir="$BASE/${repo}_private.git" --work-tree="${TREES[$repo]}" "$@"
}

ensure() { # create the repo on first use
  local repo=$1
  [ -d "$BASE/${repo}_private.git" ] && return 0
  [ -d "${TREES[$repo]}" ] || return 1
  git --git-dir="$BASE/${repo}_private.git" --work-tree="${TREES[$repo]}" init -q
  g "$repo" config user.name "Geovana Neves"
  g "$repo" config user.email "geovanan90@gmail.com"
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
    g "$repo" commit -q -m "snapshot: $n file(s)" 2>/dev/null
    echo "$repo: snapshot taken ($n file(s)) -> $(g "$repo" rev-parse --short HEAD)"
  fi
}

repo=${1:-}
action=${2:-}

if [ -z "$repo" ]; then
  for r in "${!TREES[@]}"; do snapshot "$r"; done
  exit 0
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
