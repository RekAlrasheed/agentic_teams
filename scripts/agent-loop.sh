#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Per-Agent Loop — Runs a single agent in its own terminal
#
# Usage:
#   bash scripts/agent-loop.sh pm
#   bash scripts/agent-loop.sh creative
#   bash scripts/agent-loop.sh technical
#   bash scripts/agent-loop.sh admin
# ──────────────────────────────────────────────────────────────────────────────

set -uo pipefail

AGENT_NAME="${1:-}"

if [ -z "$AGENT_NAME" ]; then
    echo "Usage: bash scripts/agent-loop.sh <pm|creative|technical|admin>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

# ── Load Environment ─────────────────────────────────────────────────────────

if [ ! -f .env ]; then
    echo "[$AGENT_NAME] .env not found."
    exit 1
fi

set -a
source .env
set +a

# Ensure claude CLI is on PATH
export PATH="$HOME/.nvm/versions/node/v22.21.1/bin:$PATH"
unset CLAUDECODE

# ── Agent Config ─────────────────────────────────────────────────────────────

case "$AGENT_NAME" in
    pm)
        DISPLAY_NAME="Navi (PM)"
        TASK_DIR="workspace/tasks/inbox"
        EXTRA_DIRS="workspace/tasks/active workspace/comms/from-founder"
        MODEL="sonnet"
        AGENT_CLAUDE_MD="agents/pm/CLAUDE.md"
        ;;
    creative)
        DISPLAY_NAME="Muse (Creative)"
        TASK_DIR="workspace/tasks/creative"
        EXTRA_DIRS=""
        MODEL="sonnet"
        AGENT_CLAUDE_MD="agents/creative/CLAUDE.md"
        ;;
    technical)
        DISPLAY_NAME="Arch (Technical)"
        TASK_DIR="workspace/tasks/technical"
        EXTRA_DIRS=""
        MODEL="sonnet"
        AGENT_CLAUDE_MD="agents/technical/CLAUDE.md"
        ;;
    admin)
        DISPLAY_NAME="Sage (Admin)"
        TASK_DIR="workspace/tasks/admin"
        EXTRA_DIRS=""
        MODEL="haiku"
        AGENT_CLAUDE_MD="agents/admin/CLAUDE.md"
        ;;
    *)
        echo "Unknown agent: $AGENT_NAME"
        echo "Valid agents: pm, creative, technical, admin"
        exit 1
        ;;
esac

# Ensure task directory exists
mkdir -p "$TASK_DIR"

STOP_FILE="workspace/comms/STOP"
FAILED_DIR="workspace/tasks/failed"
MAX_RESTARTS=${MAX_RESTARTS:-200}
MAX_TASK_RETRIES=3
SESSION_COUNTER=0
CONSECUTIVE_FAILURES=0
BACKOFF_DELAY=0

mkdir -p "$FAILED_DIR"

# ── PM-specific: Start Telegram Bridge ────────────────────────────────────────

BRIDGE_PID=""
if [ "$AGENT_NAME" = "pm" ]; then
    if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_FOUNDER_CHAT_ID:-}" ]; then
        # Kill any existing bridge first
        pkill -f "telegram_bridge" 2>/dev/null || true
        sleep 1
        echo "[$DISPLAY_NAME] Starting Telegram bridge..."
        python3 tools/telegram_bridge.py &
        BRIDGE_PID=$!
        echo "[$DISPLAY_NAME] Bridge started (PID: $BRIDGE_PID)"
    fi
fi

# ── Cleanup ──────────────────────────────────────────────────────────────────

cleanup() {
    echo ""
    echo "[$DISPLAY_NAME] Shutting down..."
    rm -f "/tmp/navaia-${AGENT_NAME}-working"
    if [ -n "$BRIDGE_PID" ] && kill -0 "$BRIDGE_PID" 2>/dev/null; then
        kill "$BRIDGE_PID" 2>/dev/null || true
        wait "$BRIDGE_PID" 2>/dev/null || true
    fi
    echo "[$DISPLAY_NAME] Sessions completed: $SESSION_COUNTER"
    exit 0
}

trap cleanup EXIT INT TERM

# ── Helper: Count tasks ──────────────────────────────────────────────────────

count_tasks() {
    local dir="$1"
    if [ -d "$dir" ]; then
        find "$dir" -type f ! -name '.gitkeep' 2>/dev/null | wc -l | tr -d ' '
    else
        echo "0"
    fi
}

has_work() {
    local main_count
    main_count=$(count_tasks "$TASK_DIR")
    if [ "$main_count" -gt 0 ]; then
        return 0
    fi
    # Check extra dirs (for PM)
    if [ -n "$EXTRA_DIRS" ]; then
        for dir in $EXTRA_DIRS; do
            local c
            c=$(count_tasks "$dir")
            if [ "$c" -gt 0 ]; then
                return 0
            fi
        done
    fi
    return 1
}

