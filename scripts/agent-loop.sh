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
    echo "Usage: bash scripts/agent-loop.sh <pm|creative|technical|admin|ceo>"
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
        EXTRA_DIRS="workspace/tasks/active workspace/comms/from-manager"
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
    ceo)
        DISPLAY_NAME="Rex (CEO)"
        TASK_DIR="workspace/tasks/ceo"
        EXTRA_DIRS=""
        MODEL="sonnet"
        AGENT_CLAUDE_MD="agents/ceo/CLAUDE.md"
        ;;
    *)
        echo "Unknown agent: $AGENT_NAME"
        echo "Valid agents: pm, creative, technical, admin, ceo"
        exit 1
        ;;
esac

# Ensure task directory exists
mkdir -p "$TASK_DIR"

STOP_FILE="workspace/comms/STOP"
FAILED_DIR="workspace/tasks/failed"
SESSION_DIR="workspace/sessions/${AGENT_NAME}"
SESSION_RESPONSES_DIR="${SESSION_DIR}/responses"
MAX_RESTARTS=${MAX_RESTARTS:-200}
MAX_TASK_RETRIES=3
SESSION_COUNTER=0
CONSECUTIVE_FAILURES=0
BACKOFF_DELAY=0

mkdir -p "$FAILED_DIR" "$SESSION_DIR" "$SESSION_RESPONSES_DIR"

# ── Generate MCP config for this agent ────────────────────────────────────────

MCP_CONFIG="/tmp/navaia-${AGENT_NAME}-mcp.json"
MCP_TEMPLATE="${REPO_ROOT}/tools/agent-mcp.json.template"
if [ -f "$MCP_TEMPLATE" ]; then
    sed "s|REPO_ROOT_PLACEHOLDER|${REPO_ROOT}|g" "$MCP_TEMPLATE" > "$MCP_CONFIG"
    echo "[$DISPLAY_NAME] MCP config generated: $MCP_CONFIG"
else
    MCP_CONFIG=""
    echo "[$DISPLAY_NAME] No MCP template found, running without MCP"
fi

# ── PM-specific: Load Health Check ────────────────────────────────────────────

if [ "$AGENT_NAME" = "pm" ]; then
    source "$SCRIPT_DIR/health-check.sh"
    HEALTH_CHECK_INTERVAL=${HEALTH_CHECK_INTERVAL:-5}  # run every N loop cycles
    HEALTH_CHECK_COUNTER=0
fi

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
    rm -f "/tmp/navaia-${AGENT_NAME}-mcp.json"
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
    # Check for waiting sessions with responses ready
    local waiting
    waiting=$(count_waiting_sessions)
    if [ "$waiting" -gt 0 ]; then
        return 0
    fi
    return 1
}

# ── Session State Management ────────────────────────────────────────────────

