#!/usr/bin/env python3
"""
Navaia Crew HQ — AI Agent Control Center
Zero-dependency Python web server with SSE for real-time updates.
"""

import json
import os
import subprocess
import sys
import time
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path

# Add tools/ to import path for navi_core
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from navi_core import (
    save_message as navi_save_message,
    load_history as navi_load_history,
    ask_sync as navi_ask_sync,
    create_task as navi_create_task,
)

# ── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = Path(__file__).resolve().parent
STATIC_DIR = DASHBOARD_DIR / "static"
AGENTS_JSON = DASHBOARD_DIR / "agents.json"

WORKSPACE = REPO_ROOT / "workspace"
TASKS_DIR = WORKSPACE / "tasks"
INBOX_DIR = TASKS_DIR / "inbox"
ACTIVE_DIR = TASKS_DIR / "active"
DONE_DIR = TASKS_DIR / "done"
BLOCKED_DIR = TASKS_DIR / "blocked"
REJECTED_DIR = TASKS_DIR / "rejected"
OUTPUTS_DIR = WORKSPACE / "outputs"
COMMS_DIR = WORKSPACE / "comms"
TO_FOUNDER_DIR = COMMS_DIR / "to-manager"
FROM_FOUNDER_DIR = COMMS_DIR / "from-manager"
INTER_AGENT_DIR = COMMS_DIR / "inter-agent"
CHAT_LOG = DASHBOARD_DIR / "chat_history.jsonl"
FAILED_DIR = TASKS_DIR / "failed"

# Trello config from env
TRELLO_KEY = os.getenv("TRELLO_KEY", "")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN", "")
TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID", "")

# ── Agent Config ─────────────────────────────────────────────────────────────

DEFAULT_AGENTS = [
    {"id": "pm", "name": "Navi", "role": "PM", "model": "sonnet", "color": "#4a9eff",
     "task_dir": "workspace/tasks/inbox", "extra_dirs": ["workspace/tasks/active", "workspace/comms/from-manager"]},
    {"id": "creative", "name": "Muse", "role": "Creative", "model": "sonnet", "color": "#ff8c42",
     "task_dir": "workspace/tasks/creative"},
    {"id": "technical", "name": "Arch", "role": "Technical", "model": "sonnet", "color": "#a855f7",
     "task_dir": "workspace/tasks/technical"},
    {"id": "admin", "name": "Sage", "role": "Admin", "model": "haiku", "color": "#22c55e",
     "task_dir": "workspace/tasks/admin"},
]


def load_agents():
    if AGENTS_JSON.exists():
        try:
            return json.loads(AGENTS_JSON.read_text())
        except Exception:
            pass
    return DEFAULT_AGENTS


def save_agents(agents):
    AGENTS_JSON.write_text(json.dumps(agents, indent=2))


# ── Activity Log ─────────────────────────────────────────────────────────────

activity_log = []
MAX_LOG = 100


def log_activity(event_type, message, agent=None):
    entry = {
        "time": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "message": message,
        "agent": agent,
    }
    activity_log.append(entry)
    if len(activity_log) > MAX_LOG:
        activity_log.pop(0)
    return entry


# ── Chat History (delegated to NaviCore) ─────────────────────────────────────


# ── Agent State Detection ────────────────────────────────────────────────────

def get_agent_state(agent):
    agent_id = agent["id"]
    task_dir = REPO_ROOT / agent.get("task_dir", f"workspace/tasks/{agent_id}")
    extra_dirs = agent.get("extra_dirs", [])

    # Count pending tasks across primary + extra dirs
    task_count = count_files(task_dir)
    for ed in extra_dirs:
        task_count += count_files(REPO_ROOT / ed)

    # Check if agent-loop.sh is running for this agent
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"agent-loop.sh {agent_id}"],
            capture_output=True, text=True, timeout=3
        )
        loop_running = result.returncode == 0 and result.stdout.strip()
    except Exception:
        loop_running = False

    if not loop_running and agent_id == "pm":
        try:
            result = subprocess.run(
                ["pgrep", "-f", "loop.sh"],
                capture_output=True, text=True, timeout=3
            )
            loop_running = result.returncode == 0 and result.stdout.strip()
        except Exception:
            pass

    # Check per-agent lock file (set by agent-loop.sh when claude is active)
    lock_file = Path(f"/tmp/navaia-{agent_id}-working")
    if lock_file.exists():
        return "WORKING"

    # Tasks queued → agent should appear active even if loop isn't running
    if task_count > 0:
        return "WORKING" if loop_running else "STARTING"

    if not loop_running:
        return "OFFLINE"

    return "IDLE"


