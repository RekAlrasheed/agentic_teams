#!/usr/bin/env python3
"""
NaviCore — Unified Navi chat engine shared by Telegram bot and Dashboard.

Single conversation history, single system prompt, single Claude interface.
Both processes import this module; the JSONL file is the source of truth.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"
CHAT_LOG = DASHBOARD_DIR / "chat_history.jsonl"

WORKSPACE = REPO_ROOT / "workspace"
TASKS_DIR = WORKSPACE / "tasks"
INBOX_DIR = TASKS_DIR / "inbox"
ACTIVE_DIR = TASKS_DIR / "active"
DONE_DIR = TASKS_DIR / "done"
BLOCKED_DIR = TASKS_DIR / "blocked"
FROM_FOUNDER_DIR = WORKSPACE / "comms" / "from-founder"
TO_FOUNDER_DIR = WORKSPACE / "comms" / "to-founder"
OUTPUTS_DIR = WORKSPACE / "outputs"
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"

# Trello config
TRELLO_KEY = os.getenv("TRELLO_KEY", "")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN", "")
TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID", "")

# Trim thresholds
_TRIM_THRESHOLD = 1000
_TRIM_TARGET = 500


# ── Conversation History (file-based, process-safe) ─────────────────────────

def save_message(role: str, text: str, source: str = "dashboard") -> dict:
    """Append a message to the shared JSONL history with file locking.

    Trim check runs inside the same lock to prevent race conditions.
    """
    msg = {
        "role": role,
        "text": text,
        "source": source,
        "time": datetime.now(timezone.utc).isoformat(),
    }
    CHAT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHAT_LOG, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(msg) + "\n")
        # Trim inside the same lock to prevent race conditions
        f.seek(0)
        lines = f.readlines()
        if len(lines) > _TRIM_THRESHOLD:
            f.seek(0)
            f.truncate()
            f.writelines(lines[-_TRIM_TARGET:])
        # Lock released automatically when f is closed
    return msg


def load_history(limit: int = 50) -> list[dict]:
    """Load the last N messages from shared JSONL."""
    if not CHAT_LOG.exists() or limit <= 0:
        return []
    try:
        with open(CHAT_LOG, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            lines = f.readlines()
            # Lock released automatically when f is closed
    except Exception:
        return []

    messages = []
    for line in lines[-limit:]:
        line = line.strip()
        if line:
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping corrupt JSONL line: {e}")
    return messages


# ── Context Builders ─────────────────────────────────────────────────────────

def _count_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(1 for f in directory.iterdir() if f.is_file() and f.name != ".gitkeep")


def get_system_status() -> str:
    agent_task_dirs = {
        "pm": [INBOX_DIR, ACTIVE_DIR],
        "creative": [TASKS_DIR / "creative"],
        "technical": [TASKS_DIR / "technical"],
        "admin": [TASKS_DIR / "admin"],
    }
    agent_states = []
    for aid, dirs in agent_task_dirs.items():
        lock = Path(f"/tmp/navaia-{aid}-working")
        task_count = sum(_count_files(d) for d in dirs)
        try:
            loop_check = subprocess.run(
                ["pgrep", "-f", f"agent-loop.sh {aid}"],
                capture_output=True, text=True, timeout=2,
            )
            loop_up = loop_check.returncode == 0 and loop_check.stdout.strip()
        except Exception:
            loop_up = False

        if lock.exists():
            agent_states.append(f"{aid}: WORKING ({task_count} tasks)")
        elif task_count > 0:
            agent_states.append(f"{aid}: STARTING ({task_count} tasks)")
        elif loop_up:
            agent_states.append(f"{aid}: IDLE")
        else:
            agent_states.append(f"{aid}: OFFLINE")

    inbox = _count_files(INBOX_DIR)
    active = _count_files(ACTIVE_DIR)
    done = _count_files(DONE_DIR)
    blocked = _count_files(BLOCKED_DIR)

    status = "Agents: " + ", ".join(agent_states) + "\n"
    status += f"Tasks — Inbox: {inbox}, Active: {active}, Done: {done}, Blocked: {blocked}"
    return status


def get_recent_outputs(limit: int = 5) -> str:
    if not OUTPUTS_DIR.exists():
        return "No outputs yet."
    files = [f for f in OUTPUTS_DIR.rglob("*") if f.is_file() and f.name != ".gitkeep"]
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
    index_file = KNOWLEDGE_DIR / "INDEX.md"
    if index_file.exists():
        try:
            return index_file.read_text(encoding="utf-8")[:3000]
        except Exception:
            pass
    return "Knowledge base not indexed yet."


def get_active_task_details() -> str:
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


# ── Trello (lightweight, reused from bridge) ─────────────────────────────────

def trello_enabled() -> bool:
    return bool(TRELLO_KEY and TRELLO_TOKEN and TRELLO_BOARD_ID)


def _trello_api(method: str, endpoint: str, params: Optional[dict] = None) -> dict | list:
    if not trello_enabled():
        return {}
    base = "https://api.trello.com/1"
    auth = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    all_params = {**auth, **(params or {})}
    query = urllib.parse.urlencode(all_params)
    url = f"{base}/{endpoint}?{query}"
    try:
        data = b"" if method.upper() in ("POST", "PUT") else None
        req = urllib.request.Request(url, data=data, method=method.upper())
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        # Sanitize error to avoid leaking credentials from URL
        logger.error(f"Trello API error on {endpoint}: {type(e).__name__}")
        return {}


def _trello_get_list_id(list_name: str) -> str:
    lists = _trello_api("GET", f"boards/{TRELLO_BOARD_ID}/lists")
    if isinstance(lists, list):
        for trello_list in lists:
            if trello_list["name"] == list_name:
                return trello_list["id"]
    return ""


def _trello_get_label_id(label_name: str) -> str:
    labels = _trello_api("GET", f"boards/{TRELLO_BOARD_ID}/labels")
    if isinstance(labels, list):
        for label in labels:
            if label.get("name") == label_name:
                return label["id"]
    return ""


def trello_get_board_summary() -> str:
    lists = _trello_api("GET", f"boards/{TRELLO_BOARD_ID}/lists")
    if not isinstance(lists, list):
        return "Could not fetch Trello board."
    summary_parts = []
    for lst in lists:
        cards = _trello_api("GET", f"lists/{lst['id']}/cards")
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


# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """You are Navaia's AI assistant chatting with the Founder (CEO).

