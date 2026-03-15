#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Agent Health Monitor — Called by the PM loop to detect and fix agent problems
#
# Usage (sourced from agent-loop.sh):
#   source scripts/health-check.sh
#   run_health_check   # runs all checks, writes alerts if needed
#
# Checks:
#   1. Stale locks — lock file exists but no Claude process running
#   2. Stuck agents — working too long for their model tier
#   3. Repeated failures — tasks sitting in agent folders across multiple cycles
#   4. Self-healing — cleans stale locks, deduplicates tasks, moves 3x failures
# ──────────────────────────────────────────────────────────────────────────────

HEALTH_CHECK_DIR="${REPO_ROOT:-.}"
HEALTH_STATE_DIR="/tmp/navaia-health"
AGENTS=("creative" "technical" "admin")
COMMS_DIR="$HEALTH_CHECK_DIR/workspace/comms/to-manager"
HEALTH_FAILED_DIR="$HEALTH_CHECK_DIR/workspace/tasks/failed"

# Max working time per model (seconds)
MAX_TIME_HAIKU=900     # 15 min
MAX_TIME_SONNET=1800   # 30 min
MAX_TIME_OPUS=3600     # 60 min

mkdir -p "$HEALTH_STATE_DIR" "$COMMS_DIR" "$HEALTH_FAILED_DIR"

# ── Check for stale locks ────────────────────────────────────────────────────

_check_stale_locks() {
    local alerts=""
    for agent in "${AGENTS[@]}"; do
        local lock_file="/tmp/navaia-${agent}-working"
        if [ -f "$lock_file" ]; then
            # Check if the agent-loop.sh process is running for this specific agent
            if ! pgrep -f "agent-loop.sh ${agent}" >/dev/null 2>&1; then
                rm -f "$lock_file"
                alerts="${alerts}- Cleaned stale lock for **${agent}** (agent loop not running)\n"
                echo "[health-check] Cleaned stale lock: $agent" >&2
            fi
        fi
    done
    echo "$alerts"
}

# ── Check for stuck agents ───────────────────────────────────────────────────

_check_stuck_agents() {
    local alerts=""
    for agent in "${AGENTS[@]}"; do
        local lock_file="/tmp/navaia-${agent}-working"
        if [ -f "$lock_file" ]; then
            local lock_age
            lock_age=$(( $(date +%s) - $(stat -f %m "$lock_file" 2>/dev/null || stat -c %Y "$lock_file" 2>/dev/null || echo "0") ))

            # Determine max time based on what model the agent is likely using
            local max_time=$MAX_TIME_SONNET
            local task_dir="$HEALTH_CHECK_DIR/workspace/tasks/${agent}"
            if [ -d "$task_dir" ]; then
                local model_hint
                model_hint=$(grep -rhi '^\*\*Model:\*\*' "$task_dir" 2>/dev/null | head -1 | sed 's/.*\*\*Model:\*\*[[:space:]]*//' | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
                case "$model_hint" in
                    opus)  max_time=$MAX_TIME_OPUS ;;
                    haiku) max_time=$MAX_TIME_HAIKU ;;
                    *)     max_time=$MAX_TIME_SONNET ;;
                esac
            fi

            if [ "$lock_age" -gt "$max_time" ]; then
                local mins=$(( lock_age / 60 ))
                local max_mins=$(( max_time / 60 ))
                alerts="${alerts}- **${agent}** has been working for ${mins}min (limit: ${max_mins}min) — may be stuck\n"
                echo "[health-check] Stuck agent detected: $agent (${mins}min)" >&2
            fi
        fi
    done
    echo "$alerts"
}

# ── Check for repeated failures ──────────────────────────────────────────────

