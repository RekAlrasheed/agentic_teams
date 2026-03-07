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


# ── Conversation Memory ─────────────────────────────────────────────────────

class ConversationMemory:
    """Keeps recent conversation history for context."""

    def __init__(self, max_messages: int = 20):
        self.messages: list[dict] = []
        self.max_messages = max_messages
        self._pending_tasks: dict[str, dict] = {}  # task_id -> task info awaiting confirmation

    def add(self, role: str, text: str):
        self.messages.append({
            "role": role,
            "text": text[:500],  # Keep messages compact
            "time": datetime.now(timezone.utc).strftime("%H:%M"),
        })
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

    def get_history_text(self) -> str:
        if not self.messages:
            return "No previous messages."
        lines = []
        for m in self.messages[-10:]:  # Last 10 for context
            prefix = "Founder" if m["role"] == "user" else "Bot"
            lines.append(f"[{m['time']}] {prefix}: {m['text']}")
        return "\n".join(lines)

    def add_pending_task(self, task_id: str, info: dict):
        self._pending_tasks[task_id] = info

    def get_pending_task(self) -> dict | None:
        """Get the most recent pending task (if any)."""
        if self._pending_tasks:
            latest = list(self._pending_tasks.values())[-1]
            return latest
        return None

    def clear_pending_tasks(self):
        self._pending_tasks.clear()

    def remove_pending_task(self, task_id: str):
        self._pending_tasks.pop(task_id, None)


conversation = ConversationMemory()


# ── Trello API ───────────────────────────────────────────────────────────────

def trello_enabled() -> bool:
    return bool(TRELLO_KEY and TRELLO_TOKEN and TRELLO_BOARD_ID)


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


def trello_get_board_summary() -> str:
    """Get a compact summary of the Trello board."""
    lists = trello_api("GET", f"boards/{TRELLO_BOARD_ID}/lists")
    if not isinstance(lists, list):
        return "Could not fetch Trello board."

    summary_parts = []
    for lst in lists:
        cards = trello_api("GET", f"lists/{lst['id']}/cards")
        if not isinstance(cards, list):
            cards = []
        if cards:
            card_names = [c["name"][:60] for c in cards[:5]]
            card_list = ", ".join(card_names)
            if len(cards) > 5:
                card_list += f" (+{len(cards) - 5} more)"
            summary_parts.append(f"{lst['name']} ({len(cards)}): {card_list}")
        else:
            summary_parts.append(f"{lst['name']}: empty")

    return "\n".join(summary_parts)


# ── Context Builders ─────────────────────────────────────────────────────────

def get_system_status() -> str:
    """Build a concise status snapshot."""
    try:
        result = subprocess.run(["pgrep", "-f", "claude"], capture_output=True, text=True)
        agents_online = result.returncode == 0
    except Exception:
        agents_online = False

    inbox = len([f for f in INBOX_DIR.iterdir() if f.is_file() and f.name != ".gitkeep"]) if INBOX_DIR.exists() else 0
    active = len([f for f in ACTIVE_DIR.iterdir() if f.is_file() and f.name != ".gitkeep"]) if ACTIVE_DIR.exists() else 0
    done = len([f for f in DONE_DIR.iterdir() if f.is_file() and f.name != ".gitkeep"]) if DONE_DIR.exists() else 0
    blocked = len([f for f in BLOCKED_DIR.iterdir() if f.is_file() and f.name != ".gitkeep"]) if BLOCKED_DIR.exists() else 0

    status = f"Agents: {'ONLINE' if agents_online else 'OFFLINE (auto-restart when tasks arrive)'}\n"
    status += f"Tasks — Inbox: {inbox}, Active: {active}, Done: {done}, Blocked: {blocked}"
    return status


def get_recent_outputs(limit: int = 5) -> str:
    """Get recent output file summaries."""
    if not OUTPUTS_DIR.exists():
        return "No outputs yet."
    files = []
    for f in OUTPUTS_DIR.rglob("*"):
        if f.is_file() and f.name != ".gitkeep":
            files.append(f)
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    if not files:
        return "No outputs yet."

    agent_names = {"creative": "Muse", "technical": "Arch", "admin": "Sage", "pm": "Navi"}
    lines = []
    for f in files[:limit]:
        rel = f.relative_to(OUTPUTS_DIR)
        agent_folder = rel.parts[0] if rel.parts else "unknown"
        agent = agent_names.get(agent_folder, agent_folder)
        size_kb = f.stat().st_size / 1024
        lines.append(f"- {agent}: {f.name} ({size_kb:.1f}KB)")
    return "\n".join(lines)


def get_knowledge_summary() -> str:
    """Load the knowledge index for company context."""
    index_file = KNOWLEDGE_DIR / "INDEX.md"
    if index_file.exists():
        try:
            return index_file.read_text(encoding="utf-8")[:3000]
        except Exception:
            pass
    return "Knowledge base not indexed yet."


