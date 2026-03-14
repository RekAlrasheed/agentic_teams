#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Navaia AI Workforce — 24/7 Auto-Restart Loop (PM only)
#
# DEPRECATED: Use scripts/start-all.sh or scripts/supervisor.sh instead.
# Those run ALL agents with auto-restart, health checks, and rate limit backoff.
#
# This script only runs the PM agent. If you need all agents:
#   bash scripts/start-all.sh --supervisor
#
# Legacy usage (PM only):
#   tmux new -s navaia
#   bash scripts/loop.sh
#
# To stop:
#   - Send /stop via Telegram
#   - Or: touch workspace/comms/STOP
#   - Or: Ctrl+C
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

# ── Configuration ────────────────────────────────────────────────────────────

MAX_RESTARTS=${MAX_RESTARTS:-200}
RESTART_DELAY=${RESTART_DELAY:-30}
SESSION_COUNTER=0
STOP_FILE="workspace/comms/STOP"

# ── Load Environment ─────────────────────────────────────────────────────────

if [ ! -f .env ]; then
    echo "❌ .env not found. Run 'bash scripts/setup.sh' first."
    exit 1
fi

set -a
source .env
set +a

# File-dispatch mode — agents run in separate terminals, no Agent Teams
unset CLAUDECODE

# ── Start Telegram Bridge (once) ────────────────────────────────────────────

BRIDGE_PID=""

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_FOUNDER_CHAT_ID:-}" ]; then
    echo "📱 Starting Telegram bridge..."
    python3 tools/telegram_bridge.py &
    BRIDGE_PID=$!
    echo "  ✅ Bridge started (PID: $BRIDGE_PID)"
else
    echo "  ⏭️  Telegram bridge skipped (credentials not set)"
fi

# ── Cleanup ──────────────────────────────────────────────────────────────────

cleanup() {
    echo ""
    echo "🧹 Shutting down Navaia AI Workforce..."
    if [ -n "$BRIDGE_PID" ] && kill -0 "$BRIDGE_PID" 2>/dev/null; then
        kill "$BRIDGE_PID" 2>/dev/null || true
        wait "$BRIDGE_PID" 2>/dev/null || true
        echo "  ✅ Telegram bridge stopped"
    fi
    # Remove STOP file if it exists
    rm -f "$STOP_FILE"
    echo "  Total sessions: $SESSION_COUNTER"
    echo "Goodbye."
    exit 0
}

trap cleanup EXIT INT TERM

# ── Main Loop ────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  NAVAIA AI WORKFORCE — 24/7 MODE"
echo "  Max restarts: $MAX_RESTARTS"
echo "  Restart delay: ${RESTART_DELAY}s"
echo "═══════════════════════════════════════════════════════"
echo ""

while [ "$SESSION_COUNTER" -lt "$MAX_RESTARTS" ]; do

    # ── Check for STOP signal ────────────────────────────────────────────────
    if [ -f "$STOP_FILE" ]; then
        echo "🛑 STOP signal detected. Halting."
        break
    fi

    # ── Check if there's any work BEFORE launching Claude (saves tokens) ────
    INBOX_COUNT=$(find workspace/tasks/inbox -type f ! -name '.gitkeep' 2>/dev/null | wc -l | tr -d ' ')
    ACTIVE_COUNT=$(find workspace/tasks/active -type f ! -name '.gitkeep' 2>/dev/null | wc -l | tr -d ' ')
    FOUNDER_MSG_COUNT=$(find workspace/comms/from-founder -type f ! -name '.gitkeep' 2>/dev/null | wc -l | tr -d ' ')

    if [ "$INBOX_COUNT" -eq 0 ] && [ "$ACTIVE_COUNT" -eq 0 ] && [ "$FOUNDER_MSG_COUNT" -eq 0 ]; then
        echo "😴 $(date '+%H:%M:%S') — No tasks. Sleeping 60s... (send a task via Telegram to wake up)"
        sleep 60
        continue
    fi

    SESSION_COUNTER=$((SESSION_COUNTER + 1))
    echo "──────────────────────────────────────────────────"
    echo "📡 Session #${SESSION_COUNTER} starting at $(date '+%Y-%m-%d %H:%M:%S')"
    echo "   Tasks: inbox=$INBOX_COUNT active=$ACTIVE_COUNT replies=$FOUNDER_MSG_COUNT"
    echo "──────────────────────────────────────────────────"

    # Build the resume prompt — uses FILE DISPATCH, not Agent Teams
    if [ "$SESSION_COUNTER" -eq 1 ]; then
        PROMPT="You are Navi, the PM Agent of Navaia's AI Workforce.

IMPORTANT: You are running in MULTI-TERMINAL mode. Each agent runs in its own terminal.
Do NOT use the Agent tool to spawn teammates. Instead, DISPATCH tasks by writing files:

To assign work to an agent, write a task file to their folder:
- Creative (Muse): workspace/tasks/creative/{timestamp}-task.md
- Technical (Arch): workspace/tasks/technical/{timestamp}-task.md
- Admin (Sage): workspace/tasks/admin/{timestamp}-task.md

Each agent loop will pick up the task automatically.

STARTUP SEQUENCE:
1. Read CLAUDE.md for your full instructions
2. Check workspace/tasks/inbox/ for new tasks from the Founder
3. Check workspace/tasks/active/ for any in-progress work
4. Check workspace/comms/from-founder/ for replies
5. If ALL folders are EMPTY — EXIT IMMEDIATELY to save tokens. Do not idle.
6. For each task: analyze it, decide which agent(s) should handle it
7. Write agent-specific task files to dispatch work
8. Send status to Founder via workspace/comms/to-founder/

NEVER ask questions in the terminal. Route questions via workspace/comms/to-founder/.
Begin your startup sequence now."
    else
        PROMPT="You are Navi, the PM Agent of Navaia's AI Workforce.
This is session #${SESSION_COUNTER}. DISPATCH tasks via files, NOT Agent tool.

RESUME SEQUENCE:
1. Check workspace/tasks/inbox/ for NEW tasks from the Founder
2. Check workspace/tasks/active/ for IN-PROGRESS work
3. Check workspace/comms/from-founder/ for replies
4. If ALL are EMPTY — EXIT IMMEDIATELY. No work = no tokens burned.
5. Dispatch tasks by writing files to workspace/tasks/{creative,technical,admin}/
6. Send a brief status update to the Founder via workspace/comms/to-founder/

NEVER ask questions in the terminal. NEVER use Agent tool to spawn teammates.
Resume operations now."
    fi

    # Launch Claude Code (PM uses sonnet by default — agents escalate per-task)
    claude --dangerously-skip-permissions --model sonnet -p "$PROMPT" || true

    # ── Post-session ─────────────────────────────────────────────────────────

    # Check for STOP signal again
    if [ -f "$STOP_FILE" ]; then
        echo "🛑 STOP signal detected after session. Halting."
        break
    fi

    echo ""
    echo "⏸️  Session #${SESSION_COUNTER} ended. Restarting in ${RESTART_DELAY}s..."
    echo "   (Press Ctrl+C to stop, or 'touch $STOP_FILE' to halt)"
    sleep "$RESTART_DELAY"

done

if [ "$SESSION_COUNTER" -ge "$MAX_RESTARTS" ]; then
    echo ""
    echo "⚠️  Maximum restart count ($MAX_RESTARTS) reached. Stopping."
    echo "   Increase MAX_RESTARTS env var to continue."
fi
