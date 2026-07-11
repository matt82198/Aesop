#!/usr/bin/env bash
# Fleet watchdog TUI dashboard. Realtime ~1s refresh. CRLF-safe (no line continuations).
# Launch in its own window: bash aesop/dash/watchdog-gui.sh
# Set AESOP_ROOT=/path/to/aesop and TRACKED_REPOS before running.

AESOP_ROOT="${AESOP_ROOT:-.}"

# Color codes (ANSI)
R=$'\e[31m'
G=$'\e[32m'
Y=$'\e[33m'
M=$'\e[35m'
C=$'\e[36m'
B=$'\e[1m'
D=$'\e[2m'
X=$'\e[0m'

# State files
BLOG="$AESOP_ROOT/state/FLEET-BACKUP.log"
SLOG="$AESOP_ROOT/state/SECURITY-ALERTS.log"
HB="$AESOP_ROOT/state/.watchdog-heartbeat"
REPOS_FILE="$AESOP_ROOT/state/.watchdog-repos.json"

SPINNER=0

# Trap Ctrl-C to restore cursor and exit cleanly
trap 'printf "\e[?25h"; clear; exit 0' INT TERM
printf '\e[?25l'

while true; do
  TICK_TIME=$(date '+%Y-%m-%d %H:%M:%S')
  SPINNER_CHARS='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  SPINNER_IDX=$(( SPINNER % 10 ))
  SPIN_CHAR="${SPINNER_CHARS:$SPINNER_IDX:1}"
  ((SPINNER++))

  now=$(date +%s)
  hb=$(cat "$HB" 2>/dev/null)
  case "$hb" in
    ''|*[!0-9]*) hb=0 ;;
  esac

  if [ "$hb" -gt 0 ]; then
    AGE=$(( now - hb ))
  else
    AGE=99999
  fi

  if [ "$AGE" -lt 200 ]; then
    WD="${G}* ALIVE${X} ${D}(${AGE}s ago)${X}"
  else
    WD="${R}* STALE/DOWN${X}"
  fi

  # Count security alerts (example: scan SECURITY-ALERTS.log)
  HI=$(grep -v '^RESOLVED-FP' "$SLOG" 2>/dev/null | grep -c ' HIGH ')
  HI=${HI:-0}
  ME=$(grep -v '^RESOLVED-FP' "$SLOG" 2>/dev/null | grep -c ' MED ')
  ME=${ME:-0}

  clear
  echo "${B}${C}==================================================================${X}"
  echo "${B}  FLEET WATCHDOG   ·   Aesop Orchestration Harness${X}"
  echo "${B}${C}==================================================================${X}"
  printf "  ${SPIN_CHAR} %s  Last refresh: %s  (realtime 1s)\n\n" "$(date '+%a %H:%M:%S')" "$TICK_TIME"

  echo "${B}  WATCHDOG STATUS${X}"
  printf "    %s\n\n" "$WD"

  echo "${B}  FLEET REPOS${X}"
  if [ -f "$REPOS_FILE" ]; then
    repos_data=$(cat "$REPOS_FILE" 2>/dev/null)
    if [ "$repos_data" != "[]" ] 2>/dev/null; then
      echo "$repos_data" | jq -r '.[] | "    \(.repo) \(.state) \(.age)"' 2>/dev/null || echo "    ${D}(failed to parse repos)${X}"
    else
      echo "    ${D}(no touched repos yet)${X}"
    fi
  else
    echo "    ${D}(no status file yet)${X}"
  fi
  echo

  echo "${B}  RECENT BACKUP EVENTS${X}"
  if [ -s "$BLOG" ]; then
    tail -3 "$BLOG" 2>/dev/null | sed 's/^/    /'
  else
    echo "    ${D}(none yet)${X}"
  fi
  echo

  printf "${B}  SECURITY / ALERTS${X}   ${R}HIGH:%s${X}  ${Y}MED:%s${X}\n" "$HI" "$ME"
  if [ -s "$SLOG" ]; then
    grep -v '^RESOLVED-FP' "$SLOG" 2>/dev/null | tail -5 | awk -v R="$R" -v Y="$Y" -v D="$D" -v X="$X" '{c=X; if($0 ~ /SUPPRESSED-FP/) c=D; else if($0 ~ / HIGH /) c=R; else if($0 ~ / MED /) c=Y; print "    " c $0 X}'
  else
    echo "    ${G}no alerts yet${X}"
  fi
  echo

  echo "${D}  REALTIME 1s refresh  ·  Ctrl-C to exit${X}"
  sleep 1
done
