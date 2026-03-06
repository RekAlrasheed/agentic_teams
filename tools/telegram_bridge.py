#!/usr/bin/env python3
"""
Telegram ↔ Filesystem Bridge for Navaia AI Workforce.

Smart bridge that classifies incoming messages as tasks, questions, or replies,
and routes them to the appropriate filesystem location.

- Tasks → workspace/tasks/inbox/
- Questions → answered immediately by the bot using system state
- Replies/approvals → workspace/comms/from-founder/
- Agent messages ← workspace/comms/to-founder/ (watched via watchdog)
"""

import asyncio
import logging
import os
import re
import signal
import sys
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

if not BOT_TOKEN or not FOUNDER_CHAT_ID:
    print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_FOUNDER_CHAT_ID must be set in .env")
    sys.exit(1)

FOUNDER_CHAT_ID = int(FOUNDER_CHAT_ID)

# Paths relative to repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX_DIR = REPO_ROOT / "workspace" / "tasks" / "inbox"
ACTIVE_DIR = REPO_ROOT / "workspace" / "tasks" / "active"
DONE_DIR = REPO_ROOT / "workspace" / "tasks" / "done"
REJECTED_DIR = REPO_ROOT / "workspace" / "tasks" / "rejected"
FROM_FOUNDER_DIR = REPO_ROOT / "workspace" / "comms" / "from-founder"
TO_FOUNDER_DIR = REPO_ROOT / "workspace" / "comms" / "to-founder"
OUTPUTS_DIR = REPO_ROOT / "workspace" / "outputs"
STOP_FILE = REPO_ROOT / "workspace" / "comms" / "STOP"

