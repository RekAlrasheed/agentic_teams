#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# CEO Scheduler — Drops task files for Rex on a fixed schedule
#
# Zero Claude tokens — pure bash. Creates task files in workspace/tasks/ceo/
# that the agent-loop picks up and feeds to Rex.
#
# Schedule:
#   - Performance Review: every 6 hours (4x/day)
#   - RL Evaluation: every 20 completed tasks (via rl-counter.sh)
#   - KPI Snapshot: quarterly (~90 days)
#   - Strategic Planning: Mon/Wed/Fri (09:00)
#
# Usage:
#   bash scripts/ceo-scheduler.sh          # Run in foreground
#   bash scripts/ceo-scheduler.sh &        # Run in background
#
# Guards:
#   - Skips if CEO already has a pending task (prevents queue buildup)
#   - Uses state files in /tmp to track last run times
# ──────────────────────────────────────────────────────────────────────────────

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

CEO_TASK_DIR="workspace/tasks/ceo"
STATE_DIR="/tmp/navaia-ceo-scheduler"
STOP_FILE="workspace/comms/STOP"
CHECK_INTERVAL=300  # 5 minutes
RL_BATCH_FILE="$STATE_DIR/rl-batch"

mkdir -p "$CEO_TASK_DIR" "$STATE_DIR"

# Source RL counter for task-completion-based evaluation triggers
source "$SCRIPT_DIR/rl-counter.sh"

# ── Helpers ──────────────────────────────────────────────────────────────────

log() {
    echo "[ceo-scheduler] $(date '+%H:%M:%S') $1"
}

has_pending_task() {
    local count
    count=$(find "$CEO_TASK_DIR" -maxdepth 1 -type f ! -name '.gitkeep' 2>/dev/null | wc -l | tr -d ' ')
    [ "$count" -gt 0 ]
}

seconds_since_last() {
    local state_file="$STATE_DIR/$1"
    if [ ! -f "$state_file" ]; then
        echo "999999"
        return
    fi
    local last
    last=$(cat "$state_file" 2>/dev/null || echo "0")
    local now
    now=$(date +%s)
    echo $(( now - last ))
}

mark_run() {
    date +%s > "$STATE_DIR/$1"
}

write_task() {
    local task_type="$1"
    local title="$2"
    local model="$3"
    local max_turns="$4"
    local description="$5"
    local timestamp
    timestamp=$(date '+%Y%m%d-%H%M%S')
    local filename="${timestamp}-${task_type}.md"

    cat > "${CEO_TASK_DIR}/${filename}" <<EOF
## TASK: ${title}
**Time:** $(date -u '+%Y-%m-%dT%H:%M:%SZ')
**Source:** ceo-scheduler (automated)
**Assigned Agent:** Rex (CEO)
**Priority:** Standard
**Model:** ${model}
**Max-Turns:** ${max_turns}

### Description
${description}

**TOKEN BUDGET:** Keep this session short. Read only what you need, write a concise report, exit.
EOF
    log "Created task: $filename (model: $model, max-turns: $max_turns)"
}

# ── Schedule Logic ───────────────────────────────────────────────────────────

check_performance_review() {
    # Every 6 hours = 21600 seconds
    local elapsed
    elapsed=$(seconds_since_last "performance-review")
    if [ "$elapsed" -ge 21600 ]; then
        # Sonnet — data read + structured report, no deep reasoning needed
        write_task "performance-review" \
            "Agent Performance Review" \
            "sonnet" "15" \
            "Review all agent performance for the last 6 hours.

Steps (keep it tight):
1. Count files in workspace/tasks/done/ — group by agent prefix
2. Count files in workspace/tasks/failed/ — group by agent prefix
3. Query workspace/token_usage.db: SELECT agent, SUM(estimated_cost) as cost, COUNT(*) as calls FROM token_usage WHERE timestamp > datetime('now', '-6 hours') GROUP BY agent
4. Write a SHORT review (200-300 words max) to workspace/outputs/ceo/performance/review-$(date '+%Y-%m-%d-%H%M').md
5. Send 3-5 bullet summary to workspace/comms/inter-agent/ceo-to-pm-performance.md
6. Exit immediately."
        mark_run "performance-review"
    fi
}