def count_files(directory):
    if not directory.exists():
        return 0
    return len([f for f in directory.iterdir() if f.is_file() and f.name != ".gitkeep"])


def get_current_task(agent):
    """Get the most recent task file for an agent."""
    agent_id = agent["id"]
    if agent_id == "pm":
        dirs = [INBOX_DIR, ACTIVE_DIR]
    else:
        dirs = [REPO_ROOT / f"workspace/tasks/{agent_id}"]

    for d in dirs:
        if not d.exists():
            continue
        files = sorted(
            [f for f in d.iterdir() if f.is_file() and f.name != ".gitkeep"],
            key=lambda f: f.stat().st_mtime, reverse=True
        )
        if files:
            try:
                content = files[0].read_text(encoding="utf-8")
                for line in content.split("\n"):
                    if line.startswith("## TASK:"):
                        return line.replace("## TASK:", "").strip()
                    if line.strip() and not line.startswith("**") and not line.startswith("---"):
                        return line.strip()[:80]
            except Exception:
                return files[0].name
    return None


# ── Trello ───────────────────────────────────────────────────────────────────

_trello_cache = {"data": None, "time": 0}


def trello_enabled():
    return bool(TRELLO_KEY and TRELLO_TOKEN and TRELLO_BOARD_ID)


def trello_api(method, endpoint, params=None):
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
    except Exception:
        return {}


def get_trello_board():
    now = time.time()
    if _trello_cache["data"] and now - _trello_cache["time"] < 10:
        return _trello_cache["data"]

    if not trello_enabled():
        return {"enabled": False, "lists": []}

    lists_data = trello_api("GET", f"boards/{TRELLO_BOARD_ID}/lists")
    if not isinstance(lists_data, list):
        return {"enabled": True, "lists": [], "error": "Could not fetch board"}

    board = {"enabled": True, "lists": []}
    label_colors = {"PM": "#4a9eff", "Creative": "#ff8c42", "Technical": "#a855f7", "Admin": "#22c55e"}

    for lst in lists_data:
        cards_data = trello_api("GET", f"lists/{lst['id']}/cards")
        cards = []
        if isinstance(cards_data, list):
            for c in cards_data:
                labels = []
                for lbl in c.get("labels", []):
                    labels.append({
                        "name": lbl.get("name", ""),
                        "color": label_colors.get(lbl.get("name", ""), "#666")
                    })
                cards.append({
                    "id": c["id"],
                    "name": c["name"],
                    "desc": c.get("desc", "")[:200],
                    "labels": labels,
                    "due": c.get("due"),
                    "url": c.get("shortUrl", ""),
                })
        board["lists"].append({
            "id": lst["id"],
            "name": lst["name"],
            "cards": cards,
        })

    _trello_cache["data"] = board
    _trello_cache["time"] = now
    return board


# ── Output Files ─────────────────────────────────────────────────────────────