# Ensure directories exist
for d in [INBOX_DIR, ACTIVE_DIR, DONE_DIR, REJECTED_DIR, FROM_FOUNDER_DIR, TO_FOUNDER_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Logging
logging.basicConfig(
    format="%(asctime)s [TelegramBridge] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Telegram message limit
TELEGRAM_MAX_LENGTH = 4000


# ── Authorization ────────────────────────────────────────────────────────────

def is_authorized(chat_id: int) -> bool:
    """Only the Founder's chat ID is allowed."""
    return chat_id == FOUNDER_CHAT_ID


# ── Message Classification ───────────────────────────────────────────────────

# Keywords/patterns that indicate a question or inquiry (not a task)
QUESTION_PATTERNS = [
    r"^(what|how|why|when|where|who|which|is|are|was|were|do|does|did|can|could|would|will|should|has|have)\b",
    r"\?$",
    r"^(status|update|progress|report)\b",
    r"^(tell me|show me|give me|list|check)\b",
    r"^(what'?s|how'?s|where'?s|who'?s)\b",
]

# Keywords that indicate approval/reply to a pending plan or question
REPLY_PATTERNS = [
    r"^(yes|no|ok|okay|approved?|reject|cancel|go ahead|proceed|confirmed?|deny|denied)\b",
    r"^(change|modify|update|edit|revise)\b.*\bto\b",
    r"^(option|choice|pick|choose)\s*[a-d1-4]",
    r"^(looks good|lgtm|ship it|do it|go for it)\b",
    r"^(stop|pause|wait|hold)\b",
]

# Keywords that strongly indicate an actionable task
TASK_PATTERNS = [
    r"^(create|build|write|make|design|develop|deploy|fix|add|remove|delete|update|set up|configure|send|draft|prepare|generate|analyze|research)\b",
    r"^(i need|i want|please|pls|can you|could you)\b.{15,}",
]


def classify_message(text: str) -> str:
    """
    Classify a message as 'task', 'question', or 'reply'.
    Returns one of: 'task', 'question', 'reply'
    """
    text_lower = text.strip().lower()

    # Short messages (under 5 words) that are questions
    word_count = len(text_lower.split())

    # Check for reply/approval patterns first (highest priority)
    for pattern in REPLY_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "reply"

    # Check for explicit task patterns
    for pattern in TASK_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "task"

    # Check for question patterns
    for pattern in QUESTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "question"

    # Default: if it's long enough (>10 words), treat as a task; otherwise question
    if word_count > 10:
        return "task"

    return "task"  # When in doubt, save it as a task so nothing is lost


# ── System State ─────────────────────────────────────────────────────────────

def count_files(directory: Path) -> int:
    """Count non-gitkeep files in a directory."""
    if not directory.exists():
        return 0
    return len([f for f in directory.iterdir() if f.is_file() and f.name != ".gitkeep"])


def get_recent_files(directory: Path, limit: int = 5) -> list[str]:
    """Get the most recent files in a directory."""
    if not directory.exists():
        return []
    files = [f for f in directory.iterdir() if f.is_file() and f.name != ".gitkeep"]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return [f.name for f in files[:limit]]


def get_task_summaries(directory: Path, limit: int = 5) -> list[str]:
    """Read task files and return short summaries."""
    if not directory.exists():
        return []
    files = [f for f in directory.iterdir() if f.is_file() and f.name != ".gitkeep"]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    summaries = []
    for f in files[:limit]:
        try:
            content = f.read_text(encoding="utf-8")
            # Extract the actual task text (after the metadata headers)
            lines = content.strip().split("\n")
            task_lines = [l for l in lines if not l.startswith("##") and not l.startswith("**") and l.strip()]
            if task_lines:
                summary = task_lines[0][:100]
                summaries.append(f"• {summary}")
        except Exception:
            summaries.append(f"• {f.name}")
    return summaries


def is_claude_running() -> bool:
    """Check if Claude Code is currently running."""
    try:
        import subprocess
        result = subprocess.run(["pgrep", "-f", "claude"], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


def build_status_response() -> str:
    """Build a comprehensive status message."""
    inbox_count = count_files(INBOX_DIR)
    active_count = count_files(ACTIVE_DIR)
    done_count = count_files(DONE_DIR)
    rejected_count = count_files(REJECTED_DIR)
    claude_running = is_claude_running()

    # Count outputs
    output_counts = {}
    for agent_dir in ["creative", "technical", "admin"]:
        agent_path = OUTPUTS_DIR / agent_dir
        if agent_path.exists():
            count = sum(1 for _ in agent_path.rglob("*") if _.is_file() and _.name != ".gitkeep")
            if count > 0:
                output_counts[agent_dir] = count

    msg = "📊 *Navaia Crew Status*\n\n"
    msg += f"🤖 Agents: {'🟢 Running' if claude_running else '🔴 Stopped'}\n\n"
    msg += f"📥 Inbox: {inbox_count}\n"
    msg += f"🔄 Active: {active_count}\n"
    msg += f"✅ Done: {done_count}\n"
    msg += f"❌ Rejected: {rejected_count}\n"

    if output_counts:
        msg += "\n📦 *Outputs:*\n"
        for agent, count in output_counts.items():
            msg += f"  {agent.title()}: {count} files\n"

    # Show recent active tasks
    if active_count > 0:
        summaries = get_task_summaries(ACTIVE_DIR, 3)
        if summaries:
            msg += "\n🔄 *Active Tasks:*\n" + "\n".join(summaries) + "\n"

    # Show recent inbox tasks
    if inbox_count > 0:
        summaries = get_task_summaries(INBOX_DIR, 3)
        if summaries:
            msg += "\n📥 *Pending Tasks:*\n" + "\n".join(summaries) + "\n"

    # Show recent completed
    if done_count > 0:
        summaries = get_task_summaries(DONE_DIR, 3)
        if summaries:
            msg += "\n✅ *Recently Done:*\n" + "\n".join(summaries) + "\n"

    return msg


def build_question_response(text: str) -> str:
    """Build a smart response to common questions."""
    text_lower = text.strip().lower()

    # "Is it doing the tasks?" / "Are the agents working?"
    if any(kw in text_lower for kw in ["doing", "working", "running", "active", "alive", "started"]):
        claude_running = is_claude_running()
        active = count_files(ACTIVE_DIR)
        inbox = count_files(INBOX_DIR)
        if claude_running:
            msg = "🟢 *Yes, the agents are running.*\n"
            if active > 0:
                msg += f"Currently working on {active} task(s).\n"
                summaries = get_task_summaries(ACTIVE_DIR, 3)
                if summaries:
                    msg += "\n".join(summaries)
            elif inbox > 0:
                msg += f"{inbox} task(s) in the inbox waiting to be picked up."
            else:
                msg += "No tasks in queue — agents are idle."
            return msg
        else:
            return f"🔴 *Agents are not running right now.*\n\n📥 {inbox} task(s) in inbox, {active} active.\n\nStart the crew with:\n`bash scripts/loop.sh`"

    # "What did it do?" / "What's been done?" / "Progress?"
    if any(kw in text_lower for kw in ["did it do", "done so far", "progress", "what happened", "been done", "completed", "finished"]):
        done = count_files(DONE_DIR)
        if done > 0:
            summaries = get_task_summaries(DONE_DIR, 5)
            return f"✅ *{done} task(s) completed:*\n\n" + "\n".join(summaries)
        else:
            active = count_files(ACTIVE_DIR)
            inbox = count_files(INBOX_DIR)
            return f"No completed tasks yet.\n\n📥 Inbox: {inbox}\n🔄 Active: {active}"

    # "What tasks are pending?" / "What's in the queue?"
    if any(kw in text_lower for kw in ["pending", "queue", "inbox", "waiting", "backlog"]):
        inbox = count_files(INBOX_DIR)
        if inbox > 0:
            summaries = get_task_summaries(INBOX_DIR, 5)
            return f"📥 *{inbox} task(s) in inbox:*\n\n" + "\n".join(summaries)
        else:
            return "📥 Inbox is empty. Send a task to get started!"

    # Generic status question — return full status
    return build_status_response()


# ── Incoming Messages ────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages from the Founder — classify and route."""
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        logger.warning(f"Unauthorized message from chat_id={update.effective_chat.id}")
        return

    text = update.message.text
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    msg_type = classify_message(text)

    logger.info(f"Message classified as '{msg_type}': {text[:50]}...")

    if msg_type == "question":
        # Answer questions directly using system state
        response = build_question_response(text)
        await update.message.reply_text(response, parse_mode="Markdown")
        logger.info("Answered question directly")

    elif msg_type == "reply":
        # Save as a reply in from-founder for agents to pick up
        filename = f"{timestamp}-reply.md"
        filepath = FROM_FOUNDER_DIR / filename

        content = f"""## FOUNDER REPLY
**Time:** {datetime.now(timezone.utc).isoformat()}
**Source:** Telegram

{text}
"""
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"Reply saved: {filepath}")
        await update.message.reply_text("👍 Got it. Passing to Navi.")

    else:
        # Save as a new task in inbox
        filename = f"{timestamp}-task.md"
        filepath = INBOX_DIR / filename

        content = f"""## NEW TASK FROM FOUNDER
**Time:** {datetime.now(timezone.utc).isoformat()}
**Source:** Telegram

{text}
"""
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"New task saved: {filepath}")

        # Acknowledge with context
        inbox_count = count_files(INBOX_DIR)
        active_count = count_files(ACTIVE_DIR)
        claude_running = is_claude_running()

        ack = "✅ *Task received.*\n"
        if claude_running:
            if active_count > 0:
                ack += f"Navi is working on {active_count} task(s). Yours is #{inbox_count} in the queue."
            else:
                ack += "Navi will pick it up now."
        else:
            ack += f"⚠️ Agents are not running. Task saved to inbox (#{inbox_count}).\nStart with: `bash scripts/loop.sh`"

        await update.message.reply_text(ack, parse_mode="Markdown")


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command — return comprehensive status."""
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    msg = build_status_response()
    await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop command — create STOP signal file."""
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    STOP_FILE.write_text(
        f"STOP requested by Founder at {datetime.now(timezone.utc).isoformat()}",
        encoding="utf-8",
    )
    logger.info("STOP signal created")
    await update.message.reply_text("🛑 STOP signal sent. The crew will halt after the current task.")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    msg = (
        "🤖 *Navaia Crew Bot*\n\n"
        "*Commands:*\n"
        "/status — Full crew status & task counts\n"
        "/stop — Halt the crew after current task\n"
        "/help — Show this message\n\n"
        "*How to use:*\n"
        "📝 *Send a task* — \"Write 3 cold emails for SaaS founders\"\n"
        "❓ *Ask a question* — \"What's the progress?\" / \"Is it running?\"\n"
        "👍 *Reply to a plan* — \"Approved\" / \"Go ahead\" / \"Change X to Y\"\n\n"
        "The bot automatically knows the difference between tasks, questions, and replies."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /clear command — clear all inbox tasks."""
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    count = 0
    for f in INBOX_DIR.iterdir():
        if f.is_file() and f.name != ".gitkeep":
            f.unlink()
            count += 1

    await update.message.reply_text(f"🗑️ Cleared {count} task(s) from inbox.")
    logger.info(f"Inbox cleared: {count} files removed")


# ── Outgoing Messages (File Watcher) ────────────────────────────────────────

class OutboxWatcher(FileSystemEventHandler):
    """Watches workspace/comms/to-founder/ for new .md files and sends them via Telegram."""

    def __init__(self, application: Application):
        self.application = application
        self._sent_files: set[str] = set()

    def on_created(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith(".md"):
            return

        filepath = Path(event.src_path)
        if filepath.name in self._sent_files:
            return

        self._sent_files.add(filepath.name)
        logger.info(f"New outbox file detected: {filepath.name}")

        try:
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(self._send_file(filepath), loop)
        except RuntimeError:
            logger.error("No event loop available for sending outbox file")

    async def _send_file(self, filepath: Path):
        """Read the file and send its content to the Founder."""
        try:
            await asyncio.sleep(0.5)
            content = filepath.read_text(encoding="utf-8")

            if len(content) > TELEGRAM_MAX_LENGTH:
                content = content[:TELEGRAM_MAX_LENGTH] + "\n\n⚠️ _Message truncated. Full content in file._"

            await self.application.bot.send_message(
                chat_id=FOUNDER_CHAT_ID,
                text=content,
                parse_mode="Markdown",
            )
            logger.info(f"Sent to Founder: {filepath.name}")
        except Exception as e:
            logger.error(f"Failed to send {filepath.name}: {e}")


class OutputWatcher(FileSystemEventHandler):
    """Watches workspace/outputs/ for new files and notifies the Founder."""

    AGENT_NAMES = {
        "creative": "Muse (Creative)",
        "technical": "Arch (Technical)",
        "admin": "Sage (Admin)",
        "pm": "Navi (PM)",
    }

    def __init__(self, application: Application):
        self.application = application
        self._notified_files: set[str] = set()

    def on_created(self, event):
        if event.is_directory:
            return

        filepath = Path(event.src_path)
        if filepath.name == ".gitkeep":
            return
        if str(filepath) in self._notified_files:
            return

        self._notified_files.add(str(filepath))
        logger.info(f"New output file detected: {filepath}")

        try:
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(self._notify_output(filepath), loop)
        except RuntimeError:
            logger.error("No event loop available for output notification")

    async def _notify_output(self, filepath: Path):
        """Notify the Founder about a new output file."""
        try:
            await asyncio.sleep(1)  # Wait for file to be fully written

            # Determine which agent produced this
            rel_path = filepath.relative_to(OUTPUTS_DIR)
            agent_folder = rel_path.parts[0] if rel_path.parts else "unknown"
            agent_name = self.AGENT_NAMES.get(agent_folder, agent_folder.title())

            # Get file info
            size = filepath.stat().st_size
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"

            msg = f"📄 *New output from {agent_name}*\n\n"
            msg += f"📁 `{rel_path}`\n"
            msg += f"📏 Size: {size_str}\n"

            # For text files, include a preview
            ext = filepath.suffix.lower()
            if ext in [".md", ".txt", ".csv", ".html", ".json"]:
                try:
                    content = filepath.read_text(encoding="utf-8")
                    # Send first 500 chars as preview
                    preview = content[:500]
                    if len(content) > 500:
                        preview += "\n\n_... (truncated)_"
                    msg += f"\n---\n{preview}"
                except Exception:
                    pass
            else:
                msg += f"\n_{ext.upper().lstrip('.')} file — open locally to view_"

            if len(msg) > TELEGRAM_MAX_LENGTH:
                msg = msg[:TELEGRAM_MAX_LENGTH - 50] + "\n\n⚠️ _Preview truncated._"

            await self.application.bot.send_message(
                chat_id=FOUNDER_CHAT_ID,
                text=msg,
                parse_mode="Markdown",
            )
            logger.info(f"Notified Founder about output: {rel_path}")
        except Exception as e:
            logger.error(f"Failed to notify about output {filepath}: {e}")


class TaskDoneWatcher(FileSystemEventHandler):
    """Watches workspace/tasks/done/ for completed tasks and notifies the Founder."""

    def __init__(self, application: Application):
        self.application = application
        self._notified_files: set[str] = set()

    def on_created(self, event):
        if event.is_directory:
            return

        filepath = Path(event.src_path)
        if filepath.name == ".gitkeep":
            return
        if filepath.name in self._notified_files:
            return

        self._notified_files.add(filepath.name)
        logger.info(f"Task completed: {filepath.name}")

        try:
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(self._notify_done(filepath), loop)
        except RuntimeError:
            logger.error("No event loop available for done notification")

    async def _notify_done(self, filepath: Path):
        """Notify the Founder that a task was completed."""
        try:
            await asyncio.sleep(0.5)
            content = filepath.read_text(encoding="utf-8")

            # Extract task description
            lines = content.strip().split("\n")
            task_lines = [l for l in lines if not l.startswith("##") and not l.startswith("**") and l.strip()]
            task_text = task_lines[0][:200] if task_lines else filepath.name

            msg = f"✅ *Task Completed*\n\n{task_text}"

            await self.application.bot.send_message(
                chat_id=FOUNDER_CHAT_ID,
                text=msg,
                parse_mode="Markdown",
            )
            logger.info(f"Notified Founder: task done — {filepath.name}")
        except Exception as e:
            logger.error(f"Failed to notify task done {filepath}: {e}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    logger.info("Starting Navaia Telegram Bridge (Smart Mode)...")
    logger.info(f"Watching outbox: {TO_FOUNDER_DIR}")
    logger.info(f"Saving tasks to: {INBOX_DIR}")

    # Build the Telegram bot application
    app = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("stop", handle_stop))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("clear", handle_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Set up file watchers
    observer = Observer()

    # 1. Watch outbox — agent messages to Founder
    outbox_watcher = OutboxWatcher(app)
    observer.schedule(outbox_watcher, str(TO_FOUNDER_DIR), recursive=False)
    logger.info(f"Watching outbox: {TO_FOUNDER_DIR}")

    # 2. Watch outputs — notify Founder when agents produce files
    output_watcher = OutputWatcher(app)
    observer.schedule(output_watcher, str(OUTPUTS_DIR), recursive=True)
    logger.info(f"Watching outputs: {OUTPUTS_DIR}")

    # 3. Watch done — notify Founder when tasks complete
    done_watcher = TaskDoneWatcher(app)
    observer.schedule(done_watcher, str(DONE_DIR), recursive=False)
    logger.info(f"Watching done: {DONE_DIR}")

    observer.start()
    logger.info("All file watchers started")

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info("Shutting down...")
        observer.stop()
        observer.join()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start polling
    logger.info("Telegram bridge is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