ROLE: Smart assistant managing 4 AI agents (Navi/PM, Muse/Creative, Arch/Technical, Sage/Admin).
COMPANY: Navaia — AI-powered real estate tech in Riyadh, products Bilal (voice) and Baian (chat).

RESPOND WITH JSON ONLY. Choose ONE format:

SINGLE TASK:
{{"action": "create_task", "message": "Your response", "task_title": "title", "task_description": "description", "agent": "PM|Creative|Technical|Admin"}}

MULTIPLE TASKS (use when Founder wants work for several agents):
{{"action": "create_tasks", "message": "Your response", "tasks": [{{"title": "task1", "description": "desc1", "agent": "Technical"}}, {{"title": "task2", "description": "desc2", "agent": "Admin"}}]}}

REPLY ONLY (no task):
{{"action": "reply", "message": "Your response"}}

AGENT ROUTING — dispatch directly to the right agent:
- Creative (Muse): content, campaigns, outreach, brand, social media, writing
- Technical (Arch): code, bugs, deploy, infra, APIs, GitHub, architecture
- Admin (Sage): docs, proposals, research, finance, compliance, contracts
- PM: only for coordination tasks that span multiple agents

CRITICAL: When Founder asks to activate agents or assign work, create tasks DIRECTLY for each agent using "create_tasks". Do NOT create a single PM task asking PM to dispatch — route tasks directly to agents.

