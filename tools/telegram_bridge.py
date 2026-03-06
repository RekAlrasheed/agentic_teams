#!/usr/bin/env python3
"""
Telegram ↔ Filesystem Bridge for Navaia AI Workforce.

Bridges Telegram messages to the filesystem so Claude Code agents can
communicate with the Founder without terminal interaction.

- Founder messages → workspace/tasks/inbox/ or workspace/comms/from-founder/
- Agent messages ← workspace/comms/to-founder/ (watched via watchdog)
"""

import asyncio
import logging
import os
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
FROM_FOUNDER_DIR = REPO_ROOT / "workspace" / "comms" / "from-founder"
TO_FOUNDER_DIR = REPO_ROOT / "workspace" / "comms" / "to-founder"
STOP_FILE = REPO_ROOT / "workspace" / "comms" / "STOP"

# Ensure directories exist
for d in [INBOX_DIR, FROM_FOUNDER_DIR, TO_FOUNDER_DIR]:
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


# ── Incoming Messages ────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages from the Founder."""
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        logger.warning(f"Unauthorized message from chat_id={update.effective_chat.id}")
        return

    text = update.message.text
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

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
    await update.message.reply_text("✅ Task received. Navi will pick it up shortly.")


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command — return task counts."""
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    tasks_dir = REPO_ROOT / "workspace" / "tasks"
    counts = {}
    for folder in ["inbox", "active", "done", "rejected"]:
        folder_path = tasks_dir / folder
        if folder_path.exists():
            counts[folder] = len([f for f in folder_path.iterdir() if f.is_file() and f.name != ".gitkeep"])
        else:
            counts[folder] = 0

    msg = (
        "📊 **Task Status**\n\n"
        f"📥 Inbox: {counts['inbox']}\n"
        f"🔄 Active: {counts['active']}\n"
        f"✅ Done: {counts['done']}\n"
        f"❌ Rejected: {counts['rejected']}"
    )
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

        # Schedule sending in the bot's event loop
        asyncio.run_coroutine_threadsafe(
            self._send_file(filepath),
            self.application.bot._local_mode and asyncio.get_event_loop() or asyncio.get_event_loop(),
        )

    async def _send_file(self, filepath: Path):
        """Read the file and send its content to the Founder."""
        try:
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


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    logger.info("Starting Navaia Telegram Bridge...")
    logger.info(f"Watching outbox: {TO_FOUNDER_DIR}")
    logger.info(f"Saving tasks to: {INBOX_DIR}")

    # Build the Telegram bot application
    app = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("stop", handle_stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Set up the file watcher for outgoing messages
    watcher = OutboxWatcher(app)
    observer = Observer()
    observer.schedule(watcher, str(TO_FOUNDER_DIR), recursive=False)
    observer.start()
    logger.info("File watcher started")

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info("Shutting down...")
        observer.stop()
        observer.join()
        app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start polling
    logger.info("Telegram bridge is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
