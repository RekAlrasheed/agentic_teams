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
MAX_RESTARTS=${MAX_RESTARTS:-200}
SESSION_COUNTER=0

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

STARTUP:
1. Read CLAUDE.md for full instructions
2. Check workspace/tasks/inbox/ for new tasks
3. Check workspace/tasks/active/ for in-progress work
4. Check workspace/comms/from-founder/ for replies
5. If ALL empty — EXIT immediately
6. For each task: analyze it, decide which agent(s) should handle it
7. Write agent-specific task files to dispatch work
8. Send status to Founder via workspace/comms/to-founder/

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

When done:
1. Move the task file to workspace/tasks/done/
2. Write a brief completion note to workspace/comms/to-founder/

If no tasks in your folder — EXIT immediately to save tokens.
NEVER ask questions in the terminal.
Begin now.
PROMPT
    fi
}

# ── Main Loop ────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  $DISPLAY_NAME — Agent Loop"
echo "  Task folder: $TASK_DIR"
echo "  Model: $MODEL"
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
    echo "[$DISPLAY_NAME] Session #${SESSION_COUNTER} — ${TASK_COUNT} task(s) found"

    PROMPT=$(build_prompt)

    # Launch Claude in interactive mode (TTY required for Pixel Agents to detect it)
    claude --dangerously-skip-permissions --model "$MODEL" --max-turns 15 "$PROMPT" || true

    echo "[$DISPLAY_NAME] Session #${SESSION_COUNTER} done. Next check in 15s..."
    sleep 15

done

echo "[$DISPLAY_NAME] Loop ended after $SESSION_COUNTER sessions."