_check_repeated_failures() {
    local alerts=""
    for agent in "${AGENTS[@]}"; do
        local task_dir="$HEALTH_CHECK_DIR/workspace/tasks/${agent}"
        [ -d "$task_dir" ] || continue

        while IFS= read -r task_file; do
            [ -z "$task_file" ] && continue
            local base_name
            base_name=$(basename "$task_file")
            local state_file="$HEALTH_STATE_DIR/${agent}-${base_name}.count"

            # Increment the seen count
            local count=0
            if [ -f "$state_file" ]; then
                count=$(cat "$state_file" 2>/dev/null || echo "0")
            fi
            count=$((count + 1))
            echo "$count" > "$state_file"

            if [ "$count" -ge 3 ]; then
                # Move to failed/ with metadata
                {
                    echo ""
                    echo "---"
                    echo "## FAILURE LOG (Health Monitor)"
                    echo "**Agent:** $agent"
                    echo "**Failed at:** $(date '+%Y-%m-%d %H:%M:%S')"
                    echo "**Cycles seen:** $count"
                    echo "**Reason:** Task remained in folder for $count consecutive health checks"
                } >> "$task_file"
                mv "$task_file" "${HEALTH_FAILED_DIR}/${agent}-${base_name}"
                rm -f "$state_file"
                alerts="${alerts}- Moved **${base_name}** to failed/ — sat in ${agent}'s folder for ${count} cycles\n"
                echo "[health-check] Moved stale task to failed: $agent/$base_name ($count cycles)" >&2
            fi
        done < <(find "$task_dir" -maxdepth 1 -type f ! -name '.gitkeep' 2>/dev/null)
    done

    # Clean up state files for tasks that no longer exist
    for state_file in "$HEALTH_STATE_DIR"/*.count; do
        [ -f "$state_file" ] || continue
        local fname
        fname=$(basename "$state_file" .count)
        local agent_part="${fname%%-*}"
        local task_part="${fname#*-}"
        local task_path="$HEALTH_CHECK_DIR/workspace/tasks/${agent_part}/${task_part}"
        if [ ! -f "$task_path" ]; then
            rm -f "$state_file"
        fi
    done

    echo "$alerts"
}

# ── Remove duplicate task files ──────────────────────────────────────────────

_deduplicate_tasks() {
    local alerts=""
    for agent in "${AGENTS[@]}"; do
        local task_dir="$HEALTH_CHECK_DIR/workspace/tasks/${agent}"
        [ -d "$task_dir" ] || continue

        local seen_hashes=""
        while IFS= read -r task_file; do
            [ -z "$task_file" ] && continue
            local hash
            hash=$(md5 -q "$task_file" 2>/dev/null || md5sum "$task_file" 2>/dev/null | cut -d' ' -f1)
            if echo "$seen_hashes" | grep -q "$hash"; then
                local base_name
                base_name=$(basename "$task_file")
                rm -f "$task_file"
                alerts="${alerts}- Removed duplicate task **${base_name}** from ${agent}'s folder\n"
                echo "[health-check] Removed duplicate: $agent/$base_name" >&2
            else
                seen_hashes="${seen_hashes}${hash}\n"
            fi
        done < <(find "$task_dir" -maxdepth 1 -type f ! -name '.gitkeep' 2>/dev/null | sort)
    done
    echo "$alerts"
}

# ── Main health check function ───────────────────────────────────────────────

run_health_check() {
    local all_alerts=""

    local stale_alerts
    stale_alerts=$(_check_stale_locks)
    all_alerts="${all_alerts}${stale_alerts}"

    local stuck_alerts
    stuck_alerts=$(_check_stuck_agents)
    all_alerts="${all_alerts}${stuck_alerts}"

    local dedup_alerts
    dedup_alerts=$(_deduplicate_tasks)
    all_alerts="${all_alerts}${dedup_alerts}"

    local failure_alerts
    failure_alerts=$(_check_repeated_failures)
    all_alerts="${all_alerts}${failure_alerts}"

    # Strip whitespace to check if there are real alerts
    local trimmed
    trimmed=$(echo -e "$all_alerts" | sed '/^$/d' | tr -d '[:space:]')

    if [ -n "$trimmed" ]; then
        local timestamp
        timestamp=$(date '+%Y%m%d-%H%M%S')
        cat > "${COMMS_DIR}/${timestamp}-health-alert.md" <<EOF
## AGENT HEALTH ALERT

The following issues were detected and handled:

$(echo -e "$all_alerts")

**Source:** Automated health monitor (PM loop)
**Time:** $(date '+%Y-%m-%d %H:%M:%S')
EOF
        echo "[health-check] Alert written to ${timestamp}-health-alert.md" >&2
    else
        echo "[health-check] All agents healthy" >&2
    fi
}