def get_outputs():
    agent_names = {"creative": "Muse", "technical": "Arch", "admin": "Sage", "pm": "Navi"}
    outputs = []
    if not OUTPUTS_DIR.exists():
        return outputs
    for f in OUTPUTS_DIR.rglob("*"):
        if f.is_file() and f.name != ".gitkeep":
            rel = f.relative_to(OUTPUTS_DIR)
            agent_folder = rel.parts[0] if rel.parts else "unknown"
            stat = f.stat()
            outputs.append({
                "path": str(rel),
                "name": f.name,
                "agent": agent_names.get(agent_folder, agent_folder),
                "agent_id": agent_folder,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
    outputs.sort(key=lambda x: x["modified"], reverse=True)
    return outputs


def read_output_file(rel_path):
    filepath = OUTPUTS_DIR / rel_path
    if not filepath.exists() or not filepath.is_file():
        return None
    # Security: ensure path doesn't escape outputs dir
    try:
        filepath.resolve().relative_to(OUTPUTS_DIR.resolve())
    except ValueError:
        return None
    return filepath.read_text(encoding="utf-8", errors="replace")


# ── Inter-Agent Communication ────────────────────────────────────────────────

_last_comms_check = {"time": 0, "files": set()}


def check_inter_agent_comms():
    if not INTER_AGENT_DIR.exists():
        return []
    now = time.time()
    events = []
    current_files = set()
    for f in INTER_AGENT_DIR.iterdir():
        if f.is_file() and f.name != ".gitkeep":
            current_files.add(f.name)
            if f.name not in _last_comms_check["files"]:
                # Parse filename: {from}-to-{to}-{topic}.md
                parts = f.stem.split("-to-")
                if len(parts) == 2:
                    sender = parts[0]
                    rest = parts[1].split("-", 1)
                    receiver = rest[0]
                    topic = rest[1] if len(rest) > 1 else "message"
                    try:
                        content = f.read_text(encoding="utf-8")[:200]
                    except Exception:
                        content = ""
                    events.append({
                        "from": sender,
                        "to": receiver,
                        "topic": topic,
                        "preview": content,
                    })
    _last_comms_check["files"] = current_files
    _last_comms_check["time"] = now
    return events


# ── Full State ───────────────────────────────────────────────────────────────

def get_full_state():
    agents = load_agents()
    agent_states = []
    for agent in agents:
        state = get_agent_state(agent)
        current_task = get_current_task(agent) if state in ("WORKING", "STARTING") else None
        task_dir = REPO_ROOT / agent.get("task_dir", f"workspace/tasks/{agent['id']}")
        agent_states.append({
            **agent,
            "state": state,
            "current_task": current_task,
            "task_count": count_files(task_dir),
        })

    # Task counts
    tasks = {
        "inbox": count_files(INBOX_DIR),
        "active": count_files(ACTIVE_DIR),
        "done": count_files(DONE_DIR),
        "blocked": count_files(BLOCKED_DIR),
        "rejected": count_files(REJECTED_DIR),
    }

    # Integration status
    telegram_running = False
    try:
        result = subprocess.run(
            ["pgrep", "-f", "telegram_bridge"],
            capture_output=True, text=True, timeout=3
        )
        telegram_running = result.returncode == 0
    except Exception:
        pass

    integrations = {
        "telegram": telegram_running,
        "trello": trello_enabled(),
        "github": (REPO_ROOT / ".git").exists(),
    }

    # Inter-agent comms
    comms = check_inter_agent_comms()
    if comms:
        for c in comms:
            log_activity("comms", f"{c['from']} → {c['to']}: {c['topic']}", c["from"])

    return {
        "agents": agent_states,
        "tasks": tasks,
        "integrations": integrations,
        "activity": activity_log[-30:],
        "comms": comms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── SSE ──────────────────────────────────────────────────────────────────────

sse_clients = []


def sse_broadcast(event_type, data):
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    dead = []
    for client in sse_clients:
        try:
            client.wfile.write(msg.encode())
            client.wfile.flush()
        except Exception:
            dead.append(client)
    for c in dead:
        sse_clients.remove(c)


def sse_monitor():
    """Background thread that broadcasts state changes every 2s."""
    prev_state = None
    while True:
        try:
            state = get_full_state()
            state_str = json.dumps(state)
            if state_str != prev_state and sse_clients:
                sse_broadcast("state", state)
                prev_state = state_str
            time.sleep(2)
        except Exception:
            time.sleep(5)


# ── Chat via NaviCore ────────────────────────────────────────────────────────
# All chat logic is now in tools/navi_core.py (shared with Telegram bot)


# ── Task Creation ────────────────────────────────────────────────────────────

def create_task(agent_id, title, description):
    """Create a task file for a specific agent."""
    agents = load_agents()
    agent = next((a for a in agents if a["id"] == agent_id), None)

    if agent_id == "pm":
        target_dir = INBOX_DIR
    else:
        target_dir = REPO_ROOT / f"workspace/tasks/{agent_id}"

    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"{timestamp}-task.md"

    agent_name = agent["name"] if agent else agent_id
    content = f"""## TASK: {title}
**Time:** {datetime.now(timezone.utc).isoformat()}
**Source:** Dashboard (Manager)
**Assigned Agent:** {agent_name}
**Priority:** Standard

### Description
{description}
"""
    (target_dir / filename).write_text(content, encoding="utf-8")
    log_activity("task", f"Task assigned to {agent_name}: {title}", agent_id)

    # Also create Trello card if enabled
    if trello_enabled():
        label_map = {"pm": "PM", "creative": "Creative", "technical": "Technical", "admin": "Admin"}
        label = label_map.get(agent_id, "PM")
        list_id = None
        lists_data = trello_api("GET", f"boards/{TRELLO_BOARD_ID}/lists")
        if isinstance(lists_data, list):
            for l in lists_data:
                if l["name"] == "Inbox":
                    list_id = l["id"]
                    break
        if list_id:
            trello_api("POST", "cards", {"idList": list_id, "name": title, "desc": description})

    return filename


# ── Agent Management ─────────────────────────────────────────────────────────

AGENT_TEMPLATE = """# {name} ({role}) — Agent Config

> You are **{name}**, the {role} agent of Navaia's AI Workforce.

## Your Role
{role_description}

## Rules
1. Save all outputs to `workspace/outputs/{agent_id}/`
2. Report progress to the PM (Navi)
3. NEVER ask questions in the terminal — route through the PM
4. Update Trello via `tools/trello_api.sh` when you start/finish tasks
"""

ROLE_DESCRIPTIONS = {
    "PM": "Team lead. Route tasks, coordinate agents, QA outputs, communicate with the Manager.",
    "Creative": "Content, campaigns, outreach, brand, social media, pitch materials.",
    "Technical": "Code, deployments, infrastructure, APIs, GitHub, debugging.",
    "Admin": "Documents, proposals, research, finance tracking, compliance.",
    "Sales": "Sales materials, CRM, client outreach, proposals, follow-ups.",
    "Legal": "Contracts, compliance, legal research, policy documents.",
    "HR": "Hiring, onboarding, culture, team docs, performance tracking.",
    "Custom": "General-purpose agent. Customize this description.",
}


def create_agent(agent_id, name, role, model, color):
    agents = load_agents()
    if any(a["id"] == agent_id for a in agents):
        return False, "Agent ID already exists"

    # Create directories
    agent_dir = REPO_ROOT / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    task_dir = REPO_ROOT / f"workspace/tasks/{agent_id}"
    task_dir.mkdir(parents=True, exist_ok=True)
    output_dir = REPO_ROOT / f"workspace/outputs/{agent_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create CLAUDE.md
    role_desc = ROLE_DESCRIPTIONS.get(role, ROLE_DESCRIPTIONS["Custom"])
    claude_md = AGENT_TEMPLATE.format(
        name=name, role=role, agent_id=agent_id, role_description=role_desc
    )
    (agent_dir / "CLAUDE.md").write_text(claude_md, encoding="utf-8")

    # Add to agents list
    new_agent = {
        "id": agent_id,
        "name": name,
        "role": role,
        "model": model,
        "color": color,
        "task_dir": f"workspace/tasks/{agent_id}",
    }
    agents.append(new_agent)
    save_agents(agents)
    log_activity("config", f"Agent created: {name} ({role})", agent_id)
    return True, new_agent


def delete_agent(agent_id):
    if agent_id in ("pm", "creative", "technical", "admin"):
        return False, "Cannot delete core agents"
    agents = load_agents()
    agents = [a for a in agents if a["id"] != agent_id]
    save_agents(agents)
    log_activity("config", f"Agent removed: {agent_id}")
    return True, "Deleted"


# ── Per-Agent Task Management ────────────────────────────────────────────────


def get_agent_tasks(agent_id):
    """List pending tasks for an agent."""
    if agent_id == "pm":
        task_dir = INBOX_DIR
    else:
        task_dir = REPO_ROOT / f"workspace/tasks/{agent_id}"
    if not task_dir.exists():
        return []

    tasks = []
    for f in sorted(task_dir.iterdir(), key=lambda x: x.stat().st_mtime):
        if f.is_file() and f.name != ".gitkeep":
            try:
                content = f.read_text(encoding="utf-8")
                title = f.name
                for line in content.split("\n"):
                    if line.startswith("## TASK:"):
                        title = line.replace("## TASK:", "").strip()
                        break
                stat = f.stat()
                tasks.append({
                    "filename": f.name,
                    "title": title,
                    "preview": content[:300],
                    "size_kb": round(stat.st_size / 1024, 1),
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                })
            except Exception:
                tasks.append({"filename": f.name, "title": f.name, "preview": ""})
    return tasks


def read_agent_task(agent_id, filename):
    """Read a specific task file content."""
    if agent_id == "pm":
        task_dir = INBOX_DIR
    else:
        task_dir = REPO_ROOT / f"workspace/tasks/{agent_id}"

    filepath = task_dir / filename
    if not filepath.exists() or not filepath.is_file():
        return None
    try:
        filepath.resolve().relative_to(task_dir.resolve())
    except ValueError:
        return None
    return filepath.read_text(encoding="utf-8", errors="replace")


def cancel_agent_task(agent_id, filename):
    """Cancel a task by moving it to failed/ with cancellation metadata."""
    if agent_id == "pm":
        task_dir = INBOX_DIR
    else:
        task_dir = REPO_ROOT / f"workspace/tasks/{agent_id}"

    filepath = task_dir / filename
    if not filepath.exists() or not filepath.is_file():
        return False, "Task not found"
    try:
        filepath.resolve().relative_to(task_dir.resolve())
    except ValueError:
        return False, "Invalid path"

    FAILED_DIR.mkdir(parents=True, exist_ok=True)
    content = filepath.read_text(encoding="utf-8", errors="replace")
    content += f"\n\n---\n**Cancelled:** {datetime.now(timezone.utc).isoformat()}\n**Reason:** Cancelled by Manager via Dashboard\n"
    (FAILED_DIR / filename).write_text(content, encoding="utf-8")
    filepath.unlink()
    log_activity("task", f"Task cancelled: {filename}", agent_id)
    return True, "Task cancelled"


def reorder_agent_tasks(agent_id, filenames):
    """Reorder tasks by updating file modification times."""
    if agent_id == "pm":
        task_dir = INBOX_DIR
    else:
        task_dir = REPO_ROOT / f"workspace/tasks/{agent_id}"
    if not task_dir.exists():
        return False, "Task directory not found"

    base_time = time.time()
    for i, fname in enumerate(filenames):
        fpath = task_dir / fname
        if fpath.exists():
            try:
                fpath.resolve().relative_to(task_dir.resolve())
            except ValueError:
                continue
            os.utime(fpath, (base_time + i, base_time + i))
    return True, "Tasks reordered"


def get_agent_outputs(agent_id, limit=10):
    """List recent output files for an agent."""
    output_dir = OUTPUTS_DIR / agent_id
    if not output_dir.exists():
        return []

    files = sorted(
        [f for f in output_dir.iterdir() if f.is_file() and f.name != ".gitkeep"],
        key=lambda f: f.stat().st_mtime, reverse=True
    )[:limit]

    return [{
        "filename": f.name,
        "path": f"{agent_id}/{f.name}",
        "size_kb": round(f.stat().st_size / 1024, 1),
        "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
    } for f in files]


def get_agent_detail_status(agent_id):
    """Get detailed status: current task content, working duration, latest output."""
    agents = load_agents()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        return None

    state = get_agent_state(agent)
    current_task = get_current_task(agent) if state in ("WORKING", "STARTING") else None

    # Full content of current task
    current_task_content = None
    if agent_id == "pm":
        dirs = [INBOX_DIR, ACTIVE_DIR]
    else:
        dirs = [REPO_ROOT / f"workspace/tasks/{agent_id}"]

    for d in dirs:
        if not d.exists():
            continue
        files = sorted(
            [f for f in d.iterdir() if f.is_file() and f.name != ".gitkeep"],
            key=lambda f: f.stat().st_mtime, reverse=True
        )
        if files:
            try:
                current_task_content = files[0].read_text(encoding="utf-8")[:2000]
            except Exception:
                pass
            break

    # Working duration from lock file
    lock_file = Path(f"/tmp/navaia-{agent_id}-working")
    duration_seconds = None
    if lock_file.exists():
        duration_seconds = int(time.time() - lock_file.stat().st_mtime)

    # Latest output preview
    output_dir = OUTPUTS_DIR / agent_id
    latest_output = None
    if output_dir.exists():
        output_files = sorted(
            [f for f in output_dir.iterdir() if f.is_file() and f.name != ".gitkeep"],
            key=lambda f: f.stat().st_mtime, reverse=True
        )
        if output_files:
            try:
                latest_output = {
                    "filename": output_files[0].name,
                    "preview": output_files[0].read_text(encoding="utf-8")[:500],
                    "modified": datetime.fromtimestamp(
                        output_files[0].stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                }
            except Exception:
                pass

    task_dir = REPO_ROOT / agent.get("task_dir", f"workspace/tasks/{agent_id}")
    return {
        **agent,
        "state": state,
        "current_task": current_task,
        "current_task_content": current_task_content,
        "duration_seconds": duration_seconds,
        "latest_output": latest_output,
        "task_count": count_files(task_dir),
    }


# ── Per-Agent Chat ───────────────────────────────────────────────────────────


def _agent_chat_log(agent_id):
    return DASHBOARD_DIR / f"chat_{agent_id}_history.jsonl"


def save_agent_message(agent_id, role, text):
    """Save a chat message for a specific agent."""
    chat_log = _agent_chat_log(agent_id)
    msg = {
        "role": role,
        "text": text,
        "time": datetime.now(timezone.utc).isoformat(),
    }
    chat_log.parent.mkdir(parents=True, exist_ok=True)
    with open(chat_log, "a") as f:
        f.write(json.dumps(msg) + "\n")
    return msg


def load_agent_chat_history(agent_id, limit=50):
    """Load last N chat messages for a specific agent."""
    chat_log = _agent_chat_log(agent_id)
    if not chat_log.exists():
        return []
    try:
        lines = chat_log.read_text(encoding="utf-8").strip().split("\n")
        messages = []
        for line in lines[-limit:]:
            if line.strip():
                messages.append(json.loads(line))
        return messages
    except Exception:
        return []


def agent_chat(agent_id, message):
    """Chat with a specific agent using their CLAUDE.md as context."""
    agents = load_agents()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        return {"error": "Agent not found"}

    save_agent_message(agent_id, "user", message)

    # Load agent's CLAUDE.md for context
    agent_claude_md = REPO_ROOT / "agents" / agent_id / "CLAUDE.md"
    agent_context = ""
    if agent_claude_md.exists():
        try:
            agent_context = agent_claude_md.read_text(encoding="utf-8")[:3000]
        except Exception:
            pass

    # Build conversation context
    recent = load_agent_chat_history(agent_id, 5)
    conv = "\n".join(
        f"{'Manager' if m['role'] == 'user' else agent['name']}: {m['text'][:150]}"
        for m in recent
    ) or "No previous messages."

    system_prompt = (
        f"You are {agent['name']}, the {agent['role']} agent of Navaia's AI Workforce.\n\n"
        f"{agent_context}\n\n"
        "You are chatting directly with the Manager (CEO). Be concise and helpful.\n"
        'RESPOND WITH JSON: {"message": "your response"}\n\n'
        f"Recent conversation:\n{conv}"
    )

    model = agent.get("model", "sonnet")

    try:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        proc = subprocess.run(
            ["claude", "-p",
             "--model", model,
             "--max-turns", "1",
             "--output-format", "text",
             "--system-prompt", system_prompt,
             "--", message],
            capture_output=True, text=True, timeout=30,
            env=env, cwd=str(REPO_ROOT),
        )
        raw = proc.stdout.strip() or proc.stderr.strip()
        if not raw:
            reply = "I'm having trouble responding right now."
        else:
            try:
                json_str = raw
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    parts = json_str.split("```")
                    if len(parts) >= 3:
                        json_str = parts[1].strip()
                result = json.loads(json_str)
                reply = result.get("message", raw[:2000])
            except (json.JSONDecodeError, ValueError):
                reply = raw[:2000]
    except subprocess.TimeoutExpired:
        reply = "I'm taking too long. Try again?"
    except FileNotFoundError:
        reply = "Claude CLI not available."
    except Exception:
        reply = "Something went wrong. Try again?"

    save_agent_message(agent_id, "assistant", reply)
    log_activity("chat", f"Chat with {agent['name']}: {message[:40]}", agent_id)
    return {"message": reply}


# ── HTTP Handler ─────────────────────────────────────────────────────────────

MIME_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
}

# Page routes to HTML files
PAGE_ROUTES = {
    "/": "index.html",
    "/office": "office.html",
    "/board": "board.html",
    "/outputs": "outputs.html",
    "/settings": "settings.html",
    "/chat": "chat.html",
}


class CrewHQHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default logging for SSE keep-alives
        if "/api/events" not in str(args):
            print(f"[CrewHQ] {args[0]}" if args else "")

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text, content_type="text/plain", status=200):
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        from urllib.parse import unquote
        path = unquote(self.path.split("?")[0])

        # Page routes
        if path in PAGE_ROUTES:
            filepath = STATIC_DIR / PAGE_ROUTES[path]
            if filepath.exists():
                self.send_text(filepath.read_text(encoding="utf-8"), "text/html")
                return
            self.send_error(404)
            return

        # Static files
        if path.startswith("/static/"):
            rel = path[8:]  # strip /static/
            filepath = STATIC_DIR / rel
            try:
                filepath.resolve().relative_to(STATIC_DIR.resolve())
            except ValueError:
                self.send_error(403)
                return
            if filepath.exists() and filepath.is_file():
                ext = filepath.suffix.lower()
                ct = MIME_TYPES.get(ext, "application/octet-stream")
                # Binary files (images etc.)
                if ext in (".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp"):
                    body = filepath.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Length", len(body))
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_text(filepath.read_text(encoding="utf-8"), ct)
                return
            self.send_error(404)
            return

        # API endpoints
        if path == "/api/state":
            self.send_json(get_full_state())
            return

        if path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            sse_clients.append(self)
            # Send initial state
            state = get_full_state()
            msg = f"event: state\ndata: {json.dumps(state)}\n\n"
            self.wfile.write(msg.encode())
            self.wfile.flush()
            # Keep connection alive
            try:
                while True:
                    time.sleep(30)
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except Exception:
                if self in sse_clients:
                    sse_clients.remove(self)
            return

        if path == "/api/trello":
            self.send_json(get_trello_board())
            return

        if path == "/api/outputs":
            self.send_json(get_outputs())
            return

        if path.startswith("/api/output/"):
            rel_path = urllib.parse.unquote(path[12:])
            content = read_output_file(rel_path)
            if content is not None:
                self.send_json({"content": content, "path": rel_path})
            else:
                self.send_json({"error": "File not found"}, 404)
            return

        if path == "/api/activity":
            self.send_json(activity_log[-50:])
            return

        if path == "/api/agents":
            self.send_json(load_agents())
            return

        if path == "/api/chat/history":
            self.send_json(navi_load_history(50))
            return

        if path == "/api/tasks":
            try:
                from task_db import TaskDB
                db = TaskDB()
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                status = qs.get("status", [None])[0]
                agent = qs.get("agent", [None])[0]
                limit = int(qs.get("limit", ["50"])[0])
                tasks = db.get_tasks(status=status, agent=agent, limit=limit)
                self.send_json(tasks)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        if path == "/api/tasks/stats":
            try:
                from task_db import TaskDB
                db = TaskDB()
                self.send_json(db.get_agent_stats())
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        if path == "/api/tokens":
            try:
                from token_tracker import TokenTracker
                tracker = TokenTracker()
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                days = int(qs.get("days", ["7"])[0])
                self.send_json({
                    "summary": tracker.get_summary(days),
                    "agents": tracker.get_agent_breakdown(days),
                    "top_consumers": tracker.get_top_consumers(days),
                    "daily": tracker.get_daily_usage(days),
                    "tips": tracker.get_optimization_tips(days),
                })
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        # ── Agent Detail API ─────────────────────────────────
        if path.startswith("/api/agent/"):
            rest = path[11:]  # after "/api/agent/"
            parts = rest.split("/", 1)
            agent_id = parts[0]
            subpath = parts[1] if len(parts) > 1 else ""

            if subpath == "tasks":
                self.send_json(get_agent_tasks(agent_id))
                return

            if subpath.startswith("task/"):
                filename = urllib.parse.unquote(subpath[5:])
                content = read_agent_task(agent_id, filename)
                if content is not None:
                    self.send_json({"content": content, "filename": filename})
                else:
                    self.send_json({"error": "Task not found"}, 404)
                return

            if subpath == "outputs":
                self.send_json(get_agent_outputs(agent_id))
                return

            if subpath.startswith("output/"):
                filename = urllib.parse.unquote(subpath[7:])
                rel_path = f"{agent_id}/{filename}"
                content = read_output_file(rel_path)
                if content is not None:
                    self.send_json({"content": content, "filename": filename})
                else:
                    self.send_json({"error": "Output not found"}, 404)
                return

            if subpath == "chat/history":
                self.send_json(load_agent_chat_history(agent_id))
                return

            if subpath == "status":
                status = get_agent_detail_status(agent_id)
                if status:
                    self.send_json(status)
                else:
                    self.send_json({"error": "Agent not found"}, 404)
                return

        self.send_error(404)

    def do_POST(self):
        path = self.path.split("?")[0]
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON"}, 400)
            return

        if path == "/api/task":
            agent_id = data.get("agent", "pm")
            title = data.get("title", "")
            description = data.get("description", "")
            if not title:
                self.send_json({"error": "Title required"}, 400)
                return
            filename = create_task(agent_id, title, description)
            self.send_json({"ok": True, "file": filename})
            return

        if path == "/api/agents":
            agent_id = data.get("id", "").lower().replace(" ", "-")
            name = data.get("name", "")
            role = data.get("role", "Custom")
            model = data.get("model", "sonnet")
            color = data.get("color", "#666666")
            if not agent_id or not name:
                self.send_json({"error": "ID and name required"}, 400)
                return
            ok, result = create_agent(agent_id, name, role, model, color)
            if ok:
                self.send_json({"ok": True, "agent": result})
            else:
                self.send_json({"error": result}, 400)
            return

        if path == "/api/chat":
            message = data.get("message", "").strip()
            if not message:
                self.send_json({"error": "Message required"}, 400)
                return
            log_activity("chat", f"Manager: {message[:60]}", "pm")
            result = navi_ask_sync(message, "dashboard")
            reply_text = result.get("message", "")
            if result.get("action") == "create_task":
                log_activity("task", f"Task created: {result.get('task_title', '')}", "pm")
            log_activity("chat", f"Navi: {reply_text[:60]}", "pm")
            self.send_json(result)
            return

        # ── Agent Detail POST API ─────────────────────────────
        if path.startswith("/api/agent/"):
            rest = path[11:]
            parts = rest.split("/", 1)
            agent_id = parts[0]
            subpath = parts[1] if len(parts) > 1 else ""

            if subpath == "chat":
                message = data.get("message", "").strip()
                if not message:
                    self.send_json({"error": "Message required"}, 400)
                    return
                result = agent_chat(agent_id, message)
                self.send_json(result)
                return

            if subpath == "task/reorder":
                filenames = data.get("filenames", [])
                if not filenames:
                    self.send_json({"error": "Filenames required"}, 400)
                    return
                ok, msg = reorder_agent_tasks(agent_id, filenames)
                if ok:
                    self.send_json({"ok": True})
                else:
                    self.send_json({"error": msg}, 400)
                return

        self.send_json({"error": "Not found"}, 404)

    def do_DELETE(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/agents/"):
            agent_id = path[12:]
            ok, msg = delete_agent(agent_id)
            if ok:
                self.send_json({"ok": True})
            else:
                self.send_json({"error": msg}, 400)
            return

        # DELETE /api/agent/{id}/task/{filename}
        if path.startswith("/api/agent/"):
            rest = path[11:]
            parts = rest.split("/", 1)
            agent_id = parts[0]
            subpath = parts[1] if len(parts) > 1 else ""
            if subpath.startswith("task/"):
                filename = urllib.parse.unquote(subpath[5:])
                ok, msg = cancel_agent_task(agent_id, filename)
                if ok:
                    self.send_json({"ok": True})
                else:
                    self.send_json({"error": msg}, 404)
                return

        self.send_json({"error": "Not found"}, 404)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    port = int(os.getenv("CREW_HQ_PORT", "7777"))

    # Ensure directories exist
    for d in [INBOX_DIR, ACTIVE_DIR, DONE_DIR, BLOCKED_DIR, REJECTED_DIR,
              OUTPUTS_DIR, TO_FOUNDER_DIR, FROM_FOUNDER_DIR, INTER_AGENT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Start SSE monitor thread
    monitor = threading.Thread(target=sse_monitor, daemon=True)
    monitor.start()

    log_activity("system", "Crew HQ started")

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = ThreadedHTTPServer(("0.0.0.0", port), CrewHQHandler)
    print(f"""
╔══════════════════════════════════════════════╗
║                                              ║
║   ◈  NAVAIA CREW HQ  ◈                      ║
║   AI Agent Control Center                    ║
║                                              ║
║   http://localhost:{port}                      ║
║                                              ║
║   Pages:                                     ║
║     /        Command Center                  ║
║     /office  Pixel Office                    ║
║     /board   Trello Board                    ║
║     /outputs Output Browser                  ║
║     /chat    Chat with Navi                  ║
║     /settings Settings                       ║
║                                              ║
╚══════════════════════════════════════════════╝
""")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCrew HQ shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
