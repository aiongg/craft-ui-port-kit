# Shared steps of the landing tools. Source it after tools/portkit/lib.sh:
#   . "$(dirname "$(readlink -f "$0")")/../portkit/lib.sh"
#   . "$(dirname "$(readlink -f "$0")")/lib.sh"
# Needs git and git-filter-repo. Nothing here pushes.
LAND=$TOOLS/land

land_need_filter_repo() {
  git filter-repo --version >/dev/null 2>&1 || die "git-filter-repo is not installed (pip install git-filter-repo)"
}

# land_slug REF: REF as a file name.
land_slug() { printf '%s' "$1" | tr '/:' '__'; }

# land_clone SRC DEST REF: a fresh repository at DEST (never touching SRC) that holds only REF and its history, as
# branch `landing-src`. REF is a branch, tag or commit of SRC; a remote-tracking `origin/REF` wins over a local branch.
# Prints the commit REF names. DEST must be under work.landing.
land_clone() {
  local src=$1 dest=$2 ref=$3 root sha
  root=$(cfgr work.landing)
  case $dest in "$root"/*) ;; *) die "refusing to replace $dest: it is not under work.landing ($root)";; esac
  sha=$(git -C "$src" rev-parse -q --verify "refs/remotes/origin/$ref^{commit}" ||
        git -C "$src" rev-parse -q --verify "$ref^{commit}") || die "$ref is not a commit of $src"
  mkdir -p "$root"
  rm -rf "$dest"
  git init -q "$dest"
  git -C "$dest" fetch -q --no-tags "$src" "$sha" || die "fetching $ref from $src failed"
  git -C "$dest" update-ref refs/heads/landing-src "$sha"
  printf '%s\n' "$sha"
}

# land_skip_check ARGS...: sets LAND_ARGS to the arguments without `--skip-check REASON`, and LAND_SKIP to the reason
# (empty when the check is not skipped). An empty reason is refused.
land_skip_check() {
  LAND_ARGS=(); LAND_SKIP=
  while [ $# -gt 0 ]; do
    if [ "$1" = --skip-check ]; then
      [ -n "${2:-}" ] || die "--skip-check needs a reason: --skip-check \"why the check cannot run\""
      LAND_SKIP=$2; shift 2
    else
      LAND_ARGS+=("$1"); shift
    fi
  done
}

# land_check CLONE TASK: `cl check all` in the landed clone (tools/land/check-landed.py), before any push command
# prints. A failure, or a missing build.cl or framework.checkout, stops the tool (exit 1) unless LAND_SKIP holds a
# reason, which is printed and recorded on the dashboard as a landing event.
land_check() {
  local clone=$1 task=$2 rc=0
  if [ -n "$LAND_SKIP" ]; then
    echo "CHECK SKIPPED by --skip-check: $LAND_SKIP"
    "$TOOLS/track" event landing "cl check all skipped: $LAND_SKIP" --task "$task" >/dev/null 2>&1 || true
    return 0
  fi
  python3 -I "$LAND/check-landed.py" "$clone" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "Do not push: the landed clone does not build clean (exit $rc). Fix it in the port and land again, or pass --skip-check \"reason\" to go on without it." >&2
    exit 1
  fi
  echo "cl check all: passed"
}

# land_rules OUT [LOCAL_PATH...]: the rewrite rules, in the order filter-repo applies them: literal replacements of
# every local framework path (longest first) by land.sibling_framework, the generic rules, then your private rules
# (land.replace_message, optional). One file serves file contents and commit messages.
land_rules() {
  local out=$1 sibling p f rules private; shift
  sibling=$(cfg land.sibling_framework)
  rules=$(cfgr land.rewrite_rules)
  private=$(cfg land.replace_message)
  : > "$out"
  if [ -n "$sibling" ]; then
    {
      for k in framework.checkout framework.integration framework.snapshot; do cfg "$k"; done
      for p in "$@"; do printf '%s\n' "$p"; done
    } | awk 'NF && !seen[$0]++ { print length($0) "\t" $0 }' | sort -rn | cut -f2- |
      while IFS= read -r p; do printf '%s==>%s\n' "${p%/}" "${sibling%/}"; done >> "$out"
  fi
  grep -v '^[[:space:]]*#' "$rules" >> "$out"
  if [ -n "$private" ]; then
    [ -f "$private" ] || die "land.replace_message names a missing file: $private"
    grep -v '^[[:space:]]*#' "$private" >> "$out"
  fi
  # filter-repo rejects blank lines.
  sed -i '/^[[:space:]]*$/d' "$out"
}

# land_scan CLONE RANGE REPORT: run scan-range.py; the full report goes to REPORT, a summary to the terminal.
# Returns 0 when clean, 1 when there are hits (a missing private patterns file stops the tool).
land_scan() {
  local clone=$1 range=$2 report=$3 rc=0
  python3 -I "$LAND/scan-range.py" "$clone" "$range" > "$report" || rc=$?
  [ "$rc" -le 1 ] || { cat "$report" >&2; die "scan failed"; }
  sed -n '/^== summary/,$p' "$report" | awk -F'\t' '/^== idents/ { print; next } /^==/ { print; next } NF >= 2 && $2 > 0 { print } NF < 2 { print }'
  return "$rc"
}

# land_rewrite CLONE REFS RULES: rewrite only the commits REFS selects, applying RULES to contents and messages.
land_rewrite() {
  local clone=$1 refs=$2 rules=$3
  # Contents take every rule; messages take them too except in trailer lines (rewrite_message.py).
  git -C "$clone" filter-repo --force --refs "$refs" --replace-text "$rules" --message-callback \
    "import sys; sys.path.insert(0, '$LAND'); import rewrite_message; return rewrite_message.apply(message, '$rules')"
}