save_session_state() {
    local task_base="$1" session_id="$2" status="$3" signal_type="${4:-}" signal_content="${5:-}"
    local state_file="${SESSION_DIR}/${task_base}.json"
    local rounds=1
    if [ -f "$state_file" ]; then
        rounds=$(python3 -c "
import json, sys
try:
    d = json.load(open('$state_file')); print(d.get('rounds',0)+1)
except: print(1)
" 2>/dev/null || echo "1")
    fi
    python3 -c "
import json
from datetime import datetime, timezone
state = {
    'session_id': '$session_id',
    'task_base': '$task_base',
    'agent': '$AGENT_NAME',
    'status': '$status',
    'signal_type': '$signal_type',
    'signal_content': '''${signal_content//\'/\\\'}''',
    'last_updated': datetime.now(timezone.utc).isoformat(),
    'rounds': $rounds
}
with open('${SESSION_DIR}/${task_base}.json', 'w') as f:
    json.dump(state, f, indent=2)
" 2>/dev/null
}

parse_json_field() {
    # Parse a field from JSON output using python3 (jq not available)
    local json_str="$1" field="$2"
    python3 -c "
import json, sys
try:
    data = json.loads(sys.stdin.read())
    print(data.get('$field', ''))
except: print('')
" <<< "$json_str"
}

detect_signal() {
    # Detect session signals in agent output text
    local result_text="$1"
    if echo "$result_text" | grep -q '\[WAITING:QUESTION\]'; then
        echo "QUESTION"
    elif echo "$result_text" | grep -q '\[WAITING:PLAN\]'; then
        echo "PLAN"
    elif echo "$result_text" | grep -q '\[WAITING:BLOCKED\]'; then
        echo "BLOCKED"
    elif echo "$result_text" | grep -q '\[DONE\]'; then
        echo "DONE"
    else
        echo "DONE"  # default: assume done if no signal
    fi
}

count_waiting_sessions() {
    local count=0
    for sf in "${SESSION_DIR}"/*.json; do
        [ -f "$sf" ] || continue
        local status
        status=$(python3 -c "
import json
try: print(json.load(open('$sf')).get('status',''))
except: print('')
" 2>/dev/null)
        if [ "$status" = "waiting" ]; then
            local task_base
            task_base=$(python3 -c "
import json
try: print(json.load(open('$sf')).get('task_base',''))
except: print('')
" 2>/dev/null)
            local response_file="${SESSION_RESPONSES_DIR}/${task_base}.md"
            if [ -f "$response_file" ]; then
                count=$((count + 1))
            fi
        fi
    done
    echo "$count"
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
- CEO (Rex): workspace/tasks/ceo/{timestamp}-task.md

Each agent loop will pick up the task automatically.

TASK DISPATCHING:
- Write task descriptions naturally — don't over-specify commands or steps. Agents know their tools.
- If the Manager's task includes "JDI" (Just Do It), pass JDI through to the agent task. This means skip planning, execute immediately.
- If the Manager's task is complex and does NOT include JDI, the agent will propose a plan before executing.

RESPONSE ROUTING:
When the Manager replies in workspace/comms/from-manager/, check if it relates to a waiting agent session:
1. Look at workspace/sessions/{agent}/ for JSON files with status "waiting"
2. Match the Manager's reply to the correct waiting session by task name
3. Write the response to workspace/sessions/{agent}/responses/{task-base}.md
4. The agent loop will automatically resume the session with full context

STARTUP:
1. Read CLAUDE.md for full instructions
2. Check workspace/tasks/inbox/ for new tasks
3. Check workspace/tasks/active/ for in-progress work
4. Check workspace/comms/from-manager/ for replies — route to waiting sessions if applicable
5. If ALL empty — EXIT immediately
6. For each task: analyze it, decide which agent(s) should handle it
7. Write agent-specific task files to dispatch work
8. Send status to Manager via workspace/comms/to-manager/

NEVER ask questions in the terminal. Route questions via workspace/comms/to-manager/.
Begin now.
PROMPT
    else
        cat <<PROMPT
You are the ${DISPLAY_NAME} of Navaia's AI Workforce.

Read ${AGENT_CLAUDE_MD} for your full role and instructions.

YOUR TASK FOLDER: ${TASK_DIR}/
Check it for task files. Execute each task according to your skills.
Save outputs to workspace/outputs/${AGENT_NAME}/.

MCP TOOLS AVAILABLE (use instead of manual file I/O):
- filesystem: read/write workspace/ and knowledge/ files
- sqlite-tasks: query workspace/tasks.db for task status
- sqlite-tokens: query workspace/token_usage.db for budget
- trello: manage Trello cards directly
- github: manage repos, PRs, issues

TASK COMPLEXITY PROTOCOL:
Before starting any task, assess its complexity:

1. If the task contains "JDI" (Just Do It) → skip planning, execute immediately.
2. If the task is SIMPLE (clear instructions, under 5 minutes of work) → execute immediately.
3. If the task is COMPLEX (multi-step, ambiguous, architectural, risky) → DO NOT start working.
   Instead:
   a. Write a plan to workspace/comms/to-manager/ explaining:
      - What you understand the task to be
      - Your proposed approach (steps)
      - Estimated scope
      - Any risks or trade-offs
   b. Wait for approval in workspace/comms/from-manager/ before proceeding.
4. If the task is UNCLEAR (missing info, ambiguous requirements) → DO NOT guess.
   Instead:
   a. Write your questions to workspace/comms/to-manager/
   b. Wait for answers in workspace/comms/from-manager/ before proceeding.

When done:
1. Move the task file to workspace/tasks/done/
2. Write a DETAILED completion report to workspace/comms/to-manager/ that includes:
   - What you did (summary of work)
   - Key results or answers the Manager needs
   - Path to output file(s) in workspace/outputs/${AGENT_NAME}/
   - Any blockers or follow-up needed
   The Manager reads this on Telegram — make it complete and useful.

SESSION SIGNALS (IMPORTANT):
When you finish working on a task, end your response with exactly one of these signals:
- [DONE] — task is fully complete
- [WAITING:QUESTION] — you have questions for the Manager (also write them to workspace/comms/to-manager/)
- [WAITING:PLAN] — you are proposing a plan for approval (also write it to workspace/comms/to-manager/)
- [WAITING:BLOCKED] — you are blocked on something external (also write details to workspace/comms/to-manager/)

The system will preserve your full conversation context. When the Manager responds, you will be
resumed with their answer and can continue exactly where you left off.

If no tasks in your folder — EXIT immediately to save tokens.
NEVER ask questions in the terminal. All questions go through workspace/comms/to-manager/.
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

    # PM-only: Periodic health check of all agents
    if [ "$AGENT_NAME" = "pm" ]; then
        HEALTH_CHECK_COUNTER=$((HEALTH_CHECK_COUNTER + 1))
        if [ "$HEALTH_CHECK_COUNTER" -ge "$HEALTH_CHECK_INTERVAL" ]; then
            echo "[$DISPLAY_NAME] Running agent health check..."
            run_health_check
            HEALTH_CHECK_COUNTER=0
        fi
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

    # Always ensure we're on main before starting a session
    # Agents create feature branches for their work, but the repo must start from main
    CURRENT_BRANCH=$(git branch --show-current 2>/dev/null)
    if [ "$CURRENT_BRANCH" != "main" ] && [ -n "$CURRENT_BRANCH" ]; then
        echo "[$DISPLAY_NAME] WARNING: Repo on branch '$CURRENT_BRANCH', switching to main..."
        git stash -q 2>/dev/null || true
        git checkout main -q 2>/dev/null || true
    fi

    # Clean stale lock files (agent not actually running)
    if [ -f "/tmp/navaia-${AGENT_NAME}-working" ]; then
        if ! pgrep -f "claude.*--model" >/dev/null 2>&1; then
            echo "[$DISPLAY_NAME] Cleaning stale lock file"
            rm -f "/tmp/navaia-${AGENT_NAME}-working"
        fi
    fi

    # Auto-detect model and max turns from task file (set by Navi)
    SESSION_MODEL=$(detect_model)
    SESSION_MAX_TURNS=$(detect_max_turns "$SESSION_MODEL")

    # Build MCP args
    MCP_ARGS=()
    if [ -n "$MCP_CONFIG" ] && [ -f "$MCP_CONFIG" ]; then
        MCP_ARGS=(--mcp-config "$MCP_CONFIG")
    fi

    # ── Phase 1: Process NEW tasks ────────────────────────────────────────
    while IFS= read -r TASK_FILE; do
        [ -z "$TASK_FILE" ] && continue
        TASK_BASE=$(basename "$TASK_FILE" .md)

        # Skip if this task already has an active/waiting session
        if [ -f "${SESSION_DIR}/${TASK_BASE}.json" ]; then
            continue
        fi

        SESSION_COUNTER=$((SESSION_COUNTER + 1))
        echo "[$DISPLAY_NAME] Session #${SESSION_COUNTER} — NEW task: $TASK_BASE — Model: $SESSION_MODEL — Max turns: $SESSION_MAX_TURNS"

        PROMPT=$(build_prompt)
        touch "/tmp/navaia-${AGENT_NAME}-working"

        CLAUDE_EXIT=0
        CLAUDE_STDERR=$(mktemp)
        CLAUDE_STDOUT=$(mktemp)
        START_TIME=$(date +%s)
        claude -p --dangerously-skip-permissions \
            --model "$SESSION_MODEL" \
            --max-turns "$SESSION_MAX_TURNS" \
            --output-format json \
            "${MCP_ARGS[@]}" \
            "$PROMPT" >"$CLAUDE_STDOUT" 2>"$CLAUDE_STDERR" || CLAUDE_EXIT=$?
        END_TIME=$(date +%s)
        DURATION_MS=$(( (END_TIME - START_TIME) * 1000 ))
        rm -f "/tmp/navaia-${AGENT_NAME}-working"

        # Parse JSON output for session_id and result
        RAW_OUTPUT=$(cat "$CLAUDE_STDOUT" 2>/dev/null || true)
        CAPTURED_SESSION_ID=$(parse_json_field "$RAW_OUTPUT" "session_id")
        RESULT_TEXT=$(parse_json_field "$RAW_OUTPUT" "result")

        # Print human-readable result
        if [ -n "$RESULT_TEXT" ]; then
            echo "$RESULT_TEXT"
        else
            echo "$RAW_OUTPUT"
        fi

        # Token tracking
        STDOUT_SIZE=$(wc -c < "$CLAUDE_STDOUT" 2>/dev/null | tr -d ' ')
        PROMPT_SIZE=${#PROMPT}
        python3 -c "
import sys; sys.path.insert(0, 'tools')
try:
    from token_tracker import TokenTracker
    t = TokenTracker()
    t.log_call(agent='${AGENT_NAME}', model='${SESSION_MODEL}',
        input_text='x' * ${PROMPT_SIZE}, output_text='x' * ${STDOUT_SIZE:-0},
        prompt_text='x' * ${PROMPT_SIZE}, duration_ms=${DURATION_MS},
        source='agent-loop', task_type='$TASK_BASE')
    w = t.check_budget()
    if w:
        print(f'[BUDGET] {w}')
        from pathlib import Path; from datetime import datetime, timezone
        d = Path('workspace/comms/to-manager'); d.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        (d / f'{ts}-budget-alert.md').write_text(f'## TOKEN BUDGET ALERT\n\n{w}\n\n**Agent:** ${AGENT_NAME}\n**Model:** ${SESSION_MODEL}\n')
except: pass
" 2>/dev/null || true
        rm -f "$CLAUDE_STDOUT"

        # Handle errors
        STDERR_CONTENT=""
        [ -f "$CLAUDE_STDERR" ] && { STDERR_CONTENT=$(cat "$CLAUDE_STDERR" 2>/dev/null || true); rm -f "$CLAUDE_STDERR"; }

        if echo "$STDERR_CONTENT" | grep -qi "rate.limit\|429\|too many requests\|overloaded\|capacity"; then
            CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
            BACKOFF_DELAY=$((30 * (2 ** (CONSECUTIVE_FAILURES - 1))))
            [ "$BACKOFF_DELAY" -gt 300 ] && BACKOFF_DELAY=300
            echo "[$DISPLAY_NAME] Rate limited (attempt $CONSECUTIVE_FAILURES). Backing off ${BACKOFF_DELAY}s..."
            if [ "$CONSECUTIVE_FAILURES" -ge 3 ]; then
                mkdir -p workspace/comms/to-manager
                echo -e "## RATE LIMIT WARNING\n\n**Agent:** $DISPLAY_NAME\n**Attempts:** $CONSECUTIVE_FAILURES\n**Backing off:** ${BACKOFF_DELAY}s" \
                    > "workspace/comms/to-manager/$(date '+%Y%m%d-%H%M%S')-rate-limit.md"
            fi
            if [ "$CONSECUTIVE_FAILURES" -ge "$MAX_TASK_RETRIES" ]; then
                echo "[$DISPLAY_NAME] Max retries. Moving task to failed/..."
                { echo -e "\n---\n## FAILURE LOG\n**Agent:** $DISPLAY_NAME\n**Failed at:** $(date)\n**Error:** Rate limited"; } >> "$TASK_FILE"
                mv "$TASK_FILE" "${FAILED_DIR}/${AGENT_NAME}-$(basename "$TASK_FILE")"
                CONSECUTIVE_FAILURES=0
            fi
            sleep "$BACKOFF_DELAY"
            continue
        elif [ "$CLAUDE_EXIT" -ne 0 ] && [ -n "$STDERR_CONTENT" ]; then
            CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
            BACKOFF_DELAY=$((10 * CONSECUTIVE_FAILURES))
            [ "$BACKOFF_DELAY" -gt 120 ] && BACKOFF_DELAY=120
            echo "[$DISPLAY_NAME] Claude exited $CLAUDE_EXIT. stderr: ${STDERR_CONTENT:0:200}. Waiting ${BACKOFF_DELAY}s..."
            if [ "$CONSECUTIVE_FAILURES" -ge "$MAX_TASK_RETRIES" ]; then
                { echo -e "\n---\n## FAILURE LOG\n**Agent:** $DISPLAY_NAME\n**Exit:** $CLAUDE_EXIT\n**stderr:** ${STDERR_CONTENT:0:500}"; } >> "$TASK_FILE"
                mv "$TASK_FILE" "${FAILED_DIR}/${AGENT_NAME}-$(basename "$TASK_FILE")"
                CONSECUTIVE_FAILURES=0
            fi
            sleep "$BACKOFF_DELAY"
            continue
        else
            CONSECUTIVE_FAILURES=0
            BACKOFF_DELAY=0
        fi

        # Detect signal from agent output
        SIGNAL=$(detect_signal "$RESULT_TEXT")
        echo "[$DISPLAY_NAME] Signal: [$SIGNAL] | Session: ${CAPTURED_SESSION_ID:0:20}..."

        if [ "$SIGNAL" = "DONE" ] || [ -z "$CAPTURED_SESSION_ID" ]; then
            # Task complete — move to done
            mv "$TASK_FILE" "workspace/tasks/done/$(basename "$TASK_FILE")" 2>/dev/null || true
            rm -f "${SESSION_DIR}/${TASK_BASE}.json" 2>/dev/null || true
            echo "[$DISPLAY_NAME] Task complete: $TASK_BASE"
        else
            # Agent is waiting — save session state for later resume
            save_session_state "$TASK_BASE" "$CAPTURED_SESSION_ID" "waiting" "$SIGNAL" ""
            echo "[$DISPLAY_NAME] Session paused ($SIGNAL). Waiting for Manager response."
        fi

    done < <(find "$TASK_DIR" -maxdepth 1 -type f ! -name '.gitkeep' 2>/dev/null | sort)

    # ── Phase 2: Resume WAITING sessions with responses ──────────────────
    for SESSION_STATE_FILE in "${SESSION_DIR}"/*.json; do
        [ -f "$SESSION_STATE_FILE" ] || continue

        SESSION_STATUS=$(python3 -c "
import json
try: print(json.load(open('$SESSION_STATE_FILE')).get('status',''))
except: print('')
" 2>/dev/null)
        [ "$SESSION_STATUS" = "waiting" ] || continue

        WAITING_TASK_BASE=$(python3 -c "
import json
try: print(json.load(open('$SESSION_STATE_FILE')).get('task_base',''))
except: print('')
" 2>/dev/null)
        RESUME_SESSION_ID=$(python3 -c "
import json
try: print(json.load(open('$SESSION_STATE_FILE')).get('session_id',''))
except: print('')
" 2>/dev/null)

        RESPONSE_FILE="${SESSION_RESPONSES_DIR}/${WAITING_TASK_BASE}.md"
        [ -f "$RESPONSE_FILE" ] || continue

        # Response found — resume the session!
        RESPONSE_TEXT=$(cat "$RESPONSE_FILE")
        echo "[$DISPLAY_NAME] Resuming session for: $WAITING_TASK_BASE (session: ${RESUME_SESSION_ID:0:20}...)"

        save_session_state "$WAITING_TASK_BASE" "$RESUME_SESSION_ID" "working" "" ""
        touch "/tmp/navaia-${AGENT_NAME}-working"

        CLAUDE_EXIT=0
        CLAUDE_STDERR=$(mktemp)
        CLAUDE_STDOUT=$(mktemp)
        START_TIME=$(date +%s)
        claude -p --dangerously-skip-permissions \
            --model "$SESSION_MODEL" \
            --max-turns "$SESSION_MAX_TURNS" \
            --output-format json \
            --resume "$RESUME_SESSION_ID" \
            "${MCP_ARGS[@]}" \
            "Manager's response: $RESPONSE_TEXT" >"$CLAUDE_STDOUT" 2>"$CLAUDE_STDERR" || CLAUDE_EXIT=$?
        END_TIME=$(date +%s)
        rm -f "/tmp/navaia-${AGENT_NAME}-working"

        # Consume the response file
        rm -f "$RESPONSE_FILE"

        RAW_OUTPUT=$(cat "$CLAUDE_STDOUT" 2>/dev/null || true)
        RESULT_TEXT=$(parse_json_field "$RAW_OUTPUT" "result")
        NEW_SESSION_ID=$(parse_json_field "$RAW_OUTPUT" "session_id")
        [ -n "$RESULT_TEXT" ] && echo "$RESULT_TEXT" || echo "$RAW_OUTPUT"

        # Token tracking for resumed session
        STDOUT_SIZE=$(wc -c < "$CLAUDE_STDOUT" 2>/dev/null | tr -d ' ')
        RESUME_PROMPT_SIZE=${#RESPONSE_TEXT}
        DURATION_MS=$(( (END_TIME - START_TIME) * 1000 ))
        python3 -c "
import sys; sys.path.insert(0, 'tools')
try:
    from token_tracker import TokenTracker
    t = TokenTracker()
    t.log_call(agent='${AGENT_NAME}', model='${SESSION_MODEL}',
        input_text='x' * ${RESUME_PROMPT_SIZE}, output_text='x' * ${STDOUT_SIZE:-0},
        prompt_text='x' * ${RESUME_PROMPT_SIZE}, duration_ms=${DURATION_MS},
        source='agent-loop-resume', task_type='$WAITING_TASK_BASE')
except: pass
" 2>/dev/null || true
        rm -f "$CLAUDE_STDOUT" "$CLAUDE_STDERR"

        # Use new session_id if it changed, otherwise keep the original
        [ -n "$NEW_SESSION_ID" ] && RESUME_SESSION_ID="$NEW_SESSION_ID"

        # Detect signal from resumed output
        SIGNAL=$(detect_signal "$RESULT_TEXT")
        echo "[$DISPLAY_NAME] Resume signal: [$SIGNAL]"

        if [ "$SIGNAL" = "DONE" ]; then
            # Find and move the original task file to done
            ORIG_TASK="${TASK_DIR}/${WAITING_TASK_BASE}.md"
            [ -f "$ORIG_TASK" ] && mv "$ORIG_TASK" "workspace/tasks/done/$(basename "$ORIG_TASK")" 2>/dev/null || true
            rm -f "$SESSION_STATE_FILE"
            echo "[$DISPLAY_NAME] Resumed task complete: $WAITING_TASK_BASE"
        else
            # Still waiting — update session state for another round
            save_session_state "$WAITING_TASK_BASE" "$RESUME_SESSION_ID" "waiting" "$SIGNAL" ""
            echo "[$DISPLAY_NAME] Session paused again ($SIGNAL). Waiting for Manager response."
        fi
    done

    # ── Session timeout check ─────────────────────────────────────────────
    for SESSION_STATE_FILE in "${SESSION_DIR}"/*.json; do
        [ -f "$SESSION_STATE_FILE" ] || continue
        python3 -c "
import json
from datetime import datetime, timezone, timedelta
try:
    d = json.load(open('$SESSION_STATE_FILE'))
    if d.get('status') != 'waiting': exit(0)
    updated = datetime.fromisoformat(d['last_updated'])
    age_hours = (datetime.now(timezone.utc) - updated).total_seconds() / 3600
    task = d.get('task_base', 'unknown')
    if age_hours > 72:
        print(f'EXPIRE:{task}')
    elif age_hours > 24:
        print(f'REMIND:{task}')
except: pass
" 2>/dev/null | while read -r line; do
            action="${line%%:*}"
            task="${line#*:}"
            if [ "$action" = "EXPIRE" ]; then
                echo "[$DISPLAY_NAME] Session expired (>72h): $task"
                ORIG_TASK="${TASK_DIR}/${task}.md"
                [ -f "$ORIG_TASK" ] && mv "$ORIG_TASK" "${FAILED_DIR}/${AGENT_NAME}-${task}.md" 2>/dev/null || true
                rm -f "$SESSION_STATE_FILE"
            elif [ "$action" = "REMIND" ]; then
                echo "[$DISPLAY_NAME] Session waiting >24h: $task — sending reminder"
                mkdir -p workspace/comms/to-manager
                echo -e "## SESSION REMINDER\n\n**Agent:** $DISPLAY_NAME\n**Task:** $task\n**Status:** Waiting for your response for over 24 hours.\n\nPlease reply or cancel the task." \
                    > "workspace/comms/to-manager/$(date '+%Y%m%d-%H%M%S')-session-reminder.md"
            fi
        done
    done

    echo "[$DISPLAY_NAME] Session #${SESSION_COUNTER} done. Next check in 15s..."
    sleep 15

done

echo "[$DISPLAY_NAME] Loop ended after $SESSION_COUNTER sessions."
