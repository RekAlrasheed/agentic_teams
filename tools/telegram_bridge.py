#!/usr/bin/env python3
"""
Navaia Crew Bot — Smart Telegram Bridge

A conversational Telegram bot that serves as the Founder's control panel
for the AI Workforce. Classifies messages, answers questions intelligently,
sends proactive updates when work is done, and syncs everything with Trello.
"""

import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ── Setup ────────────────────────────────────────────────────────────────────

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FOUNDER_CHAT_ID = os.getenv("TELEGRAM_FOUNDER_CHAT_ID")
TRELLO_KEY = os.getenv("TRELLO_KEY", "")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN", "")
TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID", "")

if not BOT_TOKEN or not FOUNDER_CHAT_ID:
    print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_FOUNDER_CHAT_ID must be set in .env")
    sys.exit(1)

FOUNDER_CHAT_ID = int(FOUNDER_CHAT_ID)

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = REPO_ROOT / "workspace" / "tasks" / "inbox"
ACTIVE_DIR = REPO_ROOT / "workspace" / "tasks" / "active"
DONE_DIR = REPO_ROOT / "workspace" / "tasks" / "done"
REJECTED_DIR = REPO_ROOT / "workspace" / "tasks" / "rejected"
BLOCKED_DIR = REPO_ROOT / "workspace" / "tasks" / "blocked"
FROM_FOUNDER_DIR = REPO_ROOT / "workspace" / "comms" / "from-founder"
TO_FOUNDER_DIR = REPO_ROOT / "workspace" / "comms" / "to-founder"
OUTPUTS_DIR = REPO_ROOT / "workspace" / "outputs"
STOP_FILE = REPO_ROOT / "workspace" / "comms" / "STOP"

for d in [INBOX_DIR, ACTIVE_DIR, DONE_DIR, REJECTED_DIR, BLOCKED_DIR, FROM_FOUNDER_DIR, TO_FOUNDER_DIR]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s [NavaiBot] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4000


# ── Trello API ───────────────────────────────────────────────────────────────

def trello_enabled() -> bool:
    return bool(TRELLO_KEY and TRELLO_TOKEN and TRELLO_BOARD_ID)


def trello_api(method: str, endpoint: str, params: dict = None) -> dict:
    """Call Trello REST API."""
    if not trello_enabled():
        return {}
    base = "https://api.trello.com/1"
    auth = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    all_params = {**auth, **(params or {})}
    query = urllib.parse.urlencode(all_params)
    url = f"{base}/{endpoint}?{query}"
    try:
        import urllib.request
        req = urllib.request.Request(url, method=method.upper())
        if method.upper() == "POST":
            req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.error(f"Trello API error: {e}")
        return {}


def trello_get_list_id(list_name: str) -> str:
    """Get Trello list ID by name."""
    lists = trello_api("GET", f"boards/{TRELLO_BOARD_ID}/lists")
    if isinstance(lists, list):
        for l in lists:
            if l["name"] == list_name:
                return l["id"]
    return ""


def trello_get_label_id(label_name: str) -> str:
    """Get Trello label ID by name."""
    labels = trello_api("GET", f"boards/{TRELLO_BOARD_ID}/labels")
    if isinstance(labels, list):
        for l in labels:
            if l.get("name") == label_name:
                return l["id"]
    return ""


def trello_create_card(list_name: str, title: str, desc: str = "", label_name: str = "") -> str:
    """Create a Trello card. Returns card ID."""
    list_id = trello_get_list_id(list_name)
    if not list_id:
        return ""
    params = {"idList": list_id, "name": title, "desc": desc}
    if label_name:
        label_id = trello_get_label_id(label_name)
        if label_id:
            params["idLabels"] = label_id
    result = trello_api("POST", "cards", params)
    card_id = result.get("id", "")
    if card_id:
        logger.info(f"Trello card created: {title} [{card_id[:8]}]")
    return card_id


