#!/usr/bin/env bash
# =============================================================================
# Navaia AI Workforce — Server Health Check
# Agent: Arch (Technical)
# Usage: bash health-check.sh [--json] [--quiet]
# =============================================================================

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
NAVAIA_ROOT="${NAVAIA_ROOT:-$HOME/Desktop/NAVAIA/agentic_teams}"
DASHBOARD_PORT=7777
EMBEDDING_PORT=8000
WEAVIATE_TEST_PORT=8080
WEAVIATE_PROD_PORT=8095
ENDPOINT_TIMEOUT=5  # seconds per curl check

# Thresholds
CPU_WARN=70
CPU_CRIT=90
MEM_WARN=80
MEM_CRIT=95
DISK_WARN=80
DISK_CRIT=90
RESPONSE_WARN_MS=1000
RESPONSE_CRIT_MS=3000

# Colors (disabled in quiet/json mode)
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# Flags
JSON_MODE=false
QUIET_MODE=false

for arg in "$@"; do
  case "$arg" in
    --json)  JSON_MODE=true ;;
    --quiet) QUIET_MODE=true ;;
  esac
done

if $JSON_MODE || $QUIET_MODE; then
  RED=''; YELLOW=''; GREEN=''; BLUE=''; CYAN=''; BOLD=''; RESET=''
fi

# ── Helpers ───────────────────────────────────────────────────────────────────
is_macos() { [[ "$(uname)" == "Darwin" ]]; }

status_icon() {
  local level="$1"
  case "$level" in
    ok)   echo "✅" ;;
    warn) echo "⚠️ " ;;
    crit) echo "🔴" ;;
    info) echo "ℹ️ " ;;
  esac
}

color_level() {
  local level="$1" text="$2"
  case "$level" in
    ok)   echo -e "${GREEN}${text}${RESET}" ;;
    warn) echo -e "${YELLOW}${text}${RESET}" ;;
    crit) echo -e "${RED}${text}${RESET}" ;;
    *)    echo "$text" ;;
  esac
}

threshold_level() {
  local val="$1" warn="$2" crit="$3"
  if   (( val >= crit )); then echo "crit"
  elif (( val >= warn )); then echo "warn"
  else echo "ok"
  fi
}

section() {
  $QUIET_MODE && return
  echo ""
  echo -e "${BOLD}${BLUE}══════════════════════════════════════════${RESET}"
  echo -e "${BOLD}${BLUE}  $1${RESET}"
  echo -e "${BOLD}${BLUE}══════════════════════════════════════════${RESET}"
}

row() {
  printf "  %-28s %s\n" "$1" "$2"
}

# ── Collectors ────────────────────────────────────────────────────────────────

# CPU: returns integer percentage (user+sys on macOS, 0-100)
get_cpu_usage() {
  if is_macos; then
    # top in batch mode, grab "CPU usage" line
    top -l 1 -n 0 -stats cpu 2>/dev/null \
      | awk '/^CPU usage/ {
          gsub(/%/, "");
          user = $3; sys = $5;
          printf "%d\n", user + sys
        }'
  else
    # Linux: read /proc/stat snapshot
    local cpu_line1 cpu_line2
    cpu_line1=$(grep '^cpu ' /proc/stat)
    sleep 0.5
    cpu_line2=$(grep '^cpu ' /proc/stat)
    awk -v l1="$cpu_line1" -v l2="$cpu_line2" 'BEGIN {
      n=split(l1, a); split(l2, b);
      idle1=a[5]; total1=0; for(i=2;i<=n;i++) total1+=a[i];
      idle2=b[5]; total2=0; for(i=2;i<=n;i++) total2+=b[i];
      printf "%d\n", (1 - (idle2-idle1)/(total2-total1)) * 100
    }'
  fi
}

# Memory: returns integer percentage used
get_mem_usage() {
  if is_macos; then
    local total_pages wired active compressed
    total_pages=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
    total_pages=$(( total_pages / 4096 ))
    # vm_stat output: "Pages wired down: N"
    wired=$(vm_stat | awk '/Pages wired down/ {gsub(/\./,"",$4); print $4}')
    active=$(vm_stat | awk '/Pages active/ {gsub(/\./,"",$3); print $3}')
    compressed=$(vm_stat | awk '/Pages occupied by compressor/ {gsub(/\./,"",$5); print $5}')
    local used_pages=$(( ${wired:-0} + ${active:-0} + ${compressed:-0} ))
    [[ "$total_pages" -gt 0 ]] && echo $(( used_pages * 100 / total_pages )) || echo 0
  else
    free | awk '/^Mem:/ { printf "%d\n", ($3/$2)*100 }'
  fi
}

