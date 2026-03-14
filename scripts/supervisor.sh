#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Navaia AI Workforce — Process Supervisor
#
# Monitors and auto-restarts all agent processes. This is the production
# entry point — it ensures agents survive crashes, rate limits, and hangs.
#
# Usage:
#   bash scripts/supervisor.sh              # Start all agents
#   bash scripts/supervisor.sh --no-bridge  # Skip Telegram bridge
#   bash scripts/supervisor.sh --agents pm,creative  # Only specific agents
#
# Managed processes:
#   1. Telegram bridge (tools/telegram_bridge.py)
#   2. Dashboard server (dashboard/server.py)
#   3. Agent loops (scripts/agent-loop.sh × N agents)
#
# Features:
#   - Auto-restart on crash (with exponential backoff)
#   - Health check every 10 seconds
#   - Telegram alerts on failures
#   - Max failure threshold before giving up
#   - Graceful shutdown via STOP file or Ctrl+C
# ──────────────────────────────────────────────────────────────────────────────

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

# ── Load Environment ─────────────────────────────────────────────────────────

if [ ! -f .env ]; then
    echo "[supervisor] .env not found. Run 'bash scripts/setup.sh' first."
    exit 1
fi

set -a
source .env
set +a

export PATH="$HOME/.nvm/versions/node/v22.21.1/bin:$PATH"
unset CLAUDECODE

# ── Configuration ─────────────────────────────────────────────────────────────

STOP_FILE="workspace/comms/STOP"
HEALTH_INTERVAL=10          # seconds between health checks
MAX_FAILURES=10             # max consecutive failures before stopping an agent
LOG_DIR="workspace/logs"
ENABLE_BRIDGE=true
ENABLE_DASHBOARD=true
AGENTS_TO_RUN="pm,creative,technical,admin"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-bridge)
            ENABLE_BRIDGE=false
            shift
            ;;
        --no-dashboard)
            ENABLE_DASHBOARD=false
            shift
            ;;
        --agents)
            AGENTS_TO_RUN="$2"
            shift 2
            ;;
        *)
            echo "[supervisor] Unknown argument: $1"
            exit 1
            ;;
    esac
done

# ── Setup ─────────────────────────────────────────────────────────────────────

mkdir -p "$LOG_DIR"

# Process tracking — associative arrays
declare -A PIDS            # process name → PID
declare -A FAIL_COUNTS     # process name → consecutive failure count
declare -A BACKOFF_UNTIL   # process name → timestamp when backoff expires
declare -A LAST_START      # process name → timestamp of last start

# ── Logging ───────────────────────────────────────────────────────────────────

log() {
    echo "[supervisor] $(date '+%H:%M:%S') $1"
}

log_to_file() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_DIR/supervisor.log"
}

# ── Telegram Alert ────────────────────────────────────────────────────────────

send_alert() {
    local message="$1"
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_FOUNDER_CHAT_ID:-}" ]; then
        # Write to outbox so bridge sends it (or direct API if bridge is down)
        local alert_file="workspace/comms/to-founder/$(date '+%Y%m%d-%H%M%S')-supervisor-alert.md"
        cat > "$alert_file" <<EOF
## SUPERVISOR ALERT

$message

**Time:** $(date '+%Y-%m-%d %H:%M:%S')
EOF
        # Also try direct Telegram API (in case bridge is what died)
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d chat_id="${TELEGRAM_FOUNDER_CHAT_ID}" \
            -d text="[Supervisor] $message" \
            -d parse_mode="Markdown" \
            > /dev/null 2>&1 || true
    fi
}

# ── Process Management ────────────────────────────────────────────────────────

start_process() {
    local name="$1"
    local cmd="$2"
    local log_file="$LOG_DIR/${name}.log"

    # Check backoff
    local now
    now=$(date +%s)
    local backoff_end="${BACKOFF_UNTIL[$name]:-0}"
    if [ "$now" -lt "$backoff_end" ]; then
        local wait_secs=$((backoff_end - now))
        log "$name: backing off for ${wait_secs}s more"
        return 1
    fi

    log "Starting $name..."
    log_to_file "START $name: $cmd"

    # Start process with output redirected to log
    bash -c "$cmd" >> "$log_file" 2>&1 &
    PIDS[$name]=$!
    LAST_START[$name]=$now

    log "$name started (PID: ${PIDS[$name]})"
    return 0
}

stop_process() {
    local name="$1"
    local pid="${PIDS[$name]:-}"

    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        log "Stopping $name (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        # Wait up to 5 seconds for graceful shutdown
        for _ in 1 2 3 4 5; do
            if ! kill -0 "$pid" 2>/dev/null; then
                break
            fi
            sleep 1
        done
        # Force kill if still alive
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        wait "$pid" 2>/dev/null || true
        log "$name stopped"
    fi
    unset "PIDS[$name]"
}

is_running() {
    local name="$1"
    local pid="${PIDS[$name]:-}"
    if [ -z "$pid" ]; then
        return 1
    fi
    kill -0 "$pid" 2>/dev/null
}