RULES:
- "reply" for most messages (greetings, questions, chat). "create_task"/"create_tasks" for work requests.
- Be concise (<200 words). Same language as Founder (English or Arabic).
- If Founder says "yes"/"go ahead" — check history for what they're confirming.

{system_status}
{recent_outputs}
{active_tasks}

CONVERSATION:
{conversation_history}"""


def _build_system_prompt() -> str:
    """Build a lean system prompt — fast to generate, small token footprint."""
    system_status = get_system_status()
    recent_outputs = get_recent_outputs(3)
    active_tasks = get_active_task_details()

    history = load_history(5)
    if history:
        lines = []
        for m in history:
            prefix = "Founder" if m["role"] == "user" else "Navi"
            text = m.get("text", "")[:150]
            lines.append(f"{prefix}: {text}")
        conv_history = "\n".join(lines)
    else:
        conv_history = "No previous messages."

    return SYSTEM_PROMPT_TEMPLATE.format(
        system_status=system_status,
        recent_outputs=recent_outputs,
        active_tasks=active_tasks,
        conversation_history=conv_history,
    )


# ── Parse Claude response ───────────────────────────────────────────────────

def _parse_response(raw: str) -> dict:
    """Extract JSON from Claude's response, handling markdown wrapping."""
    json_str = raw
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0].strip()
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0].strip()

    # Try parsing directly first
    try:
        result = json.loads(json_str)
        if isinstance(result, dict) and "action" in result and "message" in result:
            return result
    except json.JSONDecodeError:
        pass

    # Find JSON object by trying progressively smaller substrings
    start = json_str.find("{")
    if start >= 0:
        for end in range(len(json_str), start, -1):
            if json_str[end - 1] != "}":
                continue
            try:
                result = json.loads(json_str[start:end])
                if isinstance(result, dict) and "action" in result and "message" in result:
                    return result
            except json.JSONDecodeError:
                continue

    # Fallback: return raw text as reply
    return {"action": "reply", "message": raw[:4000]}


# ── Task Creation ────────────────────────────────────────────────────────────

def create_task(title: str, description: str, agent: str = "PM", source: str = "dashboard") -> str:
    """Create a task file in the right inbox + Trello card. Returns Trello card ID."""
    agent_lower = agent.lower()

    if agent_lower == "pm":
        target_dir = INBOX_DIR
    else:
        target_dir = TASKS_DIR / agent_lower
    target_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    timestamp_us = now.strftime("%Y%m%d-%H%M%S-%f")
    filename = f"{timestamp_us}-task.md"
    filepath = target_dir / filename

    content = f"""## TASK: {title}
**Time:** {now.isoformat()}
**Source:** {source.capitalize()} (Founder)
**Assigned Agent:** {agent}
**Priority:** Standard

### Description
{description}
"""
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Task created: {filepath.name} [{source}]")

    # Write to from-founder so agents can pick it up
    FROM_FOUNDER_DIR.mkdir(parents=True, exist_ok=True)
    reply_file = FROM_FOUNDER_DIR / f"{timestamp_us}-task-created.md"
    reply_file.write_text(
        f"## TASK CREATED\n**Title:** {title}\n**Agent:** {agent}\n\n{description}\n",
        encoding="utf-8"
    )

    # Create Trello card
    trello_card_id = ""
    if trello_enabled():
        label_map = {"pm": "PM", "creative": "Creative", "technical": "Technical", "admin": "Admin"}
        label = label_map.get(agent_lower, "PM")
        list_id = _trello_get_list_id("Inbox")
        if list_id:
            params = {"idList": list_id, "name": title, "desc": description}
            label_id = _trello_get_label_id(label)
            if label_id:
                params["idLabels"] = label_id
            result = _trello_api("POST", "cards", params)
            trello_card_id = result.get("id", "") if isinstance(result, dict) else ""
            if trello_card_id:
                logger.info(f"Trello card created: {title} [{trello_card_id[:8]}]")

    return trello_card_id


# ── Claude CLI Calls ─────────────────────────────────────────────────────────