# Disk: returns integer percentage for a given mountpoint (default /)
get_disk_usage() {
  local mount="${1:-/}"
  df -h "$mount" 2>/dev/null | tail -1 | awk '{gsub(/%/, "", $5); print $5}'
}

# Uptime: human-readable string
get_uptime() {
  if is_macos; then
    uptime | sed 's/^.*up //' | sed 's/,.*//'
  else
    uptime -p 2>/dev/null || uptime | sed 's/^.*up //' | sed 's/,.*//'
  fi
}

# Check if a process matching a pattern is running; returns pid or ""
find_process() {
  local pattern="$1"
  pgrep -f "$pattern" 2>/dev/null | head -1 || true
}

# HTTP endpoint: returns response time in ms, or "TIMEOUT"/"ERROR"
check_endpoint() {
  local url="$1"
  local result
  result=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" \
    --max-time "$ENDPOINT_TIMEOUT" "$url" 2>/dev/null || echo "000 0")
  local code time_sec
  code=$(awk '{print $1}' <<<"$result")
  time_sec=$(awk '{print $2}' <<<"$result")
  local ms
  ms=$(awk -v t="$time_sec" 'BEGIN { printf "%d", t * 1000 }')
  echo "$code $ms"
}

# Docker: list container name/status pairs
get_docker_containers() {
  docker ps -a --format "{{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo ""
}

# ── Report sections ───────────────────────────────────────────────────────────

report_header() {
  $QUIET_MODE && return
  echo ""
  echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════╗${RESET}"
  echo -e "${BOLD}${CYAN}║     NAVAIA SERVER HEALTH CHECK           ║${RESET}"
  echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════╝${RESET}"
  echo "  Generated: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo "  Host:      $(hostname)"
  echo "  OS:        $(uname -srm)"
}

report_system() {
  section "1. SYSTEM"

  # Uptime
  local uptime_str
  uptime_str=$(get_uptime)
  row "Uptime:" "$uptime_str"

  # CPU
  local cpu_pct
  cpu_pct=$(get_cpu_usage)
  local cpu_level
  cpu_level=$(threshold_level "$cpu_pct" "$CPU_WARN" "$CPU_CRIT")
  row "CPU Usage:" "$(status_icon "$cpu_level") $(color_level "$cpu_level" "${cpu_pct}%")"

  # Memory
  local mem_pct
  mem_pct=$(get_mem_usage)
  local mem_level
  mem_level=$(threshold_level "$mem_pct" "$MEM_WARN" "$MEM_CRIT")
  row "Memory Used:" "$(status_icon "$mem_level") $(color_level "$mem_level" "${mem_pct}%")"

  # Store for JSON
  RESULT_UPTIME="$uptime_str"
  RESULT_CPU="$cpu_pct"
  RESULT_CPU_LEVEL="$cpu_level"
  RESULT_MEM="$mem_pct"
  RESULT_MEM_LEVEL="$mem_level"
}

report_disk() {
  section "2. DISK SPACE"

  local mounts=()
  if is_macos; then
    mounts=("/" "/System/Volumes/Data")
  else
    mounts=("/")
  fi

  RESULT_DISKS=()
  for mount in "${mounts[@]}"; do
    local pct
    pct=$(get_disk_usage "$mount")
    local level
    level=$(threshold_level "${pct:-0}" "$DISK_WARN" "$DISK_CRIT")
    local label="Disk ($mount):"
    row "$label" "$(status_icon "$level") $(color_level "$level" "${pct}% used")"
    RESULT_DISKS+=("$mount:$pct:$level")
  done
}

