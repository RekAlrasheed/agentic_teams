#!/usr/bin/env python3
"""
Navaia Crew Bot — Claude-First AI Assistant

Every message is processed by Claude (via Max subscription CLI).
Claude decides whether to: answer directly, ask clarification, or create a task.
No regex classification — pure AI understanding.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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

from navi_core import (
    ask_async as navi_ask_async,
    create_task as navi_create_task,
    trello_enabled,
    trello_get_board_summary,
    get_system_status,
    get_recent_outputs,
)

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
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"

for d in [INBOX_DIR, ACTIVE_DIR, DONE_DIR, REJECTED_DIR, BLOCKED_DIR,
          FROM_FOUNDER_DIR, TO_FOUNDER_DIR, OUTPUTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s [NavaiBot] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_MAX_LENGTH = 4000


# ── Trello API (local helpers for Telegram-specific operations) ──────────────


def trello_api(method: str, endpoint: str, params: dict = None) -> dict | list:
    """Call Trello REST API."""
    if not trello_enabled():
        return {}
    base = "https://api.trello.com/1"
    auth = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    all_params = {**auth, **(params or {})}
    query = urllib.parse.urlencode(all_params)
    url = f"{base}/{endpoint}?{query}"
    try:
        req = urllib.request.Request(url, method=method.upper())
        if method.upper() in ("POST", "PUT"):
            req = urllib.request.Request(url, data=b"", method=method.upper())
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        logger.error(f"Trello API error: {e}")
        return {}


def trello_get_list_id(list_name: str) -> str:
    lists = trello_api("GET", f"boards/{TRELLO_BOARD_ID}/lists")
    if isinstance(lists, list):
        for l in lists:
            if l["name"] == list_name:
                return l["id"]
    return ""


def trello_get_label_id(label_name: str) -> str:
    labels = trello_api("GET", f"boards/{TRELLO_BOARD_ID}/labels")
    if isinstance(labels, list):
        for l in labels:
            if l.get("name") == label_name:
                return l["id"]
    return ""


def trello_create_card(list_name: str, title: str, desc: str = "", label_name: str = "") -> str:
    list_id = trello_get_list_id(list_name)
    if not list_id:
        return ""
    params = {"idList": list_id, "name": title, "desc": desc}
    if label_name:
        label_id = trello_get_label_id(label_name)
        if label_id:
            params["idLabels"] = label_id
    result = trello_api("POST", "cards", params)
    card_id = result.get("id", "") if isinstance(result, dict) else ""
    if card_id:
        logger.info(f"Trello card created: {title} [{card_id[:8]}]")
    return card_id


def trello_move_card(card_id: str, list_name: str):
    list_id = trello_get_list_id(list_name)
    if list_id and card_id:
        trello_api("PUT", f"cards/{card_id}", {"idList": list_id})
        logger.info(f"Trello card {card_id[:8]} moved to {list_name}")


def trello_comment(card_id: str, comment: str):
    if card_id:
        trello_api("POST", f"cards/{card_id}/actions/comments", {"text": comment})


# trello_get_board_summary imported from navi_core


# ── Claude CLI (delegated to NaviCore) ───────────────────────────────────────
# All chat logic now lives in navi_core.py (shared with Dashboard)


# ── Task Creation (delegated to NaviCore) ────────────────────────────────────


# ── Telegram Handlers ────────────────────────────────────────────────────────

def is_authorized(chat_id: int) -> bool:
    return chat_id == FOUNDER_CHAT_ID


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every message goes through NaviCore for intelligent processing."""
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    text = update.message.text
    if not text:
        return

    logger.info(f"Message from Founder: {text[:80]}...")

    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Process through shared NaviCore (saves history, handles tasks, calls Claude)
    result = await navi_ask_async(text, "telegram")
    message = result.get("message", "")

    # Send response (handle long messages)
    if message:
        if len(message) > TELEGRAM_MAX_LENGTH:
            message = message[:TELEGRAM_MAX_LENGTH - 50] + "\n\n_(truncated)_"
        try:
            await update.message.reply_text(message, parse_mode="Markdown")
        except Exception:
            try:
                await update.message.reply_text(message)
            except Exception as e:
                logger.error(f"Failed to send reply: {e}")
                await update.message.reply_text("I processed your message but had trouble formatting the reply. Try again?")
    else:
        await update.message.reply_text("I received your message but couldn't generate a response. Try rephrasing?")


# ── Command Handlers ─────────────────────────────────────────────────────────

