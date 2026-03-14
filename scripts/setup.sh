#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Navaia AI Workforce — First-Time Setup
#
# Run this once after cloning the repo:
#   bash scripts/setup.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

echo "═══════════════════════════════════════════════════════"
echo "  NAVAIA AI WORKFORCE — SETUP"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── 1. Check Prerequisites ──────────────────────────────────────────────────

echo "🔍 Checking prerequisites..."

MISSING=()

if ! command -v claude &> /dev/null; then
    MISSING+=("Claude Code CLI (install: npm install -g @anthropic-ai/claude-code)")
fi

if ! command -v python3 &> /dev/null; then
    MISSING+=("Python 3.10+ (install: brew install python3)")
else
    PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
        MISSING+=("Python 3.10+ (current: $PY_VERSION)")
    else
        echo "  ✅ Python $PY_VERSION"
    fi
fi

if ! command -v tmux &> /dev/null; then
    MISSING+=("tmux (install: brew install tmux)")
else
    echo "  ✅ tmux"
fi

if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    MISSING+=("pip (install: python3 -m ensurepip)")
else
    echo "  ✅ pip"
fi

if [ ${#MISSING[@]} -gt 0 ]; then
    echo ""
    echo "❌ Missing prerequisites:"
    for item in "${MISSING[@]}"; do
        echo "   - $item"
    done
    echo ""
    echo "Install the missing tools and run this script again."
    exit 1
fi

echo ""

# ── 2. Install Python Dependencies ──────────────────────────────────────────

echo "📦 Installing Python dependencies..."
pip3 install -r tools/requirements.txt --quiet
echo "  ✅ Dependencies installed"
echo ""

# ── 3. Setup .env ────────────────────────────────────────────────────────────

if [ ! -f .env ]; then
    echo "📝 Creating .env from template..."
    cp .env.example .env
    echo "  ✅ .env created"
    echo ""
    echo "  ⚠️  IMPORTANT: Edit .env and fill in your API keys:"
    echo "     - TELEGRAM_BOT_TOKEN (from @BotFather)"
    echo "     - TELEGRAM_FOUNDER_CHAT_ID (from @userinfobot)"
    echo "     - TRELLO_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID"
    echo "     - GITHUB_TOKEN"
    echo "     - AWS credentials (optional, for Technical agent)"
    echo ""
else
    echo "  ✅ .env already exists"
fi

# ── 4. Create Workspace Directories ─────────────────────────────────────────

echo "📁 Creating workspace directories..."

DIRS=(
    "workspace/tasks/inbox"
    "workspace/tasks/active"
    "workspace/tasks/done"
    "workspace/tasks/rejected"
    "workspace/outputs/creative"
    "workspace/outputs/technical"
    "workspace/outputs/admin"
    "workspace/comms/to-manager"
    "workspace/comms/from-manager"
    "workspace/comms/inter-agent"
    "knowledge/company"
    "knowledge/sales/proposals"
    "knowledge/sales/pricing"
    "knowledge/sales/case-studies"
    "knowledge/products/baian"
    "knowledge/products/ai-workforce"
    "knowledge/finance"
    "knowledge/legal"
    "knowledge/marketing"
    "knowledge/technical"
    "knowledge/hr"
    "knowledge/templates/email-templates"
)

for dir in "${DIRS[@]}"; do
    mkdir -p "$dir"
    # Add .gitkeep to maintain directory structure in git
    if [ ! -f "$dir/.gitkeep" ]; then
        touch "$dir/.gitkeep"
    fi
done
echo "  ✅ All directories created"
echo ""

# ── 5. Setup Trello Board ───────────────────────────────────────────────────

echo "📋 Trello setup..."
if [ -n "${TRELLO_KEY:-}" ] && [ -n "${TRELLO_TOKEN:-}" ] && [ -n "${TRELLO_BOARD_ID:-}" ]; then
    source tools/trello_api.sh
    trello_setup_board
    echo "  ✅ Trello board configured"
else
    echo "  ⏭️  Skipped (TRELLO_KEY/TOKEN/BOARD_ID not set in .env)"
    echo "     Run 'source tools/trello_api.sh && trello_setup_board' after setting up .env"
fi
echo ""

# ── 6. Verify Telegram Bot ──────────────────────────────────────────────────

echo "📱 Telegram bot check..."
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    BOT_INFO=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe")
    BOT_OK=$(echo "$BOT_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('ok', False))" 2>/dev/null || echo "False")
    if [ "$BOT_OK" = "True" ]; then
        BOT_NAME=$(echo "$BOT_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['username'])" 2>/dev/null || echo "unknown")
        echo "  ✅ Bot connected: @${BOT_NAME}"
    else
        echo "  ❌ Bot token invalid. Check TELEGRAM_BOT_TOKEN in .env"
    fi
else
    echo "  ⏭️  Skipped (TELEGRAM_BOT_TOKEN not set in .env)"
fi
echo ""

# ── 7. Generate Knowledge Index ─────────────────────────────────────────────

echo "📚 Generating knowledge base index..."
python3 tools/catalog.py
echo "  ✅ knowledge/INDEX.md generated"
echo ""

# ── 8. Make scripts executable ───────────────────────────────────────────────

chmod +x scripts/start.sh scripts/loop.sh scripts/setup.sh tools/telegram_bridge.py tools/catalog.py tools/trello_api.sh
echo "  ✅ Scripts made executable"
echo ""

# ── Done ─────────────────────────────────────────────────────────────────────

echo "═══════════════════════════════════════════════════════"
echo "  ✅ SETUP COMPLETE"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo ""
echo "  1. Edit .env with your actual API keys"
echo "  2. Add company files to knowledge/"
echo "  3. Create a Telegram bot via @BotFather"
echo "  4. Create a Trello board and add the ID to .env"
echo "  5. Start the crew:"
echo ""
echo "     # Single session:"
echo "     bash scripts/start.sh"
echo ""
echo "     # 24/7 mode (in tmux):"
echo "     tmux new -s navaia"
echo "     bash scripts/loop.sh"
echo ""
echo "═══════════════════════════════════════════════════════"
