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

STARTUP_PROMPT="You are Navi, the PM Agent of Navaia's AI Workforce.

STARTUP SEQUENCE:
1. Read CLAUDE.md for your full instructions and team configuration
2. Check workspace/tasks/inbox/ for new tasks from the Founder
3. Check workspace/tasks/active/ for any in-progress work
4. Spawn your teammates (Muse, Arch, Sage) as defined in CLAUDE.md
5. Send a status update to the Founder via workspace/comms/to-founder/

You are running in autonomous mode. NEVER ask questions in the terminal.
Route all questions to the Founder via Telegram (workspace/comms/to-founder/).
Update Trello for every task state change.

Begin your startup sequence now."

claude --dangerously-skip-permissions -p "$STARTUP_PROMPT"