# ── Build Agent Prompt ───────────────────────────────────────────────────────

build_prompt() {
    if [ "$AGENT_NAME" = "pm" ]; then
        cat <<'PROMPT'
You are Navi, the PM Agent of Navaia's AI Workforce.

IMPORTANT: You are running in MULTI-TERMINAL mode. Each agent runs in its own terminal.
Do NOT use the Agent tool to spawn teammates. Instead, DISPATCH tasks by writing files:

To assign work to an agent, write a task file to their folder:
- Creative (Muse): workspace/tasks/creative/{timestamp}-task.md
- Technical (Arch): workspace/tasks/technical/{timestamp}-task.md
- Admin (Sage): workspace/tasks/admin/{timestamp}-task.md

Each agent loop will pick up the task automatically.

TASK DISPATCHING:
- Write task descriptions naturally — don't over-specify commands or steps. Agents know their tools.
- If the Manager's task includes "JDI" (Just Do It), pass JDI through to the agent task. This means skip planning, execute immediately.
- If the Manager's task is complex and does NOT include JDI, the agent will propose a plan before executing.

STARTUP:
1. Read CLAUDE.md for full instructions
2. Check workspace/tasks/inbox/ for new tasks
3. Check workspace/tasks/active/ for in-progress work
4. Check workspace/comms/from-founder/ for replies
5. If ALL empty — EXIT immediately
6. For each task: analyze it, decide which agent(s) should handle it
7. Write agent-specific task files to dispatch work
8. Send status to Manager via workspace/comms/to-founder/

NEVER ask questions in the terminal. Route questions via workspace/comms/to-founder/.
Begin now.
PROMPT
    else
        cat <<PROMPT
You are the ${DISPLAY_NAME} of Navaia's AI Workforce.

Read ${AGENT_CLAUDE_MD} for your full role and instructions.
Read knowledge/INDEX.md to understand available company files.

YOUR TASK FOLDER: ${TASK_DIR}/
Check it for task files. Execute each task according to your skills.
Save outputs to workspace/outputs/${AGENT_NAME}/.

TASK COMPLEXITY PROTOCOL:
Before starting any task, assess its complexity:

1. If the task contains "JDI" (Just Do It) → skip planning, execute immediately.
2. If the task is SIMPLE (clear instructions, under 5 minutes of work) → execute immediately.
3. If the task is COMPLEX (multi-step, ambiguous, architectural, risky) → DO NOT start working.
   Instead:
   a. Write a plan to workspace/comms/to-founder/ explaining:
      - What you understand the task to be
      - Your proposed approach (steps)
      - Estimated scope
      - Any risks or trade-offs
   b. Wait for approval in workspace/comms/from-manager/ before proceeding.
4. If the task is UNCLEAR (missing info, ambiguous requirements) → DO NOT guess.
   Instead:
   a. Write your questions to workspace/comms/to-founder/
   b. Wait for answers in workspace/comms/from-manager/ before proceeding.

When done:
1. Move the task file to workspace/tasks/done/
2. Write a DETAILED completion report to workspace/comms/to-founder/ that includes:
   - What you did (summary of work)
   - Key results or answers the Manager needs
   - Path to output file(s) in workspace/outputs/${AGENT_NAME}/
   - Any blockers or follow-up needed
   The Manager reads this on Telegram — make it complete and useful.

If no tasks in your folder — EXIT immediately to save tokens.
NEVER ask questions in the terminal. All questions go through workspace/comms/to-founder/.
Begin now.
PROMPT
    fi
}

# ── Model Escalation ─────────────────────────────────────────────────────────

detect_model() {
    # Navi (PM) specifies the model in the task file as **Model:** <model>
    # If specified, use it. Otherwise fall back to the agent's default.
    local base_model="$MODEL"

    # Check task files for a PM-specified model
    while IFS= read -r f; do
        local specified
        specified=$(grep -i '^\*\*Model:\*\*' "$f" 2>/dev/null | head -1 | sed 's/.*\*\*Model:\*\*[[:space:]]*//' | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
        if [ "$specified" = "opus" ] || [ "$specified" = "sonnet" ] || [ "$specified" = "haiku" ]; then
            echo "$specified"
            return
        fi
    done < <(find "$TASK_DIR" -maxdepth 1 -type f ! -name '.gitkeep' 2>/dev/null)

    echo "$base_model"
}

detect_max_turns() {
    # Navi (PM) can specify max turns in the task file as **Max-Turns:** <number>
    # If specified, use it. Otherwise pick a default based on model.
    while IFS= read -r f; do
        local specified
        specified=$(grep -i '^\*\*Max-Turns:\*\*' "$f" 2>/dev/null | head -1 | sed 's/.*\*\*Max-Turns:\*\*[[:space:]]*//' | tr -d '[:space:]')
        if [ -n "$specified" ] && [ "$specified" -gt 0 ] 2>/dev/null; then
            echo "$specified"
            return
        fi
    done < <(find "$TASK_DIR" -maxdepth 1 -type f ! -name '.gitkeep' 2>/dev/null)

    # Smart defaults based on model — complex tasks get more room
    local model="${1:-sonnet}"
    case "$model" in
        opus)   echo "50" ;;
        sonnet) echo "25" ;;
        haiku)  echo "15" ;;
        *)      echo "15" ;;
    esac
}