def _detect_max_turns(message: str) -> str:
    """Return '1' for chat — the bot responds in a single turn.

    Multi-turn tool use is unnecessary for a chatbot and causes timeouts.
    """
    return "1"


def _detect_model(message: str) -> str:
    """Analyze task complexity and return the cheapest model that can handle it.

    Model escalation:
      haiku  — greetings, status checks, simple Q&A, formatting
      sonnet — content writing, routine code, research, task routing
      opus   — architecture decisions, multi-step reasoning, security-critical code
    """
    msg_lower = message.lower()

    # Opus triggers — complex reasoning, architecture, security-critical
    opus_keywords = [
        "architect", "redesign", "refactor the entire", "security audit",
        "design the system", "migration strategy", "database schema design",
        "evaluate trade-offs", "compare approaches", "complex bug",
        "production outage", "critical vulnerability", "system design",
        "scalability plan", "infrastructure overhaul",
    ]
    for kw in opus_keywords:
        if kw in msg_lower:
            return "opus"

    # Sonnet triggers — real work that needs quality output
    sonnet_keywords = [
        "write ", "create ", "build ", "implement", "fix ", "debug",
        "deploy", "code ", "refactor", "update ", "add feature",
        "blog", "article", "pitch", "proposal", "research",
        "analyze", "review", "campaign", "email", "content",
        "api", "endpoint", "test", "budget", "invoice",
        "translate", "plan ", "strategy",
    ]
    for kw in sonnet_keywords:
        if kw in msg_lower:
            return "sonnet"

    # Long messages likely need more reasoning
    if len(message) > 500:
        return "sonnet"

    # Default: haiku for simple chat, status, Q&A
    return "haiku"


def _call_claude(message: str, system_prompt: str, model: str, max_turns: str) -> str:
    """Shared Claude CLI invocation. Returns raw response text."""
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    proc = subprocess.run(
        ["claude", "-p",
         "--model", model,
         "--max-turns", max_turns,
         "--output-format", "text",
         "--system-prompt", system_prompt,
         "--", message],
        capture_output=True, text=True, timeout=30,
        env=env, cwd=str(REPO_ROOT),
    )
    raw = proc.stdout.strip()
    if not raw:
        raw = proc.stderr.strip()
    return raw


