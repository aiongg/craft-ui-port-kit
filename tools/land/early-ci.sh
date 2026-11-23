#!/usr/bin/env bash
# Early CI on the developer's fork: a scrubbed copy of the port's framework branch and one draft PR there, so the
# CI legs a local build does not run (wasm, macOS, Windows) report on a small diff long before landing.
#
# Usage: early-ci.sh fw FRAMEWORK_TREE REF LABEL
#   fw              the repo: the framework (the only repo early CI covers)
#   FRAMEWORK_TREE  your framework integration tree (or any clone that holds REF)
#   REF             the branch or commit to run CI on: the integration head after a green cycle
#   LABEL           a name for the run (`pilot`, `batch-1`, ...): the fork branch is port-ci/LABEL
#
# Run it after the pilot's framework sets go green and after each green framework batch (process/10-land.md,
# "Early CI on the fork"). It fetches only REF into <work.landing>/ci-LABEL (never touching the tree), fetches
# framework.branch from framework.repo, scans the range from their merge base to REF (tools/land/scan-range.py) and,
# when there are hits, rewrites only that range with git filter-repo and scans again. Hits left stop it with exit 1
# before anything is pushed. Then it has three commands, each naming only land.early_ci_fork:
#   1. push upstream's framework.branch head to the fork's framework.branch, without force: the draft PR's base stays
#      current, so its diff is the port's alone. A fork branch that has diverged refuses the push and stops the tool.
#   2. push the scrubbed head to the fork's port-ci/LABEL, with force (the scrub gives new commit ids on every run;
#      the kit owns the port-ci/ branches).
#   3. `gh pr create --draft --repo <fork> --base framework.branch --head port-ci/LABEL`, unless `gh pr list` finds
#      that branch's open PR (the push updated it).
# With land.early_ci_approved = false it prints the three commands and exits 0; the developer may run them. With
# true it runs them. Nothing else is pushed, no PR is opened outside the fork, and every PR is a draft. It refuses
# a fork URL equal to framework.repo, app.upstream or land.push_target. The look gate and `cl check all` do not run:
# the CI legs are the check. Each run appends a row to <work.landing>/early-ci.tsv (time, label, ref, scrubbed head,
# fork, pushed | printed), which cycle reads.
# Config: framework.repo, framework.branch, land.early_ci_fork, land.early_ci_approved, app.upstream,
# land.push_target, work.landing, land.rewrite_rules, land.private_patterns, land.replace_message,
# land.sibling_framework, land.known_idents. `gh` is PORT_KIT_GH_BIN when set.
set -euo pipefail
. "$(dirname "$(readlink -f "$0")")/../portkit/lib.sh"
. "$(dirname "$(readlink -f "$0")")/lib.sh"
track_self early-ci "$0" "$@"

[ $# -eq 4 ] || die "usage: early-ci.sh fw FRAMEWORK_TREE REF LABEL"
[ "$1" = fw ] || die "the repo is fw: early CI covers the framework"
[ -d "$2" ] || die "not a directory: $2"
SRC=$(readlink -f "$2"); REF=$3; LABEL=$4
case $LABEL in *[!A-Za-z0-9._-]*|'') die "LABEL takes letters, digits, '.', '_' and '-': $LABEL" ;; esac
URL=$(cfgr framework.repo); BRANCH=$(cfgr framework.branch)
FORK=$(land_fork_url)
APPROVED=$(cfg land.early_ci_approved)
GH=${PORT_KIT_GH_BIN:-gh}
SLUG=$(land_slug_of "$FORK")
land_need_filter_repo
W=$(cfgr work.landing)/ci-$LABEL; REPORT=$W.scan.txt
OLD=$(land_clone "$SRC" "$W" "$REF")
cd "$W"
git remote add landing-upstream "$URL"
git fetch -q landing-upstream "$BRANCH:refs/remotes/landing-upstream/$BRANCH"
NEXT=$(git rev-parse "landing-upstream/$BRANCH")
BASE=$(git merge-base "$OLD" "$NEXT") || die "$REF and $BRANCH share no history"
git checkout -q -B land "$OLD"
echo "ref $REF = $OLD ; $BRANCH upstream = $NEXT ; merge base $BASE ; commits: $(git rev-list --count "$BASE..land")"
if land_scan "$W" "$BASE..land" "$REPORT"; then
  echo "no hits: head unchanged $OLD"
else
  echo "== hits (full report: $REPORT): rewriting $BASE..land only =="
  RULES=$W.rules.txt
  land_rules "$RULES" "$SRC"
  land_rewrite "$W" "$BASE..land" "$RULES"
  echo "re-scan:"
  land_scan "$W" "$BASE..land" "$REPORT.2" || { echo "Do not push: HITS REMAIN (report: $REPORT.2). Fix them in the port, then run again."; exit 1; }
fi
git reset -q --hard land
NEW=$(git rev-parse land)
HEAD_BRANCH=port-ci/$LABEL
TITLE="Early CI: $LABEL"
BODY="Draft for early CI of the port's framework changes ($LABEL). Not for review or merge."
echo "scrubbed head $NEW ; clone: $W"

record() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$LABEL" "$OLD" "$NEW" "$FORK" "$1" \
    >> "$(cfgr work.landing)/early-ci.tsv"
}

if [ "$APPROVED" != True ]; then
  echo "land.early_ci_approved is false: nothing pushed. The commands, for the developer:"
  echo "  git -C $W push $FORK $NEXT:refs/heads/$BRANCH"
  echo "  git -C $W push --force $FORK land:refs/heads/$HEAD_BRANCH"
  echo "  $GH pr list --repo $SLUG --head $HEAD_BRANCH --state open --json number --jq length   # 0: open the draft"
  echo "  $GH pr create --draft --repo $SLUG --base $BRANCH --head $HEAD_BRANCH --title \"$TITLE\" --body \"$BODY\""
  record printed
  exit 0
fi

command -v "$GH" >/dev/null 2>&1 || die "gh is not installed (or PORT_KIT_GH_BIN names no command)"
git push -q "$FORK" "$NEXT:refs/heads/$BRANCH" ||
  { echo "Stopped: the fork's $BRANCH has diverged from upstream's (a push without force was refused). Bring it back to upstream's $BRANCH, then run again." >&2; exit 1; }
git push -q --force "$FORK" "land:refs/heads/$HEAD_BRANCH"
echo "pushed $NEW to $HEAD_BRANCH and $NEXT to $BRANCH on the fork"
OPEN=$("$GH" pr list --repo "$SLUG" --head "$HEAD_BRANCH" --state open --json number --jq length)
if [ "${OPEN:-0}" = 0 ]; then
  "$GH" pr create --draft --repo "$SLUG" --base "$BRANCH" --head "$HEAD_BRANCH" --title "$TITLE" --body "$BODY"
else
  echo "draft PR for $HEAD_BRANCH is open: the push updated it"
fi
record pushed
"$TOOLS/track" event landing "early CI $LABEL: $NEW on the fork's $HEAD_BRANCH" --task early-ci >/dev/null 2>&1 || true
