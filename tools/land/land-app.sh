#!/usr/bin/env bash
# Prepare the app branch for landing: clone, scan, scrub, pin the framework, print the push command.
#
# Usage: land-app.sh APP_TREE REF FRAMEWORK_REV [--skip-check REASON]
#   APP_TREE       your app integration tree (or any clone that holds REF)
#   REF            the port branch or commit to land
#   FRAMEWORK_REV  the framework commit that landed on framework.branch (land-framework.sh pushed it)
#   --skip-check   go on although `cl check all` cannot run or fails in the landed clone; REASON is printed and
#                  recorded on the dashboard. Without it a failing or impossible check stops the tool.
#
# Fetches only REF (and its history) from the tree into <work.landing>/app-<ref> (never touching it), fetches app.base_branch from app.upstream and takes
# the merge base with REF. It scans base..REF (tools/land/scan-range.py) and, when there are hits, rewrites only that
# range with git filter-repo (local framework paths become land.sibling_framework) and scans again. A last commit pins
# every framework dependency to FRAMEWORK_REV by git rev (tools/land/pin-framework.py) and drops the local patch
# blocks. Cargo.lock is not regenerated: do that against the pinned revision (process/10-land.md). Last it runs
# `cl check all` in the landed clone (tools/land/check-landed.py). It prints the push
# command for land.push_target and land.push_branch and never pushes.
# Config: build.cl, framework.checkout, app.upstream, app.base_branch, land.push_target, land.push_branch, land.sibling_framework, framework.repo,
# framework.branch, framework.patch_urls, work.landing, land.rewrite_rules, land.private_patterns,
# land.replace_message, land.known_idents.
set -euo pipefail
. "$(dirname "$(readlink -f "$0")")/../portkit/lib.sh"
. "$(dirname "$(readlink -f "$0")")/lib.sh"
track_self land-app "$0" "$@"

land_skip_check "$@"
set -- "${LAND_ARGS[@]}"
[ $# -eq 3 ] || die "usage: land-app.sh APP_TREE REF FRAMEWORK_REV [--skip-check REASON]"
[ -d "$1" ] || die "not a directory: $1"
SRC=$(readlink -f "$1"); REF=$2; FWREV=$3
UPSTREAM=$(cfgr app.upstream); BASE_BRANCH=$(cfgr app.base_branch)
TARGET=$(cfgr land.push_target); PUSH_BRANCH=$(cfgr land.push_branch)
FW_URL=$(cfgr framework.repo); FW_BRANCH=$(cfgr framework.branch)
land_need_filter_repo
W=$(cfgr work.landing)/app-$(land_slug "$REF"); REPORT=$W.scan.txt
OLD=$(land_clone "$SRC" "$W" "$REF")
cd "$W"
git remote add landing-upstream "$UPSTREAM"
git fetch -q landing-upstream "$BASE_BRANCH:refs/remotes/landing-upstream/$BASE_BRANCH"
BASE=$(git merge-base "$OLD" "landing-upstream/$BASE_BRANCH")
git checkout -q -B land "$OLD"
echo "ref $REF = $OLD ; base (merge base with $BASE_BRANCH) = $BASE ; commits: $(git rev-list --count "$BASE..land")"
STILL=0
if land_scan "$W" "$BASE..land" "$REPORT"; then
  echo "no hits: history unchanged"
else
  echo "== hits (full report: $REPORT): rewriting $BASE..land only =="
  RULES=$W.rules.txt
  land_rules "$RULES" "$SRC"
  land_rewrite "$W" "$BASE..land" "$RULES"
  echo "old head $OLD -> scrubbed head $(git rev-parse land)"
fi
git merge-base --is-ancestor "$BASE" land || die "the base $BASE is no longer in the history after the rewrite"
git reset -q --hard land
python3 -I "$LAND/pin-framework.py" "$W" "$FWREV" > "$W.changed.txt"
git add -A -- '*Cargo.toml'
if git diff --cached --quiet; then
  echo "no Cargo.toml names the framework: nothing to pin (check framework.repo and framework.patch_urls)"
else
  git -c user.name="$(git log -1 --format=%an land)" -c user.email="$(git log -1 --format=%ae land)" commit -q -m \
    "Resolve the craft framework from $FW_URL $FW_BRANCH at $FWREV

Every framework path dependency and patch is now a git dependency at that revision.
Cargo.lock is regenerated against it separately."
fi
echo "re-scan of $BASE..land, pin commit included:"
land_scan "$W" "$BASE..land" "$REPORT.2" || { echo "HITS REMAIN (report: $REPORT.2): fix them in the port, then land again"; STILL=1; }
echo "FINAL HEAD $(git rev-parse land)"
echo "Cargo.toml files changed:"; cat "$W.changed.txt"
echo "remaining framework path references in Cargo.toml files: $(git grep -nE 'path *= *"[^"]*'"$(basename "${FW_URL%.git}")"'|/hom[e]/|/User[s]/' land -- '*Cargo.toml' | wc -l)"
echo "clone: $W"
if [ "$STILL" = 1 ]; then echo "Do not push: the scan still reports hits."; exit 1; fi
land_check "$W" land-app
echo "Regenerate Cargo.lock in the clone, then push yourself:"
echo "  git -C $W push $TARGET land:$PUSH_BRANCH"