report_services() {
  section "3. NAVAIA SERVICES"

  # ── Dashboard / API ────────────────────────────────────
  local dash_pid
  dash_pid=$(find_process "navi_core.py\|dashboard\|port.*${DASHBOARD_PORT}" || true)
  # Also check if anything is listening on the port
  if [[ -z "$dash_pid" ]]; then
    dash_pid=$(lsof -ti tcp:"$DASHBOARD_PORT" 2>/dev/null | head -1 || true)
  fi
  if [[ -n "$dash_pid" ]]; then
    row "Dashboard (port $DASHBOARD_PORT):" "$(status_icon ok) Running (PID $dash_pid)"
    RESULT_DASHBOARD="running"
  else
    row "Dashboard (port $DASHBOARD_PORT):" "$(status_icon crit) $(color_level crit "NOT running")"
    RESULT_DASHBOARD="stopped"
  fi

  # ── Telegram Bridge ────────────────────────────────────
  local tg_pid
  tg_pid=$(find_process "telegram_bridge.py" || true)
  if [[ -n "$tg_pid" ]]; then
    row "Telegram Bridge:" "$(status_icon ok) Running (PID $tg_pid)"
    RESULT_TELEGRAM="running"
  else
    row "Telegram Bridge:" "$(status_icon warn) $(color_level warn "NOT running")"
    RESULT_TELEGRAM="stopped"
  fi

  # ── PM Loop ───────────────────────────────────────────
  local pm_pid
  pm_pid=$(find_process "loop.sh" || true)
  if [[ -n "$pm_pid" ]]; then
    row "PM Loop (loop.sh):" "$(status_icon ok) Running (PID $pm_pid)"
    RESULT_PM_LOOP="running"
  else
    row "PM Loop (loop.sh):" "$(status_icon warn) $(color_level warn "NOT running")"
    RESULT_PM_LOOP="stopped"
  fi

  # ── Agent Loops ────────────────────────────────────────
  local agents=("creative" "technical" "admin")
  RESULT_AGENT_LOOPS=()
  for agent in "${agents[@]}"; do
    local pid
    pid=$(find_process "agent-loop.sh.*${agent}\|${agent}.*agent-loop.sh" || true)
    local label="Agent Loop ($agent):"
    if [[ -n "$pid" ]]; then
      row "$label" "$(status_icon ok) Running (PID $pid)"
      RESULT_AGENT_LOOPS+=("$agent:running:$pid")
    else
      row "$label" "$(status_icon info) Not running (ok if unused)"
      RESULT_AGENT_LOOPS+=("$agent:stopped:0")
    fi
  done
}

report_docker() {
  section "4. DOCKER CONTAINERS"

  local docker_output
  docker_output=$(get_docker_containers)

  if [[ -z "$docker_output" ]]; then
    row "Docker:" "$(status_icon info) Not running or no containers"
    RESULT_DOCKER="none"
    return
  fi

  RESULT_DOCKER_CONTAINERS=()
  while IFS=$'\t' read -r name status ports; do
    local icon level
    if echo "$status" | grep -qi "healthy"; then
      icon=$(status_icon ok); level="ok"
    elif echo "$status" | grep -qi "unhealthy"; then
      icon=$(status_icon crit); level="crit"
    elif echo "$status" | grep -qi "up"; then
      icon=$(status_icon ok); level="ok"
    else
      icon=$(status_icon warn); level="warn"
    fi
    local short_status
    short_status=$(echo "$status" | sed 's/(.*//')
    printf "  %-30s %s %s\n" "$name" "$icon" "$(color_level "$level" "$short_status")"
    [[ -n "$ports" ]] && printf "  %-30s %s\n" "" "${CYAN}${ports}${RESET}"
    RESULT_DOCKER_CONTAINERS+=("$name:$level")
  done <<<"$docker_output"
}