async def _call_claude_async(message: str, system_prompt: str, model: str, max_turns: str) -> str:
    """Shared async Claude CLI invocation. Returns raw response text."""
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    proc = await asyncio.create_subprocess_exec(
        "claude", "-p",
        "--model", model,
        "--max-turns", max_turns,
        "--output-format", "text",
        "--system-prompt", system_prompt,
        "--", message,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(REPO_ROOT),
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    raw = stdout.decode("utf-8").strip()
    if not raw:
        raw = stderr.decode("utf-8").strip()
        if raw:
            logger.info("Claude response came via stderr")
    return raw


def _handle_response(raw: str, message: str, source: str) -> dict:
    """Parse Claude response, handle task creation, save to history."""
    if not raw:
        reply = "I'm having trouble right now. Try again in a moment."
        save_message("assistant", reply, source)
        return {"action": "reply", "message": reply}

    result = _parse_response(raw)
    reply_text = result.get("message", raw[:4000])

    # Handle single task creation
    if result.get("action") == "create_task":
        title = result.get("task_title", message[:80])
        desc = result.get("task_description", message)
        agent = result.get("agent", "PM")
        trello_id = create_task(title, desc, agent, source)
        if trello_id:
            reply_text += "\n\n📋 Added to Trello → Inbox"

    # Handle multi-task creation (dispatches directly to agent folders)
    elif result.get("action") == "create_tasks":
        tasks = result.get("tasks", [])
        created = []
        for t in tasks:
            if not isinstance(t, dict):
                continue
            title = t.get("title", "Untitled task")
            desc = t.get("description", "")
            agent = t.get("agent", "PM")
            trello_id = create_task(title, desc, agent, source)
            created.append(f"{agent}: {title}")
            logger.info(f"Multi-task dispatched → {agent}: {title}")
        if created:
            reply_text += "\n\n📋 Tasks dispatched:\n" + "\n".join(f"• {c}" for c in created)

    result["message"] = reply_text
    save_message("assistant", reply_text, source)
    return result


def ask_sync(message: str, source: str = "dashboard") -> dict:
    """Synchronous Claude call — used by Dashboard (subprocess.run).

    On timeout or empty response, retries once with a minimal prompt.
    """
    save_message("user", message, source)
    system_prompt = _build_system_prompt()
    max_turns = _detect_max_turns(message)
    model = _detect_model(message)
    logger.info(f"Model routing: '{model}' for message: {message[:80]}")

    for attempt in range(2):
        try:
            prompt = system_prompt if attempt == 0 else _RETRY_SYSTEM_PROMPT
            raw = _call_claude(message, prompt, model, max_turns)
            if raw:
                return _handle_response(raw, message, source)
            if attempt == 0:
                logger.warning("Empty response, retrying with minimal prompt")
                continue
            reply = "I'm having trouble right now. Try again in a moment."
            save_message("assistant", reply, source)
            return {"action": "reply", "message": reply}

        except subprocess.TimeoutExpired:
            if attempt == 0:
                logger.warning("Claude timed out (30s), retrying with minimal prompt")
                continue
            reply = "I'm taking too long to respond. Try a shorter message?"
            save_message("assistant", reply, source)
            return {"action": "reply", "message": reply}
        except FileNotFoundError:
            reply = "Claude CLI not found."
            save_message("assistant", reply, source)
            return {"action": "reply", "message": reply}
        except Exception as e:
            logger.error(f"NaviCore ask_sync error: {type(e).__name__}")
            if attempt == 0:
                continue
            reply = "Something went wrong on my end. Try again?"
            save_message("assistant", reply, source)
            return {"action": "reply", "message": reply}

    reply = "I couldn't process that. Try again?"
    save_message("assistant", reply, source)
    return {"action": "reply", "message": reply}


_RETRY_SYSTEM_PROMPT = (
    'You are Navaia\'s AI assistant. Respond with JSON: '
    '{"action": "reply", "message": "your reply"}. Be concise.'
)


async def ask_async(message: str, source: str = "telegram") -> dict:
    """Async Claude call — used by Telegram bot (asyncio subprocess).

    On timeout or empty response, retries once with a minimal prompt.
    """
    save_message("user", message, source)
    system_prompt = _build_system_prompt()
    max_turns = _detect_max_turns(message)
    model = _detect_model(message)
    logger.info(f"Model routing: '{model}' for message: {message[:80]}")

    for attempt in range(2):
        try:
            prompt = system_prompt if attempt == 0 else _RETRY_SYSTEM_PROMPT
            raw = await _call_claude_async(message, prompt, model, max_turns)
            if raw:
                return _handle_response(raw, message, source)
            if attempt == 0:
                logger.warning("Empty response, retrying with minimal prompt")
                continue
            reply = "I'm having trouble right now. Try again in a moment."
            save_message("assistant", reply, source)
            return {"action": "reply", "message": reply}

        except asyncio.TimeoutError:
            if attempt == 0:
                logger.warning("Claude timed out (30s), retrying with minimal prompt")
                continue
            reply = "I'm taking too long to respond. Try a shorter message?"
            save_message("assistant", reply, source)
            return {"action": "reply", "message": reply}
        except FileNotFoundError:
            reply = "My AI brain isn't connected right now."
            save_message("assistant", reply, source)
            return {"action": "reply", "message": reply}
        except Exception as e:
            logger.error(f"NaviCore ask_async error: {type(e).__name__}")
            if attempt == 0:
                continue
            reply = "Something went wrong on my end. Try again?"
            save_message("assistant", reply, source)
            return {"action": "reply", "message": reply}

    reply = "I couldn't process that. Try again?"
    save_message("assistant", reply, source)
    return {"action": "reply", "message": reply}
