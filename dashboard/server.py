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
TO_FOUNDER_DIR = COMMS_DIR / "to-founder"
FROM_FOUNDER_DIR = COMMS_DIR / "from-founder"
INTER_AGENT_DIR = COMMS_DIR / "inter-agent"
CHAT_LOG = DASHBOARD_DIR / "chat_history.jsonl"

# Trello config from env
TRELLO_KEY = os.getenv("TRELLO_KEY", "")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN", "")
TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID", "")

# ── Agent Config ─────────────────────────────────────────────────────────────

DEFAULT_AGENTS = [
    {"id": "pm", "name": "Navi", "role": "PM", "model": "sonnet", "color": "#4a9eff",
     "task_dir": "workspace/tasks/inbox", "extra_dirs": ["workspace/tasks/active", "workspace/comms/from-founder"]},
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

    # Check if agent-loop.sh is running for this agent
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"agent-loop.sh {agent_id}"],
            capture_output=True, text=True, timeout=3
        )
        loop_running = result.returncode == 0 and result.stdout.strip()
    except Exception:
        loop_running = False

    if not loop_running:
        # Also check for the main loop.sh for PM
        if agent_id == "pm":
            try:
                result = subprocess.run(
                    ["pgrep", "-f", "loop.sh"],
                    capture_output=True, text=True, timeout=3
                )
                loop_running = result.returncode == 0 and result.stdout.strip()
            except Exception:
                pass

    if not loop_running:
        return "OFFLINE"

    # Check per-agent lock file (set by agent-loop.sh when claude is active)
    lock_file = Path(f"/tmp/navaia-{agent_id}-working")
    if lock_file.exists():
        return "WORKING"

    # Loop running but no claude
    task_count = count_files(task_dir)
    if task_count > 0:
        return "STARTING"

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
**Source:** Dashboard (Founder)
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
    "PM": "Team lead. Route tasks, coordinate agents, QA outputs, communicate with the Founder.",
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
            log_activity("chat", f"Founder: {message[:60]}", "pm")
            result = navi_ask_sync(message, "dashboard")
            reply_text = result.get("message", "")
            if result.get("action") == "create_task":
                log_activity("task", f"Task created: {result.get('task_title', '')}", "pm")
            log_activity("chat", f"Navi: {reply_text[:60]}", "pm")
            self.send_json(result)
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
