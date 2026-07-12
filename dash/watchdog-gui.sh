#!/usr/bin/env bash
# Fleet watchdog TUI dashboard. Double-buffered no-flicker render. 4s refresh. CRLF-safe (no line continuations).
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
HB_DIR="$AESOP_ROOT/state/.heartbeats"

SPINNER=0
FIRST_FRAME=1

# Trap Ctrl-C to restore cursor and exit cleanly
trap 'printf "\033[?25h"; exit 0' INT TERM
printf '\033[?25l'

get_hb_threshold() {
  local name="$1"
  case "$name" in
    *monitor*) echo 3600;;
    *watchdog*) echo 300;;
    *) echo 300;;
  esac
}

render_frame() {
  local FRAME=""
  FRAME="${FRAME}${B}${C}== FLEET WATCHDOG${X}\n"
  FRAME="${FRAME}  ${SPIN_CHAR} $(date '+%a %H:%M:%S')  Daemon: $WD  ${R}HIGH:$HI${X} ${Y}MED:$ME${X}${X}\n"
  FRAME="${FRAME}\n"
  FRAME="${FRAME}${B}  REPOS BACKED UP${X}\n"
  if [ -f "$REPOS_FILE" ]; then
    repos_data=$(cat "$REPOS_FILE" 2>/dev/null)
    if [ "$repos_data" != "[]" ] 2>/dev/null; then
      REPOS_LINES=$(echo "$repos_data" | jq -r '.[] | "    \(.repo) \(.state) \(.age)"' 2>/dev/null)
      if [ -n "$REPOS_LINES" ]; then
        FRAME="${FRAME}${REPOS_LINES}\n"
      else
        FRAME="${FRAME}    ${D}(repos unavailable)${X}\n"
      fi
    else
      FRAME="${FRAME}    ${D}(no touched repos yet)${X}\n"
    fi
  else
    FRAME="${FRAME}    ${D}(no status)${X}\n"
  fi
  FRAME="${FRAME}\n"
  FRAME="${FRAME}${B}  HEARTBEATS${X}\n"
  HB_FOUND=0
  if [ -d "$HB_DIR" ] && [ -n "$(ls -A "$HB_DIR" 2>/dev/null)" ]; then
    for hb_file in "$HB_DIR"/*; do
      if [ -f "$hb_file" ]; then
        name=$(basename "$hb_file")
        epoch=$(head -1 "$hb_file" 2>/dev/null | grep -o '^[0-9]*')
        if [ -n "$epoch" ] && [ "$epoch" -gt 0 ]; then
          HB_FOUND=1
          age=$(( now - epoch ))
          threshold=$(get_hb_threshold "$name")
          if [ "$age" -lt "$threshold" ]; then
            status="${G}ALIVE${X} ${D}age:${age}s${X}"
          else
            status="${R}STALE${X} ${D}age:${age}s${X}"
          fi
          FRAME="${FRAME}    $name  $status\n"
        fi
      fi
    done
  fi
  if [ "$HB_FOUND" -eq 0 ]; then
    FRAME="${FRAME}    ${D}(none)${X}\n"
  fi
  FRAME="${FRAME}\n"
  FRAME="${FRAME}${B}  RECENT EVENTS${X}\n"
  if [ -s "$BLOG" ]; then
    BACKUP_LINES=$(tail -3 "$BLOG" 2>/dev/null | sed 's/^/    /')
    FRAME="${FRAME}${BACKUP_LINES}\n"
  else
    FRAME="${FRAME}    ${D}(none)${X}\n"
  fi
  FRAME="${FRAME}\n"
  FRAME="${FRAME}${D}  Ctrl-C to exit  ·  4s refresh${X}\n"
  echo -ne "$FRAME"
}

while true; do
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

  WD_THRESH=$(get_hb_threshold "watchdog")
  if [ "$AGE" -lt "$WD_THRESH" ]; then
    WD="${G}ALIVE${X} ${D}(${AGE}s)${X}"
  else
    WD="${R}STALE${X}"
  fi

  HI=$(grep -v '^RESOLVED-FP' "$SLOG" 2>/dev/null | grep -c ' HIGH '); HI=${HI:-0}
  ME=$(grep -v '^RESOLVED-FP' "$SLOG" 2>/dev/null | grep -c ' MED '); ME=${ME:-0}

  if [ "$FIRST_FRAME" -eq 1 ]; then
    printf '\033[2J'
    FIRST_FRAME=0
  else
    printf '\033[H'
  fi

  render_frame | while IFS= read -r line; do
    printf '%s\033[K\n' "$line"
  done
  printf '\033[J'

  sleep 4
done