def trello_move_card(card_id: str, list_name: str):
    """Move a Trello card to a different list."""
    list_id = trello_get_list_id(list_name)
    if list_id and card_id:
        trello_api("PUT", f"cards/{card_id}", {"idList": list_id})
        logger.info(f"Trello card {card_id[:8]} moved to {list_name}")


def trello_comment(card_id: str, comment: str):
    """Add a comment to a Trello card."""
    if card_id:
        trello_api("POST", f"cards/{card_id}/actions/comments", {"text": comment})


def trello_get_board_summary() -> str:
    """Get a summary of all cards on the board."""
    lists = trello_api("GET", f"boards/{TRELLO_BOARD_ID}/lists")
    if not isinstance(lists, list):
        return "Could not fetch Trello board."

    icons = {
        "Inbox": "📥", "Planning": "📋", "To Do": "📝",
        "In Progress": "🔄", "Review": "🔍", "Done": "✅",
        "Blocked": "🚫", "Rejected": "❌"
    }

    summary = ""
    for lst in lists:
        cards = trello_api("GET", f"lists/{lst['id']}/cards")
        count = len(cards) if isinstance(cards, list) else 0
        icon = icons.get(lst["name"], "📌")
        summary += f"{icon} *{lst['name']}:* {count}"
        if isinstance(cards, list) and cards:
            for c in cards[:3]:
                summary += f"\n   → {c['name']}"
            if count > 3:
                summary += f"\n   _... +{count - 3} more_"
        summary += "\n"

    return summary


# ── Authorization ────────────────────────────────────────────────────────────

def is_authorized(chat_id: int) -> bool:
    return chat_id == FOUNDER_CHAT_ID


# ── Helpers ──────────────────────────────────────────────────────────────────

def count_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return len([f for f in directory.iterdir() if f.is_file() and f.name != ".gitkeep"])


def get_task_summaries(directory: Path, limit: int = 5) -> list[str]:
    if not directory.exists():
        return []
    files = [f for f in directory.iterdir() if f.is_file() and f.name != ".gitkeep"]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    summaries = []
    for f in files[:limit]:
        try:
            content = f.read_text(encoding="utf-8")
            lines = [l for l in content.strip().split("\n") if not l.startswith("##") and not l.startswith("**") and l.strip()]
            if lines:
                summaries.append(f"• {lines[0][:100]}")
        except Exception:
            summaries.append(f"• {f.name}")
    return summaries