def get_active_task_details() -> str:
    """Get details of active tasks."""
    if not ACTIVE_DIR.exists():
        return "No active tasks."
    files = [f for f in ACTIVE_DIR.iterdir() if f.is_file() and f.name != ".gitkeep"]
    if not files:
        return "No active tasks."
    details = []
    for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
        try:
            content = f.read_text(encoding="utf-8")[:200]
            details.append(f"- {f.name}: {content.strip()[:100]}")
        except Exception:
            details.append(f"- {f.name}")
    return "\n".join(details)


# ── Claude CLI Integration ───────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """You are Navaia's AI assistant bot on Telegram. You chat with the Founder (CEO) of Navaia.

YOUR ROLE:
- You are the Founder's smart assistant. Answer questions, discuss ideas, help with tasks.
- You manage the AI Workforce (4 agents: Navi/PM, Muse/Creative, Arch/Technical, Sage/Admin).
- You decide intelligently what to do with each message.

RESPONSE FORMAT:
You MUST respond with valid JSON only. No other text before or after the JSON.
Use this exact format:

{{
  "action": "reply|create_task|ask_clarification",
  "message": "Your response text to show the Founder",
  "task_title": "Short task title (only if action=create_task)",
  "task_description": "Detailed task description (only if action=create_task)",
  "agent": "PM|Creative|Technical|Admin (only if action=create_task)",
  "priority": "high|medium|low (only if action=create_task)"
}}

WHEN TO USE EACH ACTION:
- "reply": For greetings, questions, status checks, discussions, quick answers, opinions, advice.
  Most messages should be "reply". The Founder doesn't want every message to become a task.
- "ask_clarification": When the Founder asks for work but you need details before creating a task.
  Ask about: scope, deadline, target audience, delivery format, priority, or specifics.
  Example: "Write content" → ask what kind, for which platform, what tone, etc.
- "create_task": ONLY when you have a clear, actionable task with enough detail to execute.
  The Founder explicitly wants something done, and you have enough context.

IMPORTANT RULES:
1. Be conversational and natural. You're chatting with the CEO — be smart, concise, helpful.
2. Answer in the same language as the Founder's message (English or Arabic).
3. Keep messages short — the Founder reads on mobile. Under 200 words for replies.
4. Don't create tasks for questions, greetings, status checks, or casual chat.
5. When creating a task, give a clear confirmation with what you understood.
6. If the Founder says "yes", "go ahead", "approved", "do it" — check conversation history for what they're confirming, and create the task.
7. For status questions, use the live system data provided.
8. You know Navaia's business: AI-powered real estate tech in Riyadh, products Bilal (voice) and Baian (chat), clients in pilot stage.

CURRENT SYSTEM STATE:
{system_status}

TRELLO BOARD:
{trello_state}

RECENT OUTPUTS:
{recent_outputs}

ACTIVE TASKS:
{active_tasks}

CONVERSATION HISTORY:
{conversation_history}

COMPANY KNOWLEDGE (summary):
{knowledge_summary}"""


async def ask_claude(message: str) -> dict:
    """
    Send message to Claude CLI, get structured JSON response.
    Uses Max subscription — no extra cost.
    """
    # Build context
    system_status = get_system_status()
    trello_state = trello_get_board_summary() if trello_enabled() else "Trello not configured."
    recent_outputs = get_recent_outputs(5)
    active_tasks = get_active_task_details()
    conv_history = conversation.get_history_text()
    knowledge = get_knowledge_summary()

    # Check for pending task confirmations
    pending = conversation.get_pending_task()
    pending_context = ""
    if pending:
        pending_context = f"\n\nPENDING TASK AWAITING CONFIRMATION:\nTitle: {pending.get('title', '')}\nDescription: {pending.get('description', '')}\nAgent: {pending.get('agent', '')}\nIf the Founder says yes/go ahead/approved, create this task with action=create_task."

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        system_status=system_status,
        trello_state=trello_state,
        recent_outputs=recent_outputs,
        active_tasks=active_tasks,
        conversation_history=conv_history,
        knowledge_summary=knowledge[:2000],
    )
    system_prompt += pending_context

    try:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)

        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", message,
            "--model", "haiku",
            "--max-turns", "1",
            "--output-format", "text",
            "--system-prompt", system_prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(REPO_ROOT),
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45)
        raw = stdout.decode("utf-8").strip()

        if not raw:
            logger.warning(f"Claude empty response. stderr: {stderr.decode()[:200]}")
            return {"action": "reply", "message": "I'm having trouble processing that. Could you try again?"}

        # Parse JSON from response — handle cases where Claude wraps in markdown
        json_str = raw
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        # Try to find JSON object in the response
        start = json_str.find("{")
        end = json_str.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = json_str[start:end]

        result = json.loads(json_str)

        # Validate required fields
        if "action" not in result or "message" not in result:
            return {"action": "reply", "message": raw[:TELEGRAM_MAX_LENGTH]}

        return result

    except json.JSONDecodeError:
        # Claude didn't return valid JSON — treat raw text as a reply
        logger.warning(f"Claude non-JSON response, using as plain reply")
        return {"action": "reply", "message": raw[:TELEGRAM_MAX_LENGTH] if raw else "Something went wrong. Try again?"}
    except asyncio.TimeoutError:
        logger.error("Claude CLI timed out (45s)")
        return {"action": "reply", "message": "I'm taking too long to think. Let me try a simpler answer — what do you need?"}
    except FileNotFoundError:
        logger.error("Claude CLI not found")
        return {"action": "reply", "message": "My AI brain isn't connected right now. The team can check the setup."}
    except Exception as e:
        logger.error(f"Claude CLI error: {e}")
        return {"action": "reply", "message": "Something went wrong on my end. Try again?"}


# ── Task Creation ────────────────────────────────────────────────────────────

def create_task_file(title: str, description: str, agent: str = "PM") -> str:
    """Create a task file in inbox and optionally a Trello card."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"{timestamp}-task.md"
    filepath = INBOX_DIR / filename

    content = f"""## TASK: {title}
**Time:** {datetime.now(timezone.utc).isoformat()}
**Source:** Telegram (Founder)
**Assigned Agent:** {agent}
**Priority:** Standard

### Description
{description}
"""
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Task created: {filepath.name}")

    # Create Trello card
    trello_card_id = ""
    if trello_enabled():
        label_map = {
            "PM": "PM", "Creative": "Creative",
            "Technical": "Technical", "Admin": "Admin",
        }
        label = label_map.get(agent, "PM")
        trello_card_id = trello_create_card("Inbox", title, description, label)

    return trello_card_id


