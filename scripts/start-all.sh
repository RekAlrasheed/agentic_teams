#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Navaia AI Workforce — One-Command Startup
#
# Starts everything in a tmux session with separate windows for easy monitoring.
#
# Usage:
#   bash scripts/start-all.sh          # Start all agents + bridge + dashboard
#   bash scripts/start-all.sh --supervisor  # Use supervisor mode (auto-restart)
#
# Windows created:
#   0: supervisor  — Process supervisor (or bridge if no --supervisor)
#   1: dashboard   — Web dashboard
#   2: pm          — Navi (PM Agent)
#   3: creative    — Muse (Creative Agent)
#   4: technical   — Arch (Technical Agent)
#   5: admin       — Sage (Admin Agent)
#   6: ceo         — Rex (CEO Agent)
#   7: logs        — Tail all agent logs
#
# To stop:
#   touch workspace/comms/STOP     — Graceful shutdown
#   tmux kill-session -t navaia    — Force kill everything
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SESSION_NAME="navaia"
USE_SUPERVISOR=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --supervisor|-s)
            USE_SUPERVISOR=true
            shift
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: bash scripts/start-all.sh [--supervisor]"
            exit 1
            ;;
    esac
done

# ── Preflight ─────────────────────────────────────────────────────────────────

if ! command -v tmux &> /dev/null; then
    echo "tmux is required. Install with: brew install tmux"
    exit 1
fi

if ! command -v claude &> /dev/null; then
    export PATH="$HOME/.nvm/versions/node/v22.21.1/bin:$PATH"
    if ! command -v claude &> /dev/null; then
        echo "Claude CLI not found."
        exit 1
    fi
fi

if [ ! -f "$REPO_ROOT/.env" ]; then
    echo ".env not found. Run 'bash scripts/setup.sh' first."
    exit 1
fi

# Kill existing session if running
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Existing navaia session found. Killing it..."
    tmux kill-session -t "$SESSION_NAME"
    sleep 1
fi

# Clean up stale lock files and STOP signal
rm -f /tmp/navaia-*-working
rm -f "$REPO_ROOT/workspace/comms/STOP"

# Create log directory
mkdir -p "$REPO_ROOT/workspace/logs"

echo ""
echo "================================================================"
echo "  NAVAIA AI WORKFORCE — STARTING UP"
echo "  Mode: $([ "$USE_SUPERVISOR" = true ] && echo "Supervised" || echo "Manual")"
echo "  Session: tmux attach -t $SESSION_NAME"
echo "================================================================"
echo ""

# ── Create tmux session ──────────────────────────────────────────────────────

if [ "$USE_SUPERVISOR" = true ]; then
    # Supervisor mode — one script manages everything
    tmux new-session -d -s "$SESSION_NAME" -n "supervisor" \
        "cd $REPO_ROOT && bash scripts/supervisor.sh; read -p 'Press Enter to exit...'"

    # Add a logs window
    tmux new-window -t "$SESSION_NAME" -n "logs" \
        "cd $REPO_ROOT && tail -f workspace/logs/*.log 2>/dev/null || echo 'No logs yet. Waiting...' && sleep 3600"

else
    # Manual mode — each process in its own window

    # Window 0: Telegram bridge
    tmux new-session -d -s "$SESSION_NAME" -n "bridge" \
        "cd $REPO_ROOT && source .env && python3 tools/telegram_bridge.py; read -p 'Bridge stopped. Press Enter...'"

    # Window 1: Dashboard
    tmux new-window -t "$SESSION_NAME" -n "dashboard" \
        "cd $REPO_ROOT && source .env && python3 dashboard/server.py; read -p 'Dashboard stopped. Press Enter...'"

    sleep 2  # Let bridge + dashboard start before agents

    # Window 2: PM Agent
    tmux new-window -t "$SESSION_NAME" -n "pm" \
        "cd $REPO_ROOT && bash scripts/agent-loop.sh pm; read -p 'PM stopped. Press Enter...'"

    # Window 3: Creative Agent
    tmux new-window -t "$SESSION_NAME" -n "creative" \
        "cd $REPO_ROOT && bash scripts/agent-loop.sh creative; read -p 'Creative stopped. Press Enter...'"

    # Window 4: Technical Agent
    tmux new-window -t "$SESSION_NAME" -n "technical" \
        "cd $REPO_ROOT && bash scripts/agent-loop.sh technical; read -p 'Technical stopped. Press Enter...'"

    # Window 5: Admin Agent
    tmux new-window -t "$SESSION_NAME" -n "admin" \
        "cd $REPO_ROOT && bash scripts/agent-loop.sh admin; read -p 'Admin stopped. Press Enter...'"

    # Window 6: CEO Agent
    tmux new-window -t "$SESSION_NAME" -n "ceo" \
        "cd $REPO_ROOT && bash scripts/agent-loop.sh ceo; read -p 'CEO stopped. Press Enter...'"

    # Window 7: Logs overview
    tmux new-window -t "$SESSION_NAME" -n "logs" \
        "cd $REPO_ROOT && echo 'Navaia AI Workforce Status' && echo '=========================' && while true; do clear; echo '=== Agent Status ===' && echo '' && for a in pm creative technical admin ceo; do if [ -f /tmp/navaia-\${a}-working ]; then echo \"  \$a: WORKING\"; elif pgrep -f \"agent-loop.sh \$a\" > /dev/null 2>&1; then echo \"  \$a: IDLE\"; else echo \"  \$a: OFFLINE\"; fi; done && echo '' && echo '=== Tasks ===' && echo \"  Inbox: \$(find workspace/tasks/inbox -type f ! -name .gitkeep 2>/dev/null | wc -l | tr -d ' ')\" && echo \"  Creative: \$(find workspace/tasks/creative -type f ! -name .gitkeep 2>/dev/null | wc -l | tr -d ' ')\" && echo \"  Technical: \$(find workspace/tasks/technical -type f ! -name .gitkeep 2>/dev/null | wc -l | tr -d ' ')\" && echo \"  Admin: \$(find workspace/tasks/admin -type f ! -name .gitkeep 2>/dev/null | wc -l | tr -d ' ')\" && echo \"  CEO: \$(find workspace/tasks/ceo -type f ! -name .gitkeep 2>/dev/null | wc -l | tr -d ' ')\" && echo \"  Done: \$(find workspace/tasks/done -type f ! -name .gitkeep 2>/dev/null | wc -l | tr -d ' ')\" && echo '' && echo 'Refreshing every 5s... (Ctrl+C to stop)' && sleep 5; done"

    # Select the PM window by default
    tmux select-window -t "$SESSION_NAME:pm"
fi

echo "Navaia AI Workforce started in tmux session '$SESSION_NAME'"
echo ""
echo "Commands:"
echo "  tmux attach -t $SESSION_NAME          — View agent terminals"
echo "  tmux select-window -t $SESSION_NAME:N — Switch to window N"
echo "  touch workspace/comms/STOP            — Graceful shutdown"
echo "  tmux kill-session -t $SESSION_NAME    — Force kill all"
echo ""

# Attach to the session
tmux attach -t "$SESSION_NAME"