def is_claude_running() -> bool:
    try:
        result = subprocess.run(["pgrep", "-f", "claude"], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


def get_output_files(limit: int = 10) -> list[dict]:
    """Get recent output files across all agents."""
    files = []
    if not OUTPUTS_DIR.exists():
        return files
    for f in OUTPUTS_DIR.rglob("*"):
        if f.is_file() and f.name != ".gitkeep":
            rel = f.relative_to(OUTPUTS_DIR)
            agent = rel.parts[0] if rel.parts else "unknown"
            files.append({
                "path": str(rel),
                "agent": agent,
                "name": f.name,
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
                "full_path": f,
            })
    files.sort(key=lambda x: x["modified"], reverse=True)
    return files[:limit]


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


AGENT_DISPLAY = {
    "creative": "🎨 Muse",
    "technical": "⚙️ Arch",
    "admin": "📊 Sage",
    "pm": "🧠 Navi",
}


# ── Message Classification ───────────────────────────────────────────────────

QUESTION_PATTERNS = [
    r"^(what|how|why|when|where|who|which|is|are|was|were|do|does|did|can|could|would|will|should|has|have)\b",
    r"\?$",
    r"^(status|update|progress|report|show|tell|give|list|check)\b",
    r"^(what'?s|how'?s|where'?s|who'?s)\b",
    r"(any updates|what happened|how.+going|is it done|are they done|is.+running|is.+working)",
]

REPLY_PATTERNS = [
    r"^(yes|no|ok|okay|approved?|reject|cancel|go ahead|proceed|confirmed?|deny|denied)\b",
    r"^(change|modify|update|edit|revise)\b.*\bto\b",
    r"^(option|choice|pick|choose)\s*[a-d1-4]",
    r"^(looks good|lgtm|ship it|do it|go for it|sounds good|perfect|great)\b",
    r"^(stop|pause|wait|hold)\b",
]

TASK_PATTERNS = [
    r"^(create|build|write|make|design|develop|deploy|fix|add|remove|delete|update|set up|configure|send|draft|prepare|generate|analyze|research|do|run|execute|launch|schedule|plan|review|audit|check|compare|evaluate|summarize)\b",
    r"^(i need|i want|please|pls|can you|could you|we need|let'?s)\b.{15,}",
    r"^(new task|task:)\b",
]

GREETING_PATTERNS = [
    r"^(hi|hello|hey|hola|salam|marhaba|السلام|مرحبا|اهلا|صباح|مساء)",
]


def classify_message(text: str) -> str:
    text_lower = text.strip().lower()

    for pattern in GREETING_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "greeting"

    for pattern in REPLY_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "reply"

    for pattern in TASK_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "task"

    for pattern in QUESTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "question"

    if len(text_lower.split()) > 10:
        return "task"

    return "task"


# ── Smart Responses ──────────────────────────────────────────────────────────

def build_greeting_response() -> str:
    """Friendly greeting with current status."""
    claude_running = is_claude_running()
    inbox = count_files(INBOX_DIR)
    active = count_files(ACTIVE_DIR)
    done = count_files(DONE_DIR)

    msg = "👋 Hey! I'm the Navaia Crew bot.\n\n"

    if claude_running:
        msg += "🟢 The team is *online and working*.\n"
    else:
        if inbox > 0 or active > 0:
            msg += "🟡 The team is *between sessions* — will resume shortly.\n"
        else:
            msg += "😴 The team is *idle* — no tasks in queue.\n"

    if active > 0:
        msg += f"\n🔄 *{active} task(s) in progress*\n"
        for s in get_task_summaries(ACTIVE_DIR, 3):
            msg += f"  {s}\n"

    if inbox > 0:
        msg += f"\n📥 *{inbox} task(s) waiting*\n"

    if done > 0:
        msg += f"\n✅ *{done} task(s) completed*\n"

    msg += "\n💬 Just tell me what you need — I'll route it to the right agent."
    return msg


def build_status_response() -> str:
    """Comprehensive status with Trello integration."""
    claude_running = is_claude_running()
    inbox = count_files(INBOX_DIR)
    active = count_files(ACTIVE_DIR)
    done = count_files(DONE_DIR)
    blocked = count_files(BLOCKED_DIR)

    msg = "📊 *Navaia Crew — Status Report*\n\n"
    msg += f"🤖 Agents: {'🟢 Online' if claude_running else '🔴 Offline (will auto-start when tasks arrive)'}\n\n"

    # Task counts
    msg += "*Task Pipeline:*\n"
    msg += f"  📥 Inbox: {inbox}\n"
    msg += f"  🔄 Active: {active}\n"
    msg += f"  ✅ Done: {done}\n"
    if blocked > 0:
        msg += f"  🚫 Blocked: {blocked}\n"

    # Recent outputs
    outputs = get_output_files(5)
    if outputs:
        msg += "\n*Recent Deliverables:*\n"
        for o in outputs:
            agent = AGENT_DISPLAY.get(o["agent"], o["agent"])
            msg += f"  📄 {agent}: `{o['name']}` ({format_size(o['size'])})\n"

    # Trello board summary
    if trello_enabled():
        msg += "\n*Trello Board:*\n"
        msg += trello_get_board_summary()

    return msg


def build_question_response(text: str) -> str:
    """Smart contextual answers to questions."""
    text_lower = text.strip().lower()

    # Status / running / working
    if any(kw in text_lower for kw in ["doing", "working", "running", "active", "alive", "started", "online"]):
        claude_running = is_claude_running()
        active = count_files(ACTIVE_DIR)
        inbox = count_files(INBOX_DIR)
        if claude_running:
            msg = "🟢 *Yes, the team is active right now.*\n"
            if active > 0:
                msg += f"\nWorking on {active} task(s):\n"
                for s in get_task_summaries(ACTIVE_DIR, 3):
                    msg += f"  {s}\n"
            else:
                msg += "Processing the queue."
        else:
            msg = "💤 *The team is between sessions.*\n"
            if inbox > 0:
                msg += f"\n{inbox} task(s) in the inbox — they'll pick them up on the next cycle (checks every 60s)."
            else:
                msg += "\nNo tasks in queue. Send me something and they'll get on it."
        return msg

    # Progress / done / completed / results / updates
    if any(kw in text_lower for kw in ["did it do", "done so far", "progress", "what happened", "been done",
                                        "completed", "finished", "results", "updates", "update", "deliverables",
                                        "output", "is it done"]):
        done = count_files(DONE_DIR)
        outputs = get_output_files(5)

        if done > 0 or outputs:
            msg = f"✅ *{done} task(s) completed*\n"
            if get_task_summaries(DONE_DIR, 5):
                msg += "\n*Tasks done:*\n"
                for s in get_task_summaries(DONE_DIR, 5):
                    msg += f"  {s}\n"
            if outputs:
                msg += "\n*Deliverables produced:*\n"
                for o in outputs:
                    agent = AGENT_DISPLAY.get(o["agent"], o["agent"])
                    msg += f"  📄 {agent}: `{o['name']}` ({format_size(o['size'])})\n"

                    # For text files, show a one-line preview
                    ext = o["full_path"].suffix.lower()
                    if ext in [".md", ".txt", ".csv"]:
                        try:
                            first_line = ""
                            for line in o["full_path"].read_text(encoding="utf-8").split("\n"):
                                line = line.strip()
                                if line and not line.startswith("#") and not line.startswith("**") and not line.startswith("---") and not line.startswith(">"):
                                    first_line = line[:80]
                                    break
                            if first_line:
                                msg += f"     _{first_line}_\n"
                        except Exception:
                            pass
            return msg
        else:
            active = count_files(ACTIVE_DIR)
            inbox = count_files(INBOX_DIR)
            return f"No completed tasks yet.\n\n📥 Inbox: {inbox}\n🔄 Active: {active}"

    # Pending / queue / inbox
    if any(kw in text_lower for kw in ["pending", "queue", "inbox", "waiting", "backlog", "next"]):
        inbox = count_files(INBOX_DIR)
        if inbox > 0:
            msg = f"📥 *{inbox} task(s) waiting:*\n\n"
            for s in get_task_summaries(INBOX_DIR, 5):
                msg += f"  {s}\n"
            return msg
        return "📥 Queue is empty. Send me a task!"

    # Trello / board
    if any(kw in text_lower for kw in ["trello", "board", "cards", "kanban"]):
        if trello_enabled():
            return "📋 *Trello Board:*\n\n" + trello_get_board_summary()
        return "Trello is not configured. Add TRELLO_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID to .env."

    # Who / team / agents
    if any(kw in text_lower for kw in ["who", "team", "agents", "crew"]):
        msg = "🤖 *The Navaia Crew:*\n\n"
        msg += "🧠 *Navi* — PM & Team Lead (coordinates everything)\n"
        msg += "🎨 *Muse* — Creative & Marketing (content, emails, social)\n"
        msg += "⚙️ *Arch* — Technical (code, deploy, infrastructure)\n"
        msg += "📊 *Sage* — Admin & Finance (docs, proposals, research)\n"
        msg += "\nI route your tasks to the right agent automatically."
        return msg

    # Fallback — full status
    return build_status_response()


# ── Handlers ─────────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Smart message handler — classifies and routes."""
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    text = update.message.text
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    msg_type = classify_message(text)

    logger.info(f"[{msg_type}] {text[:60]}...")

    if msg_type == "greeting":
        await update.message.reply_text(build_greeting_response(), parse_mode="Markdown")

    elif msg_type == "question":
        response = build_question_response(text)
        await update.message.reply_text(response, parse_mode="Markdown")

    elif msg_type == "reply":
        # Save reply for agents
        filename = f"{timestamp}-reply.md"
        filepath = FROM_FOUNDER_DIR / filename
        content = f"## FOUNDER REPLY\n**Time:** {datetime.now(timezone.utc).isoformat()}\n**Source:** Telegram\n\n{text}\n"
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"Reply saved: {filepath}")
        await update.message.reply_text("👍 Got it — passing to Navi.")

    else:
        # Save as task
        filename = f"{timestamp}-task.md"
        filepath = INBOX_DIR / filename
        content = f"## NEW TASK FROM FOUNDER\n**Time:** {datetime.now(timezone.utc).isoformat()}\n**Source:** Telegram\n\n{text}\n"
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"Task saved: {filepath}")

        # Create Trello card
        trello_card_id = ""
        if trello_enabled():
            # Determine which agent label to assign
            text_lower = text.lower()
            label = "PM"
            if any(kw in text_lower for kw in ["write", "content", "email", "marketing", "social", "blog", "linkedin", "campaign", "copy", "brand"]):
                label = "Creative"
            elif any(kw in text_lower for kw in ["code", "deploy", "fix", "bug", "api", "server", "database", "github", "aws", "build", "infrastructure"]):
                label = "Technical"
            elif any(kw in text_lower for kw in ["proposal", "contract", "invoice", "budget", "research", "analysis", "finance", "compliance", "hr", "document"]):
                label = "Admin"

            # Truncate title for Trello
            card_title = text[:100] + ("..." if len(text) > 100 else "")
            trello_card_id = trello_create_card("Inbox", card_title, text, label)

        # Smart acknowledgment
        inbox_count = count_files(INBOX_DIR)
        claude_running = is_claude_running()

        ack = "✅ *Task received!*\n\n"
        ack += f"📝 _{text[:100]}_\n\n"

        if trello_card_id:
            ack += f"📋 Added to Trello → Inbox\n"

        if claude_running:
            ack += "🟢 Team is online — Navi will assign it shortly."
        elif inbox_count <= 1:
            ack += "⏳ Team will pick this up on the next cycle (~60s)."
        else:
            ack += f"⏳ #{inbox_count} in queue. Team processes on next cycle."

        await update.message.reply_text(ack, parse_mode="Markdown")


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    await update.message.reply_text(build_status_response(), parse_mode="Markdown")


