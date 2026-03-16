#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# RL Counter — Zero-token trigger for reinforcement learning evaluations
#
# Counts files in workspace/tasks/done/, compares to last-evaluated count.
# Outputs TRIGGER when 20+ new completions since last eval, else WAIT:N/20.
#
# Sourced by ceo-scheduler.sh. No AI calls — pure bash.
#
# Usage:
#   source scripts/rl-counter.sh
#   result=$(check_rl_counter)
#   # Returns "TRIGGER" or "WAIT:N/20"
# ──────────────────────────────────────────────────────────────────────────────

RL_COUNTER_FILE="/tmp/navaia-rl-counter"
RL_BATCH_SIZE=20

check_rl_counter() {
    local repo_root
    repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    local done_dir="$repo_root/workspace/tasks/done"

    # Count completed tasks (excluding .gitkeep)
    local current_count=0
    if [ -d "$done_dir" ]; then
        current_count=$(find "$done_dir" -type f ! -name '.gitkeep' 2>/dev/null | wc -l | tr -d ' ')
    fi

    # Read last evaluated count
    local last_count=0
    if [ -f "$RL_COUNTER_FILE" ]; then
        last_count=$(cat "$RL_COUNTER_FILE" 2>/dev/null | tr -d ' ')
        # Validate it's a number
        if ! [[ "$last_count" =~ ^[0-9]+$ ]]; then
            last_count=0
        fi
    fi

    local new_tasks=$((current_count - last_count))

    if [ "$new_tasks" -ge "$RL_BATCH_SIZE" ]; then
        # Update the counter file to current count
        echo "$current_count" > "$RL_COUNTER_FILE"
        echo "TRIGGER"
    else
        if [ "$new_tasks" -lt 0 ]; then
            new_tasks=0
        fi
        echo "WAIT:${new_tasks}/${RL_BATCH_SIZE}"
    fi
}

# Allow direct execution for testing
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    check_rl_counter
fi