# ── Main Loop ────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  $DISPLAY_NAME — Agent Loop"
echo "  Task folder: $TASK_DIR"
echo "  Default model: $MODEL (auto-escalates for complex tasks)"
echo "═══════════════════════════════════════════════════════"
echo ""

while [ "$SESSION_COUNTER" -lt "$MAX_RESTARTS" ]; do

    # Check STOP signal
    if [ -f "$STOP_FILE" ]; then
        echo "[$DISPLAY_NAME] STOP signal. Halting."
        break
    fi

    # Check for work
    TASK_COUNT=$(count_tasks "$TASK_DIR")
    echo "[$DISPLAY_NAME] $(date '+%H:%M:%S') — Checking $TASK_DIR ... found $TASK_COUNT task(s)"
    if ! has_work; then
        echo "[$DISPLAY_NAME] $(date '+%H:%M:%S') — No tasks. Waiting 30s..."
        sleep 30
        continue
    fi

    SESSION_COUNTER=$((SESSION_COUNTER + 1))
    TASK_COUNT=$(count_tasks "$TASK_DIR")

    # Auto-detect model and max turns from task file (set by Navi)
    SESSION_MODEL=$(detect_model)
    SESSION_MAX_TURNS=$(detect_max_turns "$SESSION_MODEL")
    echo "[$DISPLAY_NAME] Session #${SESSION_COUNTER} — ${TASK_COUNT} task(s) — Model: $SESSION_MODEL — Max turns: $SESSION_MAX_TURNS"

    PROMPT=$(build_prompt)

    # Launch Claude — lock file signals "WORKING" to the dashboard
    touch "/tmp/navaia-${AGENT_NAME}-working"

    CLAUDE_EXIT=0
    CLAUDE_STDERR=$(mktemp)
    CLAUDE_STDOUT=$(mktemp)
    START_TIME=$(date +%s)
    claude --dangerously-skip-permissions --model "$SESSION_MODEL" --max-turns "$SESSION_MAX_TURNS" "$PROMPT" >"$CLAUDE_STDOUT" 2>"$CLAUDE_STDERR" || CLAUDE_EXIT=$?
    END_TIME=$(date +%s)
    DURATION_MS=$(( (END_TIME - START_TIME) * 1000 ))
    rm -f "/tmp/navaia-${AGENT_NAME}-working"

    # ── Token tracking ────────────────────────────────────────────────────
    STDOUT_SIZE=$(wc -c < "$CLAUDE_STDOUT" 2>/dev/null | tr -d ' ')
    PROMPT_SIZE=${#PROMPT}
    python3 -c "
import sys
sys.path.insert(0, 'tools')
try:
    from token_tracker import TokenTracker
    t = TokenTracker()
    t.log_call(
        agent='${AGENT_NAME}', model='${SESSION_MODEL}',
        input_text='x' * ${PROMPT_SIZE}, output_text='x' * ${STDOUT_SIZE:-0},
        prompt_text='x' * ${PROMPT_SIZE},
        duration_ms=${DURATION_MS}, source='agent-loop',
        task_type='session-${SESSION_COUNTER}',
    )
except Exception:
    pass
" 2>/dev/null || true
    cat "$CLAUDE_STDOUT" 2>/dev/null || true
    rm -f "$CLAUDE_STDOUT"

    # ── Rate limit detection and backoff ──────────────────────────────────
    STDERR_CONTENT=""
    if [ -f "$CLAUDE_STDERR" ]; then
        STDERR_CONTENT=$(cat "$CLAUDE_STDERR" 2>/dev/null || true)
        rm -f "$CLAUDE_STDERR"
    fi

    if echo "$STDERR_CONTENT" | grep -qi "rate.limit\|429\|too many requests\|overloaded\|capacity"; then
        CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
        # Exponential backoff: 30s, 60s, 120s, 240s, capped at 300s
        BACKOFF_DELAY=$((30 * (2 ** (CONSECUTIVE_FAILURES - 1))))
        if [ "$BACKOFF_DELAY" -gt 300 ]; then
            BACKOFF_DELAY=300
        fi
        echo "[$DISPLAY_NAME] Rate limited (attempt $CONSECUTIVE_FAILURES). Backing off ${BACKOFF_DELAY}s..."
        # Notify Manager if repeated
        if [ "$CONSECUTIVE_FAILURES" -ge 3 ]; then
            mkdir -p workspace/comms/to-founder
            cat > "workspace/comms/to-founder/$(date '+%Y%m%d-%H%M%S')-rate-limit.md" <<RATELIMIT
## RATE LIMIT WARNING

**Agent:** $DISPLAY_NAME
**Consecutive rate limits:** $CONSECUTIVE_FAILURES
**Backing off:** ${BACKOFF_DELAY}s

Will resume automatically after backoff.
RATELIMIT
        fi

        # ── Dead letter queue: move tasks to failed/ after max retries ──
        if [ "$CONSECUTIVE_FAILURES" -ge "$MAX_TASK_RETRIES" ]; then
            echo "[$DISPLAY_NAME] Max retries ($MAX_TASK_RETRIES) reached. Moving tasks to failed/..."
            while IFS= read -r task_file; do
                base_name=$(basename "$task_file")
                failed_file="${FAILED_DIR}/${AGENT_NAME}-${base_name}"
                # Append error metadata to the task file before moving
                {
                    echo ""
                    echo "---"
                    echo "## FAILURE LOG"
                    echo "**Agent:** $DISPLAY_NAME"
                    echo "**Failed at:** $(date '+%Y-%m-%d %H:%M:%S')"
                    echo "**Attempts:** $CONSECUTIVE_FAILURES"
                    echo "**Error:** Rate limited / API overloaded"
                    echo "**stderr:** ${STDERR_CONTENT:0:500}"
                } >> "$task_file"
                mv "$task_file" "$failed_file"
                echo "[$DISPLAY_NAME] Moved to dead letter: $base_name"
            done < <(find "$TASK_DIR" -maxdepth 1 -type f ! -name '.gitkeep' 2>/dev/null)
            # Notify Manager
            mkdir -p workspace/comms/to-founder
            cat > "workspace/comms/to-founder/$(date '+%Y%m%d-%H%M%S')-task-failed.md" <<TASKFAIL
## TASK FAILURE

**Agent:** $DISPLAY_NAME
**Status:** Tasks moved to dead letter queue after $CONSECUTIVE_FAILURES failed attempts.
**Reason:** Repeated rate limits / API errors.
**Location:** workspace/tasks/failed/

To retry: move the task file back to workspace/tasks/${AGENT_NAME}/
TASKFAIL
            CONSECUTIVE_FAILURES=0
        fi

        sleep "$BACKOFF_DELAY"
        continue
    elif [ "$CLAUDE_EXIT" -ne 0 ] && [ -n "$STDERR_CONTENT" ]; then
        # Non-rate-limit error — log but don't backoff as aggressively
        CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
        BACKOFF_DELAY=$((10 * CONSECUTIVE_FAILURES))
        if [ "$BACKOFF_DELAY" -gt 120 ]; then
            BACKOFF_DELAY=120
        fi
        echo "[$DISPLAY_NAME] Claude exited with code $CLAUDE_EXIT. Waiting ${BACKOFF_DELAY}s..."
        echo "[$DISPLAY_NAME] stderr: ${STDERR_CONTENT:0:200}"

        # Dead letter queue for non-rate-limit errors too
        if [ "$CONSECUTIVE_FAILURES" -ge "$MAX_TASK_RETRIES" ]; then
            echo "[$DISPLAY_NAME] Max retries reached. Moving tasks to failed/..."
            while IFS= read -r task_file; do
                base_name=$(basename "$task_file")
                {
                    echo ""
                    echo "---"
                    echo "## FAILURE LOG"
                    echo "**Agent:** $DISPLAY_NAME"
                    echo "**Failed at:** $(date '+%Y-%m-%d %H:%M:%S')"
                    echo "**Attempts:** $CONSECUTIVE_FAILURES"
                    echo "**Exit code:** $CLAUDE_EXIT"
                    echo "**stderr:** ${STDERR_CONTENT:0:500}"
                } >> "$task_file"
                mv "$task_file" "${FAILED_DIR}/${AGENT_NAME}-${base_name}"
            done < <(find "$TASK_DIR" -maxdepth 1 -type f ! -name '.gitkeep' 2>/dev/null)
            CONSECUTIVE_FAILURES=0
        fi

        sleep "$BACKOFF_DELAY"
        continue
    else
        # Success — reset failure counter
        CONSECUTIVE_FAILURES=0
        BACKOFF_DELAY=0
    fi

    echo "[$DISPLAY_NAME] Session #${SESSION_COUNTER} done. Next check in 15s..."
    sleep 15

done

echo "[$DISPLAY_NAME] Loop ended after $SESSION_COUNTER sessions."
