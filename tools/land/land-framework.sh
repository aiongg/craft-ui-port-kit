#!/usr/bin/env bash
# Prepare the framework changes for landing: clone, check the fast-forward, scan, scrub, print the push commands.
#
# Usage: land-framework.sh FRAMEWORK_TREE REF [--skip-check REASON]
#   FRAMEWORK_TREE  your framework integration tree (or any clone that holds REF)
#   REF             the branch or commit to land (a remote-tracking `origin/REF` of the clone wins over a local branch)
#   --skip-check    go on although `cl check all` cannot run or fails in the landed clone; REASON is printed and
#                   recorded on the dashboard. Without it a failing or impossible check stops the tool.
#
# From phase 8 on, once REF is fetched, it runs the look gate (tools/land/look-gate.py framework REF's commit): the
# phase 8 look rows pass with every pair captured from that commit, or `track phase 9 --force` recorded them as a
# decision. Before phase 8 (an early framework landing) it notes that the gate does not apply yet.
# Fetches only REF (and its history) from the tree into <work.landing>/fw-<ref> (never touching it), fetches framework.branch from framework.repo, and
# checks that REF is a fast-forward of it; if not, it stops and lists the upstream commits REF lacks (merge them
# first). It scans framework.branch..REF (tools/land/scan-range.py) and, when there are hits, rewrites only that
# range with git filter-repo and scans again, then runs `cl check all` in the landed clone (tools/land/check-landed.py).
# It prints the push commands for land.framework_via and never pushes.
# Config: build.cl, framework.checkout, framework.repo, framework.branch, land.framework_via, work.landing, land.rewrite_rules,
# land.private_patterns, land.replace_message, land.sibling_framework, land.known_idents.
# DRY_MERGE=1 continues past a failed fast-forward check, for a preview only (never land that head).
set -euo pipefail
. "$(dirname "$(readlink -f "$0")")/../portkit/lib.sh"
. "$(dirname "$(readlink -f "$0")")/lib.sh"
track_self land-framework "$0" "$@"

land_skip_check "$@"
set -- "${LAND_ARGS[@]}"
[ $# -eq 2 ] || die "usage: land-framework.sh FRAMEWORK_TREE REF [--skip-check REASON]"
[ -d "$1" ] || die "not a directory: $1"
SRC=$(readlink -f "$1"); REF=$2
URL=$(cfgr framework.repo); BRANCH=$(cfgr framework.branch); VIA=$(cfg land.framework_via)
land_need_filter_repo
W=$(cfgr work.landing)/fw-$(land_slug "$REF"); REPORT=$W.scan.txt
OLD=$(land_clone "$SRC" "$W" "$REF")
land_look_gate framework "$OLD"
cd "$W"
git remote add landing-upstream "$URL"
git fetch -q landing-upstream "$BRANCH:refs/remotes/landing-upstream/$BRANCH"
NEXT=$(git rev-parse "landing-upstream/$BRANCH")
echo "ref $REF = $OLD ; $BRANCH on $URL = $NEXT"
if ! git merge-base --is-ancestor "$NEXT" "$OLD"; then
  echo "NOT a fast-forward: $REF lacks these $BRANCH commits (merge $BRANCH into the port first):"
  git log --oneline "$OLD..$NEXT"
  [ "${DRY_MERGE:-0}" = 1 ] || exit 1
  echo "DRY_MERGE=1: continuing the preview on $BRANCH..$REF without the merge (never land this)"
fi
git checkout -q -B land "$OLD"
echo "commits to land: $(git rev-list --count "$NEXT..land")"
if land_scan "$W" "$NEXT..land" "$REPORT"; then
  NEW=$OLD; echo "no hits: head unchanged $OLD"
else
  echo "== hits (full report: $REPORT): rewriting $NEXT..land only =="
  RULES=$W.rules.txt
  land_rules "$RULES" "$SRC"
  land_rewrite "$W" "$NEXT..land" "$RULES"
  NEW=$(git rev-parse land)
  echo "old head $OLD -> new head $NEW"
  echo "re-scan:"
  land_scan "$W" "$NEXT..land" "$REPORT.2" || { echo "HITS REMAIN (report: $REPORT.2): fix them in the port, then land again"; STILL=1; }
fi
git merge-base --is-ancestor "$NEXT" land && echo "fast-forward from $BRANCH: yes"
git reset -q --hard land
echo "FINAL HEAD $(git rev-parse land)"
echo "commits ahead of $BRANCH: $(git rev-list --count "$NEXT..land")"
echo "clone: $W"
if [ "${STILL:-0}" = 1 ]; then echo "Do not push: the scan still reports hits."; exit 1; fi
land_check "$W" land-framework
echo "Review the scan report, then push from the clone yourself:"
case $VIA in
  fast-forward) echo "  git -C $W push $URL land:$BRANCH" ;;
  *) echo "  git -C $W push $URL land:port/$(land_slug "$REF")   # then open one PR into $BRANCH from that branch" ;;
esac