async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    status = get_system_status()
    outputs = get_recent_outputs(5)
    board = trello_get_board_summary() if trello_enabled() else "Not configured"

    msg = f"📊 *Navaia Crew — Status*\n\n"
    msg += f"```\n{status}\n```\n\n"

    if trello_enabled():
        msg += f"*Trello Board:*\n{board}\n\n"

    msg += f"*Recent Outputs:*\n{outputs}"

    try:
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(msg)


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
        "Just chat with me naturally — I understand everything.\n\n"
        "*I can:*\n"
        "💬 Answer questions about Navaia, the team, or anything\n"
        "📝 Create tasks when you want something done\n"
        "❓ Ask clarifying questions before starting work\n"
        "📊 Show you status, outputs, and Trello updates\n"
        "🔄 Track what the AI team is working on\n\n"
        "*Commands:*\n"
        "/status — Dashboard\n"
        "/board — Trello board\n"
        "/outputs — Recent deliverables\n"
        "/clear — Clear inbox\n"
        "/stop — Shut down crew\n"
        "/help — This message"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_board(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if trello_enabled():
        board = trello_get_board_summary()
        msg = f"📋 *Trello — Navaia Crew*\n\n{board}"
        try:
            await update.message.reply_text(msg, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(msg)
    else:
        await update.message.reply_text("Trello not configured.")


async def handle_outputs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    outputs = get_recent_outputs(10)
    msg = f"📦 *Recent Deliverables*\n\n{outputs}"
    try:
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(msg)


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
        self._loop = None

    def on_created(self, event):
        if event.is_directory or not event.src_path.endswith(".md"):
            return
        filepath = Path(event.src_path)
        if filepath.name in self._sent:
            return
        self._sent.add(filepath.name)
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._send(filepath), self._loop)

    async def _send(self, filepath: Path):
        try:
            await asyncio.sleep(1)
            content = filepath.read_text(encoding="utf-8")
            if len(content) > TELEGRAM_MAX_LENGTH:
                content = content[:TELEGRAM_MAX_LENGTH] + "\n\n_(truncated)_"
            try:
                await self.application.bot.send_message(
                    chat_id=FOUNDER_CHAT_ID, text=content, parse_mode="Markdown"
                )
            except Exception:
                # Fallback to plain text if markdown parsing fails
                await self.application.bot.send_message(
                    chat_id=FOUNDER_CHAT_ID, text=content
                )
            logger.info(f"Sent to Founder: {filepath.name}")
        except Exception as e:
            logger.error(f"Failed to send {filepath.name}: {e}")


class OutputWatcher(FileSystemEventHandler):
    """Notifies Founder when agents produce output files."""

    def __init__(self, application: Application):
        self.application = application
        self._notified: set[str] = set()
        self._loop = None

    def on_created(self, event):
        if event.is_directory:
            return
        filepath = Path(event.src_path)
        if filepath.name == ".gitkeep" or str(filepath) in self._notified:
            return
        self._notified.add(str(filepath))
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._notify(filepath), self._loop)

    async def _notify(self, filepath: Path):
        try:
            await asyncio.sleep(2)
            rel = filepath.relative_to(OUTPUTS_DIR)
            agent_names = {"creative": "Muse", "technical": "Arch", "admin": "Sage", "pm": "Navi"}
            agent_folder = rel.parts[0] if rel.parts else "unknown"
            agent = agent_names.get(agent_folder, agent_folder)
            size_kb = filepath.stat().st_size / 1024

            msg = f"📄 *New from {agent}:* `{filepath.name}` ({size_kb:.1f}KB)"

            # Preview for text files — include enough to see the actual results
            if filepath.suffix.lower() in [".md", ".txt", ".csv", ".html", ".json"]:
                try:
                    content = filepath.read_text(encoding="utf-8")[:2000]
                    msg += f"\n\n{content}"
                except Exception:
                    pass

            try:
                await self.application.bot.send_message(
                    chat_id=FOUNDER_CHAT_ID, text=msg, parse_mode="Markdown"
                )
            except Exception:
                await self.application.bot.send_message(
                    chat_id=FOUNDER_CHAT_ID, text=msg
                )
            logger.info(f"Notified: new output {rel}")
        except Exception as e:
            logger.error(f"Output notification failed: {e}")