handle_failure() {
    local name="$1"
    local count="${FAIL_COUNTS[$name]:-0}"
    count=$((count + 1))
    FAIL_COUNTS[$name]=$count

    # Exponential backoff: 10s, 20s, 40s, 80s, 160s (capped at 300s)
    local backoff=$((10 * (2 ** (count - 1))))
    if [ "$backoff" -gt 300 ]; then
        backoff=300
    fi

    local now
    now=$(date +%s)
    BACKOFF_UNTIL[$name]=$((now + backoff))

    log "$name failed (attempt $count/$MAX_FAILURES). Backoff: ${backoff}s"
    log_to_file "FAIL $name: attempt $count, backoff ${backoff}s"

    if [ "$count" -ge "$MAX_FAILURES" ]; then
        log "$name exceeded max failures ($MAX_FAILURES). Disabling."
        log_to_file "DISABLED $name: too many failures"
        send_alert "$name has crashed $MAX_FAILURES times and has been disabled. Manual intervention needed."
        return 1
    fi

    # Alert on 3rd consecutive failure
    if [ "$count" -eq 3 ]; then
        send_alert "$name has failed 3 times in a row. Auto-restarting with backoff."
    fi

    return 0
}

reset_failures() {
    local name="$1"
    FAIL_COUNTS[$name]=0
    BACKOFF_UNTIL[$name]=0
}

# ── Cleanup ───────────────────────────────────────────────────────────────────

cleanup() {
    echo ""
    log "Shutting down all processes..."

    for name in "${!PIDS[@]}"; do
        stop_process "$name"
    done

    # Clean up lock files
    rm -f /tmp/navaia-*-working
    rm -f "$STOP_FILE"

    log "All processes stopped. Goodbye."
    exit 0
}

trap cleanup EXIT INT TERM

# ── Start Services ────────────────────────────────────────────────────────────

echo ""
echo "================================================================"
echo "  NAVAIA AI WORKFORCE — PROCESS SUPERVISOR"
echo "  Agents: $AGENTS_TO_RUN"
echo "  Bridge: $ENABLE_BRIDGE | Dashboard: $ENABLE_DASHBOARD"
echo "  Health check interval: ${HEALTH_INTERVAL}s"
echo "  Max failures per process: $MAX_FAILURES"
echo "  Logs: $LOG_DIR/"
echo "================================================================"
echo ""

# Start Telegram bridge
if [ "$ENABLE_BRIDGE" = true ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    FAIL_COUNTS[bridge]=0
    start_process "bridge" "python3 tools/telegram_bridge.py"
    sleep 2  # Let bridge initialize before agents
fi

# Start Dashboard
if [ "$ENABLE_DASHBOARD" = true ]; then
    FAIL_COUNTS[dashboard]=0
    start_process "dashboard" "python3 dashboard/server.py"
    sleep 1
fi

# Start agent loops
IFS=',' read -ra AGENT_LIST <<< "$AGENTS_TO_RUN"
for agent in "${AGENT_LIST[@]}"; do
    agent=$(echo "$agent" | tr -d ' ')
    FAIL_COUNTS["agent-$agent"]=0
    start_process "agent-$agent" "bash scripts/agent-loop.sh $agent"
done

log "All processes started. Entering health check loop."
echo ""

# ── Health Check Loop ─────────────────────────────────────────────────────────

while true; do
    sleep "$HEALTH_INTERVAL"

    # Check STOP signal
    if [ -f "$STOP_FILE" ]; then
        log "STOP signal detected. Shutting down."
        break
    fi

    # Check and restart Telegram bridge
    if [ "$ENABLE_BRIDGE" = true ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
        if ! is_running "bridge"; then
            log "bridge is DOWN — restarting..."
            if handle_failure "bridge"; then
                start_process "bridge" "python3 tools/telegram_bridge.py" || true
            fi
        else
            # Process survived a health check — reset failure count if it's been running >60s
            local_now=$(date +%s)
            local_started="${LAST_START[bridge]:-0}"
            if [ $((local_now - local_started)) -gt 60 ]; then
                reset_failures "bridge"
            fi
        fi
    fi

    # Check and restart Dashboard
    if [ "$ENABLE_DASHBOARD" = true ]; then
        if ! is_running "dashboard"; then
            log "dashboard is DOWN — restarting..."
            if handle_failure "dashboard"; then
                start_process "dashboard" "python3 dashboard/server.py" || true
            fi
        else
            local_now=$(date +%s)
            local_started="${LAST_START[dashboard]:-0}"
            if [ $((local_now - local_started)) -gt 60 ]; then
                reset_failures "dashboard"
            fi
        fi
    fi

    # Check and restart agent loops
    for agent in "${AGENT_LIST[@]}"; do
        agent=$(echo "$agent" | tr -d ' ')
        local_name="agent-$agent"
        if ! is_running "$local_name"; then
            # Agent loops exit normally when there's no work — that's fine, not a failure
            # Only count as failure if it died within 10 seconds of starting
            local_now=$(date +%s)
            local_started="${LAST_START[$local_name]:-0}"

            if [ $((local_now - local_started)) -lt 10 ]; then
                # Died too fast — likely a real error
                log "$local_name crashed (ran < 10s) — restarting with backoff..."
                if handle_failure "$local_name"; then
                    start_process "$local_name" "bash scripts/agent-loop.sh $agent" || true
                fi
            else
                # Normal exit (finished work or no tasks) — restart immediately
                reset_failures "$local_name"
                start_process "$local_name" "bash scripts/agent-loop.sh $agent" || true
            fi
        fi
    done

done