check_rl_evaluation() {
    local result
    result=$(check_rl_counter)

    if [ "$result" = "TRIGGER" ]; then
        # Determine batch number
        local batch=1
        if [ -f "$RL_BATCH_FILE" ]; then
            batch=$(cat "$RL_BATCH_FILE" 2>/dev/null || echo "0")
            if ! [[ "$batch" =~ ^[0-9]+$ ]]; then batch=0; fi
            batch=$((batch + 1))
        fi
        echo "$batch" > "$RL_BATCH_FILE"

        local today
        today=$(date '+%Y-%m-%d')

        log "Triggering RL evaluation batch #${batch}..."
        write_task "rl-evaluation" \
            "RL Evaluation Batch ${batch}" \
            "sonnet" "15" \
            "Run RL evaluation batch #${batch} for all agents.

Steps:
1. Read workspace/tasks/done/ — identify completed tasks per agent since last eval
2. Read workspace/tasks/failed/ — note failures per agent
3. Query workspace/token_usage.db — get token costs per agent
4. Read recent outputs in workspace/outputs/{agent}/ — assess quality
5. For each active agent, calculate quality rating (1-5) and score delta
6. POST each agent's evaluation to http://localhost:7777/api/performance/evaluate
7. Write summary to workspace/outputs/ceo/performance/rl-eval-batch-${batch}-${today}.md
8. Exit immediately.

POST format:
{\"agent\":\"creative\",\"batch\":${batch},\"quality_rating\":4,\"score_delta\":3.0,\"token_efficiency\":0.85,\"failure_count\":0,\"success_count\":5,\"summary\":\"Strong output.\",\"tasks_evaluated\":[\"task1.md\"]}

Use the RL scoring formula from your CLAUDE.md. Evaluate ALL agents with activity."
        mark_run "rl-evaluation"
    else
        log "RL counter: $result"
    fi
}

check_kpi_snapshot() {
    # Quarterly = 7776000 seconds (~90 days)
    local elapsed
    elapsed=$(seconds_since_last "kpi-snapshot")
    if [ "$elapsed" -ge 7776000 ]; then
        local month quarter year period
        month=$(date '+%m')
        year=$(date '+%Y')
        if [ "$month" -le 3 ]; then quarter="Q1"; elif [ "$month" -le 6 ]; then quarter="Q2"; elif [ "$month" -le 9 ]; then quarter="Q3"; else quarter="Q4"; fi
        period="${quarter}-${year}"

        write_task "kpi-snapshot" \
            "Quarterly KPI Snapshot ${period}" \
            "sonnet" "20" \
            "Measure all department KPIs for ${period}.

Steps:
1. Calculate shared KPIs: task completion rate (>90%), failure rate (<10%), token efficiency
2. Calculate department KPIs per your CLAUDE.md definitions
3. Write KPI report to workspace/outputs/ceo/performance/kpi-${period}.md
4. Send summary to workspace/comms/inter-agent/ceo-to-pm-kpi-${period}.md
5. Exit immediately.

Format: table with Agent | KPI | Target | Actual | Status (MET/MISSED)"
        mark_run "kpi-snapshot"
    fi
}

check_strategic_planning() {
    # Mon/Wed/Fri only, 86400 second cooldown
    local elapsed
    elapsed=$(seconds_since_last "strategic-planning")
    local dow
    dow=$(date '+%u')  # 1=Mon, 3=Wed, 5=Fri
    local hour
    hour=$(date '+%H')
    if [ "$elapsed" -ge 86400 ] && { [ "$dow" -eq 1 ] || [ "$dow" -eq 3 ] || [ "$dow" -eq 5 ]; } && [ "$hour" -ge 9 ] && [ "$hour" -le 11 ]; then
        # Opus — strategic thinking requires deep reasoning
        write_task "strategic-planning" \
            "Strategic Planning Session" \
            "opus" "25" \
            "Bi-weekly strategic review.

Steps:
1. Review recent performance trends (read last 2-3 performance reviews)
2. Identify one growth opportunity or resource optimization
3. Write 200-word strategic note to workspace/outputs/ceo/business-dev/strategy-$(date '+%Y-%m-%d').md
4. Send 3 bullet summary to workspace/comms/inter-agent/ceo-to-pm-strategy.md
5. Exit immediately.

Focus on actionable ideas, not vision statements."
        mark_run "strategic-planning"
    fi
}

# ── Main Loop ────────────────────────────────────────────────────────────────

log "CEO Scheduler started. Checking every ${CHECK_INTERVAL}s."
log "Task dir: $CEO_TASK_DIR"

while true; do
    # Check STOP signal
    if [ -f "$STOP_FILE" ]; then
        log "STOP signal detected. Exiting."
        break
    fi

    # Only create tasks if CEO queue is empty (prevent buildup)
    if has_pending_task; then
        log "CEO has pending task(s). Skipping schedule check."
    else
        check_performance_review
        check_rl_evaluation
        check_kpi_snapshot
        check_strategic_planning
    fi

    sleep "$CHECK_INTERVAL"
done

log "CEO Scheduler stopped."
