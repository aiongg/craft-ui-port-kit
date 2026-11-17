# Shell helpers for the kit's bash tools. Source it first thing:
#   . "$(dirname "$(readlink -f "$0")")/portkit/lib.sh"
# It sets KIT (the kit root) and TOOLS, answers -h/--help with the tool's header comment, and defines:
#   cfg KEY        print a config value (empty when unset)
#   cfgr KEY       print a config value, or stop the tool naming the unset key
#   cfgl KEY       print a list value as one item per line
#   track_self NAME "$0" "$@"   re-run the calling tool under `track run NAME`, once, so the dashboard gets one
#                  event when it ends; does nothing when tools/track is missing
#   with_cap GB CMD...            run CMD under build.memory_cap (no cap when the key is empty)
#   die MSG        print MSG to stderr and exit 2
KIT=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)
TOOLS=$KIT/tools
_name=$(basename "$0")

# -h or --help as a tool's first argument prints the tool's header comment and exits, before any config is read.
case "${1:-}" in
  -h|--help) sed -n '2,/^[^#]/{/^#/s/^# \{0,1\}//p}' "$0"; exit 0 ;;
esac

die() { echo "$_name: $*" >&2; exit 2; }

cfg() { python3 -I "$TOOLS/portkit/config.py" get "$1"; }
cfgr() {
  local v
  v=$(cfg "$1") || exit 2
  [ -n "$v" ] || die "config key $1 is not set (see process/config.md)"
  printf '%s' "$v"
}
cfgl() { cfg "$1"; }

track_self() {
  local name=$1 guard; shift
  guard=PORTKIT_TRACKED_${name//[^A-Za-z0-9]/_}
  [ -z "${!guard:-}" ] && [ -x "$TOOLS/track" ] || return 0
  export "$guard=1"
  exec "$TOOLS/track" run "$name" -- "$@"
}

with_cap() {
  local gb=$1 prefix; shift
  prefix=$(cfg build.memory_cap)
  if [ -n "$prefix" ]; then
    # shellcheck disable=SC2086
    exec_prefix=${prefix//\{gb\}/$gb}
    # shellcheck disable=SC2086
    $exec_prefix "$@"
  else
    "$@"
  fi
}
