#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Navaia AI Workforce — Single Session Launcher
#
# Starts the Telegram bridge and launches Claude Code with the PM agent.
#
# Usage:
#   bash scripts/start.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

# ── Load Environment ─────────────────────────────────────────────────────────

if [ ! -f .env ]; then
    echo "❌ .env not found. Run 'bash scripts/setup.sh' first."
    exit 1
fi

set -a
source .env
set +a

# ── Preflight Checks ────────────────────────────────────────────────────────

echo "🔍 Preflight checks..."

READY=true

if ! command -v claude &> /dev/null; then
    echo "  ❌ Claude Code CLI not found"
    READY=false
fi

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
    echo "  ⚠️  TELEGRAM_BOT_TOKEN not set — bridge will not start"
fi

if [ -z "${TRELLO_KEY:-}" ] || [ -z "${TRELLO_TOKEN:-}" ]; then
    echo "  ⚠️  Trello credentials not set — task tracking disabled"
fi

if [ "$READY" = false ]; then
    echo ""
    echo "Fix the above issues and try again."
    exit 1
fi

echo "  ✅ All checks passed"
echo ""

# ── Start Telegram Bridge ───────────────────────────────────────────────────

BRIDGE_PID=""

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_FOUNDER_CHAT_ID:-}" ]; then
    echo "📱 Starting Telegram bridge..."
    python3 tools/telegram_bridge.py &
    BRIDGE_PID=$!
    echo "  ✅ Bridge started (PID: $BRIDGE_PID)"
else
    echo "  ⏭️  Telegram bridge skipped (credentials not set)"
fi

# ── Cleanup on Exit ─────────────────────────────────────────────────────────

cleanup() {
    echo ""
    echo "🧹 Cleaning up..."
    if [ -n "$BRIDGE_PID" ] && kill -0 "$BRIDGE_PID" 2>/dev/null; then
        kill "$BRIDGE_PID" 2>/dev/null || true
        wait "$BRIDGE_PID" 2>/dev/null || true
        echo "  ✅ Telegram bridge stopped"
    fi
    echo "Session ended."
}

trap cleanup EXIT INT TERM

# ── Launch Claude Code ───────────────────────────────────────────────────────

echo ""
echo "🚀 Launching Navaia AI Workforce..."
echo "═══════════════════════════════════════════════════════"
echo ""

export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
unset CLAUDECODE

STARTUP_PROMPT="You are Navi, the PM Agent of Navaia's AI Workforce.

STARTUP SEQUENCE:
1. Read CLAUDE.md for your full instructions and team configuration
2. Check workspace/tasks/inbox/ for new tasks from the Manager
3. Check workspace/tasks/active/ for any in-progress work
4. If ALL folders are EMPTY (no tasks, no active work, no founder messages) — EXIT IMMEDIATELY to save tokens. Do not idle.
5. Only if there IS work: spawn teammates using the CHEAPEST model that can handle each task (Haiku > Sonnet > Opus)
6. Send a status update to the Manager via workspace/comms/to-founder/

COST RULES: Always use the cheapest model possible. Haiku for simple tasks, Sonnet for content/code, Opus ONLY for complex architecture.
You are running in autonomous mode. NEVER ask questions in the terminal.
Route all questions to the Manager via Telegram (workspace/comms/to-founder/).

Begin your startup sequence now."

claude --dangerously-skip-permissions -p "$STARTUP_PROMPT"
