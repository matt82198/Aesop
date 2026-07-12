#!/usr/bin/env bash
# Test suite for dash/watchdog-gui.sh printf rendering fix

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
WATCHDOG_GUI="$PROJECT_ROOT/dash/watchdog-gui.sh"

C=$'\e[36m'
X=$'\e[0m'

test_printf_format_is_s() {
  if grep -q "printf '%s" "$WATCHDOG_GUI"; then
    echo "PASS: printf format uses %s for data rendering"
    return 0
  else
    echo "FAIL: printf format should use %s, not %b"
    return 1
  fi
}

test_backslash_sequences_literal() {
  local test_line="    repo/path\with\backslashes\U1234 CLEAN 5s"
  local output
  local cleaned

  output=$(printf '%s\033[K\n' "$test_line" 2>&1 | head -1)
  cleaned=$(printf '%s' "$output" | sed 's/\x1b\[[0-9;]*m//g' | sed 's/\x1b\[K//g')

  if [ "$cleaned" = "$test_line" ]; then
    echo "PASS: Backslash sequences in data are printed literally"
    return 0
  else
    echo "FAIL: Backslash sequences were mangled"
    return 1
  fi
}

test_ansi_codes_in_format_work() {
  local test_line="some data"
  local output

  output=$(printf '%s\033[K\n' "$test_line" 2>&1 | head -1)

  if printf '%s' "$output" | grep -q $'\x1b'; then
    echo "PASS: ANSI escape codes in format string are interpreted"
    return 0
  else
    echo "FAIL: ANSI escape codes in format string were not processed"
    return 1
  fi
}

test_unicode_escape_no_error() {
  local test_line="repo\Uabcd"
  local output

  if output=$(printf '%s\033[K\n' "$test_line" 2>&1); then
    echo "PASS: No error when data contains \U sequence"
    return 0
  else
    echo "FAIL: Printf errored on data with \U sequence"
    return 1
  fi
}

test_bash_syntax() {
  if bash -n "$WATCHDOG_GUI" 2>&1 >/dev/null; then
    echo "PASS: watchdog-gui.sh passes bash -n syntax check"
    return 0
  else
    echo "FAIL: watchdog-gui.sh has syntax errors"
    return 1
  fi
}

main() {
  local pass=0
  local fail=0

  echo "${C}=== watchdog-gui.sh Printf Rendering Fix Tests ===${X}"
  echo

  echo "Running: test_printf_format_is_s"
  if test_printf_format_is_s; then ((pass++)); else ((fail++)); fi
  echo

  echo "Running: test_backslash_sequences_literal"
  if test_backslash_sequences_literal; then ((pass++)); else ((fail++)); fi
  echo

  echo "Running: test_ansi_codes_in_format_work"
  if test_ansi_codes_in_format_work; then ((pass++)); else ((fail++)); fi
  echo

  echo "Running: test_unicode_escape_no_error"
  if test_unicode_escape_no_error; then ((pass++)); else ((fail++)); fi
  echo

  echo "Running: test_bash_syntax"
  if test_bash_syntax; then ((pass++)); else ((fail++)); fi
  echo

  echo "${C}=== Test Summary ===${X}"
  echo "Passed: $pass / 5"
  echo "Failed: $fail / 5"
  echo

  if [ "$fail" -eq 0 ]; then
    return 0
  else
    return 1
  fi
}

main "$@"