class TaskDoneWatcher(FileSystemEventHandler):
    """Notifies Founder when tasks are completed."""

    def __init__(self, application: Application):
        self.application = application
        self._notified: set[str] = set()
        self._loop = None

    def on_created(self, event):
        if event.is_directory:
            return
        filepath = Path(event.src_path)
        if filepath.name == ".gitkeep" or filepath.name in self._notified:
            return
        self._notified.add(filepath.name)
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._notify(filepath), self._loop)

    async def _notify(self, filepath: Path):
        try:
            await asyncio.sleep(1)
            content = filepath.read_text(encoding="utf-8")
            lines = [l for l in content.strip().split("\n") if l.strip() and not l.startswith("##") and not l.startswith("**")]
            task_text = lines[0][:120] if lines else filepath.name

            msg = f"✅ *Task Done:* {task_text}"

            # Try to move matching Trello card to Done
            if trello_enabled():
                for list_name in ["In Progress", "Review", "To Do", "Inbox"]:
                    list_id = trello_get_list_id(list_name)
                    if not list_id:
                        continue
                    cards = trello_api("GET", f"lists/{list_id}/cards")
                    if isinstance(cards, list):
                        for card in cards:
                            if task_text[:25].lower() in card["name"].lower() or card["name"].lower()[:25] in task_text.lower():
                                trello_move_card(card["id"], "Done")
                                trello_comment(card["id"], "✅ Completed")
                                msg += "\n📋 Trello card → Done"
                                break

            remaining = sum(1 for f in INBOX_DIR.iterdir() if f.is_file() and f.name != ".gitkeep") + \
                        sum(1 for f in ACTIVE_DIR.iterdir() if f.is_file() and f.name != ".gitkeep")
            if remaining > 0:
                msg += f"\n⏳ {remaining} task(s) remaining."
            else:
                msg += "\n🎉 All caught up!"

            try:
                await self.application.bot.send_message(
                    chat_id=FOUNDER_CHAT_ID, text=msg, parse_mode="Markdown"
                )
            except Exception:
                await self.application.bot.send_message(
                    chat_id=FOUNDER_CHAT_ID, text=msg
                )
            logger.info(f"Notified: task done — {filepath.name}")
        except Exception as e:
            logger.error(f"Task done notification failed: {e}")


# ── Startup Scan ─────────────────────────────────────────────────────────────

async def _async_startup_scan(app, outbox_watcher, output_watcher, done_watcher):
    """Send notifications for files created in the last 10 min while bridge was down."""
    cutoff = time.time() - 600  # 10 minutes ago

    for f in sorted(TO_FOUNDER_DIR.iterdir(), key=lambda x: x.stat().st_mtime):
        if f.is_file() and f.name.endswith(".md") and f.name != ".gitkeep":
            if f.stat().st_mtime > cutoff and f.name not in outbox_watcher._sent:
                outbox_watcher._sent.add(f.name)
                await outbox_watcher._send(f)

    for f in sorted(OUTPUTS_DIR.rglob("*"), key=lambda x: x.stat().st_mtime):
        if f.is_file() and f.name != ".gitkeep":
            if f.stat().st_mtime > cutoff and str(f) not in output_watcher._notified:
                output_watcher._notified.add(str(f))
                await output_watcher._notify(f)

    logger.info("Startup scan complete")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    logger.info("Starting Navaia Crew Bot (Claude-First AI Mode)...")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("stop", handle_stop))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("start", handle_help))
    app.add_handler(CommandHandler("board", handle_board))
    app.add_handler(CommandHandler("outputs", handle_outputs))
    app.add_handler(CommandHandler("clear", handle_clear))

    # All text messages → Claude
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # File watchers
    outbox_watcher = OutboxWatcher(app)
    output_watcher = OutputWatcher(app)
    done_watcher = TaskDoneWatcher(app)
    observer = Observer()
    observer.schedule(outbox_watcher, str(TO_FOUNDER_DIR), recursive=False)
    observer.schedule(output_watcher, str(OUTPUTS_DIR), recursive=True)
    observer.schedule(done_watcher, str(DONE_DIR), recursive=False)
    observer.start()
    logger.info("File watchers active")

    # Hook into the app's event loop once it starts via post_init
    async def _on_startup(application):
        loop = asyncio.get_running_loop()
        outbox_watcher._loop = loop
        output_watcher._loop = loop
        done_watcher._loop = loop
        logger.info("Watchers connected to event loop")
        await _async_startup_scan(application, outbox_watcher, output_watcher, done_watcher)

    app.post_init = _on_startup

    def shutdown(signum, frame):
        logger.info("Shutting down...")
        observer.stop()
        observer.join()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("Navaia Crew Bot is LIVE (Claude-powered). Every message → AI.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