async def handle_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    STOP_FILE.write_text(f"STOP requested at {datetime.now(timezone.utc).isoformat()}", encoding="utf-8")
    await update.message.reply_text(
        "🛑 *Crew shutting down.*\n\nCurrent tasks will finish, then the team goes offline.\n"
        "To restart: `bash scripts/loop.sh`",
        parse_mode="Markdown",
    )


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    msg = (
        "🤖 *Navaia Crew Bot*\n\n"
        "*Just talk to me naturally:*\n"
        "📝 Send a task → _\"Write 3 cold outreach emails for SaaS founders\"_\n"
        "❓ Ask anything → _\"What's the progress?\"_ / _\"Is it running?\"_\n"
        "👍 Approve a plan → _\"Go ahead\"_ / _\"Approved\"_\n"
        "🔄 Get updates → _\"Any updates?\"_ / _\"What did the team do?\"_\n\n"
        "*Commands:*\n"
        "/status — Full dashboard with Trello\n"
        "/board — Trello board summary\n"
        "/outputs — Recent deliverables\n"
        "/clear — Clear inbox\n"
        "/stop — Shut down the crew\n"
        "/help — This message"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_board(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if trello_enabled():
        msg = "📋 *Trello — Navaia Crew Board*\n\n" + trello_get_board_summary()
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text("Trello not configured.")


async def handle_outputs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    outputs = get_output_files(10)
    if outputs:
        msg = "📦 *Recent Deliverables*\n\n"
        for o in outputs:
            agent = AGENT_DISPLAY.get(o["agent"], o["agent"])
            msg += f"📄 {agent}: `{o['name']}` ({format_size(o['size'])})\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text("No outputs yet. Send a task to get started!")


async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    count = 0
    for f in INBOX_DIR.iterdir():
        if f.is_file() and f.name != ".gitkeep":
            f.unlink()
            count += 1
    await update.message.reply_text(f"🗑️ Cleared {count} task(s) from inbox.")


# ── File Watchers ────────────────────────────────────────────────────────────

class OutboxWatcher(FileSystemEventHandler):
    """Sends agent messages to Founder via Telegram."""

    def __init__(self, application: Application):
        self.application = application
        self._sent: set[str] = set()

    def on_created(self, event):
        if event.is_directory or not event.src_path.endswith(".md"):
            return
        filepath = Path(event.src_path)
        if filepath.name in self._sent:
            return
        self._sent.add(filepath.name)
        try:
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(self._send(filepath), loop)
        except RuntimeError:
            pass

    async def _send(self, filepath: Path):
        try:
            await asyncio.sleep(1)
            content = filepath.read_text(encoding="utf-8")
            if len(content) > TELEGRAM_MAX_LENGTH:
                content = content[:TELEGRAM_MAX_LENGTH] + "\n\n⚠️ _Truncated. Full file saved locally._"
            await self.application.bot.send_message(
                chat_id=FOUNDER_CHAT_ID, text=content, parse_mode="Markdown"
            )
            logger.info(f"Sent to Founder: {filepath.name}")
        except Exception as e:
            logger.error(f"Failed to send {filepath.name}: {e}")


class OutputWatcher(FileSystemEventHandler):
    """Notifies Founder when agents produce output files."""

    def __init__(self, application: Application):
        self.application = application
        self._notified: set[str] = set()

    def on_created(self, event):
        if event.is_directory:
            return
        filepath = Path(event.src_path)
        if filepath.name == ".gitkeep" or str(filepath) in self._notified:
            return
        self._notified.add(str(filepath))
        try:
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(self._notify(filepath), loop)
        except RuntimeError:
            pass

    async def _notify(self, filepath: Path):
        try:
            await asyncio.sleep(2)  # Wait for file to be fully written

            rel = filepath.relative_to(OUTPUTS_DIR)
            agent_folder = rel.parts[0] if rel.parts else "unknown"
            agent = AGENT_DISPLAY.get(agent_folder, agent_folder.title())
            size = format_size(filepath.stat().st_size)

            msg = f"📄 *New deliverable from {agent}*\n\n"
            msg += f"📁 `{rel}`\n"
            msg += f"📏 {size}\n"

            # Preview for text files
            ext = filepath.suffix.lower()
            if ext in [".md", ".txt", ".csv", ".html", ".json"]:
                try:
                    content = filepath.read_text(encoding="utf-8")
                    # Get meaningful preview (skip headers/metadata)
                    preview_lines = []
                    for line in content.split("\n"):
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#") and not stripped.startswith("**") and not stripped.startswith("---") and not stripped.startswith(">"):
                            preview_lines.append(stripped)
                            if len(preview_lines) >= 5:
                                break
                    if preview_lines:
                        preview = "\n".join(preview_lines)
                        if len(preview) > 400:
                            preview = preview[:400] + "..."
                        msg += f"\n_Preview:_\n{preview}"
                except Exception:
                    pass

            if len(msg) > TELEGRAM_MAX_LENGTH:
                msg = msg[:TELEGRAM_MAX_LENGTH - 50] + "\n\n⚠️ _Preview truncated._"

            await self.application.bot.send_message(
                chat_id=FOUNDER_CHAT_ID, text=msg, parse_mode="Markdown"
            )
            logger.info(f"Notified: new output {rel}")
        except Exception as e:
            logger.error(f"Output notification failed: {e}")


class TaskDoneWatcher(FileSystemEventHandler):
    """Notifies Founder when tasks are completed — with details."""

    def __init__(self, application: Application):
        self.application = application
        self._notified: set[str] = set()

    def on_created(self, event):
        if event.is_directory:
            return
        filepath = Path(event.src_path)
        if filepath.name == ".gitkeep" or filepath.name in self._notified:
            return
        self._notified.add(filepath.name)
        try:
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(self._notify(filepath), loop)
        except RuntimeError:
            pass

    async def _notify(self, filepath: Path):
        try:
            await asyncio.sleep(1)
            content = filepath.read_text(encoding="utf-8")

            # Extract original task text
            lines = content.strip().split("\n")
            task_lines = [l for l in lines if not l.startswith("##") and not l.startswith("**") and l.strip()]
            task_text = task_lines[0][:150] if task_lines else filepath.name

            msg = f"✅ *Task Completed!*\n\n"
            msg += f"📝 _{task_text}_\n\n"

            # Check for related output files (created in the last 5 minutes)
            import time
            recent_outputs = []
            cutoff = time.time() - 300  # 5 minutes
            for o in get_output_files(10):
                if o["modified"] > cutoff:
                    agent = AGENT_DISPLAY.get(o["agent"], o["agent"])
                    recent_outputs.append(f"  📄 {agent}: `{o['name']}` ({format_size(o['size'])})")

            if recent_outputs:
                msg += "*Deliverables:*\n" + "\n".join(recent_outputs) + "\n"

            # Update Trello — move card to Done if possible
            if trello_enabled():
                trello_done_note = ""
                # Try to find matching card in In Progress or Review
                for list_name in ["In Progress", "Review", "To Do", "Inbox"]:
                    list_id = trello_get_list_id(list_name)
                    if not list_id:
                        continue
                    cards = trello_api("GET", f"lists/{list_id}/cards")
                    if isinstance(cards, list):
                        for card in cards:
                            # Fuzzy match: check if task text overlaps with card name
                            if task_text[:30].lower() in card["name"].lower() or card["name"].lower() in task_text.lower():
                                trello_move_card(card["id"], "Done")
                                trello_comment(card["id"], f"✅ Completed. Output saved to workspace/outputs/")
                                trello_done_note = f"\n📋 Trello card moved to Done"
                                break
                    if trello_done_note:
                        break
                msg += trello_done_note

            remaining = count_files(INBOX_DIR) + count_files(ACTIVE_DIR)
            if remaining > 0:
                msg += f"\n\n⏳ {remaining} task(s) remaining in pipeline."
            else:
                msg += "\n\n🎉 All caught up! No more tasks in queue."

            await self.application.bot.send_message(
                chat_id=FOUNDER_CHAT_ID, text=msg, parse_mode="Markdown"
            )
            logger.info(f"Notified: task done — {filepath.name}")
        except Exception as e:
            logger.error(f"Task done notification failed: {e}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    logger.info("Starting Navaia Crew Bot (Smart Mode)...")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("stop", handle_stop))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("start", handle_help))
    app.add_handler(CommandHandler("board", handle_board))
    app.add_handler(CommandHandler("outputs", handle_outputs))
    app.add_handler(CommandHandler("clear", handle_clear))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # File watchers
    observer = Observer()

    outbox_watcher = OutboxWatcher(app)
    observer.schedule(outbox_watcher, str(TO_FOUNDER_DIR), recursive=False)

    output_watcher = OutputWatcher(app)
    observer.schedule(output_watcher, str(OUTPUTS_DIR), recursive=True)

    done_watcher = TaskDoneWatcher(app)
    observer.schedule(done_watcher, str(DONE_DIR), recursive=False)

    observer.start()
    logger.info("File watchers active (outbox, outputs, done)")

    def shutdown(signum, frame):
        logger.info("Shutting down...")
        observer.stop()
        observer.join()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Navaia Crew Bot is live. Waiting for messages...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
