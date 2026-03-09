#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Navaia AI Workforce — 24/7 Auto-Restart Loop
#
# Runs Claude Code in a loop, automatically restarting when sessions end.
# Use in tmux for persistent operation:
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

export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
# Crew uses 'claude -p' = ephemeral sessions that won't show in --resume
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

    # Build the resume prompt
    if [ "$SESSION_COUNTER" -eq 1 ]; then
        PROMPT="You are Navi, the PM Agent of Navaia's AI Workforce.

STARTUP SEQUENCE:
1. Read CLAUDE.md for your full instructions and team configuration
2. Check workspace/tasks/inbox/ for new tasks from the Founder
3. Check workspace/tasks/active/ for any in-progress work
4. If ALL folders are EMPTY (no tasks, no active work, no founder messages) — EXIT IMMEDIATELY to save tokens. Do not idle.
5. Only if there IS work: spawn teammates using the CHEAPEST model that can handle each task (Haiku > Sonnet > Opus)
6. Send a status update to the Founder via workspace/comms/to-founder/

COST RULES: Always use the cheapest model possible. Haiku for simple tasks, Sonnet for content/code, Opus ONLY for complex architecture.
You are running in autonomous mode. NEVER ask questions in the terminal.
Route all questions to the Founder via Telegram (workspace/comms/to-founder/).

Begin your startup sequence now."
    else
        PROMPT="You are Navi, the PM Agent of Navaia's AI Workforce.

A previous session ended. This is normal — sessions are ephemeral.
This is session #${SESSION_COUNTER}.

RESUME SEQUENCE:
1. Check workspace/tasks/inbox/ for NEW tasks from the Founder
2. Check workspace/tasks/active/ for IN-PROGRESS work
3. Check workspace/comms/from-founder/ for replies
4. If ALL are EMPTY — EXIT IMMEDIATELY. No work = no tokens burned.
5. Only if there IS work: spawn teammates using the CHEAPEST model possible
6. Send a brief status update to the Founder

COST RULES: Haiku for simple tasks, Sonnet for content/code, Opus ONLY for complex architecture. Never use Opus when Sonnet will do.
You are running in autonomous mode. NEVER ask questions in the terminal.

Resume operations now."
    fi

    # Launch Claude Code
    claude --dangerously-skip-permissions -p "$PROMPT" || true

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