# ── Telegram Handlers ────────────────────────────────────────────────────────

def is_authorized(chat_id: int) -> bool:
    return chat_id == FOUNDER_CHAT_ID


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every message goes through Claude for intelligent processing."""
    if not is_authorized(update.effective_chat.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    text = update.message.text
    if not text:
        return

    logger.info(f"Message from Founder: {text[:80]}...")

    # Add to conversation memory
    conversation.add("user", text)

    # Show typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Process through Claude
    result = await ask_claude(text)
    action = result.get("action", "reply")
    message = result.get("message", "")

    if action == "create_task":
        # Claude decided this is a clear, actionable task
        title = result.get("task_title", text[:80])
        description = result.get("task_description", text)
        agent = result.get("agent", "PM")

        trello_id = create_task_file(title, description, agent)

        # Append Trello confirmation to message
        if trello_id:
            message += f"\n\n📋 Added to Trello → Inbox"

        # Save reply to from-founder for agents to pick up
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        reply_file = FROM_FOUNDER_DIR / f"{timestamp}-task-created.md"
        reply_file.write_text(
            f"## TASK CREATED\n**Title:** {title}\n**Agent:** {agent}\n\n{description}\n",
            encoding="utf-8"
        )

        conversation.clear_pending_tasks()

    elif action == "ask_clarification":
        # Claude wants to ask before creating a task — store what we know so far
        task_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        conversation.add_pending_task(task_id, {
            "title": result.get("task_title", ""),
            "description": result.get("task_description", ""),
            "agent": result.get("agent", "PM"),
            "original_text": text,
        })

    # Reply action is just a direct response — no file creation needed

    # Add bot response to memory
    conversation.add("bot", message)

    # Send response (handle long messages)
    if message:
        # Try Markdown first, fall back to plain text
        if len(message) > TELEGRAM_MAX_LENGTH:
            message = message[:TELEGRAM_MAX_LENGTH - 50] + "\n\n_(truncated)_"
        try:
            await update.message.reply_text(message, parse_mode="Markdown")
        except Exception:
            # Markdown parsing failed — send as plain text
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
                content = content[:TELEGRAM_MAX_LENGTH] + "\n\n_(truncated)_"
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
            await asyncio.sleep(2)
            rel = filepath.relative_to(OUTPUTS_DIR)
            agent_names = {"creative": "Muse", "technical": "Arch", "admin": "Sage", "pm": "Navi"}
            agent_folder = rel.parts[0] if rel.parts else "unknown"
            agent = agent_names.get(agent_folder, agent_folder)
            size_kb = filepath.stat().st_size / 1024

            msg = f"📄 *New from {agent}:* `{filepath.name}` ({size_kb:.1f}KB)"

            # Preview for text files
            if filepath.suffix.lower() in [".md", ".txt", ".csv", ".html", ".json"]:
                try:
                    content = filepath.read_text(encoding="utf-8")
                    preview_lines = []
                    for line in content.split("\n"):
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
                            preview_lines.append(stripped)
                            if len(preview_lines) >= 3:
                                break
                    if preview_lines:
                        preview = "\n".join(preview_lines)[:300]
                        msg += f"\n\n_{preview}_"
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
    observer = Observer()
    observer.schedule(OutboxWatcher(app), str(TO_FOUNDER_DIR), recursive=False)
    observer.schedule(OutputWatcher(app), str(OUTPUTS_DIR), recursive=True)
    observer.schedule(TaskDoneWatcher(app), str(DONE_DIR), recursive=False)
    observer.start()
    logger.info("File watchers active")

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
