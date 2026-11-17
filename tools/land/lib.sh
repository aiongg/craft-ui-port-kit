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

# land_clone SRC DEST: a fresh clone of SRC (never touching SRC) without a checkout. DEST must be under work.landing.
land_clone() {
  local src=$1 dest=$2 root
  root=$(cfgr work.landing)
  case $dest in "$root"/*) ;; *) die "refusing to replace $dest: it is not under work.landing ($root)";; esac
  mkdir -p "$root"
  rm -rf "$dest"
  git clone -q --no-local --no-checkout "$src" "$dest"
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
  git -C "$clone" filter-repo --force --refs "$refs" --replace-text "$rules" --replace-message "$rules"
}
