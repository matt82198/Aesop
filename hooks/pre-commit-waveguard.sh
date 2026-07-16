#!/usr/bin/env bash
set -uo pipefail

main() {
  local aesop_root="${AESOP_ROOT:-$HOME/aesop}"
  local marker_file="$aesop_root/state/.wave-in-flight"

  if [ -f "$marker_file" ]; then
    printf 'Error: Wave in flight. Commit from a sibling worktree, or clear %s to override.\n' "$marker_file" >&2
    exit 1
  fi

  exit 0
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  main "$@"
fi