report_endpoints() {
  section "5. ENDPOINT RESPONSE TIMES"

  declare -A ENDPOINTS=(
    ["Dashboard"]="http://localhost:${DASHBOARD_PORT}/"
    ["Embedding Service"]="http://localhost:${EMBEDDING_PORT}/"
    ["Weaviate Test"]="http://localhost:${WEAVIATE_TEST_PORT}/v1/.well-known/ready"
    ["Weaviate Prod"]="http://localhost:${WEAVIATE_PROD_PORT}/v1/.well-known/ready"
  )

  RESULT_ENDPOINTS=()
  for name in "Dashboard" "Embedding Service" "Weaviate Test" "Weaviate Prod"; do
    local url="${ENDPOINTS[$name]}"
    local result code ms level icon
    result=$(check_endpoint "$url")
    code=$(awk '{print $1}' <<<"$result")
    ms=$(awk '{print $2}' <<<"$result")

    if [[ "$code" == "000" ]]; then
      icon=$(status_icon warn)
      printf "  %-28s %s %s\n" "${name}:" "$icon" "$(color_level warn "No response (service may be down)")"
      RESULT_ENDPOINTS+=("$name:down:0")
    elif [[ "$code" =~ ^[23] ]]; then
      if   (( ms >= RESPONSE_CRIT_MS )); then level="crit"
      elif (( ms >= RESPONSE_WARN_MS )); then level="warn"
      else level="ok"
      fi
      icon=$(status_icon "$level")
      printf "  %-28s %s %s ms  (HTTP %s)\n" "${name}:" "$icon" \
        "$(color_level "$level" "$ms")" "$code"
      RESULT_ENDPOINTS+=("$name:ok:$ms")
    else
      icon=$(status_icon warn)
      printf "  %-28s %s HTTP %s (%s ms)\n" "${name}:" "$icon" "$code" "$ms"
      RESULT_ENDPOINTS+=("$name:error-$code:$ms")
    fi
  done
}

report_summary() {
  section "SUMMARY"

  local issues=0 warnings=0

  # CPU
  [[ "${RESULT_CPU_LEVEL:-ok}" == "crit" ]] && (( issues++ )) || true
  [[ "${RESULT_CPU_LEVEL:-ok}" == "warn" ]] && (( warnings++ )) || true
  # Memory
  [[ "${RESULT_MEM_LEVEL:-ok}" == "crit" ]] && (( issues++ )) || true
  [[ "${RESULT_MEM_LEVEL:-ok}" == "warn" ]] && (( warnings++ )) || true
  # Dashboard
  [[ "${RESULT_DASHBOARD:-running}" == "stopped" ]] && (( issues++ )) || true
  # Telegram
  [[ "${RESULT_TELEGRAM:-running}" == "stopped" ]] && (( warnings++ )) || true

  local overall
  if   (( issues > 0 ));   then overall="crit"
  elif (( warnings > 0 )); then overall="warn"
  else overall="ok"
  fi

  echo ""
  printf "  %-28s %s\n" "Overall Status:" \
    "$(status_icon "$overall") $(color_level "$overall" "$(echo "$overall" | tr 'a-z' 'A-Z')")"
  printf "  %-28s %d\n" "Critical Issues:" "$issues"
  printf "  %-28s %d\n" "Warnings:" "$warnings"
  echo ""

  if (( issues == 0 && warnings == 0 )); then
    echo -e "  ${GREEN}All systems operational.${RESET}"
  fi
  echo ""
}

json_report() {
  # Simple JSON output (no external deps)
  local ts
  ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
  echo "{"
  echo "  \"timestamp\": \"$ts\","
  echo "  \"host\": \"$(hostname)\","
  echo "  \"uptime\": \"${RESULT_UPTIME:-unknown}\","
  echo "  \"cpu_pct\": ${RESULT_CPU:-0},"
  echo "  \"cpu_level\": \"${RESULT_CPU_LEVEL:-ok}\","
  echo "  \"mem_pct\": ${RESULT_MEM:-0},"
  echo "  \"mem_level\": \"${RESULT_MEM_LEVEL:-ok}\","
  echo "  \"services\": {"
  echo "    \"dashboard\": \"${RESULT_DASHBOARD:-unknown}\","
  echo "    \"telegram_bridge\": \"${RESULT_TELEGRAM:-unknown}\","
  echo "    \"pm_loop\": \"${RESULT_PM_LOOP:-unknown}\""
  echo "  }"
  echo "}"
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  # Initialise result globals
  RESULT_UPTIME="" RESULT_CPU=0 RESULT_CPU_LEVEL="ok"
  RESULT_MEM=0 RESULT_MEM_LEVEL="ok"
  RESULT_DASHBOARD="unknown" RESULT_TELEGRAM="unknown" RESULT_PM_LOOP="unknown"

  report_header
  report_system
  report_disk
  report_services
  report_docker
  report_endpoints
  report_summary

  if $JSON_MODE; then
    echo ""
    json_report
  fi
}

main "$@"
